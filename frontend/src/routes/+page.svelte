<script>
	import { api } from '$lib/api';
	import { authStore } from '$lib/auth';
	import { onMount } from 'svelte';

	let username = '';
	let password = '';
	let isRegistering = false;
	let error = '';
	let isDark = true;

	async function handleSubmit() {
		error = '';
		try {
			if (isRegistering) {
				await api.post('/register', { username, password });
				await api.login(username, password);
				window.location.href = '/dashboard';
			} else {
				await api.login(username, password);
				window.location.href = '/dashboard';
			}
		} catch (e) {
			error = e.message;
		}
	}

	function toggleTheme() {
		isDark = !isDark;
		const theme = isDark ? 'dark' : 'light';
		localStorage.setItem('alanbix_theme', theme);
		document.documentElement.setAttribute('data-theme', theme);
	}

	onMount(() => {
		isDark = (localStorage.getItem('alanbix_theme') || 'dark') === 'dark';
		if ($authStore) {
			window.location.href = '/dashboard';
		}
	});
</script>

<main class="login-page">
	<button class="login-theme-toggle" on:click={toggleTheme} title={isDark ? 'Mode clair' : 'Mode sombre'}>
		{isDark ? '☀️' : '🌙'}
	</button>
	<div class="login-card glass">
		<h1 class="title-premium">Alanbix</h1>
		<p class="subtitle">L'alambic qui distille votre LAN</p>

		{#if error}
			<p class="error-msg">{error}</p>
		{/if}

		<form on:submit|preventDefault={handleSubmit}>
			<div class="input-group">
				<label for="username">Pseudo</label>
				<input type="text" id="username" bind:value={username} placeholder="Ton pseudo" required />
			</div>

			<div class="input-group">
				<label for="password">Mot de passe</label>
				<input type="password" id="password" bind:value={password} placeholder="••••••••" required />
			</div>

			<button type="submit" class="btn-primary">
				{isRegistering ? "Créer mon compte" : "Se connecter"}
			</button>
		</form>

		<div class="toggle-mode">
			<button on:click={() => isRegistering = !isRegistering}>
				{isRegistering ? "Déjà un compte ? Se connecter" : "Nouveau ? Créer un compte"}
			</button>
		</div>
	</div>
</main>

<style>
	.login-page {
		display: flex;
		align-items: center;
		justify-content: center;
		flex-grow: 1;
		padding: 2rem;
	}

	.login-card {
		width: 100%;
		max-width: 400px;
		padding: 2.5rem;
		text-align: center;
		box-shadow: 0 25px 50px -12px rgba(0, 0, 0, 0.5);
	}

	h1 {
		font-size: 3rem;
		margin: 0;
	}

	.subtitle {
		color: var(--text-dim);
		margin-bottom: 2rem;
		font-size: 0.9rem;
	}

	.error-msg {
		color: var(--danger);
		background: rgba(239, 68, 68, 0.1);
		padding: 0.5rem;
		border-radius: 4px;
		font-size: 0.8rem;
		margin-bottom: 1rem;
	}

	.input-group {
		text-align: left;
		margin-bottom: 1.5rem;
	}

	label {
		display: block;
		margin-bottom: 0.5rem;
		font-size: 0.8rem;
		color: var(--text-dim);
		text-transform: uppercase;
		letter-spacing: 0.05em;
	}

	input {
		width: 100%;
		padding: 0.75rem;
		background: var(--input-bg);
		border: 1px solid var(--glass-border);
		border-radius: 4px;
		color: var(--input-color);
		outline: none;
		transition: border-color 0.2s;
	}

	input:focus {
		border-color: var(--accent);
		box-shadow: 0 0 0 2px var(--accent-glow);
	}

	.btn-primary {
		width: 100%;
		padding: 0.75rem;
		background: var(--accent);
		color: white;
		border: none;
		border-radius: 4px;
		font-weight: 600;
		cursor: pointer;
		transition: transform 0.1s, background-color 0.2s;
	}

	.btn-primary:hover {
		background-color: #2563eb;
	}

	.btn-primary:active {
		transform: scale(0.98);
	}

	.toggle-mode {
		margin-top: 1.5rem;
	}

	.toggle-mode button {
		background: none;
		border: none;
		color: var(--text-dim);
		font-size: 0.85rem;
		cursor: pointer;
		text-decoration: underline;
	}

	.toggle-mode button:hover {
		color: var(--text-main);
	}

	.login-theme-toggle {
		position: absolute;
		top: 1.5rem;
		right: 1.5rem;
		width: 42px;
		height: 42px;
		border-radius: 50%;
		background: var(--glass-bg);
		border: 1px solid var(--glass-border);
		backdrop-filter: blur(12px);
		cursor: pointer;
		font-size: 1.2rem;
		display: flex;
		align-items: center;
		justify-content: center;
		transition: all 0.25s ease;
		z-index: 10;
	}
	.login-theme-toggle:hover {
		transform: scale(1.1) rotate(15deg);
		box-shadow: 0 0 15px var(--accent-glow);
		border-color: var(--accent);
	}
</style>
