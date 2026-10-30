<script>
	import { resolveMediaUrl, mediaThumb } from '$lib/config';
	import { t, currentLang } from '$lib/i18nStore';
	import { get } from 'svelte/store';
	import { api } from '$lib/api';
	import { onMount, onDestroy } from 'svelte';
	import { wsMessageStore } from '$lib/ws';
	import { page } from '$app/stores';
	import { authStore } from '$lib/auth';
	import CreateTournamentWizard from '$lib/components/CreateTournamentWizard.svelte';
	import EditTournamentModal from '$lib/components/EditTournamentModal.svelte';
	import Icon from '$lib/components/Icon.svelte';
	import { formatPoints } from '$lib/utils';

	import TournamentParticipants from './components/TournamentParticipants.svelte';
	import TournamentTeams from './components/TournamentTeams.svelte';
	import TournamentStandings from './components/TournamentStandings.svelte';
	import TournamentBracket from './components/TournamentBracket.svelte';
	import GroupStagePanel from './components/GroupStagePanel.svelte';

	let tournaments = [];
	let games = [];
	let selectedId = null;
	let selected = null;
	let participants = [];
	let allUsers = [];
	let currentUser = null;
	let editingTournament = false;
	let editConfig = {};

	let showDetails = true;
	let showMobileTourneyDrawer = false;
	let isMobile = false;
	$: isMobile = typeof window !== 'undefined' && window.innerWidth <= 900;
	let showLiveStandings = false;
	let bracketRef = null;

	let loadingTournaments = true;
	let lastLoadedForTourneyId = null;

	// Mobile secondary modals for dedicated isolated views
	let showMobileInfoModal = false;
	let showMobilePlayersModal = false;
	let showMobileStandingsModal = false;
	let showMobileAdminModal = false;

	$: if (selectedId) {
		const savedShowDetails = localStorage.getItem('alanbix_show_details');
		if (savedShowDetails !== null) {
			showDetails = savedShowDetails === 'true';
		} else {
			showDetails = !isMobile && !!currentUser?.is_admin;
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

	// Tournament Creation & Teams State
	let showCreateModal = false;
	let teams = [];
	let standingsData = [];

	// Toast system
	let toasts = [];
	let toastId = 0;

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
		const urlSelect = $page?.url?.searchParams?.get('select') || $page?.url?.searchParams?.get('id');
		const savedSelect = typeof window !== 'undefined' ? localStorage.getItem('alanbix_selected_tournament') : null;
		let target = null;
		if (urlSelect && tournaments.some(t => String(t.id) === String(urlSelect))) {
			target = parseInt(urlSelect, 10);
		} else if (selectedId && tournaments.some(t => String(t.id) === String(selectedId))) {
			target = selectedId;
		} else if (savedSelect && tournaments.some(t => String(t.id) === String(savedSelect))) {
			target = parseInt(savedSelect, 10);
		} else if (tournaments.length > 0) {
			target = tournaments[0].id;
		}
		if (target) {
			await selectTournament(target);
		}
		wsUnsub = wsMessageStore.subscribe(handleWsMessage);
	});

	// Unified reactive tournament selection watcher (handles initial load, deep-links, in-app navigation, and fallback)
	$: if (tournaments.length > 0) {
		const urlSelect = $page?.url?.searchParams?.get('select') || $page?.url?.searchParams?.get('id');
		const savedSelect = typeof window !== 'undefined' ? localStorage.getItem('alanbix_selected_tournament') : null;

		let targetId = null;
		if (urlSelect && tournaments.some(t => String(t.id) === String(urlSelect))) {
			targetId = parseInt(urlSelect, 10);
		} else if (selectedId && tournaments.some(t => String(t.id) === String(selectedId))) {
			targetId = selectedId;
		} else if (savedSelect && tournaments.some(t => String(t.id) === String(savedSelect))) {
			targetId = parseInt(savedSelect, 10);
		} else {
			targetId = tournaments[0].id;
		}

		if (targetId && (String(targetId) !== String(selectedId) || lastLoadedForTourneyId !== targetId || !selected)) {
			selectTournament(targetId);
		}
	}


	// WS: Debounced & jittered refresh to prevent thundering herd across LAN clients
	let wsUnsub = null;
	let refreshDebounceTimer = null;
	let isRefreshing = false;
	let pendingRefresh = false;

	let needTournaments = false;
	let needParticipants = false;
	let needTeams = false;
	let needStandings = false;
	let needGames = false;
	let needUsers = false;
	let deletedTourneyId = null;

	function scheduleTournamentRefresh() {
		if (refreshDebounceTimer) clearTimeout(refreshDebounceTimer);
		const jitter = Math.floor(Math.random() * 100);
		refreshDebounceTimer = setTimeout(async () => {
			if (isRefreshing) {
				pendingRefresh = true;
				return;
			}
			isRefreshing = true;

			const fetchTournaments = needTournaments;
			const fetchParts = needParticipants && !!selectedId;
			const fetchTeams = needTeams && !!selectedId;
			const fetchStandings = needStandings && !!selectedId;
			const fetchGames = needGames;
			const fetchUsers = needUsers;
			const checkDeletedId = deletedTourneyId;

			needTournaments = false;
			needParticipants = false;
			needTeams = false;
			needStandings = false;
			needGames = false;
			needUsers = false;
			deletedTourneyId = null;

			try {
				const currentSelectedId = selectedId;
				const promises = [
					fetchTournaments ? api.get('/tournaments').catch(() => null) : Promise.resolve(null),
					fetchParts ? api.get(`/tournaments/${currentSelectedId}/participants`).catch(() => null) : Promise.resolve(null),
					fetchTeams ? api.get(`/tournaments/${currentSelectedId}/teams`).catch(() => null) : Promise.resolve(null),
					fetchStandings ? api.get(`/tournaments/${currentSelectedId}/standings`).catch(() => null) : Promise.resolve(null),
					fetchGames ? api.get('/tournaments/games').catch(() => null) : Promise.resolve(null),
					fetchUsers ? api.get('/room/users').catch(() => null) : Promise.resolve(null)
				];

				const [newTourneys, newParts, newTeams, newStandings, newGames, newUsers] = await Promise.all(promises);

				if (newTourneys) {
					tournaments = newTourneys;
					if (checkDeletedId && currentSelectedId === checkDeletedId) {
						selectedId = tournaments.length > 0 ? tournaments[0].id : null;
						if (selectedId) await selectTournament(selectedId);
					}
				}
				if (newParts && selectedId === currentSelectedId) participants = newParts;
				if (newTeams && selectedId === currentSelectedId) teams = newTeams;
				if (newStandings && selectedId === currentSelectedId) standingsData = newStandings.standings || [];
				if (newGames) games = newGames;
				if (newUsers) allUsers = newUsers;
			} catch (err) {
				console.error("Error during debounced tournament refresh:", err);
			} finally {
				isRefreshing = false;
				if (pendingRefresh) {
					pendingRefresh = false;
					scheduleTournamentRefresh();
				}
			}
		}, 250 + jitter);
	}

	function handleWsMessage(msg) {
		if (!msg) return;
		const t = msg.type;
		const tid = msg.tournament_id || msg.id || msg.data?.id;
		const isCurrentSelected = selectedId && (tid === selectedId || !tid);

		if (t === 'games_updated') {
			needGames = true;
		} else if (t === 'users_updated' || t === 'room_updated') {
			needUsers = true;
		} else if (t === 'teams_updated') {
			if (isCurrentSelected) {
				needTeams = true;
				needStandings = true;
			}
		} else if (t === 'score_updated' || t === 'ffa_advanced' || t === 'ffa_rolled_back') {
			needTournaments = true;
			if (isCurrentSelected) {
				needStandings = true;
			}
		} else if (t === 'tournament_started' || t === 'tournament_closed' || t === 'tournament_reopened') {
			needTournaments = true;
			if (isCurrentSelected) {
				needParticipants = true;
				needTeams = true;
				needStandings = true;
			}
		} else if (t === 'tournament_created') {
			needTournaments = true;
		} else if (t === 'tournament_updated') {
			needTournaments = true;
			if (isCurrentSelected) {
				needParticipants = true;
				needTeams = true;
				needStandings = true;
			}
		} else if (t === 'tournament_deleted') {
			needTournaments = true;
			if (msg.tournament_id) deletedTourneyId = msg.tournament_id;
		} else if (t === 'participant_joined' || t === 'participant_left') {
			needTournaments = true;
			if (isCurrentSelected) {
				needParticipants = true;
				needStandings = true;
			}
		} else {
			return;
		}

		scheduleTournamentRefresh();
	}

	onDestroy(() => {
		if (refreshDebounceTimer) clearTimeout(refreshDebounceTimer);
		if (wsUnsub) wsUnsub();
	});

	async function loadAll() {
		loadingTournaments = true;
		try {
			const [tourneysRes, gamesRes, userRes, roomUsersRes] = await Promise.all([
				api.get('/tournaments').catch(() => []),
				api.get('/tournaments/games').catch(() => []),
				api.get('/me').catch(() => null),
				api.get('/room/users').catch(() => [])
			]);
			tournaments = tourneysRes || [];
			games = gamesRes || [];
			currentUser = userRes;
			allUsers = roomUsersRes || [];
			if (selectedId) {
				selected = tournaments.find(t => String(t.id) === String(selectedId)) || null;
			}
		} catch (err) {
			console.error("Error loading all tournaments page data:", err);
		} finally {
			loadingTournaments = false;
		}
	}

	let confirmingLeave = false;

	async function selectTournament(id) {
		const numericId = typeof id === 'string' ? (parseInt(id, 10) || id) : id;
		selectedId = numericId;
		selected = tournaments.find(t => String(t.id) === String(numericId)) || null;
		lastLoadedForTourneyId = numericId;
		try { localStorage.setItem('alanbix_selected_tournament', String(numericId)); } catch (e) {}
		confirmingLeave = false;
		try {
			const [partsRes, teamsRes, standingsRes] = await Promise.all([
				api.get(`/tournaments/${numericId}/participants`).catch(() => []),
				api.get(`/tournaments/${numericId}/teams`).catch(() => []),
				api.get(`/tournaments/${numericId}/standings`).catch(() => ({ standings: [] }))
			]);
			participants = partsRes || [];
			teams = teamsRes || [];
			standingsData = standingsRes.standings || [];
			bracketRef?.resetZoom();
		} catch (err) {
			console.error("Error selecting tournament:", err);
			participants = [];
			teams = [];
			standingsData = [];
		}
	}

	async function joinTournament(id) {
		try {
			await api.post(`/tournaments/${id}/join`, {});
			toast($t('tourneys_toast_joined'), 'success');
			tournaments = await api.get('/tournaments');
			await selectTournament(id);
		} catch (e) { toast(e.detail || e.message, 'error'); }
	}

	async function leaveTournament(id) {
		try {
			confirmingLeave = false;
			await api.post(`/tournaments/${id}/leave`, {});
			toast($t('tourneys_toast_player_removed'), 'success');
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

	async function joinAllPlayers() {
		try {
			const res = await api.post(`/tournaments/${selectedId}/join-all`, {});
			toast($t('tourneys_toast_join_all_done', { count: res.added }), 'success');
			tournaments = await api.get('/tournaments');
			await selectTournament(selectedId);
		} catch (e) { toast(e.message || 'Erreur', 'error'); }
	}

	async function leaveAllPlayers() {
		try {
			const res = await api.post(`/tournaments/${selectedId}/leave-all`, {});
			toast($t('tourneys_toast_leave_all_done', { count: res.removed }), 'success');
			tournaments = await api.get('/tournaments');
			await selectTournament(selectedId);
		} catch (e) { toast(e.message || 'Erreur', 'error'); }
	}

	async function createTeam(name) {
		if (!name?.trim()) return;
		try {
			await api.post(`/tournaments/${selectedId}/teams`, { name: name.trim() });
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

	async function toggleTeamLock(teamId, isLocked) {
		try {
			await api.put(`/tournaments/${selectedId}/teams/${teamId}/lock`, { is_locked: isLocked });
			teams = await api.get(`/tournaments/${selectedId}/teams`);
			toast(isLocked ? $t('tourneys_team_locked') : $t('tourneys_team_unlocked'), 'success');
		} catch (e) { toast(e.message || 'Erreur', 'error'); }
	}

	async function setTeamCaptain(teamId, captainId) {
		try {
			await api.put(`/tournaments/${selectedId}/teams/${teamId}/captain`, { captain_id: captainId });
			teams = await api.get(`/tournaments/${selectedId}/teams`);
			toast($t('tourneys_toast_new_captain'), 'success');
		} catch (e) { toast(e.message || 'Erreur', 'error'); }
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
			await api.post(`/tournaments/${selectedId}/close`);
			toast($t('tourneys_toast_closed'), 'success');
			tournaments = await api.get('/tournaments');
			await selectTournament(selectedId);
		} catch (e) { toast(e.message || 'Erreur', 'error'); }
	}

	let confirmingReopen = false;
	async function reopenTournament() {
		try {
			confirmingReopen = false;
			await api.post(`/tournaments/${selectedId}/reopen`);
			toast($t('tourneys_toast_reopened'), 'success');
			tournaments = await api.get('/tournaments');
			await selectTournament(selectedId);
		} catch (e) { toast(e.message || 'Erreur', 'error'); }
	}

	// The signed-in player's next unplayed 1v1 match in the selected tournament
	$: myNextMatch = (() => {
		if (!selected || selected.status !== 'RUNNING' || !currentUser || !Array.isArray(selected.bracket)) return null;
		const teamMap = selected.config?._team_map || {};
		const myTeam = (participants.find(p => p.user_id === currentUser.id)?.team_name || '').toLowerCase();
		const isMe = (pid) => pid === currentUser.id || (pid < 0 && myTeam && (teamMap[String(pid)] || '').toLowerCase() === myTeam);
		for (const m of selected.bracket) {
			const pl = m.p || [];
			if (pl.length !== 2 || pl.includes(0)) continue;
			const sc = m.score || [];
			const done = sc[0] != null && sc[1] != null && (sc[0] !== 0 || sc[1] !== 0);
			if (done) continue;
			const mySlot = isMe(pl[0]) ? 0 : isMe(pl[1]) ? 1 : -1;
			if (mySlot === -1) continue;
			const oppId = pl[1 - mySlot];
			const oppName = oppId < 0
				? (teamMap[String(oppId)] || `#${Math.abs(oppId)}`)
				: (participants.find(p => p.user_id === oppId)?.username || allUsers.find(u => u.id === oppId)?.username || `#${oppId}`);
			const round = m.id?.s === 2 ? $t('tourneys_bracket_lb_round', { n: m.id.r }) : $t('tourneys_round_n', { n: m.id?.r || 1 });
			return { match: m, mySlot, oppName, round, key: `${selected.id}_${m.id?.s}_${m.id?.r}_${m.id?.m}` };
		}
		return null;
	})();
	let myScoreInput = '';
	let oppScoreInput = '';
	let lastMyMatchKey = null;
	$: if (myNextMatch?.key !== lastMyMatchKey) { lastMyMatchKey = myNextMatch?.key; myScoreInput = ''; oppScoreInput = ''; }
	let submittingMyScore = false;

	async function submitMyMatchScore() {
		const mine = parseInt(myScoreInput, 10), opp = parseInt(oppScoreInput, 10);
		if (Number.isNaN(mine) || Number.isNaN(opp)) return;
		submittingMyScore = true;
		const score = myNextMatch.mySlot === 0 ? [mine, opp] : [opp, mine];
		await doSubmitScore(myNextMatch.match, score);
		submittingMyScore = false;
	}

	async function doSubmitScore(match, score) {
		try {
			await api.put(`/tournaments/${selectedId}/score`, {
				match_s: match.id.s, match_r: match.id.r, match_m: match.id.m, score
			});
			tournaments = await api.get('/tournaments');
		} catch (e) { toast(e.message || $t('tourneys_score_error'), 'error'); }
	}

	async function advanceFFA(keepCount, perMatch = false) {
		try {
			await api.post(`/tournaments/${selectedId}/ffa-advance`, { keep_count: keepCount, per_match: perMatch });
			toast($t('tourneys_toast_round_advanced', { count: keepCount }), 'success');
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
			await api.post(`/tournaments/${selectedId}/ffa-rollback`, {});
			toast($t('tourneys_toast_ffa_rolled_back'), 'success');
			await loadAll();
			await selectTournament(selectedId);
		} catch (e) { toast(e.detail || e.message || 'Erreur', 'error'); }
	}

	function openEdit() {
		editConfig = {
			name: selected.name,
			game_id: selected.game_id,
			custom_rules: selected.config?.custom_rules ?? '',
			team_lock_mode: selected.config?.team_lock_mode || 'captain',
			points_per_win: selected.points_per_win || 3,
			use_teams: selected.config?.use_teams || false,
			team_size: selected.config?.team_size || 1,
			bracket_type: selected.config?.bracket_type || 'single_elim',
			pts_winner: selected.config?.pts_winner ?? 1.5,
			pts_second: selected.config?.pts_second ?? 1.3,
			pts_third: selected.config?.pts_third ?? 1.0,
			pts_participation: selected.config?.pts_participation ?? 1.0,
			pts_per_match: selected.config?.pts_per_match ?? 0.5,
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
				game_id: editConfig.game_id,
				points_per_win: editConfig.points_per_win,
				config: {
					...selected.config,
					use_teams: editConfig.use_teams,
					team_size: editConfig.team_size,
					custom_rules: editConfig.custom_rules,
					team_lock_mode: editConfig.team_lock_mode,
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

	function bracketLabel(format, config = null) {
		// groups then knockout: show both phases, whatever the current stage
		if (config?.phases === 'double' && config.stage) {
			const ko = config.stage === 'knockout' ? format : config.ko_type;
			return get(t)('groups_format_summary', { format: bracketLabel(ko) });
		}
		if (format === 'single_elim') return get(t)('admin_tourneys_wizard_format_single');
		if (format === 'double_elim') return get(t)('admin_tourneys_wizard_format_double');
		if (format === 'round_robin') return get(t)('admin_tourneys_wizard_format_championship');
		if (format === 'ffa') return get(t)('tourneys_format_ffa');
		return format || get(t)('tourneys_status_unknown');
	}

	function getRounds(bracket) {
		if (!bracket || !Array.isArray(bracket)) return [];
		const rounds = {};
		bracket.forEach(m => { if (!rounds[m.id.r]) rounds[m.id.r] = []; rounds[m.id.r].push(m); });
		return Object.keys(rounds).sort((a,b) => a-b).map(k => rounds[k]);
	}

	$: nameMap = (() => {
		const m = {};
		participants.forEach(p => { m[p.user_id] = p.username; });
		const tm = selected?.config?._team_map || {};
		Object.entries(tm).forEach(([id, name]) => { m[id] = name; });
		teams.forEach(t => { const key = String(-t.id); if (!m[key]) m[key] = t.name; });
		return m;
	})();

	$: seatMap = Object.fromEntries(allUsers.filter(u => u.seat_id).map(u => [u.id, u.seat_id]));

	$: selected = tournaments.find(t => String(t.id) === String(selectedId)) || selected;
	$: selectedGame = selected ? getGame(selected.game_id) : null;
	$: gameMap = Object.fromEntries(games.map(g => [g.id, g]));
	$: unregisteredUsers = allUsers.filter(u => !participants.find(p => p.user_id === u.id));
	// Groups + knockout: the group matches (section >= 100) live in the same bracket list
	$: stage = selected?.config?.stage || null;
	$: isTwoPhase = selected?.config?.phases === 'double' && !!stage;
	let phaseTab = 'knockout';
	let groupData = null;
	$: groupTables = groupData && groupData.groups ? Object.fromEntries(groupData.groups.map(g => [g.group, g.table])) : null;
	$: if (!isTwoPhase) groupData = null;
	$: if (stage !== 'knockout') phaseTab = 'knockout';
	$: koMatches = (selected?.bracket || []).filter(m => m.id.s < 100);
	$: groupMatches = (selected?.bracket || []).filter(m => m.id.s >= 100);
	$: showingGroups = isTwoPhase && (stage === 'groups' || phaseTab === 'groups');
	$: bracketRounds = selected ? getRounds(isTwoPhase ? koMatches : selected.bracket) : [];
	$: hasBracket = (selected?.bracket || []).length > 0;
	$: viewBracketType = showingGroups ? 'round_robin' : bracketType;
	$: isAdmin = currentUser?.is_admin;
	$: isParticipant = participants.some(p => p.user_id === currentUser?.id);
	$: myTeam = teams.find(t => t.members?.some(m => m.user_id === currentUser?.id));
	$: useTeams = selected?.config?.use_teams || false;
	$: myTeamSlotId = (useTeams && myTeam) ? -myTeam.id : null;
	$: bracketType = selected?.config?.bracket_type || 'single_elim';
	$: lowerIsBetter = selected?.config?.lower_score_is_better || false;
	$: booleanMode = selected?.config?.boolean_mode || false;
	$: unassignedPlayers = useTeams ? participants.filter(p => !teams.some(t => t.members?.some(m => m.user_id === p.user_id))) : [];
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
		const hasVisible = roundMatches.some(m => {
			const isBye = m.p[0] === 0 && m.p[1] === 0;
			const s0 = m.score?.[0] ?? null, s1 = m.score?.[1] ?? null;
			const isDone = s0 !== null && s1 !== null && (s0 !== 0 || s1 !== 0) && s0 !== s1;
			const isAutoWin = (m.p[0] === 0 || m.p[1] === 0) && (s0 > 0 || s1 > 0);
			return !isBye && !isAutoWin;
		});
		return hasVisible ? { matches: roundMatches, originalIndex: ri } : null;
	}).filter(Boolean);

	$: liveStandings = standingsData.map(s => ({
		id: s.entity_id, name: s.name, pts: formatPoints(s.total), rank: s.rank,
		placement_pts: formatPoints(s.placement_pts), participation_pts: formatPoints(s.participation_pts),
		score_pts: formatPoints(s.score_pts), per_member: formatPoints(s.per_member), member_count: s.member_count,
		wins: s.wins ?? 0, matches_played: s.matches_played ?? 0, pts_per_match: s.pts_per_match ?? 1.0,
		cumulated_score: s.cumulated_score ?? 0
	}));
	$: displayStandings = liveStandings;

	$: rrGroups = (() => {
		if (!selected || !selected.bracket || !(bracketType === 'round_robin' || showingGroups)) return [];
		const groups = {};
		(isTwoPhase ? groupMatches : selected.bracket).forEach(m => {
			const gId = m.id.s >= 100 ? m.id.s - 100 : m.id.s;
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
			return { id: gId, rounds: rounds };
		});
	})();

	function getPlayerPts(userId, standings) {
		if (useTeams && teams.length > 0) {
			const playerTeam = teams.find(t => t.members?.some(m => m.user_id === userId));
			if (playerTeam) {
				const teamBracketId = -playerTeam.id;
				const teamEntry = standings.find(s => s.id === teamBracketId);
				if (teamEntry) return formatPoints(teamEntry.pts);
			}
		}
		const entry = standings.find(s => s.id === userId);
		return entry ? formatPoints(entry.pts) : 0;
	}
</script>

<!-- Mobile Top Selector Bar (<= 900px) -->
<div class="mobile-tourney-bar glass">
	<button class="mobile-tourney-trigger" on:click={() => showMobileTourneyDrawer = true} title={$t('tourneys_title')}>
		<Icon name="menu" size={16} />
		<span class="trigger-name">{selected?.name || $t('tourneys_title')}</span>
		{#if selected}
			<span class="status-pill {selected.status.toLowerCase()}">
				{selected.status === 'OPEN' ? $t('tourneys_status_open') : selected.status === 'RUNNING' ? $t('tourneys_status_running') : selected.status === 'CLOSED' ? $t('tourneys_status_closed') : $t('tourneys_status_done')}
			</span>
		{/if}
		<Icon name="chevron-down" size={14} />
	</button>
	{#if currentUser?.is_admin}
		<button class="mobile-add-btn" on:click={openCreateTournamentModal} title={$t('tourneys_add_btn')}>
			<Icon name="plus" size={14} />
		</button>
	{/if}
</div>

<!-- Mobile Sub-navigation Chips for secondary info -->
{#if isMobile && selected}
	<div class="mobile-subnav-chips glass">
		<button class="m-chip" on:click={() => showMobileInfoModal = true} title={$t('tourneys_mobile_rules_info')}>
			<Icon name="info" size={13} />
			<span>{$t('tourneys_tab_rules')}</span>
		</button>
		<button class="m-chip" on:click={() => showMobilePlayersModal = true} title={$t('tourneys_mobile_players_teams')}>
			<Icon name="users" size={13} />
			<span>{$t('dash_stat_players')} ({participants.length})</span>
		</button>
		{#if liveStandings.length > 0 || selected.status === 'CLOSED'}
			<button class="m-chip" on:click={() => showMobileStandingsModal = true} title={$t('tourneys_show_standings')}>
				<Icon name="trophy" size={13} />
				<span>{$t('tourneys_show_standings')}</span>
			</button>
		{/if}
		{#if currentUser?.is_admin}
			<button class="m-chip admin" on:click={() => showMobileAdminModal = true} title={$t('nav_administration')}>
				<Icon name="gear" size={13} />
				<span>{$t('tourneys_mobile_admin_chip')}</span>
			</button>
		{/if}
		{#if selected.status === 'OPEN'}
			{#if isParticipant}
				<button class="m-chip joined" on:click={() => leaveTournament(selected.id)}>
					<span><Icon name="check-circle" size={15} /> {$t("tourneys_hero_joined")}</span>
				</button>
			{:else}
				<button class="m-chip join" on:click={() => joinTournament(selected.id)}>
					<span><Icon name="gamepad" size={15} /> {$t("tourneys_btn_join_text")}</span>
				</button>
			{/if}
		{/if}
	</div>
{/if}

<!-- Lateral Drawer for Vertical Tournament Selection (Mobile) -->
{#if showMobileTourneyDrawer}
	<!-- svelte-ignore a11y-click-events-have-key-events -->
	<div class="mobile-tourney-drawer-overlay" on:click|self={() => showMobileTourneyDrawer = false}>
		<div class="mobile-tourney-drawer glass animate-in">
			<div class="drawer-header">
				<div class="drawer-title-row">
					<Icon name="trophy" size={16} />
					<h3>{$t('tourneys_title')} ({tournaments.length})</h3>
				</div>
				<button class="drawer-close-btn" on:click={() => showMobileTourneyDrawer = false} title={$t('common_close')}>
					<Icon name="x" size={16} />
				</button>
			</div>
			{#if currentUser?.is_admin}
				<button class="drawer-add-btn" on:click={() => { showMobileTourneyDrawer = false; openCreateTournamentModal(); }}>
					<Icon name="plus" size={14} /> {$t('tourneys_add_btn')}
				</button>
			{/if}
			<div class="drawer-tourneys-list">
				{#each tournaments as tourney}
					<button
						class="drawer-tourney-item {String(selectedId) === String(tourney.id) ? 'active' : ''}"
						on:click={() => { selectTournament(tourney.id); showMobileTourneyDrawer = false; }}
					>
						{#if gameMap[tourney.game_id]?.image_url}
							<span class="drawer-item-thumb" style="background-image: url({mediaThumb(gameMap[tourney.game_id].image_url, 96)})"></span>
						{/if}
						<div class="drawer-item-info">
							<span class="drawer-item-name">{tourney.name}</span>
							<span class="drawer-item-game">{gameMap[tourney.game_id]?.name || '—'}</span>
						</div>
						<span class="status-pill {tourney.status.toLowerCase()}">
							{tourney.status === 'OPEN' ? $t('tourneys_status_open') : tourney.status === 'RUNNING' ? $t('tourneys_status_running') : tourney.status === 'CLOSED' ? $t('tourneys_status_closed') : $t('tourneys_status_done')}
						</span>
					</button>
				{/each}
			</div>
		</div>
	</div>
{/if}

<div class="tournaments-layout">
	<!-- Sidebar -->
	<aside class="t-sidebar glass">
		<div class="sidebar-header">
			<h2><Icon name="trophy" size={16} /> {$t('tourneys_title')}</h2>
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
				<button class="t-item {String(selectedId) === String(tourney.id) ? 'active' : ''} {tourney.status.toLowerCase()}" on:click={() => selectTournament(tourney.id)} style="background-image: url({mediaThumb(gameMap[tourney.game_id]?.image_url, 320)})">
					{#if tourney.status === 'CLOSED'}<div class="t-item-checkered"></div>{/if}
					<div class="t-item-overlay">
						<div class="t-item-info">
							<span class="t-item-name">{tourney.name}</span>
							<span class="t-item-meta">{gameMap[tourney.game_id]?.name || '—'}</span>
						</div>
						<span class="t-status-badge {tourney.status.toLowerCase()}">
							{tourney.status === 'OPEN' ? $t('tourneys_status_open') : tourney.status === 'RUNNING' ? $t('tourneys_status_running') : tourney.status === 'CLOSED' ? $t('tourneys_status_closed') : $t('tourneys_status_done')}
						</span>
					</div>
				</button>
			{:else}
				<div class="t-empty-sidebar"><span class="text-dim text-xs">{$t("dash_no_tournament")}</span></div>
			{/each}
		</div>
	</aside>

	<!-- Main Detail -->
	<main class="t-detail" class:collapsed-layout={selected?.status !== 'OPEN' && !showDetails}>
		{#if selected}
			<!-- Hero (Desktop only) -->
			{#if !isMobile}
			<div class="detail-hero" style="background-image: url({mediaThumb(selectedGame?.image_url, 640)})">
				{#if selected.status === 'CLOSED'}<div class="hero-checkered"></div>{/if}
				<div class="hero-overlay">
					<div class="hero-content">
						<span class="status-pill {selected.status.toLowerCase()}">
							{selected.status === 'OPEN' ? $t('tourneys_status_open') : selected?.status === 'RUNNING' ? $t('tourneys_status_running') : selected.status === 'CLOSED' ? $t('tourneys_status_closed') : $t('tourneys_status_done')}
						</span>
						<h1>{selected.name}</h1>
						<span class="hero-game">{selectedGame?.name || '—'}</span>
					</div>
					{#if selected.status === 'OPEN'}
						{#if isParticipant}
							{#if confirmingLeave}
								<span class="inline-confirm">
									<span class="inline-confirm-label">{$t("tourneys_confirm_leave")}</span>
									<button class="admin-btn confirm-yes" on:click={() => leaveTournament(selected.id)}><Icon name="check" size={15} /> {$t("tourneys_confirm_yes")}</button>
									<button class="admin-btn confirm-no" on:click={() => confirmingLeave = false}><Icon name="x" size={16} /></button>
								</span>
							{:else}
								<div class="hero-joined-wrapper" style="display: flex; gap: 0.6rem; align-items: center;">
									<span class="hero-joined"><Icon name="check-circle" size={15} /> {$t("tourneys_hero_joined")}</span>
									<button class="admin-btn stop btn-xs" on:click={() => confirmingLeave = true}><Icon name="x-circle" size={15} /> {$t("tourneys_btn_leave")}</button>
								</div>
							{/if}
						{:else}
							<button class="btn-primary hero-join" on:click={() => joinTournament(selected.id)}><Icon name="gamepad" size={15} /> {$t("tourneys_btn_join_text")}</button>
						{/if}
					{/if}
				</div>
				{#if selected.config?.custom_rules || selectedGame?.rules}
					<div class="hero-rules">
						<span class="hero-rules-label">{$t("tourneys_tab_rules")}</span>
						<p class="hero-rules-text">{selected.config?.custom_rules || selectedGame?.rules}</p>
					</div>
				{/if}
				{#if useTeams}
					<div class="hero-team-badge" style="margin-top: 0.5rem; display: inline-flex; align-items: center; gap: 0.4rem; padding: 0.25rem 0.6rem; border-radius: 6px; background: rgba(59,130,246,0.15); border: 1px solid rgba(59,130,246,0.3); font-size: 0.75rem;">
						{#if myTeam}
							<span><Icon name="users" size={15} /> {$t('dash_team_lbl')} : <strong>{myTeam.name}</strong></span>
							{#if myTeam.is_locked}<span title={$t('tourneys_team_locked')}><Icon name="lock" size={16} /></span>{/if}
						{:else}
							<span style="color: #f59e0b;"><Icon name="alert-triangle" size={15} /> {$t('profile_no_team')}</span>
							<button class="admin-btn edit btn-xs" on:click={() => { showDetails = true; setTimeout(() => document.getElementById('teams-section')?.scrollIntoView({ behavior: 'smooth' }), 50); }} style="padding: 0.15rem 0.4rem; font-size: 0.65rem;">{$t('tourneys_btn_join_text')}</button>
						{/if}
					</div>
				{/if}
			</div>
			{/if}

			<!-- Info Cards -->
			<div class="detail-body" class:collapsed-layout={selected?.status !== 'OPEN' && !showDetails}>
				{#if myNextMatch}
					<section class="my-match glass">
						<div class="mm-head">
							<p class="mm-title">{$t('dash_next_match_title')} · <span class="mm-round">{myNextMatch.round}</span></p>
							<div class="mm-versus">
								<span class="mm-vs-label">{$t('mobile_match_versus')}</span>
								<span class="mm-opponent">{myNextMatch.oppName}</span>
							</div>
						</div>
						<form class="mm-score" on:submit|preventDefault={submitMyMatchScore}>
							<label class="mm-field">
								<span>{$t('mobile_score_my_score')}</span>
								<input type="number" min="0" inputmode="numeric" bind:value={myScoreInput} disabled={submittingMyScore} />
							</label>
							<span class="mm-dash">–</span>
							<label class="mm-field">
								<span>{myNextMatch.oppName}</span>
								<input type="number" min="0" inputmode="numeric" bind:value={oppScoreInput} disabled={submittingMyScore} />
							</label>
							<button class="btn-primary mm-submit" type="submit" disabled={submittingMyScore || myScoreInput === '' || oppScoreInput === '' || myScoreInput === null || oppScoreInput === null}>
								<Icon name="check" size={14} /> {$t('mobile_score_submit')}
							</button>
						</form>
					</section>
				{/if}
				{#if !isMobile}
				<div class="controls-row">
					<button class="toggle-details-btn glass" on:click={toggleDetails}>
						<Icon name={showDetails ? 'chevron-up' : 'chevron-down'} size={12} />
						<span>{showDetails ? $t('tourneys_btn_hide_details') : $t('tourneys_btn_show_details')}</span>
					</button>
					{#if selected?.status === 'RUNNING' || selected?.status === 'DONE' || selected?.status === 'CLOSED'}
						{#if liveStandings.length > 0}
							<button class="toggle-live-btn glass" on:click={toggleLiveStandings}>
								{showLiveStandings ? $t('tourneys_hide_standings') : $t('tourneys_show_standings')}
							</button>
						{/if}
					{/if}

					{#if currentUser?.is_admin}
						<div class="admin-bar glass">
							<span class="admin-bar-label"><Icon name="gear" size={14} /> {$t("nav_administration")}</span>
							<div class="admin-bar-actions">
								{#if selected.status === 'OPEN'}
									<button class="admin-btn start" on:click={startTournament} disabled={participants.length < 2}>
										<Icon name="play" size={14} /> {$t('tourneys_btn_start')}{#if participants.length < 2} {$t('tourneys_start_min')}{/if}
									</button>
								{/if}
								{#if selected?.status === 'RUNNING'}
									<button class="admin-btn stop" on:click={stopTournament}><Icon name="stop" size={14} /> {$t('tourneys_btn_finish')}</button>
								{/if}
								{#if selected.status === 'DONE'}
									{#if confirmingClose}
										<span class="inline-confirm">
											<span class="inline-confirm-label">{$t("tourneys_confirm_close")}</span>
											<button class="admin-btn confirm-yes" on:click={closeTournament}><Icon name="check" size={15} /> {$t("tourneys_confirm_yes")}</button>
											<button class="admin-btn confirm-no" on:click={() => confirmingClose = false}><Icon name="x" size={16} /></button>
										</span>
									{:else}
										<button class="admin-btn close" on:click={() => confirmingClose = true}><Icon name="flag" size={15} /> {$t("tourneys_btn_close")}</button>
									{/if}
								{/if}
								{#if selected.status === 'CLOSED'}
									{#if confirmingReopen}
										<span class="inline-confirm">
											<span class="inline-confirm-label">{$t("tourneys_confirm_reopen")}</span>
											<button class="admin-btn confirm-yes" on:click={reopenTournament}><Icon name="check" size={15} /> {$t("tourneys_confirm_yes")}</button>
											<button class="admin-btn confirm-no" on:click={() => confirmingReopen = false}><Icon name="x" size={16} /></button>
										</span>
									{:else}
										<button class="admin-btn reset" on:click={() => confirmingReopen = true}><Icon name="unlock" size={15} /> {$t("tourneys_btn_reopen")}</button>
									{/if}
								{/if}
								{#if selected.status !== 'OPEN' && selected.status !== 'CLOSED'}
									<button class="admin-btn reset" on:click={resetTournament}><Icon name="refresh" size={15} /> {$t("tourneys_btn_reset")}</button>
								{/if}
								{#if selected.status !== 'CLOSED'}
									<button class="admin-btn edit" on:click={openEdit}><Icon name="pencil" size={15} /> {$t("tourneys_btn_edit")}</button>
								{/if}
							</div>
						</div>
					{/if}
				</div>

				{#if showDetails || (!isMobile && selected.status === 'OPEN')}
					<div class="info-row">
						<div class="info-card glass"><span class="info-label">{$t("admin_tourneys_wizard_format_lbl")}</span><span class="info-value">{bracketLabel(selected.config?.bracket_type, selected.config)}</span></div>
						<div class="info-card glass"><span class="info-label">{$t("admin_tourneys_wizard_mode_lbl")}</span><span class="info-value">{selected.config?.use_teams ? `${$t('admin_tourneys_wizard_mode_teams')} (x${selected.config?.team_size || 2})` : 'Solo'}</span></div>
						<div class="info-card glass"><span class="info-label">{$t("admin_tourneys_wizard_points_lbl")}</span><span class="info-value accent" style="font-size:0.85rem">{$t('tourneys_pts_first')} {selected.config?.pts_winner ?? 1.5} · {$t('tourneys_pts_second')} {selected.config?.pts_second ?? 1.3} · {$t('tourneys_pts_third')} {selected.config?.pts_third ?? 1.0}<br>{$t('tourneys_pts_participation_short')} {selected.config?.pts_participation ?? 1.0}{$t('tourneys_per_match')} · {$t('tourneys_pts_score_bonus_short')} {selected.config?.pts_per_match ?? 0.5}</span></div>
						<div class="info-card glass"><span class="info-label">{$t("dash_stat_players")}</span><span class="info-value">{participants.length}</span></div>
						{#if selected.config?.lower_score_is_better}
							<div class="info-card glass"><span class="info-label">{$t("admin_tourneys_wizard_format_lbl")}</span><span class="info-value" style="color:#f59e0b">{$t("tourneys_opt_reverse")}</span></div>
						{/if}
					</div>

					<!-- Results Summary (after closing) -->
					{#if selected.status === 'CLOSED'}
						<TournamentStandings
							mode="results"
							{selected}
							results={selected.results}
							{teams}
							{useTeams}
						/>
					{/if}

					<!-- Participants Pool & Available Players -->
					<TournamentParticipants
						{selected}
						{participants}
						{poolPlayers}
						{groupedPoolPlayers}
						{unregisteredUsers}
						{useTeams}
						{isAdmin}
						on:joinAll={joinAllPlayers}
						on:leaveAll={leaveAllPlayers}
						on:removePlayer={(e) => forceRemovePlayer(e.detail.userId)}
						on:addPlayer={(e) => forceAddPlayer(e.detail.userId)}
					/>

					<!-- Team Composition (in team mode) -->
					{#if useTeams}
						<div id="teams-section">
							<TournamentTeams
								{selected}
								{teams}
								{unassignedPlayers}
								{groupedUnassigned}
								{currentUser}
								{isAdmin}
								{isParticipant}
								{myTeam}
								{liveStandings}
								{getPlayerPts}
								on:createTeam={(e) => createTeam(e.detail.name)}
								on:deleteTeam={(e) => deleteTeam(e.detail.teamId)}
								on:addMember={(e) => addMemberToTeam(e.detail.teamId, e.detail.userId)}
								on:removeMember={(e) => removeMemberFromTeam(e.detail.teamId, e.detail.userId)}
								on:toggleTeamLock={(e) => toggleTeamLock(e.detail.teamId, e.detail.isLocked)}
								on:setTeamCaptain={(e) => setTeamCaptain(e.detail.teamId, e.detail.captainId)}
								on:randomizeTeams={randomizeTeams}
							/>
						</div>
					{/if}
				{/if}

				{/if}

				<!-- Split Layout: Bracket & Live Standings -->
				<div class="tournament-split-layout" class:split-active={showLiveStandings && liveStandings.length > 0} class:split-fill={selected?.status !== 'OPEN' && !showDetails}>
					{#if isTwoPhase && hasBracket}
						{#if stage === 'knockout'}
							<div class="phase-tabs" role="tablist">
								<button role="tab" class="seg-tab" class:active={phaseTab === 'knockout'} aria-selected={phaseTab === 'knockout'} on:click={() => phaseTab = 'knockout'}><Icon name="trophy" size={14} /> {$t('groups_tab_knockout')}</button>
								<button role="tab" class="seg-tab" class:active={phaseTab === 'groups'} aria-selected={phaseTab === 'groups'} on:click={() => phaseTab = 'groups'}><Icon name="layers" size={14} /> {$t('groups_tab_groups')}</button>
							</div>
						{/if}
						<GroupStagePanel {selected} {isAdmin} on:loaded={(e) => groupData = e.detail} on:changed={async (e) => {
							if (e.detail?.error) toast(e.detail.error, 'error'); else if (e.detail?.toast) toast(e.detail.toast, 'success');
							tournaments = await api.get('/tournaments');
							await selectTournament(selectedId);
						}} />
					{/if}
					<TournamentBracket
						bind:this={bracketRef}
						{selected}
						{hasBracket}
						bracketType={viewBracketType}
						{bracketRounds}
						{wbRounds}
						{lbRounds}
						{lbRoundsRaw}
						{rrGroups}
						{groupTables}
						groupAdvancers={groupData?.advancers || 0}
						{nameMap}
						{seatMap}
						{currentUser}
						{isAdmin}
						{isParticipant}
						{useTeams}
						{myTeamSlotId}
						{lowerIsBetter}
						{booleanMode}
						on:submitScore={(e) => doSubmitScore(e.detail.match, e.detail.score)}
						on:advanceFFA={(e) => advanceFFA(e.detail.keepCount, e.detail.perMatch)}
						on:finishFFA={finishFFA}
						on:rollbackFFA={rollbackFFA}
					/>

					{#if showLiveStandings && liveStandings.length > 0}
						<TournamentStandings
							mode="live"
							{selected}
							{displayStandings}
							{teams}
							{useTeams}
						/>
					{/if}
				</div>
			</div>
		{:else if loadingTournaments}
			<div class="detail-empty">
				<div class="t-spinner"></div>
				<p class="text-dim">{$t('common_loading')}</p>
			</div>
		{:else}
			<div class="detail-empty">
				<span class="empty-lg-icon"><Icon name="trophy" size={16} /></span>
				<h2>{$t('tourneys_select_tournament')}</h2>
				<p class="text-dim">{$t('tourneys_choose_from_list')}</p>
			</div>
		{/if}
	</main>
</div>


<!-- Mobile Info & Rules Modal -->
{#if showMobileInfoModal && selected}
	<div class="edit-overlay" use:portal on:click={() => showMobileInfoModal = false}>
		<div class="edit-modal glass animate-in" on:click|stopPropagation>
			<header class="edit-modal-header">
				<h3><Icon name="info" size={16} /> {selected.name}</h3>
				<button class="close-btn" on:click={() => showMobileInfoModal = false}><Icon name="x" size={16} /></button>
			</header>
			<div class="edit-modal-body">
				<div class="m-modal-section">
					<h4 style="font-size:0.8rem; font-weight:700; color:var(--accent); margin-bottom:0.4rem; text-transform:uppercase;">{$t("tourneys_tab_rules")}</h4>
					<p class="hero-rules-text" style="font-size:0.85rem; line-height:1.4; color:var(--text-main); margin-bottom:1rem;">{selected.config?.custom_rules || selectedGame?.rules || $t('tourneys_no_custom_rules')}</p>
				</div>
				<div class="m-modal-cards-grid" style="display:grid; grid-template-columns:1fr 1fr; gap:0.5rem;">
					<div class="info-card glass" style="padding:0.6rem; border-radius:8px;">
						<span class="info-label" style="font-size:0.7rem; color:var(--text-dim); display:block;">{$t("admin_tourneys_wizard_format_lbl")}</span>
						<span class="info-value" style="font-weight:700; font-size:0.85rem;">{bracketLabel(selected.config?.bracket_type, selected.config)}</span>
					</div>
					<div class="info-card glass" style="padding:0.6rem; border-radius:8px;">
						<span class="info-label" style="font-size:0.7rem; color:var(--text-dim); display:block;">{$t("admin_tourneys_wizard_mode_lbl")}</span>
						<span class="info-value" style="font-weight:700; font-size:0.85rem;">{selected.config?.use_teams ? `${$t('admin_tourneys_wizard_mode_teams')} (x${selected.config?.team_size || 2})` : 'Solo'}</span>
					</div>
					<div class="info-card glass" style="padding:0.6rem; border-radius:8px;">
						<span class="info-label" style="font-size:0.7rem; color:var(--text-dim); display:block;">{$t("dash_stat_players")}</span>
						<span class="info-value" style="font-weight:700; font-size:0.85rem;">{participants.length}</span>
					</div>
					<div class="info-card glass" style="padding:0.6rem; border-radius:8px; grid-column:span 2;">
						<span class="info-label" style="font-size:0.7rem; color:var(--text-dim); display:block;">{$t("admin_tourneys_wizard_points_lbl")}</span>
						<span class="info-value accent" style="font-size:0.8rem; font-weight:700;">{$t('tourneys_pts_first')} {selected.config?.pts_winner ?? 1.5} · {$t('tourneys_pts_second')} {selected.config?.pts_second ?? 1.3} · {$t('tourneys_pts_third')} {selected.config?.pts_third ?? 1.0}<br>{$t('tourneys_pts_participation_short')} {selected.config?.pts_participation ?? 1.0}{$t('tourneys_per_match')} · {$t('tourneys_pts_score_bonus_short')} {selected.config?.pts_per_match ?? 0.5}</span>
					</div>
				</div>
			</div>
		</div>
	</div>
{/if}

<!-- Mobile Players & Teams Modal -->
{#if showMobilePlayersModal && selected}
	<div class="edit-overlay" use:portal on:click={() => showMobilePlayersModal = false}>
		<div class="edit-modal glass animate-in" on:click|stopPropagation style="max-height: 85vh; display: flex; flex-direction: column;">
			<header class="edit-modal-header">
				<h3><Icon name="users" size={16} /> {$t('dash_stat_players')} ({participants.length})</h3>
				<button class="close-btn" on:click={() => showMobilePlayersModal = false}><Icon name="x" size={16} /></button>
			</header>
			<div class="edit-modal-body" style="overflow-y: auto; flex: 1; padding: 0.75rem;">
				<TournamentParticipants
					{selected}
					{participants}
					{poolPlayers}
					{groupedPoolPlayers}
					{unregisteredUsers}
					{useTeams}
					{isAdmin}
					on:joinAll={joinAllPlayers}
					on:leaveAll={leaveAllPlayers}
					on:removePlayer={(e) => forceRemovePlayer(e.detail.userId)}
					on:addPlayer={(e) => forceAddPlayer(e.detail.userId)}
				/>
				{#if useTeams}
					<div style="margin-top: 1rem;">
						<TournamentTeams
							{selected}
							{teams}
							{unassignedPlayers}
							{groupedUnassigned}
							{currentUser}
							{isAdmin}
							{isParticipant}
							{myTeam}
							{liveStandings}
							{getPlayerPts}
							on:createTeam={(e) => createTeam(e.detail.name)}
							on:deleteTeam={(e) => deleteTeam(e.detail.teamId)}
							on:addMember={(e) => addMemberToTeam(e.detail.teamId, e.detail.userId)}
							on:removeMember={(e) => removeMemberFromTeam(e.detail.teamId, e.detail.userId)}
							on:toggleTeamLock={(e) => toggleTeamLock(e.detail.teamId, e.detail.isLocked)}
							on:setTeamCaptain={(e) => setTeamCaptain(e.detail.teamId, e.detail.captainId)}
							on:randomizeTeams={randomizeTeams}
						/>
					</div>
				{/if}
			</div>
		</div>
	</div>
{/if}

<!-- Mobile Standings Modal -->
{#if showMobileStandingsModal && selected}
	<div class="edit-overlay" use:portal on:click={() => showMobileStandingsModal = false}>
		<div class="edit-modal glass animate-in" on:click|stopPropagation style="max-height: 85vh; display: flex; flex-direction: column;">
			<header class="edit-modal-header">
				<h3><Icon name="trophy" size={16} /> {$t('tourneys_show_standings')}</h3>
				<button class="close-btn" on:click={() => showMobileStandingsModal = false}><Icon name="x" size={16} /></button>
			</header>
			<div class="edit-modal-body" style="overflow-y: auto; flex: 1; padding: 0.75rem;">
				<TournamentStandings
					mode={selected.status === 'CLOSED' ? 'results' : 'live'}
					{selected}
					results={selected.results}
					{displayStandings}
					{teams}
					{useTeams}
				/>
			</div>
		</div>
	</div>
{/if}

<!-- Mobile Admin Modal -->
{#if showMobileAdminModal && selected && currentUser?.is_admin}
	<div class="edit-overlay" use:portal on:click={() => showMobileAdminModal = false}>
		<div class="edit-modal glass animate-in" on:click|stopPropagation>
			<header class="edit-modal-header">
				<h3><Icon name="gear" size={16} /> {$t('nav_administration')}</h3>
				<button class="close-btn" on:click={() => showMobileAdminModal = false}><Icon name="x" size={16} /></button>
			</header>
			<div class="edit-modal-body" style="display:flex; flex-direction:column; gap:0.6rem; padding:1rem;">
				{#if selected.status === 'OPEN'}
					<button class="admin-btn start full-width" on:click={() => { showMobileAdminModal = false; startTournament(); }} disabled={participants.length < 2} style="padding:0.7rem; font-size:0.85rem;">
						<Icon name="play" size={14} /> {$t('tourneys_btn_start')}{#if participants.length < 2} {$t('tourneys_start_min')}{/if}
					</button>
				{/if}
				{#if selected?.status === 'RUNNING'}
					<button class="admin-btn stop full-width" on:click={() => { showMobileAdminModal = false; stopTournament(); }} style="padding:0.7rem; font-size:0.85rem;">
						<Icon name="stop" size={14} /> {$t('tourneys_btn_finish')}
					</button>
				{/if}
				{#if selected.status === 'DONE'}
					<button class="admin-btn close full-width" on:click={() => { showMobileAdminModal = false; closeTournament(); }} style="padding:0.7rem; font-size:0.85rem;">
						<Icon name="flag" size={15} /> {$t("tourneys_btn_close")}
					</button>
				{/if}
				{#if selected.status === 'CLOSED'}
					<button class="admin-btn reset full-width" on:click={() => { showMobileAdminModal = false; reopenTournament(); }} style="padding:0.7rem; font-size:0.85rem;">
						<Icon name="unlock" size={15} /> {$t("tourneys_btn_reopen")}
					</button>
				{/if}
				{#if selected.status !== 'OPEN' && selected.status !== 'CLOSED'}
					<button class="admin-btn reset full-width" on:click={() => { showMobileAdminModal = false; resetTournament(); }} style="padding:0.7rem; font-size:0.85rem;">
						<Icon name="refresh" size={15} /> {$t("tourneys_btn_reset")}
					</button>
				{/if}
				{#if selected.status !== 'CLOSED'}
					<button class="admin-btn edit full-width" on:click={() => { showMobileAdminModal = false; openEdit(); }} style="padding:0.7rem; font-size:0.85rem;">
						<Icon name="pencil" size={15} /> {$t("tourneys_btn_edit")}
					</button>
				{/if}
				<button class="admin-btn edit full-width" on:click={() => { showMobileAdminModal = false; openCreateTournamentModal(); }} style="padding:0.7rem; font-size:0.85rem; border-color:var(--accent);">
					<Icon name="plus" size={15} /> {$t("tourneys_add_btn")}
				</button>
			</div>
		</div>
	</div>
{/if}

<!-- Edit Modal -->
<EditTournamentModal
	tournament={selected}
	{games}
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
				<h3><Icon name="trophy" size={15} /> {$t('tourneys_add_btn')}</h3>
				<button class="close-btn" on:click={() => showCreateModal = false}><Icon name="x" size={16} /></button>
			</header>
			<div class="edit-modal-body">
				<CreateTournamentWizard 
					{games} 
					onSuccess={async (newT) => {
						toast($t('tourneys_toast_updated'), 'success');
						showCreateModal = false;
						tournaments = await api.get('/tournaments');
						await selectTournament(newT.id);
					}}
					onGameCreated={async () => {
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
			<span><Icon name={t.type === 'success' ? 'check-circle' : t.type === 'error' ? 'x-circle' : 'info'} size={16} /></span>
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
	.sidebar-header h2 { font-size: var(--fs-section); margin: 0; }
	.t-count { font-size: 0.65rem; background: var(--accent-soft); color: var(--accent); padding: 0.1rem 0.4rem; border-radius: 10px; font-weight: 800; border: 1px solid rgba(59,130,246,0.15); }
	.t-list { flex-grow: 1; overflow-y: auto; display: flex; flex-direction: column; gap: 0.4rem; padding: 0.5rem; }
	.t-item { position: relative; display: flex; align-items: flex-end; min-height: 84px; padding: 0; background-size: cover; background-position: center; background-color: rgba(0,0,0,0.4); border: 1px solid #1e293b; border-radius: 10px; cursor: pointer; transition: all 0.2s; text-align: left; color: white; width: 100%; overflow: hidden; }
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
	.t-item-overlay { position: absolute; inset: 0; z-index: 2; display: flex; align-items: flex-end; justify-content: space-between; padding: 0.6rem 0.75rem; background: linear-gradient(to top, rgba(10,15,30,0.94) 0%, rgba(10,15,30,0.8) 50%, rgba(10,15,30,0.35) 100%); }
	.t-item-info { flex-grow: 1; min-width: 0; display: flex; flex-direction: column; gap: 0.1rem; }
	.t-item-name { font-size: 0.95rem; font-weight: 700; line-height: 1.2; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; text-shadow: 0 1px 4px rgba(0,0,0,0.6); }
	.t-item-meta { font-size: 0.75rem; color: rgba(255,255,255,0.8); text-shadow: 0 1px 2px rgba(0,0,0,0.5); }
	.t-item.active { outline: 2px solid var(--accent); outline-offset: -2px; }
	.t-status-badge { flex-shrink: 0; padding: 0.15rem 0.45rem; border-radius: 6px; font-size: 0.7rem; font-weight: 700; letter-spacing: 0.02em; white-space: nowrap; line-height: 1.3; text-shadow: 0 1px 2px rgba(0,0,0,0.4); }
	.t-status-badge.open { background: #166534; color: #dcfce7; border: 1px solid #22c55e; }
	.t-status-badge.running { background: #1d4ed8; color: #ffffff; border: 1px solid #3b82f6; }
	.t-status-badge.done { background: #334155; color: #e2e8f0; border: 1px solid #64748b; }
	.t-status-badge.closed { background: #065f46; color: #d1fae5; border: 1px solid #10b981; }
	.t-empty-sidebar { padding: 2rem 1rem; text-align: center; }

	/* === DETAIL === */
	.t-detail { flex-grow: 1; display: flex; flex-direction: column; overflow-y: auto; border-radius: var(--radius-lg); margin-left: -3rem; padding-left: 3rem; }
	.phase-tabs { display: inline-flex; gap: 2px; padding: 3px; margin-bottom: 0.9rem; background: var(--surface-sunken); border: 1px solid var(--glass-border); border-radius: var(--radius-md); }
	.seg-tab { display: inline-flex; align-items: center; gap: 0.4rem; padding: 0.4rem 0.9rem; border: 1px solid transparent; border-radius: calc(var(--radius-md) - 2px); background: transparent; color: var(--text-dim); font-size: 0.8125rem; font-weight: 600; cursor: pointer; }
	.seg-tab:hover { color: var(--text-main); }
	.seg-tab.active { background: var(--accent-soft); border-color: var(--accent); color: var(--accent); }
	.detail-hero { height: 150px; background-size: cover; background-position: center; background-color: var(--bg-secondary); border-radius: var(--radius-lg) var(--radius-lg) 0 0; position: relative; flex-shrink: 0; }
	.hero-overlay { position: absolute; inset: 0; display: flex; align-items: flex-end; justify-content: space-between; background: linear-gradient(to top, rgba(15,23,42,0.95) 0%, rgba(15,23,42,0.7) 55%, rgba(15,23,42,0.2)); padding: 1.2rem 1.5rem; border-radius: inherit; }
	.hero-content { display: flex; flex-direction: column; gap: 0.2rem; }
	.hero-content h1 { font-size: var(--fs-page); margin: 0; color: white; text-shadow: 0 2px 8px rgba(0,0,0,0.5); }

	.hero-checkered { position: absolute; top: 0; right: 0; width: 75%; height: 100%; z-index: 1; pointer-events: none;
		background: repeating-conic-gradient(rgba(255,255,255,0.85) 0% 25%, rgba(20,20,20,0.85) 0% 50%) 0 0 / 22px 22px;
		mask-image: linear-gradient(to left, rgba(0,0,0,0.7) 0%, rgba(0,0,0,0.35) 50%, transparent 100%), linear-gradient(to top, transparent 0%, rgba(0,0,0,0.5) 30%, rgba(0,0,0,0.5) 70%, transparent 100%);
		-webkit-mask-image: linear-gradient(to left, rgba(0,0,0,0.7) 0%, rgba(0,0,0,0.35) 50%, transparent 100%), linear-gradient(to top, transparent 0%, rgba(0,0,0,0.5) 30%, rgba(0,0,0,0.5) 70%, transparent 100%);
		mask-composite: intersect; -webkit-mask-composite: source-in;
		border-radius: 0 var(--radius-lg) 0 0;
		animation: checkered-reveal 0.6s ease-out;
	}
	@keyframes checkered-reveal { from { opacity: 0; transform: translateX(20px); } to { opacity: 1; transform: translateX(0); } }
	.hero-game { color: rgba(255,255,255,0.85); font-weight: 600; font-size: 0.85rem; text-shadow: 0 1px 4px rgba(0,0,0,0.5); }
	.hero-rules {
		position: absolute; right: 1.5rem; top: 1rem; max-width: 280px; max-height: 140px;
		overflow-y: auto; padding: 0.6rem 0.8rem; border-radius: 10px;
		background: rgba(15,23,42,0.95);
		border: 1px solid rgba(255,255,255,0.08);
		z-index: 3;
	}
	.hero-rules-label { font-size: 0.55rem; font-weight: 700; text-transform: uppercase; letter-spacing: 0.05em; color: #60a5fa; margin-bottom: 0.25rem; display: block; }
	.hero-rules-text { font-size: 0.7rem; color: rgba(255,255,255,0.75); margin: 0; line-height: 1.45; white-space: pre-line; word-break: break-word; }
	.hero-rules::-webkit-scrollbar { width: 3px; }
	.hero-rules::-webkit-scrollbar-thumb { background: rgba(96,165,250,0.3); border-radius: 3px; }
	.hero-join { align-self: flex-end; }
	.hero-joined { align-self: flex-end; padding: 0.5rem 1.2rem; background: rgba(16,185,129,0.15); border: 1px solid rgba(16,185,129,0.3); color: #10b981; border-radius: 10px; font-weight: 700; font-size: 0.85rem; text-shadow: 0 1px 4px rgba(0,0,0,0.3); }
	.status-pill { display: inline-flex; align-items: center; gap: 0.3rem; align-self: flex-start; padding: 0.2rem 0.6rem; border-radius: 20px; font-size: 0.72rem; font-weight: 700; margin-bottom: 0.2rem; text-shadow: 0 1px 3px rgba(0,0,0,0.3); }
	.status-pill.open { background: #166534; color: #dcfce7; border: 1px solid #22c55e; }
	.status-pill.running { background: #1d4ed8; color: #ffffff; border: 1px solid #3b82f6; }
	.status-pill.done { background: #334155; color: #e2e8f0; border: 1px solid #64748b; }
	.status-pill.closed { background: #065f46; color: #d1fae5; border: 1px solid #10b981; }

	.detail-body { padding: 1.2rem 1.5rem; display: flex; flex-direction: column; gap: 1.2rem; flex-grow: 1; min-height: 0; }
	.info-row { display: grid; grid-template-columns: repeat(auto-fit, minmax(120px, 1fr)); gap: 0.8rem; }
	.info-card { padding: 0.8rem; display: flex; flex-direction: column; gap: 0.2rem; border-radius: 10px; }
	.info-label { font-size: 0.6rem; font-weight: 700; text-transform: uppercase; letter-spacing: 0.06em; color: var(--text-muted); }
	.info-value { font-size: 0.9rem; font-weight: 700; }
	.info-value.accent { color: var(--accent); }

	/* Controls row */
	.controls-row { display: flex; flex-wrap: wrap; align-items: stretch; gap: 0.75rem; margin-bottom: 0.5rem; width: 100%; }
	.controls-row .admin-bar { flex-grow: 1; margin-bottom: 0; padding: 0.4rem 1rem; }
	.controls-row .toggle-details-btn, .controls-row .toggle-live-btn { margin-bottom: 0; flex-shrink: 0; align-self: stretch; border-radius: 10px; }
	.detail-body.collapsed-layout { padding-bottom: 0; }
	.t-detail.collapsed-layout { overflow-y: hidden; }
	.toggle-details-btn, .toggle-live-btn { display: inline-flex; align-items: center; justify-content: center; gap: 0.5rem; padding: 0.5rem 1rem; font-size: 0.75rem; font-weight: 700; color: var(--accent); background: var(--accent-soft); border: 1px solid var(--glass-border); border-radius: 8px; cursor: pointer; transition: all 0.2s ease-in-out; align-self: flex-start; margin-bottom: 0.5rem; }
	.toggle-details-btn:hover, .toggle-live-btn:hover { background: var(--accent); color: white; box-shadow: 0 0 10px var(--accent-glow); transform: translateY(-1px); }
	.toggle-details-btn:active, .toggle-live-btn:active { transform: translateY(0); }

	/* Admin bar */
	.admin-bar { display: flex; justify-content: space-between; align-items: center; padding: 0.7rem 1rem; border-radius: 10px; border: 1px dashed rgba(59,130,246,0.2); background: rgba(59,130,246,0.04); }
	.admin-bar-label { font-size: 0.75rem; font-weight: 700; color: var(--text-dim); }
	.admin-bar-actions { display: flex; flex-wrap: wrap; gap: 0.4rem; }
	.admin-btn { display: inline-flex; align-items: center; gap: 0.4rem; padding: 0.4rem 0.8rem; font-size: 0.8125rem; font-weight: 700; border-radius: 8px; border: 1px solid var(--glass-border); cursor: pointer; transition: all 0.2s; background: var(--surface-raised); color: var(--text-dim); }
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
	.admin-btn.edit { border-color: rgba(59,130,246,0.3); color: var(--accent); }
	.admin-btn.edit:hover { background: rgba(59,130,246,0.15); }
	.inline-confirm { display: inline-flex; align-items: center; gap: 0.4rem; animation: fadeIn 0.15s ease-out; }
	.inline-confirm-label { font-size: 0.65rem; font-weight: 700; color: var(--text-main); white-space: nowrap; }
	.admin-btn.confirm-yes { border-color: rgba(34,197,94,0.4); color: var(--success); font-weight: 800; }
	.admin-btn.confirm-yes:hover { background: rgba(34,197,94,0.2); }
	.admin-btn.confirm-no { border-color: rgba(239,68,68,0.3); color: var(--danger); padding: 0.2rem 0.5rem; min-width: unset; }
	.admin-btn.confirm-no:hover { background: rgba(239,68,68,0.15); }
	@keyframes fadeIn { from { opacity: 0; transform: translateX(-5px); } to { opacity: 1; transform: translateX(0); } }

	/* Tournament Split Layout */
	.tournament-split-layout { display: flex; flex-direction: column; gap: 1.5rem; width: 100%; flex-shrink: 0; }
	.tournament-split-layout.split-fill { flex-grow: 1; min-height: 0; flex-shrink: 1; height: 100%; }
	:global(.split-fill > .bracket-section) { flex-grow: 1; min-height: 0; height: 100%; }
	:global(.split-fill > .live-standings) { flex-grow: 1; min-height: 0; height: 100%; display: flex; flex-direction: column; }
	:global(.split-fill .ls-list) { flex-grow: 1; min-height: 0; overflow-y: auto; max-height: none; }
	:global(.split-fill .ffa-container) { max-height: none; flex-grow: 1; min-height: 0; }
	:global(.split-fill .bracket-viewport-wrapper) { flex-grow: 1; min-height: 0; height: 100%; }
	.tournament-split-layout.split-active { flex-direction: row; align-items: stretch; }
	:global(.split-active > .bracket-section) { flex: 1 1 0%; min-width: 0; }
	:global(.split-active > .live-standings) { flex: 1 1 0%; min-width: 300px; margin-top: 0; }

	/* Empty state */
	.detail-empty { flex-grow: 1; display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 0.5rem; text-align: center; }
	.empty-lg-icon { font-size: 3.5rem; opacity: 0.4; }
	.detail-empty h2 { margin: 0; }

	/* Create Modal */
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
	@keyframes modalFadeIn { from { opacity: 0; } to { opacity: 1; } }
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
	@keyframes modalSlideUp { from { transform: translateY(20px) scale(0.97); } to { transform: translateY(0) scale(1); } }
	.edit-modal-header {
		display: flex;
		justify-content: space-between;
		align-items: center;
		padding: 1.25rem 1.5rem;
		border-bottom: 1px solid var(--glass-border);
		background: var(--surface-sunken);
		flex-shrink: 0;
	}
	.edit-modal-header h3 { font-size: 1rem; font-weight: 800; margin: 0; color: var(--text-main); }
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

	/* Toasts */
	.toast-container { position: fixed; bottom: 1.5rem; right: 1.5rem; z-index: 10000; display: flex; flex-direction: column-reverse; gap: 0.75rem; pointer-events: none; }
	.toast { display: flex; align-items: center; gap: 0.75rem; padding: 0.8rem 1.4rem; border-radius: 12px; backdrop-filter: blur(16px); border: 1px solid var(--glass-border); box-shadow: 0 10px 30px rgba(0,0,0,0.4); font-size: 0.85rem; font-weight: 600; pointer-events: auto; min-width: 240px; }
	.toast.success { background: rgba(16, 185, 129, 0.15); border-color: rgba(16, 185, 129, 0.3); color: #10b981; }
	.toast.error { background: rgba(239, 68, 68, 0.15); border-color: rgba(239, 68, 68, 0.3); color: var(--danger); }
	.toast.info { background: rgba(59, 130, 246, 0.15); border-color: rgba(59, 130, 246, 0.3); color: var(--accent); }
	.toast-enter { animation: toastIn 0.4s cubic-bezier(0.16, 1, 0.3, 1) forwards; }
	.toast-leave { animation: toastOut 0.4s ease-in forwards; }
	@keyframes toastIn { from { opacity: 0; transform: translateX(80px); } to { opacity: 1; transform: translateX(0); } }
	@keyframes toastOut { from { opacity: 1; } to { opacity: 0; transform: translateX(80px); } }


	/* Mobile Tourney Drawer & Bar */
	.mobile-tourney-bar { display: none; }
	.mobile-tourney-drawer-overlay {
		position: fixed; inset: 0; background: rgba(0, 0, 0, 0.65);
		backdrop-filter: blur(4px); -webkit-backdrop-filter: blur(4px);
		z-index: 1000; display: flex; justify-content: flex-start;
	}
	.mobile-tourney-drawer {
		width: 82%; max-width: 320px; height: 100%;
		background: var(--surface-raised, #1e293b);
		border-right: 1px solid rgba(255, 255, 255, 0.08);
		padding: 0.75rem; display: flex; flex-direction: column; gap: 0.5rem;
		box-shadow: 4px 0 24px rgba(0,0,0,0.5);
		border-radius: 0 !important;
	}
	.drawer-header {
		display: flex; justify-content: space-between; align-items: center;
		padding-bottom: 0.5rem; border-bottom: 1px solid rgba(255, 255, 255, 0.08);
	}
	.drawer-title-row {
		display: flex; align-items: center; gap: 0.4rem;
	}
	.drawer-header h3 { font-size: 0.88rem; margin: 0; color: var(--text-main); font-weight: 700; }
	.drawer-close-btn {
		background: none; border: none; color: var(--text-dim); cursor: pointer; padding: 0.2rem;
	}
	.drawer-add-btn {
		background: var(--accent); color: white; border: none;
		border-radius: 3px !important; padding: 0.35rem 0.6rem;
		font-size: 0.75rem; font-weight: 700; cursor: pointer;
		display: flex; align-items: center; justify-content: center; gap: 0.3rem;
	}
	.drawer-tourneys-list {
		flex: 1; overflow-y: auto; display: flex; flex-direction: column; gap: 0.35rem;
	}
	.drawer-tourney-item {
		display: flex; align-items: center; justify-content: space-between;
		padding: 0.5rem 0.65rem; border-radius: 3px !important;
		background: rgba(255, 255, 255, 0.03); border: 1px solid rgba(255, 255, 255, 0.06);
		color: var(--text-dim); cursor: pointer; text-align: left; transition: all 0.15s;
		gap: 0.4rem;
	}
	.drawer-tourney-item:hover, .drawer-tourney-item.active {
		background: rgba(59, 130, 246, 0.15); border-color: rgba(59, 130, 246, 0.4);
		color: var(--text-main);
	}
	.drawer-tourney-item.active .drawer-item-name { color: var(--accent); }
	.drawer-item-thumb { flex-shrink: 0; width: 56px; height: 40px; border-radius: 6px; background-size: cover; background-position: center; background-color: var(--surface-sunken); }
	.drawer-item-info { display: flex; flex-direction: column; gap: 0.1rem; min-width: 0; flex: 1; }
	.drawer-item-name { font-size: 0.82rem; font-weight: 700; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
	.drawer-item-game { font-size: 0.68rem; color: var(--text-muted); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
	@media (max-width: 900px) {
		.tournaments-layout {
			flex-direction: column;
			height: auto;
			min-height: calc(100vh - 96px);
			gap: 0.35rem;
		}
		/* Hide the horizontal t-sidebar on mobile in favor of the burger menu and lateral drawer */
		.t-sidebar {
			display: none !important;
		}

		/* Mobile Selector Bar */
		.mobile-tourney-bar {
			display: flex;
			align-items: center;
			justify-content: space-between;
			gap: 0.4rem;
			height: 38px;
			padding: 0 0.5rem;
			border-radius: 3px !important;
			background: var(--glass-bg);
			border: 1px solid var(--glass-border);
			box-sizing: border-box;
			flex-shrink: 0;
			margin-bottom: 0.25rem;
		}
		.mobile-tourney-trigger {
			display: flex;
			align-items: center;
			gap: 0.4rem;
			background: none;
			border: none;
			color: var(--text-main);
			cursor: pointer;
			padding: 0;
			font-size: 0.82rem;
			font-weight: 700;
			min-width: 0;
			flex: 1;
		}
		.trigger-name {
			white-space: nowrap;
			overflow: hidden;
			text-overflow: ellipsis;
			max-width: 170px;
		}
		.mobile-add-btn {
			width: 28px;
			height: 28px;
			border-radius: 3px !important;
			background: var(--accent-soft);
			border: 1px solid var(--accent);
			color: var(--accent);
			display: flex;
			align-items: center;
			justify-content: center;
			cursor: pointer;
		}
		
		.t-detail {
			margin-left: 0;
			padding-left: 0;
			overflow-y: visible;
		}
		.t-detail.collapsed-layout {
			overflow-y: visible;
		}
		.detail-hero {
			height: auto;
			min-height: auto;
			border-radius: 3px !important;
		}
		.hero-overlay {
			position: static;
			padding: 0.4rem 0.6rem;
			flex-direction: column;
			align-items: flex-start;
			gap: 0.2rem;
		}
		.hero-content h1 {
			font-size: var(--fs-page);
			margin: 0.1rem 0;
		}
		.hero-game {
			font-size: 0.72rem;
		}
		.status-pill {
			font-size: 0.65rem;
			padding: 0.12rem 0.35rem;
			border-radius: 2px !important;
		}
		.btn-primary.hero-join, .hero-joined, .admin-btn {
			border-radius: 3px !important;
			white-space: nowrap !important;
		}
		.hero-rules {
			position: relative;
			right: auto;
			top: auto;
			max-width: none;
			margin: 0.25rem 0;
			padding: 0.35rem 0.5rem;
			font-size: 0.72rem;
			border-radius: 3px !important;
		}
		
		.detail-body {
			padding: 0.35rem;
			gap: 0.35rem;
		}
		.controls-row {
			display: flex;
			flex-wrap: wrap;
			gap: 0.35rem;
			margin-bottom: 0.25rem;
		}
		.toggle-details-btn, .toggle-live-btn {
			padding: 0.2rem 0.5rem;
			font-size: 0.72rem;
			height: 28px;
			border-radius: 3px !important;
			white-space: nowrap !important;
			display: inline-flex;
			align-items: center;
			gap: 0.3rem;
		}
		.admin-bar {
			flex-direction: column;
			align-items: flex-start;
			gap: 0.35rem;
			width: 100%;
			padding: 0.35rem 0.5rem;
			border-radius: 3px !important;
		}
		.admin-bar-label {
			font-size: 0.72rem;
		}
		.admin-bar-actions {
			flex-wrap: wrap;
			gap: 0.25rem;
		}
		.admin-btn {
			padding: 0.2rem 0.45rem;
			font-size: 0.68rem;
			height: 26px;
			border-radius: 3px !important;
			white-space: nowrap !important;
		}

		/* Flat, compact 2x2 metadata on mobile */
		.info-row {
			display: flex;
			flex-wrap: wrap;
			gap: 0.35rem;
		}
		.info-card {
			padding: 0.35rem 0.5rem;
			flex: 1 1 calc(50% - 0.35rem);
			min-width: 130px;
			border-radius: 3px !important;
			border: 1px solid rgba(255, 255, 255, 0.06);
		}
		.info-label {
			font-size: 0.6rem;
		}
		.info-value {
			font-size: 0.78rem;
			font-weight: 700;
		}
		
		.tournament-split-layout.split-active {
			flex-direction: column;
		}
		:global(.split-active > .live-standings) {
			min-width: 0;
			width: 100%;
		}
	}

	/* Mobile Subnav Chips */
	.mobile-subnav-chips {
		display: none;
	}
	.t-spinner {
		width: 32px;
		height: 32px;
		border: 3px solid rgba(255, 255, 255, 0.15);
		border-top-color: var(--accent);
		border-radius: 50%;
		animation: spin 0.8s linear infinite;
		margin: 0 auto 0.75rem auto;
	}
	@keyframes spin {
		to { transform: rotate(360deg); }
	}

	@media (max-width: 900px) {
		.mobile-subnav-chips {
			display: flex;
			align-items: center;
			gap: 0.4rem;
			padding: 0.45rem 0.75rem;
			overflow-x: auto;
			scrollbar-width: none;
			border-bottom: 1px solid var(--glass-border);
			background: rgba(15, 23, 42, 0.75);
			backdrop-filter: blur(8px);
			flex-shrink: 0;
			z-index: 10;
		}
		.mobile-subnav-chips::-webkit-scrollbar {
			display: none;
		}
		.m-chip {
			display: inline-flex;
			align-items: center;
			gap: 0.35rem;
			padding: 0.35rem 0.65rem;
			border-radius: 6px;
			background: var(--surface-raised);
			border: 1px solid var(--glass-border);
			color: var(--text-main);
			font-size: 0.75rem;
			font-weight: 600;
			white-space: nowrap;
			cursor: pointer;
			transition: all 0.15s ease;
			flex-shrink: 0;
		}
		.m-chip:active {
			transform: scale(0.96);
		}
		.m-chip.admin {
			border-color: rgba(168, 85, 247, 0.4);
			color: #c084fc;
		}
		.m-chip.join {
			background: var(--accent);
			color: #fff;
			border-color: var(--accent);
		}
		.m-chip.joined {
			background: rgba(34, 197, 94, 0.15);
			color: var(--success);
			border-color: rgba(34, 197, 94, 0.4);
		}

		/* Bracket fills exactly the room left under the selector and chips:
		   the page itself never scrolls, only the bracket inside it */
		:global(.content-area > .container:has(.tournaments-layout)) {
			display: flex;
			flex-direction: column;
			overflow: hidden !important;
		}
		.tournaments-layout {
			flex: 1 1 0;
			min-height: 0 !important;
			height: auto;
			overflow: hidden !important;
		}
		/* Live standings open in their own popup on phones, never inline */
		.tournament-split-layout :global(.live-standings) { display: none !important; }
		.t-detail {
			height: 100% !important;
			max-height: 100% !important;
			overflow: hidden !important;
			display: flex;
			flex-direction: column;
			padding: 0 !important;
		}
		.detail-body {
			flex: 1;
			min-height: 0;
			height: 100% !important;
			display: flex;
			flex-direction: column;
			overflow: hidden !important;
			padding: 0 !important;
		}
		.tournament-split-layout {
			flex: 1;
			min-height: 0;
			height: 100% !important;
			display: flex;
			flex-direction: column;
			overflow: hidden !important;
			gap: 0 !important;
		}
	}


	/* Touch targets on phones: action buttons, score boxes and remove buttons at least ~36-40px */
	@media (max-width: 900px) {
		.tournaments-layout :global(.admin-btn),
		.tournaments-layout :global(.btn-xs) {
			min-height: 40px;
			font-size: 0.8rem !important;
		}
		.tournaments-layout :global(.score-input) {
			min-height: 36px;
			width: 44px;
		}
		.tournaments-layout :global(.part-member-remove) {
			min-width: 36px;
			min-height: 36px;
			font-size: 0.85rem;
			opacity: 0.7;
		}
	}

	/* "Votre prochain match" card: the player's main question answered first, kept to one compact row */
	.my-match { padding: 0.6rem 1rem; margin-bottom: 0.75rem; border-color: var(--accent); display: flex; align-items: center; gap: 0.5rem 1.25rem; flex-wrap: wrap; }
	.mm-head { display: flex; flex-direction: column; gap: 0.1rem; min-width: 0; flex: 1 1 200px; }
	.mm-title { margin: 0; font-size: 0.8rem; color: var(--text-dim); font-weight: 600; }
	.mm-round { font-size: 0.8rem; color: var(--text-dim); }
	.mm-versus { display: flex; align-items: baseline; gap: 0.4rem; flex-wrap: wrap; }
	.mm-vs-label { color: var(--text-dim); font-size: 0.9rem; }
	.mm-opponent { font-family: var(--font-title); font-size: 1.15rem; font-weight: 700; color: var(--text-main); line-height: 1.2; }
	.mm-score { display: flex; align-items: center; gap: 0.5rem; flex-wrap: wrap; }
	.mm-field { display: flex; align-items: center; gap: 0.4rem; font-size: 0.8rem; color: var(--text-dim); }
	.mm-field span { max-width: 90px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
	.mm-field input { width: 52px !important; height: 38px; min-height: 0 !important; font-size: 1.05rem; font-weight: 700; text-align: center; border-radius: var(--radius-md); padding: 0; }
	.mm-dash { color: var(--text-dim); }
	.mm-submit { display: inline-flex; align-items: center; gap: 0.4rem; height: 38px; padding: 0 1rem; }
	.mm-submit:disabled { opacity: 0.5; cursor: not-allowed; transform: none; }
</style>
