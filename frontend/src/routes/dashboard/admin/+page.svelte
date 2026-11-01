<script>
	import { onMount, onDestroy, tick } from 'svelte';
	import { api } from '$lib/api';
	import { wsMessageStore } from '$lib/ws';
	import { t, customPageTitle } from '$lib/i18nStore';
	import Icon from '$lib/components/Icon.svelte';
	import AdminTournamentsTab from './components/AdminTournamentsTab.svelte';
	import AdminPlayersTab from './components/AdminPlayersTab.svelte';
	import AdminSettingsTab from './components/AdminSettingsTab.svelte';
	import AdminConversationsTab from './components/AdminConversationsTab.svelte';
	import AdminAwardsTab from './components/AdminAwardsTab.svelte';
	import AdminRegieTab from './components/AdminRegieTab.svelte';
	import { SETUP_STEPS, loadSetupRaw, saveSetup } from '$lib/adminSetup';
	let regiePending = 0;

	// Guided setup reminder: shown until the admin finishes or hides it
	let setupState = undefined;
	$: setupPending = setupState !== undefined && (!setupState || setupState.status === 'in_progress');
	$: setupDone = setupState ? SETUP_STEPS.filter(s => setupState.steps?.[s.id]).length : 0;
	async function hideSetup() {
		setupState = { current: 'event', steps: {}, ...(setupState || {}), status: 'skipped' };
		await saveSetup(setupState);
	}

	// Phone: the tab strip scrolls; fade the edges that hide more tabs and keep the active one in view
	let tabsEl;
	let fadeStart = false;
	let fadeEnd = false;
	function updateFade() {
		if (!tabsEl) return;
		fadeStart = tabsEl.scrollLeft > 4;
		fadeEnd = tabsEl.scrollLeft + tabsEl.clientWidth < tabsEl.scrollWidth - 4;
	}
	async function centerActiveTab() {
		await tick();
		tabsEl?.querySelector('button.active')?.scrollIntoView({ inline: 'center', block: 'nearest', behavior: 'smooth' });
		updateFade();
	}
	$: if (tabsEl && activeTab) centerActiveTab();

	let authorized = false;
	let wsUnsub = null;

	let activeTab = (typeof localStorage !== 'undefined' && localStorage.getItem('admin_tab')) || 'regie';
	if (activeTab === 'games') activeTab = 'tournaments';
	let settingsSubTab = (typeof localStorage !== 'undefined' && localStorage.getItem('admin_subtab')) || 'general';
	let selectedConvId = null;
	let playersInitialQuery = '';

	let playersTabRef = null;
	let conversationsTabRef = null;
	let awardsTabRef = null;

	$: if (typeof localStorage !== 'undefined') localStorage.setItem('admin_tab', activeTab);
	$: if (typeof localStorage !== 'undefined') localStorage.setItem('admin_subtab', settingsSubTab);

	$: {
		let baseAdmin = $t('nav_administration');
		let tabName = baseAdmin;
		if (activeTab === 'regie') tabName = `${baseAdmin} - ${$t('admin_tab_regie')}`;
		else if (activeTab === 'tournaments') tabName = `${baseAdmin} - ${$t('admin_tab_tournaments')}`;
		else if (activeTab === 'players') tabName = `${baseAdmin} - ${$t('admin_tab_players')}`;
		else if (activeTab === 'settings') tabName = `${baseAdmin} - ${$t('admin_tab_settings')}`;
		else if (activeTab === 'conversations') tabName = `${baseAdmin} - ${$t('admin_tab_conversations')}`;
		else if (activeTab === 'awards') tabName = `${baseAdmin} - ${$t('admin_tab_awards')}`;
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

		loadSetupRaw().then(s => setupState = s);
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


{#if authorized}
<div class="admin-view">
	<header class="flex-row justify-between items-center">
		<h1 class="title-premium">{$t('admin_title')}</h1>
		<div class="tabs glass" class:fade-start={fadeStart} class:fade-end={fadeEnd} bind:this={tabsEl} on:scroll={updateFade}>
			<button class={activeTab === 'regie' ? 'active' : ''} on:click={() => activeTab = 'regie'}>
				{$t('admin_tab_regie')}
				{#if regiePending > 0}<span class="regie-badge">{regiePending}</span>{/if}
			</button>
			<button class={activeTab === 'tournaments' ? 'active' : ''} on:click={() => activeTab = 'tournaments'}>{$t('admin_tab_tournaments')}</button>
			<button class={activeTab === 'players' ? 'active' : ''} on:click={() => { activeTab = 'players'; if (playersTabRef) playersTabRef.loadPlayers(); }}>{$t('admin_tab_players')}</button>
			<button class={activeTab === 'settings' ? 'active' : ''} on:click={() => activeTab = 'settings'}>{$t('admin_tab_settings')}</button>
			<button class={activeTab === 'conversations' ? 'active' : ''} on:click={() => { activeTab = 'conversations'; if (conversationsTabRef) conversationsTabRef.loadAdminConversations(); }}>
				{$t('admin_tab_chats')}
				{#if adminUnreadConvsCount > 0}
					<span class="tab-unread-badge" style="background:#22c55e;color:white;padding:0.1rem 0.4rem;border-radius:10px;font-size: 0.75rem;font-weight:bold;margin-left:0.4rem">{adminUnreadConvsCount}</span>
				{/if}
			</button>
			<button class={activeTab === 'awards' ? 'active' : ''} on:click={() => { activeTab = 'awards'; if (awardsTabRef) awardsTabRef.loadAwardsTab(); }}><Icon name="trophy" size={15} /> {$t('admin_tab_awards')}</button>
			<button class="desktop-only" on:click={() => window.location.href = '/dashboard/admin/languages'}><Icon name="globe" size={15} /> {$t('admin_tab_languages')}</button>
		</div>
	</header>

	{#if setupPending}
		<div class="setup-banner" role="status">
			<span class="setup-banner-icon"><Icon name="flag" size={20} /></span>
			<div class="setup-banner-text">
				<strong>{$t(setupState ? 'setup_banner_resume_title' : 'setup_banner_title')}</strong>
				<span>{setupState ? $t('setup_banner_resume_desc', { done: setupDone, total: SETUP_STEPS.length - 1 }) : $t('setup_banner_desc')}</span>
			</div>
			<div class="setup-banner-actions">
				<button class="btn-quiet-sm" on:click={hideSetup}>{$t('setup_banner_hide')}</button>
				<a class="btn-primary" href="/dashboard/setup">{$t(setupState ? 'setup_banner_resume' : 'setup_banner_start')}</a>
			</div>
		</div>
	{/if}

	<div class="tab-content animate-in">
		{#if activeTab === 'regie'}
			<AdminRegieTab {games} {tournaments} onReload={loadGamesAndTournaments} onOpenConversation={(id) => { selectedConvId = id; activeTab = 'conversations'; }} onOpenPlayer={(name) => { playersInitialQuery = name; activeTab = 'players'; }} bind:pendingCount={regiePending} {toast} />
		{:else if activeTab === 'tournaments'}
			<AdminTournamentsTab {games} {tournaments} onReload={loadGamesAndTournaments} {toast} />
		{:else if activeTab === 'players'}
			<AdminPlayersTab bind:this={playersTabRef} initialQuery={playersInitialQuery} {toast} />
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
				<Icon name={t.type === 'success' ? 'check-circle' : t.type === 'error' ? 'x-circle' : 'info'} size={18} />
			</span>
			<span class="toast-msg">{t.message}</span>
		</div>
	{/each}
</div>
{/if}

<style>
	.admin-view { display: flex; flex-direction: column; gap: 2rem; }
	.tabs { display: flex; padding: 0.3rem; border-radius: 12px; background: var(--surface-sunken); border: 1px solid var(--glass-border); flex-wrap: wrap; gap: 0.25rem; }
	.tabs button { display: inline-flex; align-items: center; justify-content: center; gap: 0.4rem; padding: 0.6rem 1.1rem; border: none; background: transparent; color: var(--text-dim); cursor: pointer; font-weight: 600; border-radius: 8px; transition: all 0.2s cubic-bezier(0.16, 1, 0.3, 1); font-size: var(--fs-sub); font-family: var(--font-main); }
	.tabs button:hover:not(.active) { color: var(--text-main); background: var(--hover-tint); }
	.tabs button.active { background: var(--accent-solid); color: white; box-shadow: 0 4px 14px var(--accent-glow); font-weight: 700; }

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
	.setup-banner { display: flex; align-items: center; gap: 1rem; padding: 1rem 1.25rem; border: 1px solid color-mix(in srgb, var(--accent) 35%, var(--glass-border)); border-radius: 14px; background: color-mix(in srgb, var(--accent) 7%, var(--surface-raised)); }
	.setup-banner-icon { flex-shrink: 0; width: 40px; height: 40px; border-radius: 10px; display: inline-flex; align-items: center; justify-content: center; background: var(--accent-soft); color: var(--accent); }
	.setup-banner-text { flex: 1; display: flex; flex-direction: column; gap: 0.15rem; min-width: 0; }
	.setup-banner-text span { font-size: 0.88rem; color: var(--text-dim); line-height: 1.45; }
	.setup-banner-actions { display: flex; align-items: center; gap: 0.5rem; flex-shrink: 0; }
	.setup-banner-actions .btn-primary { text-decoration: none; white-space: nowrap; }
	.btn-quiet-sm { background: transparent; border: none; color: var(--text-dim); font: inherit; font-size: 0.85rem; font-weight: 600; padding: 0.5rem 0.7rem; border-radius: 8px; cursor: pointer; }
	.btn-quiet-sm:hover { color: var(--text-main); background: var(--hover-tint); }
	@media (max-width: 600px) {
		.setup-banner { flex-wrap: wrap; padding: 0.9rem; gap: 0.75rem; }
		.setup-banner-icon { display: none; }
		.setup-banner-actions { width: 100%; justify-content: flex-end; }
	}
	.regie-badge { background: var(--danger); color: #fff; padding: 0.05rem 0.45rem; border-radius: 999px; font-size: 0.72rem; font-weight: 700; margin-left: 0.4rem; }
	/* Phone: title above, tabs as one horizontally scrollable strip */
	@media (max-width: 900px) {
		.admin-view { gap: 0.75rem; }
		.admin-view > header { flex-direction: column; align-items: stretch; gap: 0.5rem; }
		.admin-view h1 { font-size: 1.35rem; margin: 0; }
		.tabs { flex-wrap: nowrap; overflow-x: auto; scrollbar-width: none; padding: 0.2rem; }
		.tabs::-webkit-scrollbar { display: none; }
		.tabs button { flex-shrink: 0; white-space: nowrap; padding: 0.5rem 0.85rem; }
		/* the translation editor is for computers only */
		.tabs button.desktop-only { display: none; }
		/* the edges that hide other tabs fade out */
		.tabs.fade-end { -webkit-mask-image: linear-gradient(to right, #000 calc(100% - 36px), transparent); mask-image: linear-gradient(to right, #000 calc(100% - 36px), transparent); }
		.tabs.fade-start { -webkit-mask-image: linear-gradient(to left, #000 calc(100% - 36px), transparent); mask-image: linear-gradient(to left, #000 calc(100% - 36px), transparent); }
		.tabs.fade-start.fade-end { -webkit-mask-image: linear-gradient(to right, transparent, #000 36px, #000 calc(100% - 36px), transparent); mask-image: linear-gradient(to right, transparent, #000 36px, #000 calc(100% - 36px), transparent); }

		/* Flat sections: the content gets the full width instead of a card inside a card, and the page scrolls once */
		.tab-content :global(section.glass),
		.tab-content :global(.players-view.glass) {
			background: transparent; border: none; box-shadow: none; backdrop-filter: none; border-radius: 0;
			padding: 0.25rem 0 !important;
			max-height: none !important; overflow: visible !important;
		}
		.tab-content :global(section.glass + section.glass),
		.tab-content :global(section.glass + .players-view.glass) {
			border-top: 1px solid var(--glass-border); padding-top: 1rem !important;
		}
		.tab-content :global(.rg-list) { max-height: none; overflow: visible; }
		/* Exception: the AI conversations list stays in its own scrolling frame so the admin calls below stay close */
		.tab-content :global(section.glass.conv-list) {
			max-height: min(55vh, 460px) !important; overflow-y: auto !important; overscroll-behavior: contain;
			border: 1px solid var(--glass-border); border-radius: 12px; padding: 0.5rem 0.6rem !important;
			background: var(--surface-sunken);
		}
	}
	@media (max-width: 1100px) { :global(html.conv-chat-open) .admin-view > header { display: none; } }
</style>
