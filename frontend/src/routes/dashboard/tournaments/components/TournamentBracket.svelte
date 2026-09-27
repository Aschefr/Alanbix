<script>
	import { t } from '$lib/i18nStore';
	import { get } from 'svelte/store';
	import { createEventDispatcher, onDestroy } from 'svelte';

	export let selected;
	export let hasBracket = false;
	export let bracketType = 'single_elim';
	export let bracketRounds = [];
	export let wbRounds = [];
	export let lbRounds = [];
	export let lbRoundsRaw = [];
	export let rrGroups = [];
	export let nameMap = {};
	export let seatMap = {};
	export let currentUser = null;
	export let isAdmin = false;
	export let isParticipant = false;
	export let useTeams = false;
	export let myTeamSlotId = null;
	export let lowerIsBetter = false;
	export let booleanMode = false;

	const dispatch = createEventDispatcher();

	// Bracket pan/zoom
	let scale = 1, panX = 0, panY = 0, isDragging = false, startX = 0, startY = 0;
	let viewportEl, canvasEl;
	let hoveredPlayerId = null;
	let ffaKeepCount = 1;
	let confirmingRollback = false;

	// Delayed Score Submission (5s countdown with progress bar)
	const SCORE_DELAY_MS = 5000;
	let pendingScores = {}; // key -> { timer, interval, startTime, score, match }
	let pendingTick = 0;    // Reactive tick to force re-render of progress bars

	onDestroy(() => {
		Object.values(pendingScores).forEach(p => {
			if (p?.timer) clearTimeout(p.timer);
			if (p?.interval) clearInterval(p.interval);
		});
	});

	function scoreKey(match, playerIdx) {
		return `${match.id.s}_${match.id.r}_${match.id.m}_${playerIdx}`;
	}

	function scheduleScore(match, playerIdx, score) {
		const key = scoreKey(match, playerIdx);
		if (pendingScores[key]?.timer) clearTimeout(pendingScores[key].timer);
		if (pendingScores[key]?.interval) clearInterval(pendingScores[key].interval);

		if (isAdmin) {
			delete pendingScores[key];
			pendingScores = pendingScores;
			dispatch('submitScore', { match, score });
			return;
		}

		const startTime = Date.now();
		const interval = setInterval(() => { pendingTick++; }, 100);
		const timer = setTimeout(() => {
			clearInterval(interval);
			delete pendingScores[key];
			pendingScores = pendingScores;
			dispatch('submitScore', { match, score });
		}, SCORE_DELAY_MS);

		pendingScores[key] = { timer, interval, startTime, score, match };
		pendingScores = pendingScores;
	}

	function cancelPendingScore(match, playerIdx) {
		const key = scoreKey(match, playerIdx);
		if (pendingScores[key]) {
			clearTimeout(pendingScores[key].timer);
			clearInterval(pendingScores[key].interval);
			delete pendingScores[key];
			pendingScores = pendingScores;
		}
	}

	function getPendingProgress(match, playerIdx, _tick) {
		const key = scoreKey(match, playerIdx);
		const p = pendingScores[key];
		if (!p) return null;
		const elapsed = Date.now() - p.startTime;
		return Math.min(1, elapsed / SCORE_DELAY_MS);
	}

	function updateScore(match, playerIdx, value) {
		const score = [...(match.score || [null, null])];
		const trimmed = String(value).trim();
		score[playerIdx] = trimmed === '' ? null : (parseInt(trimmed, 10) || 0);
		scheduleScore(match, playerIdx, score);
	}

	function setBoolScore(match, winnerIdx) {
		const score = winnerIdx === 0 ? [1, 0] : [0, 1];
		scheduleScore(match, 0, score);
	}

	function setBoolDraw(match) {
		scheduleScore(match, 0, [1, 1]);
	}

	function resetBoolScore(match) {
		scheduleScore(match, 0, [null, null]);
	}

	function updateFFAPlacement(match, playerIdx, value) {
		const score = [...(match.score || match.p.map(() => 0))];
		score[playerIdx] = parseInt(value) || 0;
		scheduleScore(match, playerIdx, score);
	}

	function handleAdvanceFFA() {
		dispatch('advanceFFA', { keepCount: ffaKeepCount });
	}

	function handleFinishFFA() {
		dispatch('finishFFA');
	}

	function handleRollbackFFA() {
		confirmingRollback = false;
		dispatch('rollbackFFA');
	}

	function isMatchFinalized(match) {
		const scores = match.score || [];
		if (bracketType === 'ffa') {
			return scores.length > 0 && scores.every(s => s !== null && s > 0);
		}
		if (scores.length >= 2) {
			const s0 = scores[0], s1 = scores[1];
			return s0 !== null && s1 !== null && (s0 !== 0 || s1 !== 0) && s0 !== s1;
		}
		return false;
	}

	function canEditPlayerScore(match, playerIdx, _myTeamSlotId, _isParticipant, _currentUser) {
		if (isAdmin) return true;
		if (!_isParticipant || !_currentUser) return false;
		if (isMatchFinalized(match)) return false;
		const uid = _currentUser.id;
		
		if (bracketType === 'ffa') {
			const pid = match.p[playerIdx];
			return (pid === uid) || (_myTeamSlotId && pid === _myTeamSlotId);
		}
		
		const isInMatch = match.p.some(pid => pid === uid || (_myTeamSlotId && pid === _myTeamSlotId));
		return isInMatch;
	}

	function isPlayerLocked(match, playerIdx, _myTeamSlotId, _isParticipant, _currentUser) {
		if (isAdmin) return false;
		if (!_isParticipant || !_currentUser) return false;
		if (!isMatchFinalized(match)) return false;
		const uid = _currentUser.id;
		const isInMatch = match.p.some(pid => pid === uid || (_myTeamSlotId && pid === _myTeamSlotId));
		return isInMatch;
	}

	function getPlayerName(userId, map) {
		if (userId === 0) return 'TBD';
		if (userId < 0) return map[String(userId)] || `${get(t)('admin_tourneys_wizard_mode_teams')} #${Math.abs(userId)}`;
		return map[userId] || `${get(t)('role_player')} #${userId}`;
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

	// Pan & Zoom
	const ZOOM_MIN = 0.4, ZOOM_MAX = 2.5;
	function clampPan() {
		if (!viewportEl || !canvasEl) return;
		const vw = viewportEl.clientWidth;
		const vh = viewportEl.clientHeight;
		const cw = canvasEl.scrollWidth * scale;
		const ch = canvasEl.scrollHeight * scale;
		const margin = 100;
		panX = Math.min(margin, Math.max(panX, vw - cw - margin));
		panY = Math.min(margin, Math.max(panY, vh - ch - margin));
	}

	function onWheel(e) {
		e.preventDefault();
		const rect = e.currentTarget.getBoundingClientRect();
		const mx = e.clientX - rect.left, my = e.clientY - rect.top;
		const oldScale = scale;
		scale *= e.deltaY < 0 ? 1.1 : 0.9;
		scale = Math.min(Math.max(ZOOM_MIN, scale), ZOOM_MAX);
		panX = mx - (mx - panX) * (scale / oldScale);
		panY = my - (my - panY) * (scale / oldScale);
		clampPan();
	}

	function onMouseDown(e) { isDragging = true; startX = e.clientX - panX; startY = e.clientY - panY; }
	function onMouseMove(e) { if (!isDragging) return; panX = e.clientX - startX; panY = e.clientY - startY; clampPan(); }
	function onMouseUp() { isDragging = false; }

	export function resetZoom() {
		if (!viewportEl || !canvasEl) return;
		const vw = viewportEl.clientWidth;
		const vh = viewportEl.clientHeight;
		const cw = canvasEl.scrollWidth;
		const ch = canvasEl.scrollHeight;
		if (cw === 0 || ch === 0) {
			scale = 1;
			panX = 0;
			panY = 0;
			return;
		}
		const scaleX = (vw - 40) / cw;
		const scaleY = (vh - 40) / ch;
		let optimalScale = Math.min(scaleX, scaleY);
		optimalScale = Math.max(0.55, Math.min(optimalScale, 1.25));
		scale = optimalScale;
		panX = (vw - cw * scale) / 2;
		panY = (vh - ch * scale) / 2;
		clampPan();
	}

	function panTo(dx, dy) { panX += dx; panY += dy; clampPan(); }

	$: arrowLeft = panX < -10;
	$: arrowRight = viewportEl && canvasEl ? (panX + canvasEl.scrollWidth * scale > viewportEl.clientWidth + 10) : false;
	$: arrowUp = panY < -10;
	$: arrowDown = viewportEl && canvasEl ? (panY + canvasEl.scrollHeight * scale > viewportEl.clientHeight + 10) : false;
</script>

<div class="bracket-section glass" class:bracket-expanded={hasBracket}>
	<div class="section-title">
		<h3>{bracketType === 'round_robin' ? '📊 ' + $t('admin_tourneys_wizard_format_championship') : bracketType === 'ffa' ? '🏁 Free For All' : '📊 ' + $t('tourneys_tab_bracket')}</h3>
		{#if hasBracket && bracketType !== 'round_robin' && bracketType !== 'ffa'}
			<button class="btn-secondary btn-xs" on:click={resetZoom}>{$t('tourneys_btn_recenter')}</button>
		{/if}
	</div>
	{#if hasBracket}
		{#if bracketType === 'ffa'}
			<!-- FFA View -->
			<div class="ffa-container">
				{#each bracketRounds as roundMatches, ri}
					{@const isLatest = ri === bracketRounds.length - 1}
					{@const roundAllPlaced = roundMatches.every(m => m.score?.every(s => s > 0))}
					<div class="ffa-round {isLatest ? 'ffa-current' : 'ffa-past'}">
						<div class="ffa-round-hdr" style="display: flex; justify-content: space-between; align-items: center;">
							<span>{$t('tourneys_round_number', { num: ri + 1 })}</span>
							{#if isAdmin && isLatest && ri > 0 && selected?.status === 'RUNNING'}
								{#if confirmingRollback}
									<span class="inline-confirm" style="margin-left: auto; display: inline-flex; align-items: center; gap: 0.3rem;">
										<span class="inline-confirm-label" style="font-size: 0.7rem;">{$t('admin_tourneys_confirm_delete')}</span>
										<button class="admin-btn confirm-yes" on:click|stopPropagation|preventDefault={handleRollbackFFA} style="padding: 0.1rem 0.3rem; font-size: 0.7rem; border-radius: 4px; border: 1px solid var(--success); background: none; color: var(--success); cursor: pointer;">✓</button>
										<button class="admin-btn confirm-no" on:click|stopPropagation|preventDefault={() => confirmingRollback = false} style="padding: 0.1rem 0.3rem; font-size: 0.7rem; border-radius: 4px; border: 1px solid var(--danger); background: none; color: var(--danger); cursor: pointer;">✕</button>
									</span>
								{:else}
									<button class="rollback-btn" on:click|stopPropagation|preventDefault={() => confirmingRollback = true} title={$t('tourneys_ffa_rollback_tooltip')} style="background: none; border: none; color: #ef4444; cursor: pointer; font-size: 1.1rem; padding: 0 0.5rem; display: flex; align-items: center; justify-content: center; margin-left: auto;">✕</button>
								{/if}
							{/if}
						</div>
						<div class="ffa-matches-grid" style="display: flex; flex-direction: column; gap: 1rem;">
						{#each roundMatches as match, mi}
							<div class="ffa-match-box">
								<div class="ffa-player-count" style="margin-bottom: 0.5rem;">Match {mi + 1} - {$t(match.p.length > 1 ? 'admin_tourneys_players_count_plural' : 'admin_tourneys_players_count_singular', { count: match.p.length })}</div>
								<div class="ffa-players">
									{#each match.p as playerId, pi}
										{@const mRank = getFFAMatchRank(match, pi, lowerIsBetter)}
										<div class="ffa-player-row {mRank === 1 ? 'ffa-gold' : mRank === 2 ? 'ffa-silver' : mRank === 3 ? 'ffa-bronze' : ''}" class:my-player-highlight={useTeams ? (playerId === myTeamSlotId) : (playerId === currentUser?.id)}>
											<span class="ffa-rank">
												{#if mRank}#{mRank}{:else}—{/if}
											</span>
											<span class="ffa-name">{getPlayerName(playerId, nameMap)}</span>
											{#if playerId > 0 && seatMap[playerId]}<a href="/dashboard/map?highlight={seatMap[playerId]}" class="seat-badge" title={$t('players_tooltip_seat')}>💺{seatMap[playerId]}</a>{/if}
											{#if canEditPlayerScore(match, pi, myTeamSlotId, isParticipant, currentUser) && isLatest}
												<input type="number" class="score-input ffa-input" value={match.score?.[pi] || ''} placeholder="Score"
													on:change={(e) => updateFFAPlacement(match, pi, e.target.value)} min="1" />
											{:else if isPlayerLocked(match, pi, myTeamSlotId, isParticipant, currentUser)}
												<span class="score-locked ffa-input" title={$t('tourneys_score_validated')}>🔒 {match.score?.[pi]}</span>
											{:else if match.score?.[pi] > 0}
												<span class="score-display ffa-input">{match.score[pi]}</span>
											{/if}
										</div>
									{/each}
								</div>
							</div>
						{/each}
						</div>
						{#if isAdmin && isLatest && roundAllPlaced && selected?.status === 'RUNNING'}
							<div class="ffa-actions">
								<div class="ffa-advance-box" style="display:flex; align-items:center; gap:0.5rem; justify-content:center; margin-bottom: 1rem;">
									<label style="font-size: 0.9rem; color: var(--text-muted); font-weight: 600;">{$t('tourneys_ffa_keep_players')}</label>
									<input type="number" bind:value={ffaKeepCount} min="1" max={roundMatches.reduce((sum, m) => sum + m.p.length, 0)} style="width: 60px; padding: 0.3rem 0.5rem; border-radius: 6px; background: var(--surface-sunken); border: 1px solid var(--glass-border); color: var(--text-main);" />
									<button class="admin-btn" on:click={handleAdvanceFFA} style="margin: 0;">▶️ {$t('tourneys_ffa_next_round')}</button>
								</div>
								<button class="admin-btn stop" on:click={handleFinishFFA}>🏁 {$t('tourneys_ffa_finish')}</button>
							</div>
						{/if}
					</div>
				{/each}
			</div>
		{:else if bracketType === 'round_robin'}
			<!-- Round Robin Table -->
			<div class="rr-container">
				{#each rrGroups as group}
					<div class="rr-group" style="width: 100%; margin-bottom: 1rem;">
						{#if rrGroups.length > 1}
							<h4 class="rr-group-title" style="margin-bottom: 0.5rem; font-weight: 800; color: var(--accent);">Poule {String.fromCharCode(64 + parseInt(group.id))}</h4>
						{/if}
						<div class="rr-group-rounds" style="display: flex; flex-wrap: wrap; gap: 1rem;">
							{#each group.rounds as roundMatches, ri}
								<div class="rr-round">
									<div class="rr-round-hdr">{$t('spec_matchday_num', { num: ri + 1 })}</div>
									{#each roundMatches as match}
										{@const s0 = match.score?.[0] ?? null}
										{@const s1 = match.score?.[1] ?? null}
										{@const isDone = s0 !== null && s1 !== null && (s0 !== 0 || s1 !== 0) && (s0 !== s1 || selected?.config?.allow_draws)}
										<div class="rr-match {isDone ? 'match-done' : ''}">
											<span class="rr-p {isDone && (lowerIsBetter ? s0 < s1 : s0 > s1) ? 'winner' : ''}" class:my-player-highlight={useTeams ? (match.p[0] === myTeamSlotId) : (match.p[0] === currentUser?.id)}>{getPlayerName(match.p[0], nameMap)}{#if match.p[0] > 0 && seatMap[match.p[0]]}<a href="/dashboard/map?highlight={seatMap[match.p[0]]}" class="seat-badge" title={$t('tourneys_view_on_map')}>💺{seatMap[match.p[0]]}</a>{/if}</span>
											<div class="rr-scores">
												{#if booleanMode}
													{#if isDone}
														<div class="bool-badge-container">
															<span class="bool-badge {(lowerIsBetter ? (s0 ?? 0) < (s1 ?? 0) : (s0 ?? 0) > (s1 ?? 0)) ? 'win' : ((s0 ?? 0) === (s1 ?? 0) && (s0 ?? 0) !== 0 ? 'draw' : 'lose')}">{(lowerIsBetter ? (s0 ?? 0) < (s1 ?? 0) : (s0 ?? 0) > (s1 ?? 0)) ? '🏆' : ((s0 ?? 0) === (s1 ?? 0) && (s0 ?? 0) !== 0 ? '🤝' : '❌')}</span>
															<span class="rr-vs">-</span>
															<span class="bool-badge {(lowerIsBetter ? (s1 ?? 0) < (s0 ?? 0) : (s1 ?? 0) > (s0 ?? 0)) ? 'win' : ((s0 ?? 0) === (s1 ?? 0) && (s0 ?? 0) !== 0 ? 'draw' : 'lose')}">{(lowerIsBetter ? (s1 ?? 0) < (s0 ?? 0) : (s1 ?? 0) > (s0 ?? 0)) ? '🏆' : ((s0 ?? 0) === (s1 ?? 0) && (s0 ?? 0) !== 0 ? '🤝' : '❌')}</span>
															{#if isAdmin}
																<button class="bool-reset-btn" on:click={() => resetBoolScore(match)} title={$t('tourneys_reset_score_tooltip')}>⏪</button>
															{/if}
														</div>
													{:else if canEditPlayerScore(match, 0, myTeamSlotId, isParticipant, currentUser) || canEditPlayerScore(match, 1, myTeamSlotId, isParticipant, currentUser)}
														<div class="bool-btns-rr">
															<button class="bool-btn bool-check" on:click={() => setBoolScore(match, 0)} title={$t('tourneys_win_tooltip', { name: getPlayerName(match.p[0], nameMap) })}><span class="bool-default">☐</span><span class="bool-hover">✅</span></button>
															{#if selected?.config?.allow_draws}
																<button class="bool-btn bool-draw" on:click={() => setBoolDraw(match)} title={$t('tourneys_draw_tooltip')}>🤝</button>
															{/if}
															<button class="bool-btn bool-check" on:click={() => setBoolScore(match, 1)} title={$t('tourneys_win_tooltip', { name: getPlayerName(match.p[1], nameMap) })}><span class="bool-default">☐</span><span class="bool-hover">✅</span></button>
														</div>
													{:else}
														<span class="rr-score">—</span><span class="rr-vs">-</span><span class="rr-score">—</span>
													{/if}
												{:else}
													{#if canEditPlayerScore(match, 0, myTeamSlotId, isParticipant, currentUser)}
														<input type="number" class="score-input" value={s0 || ''} placeholder="—" on:change={(e) => updateScore(match, 0, e.target.value)} min="0" disabled={match.p[0] === 0 || match.p[1] === 0} />
													{:else if isPlayerLocked(match, 0, myTeamSlotId, isParticipant, currentUser)}
														<span class="score-locked" title={$t('tourneys_score_validated')}>🔒 {s0 ?? 0}</span>
													{:else}
														<span class="rr-score">{s0 ?? 0}</span>
													{/if}
													<span class="rr-vs">-</span>
													{#if canEditPlayerScore(match, 1, myTeamSlotId, isParticipant, currentUser)}
														<input type="number" class="score-input" value={s1 || ''} placeholder="—" on:change={(e) => updateScore(match, 1, e.target.value)} min="0" disabled={match.p[0] === 0 || match.p[1] === 0} />
													{:else if isPlayerLocked(match, 1, myTeamSlotId, isParticipant, currentUser)}
														<span class="score-locked" title={$t('tourneys_score_validated')}>🔒 {s1 ?? 0}</span>
													{:else}
														<span class="rr-score">{s1 ?? 0}</span>
													{/if}
												{/if}
											</div>
											<span class="rr-p {isDone && (lowerIsBetter ? s1 < s0 : s1 > s0) ? 'winner' : ''}" class:my-player-highlight={useTeams ? (match.p[1] === myTeamSlotId) : (match.p[1] === currentUser?.id)}>{getPlayerName(match.p[1], nameMap)}{#if match.p[1] > 0 && seatMap[match.p[1]]}<a href="/dashboard/map?highlight={seatMap[match.p[1]]}" class="seat-badge" title={$t('tourneys_view_on_map')}>💺{seatMap[match.p[1]]}</a>{/if}</span>
											{#if getPendingProgress(match, 0, pendingTick) !== null || getPendingProgress(match, 1, pendingTick) !== null}
												<div class="score-pending rr-pending">
													<div class="score-pending-bar" style="width:{((getPendingProgress(match, 0, pendingTick) ?? getPendingProgress(match, 1, pendingTick)) * 100).toFixed(0)}%"></div>
													<button class="score-pending-cancel" on:click|stopPropagation={() => { cancelPendingScore(match, getPendingProgress(match, 0, pendingTick) !== null ? 0 : 1); }}>✕ {$t('info_btn_cancel')}</button>
												</div>
											{/if}
										</div>
									{/each}
								</div>
							{/each}
						</div>
					</div>
				{/each}
			</div>
		{:else}
			<!-- Duel Bracket (single/double) -->
			<!-- svelte-ignore a11y-no-static-element-interactions -->
			<div class="bracket-viewport-wrapper">
				<div class="bracket-viewport" bind:this={viewportEl} on:wheel={onWheel} on:mousedown={onMouseDown} on:mousemove={onMouseMove} on:mouseup={onMouseUp} on:mouseleave={onMouseUp}>
					<div class="bracket-canvas" bind:this={canvasEl} style="transform: translate({panX}px, {panY}px) scale({scale});">
						{#if bracketType === 'double_elim' && lbRounds.length > 0}
							<div class="de-label">Winners Bracket</div>
						{/if}
						<div class="rounds-container">
							{#each wbRounds as roundMatches, ri}
								<div class="round-col {ri === wbRounds.length - 1 && wbRounds.length > 1 ? 'finale-col' : ''}">
									<div class="round-header {ri === wbRounds.length - 1 && wbRounds.length > 1 ? 'finale-header' : ''}">{ri === wbRounds.length - 1 && wbRounds.length > 1 ? $t('tourneys_bracket_finale') : 'R' + (ri + 1)}</div>
									<div class="matches-col">
										{#each roundMatches as match}
											{@const s0 = match.score?.[0] ?? null}
											{@const s1 = match.score?.[1] ?? null}
											{@const isDone = s0 !== null && s1 !== null && (s0 !== 0 || s1 !== 0) && s0 !== s1}
											{@const isBye = match.p[0] === 0 && match.p[1] === 0}
											{@const isAutoWin = (match.p[0] === 0 || match.p[1] === 0) && (s0 > 0 || s1 > 0)}
											{#if !isBye && !isAutoWin}
											<div class="bracket-match {isDone ? 'match-done' : ''} {hoveredPlayerId && (match.p[0] === hoveredPlayerId || match.p[1] === hoveredPlayerId) ? 'player-highlight' : ''}">
												<!-- svelte-ignore a11y-no-static-element-interactions -->
												<div class="player-row {match.p[0] ? 'filled' : ''} {isDone && (lowerIsBetter ? s0 < s1 : s0 > s1) ? 'winner' : ''} {isDone && (lowerIsBetter ? s0 > s1 : s0 < s1) ? 'loser' : ''}" class:my-player-highlight={useTeams ? (match.p[0] === myTeamSlotId) : (match.p[0] === currentUser?.id)} on:mouseenter={() => { if(match.p[0]) hoveredPlayerId = match.p[0]; }} on:mouseleave={() => hoveredPlayerId = null}>
													<span class="player-name">{getPlayerName(match.p[0], nameMap)}</span>
													{#if match.p[0] > 0 && seatMap[match.p[0]]}<a href="/dashboard/map?highlight={seatMap[match.p[0]]}" class="seat-badge" title={$t('tourneys_view_on_map')}>📍{seatMap[match.p[0]]}</a>{/if}
													{#if booleanMode}
														{#if canEditPlayerScore(match, 0, myTeamSlotId, isParticipant, currentUser) && !isDone}
															<div class="bool-btns">
																<button class="bool-btn bool-check" on:click={() => setBoolScore(match, 0)} title="Vainqueur"><span class="bool-default">☐</span><span class="bool-hover">✅</span></button>
															</div>
														{:else if isDone}
															<div class="bool-badge-container">
																<span class="bool-badge {(lowerIsBetter ? (s0 ?? 0) < (s1 ?? 0) : (s0 ?? 0) > (s1 ?? 0)) ? 'win' : (s0 === s1 ? 'draw' : 'lose')}">{(lowerIsBetter ? (s0 ?? 0) < (s1 ?? 0) : (s0 ?? 0) > (s1 ?? 0)) ? '✅' : (s0 === s1 ? '🤝' : '❌')}</span>
																{#if isAdmin}
																	<button class="bool-reset-btn" on:click={() => resetBoolScore(match)} title={$t('tourneys_reset_score_tooltip')}>↩️</button>
																{/if}
															</div>
														{:else}
															<span class="score-display">—</span>
														{/if}
													{:else}
														{#if canEditPlayerScore(match, 0, myTeamSlotId, isParticipant, currentUser)}
															<input type="number" class="score-input" value={s0 || ''} placeholder="—" on:change={(e) => updateScore(match, 0, e.target.value)} min="0" disabled={match.p[0] === 0 || match.p[1] === 0} />
														{:else if isPlayerLocked(match, 0, myTeamSlotId, isParticipant, currentUser)}
															<span class="score-locked" title={$t('tourneys_score_validated_admin')}>🔒 {s0 ?? 0}</span>
														{:else}
															<span class="score-display">{s0 || '—'}</span>
														{/if}
													{/if}
												</div>
												<div class="match-divider"></div>
												<!-- svelte-ignore a11y-no-static-element-interactions -->
												<div class="player-row {match.p[1] ? 'filled' : ''} {isDone && (lowerIsBetter ? s1 < s0 : s1 > s0) ? 'winner' : ''} {isDone && (lowerIsBetter ? s1 > s0 : s1 < s0) ? 'loser' : ''}" class:my-player-highlight={useTeams ? (match.p[1] === myTeamSlotId) : (match.p[1] === currentUser?.id)} on:mouseenter={() => { if(match.p[1]) hoveredPlayerId = match.p[1]; }} on:mouseleave={() => hoveredPlayerId = null}>
													<span class="player-name">{getPlayerName(match.p[1], nameMap)}</span>
													{#if match.p[1] > 0 && seatMap[match.p[1]]}<a href="/dashboard/map?highlight={seatMap[match.p[1]]}" class="seat-badge" title={$t('tourneys_view_on_map')}>📍{seatMap[match.p[1]]}</a>{/if}
													{#if booleanMode}
														{#if canEditPlayerScore(match, 1, myTeamSlotId, isParticipant, currentUser) && !isDone}
															<div class="bool-btns">
																<button class="bool-btn bool-check" on:click={() => setBoolScore(match, 1)} title="Vainqueur"><span class="bool-default">☐</span><span class="bool-hover">✅</span></button>
															</div>
														{:else if isDone}
															<div class="bool-badge-container">
																<span class="bool-badge {(lowerIsBetter ? (s1 ?? 0) < (s0 ?? 0) : (s1 ?? 0) > (s0 ?? 0)) ? 'win' : (s0 === s1 ? 'draw' : 'lose')}">{(lowerIsBetter ? (s1 ?? 0) < (s0 ?? 0) : (s1 ?? 0) > (s0 ?? 0)) ? '✅' : (s0 === s1 ? '🤝' : '❌')}</span>
																{#if isAdmin}
																	<button class="bool-reset-btn" on:click={() => resetBoolScore(match)} title={$t('tourneys_reset_score_tooltip')}>↩️</button>
																{/if}
															</div>
														{:else}
															<span class="score-display">—</span>
														{/if}
													{:else}
														{#if canEditPlayerScore(match, 1, myTeamSlotId, isParticipant, currentUser)}
															<input type="number" class="score-input" value={s1 || ''} placeholder="—" on:change={(e) => updateScore(match, 1, e.target.value)} min="0" disabled={match.p[0] === 0 || match.p[1] === 0} />
														{:else if isPlayerLocked(match, 1, myTeamSlotId, isParticipant, currentUser)}
															<span class="score-locked" title={$t('tourneys_score_validated_admin')}>🔒 {s1 ?? 0}</span>
														{:else}
															<span class="score-display">{s1 || '—'}</span>
														{/if}
													{/if}
												</div>
												{#if getPendingProgress(match, 0, pendingTick) !== null || getPendingProgress(match, 1, pendingTick) !== null}
													<div class="score-pending">
														<div class="score-pending-bar" style="width:{((getPendingProgress(match, 0, pendingTick) ?? getPendingProgress(match, 1, pendingTick)) * 100).toFixed(0)}%"></div>
														<button class="score-pending-cancel" on:click|stopPropagation={() => { cancelPendingScore(match, getPendingProgress(match, 0, pendingTick) !== null ? 0 : 1); }}>✕ {$t('info_btn_cancel')}</button>
													</div>
												{/if}
											</div>
											{/if}
										{/each}
									</div>
								</div>
							{/each}
						</div>
						{#if bracketType === 'double_elim' && lbRounds.length > 0}
							<div class="de-label lb">Losers Bracket</div>
							<div class="rounds-container lb-section">
								{#each lbRounds as lbRound}
									<div class="round-col">
										<div class="round-header lb-hdr">{lbRound.originalIndex === lbRoundsRaw.length - 1 ? 'LB Finale' : 'LB R' + (lbRound.originalIndex + 1)}</div>
										<div class="matches-col">
											{#each lbRound.matches as match}
												{@const s0 = match.score?.[0] ?? null}
												{@const s1 = match.score?.[1] ?? null}
												{@const isDone = s0 !== null && s1 !== null && (s0 !== 0 || s1 !== 0) && s0 !== s1}
												{@const isBye = match.p[0] === 0 && match.p[1] === 0}
												{@const isAutoWin = (match.p[0] === 0 || match.p[1] === 0) && (s0 > 0 || s1 > 0)}
												{#if !isBye && !isAutoWin}
												<div class="bracket-match lb-match {isDone ? 'match-done' : ''} {hoveredPlayerId && (match.p[0] === hoveredPlayerId || match.p[1] === hoveredPlayerId) ? 'player-highlight' : ''}">
													<!-- svelte-ignore a11y-no-static-element-interactions -->
													<div class="player-row {match.p[0] ? 'filled' : ''} {isDone && (lowerIsBetter ? s0 < s1 : s0 > s1) ? 'winner' : ''} {isDone && (lowerIsBetter ? s0 > s1 : s0 < s1) ? 'loser' : ''}" class:my-player-highlight={useTeams ? (match.p[0] === myTeamSlotId) : (match.p[0] === currentUser?.id)} on:mouseenter={() => { if(match.p[0]) hoveredPlayerId = match.p[0]; }} on:mouseleave={() => hoveredPlayerId = null}>
														<span class="player-name">{getPlayerName(match.p[0], nameMap)}</span>
														{#if match.p[0] > 0 && seatMap[match.p[0]]}<a href="/dashboard/map?highlight={seatMap[match.p[0]]}" class="seat-badge" title={$t('tourneys_view_on_map')}>📍{seatMap[match.p[0]]}</a>{/if}
														{#if booleanMode}
															{#if canEditPlayerScore(match, 0, myTeamSlotId, isParticipant, currentUser) && !isDone}
																<div class="bool-btns">
																	<button class="bool-btn bool-check" on:click={() => setBoolScore(match, 0)} title="Vainqueur"><span class="bool-default">☐</span><span class="bool-hover">✅</span></button>
																</div>
															{:else if isDone}
																<div class="bool-badge-container">
																	<span class="bool-badge {(lowerIsBetter ? (s0??0) < (s1??0) : (s0??0) > (s1??0)) ? 'win' : ((s0??0)===(s1??0) && (s0??0)!==0 ? 'draw' : 'lose')}">{(lowerIsBetter ? (s0??0) < (s1??0) : (s0??0) > (s1??0)) ? '✅' : ((s0??0)===(s1??0) && (s0??0)!==0 ? '🤝' : '❌')}</span>
																	{#if isAdmin}
																		<button class="bool-reset-btn" on:click={() => resetBoolScore(match)} title={$t('tourneys_reset_score_tooltip')}>↩️</button>
																	{/if}
																</div>
															{:else}<span class="score-display">—</span>{/if}
														{:else}
															{#if canEditPlayerScore(match, 0, myTeamSlotId, isParticipant, currentUser)}
																<input type="number" class="score-input" value={s0 || ''} placeholder="—" on:change={(e) => updateScore(match, 0, e.target.value)} min="0" disabled={match.p[0] === 0 || match.p[1] === 0} />
															{:else if isPlayerLocked(match, 0, myTeamSlotId, isParticipant, currentUser)}
																<span class="score-locked" title={$t('tourneys_score_validated')}>🔒 {s0 ?? 0}</span>
															{:else}
																<span class="score-display">{s0 || '—'}</span>
															{/if}
														{/if}
													</div>
													<div class="match-divider"></div>
													<!-- svelte-ignore a11y-no-static-element-interactions -->
													<div class="player-row {match.p[1] ? 'filled' : ''} {isDone && (lowerIsBetter ? s1 < s0 : s1 > s0) ? 'winner' : ''} {isDone && (lowerIsBetter ? s1 > s0 : s1 < s0) ? 'loser' : ''}" class:my-player-highlight={useTeams ? (match.p[1] === myTeamSlotId) : (match.p[1] === currentUser?.id)} on:mouseenter={() => { if(match.p[1]) hoveredPlayerId = match.p[1]; }} on:mouseleave={() => hoveredPlayerId = null}>
														<span class="player-name">{getPlayerName(match.p[1], nameMap)}</span>
														{#if match.p[1] > 0 && seatMap[match.p[1]]}<a href="/dashboard/map?highlight={seatMap[match.p[1]]}" class="seat-badge" title={$t('tourneys_view_on_map')}>📍{seatMap[match.p[1]]}</a>{/if}
														{#if booleanMode}
															{#if canEditPlayerScore(match, 1, myTeamSlotId, isParticipant, currentUser) && !isDone}
																<div class="bool-btns">
																	<button class="bool-btn bool-check" on:click={() => setBoolScore(match, 1)} title="Vainqueur"><span class="bool-default">☐</span><span class="bool-hover">✅</span></button>
																</div>
															{:else if isDone}
																<div class="bool-badge-container">
																	<span class="bool-badge {(lowerIsBetter ? (s1??0) < (s0??0) : (s1??0) > (s0??0)) ? 'win' : ((s0??0)===(s1??0) && (s0??0)!==0 ? 'draw' : 'lose')}">{(lowerIsBetter ? (s1??0) < (s0??0) : (s1??0) > (s0??0)) ? '✅' : ((s0??0)===(s1??0) && (s0??0)!==0 ? '🤝' : '❌')}</span>
																	{#if isAdmin}
																		<button class="bool-reset-btn" on:click={() => resetBoolScore(match)} title={$t('tourneys_reset_score_tooltip')}>↩️</button>
																	{/if}
																</div>
															{:else}<span class="score-display">—</span>{/if}
														{:else}
															{#if canEditPlayerScore(match, 1, myTeamSlotId, isParticipant, currentUser)}
																<input type="number" class="score-input" value={s1 || ''} placeholder="—" on:change={(e) => updateScore(match, 1, e.target.value)} min="0" disabled={match.p[0] === 0 || match.p[1] === 0} />
															{:else if isPlayerLocked(match, 1, myTeamSlotId, isParticipant, currentUser)}
																<span class="score-locked" title={$t('tourneys_score_validated')}>🔒 {s1 ?? 0}</span>
															{:else}
																<span class="score-display">{s1 || '—'}</span>
															{/if}
														{/if}
													</div>
													{#if getPendingProgress(match, 0, pendingTick) !== null || getPendingProgress(match, 1, pendingTick) !== null}
														<div class="score-pending">
															<div class="score-pending-bar" style="width:{((getPendingProgress(match, 0, pendingTick) ?? getPendingProgress(match, 1, pendingTick)) * 100).toFixed(0)}%"></div>
															<button class="score-pending-cancel" on:click|stopPropagation={() => { cancelPendingScore(match, getPendingProgress(match, 0, pendingTick) !== null ? 0 : 1); }}>✕ {$t('info_btn_cancel')}</button>
														</div>
													{/if}
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
				{#if arrowLeft}<div class="pan-arrow pan-arrow-left" on:click={() => panTo(150, 0)}>‹</div>{/if}
				{#if arrowRight}<div class="pan-arrow pan-arrow-right" on:click={() => panTo(-150, 0)}>›</div>{/if}
				{#if arrowUp}<div class="pan-arrow pan-arrow-up" on:click={() => panTo(0, 150)}>‹</div>{/if}
				{#if arrowDown}<div class="pan-arrow pan-arrow-down" on:click={() => panTo(0, -150)}>‹</div>{/if}
			</div>
		{/if}
	{:else}
		<div class="bracket-empty">
			<span class="bracket-empty-icon">🏟️</span>
			<p>{$t('tourneys_detail_empty_bracket')}</p>
		</div>
	{/if}
</div>

<style>
	.section-title { display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.75rem; }
	.section-title h3 { font-size: 0.8rem; font-weight: 700; text-transform: uppercase; letter-spacing: 0.04em; color: var(--text-dim); margin: 0; }
	.btn-xs { padding: 0.3rem 0.6rem; font-size: 0.7rem; }

	/* Bracket Section */
	.bracket-section { padding: 1rem; border-radius: 14px; display: flex; flex-direction: column; }
	.bracket-section.bracket-expanded { flex-grow: 1; min-height: 400px; }
	.bracket-viewport-wrapper { position: relative; flex-grow: 1; min-height: 450px; }
	.bracket-viewport { position: absolute; inset: 0; overflow: hidden; cursor: grab; background: var(--surface-sunken); border-radius: 10px; border: 1px solid var(--glass-border); user-select: none; -webkit-user-select: none; }
	.bracket-viewport:active { cursor: grabbing; }
	.bracket-canvas { transform-origin: 0 0; transition: transform 0.1s ease-out; padding: 2rem; display: inline-block; min-width: 100%; min-height: 100%; }
	.rounds-container { display: flex; gap: 3rem; }
	.round-col.finale-col { margin-left: 2rem; }
	.finale-header { font-size: 0.85rem !important; color: #fbbf24 !important; }
	.round-col { display: flex; flex-direction: column; gap: 0.75rem; }
	.round-header { text-align: center; font-weight: 700; color: var(--accent); text-transform: uppercase; font-size: 0.8rem; letter-spacing: 1px; margin-bottom: 0.5rem; }
	.matches-col { display: flex; flex-direction: column; justify-content: space-around; flex-grow: 1; gap: 1.5rem; position: relative; }
	.bracket-match { width: 240px; background: var(--hover-tint); border: 1px solid var(--glass-border); border-radius: 8px; overflow: hidden; box-shadow: 0 2px 4px rgba(0,0,0,0.15); transition: border-color 0.2s, box-shadow 0.2s, transform 0.2s; }
	.player-row { display: flex; align-items: center; justify-content: space-between; padding: 0.55rem 0.85rem; font-size: 0.85rem; background: var(--surface-sunken); color: var(--text-muted); cursor: default; }
	.player-row.filled { color: var(--text-main); background: var(--accent-soft); }
	.my-player-highlight {
		border-left: 4px solid var(--highlight-border, #d8b4fe) !important;
		background: var(--highlight-bg, rgba(168, 85, 247, 0.28)) !important;
		box-shadow: inset 0 0 6px var(--highlight-glow, rgba(168, 85, 247, 0.35)) !important;
	}
	.my-player-highlight.rr-p,
	.my-player-highlight .player-name,
	.my-player-highlight .ffa-name {
		color: var(--highlight-text, #f5f3ff) !important;
		text-shadow: 0 0 6px var(--highlight-glow, rgba(168, 85, 247, 0.35));
		font-weight: 800 !important;
	}
	.player-row.winner { background: rgba(34,197,94,0.15); color: #4ade80; }
	.player-row.winner .score-input, .player-row.winner .score-display { color: #4ade80; }
	.player-row.loser { opacity: 0.45; }
	.bracket-match.match-done { border-color: rgba(34,197,94,0.3); }
	.bracket-match.player-highlight { border-color: rgba(56,189,248,0.7); box-shadow: 0 0 12px rgba(56,189,248,0.4), inset 0 0 8px rgba(56,189,248,0.05); transform: scale(1.03); z-index: 10; }
	.player-name { flex-grow: 1; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; font-weight: 600; font-size: 0.85rem; }
	.seat-badge { flex-shrink: 0; display: inline-flex; align-items: center; padding: 0.1rem 0.35rem; margin-left: 0.3rem; font-size: 0.55rem; font-weight: 700; color: var(--accent); background: rgba(59,130,246,0.1); border: 1px solid rgba(59,130,246,0.25); border-radius: 4px; text-decoration: none; white-space: nowrap; transition: all 0.15s; vertical-align: middle; }
	.seat-badge:hover { background: rgba(59,130,246,0.25); color: #93c5fd; border-color: rgba(59,130,246,0.5); transform: translateY(-1px); }
	.match-divider { height: 1px; background: var(--glass-border); }
	.score-input { width: 42px; padding: 0.2rem 0.3rem; text-align: center; font-size: 0.75rem; font-weight: 700; background: var(--surface-sunken); border: 1px solid var(--glass-border); border-radius: 4px; color: var(--accent); -moz-appearance: textfield; }
	.score-input::-webkit-inner-spin-button, .score-input::-webkit-outer-spin-button { -webkit-appearance: none; margin: 0; }
	.score-input:focus { border-color: var(--accent); outline: none; box-shadow: 0 0 6px var(--accent-glow); }
	.score-display { font-size: 0.82rem; font-weight: 700; color: var(--accent); min-width: 20px; text-align: center; }
	.score-locked { font-size: 0.75rem; color: var(--text-muted); opacity: 0.7; cursor: not-allowed; transition: opacity 0.2s; display: flex; align-items: center; gap: 0.15rem; }
	.score-locked:hover { opacity: 1; }

	/* Pan Arrows */
	.pan-arrow { position: absolute; display: flex; align-items: center; justify-content: center; color: var(--accent); font-size: 1.4rem; font-weight: 900; opacity: 0.6; pointer-events: auto; cursor: pointer; z-index: 5; animation: panArrowPulse 1.5s ease-in-out infinite; transition: opacity 0.15s, transform 0.15s; }
	.pan-arrow:hover { opacity: 1; animation: none; }
	.pan-arrow-left { left: 6px; top: 50%; transform: translateY(-50%); width: 28px; height: 50px; background: linear-gradient(90deg, rgba(59,130,246,0.15), transparent); border-radius: 6px; }
	.pan-arrow-right { right: 6px; top: 50%; transform: translateY(-50%); width: 28px; height: 50px; background: linear-gradient(-90deg, rgba(59,130,246,0.15), transparent); border-radius: 6px; }
	.pan-arrow-up { top: 6px; left: 50%; transform: translateX(-50%) rotate(90deg); width: 28px; height: 50px; background: linear-gradient(90deg, rgba(59,130,246,0.15), transparent); border-radius: 6px; }
	.pan-arrow-down { bottom: 6px; left: 50%; transform: translateX(-50%) rotate(-90deg); width: 28px; height: 50px; background: linear-gradient(90deg, rgba(59,130,246,0.15), transparent); border-radius: 6px; }
	@keyframes panArrowPulse { 0%, 100% { opacity: 0.4; } 50% { opacity: 0.85; } }

	/* Score Pending */
	.score-pending { position: relative; width: 100%; height: 16px; background: rgba(0,0,0,0.2); border-radius: 0 0 8px 8px; overflow: hidden; display: flex; align-items: center; }
	.score-pending-bar { position: absolute; left: 0; top: 0; height: 100%; background: linear-gradient(90deg, #3b82f6, #60a5fa); border-radius: 0 0 0 8px; transition: width 0.1s linear; }
	.score-pending-cancel { position: relative; z-index: 2; width: 100%; background: none; border: none; color: rgba(255,255,255,0.8); font-size: 0.6rem; font-weight: 600; cursor: pointer; text-align: center; padding: 0; line-height: 16px; transition: color 0.2s; }
	.score-pending-cancel:hover { color: #f87171; }
	.rr-pending { border-radius: 6px; margin-top: 0.25rem; }
	.bracket-empty { padding: 3rem; text-align: center; color: var(--text-dim); display: flex; flex-direction: column; align-items: center; gap: 0.5rem; }
	.bracket-empty-icon { font-size: 2rem; opacity: 0.4; }
	.bracket-empty p { margin: 0; font-size: 0.85rem; }

	/* Round Robin */
	.rr-container { padding: 0.5rem; display: flex; flex-wrap: wrap; gap: 1rem; overflow-y: auto; max-height: 50vh; }
	.rr-round { min-width: 280px; flex: 1; }
	.rr-round-hdr { text-align: center; font-weight: 800; color: var(--accent); font-size: 0.7rem; text-transform: uppercase; letter-spacing: 1px; margin-bottom: 0.5rem; padding-bottom: 0.3rem; border-bottom: 1px solid var(--glass-border); }
	.rr-match { display: flex; align-items: center; justify-content: space-between; padding: 0.4rem 0.6rem; margin-bottom: 0.3rem; background: var(--surface-sunken); border-radius: 8px; border: 1px solid transparent; font-size: 0.78rem; }
	.rr-match.match-done { border-color: rgba(34,197,94,0.25); }
	.rr-p { flex: 1; font-weight: 600; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; color: var(--text-muted); }
	.rr-p.winner { color: #4ade80; }
	.rr-p:last-child { text-align: right; }
	.rr-scores { display: flex; align-items: center; gap: 0.3rem; flex-shrink: 0; }
	.rr-vs { color: var(--text-dim); font-size: 0.7rem; }
	.rr-score { font-weight: 800; color: var(--accent); min-width: 16px; text-align: center; }

	/* Double Elim */
	.de-label { padding: 0.4rem 0.8rem; font-weight: 800; font-size: 0.7rem; text-transform: uppercase; letter-spacing: 1px; color: var(--accent); border-bottom: 2px solid var(--accent); margin-bottom: 0.5rem; }
	.de-label.lb { color: #f59e0b; border-bottom-color: #f59e0b; margin-top: 1.5rem; }
	.lb-section { border-left: 2px solid rgba(245,158,11,0.2); padding-left: 0.5rem; }
	.lb-hdr { color: #f59e0b !important; }
	.lb-match { border-color: rgba(245,158,11,0.15) !important; }

	/* FFA */
	.ffa-container { padding: 0.5rem; display: flex; flex-direction: column; gap: 1rem; max-height: 55vh; overflow-y: auto; }
	.ffa-round { border-radius: 10px; padding: 0.75rem; border: 1px solid var(--glass-border); }
	.ffa-current { background: rgba(59,130,246,0.06); border-color: rgba(59,130,246,0.2); }
	.ffa-past { opacity: 0.55; }
	.ffa-round-hdr { display: flex; justify-content: space-between; align-items: center; font-weight: 800; font-size: 0.75rem; text-transform: uppercase; letter-spacing: 1px; color: var(--accent); margin-bottom: 0.6rem; padding-bottom: 0.4rem; border-bottom: 1px solid var(--glass-border); }
	.ffa-player-count { font-weight: 600; color: var(--text-muted); font-size: 0.65rem; }
	.ffa-players { display: flex; flex-direction: column; gap: 0.25rem; }
	.ffa-player-row { display: flex; align-items: center; gap: 0.6rem; padding: 0.35rem 0.5rem; border-radius: 6px; background: var(--surface-sunken); font-size: 0.78rem; }
	.ffa-gold { background: rgba(255,215,0,0.12) !important; border-left: 3px solid #ffd700; }
	.ffa-silver { background: rgba(192,192,192,0.1) !important; border-left: 3px solid #c0c0c0; }
	.ffa-bronze { background: rgba(205,127,50,0.1) !important; border-left: 3px solid #cd7f32; }
	.ffa-player-row.my-player-highlight.ffa-gold { background: rgba(255,215,0,0.15) !important; }
	.ffa-player-row.my-player-highlight.ffa-silver { background: rgba(192,192,192,0.12) !important; }
	.ffa-player-row.my-player-highlight.ffa-bronze { background: rgba(205,127,50,0.12) !important; }
	.ffa-rank { font-weight: 800; min-width: 28px; text-align: center; color: var(--accent); font-size: 0.75rem; }
	.ffa-name { flex: 1; font-weight: 600; }
	.ffa-input { width: 48px !important; text-align: center; }
	.ffa-actions { margin-top: 0.75rem; padding-top: 0.6rem; border-top: 1px solid var(--glass-border); display: flex; flex-direction: column; gap: 0.5rem; }

	/* Boolean Mode */
	.bool-btns { display: flex; gap: 0.2rem; align-items: center; }
	.bool-btn {
		padding: 0.15rem 0.35rem; border-radius: 6px; border: 1px solid var(--glass-border);
		background: transparent; cursor: pointer; font-size: 0.85rem;
		transition: all 0.15s; opacity: 0.5; line-height: 1;
	}
	.bool-btn:hover { opacity: 1; transform: scale(1.15); border-color: rgba(59,130,246,0.4); }
	.bool-btn.bool-draw:hover { border-color: rgba(245,158,11,0.5); background: rgba(245,158,11,0.1); }
	.bool-btn.bool-check .bool-hover { display: none; }
	.bool-btn.bool-check .bool-default { display: inline; }
	.bool-btn.bool-check:hover .bool-hover { display: inline; }
	.bool-btn.bool-check:hover .bool-default { display: none; }
	.bool-btn.bool-check:hover { border-color: rgba(34,197,94,0.5); background: rgba(34,197,94,0.1); }

	.bool-badge { font-size: 0.85rem; min-width: 1.5rem; text-align: center; }
	.bool-badge.win { filter: none; }
	.bool-badge.lose { opacity: 0.5; }
	.bool-badge.draw { filter: none; }

	.bool-btns-rr { display: flex; gap: 0.3rem; align-items: center; justify-content: center; }
	.bool-badge-container { display: inline-flex; align-items: center; gap: 0.25rem; }
	.bool-reset-btn {
		background: transparent; border: none; cursor: pointer; font-size: 0.8rem;
		padding: 0.1rem; border-radius: 4px; transition: all 0.15s; opacity: 0.5;
		line-height: 1; display: inline-flex; align-items: center; justify-content: center;
	}
	.bool-reset-btn:hover { opacity: 1; transform: scale(1.2); }

	.admin-btn { padding: 0.4rem 0.8rem; font-size: 0.72rem; font-weight: 700; border-radius: 8px; border: 1px solid var(--glass-border); cursor: pointer; transition: all 0.2s; background: var(--surface-raised); color: var(--text-dim); }
	.admin-btn:hover { transform: translateY(-1px); }
	.admin-btn.stop { border-color: rgba(239,68,68,0.3); color: var(--danger); }
	.admin-btn.stop:hover { background: rgba(239,68,68,0.15); }
	.inline-confirm { display: inline-flex; align-items: center; gap: 0.4rem; }
	.inline-confirm-label { font-size: 0.65rem; font-weight: 700; color: var(--text-main); white-space: nowrap; }
	.admin-btn.confirm-yes { border-color: rgba(34,197,94,0.4); color: var(--success); font-weight: 800; }
	.admin-btn.confirm-yes:hover { background: rgba(34,197,94,0.2); }
	.admin-btn.confirm-no { border-color: rgba(239,68,68,0.3); color: var(--danger); padding: 0.2rem 0.5rem; min-width: unset; }
	.admin-btn.confirm-no:hover { background: rgba(239,68,68,0.15); }
</style>
