<script>
	import '../app.css';
	import { onMount } from 'svelte';

	onMount(() => {
		const saved = localStorage.getItem('alanbix_theme') || 'dark';
		document.documentElement.setAttribute('data-theme', saved);
	});
</script>

<div class="app-container">
	<slot />
</div>

<style>
	:global(body) {
		margin: 0;
		padding: 0;
		background-color: var(--bg-primary);
		color: var(--text-main);
		font-family: 'Inter', sans-serif;
		-webkit-font-smoothing: antialiased;
	}

	.app-container {
		min-height: 100vh;
		display: flex;
		flex-direction: column;
	}
</style>
