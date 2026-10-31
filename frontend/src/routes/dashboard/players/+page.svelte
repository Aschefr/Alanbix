<script>
	import { api } from '$lib/api';
	import { onMount, onDestroy, tick } from 'svelte';
	import { wsMessageStore } from '$lib/ws';
	import { page } from '$app/stores';
	import { pmUnreadCount, groupUnreadCount } from '$lib/pmStore';
	import { t } from '$lib/i18nStore';
	import { formatPoints } from '$lib/utils';
	import { resolveMediaUrl } from '$lib/config';
	import PlayerChat from '$lib/components/PlayerChat.svelte';
	import { fitPane } from '$lib/mobileViewport';
	import Icon from '$lib/components/Icon.svelte';

	let players = [];
	let retryTimer = null;
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
	let lastReadMessageId = null;
	let playersFirstUnreadIdx = -1;
	let showScrollToBottom = false;



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
		localStorage.setItem('alanbix_chat_width_v2', chatWidth);
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

	function getAwardEmoji(key) {
		const map = {
			premier: '🏆',
			team: '🛡️',
			bourreau: '⚔️',
			coop: '🤝',
			loup: '🐺',
			participate: '🕊️',
			marathon: '🏃',
			gachette: '🎯',
			passoire: '🥅',
			bye: '🍀',
			suisse: '🇨🇭',
			lb: '🩹'
		};
		return map[key] || '🎁';
	}

	// Group unread counts (AXE-12)
	let groupUnreadMap = {}; // channel_key -> unread count
	let wsUnsub = null;

	function onWindowFocus() {
		loadPlayers(true);
	}

	onMount(async () => {
		window.addEventListener('alanbix:messages-tab', onMessagesTab);
		try { currentUser = await api.get('/me'); } catch {}
		await loadPlayers();
		await loadUnreadMap();
		await loadGroupUnreadMap();

		if (typeof window !== 'undefined') {
			window.addEventListener('focus', onWindowFocus);
		}

		// Restore chat width
		// The conversation gets the larger share by default; the list stays compact
		const savedWidth = localStorage.getItem('alanbix_chat_width_v2');
		chatWidth = savedWidth ? parseInt(savedWidth) : Math.round(window.innerWidth * 0.45);

		// Reopen the last active conversation, on a phone too: like a messaging app, the conversation is the
		// default view and the contact list is one step "back" (a deep link from a notification still wins)
		const savedPeer = localStorage.getItem('alanbix_players_chat');
		const savedGroup = localStorage.getItem('alanbix_players_group_chat');
		// Check URL params for auto-open from notification click
		const urlPeer = $page.url.searchParams.get('chat');
		const urlGroup = $page.url.searchParams.get('group');
		
		if (urlGroup) {
			openGroupChat(decodeURIComponent(urlGroup));
		} else if (urlPeer === 'group') {
			if (currentUser?.team_name) {
				openGroupChat(`team:${currentUser.team_name}`);
			} else if (savedGroup) {
				openGroupChat(savedGroup);
			}
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
			if (msg.type === 'user_presence' && msg.user_id !== undefined) {
				const active = players.find(p => p.id === msg.user_id);
				if (active && active.is_online !== msg.is_online) {
					active.is_online = msg.is_online;
					players = players;
				}
				if (chatMode === 'p2p' && chatPeerId === msg.user_id && chatPeer && chatPeer.is_online !== msg.is_online) {
					chatPeer.is_online = msg.is_online;
					chatPeer = chatPeer;
				}
			}
			if (msg.type === 'users_updated' || msg.type === 'tournament_closed' || msg.type === 'tournament_reopened' ||
				msg.type === 'tournament_created' || msg.type === 'tournament_updated' || msg.type === 'tournament_deleted' ||
				msg.type === 'tournament_started') {
				await loadPlayers(true);
				if (expandedPlayerId) {
					try {
						pointsHistory = await api.get(`/players/${expandedPlayerId}/points-history`);
					} catch { pointsHistory = null; }
				}
			}
			if (msg.type === 'private_message_new') {
				if (chatMode === 'p2p' && chatPeerId === msg.sender_id) {
					unreadMap[msg.sender_id] = 0;
					unreadMap = { ...unreadMap };
					api.get(`/players/messages/${msg.sender_id}`).catch(() => {}).then(() => loadUnreadMap());
				} else {
					loadUnreadMap();
				}
			}
			if (msg.type === 'group_message_new') {
				loadGroupUnreadMap();
			}
		});
	});

	onDestroy(() => {
		clearTimeout(retryTimer);
		if (typeof window !== 'undefined') window.removeEventListener('alanbix:messages-tab', onMessagesTab);
		if (wsUnsub) wsUnsub(); 
		if (typeof window !== 'undefined') {
			window.removeEventListener('focus', onWindowFocus);
			window.removeEventListener('mousemove', doResize);
			window.removeEventListener('mouseup', stopResize);
		}
	});

	async function loadPlayers(silent = false) {
		if (!silent && players.length === 0) loading = true;
		try { 
			const fresh = await api.get('/players'); 
			players = fresh;
			if (chatMode === 'p2p' && chatPeerId && chatPeer) {
				const active = players.find(p => p.id === chatPeerId);
				if (active && chatPeer.is_online !== active.is_online) {
					chatPeer.is_online = active.is_online;
					chatPeer = chatPeer;
				}
			}
		} catch { 
			if (players.length === 0) {
				players = [];
				// A dropped response must not leave the list empty: try again shortly
				if (!retryTimer) retryTimer = setTimeout(() => { retryTimer = null; loadPlayers(true); }, 3000);
			}
		} finally {
			if (!silent) loading = false;
		}
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



	function handleChatScroll() {
		if (!chatEl) return;
		showScrollToBottom = chatEl.scrollTop + chatEl.clientHeight < chatEl.scrollHeight - 300;
	}


	// Reactive unread short-list computation
	$: unreadPeers = players.filter(p => (unreadMap[p.id] || 0) > 0);
	$: unreadGroups = Object.entries(groupUnreadMap)
		.filter(([_, count]) => count > 0)
		.map(([key, count]) => {
			const isTeam = key.startsWith('team:');
			const label = isTeam ? key.slice(5) : key.slice(6);
			return { key, label, count, isTeam };
		});
	$: totalUnreadChats = unreadPeers.length + unreadGroups.length;

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
		Object.values(teams).forEach(arr => arr.sort((a, b) => ((unreadMap[b.id] || 0) - (unreadMap[a.id] || 0)) || (b.points - a.points)));
		noTeam.sort((a, b) => ((unreadMap[b.id] || 0) - (unreadMap[a.id] || 0)) || (b.points - a.points));
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
		const found = players.find(p => p.id === peerId);
		chatPeer = found ? { ...found } : { id: peerId };
		chatChannelKey = null;
		chatChannelInfo = null;
		chatChannelMembers = [];
		localStorage.setItem('alanbix_players_chat', String(peerId));
		localStorage.removeItem('alanbix_players_group_chat');
		await loadUnreadMap();
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
		const channel_type = channelKey.startsWith('team:') ? 'team' : 'inter';
		const team_names = channel_type === 'team' ? [channelKey.slice(5)] : channelKey.slice(6).split('|');
		chatChannelInfo = { channel_key: channelKey, channel_type, team_names };
		chatChannelMembers = players.filter(p => team_names.includes(p.team_name));
		localStorage.setItem('alanbix_players_group_chat', channelKey);
		localStorage.removeItem('alanbix_players_chat');
		await loadGroupUnreadMap();
	}

	// Phone: the conversation left through the back arrow, offered again from the contact list
	let resumable = null; // { kind: 'p2p', peerId, label } | { kind: 'group', key, label }

	function resumeChat() {
		if (!resumable) return;
		const r = resumable;
		if (r.kind === 'p2p') openChat(r.peerId); else openGroupChat(r.key);
	}

	// Tapping the Messages tab again, while on the contact list, goes back to the last conversation
	function onMessagesTab() {
		if (chatMode === null) resumeChat();
	}

	function closeChat() {
		if (chatMode === 'p2p' && chatPeerId) {
			resumable = { kind: 'p2p', peerId: chatPeerId, label: chatPeer?.username || '' };
		} else if (chatMode === 'group' && chatChannelKey) {
			const info = chatChannelInfo;
			resumable = { kind: 'group', key: chatChannelKey, label: (info?.team_names || []).join(' · ') };
		}
		chatMode = null;
		chatPeerId = null;
		chatPeer = null;
		chatChannelKey = null;
		chatChannelInfo = null;
		chatChannelMembers = [];
		// On a phone "back" only returns to the contact list: the last conversation is kept so the Messages
		// tab reopens it next time. On a computer closing the chat forgets it.
		if (!(typeof window !== 'undefined' && window.innerWidth <= 900)) {
			localStorage.removeItem('alanbix_players_chat');
			localStorage.removeItem('alanbix_players_group_chat');
		}
		if (typeof window !== 'undefined' && window.history && ($page.url.searchParams.has('chat') || $page.url.searchParams.has('group'))) {
			const cleanUrl = window.location.pathname;
			window.history.replaceState({}, '', cleanUrl);
		}
	}

	// Reactive route param listener for in-app navigation & notification taps while on page
	let lastAppliedQuery = null;
	$: if ($page.url && players.length > 0) {
		const currentQuery = $page.url.search;
		if (lastAppliedQuery !== null && currentQuery !== lastAppliedQuery) {
			lastAppliedQuery = currentQuery;
			const pGroup = $page.url.searchParams.get('group');
			const pChat = $page.url.searchParams.get('chat');
			if (pGroup) {
				openGroupChat(decodeURIComponent(pGroup));
			} else if (pChat === 'group') {
				if (currentUser?.team_name) openGroupChat(`team:${currentUser.team_name}`);
			} else if (pChat) {
				const peer = parseInt(pChat);
				if (peer && peer !== currentUser?.id && peer !== chatPeerId) {
					openChat(peer);
				}
			}
		} else if (lastAppliedQuery === null) {
			lastAppliedQuery = currentQuery;
		}
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

	function getRankEmoji(rank) {
		if (rank === 1) return '🥇';
		if (rank === 2) return '🥈';
		if (rank === 3) return '🥉';
		return rank ? `#${rank}` : '—';
	}


</script>

<div class="players-page animate-in" class:chat-active-mobile={chatMode !== null} use:fitPane={chatMode !== null}>
	<header class="players-header">
		<h1 class="title-premium page-title-icon"><Icon name="users" size={22} /> {$t('players_title')}</h1>
		<span class="player-count">{$t('players_subtitle', { count: players.length, plural: players.length > 1 ? 's' : '' })}</span>
	</header>

	<div class="players-layout" style="grid-template-columns: minmax(0, 1fr) 8px {chatWidth}px;">
		<!-- LEFT: Player directory -->
		<div class="directory-col" class:mobile-hidden={chatMode !== null}>
			{#if resumable && chatMode === null}
				<button type="button" class="resume-chat-bar glass" on:click={resumeChat}>
					<Icon name="chat" size={15} />
					<span class="resume-chat-text">{$t('players_resume_chat', { name: resumable.label })}</span>
					<Icon name="chevron-right" size={15} />
				</button>
			{/if}

			{#if totalUnreadChats > 0}
				<div class="unread-shortlist-bar glass">
					<div class="unread-shortlist-header">
						<span class="unread-shortlist-title">
							<Icon name="chat" size={13} />
							<span>{$t('players_unread_shortlist_title')}</span>
						</span>
						<span class="unread-total-badge">{totalUnreadChats}</span>
					</div>
					<div class="unread-chips-row">
						{#each unreadPeers as p (p.id)}
							<button
								type="button"
								class="unread-chip glass"
								class:active={chatMode === 'p2p' && chatPeerId === p.id}
								on:click={() => openChat(p.id)}
								title="{p.username} ({unreadMap[p.id]})"
							>
								<div class="unread-chip-avatar">
									{#if p.avatar_url}
										<img src={resolveMediaUrl(p.avatar_url)} alt="" />
									{:else}
										<span>{p.username[0].toUpperCase()}</span>
									{/if}
									{#if p.is_online}
										<span class="chip-online-dot"></span>
									{/if}
								</div>
								<span class="unread-chip-name">{p.username}</span>
								<span class="unread-chip-count">{unreadMap[p.id]}</span>
							</button>
						{/each}
						{#each unreadGroups as g (g.key)}
							<button
								type="button"
								class="unread-chip unread-chip-group glass"
								class:active={chatMode === 'group' && chatChannelKey === g.key}
								on:click={() => openGroupChat(g.key)}
								title="{g.label} ({g.count})"
							>
								<div class="unread-chip-icon">
									{#if g.isTeam}
										<Icon name="shield" size={12} />
									{:else}
										<Icon name="swords" size={12} />
									{/if}
								</div>
								<span class="unread-chip-name">{g.label}</span>
								<span class="unread-chip-count">{g.count}</span>
							</button>
						{/each}
					</div>
				</div>
			{/if}

			{#if currentUser?.team_name}
				<button type="button" class="my-team-quick-bar glass" on:click={(e) => openTeamChat(e, currentUser.team_name)}>
					<span>🛡️ {$t('players_my_team_chat_btn', { team: currentUser.team_name })}</span>
					{#if (teamUnreads[currentUser.team_name]?.total || 0) > 0}
						<span class="team-name-badge team-badge">{teamUnreads[currentUser.team_name].total}</span>
					{/if}
					<span style="margin-left:auto;font-size:0.75rem;color:var(--accent);">💬 →</span>
				</button>
			{/if}
			{#if loading && players.length === 0}
				<div class="loading-state glass"><span>⏳</span> {$t("login_checking")}</div>
			{:else}
				{#each grouped.teams as [teamName, members] (teamName)}
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
										🛡️ {$t('players_chat_type_team')}
									{:else}
										⚔️ {$t('players_chat_type_inter')}
									{/if}
								</button>
							{/if}
						</div>
						<div class="team-members">
							{#each members as player (player.id)}
								<!-- svelte-ignore a11y-click-events-have-key-events -->
								<!-- svelte-ignore a11y-no-static-element-interactions -->
								<div class="player-card" class:active-chat={chatPeerId === player.id} class:has-unread={(unreadMap[player.id] || 0) > 0} on:click={() => openChat(player.id)}>
									<div class="player-main">
										<div class="avatar-wrapper" style="position: relative; display: inline-block; flex-shrink: 0;">
											<div class="player-avatar avatar-shape-{player.avatar_shape || 'circle'}">
												{#if player.avatar_url}
													<img src={resolveMediaUrl(player.avatar_url)} alt="" class="player-avatar-img" on:error={(e) => { e.currentTarget.style.display = "none"; }} />
												{:else}
													{player.username[0].toUpperCase()}
												{/if}
												{#if (unreadMap[player.id] || 0) > 0}
													<span class="player-unread-badge">{unreadMap[player.id]}</span>
												{/if}
											</div>
											{#if player.is_online}
												<span class="online-indicator" title={$t('players_status_online')}></span>
											{/if}
										</div>
										<div class="player-info">
											<span class="player-username">{player.username}</span>
											<span class="player-pts">{formatPoints(player.points)} {$t('common_pts')}</span>
										</div>
										<div class="player-actions">
											{#if player.seat_id}
												<a href="/dashboard/map?highlight={player.seat_id}" class="action-btn seat" title="{$t('players_tooltip_seat')}" on:click|stopPropagation>📍</a>
											{/if}
											<button class="action-btn pts" on:click={(e) => togglePoints(e, player.id)} title="{$t('players_tooltip_pts')}" class:expanded={expandedPlayerId === player.id}>📊</button>
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
													<div class="pts-total">{$t("players_info_total")} <strong>{formatPoints(pointsHistory.total_points)} {$t('common_pts')}</strong></div>
													{#each pointsHistory.history as h}
														<div class="pts-row">
															<span class="pts-rank">{getRankEmoji(h.rank)}</span>
															<span class="pts-tourney">{h.tournament_name}</span>
															{#if h.game_name}<span class="pts-game">{h.game_name}</span>{/if}
															<span class="pts-val">+{formatPoints(h.total)}</span>
															{#if h.live}<span class="pts-live">{$t('tourneys_badge_live')}</span>{/if}
														</div>
													{/each}
												{:else}
													<span class="pts-empty">{$t("players_pts_none")}</span>
												{/if}
												{#if pointsHistory && pointsHistory.awards && pointsHistory.awards.length > 0}
													<div class="awards-section">
														<div class="awards-title">{$t("admin_tab_awards")}</div>
														{#each pointsHistory.awards as award}
															<div class="award-chip" title={award.description}>
																<span class="award-emoji">{getAwardEmoji(award.award_key)}</span>
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
							<span class="team-name">{$t("dash_modal_team_fallback")}</span>
							<span class="team-count">{grouped.noTeam.length}</span>
						</div>
						<div class="team-members">
							{#each grouped.noTeam as player (player.id)}
								<!-- svelte-ignore a11y-click-events-have-key-events -->
								<!-- svelte-ignore a11y-no-static-element-interactions -->
								<div class="player-card" class:active-chat={chatPeerId === player.id} class:has-unread={(unreadMap[player.id] || 0) > 0} on:click={() => openChat(player.id)}>
									<div class="player-main">
										<div class="avatar-wrapper" style="position: relative; display: inline-block; flex-shrink: 0;">
											<div class="player-avatar solo avatar-shape-{player.avatar_shape || 'circle'}">
												{#if player.avatar_url}
													<img src={resolveMediaUrl(player.avatar_url)} alt="" class="player-avatar-img" on:error={(e) => { e.currentTarget.style.display = "none"; }} />
												{:else}
													{player.username[0].toUpperCase()}
												{/if}
												{#if (unreadMap[player.id] || 0) > 0}
													<span class="player-unread-badge">{unreadMap[player.id]}</span>
												{/if}
											</div>
											{#if player.is_online}
												<span class="online-indicator" title={$t('players_status_online')}></span>
											{/if}
										</div>
										<div class="player-info">
											<span class="player-username">{player.username}</span>
											<span class="player-pts">{formatPoints(player.points)} {$t('common_pts')}</span>
										</div>
										<div class="player-actions">
											{#if player.seat_id}
												<a href="/dashboard/map?highlight={player.seat_id}" class="action-btn seat" title="{$t('players_tooltip_seat')}" on:click|stopPropagation>📍</a>
											{/if}
											<button class="action-btn pts" on:click={(e) => togglePoints(e, player.id)} title="{$t('players_tooltip_pts')}" class:expanded={expandedPlayerId === player.id}>📊</button>
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
													<div class="pts-total">{$t("players_info_total")} <strong>{formatPoints(pointsHistory.total_points)} {$t('common_pts')}</strong></div>
													{#each pointsHistory.history as h}
														<div class="pts-row">
															<span class="pts-rank">{getRankEmoji(h.rank)}</span>
															<span class="pts-tourney">{h.tournament_name}</span>
															<div class="pts-bp-wrap">
																{#if h.placement_pts > 0}<span class="pts-bp pts-bp-place" title={$t('tourneys_pts_placement_short')}>🏅{formatPoints(h.placement_pts)}</span>{/if}
																<span class="pts-bp pts-bp-parti" title={$t('tourneys_pts_participation_short')}>👤{formatPoints(h.participation_pts)}</span>
																{#if h.score_pts > 0}<span class="pts-bp pts-bp-score" title={$t('players_pts_bonus_tooltip')}>⚡{formatPoints(h.score_pts)}</span>{/if}
															</div>
															<span class="pts-val">{h.live ? '~' : '+'}{formatPoints(h.total)}</span>
															{#if h.live}<span class="pts-live">{$t('tourneys_badge_live')}</span>{/if}
														</div>
													{/each}
												{:else}
													<span class="pts-empty">{$t("players_pts_none")}</span>
												{/if}
												{#if pointsHistory && pointsHistory.awards && pointsHistory.awards.length > 0}
													<div class="awards-section">
														<div class="awards-title">{$t("admin_tab_awards")}</div>
														{#each pointsHistory.awards as award}
															<div class="award-chip" title={award.description}>
																<span class="award-emoji">{getAwardEmoji(award.award_key)}</span>
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
		<div class="chat-col glass" class:mobile-hidden={chatMode === null} style="overflow: hidden; display: flex; flex-direction: column;">
			{#if !chatMode}
				<div class="chat-empty">
					<span class="chat-empty-icon">💬</span>
					<p>{$t('players_chat_empty_prompt')}</p>
				</div>
			{:else}
				<PlayerChat
					mode={chatMode}
					peer={chatPeer}
					channelInfo={chatChannelInfo}
					channelMembers={chatChannelMembers}
					{currentUser}
					allUsers={players}
					on:close={closeChat}
					on:messageSent={() => { loadUnreadMap(); loadGroupUnreadMap(); }}
					on:messageRead={(e) => { if (e.detail?.peerId) { unreadMap[e.detail.peerId] = 0; unreadMap = { ...unreadMap }; } loadUnreadMap(); loadGroupUnreadMap(); }}
				/>
			{/if}
		</div>
	</div>
</div>

<style>
	.players-page { display: flex; flex-direction: column; gap: 1rem; height: 100%; }
	.players-header { display: flex; align-items: center; justify-content: space-between; padding: 0.25rem 0.25rem 0.5rem; flex-shrink: 0; background: none; border: none; box-shadow: none; backdrop-filter: none; }
	.players-header h1 { margin: 0; font-size: var(--fs-page); }
	.resume-chat-bar { display: none; }
	@media (max-width: 900px) {
		.resume-chat-bar { display: flex; align-items: center; gap: 0.6rem; width: 100%; padding: 0.7rem 0.9rem; margin-bottom: 0.6rem; border-radius: var(--radius-md); border: 1px solid var(--accent); color: var(--accent); font-weight: 700; font-size: 0.85rem; cursor: pointer; text-align: left; }
		.resume-chat-text { flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
	}
	.player-count { font-size: 0.75rem; font-weight: 700; padding: 0.25rem 0.8rem; border-radius: 20px; background: rgba(59,130,246,0.1); color: var(--accent); border: 1px solid rgba(59,130,246,0.25); }

	/* Layout — fill remaining height, both columns scroll independently */
	.players-layout { display: grid; gap: 0.5rem; flex: 1; min-height: 0; overflow: hidden; }

	/* Directory — scrollable */
	.directory-col { overflow-y: auto; display: flex; flex-direction: column; gap: 0.6rem; padding-right: 0.3rem; padding-bottom: 1rem; }
	.my-team-quick-bar { display: flex; align-items: center; gap: 0.6rem; padding: 0.75rem 1rem; border-radius: 12px; border: 1px solid rgba(16,185,129,0.35); background: rgba(16,185,129,0.1); color: var(--text-main); font-weight: 800; font-size: 0.82rem; cursor: pointer; text-align: left; width: 100%; flex-shrink: 0; transition: all 0.15s; }
	.my-team-quick-bar:hover { background: rgba(16,185,129,0.18); }
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
	.online-indicator {
		position: absolute;
		bottom: -2px;
		right: -2px;
		width: 10px;
		height: 10px;
		background-color: #10b981;
		border: 2px solid var(--bg-primary, #1e293b);
		border-radius: 50%;
		box-shadow: 0 0 8px #10b981;
		z-index: 10;
	}
	.player-info { flex: 1; min-width: 0; display: flex; flex-direction: column; }
	.player-username { font-weight: 700; font-size: 0.8rem; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
	.player-pts { font-size: 0.75rem; color: var(--text-muted); font-weight: 600; }

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

	.chat-col { display: flex; flex-direction: column; overflow: hidden; border-radius: 12px; min-width: 0; position: relative; }
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
	.player-avatar {
		overflow: hidden;
	}
	.player-avatar-img {
		width: 100%;
		height: 100%;
		object-fit: cover;
		border-radius: 50%;
	}
	.chat-peer-avatar {
		overflow: hidden;
	}
	.chat-peer-avatar-img {
		width: 100%;
		height: 100%;
		object-fit: cover;
		border-radius: 50%;
	}

	/* Unread separator & scroll to bottom */
	.unread-separator {
		display: flex;
		align-items: center;
		margin: 1rem 0;
		color: var(--text-muted, #94a3b8);
		font-size: 0.72rem;
		font-weight: 600;
		text-transform: uppercase;
		letter-spacing: 0.05em;
		width: 100%;
	}
	.unread-separator-line {
		flex: 1;
		height: 1px;
		background: linear-gradient(90deg, transparent, rgba(239, 68, 68, 0.4), transparent);
	}
	.unread-separator-text {
		padding: 0 0.6rem;
		color: #f87171;
	}
	.scroll-to-bottom-btn {
		position: absolute;
		bottom: 75px;
		right: 20px;
		background: var(--glass-bg);
		border: 1px solid var(--glass-border);
		color: var(--text-main);
		padding: 0.4rem 0.8rem;
		border-radius: 9999px;
		font-size: 0.78rem;
		cursor: pointer;
		display: flex;
		align-items: center;
		gap: 0.3rem;
		z-index: 10;
		box-shadow: var(--glass-shadow);
		backdrop-filter: blur(10px);
		-webkit-backdrop-filter: blur(10px);
		transition: all 0.2s ease;
	}
	.scroll-to-bottom-btn:hover {
		background: var(--hover-tint);
		transform: translateY(-2px);
	}

	@media (max-width: 900px) {
		.players-page {
			height: auto;
			min-height: calc(100vh - 120px);
		}
		/* Open conversation: fills the measured space above the tab bar, so the message box is never hidden */
		/* the conversation fills the screen edge to edge, between the top bar and the tab bar */
		.players-page.chat-active-mobile {
			margin: -0.5rem -0.5rem calc(-1 * var(--pane-bleed, 0px));
			height: calc(var(--pane-h, calc(100vh - 110px)) + var(--pane-bleed, 0px));
			min-height: 0;
			overflow: hidden;
			gap: 0;
		}
		.players-page.chat-active-mobile .players-header {
			display: none !important;
		}
		.players-page.chat-active-mobile .players-layout {
			height: 100%;
			margin: 0;
			gap: 0;
		}
		.players-page.chat-active-mobile .chat-col {
			height: 100% !important;
			border-radius: 0 !important;
			border: none !important;
			box-shadow: none !important;
		}
		.players-header {
			padding: 0.8rem 1rem;
		}
		.players-layout {
			display: block !important;
			grid-template-columns: none !important;
		}
		.resizer {
			display: none !important;
		}
		.directory-col {
			padding-right: 0;
		}
		.chat-col {
			height: calc(100vh - 130px);
			border-radius: 14px;
		}
		.mobile-hidden {
			display: none !important;
		}
	}

	.unread-shortlist-bar {
		padding: 0.5rem 0.65rem;
		margin-bottom: 0.75rem;
		border-radius: 3px !important;
		display: flex;
		flex-direction: column;
		gap: 0.4rem;
		background: var(--glass-bg);
		border: 1px solid var(--glass-border);
	}
	.unread-shortlist-header {
		display: flex;
		align-items: center;
		justify-content: space-between;
	}
	.unread-shortlist-title {
		font-size: 0.72rem;
		font-weight: 700;
		text-transform: uppercase;
		letter-spacing: 0.05em;
		color: var(--accent);
		display: flex;
		align-items: center;
		gap: 0.35rem;
	}
	.unread-total-badge {
		background: #ef4444;
		color: white;
		font-size: 0.62rem;
		font-weight: 800;
		padding: 0.1rem 0.4rem;
		border-radius: 3px;
	}
	.unread-chips-row {
		display: flex;
		align-items: center;
		gap: 0.4rem;
		overflow-x: auto;
		scrollbar-width: thin;
		padding-bottom: 0.2rem;
	}
	.unread-chip {
		display: flex;
		align-items: center;
		gap: 0.4rem;
		padding: 0.3rem 0.6rem;
		border-radius: 3px !important;
		background: var(--surface-sunken);
		border: 1px solid var(--glass-border);
		cursor: pointer;
		color: var(--text-main);
		font-size: 0.75rem;
		font-weight: 600;
		flex-shrink: 0;
		transition: all 0.15s ease;
	}
	.unread-chip:hover, .unread-chip.active {
		border-color: var(--accent);
		background: var(--accent-soft);
		color: var(--accent);
	}
	.unread-chip-avatar {
		width: 22px;
		height: 22px;
		border-radius: 3px;
		position: relative;
		overflow: hidden;
		background: var(--bg-secondary);
		display: flex;
		align-items: center;
		justify-content: center;
		font-size: 0.7rem;
		font-weight: 700;
	}
	.unread-chip-avatar img {
		width: 100%;
		height: 100%;
		object-fit: cover;
	}
	.chip-online-dot {
		position: absolute;
		bottom: 1px;
		right: 1px;
		width: 5px;
		height: 5px;
		border-radius: 50%;
		background: #22c55e;
	}
	.unread-chip-icon {
		display: flex;
		align-items: center;
		justify-content: center;
		color: var(--accent);
	}
	.unread-chip-name {
		white-space: nowrap;
		max-width: 90px;
		overflow: hidden;
		text-overflow: ellipsis;
	}
	.unread-chip-count {
		background: #ef4444;
		color: white;
		font-size: 0.6rem;
		font-weight: 800;
		padding: 0.1rem 0.35rem;
		border-radius: 3px;
	}
</style>
