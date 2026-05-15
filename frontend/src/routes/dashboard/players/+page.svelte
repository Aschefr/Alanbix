<script>
	import { api } from '$lib/api';
	import { onMount, onDestroy, tick } from 'svelte';
	import { wsMessageStore } from '$lib/ws';
	import { page } from '$app/stores';
	import { pmUnreadCount } from '$lib/pmStore';

	let players = [];
	let currentUser = null;
	let loading = true;

	// Chat state
	let chatPeerId = null;
	let chatPeer = null;
	let chatMessages = [];
	let chatInput = '';
	let chatLoading = false;
	let chatEl = null; // scroll container ref

	// Points detail expand
	let expandedPlayerId = null;
	let pointsHistory = null;
	let pointsLoading = false;

	// Team collapse state
	let collapsedTeams = {};

	// Per-player unread counts
	let unreadMap = {}; // peer_id -> unread count

	let wsUnsub = null;

	onMount(async () => {
		try { currentUser = await api.get('/me'); } catch {}
		await loadPlayers();
		await loadUnreadMap();

		// Restore last selected chat from localStorage
		const savedPeer = localStorage.getItem('alanbix_players_chat');
		// Check URL params for auto-open from notification click
		const urlPeer = $page.url.searchParams.get('chat');
		const targetPeer = urlPeer ? parseInt(urlPeer) : (savedPeer ? parseInt(savedPeer) : null);

		if (targetPeer && targetPeer !== currentUser?.id) {
			openChat(targetPeer);
		}

		wsUnsub = wsMessageStore.subscribe(msg => {
			if (!msg) return;
			if (msg.type === 'private_message_new') {
				// If we have the chat open with this peer, refresh messages
				const peerId = msg.sender_id === currentUser?.id ? msg.receiver_id : msg.sender_id;
				if (chatPeerId && (msg.sender_id === chatPeerId || msg.receiver_id === chatPeerId)) {
					loadChat(chatPeerId, true);
				}
				// Refresh unread map for badge display
				loadUnreadMap();
			}
		});
	});

	onDestroy(() => { if (wsUnsub) wsUnsub(); });

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
			// Sync sidebar badge
			pmUnreadCount.set(total);
		} catch { unreadMap = {}; pmUnreadCount.set(0); }
	}

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
		// Sort each team by points desc
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

	async function openChat(peerId) {
		if (peerId === currentUser?.id) return;
		chatPeerId = peerId;
		// Persist selection
		localStorage.setItem('alanbix_players_chat', String(peerId));
		await loadChat(peerId, false);
		// Refresh unread since opening marks as read
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
		// After reading, refresh unread map (messages got marked as read)
		if (!silent) await loadUnreadMap();
	}

	async function sendMessage() {
		const content = chatInput.trim();
		if (!content || !chatPeerId) return;
		chatInput = '';
		try {
			await api.post(`/players/messages/${chatPeerId}`, { content });
			await loadChat(chatPeerId, true);
		} catch (e) {
			chatInput = content; // Restore on error
		}
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

	function toggleTeam(name) {
		collapsedTeams[name] = !collapsedTeams[name];
		collapsedTeams = collapsedTeams;
	}

	function closeChat() {
		chatPeerId = null;
		chatPeer = null;
		chatMessages = [];
		localStorage.removeItem('alanbix_players_chat');
	}

	function timeAgo(dateStr) {
		if (!dateStr) return '';
		const diff = (Date.now() - new Date(dateStr).getTime()) / 1000;
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

	<div class="players-layout">
		<!-- LEFT: Player directory -->
		<div class="directory-col">
			{#if loading}
				<div class="loading-state glass"><span>⏳</span> Chargement...</div>
			{:else}
				{#each grouped.teams as [teamName, members]}
					<div class="team-section glass">
						<!-- svelte-ignore a11y-click-events-have-key-events -->
						<!-- svelte-ignore a11y-no-static-element-interactions -->
						<div class="team-header" on:click={() => toggleTeam(teamName)}>
							<span class="team-chevron">{collapsedTeams[teamName] ? '▸' : '▾'}</span>
							<span class="team-name">{teamName}</span>
							<span class="team-count">{members.length}</span>
						</div>
						{#if !collapsedTeams[teamName]}
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
												{:else if pointsHistory && pointsHistory.history.length > 0}
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
											</div>
										{/if}
									</div>
								{/each}
							</div>
						{/if}
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
											{:else if pointsHistory && pointsHistory.history.length > 0}
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
										</div>
									{/if}
								</div>
							{/each}
						</div>
					</div>
				{/if}
			{/if}
		</div>

		<!-- RIGHT: Chat panel -->
		<div class="chat-col glass">
			{#if !chatPeerId}
				<div class="chat-empty">
					<span class="chat-empty-icon">💬</span>
					<p>Cliquez sur un joueur pour démarrer une conversation</p>
				</div>
			{:else if chatLoading}
				<div class="chat-empty"><span>⏳</span> Chargement...</div>
			{:else}
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
						<div class="chat-no-msg">
							<p>Aucun message. Envoyez le premier !</p>
						</div>
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
					<textarea
						class="chat-input"
						bind:value={chatInput}
						on:keydown={handleKeydown}
						placeholder="Écrire un message..."
						rows="1"
					></textarea>
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
	.players-layout { display: grid; grid-template-columns: 1fr 380px; gap: 1rem; flex: 1; min-height: 0; overflow: hidden; }

	/* Directory — scrollable */
	.directory-col { overflow-y: auto; display: flex; flex-direction: column; gap: 0.6rem; padding-right: 0.3rem; padding-bottom: 1rem; }
	.team-section { border-radius: 12px; overflow: visible; flex-shrink: 0; }
	.team-header { display: flex; align-items: center; gap: 0.6rem; padding: 0.7rem 1rem; cursor: pointer; transition: background 0.15s; user-select: none; }
	.team-header:hover { background: var(--hover-tint); }
	.solo-header { cursor: default; }
	.team-chevron { font-size: 0.7rem; color: var(--text-muted); width: 12px; }
	.team-name { font-weight: 800; font-size: 0.8rem; text-transform: uppercase; letter-spacing: 0.06em; color: var(--accent); flex: 1; }
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

	/* Chat column */
	.chat-col { border-radius: 16px; display: flex; flex-direction: column; overflow: hidden; min-height: 0; }
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
</style>
