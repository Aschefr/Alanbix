<script>
	import { onMount, onDestroy } from 'svelte';
	import { api } from '$lib/api';
	import { wsMessageStore } from '$lib/ws';
	import { t, customPageTitle } from '$lib/i18nStore';
	import AdminTournamentsTab from './components/AdminTournamentsTab.svelte';
	import AdminPlayersTab from './components/AdminPlayersTab.svelte';
	import AdminSettingsTab from './components/AdminSettingsTab.svelte';
	import AdminConversationsTab from './components/AdminConversationsTab.svelte';
	import AdminAwardsTab from './components/AdminAwardsTab.svelte';

	let authorized = false;
	let wsUnsub = null;

	let activeTab = (typeof localStorage !== 'undefined' && localStorage.getItem('admin_tab')) || 'tournaments';
	if (activeTab === 'games') activeTab = 'tournaments';
	let settingsSubTab = (typeof localStorage !== 'undefined' && localStorage.getItem('admin_subtab')) || 'general';
	let selectedConvId = null;

	let playersTabRef = null;
	let conversationsTabRef = null;
	let awardsTabRef = null;

	$: if (typeof localStorage !== 'undefined') localStorage.setItem('admin_tab', activeTab);
	$: if (typeof localStorage !== 'undefined') localStorage.setItem('admin_subtab', settingsSubTab);

	$: {
		let baseAdmin = $t('nav_administration') || 'Administration';
		let tabName = baseAdmin;
		if (activeTab === 'tournaments') tabName = `${baseAdmin} - ${$t('admin_tab_tournaments') || 'Tournois & Jeux'}`;
		else if (activeTab === 'players') tabName = `${baseAdmin} - ${$t('admin_tab_players') || 'Gestion Joueurs'}`;
		else if (activeTab === 'settings') tabName = `${baseAdmin} - ${$t('admin_tab_settings') || 'IA & Paramètres'}`;
		else if (activeTab === 'conversations') tabName = `${baseAdmin} - ${$t('admin_tab_conversations') || 'Conversations IA'}`;
		else if (activeTab === 'awards') tabName = `${baseAdmin} - ${$t('admin_tab_awards') || 'Prix & Distinctions'}`;
		customPageTitle.set(tabName);
	}

	// Tournaments & Games state (passed down to TournamentsTab)
	let games = [];
	let tournaments = [];
	let adminUnreadConvsCount = 0;

	// Toast Notification System
	let toasts = [];
	let toastId = 0;
	function toast(message, type = 'info') {
		const id = ++toastId;
		toasts = [...toasts, { id, message, type, leaving: false }];
		setTimeout(() => {
			toasts = toasts.map(t => t.id === id ? { ...t, leaving: true } : t);
			setTimeout(() => { toasts = toasts.filter(t => t.id !== id); }, 400);
		}, 3000);
	}

	function portal(node) {
		document.body.appendChild(node);
		return {
			destroy() {
				if (node.parentNode) {
					node.parentNode.removeChild(node);
				}
			}
		};
	}

	async function loadGamesAndTournaments() {
		try { games = await api.get('/tournaments/games'); } catch {}
		try { tournaments = await api.get('/tournaments'); } catch {}
	}

	async function loadAdminUnreadCount() {
		try {
			const convs = await api.get('/ia/admin/conversations');
			adminUnreadConvsCount = convs.reduce((sum, c) => sum + (c.unread_count || 0), 0);
		} catch {}
	}

	function handleDataReset() {
		loadGamesAndTournaments();
		loadAdminUnreadCount();
	}

	onMount(async () => {
		try {
			const me = await api.get('/me');
			if (!me.is_admin) {
				window.location.href = '/dashboard';
				return;
			}
			authorized = true;
		} catch {
			window.location.href = '/';
			return;
		}

		await loadGamesAndTournaments();
		await loadAdminUnreadCount();

		// URL query parameters routing
		const params = new URLSearchParams(window.location.search);
		const tabParam = params.get('tab');
		const convParam = params.get('conv');
		const subtabParam = params.get('subtab');
		const scrollToParam = params.get('scroll_to');

		if (tabParam) activeTab = tabParam;
		if (convParam) selectedConvId = parseInt(convParam, 10);
		if (subtabParam) settingsSubTab = subtabParam;

		if (scrollToParam) {
			setTimeout(() => {
				const el = document.getElementById(scrollToParam);
				if (el) el.scrollIntoView({ behavior: 'smooth', block: 'center' });
			}, 300);
		}

		wsUnsub = wsMessageStore.subscribe(msg => {
			if (!msg) return;
			if (msg.type === 'games_updated' || msg.type?.startsWith('tournament_')) {
				loadGamesAndTournaments();
			}
			if (msg.type === 'chat_updated' || msg.type === 'user_message_during_override') {
				loadAdminUnreadCount();
			}
		});
	});

	onDestroy(() => {
		if (wsUnsub) wsUnsub();
	});
</script>

<svelte:head>
	<link rel="stylesheet" href="https://unpkg.com/easymde/dist/easymde.min.css" />
</svelte:head>

{#if authorized}
<div class="admin-view">
	<header class="flex-row justify-between items-center">
		<h1 class="title-premium">{$t('admin_title') || 'Administration Centrale'}</h1>
		<div class="tabs glass">
			<button class={activeTab === 'tournaments' ? 'active' : ''} on:click={() => activeTab = 'tournaments'}>{$t('admin_tab_tournaments') || 'Tournois'}</button>
			<button class={activeTab === 'players' ? 'active' : ''} on:click={() => { activeTab = 'players'; if (playersTabRef) playersTabRef.loadPlayers(); }}>{$t('admin_tab_players') || 'Gestion Joueurs'}</button>
			<button class={activeTab === 'settings' ? 'active' : ''} on:click={() => activeTab = 'settings'}>{$t('admin_tab_settings') || 'IA & Paramètres'}</button>
			<button class={activeTab === 'conversations' ? 'active' : ''} on:click={() => { activeTab = 'conversations'; if (conversationsTabRef) conversationsTabRef.loadAdminConversations(); }}>
				{$t('admin_tab_chats')}
				{#if adminUnreadConvsCount > 0}
					<span class="tab-unread-badge" style="background:#22c55e;color:white;padding:0.1rem 0.4rem;border-radius:10px;font-size:0.65rem;font-weight:bold;margin-left:0.4rem">{adminUnreadConvsCount}</span>
				{/if}
			</button>
			<button class={activeTab === 'awards' ? 'active' : ''} on:click={() => { activeTab = 'awards'; if (awardsTabRef) awardsTabRef.loadAwardsTab(); }}>🏆 {$t('admin_tab_awards') || 'Prix & Distinctions'}</button>
			<button on:click={() => window.location.href = '/dashboard/admin/languages'}>🌐 {$t('admin_tab_languages')}</button>
		</div>
	</header>

	<div class="tab-content animate-in">
		{#if activeTab === 'tournaments'}
			<AdminTournamentsTab {games} {tournaments} onReload={loadGamesAndTournaments} {toast} />
		{:else if activeTab === 'players'}
			<AdminPlayersTab bind:this={playersTabRef} {toast} />
		{:else if activeTab === 'settings'}
			<AdminSettingsTab bind:settingsSubTab onDataReset={handleDataReset} {toast} />
		{:else if activeTab === 'conversations'}
			<AdminConversationsTab bind:this={conversationsTabRef} initialConvId={selectedConvId} bind:unreadCount={adminUnreadConvsCount} {toast} />
		{:else if activeTab === 'awards'}
			<AdminAwardsTab bind:this={awardsTabRef} {toast} />
		{/if}
	</div>
</div>

<!-- Toast Notifications -->
<div class="toast-container" use:portal>
	{#each toasts as t (t.id)}
		<div class="toast {t.type} {t.leaving ? 'toast-leave' : 'toast-enter'}">
			<span class="toast-icon">
				{#if t.type === 'success'}✅{:else if t.type === 'error'}❌{:else}ℹ️{/if}
			</span>
			<span class="toast-msg">{t.message}</span>
		</div>
	{/each}
</div>
{/if}

<style>
	.admin-view { display: flex; flex-direction: column; gap: 2rem; }
	.tabs { display: flex; padding: 0.3rem; border-radius: 12px; background: var(--surface-sunken); border: 1px solid var(--glass-border); }
	.tabs button { padding: 0.6rem 1.2rem; border: none; background: transparent; color: var(--text-dim); cursor: pointer; font-weight: 600; border-radius: 8px; transition: all 0.2s; font-size: 0.85rem; }
	.tabs button.active { background: var(--accent); color: white; box-shadow: 0 4px 12px var(--accent-glow); }

	/* Toast System */
	.toast-container { position: fixed; top: 1.5rem; right: 1.5rem; z-index: 10000; display: flex; flex-direction: column; gap: 0.75rem; pointer-events: none; }
	.toast { display: flex; align-items: center; gap: 0.75rem; padding: 0.8rem 1.4rem; border-radius: 12px; backdrop-filter: blur(16px); border: 1px solid var(--glass-border); box-shadow: 0 10px 30px rgba(0,0,0,0.4); font-size: 0.88rem; font-weight: 600; pointer-events: auto; min-width: 260px; }
	.toast.success { background: rgba(16, 185, 129, 0.15); border-color: rgba(16, 185, 129, 0.3); color: #10b981; }
	.toast.error { background: rgba(239, 68, 68, 0.15); border-color: rgba(239, 68, 68, 0.3); color: var(--danger); }
	.toast.info { background: rgba(59, 130, 246, 0.15); border-color: rgba(59, 130, 246, 0.3); color: var(--accent); }
	.toast-icon { font-size: 1rem; }
	.toast-msg { flex-grow: 1; }

	.toast-enter { animation: toastIn 0.4s cubic-bezier(0.16, 1, 0.3, 1) forwards; }
	.toast-leave { animation: toastOut 0.4s ease-in forwards; }

	@keyframes toastIn {
		from { opacity: 0; transform: translateX(80px) scale(0.9); }
		to { opacity: 1; transform: translateX(0) scale(1); }
	}
	@keyframes toastOut {
		from { opacity: 1; transform: translateX(0) scale(1); }
		to { opacity: 0; transform: translateX(80px) scale(0.9); }
	}
</style>
