<script>
	import { api } from '$lib/api';
	import { onMount, onDestroy } from 'svelte';
	import { wsMessageStore } from '$lib/ws';

	let stats = {
		tournaments: 0,
		players: 0,
		games: 0,
		active: 0,
		leaderboard: []
	};
	let user = null;
	let tournaments = [];
	let roomLayout = { seats: [], tables: [] };
	let allUsers = [];
	let participants = [];
	let games = [];
	let selectedRunningIdx = 0;
	let lbMode = 'players'; // 'players' | 'teams'
	let teamLeaderboard = [];
	let previousLeaderboard = [];
	let expandedTeamIdx = -1;

	let wsUnsub = null;

	onMount(async () => {
		await refreshAll();

		// WS: auto-refresh on tournament mutations
		wsUnsub = wsMessageStore.subscribe(msg => {
			if (!msg) return;
			const t = msg.type;
			if (t === 'tournament_created' || t === 'tournament_updated' || t === 'tournament_deleted' ||
				t === 'tournament_started' || t === 'tournament_closed' ||
				t === 'score_updated' || t === 'ffa_advanced' ||
				t === 'participant_joined' || t === 'participant_left' ||
				t === 'teams_updated') {
				refreshAll();
			}
		});
	});

	onDestroy(() => { if (wsUnsub) wsUnsub(); });

	async function refreshAll() {
		user = await api.get('/me');
		previousLeaderboard = [...(stats.leaderboard || [])];
		stats = await api.get('/dashboard/stats');
		tournaments = await api.get('/tournaments');
		const res = await api.get('/room/layout');
		roomLayout = res.layout || { seats: [], tables: [] };
		if (!roomLayout.tables) roomLayout.tables = [];
		if (!roomLayout.seats) roomLayout.seats = [];
		allUsers = await api.get('/room/users');
		try { games = await api.get('/tournaments/games'); } catch { games = []; }
		roomLayout = roomLayout;
		try { teamLeaderboard = await api.get('/dashboard/team-leaderboard'); } catch { teamLeaderboard = []; }
		if (runningTournaments.length > 0) {
			await loadParticipants(runningTournaments[selectedRunningIdx]?.id || runningTournaments[0].id);
		}
	}

	async function loadParticipants(tid) {
		try { participants = await api.get(`/tournaments/${tid}/participants`); } catch { participants = []; }
	}

	async function selectRunning(idx) {
		selectedRunningIdx = idx;
		if (runningTournaments[idx]) await loadParticipants(runningTournaments[idx].id);
	}

	function getOccupant(seatId) {
		return allUsers.find(u => u.seat_id === seatId);
	}

	$: dashNameMap = (() => {
		const m = {};
		participants.forEach(p => { m[p.user_id] = p.username; });
		// Add team names from tournament config
		const tm = activeTournament?.config?._team_map || {};
		Object.entries(tm).forEach(([id, name]) => { m[id] = name; });
		return m;
	})();

	function getPlayerName(userId, map) {
		if (userId === 0) return 'TBD';
		if (userId < 0) return map[String(userId)] || `Équipe #${Math.abs(userId)}`;
		return map[userId] || `#${userId}`;
	}

	function getRounds(bracket) {
		if (!bracket || !Array.isArray(bracket)) return [];
		const rounds = {};
		bracket.forEach(m => { if (!rounds[m.id.r]) rounds[m.id.r] = []; rounds[m.id.r].push(m); });
		return Object.keys(rounds).sort((a,b) => a-b).map(k => rounds[k]);
	}

	function getRankDelta(username, currentIdx) {
		if (previousLeaderboard.length === 0) return null;
		const prevIdx = previousLeaderboard.findIndex(p => p.username === username);
		if (prevIdx === -1) return { type: 'new', text: 'NEW' };
		if (prevIdx === currentIdx) return null;
		const diff = Math.abs(prevIdx - currentIdx);
		return prevIdx > currentIdx ? { type: 'up', text: '↑' + diff } : { type: 'down', text: '↓' + diff };
	}

	$: occupiedSeats = roomLayout.seats.filter(s => getOccupant(s.id)).length;
	$: totalSeats = roomLayout.seats.length;
	$: runningTournaments = tournaments.filter(t => t.status === 'RUNNING');
	$: activeTournament = runningTournaments[selectedRunningIdx] || null;
	$: bracketRounds = activeTournament ? getRounds(activeTournament.bracket) : [];
	$: activeBracketType = activeTournament?.config?.bracket_type || 'single_elim';

	// --- Pan/Zoom for map preview ---
	let mapVb = { x: 0, y: 0, w: 900, h: 600 };
	let mapVbInit = false;
	let mapPan = null;

	$: if (!mapVbInit && (roomLayout.seats.length > 0 || roomLayout.tables.length > 0)) {
		const items = [...roomLayout.seats.map(s => ({ x: s.x, y: s.y, w: 50, h: 50 })),
			...roomLayout.tables.map(t => ({ x: t.x, y: t.y, w: t.w, h: t.h }))];
		if (items.length > 0) {
			const pad = 40;
			mapVb = {
				x: Math.min(...items.map(i => i.x)) - pad,
				y: Math.min(...items.map(i => i.y)) - pad,
				w: Math.max(...items.map(i => i.x + i.w)) + pad - (Math.min(...items.map(i => i.x)) - pad),
				h: Math.max(...items.map(i => i.y + i.h)) + pad - (Math.min(...items.map(i => i.y)) - pad)
			};
			mapVbInit = true;
		}
	}

	function mapWheel(e) {
		e.preventDefault();
		const svg = e.currentTarget;
		const rect = svg.getBoundingClientRect();
		const mx = (e.clientX - rect.left) / rect.width;
		const my = (e.clientY - rect.top) / rect.height;
		const factor = e.deltaY > 0 ? 1.15 : 0.87;
		const nw = mapVb.w * factor, nh = mapVb.h * factor;
		mapVb.x += (mapVb.w - nw) * mx;
		mapVb.y += (mapVb.h - nh) * my;
		mapVb.w = nw; mapVb.h = nh;
	}
	function mapDown(e) {
		if (e.button === 0) { mapPan = { x: e.clientX, y: e.clientY, vx: mapVb.x, vy: mapVb.y }; }
	}
	function mapMove(e) {
		if (!mapPan) return;
		const svg = e.currentTarget;
		const r = svg.getBoundingClientRect();
		const sx = mapVb.w / r.width, sy = mapVb.h / r.height;
		mapVb.x = mapPan.vx - (e.clientX - mapPan.x) * sx;
		mapVb.y = mapPan.vy - (e.clientY - mapPan.y) * sy;
	}
	function mapUp() { mapPan = null; }

	// --- Pan/Zoom for bracket preview (CSS transform) ---
	let brScale = 0.7, brPanX = 0, brPanY = 0;
	let brDrag = false, brStartX, brStartY;

	function brWheel(e) {
		e.preventDefault();
		const rect = e.currentTarget.getBoundingClientRect();
		const mx = e.clientX - rect.left, my = e.clientY - rect.top;
		const old = brScale;
		brScale *= e.deltaY < 0 ? 1.12 : 0.89;
		brScale = Math.min(Math.max(0.2, brScale), 3);
		brPanX = mx - (mx - brPanX) * (brScale / old);
		brPanY = my - (my - brPanY) * (brScale / old);
	}
	function brDown(e) { brDrag = true; brStartX = e.clientX - brPanX; brStartY = e.clientY - brPanY; }
	function brMove(e) { if (!brDrag) return; brPanX = e.clientX - brStartX; brPanY = e.clientY - brStartY; }
	function brUp() { brDrag = false; }
</script>

<div class="hq-dashboard">
	<!-- Top Command Bar -->
	<header class="command-bar">
		<div class="cmd-left">
			<h1 class="title-premium">LAN Party Dashboard</h1>
		</div>
		<div class="cmd-center">
			<div class="info-chip glass">
				<span class="chip-label">Événement</span>
				<span class="chip-value">{stats.event_name || 'Alanbix LAN'}</span>
			</div>
			<div class="info-chip glass">
				<span class="chip-label">Joueurs</span>
				<span class="chip-value">{stats.players}</span>
			</div>
			<div class="info-chip glass">
				<span class="chip-label">Tournois</span>
				<span class="chip-value">{stats.tournaments}</span>
			</div>
		</div>
		<div class="cmd-right">
			<div class="status-live">
				<span class="pulse"></span> 
				Status: <strong>LIVE</strong>
			</div>
		</div>
	</header>

	<!-- 3-Column Main Grid -->
	<div class="main-triptych">
		<!-- LEFT: Leaderboard -->
		<section class="panel leaderboard-panel glass">
			<div class="panel-header">
				<h2>Leaderboard</h2>
				<div class="lb-tabs">
					<button class="lb-tab {lbMode === 'players' ? 'active' : ''}" on:click={() => lbMode = 'players'}>Joueurs</button>
					<button class="lb-tab {lbMode === 'teams' ? 'active' : ''}" on:click={() => lbMode = 'teams'}>Equipes</button>
				</div>
			</div>
			<div class="leaderboard-list">
				{#if lbMode === 'players'}
				{#each stats.leaderboard as entry, i}
					<div class="lb-row {i < 3 ? 'top-3' : ''}">
						<span class="lb-rank {i === 0 ? 'gold' : i === 1 ? 'silver' : i === 2 ? 'bronze' : ''}">{i + 1}</span>
						<div class="lb-avatar">{entry.username[0].toUpperCase()}</div>
						<div class="lb-info">
							<span class="lb-name">{entry.username}</span>
							<span class="lb-sub">{entry.team_name || 'GamerTag'}</span>
						</div>
						{#if getRankDelta(entry.username, i)}
							<span class="lb-delta {getRankDelta(entry.username, i).type}">{getRankDelta(entry.username, i).text}</span>
						{/if}
						<div class="lb-score">
							<span class="score-val">{entry.points}</span>
							<span class="score-label">Pts</span>
						</div>
					</div>
				{:else}
					<p class="text-dim text-sm" style="padding: 1rem;">Aucun joueur classé pour le moment.</p>
				{/each}
				{:else}
				{#each teamLeaderboard as team, i}
					<div class="lb-row {i < 3 ? 'top-3' : ''} clickable" on:click={() => expandedTeamIdx = expandedTeamIdx === i ? -1 : i}>
						<span class="lb-rank {i === 0 ? 'gold' : i === 1 ? 'silver' : i === 2 ? 'bronze' : ''}">{i + 1}</span>
						<div class="lb-avatar team-av">{team.team_name[0].toUpperCase()}</div>
						<div class="lb-info">
							<span class="lb-name">{team.team_name}</span>
							<span class="lb-sub">{team.member_count} membre{team.member_count > 1 ? 's' : ''} {expandedTeamIdx === i ? '▲' : '▼'}</span>
						</div>
						<div class="lb-score">
							<span class="score-val">{team.score}</span>
							<span class="score-label">Pts</span>
						</div>
					</div>
					{#if expandedTeamIdx === i && team.members}
						<div class="team-expand">
							{#each team.members.sort((a,b) => b.points - a.points) as member}
								<div class="team-member-row">
									<span class="tm-name">👤 {member.username}</span>
									<span class="tm-pts">{member.points} pts</span>
								</div>
							{/each}
						</div>
					{/if}
				{:else}
					<p class="text-dim text-sm" style="padding: 1rem;">Aucune équipe classée.</p>
				{/each}
				{/if}
			</div>
		</section>

		<!-- CENTER: Arena Floor Map Preview -->
		<section class="panel map-panel glass">
			<div class="panel-header">
				<div>
					<h2>Arena Floor Map</h2>
					<span class="subtitle">Gaming Room</span>
				</div>
				<div class="flex-row gap-2">
					<a href="/dashboard/map" class="btn-chip">🗺️ Ouvrir</a>
				</div>
			</div>
			<div class="map-preview-canvas">
				<!-- svelte-ignore a11y-no-static-element-interactions -->
				<svg viewBox="{mapVb.x} {mapVb.y} {mapVb.w} {mapVb.h}" class="mini-map"
					on:wheel={mapWheel}
					on:mousedown={mapDown}
					on:mousemove={mapMove}
					on:mouseup={mapUp}
					on:mouseleave={mapUp}
					style="cursor: {mapPan ? 'grabbing' : 'grab'}"
				>
					<defs>
						<pattern id="dash-grid" width="40" height="40" patternUnits="userSpaceOnUse">
							<path d="M 40 0 L 0 0 0 40" fill="none" stroke="var(--map-grid-stroke)" stroke-width="1"/>
						</pattern>
					</defs>
					<rect width="100%" height="100%" fill="url(#dash-grid)"/>

					{#each roomLayout.tables as table}
						{@const cx = table.x + table.w / 2}
						{@const cy = table.y + table.h / 2}
						<g transform="rotate({table.rotation || 0}, {cx}, {cy})">
							<rect x={table.x} y={table.y} width={table.w} height={table.h} rx="6"
								fill="var(--map-table-fill)" stroke="var(--map-table-stroke)" stroke-width="1.5"/>
							<text x={cx} y={cy + 4} text-anchor="middle" fill="var(--text-muted)" font-size="10" font-weight="700">{table.label}</text>
						</g>
					{/each}

					{#each roomLayout.seats as seat}
						{@const occ = getOccupant(seat.id)}
						{@const scx = seat.x + 25}
						{@const scy = seat.y + 25}
						<g transform="rotate({seat.rotation || 0}, {scx}, {scy})">
							<rect x={seat.x} y={seat.y} width="50" height="50" rx="6"
								fill={occ ? 'var(--map-seat-mine-fill)' : 'var(--map-seat-fill)'}
								stroke={occ ? 'var(--accent)' : 'var(--map-seat-stroke)'}
								stroke-width="1.5"
							/>
							<clipPath id="dclip-{seat.id}">
								<rect x={seat.x + 2} y={seat.y} width="46" height="50"/>
							</clipPath>
							<g clip-path="url(#dclip-{seat.id})">
								<text x={scx} y={seat.y + 13} text-anchor="middle" fill="var(--text-muted)" font-size="6" font-weight="800">{seat.id}</text>
								{#if occ}
									<text x={scx} y={seat.y + 28} text-anchor="middle" fill="var(--map-seat-player-fill)" font-size="7" font-weight="700"
										textLength={occ.username.length > 7 ? 44 : null}
										lengthAdjust="spacingAndGlyphs"
									>{occ.username}</text>
									{#if occ.team_name}
										<text x={scx} y={seat.y + 38} text-anchor="middle" fill="var(--accent)" font-size="5" opacity="0.7"
											textLength={occ.team_name.length > 8 ? 42 : null}
											lengthAdjust="spacingAndGlyphs"
										>{occ.team_name}</text>
									{/if}
								{:else}
									<text x={scx} y={seat.y + 32} text-anchor="middle" fill="var(--text-muted)" font-size="7">Libre</text>
								{/if}
							</g>
						</g>
					{/each}
				</svg>
			</div>
			<div class="map-footer">
				<div class="map-legend">
					<span class="lg-item"><span class="lg-dot occupied"></span> Occupé ({occupiedSeats})</span>
					<span class="lg-item"><span class="lg-dot free"></span> Libre ({totalSeats - occupiedSeats})</span>
				</div>
			</div>
		</section>

		<!-- RIGHT: Tournament Bracket Preview -->
		<section class="panel bracket-panel glass">
			<div class="panel-header">
				<div>
					<h2>{activeTournament?.name || 'Tournois en cours'}</h2>
					<span class="subtitle">{games.find(g => g.id === activeTournament?.game_id)?.name || (runningTournaments.length + ' actif' + (runningTournaments.length > 1 ? 's' : ''))}</span>
				</div>
			</div>
			{#if runningTournaments.length > 0}
				<!-- Tabs -->
				{#if runningTournaments.length > 1}
					<div class="running-tabs">
						{#each runningTournaments as rt, i}
							<button class="rt-tab {selectedRunningIdx === i ? 'active' : ''}" on:click={() => selectRunning(i)}>{rt.name}</button>
						{/each}
					</div>
				{/if}
				<div class="bracket-preview">
					<div class="bracket-info-grid">
						<div class="bi-card">
							<span class="bi-val">{participants.length}</span>
							<span class="bi-label">Joueurs</span>
						</div>
						<div class="bi-card">
							<span class="bi-val">{activeBracketType === 'round_robin' ? 'RR' : activeBracketType === 'double_elim' ? 'DE' : activeBracketType === 'ffa' ? 'FFA' : 'SE'}</span>
							<span class="bi-label">Format</span>
						</div>
						<div class="bi-card">
							<span class="bi-val status-badge {activeTournament?.status?.toLowerCase() || ''}">{activeTournament?.status === 'RUNNING' ? 'EN COURS' : activeTournament?.status === 'CLOSED' ? 'CLÔTURÉ' : activeTournament?.status || ''}</span>
							<span class="bi-label">Status</span>
						</div>
					</div>

					{#if bracketRounds.length > 0}
						{#if activeBracketType === 'ffa'}
							<!-- FFA compact view -->
							<div class="dash-ffa">
								{#each bracketRounds as roundMatches, ri}
									{@const match = roundMatches[0]}
									{@const isLatest = ri === bracketRounds.length - 1}
									<div class="dash-ffa-round" class:ffa-latest={isLatest}>
										<div class="dash-ffa-hdr">Manche {ri+1} · {match.p.length} joueurs</div>
										{#each match.p as pid, pi}
											<div class="dash-ffa-row {match.score?.[pi] === 1 ? 'gold' : match.score?.[pi] === 2 ? 'silver' : match.score?.[pi] === 3 ? 'bronze' : ''}">
												<span class="dash-ffa-pos">{match.score?.[pi] > 0 ? '#' + match.score[pi] : '—'}</span>
												<span style="flex:1">{getPlayerName(pid, dashNameMap)}</span>
												{#if match.score?.[pi] > 0}
													<span class="dash-ffa-score">{match.score[pi]}</span>
												{/if}
											</div>
										{/each}
									</div>
								{/each}
							</div>
						{:else}
							<!-- Duel bracket -->
							<div class="bracket-visual">
								<!-- svelte-ignore a11y-no-static-element-interactions -->
								<div class="dash-bracket-viewport" on:wheel={brWheel} on:mousedown={brDown} on:mousemove={brMove} on:mouseup={brUp} on:mouseleave={brUp} style="cursor: {brDrag ? 'grabbing' : 'grab'}">
									<div class="dash-bracket-canvas" style="transform: translate({brPanX}px, {brPanY}px) scale({brScale});">
										<div class="dash-rounds">
											{#each bracketRounds as roundMatches, ri}
												<div class="dash-round-col">
													<div class="dash-round-hdr">R{ri + 1}</div>
													<div class="dash-matches-col">
														{#each roundMatches as match}
															<div class="dash-match">
																<div class="dm-player {match.p[0] ? 'filled' : ''}">
																	<span>{getPlayerName(match.p[0], dashNameMap)}</span>
																	<span class="dm-score">{match.score?.[0] ?? 0}</span>
																</div>
																<div class="dm-div"></div>
																<div class="dm-player {match.p[1] ? 'filled' : ''}">
																	<span>{getPlayerName(match.p[1], dashNameMap)}</span>
																	<span class="dm-score">{match.score?.[1] ?? 0}</span>
																</div>
															</div>
														{/each}
													</div>
												</div>
											{/each}
										</div>
									</div>
								</div>
							</div>
						{/if}
					{:else}
						<div class="no-bracket-data">
							<span>📊</span>
							<p class="text-dim text-xs">Bracket en attente</p>
						</div>
					{/if}

					<a href="/dashboard/tournaments" class="btn-chip full-width">🏆 Voir les tournois</a>
				</div>
			{:else}
				<div class="no-tournament">
					<span class="no-tourney-icon">🏆</span>
					<p>Aucun tournoi en cours</p>
					{#if user?.is_admin}
						<a href="/dashboard/admin" class="btn-chip">Créer un tournoi</a>
					{/if}
				</div>
			{/if}
		</section>
	</div>

	<!-- Bottom Stats Row -->
	<div class="stats-bar">
		<div class="stat-pill glass">
			<span class="sp-icon">🎮</span>
			<div class="sp-data">
				<span class="sp-val">{stats.games}</span>
				<span class="sp-label">Jeux</span>
			</div>
		</div>
		<div class="stat-pill glass">
			<span class="sp-icon">👥</span>
			<div class="sp-data">
				<span class="sp-val">{stats.players}</span>
				<span class="sp-label">Joueurs</span>
			</div>
		</div>
		<div class="stat-pill glass">
			<span class="sp-icon">🏆</span>
			<div class="sp-data">
				<span class="sp-val">{stats.tournaments}</span>
				<span class="sp-label">Tournois</span>
			</div>
		</div>
		<div class="stat-pill glass accent">
			<span class="sp-icon">⚡</span>
			<div class="sp-data">
				<span class="sp-val">{stats.active}</span>
				<span class="sp-label">En cours</span>
			</div>
		</div>
	</div>
</div>

<style>
	.hq-dashboard { display: flex; flex-direction: column; gap: 1.5rem; height: calc(100vh - 4rem); }

	/* Command Bar */
	.command-bar { display: flex; align-items: center; justify-content: space-between; gap: 1rem; }
	.cmd-left h1 { font-size: 1.4rem; white-space: nowrap; }
	.cmd-center { display: flex; gap: 0.75rem; }
	.info-chip { display: flex; flex-direction: column; padding: 0.4rem 1rem; border-radius: 10px; min-width: 100px; }
	.chip-label { font-size: 0.6rem; color: var(--text-muted); text-transform: uppercase; font-weight: 700; letter-spacing: 0.05em; }
	.chip-value { font-size: 0.95rem; font-weight: 800; color: var(--text-main); }
	.cmd-right { display: flex; align-items: center; }
	.status-live { display: flex; align-items: center; gap: 0.5rem; font-size: 0.8rem; color: var(--success); font-weight: 700; background: rgba(16, 185, 129, 0.08); padding: 0.5rem 1rem; border-radius: 20px; border: 1px solid rgba(16, 185, 129, 0.2); }
	.pulse { width: 8px; height: 8px; background: var(--success); border-radius: 50%; box-shadow: 0 0 8px var(--success); animation: pulse-g 2s infinite; }
	@keyframes pulse-g { 0%, 100% { opacity: 1; } 50% { opacity: 0.3; } }

	/* 3-Column Triptych */
	.main-triptych { display: grid; grid-template-columns: 280px 1fr 280px; gap: 1.2rem; flex-grow: 1; min-height: 0; }
	.panel { display: flex; flex-direction: column; border-radius: 16px; overflow: hidden; }
	.panel-header { padding: 1rem 1.2rem; border-bottom: 1px solid var(--glass-border); display: flex; justify-content: space-between; align-items: flex-start; }
	.panel-header h2 { font-size: 0.85rem; font-weight: 800; text-transform: uppercase; letter-spacing: 0.08em; }
	.panel-header .subtitle { font-size: 0.65rem; color: var(--text-muted); text-transform: uppercase; letter-spacing: 0.05em; }

	/* Leaderboard */
	.leaderboard-panel { min-width: 0; }
	.leaderboard-list { flex-grow: 1; overflow-y: auto; padding: 0.5rem; }
	.lb-row { display: flex; align-items: center; gap: 0.6rem; padding: 0.6rem 0.5rem; border-radius: 10px; margin-bottom: 0.3rem; transition: background 0.15s; border-left: 3px solid transparent; }
	.lb-row:hover { background: var(--hover-tint); }
	.lb-row.top-3 { border-left-color: var(--accent); background: var(--accent-soft); }
	.lb-rank { width: 22px; height: 22px; display: flex; align-items: center; justify-content: center; font-size: 0.7rem; font-weight: 800; border-radius: 6px; background: var(--surface-raised); color: var(--text-dim); }
	.lb-rank.gold { background: rgba(255, 215, 0, 0.15); color: #ffd700; }
	.lb-rank.silver { background: rgba(192, 192, 192, 0.15); color: #c0c0c0; }
	.lb-rank.bronze { background: rgba(205, 127, 50, 0.15); color: #cd7f32; }
	.lb-avatar { width: 28px; height: 28px; border-radius: 50%; background: var(--bg-tertiary); display: flex; align-items: center; justify-content: center; font-size: 0.7rem; font-weight: 700; color: var(--accent); border: 1px solid var(--glass-border); }
	.lb-info { flex-grow: 1; min-width: 0; }
	.lb-name { font-size: 0.8rem; font-weight: 700; display: block; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
	.lb-sub { font-size: 0.55rem; color: var(--text-muted); }
	.lb-score { text-align: right; }
	.score-val { font-size: 0.85rem; font-weight: 800; color: var(--accent); }
	.score-label { font-size: 0.5rem; color: var(--text-muted); display: block; }

	/* AXE-01: Ranking movement indicators */
	.lb-delta { font-size: 0.6rem; font-weight: 800; padding: 0.1rem 0.3rem; border-radius: 4px; min-width: 1.5rem; text-align: center; }
	.lb-delta.up { color: #10b981; background: rgba(16,185,129,0.12); }
	.lb-delta.down { color: #ef4444; background: rgba(239,68,68,0.12); }
	.lb-delta.new { color: #f59e0b; background: rgba(245,158,11,0.12); font-size: 0.5rem; }

	/* AXE-04: Expandable team detail */
	.lb-row.clickable { cursor: pointer; }
	.lb-row.clickable:hover { background: var(--hover-tint); }
	.team-expand { padding: 0.3rem 0.5rem 0.5rem 2.5rem; border-bottom: 1px solid var(--glass-border); }
	.team-member-row { display: flex; justify-content: space-between; align-items: center; padding: 0.2rem 0.4rem; font-size: 0.7rem; border-radius: 4px; }
	.team-member-row:nth-child(odd) { background: rgba(59,130,246,0.04); }
	.tm-name { color: var(--text-secondary); }
	.tm-pts { font-weight: 700; color: var(--accent); font-size: 0.65rem; }

	/* Map Panel */
	.map-panel { min-width: 0; }
	.map-preview-canvas { flex-grow: 1; padding: 0.5rem; min-height: 0; }
	.mini-map { width: 100%; height: 100%; border-radius: 8px; background: var(--surface-sunken); }
	.map-footer { padding: 0.6rem 1rem; border-top: 1px solid var(--glass-border); }
	.map-legend { display: flex; gap: 1.5rem; justify-content: center; font-size: 0.7rem; color: var(--text-dim); }
	.lg-item { display: flex; align-items: center; gap: 0.4rem; }
	.lg-dot { width: 10px; height: 10px; border-radius: 3px; }
	.lg-dot.occupied { background: rgba(59, 130, 246, 0.4); border: 1px solid var(--accent); }
	.lg-dot.free { background: var(--map-seat-fill); border: 1px solid var(--map-seat-stroke); }

	/* Bracket Panel */
	.bracket-panel { min-width: 0; }
	.bracket-preview { flex-grow: 1; display: flex; flex-direction: column; padding: 0.8rem; gap: 0.8rem; }
	.bracket-info-grid { display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 0.5rem; }
	.bi-card { display: flex; flex-direction: column; align-items: center; padding: 0.6rem; background: var(--surface-raised); border-radius: 10px; border: 1px solid var(--glass-border); }
	.bi-val { font-size: 1rem; font-weight: 800; }
	.bi-label { font-size: 0.55rem; color: var(--text-muted); text-transform: uppercase; }
	.status-badge { font-size: 0.7rem; padding: 0.15rem 0.5rem; border-radius: 6px; }
	.status-badge.running { color: var(--accent); background: rgba(59,130,246,0.1); }

	/* Running tournament tabs */
	.running-tabs { display: flex; gap: 0.25rem; padding: 0 0.8rem; overflow-x: auto; border-bottom: 1px solid var(--glass-border); }
	.rt-tab { padding: 0.45rem 0.7rem; font-size: 0.65rem; font-weight: 700; background: none; border: none; border-bottom: 2px solid transparent; color: var(--text-dim); cursor: pointer; white-space: nowrap; transition: all 0.15s; }
	.rt-tab:hover { color: var(--text-main); }
	.rt-tab.active { color: var(--accent); border-bottom-color: var(--accent); }

	/* Bracket visual (CSS transform zoom) */
	.bracket-visual { flex-grow: 1; display: flex; flex-direction: column; min-height: 0; }
	.dash-bracket-viewport { flex-grow: 1; overflow: hidden; border-radius: 8px; border: 1px solid var(--glass-border); background: var(--surface-sunken); min-height: 200px; }
	.dash-bracket-canvas { transform-origin: 0 0; transition: transform 0.08s ease-out; padding: 1rem; display: inline-block; min-width: 100%; }

	/* Dashboard FFA */
	.dash-ffa { display: flex; flex-direction: column; gap: 0.5rem; max-height: 300px; overflow-y: auto; padding: 0.25rem; }
	.dash-ffa-round { border: 1px solid var(--glass-border); border-radius: 8px; padding: 0.5rem; opacity: 0.5; }
	.dash-ffa-round.ffa-latest { opacity: 1; background: rgba(59,130,246,0.05); border-color: rgba(59,130,246,0.2); }
	.dash-ffa-hdr { font-weight: 800; font-size: 0.55rem; text-transform: uppercase; letter-spacing: 1px; color: var(--accent); margin-bottom: 0.3rem; }
	.dash-ffa-row { display: flex; align-items: center; gap: 0.4rem; padding: 0.2rem 0.3rem; font-size: 0.6rem; border-radius: 4px; }
	.dash-ffa-row.gold { background: rgba(255,215,0,0.1); border-left: 2px solid #ffd700; }
	.dash-ffa-row.silver { background: rgba(192,192,192,0.08); border-left: 2px solid #c0c0c0; }
	.dash-ffa-row.bronze { background: rgba(205,127,50,0.08); border-left: 2px solid #cd7f32; }
	.dash-ffa-pos { font-weight: 800; color: var(--accent); min-width: 20px; font-size: 0.55rem; }
	.dash-ffa-score { font-weight: 800; font-size: 0.55rem; color: #fbbf24; background: rgba(251,191,36,0.15); padding: 0.1rem 0.35rem; border-radius: 4px; }
	.dash-ffa-more { font-size: 0.5rem; color: var(--text-dim); padding: 0.15rem 0.3rem; font-style: italic; }
	.dash-rounds { display: flex; gap: 1.5rem; }
	.dash-round-col { display: flex; flex-direction: column; gap: 0.5rem; }
	.dash-round-hdr { text-align: center; font-weight: 700; color: var(--accent); font-size: 0.55rem; text-transform: uppercase; letter-spacing: 1px; }
	.dash-matches-col { display: flex; flex-direction: column; justify-content: space-around; flex-grow: 1; gap: 0.6rem; }
	.dash-match { width: 150px; background: var(--surface-raised); border: 1px solid var(--glass-border); border-radius: 6px; overflow: hidden; }
	.dm-player { display: flex; justify-content: space-between; padding: 0.3rem 0.5rem; font-size: 0.6rem; color: var(--text-muted); background: var(--surface-sunken); }
	.dm-player.filled { color: var(--text-main); background: var(--accent-soft); }
	.dm-player span { white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
	.dm-score { font-weight: 800; color: var(--accent); min-width: 14px; text-align: right; flex-shrink: 0; }
	.dm-div { height: 1px; background: var(--glass-border); }
	.no-bracket-data { display: flex; flex-direction: column; align-items: center; justify-content: center; flex-grow: 1; gap: 0.3rem; padding: 1rem; }

	.no-tournament { display: flex; flex-direction: column; align-items: center; justify-content: center; flex-grow: 1; gap: 0.75rem; padding: 2rem; }
	.no-tourney-icon { font-size: 2.5rem; opacity: 0.3; }
	.no-tournament p { color: var(--text-muted); font-size: 0.85rem; }

	/* Chips / Buttons */
	.btn-chip { display: inline-flex; align-items: center; gap: 0.4rem; padding: 0.4rem 0.9rem; background: var(--map-badge-bg); border: 1px solid var(--map-badge-border); color: var(--accent); border-radius: 8px; font-size: 0.7rem; font-weight: 700; text-decoration: none; transition: all 0.15s; cursor: pointer; }
	.btn-chip:hover { background: var(--map-badge-hover); }
	.btn-chip.full-width { justify-content: center; width: 100%; }

	/* Bottom Stats Bar */
	.stats-bar { display: flex; gap: 1rem; }
	.stat-pill { flex: 1; display: flex; align-items: center; gap: 0.75rem; padding: 0.8rem 1.2rem; border-radius: 12px; }
	.stat-pill.accent { border-color: var(--accent); box-shadow: 0 0 15px var(--accent-glow); }
	.sp-icon { font-size: 1.3rem; }
	.sp-data { display: flex; flex-direction: column; }
	.sp-val { font-size: 1.2rem; font-weight: 800; line-height: 1; }
	.sp-label { font-size: 0.6rem; color: var(--text-muted); text-transform: uppercase; font-weight: 700; }

	/* Leaderboard tabs */
	.lb-tabs { display: flex; gap: 0.2rem; }
	.lb-tab { padding: 0.25rem 0.6rem; font-size: 0.6rem; font-weight: 700; border: 1px solid var(--glass-border); border-radius: 6px; background: transparent; color: var(--text-dim); cursor: pointer; transition: all 0.2s; }
	.lb-tab:hover { border-color: var(--accent); }
	.lb-tab.active { background: var(--accent-soft); border-color: var(--accent); color: var(--accent); }
	.team-av { background: rgba(139,92,246,0.2) !important; color: #a78bfa !important; border-color: rgba(139,92,246,0.3) !important; }
</style>
