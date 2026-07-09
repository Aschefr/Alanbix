<script>
	import { api } from '$lib/api';
	import { onMount, onDestroy } from 'svelte';
	import { wsMessageStore } from '$lib/ws';
	import { goto } from '$app/navigation';
	import { t, currentLang } from '$lib/i18nStore';

	let notifications = [];
	let loading = true;

	onMount(async () => {
		await loadNotifications();
	});

	// WS: auto-refresh on new notifications
	let wsUnsub = wsMessageStore.subscribe(msg => {
		if (msg && msg.type === 'notification_new') {
			loadNotifications();
		}
	});
	onDestroy(() => { if (wsUnsub) wsUnsub(); });

	async function loadNotifications() {
		loading = true;
		try {
			notifications = await api.get('/notifications');
		} catch { notifications = []; }
		loading = false;
	}

	async function markRead(id) {
		try {
			await api.put(`/notifications/${id}/read`, {});
			notifications = notifications.map(n => n.id === id ? { ...n, is_read: true } : n);
		} catch {}
	}

	async function markAllRead() {
		try {
			await api.put('/notifications/read-all', {});
			notifications = notifications.map(n => ({ ...n, is_read: true }));
		} catch {}
	}

	async function deleteNotif(id) {
		try {
			await api.delete(`/notifications/${id}`);
			notifications = notifications.filter(n => n.id !== id);
		} catch {}
	}

	let expandedNotifs = {};
	function toggleExpand(id, isRead) {
		expandedNotifs[id] = !expandedNotifs[id];
		expandedNotifs = expandedNotifs;
		if (!isRead) {
			markRead(id);
		}
	}

	function handleActionClick(n) {
		if (n.metadata?.tournament_id) {
			goto(`/dashboard/tournaments?select=${n.metadata.tournament_id}`);
		} else if (n.metadata?.conversation_id) {
			goto(`/dashboard/ai?conv=${n.metadata.conversation_id}`);
		}
	}

	function getIcon(type) {
		if (type === 'tournament_closed') return '🏆';
		if (type === 'admin_message') return '🛡️';
		if (type === 'system') return '⚠️';
		if (type === 'award') return '🎁';
		return '📢';
	}

	let retrying = {};
	async function retryNotifications(n) {
		const tid = n.metadata?.tournament_id;
		if (!tid) return;
		retrying[n.id] = true;
		retrying = retrying;
		try {
			await api.post(`/tournaments/${tid}/retry-notifications`, {});
			// Delete the error notification since we're retrying
			await api.delete(`/notifications/${n.id}`);
			notifications = notifications.filter(x => x.id !== n.id);
		} catch (e) {
			alert('Échec: ' + (e.message || e));
		}
		delete retrying[n.id];
		retrying = retrying;
	}

	function timeAgo(dateStr, lang) {
		if (!dateStr) return '';
		let dStr = dateStr.replace(' ', 'T');
		if (!dStr.endsWith('Z')) dStr += 'Z';
		let diff = (Date.now() - new Date(dStr).getTime()) / 1000;
		if (diff < 0) diff = 0;
		const isEn = lang === 'en';
		if (diff < 60) return isEn ? "just now" : "à l'instant";
		if (diff < 3600) {
			const m = Math.floor(diff / 60);
			return isEn ? `${m}m ago` : `il y a ${m} min`;
		}
		if (diff < 86400) {
			const h = Math.floor(diff / 3600);
			return isEn ? `${h}h ago` : `il y a ${h}h`;
		}
		const j = Math.floor(diff / 86400);
		return isEn ? `${j}d ago` : `il y a ${j}j`;
	}

	import { pmUnreadCount, groupUnreadCount, totalMsgUnread, notifUnreadCount } from '$lib/pmStore';

	$: unreadCount = notifications.filter(n => !n.is_read).length;
	$: $notifUnreadCount = unreadCount;
</script>

<div class="notif-page animate-in">
	<header class="notif-header glass">
		<div class="header-left">
			<h1 class="title-premium"><span class="title-icon">🔔</span> {$t('nav_notifications')}</h1>
			{#if unreadCount > 0}
				<span class="unread-badge">{unreadCount} {$t('notif_unread', { plural: unreadCount > 1 ? 's' : '' })}</span>
			{/if}
		</div>
		{#if unreadCount > 0}
			<button class="btn-primary btn-sm" on:click={markAllRead}>✓ {$t('notifs_mark_all_read')}</button>
		{/if}
	</header>

	{#if loading}
		<div class="loading-state glass">
			<span class="spinner">⏳</span> {$t('notif_loading')}
		</div>
	{:else if notifications.length === 0}
		<div class="empty-state glass">
			<span class="empty-icon">🔕</span>
			<p>{$t('notifs_empty')}</p>
			<p class="text-dim text-sm">{$t('notifs_empty_desc')}</p>
		</div>
	{:else}
		<div class="notif-list">
			{#each notifications as n (n.id)}
				<div class="notif-card glass {n.is_read ? 'read' : 'unread'} {n.metadata?.error ? 'error' : ''} {expandedNotifs[n.id] ? 'expanded' : ''}"
					class:expandable={n.content && n.content.length > 140}
					on:click={() => {
						if (n.content && n.content.length > 140) {
							toggleExpand(n.id, n.is_read);
						} else if (!n.is_read) {
							markRead(n.id);
						}
					}}
					on:keydown={(e) => {
						if (e.key === 'Enter') {
							if (n.content && n.content.length > 140) {
								toggleExpand(n.id, n.is_read);
							} else if (!n.is_read) {
								markRead(n.id);
							}
						}
					}}
					role="button" tabindex="0"
				>
					<div class="notif-icon">{getIcon(n.type)}</div>
					<div class="notif-body">
						<div class="notif-title-row">
							<span class="notif-title">{n.title}</span>
							{#if !n.is_read}<span class="new-badge">{n.metadata?.error ? $t('notifs_error') : $t('notifs_new')}</span>{/if}
						</div>
						<p class="notif-content">{n.content}</p>
						<div class="notif-footer-row">
							<span class="notif-time">{timeAgo(n.created_at, $currentLang)}</span>
							{#if n.metadata?.tournament_id || n.metadata?.conversation_id}
								<button class="action-link-btn" on:click|stopPropagation={() => handleActionClick(n)}>
									➡️ Voir les détails
								</button>
							{/if}
							{#if n.metadata?.error && n.metadata?.tournament_id}
								<button class="retry-btn" on:click|stopPropagation={() => retryNotifications(n)} disabled={retrying[n.id]}>
									{retrying[n.id] ? '⏳ ...' : '🔄 ' + $t('notif_retry')}
								</button>
							{/if}
						</div>
					</div>
					<button
						class="notif-delete"
						on:click|stopPropagation={() => deleteNotif(n.id)}
						title={$t('notif_delete_tooltip')}
					>🗑️</button>
				</div>
			{/each}
		</div>
	{/if}
</div>

<style>
	.notif-page { display: flex; flex-direction: column; gap: 1rem; max-width: 700px; margin: 0 auto; }
	.notif-header { display: flex; align-items: center; justify-content: space-between; padding: 1.5rem 2rem; border-radius: 16px; }
	.header-left { display: flex; align-items: center; gap: 1rem; }
	.header-left h1 { margin: 0; font-size: 1.3rem; }
	.unread-badge { display: inline-block; padding: 0.25rem 0.7rem; border-radius: 20px; font-size: 0.7rem; font-weight: 800; background: rgba(59,130,246,0.15); color: var(--accent); border: 1px solid rgba(59,130,246,0.3); }
	.btn-sm { font-size: 0.8rem; padding: 0.5rem 1rem; }

	.empty-state, .loading-state { text-align: center; padding: 3rem; border-radius: 16px; }
	.empty-icon { font-size: 3rem; display: block; margin-bottom: 1rem; }
	.spinner { font-size: 1.5rem; }

	.notif-list { display: flex; flex-direction: column; gap: 0.5rem; }

	.notif-card {
		display: flex; align-items: flex-start; gap: 1rem; padding: 1rem 1.2rem;
		border-radius: 12px; cursor: default; transition: all 0.2s;
		border-left: 3px solid transparent;
	}
	.notif-card.expandable {
		cursor: pointer;
	}
	.notif-card.unread:not(.expandable) {
		cursor: pointer; /* Unread ones can still be clicked to mark read */
	}
	.notif-card.unread {
		border-left-color: var(--accent);
		background: rgba(59,130,246,0.04);
	}
	.notif-card.read { opacity: 0.85; }
	.notif-card:hover { transform: translateX(3px); opacity: 1; }

	.notif-icon { font-size: 1.5rem; flex-shrink: 0; margin-top: 0.1rem; }

	.notif-body { flex: 1; min-width: 0; }
	.notif-title-row { display: flex; align-items: center; gap: 0.6rem; margin-bottom: 0.3rem; }
	.notif-title { font-weight: 700; font-size: 0.85rem; color: var(--text-main); }
	.new-badge {
		font-size: 0.55rem; font-weight: 800; text-transform: uppercase; letter-spacing: 0.05em;
		padding: 0.15rem 0.5rem; border-radius: 10px;
		background: rgba(59,130,246,0.15); color: var(--accent); border: 1px solid rgba(59,130,246,0.3);
		animation: pulse-new 2s ease-in-out infinite;
	}
	@keyframes pulse-new { 0%, 100% { opacity: 1; } 50% { opacity: 0.5; } }

	.notif-content {
		font-size: 0.82rem; color: var(--text-dim); margin: 0; line-height: 1.5;
		display: -webkit-box; -webkit-line-clamp: 3; -webkit-box-orient: vertical; overflow: hidden;
		transition: max-height 0.2s ease-out;
	}
	.notif-card.expanded .notif-content {
		display: block;
		overflow: visible;
		-webkit-line-clamp: none;
	}
	.notif-card.expanded {
		background: rgba(255, 255, 255, 0.02);
	}
	.notif-time { font-size: 0.65rem; color: var(--text-muted); margin-top: 0.4rem; display: inline-block; }

	.notif-delete {
		flex-shrink: 0; background: transparent; border: none; cursor: pointer;
		font-size: 0.9rem; opacity: 0.3; transition: all 0.15s; padding: 0.3rem;
		border-radius: 6px;
	}
	.notif-delete:hover { opacity: 1; background: rgba(239,68,68,0.1); }

	/* Error notification card */
	.notif-card.error { border-left-color: #ef4444; background: rgba(239,68,68,0.04); }
	.notif-card.error .new-badge { background: rgba(239,68,68,0.15); color: #ef4444; border-color: rgba(239,68,68,0.3); }
	.notif-footer-row { display: flex; align-items: center; justify-content: space-between; gap: 0.8rem; margin-top: 0.4rem; }
	
	.action-link-btn {
		padding: 0.25rem 0.6rem; border-radius: 6px; font-size: 0.7rem; font-weight: 700;
		background: rgba(59,130,246,0.1); color: var(--accent); border: 1px solid rgba(59,130,246,0.2);
		cursor: pointer; transition: all 0.15s;
	}
	.action-link-btn:hover { background: rgba(59,130,246,0.2); transform: translateY(-1px); }

	.retry-btn {
		padding: 0.25rem 0.7rem; border-radius: 8px; font-size: 0.7rem; font-weight: 700;
		background: rgba(59,130,246,0.12); color: var(--accent); border: 1px solid rgba(59,130,246,0.3);
		cursor: pointer; transition: all 0.15s;
	}
	.retry-btn:hover { background: rgba(59,130,246,0.25); transform: scale(1.05); }
	.retry-btn:disabled { opacity: 0.5; cursor: wait; }
</style>
