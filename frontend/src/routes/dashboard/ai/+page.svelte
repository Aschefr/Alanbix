<script>
	import { api } from '$lib/api';
	import { onMount, onDestroy } from 'svelte';
	import Modal from '$lib/components/Modal.svelte';
	import { marked } from 'marked';
	import { wsMessageStore } from '$lib/ws';

	// Configure marked for safe rendering
	marked.setOptions({ breaks: true, gfm: true });

	function parseMd(text) {
		if (!text) return '';
		return marked.parse(text);
	}
	function escapeHtml(text) {
		if (!text) return '';
		return text.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
	}
	function estimateTokens(text) {
		if (!text) return 0;
		return Math.ceil(text.length / 3.5);
	}

	let conversations = [];
	let activeId = null;
	let messages = [];
	let usage = { estimated_tokens: 0 };
	let compression = { mode: null, auto_mode: null, compressed_at: null, context: null };
	let iaConfig = { context_window: 4096 };
	let query = '';
	let loading = false;

	// Live token counting
	$: liveTokens = (() => {
		let total = messages.reduce((sum, m) => sum + (m.content ? m.content.length : 0), 0);
		total += query.length;
		return Math.ceil(total / 3.5);
	})();
	$: contextWindow = iaConfig.context_window || 4096;
	$: tokenPct = Math.min(100, (liveTokens / contextWindow) * 100);

	// Admin notification
	let adminNotification = null;
	let unsub = null;

	function dismissNotification() { adminNotification = null; }
	function goToNotifiedConv() {
		if (adminNotification) {
			selectConversation(adminNotification.conversation_id);
			adminNotification = null;
		}
	}
	let showCompressionModal = false;
	let editingMsgId = null;
	let editingMsgContent = '';
	let editingContext = false;
	let editContextText = '';
	let chatContainer = null;
	let adminOverride = false;
	let iaBlocked = false;

	// Image attachment
	let pendingImage = null;      // File object
	let pendingImagePreview = ''; // data URL for preview
	let fileInput = null;         // hidden file input ref

	function handlePaste(e) {
		const items = e.clipboardData?.items;
		if (!items) return;
		for (const item of items) {
			if (item.type.startsWith('image/')) {
				e.preventDefault();
				const file = item.getAsFile();
				attachImage(file);
				break;
			}
		}
	}

	function handleFileSelect(e) {
		const file = e.target.files?.[0];
		if (file) attachImage(file);
		if (fileInput) fileInput.value = '';
	}

	function attachImage(file) {
		if (file.size > 8 * 1024 * 1024) { alert('Image trop volumineuse (max 8 Mo)'); return; }
		pendingImage = file;
		const reader = new FileReader();
		reader.onload = (e) => { pendingImagePreview = e.target.result; };
		reader.readAsDataURL(file);
	}

	function clearPendingImage() { pendingImage = null; pendingImagePreview = ''; }

	import { tick } from 'svelte';
	async function scrollToBottom() {
		await tick();
		if (chatContainer) chatContainer.scrollTop = chatContainer.scrollHeight;
	}

	let showModal = false;
	let modalTitle = '';
	let modalMessage = '';
	let modalType = 'info';
	let modalConfirmCallback = null;

	function askConfirm(title, message, type, callback) {
		modalTitle = title;
		modalMessage = message;
		modalType = type;
		modalConfirmCallback = callback;
		showModal = true;
	}

	onMount(async () => {
		await loadConversations();
		iaConfig = await api.get('/ia/config');
		try { const me = await api.get('/me'); iaBlocked = !!me.ia_blocked; } catch(e) {}

		// Listen for admin intervention via WebSocket
		unsub = wsMessageStore.subscribe(msg => {
			if (msg && msg.type === 'admin_message') {
				// If the user is viewing this conversation, refresh messages live
				if (activeId === msg.conversation_id) {
					selectConversation(activeId);
				}
				// Show notification
				adminNotification = msg;
				// Auto-dismiss after 10s
				setTimeout(() => { if (adminNotification && adminNotification.message_id === msg.message_id) adminNotification = null; }, 10000);
			}
		});
	});

	onDestroy(() => { if (unsub) unsub(); });

	async function loadConversations() {
		conversations = await api.get('/ia/conversations');
		if (conversations.length > 0 && !activeId) {
			selectConversation(conversations[0].id);
		}
	}

	async function selectConversation(id) {
		activeId = id;
		const res = await api.get(`/ia/conversations/${id}/messages`);
		messages = res.messages;
		usage = res.usage || { estimated_tokens: 0 };
		compression = res.compression || { mode: null };
		adminOverride = res.admin_override || false;
		scrollToBottom();
	}

	async function newConversation() {
		const res = await api.post('/ia/conversations', { 
			title: 'Nouvelle discussion',
			model: iaConfig.model
		});
		await loadConversations();
		selectConversation(res.id);
	}

	async function deleteConversation(id) {
		askConfirm('Supprimer', 'Voulez-vous vraiment supprimer cette conversation ?', 'error', async () => {
			await api.delete(`/ia/conversations/${id}`);
			if (activeId === id) activeId = null;
			await loadConversations();
		});
	}

	async function applyCompression(mode) {
		showCompressionModal = false;
		loading = true;
		try {
			await api.post(`/ia/compress/${activeId}`, { mode });
			await selectConversation(activeId);
		} catch (e) {
			alert(e.message);
		}
		loading = false;
	}

	async function revertCompression() {
		askConfirm('Annuler la compression', 'Voulez-vous restaurer le contexte original ?', 'warning', async () => {
			await api.delete(`/ia/compress/${activeId}`);
			await selectConversation(activeId);
		});
	}

	async function deleteMsg(id) {
		askConfirm('Supprimer le message', 'Voulez-vous supprimer ce message ?', 'error', async () => {
			await api.delete(`/ia/message/${id}`);
			messages = messages.filter(m => m.id !== id);
		});
	}

	async function regenerate() {
		askConfirm('Régénérer', 'Voulez-vous régénérer la dernière réponse ? L\'ancienne sera écrasée.', 'warning', async () => {
			loading = true;
			try {
				const res = await api.post(`/ia/regenerate/${activeId}`, {});
				query = res.last_user_content;
				await selectConversation(activeId);
				await send();
			} catch (e) {
				alert(e.message);
				loading = false;
			}
		});
	}

	async function editMsg(msg) {
		editingMsgId = msg.id;
		editingMsgContent = msg.content;
	}

	async function saveEdit() {
		if (!editingMsgId) return;
		await api.put(`/ia/message/${editingMsgId}`, { content: editingMsgContent });
		editingMsgId = null;
		await selectConversation(activeId);
	}

	async function cancelEdit() {
		editingMsgId = null;
		editingMsgContent = '';
	}

	async function retryFromMsg(msg) {
		// Delete all messages after this user message, then re-send
		const idx = messages.findIndex(m => m.id === msg.id);
		const toDelete = messages.slice(idx + 1);
		for (const m of toDelete) {
			await api.delete(`/ia/message/${m.id}`);
		}
		query = msg.content;
		// Delete the original user message too (send() will re-create it)
		await api.delete(`/ia/message/${msg.id}`);
		await selectConversation(activeId);
		await send();
	}

	async function editAndResend(msg) {
		// Save the edit, then retry from this message
		await api.put(`/ia/message/${editingMsgId}`, { content: editingMsgContent });
		const idx = messages.findIndex(m => m.id === editingMsgId);
		const toDelete = messages.slice(idx + 1);
		for (const m of toDelete) {
			await api.delete(`/ia/message/${m.id}`);
		}
		query = editingMsgContent;
		await api.delete(`/ia/message/${editingMsgId}`);
		editingMsgId = null;
		await selectConversation(activeId);
		await send();
	}

	function startEditContext() {
		editContextText = compression.context || '';
		editingContext = true;
	}

	async function saveContextEdit() {
		await api.put(`/ia/compress/${activeId}/edit`, { context: editContextText });
		editingContext = false;
		await selectConversation(activeId);
	}

	async function send() {
		if ((!query && !pendingImage) || loading || !activeId) return;
		const userMsg = query || '(image)';
		const attachedPreview = pendingImagePreview;
		query = '';
		
		// Upload image if present
		let imagePath = null;
		if (pendingImage) {
			try {
				const fd = new FormData();
				fd.append('conversation_id', activeId);
				fd.append('file', pendingImage);
				const uploadRes = await api.upload('/ia/upload-image', fd);
				imagePath = uploadRes.image_path;
			} catch (e) { alert('Erreur upload image: ' + e.message); loading = false; return; }
			clearPendingImage();
		}

		messages = [...messages, { id: Date.now(), role: 'user', content: userMsg, image_path: imagePath }];
		loading = true;

		let botMsgIdx = messages.length;
		messages = [...messages, { id: Date.now()+1, role: 'bot', content: '' }];
		scrollToBottom();

		try {
			const token = localStorage.getItem('alanbix_token');
			const response = await fetch('http://localhost:8000/ia/stream', {
				method: 'POST',
				headers: {
					'Content-Type': 'application/json',
					'Authorization': `Bearer ${token}`
				},
				body: JSON.stringify({
					prompt: userMsg,
					conversation_id: activeId,
					image_path: imagePath
				})
			});

			const reader = response.body.getReader();
			const decoder = new TextDecoder("utf-8");

			while (true) {
				const { value, done } = await reader.read();
				if (done) break;
				
				const chunk = decoder.decode(value, { stream: true });
				const lines = chunk.split('\n');
				for (let line of lines) {
					if (line.startsWith('data: ')) {
						const dataStr = line.replace('data: ', '');
						try {
							const data = JSON.parse(dataStr);
							if (data.text) {
								messages[botMsgIdx].content += data.text;
								messages = messages; // trigger Svelte reactivity for markdown re-render
								scrollToBottom();
							}
							if (data.done) {
								// Update token estimate from server
								if (data.estimated_tokens) {
									usage = { estimated_tokens: data.estimated_tokens };
								}
								// Auto-title: if this was the first exchange
								if (messages.length <= 2) {
									try {
										const titleRes = await api.post(`/ia/auto-title/${activeId}`, {});
										if (titleRes.title) {
											const conv = conversations.find(c => c.id === activeId);
											if (conv) conv.title = titleRes.title;
											conversations = conversations;
										}
									} catch {}
								}
							}
						} catch (e) {}
					}
				}
			}
		} catch (e) {
			alert(e.message);
		} finally {
			loading = false;
			await selectConversation(activeId);
		}
	}
</script>

<div class="ai-page flex-row">
	<!-- Admin Notification Banner -->
	{#if adminNotification}
		<div class="admin-notif" on:click={goToNotifiedConv}>
			<span class="admin-notif-icon">🛡️</span>
			<span class="admin-notif-text">
				<strong>{adminNotification.admin_name}</strong> a envoyé un message dans votre conversation
			</span>
			<button class="admin-notif-btn">Voir →</button>
			<button class="admin-notif-close" on:click|stopPropagation={dismissNotification}>✕</button>
		</div>
	{/if}
	<!-- Sidebar: Conversation History -->
	<aside class="chat-sidebar glass">
		<button class="btn-primary w-full" on:click={newConversation} disabled={iaBlocked}>+ Nouvelle Discussion</button>
		<div class="conv-list">
			{#each conversations as conv}
				<div class="conv-item {activeId === conv.id ? 'active' : ''}">
					<button class="conv-btn" on:click={() => selectConversation(conv.id)}>
						<span class="icon">💬</span>
						<span class="title">{conv.title}</span>
					</button>
					<button class="btn-icon delete-btn" on:click={() => deleteConversation(conv.id)}>❌</button>
				</div>
			{/each}
		</div>
	</aside>

	<!-- Main: Chat Window -->
	<main class="chat-main glass">
		{#if activeId}
			<header class="flex-row justify-between items-center">
				<div class="flex-col">
					<div class="flex-row items-center gap-4">
						<h2>{conversations.find(c => c.id === activeId)?.title}</h2>
						{#if compression.mode}
							<div class="compression-badge" title="Mode de compression actif">
								🗜️ {compression.mode}
								<button on:click={revertCompression} class="revert-btn">×</button>
							</div>
						{/if}
						<div class="rag-status">
							<span class="pulse"></span> IA Active
						</div>
					</div>
					<div class="usage-bar mt-1">
						<div class="flex-row justify-between">
							<span class="text-xs text-dim">Contexte: {liveTokens} / {contextWindow} tokens</span>
							{#if tokenPct > 80}
								<span class="text-xs text-danger warning-text">⚠️ Proche de la limite</span>
							{/if}
						</div>
						<div class="progress-bg">
							<div class="progress-fill {tokenPct > 90 ? 'danger-fill' : tokenPct > 75 ? 'warning-fill' : ''}" style="width: {tokenPct}%"></div>
						</div>
					</div>
				</div>
				<div class="flex-row gap-2">
					<button class="btn-sentinel" on:click={() => showCompressionModal = true} title="Gérer l'espace du contexte">
						⚙️ Espace Contexte
					</button>
					<button class="btn-sentinel danger" on:click={regenerate} title="Régénérer la dernière réponse">
						🔄 Régénérer
					</button>
				</div>
			</header>

			{#if showCompressionModal}
				<div class="modal-overlay">
					<div class="modal-content glass">
						<h3>Gérer l'espace du contexte</h3>
						<p class="text-dim text-sm mb-4">Le contexte approche de sa limite maximale. Choisissez comment libérer de l'espace :</p>
						
						<div class="flex-col gap-2">
							<button class="comp-btn" on:click={() => applyCompression('truncate')}>
								<strong>1. Tronquer (Automatique)</strong>
								<span class="text-xs text-dim">Le système oubliera les plus anciens messages (0 délai).</span>
							</button>
							<button class="comp-btn" on:click={() => applyCompression('compact')}>
								<strong>2. Compacter l'historique</strong>
								<span class="text-xs text-dim">Supprime les doublons inutiles sans altérer le sens (~50% gain).</span>
							</button>
							<button class="comp-btn primary-outline" on:click={() => applyCompression('summary')}>
								<strong>3. Résumer par l'IA (Recommandé)</strong>
								<span class="text-xs text-dim">Résumé ultra-concis de tout l'historique (~70% gain).</span>
							</button>
						</div>
						
						<div class="flex-row justify-end mt-4">
							<button class="btn-secondary" on:click={() => showCompressionModal = false}>Annuler</button>
						</div>
					</div>
				</div>
			{/if}

			<div class="messages-container" bind:this={chatContainer}>
				{#if compression.context}
					<div class="msg-wrapper system">
						<div class="msg-row system">
							<div class="avatar">🗜️</div>
							<div class="msg-content glass context-block">
								<div class="context-header">
									<span class="context-label">Contexte Compressé ({compression.mode})</span>
									<button class="action-btn" on:click={startEditContext} title="Éditer">✏️</button>
								</div>
								{#if editingContext}
									<textarea class="edit-textarea" bind:value={editContextText} rows="4"></textarea>
									<div class="edit-actions">
										<button class="btn-xs-save" on:click={saveContextEdit}>✓ Sauvegarder</button>
										<button class="btn-xs-cancel" on:click={() => editingContext = false}>✕ Annuler</button>
									</div>
								{:else}
									<div class="context-text">{compression.context}</div>
								{/if}
							</div>
						</div>
					</div>
				{/if}

				{#each messages as msg, idx}
					<div class="msg-wrapper {msg.role}">
						<div class="msg-row {msg.role}">
							<div class="avatar">{msg.role === 'bot' ? '🤖' : msg.role === 'admin' ? '🛡️' : '👤'}</div>
							<div class="msg-content glass {msg.role === 'admin' ? 'admin-msg' : ''}">
								{#if msg.role === 'admin'}
									<div class="admin-badge">Admin</div>
								{/if}
								{#if editingMsgId === msg.id}
									<textarea class="edit-textarea" bind:value={editingMsgContent} rows="3"></textarea>
									<div class="edit-actions">
										<button class="btn-xs-save" on:click={saveEdit}>✓ Sauvegarder</button>
										<button class="btn-xs-save accent" on:click={editAndResend}>↻ Réenvoyer</button>
										<button class="btn-xs-cancel" on:click={cancelEdit}>✕</button>
									</div>
								{:else}
									{#if msg.role === 'bot' || msg.role === 'admin'}
										<div class="markdown-body">{@html parseMd(msg.content)}</div>
									{:else}
										<div class="markdown-body user-text">{@html escapeHtml(msg.content).replace(/\n/g, '<br>')}</div>
									{/if}
									{#if msg.image_path}
										<div class="msg-image">
											<img src="http://localhost:8000/data/{msg.image_path}" alt="Image jointe" on:click={() => window.open('http://localhost:8000/data/' + msg.image_path, '_blank')} />
										</div>
									{/if}
									{#if msg.content === '' && loading && msg.role === 'bot' && msg.id === messages[messages.length-1].id}
										<span class="typing-indicator">Alanbix rédige...</span>
									{/if}
								{/if}
							</div>
						</div>
						<div class="msg-actions">
							{#if msg.role === 'user'}
								<button class="action-btn" on:click={() => editMsg(msg)} title="Éditer">✏️</button>
								<button class="action-btn" on:click={() => retryFromMsg(msg)} title="Réessayer">🔄</button>
							{/if}
							{#if msg.role === 'bot' && idx === messages.length - 1}
								<button class="action-btn" on:click={regenerate} title="Régénérer">🔄</button>
							{/if}
							<button class="action-btn" on:click={() => deleteMsg(msg.id)} title="Supprimer">🗑️</button>
						</div>
					</div>
				{/each}
			</div>

			{#if adminOverride}
				<div class="admin-takeover-banner">
					<span class="takeover-icon">🛡️</span>
					<span class="takeover-text">Un administrateur gère cette conversation — l'IA est temporairement en pause</span>
				</div>
			{/if}

			{#if iaBlocked}
				<div class="ia-blocked-banner">
					<span class="takeover-icon">🚫</span>
					<span class="blocked-text">Votre accès à l'IA a été suspendu par un administrateur</span>
				</div>
			{/if}

			<form class="input-area" on:submit|preventDefault={send}>
				{#if pendingImagePreview}
					<div class="pending-image-preview">
						<img src={pendingImagePreview} alt="Preview" />
						<button type="button" class="preview-clear" on:click={clearPendingImage}>✕</button>
					</div>
				{/if}
				<div class="input-row">
					<input type="file" accept="image/*" bind:this={fileInput} on:change={handleFileSelect} style="display:none" />
					<button type="button" class="btn-attach" on:click={() => fileInput?.click()} title="Joindre une image" disabled={iaBlocked}>📎</button>
					<input type="text" bind:value={query} placeholder="{iaBlocked ? 'Accès IA suspendu...' : 'Posez une question sur la LAN, les règles, le planning...'}" disabled={loading || iaBlocked} on:paste={handlePaste} />
					<button class="btn-primary" type="submit" disabled={loading || iaBlocked}>Envoyer</button>
				</div>
			</form>
		{:else}
			<div class="empty-chat flex-col center">
				<div class="large-icon">🤖</div>
				<h2>Bienvenue dans l'IA Alanbix</h2>
				<p class="text-dim">Sélectionnez une conversation ou commencez-en une nouvelle pour poser vos questions.</p>
				<button class="btn-primary" on:click={newConversation}>Démarrer</button>
			</div>
		{/if}
	</main>
</div>

<Modal 
	bind:show={showModal} 
	title={modalTitle} 
	message={modalMessage} 
	type={modalType} 
	onConfirm={modalConfirmCallback} 
/>

<style>
	.ai-page { height: calc(100vh - 4rem); gap: 2rem; align-items: stretch; }
	.chat-sidebar { width: 300px; padding: 1.5rem; display: flex; flex-direction: column; gap: 1.5rem; }
	.conv-list { display: flex; flex-direction: column; gap: 0.5rem; overflow-y: auto; }
	
	.conv-item { 
		display: flex; align-items: center; justify-content: space-between;
		background: transparent; border: 1px solid transparent; color: var(--text-dim);
		border-radius: var(--radius-md); transition: all 0.2s;
	}
	.conv-item:hover { background: var(--accent-soft); }
	.conv-item.active { background: var(--accent-soft); border-color: var(--accent); color: var(--text-main); }
	
	.conv-btn { 
		display: flex; align-items: center; gap: 0.75rem; padding: 0.75rem; 
		background: none; border: none; color: inherit; cursor: pointer; flex: 1; min-width: 0; text-align: left; overflow: hidden;
	}
	.conv-btn .title { font-size: 0.9rem; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
	
	.delete-btn { opacity: 0; padding: 0.5rem; font-size: 0.8rem; flex-shrink: 0; }
	.conv-item:hover .delete-btn { opacity: 1; }

	.chat-main { flex-grow: 1; display: flex; flex-direction: column; position: relative; overflow: hidden; }
	header { padding: 1.2rem 2rem; border-bottom: 1px solid var(--glass-border); min-height: 90px; }
	.items-center { align-items: center; }
	.gap-4 { gap: 1rem; }
	.mt-1 { margin-top: 0.25rem; }
	
	.usage-bar { display: flex; flex-direction: column; gap: 0.35rem; width: 300px; }
	.progress-bg { height: 6px; background: var(--surface-sunken); border-radius: 3px; overflow: hidden; box-shadow: inset 0 1px 3px rgba(0,0,0,0.15); }
	.progress-fill { height: 100%; background: linear-gradient(90deg, var(--accent), #8b5cf6); transition: width 0.3s ease-out; }
	.danger-fill { background: linear-gradient(90deg, var(--warning), var(--danger)); }
	.warning-text { color: var(--danger); }

	.compression-badge {
		font-size: 0.72rem; background: rgba(16,185,129,0.15); border: 1px solid var(--success); 
		color: var(--success); border-radius: 0.8rem; padding: 0.1rem 0.5rem; display: inline-flex; 
		align-items: center; gap: 0.3rem;
	}
	.revert-btn { background: none; border: none; cursor: pointer; color: inherit; padding: 0; font-size: 0.85rem; }

	.btn-sentinel { 
		padding: 0.6rem 1rem; background: var(--hover-tint); 
		border: 1px solid var(--glass-border); border-radius: 8px; color: var(--text-dim);
		font-size: 0.75rem; font-weight: 700; cursor: pointer; display: flex; align-items: center; gap: 0.5rem;
		transition: all 0.2s;
	}
	.btn-sentinel:hover { background: var(--accent-soft); border-color: var(--accent); color: var(--text-main); }
	.btn-sentinel.danger:hover { background: rgba(239, 68, 68, 0.2); border-color: var(--danger); color: var(--danger); }

	.rag-status { font-size: 0.75rem; color: var(--text-dim); display: flex; align-items: center; gap: 0.4rem; }
	.pulse { 
		width: 8px; height: 8px; background: #10b981; border-radius: 50%; 
		box-shadow: 0 0 10px #10b981; animation: pulse 2s infinite; 
	}
	@keyframes pulse {
		0% { transform: scale(0.95); box-shadow: 0 0 0 0 rgba(16, 185, 129, 0.7); }
		70% { transform: scale(1); box-shadow: 0 0 0 10px rgba(16, 185, 129, 0); }
		100% { transform: scale(0.95); box-shadow: 0 0 0 0 rgba(16, 185, 129, 0); }
	}

	.messages-container { flex-grow: 1; padding: 2rem; overflow-y: auto; display: flex; flex-direction: column; gap: 1.5rem; }
	
	.msg-wrapper { display: flex; flex-direction: column; gap: 0.25rem; max-width: 80%; }
	.msg-wrapper.user { align-self: flex-end; align-items: flex-end; }
	.msg-wrapper.bot { align-self: flex-start; align-items: flex-start; }

	.msg-row { display: flex; gap: 1rem; }
	.msg-row.user { flex-direction: row-reverse; }
	
	.avatar { width: 40px; height: 40px; display: flex; align-items: center; justify-content: center; font-size: 1.2rem; }
	.msg-content { padding: 1rem 1.25rem; font-size: 0.95rem; line-height: 1.5; white-space: pre-wrap; box-shadow: 0 4px 15px rgba(0,0,0,0.1); }
	.user .msg-content { background: linear-gradient(135deg, var(--accent), #2563eb); color: white; border-radius: 18px 18px 2px 18px; border: 1px solid rgba(255,255,255,0.1); }
	.bot .msg-content { background: var(--glass-bg); border-radius: 18px 18px 18px 2px; border: 1px solid var(--glass-border); backdrop-filter: blur(8px); color: var(--text-main); }

	.msg-actions { opacity: 0; display: flex; gap: 0.5rem; padding: 0 0.5rem; transition: opacity 0.2s; }
	.msg-wrapper:hover .msg-actions { opacity: 1; }
	.action-btn { background: none; border: none; cursor: pointer; font-size: 0.8rem; filter: grayscale(1); transition: filter 0.2s; }
	.action-btn:hover { filter: grayscale(0); }
	
	.typing-indicator { font-style: italic; opacity: 0.6; }

	.input-area { padding: 1.5rem 2rem; display: flex; gap: 1rem; border-top: 1px solid var(--glass-border); }
	.input-area input { flex-grow: 1; }
	
	.empty-chat { flex-grow: 1; justify-content: center; text-align: center; }
	.large-icon { font-size: 4rem; margin-bottom: 1rem; }
	.w-full { width: 100%; }
	.center { align-items: center; }

	.modal-overlay { position: absolute; inset: 0; background: var(--overlay-bg); z-index: 100; display: flex; align-items: center; justify-content: center; }
	.modal-content { width: 450px; padding: 2rem; border-radius: var(--radius-xl); border: 1px solid var(--glass-border); }
	.comp-btn { 
		display: flex; flex-direction: column; align-items: flex-start; gap: 0.2rem; 
		padding: 0.8rem 1rem; background: var(--hover-tint); border: 1px solid var(--glass-border);
		border-radius: var(--radius-md); cursor: pointer; transition: all 0.2s; text-align: left; color: var(--text-main);
	}
	.comp-btn:hover { background: var(--accent-soft); border-color: var(--accent); }
	.comp-btn.primary-outline { border-color: var(--accent); background: rgba(59, 130, 246, 0.1); }
	.comp-btn.primary-outline:hover { background: rgba(59, 130, 246, 0.2); }

	/* Inline edit */
	.edit-textarea { width: 100%; background: var(--surface-sunken); border: 1px solid var(--glass-border); border-radius: 8px; padding: 0.5rem; color: var(--text-main); font-size: 0.85rem; resize: vertical; font-family: inherit; }
	.edit-actions { display: flex; gap: 0.3rem; margin-top: 0.3rem; }
	.btn-xs-save { background: rgba(16,185,129,0.15); border: 1px solid rgba(16,185,129,0.3); color: #10b981; border-radius: 6px; padding: 0.2rem 0.6rem; font-size: 0.7rem; font-weight: 700; cursor: pointer; }
	.btn-xs-save:hover { background: rgba(16,185,129,0.3); }
	.btn-xs-save.accent { background: rgba(59,130,246,0.15); border-color: rgba(59,130,246,0.3); color: var(--accent); }
	.btn-xs-save.accent:hover { background: rgba(59,130,246,0.3); }
	.btn-xs-cancel { background: rgba(239,68,68,0.1); border: 1px solid rgba(239,68,68,0.2); color: var(--danger); border-radius: 6px; padding: 0.2rem 0.5rem; font-size: 0.7rem; cursor: pointer; }

	/* Compressed context block */
	.msg-wrapper.system { align-self: stretch; max-width: 100%; }
	.msg-row.system { flex-direction: row; }
	.context-block { background: rgba(16,185,129,0.06) !important; border-color: rgba(16,185,129,0.2) !important; border-radius: 12px !important; }
	.context-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.4rem; }
	.context-label { font-size: 0.7rem; font-weight: 700; color: #10b981; text-transform: uppercase; letter-spacing: 0.5px; }
	.context-text { font-size: 0.8rem; color: var(--text-dim); white-space: pre-wrap; line-height: 1.4; }

	/* Warning fill for token bar */
	.warning-fill { background: linear-gradient(90deg, #f59e0b, #f97316); }

	/* Admin message styling */
	.msg-wrapper.admin { align-self: center; max-width: 90%; }
	.msg-row.admin { flex-direction: row; }
	.admin-msg { background: rgba(168,85,247,0.12) !important; border-color: rgba(168,85,247,0.3) !important; border-radius: 12px !important; }
	.admin-badge { font-size: 0.65rem; font-weight: 700; color: #a855f7; text-transform: uppercase; letter-spacing: 0.5px; background: rgba(168,85,247,0.15); border: 1px solid rgba(168,85,247,0.3); border-radius: 0.5rem; padding: 0.1rem 0.5rem; display: inline-block; margin-bottom: 0.3rem; }

	/* Markdown body styles */
	.markdown-body { line-height: 1.6; word-break: break-word; }
	.markdown-body :global(p) { margin: 0.4em 0; }
	.markdown-body :global(p:first-child) { margin-top: 0; }
	.markdown-body :global(p:last-child) { margin-bottom: 0; }
	.markdown-body :global(h1), .markdown-body :global(h2), .markdown-body :global(h3) { margin: 0.6em 0 0.3em; font-weight: 600; }
	.markdown-body :global(h1) { font-size: 1.3em; }
	.markdown-body :global(h2) { font-size: 1.15em; }
	.markdown-body :global(h3) { font-size: 1.05em; }
	.markdown-body :global(ul), .markdown-body :global(ol) { margin: 0.4em 0; padding-left: 1.5em; }
	.markdown-body :global(li) { margin: 0.15em 0; }
	.markdown-body :global(code) { background: rgba(0,0,0,0.3); padding: 0.15em 0.35em; border-radius: 4px; font-size: 0.88em; font-family: 'Consolas', 'Monaco', monospace; }
	.markdown-body :global(pre) { background: rgba(0,0,0,0.35); border: 1px solid rgba(255,255,255,0.08); border-radius: 8px; padding: 0.8em 1em; overflow-x: auto; margin: 0.5em 0; }
	.markdown-body :global(pre code) { background: none; padding: 0; font-size: 0.85em; }
	.markdown-body :global(blockquote) { border-left: 3px solid var(--accent); margin: 0.5em 0; padding: 0.3em 0.8em; opacity: 0.85; }
	.markdown-body :global(table) { border-collapse: collapse; width: 100%; margin: 0.5em 0; font-size: 0.88em; }
	.markdown-body :global(th), .markdown-body :global(td) { border: 1px solid rgba(255,255,255,0.12); padding: 0.35em 0.6em; text-align: left; }
	.markdown-body :global(th) { background: rgba(255,255,255,0.05); font-weight: 600; }
	.markdown-body :global(a) { color: var(--accent); text-decoration: underline; }
	.markdown-body :global(strong) { font-weight: 600; }
	.markdown-body :global(hr) { border: none; border-top: 1px solid rgba(255,255,255,0.1); margin: 0.6em 0; }
	.user-text { white-space: pre-wrap; }
	.msg-content { white-space: normal; }

	/* Admin notification banner */
	.admin-notif {
		position: absolute; top: 0; left: 0; right: 0; z-index: 100;
		display: flex; align-items: center; gap: 0.75rem;
		padding: 0.75rem 1.2rem;
		background: rgba(168,85,247,0.15); border-bottom: 2px solid rgba(168,85,247,0.4);
		backdrop-filter: blur(12px);
		cursor: pointer; transition: background 0.2s;
		animation: slideDown 0.35s cubic-bezier(0.16,1,0.3,1);
	}
	.admin-notif:hover { background: rgba(168,85,247,0.25); }
	.admin-notif-icon { font-size: 1.2rem; }
	.admin-notif-text { flex: 1; font-size: 0.85rem; color: #c4b5fd; }
	.admin-notif-text strong { color: #a855f7; }
	.admin-notif-btn { background: rgba(168,85,247,0.2); border: 1px solid rgba(168,85,247,0.4); color: #a855f7; padding: 0.3rem 0.7rem; border-radius: 6px; font-size: 0.75rem; font-weight: 700; cursor: pointer; transition: all 0.15s; }
	.admin-notif-btn:hover { background: rgba(168,85,247,0.4); }
	.admin-notif-close { background: none; border: none; color: rgba(255,255,255,0.4); font-size: 1rem; cursor: pointer; padding: 0.2rem; }
	.admin-notif-close:hover { color: white; }
	@keyframes slideDown { from { opacity:0; transform:translateY(-100%); } to { opacity:1; transform:translateY(0); } }

	/* Image in message bubbles */
	.msg-image { margin-top: 0.5rem; }
	.msg-image img { max-width: 300px; max-height: 250px; border-radius: 8px; border: 1px solid var(--glass-border); cursor: pointer; transition: transform 0.15s, box-shadow 0.15s; object-fit: cover; }
	.msg-image img:hover { transform: scale(1.03); box-shadow: 0 4px 20px rgba(0,0,0,0.4); }

	/* Pending image preview */
	.pending-image-preview { position: relative; display: inline-block; margin-bottom: 0.5rem; }
	.pending-image-preview img { max-width: 200px; max-height: 120px; border-radius: 8px; border: 2px solid var(--accent); object-fit: cover; }
	.preview-clear { position: absolute; top: -6px; right: -6px; width: 22px; height: 22px; border-radius: 50%; background: rgba(239,68,68,0.9); color: white; border: none; cursor: pointer; font-size: 0.7rem; display: flex; align-items: center; justify-content: center; }

	/* Input row with attach button */
	.input-row { display: flex; gap: 0.5rem; align-items: center; width: 100%; }
	.input-row input[type="text"] { flex: 1; }
	.btn-attach { background: var(--hover-tint); border: 1px solid var(--glass-border); color: var(--text-dim); width: 40px; height: 40px; border-radius: 8px; cursor: pointer; font-size: 1.1rem; display: flex; align-items: center; justify-content: center; transition: all 0.2s; flex-shrink: 0; }
	.btn-attach:hover { background: var(--accent-soft); border-color: var(--accent); color: var(--accent); }

	/* Admin takeover banner */
	.admin-takeover-banner {
		display: flex; align-items: center; gap: 0.75rem;
		padding: 0.75rem 1.5rem; margin: 0;
		background: rgba(168, 85, 247, 0.1);
		border-top: 2px solid rgba(168, 85, 247, 0.5);
		border-bottom: 2px solid rgba(168, 85, 247, 0.5);
		animation: takeover-pulse 2s ease-in-out infinite;
	}
	.takeover-icon { font-size: 1.3rem; }
	.takeover-text { font-size: 0.85rem; color: #c4b5fd; font-weight: 500; }
	@keyframes takeover-pulse {
		0%, 100% { background: rgba(168, 85, 247, 0.08); }
		50% { background: rgba(168, 85, 247, 0.15); }
	}

	/* IA blocked banner */
	.ia-blocked-banner {
		display: flex; align-items: center; gap: 0.75rem;
		padding: 0.75rem 1.5rem;
		background: rgba(239, 68, 68, 0.1);
		border-top: 2px solid rgba(239, 68, 68, 0.5);
		border-bottom: 2px solid rgba(239, 68, 68, 0.5);
	}
	.blocked-text { font-size: 0.85rem; color: #fca5a5; font-weight: 500; }
</style>
