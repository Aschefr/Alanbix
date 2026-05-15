<script>
	import { onMount, onDestroy } from 'svelte';
	import { wsMessageStore } from '$lib/ws';
	import { connectWS } from '$lib/ws';

	const API_URL = 'http://localhost:8000';

	const VIEWS = ['leaderboard', 'teams', 'map', 'bracket', 'info'];
	let currentIdx = 0;
	let paused = false;
	let data = { leaderboard: [], event_name: 'Alanbix LAN' };
	let teamLeaderboard = [];
	let roomLayout = { seats: [], tables: [] };
	let allUsers = [];
	let tournaments = [];
	let games = [];
	let participants = [];
	let specTeams = [];
	let spectatorInfo = '';
	let interval;
	let transClass = 'slide-in';

	async function fetchPublic(path) {
		const res = await fetch(`${API_URL}${path}`);
		if (!res.ok) return null;
		return res.json();
	}

	async function refreshData() {
		try {
			const stats = await fetchPublic('/dashboard/stats');
			if (stats) {
				data.leaderboard = stats.leaderboard || [];
				data.event_name = stats.event_name || 'Alanbix LAN';
			}
			const t = await fetchPublic('/tournaments');
			if (t) tournaments = t;
			const tl = await fetchPublic('/dashboard/team-leaderboard');
			if (tl) teamLeaderboard = tl;
			const layout = await fetchPublic('/room/layout');
			if (layout) {
				roomLayout = layout.layout || { seats: [], tables: [], furniture: [] };
				if (!roomLayout.tables) roomLayout.tables = [];
				if (!roomLayout.seats) roomLayout.seats = [];
				if (!roomLayout.furniture) roomLayout.furniture = [];
			}
			const users = await fetchPublic('/room/users');
			if (users) allUsers = users;
			try { games = (await fetchPublic('/tournaments/games')) || []; } catch { games = []; }
			// Load participants for all active tournaments (RUNNING + DONE)
			let allParticipants = [];
			for (const run of tournaments.filter(t => t.status === 'RUNNING' || t.status === 'DONE')) {
				try {
					const p = (await fetchPublic(`/tournaments/${run.id}/participants`)) || [];
					allParticipants = [...allParticipants, ...p];
				} catch {}
			}
			participants = allParticipants;
			// Load teams for running tournaments (for bracket name resolution)
			let allTeams = [];
			for (const run of tournaments.filter(t => t.status === 'RUNNING' || t.status === 'DONE')) {
				try {
					const t = (await fetchPublic(`/tournaments/${run.id}/teams`)) || [];
					allTeams = [...allTeams, ...t];
				} catch {}
			}
			specTeams = allTeams;
			// Fetch info page content for spectator
			try {
				const info = await fetchPublic('/dashboard/info');
				if (info) spectatorInfo = info.spectator_content || '';
			} catch {}
		} catch (e) { console.error(e); }
	}

	function getOccupant(seatId) {
		return allUsers.find(u => u.seat_id === seatId);
	}

	function getPlayerName(userId) {
		if (userId === 0) return 'TBD';
		// Check team_map for negative IDs (team bracket)
		if (userId < 0) {
			// Primary: config._team_map
			const tmName = runningTournament?.config?._team_map?.[String(userId)];
			if (tmName) return tmName;
			// Fallback: live teams data
			const team = specTeams.find(t => t.id === Math.abs(userId));
			if (team) return team.name;
			return `Équipe #${Math.abs(userId)}`;
		}
		const p = participants.find(pp => pp.user_id === userId);
		return p ? p.username : `#${userId}`;
	}

	function getRounds(bracket) {
		if (!bracket || !Array.isArray(bracket)) return [];
		const rounds = {};
		bracket.forEach(m => { if (!rounds[m.id.r]) rounds[m.id.r] = []; rounds[m.id.r].push(m); });
		return Object.keys(rounds).sort((a,b) => a-b).map(k => rounds[k]);
	}

	function viewHasData(viewName) {
		switch (viewName) {
			case 'leaderboard': return data.leaderboard.length > 0;
			case 'teams': return teamLeaderboard.length > 0;
			case 'map': return roomLayout.seats.length > 0;
			case 'bracket': return runningTournaments.length > 0;
			case 'info': return spectatorInfo.length > 0;
			default: return true;
		}
	}

	function nextView() {
		transClass = '';
		setTimeout(() => {
			// If on bracket with multiple tournaments, cycle tournament first
			if (VIEWS[currentIdx] === 'bracket' && runningTournaments.length > 1) {
				if (bracketTourneyIdx < runningTournaments.length - 1) {
					bracketTourneyIdx++;
					transClass = 'slide-in';
					return;
				} else {
					bracketTourneyIdx = 0;
				}
			}
			let attempts = 0;
			do {
				currentIdx = (currentIdx + 1) % VIEWS.length;
				attempts++;
			} while (!viewHasData(VIEWS[currentIdx]) && attempts < VIEWS.length);
			transClass = 'slide-in';
			if (VIEWS[currentIdx] === 'leaderboard') refreshData();
		}, 50);
	}

	function prevView() {
		transClass = '';
		setTimeout(() => {
			let attempts = 0;
			do {
				currentIdx = (currentIdx - 1 + VIEWS.length) % VIEWS.length;
				attempts++;
			} while (!viewHasData(VIEWS[currentIdx]) && attempts < VIEWS.length);
			transClass = 'slide-in';
		}, 50);
	}

	function handleKey(e) {
		if (e.key === 'ArrowRight') nextView();
		else if (e.key === 'ArrowLeft') prevView();
		else if (e.key === ' ') { e.preventDefault(); paused = !paused; }
	}

	onMount(() => {
		// Apply theme
		const theme = localStorage.getItem('alanbix_theme') || 'dark';
		document.documentElement.setAttribute('data-theme', theme);

		connectWS();
		refreshData();

		interval = setInterval(() => {
			if (!paused) nextView();
		}, 12000);

		const unsubscribe = wsMessageStore.subscribe(msg => {
			if (msg) refreshData();
		});

		return () => {
			clearInterval(interval);
			unsubscribe();
		};
	});

	$: currentView = VIEWS[currentIdx];
	$: runningTournaments = tournaments.filter(t => t.status === 'RUNNING' || t.status === 'DONE');
	let bracketTourneyIdx = 0;
	$: if (runningTournaments.length > 0 && bracketTourneyIdx >= runningTournaments.length) bracketTourneyIdx = 0;
	$: runningTournament = runningTournaments.length > 0 ? runningTournaments[bracketTourneyIdx] : null;
	$: bracketRounds = runningTournament ? getRounds(runningTournament.bracket) : [];
	$: bracketType = runningTournament?.config?.bracket_type || 'single_elim';
	$: specLowerIsBetter = runningTournament?.config?.lower_score_is_better || false;
	$: runningGame = runningTournament ? games.find(g => g.id === runningTournament.game_id) : null;
	$: occupiedSeats = roomLayout.seats.filter(s => getOccupant(s.id)).length;
	$: totalSeats = roomLayout.seats.length;
	$: mapViewBox = (() => {
		const items = [...(roomLayout.seats || []).map(s => ({ x: s.x, y: s.y, w: 50, h: 50 })),
			...(roomLayout.tables || []).map(t => ({ x: t.x, y: t.y, w: t.w, h: t.h })),
			...(roomLayout.furniture || []).map(f => ({ x: f.x, y: f.y, w: f.w, h: f.h }))];
		if (items.length === 0) return '0 0 900 600';
		const pad = 40;
		const minX = Math.min(...items.map(i => i.x)) - pad;
		const minY = Math.min(...items.map(i => i.y)) - pad;
		const maxX = Math.max(...items.map(i => i.x + i.w)) + pad;
		const maxY = Math.max(...items.map(i => i.y + i.h)) + pad;
		return `${minX} ${minY} ${maxX - minX} ${maxY - minY}`;
	})();
</script>

<svelte:window on:keydown={handleKey} />

<div class="spectator-mode" class:bracket-active={currentView === 'bracket' && runningGame?.image_url}>
	{#if currentView === 'bracket' && runningGame?.image_url}
		<div class="game-fullscreen-bg" style="background-image: url({runningGame.image_url})"></div>
		<div class="game-fullscreen-vignette"></div>
	{/if}
	<div class="spec-header">
		<h2 class="spec-event">{data.event_name}</h2>
		<div class="spec-nav">
			{#each VIEWS as v, i}
				<span class="nav-dot {currentIdx === i ? 'active' : ''}" on:click={() => { currentIdx = i; transClass = 'slide-in'; }}></span>
			{/each}
			{#if paused}<span class="pause-badge">⏸ PAUSE</span>{/if}
		</div>
	</div>

	<div class="spec-content {transClass}">
		{#if currentView === 'leaderboard'}
			<div class="spec-view">
				<h1 class="spec-title">🏆 Classement Général</h1>
				<div class="spec-lb">
					{#each data.leaderboard as entry, i}
						<div class="spec-row {i < 3 ? 'spec-top' : ''}">
							<span class="spec-rank {i === 0 ? 'gold' : i === 1 ? 'silver' : i === 2 ? 'bronze' : ''}">{i + 1}</span>
							<span class="spec-name">{entry.username}</span>
							{#if entry.team_name}<span class="spec-team">{entry.team_name}</span>{/if}
							<span class="spec-pts">{entry.points} pts</span>
						</div>
					{:else}
						<p class="spec-empty">Aucun joueur classé</p>
					{/each}
				</div>
			</div>

		{:else if currentView === 'teams'}
			<div class="spec-view">
				<h1 class="spec-title">👥 Classement Équipes</h1>
				<div class="spec-lb">
					{#each teamLeaderboard as team, i}
						<div class="spec-row {i < 3 ? 'spec-top' : ''}">
							<span class="spec-rank {i === 0 ? 'gold' : i === 1 ? 'silver' : i === 2 ? 'bronze' : ''}">{i + 1}</span>
							<span class="spec-name">{team.team_name}</span>
							<span class="spec-members">{team.member_count} joueurs</span>
							<span class="spec-pts">{team.score} pts</span>
						</div>
					{:else}
						<p class="spec-empty">Aucune équipe</p>
					{/each}
				</div>
			</div>

		{:else if currentView === 'map'}
			<div class="spec-view map-view">
				<h1 class="spec-title">🗺️ Plan de Salle</h1>
				<div class="spec-map-wrap">
					<svg viewBox={mapViewBox} class="spec-map">
						<defs>
							<pattern id="spec-grid" width="40" height="40" patternUnits="userSpaceOnUse">
								<path d="M 40 0 L 0 0 0 40" fill="none" stroke="var(--map-grid-stroke)" stroke-width="1"/>
							</pattern>
						</defs>
						<rect width="100%" height="100%" fill="url(#spec-grid)"/>
						{#each roomLayout.tables as table}
							{@const cx = table.x + table.w / 2}
							{@const cy = table.y + table.h / 2}
							<g transform="rotate({table.rotation || 0}, {cx}, {cy})">
								<rect x={table.x} y={table.y} width={table.w} height={table.h} rx="6" fill="var(--map-table-fill)" stroke="var(--map-table-stroke)" stroke-width="1.5"/>
								<text x={cx} y={cy + 4} text-anchor="middle" fill="var(--text-muted)" font-size="12" font-weight="700">{table.label}</text>
							</g>
						{/each}
						{#each (roomLayout.furniture || []) as furn}
							{@const fcx = furn.x + furn.w / 2}
							{@const fcy = furn.y + furn.h / 2}
							<g transform="rotate({furn.rotation || 0}, {fcx}, {fcy})">
								<rect x={furn.x} y={furn.y} width={furn.w} height={furn.h} rx="5"
									fill="rgba(245,158,11,0.1)" stroke="rgba(245,158,11,0.4)" stroke-width="1.5" stroke-dasharray="5 2"/>
								<text x={fcx} y={fcy - 2} text-anchor="middle" font-size="14" style="pointer-events:none">{furn.icon}</text>
								<text x={fcx} y={fcy + 12} text-anchor="middle" fill="#f59e0b" font-size="9" font-weight="700">{furn.label}</text>
							</g>
						{/each}
						{#each roomLayout.seats as seat}
						{@const occ = getOccupant(seat.id)}
						{@const scx = seat.x + 25}
						{@const scy = seat.y + 25}
						<g transform="rotate({seat.rotation || 0}, {scx}, {scy})">
							<clipPath id="spec-clip-{seat.id}">
								<rect x={seat.x + 2} y={seat.y} width="46" height="50"/>
							</clipPath>
							<rect x={seat.x} y={seat.y} width="50" height="50" rx="6"
								fill={occ ? 'var(--map-seat-mine-fill)' : 'var(--map-seat-fill)'}
								stroke={occ ? 'var(--accent)' : 'var(--map-seat-stroke)'} stroke-width="1.5"/>
							<g clip-path="url(#spec-clip-{seat.id})">
								{#if occ}
									<text x={scx} y={seat.y + 13} text-anchor="middle" fill="var(--text-muted)" font-size="7" font-weight="800">{seat.id}</text>
									<text x={scx} y={seat.y + 27} text-anchor="middle" fill="var(--map-seat-player-fill)" font-size="9" font-weight="700"
										textLength={occ.username.length > 7 ? 44 : null}
										lengthAdjust="spacingAndGlyphs"
									>{occ.username}</text>
									{#if occ.team_name}
										<text x={scx} y={seat.y + 38} text-anchor="middle" fill="var(--accent)" font-size="7" font-weight="600"
											textLength={occ.team_name.length > 8 ? 42 : null}
											lengthAdjust="spacingAndGlyphs"
										>{occ.team_name}</text>
									{/if}
								{:else}
									<text x={scx} y={scy + 4} text-anchor="middle" fill="var(--text-muted)" font-size="8">Libre</text>
								{/if}
							</g>
						</g>
					{/each}
					</svg>
				</div>
				<div class="spec-map-legend">
					<span>🔵 Occupé ({occupiedSeats})</span>
					<span>⚫ Libre ({totalSeats - occupiedSeats})</span>
				</div>
			</div>

		{:else if currentView === 'bracket'}
			<div class="spec-view spec-view-wide">
				<!-- Tournament nav if multiple running -->
				{#if runningTournaments.length > 1}
					<div class="spec-tourney-nav">
						{#each runningTournaments as rt, ti}
							<button class="spec-tourney-tab {ti === bracketTourneyIdx ? 'active' : ''}" on:click={() => bracketTourneyIdx = ti}>
								{rt.name}
							</button>
						{/each}
					</div>
				{/if}
				<div class="bracket-top-info">
					<h1 class="spec-title hero-title">{runningTournament?.name || 'Bracket en cours'}</h1>
					{#if runningGame}<span class="hero-game-name">{runningGame.name}</span>{/if}
				</div>
				{#if bracketRounds.length > 0}
					{#if bracketType === 'ffa'}
						<!-- FFA View -->
						<div class="spec-ffa-area">
							{#each bracketRounds as roundMatches, ri}
								{@const match = roundMatches[0]}
								{@const isLatest = ri === bracketRounds.length - 1}
								<div class="spec-ffa-round {isLatest ? 'current' : 'past'}">
									<div class="spec-ffa-hdr">
										<span>Manche {ri + 1}</span>
										<span class="spec-ffa-count">{match.p.length} joueurs</span>
									</div>
									<div class="spec-ffa-players">
										{#each match.p as playerId, pi}
											<div class="spec-ffa-row {match.score?.[pi] === 1 ? 'gold' : match.score?.[pi] === 2 ? 'silver' : match.score?.[pi] === 3 ? 'bronze' : ''}">
												<span class="spec-ffa-rank">{#if match.score?.[pi] > 0}#{match.score[pi]}{:else}—{/if}</span>
												<span class="spec-ffa-name">{getPlayerName(playerId)}</span>
												{#if match.score?.[pi] > 0}
													<span class="spec-ffa-score">{match.score[pi]}</span>
												{/if}
											</div>
										{/each}
									</div>
								</div>
							{/each}
						</div>
					{:else if bracketType === 'round_robin'}
						<!-- Round Robin -->
						<div class="spec-rr-area">
							{#each bracketRounds as roundMatches, ri}
								<div class="spec-rr-round">
									<div class="spec-round-hdr">Journée {ri + 1}</div>
									{#each roundMatches as match}
										{@const s0 = match.score?.[0] ?? 0}
										{@const s1 = match.score?.[1] ?? 0}
										{@const isDone = s0 > 0 && s1 > 0 && s0 !== s1}
										<div class="spec-rr-match {isDone ? 'done' : ''}">
											<span class="spec-rr-p {isDone && (specLowerIsBetter ? s0 < s1 : s0 > s1) ? 'winner' : ''}">{getPlayerName(match.p[0])}</span>
											<span class="spec-rr-score">{s0} - {s1}</span>
											<span class="spec-rr-p {isDone && (specLowerIsBetter ? s1 < s0 : s1 > s0) ? 'winner' : ''}">{getPlayerName(match.p[1])}</span>
										</div>
									{/each}
								</div>
							{/each}
						</div>
					{:else}
						<!-- Duel bracket (single/double elim) -->
						<div class="spec-bracket-area">
							<div class="spec-rounds">
								{#each bracketRounds as roundMatches, ri}
									<div class="spec-round-col">
										<div class="spec-round-hdr">{ri === bracketRounds.length - 1 && bracketRounds.length > 1 ? '🏆 FINALE' : 'ROUND ' + (ri + 1)}</div>
										<div class="spec-matches">
											{#each roundMatches as match}
												{@const s0 = match.score?.[0] ?? 0}
												{@const s1 = match.score?.[1] ?? 0}
												{@const isDone = s0 > 0 && s1 > 0 && s0 !== s1}
												{@const isBye = match.p[0] === 0 && match.p[1] === 0}
												{@const isAutoWin = (match.p[0] === 0 || match.p[1] === 0) && (s0 > 0 || s1 > 0)}
												{#if !isBye && !isAutoWin}
													<div class="spec-match {isDone ? 'done' : ''}">
														<div class="spec-player {isDone && (specLowerIsBetter ? s0 < s1 : s0 > s1) ? 'winner' : ''} {isDone && (specLowerIsBetter ? s0 > s1 : s0 < s1) ? 'loser' : ''}">
															<span class="spec-pname">{getPlayerName(match.p[0])}</span>
															<span class="spec-pscore">{s0}</span>
														</div>
														<div class="spec-match-div"></div>
														<div class="spec-player {isDone && (specLowerIsBetter ? s1 < s0 : s1 > s0) ? 'winner' : ''} {isDone && (specLowerIsBetter ? s1 > s0 : s1 < s0) ? 'loser' : ''}">
															<span class="spec-pname">{getPlayerName(match.p[1])}</span>
															<span class="spec-pscore">{s1}</span>
														</div>
													</div>
												{/if}
											{/each}
										</div>
									</div>
								{/each}
							</div>
						</div>
					{/if}
				{:else}
					<p class="spec-empty">Aucun bracket actif</p>
				{/if}
			</div>

		{:else if currentView === 'info'}
			<div class="spec-view">
				<h1 class="spec-title"><span style="-webkit-text-fill-color:initial;background:none">📋</span> Informations</h1>
				<div class="spec-info-content">
					{@html spectatorInfo.replace(/\n/g, '<br>')}
				</div>
			</div>
		{/if}
	</div>
</div>

<style>
	/* Spectator inherits the active theme (dark/light) from :root / [data-theme] */
	:global(body) { overflow: hidden; }

	.spectator-mode {
		position: relative;
		height: 100vh; width: 100vw; display: flex; flex-direction: column;
		background: radial-gradient(ellipse at 30% 20%, rgba(59,130,246,0.08) 0%, transparent 50%), radial-gradient(ellipse at 70% 80%, rgba(139,92,246,0.06) 0%, transparent 50%), var(--bg-primary, #020617);
		color: var(--text-main, white); font-family: 'Inter', sans-serif;
	}
	.spectator-mode.bracket-active { background: transparent; }

	.spec-header { position: relative; z-index: 1; display: flex; justify-content: space-between; align-items: center; padding: 1.5rem 3rem; border-bottom: 1px solid var(--glass-border, rgba(255,255,255,0.06)); }
	.spec-event { font-size: 1.2rem; font-weight: 800; text-transform: uppercase; letter-spacing: 0.1em; color: var(--accent, #3b82f6); margin: 0; }
	.spec-nav { display: flex; align-items: center; gap: 0.75rem; }
	.nav-dot { width: 10px; height: 10px; border-radius: 50%; background: var(--text-muted); opacity: 0.35; cursor: pointer; transition: all 0.2s; border: 1px solid var(--glass-border); }
	.nav-dot.active { background: var(--accent, #3b82f6); opacity: 1; box-shadow: 0 0 10px rgba(59,130,246,0.5); transform: scale(1.3); border-color: transparent; }
	.pause-badge { font-size: 0.6rem; font-weight: 800; color: #fbbf24; background: rgba(251,191,36,0.1); padding: 0.2rem 0.6rem; border-radius: 20px; border: 1px solid rgba(251,191,36,0.2); }

	.spec-content { flex-grow: 1; display: flex; align-items: center; justify-content: center; padding: 2rem 4rem; }
	.bracket-active .spec-content { padding: 1rem; align-items: flex-start; }
	.spec-content.slide-in { animation: specSlideIn 0.6s cubic-bezier(0.16,1,0.3,1) forwards; }
	@keyframes specSlideIn { from { opacity: 0; transform: translateY(30px); } to { opacity: 1; transform: translateY(0); } }

	.spec-view { width: 100%; max-width: 1100px; }
	.spec-view-wide { max-width: 100%; }
	.spec-title { font-size: 3rem; font-weight: 800; text-align: center; margin-bottom: 2.5rem; background: linear-gradient(135deg, var(--title-gradient-from, white) 0%, var(--title-gradient-to, rgba(255,255,255,0.6)) 100%); -webkit-background-clip: text; -webkit-text-fill-color: transparent; background-clip: text; }

	/* Leaderboard */
	.spec-lb { display: flex; flex-direction: column; gap: 0.8rem; }
	.spec-row { display: flex; align-items: center; gap: 1.2rem; padding: 1rem 1.8rem; background: var(--hover-tint, rgba(255,255,255,0.03)); border-radius: 14px; border: 1px solid var(--glass-border, rgba(255,255,255,0.05)); font-size: 1.6rem; transition: all 0.2s; }
	.spec-row.spec-top { border-left: 3px solid var(--accent); background: var(--accent-soft); }
	.spec-rank { width: 36px; height: 36px; display: flex; align-items: center; justify-content: center; font-weight: 800; border-radius: 10px; background: var(--hover-tint); font-size: 1.2rem; }
	.spec-rank.gold { background: rgba(255,215,0,0.15); color: #ffd700; }
	.spec-rank.silver { background: rgba(192,192,192,0.15); color: #c0c0c0; }
	.spec-rank.bronze { background: rgba(205,127,50,0.15); color: #cd7f32; }
	.spec-name { flex-grow: 1; font-weight: 700; }
	.spec-team { font-size: 0.9rem; color: var(--text-muted); font-weight: 600; }
	.spec-members { font-size: 0.9rem; color: var(--text-muted); }
	.spec-pts { font-weight: 800; color: #fbbf24; min-width: 100px; text-align: right; }
	.spec-empty { text-align: center; color: var(--text-muted); font-size: 1.5rem; padding: 3rem; }

	/* Map */
	.map-view { max-width: 100%; }
	.spec-map-wrap { width: 100%; aspect-ratio: 3/2; max-height: 65vh; }
	.spec-map { width: 100%; height: 100%; border-radius: 16px; background: var(--surface-sunken, rgba(0,0,0,0.2)); border: 1px solid var(--glass-border, rgba(255,255,255,0.06)); }
	.spec-map-legend { display: flex; justify-content: center; gap: 2rem; margin-top: 1rem; font-size: 1rem; color: var(--text-muted); }

	/* Bracket - Tournament-style */
	.game-fullscreen-bg { position: fixed; inset: 0; z-index: 0; background-size: cover; background-position: center; background-repeat: no-repeat; }
	.game-fullscreen-vignette { position: fixed; inset: 0; z-index: 0; pointer-events: none; background: radial-gradient(ellipse at center, rgba(10,15,30,0.6) 0%, rgba(10,15,30,0.82) 40%, rgba(10,15,30,0.96) 70%, rgba(10,15,30,1) 100%); }
	.bracket-top-info { position: relative; z-index: 1; text-align: center; padding: 0.5rem 0 0.8rem; }
	.hero-title { margin: 0; font-size: 2rem; color: #ffffff !important; -webkit-text-fill-color: #ffffff !important; background: none !important; text-shadow: 0 2px 16px rgba(0,0,0,0.9), 0 0 40px rgba(0,0,0,0.5); }
	.hero-game-name { font-size: 0.85rem; font-weight: 600; color: #ffffff; opacity: 0.85; text-shadow: 0 1px 8px rgba(0,0,0,0.8); }
	.spec-bracket-area { position: relative; z-index: 1; flex: 1; overflow-x: auto; overflow-y: hidden; display: flex; align-items: flex-start; justify-content: center; padding: 0.5rem 0; width: 100%; }
	.spec-rounds { display: flex; gap: 2.5rem; align-items: flex-start; min-width: min-content; }
	.spec-round-col { display: flex; flex-direction: column; min-width: 240px; flex-shrink: 0; }
	.spec-round-hdr { text-align: center; font-weight: 800; color: var(--accent); font-size: 1.1rem; text-transform: uppercase; letter-spacing: 0.15em; margin-bottom: 1rem; padding: 0.4rem 1rem; background: var(--glass-bg); border-radius: 8px; }
	.spec-matches { display: flex; flex-direction: column; justify-content: space-around; flex-grow: 1; gap: 1rem; }
	.spec-match { background: var(--glass-bg); border: 1px solid var(--glass-border); border-radius: 12px; overflow: hidden; transition: all 0.2s; }
	.spec-match.done { border-color: rgba(59,130,246,0.25); box-shadow: 0 0 15px rgba(59,130,246,0.05); }
	.spec-player { display: flex; justify-content: space-between; align-items: center; padding: 0.7rem 1rem; transition: all 0.2s; }
	.spec-player.winner { background: var(--accent-soft); }
	.spec-player.loser { opacity: 0.4; }
	.spec-pname { font-size: 1.2rem; font-weight: 600; color: var(--text-dim); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
	.spec-player.winner .spec-pname { color: var(--text-main); font-weight: 800; }
	.spec-pscore { font-size: 1.3rem; font-weight: 900; color: var(--accent, #3b82f6); min-width: 2rem; text-align: right; }
	.spec-match-div { height: 1px; background: var(--glass-border); }

	/* Tournament nav tabs (multiple running) */
	.spec-tourney-nav { position: sticky; top: 0; z-index: 2; display: flex; gap: 0.3rem; justify-content: center; margin-bottom: 1rem; padding: 0.3rem; background: var(--glass-bg); border-radius: 10px; }
	.spec-tourney-tab { padding: 0.5rem 1.2rem; background: none; border: none; color: var(--text-muted); font-size: 1rem; font-weight: 700; cursor: pointer; border-radius: 8px; transition: all 0.2s; }
	.spec-tourney-tab.active { background: var(--accent-soft); color: var(--accent); }

	/* FFA spectator */
	.spec-ffa-area { position: relative; z-index: 1; flex: 1; overflow-y: auto; display: flex; flex-wrap: wrap; gap: 1.5rem; justify-content: center; padding: 0 2rem; }
	.spec-ffa-round { min-width: 300px; max-width: 500px; flex: 1; background: var(--glass-bg); border: 1px solid var(--glass-border); border-radius: 16px; overflow: hidden; }
	.spec-ffa-round.past { opacity: 0.4; }
	.spec-ffa-hdr { display: flex; justify-content: space-between; align-items: center; padding: 0.7rem 1rem; background: var(--surface-sunken); font-weight: 800; font-size: 1.1rem; color: var(--accent); text-transform: uppercase; letter-spacing: 0.1em; }
	.spec-ffa-count { font-size: 0.7rem; color: var(--text-muted); font-weight: 600; text-transform: none; letter-spacing: 0; }
	.spec-ffa-players { padding: 0.3rem 0; }
	.spec-ffa-row { display: flex; align-items: center; gap: 0.8rem; padding: 0.5rem 1rem; transition: all 0.2s; }
	.spec-ffa-row.gold { background: rgba(255,215,0,0.1); }
	.spec-ffa-row.silver { background: rgba(192,192,192,0.08); }
	.spec-ffa-row.bronze { background: rgba(205,127,50,0.08); }
	.spec-ffa-rank { font-size: 1rem; font-weight: 900; color: var(--text-muted); min-width: 2.5rem; text-align: center; }
	.spec-ffa-row.gold .spec-ffa-rank { color: #ffd700; }
	.spec-ffa-row.silver .spec-ffa-rank { color: #c0c0c0; }
	.spec-ffa-row.bronze .spec-ffa-rank { color: #cd7f32; }
	.spec-ffa-name { font-size: 1.1rem; font-weight: 600; flex: 1; color: var(--text-main); }
	.spec-ffa-score { font-size: 1.1rem; font-weight: 900; color: var(--accent); min-width: 2rem; text-align: right; }

	/* Round Robin spectator */
	.spec-rr-area { flex: 1; overflow-y: auto; display: flex; flex-wrap: wrap; gap: 1.5rem; justify-content: center; padding: 0 2rem; }
	.spec-rr-round { min-width: 300px; max-width: 420px; flex: 1; }
	.spec-rr-match { display: flex; align-items: center; gap: 0.5rem; padding: 0.5rem 0.8rem; background: var(--hover-tint, rgba(255,255,255,0.02)); border: 1px solid var(--glass-border, rgba(255,255,255,0.06)); border-radius: 8px; margin-bottom: 0.4rem; }
	.spec-rr-match.done { border-color: rgba(59,130,246,0.2); }
	.spec-rr-p { flex: 1; font-size: 1rem; color: var(--text-muted); }
	.spec-rr-p:last-child { text-align: right; }
	.spec-rr-p.winner { color: var(--text-main); font-weight: 700; }
	.spec-rr-score { font-size: 1rem; font-weight: 800; color: var(--accent); min-width: 3.5rem; text-align: center; }

	/* Info spectator */
	.spec-info-content {
		max-width: 800px; margin: 0 auto;
		font-size: 1.8rem; line-height: 1.6; color: var(--text-main, white);
		text-align: center; padding: 0 2rem;
	}
</style>
