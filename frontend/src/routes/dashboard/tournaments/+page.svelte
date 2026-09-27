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

	import TournamentParticipants from './components/TournamentParticipants.svelte';
	import TournamentTeams from './components/TournamentTeams.svelte';
	import TournamentStandings from './components/TournamentStandings.svelte';
	import TournamentBracket from './components/TournamentBracket.svelte';

	let tournaments = [];
	let games = [];
	let selectedId = null;
	let participants = [];
	let allUsers = [];
	let currentUser = null;
	let editingTournament = false;
	let editConfig = {};

	let showDetails = true;
	let showLiveStandings = false;
	let bracketRef = null;

	$: if (selectedId) {
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

		wsUnsub = wsMessageStore.subscribe(handleWsMessage);
	});

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
		try {
			const [tourneysRes, gamesRes, userRes, roomUsersRes] = await Promise.all([
				api.get('/tournaments'),
				api.get('/tournaments/games').catch(() => []),
				api.get('/me').catch(() => null),
				api.get('/room/users').catch(() => [])
			]);
			tournaments = tourneysRes;
			games = gamesRes;
			currentUser = userRes;
			allUsers = roomUsersRes;
		} catch (err) {
			console.error("Error loading all tournaments page data:", err);
		}
	}

	let confirmingLeave = false;

	async function selectTournament(id) {
		selectedId = id;
		localStorage.setItem('alanbix_selected_tournament', id);
		confirmingLeave = false;
		try {
			const [partsRes, teamsRes, standingsRes] = await Promise.all([
				api.get(`/tournaments/${id}/participants`).catch(() => []),
				api.get(`/tournaments/${id}/teams`).catch(() => []),
				api.get(`/tournaments/${id}/standings`).catch(() => ({ standings: [] }))
			]);
			participants = partsRes;
			teams = teamsRes;
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
			toast(`${res.added} joueur(s) inscrits !`, 'success');
			tournaments = await api.get('/tournaments');
			await selectTournament(selectedId);
		} catch (e) { toast(e.message || 'Erreur', 'error'); }
	}

	async function leaveAllPlayers() {
		try {
			const res = await api.post(`/tournaments/${selectedId}/leave-all`, {});
			toast(`${res.removed} joueur(s) désinscrits.`, 'success');
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

	async function doSubmitScore(match, score) {
		try {
			await api.put(`/tournaments/${selectedId}/score`, {
				match_s: match.id.s, match_r: match.id.r, match_m: match.id.m, score
			});
			tournaments = await api.get('/tournaments');
		} catch (e) { toast(e.message || 'Erreur score', 'error'); }
	}

	async function advanceFFA(keepCount) {
		try {
			await api.post(`/tournaments/${selectedId}/ffa-advance`, { keep_count: keepCount });
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
			toast($t('tourneys_toast_ffa_rolled_back') || 'Manche supprimée avec succès !', 'success');
			await loadAll();
			await selectTournament(selectedId);
		} catch (e) { toast(e.detail || e.message || 'Erreur', 'error'); }
	}

	function openEdit() {
		editConfig = {
			name: selected.name,
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

	function bracketLabel(format) {
		if (format === 'single_elim') return get(t)('admin_tourneys_wizard_format_single');
		if (format === 'double_elim') return get(t)('admin_tourneys_wizard_format_double');
		if (format === 'round_robin') return get(t)('admin_tourneys_wizard_format_championship');
		if (format === 'ffa') return 'Free For All';
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
			return { id: gId, rounds: rounds };
		});
	})();

	function getPlayerPts(userId, standings) {
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
	<main class="t-detail" class:collapsed-layout={selected?.status !== 'OPEN' && !showDetails}>
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
							{#if confirmingLeave}
								<span class="inline-confirm">
									<span class="inline-confirm-label">{$t("tourneys_confirm_leave")}</span>
									<button class="admin-btn confirm-yes" on:click={() => leaveTournament(selected.id)}>✓ {$t("tourneys_confirm_yes")}</button>
									<button class="admin-btn confirm-no" on:click={() => confirmingLeave = false}>✕</button>
								</span>
							{:else}
								<div class="hero-joined-wrapper" style="display: flex; gap: 0.6rem; align-items: center;">
									<span class="hero-joined">✅ {$t("tourneys_hero_joined")}</span>
									<button class="admin-btn stop btn-xs" on:click={() => confirmingLeave = true}>❌ {$t("tourneys_btn_leave")}</button>
								</div>
							{/if}
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
						<div class="info-card glass"><span class="info-label">{$t("admin_tourneys_wizard_points_lbl")}</span><span class="info-value accent" style="font-size:0.85rem">🥇{selected.config?.pts_winner ?? 1.5} 🥈{selected.config?.pts_second ?? 1.3} 🥉{selected.config?.pts_third ?? 1.0} 👤{selected.config?.pts_participation ?? 1.0}/m ⚡{selected.config?.pts_per_match ?? 0.5}</span></div>
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
							on:randomizeTeams={randomizeTeams}
						/>
					{/if}
				{/if}

				<!-- Split Layout: Bracket & Live Standings -->
				<div class="tournament-split-layout" class:split-active={showLiveStandings && liveStandings.length > 0} class:split-fill={selected?.status !== 'OPEN' && !showDetails}>
					<TournamentBracket
						bind:this={bracketRef}
						{selected}
						{hasBracket}
						{bracketType}
						{bracketRounds}
						{wbRounds}
						{lbRounds}
						{lbRoundsRaw}
						{rrGroups}
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
						on:advanceFFA={(e) => advanceFFA(e.detail.keepCount)}
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

	/* Controls row */
	.controls-row { display: flex; align-items: stretch; gap: 0.75rem; margin-bottom: 0.5rem; width: 100%; }
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
</style>
