<script>
	import { onMount, onDestroy, tick, createEventDispatcher } from 'svelte';
	import { api } from '$lib/api';
	import { wsMessageStore } from '$lib/ws';
	import { t } from '$lib/i18nStore';
	import Icon from '$lib/components/Icon.svelte';
	import { EMOJI_CATALOG, EMOJI_CATEGORIES, DEFAULT_RECENT_EMOJIS } from '$lib/emojiCatalog';
	import { profanityFilterEnabled, toggleProfanityFilter, filterProfanityText } from '$lib/profanity';
	import { resolveMediaUrl } from '$lib/config';

	export let mode = 'p2p'; // 'p2p' | 'group'
	export let peer = null; // for p2p
	export let channelInfo = null; // for group: { channel_key, channel_type, team_names }
	export let channelMembers = [];
	export let currentUser = null;
	export let allUsers = [];

	const dispatch = createEventDispatcher();

	let messages = [];
	let loading = false;
	let textInput = '';
	let textareaEl = null;
	let chatScrollEl = null;
	let fileInputEl = null;

	let pendingImage = null;
	let pendingImagePreview = '';
	let isUploading = false;
	let isSending = false;

	let lastReadMessageId = 0;
	let firstUnreadIdx = -1;
	let showScrollToBottom = false;
	let unreadCountSinceScroll = 0;

	let lightboxImageUrl = null;
	let replyingTo = null;
	let recentEmojis = [...DEFAULT_RECENT_EMOJIS];
	let activeReactionMenuMsgId = null;
	let fullPickerMsgId = null;
	let emojiSearchQuery = '';
	let activeEmojiCategory = 'gaming';

	let soundEnabled = true;
	let audioCtx = null;
	let highlightedMessageId = null;
	let highlightTimer = null;

	// Mentions autocomplete (ONLY players, strictly NO @Alanbix)
	let showMentionDropdown = false;
	let mentionQuery = '';
	let mentionCursorPos = 0;
	let selectedMentionIdx = 0;

	// Typing indicator state
	let typingUsers = {}; // username -> timestamp
	let lastTypingSentTime = 0;
	let typingDebounceTimer = null;
	let pruneTypersInterval = null;

	let wsUnsub = null;

	$: filteredMentions = (() => {
		if (!showMentionDropdown) return [];
		const q = mentionQuery.toLowerCase().trim();
		const list = [];
		const pool = mode === 'group' && channelMembers.length > 0 ? channelMembers : allUsers;
		(pool || []).forEach(u => {
			if (u.username && u.username.toLowerCase().includes(q) && u.id !== currentUser?.id) {
				list.push({ id: u.id, username: u.username, avatar_url: u.avatar_url, team_name: u.team_name, seat_id: u.seat_id });
			}
		});
		return list.slice(0, 6);
	})();

	$: if (selectedMentionIdx >= filteredMentions.length) {
		selectedMentionIdx = Math.max(0, filteredMentions.length - 1);
	}

	$: charCount = textInput.length;
	const maxChars = 2000;
	$: isOverLimit = charCount > maxChars;
	$: charGaugeColor = charCount >= maxChars ? '#ef4444' : charCount >= maxChars * 0.85 ? '#f59e0b' : 'var(--text-muted)';

	$: filteredEmojisList = (() => {
		let list = EMOJI_CATALOG;
		if (activeEmojiCategory === 'recent') {
			list = recentEmojis.map(emoji => EMOJI_CATALOG.find(i => i.emoji === emoji) || { emoji, name: emoji, cat: 'gaming' });
		} else if (activeEmojiCategory !== 'all') {
			list = list.filter(i => i.cat === activeEmojiCategory);
		}
		if (emojiSearchQuery.trim()) {
			const q = emojiSearchQuery.toLowerCase().trim();
			list = list.filter(i => i.name.toLowerCase().includes(q) || i.emoji.includes(q));
		}
		return list;
	})();

	$: typingText = (() => {
		const names = Object.keys(typingUsers);
		if (names.length === 0) return '';
		if (names.length === 1) return $t('chat_typing_one', { name: names[0] });
		if (names.length === 2) return $t('chat_typing_two', { a: names[0], b: names[1] });
		return $t('chat_typing_many', { name: names[0], count: names.length - 1 });
	})();

	// Re-load when target changes
	$: if (mode === 'p2p' && peer?.id) {
		loadMessages(false);
	} else if (mode === 'group' && channelInfo?.channel_key) {
		loadMessages(false);
	}

	onMount(() => {
		try {
			const savedSound = localStorage.getItem('alanbix_chat_sound_enabled');
			if (savedSound !== null) soundEnabled = savedSound === 'true';
			const savedRecent = localStorage.getItem('alanbix_recent_emojis');
			if (savedRecent) recentEmojis = JSON.parse(savedRecent);
		} catch {}

		pruneTypersInterval = setInterval(() => {
			const now = Date.now();
			let changed = false;
			for (const [name, expireAt] of Object.entries(typingUsers)) {
				if (expireAt <= now) {
					delete typingUsers[name];
					changed = true;
				}
			}
			if (changed) typingUsers = { ...typingUsers };
		}, 1500);

		wsUnsub = wsMessageStore.subscribe(async msg => {
			if (!msg) return;

			// 1. Private message received
			if (mode === 'p2p' && msg.type === 'private_message_new') {
				if (msg.sender_id === peer?.id || (msg.sender_id === currentUser?.id && msg.receiver_id === peer?.id)) {
					if (msg.message) {
						if (!messages.some(m => m.id === msg.message.id)) {
							messages = [...messages, msg.message];
							onMessageAppended(msg.message);
						}
					} else {
						await loadMessages(true);
					}
					if (msg.sender_id === peer?.id) {
						api.get(`/players/messages/${peer.id}`).catch(() => {});
						dispatch('messageRead', { peerId: peer.id });
					}
				}
			}

			// 2. Private message reaction
			if (mode === 'p2p' && msg.type === 'private_message_reaction') {
				const target = messages.find(m => m.id === msg.message_id);
				if (target) {
					target.reactions = msg.reactions || {};
					messages = [...messages];
				}
			}

			// 3. Group message received
			if (mode === 'group' && msg.type === 'group_message_new') {
				if (msg.channel_key === channelInfo?.channel_key) {
					if (msg.message) {
						if (!messages.some(m => m.id === msg.message.id)) {
							messages = [...messages, msg.message];
							onMessageAppended(msg.message);
						}
					} else {
						await loadMessages(true);
					}
				}
			}

			// 4. Group message reaction
			if (mode === 'group' && msg.type === 'group_message_reaction') {
				if (msg.channel_key === channelInfo?.channel_key) {
					const target = messages.find(m => m.id === msg.message_id);
					if (target) {
						target.reactions = msg.reactions || {};
						messages = [...messages];
					}
				}
			}

			// 5. Typing indicator
			if (msg.type === 'player_typing') {
				if (msg.sender_id === currentUser?.id) return;
				const isRelevant = (mode === 'p2p' && msg.target_type === 'p2p' && msg.sender_id === peer?.id) ||
					(mode === 'group' && msg.target_type === 'group' && msg.channel_key === channelInfo?.channel_key);
				if (isRelevant) {
					if (msg.is_typing) {
						typingUsers[msg.sender_name] = Date.now() + 4000;
					} else {
						delete typingUsers[msg.sender_name];
					}
					typingUsers = { ...typingUsers };
				}
			}
		});

		window.addEventListener('click', closeAllPickers);
	});

	onDestroy(() => {
		if (wsUnsub) wsUnsub();
		if (pruneTypersInterval) clearInterval(pruneTypersInterval);
		if (highlightTimer) clearTimeout(highlightTimer);
		if (typingDebounceTimer) clearTimeout(typingDebounceTimer);
		window.removeEventListener('click', closeAllPickers);
	});

	function closeAllPickers() {
		activeReactionMenuMsgId = null;
		fullPickerMsgId = null;
		showMentionDropdown = false;
	}

	async function loadMessages(silent = false) {
		if (!silent) loading = true;
		try {
			if (mode === 'p2p' && peer?.id) {
				const res = await api.get(`/players/messages/${peer.id}`);
				lastReadMessageId = res.last_read_message_id || 0;
				messages = res.messages || [];
			} else if (mode === 'group' && channelInfo?.channel_key) {
				const res = await api.get(`/players/group/channel/${encodeURIComponent(channelInfo.channel_key)}`);
				lastReadMessageId = res.last_read_message_id || 0;
				messages = res.messages || [];
				if (res.members) channelMembers = res.members;
			}
			if (!silent) {
				firstUnreadIdx = (lastReadMessageId && messages.length)
					? messages.findIndex((m, i) => i > 0 && m.id > lastReadMessageId && m.sender_id !== currentUser?.id)
					: -1;
			}
			await tick();
			scrollToBottom(silent ? 'smooth' : 'auto');
		} catch (e) {
			console.error("Error loading chat messages:", e);
		} finally {
			if (!silent) loading = false;
		}
	}

	function onMessageAppended(msg) {
		const isMine = msg.sender_id === currentUser?.id;
		const isScrolledUp = chatScrollEl && (chatScrollEl.scrollHeight - chatScrollEl.scrollTop - chatScrollEl.clientHeight > 150);

		// Sound alert on mention
		if (!isMine && msg.content && currentUser?.username && msg.content.toLowerCase().includes(`@${currentUser.username.toLowerCase()}`)) {
			playChime();
		}

		if (isMine || !isScrolledUp) {
			tick().then(() => scrollToBottom('smooth'));
		} else {
			unreadCountSinceScroll++;
			showScrollToBottom = true;
		}
	}

	function handleScroll() {
		if (!chatScrollEl) return;
		const distanceToBottom = chatScrollEl.scrollHeight - chatScrollEl.scrollTop - chatScrollEl.clientHeight;
		showScrollToBottom = distanceToBottom > 150;
		if (!showScrollToBottom) {
			unreadCountSinceScroll = 0;
		}
	}

	function scrollToBottom(behavior = 'smooth') {
		if (!chatScrollEl) return;
		chatScrollEl.scrollTo({ top: chatScrollEl.scrollHeight, behavior });
		showScrollToBottom = false;
		unreadCountSinceScroll = 0;
	}

	function playChime() {
		if (!soundEnabled) return;
		try {
			if (!audioCtx) {
				const AudioContext = window.AudioContext || window.webkitAudioContext;
				if (AudioContext) audioCtx = new AudioContext();
			}
			if (audioCtx && audioCtx.state === 'suspended') {
				audioCtx.resume();
			}
			if (audioCtx) {
				const now = audioCtx.currentTime;
				const osc = audioCtx.createOscillator();
				const gain = audioCtx.createGain();
				osc.type = 'sine';
				osc.frequency.setValueAtTime(587.33, now); // D5
				osc.frequency.exponentialRampToValueAtTime(880, now + 0.12); // A5
				gain.gain.setValueAtTime(0.12, now);
				gain.gain.exponentialRampToValueAtTime(0.001, now + 0.28);
				osc.connect(gain);
				gain.connect(audioCtx.destination);
				osc.start(now);
				osc.stop(now + 0.28);
			}
		} catch {}
	}

	function toggleSound() {
		soundEnabled = !soundEnabled;
		try { localStorage.setItem('alanbix_chat_sound_enabled', String(soundEnabled)); } catch {}
	}

	// Typing event emission
	function handleTypingInput() {
		autoResizeTextarea();
		checkMentionDropdown();

		const now = Date.now();
		if (now - lastTypingSentTime > 2500) {
			lastTypingSentTime = now;
			sendTypingSignal(true);
		}

		if (typingDebounceTimer) clearTimeout(typingDebounceTimer);
		typingDebounceTimer = setTimeout(() => {
			sendTypingSignal(false);
		}, 3000);
	}

	async function sendTypingSignal(isTyping) {
		try {
			await api.post('/players/typing', {
				target_type: mode,
				target_id: mode === 'p2p' ? peer?.id : null,
				channel_key: mode === 'group' ? channelInfo?.channel_key : null,
				is_typing: isTyping
			});
		} catch {}
	}

	function autoResizeTextarea() {
		if (!textareaEl) return;
		textareaEl.style.height = 'auto';
		textareaEl.style.height = Math.min(textareaEl.scrollHeight, 120) + 'px';
	}

	function checkMentionDropdown() {
		if (!textareaEl) return;
		const val = textInput;
		const pos = textareaEl.selectionStart;
		mentionCursorPos = pos;
		const textBefore = val.slice(0, pos);
		const lastAt = textBefore.lastIndexOf('@');

		if (lastAt !== -1 && (lastAt === 0 || /\s/.test(textBefore[lastAt - 1]))) {
			const query = textBefore.slice(lastAt + 1);
			if (!/\s/.test(query)) {
				mentionQuery = query;
				showMentionDropdown = true;
				selectedMentionIdx = 0;
				return;
			}
		}
		showMentionDropdown = false;
	}

	function insertMention(username) {
		const val = textInput;
		const textBefore = val.slice(0, mentionCursorPos);
		const textAfter = val.slice(mentionCursorPos);
		const lastAt = textBefore.lastIndexOf('@');
		if (lastAt !== -1) {
			textInput = textBefore.slice(0, lastAt) + '@' + username + ' ' + textAfter;
			showMentionDropdown = false;
			tick().then(() => {
				if (textareaEl) {
					const newPos = lastAt + username.length + 2;
					textareaEl.focus();
					textareaEl.setSelectionRange(newPos, newPos);
					autoResizeTextarea();
				}
			});
		}
	}

	function handleKeydown(e) {
		if (showMentionDropdown && filteredMentions.length > 0) {
			if (e.key === 'ArrowDown') {
				e.preventDefault();
				selectedMentionIdx = (selectedMentionIdx + 1) % filteredMentions.length;
				return;
			}
			if (e.key === 'ArrowUp') {
				e.preventDefault();
				selectedMentionIdx = (selectedMentionIdx - 1 + filteredMentions.length) % filteredMentions.length;
				return;
			}
			if (e.key === 'Enter' || e.key === 'Tab') {
				e.preventDefault();
				insertMention(filteredMentions[selectedMentionIdx].username);
				return;
			}
			if (e.key === 'Escape') {
				showMentionDropdown = false;
				return;
			}
		}

		if (e.key === 'Enter' && !e.shiftKey) {
			e.preventDefault();
			sendMessage();
		}
	}

	async function sendMessage() {
		const content = textInput.trim();
		if ((!content && !pendingImage) || isSending) return;

		isSending = true;
		sendTypingSignal(false);

		let uploadedImagePath = pendingImage;
		const replyId = replyingTo?.id || null;

		// Clear form immediately
		const savedText = textInput;
		textInput = '';
		pendingImage = null;
		pendingImagePreview = '';
		replyingTo = null;
		showMentionDropdown = false;
		if (textareaEl) textareaEl.style.height = 'auto';

		try {
			if (mode === 'p2p') {
				const res = await api.post(`/players/messages/${peer.id}`, {
					content,
					image_path: uploadedImagePath,
					reply_to_id: replyId
				});
				if (res.message && !messages.some(m => m.id === res.message.id)) {
					messages = [...messages, res.message];
					tick().then(() => scrollToBottom('smooth'));
				}
			} else if (mode === 'group') {
				const res = await api.post('/players/group/send', {
					content,
					channel_type: channelInfo.channel_type,
					team_names: channelInfo.team_names,
					image_path: uploadedImagePath,
					reply_to_id: replyId
				});
				if (res.message && !messages.some(m => m.id === res.message.id)) {
					messages = [...messages, res.message];
					tick().then(() => scrollToBottom('smooth'));
				}
			}
			dispatch('messageSent');
		} catch (e) {
			console.error("Failed to send message:", e);
			textInput = savedText; // Restore on error
		} finally {
			isSending = false;
		}
	}

	async function handleFileUpload(e) {
		const file = e.target.files?.[0];
		if (!file) return;
		await processImageFile(file);
	}

	async function processImageFile(file) {
		if (!file.type.startsWith('image/')) return;
		if (file.size > 8 * 1024 * 1024) {
			alert("L'image est trop volumineuse (max 8 Mo).");
			return;
		}

		isUploading = true;
		const reader = new FileReader();
		reader.onload = (e) => { pendingImagePreview = e.target.result; };
		reader.readAsDataURL(file);

		try {
			const formData = new FormData();
			formData.append('file', file);
			const token = localStorage.getItem('token');
			const API_URL = import.meta.env.VITE_API_URL || '';
			const res = await fetch(`${API_URL}/players/upload-image`, {
				method: 'POST',
				headers: { 'Authorization': `Bearer ${token}` },
				body: formData
			});
			if (!res.ok) throw new Error("Upload failed");
			const data = await res.json();
			pendingImage = data.image_path;
		} catch (e) {
			console.error("Image upload failed:", e);
			pendingImage = null;
			pendingImagePreview = '';
			alert($t('chat_image_send_failed'));
		} finally {
			isUploading = false;
		}
	}

	function handlePaste(e) {
		const items = e.clipboardData?.items;
		if (!items) return;
		for (const item of items) {
			if (item.type.startsWith('image/')) {
				const file = item.getAsFile();
				if (file) {
					e.preventDefault();
					processImageFile(file);
					return;
				}
			}
		}
	}

	function handleDragOver(e) {
		e.preventDefault();
	}

	function handleDrop(e) {
		e.preventDefault();
		const file = e.dataTransfer?.files?.[0];
		if (file && file.type.startsWith('image/')) {
			processImageFile(file);
		}
	}

	// Reaction toggling
	async function toggleReaction(msgId, emoji) {
		closeAllPickers();
		saveRecentEmoji(emoji);

		// Optimistic toggle
		const target = messages.find(m => m.id === msgId);
		if (target) {
			const rx = { ...(target.reactions || {}) };
			const users = [...(rx[emoji] || [])];
			const idx = users.indexOf(currentUser?.id);
			if (idx > -1) {
				users.splice(idx, 1);
				if (users.length === 0) delete rx[emoji];
				else rx[emoji] = users;
			} else {
				users.push(currentUser?.id);
				rx[emoji] = users;
			}
			target.reactions = rx;
			messages = [...messages];
		}

		try {
			if (mode === 'p2p') {
				await api.post(`/players/messages/${peer.id}/${msgId}/reactions`, { emoji });
			} else if (mode === 'group') {
				await api.post(`/players/group/channel/${encodeURIComponent(channelInfo.channel_key)}/messages/${msgId}/reactions`, { emoji });
			}
		} catch (e) {
			console.error("Reaction failed:", e);
		}
	}

	function saveRecentEmoji(emoji) {
		if (!recentEmojis.includes(emoji)) {
			recentEmojis = [emoji, ...recentEmojis.slice(0, 7)];
			try { localStorage.setItem('alanbix_recent_emojis', JSON.stringify(recentEmojis)); } catch {}
		}
	}

	function startReply(msg) {
		replyingTo = msg;
		if (textareaEl) textareaEl.focus();
	}

	function cancelReply() {
		replyingTo = null;
	}

	function jumpToMessage(msgId) {
		const el = document.getElementById(`player-chat-msg-${msgId}`);
		if (el) {
			el.scrollIntoView({ behavior: 'smooth', block: 'center' });
			highlightedMessageId = msgId;
			if (highlightTimer) clearTimeout(highlightTimer);
			highlightTimer = setTimeout(() => {
				highlightedMessageId = null;
			}, 2000);
		}
	}

	// Profanity & formatting
	function formatMessageText(text) {
		if (!text) return '';
		let safe = text
			.replace(/&/g, '&amp;')
			.replace(/</g, '&lt;')
			.replace(/>/g, '&gt;');

		if ($profanityFilterEnabled) {
			safe = filterProfanityText(safe);
		}

		// Highlight @mentions
		safe = safe.replace(/@(\w+)/g, '<span class="mention-tag">@$1</span>');

		// Clickable links
		safe = safe.replace(
			/(https?:\/\/[^\s<]+)/g,
			'<a href="$1" target="_blank" rel="noopener noreferrer" class="chat-link">$1</a>'
		);

		return safe;
	}

	function timeAgo(dateStr, translate) {
		if (!dateStr) return '';
		let dStr = dateStr.replace(' ', 'T');
		if (!dStr.endsWith('Z')) dStr += 'Z';
		let diff = (Date.now() - new Date(dStr).getTime()) / 1000;
		if (diff < 0) diff = 0;
		if (diff < 60) return translate('players_time_justnow');
		if (diff < 3600) return translate('players_time_min', { count: Math.floor(diff / 60) });
		if (diff < 86400) return translate('players_time_hour', { count: Math.floor(diff / 3600) });
		return translate('players_time_day', { count: Math.floor(diff / 86400) });
	}
</script>

<div class="player-chat-container" on:dragover={handleDragOver} on:drop={handleDrop}>
	<!-- Header -->
	<div class="chat-header glass">
		<button class="mobile-back-btn" on:click={() => dispatch('close')} title={$t('chat_back_to_players')} aria-label={$t('chat_back_to_players')}>
			<Icon name="arrow-left" size={16} />
			<span class="mobile-back-label">{$t('common_back')}</span>
		</button>
		{#if mode === 'p2p'}
			<div class="header-main">
				<div class="avatar-wrapper" style="position: relative; display: inline-block; flex-shrink: 0;">
					<div class="peer-avatar avatar-shape-{peer?.avatar_shape || 'circle'}">
						{#if peer?.avatar_url}
							<img src={resolveMediaUrl(peer.avatar_url)} alt="" class="peer-avatar-img" />
						{:else}
							{peer?.username?.[0]?.toUpperCase() || '?'}
						{/if}
					</div>
					{#if peer?.is_online}
						<span class="online-indicator" title={$t('players_status_online')}></span>
					{/if}
				</div>
				<div class="peer-meta">
					<div class="peer-name-line">
						<span class="peer-name">{peer?.username || '?'}</span>
						{#if peer?.seat_id}
							<a href="/dashboard/map?highlight={peer.seat_id}" class="seat-badge" title={$t('players_tooltip_seat')}>📍 {peer.seat_id}</a>
						{/if}
					</div>
					<div class="peer-subtitle">
						{#if peer?.is_online}
							<span class="status-indicator online">🟢 {$t('players_status_online')}</span>
						{:else}
							<span class="status-indicator offline">⚪ {$t('players_status_offline')}</span>
						{/if}
						{#if peer?.team_name}
							<span class="subtitle-sep">·</span>
							<span class="peer-team">👥 {peer.team_name}</span>
						{/if}
					</div>
				</div>
			</div>
		{:else if mode === 'group'}
			<div class="header-main">
				<div class="group-icon-badge">
					{#if channelInfo?.channel_type === 'team'}
						<Icon name="shield" size={20} />
					{:else}
						<Icon name="swords" size={20} />
					{/if}
				</div>
				<div class="peer-meta">
					<div class="peer-name-line">
						<span class="peer-name">
							{#if channelInfo?.channel_type === 'team'}
								{channelInfo.team_names[0]}
							{:else}
								{(channelInfo?.team_names || []).join(' vs ')}
							{/if}
						</span>
					</div>
					<div class="peer-subtitle">
						<span class="group-badge-sub">
							{channelInfo?.channel_type === 'team' ? $t('players_chat_type_team') : $t('players_chat_type_inter')}
						</span>
						<span class="subtitle-sep">·</span>
						<span class="member-count-sub">{$t('chat_participants_count', { count: channelMembers.length })}</span>
					</div>
				</div>
			</div>
		{/if}

		<!-- Action tools: Profanity Shield, Sound, Close -->
		<div class="header-tools">
			<button
				class="chat-toggle"
				class:on={$profanityFilterEnabled}
				on:click={toggleProfanityFilter}
				aria-pressed={$profanityFilterEnabled}
				title={$profanityFilterEnabled ? $t('profanity_filter_enabled') : $t('profanity_filter_disabled')}
				aria-label={$profanityFilterEnabled ? $t('profanity_filter_enabled') : $t('profanity_filter_disabled')}
			>
				<Icon name={$profanityFilterEnabled ? 'shield-check' : 'shield-off'} size={15} />
			</button>
			<button
				class="chat-toggle"
				class:on={soundEnabled}
				on:click={toggleSound}
				aria-pressed={soundEnabled}
				title={soundEnabled ? $t('dash_chat_sound_enabled') : $t('dash_chat_sound_disabled')}
				aria-label={soundEnabled ? $t('dash_chat_sound_enabled') : $t('dash_chat_sound_disabled')}
			>
				<Icon name={soundEnabled ? 'bell' : 'bell-off'} size={15} />
			</button>
			<button class="tool-btn close-btn desktop-only" on:click={() => dispatch('close')} title={$t('players_chat_tooltip_close')}>
				✕
			</button>
		</div>
	</div>

	<!-- Messages Scroll Area -->
	<div class="messages-scroll" bind:this={chatScrollEl} on:scroll={handleScroll}>
		{#if loading}
			<div class="empty-state"><span>⏳</span> {$t('loading')}</div>
		{:else if messages.length === 0}
			<div class="empty-state">
				<span class="empty-icon"><Icon name="chat" size={32} /></span>
				<p>{$t('players_chat_no_msg')}</p>
			</div>
		{:else}
			{#each messages as msg, idx (msg.id || idx)}
				{#if idx === firstUnreadIdx}
					<div class="unread-divider">
						<span class="divider-line"></span>
						<span class="divider-text">{$t('chat_new_messages')}</span>
						<span class="divider-line"></span>
					</div>
				{/if}

				<div
					id="player-chat-msg-{msg.id}"
					class="message-row {msg.sender_id === currentUser?.id ? 'mine' : 'theirs'}"
					class:highlighted={highlightedMessageId === msg.id}
				>
					<div class="bubble-box">
						<!-- Sender name in group chat -->
						{#if mode === 'group' && msg.sender_id !== currentUser?.id}
							<span class="bubble-sender-name">{msg.sender_name || '?'}</span>
						{/if}

						<!-- Quoted Reply Box -->
						{#if msg.reply_to_data}
							<!-- svelte-ignore a11y-click-events-have-key-events -->
							<!-- svelte-ignore a11y-no-static-element-interactions -->
							<div class="reply-quote-preview" on:click={() => jumpToMessage(msg.reply_to_data.id)}>
								<span class="quote-sender">↩ {msg.reply_to_data.sender_name}</span>
								<p class="quote-text">{msg.reply_to_data.content || '📷 ' + $t('chat_image_placeholder')}</p>
							</div>
						{/if}

						<!-- Attached Image -->
						{#if msg.image_path}
							<!-- svelte-ignore a11y-click-events-have-key-events -->
							<!-- svelte-ignore a11y-no-static-element-interactions -->
							<div class="image-attachment-wrap" on:click={() => lightboxImageUrl = msg.image_path}>
								<img src={msg.image_path} alt={$t('chat_image_alt')} class="message-img" loading="lazy" />
							</div>
						{/if}

						<!-- Text content -->
						{#if msg.content}
							<div class="bubble-text">{@html formatMessageText(msg.content)}</div>
						{/if}

						<!-- Link Preview Card -->
						{#if msg.link_preview}
							<a href={msg.link_preview.url} target="_blank" rel="noopener noreferrer" class="link-preview-card">
								{#if msg.link_preview.image}
									<img src={msg.link_preview.image} alt="" class="lp-img" />
								{/if}
								<div class="lp-info">
									<span class="lp-domain">{msg.link_preview.domain || ''}</span>
									<span class="lp-title">{msg.link_preview.title || ''}</span>
									{#if msg.link_preview.description}
										<p class="lp-desc">{msg.link_preview.description}</p>
									{/if}
								</div>
							</a>
						{/if}

						<!-- Time -->
						<span class="bubble-timestamp">{timeAgo(msg.created_at, $t)}</span>

						<!-- Reactions pill bar -->
						{#if msg.reactions && Object.keys(msg.reactions).length > 0}
							<div class="reactions-pill-bar">
								{#each Object.entries(msg.reactions) as [emoji, userIds]}
									<button
										class="reaction-pill"
										class:user-reacted={userIds.includes(currentUser?.id)}
										on:click={() => toggleReaction(msg.id, emoji)}
										title={$t('chat_reaction_count', { count: userIds.length })}
									>
										<span class="pill-emoji">{emoji}</span>
										<span class="pill-count">{userIds.length}</span>
									</button>
								{/each}
							</div>
						{/if}

						<!-- Floating quick-action bar (hover) -->
						<div class="message-hover-actions">
							{#each recentEmojis.slice(0, 3) as emoji}
								<button class="quick-react-btn" on:click={() => toggleReaction(msg.id, emoji)}>
									{emoji}
								</button>
							{/each}
							<button
								class="quick-react-btn"
								on:click|stopPropagation={() => { fullPickerMsgId = fullPickerMsgId === msg.id ? null : msg.id; }}
								title={$t('dash_chat_all_emojis')}
							>
								➕
							</button>
							<button class="quick-react-btn" on:click={() => startReply(msg)} title={$t('dash_chat_reply_action')}>
								↩
							</button>
						</div>

						<!-- Full Emoji Picker Popover -->
						{#if fullPickerMsgId === msg.id}
							<!-- svelte-ignore a11y-click-events-have-key-events -->
							<!-- svelte-ignore a11y-no-static-element-interactions -->
							<div class="full-emoji-popover {idx < 2 ? 'popover-down' : 'popover-up'}" on:click|stopPropagation>
								<div class="picker-search-bar">
									<span>🔍</span>
									<input
										type="text"
										class="picker-search-input"
										placeholder={$t('dash_chat_search_emojis')}
										bind:value={emojiSearchQuery}
										on:click|stopPropagation
									/>
									{#if emojiSearchQuery}
										<button class="picker-clear-btn" on:click|stopPropagation={() => emojiSearchQuery = ''}>✕</button>
									{/if}
								</div>

								<div class="picker-cat-tabs">
									{#each EMOJI_CATEGORIES as cat}
										<button
											class="cat-tab"
											class:active={activeEmojiCategory === cat.id}
											on:click|stopPropagation={() => activeEmojiCategory = cat.id}
											title={$t(cat.labelKey)}
										>
											{cat.icon}
										</button>
									{/each}
								</div>

								<div class="picker-grid">
									{#if filteredEmojisList.length === 0}
										<div class="picker-empty">{$t('dash_chat_no_emojis_found')}</div>
									{:else}
										{#each filteredEmojisList as item}
											<button
												class="picker-emoji-btn"
												on:click|stopPropagation={() => toggleReaction(msg.id, item.emoji)}
												title={item.name}
											>
												{item.emoji}
											</button>
										{/each}
									{/if}
								</div>
							</div>
						{/if}
					</div>
				</div>
			{/each}
		{/if}
	</div>

	<!-- Floating Scroll to Bottom Button -->
	{#if showScrollToBottom}
		<button class="floating-scroll-btn glass" type="button" on:click={() => scrollToBottom('smooth')}>
			👇 {$t('chat_scroll_to_bottom')} {#if unreadCountSinceScroll > 0}<span class="scroll-unread-badge">({unreadCountSinceScroll})</span>{/if}
		</button>
	{/if}

	<!-- Active Typing Bar -->
	{#if typingText}
		<div class="typing-status-bar">
			<span class="typing-dots">
				<span></span><span></span><span></span>
			</span>
			<span class="typing-text">{typingText}</span>
		</div>
	{/if}

	<!-- Active Reply Bar -->
	{#if replyingTo}
		<div class="active-reply-bar">
			<div class="reply-meta">
				<span class="reply-target">↩ {$t('dash_chat_replying_to')} <strong>{replyingTo.sender_name || (replyingTo.sender_id === currentUser?.id ? $t('chat_you') : (peer?.username || $t('chat_member_fallback')))}</strong></span>
				<p class="reply-snippet">{replyingTo.content || '📷 ' + $t('chat_image_placeholder')}</p>
			</div>
			<button class="cancel-reply-btn" on:click={cancelReply}>✕</button>
		</div>
	{/if}

	<!-- Pending Image Preview Bar -->
	{#if pendingImagePreview}
		<div class="pending-preview-bar">
			<div class="thumb-box">
				<img src={pendingImagePreview} alt={$t('chat_preview_alt')} />
				<button class="remove-thumb-btn" on:click={() => { pendingImage = null; pendingImagePreview = ''; }}>✕</button>
			</div>
			<span class="preview-lbl">{$t('chat_image_ready')} {#if isUploading}{$t('chat_uploading')}{/if}</span>
		</div>
	{/if}

	<!-- Input Area -->
	<div class="input-container">
		<!-- Mention dropdown -->
		{#if showMentionDropdown && filteredMentions.length > 0}
			<div class="mention-dropdown glass">
				{#each filteredMentions as mUser, mIdx}
					<!-- svelte-ignore a11y-click-events-have-key-events -->
					<!-- svelte-ignore a11y-no-static-element-interactions -->
					<div
						class="mention-row"
						class:active={mIdx === selectedMentionIdx}
						on:click={() => insertMention(mUser.username)}
					>
						<span class="mention-avatar">{mUser.username[0].toUpperCase()}</span>
						<span class="mention-name">{mUser.username}</span>
						{#if mUser.team_name}<span class="mention-team">{mUser.team_name}</span>{/if}
					</div>
				{/each}
			</div>
		{/if}

		<div class="input-actions-row">
			<!-- Attachment button -->
			<input
				type="file"
				accept="image/png,image/jpeg,image/webp,image/gif"
				style="display: none;"
				bind:this={fileInputEl}
				on:change={handleFileUpload}
			/>
			<button
				class="input-icon-btn"
				title={$t('chat_attach_image_dm')}
				on:click={() => fileInputEl?.click()}
				disabled={isUploading}
			>
				<Icon name="paperclip" size={15} />
			</button>

			<!-- Textarea wrapper -->
			<div class="textarea-wrap">
				<textarea
					bind:this={textareaEl}
					bind:value={textInput}
					on:input={handleTypingInput}
					on:keydown={handleKeydown}
					on:paste={handlePaste}
					placeholder={mode === 'p2p' ? $t('players_chat_placeholder_single') : $t('players_chat_placeholder')}
					rows="1"
				></textarea>
				<span class="char-count" style="color: {charGaugeColor};">{charCount}/{maxChars}</span>
			</div>

			<!-- Send Button -->
			<button
				class="send-btn"
				on:click={sendMessage}
				disabled={(!textInput.trim() && !pendingImage) || isSending || isOverLimit}
			>
				{#if isSending}
					<span class="spinner-mini"></span>
				{:else}
					<span>➤</span>
				{/if}
			</button>
		</div>
	</div>

	<!-- Lightbox Modal -->
	{#if lightboxImageUrl}
		<!-- svelte-ignore a11y-click-events-have-key-events -->
		<!-- svelte-ignore a11y-no-static-element-interactions -->
		<div class="lightbox-backdrop" on:click={() => lightboxImageUrl = null}>
			<div class="lightbox-content" on:click|stopPropagation>
				<img src={lightboxImageUrl} alt={$t('chat_enlarged_alt')} class="lightbox-img" />
				<button class="lightbox-close-btn" on:click={() => lightboxImageUrl = null}>✕</button>
			</div>
		</div>
	{/if}
</div>

<style>
	.player-chat-container {
		display: flex;
		flex-direction: column;
		height: 100%;
		position: relative;
		overflow: hidden;
		background: transparent;
		border-radius: 12px;
	}

	/* Header */
	.chat-header {
		display: flex;
		align-items: center;
		justify-content: space-between;
		padding: 0.65rem 0.9rem;
		border-bottom: 2px solid var(--accent-soft);
		background: var(--surface-raised);
		box-shadow: 0 2px 8px rgba(0, 0, 0, 0.12);
		flex-shrink: 0;
		gap: 0.6rem;
		z-index: 20;
	}
	.mobile-back-btn {
		display: none;
		align-items: center;
		gap: 0.35rem;
		padding: 0.35rem 0.65rem;
		border-radius: 6px;
		background: var(--accent-soft);
		border: 1px solid rgba(59, 130, 246, 0.25);
		color: var(--accent);
		font-size: 0.78rem;
		font-weight: 700;
		cursor: pointer;
		flex-shrink: 0;
		transition: all 0.15s ease;
	}
	.mobile-back-btn:active {
		transform: scale(0.96);
		background: rgba(59, 130, 246, 0.2);
	}
	.peer-name-line {
		display: flex;
		align-items: center;
		gap: 0.4rem;
	}
	.peer-subtitle {
		display: flex;
		align-items: center;
		gap: 0.3rem;
		font-size: 0.68rem;
		color: var(--text-dim);
	}
	.status-indicator.online {
		color: #10b981;
		font-weight: 600;
	}
	.status-indicator.offline {
		color: var(--text-muted);
	}
	.subtitle-sep {
		opacity: 0.5;
	}
	@media (max-width: 900px) {
		/* messaging-app style: just the arrow, so the contact's name keeps its room */
		.mobile-back-btn {
			display: flex;
			justify-content: center;
			width: 36px;
			height: 36px;
			padding: 0;
		}
		.mobile-back-label {
			display: none;
		}
		.desktop-only {
			display: none !important;
		}
		.player-chat-container {
			border-radius: 0 !important;
		}
	}
	.header-main {
		display: flex;
		align-items: center;
		gap: 0.6rem;
		min-width: 0;
		flex: 1;
	}
	.peer-avatar {
		width: 32px;
		height: 32px;
		border-radius: 50%;
		background: var(--bg-tertiary, #334155);
		display: flex;
		align-items: center;
		justify-content: center;
		font-size: 0.75rem;
		font-weight: 800;
		color: var(--accent);
		border: 1px solid rgba(59, 130, 246, 0.3);
		overflow: hidden;
	}
	.peer-avatar-img {
		width: 100%;
		height: 100%;
		object-fit: cover;
	}
	.online-indicator {
		position: absolute;
		bottom: -2px;
		right: -2px;
		width: 9px;
		height: 9px;
		background: #10b981;
		border: 2px solid var(--bg-primary, #0f172a);
		border-radius: 50%;
	}
	.group-icon-badge {
		font-size: 1.2rem;
		line-height: 1;
	}
	.peer-meta {
		display: flex;
		flex-direction: column;
		min-width: 0;
	}
	.peer-name {
		font-weight: 700;
		font-size: 0.85rem;
		color: var(--text-main);
		white-space: nowrap;
		overflow: hidden;
		text-overflow: ellipsis;
	}
	.peer-team {
		font-size: 0.65rem;
		color: var(--text-muted);
		white-space: nowrap;
		overflow: hidden;
		text-overflow: ellipsis;
	}
	.seat-badge {
		font-size: 0.65rem;
		padding: 0.15rem 0.4rem;
		border-radius: 4px;
		background: rgba(59, 130, 246, 0.15);
		border: 1px solid rgba(59, 130, 246, 0.3);
		color: var(--accent);
		text-decoration: none;
		white-space: nowrap;
	}
	.header-tools {
		display: flex;
		align-items: center;
		gap: 0.35rem;
		flex-shrink: 0;
	}
	.tool-btn {
		background: var(--surface-sunken, rgba(15, 23, 42, 0.5));
		border: 1px solid var(--glass-border);
		border-radius: 6px;
		padding: 0.25rem 0.45rem;
		font-size: 0.8rem;
		cursor: pointer;
		color: var(--text-muted);
		transition: all 0.15s;
	}
	.tool-btn:hover {
		background: var(--hover-tint, rgba(255, 255, 255, 0.1));
		color: var(--text-main);
	}
	.tool-btn.active {
		border-color: rgba(59, 130, 246, 0.5);
		background: rgba(59, 130, 246, 0.15);
	}
	.close-btn {
		font-weight: 800;
	}

	/* Messages scroll */
	.messages-scroll {
		flex: 1;
		min-height: 0;
		overflow-y: auto;
		overflow-x: hidden;
		padding: 1.2rem 0.8rem 0.8rem;
		display: flex;
		flex-direction: column;
		gap: 0.75rem;
	}
	.empty-state {
		display: flex;
		flex-direction: column;
		align-items: center;
		justify-content: center;
		height: 100%;
		color: var(--text-muted);
		font-size: 0.8rem;
		gap: 0.4rem;
	}
	.empty-icon { font-size: 1.8rem; opacity: 0.6; }

	.unread-divider {
		display: flex;
		align-items: center;
		gap: 0.6rem;
		margin: 0.4rem 0;
	}
	.divider-line {
		flex: 1;
		height: 1px;
		background: #8b5cf6;
		opacity: 0.5;
	}
	.divider-text {
		font-size: 0.6rem;
		font-weight: 800;
		color: #a78bfa;
		text-transform: uppercase;
		letter-spacing: 0.05em;
	}

	/* Message row */
	.message-row {
		display: flex;
		flex-direction: column;
		max-width: 82%;
		position: relative;
		transition: background 0.3s ease;
	}
	.message-row.mine {
		align-self: flex-end;
		align-items: flex-end;
	}
	.message-row.theirs {
		align-self: flex-start;
		align-items: flex-start;
	}
	.message-row.highlighted .bubble-box {
		animation: flash-highlight 1.8s ease;
	}
	@keyframes flash-highlight {
		0%, 100% { box-shadow: none; }
		20%, 60% { box-shadow: 0 0 16px rgba(59, 130, 246, 0.8); }
	}

	.bubble-box {
		position: relative;
		padding: 0.55rem 0.75rem;
		border-radius: 12px;
		word-break: break-word;
		box-shadow: 0 2px 6px rgba(0, 0, 0, 0.15);
		font-size: 0.78rem;
		line-height: 1.35;
	}
	.mine .bubble-box {
		background: linear-gradient(135deg, rgba(59, 130, 246, 0.9), rgba(37, 99, 235, 0.95));
		color: #ffffff;
		border-bottom-right-radius: 3px;
	}
	.theirs .bubble-box {
		background: var(--surface-raised);
		color: var(--text-main);
		border: 1px solid var(--glass-border);
		border-bottom-left-radius: 3px;
	}

	.bubble-sender-name {
		font-size: 0.65rem;
		font-weight: 800;
		color: #38bdf8;
		margin-bottom: 0.2rem;
		display: block;
	}

	.bubble-timestamp {
		font-size: 0.58rem;
		opacity: 0.7;
		display: block;
		margin-top: 0.25rem;
		text-align: right;
	}

	/* Quoted reply inside bubble */
	.reply-quote-preview {
		background: rgba(0, 0, 0, 0.25);
		border-left: 3px solid rgba(255, 255, 255, 0.6);
		padding: 0.25rem 0.5rem;
		border-radius: 4px;
		margin-bottom: 0.35rem;
		cursor: pointer;
		font-size: 0.68rem;
		transition: background 0.15s;
	}
	.reply-quote-preview:hover {
		background: rgba(0, 0, 0, 0.35);
	}
	.quote-sender {
		font-weight: 700;
		font-size: 0.62rem;
		opacity: 0.9;
		display: block;
	}
	.quote-text {
		margin: 0;
		white-space: nowrap;
		overflow: hidden;
		text-overflow: ellipsis;
		opacity: 0.8;
	}

	/* Image attachment */
	.image-attachment-wrap {
		margin: 0.25rem 0;
		border-radius: 6px;
		overflow: hidden;
		cursor: pointer;
		max-width: 220px;
		max-height: 180px;
	}
	.message-img {
		width: 100%;
		height: 100%;
		object-fit: cover;
		display: block;
		transition: transform 0.15s;
	}
	.image-attachment-wrap:hover .message-img {
		transform: scale(1.02);
	}

	/* Link preview card */
	.link-preview-card {
		display: flex;
		flex-direction: column;
		border-radius: 6px;
		overflow: hidden;
		background: rgba(0, 0, 0, 0.3);
		border: 1px solid rgba(255, 255, 255, 0.15);
		text-decoration: none;
		color: inherit;
		margin-top: 0.35rem;
		max-width: 220px;
	}
	.lp-img {
		width: 100%;
		height: 80px;
		object-fit: cover;
	}
	.lp-info {
		padding: 0.35rem;
		display: flex;
		flex-direction: column;
		gap: 0.15rem;
	}
	.lp-domain {
		font-size: 0.55rem;
		text-transform: uppercase;
		opacity: 0.7;
	}
	.lp-title {
		font-size: 0.65rem;
		font-weight: 700;
		line-height: 1.2;
	}
	.lp-desc {
		font-size: 0.58rem;
		opacity: 0.75;
		margin: 0;
		line-height: 1.2;
		display: -webkit-box;
		-webkit-line-clamp: 2;
		-webkit-box-orient: vertical;
		overflow: hidden;
	}

	/* Reactions pill bar */
	.reactions-pill-bar {
		display: flex;
		flex-wrap: wrap;
		gap: 0.25rem;
		margin-top: 0.35rem;
	}
	.reaction-pill {
		display: inline-flex;
		align-items: center;
		gap: 0.25rem;
		padding: 0.1rem 0.35rem;
		border-radius: 12px;
		font-size: 0.65rem;
		background: rgba(0, 0, 0, 0.25);
		border: 1px solid rgba(255, 255, 255, 0.15);
		color: inherit;
		cursor: pointer;
		transition: all 0.15s;
	}
	.reaction-pill:hover {
		transform: scale(1.08);
	}
	.reaction-pill.user-reacted {
		background: rgba(59, 130, 246, 0.3);
		border-color: rgba(59, 130, 246, 0.7);
	}

	/* Hover actions bar */
	.message-hover-actions {
		position: absolute;
		top: -14px;
		display: none;
		align-items: center;
		gap: 2px;
		background: var(--bg-secondary, #1e293b);
		border: 1px solid var(--glass-border);
		border-radius: 14px;
		padding: 2px 4px;
		box-shadow: 0 4px 10px rgba(0, 0, 0, 0.25);
		z-index: 20;
	}
	.bubble-box:hover .message-hover-actions {
		display: flex;
	}
	.theirs .message-hover-actions {
		left: 4px;
		right: auto;
	}
	.mine .message-hover-actions {
		right: 4px;
		left: auto;
	}
	.quick-react-btn {
		background: transparent;
		border: none;
		font-size: 0.75rem;
		color: var(--text-main);
		cursor: pointer;
		padding: 2px 4px;
		border-radius: 4px;
		transition: transform 0.1s;
		display: inline-flex;
		align-items: center;
		justify-content: center;
	}
	.quick-react-btn:hover {
		transform: scale(1.2);
		background: var(--hover-tint);
	}

	/* Full emoji picker popover */
	.full-emoji-popover {
		position: absolute;
		width: 250px;
		background: var(--bg-secondary, #1e293b);
		border: 1px solid var(--glass-border);
		border-radius: 10px;
		box-shadow: 0 8px 24px rgba(0, 0, 0, 0.4);
		padding: 0.5rem;
		z-index: 100;
	}
	.theirs .full-emoji-popover {
		left: 0;
		right: auto;
	}
	.mine .full-emoji-popover {
		right: 0;
		left: auto;
	}
	.full-emoji-popover.popover-up { bottom: 100%; margin-bottom: 6px; }
	.full-emoji-popover.popover-down { top: 100%; margin-top: 6px; }

	.picker-search-bar {
		display: flex;
		align-items: center;
		gap: 0.3rem;
		background: var(--surface-sunken);
		border: 1px solid var(--glass-border);
		border-radius: 6px;
		padding: 0.2rem 0.4rem;
		margin-bottom: 0.4rem;
	}
	.picker-search-input {
		background: transparent;
		border: none;
		color: var(--text-main);
		font-size: 0.7rem;
		width: 100%;
		outline: none;
	}
	.picker-clear-btn {
		background: transparent;
		border: none;
		color: var(--text-muted);
		cursor: pointer;
		font-size: 0.65rem;
	}
	.picker-cat-tabs {
		display: flex;
		gap: 2px;
		margin-bottom: 0.4rem;
	}
	.cat-tab {
		flex: 1;
		background: transparent;
		border: none;
		font-size: 0.8rem;
		padding: 0.2rem 0;
		border-radius: 4px;
		cursor: pointer;
		opacity: 0.6;
		transition: all 0.1s;
	}
	.cat-tab:hover, .cat-tab.active {
		opacity: 1;
		background: var(--hover-tint, rgba(255, 255, 255, 0.1));
	}
	.picker-grid {
		display: grid;
		grid-template-columns: repeat(7, 1fr);
		gap: 4px;
		max-height: 140px;
		overflow-y: auto;
	}
	.picker-emoji-btn {
		background: transparent;
		border: none;
		font-size: 1rem;
		cursor: pointer;
		padding: 2px;
		border-radius: 4px;
		transition: transform 0.1s;
	}
	.picker-emoji-btn:hover {
		transform: scale(1.25);
		background: var(--hover-tint, rgba(255, 255, 255, 0.1));
	}
	.picker-empty {
		grid-column: span 7;
		text-align: center;
		font-size: 0.65rem;
		color: var(--text-muted);
		padding: 1rem 0;
	}

	/* Floating scroll to bottom button */
	.floating-scroll-btn {
		position: absolute;
		bottom: 60px;
		left: 50%;
		transform: translateX(-50%);
		padding: 0.35rem 0.8rem;
		border-radius: 20px;
		font-size: 0.72rem;
		font-weight: 700;
		cursor: pointer;
		z-index: 20;
		box-shadow: 0 4px 12px rgba(0, 0, 0, 0.4);
		border: 1px solid var(--accent);
		background: var(--surface-raised);
		color: var(--text-main);
	}
	.scroll-unread-badge {
		color: var(--accent);
		margin-left: 2px;
	}

	/* Typing indicator */
	.typing-status-bar {
		display: flex;
		align-items: center;
		gap: 0.4rem;
		padding: 0.2rem 0.9rem;
		font-size: 0.65rem;
		color: var(--text-muted);
		font-style: italic;
		background: transparent;
	}
	.typing-dots {
		display: inline-flex;
		gap: 2px;
	}
	.typing-dots span {
		width: 4px;
		height: 4px;
		background: var(--text-muted);
		border-radius: 50%;
		animation: dot-bounce 1.4s infinite ease-in-out;
	}
	.typing-dots span:nth-child(2) { animation-delay: 0.2s; }
	.typing-dots span:nth-child(3) { animation-delay: 0.4s; }
	@keyframes dot-bounce {
		0%, 80%, 100% { transform: scale(0); opacity: 0.3; }
		40% { transform: scale(1); opacity: 1; }
	}

	/* Active reply bar */
	.active-reply-bar {
		display: flex;
		align-items: center;
		justify-content: space-between;
		padding: 0.35rem 0.9rem;
		background: var(--surface-sunken, rgba(15, 23, 42, 0.6));
		border-top: 1px solid var(--glass-border);
		font-size: 0.68rem;
	}
	.reply-target {
		font-weight: 700;
		color: var(--accent);
	}
	.reply-snippet {
		margin: 0;
		color: var(--text-muted);
		white-space: nowrap;
		overflow: hidden;
		text-overflow: ellipsis;
		max-width: 250px;
	}
	.cancel-reply-btn {
		background: transparent;
		border: none;
		color: var(--text-muted);
		cursor: pointer;
		font-weight: 800;
	}

	/* Pending preview */
	.pending-preview-bar {
		display: flex;
		align-items: center;
		gap: 0.5rem;
		padding: 0.35rem 0.9rem;
		background: var(--surface-sunken);
		border-top: 1px solid var(--glass-border);
	}
	.thumb-box {
		position: relative;
		width: 36px;
		height: 36px;
		border-radius: 6px;
		overflow: hidden;
		border: 1px solid var(--glass-border);
	}
	.thumb-box img {
		width: 100%;
		height: 100%;
		object-fit: cover;
	}
	.remove-thumb-btn {
		position: absolute;
		top: 1px;
		right: 1px;
		background: rgba(0, 0, 0, 0.7);
		color: white;
		border: none;
		width: 14px;
		height: 14px;
		font-size: 0.55rem;
		border-radius: 50%;
		cursor: pointer;
	}
	.preview-lbl {
		font-size: 0.65rem;
		color: var(--text-muted);
	}

	/* Input container */
	.input-container {
		position: relative;
		border-top: 1px solid var(--glass-border);
		background: var(--surface-sunken, rgba(15, 23, 42, 0.7));
		padding: 0.5rem 0.75rem;
		flex-shrink: 0;
	}
	.input-actions-row {
		display: flex;
		align-items: flex-end;
		gap: 0.4rem;
	}
	.input-icon-btn {
		background: var(--surface-raised);
		border: 1px solid var(--glass-border);
		border-radius: 8px;
		width: 32px;
		height: 32px;
		display: flex;
		align-items: center;
		justify-content: center;
		font-size: 0.9rem;
		color: var(--text-muted);
		cursor: pointer;
		flex-shrink: 0;
		transition: all 0.15s;
	}
	.input-icon-btn:hover {
		color: var(--accent);
		background: var(--accent-soft);
	}
	.textarea-wrap {
		flex: 1;
		position: relative;
	}
	textarea {
		width: 100%;
		min-height: 32px;
		max-height: 100px;
		background: var(--input-bg, var(--surface-sunken));
		border: 1px solid var(--glass-border);
		border-radius: 8px;
		padding: 0.35rem 2.5rem 0.35rem 0.6rem;
		color: var(--input-color, var(--text-main));
		font-size: 0.78rem;
		line-height: 1.3;
		font-family: inherit;
		resize: none;
		box-sizing: border-box;
	}
	textarea:focus {
		outline: none;
		border-color: var(--accent);
	}
	.char-count {
		position: absolute;
		right: 6px;
		bottom: 4px;
		font-size: 0.5rem;
		font-weight: 700;
		pointer-events: none;
	}
	.send-btn {
		width: 32px;
		height: 32px;
		border-radius: 8px;
		background: var(--accent);
		color: white;
		border: none;
		display: flex;
		align-items: center;
		justify-content: center;
		cursor: pointer;
		flex-shrink: 0;
		transition: transform 0.1s, opacity 0.15s;
	}
	.send-btn:disabled {
		opacity: 0.4;
		cursor: not-allowed;
	}
	.send-btn:not(:disabled):hover {
		transform: scale(1.05);
	}
	.spinner-mini {
		width: 12px;
		height: 12px;
		border: 2px solid rgba(255, 255, 255, 0.3);
		border-top-color: white;
		border-radius: 50%;
		animation: spin 0.6s linear infinite;
	}
	@keyframes spin { to { transform: rotate(360deg); } }

	/* Mention dropdown */
	.mention-dropdown {
		position: absolute;
		bottom: 100%;
		left: 0.75rem;
		right: 0.75rem;
		margin-bottom: 6px;
		background: var(--bg-secondary, #1e293b);
		border: 1px solid var(--glass-border);
		border-radius: 8px;
		box-shadow: 0 8px 24px rgba(0, 0, 0, 0.4);
		overflow: hidden;
		z-index: 100;
	}
	.mention-row {
		display: flex;
		align-items: center;
		gap: 0.5rem;
		padding: 0.4rem 0.6rem;
		cursor: pointer;
		transition: background 0.1s;
		font-size: 0.75rem;
	}
	.mention-row:hover, .mention-row.active {
		background: var(--hover-tint, rgba(59, 130, 246, 0.15));
	}
	.mention-avatar {
		width: 20px;
		height: 20px;
		border-radius: 50%;
		background: var(--bg-tertiary);
		display: flex;
		align-items: center;
		justify-content: center;
		font-size: 0.6rem;
		font-weight: 800;
		color: var(--accent);
	}
	.mention-name { font-weight: 700; color: var(--text-main); }
	.mention-team { font-size: 0.65rem; color: var(--text-muted); }

	/* Lightbox */
	.lightbox-backdrop {
		position: fixed;
		inset: 0;
		background: rgba(0, 0, 0, 0.85);
		backdrop-filter: blur(6px);
		z-index: 9999;
		display: flex;
		align-items: center;
		justify-content: center;
		padding: 1.5rem;
	}
	.lightbox-content {
		position: relative;
		max-width: 90vw;
		max-height: 90vh;
	}
	.lightbox-img {
		max-width: 90vw;
		max-height: 85vh;
		border-radius: 8px;
		box-shadow: 0 10px 30px rgba(0, 0, 0, 0.6);
	}
	.lightbox-close-btn {
		position: absolute;
		top: -12px;
		right: -12px;
		background: #ef4444;
		color: white;
		border: none;
		width: 28px;
		height: 28px;
		border-radius: 50%;
		font-size: 0.8rem;
		font-weight: 900;
		cursor: pointer;
		display: flex;
		align-items: center;
		justify-content: center;
	}

	:global(.mention-tag) {
		color: #38bdf8;
		font-weight: 700;
	}
	:global(.chat-link) {
		color: #60a5fa;
		text-decoration: underline;
		word-break: break-all;
	}
</style>
