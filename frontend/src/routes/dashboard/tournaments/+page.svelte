<script>
	import { t, currentLang } from '$lib/i18nStore';
	import { get } from 'svelte/store';
	import { api } from '$lib/api';
	import { onMount, onDestroy } from 'svelte';
	import { wsMessageStore } from '$lib/ws';
	import { page } from '$app/stores';
	import { authStore } from '$lib/auth';
	import CreateTournamentWizard from '$lib/components/CreateTournamentWizard.svelte';
	import EditTournamentModal from '$lib/components/EditTournamentModal.svelte';

	let tournaments = [];
	let games = [];
	let selectedId = null;
	let participants = [];
	let allUsers = [];
	let currentUser = null;
	let editingTournament = false;
	let editConfig = {};

	let ffaKeepCount = 1;

	let showDetails = true;
	let showLiveStandings = false;

	$: if (selectedId && currentUser) {
		const savedShowDetails = localStorage.getItem('alanbix_show_details');
		if (savedShowDetails !== null) {
			showDetails = savedShowDetails === 'true';
		} else {
			showDetails = true;
		}

		const isFinished = selected?.status === 'DONE' || selected?.status === 'CLOSED';
		const key = isFinished ? 'alanbix_show_finished_standings' : 'alanbix_show_live_standings';
		const savedShowLive = localStorage.getItem(key);
		if (savedShowLive !== null) {
			showLiveStandings = savedShowLive === 'true';
		} else {
			showLiveStandings = isFinished;
		}
	}

	function toggleDetails() {
		showDetails = !showDetails;
		localStorage.setItem('alanbix_show_details', showDetails.toString());
	}

	function toggleLiveStandings() {
		showLiveStandings = !showLiveStandings;
		const isFinished = selected?.status === 'DONE' || selected?.status === 'CLOSED';
		const key = isFinished ? 'alanbix_show_finished_standings' : 'alanbix_show_live_standings';
		localStorage.setItem(key, showLiveStandings.toString());
	}

	// Tournament Creation State
	let showCreateModal = false;
	let teams = [];
	let newTeamName = '';
	let standingsData = [];

	// Bracket pan/zoom
	let scale = 1, panX = 0, panY = 0, isDragging = false, startX, startY;
	let viewportEl, canvasEl;

	// Toast system
	let toasts = [];
	let toastId = 0;

	// Svelte portal action to avoid transform container clipping (G-49 / scroll fix)
	function portal(node) {
		document.body.appendChild(node);
		return {
			destroy() {
				if (node.parentNode) {
					node.parentNode.removeChild(node);
				}
			}
		};
	}
	function toast(msg, type = 'info') {
		const id = ++toastId;
		toasts = [...toasts, { id, message: msg, type, leaving: false }];
		setTimeout(() => {
			toasts = toasts.map(t => t.id === id ? { ...t, leaving: true } : t);
			setTimeout(() => { toasts = toasts.filter(t => t.id !== id); }, 400);
		}, 3000);
	}

	onMount(async () => {
		await loadAll();
		// Check URL ?select= param first
		const urlSelect = $page.url.searchParams.get('select');
		if (urlSelect && tournaments.find(t => t.id === parseInt(urlSelect))) {
			await selectTournament(parseInt(urlSelect));
		} else {
			const saved = localStorage.getItem('alanbix_selected_tournament');
			if (saved && tournaments.find(t => t.id === parseInt(saved))) {
				await selectTournament(parseInt(saved));
			} else if (tournaments.length > 0) {
				await selectTournament(tournaments[0].id);
			}
		}

	});

	// WS: re-fetch data when another client modifies tournament state
	let wsUnsub = null;
	function refreshStandings() {
		if (selectedId) api.get(`/tournaments/${selectedId}/standings`).then(r => { standingsData = r.standings || []; }).catch(() => {});
	}
	$: {
		if (!wsUnsub) {
			wsUnsub = wsMessageStore.subscribe(msg => {
				if (!msg) return;
				if (msg.type === 'teams_updated' && msg.tournament_id && selectedId === msg.tournament_id) {
					api.get(`/tournaments/${msg.tournament_id}/teams`).then(t => { teams = t; }).catch(() => {});
					refreshStandings();
				}
				if ((msg.type === 'score_updated' || msg.type === 'ffa_advanced' || msg.type === 'ffa_rolled_back') && msg.tournament_id) {
					api.get('/tournaments').then(t => { tournaments = t; }).catch(() => {});
					if (selectedId === msg.tournament_id) refreshStandings();
				}
				if (msg.type === 'tournament_started' || msg.type === 'tournament_closed' || msg.type === 'tournament_reopened') {
					api.get('/tournaments').then(t => { tournaments = t; }).catch(() => {});
					if (msg.id && selectedId === msg.id || msg.tournament_id && selectedId === msg.tournament_id) {
						const tid = msg.id || msg.tournament_id;
						api.get(`/tournaments/${tid}/participants`).then(p => { participants = p; }).catch(() => {});
						api.get(`/tournaments/${tid}/teams`).then(t => { teams = t; }).catch(() => {});
						refreshStandings();
					}
				}
				// --- New real-time events ---
				if (msg.type === 'tournament_created' || msg.type === 'tournament_updated') {
					api.get('/tournaments').then(t => { tournaments = t; }).catch(() => {});
					if (msg.type === 'tournament_updated' && msg.data?.id && selectedId === msg.data.id) {
						api.get(`/tournaments/${selectedId}/participants`).then(p => { participants = p; }).catch(() => {});
						api.get(`/tournaments/${selectedId}/teams`).then(t => { teams = t; }).catch(() => {});
						refreshStandings();
					}
				}
				if (msg.type === 'tournament_deleted') {
					api.get('/tournaments').then(t => {
						tournaments = t;
						if (selectedId === msg.tournament_id) {
							selectedId = tournaments.length > 0 ? tournaments[0].id : null;
							if (selectedId) selectTournament(selectedId);
						}
					}).catch(() => {});
				}
				if ((msg.type === 'participant_joined' || msg.type === 'participant_left') && msg.tournament_id) {
					api.get('/tournaments').then(t => { tournaments = t; }).catch(() => {});
					if (selectedId === msg.tournament_id) {
						api.get(`/tournaments/${msg.tournament_id}/participants`).then(p => { participants = p; }).catch(() => {});
						refreshStandings();
					}
				}
			});
		}
	}
	onDestroy(() => {
		if (wsUnsub) wsUnsub();
	});

	async function loadAll() {
		tournaments = await api.get('/tournaments');
		try { games = await api.get('/tournaments/games'); } catch { games = []; }
		try { currentUser = await api.get('/me'); } catch {}
		try { allUsers = await api.get('/room/users'); } catch {}
	}

	async function selectTournament(id) {
		selectedId = id;
		localStorage.setItem('alanbix_selected_tournament', id);
		resetZoom();
		try { participants = await api.get(`/tournaments/${id}/participants`); } catch { participants = []; }
		try { teams = await api.get(`/tournaments/${id}/teams`); } catch { teams = []; }
		try {
			const res = await api.get(`/tournaments/${id}/standings`);
			standingsData = res.standings || [];
		} catch { standingsData = []; }
	}

	async function joinTournament(id) {
		try {
			await api.post(`/tournaments/${id}/join`, {});
			toast($t('tourneys_toast_joined'), 'success');
			tournaments = await api.get('/tournaments');
			await selectTournament(id);
		} catch (e) { toast(e.detail || e.message, 'error'); }
	}

	async function forceAddPlayer(userId) {
		try {
			await api.post(`/tournaments/${selectedId}/join`, { user_id: userId });
			tournaments = await api.get('/tournaments');
			await selectTournament(selectedId);
			toast($t('tourneys_toast_player_added'), 'success');
		} catch (e) { toast(e.message || 'Erreur', 'error'); }
	}

	async function forceRemovePlayer(userId) {
		try {
			await api.delete(`/tournaments/${selectedId}/participants/${userId}`);
			tournaments = await api.get('/tournaments');
			await selectTournament(selectedId);
			toast($t('tourneys_toast_player_removed'), 'success');
		} catch (e) { toast(e.message || 'Erreur', 'error'); }
	}

	let confirmJoinAll = false;
	let confirmLeaveAll = false;

	async function joinAllPlayers() {
		try {
			confirmJoinAll = false;
			const res = await api.post(`/tournaments/${selectedId}/join-all`, {});
			toast(`${res.added} joueur(s) inscrits !`, 'success');
			tournaments = await api.get('/tournaments');
			await selectTournament(selectedId);
		} catch (e) { toast(e.message || 'Erreur', 'error'); confirmJoinAll = false; }
	}

	async function leaveAllPlayers() {
		try {
			confirmLeaveAll = false;
			const res = await api.post(`/tournaments/${selectedId}/leave-all`, {});
			toast(`${res.removed} joueur(s) désinscrits.`, 'success');
			tournaments = await api.get('/tournaments');
			await selectTournament(selectedId);
		} catch (e) { toast(e.message || 'Erreur', 'error'); confirmLeaveAll = false; }
	}

	// Team management
	async function createTeam() {
		if (!newTeamName.trim()) return;
		try {
			await api.post(`/tournaments/${selectedId}/teams`, { name: newTeamName.trim() });
			newTeamName = '';
			teams = await api.get(`/tournaments/${selectedId}/teams`);
			toast($t('tourneys_toast_team_created'), 'success');
		} catch (e) { toast(e.message, 'error'); }
	}

	async function deleteTeam(teamId) {
		try {
			await api.delete(`/tournaments/${selectedId}/teams/${teamId}`);
			teams = await api.get(`/tournaments/${selectedId}/teams`);
		} catch (e) { toast(e.message, 'error'); }
	}

	async function addMemberToTeam(teamId, userId) {
		try {
			await api.post(`/tournaments/${selectedId}/teams/${teamId}/members`, { user_id: userId });
			teams = await api.get(`/tournaments/${selectedId}/teams`);
		} catch (e) { toast(e.message, 'error'); }
	}

	async function removeMemberFromTeam(teamId, userId) {
		try {
			await api.delete(`/tournaments/${selectedId}/teams/${teamId}/members/${userId}`);
			teams = await api.get(`/tournaments/${selectedId}/teams`);
		} catch (e) { toast(e.message, 'error'); }
	}

	async function randomizeTeams() {
		try {
			await api.post(`/tournaments/${selectedId}/teams/randomize`, {});
			teams = await api.get(`/tournaments/${selectedId}/teams`);
			toast($t('tourneys_toast_players_distributed'), 'success');
		} catch (e) { toast(e.message, 'error'); }
	}

	// Admin actions
	async function startTournament() {
		try {
			await api.post(`/tournaments/${selectedId}/start`, {});
			toast($t('tourneys_toast_started'), 'success');
			tournaments = await api.get('/tournaments');
			await selectTournament(selectedId);
		} catch (e) { toast(e.detail || e.message || 'Erreur', 'error'); }
	}

	async function stopTournament() {
		try {
			await api.put(`/tournaments/${selectedId}`, { status: 'DONE' });
			toast($t('tourneys_toast_finished'), 'success');
			tournaments = await api.get('/tournaments');
			await selectTournament(selectedId);
		} catch (e) { toast(e.message || 'Erreur', 'error'); }
	}

	async function resetTournament() {
		try {
			await api.put(`/tournaments/${selectedId}`, { status: 'OPEN', bracket: null });
			toast($t('tourneys_toast_reset'), 'success');
			tournaments = await api.get('/tournaments');
			await selectTournament(selectedId);
		} catch (e) { toast(e.message || 'Erreur', 'error'); }
	}

	let confirmingClose = false;
	async function closeTournament() {
		try {
			confirmingClose = false;
			const res = await api.post(`/tournaments/${selectedId}/close`);
			toast($t('tourneys_toast_closed'), 'success');
			tournaments = await api.get('/tournaments');
			await selectTournament(selectedId);
		} catch (e) { toast(e.message || 'Erreur', 'error'); }
	}

	let confirmingReopen = false;
	let confirmingRollback = false;
	async function reopenTournament() {
		try {
			confirmingReopen = false;
			await api.post(`/tournaments/${selectedId}/reopen`);
			toast($t('tourneys_toast_reopened'), 'success');
			tournaments = await api.get('/tournaments');
			await selectTournament(selectedId);
		} catch (e) { toast(e.message || 'Erreur', 'error'); }
	}

	async function updateFFAPlacement(match, playerIdx, value) {
		const score = [...(match.score || match.p.map(() => 0))];
		score[playerIdx] = parseInt(value) || 0;
		scheduleScore(match, playerIdx, score);
	}

	// --- Delayed Score Submission (5s countdown with progress bar) ---
	const SCORE_DELAY_MS = 5000;
	let pendingScores = {};  // key -> { timer, startTime, score, match }
	let pendingTick = 0;     // Reactive tick to force re-render of progress bars

	function scoreKey(match, playerIdx) {
		return `${match.id.s}_${match.id.r}_${match.id.m}_${playerIdx}`;
	}

	function scheduleScore(match, playerIdx, score) {
		const key = scoreKey(match, playerIdx);
		// Cancel any existing pending submission for this slot
		if (pendingScores[key]?.timer) clearTimeout(pendingScores[key].timer);
		if (pendingScores[key]?.interval) clearInterval(pendingScores[key].interval);

		// Admin bypass: submit immediately
		if (isAdmin) {
			doSubmitScore(match, score, key);
			return;
		}

		const startTime = Date.now();
		const interval = setInterval(() => { pendingTick++; }, 100); // update progress every 100ms
		const timer = setTimeout(() => {
			clearInterval(interval);
			doSubmitScore(match, score, key);
		}, SCORE_DELAY_MS);

		pendingScores[key] = { timer, interval, startTime, score, match };
		pendingScores = pendingScores; // trigger reactivity
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

	async function doSubmitScore(match, score, key) {
		delete pendingScores[key];
		pendingScores = pendingScores;
		try {
			await api.put(`/tournaments/${selectedId}/score`, {
				match_s: match.id.s, match_r: match.id.r, match_m: match.id.m, score
			});
			tournaments = await api.get('/tournaments');
		} catch (e) { toast(e.message || 'Erreur score', 'error'); }
	}

	async function updateScore(match, playerIdx, value) {
		const score = [...(match.score || [null, null])];
		const trimmed = String(value).trim();
		score[playerIdx] = trimmed === '' ? null : (parseInt(trimmed, 10) || 0);
		scheduleScore(match, playerIdx, score);
	}

	// AXE-32: Boolean mode score helpers
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

	async function advanceFFA() {
		try {
			await api.post(`/tournaments/${selectedId}/ffa-advance`, { keep_count: ffaKeepCount });
			toast($t('tourneys_toast_round_advanced', { count: ffaKeepCount }), 'success');
			await loadAll();
			await selectTournament(selectedId);
		} catch (e) { toast(e.detail || e.message || 'Erreur', 'error'); }
	}

	async function finishFFA() {
		try {
			await api.post(`/tournaments/${selectedId}/ffa-finish`, {});
			toast($t('tourneys_toast_ffa_finished'), 'success');
			tournaments = await api.get('/tournaments');
			await selectTournament(selectedId);
		} catch (e) { toast(e.message || 'Erreur', 'error'); }
	}

	async function rollbackFFA() {
		try {
			confirmingRollback = false;
			await api.post(`/tournaments/${selectedId}/ffa-rollback`, {});
			toast($t('tourneys_toast_ffa_rolled_back') || 'Manche supprimée avec succès !', 'success');
			await loadAll();
			await selectTournament(selectedId);
		} catch (e) { toast(e.detail || e.message || 'Erreur', 'error'); }
	}

	// AXE-15: Check if a match is finalized (scores validated)
	function isMatchFinalized(match) {
		const scores = match.score || [];
		if (bracketType === 'ffa') {
			return scores.length > 0 && scores.every(s => s !== null && s > 0);
		}
		// Duel / Round Robin: both scores must be explicit numbers (not null), different, at least one > 0
		if (scores.length >= 2) {
			const s0 = scores[0], s1 = scores[1];
			return s0 !== null && s1 !== null && (s0 !== 0 || s1 !== 0) && s0 !== s1;
		}
		return false;
	}

	function canEditScore(match) {
		if (isAdmin) return true;
		return false;
	}

	function canEditPlayerScore(match, playerIdx, _myTeamSlotId, _isParticipant, _currentUser) {
		if (isAdmin) return true;
		if (!_isParticipant || !_currentUser) return false;
		if (isMatchFinalized(match)) return false;
		const uid = _currentUser.id;
		
		// In FFA, strictly only allow editing your own slot to prevent trolling.
		if (bracketType === 'ffa') {
			const pid = match.p[playerIdx];
			return (pid === uid) || (_myTeamSlotId && pid === _myTeamSlotId);
		}
		
		// For duels/round robin, allow editing both slots so boolean mode and 1v1 score entry work as intended.
		const isInMatch = match.p.some(pid => pid === uid || (_myTeamSlotId && pid === _myTeamSlotId));
		return isInMatch;
	}

	// AXE-15: Check if a player's score slot should show a lock indicator
	function isPlayerLocked(match, playerIdx, _myTeamSlotId, _isParticipant, _currentUser) {
		if (isAdmin) return false;
		if (!_isParticipant || !_currentUser) return false;
		if (!isMatchFinalized(match)) return false;
		const uid = _currentUser.id;
		const isInMatch = match.p.some(pid => pid === uid || (_myTeamSlotId && pid === _myTeamSlotId));
		return isInMatch;
	}

	function openEdit() {
		editConfig = {
			name: selected.name,
			points_per_win: selected.points_per_win || 3,
			use_teams: selected.config?.use_teams || false,
			team_size: selected.config?.team_size || 1,
			bracket_type: selected.config?.bracket_type || 'single_elim',
			pts_winner: selected.config?.pts_winner ?? 10,
			pts_second: selected.config?.pts_second ?? 6,
			pts_third: selected.config?.pts_third ?? 4,
			pts_participation: selected.config?.pts_participation ?? 1,
			pts_per_match: selected.config?.pts_per_match ?? selected.config?.pts_per_goal ?? 1.0,
			lower_score_is_better: selected.config?.lower_score_is_better || false,
			boolean_mode: selected.config?.boolean_mode || false,
			allow_draws: selected.config?.allow_draws || false,
			phases: selected.config?.phases || 'single',
			group_size: selected.config?.group_size || 4,
			advancers_count: selected.config?.advancers_count || 2,
			meet_twice: selected.config?.meet_twice || false,
			ffa_group_size: selected.config?.ffa_group_size || 4,
			ffa_advancers: selected.config?.ffa_advancers || 2
		};
		editingTournament = true;
	}

	async function saveEdit() {
		try {
			await api.put(`/tournaments/${selectedId}`, {
				name: editConfig.name,
				points_per_win: editConfig.points_per_win,
				config: {
					...selected.config,
					use_teams: editConfig.use_teams,
					team_size: editConfig.team_size,
					bracket_type: editConfig.bracket_type,
					pts_winner: editConfig.pts_winner,
					pts_second: editConfig.pts_second,
					pts_third: editConfig.pts_third,
					pts_participation: editConfig.pts_participation,
					pts_per_match: editConfig.pts_per_match,
					lower_score_is_better: editConfig.lower_score_is_better,
					boolean_mode: editConfig.boolean_mode,
					allow_draws: editConfig.allow_draws,
					phases: editConfig.phases,
					group_size: editConfig.group_size,
					advancers_count: editConfig.advancers_count,
					meet_twice: editConfig.meet_twice,
					ffa_group_size: editConfig.ffa_group_size,
					ffa_advancers: editConfig.ffa_advancers
				}
			});
			toast($t('tourneys_toast_updated'), 'success');
			editingTournament = false;
			tournaments = await api.get('/tournaments');
			await selectTournament(selectedId);
		} catch (e) { toast(e.message || 'Erreur', 'error'); }
	}

	function openCreateTournamentModal() {
		showCreateModal = true;
	}

	function getGame(gid) { return games.find(g => g.id === gid) || games.find(g => String(g.id) === String(gid)); }

	let keepCount = 2;
	let lastFFARoundId = '';
	$: currentFFAMatch = (bracketType === 'ffa' && bracketRounds.length > 0) ? bracketRounds[bracketRounds.length - 1][0] : null;
	$: if (currentFFAMatch && (selectedId + '-' + currentFFAMatch.id.r) !== lastFFARoundId) {
		lastFFARoundId = selectedId + '-' + currentFFAMatch.id.r;
		keepCount = Math.max(2, Math.ceil(currentFFAMatch.p.length / 2));
	}

	function bracketLabel(format) {
		if (format === 'single_elim') return get(t)('admin_tourneys_wizard_format_single');
		if (format === 'double_elim') return get(t)('admin_tourneys_wizard_format_double');
		if (format === 'round_robin') return get(t)('admin_tourneys_wizard_format_championship');
		if (format === 'ffa') return 'Free For All';
		return format || get(t)('tourneys_status_unknown');
	}

	// Bracket helpers
	function getRounds(bracket) {
		if (!bracket || !Array.isArray(bracket)) return [];
		const rounds = {};
		bracket.forEach(m => { if (!rounds[m.id.r]) rounds[m.id.r] = []; rounds[m.id.r].push(m); });
		return Object.keys(rounds).sort((a,b) => a-b).map(k => rounds[k]);
	}

	// Reactive player name map — must be passed to getPlayerName in template
	// so Svelte detects nameMap as a direct template dependency and re-renders
	$: nameMap = (() => {
		const m = {};
		participants.forEach(p => { m[p.user_id] = p.username; });
		// Primary source: config._team_map (set at tournament start)
		const tm = selected?.config?._team_map || {};
		Object.entries(tm).forEach(([id, name]) => { m[id] = name; });
		// Fallback: rebuild from live teams data (survives config loss on reopen/re-close)
		teams.forEach(t => { const key = String(-t.id); if (!m[key]) m[key] = t.name; });
		return m;
	})();

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

	// Pan & Zoom (cursor-centered) with clamping (AXE-29)
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
	function resetZoom() {
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

		// Calculate optimal scale factor to fit within viewport with margins
		const scaleX = (vw - 40) / cw;
		const scaleY = (vh - 40) / ch;
		let optimalScale = Math.min(scaleX, scaleY);

		// Clamp optimalScale so that text remains readable (min 0.55, max 1.25)
		optimalScale = Math.max(0.55, Math.min(optimalScale, 1.25));
		scale = optimalScale;

		// Center the bracket canvas in the viewport
		panX = (vw - cw * scale) / 2;
		panY = (vh - ch * scale) / 2;

		clampPan();
	}
	function panTo(dx, dy) { panX += dx; panY += dy; clampPan(); }

	// AXE-29: Directional arrows state
	$: arrowLeft = panX < -10;
	$: arrowRight = viewportEl && canvasEl ? (panX + canvasEl.scrollWidth * scale > viewportEl.clientWidth + 10) : false;
	$: arrowUp = panY < -10;
	$: arrowDown = viewportEl && canvasEl ? (panY + canvasEl.scrollHeight * scale > viewportEl.clientHeight + 10) : false;
	// Force re-evaluation when pan/scale changes
	$: if (panX !== undefined || panY !== undefined || scale) { arrowLeft = panX < -10; arrowRight = viewportEl && canvasEl ? (panX + canvasEl.scrollWidth * scale > viewportEl.clientWidth + 10) : false; arrowUp = panY < -10; arrowDown = viewportEl && canvasEl ? (panY + canvasEl.scrollHeight * scale > viewportEl.clientHeight + 10) : false; }

	// Auto-fit and center bracket on tournament switch
	$: if (selectedId && viewportEl) {
		setTimeout(() => resetZoom(), 150);
	}

	// Player hover tracking for bracket path highlight
	let hoveredPlayerId = null;

	// Seat map: userId -> seatId (for bracket seat badges)
	$: seatMap = Object.fromEntries(allUsers.filter(u => u.seat_id).map(u => [u.id, u.seat_id]));

	$: selected = tournaments.find(t => t.id === selectedId);
	$: selectedGame = selected ? getGame(selected.game_id) : null;
	$: gameMap = Object.fromEntries(games.map(g => [g.id, g]));
	$: unregisteredUsers = allUsers.filter(u => !participants.find(p => p.user_id === u.id));
	$: bracketRounds = selected ? getRounds(selected.bracket) : [];
	$: hasBracket = bracketRounds.length > 0;
	$: isAdmin = currentUser?.is_admin;
	$: isParticipant = participants.some(p => p.user_id === currentUser?.id);
	$: myTeam = teams.find(t => t.members?.some(m => m.user_id === currentUser?.id));
	$: useTeams = selected?.config?.use_teams || false;
	$: myTeamSlotId = (useTeams && myTeam) ? -myTeam.id : null;
	$: bracketType = selected?.config?.bracket_type || 'single_elim';
	$: lowerIsBetter = selected?.config?.lower_score_is_better || false;
	$: booleanMode = selected?.config?.boolean_mode || false;
	$: unassignedPlayers = useTeams ? participants.filter(p => !teams.some(t => t.members?.some(m => m.user_id === p.user_id))) : [];
	$: groupedParticipants = (() => {
		const groups = {};
		participants.forEach(p => {
			const key = p.team_name || '';
			if (!groups[key]) groups[key] = [];
			groups[key].push(p);
		});
		return Object.entries(groups).sort(([a], [b]) => {
			if (!a) return 1;
			if (!b) return -1;
			return a.localeCompare(b);
		});
	})();
	
	// Pool of players available to be assigned to teams (with drain effect)
	$: poolPlayers = useTeams ? unassignedPlayers : participants;
	$: groupedPoolPlayers = (() => {
		const groups = {};
		poolPlayers.forEach(p => {
			const key = p.team_name || '';
			if (!groups[key]) groups[key] = [];
			groups[key].push(p);
		});
		return Object.entries(groups).sort(([a], [b]) => {
			if (!a) return 1;
			if (!b) return -1;
			return a.localeCompare(b);
		});
	})();
	$: groupedUnassigned = (() => {
		const g = {};
		unassignedPlayers.forEach(p => { const k = p.team_name || ''; if (!g[k]) g[k] = []; g[k].push(p); });
		return Object.entries(g).sort(([a], [b]) => (a || 'zzz').localeCompare(b || 'zzz'));
	})();
	$: wbRounds = bracketType === 'double_elim' ? getRounds((selected?.bracket || []).filter(m => m.id.s === 1)) : bracketRounds;
	$: lbRoundsRaw = bracketType === 'double_elim' ? getRounds((selected?.bracket || []).filter(m => m.id.s === 2)) : [];
	$: lbRounds = lbRoundsRaw.map((roundMatches, ri) => {
		// Filter: keep only rounds that have at least one visible match
		const hasVisible = roundMatches.some(m => {
			const isBye = m.p[0] === 0 && m.p[1] === 0;
			const s0 = m.score?.[0] ?? null, s1 = m.score?.[1] ?? null;
			const isDone = s0 !== null && s1 !== null && (s0 !== 0 || s1 !== 0) && s0 !== s1;
			const isAutoWin = (m.p[0] === 0 || m.p[1] === 0) && (s0 > 0 || s1 > 0);
			return !isBye && !isAutoWin;
		});
		return hasVisible ? { matches: roundMatches, originalIndex: ri } : null;
	}).filter(Boolean);

	// --- Live Standings (projection, no DB mutation) ---
	// Standings come from backend (single source of truth)
	$: liveStandings = standingsData.map(s => ({
		id: s.entity_id, name: s.name, pts: s.total, rank: s.rank,
		placement_pts: s.placement_pts, participation_pts: s.participation_pts,
		score_pts: s.score_pts, per_member: s.per_member, member_count: s.member_count,
		wins: s.wins ?? 0, matches_played: s.matches_played ?? 0, pts_per_match: s.pts_per_match ?? 1.0,
		cumulated_score: s.cumulated_score ?? 0
	}));
	$: displayStandings = liveStandings;

	$: rrGroups = (() => {
		if (!selected || !selected.bracket || bracketType !== 'round_robin') return [];
		const groups = {};
		selected.bracket.forEach(m => {
			const gId = m.id.s;
			if (!groups[gId]) groups[gId] = [];
			groups[gId].push(m);
		});
		
		return Object.keys(groups).sort((a,b) => parseInt(a)-parseInt(b)).map(gId => {
			const groupMatches = groups[gId];
			const roundsMap = {};
			groupMatches.forEach(m => {
				if (!roundsMap[m.id.r]) roundsMap[m.id.r] = [];
				roundsMap[m.id.r].push(m);
			});
			const rounds = Object.keys(roundsMap).sort((a,b) => parseInt(a)-parseInt(b)).map(r => roundsMap[r]);
			return {
				id: gId,
				rounds: rounds
			};
		});
	})();

	function getPlayerPts(userId, standings) {
		// In team mode, find user's team and return per_member from backend
		if (useTeams && teams.length > 0) {
			const playerTeam = teams.find(t => t.members?.some(m => m.user_id === userId));
			if (playerTeam) {
				const teamBracketId = -playerTeam.id;
				const teamEntry = standings.find(s => s.id === teamBracketId);
				if (teamEntry) return teamEntry.pts;
			}
		}
		const entry = standings.find(s => s.id === userId);
		return entry ? entry.pts : 0;
	}
</script>

<div class="tournaments-layout">
	<!-- Sidebar -->
	<aside class="t-sidebar glass">
		<div class="sidebar-header">
			<h2>🏆 {$t('tourneys_title')}</h2>
			<span class="t-count">{tournaments.length}</span>
		</div>
		{#if currentUser?.is_admin}
			<div class="sidebar-actions">
				<button class="add-tournament-btn-full" on:click={openCreateTournamentModal}>
					{$t('tourneys_add_btn')}
				</button>
			</div>
		{/if}
		<div class="t-list">
			{#each tournaments as tourney}
				<button class="t-item {selectedId === tourney.id ? 'active' : ''} {tourney.status.toLowerCase()}" on:click={() => selectTournament(tourney.id)} style="background-image: url({gameMap[tourney.game_id]?.image_url || ''})">
					{#if tourney.status === 'CLOSED'}<div class="t-item-checkered"></div>{/if}
					<div class="t-item-overlay">
						<div class="t-item-info">
							<span class="t-item-name">{tourney.name}</span>
							<span class="t-item-meta">{gameMap[tourney.game_id]?.name || '—'}</span>
						</div>
						<span class="t-status-badge {tourney.status.toLowerCase()}">
							{tourney.status === 'OPEN' ? '🟢 ' + $t('tourneys_status_open') : tourney.status === 'RUNNING' ? '🔵 ' + $t('tourneys_status_running') : tourney.status === 'CLOSED' ? '🏁 ' + $t('tourneys_status_closed') : '⚪ ' + $t('tourneys_status_done')}
						</span>
					</div>
				</button>
			{:else}
				<div class="t-empty-sidebar"><span class="text-dim text-xs">{$t("dash_no_tournament")}</span></div>
			{/each}
		</div>
	</aside>

	<!-- Main Detail -->
	<main class="t-detail" class:collapsed-layout={selected?.status === 'RUNNING' && !showDetails}>
		{#if selected}
			<!-- Hero -->
			<div class="detail-hero" style="background-image: url({selectedGame?.image_url || ''})">
				{#if selected.status === 'CLOSED'}<div class="hero-checkered"></div>{/if}
				<div class="hero-overlay">
					<div class="hero-content">
						<span class="status-pill {selected.status.toLowerCase()}">
							{selected.status === 'OPEN' ? '🟢 ' + $t('tourneys_status_open') : selected?.status === 'RUNNING' ? '🔵 ' + $t('tourneys_status_running') : selected.status === 'CLOSED' ? '🏁 ' + $t('tourneys_status_closed') : '⚪ ' + $t('tourneys_status_done')}
						</span>
						<h1>{selected.name}</h1>
						<span class="hero-game">{selectedGame?.name || '—'}</span>
					</div>
					{#if selected.status === 'OPEN'}
						{#if isParticipant}
							<span class="hero-joined">✅ {$t("tourneys_hero_joined")}</span>
						{:else}
							<button class="btn-primary hero-join" on:click={() => joinTournament(selected.id)}>🎮 {$t("tourneys_btn_join_text")}</button>
						{/if}
					{/if}
				</div>
				{#if selectedGame?.rules}
					<div class="hero-rules">
						<span class="hero-rules-label">{$t("tourneys_tab_rules")}</span>
						<p class="hero-rules-text">{selectedGame.rules}</p>
					</div>
				{/if}
			</div>

			<!-- Info Cards -->
			<div class="detail-body" class:collapsed-layout={selected?.status !== 'OPEN' && !showDetails}>
				<div class="controls-row">
					{#if selected?.status === 'RUNNING' || selected?.status === 'DONE' || selected?.status === 'CLOSED'}
						<button class="toggle-details-btn glass" on:click={toggleDetails}>
							{showDetails ? '▲ ' + $t('tourneys_btn_hide_details') : '▼ ' + $t('tourneys_btn_show_details')}
						</button>
					{/if}
					{#if selected?.status === 'RUNNING' || selected?.status === 'DONE' || selected?.status === 'CLOSED'}
						{#if liveStandings.length > 0}
							<button class="toggle-live-btn glass" on:click={toggleLiveStandings}>
								{showLiveStandings ? '◀ ' + ($t('tourneys_hide_standings') || 'Masquer le classement') : '▶ ' + ($t('tourneys_show_standings') || 'Classement live')}
							</button>
						{/if}
					{/if}

					{#if currentUser?.is_admin}
						<div class="admin-bar glass">
							<span class="admin-bar-label">⚙️ {$t("nav_administration")}</span>
							<div class="admin-bar-actions">
								{#if selected.status === 'OPEN'}
									<button class="admin-btn start" on:click={startTournament} disabled={participants.length < 2}>
										▶ {$t('tourneys_btn_start')}{#if participants.length < 2} (min. 2){/if}
									</button>
								{/if}
								{#if selected?.status === 'RUNNING'}
									<button class="admin-btn stop" on:click={stopTournament}>⏹ {$t('tourneys_btn_finish')}</button>
								{/if}
								{#if selected.status === 'DONE'}
									{#if confirmingClose}
										<span class="inline-confirm">
											<span class="inline-confirm-label">{$t("tourneys_confirm_close")}</span>
											<button class="admin-btn confirm-yes" on:click={closeTournament}>✓ {$t("tourneys_confirm_yes")}</button>
											<button class="admin-btn confirm-no" on:click={() => confirmingClose = false}>✕</button>
										</span>
									{:else}
										<button class="admin-btn close" on:click={() => confirmingClose = true}>🏁 {$t("tourneys_btn_close")}</button>
									{/if}
								{/if}
								{#if selected.status === 'CLOSED'}
									{#if confirmingReopen}
										<span class="inline-confirm">
											<span class="inline-confirm-label">{$t("tourneys_confirm_reopen")}</span>
											<button class="admin-btn confirm-yes" on:click={reopenTournament}>✓ {$t("tourneys_confirm_yes")}</button>
											<button class="admin-btn confirm-no" on:click={() => confirmingReopen = false}>✕</button>
										</span>
									{:else}
										<button class="admin-btn reset" on:click={() => confirmingReopen = true}>🔓 {$t("tourneys_btn_reopen")}</button>
									{/if}
								{/if}
								{#if selected.status !== 'OPEN' && selected.status !== 'CLOSED'}
									<button class="admin-btn reset" on:click={resetTournament}>🔄 {$t("tourneys_btn_reset")}</button>
								{/if}
								{#if selected.status !== 'CLOSED'}
									<button class="admin-btn edit" on:click={openEdit}>✏️ {$t("tourneys_btn_edit")}</button>
								{/if}
							</div>
						</div>
					{/if}
				</div>

				{#if showDetails || selected.status === 'OPEN'}
					<div class="info-row">
						<div class="info-card glass"><span class="info-label">{$t("admin_tourneys_wizard_format_lbl")}</span><span class="info-value">{bracketLabel(selected.config?.bracket_type)}</span></div>
						<div class="info-card glass"><span class="info-label">{$t("admin_tourneys_wizard_mode_lbl")}</span><span class="info-value">{selected.config?.use_teams ? `${$t('admin_tourneys_wizard_mode_teams')} (x${selected.config?.team_size || 2})` : 'Solo'}</span></div>
						<div class="info-card glass"><span class="info-label">{$t("admin_tourneys_wizard_points_lbl")}</span><span class="info-value accent" style="font-size:0.85rem">🥇{selected.config?.pts_winner ?? 10} 🥈{selected.config?.pts_second ?? 6} 🥉{selected.config?.pts_third ?? 4} 👤{selected.config?.pts_participation ?? 1}/m ⚡{selected.config?.pts_per_match ?? selected.config?.pts_per_goal ?? 1.0}</span></div>
						<div class="info-card glass"><span class="info-label">{$t("dash_stat_players")}</span><span class="info-value">{participants.length}</span></div>
						{#if selected.config?.lower_score_is_better}
							<div class="info-card glass"><span class="info-label">{$t("admin_tourneys_wizard_format_lbl")}</span><span class="info-value" style="color:#f59e0b">{$t("tourneys_opt_reverse")}</span></div>
						{/if}
					</div>

					<!-- Results Summary (after closing) -->
					{#if selected.status === 'CLOSED' && selected.results}
						<div class="results-section glass">
							<h3>{$t("tourneys_results_title")}</h3>
							<div class="results-table">
								<div class="res-header">
									<span class="res-rank">#</span>
									<span class="res-name">{$t("tourneys_results_player_team")}</span>
									<span class="res-pts">{$t("admin_tourneys_wizard_points_bonus")}</span>
									<span class="res-pts">Score</span>
									<span class="res-pts">{$t("admin_tourneys_wizard_points_part").substring(0,5)}.</span>
									<span class="res-total">Total</span>
								</div>
								{#each selected.results as r}
									<div class="res-row {r.rank === 1 ? 'gold' : r.rank === 2 ? 'silver' : r.rank === 3 ? 'bronze' : ''}">
										<span class="res-rank">{r.rank != null && r.rank <= 3 ? ['🥇','🥈','🥉'][r.rank-1] : r.rank != null ? '#' + r.rank : '—'}</span>
										<span class="res-name">{r.name}</span>
										<span class="res-pts">{r.placement_pts}</span>
										<span class="res-pts">{r.score_pts}</span>
										<span class="res-pts">{r.participation_pts}</span>
										<span class="res-total">{r.total}</span>
									</div>
								{/each}
							</div>
						</div>
					{/if}
				{/if}

			{#if showDetails || selected.status === 'OPEN'}
			<!-- Participants / Pool -->
				{#if !useTeams || selected.status === 'OPEN' || isAdmin}
				<div class="participants-section glass">
					<div class="section-title">
						<h3>👥 {useTeams ? $t('tourneys_tab_registered') : $t('dash_modal_tournaments_title')} <span class="part-count">{participants.length} {$t('changelog_fallback_name').toLowerCase()}{#if useTeams && participants.length > 0}, {poolPlayers.length} {$t('tourneys_unassigned_players', { count: poolPlayers.length, plural: poolPlayers.length > 1 ? 's' : '' })}{/if}</span></h3>
						{#if isAdmin && selected.status === 'OPEN'}
							<div class="part-bulk-actions">
								{#if confirmJoinAll}
									<span class="inline-confirm">
										<span class="inline-confirm-label">{$t("tourneys_confirm_join_all")}</span>
										<button class="admin-btn confirm-yes" on:click={joinAllPlayers}>✓</button>
										<button class="admin-btn confirm-no" on:click={() => confirmJoinAll = false}>✕</button>
									</span>
								{:else}
									<button class="admin-btn start btn-xs" on:click={() => confirmJoinAll = true} disabled={unregisteredUsers.length === 0}>📥 {$t("tourneys_btn_join_all")}</button>
								{/if}
								{#if confirmLeaveAll}
									<span class="inline-confirm">
										<span class="inline-confirm-label">{$t("tourneys_confirm_leave_all")}</span>
										<button class="admin-btn confirm-yes" on:click={leaveAllPlayers}>✓</button>
										<button class="admin-btn confirm-no" on:click={() => confirmLeaveAll = false}>✕</button>
									</span>
								{:else}
									<button class="admin-btn stop btn-xs" on:click={() => confirmLeaveAll = true} disabled={participants.length === 0}>📤 {$t("tourneys_btn_leave_all")}</button>
								{/if}
							</div>
						{/if}
					</div>
					{#if poolPlayers.length === 0}
						<span class="text-dim text-sm">{useTeams && participants.length > 0 ? $t('tourneys_all_placed') : $t('tourneys_no_registered')}</span>
					{:else}
						<div class="part-cards-grid">
							{#each groupedPoolPlayers as [teamName, members]}
								<div class="part-card glass">
									<div class="part-card-header">
										<span class="part-card-name">{teamName || $t('dash_modal_team_fallback')}</span>
										<span class="part-card-count">{members.length}</span>
									</div>
									<div class="part-card-members">
										{#each members as p}
											<div class="part-member-row pool-badge" draggable={isAdmin && selected.status === 'OPEN' && useTeams} on:dragstart={(e) => { e.dataTransfer.setData('userId', p.user_id); e.target.classList.add('dragging'); }} on:dragend={(e) => e.target.classList.remove('dragging')}>
												<span>👤 {p.username}</span>
												{#if isAdmin && selected.status === 'OPEN'}
													<button class="part-member-remove" on:click={() => forceRemovePlayer(p.user_id)} title={$t('tourneys_unregister_player', { name: p.username })}>✕</button>
												{/if}
											</div>
										{/each}
									</div>
								</div>
							{/each}
						</div>
					{/if}
				</div>
				{/if}

				<!-- Team Composition (always visible in team mode) -->
				{#if useTeams}
					<div class="teams-section glass">
						<div class="section-title">
							<h3>👥 {$t('tourneys_tab_teams')}</h3>
							{#if isAdmin && selected.status === 'OPEN'}
								<div style="display:flex;gap:0.5rem;">
									<button class="btn-secondary btn-xs" on:click={randomizeTeams}>🎲 {$t('tourneys_btn_randomize')}</button>
								</div>
							{/if}
						</div>
						{#if selected.status === 'OPEN' && (isAdmin || isParticipant)}
							<div class="team-create-row">
								<input type="text" placeholder="{$t('profile_team_placeholder')}" bind:value={newTeamName} class="team-input" on:keydown={(e) => e.key === 'Enter' && createTeam()} />
								<button class="btn-primary btn-xs" on:click={createTeam}>+ {$t('tourneys_btn_create_team')}</button>
							</div>
						{/if}
						<div class="teams-grid">
							{#each teams as team}
								<div class="team-card glass"
									on:dragover|preventDefault={(e) => { if(isAdmin && selected.status === 'OPEN') e.currentTarget.classList.add('drag-over'); }}
									on:dragleave={(e) => e.currentTarget.classList.remove('drag-over')}
									on:drop|preventDefault={(e) => {
										e.currentTarget.classList.remove('drag-over');
										if(isAdmin && selected.status === 'OPEN') {
											const uid = e.dataTransfer.getData('userId');
											if(uid) addMemberToTeam(team.id, parseInt(uid));
										}
									}}>

									<div class="team-card-header">
										<span class="team-name">{team.name}</span>
										<div style="display:flex;gap:0.3rem;align-items:center;">
											{#if selected.status === 'OPEN' && isParticipant && !myTeam}
												<button class="btn-join" on:click={() => addMemberToTeam(team.id, currentUser.id)} title={$t("tourneys_btn_join_text")}>⭐ {$t("tourneys_btn_join_text")}</button>
											{/if}
											{#if selected.status === 'OPEN' && (isAdmin || team.created_by === currentUser?.id)}
												<button class="team-delete" on:click={() => deleteTeam(team.id)} title={$t("btn_delete")}>✕</button>
											{/if}
										</div>
									</div>
									<div class="team-members">
										{#each team.members || [] as m}
											<div class="team-member">
												<span>👤 {m.username}</span>
												<div style="display:flex;align-items:center;gap:0.4rem">
													{#if selected?.status !== 'OPEN'}
														<span class="member-pts">{getPlayerPts(m.user_id, liveStandings)} pts</span>
													{/if}
												{#if selected.status === 'OPEN' && (isAdmin || m.user_id === currentUser?.id)}
													<button class="member-remove" on:click={() => removeMemberFromTeam(team.id, m.user_id)}>✕</button>
												{/if}
												</div>
											</div>
										{/each}
									</div>
									{#if isAdmin && selected.status === 'OPEN' && unassignedPlayers.length > 0}
										<select class="team-add-select" on:change={(e) => { if (e.target.value) { addMemberToTeam(team.id, parseInt(e.target.value)); e.target.value = ''; } }}>
											<option value="">{$t('tourneys_add_member_placeholder')}</option>
											{#each groupedUnassigned as [groupName, members]}
												<optgroup label={groupName || $t('dash_modal_team_fallback')}>
													{#each members as p}
														<option value={p.user_id}>{p.username}</option>
													{/each}
												</optgroup>
											{/each}
										</select>
								{/if}
								</div>

							{:else}
								<span class="text-dim text-sm">{$t("tourneys_no_teams")}</span>
							{/each}
						</div>
						{#if isAdmin && selected.status === 'OPEN' && unassignedPlayers.length > 0}
							<div class="unassigned-hint">⚠️ {$t('tourneys_unassigned_players', { count: unassignedPlayers.length, plural: unassignedPlayers.length > 1 ? 's' : '' })}</div>
						{/if}
					</div>
				{/if}

				{/if}

			<div class="tournament-split-layout" class:split-active={showLiveStandings && liveStandings.length > 0} class:split-fill={selected?.status === 'RUNNING' && !showDetails}>
			<!-- Bracket -->
				<div class="bracket-section glass" class:bracket-expanded={hasBracket}>
					<div class="section-title">
						<h3>{bracketType === 'round_robin' ? '📊 ' + $t('admin_tourneys_wizard_format_championship') : bracketType === 'ffa' ? '🏁 Free For All' : '📊 ' + $t('tourneys_tab_bracket')}</h3>
						{#if hasBracket && bracketType !== 'round_robin' && bracketType !== 'ffa'}<button class="btn-secondary btn-xs" on:click={resetZoom}>{$t('tourneys_btn_recenter')}</button>{/if}
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
  														<button class="admin-btn confirm-yes" on:click|stopPropagation|preventDefault={rollbackFFA} style="padding: 0.1rem 0.3rem; font-size: 0.7rem; border-radius: 4px; border: 1px solid var(--success); background: none; color: var(--success); cursor: pointer;">✓</button>
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
													<button class="admin-btn" on:click={advanceFFA} style="margin: 0;">▶️ {$t('tourneys_ffa_next_round')}</button>
												</div>
  												<button class="admin-btn stop" on:click={finishFFA}>🏁 {$t('tourneys_ffa_finish')}</button>
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
											{#each lbRounds as lbRound, ri}
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

				<!-- Live Standings -->
				{#if showLiveStandings && liveStandings.length > 0}
					<div class="live-standings glass">
						<div class="section-title"><h3>📊 {$t(selected?.status === 'RUNNING' ? 'tourneys_standings_live' : 'tourneys_standings_final')}</h3>{#if selected?.status === 'RUNNING'}<span class="live-badge">⚡ LIVE</span>{:else}<span class="live-badge" style="color:#3b82f6;background:rgba(59,130,246,0.1);border-color:rgba(59,130,246,0.2)">✅ FINAL</span>{/if}</div>
						<div class="ls-config-summary">
							<span class="ls-cfg" title={$t('tourneys_pts_1st_tooltip')}>🥇 {selected?.config?.pts_winner ?? 10}</span>
							<span class="ls-cfg" title={$t('tourneys_pts_2nd_tooltip')}>🥈 {selected?.config?.pts_second ?? 6}</span>
							<span class="ls-cfg" title={$t('tourneys_pts_3rd_tooltip')}>🥉 {selected?.config?.pts_third ?? 4}</span>
							<span class="ls-cfg" title={$t('tourneys_pts_participation_tooltip')}>👤 {selected?.config?.pts_participation ?? 1}{$t('tourneys_per_match')}</span>
							<span class="ls-cfg" title={$t('tourneys_pts_bonus_tooltip')}>⚡ {selected?.config?.pts_per_match ?? selected?.config?.pts_per_goal ?? 1.0} {$t('admin_tourneys_wizard_points_bonus')}</span>
						</div>
						<div class="ls-list">
							{#each displayStandings as entry, i}
								<div class="ls-row {entry.rank && entry.rank <= 3 ? 'ls-top' : ''}">
									<span class="ls-rank {entry.rank === 1 ? 'gold' : entry.rank === 2 ? 'silver' : entry.rank === 3 ? 'bronze' : ''}">{entry.rank || '—'}</span>
									<div class="ls-info">
										<span class="ls-name">{entry.name}</span>
										<div class="ls-breakdown">
											{#if entry.placement_pts > 0}<span class="ls-bp ls-bp-place" title="Placement : top {entry.rank}">🏅{entry.placement_pts}</span>{/if}
											<span class="ls-bp ls-bp-parti" title={$t('tourneys_participation_tooltip_detail', { count: entry.matches_played, plural: entry.matches_played > 1 ? 's' : '', pts: selected?.config?.pts_participation ?? 1 })}>👤{entry.participation_pts}</span>
											{#if entry.score_pts > 0}<span class="ls-bp ls-bp-score" title={$t('tourneys_pts_bonus_detail_tooltip', { score: entry.cumulated_score, floor: entry.pts_per_match, ceiling: Math.round(entry.pts_per_match * 2 * 10) / 10 })}>⚡{entry.score_pts}</span>{/if}
										</div>
									</div>
									<span class="ls-pts">{entry.pts} pts</span>
								</div>
							{/each}
						</div>
					</div>
				{/if}


				</div>

				<!-- Admin: unregistered users -->
				{#if currentUser?.is_admin && selected.status === 'OPEN' && unregisteredUsers.length > 0}
					<div class="unreg-section glass">
						<div class="section-title">
							<h3>➕ {$t('tourneys_available_players')}</h3>
							<span class="unreg-hint">{$t('tourneys_click_to_register')}</span>
						</div>
						<div class="unreg-badges">
							{#each unregisteredUsers as u}
								<button class="unreg-badge" on:click={() => forceAddPlayer(u.id)} title={$t('tourneys_detail_unregistered_add_title', { name: u.username })}>
									<span>👤</span>
									<span class="unreg-name">{u.username}</span>
									{#if u.team_name}<span class="unreg-team">• {u.team_name}</span>{/if}
									<span class="unreg-plus">+</span>
								</button>
							{/each}
						</div>
					</div>
				{/if}
			</div>

		{:else}
			<div class="detail-empty">
				<span class="empty-lg-icon">🏟️</span>
				<h2>{$t('tourneys_select_tournament')}</h2>
				<p class="text-dim">{$t('tourneys_choose_from_list')}</p>
			</div>
		{/if}
	</main>
</div>

<!-- Edit Modal -->
<EditTournamentModal
	tournament={selected}
	show={editingTournament}
	on:close={() => editingTournament = false}
	on:save={async (e) => {
		editConfig = e.detail.editConfig;
		await saveEdit();
	}}
/>

<!-- Create Modal -->
{#if showCreateModal}
	<div class="edit-overlay" use:portal on:click={() => showCreateModal = false}>
		<div class="edit-modal glass" on:click|stopPropagation>
			<header class="edit-modal-header">
				<h3>🏆 Nouveau Tournoi</h3>
				<button class="close-btn" on:click={() => showCreateModal = false}>✕</button>
			</header>
			<div class="edit-modal-body">
				<CreateTournamentWizard 
					{games} 
					onSuccess={async (newT) => {
						toast('Tournoi créé avec succès !', 'success');
						showCreateModal = false;
						tournaments = await api.get('/tournaments');
						await selectTournament(newT.id);
					}}
					onGameCreated={async (newGameId) => {
						try {
							games = await api.get('/tournaments/games');
						} catch {
							games = [];
						}
					}}
					onCancel={() => showCreateModal = false}
				/>
			</div>
		</div>
	</div>
{/if}

<!-- Toasts -->
<div class="toast-container" use:portal>
	{#each toasts as t (t.id)}
		<div class="toast {t.type} {t.leaving ? 'toast-leave' : 'toast-enter'}">
			<span>{#if t.type === 'success'}✅{:else if t.type === 'error'}❌{:else}ℹ️{/if}</span>
			<span class="toast-msg">{t.message}</span>
		</div>
	{/each}
</div>

<style>
	.sidebar-actions { padding: 0.5rem 0.5rem 0 0.5rem; display: flex; flex-direction: column; }
	.add-tournament-btn-full {
		display: flex;
		align-items: center;
		justify-content: center;
		gap: 0.4rem;
		padding: 0.6rem;
		font-size: 0.8rem;
		border-radius: 10px;
		cursor: pointer;
		font-weight: 700;
		width: 100%;
		border: 1px solid var(--glass-border);
		background: var(--accent-soft);
		color: var(--accent);
		transition: all 0.2s;
	}
	.add-tournament-btn-full:hover {
		background: var(--accent);
		color: white;
		box-shadow: 0 0 10px var(--accent-glow);
	}
	.edit-field input[type="text"],
	.edit-field input[type="number"],
	.edit-field select {
		width: 100%;
		padding: 0.5rem 0.8rem;
		border-radius: 8px;
		border: 1px solid var(--glass-border);
		background: var(--surface-sunken);
		color: var(--text-main);
		font-size: 0.8rem;
		outline: none;
		transition: border-color 0.15s;
	}
	.edit-field input:focus,
	.edit-field select:focus {
		border-color: var(--accent);
	}

	/* === LAYOUT === */
	.tournaments-layout {
		display: flex;
		height: 100%;
		--highlight-border: #d8b4fe;
		--highlight-bg: rgba(168, 85, 247, 0.28);
		--highlight-text: #f5f3ff;
		--highlight-glow: rgba(168, 85, 247, 0.35);
	}
	:global([data-theme="light"]) .tournaments-layout {
		--highlight-border: #9333ea;
		--highlight-bg: rgba(168, 85, 247, 0.25);
		--highlight-text: #581c87;
		--highlight-glow: rgba(147, 51, 234, 0.2);
	}

	/* === SIDEBAR === */
	.t-sidebar { width: 280px; min-width: 260px; display: flex; flex-direction: column; padding: 0; overflow: hidden; flex-shrink: 0; margin-right: 1.5rem; position: relative; z-index: 2; }
	.sidebar-header { display: flex; justify-content: space-between; align-items: center; padding: 1rem 1.2rem; border-bottom: 1px solid var(--glass-border); }
	.sidebar-header h2 { font-size: 0.95rem; margin: 0; }
	.t-count { font-size: 0.65rem; background: var(--accent-soft); color: var(--accent); padding: 0.1rem 0.4rem; border-radius: 10px; font-weight: 800; border: 1px solid rgba(59,130,246,0.15); }
	.t-list { flex-grow: 1; overflow-y: auto; display: flex; flex-direction: column; gap: 0.4rem; padding: 0.5rem; }
	.t-item { position: relative; display: flex; align-items: flex-end; min-height: 72px; padding: 0; background-size: cover; background-position: center; background-color: rgba(0,0,0,0.4); border: 1px solid #1e293b; border-radius: 10px; cursor: pointer; transition: all 0.2s; text-align: left; color: white; width: 100%; overflow: hidden; }
	.t-item::before { content: ''; position: absolute; inset: 0; z-index: 1; pointer-events: none; border-radius: inherit; transition: opacity 0.2s; opacity: 0; }
	.t-item.open::before { background: radial-gradient(ellipse at center, transparent 20%, rgba(34,197,94,0.28) 100%); opacity: 1; }
	.t-item.running::before { background: radial-gradient(ellipse at center, transparent 20%, rgba(59,130,246,0.3) 100%); opacity: 1; }
	.t-item.done::before { background: radial-gradient(ellipse at center, transparent 10%, rgba(100,116,139,0.35) 100%); opacity: 1; }
	.t-item.closed::before { background: radial-gradient(ellipse at center, transparent 10%, rgba(100,116,139,0.4) 100%); opacity: 1; }
	.t-item:hover { border-color: rgba(71,85,105,0.7); transform: scale(1.02); box-shadow: 0 4px 12px rgba(0,0,0,0.4); }
	.t-item.active { border-color: var(--accent); box-shadow: 0 0 12px rgba(59,130,246,0.3); }
	.t-item-checkered { position: absolute; top: 0; right: 0; width: 35%; height: 100%; z-index: 1; pointer-events: none;
		background: repeating-conic-gradient(rgba(255,255,255,0.75) 0% 25%, rgba(20,20,20,0.75) 0% 50%) 0 0 / 14px 14px;
		mask-image: linear-gradient(to left, rgba(0,0,0,0.6) 0%, rgba(0,0,0,0.25) 50%, transparent 100%), linear-gradient(to top, transparent 0%, rgba(0,0,0,0.5) 25%, rgba(0,0,0,0.5) 75%, transparent 100%);
		-webkit-mask-image: linear-gradient(to left, rgba(0,0,0,0.6) 0%, rgba(0,0,0,0.25) 50%, transparent 100%), linear-gradient(to top, transparent 0%, rgba(0,0,0,0.5) 25%, rgba(0,0,0,0.5) 75%, transparent 100%);
		mask-composite: intersect; -webkit-mask-composite: source-in;
	}
	.t-item-overlay { position: absolute; inset: 0; z-index: 2; display: flex; align-items: flex-end; justify-content: space-between; padding: 0.6rem 0.75rem; background: linear-gradient(to top, rgba(10,15,30,0.92) 0%, rgba(10,15,30,0.45) 55%, transparent 100%), radial-gradient(ellipse at center, transparent 50%, rgba(10,15,30,0.3) 100%); }
	.t-item-info { flex-grow: 1; min-width: 0; display: flex; flex-direction: column; gap: 0.1rem; }
	.t-item-name { font-size: 0.82rem; font-weight: 700; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; text-shadow: 0 1px 4px rgba(0,0,0,0.6); }
	.t-item-meta { font-size: 0.65rem; color: rgba(255,255,255,0.55); text-shadow: 0 1px 2px rgba(0,0,0,0.5); }
	.t-item.active .t-item-name { color: #60a5fa; }
	.t-status-badge { flex-shrink: 0; padding: 0.15rem 0.45rem; border-radius: 6px; font-size: 0.55rem; font-weight: 700; letter-spacing: 0.02em; white-space: nowrap; line-height: 1.3; text-shadow: 0 1px 2px rgba(0,0,0,0.4); }
	.t-status-badge.open { background: rgba(34,197,94,0.25); color: #4ade80; border: 1px solid rgba(34,197,94,0.4); }
	.t-status-badge.running { background: rgba(59,130,246,0.25); color: #60a5fa; border: 1px solid rgba(59,130,246,0.4); }
	.t-status-badge.done { background: rgba(100,116,139,0.25); color: #94a3b8; border: 1px solid rgba(100,116,139,0.35); }
	.t-status-badge.closed { background: rgba(16,185,129,0.2); color: #34d399; border: 1px solid rgba(16,185,129,0.35); }
	.t-empty-sidebar { padding: 2rem 1rem; text-align: center; }

	/* === DETAIL === */
	.t-detail { flex-grow: 1; display: flex; flex-direction: column; overflow-y: auto; border-radius: var(--radius-lg); margin-left: -3rem; padding-left: 3rem; }
	.detail-hero { height: 180px; background-size: cover; background-position: center; background-color: var(--bg-secondary); border-radius: var(--radius-lg) var(--radius-lg) 0 0; position: relative; flex-shrink: 0; }
	.hero-overlay { position: absolute; inset: 0; display: flex; align-items: flex-end; justify-content: space-between; background: linear-gradient(to top, rgba(15,23,42,0.95) 0%, rgba(15,23,42,0.3) 60%, transparent); padding: 1.2rem 1.5rem; border-radius: inherit; }
	.hero-content { display: flex; flex-direction: column; gap: 0.2rem; }
	.hero-content h1 { font-size: 1.5rem; margin: 0; color: white; text-shadow: 0 2px 8px rgba(0,0,0,0.5); }

	/* Checkered flag for CLOSED tournaments */
	.hero-checkered { position: absolute; top: 0; right: 0; width: 75%; height: 100%; z-index: 1; pointer-events: none;
		background: repeating-conic-gradient(rgba(255,255,255,0.85) 0% 25%, rgba(20,20,20,0.85) 0% 50%) 0 0 / 22px 22px;
		mask-image: linear-gradient(to left, rgba(0,0,0,0.7) 0%, rgba(0,0,0,0.35) 50%, transparent 100%), linear-gradient(to top, transparent 0%, rgba(0,0,0,0.5) 30%, rgba(0,0,0,0.5) 70%, transparent 100%);
		-webkit-mask-image: linear-gradient(to left, rgba(0,0,0,0.7) 0%, rgba(0,0,0,0.35) 50%, transparent 100%), linear-gradient(to top, transparent 0%, rgba(0,0,0,0.5) 30%, rgba(0,0,0,0.5) 70%, transparent 100%);
		mask-composite: intersect; -webkit-mask-composite: source-in;
		border-radius: 0 var(--radius-lg) 0 0;
		animation: checkered-reveal 0.6s ease-out;
	}
	@keyframes checkered-reveal { from { opacity: 0; transform: translateX(20px); } to { opacity: 1; transform: translateX(0); } }
	.hero-game { color: #60a5fa; font-weight: 600; font-size: 0.85rem; text-shadow: 0 1px 4px rgba(0,0,0,0.5); }
	.hero-rules {
		position: absolute; right: 1.5rem; bottom: 1rem; max-width: 280px; max-height: 140px;
		overflow-y: auto; padding: 0.6rem 0.8rem; border-radius: 10px;
		background: rgba(15,23,42,0.7); backdrop-filter: blur(6px);
		border: 1px solid rgba(255,255,255,0.08);
		z-index: 3;
	}
	.hero-rules-label { font-size: 0.55rem; font-weight: 700; text-transform: uppercase; letter-spacing: 0.05em; color: #60a5fa; margin-bottom: 0.25rem; display: block; }
	.hero-rules-text { font-size: 0.7rem; color: rgba(255,255,255,0.75); margin: 0; line-height: 1.45; white-space: pre-line; word-break: break-word; }
	.hero-rules::-webkit-scrollbar { width: 3px; }
	.hero-rules::-webkit-scrollbar-thumb { background: rgba(96,165,250,0.3); border-radius: 3px; }
	.hero-join { align-self: flex-end; }
	.hero-joined { align-self: flex-end; padding: 0.5rem 1.2rem; background: rgba(16,185,129,0.15); border: 1px solid rgba(16,185,129,0.3); color: #10b981; border-radius: 10px; font-weight: 700; font-size: 0.85rem; text-shadow: 0 1px 4px rgba(0,0,0,0.3); }
	.status-pill { display: inline-flex; align-items: center; gap: 0.3rem; align-self: flex-start; padding: 0.2rem 0.6rem; border-radius: 20px; font-size: 0.65rem; font-weight: 700; margin-bottom: 0.2rem; text-shadow: 0 1px 3px rgba(0,0,0,0.3); }
	.status-pill.open { background: rgba(34,197,94,0.2); color: #4ade80; border: 1px solid rgba(34,197,94,0.3); }
	.status-pill.running { background: rgba(59,130,246,0.2); color: #60a5fa; border: 1px solid rgba(59,130,246,0.3); }
	.status-pill.done { background: rgba(100,116,139,0.2); color: #94a3b8; border: 1px solid rgba(100,116,139,0.3); }
	.status-pill.closed { background: rgba(16,185,129,0.2); color: #34d399; border: 1px solid rgba(16,185,129,0.3); }

	.detail-body { padding: 1.2rem 1.5rem; display: flex; flex-direction: column; gap: 1.2rem; flex-grow: 1; min-height: 0; }
	.info-row { display: grid; grid-template-columns: repeat(auto-fit, minmax(120px, 1fr)); gap: 0.8rem; }
	.info-card { padding: 0.8rem; display: flex; flex-direction: column; gap: 0.2rem; border-radius: 10px; }
	.info-label { font-size: 0.6rem; font-weight: 700; text-transform: uppercase; letter-spacing: 0.06em; color: var(--text-muted); }
	.info-value { font-size: 0.9rem; font-weight: 700; }
	.info-value.accent { color: var(--accent); }

	/* === SECTION TITLES === */
	.section-title { display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.75rem; }
	.section-title h3 { font-size: 0.8rem; font-weight: 700; text-transform: uppercase; letter-spacing: 0.04em; color: var(--text-dim); margin: 0; }
	.btn-xs { padding: 0.3rem 0.6rem; font-size: 0.7rem; }

	/* === BRACKET === */
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
	.bracket-match { width: 240px; background: var(--hover-tint); border: 1px solid var(--glass-border); border-radius: 8px; overflow: hidden; box-shadow: 0 2px 4px rgba(0,0,0,0.15); }
	.player-row { display: flex; align-items: center; justify-content: space-between; padding: 0.55rem 0.85rem; font-size: 0.85rem; background: var(--surface-sunken); color: var(--text-muted); }
	.player-row.filled { color: var(--text-main); background: var(--accent-soft); }
	.my-player-highlight {
		border-left: 4px solid var(--highlight-border) !important;
		background: var(--highlight-bg) !important;
		box-shadow: inset 0 0 6px var(--highlight-glow) !important;
	}
	.my-player-highlight.rr-p,
	.my-player-highlight .player-name,
	.my-player-highlight .ffa-name {
		color: var(--highlight-text) !important;
		text-shadow: 0 0 6px var(--highlight-glow);
		font-weight: 800 !important;
	}
	.player-row.winner { background: rgba(34,197,94,0.15); color: #4ade80; }
	.player-row.winner .score-input, .player-row.winner .score-display { color: #4ade80; }
	.player-row.loser { opacity: 0.45; }
	.bracket-match.match-done { border-color: rgba(34,197,94,0.3); }
	.bracket-match.player-highlight { border-color: rgba(56,189,248,0.7); box-shadow: 0 0 12px rgba(56,189,248,0.4), inset 0 0 8px rgba(56,189,248,0.05); transform: scale(1.03); z-index: 10; }
	.bracket-match { transition: border-color 0.2s, box-shadow 0.2s, transform 0.2s; }
	.player-row { cursor: default; }
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

	/* AXE-29: Directional pan arrows */
	.pan-arrow { position: absolute; display: flex; align-items: center; justify-content: center; color: var(--accent); font-size: 1.4rem; font-weight: 900; opacity: 0.6; pointer-events: auto; cursor: pointer; z-index: 5; animation: panArrowPulse 1.5s ease-in-out infinite; transition: opacity 0.15s, transform 0.15s; }
	.pan-arrow:hover { opacity: 1; animation: none; }
	.pan-arrow-left { left: 6px; top: 50%; transform: translateY(-50%); width: 28px; height: 50px; background: linear-gradient(90deg, rgba(59,130,246,0.15), transparent); border-radius: 6px; }
	.pan-arrow-right { right: 6px; top: 50%; transform: translateY(-50%); width: 28px; height: 50px; background: linear-gradient(-90deg, rgba(59,130,246,0.15), transparent); border-radius: 6px; }
	.pan-arrow-up { top: 6px; left: 50%; transform: translateX(-50%) rotate(90deg); width: 28px; height: 50px; background: linear-gradient(90deg, rgba(59,130,246,0.15), transparent); border-radius: 6px; }
	.pan-arrow-down { bottom: 6px; left: 50%; transform: translateX(-50%) rotate(-90deg); width: 28px; height: 50px; background: linear-gradient(90deg, rgba(59,130,246,0.15), transparent); border-radius: 6px; }
	@keyframes panArrowPulse { 0%, 100% { opacity: 0.4; } 50% { opacity: 0.85; } }
	/* Score countdown progress bar */
	.score-pending { position: relative; width: 100%; height: 16px; background: rgba(0,0,0,0.2); border-radius: 0 0 8px 8px; overflow: hidden; display: flex; align-items: center; }
	.score-pending-bar { position: absolute; left: 0; top: 0; height: 100%; background: linear-gradient(90deg, #3b82f6, #60a5fa); border-radius: 0 0 0 8px; transition: width 0.1s linear; }
	.score-pending-cancel { position: relative; z-index: 2; width: 100%; background: none; border: none; color: rgba(255,255,255,0.8); font-size: 0.6rem; font-weight: 600; cursor: pointer; text-align: center; padding: 0; line-height: 16px; transition: color 0.2s; }
	.score-pending-cancel:hover { color: #f87171; }
	.rr-pending { border-radius: 6px; margin-top: 0.25rem; }
	.bracket-empty { padding: 3rem; text-align: center; color: var(--text-dim); display: flex; flex-direction: column; align-items: center; gap: 0.5rem; }
	.bracket-empty-icon { font-size: 2rem; opacity: 0.4; }
	.bracket-empty p { margin: 0; font-size: 0.85rem; }

	/* === PARTICIPANTS === */
	.participants-section { padding: 1rem; border-radius: 14px; }
	.part-count { font-size: 0.6rem; background: var(--accent-soft); color: var(--accent); padding: 0.1rem 0.4rem; border-radius: 10px; font-weight: 800; border: 1px solid rgba(59,130,246,0.15); margin-left: 0.3rem; }
	.part-bulk-actions { display: flex; gap: 0.4rem; align-items: center; }
	.part-cards-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(200px, 1fr)); gap: 0.75rem; }
	.part-card { padding: 0.75rem; border-radius: 10px; }
	.part-card-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.5rem; padding-bottom: 0.4rem; border-bottom: 1px solid var(--glass-border); }
	.part-card-name { font-weight: 800; font-size: 0.85rem; color: var(--accent); }
	.part-card-count { font-size: 0.6rem; background: rgba(255,255,255,0.06); padding: 0.1rem 0.4rem; border-radius: 8px; color: var(--text-muted); font-weight: 700; }
	.part-card-members { display: flex; flex-direction: column; gap: 0.3rem; }
	.part-member-row { display: flex; justify-content: space-between; align-items: center; font-size: 0.75rem; padding: 0.25rem 0.4rem; background: rgba(59,130,246,0.08); border-radius: 6px; font-weight: 600; color: var(--text-main); }
	.part-member-remove { background: none; border: none; color: var(--text-muted); cursor: pointer; font-size: 0.65rem; opacity: 0.4; transition: all 0.15s; }
	.part-member-remove:hover { opacity: 1; color: var(--danger, #ef4444); }

	/* === UNREG BADGES === */
	.unreg-section { padding: 1rem; border-radius: 14px; }
	.unreg-hint { font-size: 0.6rem; color: var(--text-muted); font-style: italic; }
	.unreg-badges { display: flex; flex-wrap: wrap; gap: 0.35rem; }
	.unreg-badge { display: flex; align-items: center; gap: 0.3rem; padding: 0.3rem 0.6rem; border-radius: 20px; font-size: 0.72rem; font-weight: 600; background: var(--surface-raised); border: 1px solid var(--glass-border); color: var(--text-dim); cursor: pointer; transition: all 0.2s; }
	.unreg-badge:hover { background: var(--map-user-option-hover); border-color: var(--accent); color: var(--accent); }
	.unreg-name { color: inherit; }
	.unreg-team { color: var(--text-muted); font-size: 0.6rem; }
	.unreg-badge:hover .unreg-team { color: var(--text-dim); }
	.unreg-plus { color: var(--accent); font-weight: 800; font-size: 0.8rem; opacity: 0; transition: opacity 0.15s; }
	.unreg-badge:hover .unreg-plus { opacity: 1; }

	/* === ADMIN BAR === */
	.admin-bar { display: flex; justify-content: space-between; align-items: center; padding: 0.7rem 1rem; border-radius: 10px; border: 1px dashed rgba(59,130,246,0.2); background: rgba(59,130,246,0.04); }
	.admin-bar-label { font-size: 0.75rem; font-weight: 700; color: var(--text-dim); }
	.admin-bar-actions { display: flex; gap: 0.4rem; }
	.admin-btn { padding: 0.4rem 0.8rem; font-size: 0.72rem; font-weight: 700; border-radius: 8px; border: 1px solid var(--glass-border); cursor: pointer; transition: all 0.2s; background: var(--surface-raised); color: var(--text-dim); }
	.admin-btn:hover { transform: translateY(-1px); }
	.admin-btn:disabled { opacity: 0.4; cursor: not-allowed; transform: none; }
	.admin-btn.start { border-color: rgba(34,197,94,0.3); color: var(--success); }
	.admin-btn.start:hover:not(:disabled) { background: rgba(34,197,94,0.15); }
	.admin-btn.stop { border-color: rgba(239,68,68,0.3); color: var(--danger); }
	.admin-btn.stop:hover { background: rgba(239,68,68,0.15); }
	.admin-btn.reset { border-color: rgba(251,191,36,0.3); color: #fbbf24; }
	.admin-btn.reset:hover { background: rgba(251,191,36,0.1); }
	.admin-btn.close { border-color: rgba(16,185,129,0.3); color: #10b981; }
	.admin-btn.close:hover { background: rgba(16,185,129,0.15); }
	.inline-confirm { display: inline-flex; align-items: center; gap: 0.4rem; animation: fadeIn 0.15s ease-out; }
	.inline-confirm-label { font-size: 0.65rem; font-weight: 700; color: var(--text-main); white-space: nowrap; }
	.admin-btn.confirm-yes { border-color: rgba(34,197,94,0.4); color: var(--success); font-weight: 800; }
	.admin-btn.confirm-yes:hover { background: rgba(34,197,94,0.2); }
	.admin-btn.confirm-no { border-color: rgba(239,68,68,0.3); color: var(--danger); padding: 0.2rem 0.5rem; min-width: unset; }
	.admin-btn.confirm-no:hover { background: rgba(239,68,68,0.15); }
	@keyframes fadeIn { from { opacity: 0; transform: translateX(-5px); } to { opacity: 1; transform: translateX(0); } }
	.admin-btn.edit { border-color: rgba(59,130,246,0.3); color: var(--accent); }

	/* Results Section */
	.results-section { padding: 1rem; }
	.results-section h3 { font-size: 0.9rem; margin-bottom: 0.75rem; }
	.results-table { display: flex; flex-direction: column; gap: 2px; }
	.res-header, .res-row { display: grid; grid-template-columns: 40px 1fr repeat(3, 55px) 60px; align-items: center; padding: 0.35rem 0.5rem; font-size: 0.65rem; border-radius: 4px; }
	.res-header { font-weight: 800; color: var(--text-muted); text-transform: uppercase; font-size: 0.5rem; letter-spacing: 0.5px; }
	.res-row { background: var(--surface-sunken); }
	.res-row.gold { background: rgba(255,215,0,0.08); border-left: 3px solid #ffd700; }
	.res-row.silver { background: rgba(192,192,192,0.06); border-left: 3px solid #c0c0c0; }
	.res-row.bronze { background: rgba(205,127,50,0.06); border-left: 3px solid #cd7f32; }
	.res-rank { font-weight: 800; text-align: center; }
	.res-name { font-weight: 700; color: var(--text-main); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
	.res-pts { text-align: center; color: var(--text-muted); }
	.res-total { text-align: center; font-weight: 800; color: var(--accent); font-size: 0.75rem; }
	.admin-btn.edit:hover { background: rgba(59,130,246,0.15); }

	/* === EDIT MODAL === */
	.edit-overlay {
		position: fixed;
		inset: 0;
		background: rgba(0, 0, 0, 0.45);
		backdrop-filter: blur(8px);
		-webkit-backdrop-filter: blur(8px);
		z-index: 9999;
		display: flex;
		align-items: center;
		justify-content: center;
		padding: 1.5rem;
		animation: modalFadeIn 0.2s ease-out forwards;
	}
	@keyframes modalFadeIn {
		from { opacity: 0; }
		to { opacity: 1; }
	}
	.edit-modal {
		width: 580px;
		max-width: 100%;
		max-height: 85vh;
		border-radius: 16px;
		border: 1px solid var(--glass-border);
		box-shadow: 0 30px 70px rgba(0, 0, 0, 0.45);
		background: var(--bg-primary);
		display: flex;
		flex-direction: column;
		overflow: hidden;
		animation: modalSlideUp 0.3s cubic-bezier(0.16, 1, 0.3, 1) forwards;
	}
	@keyframes modalSlideUp {
		from { transform: translateY(20px) scale(0.97); }
		to { transform: translateY(0) scale(1); }
	}
	.edit-modal-header {
		display: flex;
		justify-content: space-between;
		align-items: center;
		padding: 1.25rem 1.5rem;
		border-bottom: 1px solid var(--glass-border);
		background: var(--surface-sunken);
		flex-shrink: 0;
	}
	.header-title-wrapper {
		display: flex;
		align-items: center;
		gap: 0.75rem;
	}
	.header-emoji {
		font-size: 1.3rem;
	}
	.edit-modal-header h3 {
		font-size: 1rem;
		font-weight: 800;
		margin: 0;
		color: var(--text-main);
	}
	.header-subtitle {
		font-size: 0.72rem;
		color: var(--text-dim);
		font-weight: 500;
	}
	.close-btn {
		background: var(--hover-tint);
		border: 1px solid var(--glass-border);
		color: var(--text-dim);
		cursor: pointer;
		font-size: 0.85rem;
		width: 30px;
		height: 30px;
		display: flex;
		align-items: center;
		justify-content: center;
		border-radius: 50%;
		transition: all 0.2s;
	}
	.close-btn:hover {
		background: var(--accent-soft);
		color: var(--accent);
		border-color: var(--accent);
		transform: rotate(90deg);
	}
	.edit-modal-body {
		padding: 1.5rem 1.5rem 2.5rem 1.5rem;
		display: flex;
		flex-direction: column;
		gap: 1.25rem;
		overflow-y: auto;
		flex: 1;
		min-height: 0;
	}
	.edit-section-card {
		background: var(--surface-raised);
		border: 1px solid var(--glass-border);
		border-radius: 12px;
		padding: 1.25rem;
		display: flex;
		flex-direction: column;
		gap: 1rem;
		box-shadow: 0 4px 15px rgba(0, 0, 0, 0.05);
	}
	.section-title {
		font-size: 0.75rem;
		font-weight: 800;
		color: var(--text-main);
		margin: 0;
		text-transform: uppercase;
		letter-spacing: 0.05em;
		border-bottom: 1px solid var(--glass-border);
		padding-bottom: 0.4rem;
	}
	.edit-grid-2col {
		display: grid;
		grid-template-columns: repeat(2, 1fr);
		gap: 1rem;
	}
	.edit-field {
		display: flex;
		flex-direction: column;
		gap: 0.35rem;
	}
	.edit-field.full-width {
		grid-column: 1 / -1;
	}
	.edit-field label {
		font-size: 0.65rem;
		font-weight: 700;
		color: var(--text-dim);
		text-transform: uppercase;
		letter-spacing: 0.05em;
	}
	.edit-field input[type="text"],
	.edit-field input[type="number"] {
		width: 100%;
		padding: 0.5rem 0.75rem;
		font-size: 0.8rem;
		background: var(--surface-sunken);
		border: 1px solid var(--glass-border);
		border-radius: 8px;
		color: var(--text-main);
		transition: all 0.2s;
	}
	.edit-field input:focus {
		outline: none;
		border-color: var(--accent);
		box-shadow: 0 0 0 3px var(--accent-glow);
	}
	.edit-sub-row {
		display: flex;
		gap: 1rem;
		margin-top: -0.25rem;
	}
	.edit-field.narrow {
		max-width: 150px;
	}
	.edit-toggle-row {
		display: flex;
		gap: 0.3rem;
		background: var(--surface-sunken);
		padding: 0.2rem;
		border-radius: 8px;
		border: 1px solid var(--glass-border);
		width: 100%;
	}
	.edit-toggle {
		flex: 1;
		padding: 0.4rem 0.6rem;
		font-size: 0.7rem;
		font-weight: 700;
		border: none;
		border-radius: 6px;
		background: transparent;
		color: var(--text-dim);
		cursor: pointer;
		transition: all 0.15s;
		white-space: nowrap;
	}
	.edit-toggle:hover {
		color: var(--text-main);
		background: var(--hover-tint);
	}
	.edit-toggle.active {
		background: var(--bg-primary);
		color: var(--accent);
		box-shadow: 0 2px 6px rgba(0, 0, 0, 0.1), 0 0 0 1px var(--glass-border);
	}
	.edit-options-grid {
		display: grid;
		grid-template-columns: repeat(2, 1fr);
		gap: 0.75rem;
		width: 100%;
	}
	.edit-options-grid.simple-grid {
		grid-column: 2;
		align-content: end;
	}
	.option-card {
		display: flex;
		align-items: flex-start;
		gap: 0.6rem;
		padding: 0.6rem 0.8rem;
		background: var(--surface-sunken);
		border: 1px solid var(--glass-border);
		border-radius: 8px;
		cursor: pointer;
		text-align: left;
		transition: all 0.2s;
	}
	.option-card:hover {
		border-color: var(--accent);
		background: var(--hover-tint);
	}
	.option-card.active {
		border-color: var(--accent);
		background: var(--accent-soft);
		box-shadow: 0 0 8px var(--accent-glow);
	}
	.option-icon {
		font-size: 1rem;
		margin-top: 0.05rem;
	}
	.option-content {
		display: flex;
		flex-direction: column;
		gap: 0.1rem;
	}
	.option-label {
		font-size: 0.72rem;
		font-weight: 700;
		color: var(--text-main);
	}
	.option-desc {
		font-size: 0.6rem;
		color: var(--text-muted);
		line-height: 1.2;
	}
	.edit-format-specific-panel {
		background: var(--surface-sunken);
		border: 1px solid var(--glass-border);
		border-radius: 8px;
		padding: 0.8rem;
		margin-top: 0.25rem;
		display: flex;
		flex-direction: column;
		gap: 0.6rem;
		width: 100%;
	}
	.specific-title {
		font-size: 0.7rem;
		font-weight: 800;
		color: var(--text-dim);
		margin: 0;
		text-transform: uppercase;
		letter-spacing: 0.05em;
	}
	.edit-pts-grid-modern {
		display: grid;
		grid-template-columns: repeat(4, 1fr);
		gap: 0.6rem;
		width: 100%;
	}
	.edit-pts-card {
		background: var(--surface-sunken);
		border: 1px solid var(--glass-border);
		border-radius: 8px;
		padding: 0.5rem;
		display: flex;
		flex-direction: column;
		align-items: center;
		gap: 0.25rem;
		transition: all 0.2s;
	}
	.edit-pts-card:hover {
		border-color: var(--accent);
	}
	.edit-pts-card.full-row {
		grid-column: 1 / -1;
		flex-direction: row;
		justify-content: space-between;
		padding: 0.5rem 0.8rem;
	}
	.edit-pts-card.full-row label {
		margin-bottom: 0;
	}
	.edit-pts-card.full-row input {
		width: 80px;
		text-align: right;
	}
	.edit-pts-card label {
		font-size: 0.6rem;
		font-weight: 700;
		color: var(--text-dim);
	}
	.edit-pts-card input {
		width: 100%;
		padding: 0.35rem;
		text-align: center;
		font-size: 0.8rem;
		font-weight: 800;
		background: var(--bg-primary);
		border: 1px solid var(--glass-border);
		border-radius: 6px;
		color: var(--accent);
		transition: all 0.2s;
	}
	.edit-pts-card input:focus {
		outline: none;
		border-color: var(--accent);
		box-shadow: 0 0 0 2px var(--accent-glow);
	}
	.edit-modal-footer {
		display: flex;
		justify-content: flex-end;
		gap: 0.6rem;
		padding: 1rem 1.5rem;
		border-top: 1px solid var(--glass-border);
		background: var(--bg-secondary);
		flex-shrink: 0;
	}
	.anim-fade-in {
		animation: quickFadeIn 0.2s ease-out forwards;
	}
	@keyframes quickFadeIn {
		from { opacity: 0; transform: translateY(4px); }
		to { opacity: 1; transform: translateY(0); }
	}
	/* === EMPTY STATE === */
	.detail-empty { flex-grow: 1; display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 0.5rem; text-align: center; }
	.empty-lg-icon { font-size: 3.5rem; opacity: 0.4; }
	.detail-empty h2 { margin: 0; }

	/* === TOASTS === */
	.toast-container { position: fixed; bottom: 1.5rem; right: 1.5rem; z-index: 10000; display: flex; flex-direction: column-reverse; gap: 0.75rem; pointer-events: none; }
	.toast { display: flex; align-items: center; gap: 0.75rem; padding: 0.8rem 1.4rem; border-radius: 12px; backdrop-filter: blur(16px); border: 1px solid var(--glass-border); box-shadow: 0 10px 30px rgba(0,0,0,0.4); font-size: 0.85rem; font-weight: 600; pointer-events: auto; min-width: 240px; }
	.toast.success { background: rgba(16, 185, 129, 0.15); border-color: rgba(16, 185, 129, 0.3); color: #10b981; }
	.toast.error { background: rgba(239, 68, 68, 0.15); border-color: rgba(239, 68, 68, 0.3); color: var(--danger); }
	.toast.info { background: rgba(59, 130, 246, 0.15); border-color: rgba(59, 130, 246, 0.3); color: var(--accent); }
	.toast-enter { animation: toastIn 0.4s cubic-bezier(0.16, 1, 0.3, 1) forwards; }
	.toast-leave { animation: toastOut 0.4s ease-in forwards; }
	@keyframes toastIn { from { opacity: 0; transform: translateX(80px); } to { opacity: 1; transform: translateX(0); } }
	@keyframes toastOut { from { opacity: 1; } to { opacity: 0; transform: translateX(80px); } }

	/* === TEAM COMPOSITION === */
	.teams-section { padding: 1rem; }
	.team-create-row { display: flex; gap: 0.5rem; margin-bottom: 0.8rem; }
	.team-input { flex: 1; padding: 0.5rem 0.8rem; border-radius: 8px; border: 1px solid var(--glass-border); background: var(--surface-sunken); color: var(--input-color); font-size: 0.8rem; }
	.teams-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(200px, 1fr)); gap: 0.75rem; }
	.team-card { padding: 0.75rem; border-radius: 10px; }
	.team-card-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.5rem; padding-bottom: 0.4rem; border-bottom: 1px solid var(--glass-border); }
	.team-name { font-weight: 800; font-size: 0.85rem; color: var(--accent); }
	.team-delete { background: none; border: none; color: var(--danger); cursor: pointer; font-size: 0.75rem; opacity: 0.5; }
	.team-delete:hover { opacity: 1; }
	.btn-join { background: rgba(16,185,129,0.15); border: 1px solid rgba(16,185,129,0.3); color: #10b981; border-radius: 6px; padding: 0.15rem 0.5rem; font-size: 0.6rem; font-weight: 700; cursor: pointer; transition: all 0.15s; }
	.btn-join:hover { background: rgba(16,185,129,0.3); }
	.team-members { display: flex; flex-direction: column; gap: 0.3rem; margin-bottom: 0.5rem; }
	.team-member { display: flex; justify-content: space-between; align-items: center; font-size: 0.75rem; padding: 0.25rem 0.4rem; background: rgba(59,130,246,0.08); border-radius: 6px; }
	.member-remove { background: none; border: none; color: var(--danger); cursor: pointer; font-size: 0.65rem; opacity: 0.4; }
	.member-remove:hover { opacity: 1; }
	.member-pts { font-size: 0.65rem; font-weight: 800; color: #fbbf24; background: rgba(251,191,36,0.1); padding: 0.1rem 0.4rem; border-radius: 4px; white-space: nowrap; }
	.team-add-select { width: 100%; padding: 0.35rem; border-radius: 6px; border: 1px solid var(--glass-border); background: var(--input-bg); color: var(--input-color); font-size: 0.7rem; appearance: none; -webkit-appearance: none; background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='10' height='6'%3E%3Cpath d='M0 0l5 6 5-6z' fill='%23888'/%3E%3C/svg%3E"); background-repeat: no-repeat; background-position: right 0.5rem center; padding-right: 1.5rem; cursor: pointer; }
	.team-add-select option { background: var(--bg-secondary); color: var(--text-main); padding: 0.4rem; }
	.unassigned-hint { margin-top: 0.75rem; padding: 0.5rem 0.75rem; background: rgba(245,158,11,0.1); border: 1px solid rgba(245,158,11,0.2); border-radius: 8px; color: #f59e0b; font-size: 0.75rem; font-weight: 600; }
	
	/* AXE-30: Drag & Drop */
	.pool-badge[draggable="true"] { cursor: grab; transition: opacity 0.2s, transform 0.2s; }
	.pool-badge[draggable="true"]:active { cursor: grabbing; }
	.pool-badge.dragging { opacity: 0.4; transform: scale(0.95); }
	.team-card { transition: border-color 0.2s, box-shadow 0.2s, background 0.2s, transform 0.2s; }
	.team-card.drag-over { border-color: rgba(6, 182, 212, 0.8); box-shadow: 0 0 15px rgba(6, 182, 212, 0.4), inset 0 0 10px rgba(6, 182, 212, 0.1); background: rgba(6, 182, 212, 0.05); transform: scale(1.02); }


	/* === ROUND ROBIN === */
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

	/* === DOUBLE ELIM LABELS === */
	.de-label { padding: 0.4rem 0.8rem; font-weight: 800; font-size: 0.7rem; text-transform: uppercase; letter-spacing: 1px; color: var(--accent); border-bottom: 2px solid var(--accent); margin-bottom: 0.5rem; }
	.de-label.lb { color: #f59e0b; border-bottom-color: #f59e0b; margin-top: 1.5rem; }
	.lb-section { border-left: 2px solid rgba(245,158,11,0.2); padding-left: 0.5rem; }
	.lb-hdr { color: #f59e0b !important; }
	.lb-match { border-color: rgba(245,158,11,0.15) !important; }

	/* === FFA MODE === */
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
	.ffa-advance-row { display: flex; align-items: center; gap: 0.5rem; font-size: 0.8rem; font-weight: 600; }
	.ffa-keep-input { width: 50px; padding: 0.3rem; border-radius: 6px; border: 1px solid var(--glass-border); background: var(--surface-sunken); color: var(--input-color); text-align: center; font-weight: 800; }

	/* Live Standings */
	.live-standings { padding: 1.2rem; border-radius: var(--radius-lg); border: 1px solid rgba(59,130,246,0.15); }
	.live-badge { font-size: 0.55rem; font-weight: 800; color: #10b981; background: rgba(16,185,129,0.1); padding: 0.15rem 0.5rem; border-radius: 20px; border: 1px solid rgba(16,185,129,0.2); animation: pulse-live 2s infinite; }
	@keyframes pulse-live { 0%,100% { opacity: 1; } 50% { opacity: 0.5; } }
	.ls-list { display: flex; flex-direction: column; gap: 0.3rem; margin-top: 0.75rem; max-height: 400px; overflow-y: auto; }
	.ls-row { display: flex; align-items: center; gap: 0.6rem; padding: 0.45rem 0.6rem; border-radius: 8px; transition: background 0.15s; }
	.ls-row:hover { background: var(--hover-tint); }
	.ls-row.ls-top { border-left: 2px solid var(--accent); background: rgba(59,130,246,0.04); }
	.ls-rank { width: 22px; height: 22px; display: flex; align-items: center; justify-content: center; font-size: 0.7rem; font-weight: 800; border-radius: 6px; background: var(--surface-raised); color: var(--text-dim); }
	.ls-rank.gold { background: rgba(255,215,0,0.15); color: #ffd700; }
	.ls-rank.silver { background: rgba(192,192,192,0.15); color: #c0c0c0; }
	.ls-rank.bronze { background: rgba(205,127,50,0.15); color: #cd7f32; }
	.ls-name { flex-grow: 1; font-size: 0.8rem; font-weight: 600; }
	.ls-pts { font-size: 0.8rem; font-weight: 800; color: var(--accent); white-space: nowrap; }

	/* Standings config summary */
	.ls-config-summary { display: flex; gap: 0.5rem; flex-wrap: wrap; margin-top: 0.5rem; padding: 0.4rem 0.6rem; border-radius: 8px; background: var(--surface-sunken); }
	.ls-cfg { font-size: 0.65rem; font-weight: 600; color: var(--text-dim); cursor: help; white-space: nowrap; }

	/* Standings row info & breakdown */
	.ls-info { flex-grow: 1; display: flex; flex-direction: column; gap: 0.1rem; min-width: 0; }
	.ls-breakdown { display: flex; gap: 0.3rem; flex-wrap: wrap; }
	.ls-bp { font-size: 0.55rem; font-weight: 700; padding: 0.05rem 0.35rem; border-radius: 4px; cursor: help; white-space: nowrap; }
	.ls-bp-place { color: #fbbf24; background: rgba(251,191,36,0.1); }
	.ls-bp-score { color: #818cf8; background: rgba(129,140,248,0.1); }
	.ls-bp-parti { color: var(--text-muted); background: var(--surface-sunken); }

	/* AXE-32: Boolean Mode */
	.bool-btns { display: flex; gap: 0.2rem; align-items: center; }
	.bool-btn {
		padding: 0.15rem 0.35rem; border-radius: 6px; border: 1px solid var(--glass-border);
		background: transparent; cursor: pointer; font-size: 0.85rem;
		transition: all 0.15s; opacity: 0.5; line-height: 1;
	}
	.bool-btn:hover { opacity: 1; transform: scale(1.15); border-color: rgba(59,130,246,0.4); }
	.bool-btn.bool-draw:hover { border-color: rgba(245,158,11,0.5); background: rgba(245,158,11,0.1); }
	/* Checkbox style: ☐ default → ✅ on hover */
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

	/* === CONTROLS ROW === */
	.controls-row { display: flex; align-items: stretch; gap: 0.75rem; margin-bottom: 0.5rem; width: 100%; }
	.controls-row .admin-bar { flex-grow: 1; margin-bottom: 0; padding: 0.4rem 1rem; }
	.controls-row .toggle-details-btn, .controls-row .toggle-live-btn { margin-bottom: 0; flex-shrink: 0; align-self: stretch; border-radius: 10px; }
	.detail-body.collapsed-layout { padding-bottom: 0; }
	.t-detail.collapsed-layout { overflow-y: hidden; }
	.toggle-details-btn, .toggle-live-btn { display: inline-flex; align-items: center; justify-content: center; gap: 0.5rem; padding: 0.5rem 1rem; font-size: 0.75rem; font-weight: 700; color: var(--accent); background: var(--accent-soft); border: 1px solid var(--glass-border); border-radius: 8px; cursor: pointer; transition: all 0.2s ease-in-out; align-self: flex-start; margin-bottom: 0.5rem; }
	.toggle-details-btn:hover, .toggle-live-btn:hover { background: var(--accent); color: white; box-shadow: 0 0 10px var(--accent-glow); transform: translateY(-1px); }
	.toggle-details-btn:active, .toggle-live-btn:active { transform: translateY(0); }
	/* === TOURNAMENT SPLIT LAYOUT === */
	.tournament-split-layout { display: flex; flex-direction: column; gap: 1.5rem; width: 100%; flex-shrink: 0; }
	
	/* Layout behavior for folded (max-height viewport) mode */
	.tournament-split-layout.split-fill { flex-grow: 1; min-height: 0; flex-shrink: 1; height: 100%; }
	.split-fill > .bracket-section { flex-grow: 1; min-height: 0; height: 100%; }
	.split-fill > .live-standings { flex-grow: 1; min-height: 0; height: 100%; display: flex; flex-direction: column; }
	.split-fill .ls-list { flex-grow: 1; min-height: 0; overflow-y: auto; max-height: none; }
	.split-fill .ffa-container { max-height: none; flex-grow: 1; min-height: 0; }
	.split-fill .bracket-viewport-wrapper { flex-grow: 1; min-height: 0; height: 100%; }

	/* Active split layout (side-by-side) - Ordered last to win cascade and force 50% width */
	.tournament-split-layout.split-active { flex-direction: row; align-items: stretch; }
	.split-active > .bracket-section { flex: 1 1 0%; min-width: 0; }
	.split-active > .live-standings { flex: 1 1 0%; min-width: 300px; margin-top: 0; }
</style>
