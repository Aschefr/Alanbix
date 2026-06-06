/**
 * Central configuration for API/WebSocket URLs.
 *
 * In production (standalone Docker), the frontend and backend share the same origin,
 * so we use relative paths (empty string).
 * In development (Vite), they run on different ports, so we use localhost:8000.
 */

function resolveApiUrl(): string {
	// In development, the Vite dev server runs on 5173 but API is on 8000
	if (import.meta.env.DEV) {
		return 'http://localhost:8000';
	}

	// In production (the unified Docker container), API is served from the same origin
	// Returning an empty string makes all fetch requests relative to the current host:port
	return '';
}

export const API_URL = resolveApiUrl();

// For WebSockets, we need absolute URLs, so if API_URL is empty, we construct it from window.location
function resolveWsUrl(): string {
	if (import.meta.env.DEV) {
		return 'ws://localhost:8000/ws';
	}
	
	if (typeof window !== 'undefined') {
		const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
		return `${protocol}//${window.location.host}/ws`;
	}
	return 'ws://localhost:8000/ws';
}

export const WS_URL = resolveWsUrl();
