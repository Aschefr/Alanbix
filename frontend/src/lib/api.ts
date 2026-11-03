import { get } from 'svelte/store';
import { authStore } from './auth';
import { API_URL, resolveApiUrl, isDemoMode } from './config';
import { handleDemoRequest } from './demoData';

// --- Session: renewed while the app is used, so only inactivity logs out ---
const SESSION_EXPIRED_FLAG = 'alanbix_session_expired';
const RENEW_AFTER_SECONDS = 3600;

/** The token's claims (exp, iat in seconds), or null if it cannot be read. */
export function tokenClaims(token: string | null): { exp?: number; iat?: number } | null {
	try {
		const part = token?.split('.')[1];
		return part ? JSON.parse(atob(part.replace(/-/g, '+').replace(/_/g, '/'))) : null;
	} catch {
		return null;
	}
}

/** Log out because the session ran out; the login screen then says so. */
export function expireSession() {
	try { sessionStorage.setItem(SESSION_EXPIRED_FLAG, '1'); } catch {}
	authStore.logout();
}

/** True once, on the login screen, after a session ran out. */
export function takeSessionExpired(): boolean {
	try {
		const expired = sessionStorage.getItem(SESSION_EXPIRED_FLAG) === '1';
		sessionStorage.removeItem(SESSION_EXPIRED_FLAG);
		return expired;
	} catch {
		return false;
	}
}

let renewing = false;
function renewSessionIfOld(token: string, baseUrl: string) {
	const iat = tokenClaims(token)?.iat ?? 0;
	if (renewing || Date.now() / 1000 - iat < RENEW_AFTER_SECONDS) return;
	renewing = true;
	fetch(`${baseUrl}/token/refresh`, { method: 'POST', headers: { Authorization: `Bearer ${token}` }, credentials: 'omit' })
		.then(r => (r.ok ? r.json() : null))
		.then(data => {
			// Keep the new session only if the player is still the one logged in
			if (data?.access_token && get(authStore) === token) authStore.login(data.access_token);
		})
		.catch(() => {})
		.finally(() => { renewing = false; });
}

async function request(path: string, options: RequestInit = {}) {
	if (isDemoMode()) {
		return handleDemoRequest(path, options.method || 'GET', options.body);
	}

	const token = get(authStore);
	const baseUrl = resolveApiUrl() || API_URL;

	const headers = new Headers(options.headers || {});
	if (token) {
		headers.set('Authorization', `Bearer ${token}`);
	}

	const response = await fetch(`${baseUrl}${path}`, {
		...options,
		headers,
		credentials: 'omit' // Use omit for '*' origins with credentials:True
	});


	if (response.status === 401) {
		if (token) expireSession();
	} else if (response.ok && token) {
		renewSessionIfOld(token, baseUrl);
	}

	if (!response.ok) {
		const error = await response.json().catch(() => ({ detail: 'Unknown error' }));
		const errMsg = typeof error.detail === 'object' ? (error.detail.message || 'Request failed') : (error.detail || 'Request failed');
		const errObj: any = new Error(errMsg);
		if (typeof error.detail === 'object') {
			Object.assign(errObj, error.detail);
		}
		throw errObj;
	}

	return response.json();
}

export const api = {
	get: (path: string) => request(path),
	post: (path: string, data: any) => request(path, {
		method: 'POST',
		headers: { 'Content-Type': 'application/json' },
		body: JSON.stringify(data)
	}),
	put: (path: string, data: any) => request(path, {
		method: 'PUT',
		headers: { 'Content-Type': 'application/json' },
		body: JSON.stringify(data)
	}),
	patch: (path: string, data: any) => request(path, {
		method: 'PATCH',
		headers: { 'Content-Type': 'application/json' },
		body: JSON.stringify(data)
	}),
	delete: (path: string) => request(path, {
		method: 'DELETE'
	}),
	upload: (path: string, formData: FormData) => request(path, {
		method: 'POST',
		body: formData
		// No Content-Type header — browser sets multipart boundary automatically
	}),
	login: async (username: string, password: string) => {
		if (isDemoMode() || username.trim().toLowerCase() === 'demo') {
			const demoRes = handleDemoRequest('/token', 'POST', { username });
			authStore.login(demoRes.access_token);
			return demoRes;
		}

		const formData = new URLSearchParams();
		formData.append('username', username);
		formData.append('password', password);

		const baseUrl = resolveApiUrl() || API_URL;
		const data = await fetch(`${baseUrl}/token`, {
			method: 'POST',
			headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
			body: formData
		}).then(async res => {
			if (!res.ok) {
				// The login page turns the status into a translated message
				const err: any = new Error(`login ${res.status}`); // i18n-ignore
				err.status = res.status;
				err.retryAfter = Number(res.headers.get('Retry-After')) || 0;
				throw err;
			}
			return res.json();
		});

		authStore.login(data.access_token);
		return data;
	}
};
