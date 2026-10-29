<script>
	import { onMount, onDestroy } from 'svelte';
	import { api } from '$lib/api';
	import { wsMessageStore } from '$lib/ws';
	import { t } from '$lib/i18nStore';
	import PublicChat from '$lib/components/PublicChat.svelte';

	import DashboardLeaderboard from './components/DashboardLeaderboard.svelte';
	import DashboardFloorMap from './components/DashboardFloorMap.svelte';
	import DashboardBracketPreview from './components/DashboardBracketPreview.svelte';
	import DashboardPlayerModal from './components/DashboardPlayerModal.svelte';

	let stats = {
		tournaments: 0,
		players: 0,
		games: 0,
		active: 0,
		leaderboard: []
	};
	let user = null;
	let tournaments = [];
	let roomLayout = { seats: [], tables: [], furniture: [] };
	let allUsers = [];
	let participants = [];
	let dashTeams = [];
	let games = [];
	let selectedRunningIdx = 0;
	let teamLeaderboard = [];
	let previousLeaderboard = [];

	let showPlayerStatsModal = false;
	let selectedPlayerStats = null;
	let loadingPlayerStats = false;

	// Public Chat interactive animations on the map
	let hoveredSeatId = null;
	let activePulsingSeats = {};
	let activeBeams = [];
	let beamCounter = 0;

	// Resizable splitter between Public Chat and Floor Map
	let centerColEl = null;
	let chatSplitRatio = 55; // percentage: 55% chat / 45% map
	let isDraggingSplitter = false;

	if (typeof localStorage !== 'undefined') {
		const savedSplit = localStorage.getItem('alanbix_dash_chat_split');
		if (savedSplit) {
			const parsed = parseFloat(savedSplit);
			if (!isNaN(parsed) && parsed >= 15 && parsed <= 85) {
				chatSplitRatio = parsed;
			}
		}
	}

	function startSplitterDrag(e) {
		e.preventDefault();
		isDraggingSplitter = true;
		if (typeof document !== 'undefined') {
			document.body.style.cursor = 'row-resize';
			document.body.style.userSelect = 'none';
		}
		window.addEventListener('pointermove', onSplitterDrag);
		window.addEventListener('pointerup', stopSplitterDrag);
		window.addEventListener('pointercancel', stopSplitterDrag);
	}

	function onSplitterDrag(e) {
		if (!isDraggingSplitter || !centerColEl) return;
		const rect = centerColEl.getBoundingClientRect();
		if (rect.height <= 0) return;
		const offsetY = e.clientY - rect.top;
		const newRatio = Math.min(Math.max((offsetY / rect.height) * 100, 15), 85);
		chatSplitRatio = Math.round(newRatio * 10) / 10;
	}

	function stopSplitterDrag() {
		if (isDraggingSplitter) {
			isDraggingSplitter = false;
			if (typeof document !== 'undefined') {
				document.body.style.cursor = '';
				document.body.style.userSelect = '';
			}
			if (typeof localStorage !== 'undefined') {
				localStorage.setItem('alanbix_dash_chat_split', String(chatSplitRatio));
			}
		}
		window.removeEventListener('pointermove', onSplitterDrag);
		window.removeEventListener('pointerup', stopSplitterDrag);
		window.removeEventListener('pointercancel', stopSplitterDrag);
	}

	function resetSplitter() {
		chatSplitRatio = 55;
		if (typeof localStorage !== 'undefined') {
			localStorage.setItem('alanbix_dash_chat_split', '55');
		}
	}

	let wsUnsub = null;
	let refreshDebounceTimer = null;
	let isRefreshing = false;
	let pendingRefresh = false;

	function scheduleRefreshAll() {
		if (refreshDebounceTimer) clearTimeout(refreshDebounceTimer);
		const jitter = Math.floor(Math.random() * 100);
		refreshDebounceTimer = setTimeout(async () => {
			if (isRefreshing) {
				pendingRefresh = true;
				return;
			}
			isRefreshing = true;
			try {
				await refreshAll();
			} finally {
				isRefreshing = false;
				if (pendingRefresh) {
					pendingRefresh = false;
					scheduleRefreshAll();
				}
			}
		}, 250 + jitter);
	}

	onMount(async () => {
		await refreshAll();

		// WS: auto-refresh on tournament mutations & public chat seat pulse
		wsUnsub = wsMessageStore.subscribe(msg => {
			if (!msg) return;
			const t = msg.type;
			if (t === 'public_chat_message' && msg.seat_id) {
				triggerSeatPulse(msg.seat_id);
			} else if (
				t === 'tournament_created' || t === 'tournament_updated' || t === 'tournament_deleted' ||
				t === 'tournament_started' || t === 'tournament_closed' ||
				t === 'score_updated' || t === 'ffa_advanced' ||
				t === 'participant_joined' || t === 'participant_left' ||
				t === 'room_updated' || t === 'users_updated' ||
				t === 'teams_updated' || t === 'games_updated' ||
				t === 'config_updated' || t === 'ia_config_updated'
			) {
				scheduleRefreshAll();
			}
		});
	});

	function triggerSeatPulse(seatId) {
		if (!seatId || !roomLayout?.seats) return;
		const seat = roomLayout.seats.find(s => String(s.id) === String(seatId));
		if (!seat) return;

		activePulsingSeats = { ...activePulsingSeats, [seatId]: true };
		const bubbleId = ++beamCounter;
		const sx = seat.x + 25;
		const sy = seat.y + 25;
		const targetY = -40; // top offset

		activeBeams = [...activeBeams, { id: bubbleId, x: sx, startY: sy, endY: targetY }];

		setTimeout(() => {
			activeBeams = activeBeams.filter(b => b.id !== bubbleId);
		}, 950);

		setTimeout(() => {
			const copy = { ...activePulsingSeats };
			delete copy[seatId];
			activePulsingSeats = copy;
		}, 800);
	}

	onDestroy(() => {
		if (refreshDebounceTimer) clearTimeout(refreshDebounceTimer);
		if (wsUnsub) wsUnsub();
		if (typeof window !== 'undefined') {
			window.removeEventListener('pointermove', onSplitterDrag);
			window.removeEventListener('pointerup', stopSplitterDrag);
			window.removeEventListener('pointercancel', stopSplitterDrag);
		}
	});

	async function refreshAll() {
		previousLeaderboard = [...(stats.leaderboard || [])];
		try {
			const [userRes, statsRes, tournamentsRes, layoutRes, roomUsersRes, gamesRes, teamLbRes] = await Promise.all([
				api.get('/me'),
				api.get('/dashboard/stats'),
				api.get('/tournaments'),
				api.get('/room/layout'),
				api.get('/room/users'),
				api.get('/tournaments/games').catch(() => []),
				api.get('/dashboard/team-leaderboard').catch(() => [])
			]);

			user = userRes;
			stats = statsRes;
			tournaments = tournamentsRes;
			const res = layoutRes || { layout: { seats: [], tables: [], furniture: [] } };
			roomLayout = res.layout || { seats: [], tables: [], furniture: [] };
			if (!roomLayout.tables) roomLayout.tables = [];
			if (!roomLayout.seats) roomLayout.seats = [];
			if (!roomLayout.furniture) roomLayout.furniture = [];
			allUsers = roomUsersRes;
			games = gamesRes;
			teamLeaderboard = teamLbRes;

			const activeRunning = tournaments.filter(t => t.status === 'RUNNING');
			if (activeRunning.length > 0) {
				await loadParticipants(activeRunning[selectedRunningIdx]?.id || activeRunning[0].id);
			}
		} catch (err) {
			console.error("Error refreshing dashboard stats:", err);
		}
	}

	async function loadParticipants(tid) {
		try { participants = await api.get(`/tournaments/${tid}/participants`); } catch { participants = []; }
		try { dashTeams = await api.get(`/tournaments/${tid}/teams`); } catch { dashTeams = []; }
	}

	async function selectRunning(idx) {
		selectedRunningIdx = idx;
		if (runningTournaments[idx]) await loadParticipants(runningTournaments[idx].id);
	}

	async function openPlayerStats(username) {
		const foundUser = (allUsers || []).find(u => u.username === username);
		if (!foundUser) return;
		loadingPlayerStats = true;
		showPlayerStatsModal = true;
		selectedPlayerStats = { username, total_points: 0, history: [], awards: [] };
		try {
			const res = await api.get(`/players/${foundUser.id}/points-history`);
			selectedPlayerStats = {
				username,
				total_points: res.total_points,
				history: res.history || [],
				awards: res.awards || []
			};
		} catch (e) {
			console.error("Erreur lors de la récupération des stats du joueur", e);
		} finally {
			loadingPlayerStats = false;
		}
	}

	$: runningTournaments = tournaments.filter(t => t.status === 'RUNNING');
	$: activeTournament = runningTournaments[selectedRunningIdx] || null;

	let mobileActiveTab = 'matches'; // 'matches' | 'chat'

	$: myActiveMatches = (() => {
		const tFunc = $t;
		if (!user || !tournaments || !tournaments.length) return [];
		const myUid = user.id;
		const myTeamName = (user.team_name || '').toLowerCase();
		const list = [];

		for (const tourney of tournaments) {
			if (tourney.status !== 'RUNNING' && tourney.status !== 'OPEN') continue;
			if (!tourney.bracket || !Array.isArray(tourney.bracket)) continue;
			const config = tourney.config || {};
			const useTeams = config.use_teams;
			const teamMap = config._team_map || {};

			for (const m of tourney.bracket) {
				const p = m.p || [];
				if (p.length < 2) continue;
				const score = m.score || [];
				const isCompleted = (score.length >= 2 && ((score[0] !== null && score[0] > 0) || (score[1] !== null && score[1] > 0)));
				if (isCompleted) continue;

				let mySlot = -1;
				for (let i = 0; i < p.length; i++) {
					const pid = p[i];
					if (pid === myUid) { mySlot = i; break; }
					if (useTeams && myTeamName && pid < 0) {
						const tName = (teamMap[String(pid)] || '').toLowerCase();
						if (tName === myTeamName) { mySlot = i; break; }
					}
				}
				if (mySlot === -1) continue;

				let oppPid = null;
				let oppName = tFunc('mobile_opp_tbd');
				let oppUser = null;
				let oppSeat = null;
				let isReady = false;

				if (p.length === 2) {
					oppPid = mySlot === 0 ? p[1] : p[0];
					if (oppPid === 0) {
						oppName = tFunc('mobile_opp_tbd');
						isReady = false;
					} else if (oppPid < 0) {
						oppName = teamMap[String(oppPid)] || tFunc('mobile_team_placeholder', { id: Math.abs(oppPid) });
						isReady = true;
					} else {
						oppUser = (allUsers || []).find(u => u.id === oppPid);
						oppName = oppUser ? oppUser.username : `Joueur #${oppPid}`;
						oppSeat = oppUser?.seat_id || null;
						isReady = true;
					}
				} else {
					// FFA mode (3+ players)
					const otherPids = p.filter((_, idx) => idx !== mySlot);
					isReady = !otherPids.includes(0);
					const oppNames = otherPids.map(pid => {
						if (pid === 0) return 'TBD';
						if (pid < 0) return teamMap[String(pid)] || tFunc('mobile_team_placeholder', { id: Math.abs(pid) });
						const u = (allUsers || []).find(x => x.id === pid);
						return u ? u.username : `Joueur #${pid}`;
					});
					oppName = `Groupe (${oppNames.join(', ')})`;
					oppPid = otherPids.find(pid => pid > 0) || null;
					oppUser = oppPid ? (allUsers || []).find(u => u.id === oppPid) : null;
					oppSeat = oppUser?.seat_id || null;
				}

				const gameObj = (games || []).find(g => g.id === tourney.game_id);
				const gameName = gameObj?.name || tourney.game || 'Tournoi';

				let roundLabel = 'Match';
				if (m.id?.s === 2) {
					roundLabel = `Loser Bracket · Tour ${m.id.r || '?'}`;
				} else if (m.id?.s === 3) {
					roundLabel = `Grande Finale`;
				} else if (m.id?.r) {
					roundLabel = `Tour ${m.id.r}`;
				}

				list.push({
					tournament_id: tourney.id,
					tournament_name: tourney.name,
					game_name: gameName,
					round_label: roundLabel,
					match_id: m.id,
					is_ready: isReady,
					opponent_name: oppName,
					opponent_id: oppPid > 0 ? oppPid : null,
					opponent_seat: oppSeat,
					status_label: isReady ? `⚔️ ${tFunc('mobile_match_ready')}` : `⏳ ${tFunc('mobile_match_waiting')}`
				});
			}
		}
		return list;
	})();
</script>

<div class="hq-dashboard">
	<!-- MOBILE-ONLY HEADER TABS (<= 900px) -->
	<div class="mobile-dash-header mobile-only">
		<div class="mobile-dash-tabs">
			<button
				class="mobile-dash-tab"
				class:active={mobileActiveTab === 'matches'}
				on:click={() => mobileActiveTab = 'matches'}
			>
				<span class="tab-txt">⚔️ {$t('mobile_tab_my_matches')}</span>
				{#if myActiveMatches.length > 0}
					<span class="mobile-badge-count">{myActiveMatches.length}</span>
				{/if}
			</button>
			<button
				class="mobile-dash-tab"
				class:active={mobileActiveTab === 'chat'}
				on:click={() => mobileActiveTab = 'chat'}
			>
				<span class="tab-txt">🌐 {$t('mobile_tab_public_chat')}</span>
			</button>
		</div>
	</div>

	<!-- MOBILE VIEW: MATCHES TAB -->
	<div class="mobile-tab-content mobile-matches-panel mobile-only" class:hidden-on-mobile={mobileActiveTab !== 'matches'}>
		<!-- Active Matches Section -->
		<section class="mobile-section">
			<div class="mobile-section-header">
				<h2>⚔️ {$t('mobile_tab_my_matches')}</h2>
				<span class="badge-pill">{$t('mobile_active_matches_count', { count: myActiveMatches.length, suffix: myActiveMatches.length > 1 ? 's' : '' })}</span>
			</div>

			{#if myActiveMatches.length === 0}
				<div class="empty-matches-card glass">
					<div class="empty-icon">🎯</div>
					<h3>{$t('mobile_empty_matches_title')}</h3>
					<p>{$t('mobile_empty_matches_desc')}</p>
					<a href="/dashboard/tournaments" class="btn btn-sm btn-primary">
						🏆 {$t('mobile_btn_view_tournaments')}
					</a>
				</div>
			{:else}
				<div class="matches-cards-list">
					{#each myActiveMatches as m}
						<div class="match-card glass" class:match-ready={m.is_ready}>
							<div class="match-card-top">
								<span class="match-game-tag">🎮 {m.game_name}</span>
								<span class="match-status-tag" class:tag-ready={m.is_ready}>
									{m.status_label}
								</span>
							</div>

							<div class="match-tourney-title">
								<strong>{m.tournament_name}</strong> · <span class="round-name">{m.round_label}</span>
							</div>

							<div class="match-versus-box">
								<div class="vs-label">{$t('mobile_match_versus')}</div>
								<div class="opponent-name">
									{m.opponent_name}
									{#if m.opponent_seat}
										<a href="/dashboard/map?highlight={m.opponent_seat}" class="seat-link" title="Voir sur le plan">
											📍 {$t('mobile_match_seat_link', { seat: m.opponent_seat })}
										</a>
									{/if}
								</div>
							</div>

							<div class="match-card-actions">
								<a href="/dashboard/tournaments?select={m.tournament_id}" class="btn btn-primary btn-match-action">
									⚔️ {$t('mobile_match_enter_score')} →
								</a>
								{#if m.opponent_id}
									<a href="/dashboard/players?chat={m.opponent_id}" class="btn btn-secondary btn-chat-action" title="Envoyer un message">
										💬 {$t('mobile_match_send_msg')}
									</a>
								{/if}
							</div>
						</div>
					{/each}
				</div>
			{/if}
		</section>

		<!-- Tournaments Summary -->
		<section class="mobile-section">
			<div class="mobile-section-header">
				<h2>🏆 {$t('nav_tournaments')} ({tournaments.length})</h2>
				<a href="/dashboard/tournaments" class="see-all-link">{$t('mobile_see_all')} →</a>
			</div>
			<div class="mobile-tourneys-list">
				{#each (tournaments || []).slice(0, 4) as tourney}
					<a href="/dashboard/tournaments/{tourney.id}" class="mobile-tourney-card glass">
						<div class="tourney-card-info">
							<span class="tourney-name">{tourney.name}</span>
							<span class="tourney-sub">
								🎮 {tourney.game || 'Jeu'} · {tourney.participants_count || 0} participants
							</span>
						</div>
						<span class="tourney-badge badge-{tourney.status.toLowerCase()}">
							{#if tourney.status === 'RUNNING'}🟢 {$t('mobile_status_running')}{:else if tourney.status === 'OPEN'}🔵 {$t('mobile_status_open')}{:else}⚪ {$t('mobile_status_done')}{/if}
						</span>
					</a>
				{/each}
			</div>
		</section>

		<!-- Leaderboard Top 3 -->
		{#if stats.leaderboard && stats.leaderboard.length > 0}
			<section class="mobile-section">
				<div class="mobile-section-header">
					<h2>🏅 {$t('mobile_top_podium_title')}</h2>
				</div>
				<div class="mobile-podium glass">
					{#each stats.leaderboard.slice(0, 3) as p, idx}
						<div class="podium-row">
							<span class="podium-rank">{idx === 0 ? '🥇' : idx === 1 ? '🥈' : '🥉'}</span>
							<span class="podium-name">{p.username}</span>
							{#if p.team_name}
								<span class="podium-team">👥 {p.team_name}</span>
							{/if}
							<span class="podium-pts">{p.points || 0} pts</span>
						</div>
					{/each}
				</div>
			</section>
		{/if}
	</div>

	<!-- MOBILE VIEW: PUBLIC CHAT TAB -->
	<div class="mobile-tab-content mobile-chat-panel mobile-only" class:hidden-on-mobile={mobileActiveTab !== 'chat'}>
		<PublicChat
			{user}
			{allUsers}
			on:seatHover={(e) => hoveredSeatId = e.detail}
			on:seatLeave={() => hoveredSeatId = null}
		/>
	</div>

	<!-- Top Command Bar (Desktop only > 900px) -->
	<header class="command-bar desktop-only">
		<div class="cmd-left">
			<h1 class="title-premium">LAN Party Dashboard</h1>
		</div>
		<div class="cmd-center">
			<div class="info-chip glass">
				<span class="chip-label">{$t('dash_stat_event')}</span>
				<span class="chip-value">{stats.event_name || 'Alanbix LAN'}</span>
			</div>
			{#if user?.team_name}
				<div class="info-chip glass" style="border-color: rgba(59,130,246,0.35); background: rgba(59,130,246,0.08);">
					<span class="chip-label" style="color: var(--accent);">👥 {$t('dash_team_lbl') || 'Équipe'}</span>
					<span class="chip-value" style="color: var(--accent); font-weight: 800;">{user.team_name}</span>
				</div>
			{/if}
			<div class="info-chip glass">
				<span class="chip-label">{$t('dash_stat_players')}</span>
				<span class="chip-value">{stats.players}</span>
			</div>
			<div class="info-chip glass">
				<span class="chip-label">{$t('dash_stat_tournaments')}</span>
				<span class="chip-value">{stats.tournaments}</span>
			</div>
		</div>
		<div class="cmd-right">
			<div class="status-live">
				<span class="pulse"></span> 
				{@html $t('dash_live_status')}
			</div>
		</div>
	</header>

	<!-- 3-Column Main Grid -->
	<div class="main-triptych desktop-only">
		<!-- LEFT: Leaderboard -->
		<DashboardLeaderboard
			{stats}
			{teamLeaderboard}
			{previousLeaderboard}
			on:openPlayerStats={(e) => openPlayerStats(e.detail)}
		/>

		<!-- CENTER COLUMN: Public Chat (Top) + Resizer + Arena Floor Map (Bottom) -->
		<div class="center-column" bind:this={centerColEl}>
			<!-- TOP: Public Chat -->
			<div class="center-chat-panel" class:no-transition={isDraggingSplitter} style="height: {chatSplitRatio}%;">
				<PublicChat
					{user}
					{allUsers}
					on:seatHover={(e) => hoveredSeatId = e.detail}
					on:seatLeave={() => hoveredSeatId = null}
				/>
			</div>

			<!-- SPLITTER DIVIDER / RESIZER -->
			<!-- svelte-ignore a11y-no-static-element-interactions -->
			<div
				class="chat-map-splitter"
				class:dragging={isDraggingSplitter}
				on:pointerdown={startSplitterDrag}
				on:dblclick={resetSplitter}
				title="Glisser pour redimensionner (Double-clic pour réinitialiser)"
			>
				<div class="splitter-handle">
					<span class="splitter-pill"></span>
				</div>
			</div>

			<!-- BOTTOM: Arena Floor Map Preview -->
			<DashboardFloorMap
				{roomLayout}
				{allUsers}
				{user}
				{hoveredSeatId}
				{activePulsingSeats}
				{activeBeams}
				{isDraggingSplitter}
				{chatSplitRatio}
			/>
		</div>

		<!-- RIGHT: Tournament Bracket Preview -->
		<DashboardBracketPreview
			{runningTournaments}
			{activeTournament}
			{selectedRunningIdx}
			{participants}
			{dashTeams}
			{games}
			{user}
			on:selectRunning={(e) => selectRunning(e.detail)}
		/>
	</div>

	<!-- Bottom Stats Row -->
	<div class="stats-bar desktop-only">
		<div class="stat-pill glass">
			<span class="sp-icon">🎮</span>
			<div class="sp-data">
				<span class="sp-val">{stats.games}</span>
				<span class="sp-label">{$t('dash_pill_games')}</span>
			</div>
		</div>
		<div class="stat-pill glass">
			<span class="sp-icon">👥</span>
			<div class="sp-data">
				<span class="sp-val">{stats.players}</span>
				<span class="sp-label">{$t('dash_pill_players')}</span>
			</div>
		</div>
		<div class="stat-pill glass">
			<span class="sp-icon">🏆</span>
			<div class="sp-data">
				<span class="sp-val">{stats.tournaments}</span>
				<span class="sp-label">{$t('dash_pill_tournaments')}</span>
			</div>
		</div>
		<div class="stat-pill glass accent">
			<span class="sp-icon">⚡</span>
			<div class="sp-data">
				<span class="sp-val">{stats.active}</span>
				<span class="sp-label">{$t('dash_pill_active')}</span>
			</div>
		</div>
	</div>
</div>

<DashboardPlayerModal
	bind:show={showPlayerStatsModal}
	{selectedPlayerStats}
	{loadingPlayerStats}
	{allUsers}
	on:close={() => showPlayerStatsModal = false}
/>

<style>
	.hq-dashboard {
		display: flex;
		flex-direction: column;
		gap: 1.5rem;
		height: calc(100vh - 4rem);
	}

	/* Command Bar */
	.command-bar {
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: 1rem;
		flex-shrink: 0;
	}
	.cmd-left h1 {
		font-size: 1.4rem;
		white-space: nowrap;
	}
	.cmd-center {
		display: flex;
		gap: 0.75rem;
	}
	.info-chip {
		display: flex;
		flex-direction: column;
		padding: 0.4rem 1rem;
		border-radius: 10px;
		min-width: 100px;
	}
	.chip-label {
		font-size: 0.6rem;
		color: var(--text-muted);
		text-transform: uppercase;
		font-weight: 700;
		letter-spacing: 0.05em;
	}
	.chip-value {
		font-size: 0.95rem;
		font-weight: 800;
		color: var(--text-main);
	}
	.cmd-right {
		display: flex;
		align-items: center;
	}
	.status-live {
		display: flex;
		align-items: center;
		gap: 0.5rem;
		font-size: 0.8rem;
		color: var(--success);
		font-weight: 700;
		background: rgba(16, 185, 129, 0.08);
		padding: 0.5rem 1rem;
		border-radius: 20px;
		border: 1px solid rgba(16, 185, 129, 0.2);
	}
	.pulse {
		width: 8px;
		height: 8px;
		background: var(--success);
		border-radius: 50%;
		box-shadow: 0 0 8px var(--success);
		animation: pulse-g 2s infinite;
		will-change: opacity;
	}
	@keyframes pulse-g {
		0%, 100% { opacity: 1; }
		50% { opacity: 0.3; }
	}

	/* 3-Column Triptych */
	.main-triptych {
		display: grid;
		grid-template-columns: 280px 1fr 340px;
		gap: 1.2rem;
		flex-grow: 1;
		min-height: 0;
	}

	/* Center Column (Public Chat + Resizer + Arena Map) */
	.center-column {
		display: flex;
		flex-direction: column;
		gap: 0;
		min-height: 0;
		min-width: 0;
		height: 100%;
		position: relative;
	}
	.center-chat-panel {
		min-height: 120px;
		min-width: 0;
		overflow: hidden;
		display: flex;
		flex-direction: column;
		transition: height 0.1s ease-out;
	}
	.no-transition {
		transition: none !important;
	}

	/* Sleek Neon Draggable Splitter */
	.chat-map-splitter {
		height: 14px;
		display: flex;
		align-items: center;
		justify-content: center;
		cursor: row-resize;
		user-select: none;
		-webkit-user-select: none;
		position: relative;
		z-index: 15;
		margin: 0;
		padding: 2px 0;
		transition: background 0.2s ease;
		flex-shrink: 0;
	}
	.chat-map-splitter::before {
		content: '';
		position: absolute;
		left: 8%;
		right: 8%;
		height: 1px;
		background: linear-gradient(90deg, transparent, var(--glass-border, rgba(255,255,255,0.15)), transparent);
		transition: all 0.25s ease;
	}
	.splitter-handle {
		display: flex;
		align-items: center;
		justify-content: center;
		width: 48px;
		height: 8px;
		border-radius: 9999px;
		background: rgba(15, 23, 42, 0.85);
		border: 1px solid var(--glass-border, rgba(255,255,255,0.18));
		box-shadow: 0 2px 6px rgba(0, 0, 0, 0.4);
		transition: all 0.2s ease;
		backdrop-filter: blur(8px);
	}
	.splitter-pill {
		width: 18px;
		height: 2px;
		border-radius: 1px;
		background: var(--text-muted, #94a3b8);
		transition: all 0.2s ease;
	}
	.chat-map-splitter:hover::before,
	.chat-map-splitter.dragging::before {
		background: linear-gradient(90deg, transparent, var(--accent, #6366f1), transparent);
		height: 2px;
		box-shadow: 0 0 10px var(--accent, #6366f1);
	}
	.chat-map-splitter:hover .splitter-handle,
	.chat-map-splitter.dragging .splitter-handle {
		width: 62px;
		border-color: var(--accent, #6366f1);
		background: rgba(99, 102, 241, 0.25);
		box-shadow: 0 0 12px rgba(99, 102, 241, 0.5);
	}
	.chat-map-splitter:hover .splitter-pill,
	.chat-map-splitter.dragging .splitter-pill {
		background: #ffffff;
		width: 28px;
	}

	/* Bottom Stats Bar */
	.stats-bar {
		display: flex;
		gap: 1rem;
		flex-shrink: 0;
	}
	.stat-pill {
		flex: 1;
		display: flex;
		align-items: center;
		gap: 0.75rem;
		padding: 0.8rem 1.2rem;
		border-radius: 12px;
	}
	.stat-pill.accent {
		border-color: var(--accent);
		box-shadow: 0 0 15px var(--accent-glow);
	}
	.sp-icon { font-size: 1.3rem; }
	.sp-data { display: flex; flex-direction: column; }
	.sp-val { font-size: 1.2rem; font-weight: 800; line-height: 1; }
	.sp-label {
		font-size: 0.6rem;
		color: var(--text-muted);
		text-transform: uppercase;
		font-weight: 700;
	}

	/* Mobile Dashboard Styles (<= 900px) */
	.mobile-only {
		display: none;
	}

	@media (max-width: 900px) {
		.desktop-only {
			display: none !important;
		}

		.mobile-only {
			display: flex;
		}

		.hq-dashboard {
			height: auto;
			min-height: calc(100vh - 120px);
			gap: 1rem;
		}

		.mobile-dash-header {
			position: sticky;
			top: 50px;
			z-index: 50;
			background: var(--bg-primary);
			padding: 0.2rem 0 0.5rem;
		}

		.mobile-dash-tabs {
			display: flex;
			gap: 0.5rem;
			background: rgba(15, 23, 42, 0.7);
			padding: 0.3rem;
			border-radius: 12px;
			border: 1px solid var(--glass-border);
			width: 100%;
		}

		.mobile-dash-tab {
			flex: 1;
			display: flex;
			align-items: center;
			justify-content: center;
			gap: 0.5rem;
			padding: 0.55rem 0.8rem;
			border-radius: 8px;
			border: none;
			background: transparent;
			color: var(--text-dim);
			font-weight: 600;
			font-size: 0.88rem;
			cursor: pointer;
			transition: all 0.2s;
		}

		.mobile-dash-tab.active {
			background: var(--accent);
			color: #fff;
			box-shadow: 0 2px 10px var(--accent-glow);
		}

		.mobile-badge-count {
			background: #ef4444;
			color: #fff;
			font-size: 0.65rem;
			font-weight: 800;
			padding: 0.1rem 0.45rem;
			border-radius: 10px;
		}

		.mobile-tab-content {
			display: flex;
			flex-direction: column;
			gap: 1.25rem;
		}

		.hidden-on-mobile {
			display: none !important;
		}

		.mobile-chat-panel {
			height: calc(100vh - 170px);
			border-radius: 14px;
			overflow: hidden;
		}

		/* Mobile Matches Section */
		.mobile-section {
			display: flex;
			flex-direction: column;
			gap: 0.75rem;
		}

		.mobile-section-header {
			display: flex;
			align-items: center;
			justify-content: space-between;
		}

		.mobile-section-header h2 {
			font-size: 1.05rem;
			margin: 0;
			color: #f1f5f9;
			font-weight: 700;
		}

		.badge-pill {
			font-size: 0.72rem;
			font-weight: 700;
			padding: 0.15rem 0.55rem;
			border-radius: 8px;
			background: rgba(59, 130, 246, 0.15);
			color: #60a5fa;
			border: 1px solid rgba(59, 130, 246, 0.3);
		}

		.empty-matches-card {
			display: flex;
			flex-direction: column;
			align-items: center;
			justify-content: center;
			text-align: center;
			padding: 2rem 1.2rem;
			border-radius: 14px;
			border: 1px dashed rgba(255, 255, 255, 0.12);
			gap: 0.6rem;
		}
		.empty-icon { font-size: 2.2rem; }
		.empty-matches-card h3 { margin: 0; font-size: 1rem; color: #f1f5f9; }
		.empty-matches-card p { margin: 0; font-size: 0.82rem; color: #94a3b8; max-width: 320px; }

		/* Match Cards */
		.matches-cards-list {
			display: flex;
			flex-direction: column;
			gap: 0.85rem;
		}

		.match-card {
			background: rgba(15, 23, 42, 0.8);
			border: 1px solid rgba(255, 255, 255, 0.08);
			border-radius: 14px;
			padding: 1rem;
			display: flex;
			flex-direction: column;
			gap: 0.7rem;
			box-shadow: 0 4px 16px rgba(0, 0, 0, 0.3);
			border-left: 4px solid #f59e0b;
		}

		.match-card.match-ready {
			border-left: 4px solid #10b981;
			background: rgba(16, 185, 129, 0.04);
		}

		.match-card-top {
			display: flex;
			align-items: center;
			justify-content: space-between;
			font-size: 0.75rem;
		}

		.match-game-tag {
			font-weight: 700;
			color: var(--accent);
		}

		.match-status-tag {
			font-weight: 800;
			font-size: 0.7rem;
			padding: 0.15rem 0.5rem;
			border-radius: 6px;
			background: rgba(245, 158, 11, 0.15);
			color: #fbbf24;
			border: 1px solid rgba(245, 158, 11, 0.3);
		}

		.match-status-tag.tag-ready {
			background: rgba(16, 185, 129, 0.15);
			color: #34d399;
			border-color: rgba(16, 185, 129, 0.3);
		}

		.match-tourney-title {
			font-size: 0.95rem;
			color: #f8fafc;
		}
		.match-tourney-title .round-name {
			color: #94a3b8;
			font-size: 0.85rem;
		}

		.match-versus-box {
			background: rgba(0, 0, 0, 0.25);
			border: 1px solid rgba(255, 255, 255, 0.05);
			border-radius: 8px;
			padding: 0.6rem 0.75rem;
			display: flex;
			align-items: center;
			gap: 0.6rem;
		}

		.vs-label {
			font-size: 0.75rem;
			color: #94a3b8;
			font-weight: 600;
		}

		.opponent-name {
			font-size: 0.92rem;
			font-weight: 700;
			color: #f1f5f9;
			display: flex;
			align-items: center;
			gap: 0.5rem;
			flex-wrap: wrap;
		}

		.seat-link {
			font-size: 0.72rem;
			color: #10b981;
			background: rgba(16, 185, 129, 0.12);
			border: 1px solid rgba(16, 185, 129, 0.25);
			padding: 0.1rem 0.45rem;
			border-radius: 6px;
			text-decoration: none;
			font-weight: 600;
		}

		.match-card-actions {
			display: flex;
			gap: 0.5rem;
			margin-top: 0.2rem;
		}

		.btn-match-action {
			flex: 1;
			text-align: center;
			text-decoration: none;
			font-size: 0.85rem;
			padding: 0.55rem 0.75rem;
		}

		.btn-chat-action {
			text-decoration: none;
			font-size: 0.85rem;
			padding: 0.55rem 0.75rem;
		}

		/* Mobile Tourneys List */
		.mobile-tourneys-list {
			display: flex;
			flex-direction: column;
			gap: 0.5rem;
		}

		.mobile-tourney-card {
			display: flex;
			align-items: center;
			justify-content: space-between;
			padding: 0.75rem 0.9rem;
			border-radius: 10px;
			border: 1px solid rgba(255, 255, 255, 0.06);
			text-decoration: none;
			gap: 0.75rem;
			transition: background 0.15s;
		}

		.tourney-card-info {
			display: flex;
			flex-direction: column;
			gap: 0.2rem;
			min-width: 0;
		}

		.tourney-name {
			font-size: 0.88rem;
			font-weight: 700;
			color: #f1f5f9;
			overflow: hidden;
			text-overflow: ellipsis;
			white-space: nowrap;
		}

		.tourney-sub {
			font-size: 0.75rem;
			color: #94a3b8;
		}

		.tourney-badge {
			font-size: 0.72rem;
			font-weight: 700;
			padding: 0.2rem 0.55rem;
			border-radius: 6px;
			white-space: nowrap;
		}
		.badge-running { background: rgba(16, 185, 129, 0.15); color: #34d399; }
		.badge-open { background: rgba(59, 130, 246, 0.15); color: #60a5fa; }
		.badge-done, .badge-closed { background: rgba(148, 163, 184, 0.15); color: #94a3b8; }

		.see-all-link {
			font-size: 0.8rem;
			color: var(--accent);
			text-decoration: none;
			font-weight: 600;
		}

		/* Mobile Podium */
		.mobile-podium {
			border-radius: 12px;
			padding: 0.5rem 0.85rem;
			display: flex;
			flex-direction: column;
			gap: 0.5rem;
			border: 1px solid rgba(255, 255, 255, 0.06);
		}

		.podium-row {
			display: flex;
			align-items: center;
			gap: 0.6rem;
			padding: 0.35rem 0;
			font-size: 0.85rem;
		}

		.podium-rank { font-size: 1rem; }
		.podium-name { font-weight: 700; color: #f1f5f9; flex: 1; }
		.podium-team { font-size: 0.75rem; color: #94a3b8; }
		.podium-pts { font-weight: 800; color: #fbbf24; }
	}
</style>
