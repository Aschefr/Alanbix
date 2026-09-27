/**
 * Central configuration for API/WebSocket URLs.
 *
 * In production (standalone Docker), the frontend and backend share the same origin,
 * so we use relative paths (empty string).
 * In development (Vite), they run on different ports, so we use localhost:8000.
 */

function resolveApiUrl(): string {
	if (typeof window !== 'undefined') {
		const hostname = window.location.hostname;
		const port = window.location.port;

		// When running in development mode (e.g. Vite on port 41481 or 5173),
		// dynamically point to port 8000 on the same host (localhost or current LAN IP)
		if (port === '41481' || port === '5173') {
			return `http://${hostname}:8000`;
		}
	}

	// 1. If an explicit VITE_API_URL is provided in the environment, use it.
	const envApiUrl = import.meta.env.VITE_API_URL;
	if (envApiUrl && envApiUrl !== 'undefined') {
		return envApiUrl;
	}

	// In development fallback
	if (import.meta.env.DEV) {
		if (typeof window !== 'undefined') {
			const hostname = window.location.hostname;
			return `http://${hostname}:8000`;
		}
		return 'http://localhost:8000';
	}

	// In production (the unified Docker container), API is served from the same origin
	return '';
}

export const API_URL = resolveApiUrl();

// For WebSockets, we need absolute URLs
function resolveWsUrl(): string {
	if (typeof window !== 'undefined') {
		const hostname = window.location.hostname;
		const port = window.location.port;
		const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';

		// When running in development mode (port 41481 or 5173),
		// dynamically connect to WebSocket on port 8000 of the current host
		if (port === '41481' || port === '5173') {
			return `${protocol}//${hostname}:8000/ws`;
		}

		return `${protocol}//${window.location.host}/ws`;
	}

	return 'ws://localhost:8000/ws';
}

export const WS_URL = resolveWsUrl();

