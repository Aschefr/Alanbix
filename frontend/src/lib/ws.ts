import { writable } from 'svelte/store';

export const wsMessageStore = writable<any>(null);

let socket: WebSocket | null = null;

export function connectWS() {
	if (socket && (socket.readyState === WebSocket.OPEN || socket.readyState === WebSocket.CONNECTING)) return;

	socket = new WebSocket('ws://localhost:8000/ws');

	socket.onmessage = (event) => {
		const message = JSON.parse(event.data);
		wsMessageStore.set(message);
	};

	socket.onclose = () => {
		setTimeout(connectWS, 3000); // Reconnect after 3s
	};

	socket.onerror = (err) => {
		console.error('WS Error:', err);
		socket?.close();
	};
}
