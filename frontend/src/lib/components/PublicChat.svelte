<script>
	import { onMount, onDestroy, tick, createEventDispatcher } from 'svelte';
	import { api } from '$lib/api';
	import { wsMessageStore } from '$lib/ws';
	import { t } from '$lib/i18nStore';
	import { EMOJI_CATALOG, EMOJI_CATEGORIES, DEFAULT_RECENT_EMOJIS } from '$lib/emojiCatalog';

	export let user = null;
	export let allUsers = [];

	const dispatch = createEventDispatcher();

	let messages = [];
	let chatConfig = {
		enabled: true,
		slowmode_seconds: 3,
		max_length: 250,
		block_duplicates: true,
		banned_words: [],
		ai_mention_enabled: true,
		ai_cooldown_seconds: 15
	};

	let textInput = '';
	let textareaEl = null;
	let chatScrollEl = null;
	let fileInputEl = null;

	let pendingImage = null;
	let pendingImagePreview = '';
	let isUploading = false;
	let isSending = false;

	let isScrolledUp = false;
	let unreadCountSinceScroll = 0;
	let isAutoScrolling = false;

	let lastReadMessageId = 0;
	let unreadDividerIndex = -1;
	let hasMoreEarlier = false;
	let isLoadingEarlier = false;

	let slowmodeRemaining = 0;
	let slowmodeInterval = null;

	let lightboxImageUrl = null;
	let showGifMenu = false;

	// Modern Chat Features State (Points 1, 2, 3, 5)
	let pinnedMessage = null; // { message, pinned_by, pinned_at }
	let replyingTo = null; // message object being replied to
	let recentEmojis = [...DEFAULT_RECENT_EMOJIS];
	let activeReactionMenuMsgId = null;
	let fullPickerMsgId = null;
	let emojiSearchQuery = '';
	let activeEmojiCategory = 'gaming';
	let soundEnabled = true;
	let audioCtx = null;
	let highlightedMessageId = null;
	let highlightTimer = null;

	// @mention autocomplete state
	let showMentionDropdown = false;
	let mentionQuery = '';
	let mentionCursorPos = 0;
	let selectedMentionIdx = 0;

	let wsUnsub = null;

	// Popular gaming reaction GIFs for quick picker
	const QUICK_GIFS = [
		{ name: 'GG', url: 'https://media.giphy.com/media/l4pTfx2qLszoacZRS/giphy.gif' },
		{ name: 'Hype', url: 'https://media.giphy.com/media/artj92V8o75VPL7AeQ/giphy.gif' },
		{ name: 'Popcorn', url: 'https://media.giphy.com/media/GLbiGvv9RiNpPdzyIN/giphy.gif' },
		{ name: 'EZ Clap', url: 'https://media.giphy.com/media/3o7TKSjRrfIPjeiVyM/giphy.gif' },
		{ name: 'Facepalm', url: 'https://media.giphy.com/media/WrNfErAnGV7mM/giphy.gif' },
		{ name: 'Mind Blown', url: 'https://media.giphy.com/media/26ufdipQqU2lhNA4g/giphy.gif' }
	];

	$: filteredMentions = (() => {
		if (!showMentionDropdown) return [];
		const q = mentionQuery.toLowerCase().trim();
		const list = [];
		// 1. Add Alanbix AI if enabled
		if (chatConfig.ai_mention_enabled && 'alanbix'.includes(q)) {
			list.push({ is_bot: true, username: 'Alanbix', avatar_url: '/favicon.svg' });
		}
		// 2. Add matching players
		(allUsers || []).forEach(u => {
			if (u.username && u.username.toLowerCase().includes(q) && u.id !== user?.id) {
				list.push({ is_bot: false, username: u.username, avatar_url: u.avatar_url, avatar_shape: u.avatar_shape, team_name: u.team_name, seat_id: u.seat_id });
			}
		});
		return list.slice(0, 7);
	})();

	$: if (selectedMentionIdx >= filteredMentions.length) {
		selectedMentionIdx = Math.max(0, filteredMentions.length - 1);
	}

	$: charCount = textInput.length;
	$: maxChars = chatConfig.max_length || 250;
	$: isOverLimit = charCount > maxChars;
	$: charGaugeColor = charCount >= maxChars ? '#ef4444' : charCount >= maxChars * 0.8 ? '#f59e0b' : 'var(--text-muted)';

	let messagesListEl = null;
	let resizeObserver = null;

	// Typing indicator state
	let typingUsers = {}; // key -> { username, is_bot, expiresAt }
	let userIsTyping = false;
	let lastTypingSentTime = 0;
	let typingDebounceTimer = null;
	let pruneTypersInterval = null;
	let currentPhraseIdx = 0;
	let phraseRotateInterval = null;

	const SINGULAR_PHRASE_KEYS = [
		'dash_chat_typing_singular_1',
		'dash_chat_typing_singular_2',
		'dash_chat_typing_singular_3',
		'dash_chat_typing_singular_4',
		'dash_chat_typing_singular_5',
		'dash_chat_typing_singular_6'
	];
	const PLURAL_PHRASE_KEYS = [
		'dash_chat_typing_plural_1',
		'dash_chat_typing_plural_2',
		'dash_chat_typing_plural_3',
		'dash_chat_typing_plural_4',
		'dash_chat_typing_plural_5',
		'dash_chat_typing_plural_6'
	];

	$: activeTypersList = Object.values(typingUsers);
	$: isTypingPlural = activeTypersList.length > 1;

	$: formattedTypersNames = (() => {
		const names = activeTypersList.map(u => u.username);
		if (names.length === 0) return '';
		if (names.length === 1) return names[0];
		const andWord = $t('dash_chat_typing_and') || 'et';
		if (names.length === 2) return `${names[0]} ${andWord} ${names[1]}`;
		return `${names.slice(0, -1).join(', ')} ${andWord} ${names[names.length - 1]}`;
	})();

	$: currentHumorousPhrase = $t(
		isTypingPlural ? PLURAL_PHRASE_KEYS[currentPhraseIdx] : SINGULAR_PHRASE_KEYS[currentPhraseIdx]
	);

	$: quickReactionList = (() => {
		const base = (recentEmojis && recentEmojis.length > 0) ? recentEmojis : DEFAULT_RECENT_EMOJIS;
		const merged = [...base];
		for (const d of DEFAULT_RECENT_EMOJIS) {
			if (!merged.includes(d)) merged.push(d);
		}
		return merged.slice(0, 4);
	})();

	$: filteredEmojisList = (() => {
		const q = emojiSearchQuery.toLowerCase().trim();
		if (q) {
			return EMOJI_CATALOG.filter(item =>
				item.emoji.toLowerCase().includes(q) ||
				item.name.toLowerCase().includes(q)
			);
		}
		if (activeEmojiCategory === 'recent') {
			return recentEmojis.map(emoji => {
				const found = EMOJI_CATALOG.find(e => e.emoji === emoji);
				return found || { emoji, name: emoji, cat: 'recent', isTag: emoji.length > 2 };
			});
		}
		if (activeEmojiCategory === 'all') {
			return EMOJI_CATALOG;
		}
		return EMOJI_CATALOG.filter(item => item.cat === activeEmojiCategory);
	})();

	onMount(async () => {
		// Load stored last read message ID
		const storedLastRead = localStorage.getItem('alanbix_last_read_chat_id');
		if (storedLastRead) {
			lastReadMessageId = parseInt(storedLastRead, 10) || 0;
		}

		// Load stored sound preference
		const storedSound = localStorage.getItem('alanbix_chat_sound_enabled');
		if (storedSound !== null) {
			soundEnabled = storedSound === 'true';
		}

		// Load stored recent emojis
		try {
			const storedRecent = localStorage.getItem('alanbix_recent_chat_emojis');
			if (storedRecent) {
				const parsed = JSON.parse(storedRecent);
				if (Array.isArray(parsed) && parsed.length > 0) {
					recentEmojis = parsed;
				}
			}
		} catch (e) {}

		await Promise.all([loadMessages(), loadConfig(), loadPinnedMessage()]);

		// ResizeObserver to keep auto-scroll locked to bottom when elements/images resize or splitter is dragged
		if (typeof ResizeObserver !== 'undefined' && messagesListEl) {
			resizeObserver = new ResizeObserver(() => {
				if (!isScrolledUp && chatScrollEl) {
					chatScrollEl.scrollTop = chatScrollEl.scrollHeight;
				}
			});
			resizeObserver.observe(messagesListEl);
		}

		// Prune expired typers every second
		pruneTypersInterval = setInterval(() => {
			const now = Date.now();
			let changed = false;
			const copy = { ...typingUsers };
			for (const [k, v] of Object.entries(copy)) {
				if (now > v.expiresAt) {
					delete copy[k];
					changed = true;
				}
			}
			if (changed) {
				if (Object.keys(copy).length === 0) {
					stopPhraseRotation();
				}
				typingUsers = copy;
			}
		}, 1000);

		// Setup WebSocket listener
		wsUnsub = wsMessageStore.subscribe(msg => {
			if (!msg) return;
			if (msg.type === 'public_chat_message' && msg.message) {
				handleIncomingMessage(msg.message);
				clearTyper(msg.message.is_bot ? 'bot_alanbix' : msg.message.user_id);
			} else if (msg.type === 'public_chat_typing') {
				handleTypingEvent(msg);
			} else if (msg.type === 'public_chat_message_deleted') {
				messages = messages.filter(m => m.id !== msg.message_id);
				if (pinnedMessage?.message?.id === msg.message_id) {
					pinnedMessage = null;
				}
			} else if (msg.type === 'public_chat_cleared') {
				messages = [];
				unreadCountSinceScroll = 0;
				unreadDividerIndex = -1;
				pinnedMessage = null;
			} else if (msg.type === 'public_chat_config_updated' && msg.config) {
				chatConfig = { ...chatConfig, ...msg.config };
			} else if (msg.type === 'public_chat_pinned_updated') {
				pinnedMessage = msg.pinned || null;
			} else if (msg.type === 'public_chat_reaction_updated') {
				const target = messages.find(m => m.id === msg.message_id);
				if (target) {
					target.reactions = msg.reactions || {};
					messages = [...messages];
				}
			}
		});
	});

	onDestroy(() => {
		stopPhraseRotation();
		if (resizeObserver) resizeObserver.disconnect();
		if (wsUnsub) wsUnsub();
		if (slowmodeInterval) clearInterval(slowmodeInterval);
		if (pruneTypersInterval) clearInterval(pruneTypersInterval);
		if (typingDebounceTimer) clearTimeout(typingDebounceTimer);
		if (highlightTimer) clearTimeout(highlightTimer);
		if (audioCtx) {
			try { audioCtx.close(); } catch (e) {}
		}
		if (userIsTyping) {
			api.post('/public-chat/typing', { is_typing: false }).catch(() => {});
		}
	});

	function startPhraseRotation() {
		if (!phraseRotateInterval) {
			currentPhraseIdx = Math.floor(Math.random() * SINGULAR_PHRASE_KEYS.length);
			phraseRotateInterval = setInterval(() => {
				currentPhraseIdx = (currentPhraseIdx + 1) % SINGULAR_PHRASE_KEYS.length;
			}, 6000);
		}
	}

	function stopPhraseRotation() {
		if (phraseRotateInterval) {
			clearInterval(phraseRotateInterval);
			phraseRotateInterval = null;
		}
	}

	function handleTypingEvent(data) {
		const isBot = !!data.is_bot;
		const key = isBot ? 'bot_alanbix' : String(data.user_id);

		// Don't show typing for self
		if (!isBot && user && data.user_id === user.id) return;

		const copy = { ...typingUsers };
		if (data.is_typing) {
			copy[key] = {
				username: data.username || (isBot ? 'Alanbix' : 'Joueur'),
				is_bot: isBot,
				expiresAt: Date.now() + 6000
			};
			startPhraseRotation();
		} else {
			delete copy[key];
			if (Object.keys(copy).length === 0) {
				stopPhraseRotation();
			}
		}
		typingUsers = copy;
	}

	function clearTyper(key) {
		if (key && typingUsers[key]) {
			const copy = { ...typingUsers };
			delete copy[key];
			if (Object.keys(copy).length === 0) {
				stopPhraseRotation();
			}
			typingUsers = copy;
		}
	}

	function onTypingActivity() {
		if (!chatConfig.enabled && !user?.is_admin) return;
		const now = Date.now();
		if (!userIsTyping || (now - lastTypingSentTime > 3000)) {
			userIsTyping = true;
			lastTypingSentTime = now;
			api.post('/public-chat/typing', { is_typing: true }).catch(() => {});
		}
		if (typingDebounceTimer) clearTimeout(typingDebounceTimer);
		typingDebounceTimer = setTimeout(() => {
			stopUserTyping();
		}, 3500);
	}

	function stopUserTyping() {
		if (typingDebounceTimer) {
			clearTimeout(typingDebounceTimer);
			typingDebounceTimer = null;
		}
		if (userIsTyping) {
			userIsTyping = false;
			api.post('/public-chat/typing', { is_typing: false }).catch(() => {});
		}
	}

	async function loadConfig() {
		try {
			const res = await api.get('/public-chat/config');
			if (res) chatConfig = { ...chatConfig, ...res };
		} catch (e) {
			console.error("Failed to load chat config:", e);
		}
	}

	async function loadMessages() {
		try {
			const res = await api.get('/public-chat/messages?limit=50');
			const loaded = res || [];
			loaded.forEach(m => {
				m._formattedContent = renderFormattedText(m.content);
			});
			messages = loaded;
			hasMoreEarlier = loaded.length >= 50;

			// Find unread divider position
			if (lastReadMessageId > 0 && messages.length > 0) {
				const firstUnreadIdx = messages.findIndex(m => m.id > lastReadMessageId && m.user_id !== user?.id);
				unreadDividerIndex = firstUnreadIdx;
			}

			isScrolledUp = false;
			unreadCountSinceScroll = 0;
			await tick();
			scrollToBottom(true);
			markAllRead();

			// Multi-pass alignments to account for async layout, font loading and CSS flexbox rendering
			requestAnimationFrame(() => {
				requestAnimationFrame(() => {
					if (!isScrolledUp && chatScrollEl) {
						chatScrollEl.scrollTop = chatScrollEl.scrollHeight;
					}
				});
			});
			setTimeout(() => {
				if (!isScrolledUp && chatScrollEl) {
					chatScrollEl.scrollTop = chatScrollEl.scrollHeight;
				}
			}, 60);
			setTimeout(() => {
				if (!isScrolledUp && chatScrollEl) {
					chatScrollEl.scrollTop = chatScrollEl.scrollHeight;
				}
			}, 200);
			setTimeout(() => {
				if (!isScrolledUp && chatScrollEl) {
					chatScrollEl.scrollTop = chatScrollEl.scrollHeight;
				}
			}, 500);
		} catch (e) {
			console.error("Failed to load public chat messages:", e);
		}
	}

	async function loadEarlierMessages() {
		if (isLoadingEarlier || !hasMoreEarlier || messages.length === 0) return;
		isLoadingEarlier = true;
		const oldestId = messages[0].id;
		const scrollEl = chatScrollEl;
		const prevScrollHeight = scrollEl ? scrollEl.scrollHeight : 0;
		const prevScrollTop = scrollEl ? scrollEl.scrollTop : 0;

		try {
			const res = await api.get(`/public-chat/messages?limit=50&before_id=${oldestId}`);
			const older = res || [];
			if (older.length < 50) {
				hasMoreEarlier = false;
			}
			if (older.length > 0) {
				older.forEach(m => {
					m._formattedContent = renderFormattedText(m.content);
				});
				if (unreadDividerIndex !== -1) {
					unreadDividerIndex += older.length;
				}
				messages = [...older, ...messages];

				await tick();
				if (scrollEl) {
					const heightDiff = scrollEl.scrollHeight - prevScrollHeight;
					scrollEl.scrollTop = prevScrollTop + heightDiff;
				}
			}
		} catch (e) {
			console.error("Failed to load earlier messages:", e);
		} finally {
			isLoadingEarlier = false;
		}
	}

	function handleIncomingMessage(newMsg) {
		// Avoid duplicate if already present
		if (messages.some(m => m.id === newMsg.id)) return;

		newMsg._formattedContent = renderFormattedText(newMsg.content);

		// DOM capping: if user is at bottom and buffer grows beyond 200 items, prune oldest to maintain 60 FPS
		if (!isScrolledUp && messages.length >= 200) {
			messages = [...messages.slice(messages.length - 150), newMsg];
			hasMoreEarlier = true;
			if (unreadDividerIndex !== -1) {
				unreadDividerIndex = Math.max(-1, unreadDividerIndex - 50);
			}
		} else {
			messages = [...messages, newMsg];
		}

		// Play notification chime if user is directly mentioned (Point 5)
		if (user && newMsg.user_id !== user.id && newMsg.mentions?.user_ids?.includes(user.id)) {
			playMentionChime();
		}

		// If user is scrolled up and it's not their own message, increment unread counter
		if (isScrolledUp && newMsg.user_id !== user?.id) {
			unreadCountSinceScroll++;
		} else {
			// Auto scroll to bottom
			tick().then(() => scrollToBottom(false));
			markAllRead();
		}
	}

	function markAllRead() {
		if (messages.length > 0) {
			const latestId = messages[messages.length - 1].id;
			lastReadMessageId = latestId;
			localStorage.setItem('alanbix_last_read_chat_id', String(latestId));
		}
	}

	function handleScroll() {
		if (!chatScrollEl || isAutoScrolling) return;
		const { scrollTop, scrollHeight, clientHeight } = chatScrollEl;
		const distanceToBottom = scrollHeight - (scrollTop + clientHeight);

		if (distanceToBottom > 60) {
			isScrolledUp = true;
		} else {
			isScrolledUp = false;
			unreadCountSinceScroll = 0;
			markAllRead();
		}

		// Infinite backward scroll: automatically load earlier history when reaching top
		if (scrollTop < 30 && hasMoreEarlier && !isLoadingEarlier) {
			loadEarlierMessages();
		}
	}

	async function scrollToBottom(instant = false) {
		if (!chatScrollEl) return;
		isAutoScrolling = true;
		await tick();
		if (instant) {
			chatScrollEl.scrollTop = chatScrollEl.scrollHeight;
			isScrolledUp = false;
			unreadCountSinceScroll = 0;
			isAutoScrolling = false;
		} else {
			chatScrollEl.scrollTo({
				top: chatScrollEl.scrollHeight,
				behavior: 'smooth'
			});
			setTimeout(() => {
				isAutoScrolling = false;
				isScrolledUp = false;
				unreadCountSinceScroll = 0;
			}, 250);
		}
	}

	function handleKeydown(e) {
		// Mention dropdown navigation
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
				applyMention(filteredMentions[selectedMentionIdx]);
				return;
			}
			if (e.key === 'Escape') {
				e.preventDefault();
				showMentionDropdown = false;
				return;
			}
		}

		if (e.key === 'Escape' && replyingTo) {
			e.preventDefault();
			cancelReply();
			return;
		}

		// Send on Enter (without Shift)
		if (e.key === 'Enter' && !e.shiftKey) {
			e.preventDefault();
			handleSend();
		}
	}

	function handleInput(e) {
		// Auto resize textarea height
		if (textareaEl) {
			textareaEl.style.height = 'auto';
			textareaEl.style.height = Math.min(textareaEl.scrollHeight, 100) + 'px';
		}

		// Detect @ mention trigger
		const text = textInput;
		const cursor = textareaEl ? textareaEl.selectionStart : text.length;
		const beforeCursor = text.slice(0, cursor);
		const lastAtIdx = beforeCursor.lastIndexOf('@');

		if (lastAtIdx !== -1 && (lastAtIdx === 0 || /\s/.test(beforeCursor[lastAtIdx - 1]))) {
			const query = beforeCursor.slice(lastAtIdx + 1);
			if (!/\s/.test(query)) {
				showMentionDropdown = true;
				mentionQuery = query;
				mentionCursorPos = lastAtIdx;
				return;
			}
		}

		showMentionDropdown = false;

		// Typing indicator emission
		if (textInput.trim().length > 0) {
			onTypingActivity();
		} else if (userIsTyping) {
			stopUserTyping();
		}
	}

	function applyMention(m) {
		if (!m) return;
		const prefix = textInput.slice(0, mentionCursorPos);
		const after = textInput.slice(textareaEl ? textareaEl.selectionStart : mentionCursorPos + mentionQuery.length + 1);
		const inserted = `@${m.username} `;
		textInput = prefix + inserted + after;
		showMentionDropdown = false;

		tick().then(() => {
			if (textareaEl) {
				const nextPos = prefix.length + inserted.length;
				textareaEl.focus();
				textareaEl.setSelectionRange(nextPos, nextPos);
			}
		});
	}

	function handlePaste(e) {
		const items = e.clipboardData?.items;
		if (!items) return;
		for (const item of items) {
			if (item.type.startsWith('image/')) {
				e.preventDefault();
				const file = item.getAsFile();
				if (file) attachImage(file);
				break;
			}
		}
	}

	function handleFileSelect(e) {
		const file = e.target.files?.[0];
		if (file) attachImage(file);
		if (fileInputEl) fileInputEl.value = '';
	}

	function attachImage(file) {
		if (file.size > 8 * 1024 * 1024) {
			alert("L'image est trop volumineuse (maximum 8 Mo).");
			return;
		}
		pendingImage = file;
		const reader = new FileReader();
		reader.onload = (e) => { pendingImagePreview = e.target.result; };
		reader.readAsDataURL(file);
	}

	function removePendingImage() {
		pendingImage = null;
		pendingImagePreview = '';
	}

	function selectQuickGif(gifUrl) {
		textInput = (textInput ? textInput + ' ' : '') + gifUrl;
		showGifMenu = false;
		if (textareaEl) textareaEl.focus();
	}

	function startSlowmodeCooldown(seconds) {
		slowmodeRemaining = seconds;
		if (slowmodeInterval) clearInterval(slowmodeInterval);
		slowmodeInterval = setInterval(() => {
			slowmodeRemaining -= 1;
			if (slowmodeRemaining <= 0) {
				clearInterval(slowmodeInterval);
				slowmodeRemaining = 0;
			}
		}, 1000);
	}

	async function handleSend() {
		if (isSending || slowmodeRemaining > 0) return;
		const text = textInput.trim();
		if (!text && !pendingImage) return;

		if (text.length > maxChars) return;

		stopUserTyping();
		isSending = true;

		const sentText = text;
		const sentImage = pendingImage;
		const replyToId = replyingTo ? replyingTo.id : null;
		replyingTo = null;

		// Optimistic clear for immediate responsiveness
		textInput = '';
		if (textareaEl) {
			textareaEl.style.height = 'auto';
		}

		try {
			let imagePath = null;
			if (sentImage) {
				isUploading = true;
				const formData = new FormData();
				formData.append('file', sentImage);
				const uploadRes = await api.upload('/public-chat/upload-image', formData);
				imagePath = uploadRes.image_path;
				isUploading = false;
				removePendingImage();
			}

			await api.post('/public-chat/messages', {
				content: sentText,
				image_path: imagePath,
				reply_to_id: replyToId
			});

			// Apply slowmode cooldown
			if (!user?.is_admin && chatConfig.slowmode_seconds > 0) {
				startSlowmodeCooldown(chatConfig.slowmode_seconds);
			}

			unreadDividerIndex = -1;
			await tick();
			scrollToBottom(false);
		} catch (e) {
			// Restore text if error
			textInput = sentText;
			alert(e.message || "Erreur lors de l'envoi du message.");
		} finally {
			isSending = false;
			isUploading = false;
		}
	}

	async function deleteMessage(msgId) {
		if (!confirm($t('dash_chat_delete_confirm') || 'Supprimer ce message ?')) return;
		try {
			await api.delete(`/public-chat/messages/${msgId}`);
		} catch (e) {
			alert(e.message || "Erreur de suppression.");
		}
	}

	async function clearAllChat() {
		if (!confirm($t('dash_chat_clear_confirm') || 'Effacer tout l\'historique du chat ?')) return;
		try {
			await api.post('/public-chat/clear', {});
		} catch (e) {
			alert(e.message || "Erreur lors de la purge.");
		}
	}

	// =========================================================================
	// Point 5: Sound Notifications (Web Audio API - 100% Offline / Rule G-17)
	// =========================================================================
	function initAudio() {
		if (!audioCtx && typeof window !== 'undefined') {
			const AudioContextClass = window.AudioContext || window.webkitAudioContext;
			if (AudioContextClass) {
				audioCtx = new AudioContextClass();
			}
		}
	}

	function playMentionChime() {
		if (!soundEnabled) return;
		try {
			initAudio();
			if (!audioCtx) return;
			if (audioCtx.state === 'suspended') {
				audioCtx.resume();
			}
			const now = audioCtx.currentTime;
			const osc = audioCtx.createOscillator();
			const gain = audioCtx.createGain();

			osc.type = 'sine';
			osc.frequency.setValueAtTime(523.25, now); // C5
			osc.frequency.setValueAtTime(783.99, now + 0.06); // G5

			gain.gain.setValueAtTime(0.001, now);
			gain.gain.exponentialRampToValueAtTime(0.12, now + 0.02);
			gain.gain.exponentialRampToValueAtTime(0.06, now + 0.07);
			gain.gain.exponentialRampToValueAtTime(0.0001, now + 0.22);

			osc.connect(gain);
			gain.connect(audioCtx.destination);

			osc.start(now);
			osc.stop(now + 0.24);
		} catch (e) {
			console.warn("Could not play mention chime:", e);
		}
	}

	function toggleSound() {
		soundEnabled = !soundEnabled;
		localStorage.setItem('alanbix_chat_sound_enabled', String(soundEnabled));
		if (soundEnabled) {
			playMentionChime();
		}
	}

	// =========================================================================
	// Point 3: Pinned Message / Admin Announcements
	// =========================================================================
	async function loadPinnedMessage() {
		try {
			const res = await api.get('/public-chat/pinned');
			pinnedMessage = res?.pinned || null;
		} catch (e) {
			console.error("Failed to load pinned message:", e);
		}
	}

	async function pinMessage(msgId) {
		try {
			// If clicking on already pinned message, unpin it
			const targetId = pinnedMessage?.message?.id === msgId ? null : msgId;
			const res = await api.post('/public-chat/pin', { message_id: targetId });
			pinnedMessage = res?.pinned || null;
		} catch (e) {
			alert(e.message || "Erreur lors de l'épinglage.");
		}
	}

	async function unpinMessage() {
		try {
			await api.post('/public-chat/pin', { message_id: null });
			pinnedMessage = null;
		} catch (e) {
			alert(e.message || "Erreur lors du désépinglage.");
		}
	}

	// =========================================================================
	// Point 2: Reply / Quote & Target Highlight Navigation
	// =========================================================================
	function startReply(msg) {
		replyingTo = msg;
		activeReactionMenuMsgId = null;
		tick().then(() => {
			if (textareaEl) {
				textareaEl.focus();
			}
		});
	}

	function cancelReply() {
		replyingTo = null;
	}

	async function scrollToAndHighlightMessage(targetId) {
		if (!targetId) return;
		let targetEl = document.getElementById(`public-chat-msg-${targetId}`);
		if (!targetEl && hasMoreEarlier) {
			let attempts = 0;
			while (!targetEl && hasMoreEarlier && attempts < 4) {
				attempts++;
				await loadEarlierMessages();
				await tick();
				targetEl = document.getElementById(`public-chat-msg-${targetId}`);
			}
		}
		if (targetEl) {
			targetEl.scrollIntoView({ behavior: 'smooth', block: 'center' });
			highlightedMessageId = targetId;
			if (highlightTimer) clearTimeout(highlightTimer);
			highlightTimer = setTimeout(() => {
				highlightedMessageId = null;
			}, 2000);
		}
	}

	// =========================================================================
	// Point 1: Emoji Reactions (Toggle & Display)
	// =========================================================================
	async function toggleReaction(msgId, emoji) {
		if (!user) return;
		activeReactionMenuMsgId = null;

		// Optimistic UI update for immediate responsiveness
		const targetMsg = messages.find(m => m.id === msgId);
		if (targetMsg) {
			const reactions = { ...(targetMsg.reactions || {}) };
			const userList = [...(reactions[emoji] || [])];
			const idx = userList.indexOf(user.id);
			if (idx !== -1) {
				userList.splice(idx, 1);
				if (userList.length === 0) {
					delete reactions[emoji];
				} else {
					reactions[emoji] = userList;
				}
			} else {
				userList.push(user.id);
				reactions[emoji] = userList;
			}
			targetMsg.reactions = reactions;
			messages = [...messages];
		}

		try {
			const res = await api.post(`/public-chat/messages/${msgId}/react`, { emoji });
			if (res && res.reactions && targetMsg) {
				targetMsg.reactions = res.reactions;
				messages = [...messages];
			}
		} catch (e) {
			console.error("Failed to react to message:", e);
		}
	}

	function getReactionUsernames(userIdList) {
		if (!userIdList || userIdList.length === 0) return '';
		return userIdList
			.map(id => {
				if (user && id === user.id) return 'Vous';
				const found = (allUsers || []).find(u => u.id === id);
				return found?.username || `Joueur #${id}`;
			})
			.join(', ');
	}

	function updateRecentEmojis(emoji) {
		if (!emoji) return;
		const filtered = recentEmojis.filter(e => e !== emoji);
		recentEmojis = [emoji, ...filtered].slice(0, 20);
		try {
			localStorage.setItem('alanbix_recent_chat_emojis', JSON.stringify(recentEmojis));
		} catch (e) {}
	}

	function onSelectEmoji(msgId, emoji) {
		toggleReaction(msgId, emoji);
		updateRecentEmojis(emoji);
		activeReactionMenuMsgId = null;
		fullPickerMsgId = null;
	}

	function toggleQuickReactionMenu(msgId) {
		if (activeReactionMenuMsgId === msgId || fullPickerMsgId === msgId) {
			activeReactionMenuMsgId = null;
			fullPickerMsgId = null;
		} else {
			activeReactionMenuMsgId = msgId;
			fullPickerMsgId = null;
		}
	}

	function openFullEmojiPicker(msgId) {
		activeReactionMenuMsgId = null;
		fullPickerMsgId = msgId;
		emojiSearchQuery = '';
		activeEmojiCategory = 'gaming';
	}

	function closeAllEmojiPopovers() {
		activeReactionMenuMsgId = null;
		fullPickerMsgId = null;
	}

	function handleWindowClick() {
		closeAllEmojiPopovers();
		showGifMenu = false;
		showMentionDropdown = false;
	}

	function formatTime(isoStr) {
		if (!isoStr) return '';
		try {
			const d = new Date(isoStr);
			return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
		} catch {
			return '';
		}
	}

	function renderFormattedText(text) {
		if (!text) return '';
		// Replace URLs with clickable safe links
		const escaped = text
			.replace(/&/g, '&amp;')
			.replace(/</g, '&lt;')
			.replace(/>/g, '&gt;');

		// Highlight @mentions
		const withMentions = escaped.replace(/@([a-zA-Z0-9_-]+)/g, (match, handle) => {
			const isMe = user && handle.toLowerCase() === user.username?.toLowerCase();
			const isAlanbix = handle.toLowerCase() === 'alanbix';
			const cls = isAlanbix ? 'mention-alanbix' : isMe ? 'mention-me' : 'mention-user';
			return `<span class="mention-chip ${cls}">@${handle}</span>`;
		});

		// Turn URLs into clickable links
		const urlRegex = /(https?:\/\/[^\s]+)/g;
		return withMentions.replace(urlRegex, (url) => {
			// If it is a direct gif/image url, show indicator
			const isImg = /\.(gif|png|jpg|jpeg|webp)(\?.*)?$/i.test(url) || url.includes('giphy.com') || url.includes('tenor.com');
			return `<a href="${url}" target="_blank" rel="noopener noreferrer" class="chat-link ${isImg ? 'media-link' : ''}">${url}</a>`;
		});
	}

	function onMessageHover(msg) {
		if (msg.seat_id) {
			dispatch('seatHover', msg.seat_id);
		}
	}

	function onMessageLeave(msg) {
		if (msg.seat_id) {
			dispatch('seatLeave', msg.seat_id);
		}
	}
</script>

<svelte:window on:click={handleWindowClick} />

<div class="public-chat-card glass">
	<!-- Header -->
	<header class="chat-header">
		<div class="header-left">
			<div class="chat-live-pulse"></div>
			<span class="chat-title title-premium">{$t('dash_chat_title')}</span>
			{#if !chatConfig.enabled}
				<span class="chat-disabled-badge">{$t('dash_chat_disabled_badge')}</span>
			{/if}
			{#if chatConfig.slowmode_seconds > 0}
				<span class="chat-slowmode-indicator" title="Slowmode">⏱️ {chatConfig.slowmode_seconds}s</span>
			{/if}
		</div>
		<div class="header-right">
			<!-- Sound Toggle Button (Point 5) -->
			<button
				class="chat-btn-icon-sound {soundEnabled ? 'sound-active' : 'sound-muted'}"
				on:click={toggleSound}
				title={soundEnabled ? $t('dash_chat_sound_enabled') : $t('dash_chat_sound_disabled')}
			>
				{soundEnabled ? '🔔' : '🔕'}
			</button>

			{#if user?.is_admin}
				<button class="chat-btn-icon-danger" on:click={clearAllChat} title="Purger le chat (Admin)">
					<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M3 6h18M19 6v14a2 2 0 01-2 2H7a2 2 0 01-2-2V6m3 0V4a2 2 0 012-2h4a2 2 0 012 2v2M10 11v6M14 11v6"/></svg>
				</button>
			{/if}
		</div>
	</header>

	<!-- Pinned Announcement Banner (Point 3) -->
	{#if pinnedMessage && pinnedMessage.message}
		<div class="chat-pinned-banner">
			<!-- svelte-ignore a11y-click-events-have-key-events -->
			<div class="pinned-banner-content" on:click={() => scrollToAndHighlightMessage(pinnedMessage.message.id)}>
				<span class="pinned-pin-icon">📌</span>
				<div class="pinned-text-wrap">
					<div class="pinned-header-line">
						<span class="pinned-badge-tag">{$t('dash_chat_pinned_title')}</span>
						<span class="pinned-author-name">{pinnedMessage.message.username || pinnedMessage.message.sender_name || 'Anonyme'}</span>
					</div>
					<div class="pinned-message-preview">{pinnedMessage.message.content || (pinnedMessage.message.image_path ? 'Pièce jointe' : '')}</div>
				</div>
			</div>
			<div class="pinned-banner-actions">
				<button
					class="pinned-action-btn"
					on:click={() => scrollToAndHighlightMessage(pinnedMessage.message.id)}
					title="Voir dans le chat"
				>
					↗
				</button>
				{#if user?.is_admin}
					<button
						class="pinned-action-btn btn-unpin"
						on:click={unpinMessage}
						title={$t('dash_chat_unpin_action')}
					>
						✕
					</button>
				{/if}
			</div>
		</div>
	{/if}

	<!-- Messages Scroll View -->
	<div class="chat-scroll-container" bind:this={chatScrollEl} on:scroll={handleScroll}>
		<div class="chat-messages-inner" bind:this={messagesListEl}>
			{#if messages.length === 0}
				<div class="chat-empty-state">
					<span class="empty-icon">💬</span>
					<p>{$t('dash_chat_empty')}</p>
				</div>
			{:else}
				{#if hasMoreEarlier}
					<div class="load-earlier-container">
						<button
							class="btn-load-earlier"
							on:click={loadEarlierMessages}
							disabled={isLoadingEarlier}
							title="Charger les messages plus anciens"
						>
							{#if isLoadingEarlier}
								<span class="mini-spinner"></span>
								<span>{$t('dash_chat_loading_earlier') || 'Chargement...'}</span>
							{:else}
								<span>↑ {$t('dash_chat_load_earlier') || 'Charger les messages précédents'}</span>
							{/if}
						</button>
					</div>
				{/if}

				{#each messages as msg, idx (msg.id)}
					<!-- Unread Divider Line -->
					{#if idx === unreadDividerIndex}
						<div class="unread-divider">
							<span class="divider-line"></span>
							<span class="divider-badge">🔴 {$t('dash_chat_unread_divider')}</span>
							<span class="divider-line"></span>
						</div>
					{/if}

					<!-- Chat Message Row -->
					<!-- svelte-ignore a11y-mouse-events-have-key-events -->
					<div
						id="public-chat-msg-{msg.id}"
						class="chat-msg-row {msg.is_bot ? 'is-bot' : ''} {user && msg.mentions?.user_ids?.includes(user.id) ? 'is-mentioned' : ''} {user && msg.user_id === user.id ? 'is-mine' : ''} {highlightedMessageId === msg.id ? 'is-highlighted' : ''}"
						on:mouseenter={() => onMessageHover(msg)}
						on:mouseleave={() => onMessageLeave(msg)}
					>
						<!-- Message Hover Action Bar (Points 1, 2, 3) -->
						<div class="msg-action-bar {activeReactionMenuMsgId === msg.id || fullPickerMsgId === msg.id ? 'has-active-popover' : ''}">
							<button
								class="msg-action-btn"
								on:click|stopPropagation={() => toggleQuickReactionMenu(msg.id)}
								title={$t('dash_chat_react_action')}
							>
								🙂+
							</button>
							<button
								class="msg-action-btn"
								on:click|stopPropagation={() => startReply(msg)}
								title={$t('dash_chat_reply_action')}
							>
								↩️
							</button>
							{#if user?.is_admin}
								<button
									class="msg-action-btn {pinnedMessage?.message?.id === msg.id ? 'active-pin' : ''}"
									on:click|stopPropagation={() => pinMessage(msg.id)}
									title={pinnedMessage?.message?.id === msg.id ? $t('dash_chat_unpin_action') : $t('dash_chat_pin_action')}
								>
									📌
								</button>
								<button
									class="msg-action-btn btn-danger-action"
									on:click|stopPropagation={() => deleteMessage(msg.id)}
									title={$t('dash_chat_delete_tooltip')}
								>
									🗑️
								</button>
							{/if}

							<!-- Quick Reactions Popover (Point 1) -->
							{#if activeReactionMenuMsgId === msg.id}
								<div class="quick-reactions-popover {idx < 3 ? 'popover-down' : 'popover-up'}" on:click|stopPropagation>
									{#each quickReactionList as emoji}
										<button
											class="reaction-pick-emoji {emoji.length > 2 ? 'is-text-tag' : ''}"
											on:click|stopPropagation={() => onSelectEmoji(msg.id, emoji)}
											title={emoji}
										>
											{emoji}
										</button>
									{/each}
									<span class="quick-divider"></span>
									<button
										class="reaction-pick-more-btn"
										on:click|stopPropagation={() => openFullEmojiPicker(msg.id)}
										title={$t('dash_chat_all_emojis')}
									>
										➕
									</button>
								</div>
							{/if}

							<!-- Full Standard Emoji Picker Popover -->
							{#if fullPickerMsgId === msg.id}
								<div class="full-emoji-picker {idx < 3 ? 'popover-down' : 'popover-up'}" on:click|stopPropagation>
									<!-- Search Bar -->
									<div class="picker-search-bar">
										<span class="picker-search-icon">🔍</span>
										<input
											type="text"
											class="picker-search-input"
											placeholder={$t('dash_chat_search_emojis')}
											bind:value={emojiSearchQuery}
											on:click|stopPropagation
										/>
										{#if emojiSearchQuery}
											<button class="picker-clear-search" on:click|stopPropagation={() => emojiSearchQuery = ''}>✕</button>
										{/if}
									</div>

									<!-- Category Navigation Tabs -->
									<div class="picker-cat-tabs">
										{#each EMOJI_CATEGORIES as cat}
											<button
												class="cat-tab {activeEmojiCategory === cat.id ? 'active' : ''}"
												on:click|stopPropagation={() => activeEmojiCategory = cat.id}
												title={$t(cat.labelKey)}
											>
												{cat.icon}
											</button>
										{/each}
									</div>

									<!-- Scrollable Emojis & Tags Grid -->
									<div class="picker-emojis-scroll">
										{#if filteredEmojisList.length === 0}
											<div class="picker-empty-state">
												<span class="picker-empty-icon">🕵️</span>
												<p>{$t('dash_chat_no_emojis_found')}</p>
											</div>
										{:else}
											<div class="picker-emojis-grid">
												{#each filteredEmojisList as item}
													<button
														class="grid-emoji-btn {item.isTag ? 'is-text-tag' : ''}"
														on:click|stopPropagation={() => onSelectEmoji(msg.id, item.emoji)}
														title={item.name}
													>
														{item.emoji}
													</button>
												{/each}
											</div>
										{/if}
									</div>
								</div>
							{/if}
						</div>

						<!-- Avatar -->
						<div class="msg-avatar avatar-shape-{msg.avatar_shape || 'circle'} {msg.is_bot ? 'bot-avatar' : ''}">
							{#if msg.is_bot}
								<span class="bot-icon">🤖</span>
							{:else if msg.avatar_url}
								<img src={msg.avatar_url} alt="" class="avatar-img" />
							{:else}
								{(msg.username || '?')[0].toUpperCase()}
							{/if}
						</div>

						<!-- Content Container -->
						<div class="msg-content-wrapper">
							<div class="msg-header">
								<span class="msg-author {msg.is_bot ? 'bot-author' : ''}">
									{msg.username || msg.sender_name || 'Anonyme'}
								</span>
								{#if msg.is_bot}
									<span class="bot-badge">{$t('dash_chat_bot_badge')}</span>
								{/if}
								{#if msg.team_name}
									<span class="team-tag">{msg.team_name}</span>
								{/if}
								{#if msg.seat_id}
									<span class="seat-tag" title="Emplacement salle">💺 {msg.seat_id}</span>
								{/if}
								<span class="msg-time">{formatTime(msg.created_at)}</span>
							</div>

							<!-- Quoted Message (Point 2) -->
							{#if msg.reply_to}
								<!-- svelte-ignore a11y-click-events-have-key-events -->
								<div
									class="msg-reply-quote"
									on:click|stopPropagation={() => scrollToAndHighlightMessage(msg.reply_to.id)}
									title="Voir le message original"
								>
									<span class="quote-symbol">↩️</span>
									<strong class="quote-author">@{msg.reply_to.username}</strong>
									<span class="quote-snippet">{msg.reply_to.content}</span>
								</div>
							{/if}

							<!-- Text Content -->
							{#if msg.content}
								<div class="msg-text">
									{@html msg._formattedContent !== undefined ? msg._formattedContent : renderFormattedText(msg.content)}
								</div>
							{/if}

							<!-- Attached Image / GIF -->
							{#if msg.image_path}
								<!-- svelte-ignore a11y-click-events-have-key-events -->
								<div class="msg-image-attachment" on:click={() => lightboxImageUrl = msg.image_path}>
									<img src={msg.image_path} alt="Pièce jointe" loading="lazy" on:load={() => { if (!isScrolledUp && chatScrollEl) chatScrollEl.scrollTop = chatScrollEl.scrollHeight; }} />
									<span class="zoom-indicator">🔍</span>
								</div>
							{/if}

							<!-- Rich OpenGraph Link Preview -->
							{#if msg.link_preview}
								<a href={msg.link_preview.url} target="_blank" rel="noopener noreferrer" class="link-preview-card glass-hover">
									{#if msg.link_preview.image}
										<img src={msg.link_preview.image} alt="" class="lp-thumb" loading="lazy" on:load={() => { if (!isScrolledUp && chatScrollEl) chatScrollEl.scrollTop = chatScrollEl.scrollHeight; }} />
									{/if}
									<div class="lp-info">
										<span class="lp-domain">{msg.link_preview.domain}</span>
										<span class="lp-title">{msg.link_preview.title}</span>
										{#if msg.link_preview.description}
											<span class="lp-desc">{msg.link_preview.description}</span>
										{/if}
									</div>
								</a>
							{/if}

							<!-- Reaction Pills (Point 1) -->
							{#if msg.reactions && Object.keys(msg.reactions).length > 0}
								<div class="msg-reactions-container">
									{#each Object.entries(msg.reactions) as [emoji, userIds]}
										{#if userIds && userIds.length > 0}
											<button
												class="reaction-pill {user && userIds.includes(user.id) ? 'reacted-by-user' : ''} {emoji.length > 2 ? 'is-text-tag' : ''}"
												on:click|stopPropagation={() => onSelectEmoji(msg.id, emoji)}
												title={getReactionUsernames(userIds)}
											>
												<span class="reaction-emoji">{emoji}</span>
												<span class="reaction-count">{userIds.length}</span>
											</button>
										{/if}
									{/each}
								</div>
							{/if}
						</div>
					</div>
				{/each}
			{/if}
		</div>
	</div>

	<!-- Floating Jump to Latest Button -->
	{#if isScrolledUp}
		<button class="jump-latest-pill" on:click={() => scrollToBottom(false)}>
			<span>↓</span>
			<span>{$t('dash_chat_jump_latest')}</span>
			{#if unreadCountSinceScroll > 0}
				<span class="unread-pill-count">{unreadCountSinceScroll}</span>
			{/if}
		</button>
	{/if}

	<!-- Mention Autocomplete Popover -->
	{#if showMentionDropdown && filteredMentions.length > 0}
		<div class="mention-dropdown glass">
			{#each filteredMentions as m, idx}
				<!-- svelte-ignore a11y-click-events-have-key-events -->
				<div
					class="mention-item {idx === selectedMentionIdx ? 'selected' : ''}"
					on:mousedown|preventDefault={() => applyMention(m)}
				>
					{#if m.is_bot}
						<span class="m-avatar bot-av">🤖</span>
					{:else if m.avatar_url}
						<img src={m.avatar_url} alt="" class="m-avatar avatar-shape-{m.avatar_shape || 'circle'}" />
					{:else}
						<div class="m-avatar m-avatar-fallback">{(m.username || '?')[0].toUpperCase()}</div>
					{/if}
					<span class="m-name">{m.username}</span>
					{#if m.is_bot}
						<span class="m-sub bot-sub">Mascotte IA</span>
					{:else if m.team_name}
						<span class="m-sub">{m.team_name}</span>
					{/if}
				</div>
			{/each}
		</div>
	{/if}

	<!-- GIF Picker Popover -->
	{#if showGifMenu}
		<div class="gif-picker-popover glass">
			<div class="gif-grid">
				{#each QUICK_GIFS as g}
					<!-- svelte-ignore a11y-click-events-have-key-events -->
					<button class="gif-chip" on:click={() => selectQuickGif(g.url)}>
						<img src={g.url} alt={g.name} loading="lazy" />
						<span>{g.name}</span>
					</button>
				{/each}
			</div>
		</div>
	{/if}

	<!-- Pending Image Preview Bar -->
	{#if pendingImagePreview}
		<div class="pending-preview-bar">
			<div class="preview-thumb-box">
				<img src={pendingImagePreview} alt="Aperçu" />
				<button class="remove-preview-btn" on:click={removePendingImage} title="Supprimer">✕</button>
			</div>
			<span class="preview-label">{pendingImage?.name || 'Image prête à l\'envoi'}</span>
		</div>
	{/if}

	<!-- Active Typers Indicator Bar -->
	{#if activeTypersList.length > 0}
		<div class="chat-typing-bar">
			<div class="typing-dots-anim">
				<span class="t-dot"></span>
				<span class="t-dot"></span>
				<span class="t-dot"></span>
			</div>
			<div class="typing-text-wrapper">
				<span class="typers-highlight">{formattedTypersNames}</span>
				<span class="typing-ellipsis">…</span>
				<span class="typing-humor-phrase">{currentHumorousPhrase}</span>
			</div>
		</div>
	{/if}

	<!-- Replying To Preview Bar (Point 2) -->
	{#if replyingTo}
		<div class="replying-preview-bar">
			<div class="replying-content">
				<span class="replying-icon">↩️</span>
				<div class="replying-text-group">
					<span class="replying-lead">
						{$t('dash_chat_replying_to')}
						<strong>@{replyingTo.username || replyingTo.sender_name || 'Anonyme'}</strong>
					</span>
					<span class="replying-snippet">{replyingTo.content || (replyingTo.image_path ? 'Pièce jointe' : '')}</span>
				</div>
			</div>
			<button class="replying-cancel-btn" on:click={cancelReply} title={$t('dash_chat_cancel_reply')}>✕</button>
		</div>
	{/if}

	<!-- Input Footer Bar -->
	<footer class="chat-input-bar">
		<input type="file" accept="image/*" bind:this={fileInputEl} on:change={handleFileSelect} style="display:none;" />

		<!-- Attach Media Button -->
		<button class="btn-action-icon" on:click={() => fileInputEl?.click()} title="{$t('dash_chat_attach_tooltip')}">
			📎
		</button>

		<!-- GIF Button -->
		<button class="btn-action-icon gif-btn" on:click={() => showGifMenu = !showGifMenu} title="{$t('dash_chat_gif_tooltip')}">
			GIF
		</button>

		<!-- Textarea -->
		<div class="textarea-wrapper">
			<textarea
				bind:this={textareaEl}
				bind:value={textInput}
				on:keydown={handleKeydown}
				on:input={handleInput}
				on:paste={handlePaste}
				placeholder={!chatConfig.enabled ? (user?.is_admin ? $t('dash_chat_disabled_admin_hint') : $t('dash_chat_disabled_msg')) : $t('dash_chat_placeholder')}
				disabled={!chatConfig.enabled && !user?.is_admin}
				rows="1"
				maxlength={maxChars + 10}
			></textarea>
			<span class="char-counter" style="color: {charGaugeColor}">
				{charCount}/{maxChars}
			</span>
		</div>

		<!-- Send Button -->
		<button
			class="btn-send-chat {slowmodeRemaining > 0 ? 'slowmode-locked' : ''}"
			on:click={handleSend}
			disabled={isSending || isUploading || isOverLimit || (!textInput.trim() && !pendingImage) || (!chatConfig.enabled && !user?.is_admin)}
		>
			{#if isUploading}
				<span class="mini-spinner"></span>
			{:else if slowmodeRemaining > 0}
				<span class="slowmode-countdown">{slowmodeRemaining}s</span>
			{:else}
				<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M22 2L11 13M22 2l-7 20-4-9-9-4 20-7z"/></svg>
			{/if}
		</button>
	</footer>
</div>

<!-- Lightbox Modal -->
{#if lightboxImageUrl}
	<!-- svelte-ignore a11y-click-events-have-key-events -->
	<div class="lightbox-overlay" on:click={() => lightboxImageUrl = null}>
		<div class="lightbox-container" on:click|stopPropagation>
			<img src={lightboxImageUrl} alt="Agrandissement" class="lightbox-img" />
			<button class="lightbox-close" on:click={() => lightboxImageUrl = null}>✕</button>
		</div>
	</div>
{/if}

<style>
	.public-chat-card {
		display: flex;
		flex-direction: column;
		height: 100%;
		border-radius: 16px;
		overflow: hidden;
		min-height: 0;
		position: relative;
	}

	.chat-header {
		display: flex;
		justify-content: space-between;
		align-items: center;
		padding: 0.65rem 1rem;
		border-bottom: 1px solid var(--glass-border);
		background: var(--surface-sunken);
		flex-shrink: 0;
	}

	.header-left {
		display: flex;
		align-items: center;
		gap: 0.5rem;
	}

	.chat-live-pulse {
		width: 8px;
		height: 8px;
		border-radius: 50%;
		background: #10b981;
		box-shadow: 0 0 8px #10b981;
		animation: livePulse 2s infinite ease-in-out;
	}
	@keyframes livePulse {
		0%, 100% { opacity: 0.6; transform: scale(0.9); }
		50% { opacity: 1; transform: scale(1.15); box-shadow: 0 0 12px #10b981; }
	}

	.chat-title {
		font-size: 0.85rem;
		font-weight: 800;
		text-transform: uppercase;
		letter-spacing: 0.08em;
	}

	.chat-disabled-badge {
		font-size: 0.6rem;
		font-weight: 800;
		color: #ef4444;
		background: rgba(239, 68, 68, 0.15);
		padding: 0.15rem 0.4rem;
		border-radius: 4px;
	}

	.chat-slowmode-indicator {
		font-size: 0.65rem;
		font-weight: 700;
		color: var(--text-muted);
		background: var(--surface-raised);
		padding: 0.15rem 0.45rem;
		border-radius: 4px;
		border: 1px solid var(--glass-border);
	}

	.chat-btn-icon-danger {
		background: none;
		border: none;
		color: var(--text-muted);
		padding: 0.2rem 0.4rem;
		border-radius: 6px;
		cursor: pointer;
		transition: all 0.15s;
	}
	.chat-btn-icon-danger:hover {
		color: #ef4444;
		background: rgba(239, 68, 68, 0.12);
	}

	/* Messages Container */
	.chat-scroll-container {
		flex: 1;
		overflow-y: auto;
		padding: 0.6rem 0.8rem;
		min-height: 0;
	}

	.chat-messages-inner {
		display: flex;
		flex-direction: column;
		gap: 0.65rem;
		min-height: 100%;
	}

	/* Load Earlier Messages */
	.load-earlier-container {
		display: flex;
		justify-content: center;
		padding: 0.25rem 0 0.5rem 0;
	}
	.btn-load-earlier {
		background: var(--surface-raised);
		border: 1px solid var(--glass-border);
		color: var(--text-muted);
		font-size: 0.68rem;
		font-weight: 600;
		padding: 0.3rem 0.8rem;
		border-radius: 20px;
		cursor: pointer;
		display: inline-flex;
		align-items: center;
		gap: 0.4rem;
		transition: all 0.2s ease;
	}
	.btn-load-earlier:hover:not(:disabled) {
		background: var(--surface-sunken);
		color: var(--accent);
		border-color: var(--accent);
		transform: translateY(-1px);
	}
	.btn-load-earlier:disabled {
		opacity: 0.6;
		cursor: not-allowed;
	}

	.chat-empty-state {
		display: flex;
		flex-direction: column;
		align-items: center;
		justify-content: center;
		height: 100%;
		color: var(--text-muted);
		text-align: center;
		padding: 1.5rem;
		gap: 0.4rem;
	}
	.chat-empty-state .empty-icon { font-size: 2rem; opacity: 0.4; }
	.chat-empty-state p { font-size: 0.75rem; margin: 0; }

	/* Unread Divider */
	.unread-divider {
		display: flex;
		align-items: center;
		gap: 0.5rem;
		margin: 0.4rem 0;
	}
	.divider-line {
		flex: 1;
		height: 1px;
		background: rgba(239, 68, 68, 0.4);
	}
	.divider-badge {
		font-size: 0.6rem;
		font-weight: 800;
		color: #ef4444;
		text-transform: uppercase;
		letter-spacing: 0.05em;
		background: rgba(239, 68, 68, 0.12);
		padding: 0.15rem 0.5rem;
		border-radius: 10px;
	}

	/* Message Row */
	.chat-msg-row {
		position: relative;
		display: flex;
		gap: 0.6rem;
		padding: 0.35rem 0.5rem;
		border-radius: 8px;
		transition: background 0.15s;
		animation: fadeInMsg 0.2s ease-out;
	}
	@keyframes fadeInMsg {
		from { opacity: 0; transform: translateY(4px); }
		to { opacity: 1; transform: translateY(0); }
	}

	.chat-msg-row:hover {
		background: rgba(255, 255, 255, 0.03);
	}

	.chat-msg-row.is-bot {
		background: rgba(168, 85, 247, 0.06);
		border-left: 2px solid #a855f7;
	}

	.chat-msg-row.is-mentioned {
		background: rgba(59, 130, 246, 0.08);
		border-left: 2px solid var(--accent);
	}

	.msg-avatar {
		width: 28px;
		height: 28px;
		min-width: 28px;
		background: var(--surface-raised);
		border: 1px solid var(--glass-border);
		display: flex;
		align-items: center;
		justify-content: center;
		font-size: 0.7rem;
		font-weight: 800;
		color: var(--accent);
		overflow: hidden;
		flex-shrink: 0;
	}
	.avatar-shape-circle { border-radius: 50%; }
	.avatar-shape-rounded { border-radius: 6px; }
	.avatar-shape-square { border-radius: 2px; }
	.avatar-img { width: 100%; height: 100%; object-fit: cover; }

	.bot-avatar {
		background: linear-gradient(135deg, rgba(168, 85, 247, 0.2), rgba(59, 130, 246, 0.2));
		border-color: #a855f7;
	}
	.bot-icon { font-size: 0.9rem; }

	.msg-content-wrapper {
		flex: 1;
		min-width: 0;
		display: flex;
		flex-direction: column;
		gap: 0.2rem;
	}

	.msg-header {
		display: flex;
		align-items: center;
		gap: 0.4rem;
		flex-wrap: wrap;
	}

	.msg-author {
		font-size: 0.72rem;
		font-weight: 800;
		color: var(--text-main);
	}
	.bot-author {
		color: #c084fc;
	}

	.bot-badge {
		font-size: 0.52rem;
		font-weight: 900;
		color: white;
		background: linear-gradient(135deg, #a855f7, #3b82f6);
		padding: 0.05rem 0.35rem;
		border-radius: 4px;
		letter-spacing: 0.05em;
	}

	.team-tag {
		font-size: 0.58rem;
		font-weight: 700;
		color: var(--accent);
		opacity: 0.85;
	}

	.seat-tag {
		font-size: 0.58rem;
		font-weight: 700;
		color: var(--text-muted);
		background: var(--surface-sunken);
		padding: 0.05rem 0.3rem;
		border-radius: 4px;
	}

	.msg-time {
		font-size: 0.55rem;
		color: var(--text-muted);
		margin-left: auto;
	}

	.msg-delete-btn {
		background: none;
		border: none;
		color: var(--text-muted);
		font-size: 0.65rem;
		padding: 0 0.2rem;
		cursor: pointer;
		opacity: 0;
		transition: opacity 0.15s;
	}
	.chat-msg-row:hover .msg-delete-btn { opacity: 0.6; }
	.msg-delete-btn:hover { opacity: 1 !important; color: #ef4444; }

	.msg-text {
		font-size: 0.76rem;
		color: var(--text-secondary);
		line-height: 1.35;
		white-space: pre-wrap;
		word-break: break-word;
	}

	:global(.mention-chip) {
		display: inline-block;
		font-weight: 800;
		padding: 0.05rem 0.3rem;
		border-radius: 4px;
		font-size: 0.72rem;
	}
	:global(.mention-alanbix) {
		color: #c084fc;
		background: rgba(168, 85, 247, 0.15);
	}
	:global(.mention-me) {
		color: #38bdf8;
		background: rgba(56, 189, 248, 0.15);
	}
	:global(.mention-user) {
		color: var(--accent);
		background: rgba(59, 130, 246, 0.12);
	}
	:global(.chat-link) {
		color: #60a5fa;
		text-decoration: underline;
		word-break: break-all;
	}

	/* Image attachment */
	.msg-image-attachment {
		margin-top: 0.25rem;
		position: relative;
		display: inline-block;
		max-width: 220px;
		border-radius: 8px;
		overflow: hidden;
		border: 1px solid var(--glass-border);
		cursor: pointer;
	}
	.msg-image-attachment img {
		display: block;
		width: 100%;
		max-height: 140px;
		object-fit: cover;
		transition: transform 0.2s;
	}
	.msg-image-attachment:hover img {
		transform: scale(1.03);
	}
	.zoom-indicator {
		position: absolute;
		bottom: 4px;
		right: 4px;
		background: rgba(0, 0, 0, 0.6);
		font-size: 0.6rem;
		padding: 2px 4px;
		border-radius: 4px;
	}

	/* Link Preview Card */
	.link-preview-card {
		margin-top: 0.3rem;
		display: flex;
		gap: 0.5rem;
		padding: 0.45rem;
		background: var(--surface-sunken);
		border: 1px solid var(--glass-border);
		border-radius: 8px;
		text-decoration: none;
		max-width: 320px;
	}
	.lp-thumb {
		width: 55px;
		height: 55px;
		object-fit: cover;
		border-radius: 4px;
		flex-shrink: 0;
	}
	.lp-info {
		display: flex;
		flex-direction: column;
		justify-content: center;
		min-width: 0;
		overflow: hidden;
	}
	.lp-domain { font-size: 0.52rem; color: var(--accent); font-weight: 700; text-transform: uppercase; }
	.lp-title { font-size: 0.68rem; font-weight: 800; color: var(--text-main); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
	.lp-desc { font-size: 0.58rem; color: var(--text-muted); line-height: 1.2; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; }

	/* Floating jump button */
	.jump-latest-pill {
		position: absolute;
		bottom: 56px;
		right: 14px;
		display: flex;
		align-items: center;
		gap: 0.35rem;
		background: var(--accent);
		color: white;
		border: none;
		border-radius: 20px;
		padding: 0.35rem 0.75rem;
		font-size: 0.68rem;
		font-weight: 800;
		cursor: pointer;
		box-shadow: 0 4px 14px rgba(0, 0, 0, 0.35);
		z-index: 10;
		animation: popIn 0.2s cubic-bezier(0.175, 0.885, 0.32, 1.275);
	}
	@keyframes popIn {
		from { transform: scale(0.8) translateY(10px); opacity: 0; }
		to { transform: scale(1) translateY(0); opacity: 1; }
	}
	.unread-pill-count {
		background: #ef4444;
		font-size: 0.55rem;
		padding: 0.1rem 0.35rem;
		border-radius: 10px;
	}

	/* Mention dropdown */
	.mention-dropdown {
		position: absolute;
		bottom: 56px;
		left: 12px;
		width: 240px;
		max-height: 180px;
		overflow-y: auto;
		border-radius: 10px;
		background: var(--bg-tertiary);
		border: 1px solid var(--glass-border);
		box-shadow: 0 8px 24px rgba(0, 0, 0, 0.4);
		z-index: 20;
		padding: 0.25rem;
	}
	.mention-item {
		display: flex;
		align-items: center;
		gap: 0.45rem;
		padding: 0.35rem 0.5rem;
		border-radius: 6px;
		cursor: pointer;
		font-size: 0.72rem;
		transition: background 0.1s;
	}
	.mention-item.selected, .mention-item:hover {
		background: var(--accent-soft);
	}
	.m-avatar {
		width: 20px;
		height: 20px;
		min-width: 20px;
		object-fit: cover;
		display: flex;
		align-items: center;
		justify-content: center;
		font-size: 0.6rem;
		font-weight: 800;
	}
	.m-avatar-fallback { background: var(--surface-raised); color: var(--accent); border-radius: 50%; }
	.m-name { font-weight: 800; color: var(--text-main); }
	.m-sub { font-size: 0.55rem; color: var(--text-muted); margin-left: auto; }
	.bot-sub { color: #c084fc; font-weight: 700; }

	/* GIF Picker Popover */
	.gif-picker-popover {
		position: absolute;
		bottom: 56px;
		left: 40px;
		width: 260px;
		background: var(--bg-tertiary);
		border: 1px solid var(--glass-border);
		border-radius: 10px;
		box-shadow: 0 8px 24px rgba(0, 0, 0, 0.45);
		padding: 0.5rem;
		z-index: 20;
	}
	.gif-grid {
		display: grid;
		grid-template-columns: repeat(3, 1fr);
		gap: 0.35rem;
	}
	.gif-chip {
		background: var(--surface-sunken);
		border: 1px solid var(--glass-border);
		border-radius: 6px;
		overflow: hidden;
		cursor: pointer;
		display: flex;
		flex-direction: column;
		align-items: center;
		padding: 0;
		transition: transform 0.15s;
	}
	.gif-chip:hover { transform: scale(1.05); }
	.gif-chip img { width: 100%; height: 50px; object-fit: cover; }
	.gif-chip span { font-size: 0.55rem; font-weight: 700; color: var(--text-muted); padding: 2px 0; }

	/* Pending preview */
	.pending-preview-bar {
		display: flex;
		align-items: center;
		gap: 0.5rem;
		padding: 0.3rem 0.8rem;
		background: var(--surface-sunken);
		border-top: 1px solid var(--glass-border);
	}
	.preview-thumb-box {
		position: relative;
		width: 36px;
		height: 36px;
		border-radius: 6px;
		overflow: hidden;
		border: 1px solid var(--glass-border);
	}
	.preview-thumb-box img { width: 100%; height: 100%; object-fit: cover; }
	.remove-preview-btn {
		position: absolute;
		top: 2px;
		right: 2px;
		background: rgba(0, 0, 0, 0.7);
		color: white;
		border: none;
		width: 14px;
		height: 14px;
		font-size: 0.5rem;
		border-radius: 50%;
		cursor: pointer;
		display: flex;
		align-items: center;
		justify-content: center;
	}
	.preview-label { font-size: 0.65rem; color: var(--text-muted); font-weight: 600; }

	/* Input Bar */
	.chat-input-bar {
		display: flex;
		align-items: flex-end;
		gap: 0.4rem;
		padding: 0.5rem 0.8rem;
		border-top: 1px solid var(--glass-border);
		background: var(--surface-sunken);
		flex-shrink: 0;
	}

	.btn-action-icon {
		background: var(--surface-raised);
		border: 1px solid var(--glass-border);
		border-radius: 8px;
		width: 32px;
		height: 32px;
		display: flex;
		align-items: center;
		justify-content: center;
		font-size: 0.85rem;
		color: var(--text-muted);
		cursor: pointer;
		transition: all 0.15s;
		flex-shrink: 0;
	}
	.btn-action-icon:hover {
		color: var(--accent);
		background: var(--accent-soft);
	}
	.gif-btn {
		font-size: 0.6rem;
		font-weight: 900;
		color: var(--accent);
	}

	.textarea-wrapper {
		flex: 1;
		position: relative;
		display: flex;
		align-items: center;
	}

	textarea {
		width: 100%;
		min-height: 32px;
		max-height: 90px;
		background: var(--bg-tertiary);
		border: 1px solid var(--glass-border);
		border-radius: 8px;
		padding: 0.35rem 2.5rem 0.35rem 0.6rem;
		color: var(--text-main);
		font-size: 0.75rem;
		resize: none;
		line-height: 1.3;
		font-family: inherit;
		box-sizing: border-box;
	}
	textarea:focus {
		outline: none;
		border-color: var(--accent);
	}

	.char-counter {
		position: absolute;
		right: 6px;
		bottom: 6px;
		font-size: 0.5rem;
		font-weight: 700;
		pointer-events: none;
	}

	.btn-send-chat {
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
		transition: transform 0.1s, opacity 0.15s;
		flex-shrink: 0;
	}
	.btn-send-chat:disabled {
		opacity: 0.4;
		cursor: not-allowed;
	}
	.btn-send-chat:not(:disabled):hover {
		transform: scale(1.05);
	}
	.slowmode-locked {
		background: var(--surface-raised) !important;
		color: var(--text-muted) !important;
		border: 1px solid var(--glass-border);
	}
	.slowmode-countdown {
		font-size: 0.65rem;
		font-weight: 800;
	}

	.mini-spinner {
		width: 14px;
		height: 14px;
		border: 2px solid rgba(255, 255, 255, 0.3);
		border-top-color: white;
		border-radius: 50%;
		animation: spin 0.6s linear infinite;
	}
	@keyframes spin { to { transform: rotate(360deg); } }

	/* Lightbox */
	.lightbox-overlay {
		position: fixed;
		inset: 0;
		background: rgba(0, 0, 0, 0.85);
		backdrop-filter: blur(8px);
		z-index: 9999;
		display: flex;
		align-items: center;
		justify-content: center;
		padding: 1.5rem;
	}
	.lightbox-container {
		position: relative;
		max-width: 90vw;
		max-height: 90vh;
	}
	.lightbox-img {
		max-width: 90vw;
		max-height: 85vh;
		border-radius: 10px;
		box-shadow: 0 10px 40px rgba(0, 0, 0, 0.6);
	}
	.lightbox-close {
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
		box-shadow: 0 2px 8px rgba(0,0,0,0.4);
	}

	/* Active Typers Indicator */
	.chat-typing-bar {
		display: flex;
		align-items: center;
		gap: 0.45rem;
		padding: 0.3rem 0.85rem;
		background: var(--surface-sunken);
		border-top: 1px solid var(--glass-border);
		font-size: 0.72rem;
		color: var(--text-dim);
		min-height: 28px;
		animation: typingSlideIn 0.2s cubic-bezier(0.16, 1, 0.3, 1);
		overflow: hidden;
		flex-shrink: 0;
	}

	@keyframes typingSlideIn {
		from {
			opacity: 0;
			transform: translateY(3px);
			max-height: 0;
		}
		to {
			opacity: 1;
			transform: translateY(0);
			max-height: 34px;
		}
	}

	.typing-dots-anim {
		display: inline-flex;
		align-items: center;
		gap: 3px;
		flex-shrink: 0;
		padding: 0 2px;
	}

	.t-dot {
		width: 4px;
		height: 4px;
		background-color: var(--accent);
		border-radius: 50%;
		display: inline-block;
		animation: typingDotBounce 1.4s infinite ease-in-out both;
	}
	.t-dot:nth-child(1) { animation-delay: -0.32s; }
	.t-dot:nth-child(2) { animation-delay: -0.16s; }
	.t-dot:nth-child(3) { animation-delay: 0s; }

	@keyframes typingDotBounce {
		0%, 80%, 100% {
			transform: scale(0.65);
			opacity: 0.35;
		}
		40% {
			transform: scale(1.15);
			opacity: 1;
		}
	}

	.typing-text-wrapper {
		white-space: nowrap;
		overflow: hidden;
		text-overflow: ellipsis;
		line-height: 1.25;
	}

	.typers-highlight {
		font-weight: 700;
		color: var(--accent);
	}

	.typing-ellipsis {
		color: var(--accent);
		margin: 0 0.15rem;
		opacity: 0.85;
	}

	.typing-humor-phrase {
		color: var(--text-dim);
		font-style: italic;
	}

	/* Sound Toggle in Header (Point 5) */
	.chat-btn-icon-sound {
		background: none;
		border: none;
		color: var(--text-muted);
		padding: 0.2rem 0.35rem;
		border-radius: 6px;
		cursor: pointer;
		font-size: 0.85rem;
		transition: all 0.2s;
		line-height: 1;
	}
	.chat-btn-icon-sound:hover {
		color: var(--text-primary);
		background: rgba(255, 255, 255, 0.08);
	}
	.chat-btn-icon-sound.sound-muted {
		opacity: 0.55;
		filter: grayscale(1);
	}

	/* Pinned Message Banner (Point 3) */
	.chat-pinned-banner {
		display: flex;
		align-items: center;
		justify-content: space-between;
		padding: 0.35rem 0.8rem;
		background: rgba(245, 158, 11, 0.09);
		border-bottom: 1px solid rgba(245, 158, 11, 0.25);
		gap: 0.5rem;
		flex-shrink: 0;
		animation: slideDownPinned 0.2s ease-out;
	}
	@keyframes slideDownPinned {
		from { opacity: 0; transform: translateY(-6px); }
		to { opacity: 1; transform: translateY(0); }
	}
	.pinned-banner-content {
		display: flex;
		align-items: center;
		gap: 0.5rem;
		flex: 1;
		min-width: 0;
		cursor: pointer;
	}
	.pinned-pin-icon {
		font-size: 0.85rem;
		flex-shrink: 0;
	}
	.pinned-text-wrap {
		display: flex;
		flex-direction: column;
		min-width: 0;
	}
	.pinned-header-line {
		display: flex;
		align-items: center;
		gap: 0.4rem;
	}
	.pinned-badge-tag {
		font-size: 0.58rem;
		font-weight: 800;
		text-transform: uppercase;
		letter-spacing: 0.05em;
		color: #f59e0b;
	}
	.pinned-author-name {
		font-size: 0.68rem;
		font-weight: 700;
		color: var(--text-secondary);
	}
	.pinned-message-preview {
		font-size: 0.72rem;
		color: var(--text-primary);
		white-space: nowrap;
		overflow: hidden;
		text-overflow: ellipsis;
	}
	.pinned-banner-actions {
		display: flex;
		align-items: center;
		gap: 0.25rem;
		flex-shrink: 0;
	}
	.pinned-action-btn {
		background: rgba(255, 255, 255, 0.06);
		border: 1px solid var(--glass-border);
		color: var(--text-secondary);
		border-radius: 4px;
		width: 22px;
		height: 22px;
		display: flex;
		align-items: center;
		justify-content: center;
		font-size: 0.75rem;
		cursor: pointer;
		transition: all 0.2s;
	}
	.pinned-action-btn:hover {
		color: var(--text-primary);
		background: rgba(255, 255, 255, 0.12);
	}
	.pinned-action-btn.btn-unpin:hover {
		color: #ef4444;
		border-color: rgba(239, 68, 68, 0.3);
	}

	/* Message Highlighting (on jump to quote or pin) */
	.chat-msg-row.is-highlighted {
		background: rgba(168, 85, 247, 0.22) !important;
		box-shadow: 0 0 14px rgba(168, 85, 247, 0.4);
		transition: background 0.3s ease, box-shadow 0.3s ease;
	}

	/* Quoted Reply inside Message (Point 2) */
	.msg-reply-quote {
		display: flex;
		align-items: center;
		gap: 0.4rem;
		padding: 0.2rem 0.5rem;
		background: rgba(255, 255, 255, 0.04);
		border-left: 3px solid var(--accent);
		border-radius: 4px;
		font-size: 0.7rem;
		cursor: pointer;
		margin-bottom: 0.2rem;
		transition: background 0.2s;
		max-width: 100%;
		overflow: hidden;
	}
	.msg-reply-quote:hover {
		background: rgba(255, 255, 255, 0.08);
	}
	.quote-symbol {
		font-size: 0.75rem;
		flex-shrink: 0;
		opacity: 0.7;
	}
	.quote-author {
		color: var(--accent);
		font-weight: 700;
		flex-shrink: 0;
	}
	.quote-snippet {
		color: var(--text-muted);
		white-space: nowrap;
		overflow: hidden;
		text-overflow: ellipsis;
	}

	/* Message Hover Actions Bar (Points 1, 2, 3) */
	.msg-action-bar {
		position: absolute;
		right: 0.5rem;
		top: -0.5rem;
		display: flex;
		align-items: center;
		gap: 2px;
		background: var(--surface-raised);
		border: 1px solid var(--glass-border);
		border-radius: 6px;
		padding: 2px 3px;
		opacity: 0;
		pointer-events: none;
		transition: opacity 0.15s ease;
		z-index: 20;
		box-shadow: 0 2px 8px rgba(0,0,0,0.3);
	}
	.chat-msg-row:hover .msg-action-bar,
	.msg-action-bar.has-active-popover {
		opacity: 1;
		pointer-events: auto;
	}
	.msg-action-btn {
		background: none;
		border: none;
		color: var(--text-secondary);
		font-size: 0.72rem;
		padding: 2px 5px;
		border-radius: 4px;
		cursor: pointer;
		transition: all 0.15s;
		line-height: 1;
	}
	.msg-action-btn:hover {
		color: var(--text-primary);
		background: rgba(255, 255, 255, 0.1);
	}
	.msg-action-btn.active-pin {
		color: #f59e0b;
	}
	.msg-action-btn.btn-danger-action:hover {
		color: #ef4444;
		background: rgba(239, 68, 68, 0.15);
	}

	/* Quick Reactions Popover (Point 1) */
	.quick-reactions-popover {
		position: absolute;
		right: 0;
		display: flex;
		align-items: center;
		gap: 3px;
		padding: 4px 6px;
		background: var(--surface-raised);
		border: 1px solid var(--glass-border);
		border-radius: 8px;
		box-shadow: 0 4px 16px rgba(0, 0, 0, 0.45);
		z-index: 50;
		animation: popInReaction 0.15s ease-out;
		white-space: nowrap;
	}
	.quick-reactions-popover.popover-up {
		bottom: calc(100% + 4px);
		top: auto;
	}
	.quick-reactions-popover.popover-down {
		top: calc(100% + 4px);
		bottom: auto;
	}
	@keyframes popInReaction {
		from { opacity: 0; transform: scale(0.92); }
		to { opacity: 1; transform: scale(1); }
	}
	.reaction-pick-emoji {
		background: none;
		border: none;
		font-size: 1.05rem;
		padding: 2px 4px;
		border-radius: 4px;
		cursor: pointer;
		transition: transform 0.15s, background 0.15s;
		line-height: 1;
		display: inline-flex;
		align-items: center;
		justify-content: center;
	}
	.reaction-pick-emoji:hover {
		transform: scale(1.22);
		background: rgba(255, 255, 255, 0.1);
	}
	.reaction-pick-emoji.is-text-tag {
		font-size: 0.65rem;
		font-weight: 800;
		font-family: monospace;
		padding: 3px 6px;
		background: rgba(168, 85, 247, 0.12);
		border: 1px solid rgba(168, 85, 247, 0.3);
		color: #e9d5ff;
	}
	.reaction-pick-emoji.is-text-tag:hover {
		background: rgba(168, 85, 247, 0.25);
		border-color: #a855f7;
	}
	.quick-divider {
		width: 1px;
		height: 18px;
		background: var(--glass-border);
		margin: 0 2px;
		display: inline-block;
	}
	.reaction-pick-more-btn {
		background: rgba(255, 255, 255, 0.06);
		border: 1px solid var(--glass-border);
		color: var(--text-secondary);
		border-radius: 4px;
		font-size: 0.72rem;
		padding: 3px 6px;
		cursor: pointer;
		display: inline-flex;
		align-items: center;
		justify-content: center;
		line-height: 1;
		transition: all 0.15s;
	}
	.reaction-pick-more-btn:hover {
		background: var(--accent-soft);
		border-color: var(--accent);
		color: var(--accent);
		transform: scale(1.08);
	}

	/* Full Standard Emoji Picker Popover */
	.full-emoji-picker {
		position: absolute;
		right: 0;
		width: 295px;
		max-width: min(320px, calc(100vw - 40px));
		background: var(--surface-raised);
		border: 1px solid var(--glass-border);
		border-radius: 10px;
		box-shadow: 0 10px 32px rgba(0, 0, 0, 0.55);
		z-index: 60;
		display: flex;
		flex-direction: column;
		animation: popInReaction 0.18s ease-out;
		overflow: hidden;
	}
	.full-emoji-picker.popover-up {
		bottom: calc(100% + 4px);
		top: auto;
	}
	.full-emoji-picker.popover-down {
		top: calc(100% + 4px);
		bottom: auto;
	}

	.picker-search-bar {
		display: flex;
		align-items: center;
		gap: 0.4rem;
		padding: 0.45rem 0.6rem;
		border-bottom: 1px solid var(--glass-border);
		background: var(--surface-sunken);
	}
	.picker-search-icon {
		font-size: 0.75rem;
		opacity: 0.6;
	}
	.picker-search-input {
		flex: 1;
		background: transparent;
		border: none;
		outline: none;
		color: var(--text-primary);
		font-size: 0.72rem;
		padding: 0;
	}
	.picker-search-input::placeholder {
		color: var(--text-muted);
	}
	.picker-clear-search {
		background: none;
		border: none;
		color: var(--text-muted);
		font-size: 0.65rem;
		cursor: pointer;
		padding: 2px 4px;
		border-radius: 50%;
		transition: color 0.15s;
	}
	.picker-clear-search:hover {
		color: var(--text-primary);
	}

	.picker-cat-tabs {
		display: flex;
		align-items: center;
		gap: 2px;
		padding: 0.3rem 0.45rem;
		border-bottom: 1px solid var(--glass-border);
		background: var(--surface-raised);
		overflow-x: auto;
	}
	.cat-tab {
		background: none;
		border: none;
		font-size: 0.95rem;
		padding: 4px 6px;
		border-radius: 6px;
		cursor: pointer;
		transition: all 0.15s;
		opacity: 0.6;
		display: flex;
		align-items: center;
		justify-content: center;
		line-height: 1;
	}
	.cat-tab:hover {
		opacity: 1;
		background: rgba(255, 255, 255, 0.08);
	}
	.cat-tab.active {
		opacity: 1;
		background: var(--accent-soft);
		border-bottom: 2px solid var(--accent);
		border-radius: 6px 6px 2px 2px;
	}

	.picker-emojis-scroll {
		max-height: 200px;
		overflow-y: auto;
		padding: 0.45rem;
	}
	.picker-empty-state {
		display: flex;
		flex-direction: column;
		align-items: center;
		justify-content: center;
		padding: 1.5rem 0.5rem;
		color: var(--text-muted);
		gap: 0.3rem;
	}
	.picker-empty-icon {
		font-size: 1.5rem;
		opacity: 0.6;
	}
	.picker-empty-state p {
		font-size: 0.72rem;
		margin: 0;
	}

	.picker-emojis-grid {
		display: grid;
		grid-template-columns: repeat(7, 1fr);
		gap: 4px;
	}
	.grid-emoji-btn {
		background: none;
		border: none;
		font-size: 1.15rem;
		padding: 4px 2px;
		border-radius: 6px;
		cursor: pointer;
		transition: transform 0.12s, background 0.12s;
		display: flex;
		align-items: center;
		justify-content: center;
		line-height: 1;
	}
	.grid-emoji-btn:hover {
		transform: scale(1.22);
		background: rgba(255, 255, 255, 0.1);
	}
	.grid-emoji-btn.is-text-tag {
		font-size: 0.62rem;
		font-weight: 800;
		font-family: monospace;
		padding: 4px 2px;
		background: rgba(168, 85, 247, 0.12);
		border: 1px solid rgba(168, 85, 247, 0.3);
		color: #e9d5ff;
		grid-column: span 2;
	}
	.grid-emoji-btn.is-text-tag:hover {
		background: rgba(168, 85, 247, 0.25);
		border-color: #a855f7;
		transform: scale(1.05);
	}

	/* Reaction Pills Under Message (Point 1) */
	.msg-reactions-container {
		display: flex;
		flex-wrap: wrap;
		gap: 0.3rem;
		margin-top: 0.25rem;
	}
	.reaction-pill {
		display: inline-flex;
		align-items: center;
		gap: 0.25rem;
		padding: 0.1rem 0.4rem;
		background: var(--surface-raised);
		border: 1px solid var(--glass-border);
		border-radius: 12px;
		font-size: 0.68rem;
		color: var(--text-secondary);
		cursor: pointer;
		transition: all 0.15s;
	}
	.reaction-pill:hover {
		background: rgba(255, 255, 255, 0.08);
		border-color: rgba(255, 255, 255, 0.2);
	}
	.reaction-pill.reacted-by-user {
		background: rgba(168, 85, 247, 0.16);
		border-color: #a855f7;
		color: #e9d5ff;
		font-weight: 700;
	}
	.reaction-pill.is-text-tag {
		font-family: monospace;
		font-weight: 800;
	}
	.reaction-emoji {
		font-size: 0.75rem;
		line-height: 1;
	}
	.reaction-count {
		font-size: 0.65rem;
		font-weight: 700;
	}

	/* Replying Preview Bar Above Input (Point 2) */
	.replying-preview-bar {
		display: flex;
		align-items: center;
		justify-content: space-between;
		padding: 0.35rem 0.8rem;
		background: rgba(59, 130, 246, 0.08);
		border-top: 1px solid rgba(59, 130, 246, 0.2);
		border-left: 3px solid var(--accent);
		font-size: 0.72rem;
		flex-shrink: 0;
		animation: slideUpReply 0.2s ease-out;
	}
	@keyframes slideUpReply {
		from { opacity: 0; transform: translateY(4px); }
		to { opacity: 1; transform: translateY(0); }
	}
	.replying-content {
		display: flex;
		align-items: center;
		gap: 0.45rem;
		min-width: 0;
		flex: 1;
	}
	.replying-icon {
		font-size: 0.8rem;
		flex-shrink: 0;
	}
	.replying-text-group {
		display: flex;
		flex-direction: column;
		min-width: 0;
	}
	.replying-lead {
		font-size: 0.65rem;
		color: var(--text-secondary);
	}
	.replying-lead strong {
		color: var(--accent);
	}
	.replying-snippet {
		color: var(--text-primary);
		white-space: nowrap;
		overflow: hidden;
		text-overflow: ellipsis;
		font-size: 0.72rem;
	}
	.replying-cancel-btn {
		background: none;
		border: none;
		color: var(--text-muted);
		cursor: pointer;
		font-size: 0.8rem;
		padding: 0.15rem 0.35rem;
		border-radius: 4px;
		transition: all 0.15s;
		flex-shrink: 0;
	}
	.replying-cancel-btn:hover {
		color: #ef4444;
		background: rgba(239, 68, 68, 0.12);
	}
</style>
