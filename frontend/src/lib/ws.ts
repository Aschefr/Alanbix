import { writable } from 'svelte/store';
import { WS_URL, resolveWsUrl, isDemoMode } from './config';

export const wsMessageStore = writable<any>(null);

let socket: WebSocket | null = null;
let heartbeatTimer: any = null;

export function authenticateWS(token?: string) {
	if (isDemoMode()) return;
	const authToken = token || (typeof window !== 'undefined' ? localStorage.getItem('alanbix_token') : null);
	if (socket && socket.readyState === WebSocket.OPEN && authToken) {
		try {
			socket.send(JSON.stringify({ type: 'auth', token: authToken }));
		} catch {}
	}
}

function startHeartbeat() {
	stopHeartbeat();
	heartbeatTimer = setInterval(() => {
		if (socket && socket.readyState === WebSocket.OPEN) {
			try {
				socket.send(JSON.stringify({ type: 'ping' }));
			} catch {}
		}
	}, 25000);
}

function stopHeartbeat() {
	if (heartbeatTimer) {
		clearInterval(heartbeatTimer);
		heartbeatTimer = null;
	}
}

export function connectWS() {
	if (isDemoMode()) return;
	if (socket && (socket.readyState === WebSocket.OPEN || socket.readyState === WebSocket.CONNECTING)) return;

	try {
		const targetWsUrl = resolveWsUrl() || WS_URL;
		socket = new WebSocket(targetWsUrl);
	} catch (err) {
		console.error('[WebSocket] Initialization error:', err);
		setTimeout(connectWS, 3000);
		return;
	}

	socket.onopen = () => {
		startHeartbeat();
		authenticateWS();
	};

	socket.onmessage = (event) => {
		try {
			const message = JSON.parse(event.data);
			wsMessageStore.set(message);
		} catch (err) {
			// Ignore non-JSON control/ping frames
		}
	};

	socket.onclose = () => {
		stopHeartbeat();
		if (!isDemoMode()) {
			setTimeout(connectWS, 3000); // Reconnect after 3s
		}
	};

	socket.onerror = (err) => {
		console.error('[WebSocket] Connection error:', err);
		stopHeartbeat();
		socket?.close();
	};
}
