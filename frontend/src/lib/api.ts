import { get } from 'svelte/store';
import { authStore } from './auth';
import { API_URL, resolveApiUrl, isDemoMode } from './config';
import { handleDemoRequest } from './demoData';

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
		authStore.logout();
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
		}).then(res => {
			if (!res.ok) throw new Error('Identifiants invalides');
			return res.json();
		});

		authStore.login(data.access_token);
		return data;
	}
};
