<script>
	import { authStore } from '$lib/auth';
	import { onMount, onDestroy } from 'svelte';
	import { api } from '$lib/api';
	import { connectWS, wsMessageStore } from '$lib/ws';
	import { invalidateAll } from '$app/navigation';

	let user = { username: '...', is_admin: false };
	let unsub = null;
	let isDark = true;

	onMount(async () => {
		isDark = (localStorage.getItem('alanbix_theme') || 'dark') === 'dark';
		try {
			user = await api.get('/me');
			connectWS();
			unsub = wsMessageStore.subscribe(msg => {
				if (msg && msg.type) {
					invalidateAll();
				}
			});
		} catch (e) {
			window.location.href = '/';
		}
	});

	onDestroy(() => {
		if (unsub) unsub();
	});

	function toggleTheme() {
		isDark = !isDark;
		const theme = isDark ? 'dark' : 'light';
		localStorage.setItem('alanbix_theme', theme);
		document.documentElement.setAttribute('data-theme', theme);
	}

	function logout() {
		authStore.logout();
		window.location.href = '/';
	}
</script>

<div class="dashboard-layout">
	<nav class="side-nav glass">
		<div class="nav-brand">
			<div class="logo-alambic">
				<div class="liquid"></div>
			</div>
			<span class="brand-name title-premium">ALANBIX</span>
		</div>

		<div class="nav-links">
			<a href="/dashboard" class="nav-item">
				<span class="icon">🏠</span>
				<span class="label">Dashboard</span>
			</a>
			<a href="/dashboard/tournaments" class="nav-item">
				<span class="icon">🏆</span>
				<span class="label">Tournois</span>
			</a>
			<a href="/dashboard/ai" class="nav-item">
				<span class="icon">🤖</span>
				<span class="label">Assistant IA</span>
			</a>
			<a href="/dashboard/map" class="nav-item">

				<span class="icon">📍</span>
				<span class="label">Plan Salle</span>
			</a>
			<a href="/spectator" target="_blank" class="nav-item">
				<span class="icon">📺</span>
				<span class="label">Projecteur</span>
			</a>
			
			{#if user.is_admin}
				<div class="nav-separator"></div>
				<a href="/dashboard/admin" class="nav-item admin">
					<span class="icon">⚙️</span>
					<span class="label">Administration</span>
				</a>
			{/if}
		</div>

		<div class="nav-footer">
			<a href="/dashboard/profile" class="user-profile">
				<div class="avatar">{user.username[0].toUpperCase()}</div>
				<div class="info">
					<div class="username">{user.username}</div>
					<div class="role">{user.is_admin ? 'Administrateur' : 'Joueur'}</div>
				</div>
			</a>
			<div class="footer-actions">
				<button class="theme-toggle" on:click={toggleTheme} title={isDark ? 'Mode clair' : 'Mode sombre'}>
					<span class="theme-icon" class:spin={true}>{isDark ? '☀️' : '🌙'}</span>
				</button>
				<button class="logout-btn" on:click={logout}>
					<span>Déconnexion</span>
				</button>
			</div>
		</div>
	</nav>

	<main class="content-area">
		<div class="container animate-in">
			<slot />
		</div>
	</main>
</div>


<style>
	.dashboard-layout {
		display: grid;
		grid-template-columns: 220px 1fr;
		min-height: 100vh;
		background: var(--bg-primary);
	}

	.side-nav {
		height: calc(100vh - 2rem);
		margin: 1rem;
		margin-right: 0;
		display: flex;
		flex-direction: column;
		padding: 1.5rem 1rem;
		border-radius: var(--radius-xl);
	}

	.nav-brand {
		display: flex;
		align-items: center;
		gap: 0.75rem;
		margin-bottom: 2rem;
		padding-left: 0.3rem;
	}

	.logo-alambic {
		width: 32px;
		height: 32px;
		border: 2px solid var(--accent);
		border-radius: 50% 50% 50% 10%;
		transform: rotate(-15deg);
		position: relative;
		overflow: hidden;
	}

	.liquid {
		position: absolute;
		bottom: 0;
		width: 100%;
		height: 60%;
		background: var(--accent);
		opacity: 0.6;
		box-shadow: 0 0 10px var(--accent-glow);
	}

	.brand-name {
		font-size: 1.2rem;
		font-weight: 800;
		font-family: var(--font-title);
	}

	.nav-links {
		display: flex;
		flex-direction: column;
		gap: 0.5rem;
		flex-grow: 1;
	}

	.nav-item {
		display: flex;
		align-items: center;
		gap: 1rem;
		padding: 0.75rem 1rem;
		text-decoration: none;
		color: var(--text-dim);
		border-radius: var(--radius-md);
		transition: all 0.2s;
	}

	.nav-item:hover {
		background: var(--hover-tint);
		color: var(--accent);
		transform: translateX(5px);
	}

	.nav-item.admin {
		color: #fbbf24;
	}

	.nav-item.admin:hover {
		background: rgba(251, 191, 36, 0.1);
		color: #fbbf24;
		box-shadow: inset 3px 0 0 #fbbf24;
	}

	.nav-separator {
		height: 1px;
		background: var(--glass-border);
		margin: 1rem 0;
	}

	.nav-footer {
		display: flex;
		flex-direction: column;
		gap: 1.5rem;
		padding-top: 2rem;
		border-top: 1px solid var(--glass-border);
	}

	.user-profile {
		display: flex;
		align-items: center;
		gap: 0.75rem;
		text-decoration: none;
		color: inherit;
		padding: 0.4rem;
		border-radius: var(--radius-md);
		transition: background 0.15s;
	}
	.user-profile:hover {
		background: var(--hover-tint);
	}

	.avatar {
		width: 40px;
		height: 40px;
		background: var(--bg-tertiary);
		border-radius: 50%;
		display: flex;
		align-items: center;
		justify-content: center;
		font-weight: 700;
		color: var(--accent);
		border: 1px solid var(--accent-soft);
	}

	.username {
		font-weight: 600;
		font-size: 0.9rem;
	}

	.role {
		font-size: 0.75rem;
		color: var(--text-muted);
	}

	.logout-btn {
		background: transparent;
		border: 1px solid var(--glass-border);
		color: var(--text-dim);
		padding: 0.6rem;
		border-radius: var(--radius-md);
		cursor: pointer;
		font-weight: 600;
		font-size: 0.8rem;
		transition: all 0.2s;
	}

	.logout-btn:hover {
		border-color: var(--danger);
		color: var(--danger);
		background: rgba(239, 68, 68, 0.05);
	}

	.footer-actions {
		display: flex;
		gap: 0.5rem;
		align-items: center;
	}

	.theme-toggle {
		width: 38px;
		height: 38px;
		border-radius: var(--radius-md);
		background: var(--hover-tint);
		border: 1px solid var(--glass-border);
		cursor: pointer;
		display: flex;
		align-items: center;
		justify-content: center;
		font-size: 1.1rem;
		transition: all 0.25s ease;
		padding: 0;
	}
	.theme-toggle:hover {
		background: var(--accent-soft);
		border-color: var(--accent);
		transform: scale(1.08);
		box-shadow: 0 0 12px var(--accent-glow);
	}
	.theme-icon {
		display: inline-block;
		transition: transform 0.4s ease;
	}
	.theme-toggle:hover .theme-icon {
		transform: rotate(25deg);
	}

	.logout-btn {
		flex: 1;
	}

	.content-area {
		padding: 1.5rem;
		overflow-y: auto;
		height: 100vh;
	}
</style>
