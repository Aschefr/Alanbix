import { get } from 'svelte/store';
import { authStore } from './auth';
import { API_URL } from './config';

async function request(path: string, options: RequestInit = {}) {
	const token = get(authStore);
	
	const headers = new Headers(options.headers || {});
	if (token) {
		headers.set('Authorization', `Bearer ${token}`);
	}

	const response = await fetch(`${API_URL}${path}`, {
		...options,
		headers,
		credentials: 'omit' // Use omit for '*' origins with credentials:True
	});


	if (response.status === 401) {
		authStore.logout();
	}

	if (!response.ok) {
		const error = await response.json().catch(() => ({ detail: 'Unknown error' }));
		throw new Error(error.detail || 'Request failed');
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
		const formData = new URLSearchParams();
		formData.append('username', username);
		formData.append('password', password);

		const data = await fetch(`${API_URL}/token`, {
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
