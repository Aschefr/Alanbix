import { sveltekit } from '@sveltejs/kit/vite';
import { defineConfig } from 'vite';

export default defineConfig({
	plugins: [sveltekit()],
	server: {
		cors: true,
		allowedHosts: true,
		watch: {
			usePolling: true,
			interval: 1500,
			ignored: [/\/android\//, /\/ios\//, /\.gradle\//, /\/build\//, /\.svelte-kit\//]
		},
		fs: {
			allow: ['..']
		},
		proxy: {
			'^/(check-username|token|register|me|users|tournaments|notifications|players|games|ia|i18n|dashboard/(stats|team-leaderboard|info)|system|health|api|static|data|devices|room|public-chat)': {
				target: 'http://backend:8000',
				changeOrigin: true
			}
		}
	}
});
