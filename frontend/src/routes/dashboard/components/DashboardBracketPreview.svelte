<script>
	import { createEventDispatcher } from 'svelte';
	import { t } from '$lib/i18nStore';

	export let runningTournaments = [];
	export let activeTournament = null;
	export let selectedRunningIdx = 0;
	export let participants = [];
	export let dashTeams = [];
	export let games = [];
	export let user = null;

	const dispatch = createEventDispatcher();

	$: activeBracketType = activeTournament?.config?.bracket_type || 'single_elim';

	$: dashNameMap = (() => {
		const m = {};
		(participants || []).forEach(p => { m[p.user_id] = p.username; });
		const tm = activeTournament?.config?._team_map || {};
		Object.entries(tm).forEach(([id, name]) => { m[id] = name; });
		(dashTeams || []).forEach(t => { const key = String(-t.id); if (!m[key]) m[key] = t.name; });
		return m;
	})();

	function getPlayerName(userId, map) {
		if (userId === 0) return 'TBD';
		if (userId < 0) return map[String(userId)] || `${$t('admin_tourneys_wizard_mode_teams')} #${Math.abs(userId)}`;
		return map[userId] || `#${userId}`;
	}

	function getRounds(bracket) {
		if (!bracket || !Array.isArray(bracket)) return [];
		const rounds = {};
		bracket.forEach(m => {
			if (!rounds[m.id.r]) rounds[m.id.r] = [];
			rounds[m.id.r].push(m);
		});
		return Object.keys(rounds).sort((a,b) => a-b).map(k => rounds[k]);
	}

	function getFFAMatchRank(match, scoreIndex, lowerIsBetter) {
		const score = match.score?.[scoreIndex];
		if (!score || score <= 0) return null;
		const validScores = [...match.score].filter(s => s > 0).sort((a, b) => lowerIsBetter ? a - b : b - a);
		let rank = 1;
		let prevScore = validScores[0];
		for (let i = 0; i < validScores.length; i++) {
			if (validScores[i] !== prevScore) { rank++; prevScore = validScores[i]; }
			if (validScores[i] === score) return rank;
		}
		return null;
	}

	$: bracketRounds = activeTournament ? getRounds(activeTournament.bracket) : [];

	$: dashRRGroups = (() => {
		if (activeBracketType !== 'round_robin' || !activeTournament) return [];
		const groups = {};
		(activeTournament.bracket || []).forEach(m => {
			if (!groups[m.id.s]) groups[m.id.s] = [];
			groups[m.id.s].push(m);
		});
		return Object.keys(groups).sort((a,b) => a-b).map(k => ({
			id: k,
			rounds: getRounds(groups[k])
		}));
	})();

	$: wbRounds = activeBracketType === 'double_elim' ? getRounds((activeTournament?.bracket || []).filter(m => m.id.s === 1)) : bracketRounds;
	$: lbRoundsRaw = activeBracketType === 'double_elim' ? getRounds((activeTournament?.bracket || []).filter(m => m.id.s === 2)) : [];
	$: lbRounds = lbRoundsRaw.map((roundMatches, ri) => {
		const hasVisible = roundMatches.some(m => {
			const isBye = m.p[0] === 0 && m.p[1] === 0;
			const s0 = m.score?.[0] ?? null, s1 = m.score?.[1] ?? null;
			const isAutoWin = (m.p[0] === 0 || m.p[1] === 0) && (s0 > 0 || s1 > 0);
			return !isBye && !isAutoWin;
		});
		return hasVisible ? { matches: roundMatches, originalIndex: ri } : null;
	}).filter(Boolean);

	// Pan/Zoom for bracket preview
	let brScale = 0.7, brPanX = 0, brPanY = 0;
	let brDrag = false, brStartX, brStartY;
	let brViewportEl, brCanvasEl;

	const BR_ZOOM_MIN = 0.3, BR_ZOOM_MAX = 2.0;
	function brClampPan() {
		if (!brViewportEl || !brCanvasEl) return;
		const vw = brViewportEl.clientWidth;
		const vh = brViewportEl.clientHeight;
		const cw = brCanvasEl.scrollWidth * brScale;
		const ch = brCanvasEl.scrollHeight * brScale;
		const margin = 40;
		if (cw <= vw) {
			const minX = -margin;
			const maxX = vw - cw + margin;
			brPanX = Math.min(maxX, Math.max(brPanX, minX));
		} else {
			brPanX = Math.min(margin, Math.max(brPanX, vw - cw - margin));
		}
		if (ch <= vh) {
			const minY = -margin;
			const maxY = vh - ch + margin;
			brPanY = Math.min(maxY, Math.max(brPanY, minY));
		} else {
			brPanY = Math.min(margin, Math.max(brPanY, vh - ch - margin));
		}
	}

	function brWheel(e) {
		e.preventDefault();
		const rect = e.currentTarget.getBoundingClientRect();
		const mx = e.clientX - rect.left, my = e.clientY - rect.top;
		const old = brScale;
		brScale *= e.deltaY < 0 ? 1.12 : 0.89;
		brScale = Math.min(Math.max(BR_ZOOM_MIN, brScale), BR_ZOOM_MAX);
		brPanX = mx - (mx - brPanX) * (brScale / old);
		brPanY = my - (my - brPanY) * (brScale / old);
		brClampPan();
	}
	function brDown(e) { brDrag = true; brStartX = e.clientX - brPanX; brStartY = e.clientY - brPanY; }
	function brMove(e) { if (!brDrag) return; brPanX = e.clientX - brStartX; brPanY = e.clientY - brStartY; brClampPan(); }
	function brUp() { brDrag = false; }
	function brPanTo(dx, dy) { brPanX += dx; brPanY += dy; brClampPan(); }

	$: brArrowLeft = brPanX < -10;
	$: brArrowRight = brViewportEl && brCanvasEl ? (brPanX + brCanvasEl.scrollWidth * brScale > brViewportEl.clientWidth + 10) : false;
	$: brArrowUp = brPanY < -10;
	$: brArrowDown = brViewportEl && brCanvasEl ? (brPanY + brCanvasEl.scrollHeight * brScale > brViewportEl.clientHeight + 10) : false;

	function getMostAdvancedRoundIndex(rounds) {
		if (!rounds || rounds.length === 0) return 0;
		let maxRi = 0;
		for (let ri = 0; ri < rounds.length; ri++) {
			const hasActive = rounds[ri].some(m => {
				const s0 = m.score?.[0] ?? null;
				const s1 = m.score?.[1] ?? null;
				const isDone = s0 !== null && s1 !== null && (s0 !== 0 || s1 !== 0);
				const hasPlayers = m.p && m.p[0] > 0 && m.p[1] > 0;
				return hasPlayers && !isDone;
			});
			if (hasActive) maxRi = ri;
		}
		if (maxRi > 0) return maxRi;

		for (let ri = 0; ri < rounds.length; ri++) {
			const hasPlayed = rounds[ri].some(m => {
				const s0 = m.score?.[0] ?? null;
				const s1 = m.score?.[1] ?? null;
				return s0 !== null && s1 !== null && (s0 !== 0 || s1 !== 0);
			});
			if (hasPlayed) maxRi = ri;
		}
		return maxRi;
	}

	function focusAdvancedRound() {
		if (!brViewportEl || !brCanvasEl || bracketRounds.length === 0) return;
		const ri = getMostAdvancedRoundIndex(bracketRounds);
		const vw = brViewportEl.clientWidth || 340;
		const vh = brViewportEl.clientHeight || 280;

		brScale = 0.75;
		const colWidth = 150;
		const gap = 24;

		const startRi = Math.max(0, ri - 1);
		const endRi = ri;
		const centerIndex = (startRi + endRi) / 2;
		const colCenter = centerIndex * (colWidth + gap) + (colWidth / 2);
		brPanX = (vw / 2) - (colCenter * brScale);

		const canvasHeight = brCanvasEl.scrollHeight || 250;
		brPanY = (vh / 2) - ((canvasHeight * brScale) / 2);
		brClampPan();
	}

	$: if (bracketRounds && brViewportEl) {
		setTimeout(() => focusAdvancedRound(), 150);
	}
</script>

<section class="panel bracket-panel glass">
	<div class="panel-header">
		<div>
			<h2>{activeTournament?.name || $t('dash_bracket_title')}</h2>
			<span class="subtitle">{games.find(g => g.id === activeTournament?.game_id)?.name || (runningTournaments.length + ' ' + $t('dash_pill_active').toLowerCase() + (runningTournaments.length > 1 ? 's' : ''))}</span>
		</div>
	</div>
	{#if runningTournaments.length > 0}
		<!-- Tabs -->
		{#if runningTournaments.length > 1}
			<div class="running-tabs">
				{#each runningTournaments as rt, i}
					<button class="rt-tab {selectedRunningIdx === i ? 'active' : ''}" on:click={() => dispatch('selectRunning', i)}>{rt.name}</button>
				{/each}
			</div>
		{/if}
		<div class="bracket-preview">
			<div class="bracket-info-grid">
				<div class="bi-card">
					<span class="bi-val">{participants.length}</span>
					<span class="bi-label">{$t('dash_stat_players')}</span>
				</div>
				<div class="bi-card">
					<span class="bi-val">{activeBracketType === 'round_robin' ? 'RR' : activeBracketType === 'double_elim' ? 'DE' : activeBracketType === 'ffa' ? 'FFA' : 'SE'}</span>
					<span class="bi-label">{$t('admin_tourneys_wizard_format_lbl')}</span>
				</div>
				<div class="bi-card">
					<span class="bi-val status-badge {activeTournament?.status?.toLowerCase() || ''}">{activeTournament?.status === 'RUNNING' ? $t('tourneys_status_running').toUpperCase() : activeTournament?.status === 'CLOSED' ? $t('tourneys_status_closed').toUpperCase() : activeTournament?.status || ''}</span>
					<span class="bi-label">Status</span>
				</div>
			</div>

			{#if bracketRounds.length > 0}
				{#if activeBracketType === 'ffa'}
					<!-- FFA compact view -->
					<div class="dash-ffa">
						{#each bracketRounds as roundMatches, ri}
							{@const isLatest = ri === bracketRounds.length - 1}
							<div class="dash-ffa-round" class:ffa-latest={isLatest}>
								<div class="dash-ffa-hdr" style="display: flex; justify-content: space-between; align-items: center; padding: 0.5rem 0.8rem; background: var(--surface-sunken); border-radius: 8px 8px 0 0; font-weight: 700; color: var(--accent); margin-bottom: 0.5rem;">
									{$t('dash_bracket_ffa_round', { round: ri+1, count: roundMatches.length })}
								</div>
								<div class="dash-ffa-matches" style="display: flex; flex-direction: column; gap: 0.8rem; padding: 0 0.5rem 0.5rem;">
								{#each roundMatches as match, mi}
									<div class="dash-ffa-match-box">
										<div class="dash-ffa-count" style="font-size: 0.7rem; color: var(--text-muted); font-weight: 600; margin-bottom: 0.3rem;">Match {mi + 1} - {$t(match.p.length > 1 ? 'admin_tourneys_players_count_plural' : 'admin_tourneys_players_count_singular', { count: match.p.length })}</div>
										{#each match.p as pid, pi}
											{@const mRank = getFFAMatchRank(match, pi, activeTournament?.config?.lower_score_is_better)}
											<div class="dash-ffa-row {mRank === 1 ? 'gold' : mRank === 2 ? 'silver' : mRank === 3 ? 'bronze' : ''}">
												<span class="dash-ffa-pos">{mRank ? '#' + mRank : '—'}</span>
												<span style="flex:1">{getPlayerName(pid, dashNameMap)}</span>
												{#if match.score?.[pi] > 0}
													<span class="dash-ffa-score">{match.score[pi]}</span>
												{/if}
											</div>
										{/each}
									</div>
								{/each}
								</div>
							</div>
						{/each}
					</div>
				{:else if activeBracketType === 'round_robin'}
					<!-- Round Robin view -->
					<div class="dash-rr">
						{#each dashRRGroups as group}
							<div class="dash-rr-group" style="margin-bottom: 1.5rem; width: 100%;">
								{#if dashRRGroups.length > 1}
									<h4 style="color: var(--accent); font-weight: 800; margin-bottom: 0.5rem;">Poule {String.fromCharCode(64 + parseInt(group.id))}</h4>
								{/if}
								<div class="dash-rr-rounds" style="display: flex; flex-wrap: wrap; gap: 1rem;">
									{#each group.rounds as roundMatches, ri}
										<div class="dash-rr-round" style="min-width: 250px; flex: 1;">
											<div class="dash-rr-hdr" style="font-weight: 700; color: var(--text-muted); margin-bottom: 0.5rem; font-size: 0.8rem; text-transform: uppercase;">{$t('spec_matchday_num', { num: ri + 1 })}</div>
											<div class="dash-rr-matches" style="display: flex; flex-direction: column; gap: 0.4rem;">
												{#each roundMatches as match}
													{@const s0 = match.score?.[0] ?? null}
													{@const s1 = match.score?.[1] ?? null}
													{@const isDone = s0 !== null && s1 !== null && (s0 !== 0 || s1 !== 0) && (s0 !== s1 || activeTournament?.config?.allow_draws)}
													{@const lowerIsBetter = activeTournament?.config?.lower_score_is_better}
													{@const p0Winner = isDone && (lowerIsBetter ? s0 < s1 : s0 > s1)}
													{@const p1Winner = isDone && (lowerIsBetter ? s1 < s0 : s1 > s0)}
													<div class="dash-rr-match {isDone ? 'done' : ''}" style="display: flex; justify-content: space-between; align-items: center; padding: 0.5rem; background: var(--surface-sunken); border-radius: 6px; border: 1px solid var(--glass-border);">
														<span class="dash-rr-p {p0Winner ? 'winner' : ''}" style="flex: 1; {p0Winner ? 'color: var(--text-main); font-weight: 700;' : 'color: var(--text-muted);'}">{getPlayerName(match.p[0], dashNameMap)}</span>
														
														<span class="dash-rr-score" style="font-weight: 800; color: var(--accent); padding: 0 0.5rem;">
															{#if activeTournament?.config?.boolean_mode}
																{#if isDone}
																	{p0Winner ? '✅' : (s0 === s1 && s0 !== 0 ? '🤝' : '❌')} - {p1Winner ? '✅' : (s0 === s1 && s0 !== 0 ? '🤝' : '❌')}
																{:else}—{/if}
															{:else}
																{s0 ?? 0} - {s1 ?? 0}
															{/if}
														</span>
														
														<span class="dash-rr-p {p1Winner ? 'winner' : ''}" style="flex: 1; text-align: right; {p1Winner ? 'color: var(--text-main); font-weight: 700;' : 'color: var(--text-muted);'}">{getPlayerName(match.p[1], dashNameMap)}</span>
													</div>
												{/each}
											</div>
										</div>
									{/each}
								</div>
							</div>
						{/each}
					</div>
				{:else}
					<!-- Duel bracket -->
					<div class="bracket-visual">
						<!-- svelte-ignore a11y-no-static-element-interactions -->
						<div class="dash-bracket-viewport" bind:this={brViewportEl} on:wheel={brWheel} on:mousedown={brDown} on:mousemove={brMove} on:mouseup={brUp} on:mouseleave={brUp} style="cursor: {brDrag ? 'grabbing' : 'grab'}">
							<div class="dash-bracket-canvas" bind:this={brCanvasEl} style="transform: translate({brPanX}px, {brPanY}px) scale({brScale});">
								<div class="dash-rounds">
									{#each wbRounds as roundMatches, ri}
										<div class="dash-round-col">
											<div class="dash-round-hdr">R{ri + 1}</div>
											<div class="dash-matches-col">
												{#each roundMatches as match}
													{@const s0 = match.score?.[0] ?? null}
													{@const s1 = match.score?.[1] ?? null}
													{@const isDone = s0 !== null && s1 !== null && (s0 !== 0 || s1 !== 0) && s0 !== s1}
													{@const isBye = match.p[0] === 0 && match.p[1] === 0}
													{@const isAutoWin = (match.p[0] === 0 || match.p[1] === 0) && (s0 > 0 || s1 > 0)}
													{#if !isBye && !isAutoWin}
													{@const lowerIsBetter = activeTournament?.config?.lower_score_is_better}
													{@const p0Winner = isDone && (lowerIsBetter ? s0 < s1 : s0 > s1)}
													{@const p0Loser = isDone && (lowerIsBetter ? s0 > s1 : s0 < s1)}
													{@const p1Winner = isDone && (lowerIsBetter ? s1 < s0 : s1 > s0)}
													{@const p1Loser = isDone && (lowerIsBetter ? s1 > s0 : s1 < s0)}
													<div class="dash-match {isDone ? 'done' : ''}">
														<div class="dm-player {match.p[0] ? 'filled' : ''} {p0Winner ? 'winner' : ''} {p0Loser ? 'loser' : ''}">
															<span>{getPlayerName(match.p[0], dashNameMap)}</span>
															<span class="dm-score">{#if activeTournament?.config?.boolean_mode}{#if p0Winner}✅{:else if p0Loser}❌{:else if isDone}🤝{:else}—{/if}{:else}{s0 ?? 0}{/if}</span>
														</div>
														<div class="dm-div"></div>
														<div class="dm-player {match.p[1] ? 'filled' : ''} {p1Winner ? 'winner' : ''} {p1Loser ? 'loser' : ''}">
															<span>{getPlayerName(match.p[1], dashNameMap)}</span>
															<span class="dm-score">{#if activeTournament?.config?.boolean_mode}{#if p1Winner}✅{:else if p1Loser}❌{:else if isDone}🤝{:else}—{/if}{:else}{s1 ?? 0}{/if}</span>
														</div>
													</div>
													{/if}
												{/each}
											</div>
										</div>
									{/each}
								</div>
								{#if activeBracketType === 'double_elim' && lbRounds.length > 0}
									<div style="margin: 0 1rem; align-self: center; font-weight: 800; color: var(--text-muted); text-transform: uppercase; font-size: 0.8rem; letter-spacing: 0.1em; padding: 1rem 0; text-align: center;">Losers Bracket</div>
									<div class="dash-rounds">
										{#each lbRounds as lbRound, ri}
											<div class="dash-round-col">
												<div class="dash-round-hdr">{lbRound.originalIndex === lbRoundsRaw.length - 1 ? 'LB Finale' : 'LB R' + (lbRound.originalIndex + 1)}</div>
												<div class="dash-matches-col">
													{#each lbRound.matches as match}
														{@const s0 = match.score?.[0] ?? null}
														{@const s1 = match.score?.[1] ?? null}
														{@const isDone = s0 !== null && s1 !== null && (s0 !== 0 || s1 !== 0) && s0 !== s1}
														{@const isBye = match.p[0] === 0 && match.p[1] === 0}
														{@const isAutoWin = (match.p[0] === 0 || match.p[1] === 0) && (s0 > 0 || s1 > 0)}
														{#if !isBye && !isAutoWin}
														{@const lowerIsBetter = activeTournament?.config?.lower_score_is_better}
														{@const p0Winner = isDone && (lowerIsBetter ? s0 < s1 : s0 > s1)}
														{@const p0Loser = isDone && (lowerIsBetter ? s0 > s1 : s0 < s1)}
														{@const p1Winner = isDone && (lowerIsBetter ? s1 < s0 : s1 > s0)}
														{@const p1Loser = isDone && (lowerIsBetter ? s1 > s0 : s1 < s0)}
														<div class="dash-match {isDone ? 'done' : ''}" style="opacity: 0.9;">
															<div class="dm-player {match.p[0] ? 'filled' : ''} {p0Winner ? 'winner' : ''} {p0Loser ? 'loser' : ''}">
																<span>{getPlayerName(match.p[0], dashNameMap)}</span>
																<span class="dm-score">{#if activeTournament?.config?.boolean_mode}{#if p0Winner}✅{:else if p0Loser}❌{:else if isDone}🤝{:else}—{/if}{:else}{s0 ?? 0}{/if}</span>
															</div>
															<div class="dm-div"></div>
															<div class="dm-player {match.p[1] ? 'filled' : ''} {p1Winner ? 'winner' : ''} {p1Loser ? 'loser' : ''}">
																<span>{getPlayerName(match.p[1], dashNameMap)}</span>
																<span class="dm-score">{#if activeTournament?.config?.boolean_mode}{#if p1Winner}✅{:else if p1Loser}❌{:else if isDone}🤝{:else}—{/if}{:else}{s1 ?? 0}{/if}</span>
															</div>
														</div>
														{/if}
													{/each}
												</div>
											</div>
										{/each}
									</div>
								{/if}
							</div>
						</div>
						<!-- svelte-ignore a11y-click-events-have-key-events -->
						{#if brArrowLeft}<div class="pan-arrow pan-arrow-left" on:click={() => brPanTo(100, 0)}>‹</div>{/if}
						<!-- svelte-ignore a11y-click-events-have-key-events -->
						{#if brArrowRight}<div class="pan-arrow pan-arrow-right" on:click={() => brPanTo(-100, 0)}>›</div>{/if}
						<!-- svelte-ignore a11y-click-events-have-key-events -->
						{#if brArrowUp}<div class="pan-arrow pan-arrow-up" on:click={() => brPanTo(0, 100)}>‹</div>{/if}
						<!-- svelte-ignore a11y-click-events-have-key-events -->
						{#if brArrowDown}<div class="pan-arrow pan-arrow-down" on:click={() => brPanTo(0, -100)}>‹</div>{/if}
					</div>
				{/if}
			{:else}
				<div class="no-bracket-data">
					<span>📊</span>
					<p class="text-dim text-xs">{$t('dash_bracket_waiting')}</p>
				</div>
			{/if}

			<a href="/dashboard/tournaments" class="btn-chip full-width">{$t('dash_bracket_view_all')}</a>
		</div>
	{:else}
		<div class="no-tournament">
			<span class="no-tourney-icon">🏆</span>
			<p>{$t('dash_no_tournament')}</p>
			{#if user?.is_admin}
				<a href="/dashboard/admin" class="btn-chip">{$t('dash_no_tournament_create')}</a>
			{/if}
		</div>
	{/if}
</section>

<style>
	.panel {
		display: flex;
		flex-direction: column;
		border-radius: 16px;
		overflow: hidden;
		min-height: 0;
	}
	.panel-header {
		padding: 1rem 1.2rem;
		border-bottom: 1px solid var(--glass-border);
		display: flex;
		justify-content: space-between;
		align-items: flex-start;
		flex-shrink: 0;
	}
	.panel-header h2 {
		font-size: 0.85rem;
		font-weight: 800;
		text-transform: uppercase;
		letter-spacing: 0.08em;
	}
	.panel-header .subtitle {
		font-size: 0.65rem;
		color: var(--text-muted);
		text-transform: uppercase;
		letter-spacing: 0.05em;
	}

	.bracket-panel {
		min-width: 0;
		height: 100%;
	}
	.bracket-preview {
		flex-grow: 1;
		display: flex;
		flex-direction: column;
		padding: 0.8rem;
		gap: 0.8rem;
		min-height: 0;
	}
	.bracket-info-grid {
		display: grid;
		grid-template-columns: 1fr 1fr 1fr;
		gap: 0.5rem;
		flex-shrink: 0;
	}
	.bi-card {
		display: flex;
		flex-direction: column;
		align-items: center;
		padding: 0.6rem;
		background: var(--surface-raised);
		border-radius: 10px;
		border: 1px solid var(--glass-border);
	}
	.bi-val { font-size: 1rem; font-weight: 800; }
	.bi-label { font-size: 0.55rem; color: var(--text-muted); text-transform: uppercase; }
	.status-badge { font-size: 0.7rem; padding: 0.15rem 0.5rem; border-radius: 6px; }
	.status-badge.running { color: var(--accent); background: rgba(59,130,246,0.1); }

	.running-tabs {
		display: flex;
		gap: 0.25rem;
		padding: 0 0.8rem;
		overflow-x: auto;
		border-bottom: 1px solid var(--glass-border);
		flex-shrink: 0;
		min-height: 32px;
		align-items: flex-end;
	}
	.rt-tab {
		padding: 0.45rem 0.7rem;
		font-size: 0.65rem;
		font-weight: 700;
		background: none;
		border: none;
		border-bottom: 2px solid transparent;
		color: var(--text-dim);
		cursor: pointer;
		white-space: nowrap;
		transition: all 0.15s;
	}
	.rt-tab:hover { color: var(--text-main); }
	.rt-tab.active { color: var(--accent); border-bottom-color: var(--accent); }

	.bracket-visual {
		flex-grow: 1;
		display: flex;
		flex-direction: column;
		min-height: 0;
		position: relative;
	}
	.dash-bracket-viewport {
		flex-grow: 1;
		overflow: hidden;
		border-radius: 8px;
		border: 1px solid var(--glass-border);
		background: var(--surface-sunken);
		min-height: 200px;
		user-select: none;
		-webkit-user-select: none;
	}
	.dash-bracket-canvas {
		transform-origin: 0 0;
		transition: transform 0.08s ease-out;
		padding: 1rem;
		display: inline-block;
		min-width: 100%;
	}

	.pan-arrow {
		position: absolute;
		display: flex;
		align-items: center;
		justify-content: center;
		color: var(--accent);
		font-size: 1.2rem;
		font-weight: 900;
		opacity: 0.6;
		pointer-events: auto;
		cursor: pointer;
		z-index: 5;
		animation: panArrowPulse 1.5s ease-in-out infinite;
		transition: opacity 0.15s;
	}
	.pan-arrow:hover { opacity: 1; animation: none; }
	.pan-arrow-left { left: 4px; top: 50%; transform: translateY(-50%); width: 22px; height: 40px; background: linear-gradient(90deg, rgba(59,130,246,0.15), transparent); border-radius: 4px; }
	.pan-arrow-right { right: 4px; top: 50%; transform: translateY(-50%); width: 22px; height: 40px; background: linear-gradient(-90deg, rgba(59,130,246,0.15), transparent); border-radius: 4px; }
	.pan-arrow-up { top: 4px; left: 50%; transform: translateX(-50%) rotate(90deg); width: 22px; height: 40px; background: linear-gradient(90deg, rgba(59,130,246,0.15), transparent); border-radius: 4px; }
	.pan-arrow-down { bottom: 4px; left: 50%; transform: translateX(-50%) rotate(-90deg); width: 22px; height: 40px; background: linear-gradient(90deg, rgba(59,130,246,0.15), transparent); border-radius: 4px; }
	@keyframes panArrowPulse { 0%, 100% { opacity: 0.4; } 50% { opacity: 0.85; } }

	.dash-ffa { display: flex; flex-direction: column; gap: 0.5rem; flex-grow: 1; min-height: 0; overflow-y: auto; padding: 0.25rem; }
	.dash-ffa-round { border: 1px solid var(--glass-border); border-radius: 8px; padding: 0.5rem; opacity: 0.5; }
	.dash-ffa-round.ffa-latest { opacity: 1; background: rgba(59,130,246,0.05); border-color: rgba(59,130,246,0.2); }
	.dash-ffa-row { display: flex; align-items: center; gap: 0.4rem; padding: 0.2rem 0.3rem; font-size: 0.6rem; border-radius: 4px; }
	.dash-ffa-row.gold { background: rgba(255,215,0,0.1); border-left: 2px solid #ffd700; }
	.dash-ffa-row.silver { background: rgba(192,192,192,0.08); border-left: 2px solid #c0c0c0; }
	.dash-ffa-row.bronze { background: rgba(205,127,50,0.08); border-left: 2px solid #cd7f32; }
	.dash-ffa-pos { font-weight: 800; color: var(--accent); min-width: 20px; font-size: 0.55rem; }
	.dash-ffa-score { font-weight: 800; font-size: 0.55rem; color: #fbbf24; background: rgba(251,191,36,0.15); padding: 0.1rem 0.35rem; border-radius: 4px; }

	.dash-rounds { display: flex; gap: 1.5rem; }
	.dash-round-col { display: flex; flex-direction: column; gap: 0.5rem; }
	.dash-round-hdr { text-align: center; font-weight: 700; color: var(--accent); font-size: 0.55rem; text-transform: uppercase; letter-spacing: 1px; }
	.dash-matches-col { display: flex; flex-direction: column; justify-content: space-around; flex-grow: 1; gap: 0.6rem; }
	.dash-match { width: 150px; background: var(--surface-raised); border: 1px solid var(--glass-border); border-radius: 6px; overflow: hidden; }
	.dm-player { display: flex; justify-content: space-between; padding: 0.3rem 0.5rem; font-size: 0.6rem; color: var(--text-muted); background: var(--surface-sunken); }
	.dm-player.filled { color: var(--text-main); background: var(--accent-soft); }
	.dm-player.winner { background: rgba(34, 197, 94, 0.18) !important; color: #4ade80 !important; font-weight: 700; }
	.dm-player.winner .dm-score { color: #4ade80 !important; }
	.dm-player.loser { opacity: 0.65; }
	.dm-player span { white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
	.dm-score { font-weight: 800; color: var(--accent); min-width: 14px; text-align: right; flex-shrink: 0; }
	.dm-div { height: 1px; background: var(--glass-border); }

	.no-bracket-data { display: flex; flex-direction: column; align-items: center; justify-content: center; flex-grow: 1; gap: 0.3rem; padding: 1rem; }
	.no-tournament { display: flex; flex-direction: column; align-items: center; justify-content: center; flex-grow: 1; gap: 0.75rem; padding: 2rem; }
	.no-tourney-icon { font-size: 2.5rem; opacity: 0.3; }
	.no-tournament p { color: var(--text-muted); font-size: 0.85rem; }

	.btn-chip {
		display: inline-flex;
		align-items: center;
		gap: 0.4rem;
		padding: 0.4rem 0.9rem;
		background: var(--map-badge-bg);
		border: 1px solid var(--map-badge-border);
		color: var(--accent);
		border-radius: 8px;
		font-size: 0.7rem;
		font-weight: 700;
		text-decoration: none;
		transition: all 0.15s;
		cursor: pointer;
	}
	.btn-chip:hover { background: var(--map-badge-hover); }
	.btn-chip.full-width { justify-content: center; width: 100%; margin-top: auto; }
</style>
