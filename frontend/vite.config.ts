import { sveltekit } from '@sveltejs/kit/vite';
import { defineConfig } from 'vite';

export default defineConfig({
	plugins: [sveltekit()],
	server: {
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
			'^/(check-username|token|register|me|users|tournaments|notifications|players|games|ia|i18n|dashboard/stats|system|health|api|static|data)': {
				target: 'http://backend:8000',
				changeOrigin: true
			}
		}
	}
});
