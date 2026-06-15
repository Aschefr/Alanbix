/**
 * Central configuration for API/WebSocket URLs.
 *
 * In production (standalone Docker), the frontend and backend share the same origin,
 * so we use relative paths (empty string).
 * In development (Vite), they run on different ports, so we use localhost:8000.
 */

function resolveApiUrl(): string {
	// 1. If an explicit VITE_API_URL is provided in the environment, use it.
	const envApiUrl = import.meta.env.VITE_API_URL;
	if (envApiUrl && envApiUrl !== 'undefined') {
		return envApiUrl;
	}

	// In development, the Vite dev server runs on 5173 but API is on 8000
	if (import.meta.env.DEV) {
		if (typeof window !== 'undefined') {
			const hostname = window.location.hostname;
			if (hostname !== 'localhost' && hostname !== '127.0.0.1') {
				return `http://${hostname}:8000`;
			}
		}
		return 'http://localhost:8000';
	}

	// In production (the unified Docker container), API is served from the same origin
	// Returning an empty string makes all fetch requests relative to the current host:port
	return '';
}

export const API_URL = resolveApiUrl();

// For WebSockets, we need absolute URLs, so if API_URL is empty, we construct it from window.location
function resolveWsUrl(): string {
	// 1. If VITE_API_URL is set, we can derive the WebSocket URL from it.
	const envApiUrl = import.meta.env.VITE_API_URL;
	if (envApiUrl && envApiUrl !== 'undefined') {
		try {
			const url = new URL(envApiUrl);
			const protocol = url.protocol === 'https:' ? 'wss:' : 'ws:';
			return `${protocol}//${url.host}/ws`;
		} catch (e) {
			// Fallback: simple string replacement
			let wsUrl = envApiUrl.replace(/^http:/, 'ws:').replace(/^https:/, 'wss:');
			if (!wsUrl.endsWith('/ws')) {
				wsUrl = wsUrl.replace(/\/$/, '') + '/ws';
			}
			return wsUrl;
		}
	}

	if (import.meta.env.DEV) {
		if (typeof window !== 'undefined') {
			const hostname = window.location.hostname;
			if (hostname !== 'localhost' && hostname !== '127.0.0.1') {
				return `ws://${hostname}:8000/ws`;
			}
		}
		return 'ws://localhost:8000/ws';
	}
	
	if (typeof window !== 'undefined') {
		const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
		return `${protocol}//${window.location.host}/ws`;
	}
	return 'ws://localhost:8000/ws';
}

export const WS_URL = resolveWsUrl();
