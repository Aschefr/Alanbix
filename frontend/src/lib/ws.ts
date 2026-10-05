import { writable } from 'svelte/store';
import { WS_URL } from './config';

export const wsMessageStore = writable<any>(null);

let socket: WebSocket | null = null;
let heartbeatTimer: any = null;

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
	if (socket && (socket.readyState === WebSocket.OPEN || socket.readyState === WebSocket.CONNECTING)) return;

	try {
		socket = new WebSocket(WS_URL);
	} catch (err) {
		console.error('[WebSocket] Initialization error:', err);
		setTimeout(connectWS, 3000);
		return;
	}

	socket.onopen = () => {
		startHeartbeat();
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
		setTimeout(connectWS, 3000); // Reconnect after 3s
	};

	socket.onerror = (err) => {
		console.error('[WebSocket] Connection error:', err);
		stopHeartbeat();
		socket?.close();
	};
}
