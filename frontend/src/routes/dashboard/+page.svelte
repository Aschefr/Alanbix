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
</script>

<div class="hq-dashboard">
	<!-- Top Command Bar -->
	<header class="command-bar">
		<div class="cmd-left">
			<h1 class="title-premium">LAN Party Dashboard</h1>
		</div>
		<div class="cmd-center">
			<div class="info-chip glass">
				<span class="chip-label">{$t('dash_stat_event')}</span>
				<span class="chip-value">{stats.event_name || 'Alanbix LAN'}</span>
			</div>
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
	<div class="main-triptych">
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
	<div class="stats-bar">
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
</style>
