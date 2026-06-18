<script>
	import { t } from '$lib/i18nStore';
	import { get } from 'svelte/store';
	import { api } from '$lib/api';
	import { onMount, onDestroy, tick } from 'svelte';
	import Modal from '$lib/components/Modal.svelte';
	import { marked } from 'marked';
	import { wsMessageStore } from '$lib/ws';
	import { API_URL } from '$lib/config';
	import { aiUnreadCount } from '$lib/pmStore';

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
	let userObj = null;
	let iaConfig = { context_window: 4096 };
	let query = '';
	let loading = false;
	let autoScrollEnabled = true;
	let isAutoScrolling = false;
	let textareaRef;

	function handleScroll() {
		if (isAutoScrolling || !chatContainer) return;
		const threshold = 50;
		const isAtBottom = chatContainer.scrollHeight - chatContainer.scrollTop - chatContainer.clientHeight < threshold;
		autoScrollEnabled = isAtBottom;
	}

	// Live token counting — only count messages that Ollama will actually receive
	// +1300 tokens overhead for system prompt + user identity + tool definitions
	const SYSTEM_OVERHEAD_TOKENS = 1300;
	$: liveTokens = (() => {
		let activeMessages = compression.compressed_at
			? messages.filter(m => !m.timestamp || m.timestamp > compression.compressed_at)
			: messages;
		let total = activeMessages.reduce((sum, m) => sum + (m.content ? m.content.length : 0), 0);
		if (compression.context) total += compression.context.length;
		total += query.length;
		return Math.ceil(total / 3.5) + SYSTEM_OVERHEAD_TOKENS;
	})();
	$: contextWindow = iaConfig.context_window || 4096;
	$: tokenPct = Math.min(100, (liveTokens / contextWindow) * 100);

	// Find the index of the first message after compression (to insert context block inline)
	$: compressionInsertIdx = (() => {
		if (!compression.compressed_at || !compression.mode) return -1;
		const idx = messages.findIndex(m => m.timestamp && m.timestamp > compression.compressed_at);
		return idx >= 0 ? idx : messages.length; // if no messages after, insert at end
	})();

	// Admin notification
	let adminNotification = null;
	let unsub = null;

	function dismissNotification() { adminNotification = null; }
	function goToNotifiedConv() {
		if (adminNotification) {
			selectConversation(adminNotification.conversation_id, true);
			adminNotification = null;
		}
	}
	let showCompressionModal = false;
	let compressionReason = ''; // 'manual' or 'auto'
	let pendingQuery = ''; // message deferred until after compression
	let pendingImagePath = null;
	let editingMsgId = null;
	let editingMsgContent = '';
	let editingContext = false;
	let editContextText = '';
	let chatContainer = null;
	let adminOverride = false;
	let iaBlocked = false;
	let autoCompressNotif = false;
	let compressing = false;

	// Queue state (G-52)
	let queuePosition = 0;
	let queueEstWait = 0;
	let queueEntryId = null;
	let queued = false;
	let busyOtherConv = false; // true when user has active request in ANOTHER conversation

	// Generation progress bar metrics
	let avgDuration = 15;
	let elapsedTime = 0;
	let progressInterval = null;
	let lastLoading = false;

	$: if (loading && !lastLoading) {
		elapsedTime = 0;
		lastLoading = true;
	} else if (!loading) {
		if (lastLoading) {
			tick().then(() => {
				if (textareaRef) textareaRef.focus();
			});
		}
		lastLoading = false;
	}

	$: if (activeId) {
		tick().then(() => {
			if (textareaRef) textareaRef.focus();
		});
	}

	$: currentStatus = messages[messages.length - 1]?.role === 'bot' ? messages[messages.length - 1]?.status : null;
	$: if (loading && !queued && !compressing && currentStatus !== 'done' && currentStatus !== 'generating') {
		if (currentStatus === 'tool_call') {
			if (progressInterval) {
				clearInterval(progressInterval);
				progressInterval = null;
			}
		} else {
			if (!progressInterval) {
				progressInterval = setInterval(() => {
					elapsedTime += 0.1;
				}, 100);
			}
		}
	} else {
		if (progressInterval) {
			clearInterval(progressInterval);
			progressInterval = null;
		}
	}

	// Rotating typing messages (Astérix/Alanbix themed)
	const typingMessages = [
		'🧪 Alanbix distille une réponse…',
		'📜 Alanbix consulte les parchemins…',
		'🧠 Alanbix réfléchit intensément…',
		'⚗️ La potion de réponse mijote…',
		'🏛️ Alanbix consulte le sénat…',
		'🗡️ Alanbix combat les bugs gaulois…',
		'🐗 Alanbix chasse le sanglier de données…',
		'🍖 Pause banquet… non, Alanbix travaille !',
		'🪄 Par Toutatis, ça arrive…',
		'🛡️ Alanbix forge sa réponse…',
		'📖 Alanbix tourne les pages du savoir…',
		'🌿 Cueillette du gui numérique en cours…',
		'🏺 L\'alambic tourne à plein régime…',
		'⭐ Alanbix aligne les menhirs…',
	];
	let typingMsgIdx = 0;
	let typingFade = true;
	let typingInterval = null;
	$: typingText = typingMessages[typingMsgIdx];
	$: if (loading && !compressing && !queued) {
		if (!typingInterval) {
			typingMsgIdx = Math.floor(Math.random() * typingMessages.length);
			typingInterval = setInterval(() => {
				typingFade = false;
				setTimeout(() => {
					typingMsgIdx = (typingMsgIdx + 1) % typingMessages.length;
					typingFade = true;
				}, 200);
			}, 5000);
		}
	} else {
		if (typingInterval) { clearInterval(typingInterval); typingInterval = null; }
	}

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


	async function scrollToBottom() {
		if (!autoScrollEnabled) return;
		await tick();
		if (chatContainer) {
			isAutoScrolling = true;
			chatContainer.scrollTop = chatContainer.scrollHeight;
			setTimeout(() => {
				isAutoScrolling = false;
			}, 50);
		}
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
		aiUnreadCount.set(0);
		await loadConversations();
		iaConfig = await api.get('/ia/config');
		try { userObj = await api.get('/me'); iaBlocked = !!userObj.ia_blocked; } catch(e) {}
		try {
			const qs = await api.get('/ia/queue/status');
			if (qs && qs.avg_duration !== undefined) {
				avgDuration = qs.avg_duration;
			}
		} catch {}

		// Listen for admin intervention and chat updates via WebSocket
		unsub = wsMessageStore.subscribe(msg => {
			if (msg && msg.user_id !== undefined) {
				// Only process messages targeting this user (unless it's an admin listening, but here we are on the player page)
				// Get active user ID if we fetched it
				api.get('/me').then(me => {
					if (msg.user_id !== me.id) return;
					
					if (msg.type === 'admin_message') {
						// If the user is viewing this conversation, refresh messages live and mark read
						if (activeId === msg.conversation_id) {
							selectConversation(activeId);
						} else {
							// Otherwise, mark conversation as having unread messages
							const conv = conversations.find(c => c.id === msg.conversation_id);
							if (conv) {
								conv.has_new_messages = true;
								conv.unread_count = (conv.unread_count || 0) + 1;
								conversations = conversations;
							}
						}
						// Show notification
						adminNotification = msg;
						// Auto-dismiss after 10s
						setTimeout(() => { if (adminNotification && adminNotification.message_id === msg.message_id) adminNotification = null; }, 10000);
					}
					if (msg && msg.type === 'chat_updated' && msg.role === 'bot') {
						// Bot/AI finished writing or responded
						if (activeId === msg.conversation_id) {
							selectConversation(activeId);
						} else {
							const conv = conversations.find(c => c.id === msg.conversation_id);
							if (conv) {
								conv.has_new_messages = true;
								conv.unread_count = (conv.unread_count || 0) + 1;
								conversations = conversations;
							}
						}
					}
				}).catch(() => {});
			}
			// Auto-title arrives asynchronously via background task (no user_id filter required as conversation_id is unique)
			if (msg && msg.type === 'conv_title_updated') {
				const conv = conversations.find(c => c.id === msg.conversation_id);
				if (conv) {
					conv.title = msg.title;
					conversations = conversations;
				}
			}
		});
	});

	onDestroy(() => {
		if (unsub) unsub();
		if (progressInterval) clearInterval(progressInterval);
	});

	async function loadConversations() {
		conversations = await api.get('/ia/conversations');
		if (conversations.length > 0 && !activeId) {
			selectConversation(conversations[0].id);
		}
	}

	async function selectConversation(id, forceScroll = false) {
		const isNew = id !== activeId;
		activeId = id;
		const res = await api.get(`/ia/conversations/${id}/messages`);
		messages = res.messages;
		usage = res.usage || { estimated_tokens: 0 };
		compression = res.compression || { mode: null };
		adminOverride = res.admin_override || false;
		if (isNew || forceScroll) {
			autoScrollEnabled = true;
		}
		scrollToBottom();

		// Check if user has an active/queued AI request FOR THIS conversation
		busyOtherConv = false;
		try {
			const qs = await api.get('/ia/queue/status');
			if (qs && qs.avg_duration !== undefined) {
				avgDuration = qs.avg_duration;
			}
			if (qs && (qs.status === 'processing' || qs.status === 'queued')) {
				if (qs.conversation_id === id) {
					loading = true;
					queued = qs.status === 'queued';
					queuePosition = qs.position || 0;
					queueEstWait = qs.estimated_wait || 0;
					queueEntryId = qs.entry_id || null;
					// Add a placeholder bot message to show the typing indicator
					const lastMsg = messages[messages.length - 1];
					if (!lastMsg || lastMsg.role !== 'bot' || lastMsg.content !== '') {
						messages = [...messages, { id: Date.now(), role: 'bot', content: '' }];
					}
					scrollToBottom();
					// Record initial DB message count for change detection
					const initialCount = res.messages.length;
					// Poll for completion: check if bot message appeared in DB
					const pollId = setInterval(async () => {
						if (activeId !== id) { clearInterval(pollId); return; }
						try {
							const fresh = await api.get(`/ia/conversations/${id}/messages`);
							const qsNow = await api.get('/ia/queue/status');
							if (qsNow && qsNow.avg_duration !== undefined) {
								avgDuration = qsNow.avg_duration;
							}
							if (qsNow && qsNow.status === 'queued') {
								queuePosition = qsNow.position || 0;
								queueEstWait = qsNow.estimated_wait || 0;
							} else if (qsNow && qsNow.status === 'processing') {
								queued = false; queuePosition = 0;
							}
							if (fresh.messages.length > initialCount || !qsNow || !qsNow.status) {
								clearInterval(pollId);
								messages = fresh.messages;
								usage = fresh.usage || { estimated_tokens: 0 };
								loading = false;
								queued = false; queuePosition = 0; queueEntryId = null;
								scrollToBottom();
							}
						} catch { clearInterval(pollId); loading = false; }
					}, 2000);
				} else {
					// Request is for a DIFFERENT conversation — block input here
					busyOtherConv = true;
					queueEntryId = qs.entry_id || null;
				}
			}
		} catch {}
	}

	async function newConversation() {
		const res = await api.post('/ia/conversations', { 
			title: 'Nouvelle discussion',
			model: iaConfig.model
		});
		await loadConversations();
		await selectConversation(res.id);
	}

	async function deleteConversation(id) {
		askConfirm($t('ai_confirm_delete_title'), $t('ai_confirm_delete_desc'), 'error', async () => {
			await api.delete(`/ia/conversations/${id}`);
			if (activeId === id) activeId = null;
			await loadConversations();
		});
	}

	async function applyCompression(mode) {
		showCompressionModal = false;
		compressing = true;
		loading = true;
		try {
			await api.post(`/ia/compress/${activeId}`, { mode });
			compressing = false;
			await selectConversation(activeId);
			// Scroll to the compression block so the user sees it immediately
			await tick();
			const ctxEl = chatContainer?.querySelector('.context-block');
			if (ctxEl) {
				isAutoScrolling = true;
				ctxEl.scrollIntoView({ behavior: 'smooth', block: 'center' });
				setTimeout(() => { isAutoScrolling = false; }, 500);
			}
			autoCompressNotif = true;
			setTimeout(() => { autoCompressNotif = false; }, 5000);
			// If there was a pending message deferred by the context check, send it now
			if (pendingQuery) {
				// Pause so the user can see the compression result before the AI responds
				await new Promise(r => setTimeout(r, 1800));
				query = pendingQuery;
				pendingQuery = '';
				pendingImagePath = null;
				loading = false;
				await send();
				return;
			}
		} catch (e) {
			compressing = false;
			alert(e.message);
			// Restore pending query so user doesn't lose their message
			if (pendingQuery) { query = pendingQuery; pendingQuery = ''; }
		}
		loading = false;
	}

	async function revertCompression() {
		askConfirm($t('ai_confirm_revert_title'), $t('ai_confirm_revert_desc'), 'warning', async () => {
			await api.delete(`/ia/compress/${activeId}`);
			await selectConversation(activeId);
		});
	}

	async function deleteMsg(id) {
		askConfirm($t('ai_confirm_delete_msg_title'), $t('ai_confirm_delete_msg_desc'), 'error', async () => {
			await api.delete(`/ia/message/${id}`);
			messages = messages.filter(m => m.id !== id);
		});
	}

	async function regenerate() {
		askConfirm($t('ai_confirm_regen_title'), $t('ai_confirm_regen_desc'), 'warning', async () => {
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

	async function cancelQueue() {
		try {
			if (queueEntryId) {
				await api.delete(`/ia/queue/${queueEntryId}`);
			} else {
				await api.delete('/ia/queue/user/cancel');
			}
		} catch {}
		queued = false;
		queuePosition = 0;
		queueEntryId = null;
		loading = false;
	}

	async function send() {
		if ((!query && !pendingImage) || loading || !activeId) return;

		// Check context budget BEFORE sending — if over 85%, intercept and show compression picker
		const nextTokens = liveTokens + Math.ceil((query || '').length / 3.5);
		if (nextTokens > contextWindow * 0.85 && !compression.mode) {
			// Defer the message, show compression modal
			pendingQuery = query;
			compressionReason = 'auto';
			showCompressionModal = true;
			return;
		}

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
		queued = false;
		queuePosition = 0;
		queueEntryId = null;

		let botMsgIdx = messages.length;
		messages = [...messages, { 
			id: Date.now()+1, 
			role: 'bot', 
			content: '', 
			think_content: '', 
			status: 'thinking', 
			model_info: null, 
			active_tool: null 
		}];
		autoScrollEnabled = true;
		scrollToBottom();

		try {
			const token = localStorage.getItem('alanbix_token');
			const response = await fetch(`${API_URL}/ia/stream`, {
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
							if (data.avg_duration !== undefined) {
								avgDuration = data.avg_duration;
							}
							// Model and instance metadata
							if (data.model_info) {
								messages[botMsgIdx].model_info = data.model_info;
								messages = messages;
								continue;
							}
							// Queue events (G-52)
							if (data.queued) {
								queued = true;
								queuePosition = data.position || 1;
								queueEstWait = data.estimated_wait || 0;
								queueEntryId = data.entry_id || null;
								messages[botMsgIdx].status = 'queued';
								messages = messages;
								continue;
							}
							if (data.position !== undefined && !data.done) {
								queuePosition = data.position;
								queueEstWait = data.estimated_wait || 0;
								messages[botMsgIdx].status = 'queued';
								messages = messages;
								continue;
							}
							if (data.processing) {
								queued = false;
								queuePosition = 0;
								messages[botMsgIdx].status = 'thinking';
								messages = messages;
								continue;
							}
							// Status updates (thinking, Qwen reasoning stream, tool execution)
							if (data.status) {
								messages[botMsgIdx].status = data.status;
								if (data.status === 'tool_call') {
									messages[botMsgIdx].active_tool = data.tool_name;
									if (!messages[botMsgIdx].used_tools) {
										messages[botMsgIdx].used_tools = [];
									}
									if (!messages[botMsgIdx].used_tools.includes(data.tool_name)) {
										messages[botMsgIdx].used_tools.push(data.tool_name);
									}
								}
								if (data.status === 'thinking' && data.think_chunk) {
									messages[botMsgIdx].think_content = (messages[botMsgIdx].think_content || '') + data.think_chunk;
								}
								messages = messages;
								scrollToBottom();
								continue;
							}
							// Normal token streaming
							if (data.text) {
								if (messages[botMsgIdx].status === 'thinking' || messages[botMsgIdx].status === 'queued') {
									messages[botMsgIdx].status = 'generating';
								}
								messages[botMsgIdx].content += data.text;
								messages = messages; // trigger Svelte reactivity
								scrollToBottom();
							}
							if (data.done) {
								messages[botMsgIdx].status = 'done';
								if (data.meta) {
									messages[botMsgIdx].meta = data.meta;
								}
								messages = messages;
								// Update token estimate from server
								if (data.estimated_tokens) {
									usage = { estimated_tokens: data.estimated_tokens };
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
			queued = false;
			queuePosition = 0;
			queueEntryId = null;
			await selectConversation(activeId);
		}
	}

	function handleInputKeydown(e) {
		if (e.key === 'Enter' && !e.shiftKey) {
			e.preventDefault();
			send();
		}
	}

	function autoResizeTextarea(e) {
		const el = e.target;
		el.style.height = 'auto';
		const maxHeight = 6 * 1.5 * 16; // ~6 lines
		el.style.height = Math.min(el.scrollHeight, maxHeight) + 'px';
	}
</script>

<div class="ai-page flex-row">
	<!-- Admin Notification Banner -->
	{#if adminNotification}
		<div class="admin-notif" on:click={goToNotifiedConv}>
			<span class="admin-notif-icon">🛡️</span>
			<span class="admin-notif-text">
				{@html $t("ai_banner_sent", { admin: adminNotification.admin_name })}
			</span>
			<button class="admin-notif-btn">{$t("ai_banner_sent").includes("Voir") ? "Voir →" : $t("ai_banner_view")}</button>
			<button class="admin-notif-close" on:click|stopPropagation={dismissNotification}>✕</button>
		</div>
	{/if}
	<!-- Sidebar: Conversation History -->
	<aside class="chat-sidebar glass">
		<button class="btn-primary w-full" on:click={newConversation} disabled={iaBlocked}>{$t("ai_btn_new_chat")}</button>
		<div class="conv-list">
			{#each conversations as conv}
				<div class="conv-item {activeId === conv.id ? 'active' : ''}" class:unread={conv.has_new_messages}>
					<button class="conv-btn" on:click={() => {
						conv.has_new_messages = false;
						conv.unread_count = 0;
						conversations = conversations;
						selectConversation(conv.id, true);
					}}>
						<span class="icon">💬</span>
						<span class="title">{conv.title}</span>
						{#if conv.has_new_messages}
							<span class="unread-badge">{$t("changelog_fallback_name")}</span>
						{/if}
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
							<span class="pulse"></span> {$t("ai_status_active")}
						</div>
					</div>
					<div class="usage-bar mt-1">
						<div class="flex-row justify-between">
							<span class="text-xs text-dim">{$t("ai_label_context")} {liveTokens} / {contextWindow} tokens</span>
							{#if tokenPct > 80}
								<span class="text-xs text-danger warning-text">{$t("ai_context_limit")}</span>
							{/if}
						</div>
						<div class="progress-bg">
							<div class="progress-fill {tokenPct > 90 ? 'danger-fill' : tokenPct > 75 ? 'warning-fill' : ''}" style="width: {tokenPct}%"></div>
						</div>
					</div>
				</div>
				<div class="flex-row gap-2">
					<button class="btn-sentinel" on:click={() => { compressionReason = 'manual'; showCompressionModal = true; }} title={$t('ai_btn_context_tooltip')} disabled={iaBlocked}>
						{$t("ai_btn_context_label")}
					</button>
					<button class="btn-sentinel danger" on:click={regenerate} title={$t('ai_btn_regenerate_tooltip')} disabled={iaBlocked}>
						{$t("ai_btn_regenerate_label")}
					</button>
				</div>
			</header>

			{#if showCompressionModal}
				<div class="modal-overlay">
					<div class="modal-content glass">
						{#if compressionReason === 'auto'}
							<h3>{$t("ai_context_full")}</h3>
							<p class="text-dim text-sm mb-4">{$t("ai_context_full_desc")}</p>
							{#if pendingQuery}
								<div class="pending-msg-preview">
									<span class="pending-label">{$t("ai_pending_message")}</span>
									<span class="pending-text">{pendingQuery.length > 80 ? pendingQuery.slice(0, 80) + '…' : pendingQuery}</span>
								</div>
							{/if}
						{:else}
							<h3>{$t("ai_btn_context_tooltip")}</h3>
							<p class="text-dim text-sm mb-4">{$t("ai_context_free_options")}</p>
						{/if}
						
						<div class="flex-col gap-2">
							<button class="comp-btn" on:click={() => applyCompression('truncate')}>
								<strong>{$t("ai_context_option_truncate")}</strong>
								<span class="text-xs text-dim">{$t("ai_context_option_truncate_desc")}</span>
							</button>
							<button class="comp-btn" on:click={() => applyCompression('compact')}>
								<strong>{$t("ai_context_option_compact")}</strong>
								<span class="text-xs text-dim">{$t("ai_context_option_compact_desc")}</span>
							</button>
							<button class="comp-btn primary-outline" on:click={() => applyCompression('summary')}>
								<strong>{$t("ai_context_option_summary")}</strong>
								<span class="text-xs text-dim">{$t("ai_context_option_summary_desc")}</span>
							</button>
						</div>
						
						<div class="flex-row justify-end mt-4">
							<button class="btn-secondary" on:click={() => { showCompressionModal = false; if (pendingQuery) { query = pendingQuery; pendingQuery = ''; } }}>{$t("info_btn_cancel")}</button>
						</div>
					</div>
				</div>
			{/if}

			<div class="messages-container" bind:this={chatContainer} on:scroll={handleScroll}>
				{#if autoCompressNotif}
					<div class="auto-compress-notif">
						<span>🗜️</span>
						<span>{$t("ai_notif_compressed")}</span>
					</div>
				{/if}
				{#each messages as msg, idx}
					{#if idx === compressionInsertIdx && compression.mode}
						<div class="msg-wrapper system">
							<div class="msg-row system">
							<div class="avatar">🗜️</div>
							<div class="msg-content glass context-block">
								<details class="context-details">
									<summary class="context-summary">
										<span class="context-label">{$t("ai_context_compressed", { mode: compression.mode })}</span>
										<span class="context-size">{compression.context ? Math.ceil(compression.context.length / 3.5) + ' tokens' : '⚠️ vide'}</span>
										{#if !iaBlocked}
											<button class="action-btn" on:click|stopPropagation={startEditContext} title={$t('ai_tooltip_edit')}>✏️</button>
										{/if}
									</summary>
									{#if editingContext}
										<textarea class="edit-textarea" bind:value={editContextText} rows="4"></textarea>
										<div class="edit-actions">
											<button class="btn-xs-save" on:click={saveContextEdit}>✓ {$t('info_btn_save')}</button>
											<button class="btn-xs-cancel" on:click={() => editingContext = false}>✕ {$t("info_btn_cancel")}</button>
										</div>
									{:else}
										{#if compression.context}
											<div class="context-text">{compression.context}</div>
										{:else}
											<div class="context-text" style="opacity:0.5;font-style:italic">{$t("ai_context_empty")}</div>
										{/if}
									{/if}
								</details>
							</div>
						</div>
						</div>
					{/if}
					<div class="msg-wrapper {msg.role}">
						<div class="msg-row {msg.role}">
							<div class="avatar avatar-shape-{userObj?.avatar_shape || 'circle'}">
								{#if msg.role === 'bot'}
									🤖
								{:else if msg.role === 'admin'}
									🛡️
								{:else if msg.role === 'user' && userObj?.avatar_url}
									<img src={userObj.avatar_url} alt="" class="avatar-img" />
								{:else}
									👤
								{/if}
							</div>
							<div class="msg-content glass {msg.role === 'admin' ? 'admin-msg' : ''}"
								class:thinking-active={msg.role === 'bot' && idx === messages.length - 1 && loading && !queued && !compressing && (msg.status === 'thinking' || msg.status === 'tool_call')}
								class:pulse-progress={msg.role === 'bot' && idx === messages.length - 1 && loading && !queued && !compressing && ((msg.status === 'thinking' && elapsedTime >= avgDuration) || msg.status === 'tool_call')}
								style="--progress-percent: {Math.min(100, (elapsedTime / (avgDuration || 15)) * 100)}%;">
								{#if msg.role === 'admin'}
									<div class="admin-badge">Admin</div>
								{/if}
								{#if msg.role === 'bot'}
									{@const modelInfo = msg.model_info || (msg.meta && msg.meta.model_info)}
									{@const usedTools = msg.used_tools || (msg.meta && msg.meta.used_tools)}
									{@const msgDuration = msg.meta?.duration}
									<div class="bot-meta">
										{#if idx === messages.length - 1 && loading && !queued && !compressing && (msg.status === 'thinking' || msg.status === 'tool_call')}
											<span class="status-badge timer-badge">⏱️ {elapsedTime.toFixed(1)}s / {avgDuration.toFixed(1)}s</span>
										{:else if msgDuration !== undefined && msgDuration !== null}
											<span class="status-badge timer-badge" title="Temps de réponse du LLM (jusqu'au premier token)">⏱️ {msgDuration.toFixed(1)}s</span>
										{/if}
										{#if modelInfo}
											<span class="model-badge">🤖 {modelInfo.model} ({modelInfo.instance})</span>
										{/if}
										{#if msg.status === 'queued'}
											<span class="status-badge queued">{$t("ai_status_queued")}</span>
										{:else if msg.status === 'tool_call'}
											<span class="status-badge tool">{$t("ai_status_tool_running", { tool: msg.active_tool || 'Consultation' })}</span>
										{:else if msg.status === 'thinking'}
											<span class="status-badge thinking">{$t("ai_status_thinking")}</span>
										{/if}
										{#if usedTools && usedTools.length > 0}
											{#each usedTools as tool}
												<span class="status-badge tool finished">🛠️ {tool}</span>
											{/each}
										{/if}
									</div>
								{/if}
								{#if editingMsgId === msg.id}
									<textarea class="edit-textarea" bind:value={editingMsgContent} rows="3"></textarea>
									<div class="edit-actions">
										<button class="btn-xs-save" on:click={saveEdit}>✓ {$t('info_btn_save')}</button>
										<button class="btn-xs-save accent" on:click={editAndResend}>↻ {$t('ai_resend')}</button>
										<button class="btn-xs-cancel" on:click={cancelEdit}>✕</button>
									</div>
								{:else}
									{#if msg.role === 'bot' && msg.think_content}
										<details class="think-details" open={msg.status === 'thinking'}>
											<summary class="think-summary">
												<span>{$t("ai_thinking_process")}</span>
											</summary>
											<div class="think-text">{msg.think_content}</div>
										</details>
									{/if}
									{#if msg.role === 'bot' || msg.role === 'admin'}
										{#if msg.content}
											<div class="markdown-body">{@html parseMd(msg.content)}</div>
										{/if}
									{:else}
										<div class="markdown-body user-text">{@html escapeHtml(msg.content).replace(/\n/g, '<br>')}</div>
									{/if}
									{#if msg.image_path}
										<div class="msg-image">
											<img src="{API_URL}/data/{msg.image_path}" alt="{$t('ai_attached_image')}" on:click={() => window.open(API_URL + '/data/' + msg.image_path, '_blank')} />
										</div>
									{/if}
									{#if msg.content === '' && loading && msg.role === 'bot' && msg.id === messages[messages.length-1].id}
										<span class="typing-indicator" class:typing-fade-in={typingFade} class:typing-fade-out={!typingFade}>{compressing ? $t("ai_compressing") : queued ? $t("ai_queue_position", { pos: queuePosition }) : typingText}</span>
									{/if}
								{/if}
							</div>
						</div>
						{#if !iaBlocked}
							<div class="msg-actions">
								{#if msg.role === 'user'}
									<button class="action-btn" on:click={() => editMsg(msg)} title={$t('ai_tooltip_edit')}>✏️</button>
									<button class="action-btn" on:click={() => retryFromMsg(msg)} title={$t('ai_tooltip_retry')}>🔄</button>
								{/if}
								{#if msg.role === 'bot' && idx === messages.length - 1}
									<button class="action-btn" on:click={regenerate} title={$t('ai_tooltip_regenerate')}>🔄</button>
								{/if}
								<button class="action-btn" on:click={() => deleteMsg(msg.id)} title={$t('ai_tooltip_delete')}>🗑️</button>
							</div>
						{/if}
					</div>
				{/each}
				{#if compressing}
					<div class="msg-wrapper system">
						<div class="msg-row system">
							<div class="avatar">🗜️</div>
							<div class="msg-content glass context-block" style="text-align:center">
								<span class="typing-indicator">{$t("ai_compressing")}</span>
							</div>
						</div>
					</div>
				{/if}
			</div>

			{#if adminOverride}
				<div class="admin-takeover-banner">
					<span class="takeover-icon">🛡️</span>
					<span class="takeover-text">{$t("ai_admin_banner")}</span>
				</div>
			{/if}

			{#if iaBlocked}
				<div class="ia-blocked-banner">
					<span class="takeover-icon">🚫</span>
					<span class="blocked-text">{$t("ai_blocked")}</span>
				</div>
			{/if}

			{#if queued && queuePosition > 0}
				<div class="queue-banner">
					<div class="queue-banner-content">
						<span class="queue-icon">⏳</span>
						<div class="queue-info">
							<span class="queue-label">{@html $t("ai_queue_position_banner", { pos: queuePosition })}</span>
							{#if queueEstWait > 0}
								<span class="queue-wait">{$t("ai_queue_estimated", { time: queueEstWait })}</span>
							{/if}
						</div>
						<button class="queue-cancel-btn" on:click={cancelQueue} title="Annuler">❌ {$t("info_btn_cancel")}</button>
					</div>
					<div class="queue-progress-bg">
						<div class="queue-progress-fill"></div>
					</div>
				</div>
			{/if}

			<form class="input-area" class:input-disabled={loading || busyOtherConv} on:submit|preventDefault={send}>
				{#if pendingImagePreview}
					<div class="pending-image-preview">
						<img src={pendingImagePreview} alt="Preview" />
						<button type="button" class="preview-clear" on:click={clearPendingImage}>✕</button>
					</div>
				{/if}
				<div class="input-row">
					<input type="file" accept="image/*" bind:this={fileInput} on:change={handleFileSelect} style="display:none" />
					<button type="button" class="btn-attach" on:click={() => fileInput?.click()} title={$t('ai_input_tooltip_attach')} disabled={iaBlocked || loading || busyOtherConv}>📎</button>
					<textarea
						bind:this={textareaRef}
						bind:value={query}
						placeholder={iaBlocked ? $t('ai_input_blocked') : busyOtherConv ? $t('ai_input_busy_other') : loading ? $t('ai_input_generating') : $t('ai_input_placeholder')}
						disabled={loading || iaBlocked || busyOtherConv}
						title={busyOtherConv ? $t('ai_input_title_busy') : loading ? $t('ai_input_title_wait') : ''}
						on:paste={handlePaste}
						on:keydown={handleInputKeydown}
						on:input={autoResizeTextarea}
						rows="1"
						class="chat-textarea"
					></textarea>
					{#if loading}
						<button class="btn-stop" type="button" on:click={cancelQueue} title={$t('ai_tooltip_stop')}>{$t("ai_stop")}</button>
					{:else if busyOtherConv}
						<button class="btn-stop" type="button" on:click={async () => { await cancelQueue(); busyOtherConv = false; }} title={$t('ai_tooltip_cancel')}>{$t("ai_release")}</button>
					{:else}
						<button class="btn-primary" type="submit" disabled={iaBlocked}>{$t("ai_btn_send")}</button>
					{/if}
				</div>
			</form>
		{:else}
			<div class="empty-chat flex-col center">
				<div class="large-icon">🤖</div>
				<h2>{$t("ai_welcome_title")}</h2>
				<p class="text-dim">{$t("ai_welcome_desc")}</p>
				<button class="btn-primary" on:click={newConversation}>{$t("ai_welcome_start")}</button>
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
	.chat-sidebar { width: 260px; min-width: 260px; max-width: 260px; flex-shrink: 0; padding: 1.5rem; display: flex; flex-direction: column; gap: 1.5rem; }
	.conv-list { display: flex; flex-direction: column; gap: 0.5rem; overflow-y: auto; }
	
	.conv-item { 
		display: flex; align-items: center; justify-content: space-between;
		background: transparent; border: 1px solid transparent; color: var(--text-dim);
		border-radius: var(--radius-md); transition: all 0.2s;
	}
	.conv-item:hover { background: var(--accent-soft); }
	.conv-item.active { background: var(--accent-soft); border-color: var(--accent); color: var(--text-main); }
	.conv-item.unread {
		border-color: rgba(16, 185, 129, 0.4);
		background: rgba(16, 185, 129, 0.05);
		color: var(--text-main);
	}
	.conv-item.unread:hover {
		background: rgba(16, 185, 129, 0.1);
	}
	
	.conv-btn { 
		display: flex; align-items: center; gap: 0.75rem; padding: 0.75rem; 
		background: none; border: none; color: inherit; cursor: pointer; flex: 1; min-width: 0; text-align: left; overflow: hidden;
	}
	.conv-btn .title { font-size: 0.82rem; white-space: normal; overflow: hidden; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; line-height: 1.3; }
	
	.unread-badge {
		background: var(--success);
		color: white;
		font-size: 0.65rem;
		font-weight: 700;
		padding: 0.15rem 0.4rem;
		border-radius: 4px;
		text-transform: uppercase;
		letter-spacing: 0.5px;
		margin-left: auto;
		flex-shrink: 0;
	}

	.delete-btn { opacity: 0; padding: 0.5rem; font-size: 0.8rem; flex-shrink: 0; }
	.conv-item:hover .delete-btn { opacity: 1; }

	.chat-main { flex-grow: 1; display: flex; flex-direction: column; position: relative; overflow: hidden; }
	header { padding: 1.2rem 2rem; border-bottom: 1px solid var(--glass-border); min-height: 90px; }
	header h2 { font-size: 1rem; line-height: 1.3; max-width: 280px; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; word-break: break-word; }
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
		box-shadow: 0 0 10px #10b981; animation: pulse 2s infinite; will-change: opacity;
	}
	@keyframes pulse {
		0%, 100% { opacity: 1; }
		50% { opacity: 0.3; }
	}

	.messages-container { flex-grow: 1; padding: 2rem; overflow-y: auto; display: flex; flex-direction: column; gap: 1.5rem; }
	
	.msg-wrapper { display: flex; flex-direction: column; gap: 0.25rem; max-width: 80%; }
	.msg-wrapper.user { align-self: flex-end; align-items: flex-end; }
	.msg-wrapper.bot { align-self: flex-start; align-items: flex-start; }

	.msg-row { display: flex; gap: 1rem; }
	.msg-row.user { flex-direction: row-reverse; }
	
	.avatar { width: 40px; height: 40px; display: flex; align-items: center; justify-content: center; font-size: 1.2rem; overflow: hidden; border-radius: 50%; }
	.avatar-img { width: 100%; height: 100%; object-fit: cover; border-radius: 50%; }
	.msg-content { padding: 1rem 1.25rem; font-size: 0.95rem; line-height: 1.5; white-space: pre-wrap; box-shadow: 0 4px 15px rgba(0,0,0,0.1); }
	.user .msg-content { background: linear-gradient(135deg, var(--accent), #2563eb); color: white; border-radius: 18px 18px 2px 18px; border: 1px solid rgba(255,255,255,0.1); }
	.bot .msg-content { background: var(--glass-bg); border-radius: 18px 18px 18px 2px; border: 1px solid var(--glass-border); color: var(--text-main); }

	.msg-actions { opacity: 0; display: flex; gap: 0.5rem; padding: 0 0.5rem; transition: opacity 0.2s; }
	.msg-wrapper:hover .msg-actions { opacity: 1; }
	.action-btn { background: none; border: none; cursor: pointer; font-size: 0.8rem; filter: grayscale(1); transition: filter 0.2s; }
	.action-btn:hover { filter: grayscale(0); }
	
	.typing-indicator { font-style: italic; opacity: 0.6; transition: opacity 0.2s ease; }
	.typing-fade-in { opacity: 0.6; }
	.typing-fade-out { opacity: 0; }

	.input-area { padding: 1.5rem 2rem; display: flex; gap: 1rem; border-top: 1px solid var(--glass-border); transition: opacity 0.3s; }
	.input-area.input-disabled { opacity: 0.55; }
	.input-area.input-disabled .chat-textarea { cursor: not-allowed; background: var(--surface-sunken); }
	.input-area .chat-textarea { flex-grow: 1; }
	.btn-stop {
		padding: 0.6rem 1.2rem; font-size: 0.85rem; font-weight: 700;
		color: #ef4444; background: rgba(239,68,68,0.1); border: 1px solid rgba(239,68,68,0.35);
		border-radius: var(--radius-md); cursor: pointer; transition: all 0.2s;
		white-space: nowrap; display: flex; align-items: center; gap: 0.3rem;
	}
	.btn-stop:hover { background: rgba(239,68,68,0.2); border-color: #ef4444; }
	
	.empty-chat { flex-grow: 1; justify-content: center; text-align: center; }
	.large-icon { font-size: 4rem; margin-bottom: 1rem; }
	.w-full { width: 100%; }
	.center { align-items: center; }

	.modal-overlay { position: absolute; inset: 0; background: var(--overlay-bg); z-index: 100; display: flex; align-items: center; justify-content: center; }
	.modal-content { width: 450px; padding: 2rem; border-radius: var(--radius-xl); border: 1px solid var(--glass-border); background: var(--bg-secondary) !important; }
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
	.context-details { width: 100%; }
	.context-details summary { list-style: none; cursor: pointer; }
	.context-details summary::-webkit-details-marker { display: none; }
	.context-summary { display: flex; align-items: center; gap: 0.5rem; padding: 0.2rem 0; }
	.context-summary::before { content: '▶'; font-size: 0.6rem; color: #10b981; transition: transform 0.2s; }
	.context-details[open] .context-summary::before { transform: rotate(90deg); }
	.context-label { font-size: 0.7rem; font-weight: 700; color: #10b981; text-transform: uppercase; letter-spacing: 0.5px; }
	.context-size { font-size: 0.6rem; color: var(--text-muted); background: rgba(16,185,129,0.1); padding: 0.1rem 0.4rem; border-radius: 4px; margin-left: auto; }
	.context-text { font-size: 0.8rem; color: var(--text-dim); white-space: pre-wrap; line-height: 1.4; margin-top: 0.5rem; padding-top: 0.5rem; border-top: 1px solid rgba(16,185,129,0.15); }

	/* Warning fill for token bar */
	.warning-fill { background: linear-gradient(90deg, #f59e0b, #f97316); }

	/* Admin message styling */
	.msg-wrapper.admin { align-self: center; max-width: 90%; }
	.msg-row.admin { flex-direction: row; }
	.admin-msg { background: rgba(168,85,247,0.12) !important; border-color: rgba(168,85,247,0.3) !important; border-radius: 12px !important; }
	.admin-badge { font-size: 0.65rem; font-weight: 700; color: #a855f7; text-transform: uppercase; letter-spacing: 0.5px; background: rgba(168,85,247,0.15); border: 1px solid rgba(168,85,247,0.3); border-radius: 0.5rem; padding: 0.1rem 0.5rem; display: inline-block; margin-bottom: 0.3rem; }

	/* Bot status & thinking details */
	.bot-meta {
		display: flex;
		flex-wrap: wrap;
		gap: 0.5rem;
		font-size: 0.72rem;
		margin-bottom: 0.5rem;
		align-items: center;
	}
	.model-badge {
		background: rgba(255, 255, 255, 0.05);
		padding: 0.15rem 0.45rem;
		border-radius: 6px;
		border: 1px solid rgba(255, 255, 255, 0.1);
		color: var(--text-muted);
		font-weight: 500;
	}
	.status-badge {
		padding: 0.15rem 0.45rem;
		border-radius: 6px;
		font-weight: 600;
		font-size: 0.7rem;
		text-transform: uppercase;
		letter-spacing: 0.3px;
	}
	.status-badge.queued {
		background: rgba(245, 158, 11, 0.12);
		color: #f59e0b;
		border: 1px solid rgba(245, 158, 11, 0.25);
	}
	.status-badge.tool {
		background: rgba(59, 130, 246, 0.12);
		color: #3b82f6;
		border: 1px solid rgba(59, 130, 246, 0.25);
	}
	.status-badge.tool.finished {
		background: rgba(16, 185, 129, 0.08);
		color: #10b981;
		border: 1px solid rgba(16, 185, 129, 0.2);
	}
	.status-badge.thinking {
		background: rgba(168, 85, 247, 0.12);
		color: #a855f7;
		border: 1px solid rgba(168, 85, 247, 0.25);
	}
	.think-details {
		width: 100%;
		margin: 0.6rem 0;
		border-left: 3px solid rgba(168, 85, 247, 0.45);
		background: rgba(0, 0, 0, 0.15);
		border-radius: 0 8px 8px 0;
	}
	.think-details summary {
		list-style: none;
		cursor: pointer;
		outline: none;
		user-select: none;
	}
	.think-details summary::-webkit-details-marker {
		display: none;
	}
	.think-summary {
		display: flex;
		align-items: center;
		gap: 0.4rem;
		padding: 0.4rem 0.7rem;
		font-size: 0.75rem;
		color: #a855f7;
		font-weight: 600;
	}
	.think-summary::before {
		content: '▶';
		font-size: 0.55rem;
		color: #a855f7;
		transition: transform 0.2s;
	}
	.think-details[open] .think-summary::before {
		transform: rotate(90deg);
	}
	.think-text {
		padding: 0.5rem 0.7rem;
		font-size: 0.8rem;
		font-family: var(--font-mono, monospace);
		white-space: pre-wrap;
		color: var(--text-dim);
		line-height: 1.45;
		border-top: 1px solid rgba(255, 255, 255, 0.05);
	}

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
	.input-row { display: flex; gap: 0.5rem; align-items: flex-end; width: 100%; }
	.chat-textarea {
		flex: 1; resize: none; overflow-y: auto;
		min-height: 40px; max-height: 144px; /* ~6 lines */
		padding: 0.6rem 0.8rem; font-size: 0.95rem; line-height: 1.5;
		border: 1px solid var(--glass-border); border-radius: var(--radius-md);
		background: var(--bg-secondary); color: var(--text-main);
		font-family: inherit; outline: none; transition: border-color 0.2s;
	}
	.chat-textarea:focus { border-color: var(--accent); }
	.chat-textarea:disabled { cursor: not-allowed; background: var(--surface-sunken); opacity: 0.7; }
	.chat-textarea::placeholder { color: var(--text-muted); }
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
	/* Pending message preview in modal */
	.pending-msg-preview {
		display: flex; flex-direction: column; gap: 0.2rem;
		padding: 0.6rem 0.8rem; margin-bottom: 0.75rem;
		background: rgba(59,130,246,0.08); border: 1px solid rgba(59,130,246,0.2);
		border-radius: 8px;
	}
	.pending-label { font-size: 0.7rem; font-weight: 700; color: var(--accent); }
	.pending-text { font-size: 0.8rem; color: var(--text-main); font-style: italic; }
	/* Auto-compress notification */
	.auto-compress-notif {
		display: flex; align-items: center; gap: 0.5rem;
		padding: 0.6rem 1rem; margin-bottom: 0.5rem;
		background: rgba(16,185,129,0.1); border: 1px solid rgba(16,185,129,0.25);
		border-radius: 10px; font-size: 0.8rem; color: #10b981; font-weight: 600;
		animation: compressIn 0.4s ease-out;
	}
	@keyframes compressIn { from { opacity: 0; transform: translateY(-10px); } to { opacity: 1; transform: translateY(0); } }

	/* Queue banner (G-52) — no backdrop-filter per G-49 */
	.queue-banner {
		padding: 0.6rem 1.5rem; margin: 0;
		background: rgba(245, 158, 11, 0.1);
		border-top: 2px solid rgba(245, 158, 11, 0.4);
		border-bottom: 2px solid rgba(245, 158, 11, 0.4);
		animation: slideDown 0.35s cubic-bezier(0.16,1,0.3,1);
	}
	.queue-banner-content {
		display: flex; align-items: center; gap: 0.75rem;
	}
	.queue-icon { font-size: 1.2rem; }
	.queue-info { flex: 1; display: flex; flex-direction: column; gap: 0.15rem; }
	.queue-label { font-size: 0.85rem; color: #fbbf24; font-weight: 500; }
	.queue-label strong { color: #f59e0b; font-weight: 800; }
	.queue-wait { font-size: 0.72rem; color: var(--text-muted); }
	.queue-cancel-btn {
		background: rgba(239, 68, 68, 0.12); border: 1px solid rgba(239, 68, 68, 0.3);
		color: #f87171; border-radius: 6px; padding: 0.3rem 0.7rem;
		font-size: 0.72rem; font-weight: 700; cursor: pointer; transition: all 0.2s;
		white-space: nowrap;
	}
	.queue-cancel-btn:hover { background: rgba(239, 68, 68, 0.25); border-color: #ef4444; }
	.queue-progress-bg {
		height: 3px; background: rgba(245, 158, 11, 0.15); border-radius: 2px;
		margin-top: 0.4rem; overflow: hidden;
	}
	.queue-progress-fill {
		height: 100%; width: 40%;
		background: linear-gradient(90deg, #f59e0b, #fbbf24);
		animation: queueSlide 1.5s ease-in-out infinite;
		border-radius: 2px;
	}
	@keyframes queueSlide {
		0% { transform: translateX(-100%); }
		100% { transform: translateX(350%); }
	}

	.status-badge.timer-badge {
		background: rgba(139, 92, 246, 0.15);
		color: #c084fc;
		border: 1px solid rgba(139, 92, 246, 0.35);
		font-family: var(--font-mono, monospace);
		font-size: 0.68rem;
		text-transform: none;
		letter-spacing: 0;
	}

	.bot .msg-content.thinking-active {
		background: linear-gradient(90deg, rgba(139, 92, 246, 0.08) var(--progress-percent), var(--glass-bg) var(--progress-percent)) !important;
		border-color: rgba(139, 92, 246, 0.25) !important;
	}

	@keyframes pulseProgress {
		0%, 100% { border-color: rgba(139, 92, 246, 0.25); box-shadow: 0 4px 15px rgba(0,0,0,0.1); }
		50% { border-color: rgba(139, 92, 246, 0.65); box-shadow: 0 4px 15px rgba(0,0,0,0.1), inset 0 0 0 9999px rgba(139, 92, 246, 0.16); }
	}
	.pulse-progress {
		animation: pulseProgress 2s infinite ease-in-out !important;
	}
</style>
