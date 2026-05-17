self.addEventListener('install', (event) => {
	self.skipWaiting();
});

self.addEventListener('activate', (event) => {
	event.waitUntil(self.clients.claim());
});

self.addEventListener('notificationclick', (event) => {
	event.notification.close();

	const urlToOpen = event.notification.data?.url;
	if (!urlToOpen) return;

	event.waitUntil(
		clients.matchAll({ type: 'window', includeUncontrolled: true }).then((windowClients) => {
			let matchingClient = null;

			// Try to find a client that is already at the exact target URL
			for (let i = 0; i < windowClients.length; i++) {
				const client = windowClients[i];
				if (client.url === urlToOpen) {
					matchingClient = client;
					break;
				}
			}

			// Otherwise, try to find ANY open client of our app
			if (!matchingClient && windowClients.length > 0) {
				matchingClient = windowClients[0];
			}

			if (matchingClient) {
				// Use BroadcastChannel to ensure the message arrives even if client is uncontrolled
				const channel = new BroadcastChannel('alanbix_sw_channel');
				channel.postMessage({ type: 'alanbix_nav', url: urlToOpen });
				
				if ('focus' in matchingClient) {
					return matchingClient.focus();
				}
				return matchingClient;
			} else {
				// If no windows are open at all, open a new window
				if (clients.openWindow) {
					return clients.openWindow(urlToOpen);
				}
			}
		})
	);
});
