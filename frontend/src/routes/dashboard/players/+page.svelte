<script>
	import { api } from '$lib/api';
	import { onMount, onDestroy, tick } from 'svelte';
	import { wsMessageStore } from '$lib/ws';
	import { page } from '$app/stores';
	import { pmUnreadCount, groupUnreadCount } from '$lib/pmStore';

	let players = [];
	let currentUser = null;
	let loading = true;

	// Chat state — dual mode: P2P (chatPeerId) or Group (chatChannelKey)
	let chatMode = null; // 'p2p' | 'group' | null
	let chatPeerId = null;
	let chatPeer = null;
	let chatChannelKey = null;
	let chatChannelInfo = null; // {channel_key, channel_type, team_names}
	let chatChannelMembers = [];
	let chatMessages = [];
	let chatInput = '';
	let chatLoading = false;
	let chatEl = null; // scroll container ref

	// Points detail expand
	let expandedPlayerId = null;
	let pointsHistory = null;
	let pointsLoading = false;

	// Resizer state
	let chatWidth = 380;
	let isResizing = false;

	function startResize(e) {
		isResizing = true;
		document.body.style.cursor = 'col-resize';
		document.body.style.userSelect = 'none';
		window.addEventListener('mousemove', doResize);
		window.addEventListener('mouseup', stopResize);
	}

	function doResize(e) {
		if (!isResizing) return;
		const newWidth = window.innerWidth - e.clientX - 30;
		const maxAllowedWidth = window.innerWidth * 0.70;
		if (newWidth >= 250 && newWidth <= maxAllowedWidth) {
			chatWidth = newWidth;
		}
	}

	function stopResize() {
		isResizing = false;
		document.body.style.cursor = '';
		document.body.style.userSelect = '';
		localStorage.setItem('alanbix_chat_width', chatWidth);
		window.removeEventListener('mousemove', doResize);
		window.removeEventListener('mouseup', stopResize);
	}

	// Svelte reactive helper to check if a team's chat channel is currently active
	function isTeamChatActive(teamName, mode, channelKey) {
		if (mode !== 'group' || !channelKey || !currentUser) return false;
		if (currentUser.is_admin || !currentUser.team_name) {
			return channelKey === `team:${teamName}`;
		}
		if (currentUser.team_name === teamName) {
			return channelKey === `team:${teamName}`;
		} else {
			const names = [currentUser.team_name, teamName].sort();
			return channelKey === `inter:${names[0]}|${names[1]}`;
		}
	}

	// Per-player unread counts
	let unreadMap = {}; // peer_id -> unread count

	// Group unread counts (AXE-12)
	let groupUnreadMap = {}; // channel_key -> unread count

	let wsUnsub = null;

	onMount(async () => {
		try { currentUser = await api.get('/me'); } catch {}
		await loadPlayers();
		await loadUnreadMap();
		await loadGroupUnreadMap();

		// Restore chat width
		const savedWidth = localStorage.getItem('alanbix_chat_width');
		if (savedWidth) chatWidth = parseInt(savedWidth);

		// Restore last selected chat from localStorage
		const savedPeer = localStorage.getItem('alanbix_players_chat');
		const savedGroup = localStorage.getItem('alanbix_players_group_chat');
		// Check URL params for auto-open from notification click
		const urlPeer = $page.url.searchParams.get('chat');
		const urlGroup = $page.url.searchParams.get('group');
		
		if (urlGroup) {
			openGroupChat(decodeURIComponent(urlGroup));
		} else {
			const targetPeer = urlPeer ? parseInt(urlPeer) : (savedPeer ? parseInt(savedPeer) : null);
			if (targetPeer && targetPeer !== currentUser?.id) {
				openChat(targetPeer);
			} else if (savedGroup) {
				openGroupChat(savedGroup);
			}
		}

		wsUnsub = wsMessageStore.subscribe(async msg => {
			if (!msg) return;
			if (msg.type === 'users_updated' || msg.type === 'tournament_closed' || msg.type === 'tournament_reopened' ||
				msg.type === 'tournament_created' || msg.type === 'tournament_updated' || msg.type === 'tournament_deleted' ||
				msg.type === 'tournament_started') {
				await loadPlayers();
				if (expandedPlayerId) {
					try {
						pointsHistory = await api.get(`/players/${expandedPlayerId}/points-history`);
					} catch { pointsHistory = null; }
				}
			}
			if (msg.type === 'private_message_new') {
				const peerId = msg.sender_id === currentUser?.id ? msg.receiver_id : msg.sender_id;
				if (chatMode === 'p2p' && chatPeerId && (msg.sender_id === chatPeerId || msg.receiver_id === chatPeerId)) {
					loadChat(chatPeerId, true);
				}
				loadUnreadMap();
			}
			if (msg.type === 'group_message_new') {
				if (chatMode === 'group' && chatChannelKey === msg.channel_key) {
					loadGroupChat(msg.channel_key, true);
				}
				loadGroupUnreadMap();
			}
		});
	});

	onDestroy(() => { 
		if (wsUnsub) wsUnsub(); 
		if (typeof window !== 'undefined') {
			window.removeEventListener('mousemove', doResize);
			window.removeEventListener('mouseup', stopResize);
		}
	});

	async function loadPlayers() {
		loading = true;
		try { players = await api.get('/players'); } catch { players = []; }
		loading = false;
	}

	async function loadUnreadMap() {
		try {
			const convos = await api.get('/players/messages/conversations');
			const map = {};
			let total = 0;
			convos.forEach(c => { if (c.unread > 0) { map[c.peer_id] = c.unread; total += c.unread; } });
			unreadMap = map;
			pmUnreadCount.set(total);
		} catch { unreadMap = {}; pmUnreadCount.set(0); }
	}

	async function loadGroupUnreadMap() {
		try {
			const channels = await api.get('/players/group/channels');
			const map = {};
			let total = 0;
			channels.forEach(c => { if (c.unread > 0) { map[c.channel_key] = c.unread; total += c.unread; } });
			groupUnreadMap = map;
			groupUnreadCount.set(total);
		} catch { groupUnreadMap = {}; groupUnreadCount.set(0); }
	}

	// Reactive per-team unread breakdown — recalculated whenever groupUnreadMap changes
	$: teamUnreads = (() => {
		const result = {};
		// Build for every team mentioned in groupUnreadMap keys
		const allTeams = new Set();
		Object.keys(groupUnreadMap).forEach(key => {
			if (key.startsWith('team:')) allTeams.add(key.slice(5));
			if (key.startsWith('inter:')) key.slice(6).split('|').forEach(t => allTeams.add(t));
		});
		// Also include teams from players list
		players.forEach(p => { if (p.team_name) allTeams.add(p.team_name); });
		allTeams.forEach(teamName => {
			const teamCount = groupUnreadMap[`team:${teamName}`] || 0;
			const inters = [];
			Object.entries(groupUnreadMap).forEach(([k, count]) => {
				if (k.startsWith('inter:') && k.includes(teamName) && count > 0) {
					const teams = k.slice(6).split('|');
					const otherTeam = teams[0] === teamName ? teams[1] : teams[0];
					inters.push({ key: k, otherTeam, count });
				}
			});
			result[teamName] = { teamCount, inters, total: teamCount + inters.reduce((s, i) => s + i.count, 0) };
		});
		return result;
	})();

	// Group players by team
	$: grouped = (() => {
		const teams = {};
		const noTeam = [];
		players.forEach(p => {
			if (p.team_name) {
				if (!teams[p.team_name]) teams[p.team_name] = [];
				teams[p.team_name].push(p);
			} else {
				noTeam.push(p);
			}
		});
		Object.values(teams).forEach(arr => arr.sort((a, b) => b.points - a.points));
		noTeam.sort((a, b) => b.points - a.points);
		const sorted = Object.entries(teams).sort(([a], [b]) => a.localeCompare(b));
		return { teams: sorted, noTeam };
	})();

	async function togglePoints(e, playerId) {
		e.stopPropagation();
		if (expandedPlayerId === playerId) {
			expandedPlayerId = null;
			pointsHistory = null;
			return;
		}
		expandedPlayerId = playerId;
		pointsLoading = true;
		try {
			pointsHistory = await api.get(`/players/${playerId}/points-history`);
		} catch { pointsHistory = null; }
		pointsLoading = false;
	}

	// --- P2P Chat ---
	async function openChat(peerId) {
		if (peerId === currentUser?.id) return;
		chatMode = 'p2p';
		chatPeerId = peerId;
		chatChannelKey = null;
		chatChannelInfo = null;
		chatChannelMembers = [];
		localStorage.setItem('alanbix_players_chat', String(peerId));
		localStorage.removeItem('alanbix_players_group_chat');
		await loadChat(peerId, false);
		await loadUnreadMap();
	}

	async function loadChat(peerId, silent) {
		if (!silent) chatLoading = true;
		try {
			const data = await api.get(`/players/messages/${peerId}`);
			chatPeer = data.peer;
			chatMessages = data.messages || [];
			await tick();
			scrollChat();
		} catch { chatMessages = []; }
		if (!silent) chatLoading = false;
		if (!silent) await loadUnreadMap();
	}

	async function sendMessage() {
		if (chatMode === 'group') { sendGroupMessage(); return; }
		const content = chatInput.trim();
		if (!content || !chatPeerId) return;
		chatInput = '';
		try {
			await api.post(`/players/messages/${chatPeerId}`, { content });
			await loadChat(chatPeerId, true);
		} catch (e) {
			chatInput = content;
		}
	}

	// --- Group Chat (AXE-12) ---
	function openTeamChat(e, teamName) {
		e.stopPropagation();
		if (!currentUser) return;
		if (currentUser.is_admin || !currentUser.team_name) {
			openGroupChat(`team:${teamName}`);
			return;
		}
		const isMyTeam = currentUser.team_name === teamName;
		if (isMyTeam) {
			openGroupChat(`team:${teamName}`);
		} else {
			// Inter-team: sorted alphabetically for deterministic key
			const names = [currentUser.team_name, teamName].sort();
			openGroupChat(`inter:${names[0]}|${names[1]}`);
		}
	}

	async function openGroupChat(channelKey) {
		chatMode = 'group';
		chatChannelKey = channelKey;
		chatPeerId = null;
		chatPeer = null;
		localStorage.setItem('alanbix_players_group_chat', channelKey);
		localStorage.removeItem('alanbix_players_chat');
		await loadGroupChat(channelKey, false);
		await loadGroupUnreadMap();
	}

	async function loadGroupChat(channelKey, silent) {
		if (!silent) chatLoading = true;
		try {
			const data = await api.get(`/players/group/channel/${channelKey}`);
			chatChannelInfo = data.channel;
			chatMessages = (data.messages || []).map(m => ({
				...m, sender_id: m.sender_id, sender_name: m.sender_name
			}));
			chatChannelMembers = data.members || [];
			await tick();
			scrollChat();
		} catch { chatMessages = []; chatChannelInfo = null; }
		if (!silent) chatLoading = false;
		if (!silent) await loadGroupUnreadMap();
	}

	async function sendGroupMessage() {
		const content = chatInput.trim();
		if (!content || !chatChannelKey) return;
		chatInput = '';
		// Parse channel_key to determine type and team_names
		let channel_type, team_names;
		if (chatChannelKey.startsWith('team:')) {
			channel_type = 'team';
			team_names = [chatChannelKey.slice(5)];
		} else {
			channel_type = 'inter';
			team_names = chatChannelKey.slice(6).split('|');
		}
		try {
			await api.post('/players/group/send', { content, channel_type, team_names });
			await loadGroupChat(chatChannelKey, true);
		} catch (e) {
			chatInput = content;
		}
	}

	function closeChat() {
		chatMode = null;
		chatPeerId = null;
		chatPeer = null;
		chatChannelKey = null;
		chatChannelInfo = null;
		chatChannelMembers = [];
		chatMessages = [];
		localStorage.removeItem('alanbix_players_chat');
		localStorage.removeItem('alanbix_players_group_chat');
	}

	function scrollChat() {
		if (chatEl) chatEl.scrollTop = chatEl.scrollHeight;
	}

	function handleKeydown(e) {
		if (e.key === 'Enter' && !e.shiftKey) {
			e.preventDefault();
			sendMessage();
		}
	}



	function timeAgo(dateStr) {
		if (!dateStr) return '';
		let dStr = dateStr.replace(' ', 'T');
		if (!dStr.endsWith('Z')) dStr += 'Z';
		let diff = (Date.now() - new Date(dStr).getTime()) / 1000;
		if (diff < 0) diff = 0;
		if (diff < 60) return "à l'instant";
		if (diff < 3600) return `${Math.floor(diff / 60)} min`;
		if (diff < 86400) return `${Math.floor(diff / 3600)}h`;
		return `${Math.floor(diff / 86400)}j`;
	}

	function getRankEmoji(rank) {
		if (rank === 1) return '🥇';
		if (rank === 2) return '🥈';
		if (rank === 3) return '🥉';
		return rank ? `#${rank}` : '—';
	}


</script>

<div class="players-page animate-in">
	<header class="players-header glass">
		<h1 class="title-premium">👥 Joueurs</h1>
		<span class="player-count">{players.length} inscrit{players.length > 1 ? 's' : ''}</span>
	</header>

	<div class="players-layout" style="grid-template-columns: minmax(0, 1fr) 8px {chatWidth}px;">
		<!-- LEFT: Player directory -->
		<div class="directory-col">
			{#if loading}
				<div class="loading-state glass"><span>⏳</span> Chargement...</div>
			{:else}
				{#each grouped.teams as [teamName, members]}
					<div class="team-section glass" class:active-chat={isTeamChatActive(teamName, chatMode, chatChannelKey)}>
						<!-- svelte-ignore a11y-click-events-have-key-events -->
						<!-- svelte-ignore a11y-no-static-element-interactions -->
						<div class="team-header" on:click={(e) => openTeamChat(e, teamName)}>
							<span class="team-name">
								{teamName}
								{#if (teamUnreads[teamName]?.teamCount || 0) > 0}
									<span class="team-name-badge team-badge">🛡️ {teamUnreads[teamName].teamCount}</span>
								{/if}
								{#each (teamUnreads[teamName]?.inters || []) as inter}
									<span class="team-name-badge inter-badge">⚔️ {inter.count}</span>
								{/each}
							</span>
							<span class="team-count">{members.length}</span>
							{#if currentUser}
								<button
									class="team-chat-btn"
									class:has-unread={(teamUnreads[teamName]?.total || 0) > 0}
									on:click={(e) => openTeamChat(e, teamName)}
								>
									{#if currentUser.is_admin || !currentUser.team_name || currentUser.team_name === teamName}
										🛡️ Chat équipe
									{:else}
										⚔️ Chat inter
									{/if}
								</button>
							{/if}
						</div>
						<div class="team-members">
							{#each members as player}
								<!-- svelte-ignore a11y-click-events-have-key-events -->
								<!-- svelte-ignore a11y-no-static-element-interactions -->
								<div class="player-card" class:active-chat={chatPeerId === player.id} class:has-unread={(unreadMap[player.id] || 0) > 0} on:click={() => openChat(player.id)}>
									<div class="player-main">
										<div class="player-avatar">
											{player.username[0].toUpperCase()}
											{#if (unreadMap[player.id] || 0) > 0}
												<span class="player-unread-badge">{unreadMap[player.id]}</span>
											{/if}
										</div>
										<div class="player-info">
											<span class="player-username">{player.username}</span>
											<span class="player-pts">{player.points} pts</span>
										</div>
										<div class="player-actions">
											{#if player.seat_id}
												<a href="/dashboard/map?highlight={player.seat_id}" class="action-btn seat" title="Voir siège" on:click|stopPropagation>📍</a>
											{/if}
											<button class="action-btn pts" on:click={(e) => togglePoints(e, player.id)} title="Détail des points" class:expanded={expandedPlayerId === player.id}>📊</button>
										</div>
									</div>
									{#if expandedPlayerId === player.id}
										<!-- svelte-ignore a11y-click-events-have-key-events -->
										<!-- svelte-ignore a11y-no-static-element-interactions -->
										<div class="points-detail" on:click|stopPropagation>
											{#if pointsLoading}
												<span class="pts-loading">⏳</span>
											{:else}
												{#if pointsHistory && pointsHistory.history && pointsHistory.history.length > 0}
													<div class="pts-total">Total : <strong>{pointsHistory.total_points} pts</strong></div>
													{#each pointsHistory.history as h}
														<div class="pts-row">
															<span class="pts-rank">{getRankEmoji(h.rank)}</span>
															<span class="pts-tourney">{h.tournament_name}</span>
															{#if h.game_name}<span class="pts-game">{h.game_name}</span>{/if}
															<span class="pts-val">+{h.total}</span>
															{#if h.live}<span class="pts-live">LIVE</span>{/if}
														</div>
													{/each}
												{:else}
													<span class="pts-empty">Aucune participation</span>
												{/if}
												{#if pointsHistory && pointsHistory.awards && pointsHistory.awards.length > 0}
													<div class="awards-section">
														<div class="awards-title">🏆 Prix & Distinctions</div>
														{#each pointsHistory.awards as award}
															<div class="award-chip" title={award.description}>
																<span class="award-emoji">🎁</span>
																<div class="award-text">
																	<span class="award-name">{award.title}</span>
																	{#if award.description}
																		<span class="award-desc">{award.description}</span>
																	{/if}
																</div>
															</div>
														{/each}
													</div>
												{/if}
											{/if}
										</div>
									{/if}
								</div>
							{/each}
						</div>
					</div>
				{/each}

				{#if grouped.noTeam.length > 0}
					<div class="team-section glass">
						<div class="team-header solo-header">
							<span class="team-name">Sans équipe</span>
							<span class="team-count">{grouped.noTeam.length}</span>
						</div>
						<div class="team-members">
							{#each grouped.noTeam as player}
								<!-- svelte-ignore a11y-click-events-have-key-events -->
								<!-- svelte-ignore a11y-no-static-element-interactions -->
								<div class="player-card" class:active-chat={chatPeerId === player.id} class:has-unread={(unreadMap[player.id] || 0) > 0} on:click={() => openChat(player.id)}>
									<div class="player-main">
										<div class="player-avatar solo">
											{player.username[0].toUpperCase()}
											{#if (unreadMap[player.id] || 0) > 0}
												<span class="player-unread-badge">{unreadMap[player.id]}</span>
											{/if}
										</div>
										<div class="player-info">
											<span class="player-username">{player.username}</span>
											<span class="player-pts">{player.points} pts</span>
										</div>
										<div class="player-actions">
											{#if player.seat_id}
												<a href="/dashboard/map?highlight={player.seat_id}" class="action-btn seat" title="Voir siège" on:click|stopPropagation>📍</a>
											{/if}
											<button class="action-btn pts" on:click={(e) => togglePoints(e, player.id)} title="Détail des points" class:expanded={expandedPlayerId === player.id}>📊</button>
										</div>
									</div>
									{#if expandedPlayerId === player.id}
										<!-- svelte-ignore a11y-click-events-have-key-events -->
										<!-- svelte-ignore a11y-no-static-element-interactions -->
										<div class="points-detail" on:click|stopPropagation>
											{#if pointsLoading}
												<span class="pts-loading">⏳</span>
											{:else}
												{#if pointsHistory && pointsHistory.history && pointsHistory.history.length > 0}
													<div class="pts-total">Total : <strong>{pointsHistory.total_points} pts</strong></div>
													{#each pointsHistory.history as h}
														<div class="pts-row">
															<span class="pts-rank">{getRankEmoji(h.rank)}</span>
															<span class="pts-tourney">{h.tournament_name}</span>
															<div class="pts-bp-wrap">
																{#if h.placement_pts > 0}<span class="pts-bp pts-bp-place" title="Placement">🏅{h.placement_pts}</span>{/if}
																<span class="pts-bp pts-bp-parti" title="Participation">👤{h.participation_pts}</span>
																{#if h.score_pts > 0}<span class="pts-bp pts-bp-score" title="Bonus/Score — distribué selon le score cumulé">⚡{h.score_pts}</span>{/if}
															</div>
															<span class="pts-val">{h.live ? '~' : '+'}{h.total}</span>
															{#if h.live}<span class="pts-live">LIVE</span>{/if}
														</div>
													{/each}
												{:else}
													<span class="pts-empty">Aucune participation</span>
												{/if}
												{#if pointsHistory && pointsHistory.awards && pointsHistory.awards.length > 0}
													<div class="awards-section">
														<div class="awards-title">🏆 Prix & Distinctions</div>
														{#each pointsHistory.awards as award}
															<div class="award-chip" title={award.description}>
																<span class="award-emoji">🎁</span>
																<div class="award-text">
																	<span class="award-name">{award.title}</span>
																	{#if award.description}
																		<span class="award-desc">{award.description}</span>
																	{/if}
																</div>
															</div>
														{/each}
													</div>
												{/if}
											{/if}
										</div>
									{/if}
								</div>
							{/each}
						</div>
					</div>
				{/if}
			{/if}
		</div>

		<!-- CENTER: Resizer -->
		<!-- svelte-ignore a11y-no-static-element-interactions -->
		<div class="resizer" class:active={isResizing} on:mousedown={startResize}></div>

		<!-- RIGHT: Chat panel -->
		<div class="chat-col glass">
			{#if !chatMode}
				<div class="chat-empty">
					<span class="chat-empty-icon">💬</span>
					<p>Cliquez sur un joueur ou une équipe pour démarrer une conversation</p>
				</div>
			{:else if chatLoading}
				<div class="chat-empty"><span>⏳</span> Chargement...</div>
			{:else if chatMode === 'p2p'}
				<div class="chat-header">
					<div class="chat-peer-avatar">{chatPeer?.username?.[0]?.toUpperCase() || '?'}</div>
					<div class="chat-peer-info">
						<span class="chat-peer-name">{chatPeer?.username || '?'}</span>
						{#if chatPeer?.team_name}<span class="chat-peer-team">{chatPeer.team_name}</span>{/if}
					</div>
					{#if chatPeer?.seat_id}
						<a href="/dashboard/map?highlight={chatPeer.seat_id}" class="chat-seat-link" title="Voir siège">📍 {chatPeer.seat_id}</a>
					{/if}
					<button class="chat-close" on:click={closeChat} title="Fermer">✕</button>
				</div>

				<div class="chat-messages" bind:this={chatEl}>
					{#if chatMessages.length === 0}
						<div class="chat-no-msg"><p>Aucun message. Envoyez le premier !</p></div>
					{:else}
						{#each chatMessages as msg}
							<div class="chat-bubble {msg.sender_id === currentUser?.id ? 'mine' : 'theirs'}">
								<div class="bubble-content">{msg.content}</div>
								<span class="bubble-time">{timeAgo(msg.created_at)}</span>
							</div>
						{/each}
					{/if}
				</div>

				<div class="chat-input-bar">
					<textarea class="chat-input" bind:value={chatInput} on:keydown={handleKeydown} placeholder="Écrire un message..." rows="1"></textarea>
					<button class="chat-send" on:click={sendMessage} disabled={!chatInput.trim()}>
						<span>➤</span>
					</button>
				</div>
			{:else if chatMode === 'group'}
				<div class="chat-header group-header">
					<div class="chat-group-icon">{chatChannelInfo?.channel_type === 'team' ? '🛡️' : '⚔️'}</div>
					<div class="chat-peer-info">
						<span class="chat-peer-name">
							{#if chatChannelInfo?.channel_type === 'team'}
								{chatChannelInfo.team_names[0]}
							{:else}
								{(chatChannelInfo?.team_names || []).join(' vs ')}
							{/if}
						</span>
						<span class="chat-peer-team">
							{chatChannelInfo?.channel_type === 'team' ? 'Chat d\'équipe' : 'Chat inter-équipes'}
							 · {chatChannelMembers.length} membres
						</span>
					</div>
					<span class="group-type-badge {chatChannelInfo?.channel_type}">
						{chatChannelInfo?.channel_type === 'team' ? 'ÉQUIPE' : 'INTER'}
					</span>
					<button class="chat-close" on:click={closeChat} title="Fermer">✕</button>
				</div>

				<div class="chat-messages" bind:this={chatEl}>
					{#if chatMessages.length === 0}
						<div class="chat-no-msg"><p>Aucun message. Lancez la conversation !</p></div>
					{:else}
						{#each chatMessages as msg}
							<div class="chat-bubble {msg.sender_id === currentUser?.id ? 'mine' : 'theirs'}">
								{#if msg.sender_id !== currentUser?.id}
									<span class="bubble-sender">{msg.sender_name}</span>
								{/if}
								<div class="bubble-content">{msg.content}</div>
								<span class="bubble-time">{timeAgo(msg.created_at)}</span>
							</div>
						{/each}
					{/if}
				</div>

				<div class="chat-input-bar">
					<textarea class="chat-input" bind:value={chatInput} on:keydown={handleKeydown} placeholder="Écrire au groupe..." rows="1"></textarea>
					<button class="chat-send" on:click={sendMessage} disabled={!chatInput.trim()}>
						<span>➤</span>
					</button>
				</div>
			{/if}
		</div>
	</div>
</div>

<style>
	.players-page { display: flex; flex-direction: column; gap: 1rem; height: calc(100vh - 4rem); }
	.players-header { display: flex; align-items: center; justify-content: space-between; padding: 1.2rem 2rem; border-radius: 16px; flex-shrink: 0; }
	.players-header h1 { margin: 0; font-size: 1.3rem; }
	.player-count { font-size: 0.75rem; font-weight: 700; padding: 0.25rem 0.8rem; border-radius: 20px; background: rgba(59,130,246,0.1); color: var(--accent); border: 1px solid rgba(59,130,246,0.25); }

	/* Layout — fill remaining height, both columns scroll independently */
	.players-layout { display: grid; gap: 0.5rem; flex: 1; min-height: 0; overflow: hidden; }

	/* Directory — scrollable */
	.directory-col { overflow-y: auto; display: flex; flex-direction: column; gap: 0.6rem; padding-right: 0.3rem; padding-bottom: 1rem; }
	.team-section { border-radius: 12px; overflow: visible; flex-shrink: 0; border-left: 3px solid transparent !important; transition: all 0.15s; }
	.team-section.active-chat { background-color: var(--accent-soft) !important; border-left: 3px solid var(--accent) !important; }
	.team-header { display: flex; align-items: center; gap: 0.6rem; padding: 0.7rem 1rem; cursor: pointer; transition: background 0.15s; user-select: none; }
	.team-header:hover { background: var(--hover-tint); }
	.solo-header { cursor: default; }
	.team-chevron { font-size: 0.7rem; color: var(--text-muted); width: 12px; }
	.team-name { font-weight: 800; font-size: 0.8rem; text-transform: uppercase; letter-spacing: 0.06em; color: var(--accent); flex: 1; position: relative; display: inline-flex; align-items: center; gap: 0.4rem; }
	.team-name-badge {
		min-width: 16px; height: 16px; line-height: 16px;
		padding: 0 4px; border-radius: 8px;
		background: #8b5cf6; color: white;
		font-size: 0.5rem; font-weight: 800; text-align: center;
		box-shadow: 0 0 6px rgba(139,92,246,0.5);
		text-transform: none; letter-spacing: 0;
		animation: notif-pulse 2s ease-in-out infinite; will-change: opacity;
	}
	.team-name-badge.team-badge { background: #10b981; box-shadow: 0 0 6px rgba(16,185,129,0.5); }
	.team-name-badge.inter-badge { background: #f59e0b; box-shadow: 0 0 6px rgba(245,158,11,0.5); }
	@keyframes notif-pulse { 0%,100% { opacity: 1; } 50% { opacity: 0.4; } }
	.team-count { font-size: 0.6rem; font-weight: 700; padding: 0.15rem 0.5rem; border-radius: 10px; background: rgba(59,130,246,0.1); color: var(--accent); }

	.team-members { padding: 0 0.5rem 0.5rem; display: flex; flex-direction: column; gap: 0.3rem; }

	/* Player card — clickable row */
	.player-card { border-radius: 8px; padding: 0.1rem; transition: all 0.15s; cursor: pointer; }
	.player-card:hover { background: var(--hover-tint); }
	.player-card.active-chat { background: rgba(59,130,246,0.08); border-left: 3px solid var(--accent); }
	.player-card.has-unread { background: rgba(139,92,246,0.06); }
	.player-card.has-unread:not(.active-chat) { border-left: 3px solid #8b5cf6; }
	.player-main { display: flex; align-items: center; gap: 0.6rem; padding: 0.5rem 0.6rem; }
	.player-avatar { width: 30px; height: 30px; border-radius: 50%; background: var(--bg-tertiary); display: flex; align-items: center; justify-content: center; font-size: 0.7rem; font-weight: 800; color: var(--accent); border: 1px solid rgba(59,130,246,0.2); flex-shrink: 0; position: relative; }
	.player-avatar.solo { border-color: var(--glass-border); color: var(--text-dim); }
	.player-info { flex: 1; min-width: 0; display: flex; flex-direction: column; }
	.player-username { font-weight: 700; font-size: 0.8rem; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
	.player-pts { font-size: 0.6rem; color: var(--text-muted); font-weight: 600; }

	/* Per-player unread badge */
	.player-unread-badge {
		position: absolute; top: -4px; right: -6px;
		min-width: 16px; height: 16px; line-height: 16px;
		padding: 0 4px; border-radius: 8px;
		background: #8b5cf6; color: white;
		font-size: 0.5rem; font-weight: 800; text-align: center;
		box-shadow: 0 0 6px rgba(139,92,246,0.5);
	}

	.player-actions { display: flex; gap: 0.25rem; flex-shrink: 0; }
	.action-btn { width: 28px; height: 28px; border-radius: 6px; border: 1px solid var(--glass-border); background: transparent; cursor: pointer; font-size: 0.7rem; display: flex; align-items: center; justify-content: center; transition: all 0.15s; text-decoration: none; }
	.action-btn:hover { background: var(--hover-tint); transform: translateY(-1px); }
	.action-btn.seat:hover { border-color: rgba(16,185,129,0.4); }
	.action-btn.pts:hover, .action-btn.pts.expanded { border-color: rgba(251,191,36,0.4); background: rgba(251,191,36,0.06); }

	/* Points detail */
	.points-detail { padding: 0.4rem 0.6rem 0.6rem 3rem; display: flex; flex-direction: column; gap: 0.25rem; cursor: default; }
	.pts-total { font-size: 0.7rem; font-weight: 700; color: var(--accent); margin-bottom: 0.2rem; }
	.pts-row { display: flex; align-items: center; gap: 0.5rem; font-size: 0.65rem; padding: 0.2rem 0.4rem; border-radius: 4px; }
	.pts-row:nth-child(odd) { background: rgba(59,130,246,0.03); }
	.pts-rank { font-weight: 800; min-width: 24px; }
	.pts-tourney { flex: 1; font-weight: 600; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
	.pts-game { font-size: 0.55rem; color: var(--text-muted); }
	.pts-val { font-weight: 800; color: var(--success); }
	.pts-live { font-size: 0.5rem; font-weight: 800; color: var(--accent); background: rgba(59,130,246,0.12); padding: 0.1rem 0.3rem; border-radius: 4px; }
	.pts-loading { font-size: 0.8rem; }
	.pts-empty { font-size: 0.65rem; color: var(--text-muted); font-style: italic; }

	/* Breakdown chips in points detail */
	.pts-bp-wrap { display: flex; gap: 0.2rem; flex-wrap: wrap; }
	.pts-bp { font-size: 0.5rem; font-weight: 700; padding: 0.05rem 0.3rem; border-radius: 3px; cursor: help; white-space: nowrap; }
	.pts-bp-place { color: #fbbf24; background: rgba(251,191,36,0.1); }
	.pts-bp-score { color: #818cf8; background: rgba(129,140,248,0.1); }
	.pts-bp-parti { color: var(--text-muted); background: var(--surface-sunken); }

	/* Resizer and Chat column */
	.resizer { width: 8px; cursor: col-resize; border-radius: 4px; transition: background 0.2s; position: relative; z-index: 10; margin: 0 -4px; }
	.resizer:hover, .resizer.active { background: var(--accent); opacity: 0.5; }

	.chat-col { display: flex; flex-direction: column; overflow: hidden; border-radius: 12px; min-width: 0; }
	.chat-empty { display: flex; flex-direction: column; align-items: center; justify-content: center; flex: 1; gap: 0.5rem; color: var(--text-muted); font-size: 0.85rem; }
	.chat-empty-icon { font-size: 2.5rem; opacity: 0.3; }

	.chat-header { display: flex; align-items: center; gap: 0.7rem; padding: 0.8rem 1rem; border-bottom: 1px solid var(--glass-border); flex-shrink: 0; }
	.chat-peer-avatar { width: 32px; height: 32px; border-radius: 50%; background: var(--bg-tertiary); display: flex; align-items: center; justify-content: center; font-weight: 800; font-size: 0.75rem; color: var(--accent); border: 1px solid rgba(59,130,246,0.2); }
	.chat-peer-info { flex: 1; }
	.chat-peer-name { font-weight: 700; font-size: 0.85rem; display: block; }
	.chat-peer-team { font-size: 0.6rem; color: var(--text-muted); }
	.chat-seat-link { font-size: 0.6rem; font-weight: 700; color: var(--accent); text-decoration: none; padding: 0.2rem 0.5rem; border-radius: 4px; background: rgba(59,130,246,0.08); border: 1px solid rgba(59,130,246,0.2); transition: all 0.15s; }
	.chat-seat-link:hover { background: rgba(59,130,246,0.2); }
	.chat-close { background: transparent; border: none; cursor: pointer; font-size: 1rem; color: var(--text-muted); padding: 0.3rem; border-radius: 6px; transition: all 0.15s; }
	.chat-close:hover { background: rgba(239,68,68,0.1); color: var(--danger); }

	/* Messages */
	.chat-messages { flex: 1; overflow-y: auto; padding: 0.8rem; display: flex; flex-direction: column; gap: 0.4rem; }
	.chat-no-msg { display: flex; align-items: center; justify-content: center; flex: 1; color: var(--text-muted); font-size: 0.8rem; }

	.chat-bubble { max-width: 80%; padding: 0.5rem 0.75rem; border-radius: 12px; font-size: 0.8rem; line-height: 1.45; word-break: break-word; }
	.chat-bubble.mine { align-self: flex-end; background: var(--accent); color: white; border-bottom-right-radius: 4px; }
	.chat-bubble.theirs { align-self: flex-start; background: var(--surface-raised); border: 1px solid var(--glass-border); border-bottom-left-radius: 4px; }
	.bubble-content { white-space: pre-wrap; }
	.bubble-time { display: block; font-size: 0.5rem; opacity: 0.6; margin-top: 0.2rem; text-align: right; }
	.chat-bubble.theirs .bubble-time { text-align: left; }

	/* Input bar */
	.chat-input-bar { display: flex; align-items: flex-end; gap: 0.5rem; padding: 0.6rem 0.8rem; border-top: 1px solid var(--glass-border); flex-shrink: 0; }
	.chat-input { flex: 1; resize: none; border: 1px solid var(--glass-border); border-radius: 10px; padding: 0.5rem 0.7rem; font-size: 0.8rem; background: var(--surface-sunken); color: var(--text-main); font-family: inherit; outline: none; transition: border-color 0.15s; max-height: 80px; }
	.chat-input:focus { border-color: var(--accent); }
	.chat-send { width: 36px; height: 36px; border-radius: 50%; background: var(--accent); border: none; color: white; cursor: pointer; display: flex; align-items: center; justify-content: center; font-size: 1rem; transition: all 0.15s; flex-shrink: 0; }
	.chat-send:hover:not(:disabled) { transform: scale(1.08); box-shadow: 0 0 12px var(--accent-glow); }
	.chat-send:disabled { opacity: 0.3; cursor: not-allowed; }

	/* Loading */
	.loading-state { text-align: center; padding: 3rem; border-radius: 16px; font-size: 0.85rem; color: var(--text-muted); }

	/* Group Chat (AXE-12) */
	.team-chat-btn {
		padding: 0.3rem 0.7rem; border-radius: 8px; border: 1px solid var(--glass-border);
		background: transparent; cursor: pointer; font-size: 0.65rem; font-weight: 700;
		display: flex; align-items: center; gap: 0.3rem;
		transition: all 0.2s; position: relative; flex-shrink: 0;
		color: var(--text-dim); white-space: nowrap;
	}
	.team-chat-btn:hover { background: rgba(139,92,246,0.1); border-color: rgba(139,92,246,0.4); transform: translateY(-1px); color: #8b5cf6; }
	.team-chat-btn.has-unread {
		border-color: #8b5cf6; color: #8b5cf6;
		background: rgba(139,92,246,0.08);
		animation: btn-glow 2s ease-in-out infinite; will-change: opacity, box-shadow;
	}
	@keyframes btn-glow {
		0%, 100% { box-shadow: 0 0 4px rgba(139,92,246,0.2); }
		50% { box-shadow: 0 0 12px rgba(139,92,246,0.5); }
	}
	.team-unread-badge {
		position: absolute; top: -5px; right: -6px;
		min-width: 14px; height: 14px; line-height: 14px;
		padding: 0 3px; border-radius: 7px;
		background: #8b5cf6; color: white;
		font-size: 0.45rem; font-weight: 800; text-align: center;
		box-shadow: 0 0 6px rgba(139,92,246,0.5);
	}
	.chat-group-icon { font-size: 1.4rem; flex-shrink: 0; }
	.group-type-badge {
		font-size: 0.5rem; font-weight: 800; padding: 0.2rem 0.5rem; border-radius: 6px;
		text-transform: uppercase; letter-spacing: 0.08em; flex-shrink: 0;
	}
	.group-type-badge.team { background: rgba(16,185,129,0.12); color: #10b981; border: 1px solid rgba(16,185,129,0.3); }
	.group-type-badge.inter { background: rgba(245,158,11,0.12); color: #f59e0b; border: 1px solid rgba(245,158,11,0.3); }
	.group-header .chat-peer-name { color: #8b5cf6; }
	.bubble-sender {
		display: block; font-size: 0.55rem; font-weight: 800; color: #8b5cf6;
		margin-bottom: 0.15rem; text-transform: uppercase; letter-spacing: 0.03em;
	}
	.awards-section { margin-top: 0.8rem; border-top: 1px dashed var(--glass-border); padding-top: 0.6rem; display: flex; flex-direction: column; gap: 0.35rem; }
	.awards-title { font-size: 0.7rem; font-weight: 800; color: #fbbf24; text-transform: uppercase; letter-spacing: 0.05em; margin-bottom: 0.2rem; }
	.award-chip { display: flex; align-items: flex-start; gap: 0.5rem; background: rgba(251, 191, 36, 0.06); border: 1px solid rgba(251, 191, 36, 0.2); padding: 0.4rem 0.6rem; border-radius: 8px; transition: all 0.2s; text-align: left; }
	.award-chip:hover { background: rgba(251, 191, 36, 0.1); border-color: rgba(251, 191, 36, 0.4); transform: scale(1.02); }
	.award-emoji { font-size: 0.9rem; flex-shrink: 0; }
	.award-text { display: flex; flex-direction: column; gap: 0.05rem; }
	.award-name { font-size: 0.72rem; font-weight: 700; color: var(--text-main); }
	.award-desc { font-size: 0.62rem; color: var(--text-muted); line-height: 1.3; }
</style>
