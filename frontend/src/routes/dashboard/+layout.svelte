<script>
	import { authStore } from '$lib/auth';
	import { onMount, onDestroy } from 'svelte';
	import { api } from '$lib/api';
	import { connectWS, wsMessageStore } from '$lib/ws';
	import { invalidateAll } from '$app/navigation';
	import { pmUnreadCount } from '$lib/pmStore';

	let user = { username: '...', is_admin: false };
	let unsub = null;
	let isDark = true;
	let notifCount = 0;
	let notifBounce = false;
	let pmBounce = false;
	let lastPmSender = null;
	let iaInstances = [];
	let iaInterval = null;

	onMount(async () => {
		isDark = (localStorage.getItem('alanbix_theme') || 'dark') === 'dark';
		try {
			user = await api.get('/me');
			connectWS();
			// Fetch initial unread count
			try {
				const nc = await api.get('/notifications/unread-count');
				notifCount = nc.count || 0;
			} catch {}
			try {
				const pc = await api.get('/players/messages/unread-count');
				pmUnreadCount.set(pc.count || 0);
			} catch {}
			unsub = wsMessageStore.subscribe(msg => {
				if (msg && msg.type) {
					invalidateAll();
					// Update notification badge in real-time
					if (msg.type === 'notification_new') {
						api.get('/notifications/unread-count').then(r => {
							notifCount = r.count || 0;
							notifBounce = true;
							setTimeout(() => notifBounce = false, 600);
						}).catch(() => {});
					}
					if (msg.type === 'private_message_new') {
						// Track sender for auto-open on Players page
						if (msg.sender_id && msg.sender_id !== user.id) {
							lastPmSender = msg.sender_id;
							localStorage.setItem('alanbix_pm_last_sender', String(msg.sender_id));
						}
						api.get('/players/messages/unread-count').then(r => {
							pmUnreadCount.set(r.count || 0);
							pmBounce = true;
							setTimeout(() => pmBounce = false, 600);
						}).catch(() => {});
					}
				}
			});
		} catch (e) {
			window.location.href = '/';
		}
		// Admin: poll IA status
		if (user.is_admin) {
			pollIaStatus();
			iaInterval = setInterval(pollIaStatus, 30000);
		}
	});

	async function pollIaStatus() {
		try { iaInstances = await api.get('/ia/instances/status'); } catch { iaInstances = []; }
		// Poll faster when any instance is busy
		const anyBusy = iaInstances.some(i => i.busy);
		const nextInterval = anyBusy ? 5000 : 30000;
		if (iaInterval) clearInterval(iaInterval);
		iaInterval = setInterval(pollIaStatus, nextInterval);
	}

	onDestroy(() => {
		if (unsub) unsub();
		if (iaInterval) clearInterval(iaInterval);
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
			<a href="/dashboard/info" class="nav-item">
				<span class="icon">📋</span>
				<span class="label">Infos</span>
			</a>
			<a href="/dashboard/tournaments" class="nav-item">
				<span class="icon">🏆</span>
				<span class="label">Tournois</span>
			</a>
			<a href="/dashboard/players{$pmUnreadCount > 0 && lastPmSender ? '?chat=' + lastPmSender : ''}" class="nav-item pm-nav">
				<span class="icon">👥</span>
				<span class="label">Joueurs</span>
				{#if $pmUnreadCount > 0}
					<span class="pm-count-badge" class:bounce={pmBounce}>{$pmUnreadCount}</span>
				{/if}
			</a>
			<a href="/dashboard/notifications" class="nav-item notif-nav" on:click={() => { api.get('/notifications/unread-count').then(r => notifCount = r.count || 0).catch(() => {}); }}>
				<span class="icon">🔔</span>
				<span class="label">Notifications</span>
				{#if notifCount > 0}
					<span class="notif-count-badge" class:bounce={notifBounce}>{notifCount}</span>
				{/if}
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
			{#if user.is_admin && iaInstances.length > 0}
				<div class="ia-status-widget">
					<div class="ia-status-title">🖥️ IA Instances</div>
					{#each iaInstances as inst}
						<div class="ia-inst-row" title="{inst.url} — {inst.latency_ms || 0}ms{inst.busy ? ' — Génération en cours' : ''}">
							<span class="ia-dot {inst.busy ? 'busy' : inst.online ? 'online' : 'offline'}"></span>
							<span class="ia-inst-label">{inst.label || inst.model || '?'}</span>
							{#if inst.busy}
								<span class="ia-inst-ping busy">⚡</span>
							{:else if inst.online}
								<span class="ia-inst-ping">{inst.latency_ms}ms</span>
							{:else}
								<span class="ia-inst-ping offline">off</span>
							{/if}
						</div>
					{/each}
				</div>
			{/if}
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

	/* Notification badge */
	.notif-nav { position: relative; }
	.notif-count-badge {
		position: absolute; top: 4px; right: 8px;
		min-width: 18px; height: 18px; line-height: 18px;
		padding: 0 5px; border-radius: 10px;
		background: #ef4444; color: white;
		font-size: 0.6rem; font-weight: 800; text-align: center;
		box-shadow: 0 0 8px rgba(239,68,68,0.5);
		animation: notif-pulse 2s ease-in-out infinite;
		will-change: opacity;
	}
	.notif-count-badge.bounce {
		animation: notif-bounce 0.6s ease;
	}
	@keyframes notif-pulse {
		0%, 100% { opacity: 1; }
		50% { opacity: 0.4; }
	}
	@keyframes notif-bounce {
		0% { transform: scale(1); }
		30% { transform: scale(1.5); }
		50% { transform: scale(0.9); }
		70% { transform: scale(1.2); }
		100% { transform: scale(1); }
	}

	/* PM badge (same pattern as notif) */
	.pm-nav { position: relative; }
	.pm-count-badge {
		position: absolute; top: 4px; right: 8px;
		min-width: 18px; height: 18px; line-height: 18px;
		padding: 0 5px; border-radius: 10px;
		background: #8b5cf6; color: white;
		font-size: 0.6rem; font-weight: 800; text-align: center;
		box-shadow: 0 0 8px rgba(139,92,246,0.5);
		animation: notif-pulse 2s ease-in-out infinite;
		will-change: opacity;
	}
	.pm-count-badge.bounce {
		animation: notif-bounce 0.6s ease;
	}

	/* IA Status Widget */
	.ia-status-widget {
		padding: 0.6rem 0.8rem; border-radius: var(--radius-md);
		background: var(--hover-tint); border: 1px solid var(--glass-border);
		margin-bottom: 0.8rem;
	}
	.ia-status-title { font-size: 0.65rem; font-weight: 700; color: var(--text-muted); text-transform: uppercase; letter-spacing: 0.05em; margin-bottom: 0.4rem; }
	.ia-inst-row { display: flex; align-items: center; gap: 0.5rem; padding: 0.15rem 0; }
	.ia-dot { width: 7px; height: 7px; border-radius: 50%; flex-shrink: 0; }
	.ia-dot.online { background: #10b981; box-shadow: 0 0 6px rgba(16,185,129,0.6); animation: dot-pulse 2s ease-in-out infinite; will-change: opacity; }
	.ia-dot.offline { background: #ef4444; box-shadow: 0 0 6px rgba(239,68,68,0.4); }
	.ia-dot.busy { background: #f59e0b; box-shadow: 0 0 8px rgba(245,158,11,0.7); animation: dot-busy 0.5s ease-in-out infinite; will-change: opacity; }
	@keyframes dot-pulse { 0%,100% { opacity: 1; } 50% { opacity: 0.5; } }
	@keyframes dot-busy { 0%,100% { opacity: 1; } 50% { opacity: 0.3; } }
	.ia-inst-label { font-size: 0.7rem; color: var(--text-dim); flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
	.ia-inst-ping { font-size: 0.6rem; color: var(--text-muted); font-family: monospace; }
	.ia-inst-ping.offline { color: #ef4444; font-weight: 700; }
	.ia-inst-ping.busy { color: #f59e0b; font-weight: 700; font-size: 0.75rem; }
</style>
