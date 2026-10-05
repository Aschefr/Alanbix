/**
 * Central configuration for API/WebSocket URLs.
 *
 * In production (standalone Docker container on Unraid, Docker Hub, reverse proxies):
 * The frontend and backend share the exact same origin (host and port),
 * so API calls use relative URLs (empty string '') and WebSockets use window.location.host.
 *
 * In development (Vite dev server with HMR):
 * Frontend runs on Vite (e.g. port 5173 or container port 41481),
 * while FastAPI runs separately on port 8000.
 */

function resolveApiUrl(): string {
	// 1. In DEVELOPMENT mode only (vite dev), route to FastAPI on port 8000
	if (import.meta.env.DEV) {
		const envApiUrl = import.meta.env.VITE_API_URL;
		if (envApiUrl && envApiUrl !== 'undefined' && envApiUrl !== '') {
			return envApiUrl;
		}

		if (typeof window !== 'undefined') {
			const hostname = window.location.hostname;
			return `http://${hostname}:8000`;
		}
		return 'http://localhost:8000';
	}

	// 2. In PRODUCTION (standalone Docker / Unraid / Docker Hub):
	// Check if an explicit VITE_API_URL was passed at build time (e.g. for split deployments)
	const envApiUrl = import.meta.env.VITE_API_URL;
	if (envApiUrl && envApiUrl !== 'undefined' && envApiUrl !== '') {
		return envApiUrl;
	}

	// In production, the API is served from the exact same origin (relative path)
	return '';
}

export const API_URL = resolveApiUrl();

// Helper to derive ws(s):// URL from an absolute http(s):// endpoint
function toWsFromHttp(url: string): string {
	const clean = url.replace(/\/+$/, '');
	let ws = clean;
	if (clean.startsWith('https://')) {
		ws = clean.replace(/^https:\/\//, 'wss://');
	} else if (clean.startsWith('http://')) {
		// Upgrade to wss if current page is served over HTTPS to avoid mixed content block
		const isHttps = typeof window !== 'undefined' && window.location.protocol === 'https:';
		ws = clean.replace(/^http:\/\//, isHttps ? 'wss://' : 'ws://');
	}
	return `${ws}/ws`;
}

// For WebSockets, we need absolute URLs
function resolveWsUrl(): string {
	// 0. Explicit WebSocket URL override if provided
	const envWsUrl = import.meta.env.VITE_WS_URL;
	if (envWsUrl && envWsUrl !== 'undefined' && envWsUrl !== '') {
		return envWsUrl;
	}

	// 1. In DEVELOPMENT mode only (vite dev)
	if (import.meta.env.DEV) {
		const envApiUrl = import.meta.env.VITE_API_URL;
		if (envApiUrl && envApiUrl !== 'undefined' && envApiUrl !== '' && (envApiUrl.startsWith('http://') || envApiUrl.startsWith('https://'))) {
			return toWsFromHttp(envApiUrl);
		}

		if (typeof window !== 'undefined') {
			const hostname = window.location.hostname;
			const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
			return `${protocol}//${hostname}:8000/ws`;
		}
		return 'ws://localhost:8000/ws';
	}

	// 2. In PRODUCTION (standalone Docker / Unraid / Docker Hub):
	// If an explicit API URL was passed (split deployments), derive WS from it
	const envApiUrl = import.meta.env.VITE_API_URL;
	if (envApiUrl && envApiUrl !== 'undefined' && envApiUrl !== '' && (envApiUrl.startsWith('http://') || envApiUrl.startsWith('https://'))) {
		return toWsFromHttp(envApiUrl);
	}

	if (typeof window !== 'undefined') {
		const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
		return `${protocol}//${window.location.host}/ws`;
	}

	return 'ws://localhost:41481/ws';
}

export const WS_URL = resolveWsUrl();
