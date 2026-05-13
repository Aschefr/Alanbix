import { writable } from 'svelte/store';

const TOKEN_KEY = 'alanbix_token';

function createAuthStore() {
	const initialToken = typeof window !== 'undefined' ? localStorage.getItem(TOKEN_KEY) : null;
	const { subscribe, set } = writable<string | null>(initialToken);

	return {
		subscribe,
		login: (token: string) => {
			localStorage.setItem(TOKEN_KEY, token);
			set(token);
		},
		logout: () => {
			localStorage.removeItem(TOKEN_KEY);
			set(null);
		}
	};
}

export const authStore = createAuthStore();
