/**
 * Central configuration for API/WebSocket URLs.
 *
 * Uses VITE_API_URL env var if set, otherwise auto-detects from the current
 * browser hostname — perfect for LAN deployments where the backend port
 * is the only thing that differs from the frontend port.
 */

const BACKEND_PORT = '8000';

function resolveApiUrl(): string {
	// 1. Explicit env var (set in docker-compose / .env)
	const envUrl = import.meta.env.VITE_API_URL;
	if (envUrl && envUrl !== '' && typeof window === 'undefined') {
		return envUrl.replace(/\/$/, '');
	}

	// 2. Browser auto-detect: same hostname, backend port
	if (typeof window !== 'undefined') {
		if (envUrl && envUrl !== '') {
			// If VITE_API_URL looks like it uses localhost, swap in the actual browser hostname
			// so that remote clients hit the right machine
			try {
				const parsed = new URL(envUrl);
				if (parsed.hostname === 'localhost' || parsed.hostname === '127.0.0.1') {
					return `${parsed.protocol}//${window.location.hostname}:${parsed.port}`;
				}
			} catch { /* fallback below */ }
			return envUrl.replace(/\/$/, '');
		}
		return `${window.location.protocol}//${window.location.hostname}:${BACKEND_PORT}`;
	}

	// 3. SSR fallback
	return `http://localhost:${BACKEND_PORT}`;
}

export const API_URL = resolveApiUrl();

export const WS_URL = API_URL.replace(/^http/, 'ws') + '/ws';
