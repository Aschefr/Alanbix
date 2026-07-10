<script>
	import { authStore } from '$lib/auth';
	import { onMount, onDestroy, tick } from 'svelte';
	import { api } from '$lib/api';
	import { connectWS, wsMessageStore } from '$lib/ws';
	import { invalidateAll, goto } from '$app/navigation';
	import { pmUnreadCount, groupUnreadCount, totalMsgUnread, notifUnreadCount, aiUnreadCount } from '$lib/pmStore';
	import { get } from 'svelte/store';
	import TutorialOverlay from '$lib/components/TutorialOverlay.svelte';
	import { currentLang, availableLanguages, lanMultilingual, loadLocale, flagMap, t, initI18n, refreshEventName } from '$lib/i18nStore';

	let user = { username: '...', is_admin: false };
	let loading = true;
	let connectionError = '';
	let unsub = null;
	let isDark = true;
	let notifBounce = false;
	let aiBounce = false;
	let pmBounce = false;
	let lastPmSender = null;
	let iaInstances = [];
	let iaInterval = null;
	let iaQueueSize = 0;
	let iaQueueActive = 0;
	let version = '...';
	let showChangelog = false;
	let changelogData = [];
	let loadingChangelog = false;
	let changelogError = null;

	async function openChangelog() {
		showChangelog = true;
		if (changelogData.length > 0) return;
		loadingChangelog = true;
		changelogError = null;
		try {
			changelogData = await api.get('/changelog');
		} catch (e) {
			changelogError = e.message || "Erreur lors de la récupération des notes de mise à jour.";
		} finally {
			loadingChangelog = false;
		}
	}

	function formatDate(dateStr) {
		try {
			const d = new Date(dateStr);
			return d.toLocaleDateString('fr-FR', { day: 'numeric', month: 'long', year: 'numeric' });
		} catch {
			return dateStr;
		}
	}

	function parseMarkdown(md) {
		if (!md) return '';
		return md
			.replace(/&/g, '&amp;')
			.replace(/</g, '&lt;')
			.replace(/>/g, '&gt;')
			.replace(/^### (.*$)/gim, '<h4>$1</h4>')
			.replace(/^## (.*$)/gim, '<h3>$1</h3>')
			.replace(/^# (.*$)/gim, '<h2>$1</h2>')
			.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
			.replace(/\*(.*?)\*/g, '<em>$1</em>')
			.replace(/`([^`]+)`/g, '<code>$1</code>')
			.replace(/^\s*-\s+(.*$)/gim, '<li>$1</li>')
			.replace(/\n/g, '<br />');
	}


	let browserNotifSupport = false;
	let browserNotifStatus = 'default';

	function requestBrowserNotifications() {
		if (!('Notification' in window)) return;
		Notification.requestPermission().then(perm => {
			browserNotifStatus = perm;
			if (perm === 'granted') {
				showGlobalToast('Notifications du navigateur activées', 'success');
				if ('serviceWorker' in navigator) {
					navigator.serviceWorker.getRegistration().then(reg => {
						if (reg && reg.showNotification) {
							reg.showNotification('Alanbix', { body: 'Notifications activées avec succès !', icon: '/favicon.svg' });
						} else {
							new Notification('Alanbix', { body: 'Notifications activées avec succès !', icon: '/favicon.svg' });
						}
					});
				} else {
					new Notification('Alanbix', { body: 'Notifications activées avec succès !', icon: '/favicon.svg' });
				}
			}
		});
	}

	function notifyBrowser(title, body, link = null) {
		try {
			if (!('Notification' in window)) return;
			if (Notification.permission !== 'granted') return;
			
			const absoluteLink = link ? new URL(link, window.location.origin).href : null;
			const tag = 'alanbix-notification';

			const options = {
				body: body,
				icon: '/favicon.svg',
				tag: tag,
				renotify: true,
				data: { url: absoluteLink }
			};

			if ('serviceWorker' in navigator) {
				navigator.serviceWorker.getRegistration().then(reg => {
					if (reg && reg.showNotification) {
						reg.showNotification(title, options);
					} else {
						fallbackNotification(title, options, link);
					}
				});
			} else {
				fallbackNotification(title, options, link);
			}
		} catch (err) {
			console.warn('[Alanbix] Browser notification failed:', err);
		}
	}

	function fallbackNotification(title, options, link) {
		const n = new Notification(title, options);
		if (link) {
			n.onclick = function(e) {
				e.preventDefault();
				localStorage.setItem('alanbix_notif_nav', link);
				window.focus();
				n.close();
			};
		}
	}

	// Navigate to pending notification target when page regains focus
	function handleNotifNav() {
		const pendingNav = localStorage.getItem('alanbix_notif_nav');
		if (pendingNav) {
			localStorage.removeItem('alanbix_notif_nav');
			goto(pendingNav);
		}
	}

	let globalToasts = [];
	let gToastId = 0;
	function showGlobalToast(message, type = 'info', link = null) {
		const id = ++gToastId;
		globalToasts = [...globalToasts, { id, message, type, link, leaving: false }];
		setTimeout(() => {
			globalToasts = globalToasts.map(t => t.id === id ? { ...t, leaving: true } : t);
			setTimeout(() => { globalToasts = globalToasts.filter(t => t.id !== id); }, 400);
		}, 4000);
	}

	async function initApp() {
		try {
			user = await api.get('/me');
			connectWS();
			// Fetch initial unread count
			try {
				const nc = await api.get('/notifications/unread-count');
				notifUnreadCount.set(nc.count || 0);
			} catch {}
			try {
				const pc = await api.get('/players/messages/unread-count');
				pmUnreadCount.set(pc.count || 0);
			} catch {}
			try {
				const gc = await api.get('/players/group/unread-count');
				groupUnreadCount.set(gc.count || 0);
			} catch {}
			
			if (unsub) unsub();
			unsub = wsMessageStore.subscribe(msg => {
				if (msg && msg.type) {
					const criticalTypes = [
						'config_updated', 'users_updated', 
						'tournament_created', 'tournament_updated', 'tournament_deleted',
						'tournament_started', 'tournament_closed', 'tournament_reopened'
					];
					if (criticalTypes.includes(msg.type)) {
						invalidateAll();
					}
					if (msg.type === 'config_updated') {
						refreshEventName();
					}
					// Update notification badge in real-time
					if (msg.type === 'notification_new') {
						api.get('/notifications/unread-count').then(r => {
							const oldCount = get(notifUnreadCount);
							const newCount = r.count || 0;
							notifUnreadCount.set(newCount);
							if (newCount > oldCount) {
								showGlobalToast('🔔 Nouvelle notification reçue', 'info', '/dashboard/notifications');
								notifyBrowser('Alanbix', '🔔 Nouvelle notification reçue', '/dashboard/notifications');
							}
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
							const oldCount = get(pmUnreadCount);
							const newCount = r.count || 0;
							pmUnreadCount.set(newCount);
							if (newCount > oldCount && msg.sender_id !== user.id) {
								const link = '/dashboard/players' + (msg.sender_id ? '?chat=' + msg.sender_id : '');
								const senderName = msg.sender_name || 'Quelqu\'un';
								const preview = msg.preview || '';
								showGlobalToast(`💬 ${senderName} : ${preview}`, 'pm', link);
								notifyBrowser(`💬 ${senderName}`, preview, link);
							}
							pmBounce = true;
							setTimeout(() => pmBounce = false, 600);
						}).catch(() => {});
					}
					// AXE-12: Group message notification
					if (msg.type === 'group_message_new') {
						api.get('/players/group/unread-count').then(r => {
							const oldCount = get(groupUnreadCount);
							const newCount = r.count || 0;
							groupUnreadCount.set(newCount);
							if (newCount > oldCount && msg.sender_id !== user.id) {
								const link = '/dashboard/players?chat=group';
								const senderName = msg.sender_name || 'Quelqu\'un';
								const preview = msg.preview || '';
								showGlobalToast(`👥 ${senderName} : ${preview}`, 'pm', link);
								notifyBrowser(`👥 ${senderName} (groupe)`, preview, link);
							}
							pmBounce = true;
							setTimeout(() => pmBounce = false, 600);
						}).catch(() => {});
					}
					// AI queue updates (G-52)
					if (msg.type === 'ia_queue_update') {
						iaQueueSize = msg.queue_size || 0;
						iaQueueActive = msg.active_count || 0;
					}
					// AI response arrived: badge on Assistant IA nav link
					// Only if the player is not currently on the /dashboard/ai page and matches user_id
					if (msg.type === 'chat_updated' && msg.role === 'bot') {
						if (msg.user_id === user.id && !window.location.pathname.startsWith('/dashboard/ai')) {
							aiUnreadCount.update(n => n + 1);
							aiBounce = true;
							setTimeout(() => aiBounce = false, 600);
						}
					}
					// Admin message: the notification already exists via notification_new,
					// so we only add the AI nav badge (no duplicate toast) and match user_id
					if (msg.type === 'admin_message') {
						if (msg.user_id === user.id && !window.location.pathname.startsWith('/dashboard/ai')) {
							aiUnreadCount.update(n => n + 1);
							aiBounce = true;
							setTimeout(() => aiBounce = false, 600);
						}
					}
				}
			});

			// Fetch SemVer version
			try {
				const res = await api.get('/health');
				version = res.version || '1.26.7';
			} catch {
				version = '1.26.7';
			}

			// Admin: poll IA status
			if (user.is_admin) {
				if (iaInterval) clearInterval(iaInterval);
				pollIaStatus();
				iaInterval = setInterval(pollIaStatus, 30000);
			}

			connectionError = '';
			loading = false;
		} catch (e) {
			console.error("[Alanbix] App init error:", e);
			// Check if we got logged out (401 response cleared authStore)
			if (!get(authStore)) {
				window.location.href = '/';
				return;
			}
			connectionError = "Serveur hors ligne. Tentative de connexion...";
			setTimeout(initApp, 3000);
		}
	}

	onMount(async () => {
		isDark = (localStorage.getItem('alanbix_theme') || 'dark') === 'dark';
		await initI18n();
		if ('Notification' in window) {
			browserNotifSupport = true;
			browserNotifStatus = Notification.permission;
		}
		// Listen for page focus to handle notification click navigation
		window.addEventListener('focus', handleNotifNav);
		document.addEventListener('visibilitychange', () => {
			if (document.visibilityState === 'visible') handleNotifNav();
		});

		// Listen for profile changes to update sidebar without F5
		window.addEventListener('user-updated', handleUserUpdateEvent);

		// Use BroadcastChannel for reliable SW -> Client communication
		const channel = new BroadcastChannel('alanbix_sw_channel');
		channel.onmessage = (event) => {
			if (event.data && event.data.type === 'alanbix_nav' && event.data.url) {
				const urlObj = new URL(event.data.url);
				goto(urlObj.pathname + urlObj.search);
			}
		};

		await initApp();
	});

	async function handleUserUpdateEvent() {
		try {
			user = await api.get('/me');
		} catch {}
	}

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
		if (typeof window !== 'undefined') {
			window.removeEventListener('user-updated', handleUserUpdateEvent);
		}
	});

	let navFontSize = '0.95rem';

	$: if ($t || version || user) {
		adjustNavFontSize();
	}

	async function adjustNavFontSize() {
		await tick();
		const sideNav = document.querySelector('.side-nav');
		if (!sideNav) return;
		
		const labels = sideNav.querySelectorAll('.nav-item .label');
		if (labels.length === 0) return;

		let sizeRem = 0.95;
		const minSizeRem = 0.75;
		
		// Reset to max size first to measure
		sideNav.style.setProperty('--nav-font-size', `${sizeRem}rem`);
		await tick();

		let hasOverflow = true;
		while (hasOverflow && sizeRem > minSizeRem) {
			hasOverflow = false;
			for (const label of labels) {
				// If a label wraps to 2 lines, its height is > 25px
				if (label.offsetHeight > 25) {
					hasOverflow = true;
					break;
				}
			}
			
			if (hasOverflow) {
				sizeRem -= 0.05;
				sideNav.style.setProperty('--nav-font-size', `${sizeRem}rem`);
				await tick();
			}
		}
	}

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

{#if loading}
	<div class="app-loading-screen" style="display:flex;align-items:center;justify-content:center;height:100vh;width:100vw;background:var(--bg-primary);color:var(--text-main);font-weight:700">
		<div style="display:flex;flex-direction:column;align-items:center;gap:1.5rem">
			<div class="logo-alambic loading-logo" style="width:64px;height:64px;">
				<div class="liquid boiling-liquid" style="height:70%"></div>
				<div class="bubble b1"></div>
				<div class="bubble b2"></div>
				<div class="bubble b3"></div>
			</div>
			<span class="loading-text" style="font-size:0.95rem;opacity:0.8;letter-spacing:0.15em;color:var(--accent)">
				{#if connectionError}
					{connectionError}
				{:else}
					DISTILLATION...
				{/if}
			</span>
			{#if connectionError}
				<button on:click={() => { connectionError = ''; initApp(); }} class="btn-retry">
					🔄 RÉESSAYER
				</button>
			{/if}
		</div>
	</div>
{:else}
<div class="dashboard-layout">
	<nav class="side-nav glass">
		<div class="nav-brand">
			<div class="logo-alambic">
				<div class="liquid"></div>
			</div>
			<div class="brand-text">
				<span class="brand-name title-premium">ALANBIX</span>
				<button class="version-badge" on:click={openChangelog}>
					v{version}
				</button>
			</div>
		</div>

		<div class="nav-links">
			<a href="/dashboard" class="nav-item">
				<span class="icon">🏠</span>
				<span class="label">{$t('nav_dashboard')}</span>
			</a>
			<a href="/dashboard/info" class="nav-item">
				<span class="icon">📋</span>
				<span class="label">{$t('nav_infos')}</span>
			</a>
			<a href="/dashboard/tournaments" class="nav-item">
				<span class="icon">🏆</span>
				<span class="label">{$t('nav_tournaments')}</span>
			</a>
			<a href="/dashboard/players{$totalMsgUnread > 0 && lastPmSender ? '?chat=' + lastPmSender : ''}" class="nav-item pm-nav">
				<span class="icon">👥</span>
				<span class="label">{$t('nav_players')}</span>
				{#if $totalMsgUnread > 0}
					<span class="pm-count-badge" class:bounce={pmBounce}>{$totalMsgUnread}</span>
				{/if}
			</a>
			<a href="/dashboard/notifications" class="nav-item notif-nav" on:click={() => { api.get('/notifications/unread-count').then(r => notifUnreadCount.set(r.count || 0)).catch(() => {}); }}>
				<span class="icon">🔔</span>
				<span class="label">{$t('nav_notifications')}</span>
				{#if $notifUnreadCount > 0}
					<span class="notif-count-badge" class:bounce={notifBounce}>{$notifUnreadCount}</span>
				{/if}
			</a>
			<a href="/dashboard/ai" class="nav-item ai-nav" on:click={() => aiUnreadCount.set(0)}>
				<span class="icon">🤖</span>
				<span class="label">{$t('nav_ai_assistant')}</span>
				{#if $aiUnreadCount > 0}
					<span class="ai-count-badge" class:bounce={aiBounce}>{$aiUnreadCount}</span>
				{/if}
			</a>
			<a href="/dashboard/map" class="nav-item">

				<span class="icon">📍</span>
				<span class="label">{$t('nav_map')}</span>
			</a>
			<a href="/spectator" target="_blank" class="nav-item">
				<span class="icon">📺</span>
				<span class="label">{$t('nav_spectator')}</span>
			</a>
			
			{#if user.is_admin}
				<div class="nav-separator"></div>
				<a href="/dashboard/admin" class="nav-item admin">
					<span class="icon">⚙️</span>
					<span class="label">{$t('nav_administration')}</span>
				</a>
			{/if}
		</div>

		<div class="nav-footer">
			{#if user.is_admin && iaInstances.filter(i => i.enabled !== false).length > 0}
				<div class="ia-status-widget">
					<div class="ia-status-title">🖥️ {$t('ia_status_title')}</div>
					{#each iaInstances.filter(i => i.enabled !== false) as inst}
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
					{#if iaQueueSize > 0 || iaQueueActive > 0}
						<div class="ia-queue-line">
							<span class="ia-queue-icon">📋</span>
							<span class="ia-queue-text">File: {iaQueueSize} en attente{iaQueueActive > 0 ? ` (${iaQueueActive} actif${iaQueueActive > 1 ? 's' : ''})` : ''}</span>
						</div>
					{/if}
				</div>
			{/if}
			<a href="/dashboard/profile" class="user-profile">
				<div class="avatar avatar-shape-{user.avatar_shape || 'circle'}">
					{#if user.avatar_url}
						<img src={user.avatar_url} alt={user.username} />
					{:else}
						{user.username[0].toUpperCase()}
					{/if}
				</div>
				<div class="info">
					<div class="username">{user.username}</div>
					<div class="role">{user.is_admin ? $t('role_admin') : $t('role_player')}</div>
				</div>
			</a>
			{#if $lanMultilingual}
				<div class="lang-selector-wrapper">
					<select bind:value={$currentLang} on:change={(e) => loadLocale(e.target.value)} class="lang-select">
						{#each $availableLanguages as l}
							<option value={l}>{flagMap[l] || l.toUpperCase()}</option>
						{/each}
					</select>
				</div>
			{/if}
			<div class="footer-actions">
				{#if browserNotifSupport && browserNotifStatus !== 'granted' && browserNotifStatus !== 'denied'}
					<button class="theme-toggle" on:click={requestBrowserNotifications} title={$t('tooltip_system_notifs')}>
						<span class="theme-icon">🔔</span>
					</button>
				{/if}
				<button class="theme-toggle" on:click={toggleTheme} title={isDark ? $t('tooltip_light_mode') : $t('tooltip_dark_mode')}>
					<span class="theme-icon" class:spin={true}>{isDark ? '☀️' : '🌙'}</span>
				</button>
				<button class="logout-btn" on:click={logout}>
					<span>{$t('logout')}</span>
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

<!-- Tutorial Overlay -->
<TutorialOverlay />

{#if showChangelog}
	<!-- svelte-ignore a11y-click-events-have-key-events -->
	<div class="changelog-overlay" on:click={() => showChangelog = false}>
		<div class="changelog-modal glass" on:click|stopPropagation>
			<div class="changelog-header">
				<h3>📜 Historique des Versions</h3>
				<button class="changelog-close" on:click={() => showChangelog = false}>✕</button>
			</div>
			
			<div class="changelog-body">
				{#if loadingChangelog}
					<div class="changelog-loading">
						<div class="spinner"></div>
						<span>Chargement des patch notes...</span>
					</div>
				{:else if changelogError}
					<div class="changelog-error">
						<span class="error-icon">⚠️</span>
						<p>{changelogError}</p>
						<button class="btn-primary btn-xs" on:click={() => { changelogData = []; openChangelog(); }}>Réessayer</button>
					</div>
				{:else if changelogData.length === 0}
					<div class="changelog-empty">
						<span>Aucune version publiée sur GitHub.</span>
					</div>
				{:else}
					<div class="changelog-list">
						{#each changelogData as rel}
							<div class="changelog-item glass">
								<div class="changelog-item-header">
									<span class="changelog-tag">{rel.tag_name}</span>
									<span class="changelog-date">{formatDate(rel.published_at)}</span>
								</div>
								<h4 class="changelog-title">{rel.name || 'Mise à jour'}</h4>
								<div class="changelog-content">
									{@html parseMarkdown(rel.body)}
								</div>
							</div>
						{/each}
					</div>
				{/if}
			</div>
		</div>
	</div>
{/if}

<!-- Global Toasts -->
<div class="global-toast-container">
	{#each globalToasts as t (t.id)}
		<!-- svelte-ignore a11y-click-events-have-key-events -->
		<div class="global-toast {t.type} {t.leaving ? 'toast-leave' : 'toast-enter'} {t.link ? 'clickable' : ''}"
			 on:click={() => { if(t.link) goto(t.link); }}
			 role={t.link ? "button" : "alert"} tabindex={t.link ? 0 : -1}>
			<div class="toast-content">{t.message}</div>
		</div>
	{/each}
</div>
{/if}


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
		overflow-y: auto;
		overflow-x: hidden;
		scrollbar-width: thin;
		scrollbar-color: var(--glass-border) transparent;
	}

	.side-nav::-webkit-scrollbar {
		width: 4px;
	}

	.side-nav::-webkit-scrollbar-track {
		background: transparent;
	}

	.side-nav::-webkit-scrollbar-thumb {
		background: var(--glass-border);
		border-radius: 4px;
	}

	.side-nav::-webkit-scrollbar-thumb:hover {
		background: var(--accent-soft);
	}

	.nav-brand {
		display: flex;
		align-items: center;
		gap: 0.75rem;
		margin-bottom: 2rem;
		padding-left: 0.3rem;
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

	.nav-item .label {
		font-size: var(--nav-font-size, 0.95rem);
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
		overflow: hidden;
	}
	.avatar img {
		width: 100%;
		height: 100%;
		object-fit: cover;
		border-radius: 50%;
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

	.lang-selector-wrapper {
		position: relative;
		margin-bottom: 0.8rem;
		width: 100%;
	}
	.lang-selector-wrapper::after {
		content: "▼";
		font-size: 0.6rem;
		position: absolute;
		right: 0.8rem;
		top: 50%;
		transform: translateY(-50%);
		color: var(--text-muted);
		pointer-events: none;
	}
	.lang-select {
		width: 100%;
		padding: 0.6rem 2rem 0.6rem 0.8rem;
		font-size: 0.8rem;
		font-weight: 600;
		border-radius: var(--radius-md);
		background: var(--hover-tint);
		border: 1px solid var(--glass-border);
		color: var(--text-main);
		cursor: pointer;
		appearance: none;
		transition: all 0.2s ease;
	}
	.lang-select:hover {
		border-color: var(--accent);
		background: var(--surface-raised);
	}
	.lang-select option {
		background: var(--bg-secondary);
		color: var(--text-main);
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

	.container {
		height: 100%;
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

	/* AI response unread badge */
	.ai-nav { position: relative; }
	.ai-count-badge {
		position: absolute; top: 4px; right: 8px;
		min-width: 18px; height: 18px; line-height: 18px;
		padding: 0 5px; border-radius: 10px;
		background: var(--accent); color: white;
		font-size: 0.6rem; font-weight: 800; text-align: center;
		box-shadow: 0 0 8px var(--accent-glow);
		animation: notif-pulse 2s ease-in-out infinite;
		will-change: opacity;
	}
	.ai-count-badge.bounce {
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
	/* Queue line in sidebar widget (G-52) */
	.ia-queue-line {
		display: flex; align-items: center; gap: 0.4rem;
		padding: 0.25rem 0; margin-top: 0.3rem;
		border-top: 1px solid rgba(255,255,255,0.06);
	}
	.ia-queue-icon { font-size: 0.65rem; }
	.ia-queue-text { font-size: 0.65rem; color: #fbbf24; font-weight: 600; }

	/* Global Toasts */
	.global-toast-container {
		position: fixed;
		bottom: 2rem;
		right: 2rem;
		display: flex;
		flex-direction: column;
		gap: 0.5rem;
		z-index: 9999;
		pointer-events: none;
	}
	.global-toast {
		background: var(--bg-secondary);
		border: 1px solid var(--glass-border);
		border-radius: var(--radius-md);
		padding: 1rem 1.5rem;
		color: var(--text-primary);
		box-shadow: 0 4px 15px rgba(0,0,0,0.3);
		backdrop-filter: blur(8px);
		font-weight: 600;
		font-size: 0.95rem;
		pointer-events: auto;
		transition: transform 0.15s, box-shadow 0.15s;
	}
	.global-toast.clickable {
		cursor: pointer;
	}
	.global-toast.clickable:hover {
		transform: scale(1.02);
		box-shadow: 0 6px 20px rgba(0,0,0,0.4);
	}
	.global-toast.info {
		border-left: 4px solid var(--accent);
	}
	.global-toast.pm {
		border-left: 4px solid #8b5cf6;
	}
	.global-toast.toast-enter {
		animation: slide-in-right 0.4s cubic-bezier(0.175, 0.885, 0.32, 1.275) forwards;
	}
	.global-toast.toast-leave {
		animation: slide-out-right 0.4s ease forwards;
	}
	@keyframes slide-in-right {
		from { transform: translateX(120%); opacity: 0; }
		to { transform: translateX(0); opacity: 1; }
	}
	@keyframes slide-out-right {
		from { transform: translateX(0); opacity: 1; }
		to { transform: translateX(120%); opacity: 0; }
	}

	/* Version Badge & Changelog Modal */
	.brand-text {
		display: flex;
		flex-direction: column;
		align-items: flex-start;
		gap: 0.15rem;
	}

	.version-badge {
		background: var(--accent-soft);
		color: var(--accent);
		border: 1px solid var(--accent-glow);
		border-radius: 12px;
		padding: 0.1rem 0.45rem;
		font-size: 0.62rem;
		font-weight: 800;
		cursor: pointer;
		transition: all 0.2s ease-in-out;
		box-shadow: 0 0 6px var(--accent-glow);
		margin: 0;
		white-space: nowrap;
	}
	.version-badge:hover {
		background: var(--accent);
		color: var(--bg-primary);
		box-shadow: 0 0 15px var(--accent-glow);
		transform: scale(1.05);
	}

	.changelog-overlay {
		position: fixed;
		top: 0;
		left: 0;
		width: 100vw;
		height: 100vh;
		background: rgba(0, 0, 0, 0.6);
		backdrop-filter: blur(8px);
		z-index: 11000;
		display: flex;
		align-items: center;
		justify-content: center;
		animation: fadeIn 0.2s ease-out forwards;
	}
	.changelog-modal {
		width: 90%;
		max-width: 600px;
		max-height: 80vh;
		background: var(--bg-secondary);
		border: 1px solid var(--glass-border);
		border-radius: var(--radius-xl);
		display: flex;
		flex-direction: column;
		overflow: hidden;
		box-shadow: 0 20px 40px rgba(0, 0, 0, 0.5), 0 0 30px var(--accent-soft);
		animation: scaleUp 0.3s cubic-bezier(0.34, 1.56, 0.64, 1) forwards;
	}
	.changelog-header {
		display: flex;
		justify-content: space-between;
		align-items: center;
		padding: 1.2rem 1.5rem;
		border-bottom: 1px solid var(--glass-border);
		background: rgba(255, 255, 255, 0.02);
	}
	.changelog-header h3 {
		margin: 0;
		font-family: var(--font-title);
		font-size: 1.1rem;
		color: var(--text-main);
	}
	.changelog-close {
		background: none;
		border: none;
		color: var(--text-muted);
		font-size: 1.2rem;
		cursor: pointer;
		transition: color 0.15s;
	}
	.changelog-close:hover {
		color: var(--danger);
	}
	.changelog-body {
		flex: 1;
		overflow-y: auto;
		padding: 1.5rem;
		display: flex;
		flex-direction: column;
		gap: 1rem;
	}
	.changelog-loading, .changelog-error, .changelog-empty {
		display: flex;
		flex-direction: column;
		align-items: center;
		justify-content: center;
		gap: 1rem;
		padding: 3rem 1rem;
		text-align: center;
		color: var(--text-muted);
	}
	.changelog-loading .spinner {
		width: 30px;
		height: 30px;
		border: 3px solid var(--glass-border);
		border-top-color: var(--accent);
		border-radius: 50%;
		animation: spin 1s linear infinite;
	}
	.changelog-list {
		display: flex;
		flex-direction: column;
		gap: 1rem;
	}
	.changelog-item {
		padding: 1.2rem;
		border-radius: var(--radius-lg);
		background: rgba(255, 255, 255, 0.01);
		border: 1px solid var(--glass-border);
		transition: transform 0.2s, border-color 0.2s;
	}
	.changelog-item:hover {
		border-color: var(--accent-soft);
		transform: translateY(-2px);
	}
	.changelog-item-header {
		display: flex;
		justify-content: space-between;
		align-items: center;
		margin-bottom: 0.5rem;
	}
	.changelog-tag {
		font-size: 0.75rem;
		font-weight: 800;
		color: var(--accent);
		background: var(--accent-soft);
		padding: 0.15rem 0.5rem;
		border-radius: 12px;
		border: 1px solid var(--accent-glow);
	}
	.changelog-date {
		font-size: 0.75rem;
		color: var(--text-muted);
	}
	.changelog-title {
		margin: 0 0 0.8rem 0;
		font-size: 0.95rem;
		font-weight: 700;
		color: var(--text-main);
	}
	.changelog-content {
		font-size: 0.82rem;
		line-height: 1.5;
		color: var(--text-dim);
	}
	.changelog-content h2, .changelog-content h3, .changelog-content h4 {
		margin: 1rem 0 0.5rem 0;
		color: var(--text-main);
	}
	.changelog-content li {
		margin-bottom: 0.25rem;
	}
	.changelog-content code {
		background: var(--surface-sunken);
		padding: 0.1rem 0.3rem;
		border-radius: 4px;
		font-family: monospace;
		color: var(--accent);
	}

	@keyframes fadeIn {
		from { opacity: 0; }
		to { opacity: 1; }
	}
	@keyframes scaleUp {
		from { transform: scale(0.95); opacity: 0; }
		to { transform: scale(1); opacity: 1; }
	}
</style>
