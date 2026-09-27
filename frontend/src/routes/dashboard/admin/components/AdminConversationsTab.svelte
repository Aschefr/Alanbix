<script>
	import { get } from 'svelte/store';
	import { onMount, onDestroy, tick } from 'svelte';
	import { marked } from 'marked';
	import { api } from '$lib/api';
	import { API_URL } from '$lib/config';
	import { t } from '$lib/i18nStore';
	import { wsMessageStore } from '$lib/ws';

	marked.setOptions({ breaks: true, gfm: true });
	function parseMd(text) { return text ? marked.parse(text) : ''; }

	export let toast = (msg, type) => {};
	export let initialConvId = null;
	export let unreadCount = 0;

	let wsUnsub = null;

	// --- Admin Conversation Monitoring ---
	let adminConversations = [];
	let collapsedPlayers = {};
	function togglePlayerCollapse(username) {
		collapsedPlayers[username] = !collapsedPlayers[username];
	}

	$: groupedConversations = (() => {
		const groups = {};
		adminConversations.forEach(c => {
			const user = c.username || 'Inconnu';
			if (!groups[user]) {
				groups[user] = {
					username: user,
					conversations: [],
					has_unread: false,
					is_online: c.is_online || false
				};
			}
			if (c.is_online) {
				groups[user].is_online = true;
			}
			groups[user].conversations.push(c);
			if (c.has_new_messages) {
				groups[user].has_unread = true;
			}
		});
		return Object.values(groups).sort((a, b) => {
			const maxA = Math.max(...a.conversations.map(c => new Date(c.last_message_at || 0).getTime()));
			const maxB = Math.max(...b.conversations.map(c => new Date(c.last_message_at || 0).getTime()));
			return maxB - maxA;
		});
	})();

	$: adminUnreadConvsCount = adminConversations.reduce((sum, c) => sum + (c.unread_count || 0), 0);
	$: unreadCount = adminUnreadConvsCount;

	let adminActiveConvId = null;
	let adminConvMessages = [];
	let adminConvInfo = null;
	let adminInterveneText = '';
	let adminChatContainer = null;
	let adminLastReadMessageId = null;
	let adminFirstUnreadIdx = -1;
	let adminShowScrollToBottom = false;

	let adminPendingImage = null;
	let adminImagePreview = '';
	let adminFileInput = null;

	// Appels Admin & Suggestions RAG
	let adminCalls = [];
	let ragSuggestions = [];
	let ragAnswers = {};

	onMount(async () => {
		await loadAdminConversations();
		await loadAdminCalls();
		await loadRagSuggestions();

		if (initialConvId) {
			const convId = parseInt(initialConvId, 10);
			if (!isNaN(convId)) {
				selectAdminConv(convId);
			}
		}

		wsUnsub = wsMessageStore.subscribe(msg => {
			if (!msg) return;
			if (msg.type === 'admin_calls_updated') {
				loadAdminCalls();
			}
			if (msg.type === 'rag_suggestions_updated') {
				loadRagSuggestions();
			}
			if (msg.type === 'ia_message_deleted') {
				if (adminActiveConvId === msg.conversation_id) {
					selectAdminConv(adminActiveConvId);
				}
			}
			if (msg.type === 'user_message_during_override') {
				if (adminActiveConvId === msg.conversation_id) {
					selectAdminConv(adminActiveConvId);
				} else {
					const existing = adminConversations.find(c => c.id === msg.conversation_id);
					if (existing) {
						adminConversations = adminConversations.map(c =>
							c.id === msg.conversation_id
								? { ...c, has_new_messages: true, unread_count: (c.unread_count || 0) + 1 }
								: c
						);
					} else {
						loadAdminConversations();
					}
				}
			}
			if (msg.type === 'chat_updated') {
				if (adminActiveConvId && adminActiveConvId === msg.conversation_id) {
					selectAdminConv(adminActiveConvId);
				} else {
					if (msg.role === 'user') {
						const existing = adminConversations.find(c => c.id === msg.conversation_id);
						if (existing) {
							adminConversations = adminConversations.map(c =>
								c.id === msg.conversation_id
									? { ...c, has_new_messages: true, unread_count: (c.unread_count || 0) + 1 }
									: c
							);
						} else {
							loadAdminConversations();
						}
					}
				}
			}
		});
	});

	onDestroy(() => {
		if (wsUnsub) wsUnsub();
	});

	function handleAdminFileSelect(e) {
		const file = e.target.files?.[0];
		if (!file) return;
		if (file.size > 8 * 1024 * 1024) { toast('Image trop volumineuse (max 8 Mo)', 'error'); return; }
		adminPendingImage = file;
		const reader = new FileReader();
		reader.onload = (ev) => { adminImagePreview = ev.target.result; };
		reader.readAsDataURL(file);
		if (adminFileInput) adminFileInput.value = '';
	}

	function handleAdminPaste(e) {
		const items = e.clipboardData?.items;
		if (!items) return;
		for (const item of items) {
			if (item.type.startsWith('image/')) {
				e.preventDefault();
				const file = item.getAsFile();
				if (file.size > 8 * 1024 * 1024) { toast('Image trop volumineuse (max 8 Mo)', 'error'); return; }
				adminPendingImage = file;
				const reader = new FileReader();
				reader.onload = (ev) => { adminImagePreview = ev.target.result; };
				reader.readAsDataURL(file);
				break;
			}
		}
	}

	async function adminScrollToBottom() {
		await tick();
		if (adminChatContainer) adminChatContainer.scrollTop = adminChatContainer.scrollHeight;
	}

	function handleAdminChatScroll() {
		if (!adminChatContainer) return;
		adminShowScrollToBottom = adminChatContainer.scrollTop + adminChatContainer.clientHeight < adminChatContainer.scrollHeight - 300;
	}

	export async function loadAdminConversations() {
		try {
			const fresh = await api.get('/ia/admin/conversations');
			if (adminActiveConvId) {
				adminConversations = fresh.map(c =>
					c.id === adminActiveConvId ? { ...c, has_new_messages: false, unread_count: 0 } : c
				);
			} else {
				adminConversations = fresh;
			}
		} catch (e) { toast('Erreur chargement conversations', 'error'); }
	}

	export async function selectAdminConv(id) {
		const isNew = id !== adminActiveConvId;
		adminActiveConvId = id;
		adminConversations = adminConversations.map(c =>
			c.id === id ? { ...c, has_new_messages: false, unread_count: 0 } : c
		);
		try {
			const res = await api.get(`/ia/admin/conversations/${id}/messages`);
			adminLastReadMessageId = res.last_read_message_id || 0;
			adminConvMessages = res.messages;
			if (isNew) {
				adminFirstUnreadIdx = (adminLastReadMessageId && adminConvMessages.length) ? adminConvMessages.findIndex((m, i) => i > 0 && m.id > adminLastReadMessageId && m.role !== 'admin') : -1;
			}
			adminConvInfo = res.conversation;
			adminScrollToBottom();
			await loadAdminConversations();
		} catch (e) { toast(e.message, 'error'); }
	}

	async function adminSendIntervention() {
		if ((!adminInterveneText.trim() && !adminPendingImage) || !adminActiveConvId) return;
		try {
			let imagePath = null;
			if (adminPendingImage) {
				const fd = new FormData();
				fd.append('conversation_id', adminActiveConvId);
				fd.append('file', adminPendingImage);
				const uploadRes = await api.upload('/ia/upload-image', fd);
				imagePath = uploadRes.image_path;
				adminPendingImage = null;
				adminImagePreview = '';
			}
			await api.post(`/ia/admin/conversations/${adminActiveConvId}/intervene`, { content: adminInterveneText || '(image)', image_path: imagePath });
			adminInterveneText = '';
			toast('Message admin envoyé', 'success');
			await selectAdminConv(adminActiveConvId);
		} catch (e) { toast(e.message, 'error'); }
	}

	async function toggleAdminOverride(convId, value) {
		try {
			await api.put(`/ia/admin/conversations/${convId}/override`, { admin_override: value });
			toast(value ? 'Admin prend la main' : 'IA reprend la main', 'success');
			if (adminConvInfo) adminConvInfo.admin_override = value;
			await loadAdminConversations();
		} catch (e) { toast(e.message, 'error'); }
	}

	async function loadAdminCalls() {
		try { adminCalls = await api.get('/ia/admin-calls?status=pending'); } catch { adminCalls = []; }
	}

	async function resolveAdminCall(id, note = '') {
		try {
			await api.put(`/ia/admin-calls/${id}/resolve`, { note });
			await loadAdminCalls();
			toast('Demande marquée comme résolue', 'success');
		} catch(e) { toast(e.message || 'Erreur', 'error'); }
	}

	async function dismissAdminCall(id) {
		try {
			await api.put(`/ia/admin-calls/${id}/dismiss`, {});
			await loadAdminCalls();
			toast('Demande ignorée', 'success');
		} catch(e) { toast(e.message || 'Erreur', 'error'); }
	}

	async function loadRagSuggestions() {
		try { ragSuggestions = await api.get('/ia/rag-suggestions?status=pending'); } catch { ragSuggestions = []; }
	}

	async function approveRagSuggestion(id) {
		const answer = (ragAnswers[id] || '').trim();
		if (!answer) { toast('Saisissez une réponse avant d\'approuver', 'error'); return; }
		try {
			await api.put(`/ia/rag-suggestions/${id}/approve`, { answer });
			await loadRagSuggestions();
			delete ragAnswers[id];
			toast('Suggestion approuvée et injectée dans la base RAG', 'success');
		} catch(e) { toast(e.message || 'Erreur', 'error'); }
	}

	async function rejectRagSuggestion(id) {
		try {
			await api.put(`/ia/rag-suggestions/${id}/reject`, {});
			await loadRagSuggestions();
			toast('Suggestion rejetée', 'success');
		} catch(e) { toast(e.message || 'Erreur', 'error'); }
	}
</script>

<div class="admin-grid">
	<!-- Conversation list -->
	<section class="list glass" style="max-height:80vh;overflow-y:auto">
		<div class="list-header">
			<div class="flex-row items-center gap-3">
				<div class="list-icon">💬</div>
				<div>
					<h2 style="margin:0">{$t("admin_chats_title")}</h2>
					<span class="text-xs text-dim">{$t("admin_chats_subtitle")}</span>
				</div>
			</div>
			<span class="badge-count">{adminConversations.length}</span>
		</div>
		<div class="item-list" style="display:flex; flex-direction:column; gap:0.5rem;">
			{#each groupedConversations as group}
				<div class="user-group-header glass-hover" on:click={() => togglePlayerCollapse(group.username)} style="display:flex; justify-content:space-between; align-items:center; padding:0.6rem 0.8rem; border-radius:8px; cursor:pointer; background:rgba(255,255,255,0.02); border:1px solid rgba(255,255,255,0.05); user-select:none; margin-top:0.3rem;">
					<div class="flex-row items-center gap-2">
						<span class="user-group-icon">👤</span>
						<span class="user-group-title" style="font-weight:600; font-size:0.9rem; color:var(--text-main);">{group.username}</span>
						{#if group.is_online}
							<span style="color:#10b981; font-size:0.8rem; margin-left:0.2rem; text-shadow: 0 0 6px rgba(16,185,129,0.6);" title={$t('players_status_online')}>●</span>
						{/if}
						{#if group.has_unread}
							<span class="status-pill-sm open" style="background:rgba(34,197,94,0.15); color:#22c55e; border:1px solid rgba(34,197,94,0.3); padding:0.1rem 0.3rem; font-size:0.7rem; line-height:1;">{$t('dash_stat_new')}</span>
						{/if}
					</div>
					<div class="flex-row items-center gap-2">
						<span class="badge-count-inline" style="background:rgba(255,255,255,0.05); padding:0.15rem 0.4rem; border-radius:10px; font-size:0.75rem; color:var(--text-dim);">{group.conversations.length}</span>
						<span class="toggle-arrow" style="font-size:0.7rem; color:var(--text-dim); transition: transform 0.2s; transform: {collapsedPlayers[group.username] ? 'rotate(0deg)' : 'rotate(90deg)'}">▶</span>
					</div>
				</div>
				{#if !collapsedPlayers[group.username]}
					<div class="user-group-items" style="display:flex; flex-direction:column; gap:0.4rem; padding-left:0.5rem; border-left:1px dashed rgba(255,255,255,0.08); margin-left:0.5rem; margin-bottom:0.3rem;">
						{#each group.conversations as c}
							<div class="admin-item-card glass-hover {adminActiveConvId === c.id ? 'editing-expanded' : ''}" style="cursor:pointer;flex-direction:column;align-items:stretch;border-left: 4px solid {c.has_new_messages ? '#22c55e' : (c.admin_override ? '#a855f7' : 'rgba(255,255,255,0.05)')}; padding:0.5rem 0.7rem;" on:click={() => selectAdminConv(c.id)}>
								<div class="card-top-row" style="display:flex;justify-content:space-between;align-items:center">
									<div class="item-info" style="width:100%">
										<div class="flex-row items-center gap-2" style="flex-wrap:wrap">
											<span class="item-name" style="font-size:0.85rem; font-weight:550;">{c.title}</span>
											{#if c.has_new_messages}
												<span class="status-pill-sm open" style="background:rgba(34,197,94,0.15);color:#22c55e;border:1px solid rgba(34,197,94,0.3)">{c.unread_count > 1 ? $t('admin_chats_unread_plural', { count: c.unread_count }) : $t('admin_chats_unread_singular', { count: c.unread_count })}</span>
											{/if}
											{#if c.admin_override}
												<span class="status-pill-sm" style="background:rgba(168,85,247,0.2);color:#a855f7;border:1px solid #a855f7">🛡️ Admin</span>
											{/if}
										</div>
										<div class="item-meta" style="font-size:0.7rem;">{c.message_count} msg • {$t('dash_pill_active')} : {c.last_message_at ? new Date(c.last_message_at).toLocaleString('fr-FR', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' }) : ''}</div>
										{#if c.last_message_preview}
											<div class="last-msg-preview" style="font-size:0.72rem;color:var(--text-dim);margin-top:0.2rem;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;max-width:320px;opacity:0.8">
												<strong>{c.last_message_role === 'user' ? '👤' : c.last_message_role === 'admin' ? '🛡️' : '🤖'}:</strong> {c.last_message_preview}
											</div>
										{/if}
									</div>
								</div>
							</div>
						{/each}
					</div>
				{/if}
			{:else}
				<div class="empty-list">
					<span class="empty-icon">💬</span>
					<p>{$t('admin_chats_empty')}</p>
				</div>
			{/each}
		</div>
	</section>

	<!-- Conversation detail -->
	<section class="list glass" style="max-height:80vh;display:flex;flex-direction:column;position:relative">
		{#if adminActiveConvId && adminConvInfo}
			<div class="list-header">
				<div class="flex-row items-center gap-3">
					<div class="list-icon">🔍</div>
					<div>
						<h2 style="margin:0">{adminConvInfo.title}</h2>
						<span class="text-xs text-dim">{$t("admin_chats_player")} {adminConvInfo.username}</span>
					</div>
				</div>
				<div class="flex-row gap-2 items-center">
					{#if adminConvInfo.admin_override}
						<button class="btn-primary btn-xs" on:click={() => toggleAdminOverride(adminActiveConvId, false)}>🤖 {$t('admin_chats_takeover')}</button>
					{:else}
						<button class="btn-sentinel" on:click={() => toggleAdminOverride(adminActiveConvId, true)}>{$t('admin_chats_btn_takeover')}</button>
					{/if}
				</div>
			</div>
			<div bind:this={adminChatContainer} on:scroll={handleAdminChatScroll} style="flex:1;overflow-y:auto;padding:1rem;display:flex;flex-direction:column;gap:0.75rem;position:relative">
				{#each adminConvMessages as m, idx}
					{#if idx === adminFirstUnreadIdx}
						<div class="unread-separator">
							<span class="unread-separator-line"></span>
							<span class="unread-separator-text">{$t('chat_new_messages')}</span>
							<span class="unread-separator-line"></span>
						</div>
					{/if}
					<div style="display:flex;gap:0.5rem;{m.role === 'user' ? 'flex-direction:row-reverse' : ''}">
						<div style="font-size:1.1rem">{m.role === 'bot' ? '🤖' : m.role === 'admin' ? '🛡️' : '👤'}</div>
						<div style="display:flex;flex-direction:column;max-width:80%;align-items:{m.role === 'user' ? 'flex-end' : 'flex-start'}">
							{#if m.role === 'user'}
								<span style="font-size:0.7rem;color:var(--text-muted);margin-bottom:2px;font-weight:600;">{adminConvInfo.username}</span>
							{/if}
							<div style="padding:0.6rem 0.8rem;border-radius:12px;font-size:0.85rem;line-height:1.4;{m.role === 'user' ? 'background:rgba(59,130,246,0.15);border:1px solid rgba(59,130,246,0.3)' : m.role === 'admin' ? 'background:rgba(168,85,247,0.12);border:1px solid rgba(168,85,247,0.3)' : 'background:var(--hover-tint);border:1px solid var(--glass-border)'}">
								{#if m.role === 'admin'}<span style="font-size:0.65rem;font-weight:700;color:#a855f7;text-transform:uppercase;margin-bottom:0.2rem;display:block">Admin</span>{/if}
								<div class="admin-conv-md">{@html parseMd(m.content)}</div>
								{#if m.image_path}
									<div style="margin-top:0.4rem">
										<img src="{API_URL}/data/{m.image_path}" alt="" style="max-width:250px;max-height:180px;border-radius:8px;border:1px solid var(--glass-border);cursor:pointer;object-fit:cover" on:click={() => window.open(API_URL + '/data/' + m.image_path, '_blank')} />
									</div>
								{/if}
							</div>
							
							{#if m.role === 'bot' && m.meta}
								<div class="msg-meta-row" style="display:flex;flex-wrap:wrap;gap:0.4rem;font-size:0.65rem;color:var(--text-dim);margin-top:0.2rem;padding:0 0.2rem;opacity:0.8">
									{#if m.meta.model_info}
										<span title="Modèle / Instance" style="background:rgba(255,255,255,0.05);padding:1px 4px;border-radius:4px;border:1px solid var(--glass-border)">🤖 {m.meta.model_info.model || 'Modèle'} ({m.meta.model_info.instance || 'Default'})</span>
									{/if}
									{#if m.meta.duration}
										<span title="Temps de réponse" style="background:rgba(255,255,255,0.05);padding:1px 4px;border-radius:4px;border:1px solid var(--glass-border)">⏱️ {m.meta.duration.toFixed(1)}s</span>
									{/if}
									{#if m.meta.used_tools && m.meta.used_tools.length > 0}
										<span title="Outils utilisés: {m.meta.used_tools.join(', ')}" style="background:rgba(59,130,246,0.1);color:var(--accent);padding:1px 4px;border-radius:4px;border:1px solid rgba(59,130,246,0.2)">🛠️ {m.meta.used_tools.join(', ')}</span>
									{/if}
								</div>
							{/if}
							
							<span style="font-size:0.62rem;color:var(--text-muted);margin-top:0.15rem;align-self:{m.role === 'user' ? 'flex-end' : 'flex-start'};padding:0 0.25rem">
								{m.timestamp ? new Date(m.timestamp).toLocaleString('fr-FR', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit', second: '2-digit' }) : ''}
							</span>
						</div>
					</div>
				{/each}
			</div>
			{#if adminShowScrollToBottom}
				<button class="scroll-to-bottom-btn glass" type="button" on:click={adminScrollToBottom}>
					👇 {$t('chat_scroll_to_bottom')}
				</button>
			{/if}
			{#if adminConvInfo.admin_override}
				<div style="padding:0.75rem 1rem;border-top:1px solid var(--glass-border);display:flex;flex-direction:column;gap:0.5rem">
					{#if adminImagePreview}
						<div style="position:relative;display:inline-block">
							<img src={adminImagePreview} alt="Preview" style="max-width:150px;max-height:80px;border-radius:6px;border:2px solid #a855f7;object-fit:cover" />
							<button style="position:absolute;top:-6px;right:-6px;width:20px;height:20px;border-radius:50%;background:rgba(239,68,68,0.9);color:white;border:none;cursor:pointer;font-size:0.65rem;display:flex;align-items:center;justify-content:center" on:click={() => { adminPendingImage = null; adminImagePreview = ''; }}>✕</button>
						</div>
					{/if}
					<div style="display:flex;gap:0.5rem;align-items:center">
						<input type="file" accept="image/*" bind:this={adminFileInput} on:change={handleAdminFileSelect} style="display:none" />
						<button class="btn-attach" style="width:36px;height:36px;font-size:1rem;border-radius:6px" on:click={() => adminFileInput?.click()} title="Joindre une image">📎</button>
						<input type="text" bind:value={adminInterveneText} placeholder="{$t('admin_chats_placeholder')}" style="flex:1" on:keydown={(e) => { if (e.key === 'Enter') adminSendIntervention(); }} on:paste={handleAdminPaste} />
						<button class="btn-primary" on:click={adminSendIntervention}>{$t('ai_btn_send')}</button>
					</div>
				</div>
			{:else}
				<div style="padding:0.75rem 1rem;border-top:1px solid var(--glass-border);text-align:center;font-size:0.8rem;color:var(--text-dim)">
					{$t('admin_chats_system_control')}
				</div>
			{/if}
		{:else}
			<div class="empty-list" style="flex:1;display:flex;flex-direction:column;align-items:center;justify-content:center">
				<span class="empty-icon">🔍</span>
				<p>{$t('admin_chats_no_conv_selected')}</p>
			</div>
		{/if}
	</section>
</div>

<!-- Appels Admin & Suggestions RAG -->
<div style="display:flex;gap:1.5rem;flex-wrap:wrap;padding:1rem 0">
	<!-- Appels Admin IA -->
	<section class="list glass" style="flex:1;min-width:300px">
		<div class="list-header">
			<div class="flex-row items-center gap-3">
				<div class="list-icon">📣</div>
				<div>
					<h2 style="margin:0">{$t('ai_admin_calls_title')}</h2>
					<span class="text-xs text-dim">{$t('ia_queue_admin_badge', { waiting: adminCalls.length })}</span>
				</div>
			</div>
			<div style="display:flex;gap:0.5rem;align-items:center">
				{#if adminCalls.length > 0}<span class="badge-count" style="background:#f97316">{adminCalls.length}</span>{/if}
				<button class="btn-icon-sm" on:click={loadAdminCalls} title="Rafraîchir">🔄</button>
			</div>
		</div>
		<div class="item-list" style="display:flex;flex-direction:column;gap:0.75rem;padding:0.75rem">
			{#if adminCalls.length === 0}
				<p class="text-dim" style="text-align:center;padding:1rem 0">{$t('ai_admin_calls_empty')}</p>
			{:else}
				{#each adminCalls as call}
					<div class="admin-item-card" style="flex-direction:column;align-items:flex-start;gap:0.5rem;border-left:3px solid #f97316">
						<div style="display:flex;justify-content:space-between;width:100%;align-items:center">
							<span style="font-weight:600;color:#f97316">📣 {call.username}</span>
							<span class="text-dim" style="font-size:0.75rem">{new Date(call.created_at).toLocaleString('fr-FR',{hour:'2-digit',minute:'2-digit',day:'2-digit',month:'2-digit'})}</span>
						</div>
						<p style="margin:0;font-size:0.9rem;line-height:1.4">{call.question}</p>
						{#if call.conversation_id}
							<button class="btn-secondary" style="font-size:0.8rem;padding:0.2rem 0.6rem" on:click={() => selectAdminConv(call.conversation_id)}>💬 Voir la conversation</button>
						{/if}
						<div style="display:flex;gap:0.4rem">
							<button class="btn-primary" style="font-size:0.8rem;padding:0.25rem 0.75rem" on:click={() => resolveAdminCall(call.id)}>{$t('ai_call_admin_resolve_btn')}</button>
							<button class="btn-secondary" style="font-size:0.8rem;padding:0.25rem 0.75rem" on:click={() => dismissAdminCall(call.id)}>{$t('ai_call_admin_dismiss_btn')}</button>
						</div>
					</div>
				{/each}
			{/if}
		</div>
	</section>
	<!-- Suggestions RAG -->
	<section id="rag-suggestions-section" class="list glass" style="flex:1;min-width:300px">
		<div class="list-header">
			<div class="flex-row items-center gap-3">
				<div class="list-icon">💡</div>
				<div>
					<h2 style="margin:0">{$t('ai_rag_suggestions_title')}</h2>
					<span class="text-xs text-dim">{$t('ia_queue_admin_badge', { waiting: ragSuggestions.length })}</span>
				</div>
			</div>
			<div style="display:flex;gap:0.5rem;align-items:center">
				{#if ragSuggestions.length > 0}<span class="badge-count">{ragSuggestions.length}</span>{/if}
				<button class="btn-icon-sm" on:click={loadRagSuggestions} title="Rafraîchir">🔄</button>
			</div>
		</div>
		<div class="item-list" style="display:flex;flex-direction:column;gap:0.75rem;padding:0.75rem">
			{#if ragSuggestions.length === 0}
				<p class="text-dim" style="text-align:center;padding:1rem 0">{$t('ai_rag_suggestions_empty')}</p>
			{:else}
				{#each ragSuggestions as s}
					<div class="admin-item-card" style="flex-direction:column;align-items:flex-start;gap:0.5rem;border-left:3px solid var(--accent)">
						<div style="display:flex;justify-content:space-between;width:100%;align-items:center">
							<span style="font-weight:600">{s.username} — <em style="color:var(--accent)">{s.category}</em></span>
							<span class="text-dim" style="font-size:0.75rem">{new Date(s.created_at).toLocaleString('fr-FR',{hour:'2-digit',minute:'2-digit',day:'2-digit',month:'2-digit'})}</span>
						</div>
						<p style="margin:0;font-size:0.9rem;font-weight:500;line-height:1.4">{s.question}</p>
						<p style="margin:0;font-size:0.8rem;color:var(--text-dim);line-height:1.3">{s.context}</p>
						<textarea bind:value={ragAnswers[s.id]} placeholder={$t('ai_rag_answer_placeholder')} rows="3" style="width:100%;box-sizing:border-box;font-size:0.85rem;resize:vertical;" class="edit-textarea"></textarea>
						<div style="display:flex;gap:0.4rem">
							<button class="btn-primary" style="font-size:0.8rem;padding:0.25rem 0.75rem" on:click={() => approveRagSuggestion(s.id)}>{$t('ai_rag_approve_btn')}</button>
							<button class="btn-secondary" style="font-size:0.8rem;padding:0.25rem 0.75rem" on:click={() => rejectRagSuggestion(s.id)}>{$t('ai_rag_reject_btn')}</button>
						</div>
					</div>
				{/each}
			{/if}
		</div>
	</section>
</div>

<style>
	.admin-grid { display: grid; grid-template-columns: minmax(380px, 1fr) 2fr; gap: 2rem; }
	.list { padding: 2rem; display: flex; flex-direction: column; }
	.list-header { display: flex; justify-content: space-between; align-items: center; padding-bottom: 1rem; margin-bottom: 1rem; border-bottom: 1px solid var(--glass-border); }
	.list-icon { width: 40px; height: 40px; display: flex; align-items: center; justify-content: center; font-size: 1.4rem; background: var(--accent-soft); border-radius: 10px; border: 1px solid rgba(59,130,246,0.15); }
	.badge-count { font-size: 0.7rem; background: var(--accent-soft); color: var(--accent); padding: 0.2rem 0.6rem; border-radius: 4px; font-weight: 800; border: 1px solid var(--accent); }
	.admin-item-card { display: flex; align-items: center; gap: 1rem; padding: 1rem; border-radius: 12px; margin-bottom: 0.75rem; border: 1px solid var(--glass-border); transition: all 0.2s; }
	.admin-item-card:hover { border-color: var(--accent); background: rgba(59, 130, 246, 0.05); }
	.card-top-row { display: flex; align-items: center; gap: 1rem; }
	.editing-expanded { border-color: var(--accent) !important; background: rgba(59,130,246,0.03) !important; }
	.item-info { flex-grow: 1; }
	.item-name { font-weight: 700; font-size: 1rem; }
	.item-meta { font-size: 0.75rem; color: var(--text-dim); margin-top: 0.2rem; }
	.status-pill-sm { font-size: 0.6rem; font-weight: 700; text-transform: uppercase; letter-spacing: 0.05em; padding: 0.15rem 0.5rem; border-radius: 20px; }
	.status-pill-sm.open { background: rgba(34,197,94,0.1); color: var(--success); border: 1px solid rgba(34,197,94,0.2); }
	.status-pill-sm.running { background: var(--accent-soft); color: var(--accent); border: 1px solid rgba(59,130,246,0.2); }
	.empty-list { display: flex; flex-direction: column; align-items: center; justify-content: center; padding: 3rem 1rem; gap: 0.5rem; }
	.empty-icon { font-size: 2.5rem; opacity: 0.5; }
	.empty-list p { color: var(--text-dim); font-weight: 600; margin: 0; }
	.glass-hover { transition: all 0.2s; }
	.glass-hover:hover { background: var(--hover-tint); border-color: var(--glass-border); }
	.btn-sentinel { padding: 0.4rem 0.9rem; font-size: 0.7rem; font-weight: 700; color: #a855f7; background: rgba(168,85,247,0.1); border: 1px solid rgba(168,85,247,0.3); border-radius: 8px; cursor: pointer; transition: all 0.2s; white-space: nowrap; }
	.btn-sentinel:hover { background: rgba(168,85,247,0.25); border-color: #a855f7; box-shadow: 0 0 12px rgba(168,85,247,0.2); }
	.btn-attach { background: var(--hover-tint); border: 1px solid var(--glass-border); color: var(--text-dim); width: 36px; height: 36px; border-radius: 6px; cursor: pointer; font-size: 1rem; display: flex; align-items: center; justify-content: center; transition: all 0.2s; flex-shrink: 0; }
	.btn-attach:hover { background: var(--accent-soft); border-color: var(--accent); color: var(--accent); }
	.btn-icon-sm { background: var(--hover-tint); border: 1px solid var(--glass-border); border-radius: 6px; padding: 0.2rem 0.4rem; cursor: pointer; font-size: 0.8rem; }
	.btn-icon-sm:hover { background: var(--accent-soft); border-color: var(--accent); }
	.edit-textarea { background: var(--input-bg); border: 1px solid var(--glass-border); border-radius: 8px; padding: 0.6rem 0.8rem; color: var(--input-color); font-family: var(--font-main); font-size: 0.85rem; transition: all 0.2s; }
	.edit-textarea:focus { border-color: var(--accent); outline: none; box-shadow: 0 0 0 3px var(--accent-soft); }
	.admin-conv-md :global(p) { margin: 0.3em 0; }
	.admin-conv-md :global(p:first-child) { margin-top: 0; }
	.admin-conv-md :global(p:last-child) { margin-bottom: 0; }
	.admin-conv-md :global(code) { background: rgba(0,0,0,0.3); padding: 0.1em 0.3em; border-radius: 4px; font-size: 0.85em; }
	.admin-conv-md :global(pre) { background: rgba(0,0,0,0.35); border: 1px solid rgba(255,255,255,0.08); border-radius: 8px; padding: 0.6em; overflow-x: auto; margin: 0.4em 0; }
	.admin-conv-md :global(pre code) { background: none; padding: 0; }
	.admin-conv-md :global(strong) { font-weight: 600; }
	.admin-conv-md :global(ul), .admin-conv-md :global(ol) { margin: 0.3em 0; padding-left: 1.3em; }
	.admin-conv-md :global(blockquote) { border-left: 3px solid var(--accent); padding: 0.2em 0.6em; margin: 0.3em 0; opacity: 0.85; }
	.unread-separator { display: flex; align-items: center; margin: 1.5rem 0; color: var(--text-muted, #94a3b8); font-size: 0.8rem; font-weight: 600; text-transform: uppercase; letter-spacing: 0.05em; width: 100%; }
	.unread-separator-line { flex: 1; height: 1px; background: linear-gradient(90deg, transparent, rgba(239, 68, 68, 0.4), transparent); }
	.unread-separator-text { padding: 0 0.8rem; color: #f87171; }
	.scroll-to-bottom-btn { position: absolute; bottom: 90px; right: 20px; background: var(--glass-bg); border: 1px solid var(--glass-border); color: var(--text-main); padding: 0.5rem 1rem; border-radius: 9999px; font-size: 0.85rem; cursor: pointer; display: flex; align-items: center; gap: 0.4rem; z-index: 10; box-shadow: var(--glass-shadow); backdrop-filter: blur(10px); -webkit-backdrop-filter: blur(10px); transition: all 0.2s ease; }
	.scroll-to-bottom-btn:hover { background: var(--hover-tint); transform: translateY(-2px); }
</style>
