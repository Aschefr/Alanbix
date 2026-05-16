import { sveltekit } from '@sveltejs/kit/vite';
import { defineConfig } from 'vite';

export default defineConfig({
	plugins: [sveltekit()],
	server: {
		allowedHosts: 'all',
		fs: {
			allow: ['..']
		},
		proxy: {
			'/static': {
				target: 'http://backend:8000',
				changeOrigin: true
			},
			'/data': {
				target: 'http://backend:8000',
				changeOrigin: true
			}
		}
	}
});
