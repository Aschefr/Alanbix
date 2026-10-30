<script>
	import { t } from '$lib/i18nStore';
	import { get } from 'svelte/store';
	import { createEventDispatcher, onDestroy } from 'svelte';
	import Icon from '$lib/components/Icon.svelte';

	export let selected;
	export let hasBracket = false;
	export let bracketType = 'single_elim';
	export let bracketRounds = [];
	export let wbRounds = [];
	export let lbRounds = [];
	export let lbRoundsRaw = [];
	export let rrGroups = [];
	export let groupTables = null; // { groupNumber: [row, ...] } from /group-stage (groups + knockout)
	export let groupAdvancers = 0;
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
		onMouseUp();
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
		dispatch('advanceFFA', { keepCount: ffaKeepCount, perMatch: true });
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

	// Round robin: one match open for admin score entry at a time, journées collapsible
	let rrOpenKey = null;
	let rrToggled = {};
	function rrKey(m) { return `${m.id?.g ?? 0}_${m.id?.s}_${m.id?.r}_${m.id?.m}`; }
	function isRRDone(m) {
		const a = m.score?.[0] ?? null, b = m.score?.[1] ?? null;
		return a !== null && b !== null && (a !== 0 || b !== 0) && (a !== b || !!selected?.config?.allow_draws);
	}
	// group cards: my group first, matches folded away unless it is mine (or the only one)
	let rrMatchesOpen = {};
	function isMineMatch(m) {
		return useTeams ? (m.p[0] === myTeamSlotId || m.p[1] === myTeamSlotId) : (m.p[0] === currentUser?.id || m.p[1] === currentUser?.id);
	}
	function groupHasMine(group) { return group.rounds.some(r => r.some(isMineMatch)); }
	function groupCounts(group) {
		const all = group.rounds.flat();
		return { total: all.length, played: all.filter(isRRDone).length };
	}
	$: orderedGroups = [...rrGroups].sort((a, b) => Number(groupHasMine(b)) - Number(groupHasMine(a)));
	function matchesOpen(group, mine) {
		return rrMatchesOpen[group.id] ?? (mine || rrGroups.length === 1 || !groupTables);
	}
	function currentRRRound(group) {
		const i = group.rounds.findIndex(r => r.some(m => !isRRDone(m)));
		return i === -1 ? group.rounds.length - 1 : i;
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
		if (userId === 0) return get(t)('tourneys_tbd');
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
		// Free movement, as long as a slice of the bracket stays on screen
		const keepX = Math.min(cw, vw) * 0.3, keepY = Math.min(ch, vh) * 0.3;
		panX = Math.min(vw - keepX, Math.max(panX, keepX - cw));
		panY = Math.min(vh - keepY, Math.max(panY, keepY - ch));
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

	// Gesture state
	let touchMode = 'none'; // 'none' | 'pan' | 'pinch'
	let initialPinchDist = 0;
	let initialScale = 1;
	let pinchCenter = { x: 0, y: 0 };

	function getTouchDist(t1, t2) {
		const dx = t1.clientX - t2.clientX;
		const dy = t1.clientY - t2.clientY;
		return Math.hypot(dx, dy);
	}

	function getTouchCenter(t1, t2) {
		return {
			x: (t1.clientX + t2.clientX) / 2,
			y: (t1.clientY + t2.clientY) / 2
		};
	}

	function onMouseDown(e) {
		isDragging = true;
		startX = e.clientX - panX;
		startY = e.clientY - panY;
		// Follow the mouse even outside the frame, until the button is released
		window.addEventListener('mousemove', onMouseMove);
		window.addEventListener('mouseup', onMouseUp);
	}

	function onMouseMove(e) {
		if (!isDragging) return;
		panX = e.clientX - startX;
		panY = e.clientY - startY;
		clampPan();
	}

	function onMouseUp() {
		isDragging = false;
		window.removeEventListener('mousemove', onMouseMove);
		window.removeEventListener('mouseup', onMouseUp);
	}

	function onTouchStart(e) {
		if (e.touches.length === 1) {
			touchMode = 'pan';
			isDragging = true;
			startX = e.touches[0].clientX - panX;
			startY = e.touches[0].clientY - panY;
		} else if (e.touches.length >= 2) {
			touchMode = 'pinch';
			isDragging = false;
			initialPinchDist = getTouchDist(e.touches[0], e.touches[1]);
			initialScale = scale;
			pinchCenter = getTouchCenter(e.touches[0], e.touches[1]);
		}
	}

	function onTouchMove(e) {
		if (touchMode === 'pan' && e.touches.length === 1 && isDragging) {
			if (e.cancelable) e.preventDefault();
			e.stopPropagation();
			panX = e.touches[0].clientX - startX;
			panY = e.touches[0].clientY - startY;
			clampPan();
		} else if (touchMode === 'pinch' && e.touches.length >= 2) {
			if (e.cancelable) e.preventDefault();
			e.stopPropagation();
			const currentDist = getTouchDist(e.touches[0], e.touches[1]);
			if (initialPinchDist > 5 && currentDist > 5) {
				const ratio = currentDist / initialPinchDist;
				const newScale = Math.min(Math.max(ZOOM_MIN, initialScale * ratio), ZOOM_MAX);
				if (viewportEl && scale > 0) {
					const rect = viewportEl.getBoundingClientRect();
					const mx = pinchCenter.x - rect.left;
					const my = pinchCenter.y - rect.top;
					panX = mx - (mx - panX) * (newScale / scale);
					panY = my - (my - panY) * (newScale / scale);
				}
				scale = newScale;
				clampPan();
			}
		}
	}

	function onTouchEnd(e) {
		if (e.touches.length === 1) {
			touchMode = 'pan';
			isDragging = true;
			startX = e.touches[0].clientX - panX;
			startY = e.touches[0].clientY - panY;
		} else if (e.touches.length === 0) {
			touchMode = 'none';
			isDragging = false;
			initialPinchDist = 0;
		}
	}

	export function zoomIn() {
		const newScale = Math.min(scale * 1.25, ZOOM_MAX);
		if (viewportEl) {
			const mx = viewportEl.clientWidth / 2;
			const my = viewportEl.clientHeight / 2;
			panX = mx - (mx - panX) * (newScale / scale);
			panY = my - (my - panY) * (newScale / scale);
		}
		scale = newScale;
		clampPan();
	}

	export function zoomOut() {
		const newScale = Math.max(scale * 0.8, ZOOM_MIN);
		if (viewportEl) {
			const mx = viewportEl.clientWidth / 2;
			const my = viewportEl.clientHeight / 2;
			panX = mx - (mx - panX) * (newScale / scale);
			panY = my - (my - panY) * (newScale / scale);
		}
		scale = newScale;
		clampPan();
	}

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

	// ---- Free-for-all tree: rounds left to right, lobbies stacked, links from the lobbies players came from
	const FFA_COL_W = 250, FFA_GAP_X = 90, FFA_ROW_H = 30, FFA_BOX_HEAD = 30, FFA_BOX_PAD = 10, FFA_GAP_Y = 22, FFA_HDR_H = 48, FFA_ACTIONS_H = 150;
	function computeFFALayout(rounds) {
		const boxes = [], edges = [], cols = [];
		let prev = [];
		rounds.forEach((matches, ri) => {
			const x = ri * (FFA_COL_W + FFA_GAP_X);
			cols.push({ x, ri, latest: ri === rounds.length - 1 });
			const items = matches.map((match, mi) => ({
				match, mi, ri, x, y: 0, latest: ri === rounds.length - 1,
				h: FFA_BOX_HEAD + match.p.length * FFA_ROW_H + FFA_BOX_PAD, sources: [], want: null
			}));
			items.forEach(it => {
				if (ri === 0) return;
				const pids = new Set(it.match.p.filter(Boolean));
				it.sources = prev.filter(pb => pb.match.p.some(pid => pid && pids.has(pid)));
				const centers = it.sources.map(sb => sb.y + sb.h / 2);
				it.want = centers.length ? centers.reduce((a, b) => a + b, 0) / centers.length - it.h / 2 : null;
			});
			let cursor = FFA_HDR_H;
			const order = ri === 0 ? items : [...items].sort((a, b) => (a.want ?? 1e9) - (b.want ?? 1e9) || a.mi - b.mi);
			order.forEach(it => {
				it.y = Math.max(it.want ?? cursor, cursor);
				cursor = it.y + it.h + FFA_GAP_Y;
			});
			items.forEach(it => it.sources.forEach(sb => {
				const x1 = sb.x + FFA_COL_W, y1 = sb.y + sb.h / 2, x2 = it.x, y2 = it.y + it.h / 2;
				const mx = (x1 + x2) / 2;
				edges.push({ d: `M ${x1} ${y1} C ${mx} ${y1}, ${mx} ${y2}, ${x2} ${y2}`, key: `${sb.ri}-${sb.mi}-${it.mi}` });
			}));
			boxes.push(...items);
			prev = items;
		});
		const latestBottom = Math.max(0, ...boxes.filter(b => b.latest).map(b => b.y + b.h));
		const width = Math.max(1, rounds.length * (FFA_COL_W + FFA_GAP_X) - FFA_GAP_X);
		const height = Math.max(FFA_HDR_H, ...boxes.map(b => b.y + b.h)) + FFA_ACTIONS_H;
		return { boxes, edges, cols, width, height, actionsY: latestBottom + 16, actionsX: cols.length ? cols[cols.length - 1].x : 0 };
	}
	$: ffaLayout = bracketType === 'ffa' ? computeFFALayout(bracketRounds) : { boxes: [], edges: [], cols: [], width: 1, height: 1, actionsY: 0, actionsX: 0 };

	// qualifiers per lobby: the tournament setting is the default for every new round
	let ffaRoundsSeen = 0;
	$: if (bracketType === 'ffa' && bracketRounds.length !== ffaRoundsSeen) {
		ffaRoundsSeen = bracketRounds.length;
		ffaKeepCount = Math.max(1, Number(selected?.config?.ffa_advancers) || 1);
	}
	// the tree changes size when a round is added: fit it again
	let ffaFitted = 0;
	$: if (bracketType === 'ffa' && viewportEl && canvasEl && bracketRounds.length !== ffaFitted) {
		ffaFitted = bracketRounds.length;
		setTimeout(() => resetZoom(), 0);
	}

	$: arrowLeft = panX < -10;
	$: arrowRight = viewportEl && canvasEl ? (panX + canvasEl.scrollWidth * scale > viewportEl.clientWidth + 10) : false;
	$: arrowUp = panY < -10;
	$: arrowDown = viewportEl && canvasEl ? (panY + canvasEl.scrollHeight * scale > viewportEl.clientHeight + 10) : false;
</script>

<div class="bracket-section glass" class:bracket-expanded={hasBracket}>
	<div class="section-title">
		<h3>{bracketType === 'round_robin' ? $t('admin_tourneys_wizard_format_championship') : bracketType === 'ffa' ? $t('tourneys_format_ffa') : $t('tourneys_tab_bracket')}</h3>
		{#if hasBracket && bracketType !== 'round_robin'}
			<button class="btn-secondary btn-xs" on:click={resetZoom}>{$t('tourneys_btn_recenter')}</button>
		{/if}
	</div>
	{#if hasBracket}
		{#if bracketType === 'ffa'}
			<!-- Free-for-all tree (pan / zoom like the elimination bracket) -->
			<!-- svelte-ignore a11y-no-static-element-interactions -->
			<div class="bracket-viewport-wrapper">
				<div class="bracket-viewport" bind:this={viewportEl} on:wheel={onWheel} on:mousedown={onMouseDown} on:touchstart={onTouchStart} on:touchmove={onTouchMove} on:touchend={onTouchEnd} on:touchcancel={onTouchEnd}>
					<div class="bracket-canvas" bind:this={canvasEl} style="transform: translate({panX}px, {panY}px) scale({scale});">
						<div class="ffa-tree" style="width: {ffaLayout.width}px; height: {ffaLayout.height}px;">
							<svg class="ffa-edges" width={ffaLayout.width} height={ffaLayout.height} aria-hidden="true">
								{#each ffaLayout.edges as e (e.key)}
									<path d={e.d} />
								{/each}
							</svg>

							{#each ffaLayout.cols as col}
								<div class="ffa-col-head" class:current={col.latest} style="left: {col.x}px; width: {FFA_COL_W}px;">
									<span>{$t('tourneys_round_number', { num: col.ri + 1 })}</span>
									{#if isAdmin && col.latest && col.ri > 0 && selected?.status === 'RUNNING'}
										{#if confirmingRollback}
											<span class="ffa-confirm">
												<span>{$t('admin_tourneys_confirm_delete')}</span>
												<button class="ffa-mini yes" on:mousedown|stopPropagation on:click|stopPropagation|preventDefault={handleRollbackFFA} aria-label={$t('admin_tourneys_confirm_yes')}><Icon name="check" size={13} /></button>
												<button class="ffa-mini no" on:mousedown|stopPropagation on:click|stopPropagation|preventDefault={() => confirmingRollback = false} aria-label={$t('admin_tourneys_confirm_no')}><Icon name="x" size={13} /></button>
											</span>
										{:else}
											<button class="ffa-mini no" on:mousedown|stopPropagation on:click|stopPropagation|preventDefault={() => confirmingRollback = true} title={$t('tourneys_ffa_rollback_tooltip')} aria-label={$t('tourneys_ffa_rollback_tooltip')}><Icon name="x" size={13} /></button>
										{/if}
									{/if}
								</div>
							{/each}

							{#each ffaLayout.boxes as box (`${box.ri}-${box.match.id.m}`)}
								{@const match = box.match}
								<div class="ffa-match-box" class:ffa-box-current={box.latest} style="left: {box.x}px; top: {box.y}px; width: {FFA_COL_W}px; height: {box.h}px;">
									<div class="ffa-player-count">{$t('tourneys_ffa_match_label', { n: box.mi + 1 })} · {$t(match.p.length > 1 ? 'admin_tourneys_players_count_plural' : 'admin_tourneys_players_count_singular', { count: match.p.length })}</div>
									<div class="ffa-players">
										{#each match.p as playerId, pi}
											{@const mRank = getFFAMatchRank(match, pi, lowerIsBetter)}
											<div class="ffa-player-row {mRank === 1 ? 'ffa-gold' : mRank === 2 ? 'ffa-silver' : mRank === 3 ? 'ffa-bronze' : ''}" class:my-player-highlight={useTeams ? (playerId === myTeamSlotId) : (playerId === currentUser?.id)}>
												<span class="ffa-rank">{#if mRank}#{mRank}{:else}—{/if}</span>
												<span class="ffa-name">{getPlayerName(playerId, nameMap)}</span>
												{#if canEditPlayerScore(match, pi, myTeamSlotId, isParticipant, currentUser) && box.latest}
													<input type="number" class="score-input ffa-input" value={match.score?.[pi] || ''} placeholder={$t('tourneys_score_placeholder')}
														on:mousedown|stopPropagation on:touchstart|stopPropagation
														on:change={(e) => updateFFAPlacement(match, pi, e.target.value)} min="0" />
												{:else if isPlayerLocked(match, pi, myTeamSlotId, isParticipant, currentUser)}
													<span class="score-locked ffa-input" title={$t('tourneys_score_validated')}><Icon name="lock" size={12} /> {match.score?.[pi]}</span>
												{:else if match.score?.[pi] > 0}
													<span class="score-display ffa-input">{match.score[pi]}</span>
												{/if}
											</div>
										{/each}
									</div>
								</div>
							{/each}

							{#if isAdmin && selected?.status === 'RUNNING' && ffaLayout.boxes.filter(b => b.latest).every(b => b.match.score?.length && b.match.score.every(sc => sc > 0))}
								<!-- svelte-ignore a11y-no-static-element-interactions -->
								<div class="ffa-actions" style="left: {ffaLayout.actionsX}px; top: {ffaLayout.actionsY}px; width: {FFA_COL_W}px;" on:mousedown|stopPropagation on:touchstart|stopPropagation>
									<label class="ffa-keep">
										<span>{$t('tourneys_ffa_keep_players')}</span>
										<input type="number" bind:value={ffaKeepCount} min="1" max={Math.max(1, ...ffaLayout.boxes.filter(b => b.latest).map(b => b.match.p.length))} />
									</label>
									<button class="admin-btn" on:click={handleAdvanceFFA}><Icon name="play" size={14} /> {$t('tourneys_ffa_next_round')}</button>
									<button class="admin-btn stop" on:click={handleFinishFFA}><Icon name="flag" size={14} /> {$t('tourneys_ffa_finish')}</button>
								</div>
							{/if}
						</div>
					</div>
				</div>
			</div>
		{:else if bracketType === 'round_robin'}
			<!-- Round Robin Table -->
			<div class="rr-container">
				<div class="rr-groups-grid" class:single={rrGroups.length === 1}>
				{#each orderedGroups as group (group.id)}
					{@const counts = groupCounts(group)}
					{@const mineGroup = groupHasMine(group)}
					{@const table = groupTables?.[group.id]}
					{@const open = matchesOpen(group, mineGroup)}
					<section class="rr-group" class:mine-group={mineGroup}>
						<header class="rr-group-head">
							{#if rrGroups.length > 1}
								<h4 class="rr-group-title">{$t('spec_group_num', { group: String.fromCharCode(64 + parseInt(group.id)) })}</h4>
							{/if}
							{#if mineGroup}<span class="rr-mine-tag">{$t('groups_my_group')}</span>{/if}
							<span class="rr-group-progress">{counts.played}/{counts.total}</span>
						</header>

						{#if table}
							<table class="rr-table">
								<thead>
									<tr>
										<th class="pos">#</th>
										<th class="nm">{$t('groups_col_player')}</th>
										<th title={$t('groups_col_played_tip')}>{$t('groups_col_played')}</th>
										<th title={$t('groups_col_wins_tip')}>{$t('groups_col_wins')}</th>
										<th title={$t('groups_col_draws_tip')}>{$t('groups_col_draws')}</th>
										<th title={$t('groups_col_losses_tip')}>{$t('groups_col_losses')}</th>
										<th title={$t('groups_col_diff_tip')}>{$t('groups_col_diff')}</th>
										<th class="pts">{$t('groups_col_points')}</th>
									</tr>
								</thead>
								<tbody>
									{#each table as row}
										<tr class:qualified={groupAdvancers > 0 && row.position <= groupAdvancers} class:me={useTeams ? row.entity_id === myTeamSlotId : row.entity_id === currentUser?.id}>
											<td class="pos">{row.position}</td>
											<td class="nm">{getPlayerName(row.entity_id, nameMap)}</td>
											<td>{row.played}</td>
											<td>{row.wins}</td>
											<td>{row.draws}</td>
											<td>{row.losses}</td>
											<td>{row.diff > 0 ? `+${row.diff}` : row.diff}</td>
											<td class="pts">{row.points}</td>
										</tr>
									{/each}
								</tbody>
							</table>
							<button class="rr-matches-toggle" aria-expanded={open} on:click={() => rrMatchesOpen[group.id] = !open}>
								<Icon name={open ? 'chevron-up' : 'chevron-down'} size={14} /> {open ? $t('groups_hide_matches') : $t('groups_show_matches')}
							</button>
						{/if}

						{#if open}
						<div class="rr-group-rounds">
							{#each group.rounds as roundMatches, ri}
								{@const playedCount = roundMatches.filter(m => isRRDone(m)).length}
								{@const roundKey = `${group.id}_${ri}`}
								{@const isCurrent = ri === currentRRRound(group)}
								{@const isOpen = rrToggled[roundKey] ? !(isCurrent || playedCount < roundMatches.length) : (isCurrent || playedCount < roundMatches.length)}
								<div class="rr-round" class:current={isCurrent}>
									<button class="rr-round-hdr" on:click={() => { rrToggled[roundKey] = !rrToggled[roundKey]; }} aria-expanded={isOpen}>
										<span class="rr-round-name">{$t('spec_matchday_num', { num: ri + 1 })}</span>
										{#if isCurrent}<span class="rr-round-live">{$t('tourneys_status_running')}</span>{/if}
										<span class="rr-round-count">{playedCount}/{roundMatches.length}</span>
										<Icon name={isOpen ? 'chevron-up' : 'chevron-down'} size={14} />
									</button>
									{#if isOpen}
									{#each roundMatches as match}
										{@const s0 = match.score?.[0] ?? null}
										{@const s1 = match.score?.[1] ?? null}
										{@const isDone = isRRDone(match)}
										{@const win0 = isDone && (lowerIsBetter ? s0 < s1 : s0 > s1)}
										{@const win1 = isDone && (lowerIsBetter ? s1 < s0 : s1 > s0)}
										{@const mine = useTeams ? (match.p[0] === myTeamSlotId || match.p[1] === myTeamSlotId) : (match.p[0] === currentUser?.id || match.p[1] === currentUser?.id)}
										{@const mKey = rrKey(match)}
										{@const adminEditing = isAdmin && rrOpenKey === mKey}
										<!-- svelte-ignore a11y-click-events-have-key-events a11y-no-static-element-interactions -->
										<div class="rr-match" class:bool-row={booleanMode} class:match-done={isDone} class:mine class:admin-tap={isAdmin} class:editing={adminEditing} on:click={() => { if (isAdmin) rrOpenKey = adminEditing ? null : mKey; }}>
											<span class="rr-p" class:winner={win0} class:loser={isDone && !win0 && win1}>{#if win0}<Icon name="check" size={13} />{/if}{getPlayerName(match.p[0], nameMap)}{#if match.p[0] > 0 && seatMap[match.p[0]]}<a href="/dashboard/map?highlight={seatMap[match.p[0]]}" class="seat-badge" title={$t('tourneys_view_on_map')} on:click|stopPropagation>💺{seatMap[match.p[0]]}</a>{/if}</span>
											<div class="rr-scores">
												{#if booleanMode}
													{#if isDone}
														<div class="bool-badge-container">
															<span class="bool-badge {(lowerIsBetter ? (s0 ?? 0) < (s1 ?? 0) : (s0 ?? 0) > (s1 ?? 0)) ? 'win' : ((s0 ?? 0) === (s1 ?? 0) && (s0 ?? 0) !== 0 ? 'draw' : 'lose')}"><Icon name={(lowerIsBetter ? (s0 ?? 0) < (s1 ?? 0) : (s0 ?? 0) > (s1 ?? 0)) ? 'trophy' : ((s0 ?? 0) === (s1 ?? 0) && (s0 ?? 0) !== 0 ? 'minus' : 'x')} size={15} /></span>
															<span class="rr-vs">-</span>
															<span class="bool-badge {(lowerIsBetter ? (s1 ?? 0) < (s0 ?? 0) : (s1 ?? 0) > (s0 ?? 0)) ? 'win' : ((s0 ?? 0) === (s1 ?? 0) && (s0 ?? 0) !== 0 ? 'draw' : 'lose')}"><Icon name={(lowerIsBetter ? (s1 ?? 0) < (s0 ?? 0) : (s1 ?? 0) > (s0 ?? 0)) ? 'trophy' : ((s0 ?? 0) === (s1 ?? 0) && (s0 ?? 0) !== 0 ? 'minus' : 'x')} size={15} /></span>
															{#if isAdmin}
																<button class="bool-reset-btn" on:click={() => resetBoolScore(match)} title={$t('tourneys_reset_score_tooltip')} aria-label={$t('tourneys_reset_score_tooltip')}><Icon name="restart" size={14} /></button>
															{/if}
														</div>
													{:else if canEditPlayerScore(match, 0, myTeamSlotId, isParticipant, currentUser) || canEditPlayerScore(match, 1, myTeamSlotId, isParticipant, currentUser)}
														<div class="bool-btns-rr">
															<button class="bool-pick" on:click={() => setBoolScore(match, 0)} title={$t('tourneys_win_tooltip', { name: getPlayerName(match.p[0], nameMap) })} aria-label={$t('tourneys_win_tooltip', { name: getPlayerName(match.p[0], nameMap) })}><Icon name="trophy" size={16} /></button>
															{#if selected?.config?.allow_draws}
																<button class="bool-pick draw" on:click={() => setBoolDraw(match)} title={$t('tourneys_draw_tooltip')} aria-label={$t('tourneys_draw_tooltip')}><Icon name="minus" size={16} /></button>
															{/if}
															<button class="bool-pick" on:click={() => setBoolScore(match, 1)} title={$t('tourneys_win_tooltip', { name: getPlayerName(match.p[1], nameMap) })} aria-label={$t('tourneys_win_tooltip', { name: getPlayerName(match.p[1], nameMap) })}><Icon name="trophy" size={16} /></button>
														</div>
													{:else}
														<span class="rr-score">—</span><span class="rr-vs">-</span><span class="rr-score">—</span>
													{/if}
												{:else if isAdmin && !adminEditing}
													<span class="rr-score-text">{isDone ? `${s0} – ${s1}` : '—'}</span>
												{:else}
													<!-- svelte-ignore a11y-click-events-have-key-events a11y-no-static-element-interactions -->
													<span class="rr-edit" on:click|stopPropagation>
													{#if canEditPlayerScore(match, 0, myTeamSlotId, isParticipant, currentUser)}
														<input type="number" class="score-input" value={s0 ?? ''} placeholder="—" on:change={(e) => updateScore(match, 0, e.target.value)} min="0" disabled={match.p[0] === 0 || match.p[1] === 0} />
													{:else if isPlayerLocked(match, 0, myTeamSlotId, isParticipant, currentUser)}
														<span class="score-locked" title={$t('tourneys_score_validated')}>🔒 {s0 ?? 0}</span>
													{:else}
														<span class="rr-score">{isDone ? s0 : '—'}</span>
													{/if}
													<span class="rr-vs">–</span>
													{#if canEditPlayerScore(match, 1, myTeamSlotId, isParticipant, currentUser)}
														<input type="number" class="score-input" value={s1 ?? ''} placeholder="—" on:change={(e) => updateScore(match, 1, e.target.value)} min="0" disabled={match.p[0] === 0 || match.p[1] === 0} />
													{:else if isPlayerLocked(match, 1, myTeamSlotId, isParticipant, currentUser)}
														<span class="score-locked" title={$t('tourneys_score_validated')}>🔒 {s1 ?? 0}</span>
													{:else}
														<span class="rr-score">{isDone ? s1 : '—'}</span>
													{/if}
													</span>
												{/if}
											</div>
											<span class="rr-p" class:winner={win1} class:loser={isDone && !win1 && win0}>{#if match.p[1] > 0 && seatMap[match.p[1]]}<a href="/dashboard/map?highlight={seatMap[match.p[1]]}" class="seat-badge" title={$t('tourneys_view_on_map')} on:click|stopPropagation>💺{seatMap[match.p[1]]}</a>{/if}{getPlayerName(match.p[1], nameMap)}{#if win1}<Icon name="check" size={13} />{/if}</span>
											{#if getPendingProgress(match, 0, pendingTick) !== null || getPendingProgress(match, 1, pendingTick) !== null}
												<div class="score-pending rr-pending">
													<div class="score-pending-bar" style="width:{((getPendingProgress(match, 0, pendingTick) ?? getPendingProgress(match, 1, pendingTick)) * 100).toFixed(0)}%"></div>
													<button class="score-pending-cancel" on:click|stopPropagation={() => { cancelPendingScore(match, getPendingProgress(match, 0, pendingTick) !== null ? 0 : 1); }}>✕ {$t('info_btn_cancel')}</button>
												</div>
											{/if}
										</div>
									{/each}
									{/if}
								</div>
							{/each}
						</div>
						{/if}
					</section>
				{/each}
				</div>
			</div>
		{:else}
			<!-- Duel Bracket (single/double) -->
			<!-- svelte-ignore a11y-no-static-element-interactions -->
			<div class="bracket-viewport-wrapper">
				<div class="bracket-viewport" bind:this={viewportEl} on:wheel={onWheel} on:mousedown={onMouseDown} on:touchstart={onTouchStart} on:touchmove={onTouchMove} on:touchend={onTouchEnd} on:touchcancel={onTouchEnd}>
					<div class="bracket-canvas" bind:this={canvasEl} style="transform: translate({panX}px, {panY}px) scale({scale});">
						{#if bracketType === 'double_elim' && lbRounds.length > 0}
							<div class="de-label">{$t('tourneys_bracket_winners')}</div>
						{/if}
						<div class="rounds-container">
							{#each wbRounds as roundMatches, ri}
								<div class="round-col {ri === wbRounds.length - 1 && wbRounds.length > 1 ? 'finale-col' : ''}">
									<div class="round-header {ri === wbRounds.length - 1 && wbRounds.length > 1 ? 'finale-header' : ''}">{ri === wbRounds.length - 1 && wbRounds.length > 1 ? $t('tourneys_bracket_finale') : $t('tourneys_round_n', { n: ri + 1 })}</div>
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
																<button class="bool-btn bool-check" on:click={() => setBoolScore(match, 0)} title={$t('tourneys_winner_tooltip')}><span class="bool-default">☐</span><span class="bool-hover">✅</span></button>
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
																<button class="bool-btn bool-check" on:click={() => setBoolScore(match, 1)} title={$t('tourneys_winner_tooltip')}><span class="bool-default">☐</span><span class="bool-hover">✅</span></button>
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
							<div class="de-label lb">{$t('tourneys_bracket_losers')}</div>
							<div class="rounds-container lb-section">
								{#each lbRounds as lbRound}
									<div class="round-col">
										<div class="round-header lb-hdr">{lbRound.originalIndex === lbRoundsRaw.length - 1 ? $t('tourneys_bracket_lb_final') : $t('tourneys_bracket_lb_round', { n: lbRound.originalIndex + 1 })}</div>
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
																	<button class="bool-btn bool-check" on:click={() => setBoolScore(match, 0)} title={$t('tourneys_winner_tooltip')}><span class="bool-default">☐</span><span class="bool-hover">✅</span></button>
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
																	<button class="bool-btn bool-check" on:click={() => setBoolScore(match, 1)} title={$t('tourneys_winner_tooltip')}><span class="bool-default">☐</span><span class="bool-hover">✅</span></button>
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
				<!-- Floating Zoom Controls -->
				<div class="bracket-floating-tools">
					<button class="tool-btn" on:click={zoomIn} title={$t('tourneys_zoom_in')} aria-label={$t('tourneys_zoom_in')}>
						<Icon name="plus" size={14} />
					</button>
					<button class="tool-btn" on:click={zoomOut} title={$t('tourneys_zoom_out')} aria-label={$t('tourneys_zoom_out')}>
						<Icon name="minus" size={14} />
					</button>
					<button class="tool-btn" on:click={resetZoom} title={$t('tourneys_btn_recenter')}>
						<Icon name="refresh" size={14} />
					</button>
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
	.section-title h3 { font-size: var(--fs-sub); font-weight: 700; text-transform: uppercase; letter-spacing: 0.04em; color: var(--text-dim); margin: 0; }
	.btn-xs { padding: 0.3rem 0.6rem; font-size: 0.7rem; }

	/* Bracket Section */
	.bracket-section { padding: 1rem; border-radius: 14px; display: flex; flex-direction: column; min-height: 0; }
	.bracket-section.bracket-expanded { flex-grow: 1; min-height: 400px; }
	.bracket-viewport-wrapper { position: relative; flex-grow: 1; min-height: 450px; }
	.bracket-viewport {
		position: relative;
		overflow: hidden;
		width: 100%;
		height: 100%;
		cursor: grab;
		touch-action: none;
		user-select: none;
		-webkit-user-select: none;
		overscroll-behavior: contain;
	}
	.bracket-viewport:active {
		cursor: grabbing;
	}
	.bracket-viewport:active { cursor: grabbing; }
	.bracket-canvas { transform-origin: 0 0; transition: transform 0.1s ease-out; padding: 2rem; display: inline-block; min-width: 100%; min-height: 100%; }
	.rounds-container { display: flex; gap: 3rem; }
	.round-col.finale-col { margin-left: 2rem; }
	.finale-header { font-size: 0.85rem !important; color: #fbbf24 !important; }
	:global([data-theme="light"]) .finale-header { color: #92400e !important; }
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
	/* the groups scroll inside the section: the page itself does not scroll */
	.rr-container { padding: 0.5rem; display: flex; flex-direction: column; gap: 1rem; flex: 1 1 0; min-height: 0; overflow-y: auto; }
	.rr-groups-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(min(100%, 440px), 1fr)); gap: 1rem; align-items: start; }
	@media (max-width: 640px) {
		.rr-match .seat-badge { display: none; }
		.rr-match.bool-row .rr-p:first-child, .rr-match.bool-row .rr-p:last-child { justify-content: flex-start; text-align: left; }
		.rr-match.bool-row .rr-p:first-child { justify-content: flex-end; text-align: right; }
		.bool-pick { width: 30px; height: 30px; }
	}
	.rr-groups-grid.single { grid-template-columns: minmax(0, 1fr); }
	.rr-group { display: flex; flex-direction: column; gap: 0.6rem; padding: 0.8rem 0.9rem; border-radius: 12px; border: 1px solid var(--glass-border); background: var(--surface-raised); min-width: 0; }
	.rr-group.mine-group { border-color: color-mix(in srgb, var(--accent) 55%, var(--glass-border)); }
	.rr-group-head { display: flex; align-items: center; gap: 0.6rem; }
	.rr-group-title { margin: 0; font-family: var(--font-title); font-size: var(--fs-section); font-weight: 700; color: var(--text-main); }
	.rr-mine-tag { font-size: 0.75rem; font-weight: 700; color: var(--accent); background: var(--accent-soft); border: 1px solid color-mix(in srgb, var(--accent) 35%, transparent); border-radius: 999px; padding: 0.1rem 0.55rem; }
	.rr-group-progress { margin-left: auto; font-size: 0.8125rem; font-weight: 700; color: var(--text-dim); font-variant-numeric: tabular-nums; }
	.rr-table { width: 100%; border-collapse: collapse; font-size: 0.8125rem; }
	.rr-table th { text-align: center; font-weight: 600; color: var(--text-dim); padding: 0.25rem 0.3rem; border-bottom: 1px solid var(--glass-border); white-space: nowrap; }
	.rr-table td { text-align: center; padding: 0.3rem; color: var(--text-main); border-bottom: 1px solid color-mix(in srgb, var(--glass-border) 55%, transparent); font-variant-numeric: tabular-nums; }
	.rr-table .nm { text-align: left; max-width: 150px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-weight: 600; }
	.rr-table .pos { width: 1.5rem; color: var(--text-dim); }
	.rr-table .pts { font-weight: 800; color: var(--accent); }
	.rr-table tr.qualified td { background: color-mix(in srgb, var(--success) 8%, transparent); }
	.rr-table tr.qualified .pos { color: var(--success); font-weight: 800; }
	.rr-table tr.me .nm { color: var(--accent); }
	.rr-matches-toggle { align-self: flex-start; display: inline-flex; align-items: center; gap: 0.4rem; background: none; border: none; padding: 0.2rem 0; color: var(--accent); font-size: 0.8125rem; font-weight: 600; cursor: pointer; }
	.rr-matches-toggle:hover { text-decoration: underline; }
	.rr-group-rounds { display: grid; grid-template-columns: minmax(0, 1fr); gap: 0.6rem; align-items: start; }
	.rr-round { min-width: 0; }
	.rr-round-hdr {
		width: 100%; display: flex; align-items: center; gap: 0.5rem;
		background: none; border: none; border-bottom: 1px solid var(--glass-border);
		padding: 0.35rem 0.25rem 0.45rem; margin-bottom: 0.5rem; cursor: pointer;
		color: var(--text-dim); font: inherit;
	}
	.rr-round-name { font-family: var(--font-title); font-weight: 700; font-size: 0.95rem; color: var(--text-main); }
	.rr-round.current .rr-round-hdr { border-bottom-color: var(--accent); }
	.rr-round-live { font-size: 0.72rem; font-weight: 700; color: #fff; background: var(--accent-solid); border-radius: 999px; padding: 0.1rem 0.5rem; }
	.rr-round-count { margin-left: auto; font-size: 0.8rem; font-variant-numeric: tabular-nums; }
	.rr-match {
		display: grid; grid-template-columns: minmax(0, 1fr) auto minmax(0, 1fr); align-items: center; gap: 0.6rem;
		padding: 0.5rem 0.7rem; margin-bottom: 0.3rem; background: var(--surface-sunken);
		border-radius: 8px; border: 1px solid transparent; border-left: 3px solid transparent; font-size: 0.875rem;
	}
	/* win buttons sit right next to the player they credit */
	.rr-match.bool-row .rr-p:first-child { justify-content: flex-end; text-align: right; }
	.rr-match.bool-row .rr-p:last-child { justify-content: flex-start; text-align: left; }
	.rr-match.mine { background: var(--highlight-bg); border-left-color: var(--highlight-border); }
	.rr-match.admin-tap { cursor: pointer; }
	.rr-match.admin-tap:hover, .rr-match.editing { border-color: var(--accent); }
	.rr-p { display: inline-flex; align-items: center; gap: 0.3rem; min-width: 0; font-weight: 600; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; color: var(--text-main); }
	.rr-p:last-child { justify-content: flex-end; text-align: right; }
	.rr-p.winner { font-weight: 800; color: var(--success); }
	.rr-p.loser { color: var(--text-muted); font-weight: 500; }
	.rr-scores { display: flex; align-items: center; justify-content: center; gap: 0.3rem; }
	.rr-edit { display: inline-flex; align-items: center; gap: 0.3rem; }
	.rr-vs { color: var(--text-dim); }
	.rr-score, .rr-score-text { font-weight: 800; color: var(--text-main); min-width: 16px; text-align: center; font-variant-numeric: tabular-nums; }
	.rr-score-text { min-width: 3.2rem; }
	.rr-edit .score-input { width: 52px; height: 36px; font-size: 1rem; text-align: center; border: 1px solid var(--glass-border); background: var(--input-bg); color: var(--input-color); border-radius: 8px; }
	.rr-edit .score-input:focus { border-color: var(--accent); outline: none; box-shadow: 0 0 0 3px var(--accent-soft); }
	.bool-btns-rr { display: inline-flex; align-items: center; gap: 0.3rem; }
	.bool-pick { display: inline-flex; align-items: center; justify-content: center; width: 34px; height: 34px; border-radius: 8px; border: 1px solid var(--glass-border); background: var(--surface-raised); color: var(--text-dim); cursor: pointer; transition: color 0.15s, border-color 0.15s, background 0.15s; }
	.bool-pick:hover { color: var(--success); border-color: var(--success); background: color-mix(in srgb, var(--success) 10%, transparent); }
	.bool-pick.draw:hover { color: var(--warning); border-color: var(--warning); background: color-mix(in srgb, var(--warning) 10%, transparent); }
	.bool-badge { display: inline-flex; align-items: center; justify-content: center; width: 28px; height: 28px; border-radius: 8px; }
	.bool-badge.win { color: var(--success); background: color-mix(in srgb, var(--success) 12%, transparent); }
	.bool-badge.draw { color: var(--warning); background: color-mix(in srgb, var(--warning) 12%, transparent); }
	.bool-badge.lose { color: var(--text-muted); }

	/* Zoom controls themed like the rest of the app */
	.bracket-floating-tools { display: flex; gap: 0.4rem; padding: 0.5rem; }
	.bracket-floating-tools .tool-btn {
		width: 32px; height: 32px; display: inline-flex; align-items: center; justify-content: center;
		background: var(--bg-secondary); color: var(--text-dim);
		border: 1px solid var(--glass-border); border-radius: var(--radius-md); cursor: pointer;
	}
	.bracket-floating-tools .tool-btn:hover { color: var(--accent); border-color: var(--accent); }

	/* Double Elim */
	.de-label { padding: 0.4rem 0.8rem; font-weight: 800; font-size: 0.7rem; text-transform: uppercase; letter-spacing: 1px; color: var(--accent); border-bottom: 2px solid var(--accent); margin-bottom: 0.5rem; }
	.de-label.lb { color: #f59e0b; border-bottom-color: #f59e0b; margin-top: 1.5rem; }
	.lb-section { border-left: 2px solid rgba(245,158,11,0.2); padding-left: 0.5rem; }
	.lb-hdr { color: #f59e0b !important; }
	.lb-match { border-color: rgba(245,158,11,0.15) !important; }

	/* FFA */
	.ffa-tree { position: relative; }
	.ffa-edges { position: absolute; inset: 0; pointer-events: none; overflow: visible; }
	.ffa-edges path { fill: none; stroke: color-mix(in srgb, var(--accent) 45%, var(--glass-border)); stroke-width: 2; }
	.ffa-col-head { position: absolute; top: 0; height: 34px; display: flex; align-items: center; justify-content: space-between; padding: 0 0.6rem; border-radius: 8px; font-weight: 800; font-size: 0.8125rem; text-transform: uppercase; letter-spacing: 0.06em; color: var(--text-dim); border: 1px solid var(--glass-border); background: var(--surface-sunken); }
	.ffa-col-head.current { color: var(--accent); border-color: var(--accent); background: var(--accent-soft); }
	.ffa-confirm { display: inline-flex; align-items: center; gap: 0.3rem; font-size: 0.75rem; text-transform: none; letter-spacing: 0; font-weight: 600; }
	.ffa-mini { display: inline-flex; align-items: center; justify-content: center; width: 22px; height: 22px; border-radius: 6px; border: 1px solid var(--glass-border); background: transparent; color: var(--text-dim); cursor: pointer; }
	.ffa-mini.yes { color: var(--success); border-color: var(--success); }
	.ffa-mini.no:hover { color: var(--danger); border-color: var(--danger); }
	.ffa-match-box { position: absolute; box-sizing: border-box; padding: 0.35rem 0.4rem 0.4rem; border-radius: 10px; border: 1px solid var(--glass-border); background: var(--surface-raised); }
	.ffa-match-box.ffa-box-current { border-color: color-mix(in srgb, var(--accent) 50%, var(--glass-border)); background: var(--surface-raised); }
	.ffa-player-count { height: 22px; display: flex; align-items: center; padding: 0 0.3rem; font-weight: 700; color: var(--text-dim); font-size: 0.75rem; }
	.ffa-players { display: flex; flex-direction: column; gap: 2px; }
	.ffa-player-row { display: flex; align-items: center; gap: 0.5rem; height: 28px; box-sizing: border-box; padding: 0 0.5rem; border-radius: 6px; background: var(--surface-sunken); font-size: 0.8125rem; }
	.ffa-gold { background: rgba(255,215,0,0.12) !important; border-left: 3px solid #ffd700; }
	.ffa-silver { background: rgba(192,192,192,0.1) !important; border-left: 3px solid #c0c0c0; }
	.ffa-bronze { background: rgba(205,127,50,0.1) !important; border-left: 3px solid #cd7f32; }
	.ffa-rank { font-weight: 800; min-width: 26px; text-align: center; color: var(--accent); font-size: 0.75rem; }
	.ffa-name { flex: 1; min-width: 0; font-weight: 600; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
	.ffa-input { width: 48px !important; text-align: center; }
	.ffa-actions { position: absolute; display: flex; flex-direction: column; gap: 0.5rem; padding-top: 0.2rem; }
	.ffa-keep { display: flex; align-items: center; justify-content: space-between; gap: 0.5rem; font-size: 0.8125rem; font-weight: 600; color: var(--text-dim); }
	.ffa-keep input { width: 56px; padding: 0.3rem 0.5rem; border-radius: 6px; background: var(--surface-sunken); border: 1px solid var(--glass-border); color: var(--text-main); text-align: center; }
	.ffa-actions .admin-btn { display: inline-flex; align-items: center; justify-content: center; gap: 0.4rem; margin: 0; }

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

	@media (max-width: 900px) {
		.bracket-section {
			height: 100%;
			flex: 1;
			display: flex;
			flex-direction: column;
			min-height: 0;
			padding: 0.25rem;
			background: transparent;
			border: none;
		}
		.section-title {
			display: none;
		}
		.bracket-viewport-wrapper {
			flex: 1;
			height: 100%;
			min-height: 0;
		}
		.bracket-viewport {
			position: relative;
			overflow: hidden;
			width: 100%;
			height: 100%;
			cursor: grab;
			touch-action: none;
			user-select: none;
			-webkit-user-select: none;
			overscroll-behavior: contain;
		}
		.bracket-viewport:active {
			cursor: grabbing;
		}
		.bracket-canvas {
			padding: 1rem;
		}
		.rounds-container {
			gap: 1.5rem;
		}
		.pan-arrow {
			display: none !important;
		}
		.score-input {
			width: 48px;
			padding: 0.35rem 0.4rem;
			font-size: 0.85rem;
		}
	}
</style>
