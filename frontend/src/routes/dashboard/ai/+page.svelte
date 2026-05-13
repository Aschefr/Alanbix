<script>
	import { api } from '$lib/api';
	import { onMount } from 'svelte';
	import Modal from '$lib/components/Modal.svelte';

	let conversations = [];
	let activeId = null;
	let messages = [];
	let usage = { estimated_tokens: 0 };
	let compression = { mode: null, auto_mode: null, compressed_at: null, context: null };
	let iaConfig = { context_window: 4096 };
	let query = '';
	let loading = false;
	let showCompressionModal = false;
	let editingMsgId = null;
	let editingMsgContent = '';
	let editingContext = false;
	let editContextText = '';

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
	});

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
		if (!query || loading || !activeId) return;
		const userMsg = query;
		query = '';
		messages = [...messages, { id: Date.now(), role: 'user', content: userMsg }];
		loading = true;

		let botMsgIdx = messages.length;
		messages = [...messages, { id: Date.now()+1, role: 'bot', content: '' }];

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
					conversation_id: activeId
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
							}
							if (data.title) {
								const conv = conversations.find(c => c.id === activeId);
								if (conv) conv.title = data.title;
								conversations = conversations;
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
	<!-- Sidebar: Conversation History -->
	<aside class="chat-sidebar glass">
		<button class="btn-primary w-full" on:click={newConversation}>+ Nouvelle Discussion</button>
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
							<span class="text-xs text-dim">Contexte: {usage.estimated_tokens || 0} / {iaConfig.context_window || 4096} tokens</span>
							{#if usage.estimated_tokens > (iaConfig.context_window || 4096) * 0.8}
								<span class="text-xs text-danger warning-text">⚠️ Proche de la limite</span>
							{/if}
						</div>
						<div class="progress-bg">
							<div class="progress-fill {(usage.estimated_tokens > (iaConfig.context_window || 4096) * 0.8) ? 'danger-fill' : ''}" style="width: {Math.min(100, ((usage.estimated_tokens || 0) / (iaConfig.context_window || 4096)) * 100)}%"></div>
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

			<div class="messages-container">
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
							<div class="avatar">{msg.role === 'bot' ? '🤖' : '👤'}</div>
							<div class="msg-content glass">
								{#if editingMsgId === msg.id}
									<textarea class="edit-textarea" bind:value={editingMsgContent} rows="3"></textarea>
									<div class="edit-actions">
										<button class="btn-xs-save" on:click={saveEdit}>✓ Sauvegarder</button>
										<button class="btn-xs-save accent" on:click={editAndResend}>↻ Réenvoyer</button>
										<button class="btn-xs-cancel" on:click={cancelEdit}>✕</button>
									</div>
								{:else}
									{msg.content}
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

			<form class="input-area" on:submit|preventDefault={send}>
				<input type="text" bind:value={query} placeholder="Posez une question sur la LAN, les règles, le planning..." disabled={loading} />
				<button class="btn-primary" type="submit" disabled={loading}>Envoyer</button>
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
		background: none; border: none; color: inherit; cursor: pointer; flex-grow: 1; text-align: left;
	}
	.conv-btn .title { font-size: 0.9rem; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; max-width: 180px; }
	
	.delete-btn { opacity: 0; padding: 0.5rem; font-size: 0.8rem; }
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
</style>
