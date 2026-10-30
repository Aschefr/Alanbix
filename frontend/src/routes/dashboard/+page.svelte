<script>
	import { resolveMediaUrl, mediaThumb } from '$lib/config';

	import { onMount, onDestroy } from 'svelte';

	import { api } from '$lib/api';

	import { wsMessageStore } from '$lib/ws';

	import { t } from '$lib/i18nStore';

	import PublicChat from '$lib/components/PublicChat.svelte';

	import Icon from '$lib/components/Icon.svelte';
	import { goto } from '$app/navigation';



	import DashboardLeaderboard from './components/DashboardLeaderboard.svelte';

	import DashboardFloorMap from './components/DashboardFloorMap.svelte';

	import DashboardBracketPreview from './components/DashboardBracketPreview.svelte';

	import DashboardPlayerModal from './components/DashboardPlayerModal.svelte';



	// Quick Score & Navigation State (Home Page UX)
	// Ready-to-play matches first, waiting ones (opponent unknown) after
	// Scores the player entered stay visible until they hide them (shared with the tournaments page)
	const HIDDEN_KEY = 'alanbix_hidden_results';
	function loadHiddenResults() {
		try { return JSON.parse(localStorage.getItem(HIDDEN_KEY) || '[]'); } catch (e) { return []; }
	}
	let hiddenResults = typeof localStorage !== 'undefined' ? loadHiddenResults() : [];
	function saveHidden() {
		try { localStorage.setItem(HIDDEN_KEY, JSON.stringify(hiddenResults.slice(-200))); } catch (e) {}
	}
	function hideResult(key) { hiddenResults = [...hiddenResults.filter(k => k !== key), key]; saveHidden(); }
	function showHiddenResults() { hiddenResults = []; saveHidden(); }
	$: myActiveMatches = myMatchesAll.filter(m => !m.completed);
	$: myResults = myMatchesAll.filter(m => m.completed && !hiddenResults.includes(m.match_key)).slice(-6).reverse();
	$: hiddenResultsCount = myMatchesAll.filter(m => m.completed && hiddenResults.includes(m.match_key)).length;
	$: myMatchesSorted = [...myActiveMatches].sort((x, y) => Number(y.is_ready) - Number(x.is_ready));
	let dashTab = 'tournaments';
	try { dashTab = localStorage.getItem('alanbix_dash_tab') || 'tournaments'; } catch (e) {}
	function setDashTab(tab) {
		dashTab = tab;
		try { localStorage.setItem('alanbix_dash_tab', tab); } catch (e) {}
	}
	let activeScoreMatchKey = null;
	let quickScores = {};
	let isSubmittingScore = false;
	let toasts = [];
	let toastId = 0;

	function toast(msg, type = 'info') {
		const id = ++toastId;
		toasts = [...toasts, { id, message: msg, type, leaving: false }];
		setTimeout(() => {
			toasts = toasts.map(t => t.id === id ? { ...t, leaving: true } : t);
			setTimeout(() => { toasts = toasts.filter(t => t.id !== id); }, 400);
		}, 3000);
	}

	function navigateToTournament(tournamentId) {
		if (tournamentId) {
			try { localStorage.setItem('alanbix_selected_tournament', String(tournamentId)); } catch (e) {}
			goto(`/dashboard/tournaments?select=${tournamentId}`);
		} else {
			goto('/dashboard/tournaments');
		}
	}

	function navigateToMap(seatId) {
		if (seatId) {
			goto(`/dashboard/map?highlight=${seatId}`);
		}
	}

	function navigateToChat(userId) {
		if (userId) {
			goto(`/dashboard/players?chat=${userId}`);
		}
	}

	function toggleScoreEntry(m) {
		if (activeScoreMatchKey === m.match_key) {
			activeScoreMatchKey = null;
			return;
		}
		activeScoreMatchKey = m.match_key;
		const currentScores = m.raw_match?.score || [];
		if (m.is_ffa) {
			quickScores[m.match_key] = { myScore: currentScores[m.my_slot] || 0, oppScore: 0 };
			quickScores = quickScores;
			return;
		}
		const myVal = m.my_slot === 0 ? (currentScores[0] ?? 0) : (currentScores[1] ?? 0);
		const oppVal = m.my_slot === 0 ? (currentScores[1] ?? 0) : (currentScores[0] ?? 0);
		quickScores[m.match_key] = {
			myScore: myVal || 0,
			oppScore: oppVal || 0
		};
		quickScores = quickScores;
	}

	function adjustQuickScore(matchKey, field, delta) {
		if (!quickScores[matchKey]) {
			quickScores[matchKey] = { myScore: 0, oppScore: 0 };
		}
		const cur = parseInt(quickScores[matchKey][field], 10) || 0;
		quickScores[matchKey][field] = Math.max(0, cur + delta);
		quickScores = quickScores;
	}

	async function submitQuickScore(m, outcome = null) {
		if (isSubmittingScore) return;
		isSubmittingScore = true;
		try {
			let scorePayload = [];
			if (m.is_ffa) {
				// Free-for-all: send only my own slot, the server keeps everybody else's score
				const entry = quickScores[m.match_key] || { myScore: 0 };
				scorePayload = (m.raw_match?.p || []).map(() => null);
				scorePayload[m.my_slot] = parseInt(entry.myScore, 10) || 0;
			} else if (m.boolean_mode) {
				if (outcome === 'win') {
					scorePayload = m.my_slot === 0 ? [1, 0] : [0, 1];
				} else if (outcome === 'loss') {
					scorePayload = m.my_slot === 0 ? [0, 1] : [1, 0];
				} else if (outcome === 'draw') {
					scorePayload = [1, 1];
				}
			} else {
				const entry = quickScores[m.match_key] || { myScore: 0, oppScore: 0 };
				const myVal = parseInt(entry.myScore, 10) || 0;
				const oppVal = parseInt(entry.oppScore, 10) || 0;
				scorePayload = m.my_slot === 0 ? [myVal, oppVal] : [oppVal, myVal];
			}

			await api.put(`/tournaments/${m.tournament_id}/score`, {
				match_s: m.match_id.s,
				match_r: m.match_id.r,
				match_m: m.match_id.m,
				score: scorePayload
			});

			toast($t('mobile_score_saved'), 'success');
			activeScoreMatchKey = null;
			scheduleRefreshAll();
		} catch (err) {
			toast(err.detail || err.message || $t('dash_score_submit_error'), 'error');
		} finally {
			isSubmittingScore = false;
		}
	}

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


	});



	async function refreshAll() {

		previousLeaderboard = [...(stats.leaderboard || [])];

		try {

			const [userRes, statsRes, tournamentsRes, layoutRes, roomUsersRes, gamesRes, teamLbRes] = await Promise.all([
				api.get('/me').catch(() => user || null),
				api.get('/dashboard/stats').catch(() => stats || { tournaments: 0, players: 0, leaderboard: [] }),
				api.get('/tournaments').then(list => (list || []).filter(t => !t.is_hidden)).catch(() => tournaments || []),
				api.get('/room/layout').catch(() => ({ layout: { seats: [], tables: [], furniture: [] } })),
				api.get('/room/users').catch(() => []),
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
	let mobilePodiumOpen = true;
	// Full ranking on mobile: the choice is kept between visits
	let mobileLbFull = false;
	try { mobileLbFull = localStorage.getItem('alanbix_mobile_lb_full') === '1'; } catch {}
	function toggleMobileLb() {
		mobileLbFull = !mobileLbFull;
		try { localStorage.setItem('alanbix_mobile_lb_full', mobileLbFull ? '1' : '0'); } catch {}
	}
	$: mobileTourneysSummary = (() => {
		const active = (tournaments || []).filter(t => t.status === 'RUNNING' || t.status === 'OPEN');
		return (active.length > 0 ? active : (tournaments || [])).slice(0, 4);
	})();



	$: myMatchesAll = (() => {

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

				const s0 = score[0] ?? null, s1 = score[1] ?? null;
				const isCompleted = p.length > 2 ? (score.length > 0 && score.every(s => s !== null && s > 0)) : (s0 !== null && s1 !== null && (s0 !== 0 || s1 !== 0) && (s0 !== s1 || config.allow_draws));

				// a finished match stays listed (as a result line) unless it was a walkover
				if (isCompleted && p.includes(0)) continue;



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

						oppName = oppUser ? oppUser.username : `${tFunc('role_player')} #${oppPid}`;

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

						return u ? u.username : `${tFunc('role_player')} #${pid}`;

					});

					oppName = `${tFunc('tourneys_format_ffa')} · ${otherPids.length + 1} ${tFunc('dash_stat_players').toLowerCase()}`;

					oppPid = otherPids.find(pid => pid > 0) || null;

					oppUser = oppPid ? (allUsers || []).find(u => u.id === oppPid) : null;

					oppSeat = oppUser?.seat_id || null;

				}



				const gameObj = (games || []).find(g => g.id === tourney.game_id);

				const gameName = gameObj?.name || tourney.game || 'Tournoi';



				let roundLabel = 'Match';

				if (m.id?.s === 2) {

					roundLabel = `Loser Bracket · Tour ${m.id.r || '?'}`;

				} else if (m.id?.s >= 100) {

					roundLabel = `${tFunc('spec_group_num', { group: String.fromCharCode(64 + m.id.s - 100) })} · Tour ${m.id.r || '?'}`;

				} else if (m.id?.s === 3) {

					roundLabel = `Grande Finale`;

				} else if (m.id?.r) {

					roundLabel = `Tour ${m.id.r}`;

				}



				list.push({
					tournament_id: tourney.id,
					tournament_name: tourney.name,
					game_name: gameName,
					game_image: mediaThumb(gameObj?.image_url, 96),
					round_label: roundLabel,
					match_id: m.id,
					raw_match: m,
					is_ready: isReady,
					my_slot: mySlot,
					is_ffa: p.length > 2,
					completed: isCompleted,
					my_score: score[mySlot] ?? null,
					opp_score: p.length === 2 ? (score[1 - mySlot] ?? null) : null,
					outcome: p.length === 2 && isCompleted
						? (score[mySlot] === score[1 - mySlot] ? 'draw' : ((config.lower_score_is_better ? score[mySlot] < score[1 - mySlot] : score[mySlot] > score[1 - mySlot]) ? 'win' : 'loss'))
						: null,
					my_name: user?.username || 'Vous',
					opponent_name: oppName,
					opponent_id: oppPid > 0 ? oppPid : null,
					opponent_seat: oppSeat,
					boolean_mode: Boolean(config.boolean_mode),
					allow_draws: Boolean(config.allow_draws),
					lower_is_better: Boolean(config.lower_score_is_better),
					status_label: isReady ? tFunc('mobile_match_ready') : tFunc('mobile_match_waiting'),
					match_key: `${tourney.id}_${m.id?.s}_${m.id?.r}_${m.id?.m}`
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

				<span class="tab-txt"><Icon name="swords" size={14} /> {$t('mobile_tab_my_matches')}</span>

				{#if myActiveMatches.length > 0}

					<span class="mobile-badge-count">{myActiveMatches.length}</span>

				{/if}

			</button>

			<button

				class="mobile-dash-tab"

				class:active={mobileActiveTab === 'chat'}

				on:click={() => mobileActiveTab = 'chat'}

			>

				<span class="tab-txt"><Icon name="globe" size={14} /> {$t('mobile_tab_public_chat')}</span>

			</button>

		</div>

	</div>



	<!-- MOBILE VIEW: MATCHES TAB -->

	<div class="mobile-tab-content mobile-matches-panel mobile-only" class:hidden-on-mobile={mobileActiveTab !== 'matches'}>

		<!-- Active Matches Section -->

		<section class="mobile-section">

			<div class="mobile-section-header">

				<h2><Icon name="swords" size={15} /> {$t('mobile_tab_my_matches')}</h2>

				<span class="badge-pill">{$t('mobile_active_matches_count', { count: myActiveMatches.length, suffix: myActiveMatches.length > 1 ? 's' : '' })}</span>

			</div>



			{#if myActiveMatches.length === 0}
				<div class="empty-matches-card glass">
					<div class="empty-icon"><Icon name="target" size={32} /></div>
					<h3>{$t('mobile_empty_matches_title')}</h3>
					<p>{$t('mobile_empty_matches_desc')}</p>
					<button class="btn btn-sm btn-primary" on:click={() => navigateToTournament(activeTournament?.id || (tournaments && tournaments[0]?.id))}>
						<Icon name="trophy" size={14} /> {$t('mobile_btn_view_tournaments')}
					</button>
				</div>
			{:else}
				<div class="matches-cards-list">
					{#each myActiveMatches as m}
						<div class="match-card glass" class:match-ready={m.is_ready}>
							<div class="match-card-top">
								<span class="mym-thumb" class:empty={!m.game_image} style={m.game_image ? `background-image: url(${m.game_image})` : ''} aria-hidden="true">{#if !m.game_image}<Icon name="trophy" size={16} />{/if}</span>
								<div class="mc-versus">
									<span class="vs-label">{$t('mobile_match_versus')}</span>
									<span class="opponent-name">{m.opponent_name}</span>
								</div>
								<span class="match-status-tag" class:tag-ready={m.is_ready}>
									{m.status_label}
								</span>
							</div>
							<div class="match-tourney-title">
								{m.game_name} · {m.tournament_name} · <span class="round-name">{m.round_label}</span>
								{#if m.opponent_seat}
									<button class="seat-link" on:click={() => navigateToMap(m.opponent_seat)} title={$t('tourneys_view_on_map')}>
										<Icon name="pin" size={12} /> {$t('mobile_match_seat_link', { seat: m.opponent_seat })}
									</button>
								{/if}
							</div>

							<!-- Quick Score Panel (Inline & Smooth) -->
							{#if activeScoreMatchKey === m.match_key}
								<div class="quick-score-panel">
									<div class="quick-score-header">
										<span class="quick-score-title"><Icon name="check" size={13} /> {$t('mobile_match_quick_score')}</span>
										<button class="quick-score-close" on:click={() => activeScoreMatchKey = null} title={$t('common_close')}>
											<Icon name="x" size={14} />
										</button>
									</div>

									{#if m.is_ffa}
										<div class="numeric-score-row">
											<div class="score-player-col">
												<span class="player-label">{$t('mobile_score_ffa_mine')}</span>
												<div class="score-stepper">
													<button class="stepper-btn" on:click={() => adjustQuickScore(m.match_key, 'myScore', -1)} disabled={isSubmittingScore}>−</button>
													<input type="number" min="0" class="stepper-input" bind:value={quickScores[m.match_key].myScore} disabled={isSubmittingScore} />
													<button class="stepper-btn" on:click={() => adjustQuickScore(m.match_key, 'myScore', 1)} disabled={isSubmittingScore}>+</button>
												</div>
											</div>
										</div>
										<button class="btn btn-primary btn-submit-quick-score" disabled={isSubmittingScore} on:click={() => submitQuickScore(m)}>
											<Icon name="check" size={14} /> {isSubmittingScore ? $t('mobile_score_submitting') : $t('mobile_score_submit')}
										</button>
									{:else if m.boolean_mode}
										<div class="boolean-score-actions">
											<button 
												class="btn-bool-score win" 
												disabled={isSubmittingScore}
												on:click={() => submitQuickScore(m, 'win')}
											>
												<Icon name="trophy" size={14} /> {$t('mobile_score_win')}
											</button>
											<button 
												class="btn-bool-score loss" 
												disabled={isSubmittingScore}
												on:click={() => submitQuickScore(m, 'loss')}
											>
												<Icon name="x" size={14} /> {$t('mobile_score_loss')}
											</button>
											{#if m.allow_draws}
												<button 
													class="btn-bool-score draw" 
													disabled={isSubmittingScore}
													on:click={() => submitQuickScore(m, 'draw')}
												>
													{$t('mobile_score_draw')}
												</button>
											{/if}
										</div>
									{:else}
										<div class="numeric-score-row">
											<div class="score-player-col">
												<span class="player-label">{m.my_name || $t('mobile_score_my_score')}</span>
												<div class="score-stepper">
													<button class="stepper-btn" on:click={() => adjustQuickScore(m.match_key, 'myScore', -1)} disabled={isSubmittingScore}>−</button>
													<input 
														type="number" 
														min="0"
														class="stepper-input" 
														bind:value={quickScores[m.match_key].myScore}
														disabled={isSubmittingScore} 
													/>
													<button class="stepper-btn" on:click={() => adjustQuickScore(m.match_key, 'myScore', 1)} disabled={isSubmittingScore}>+</button>
												</div>
											</div>

											<div class="score-vs-divider">VS</div>

											<div class="score-player-col">
												<span class="player-label">{m.opponent_name || $t('mobile_score_opp_score')}</span>
												<div class="score-stepper">
													<button class="stepper-btn" on:click={() => adjustQuickScore(m.match_key, 'oppScore', -1)} disabled={isSubmittingScore}>−</button>
													<input 
														type="number" 
														min="0"
														class="stepper-input" 
														bind:value={quickScores[m.match_key].oppScore}
														disabled={isSubmittingScore} 
													/>
													<button class="stepper-btn" on:click={() => adjustQuickScore(m.match_key, 'oppScore', 1)} disabled={isSubmittingScore}>+</button>
												</div>
											</div>
										</div>

										<button 
											class="btn btn-primary btn-submit-quick-score" 
											disabled={isSubmittingScore}
											on:click={() => submitQuickScore(m)}
										>
											<Icon name="check" size={14} /> 
											{isSubmittingScore ? $t('mobile_score_submitting') : $t('mobile_score_submit')}
										</button>
									{/if}
								</div>
							{/if}

							<div class="match-card-actions">
								{#if m.is_ready}
									<button 
										class="btn btn-primary btn-match-action"
										on:click={() => toggleScoreEntry(m)}
									>
										<Icon name="check" size={13} /> {activeScoreMatchKey === m.match_key ? $t('common_close') : $t('mobile_match_enter_score_btn')}
									</button>
								{/if}

								<button 
									class="btn btn-secondary btn-tree-action"
									on:click={() => navigateToTournament(m.tournament_id)}
									title={$t('mobile_match_view_bracket')}
								>
									<Icon name="swords" size={13} /> {$t('mobile_match_view_bracket')}
								</button>

								{#if m.opponent_id}
									<button 
										class="btn btn-secondary btn-chat-action" 
										on:click={() => navigateToChat(m.opponent_id)}
										title={$t('mobile_match_send_msg')}
									>
										<Icon name="chat" size={13} />
									</button>
								{/if}
							</div>
						</div>
					{/each}
				</div>
			{/if}
			{#if myResults.length > 0 || hiddenResultsCount > 0}
				<div class="my-results">
					{#each myResults as r (r.match_key)}
						<div class="result-row" class:win={r.outcome === 'win'} class:loss={r.outcome === 'loss'}>
							<Icon name="check-circle" size={15} />
							<span class="rr-text">
								<strong>{r.is_ffa ? $t('result_ffa_mine', { n: r.my_score }) : `${$t('mobile_score_my_score')} ${r.my_score} – ${r.opp_score}`}</strong>
								{#if !r.is_ffa}{r.opponent_name}{/if}
								<span class="rr-meta">· {r.game_name} · {r.round_label}</span>
							</span>
							<button class="rr-hide" on:click={() => hideResult(r.match_key)} title={$t('result_hide')} aria-label={$t('result_hide')}><Icon name="x" size={14} /></button>
						</div>
					{/each}
					{#if hiddenResultsCount > 0}
						<button class="rr-show" on:click={showHiddenResults}>{$t('result_show_hidden', { n: hiddenResultsCount })}</button>
					{/if}
				</div>
			{/if}
		</section>

		<!-- Tournaments Summary -->
		<section class="mobile-section">
			<div class="mobile-section-header">
				<h2><Icon name="trophy" size={15} /> {$t('nav_tournaments')} ({tournaments.length})</h2>
				<button class="see-all-link" on:click={() => navigateToTournament(activeTournament?.id || (tournaments && tournaments[0]?.id))}>{$t('mobile_see_all')} →</button>
			</div>
			<div class="mobile-tourneys-list">
				{#each (tournaments || []).slice(0, 4) as tourney}
					<button class="mobile-tourney-card glass" on:click={() => navigateToTournament(tourney.id)}>
						<div class="tourney-card-info">
							<span class="tourney-name">{tourney.name}</span>
							<span class="tourney-sub">
								<Icon name="gamepad" size={12} /> {tourney.game || $t('common_game_fallback')} · {$t('dash_participants_count', { count: tourney.participants_count || 0 })}
							</span>
						</div>
						<span class="tourney-badge badge-{tourney.status.toLowerCase()}">
							{#if tourney.status === 'RUNNING'}{$t('mobile_status_running')}{:else if tourney.status === 'OPEN'}{$t('mobile_status_open')}{:else}{$t('mobile_status_done')}{/if}
						</span>
					</button>
				{/each}
			</div>
		</section>

		<!-- Leaderboard: top 3, unfolds (remembered) into the full player / team ranking -->
		{#if stats.leaderboard && stats.leaderboard.length > 0}
			<section class="mobile-section">
				<div class="mobile-section-header">
					<h2><Icon name="trophy" size={15} /> {mobileLbFull ? $t('dash_lb_title') : $t('mobile_top_podium_title')}</h2>
					<button class="mobile-lb-toggle" on:click={toggleMobileLb} aria-expanded={mobileLbFull}>
						{mobileLbFull ? $t('mobile_lb_show_top3') : $t('mobile_lb_show_all')}
						<Icon name={mobileLbFull ? 'chevron-up' : 'chevron-down'} size={14} />
					</button>
				</div>
				{#if mobileLbFull}
					<div class="mobile-lb-full">
						<DashboardLeaderboard
							{stats}
							{teamLeaderboard}
							{previousLeaderboard}
							on:openPlayerStats={(e) => openPlayerStats(e.detail)}
						/>
					</div>
				{:else}
					<div class="mobile-podium glass">
						{#each stats.leaderboard.slice(0, 3) as p, idx}
							<div class="podium-row">
								<span class="podium-rank">{idx === 0 ? '🥇' : idx === 1 ? '🥈' : '🥉'}</span>
								<span class="podium-name">{p.username}</span>
								{#if p.team_name}
									<span class="podium-team">👥 {p.team_name}</span>
								{/if}
								<span class="podium-pts">{p.points || 0} {$t('common_pts')}</span>
							</div>
						{/each}
					</div>
				{/if}
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

			<h1 class="title-premium">{$t('dash_title')}</h1>

		</div>

		<div class="cmd-center">

			<div class="info-chip glass">

				<span class="chip-label">{$t('dash_stat_event')}</span>

				<span class="chip-value">{stats.event_name || 'Alanbix LAN'}</span>

			</div>

			{#if user?.team_name}

				<div class="info-chip glass" style="border-color: rgba(59,130,246,0.35); background: rgba(59,130,246,0.08);">

					<span class="chip-label" style="color: var(--accent); display: inline-flex; align-items: center; gap: 0.35rem;"><Icon name="users" size={13} /> {$t('dash_team_lbl')}</span>

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

			{#if stats.active > 0}
			<div class="status-live">

				<span class="pulse"></span> 

				{@html $t('dash_live_status')}

			</div>
			{/if}

		</div>

	</header>



	<!-- Desktop: "Mes matchs" first, secondary views in tabs, chat on the right -->
	<div class="dash-grid desktop-only">
		<div class="dash-left">
			<section class="my-matches glass">
				<header class="mym-header">
					<h2><Icon name="swords" size={16} /> {$t('mobile_tab_my_matches')} <span class="mym-count">{myActiveMatches.length}</span></h2>
					<button class="mym-link" on:click={() => navigateToTournament(activeTournament?.id || (tournaments && tournaments[0]?.id))}>
						{$t('mobile_btn_view_tournaments')} <Icon name="chevron-right" size={14} />
					</button>
				</header>
				{#if myActiveMatches.length === 0}
					<p class="mym-empty"><Icon name="target" size={18} /> {$t('mobile_empty_matches_title')}</p>
				{:else}
					<ul class="mym-list">
						{#each myMatchesSorted as m (m.match_key)}
							<li class="mym-row" class:ready={m.is_ready}>
								<span class="mym-thumb" class:empty={!m.game_image} style={m.game_image ? `background-image: url(${m.game_image})` : ''} aria-hidden="true">{#if !m.game_image}<Icon name="trophy" size={16} />{/if}</span>
								<div class="mym-main">
									<div class="mym-versus">
										<span class="mym-vs">{$t('mobile_match_versus')}</span>
										<span class="mym-opponent">{m.opponent_name}</span>
										{#if m.opponent_seat}
											<button class="mym-seat" on:click={() => navigateToMap(m.opponent_seat)} title={$t('tourneys_view_on_map')}>
												<Icon name="pin" size={12} /> {$t('mobile_match_seat_link', { seat: m.opponent_seat })}
											</button>
										{/if}
									</div>
									<div class="mym-meta">{m.game_name} · {m.tournament_name} · {m.round_label}</div>
								</div>
								<span class="mym-status" class:ready={m.is_ready}>{m.status_label}</span>
								<div class="mym-actions">
									{#if m.is_ready}
										<button class="btn-primary mym-btn" on:click={() => toggleScoreEntry(m)}>
											<Icon name="check" size={13} /> {activeScoreMatchKey === m.match_key ? $t('common_close') : $t('mobile_match_enter_score_btn')}
										</button>
									{/if}
									<button class="btn-secondary mym-btn" on:click={() => navigateToTournament(m.tournament_id)} title={$t('mobile_match_view_bracket')}>
										<Icon name="swords" size={13} /> {$t('mobile_match_view_bracket')}
									</button>
								</div>
								{#if activeScoreMatchKey === m.match_key}
									<div class="mym-score">
										{#if m.is_ffa}
											<label class="mym-field"><span>{$t('mobile_score_ffa_mine')}</span>
												<input type="number" min="0" inputmode="numeric" bind:value={quickScores[m.match_key].myScore} disabled={isSubmittingScore} />
											</label>
											<button class="btn-primary mym-btn" disabled={isSubmittingScore} on:click={() => submitQuickScore(m)}>
												<Icon name="check" size={13} /> {isSubmittingScore ? $t('mobile_score_submitting') : $t('mobile_score_submit')}
											</button>
										{:else if m.boolean_mode}
											<button class="btn-success mym-btn" disabled={isSubmittingScore} on:click={() => submitQuickScore(m, 'win')}><Icon name="trophy" size={13} /> {$t('mobile_score_win')}</button>
											<button class="btn-secondary mym-btn" disabled={isSubmittingScore} on:click={() => submitQuickScore(m, 'loss')}><Icon name="x" size={13} /> {$t('mobile_score_loss')}</button>
											{#if m.allow_draws}
												<button class="btn-secondary mym-btn" disabled={isSubmittingScore} on:click={() => submitQuickScore(m, 'draw')}>{$t('mobile_score_draw')}</button>
											{/if}
										{:else}
											<label class="mym-field"><span>{m.my_name || $t('mobile_score_my_score')}</span>
												<input type="number" min="0" inputmode="numeric" bind:value={quickScores[m.match_key].myScore} disabled={isSubmittingScore} />
											</label>
											<span class="mym-dash">–</span>
											<label class="mym-field"><span>{m.opponent_name || $t('mobile_score_opp_score')}</span>
												<input type="number" min="0" inputmode="numeric" bind:value={quickScores[m.match_key].oppScore} disabled={isSubmittingScore} />
											</label>
											<button class="btn-primary mym-btn" disabled={isSubmittingScore} on:click={() => submitQuickScore(m)}>
												<Icon name="check" size={13} /> {isSubmittingScore ? $t('mobile_score_submitting') : $t('mobile_score_submit')}
											</button>
										{/if}
									</div>
								{/if}
							</li>
						{/each}
					</ul>
				{/if}
				{#if myResults.length > 0 || hiddenResultsCount > 0}
				<div class="my-results">
					{#each myResults as r (r.match_key)}
						<div class="result-row" class:win={r.outcome === 'win'} class:loss={r.outcome === 'loss'}>
							<Icon name="check-circle" size={15} />
							<span class="rr-text">
								<strong>{r.is_ffa ? $t('result_ffa_mine', { n: r.my_score }) : `${$t('mobile_score_my_score')} ${r.my_score} – ${r.opp_score}`}</strong>
								{#if !r.is_ffa}{r.opponent_name}{/if}
								<span class="rr-meta">· {r.game_name} · {r.round_label}</span>
							</span>
							<button class="rr-hide" on:click={() => hideResult(r.match_key)} title={$t('result_hide')} aria-label={$t('result_hide')}><Icon name="x" size={14} /></button>
						</div>
					{/each}
					{#if hiddenResultsCount > 0}
						<button class="rr-show" on:click={showHiddenResults}>{$t('result_show_hidden', { n: hiddenResultsCount })}</button>
					{/if}
				</div>
			{/if}
			</section>

			<section class="dash-tabs">
				<div class="dash-tablist" role="tablist">
					<button role="tab" class="dash-tab" class:active={dashTab === 'tournaments'} aria-selected={dashTab === 'tournaments'} on:click={() => setDashTab('tournaments')}>
						<Icon name="trophy" size={14} /> {$t('dash_tab_tournaments')}
					</button>
					<button role="tab" class="dash-tab" class:active={dashTab === 'leaderboard'} aria-selected={dashTab === 'leaderboard'} on:click={() => setDashTab('leaderboard')}>
						<Icon name="users" size={14} /> {$t('dash_lb_title')}
					</button>
					<button role="tab" class="dash-tab" class:active={dashTab === 'map'} aria-selected={dashTab === 'map'} on:click={() => setDashTab('map')}>
						<Icon name="map" size={14} /> {$t('dash_map_title')}
					</button>
				</div>
				<div class="dash-tab-body">
					{#if dashTab === 'tournaments'}
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
					{:else if dashTab === 'leaderboard'}
						<DashboardLeaderboard
							{stats}
							{teamLeaderboard}
							{previousLeaderboard}
							on:openPlayerStats={(e) => openPlayerStats(e.detail)}
						/>
					{:else}
						<DashboardFloorMap
							{roomLayout}
							{allUsers}
							{user}
							{hoveredSeatId}
							{activePulsingSeats}
							{activeBeams}
							chatSplitRatio={0}
						/>
					{/if}
				</div>
			</section>
		</div>

		<div class="dash-right">
			<PublicChat
				{user}
				{allUsers}
				on:seatHover={(e) => hoveredSeatId = e.detail}
				on:seatLeave={() => hoveredSeatId = null}
			/>
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




<!-- Toasts Notification System -->
{#if toasts.length > 0}
	<div class="toast-container">
		{#each toasts as t (t.id)}
			<div class="toast {t.type} {t.leaving ? 'toast-leave' : 'toast-enter'}">
				<span>{#if t.type === 'success'}✓{:else if t.type === 'error'}✕{:else}ℹ{/if}</span>
				<span class="toast-msg">{t.message}</span>
			</div>
		{/each}
	</div>
{/if}

<style>
	.my-results { display: flex; flex-direction: column; gap: 0.3rem; margin-top: 0.5rem; }
	.result-row { display: flex; align-items: center; gap: 0.5rem; padding: 0.3rem 0.4rem 0.3rem 0.7rem; border-radius: var(--radius-md); font-size: 0.8125rem; color: var(--text-dim); background: var(--surface-sunken); border: 1px solid var(--glass-border); }
	.result-row.win { border-color: color-mix(in srgb, var(--success) 45%, transparent); }
	.result-row.win > :global(svg) { color: var(--success); }
	.result-row.loss { border-color: color-mix(in srgb, var(--danger) 30%, transparent); }
	.result-row .rr-text { flex: 1; min-width: 0; color: var(--text-main); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
	.result-row .rr-meta { color: var(--text-dim); }
	.rr-hide { display: inline-flex; align-items: center; justify-content: center; width: 26px; height: 26px; flex-shrink: 0; border: none; border-radius: 6px; background: transparent; color: var(--text-dim); cursor: pointer; }
	.rr-hide:hover { background: var(--hover-tint); color: var(--text-main); }
	.rr-show { align-self: flex-start; background: none; border: none; padding: 0.1rem 0; color: var(--accent); font-size: 0.75rem; font-weight: 600; cursor: pointer; }
	.rr-show:hover { text-decoration: underline; }


	.hq-dashboard {

		display: flex;

		flex-direction: column;

		gap: 1.5rem;

		height: 100%;

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
		font-size: var(--fs-page);

		

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

		font-size: 0.72rem;

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



		/* Glued under the mobile top bar, full width and same surface, so the
		   scrolling content never shows between the two */
		.mobile-dash-header {
			position: sticky;
			top: var(--mobile-top-h, 42px);
			z-index: 50;
			margin: -0.5rem -0.5rem 0.5rem;
			padding: 0.4rem 0.5rem;
			background: var(--mobile-bar-bg, rgba(15, 23, 42, 0.95));
			backdrop-filter: blur(12px);
			-webkit-backdrop-filter: blur(12px);
			border-bottom: 1px solid var(--glass-border, rgba(255, 255, 255, 0.08));
		}



		.mobile-dash-tabs {

			display: flex;

			gap: 0.5rem;

			background: var(--surface-sunken);

			padding: 0.3rem;

			border-radius: 4px;

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

			font-size: 0.78rem;

			cursor: pointer;

			transition: all 0.2s;

		}



		.mobile-dash-tab.active {

			background: var(--accent);

			color: #fff;

			box-shadow: none;

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
			/* the last block must clear the bottom tab bar */
			padding-bottom: calc(var(--mobile-nav-h, 48px) + var(--safe-bottom, 0px) + 1rem);

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

			color: var(--text-main);

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

			border: 1px dashed var(--glass-border);

			gap: 0.6rem;

		}

		.empty-icon { font-size: 2.2rem; }

		.empty-matches-card h3 { margin: 0; font-size: 1rem; color: var(--text-main); }

		.empty-matches-card p { margin: 0; font-size: 0.82rem; color: var(--text-dim); max-width: 320px; }



		/* Match Cards */

		.matches-cards-list {

			display: flex;

			flex-direction: column;

			gap: 0.5rem;
		}
		.match-card {

			background: var(--glass-bg);

			border: 1px solid var(--glass-border);

			border-radius: 14px;
			padding: 0.6rem 0.75rem;
			display: flex;
			flex-direction: column;
			gap: 0.35rem;
			border-left: 3px solid #f59e0b;

		}



		.match-card.match-ready {

			border-left: 3px solid #10b981;

		}



		.match-card-top {

			display: flex;

			align-items: center;

			justify-content: space-between;
			gap: 0.5rem;
		}
		.mc-versus { display: flex; align-items: baseline; gap: 0.35rem; min-width: 0; flex: 1; }
		.match-card-top .mym-thumb { width: 48px; height: 34px; }
		.mc-versus .vs-label { white-space: nowrap; }
		.mc-versus .opponent-name { white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }



		.match-game-tag {

			font-weight: 700;

			color: var(--accent);

		}



		.match-status-tag {

			font-weight: 700;
			font-size: 0.68rem;
			white-space: nowrap;
			flex-shrink: 0;
			padding: 0.1rem 0.4rem;

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
			font-size: 0.78rem;
			color: var(--text-muted);
			display: flex;
			align-items: center;
			gap: 0.4rem;
			flex-wrap: wrap;
		}
		.match-tourney-title .round-name {
			color: var(--text-muted);
		}



		.match-versus-box {

			background: var(--surface-sunken);

			border: 1px solid var(--glass-border);

			border-radius: 8px;

			padding: 0.6rem 0.75rem;

			display: flex;

			align-items: center;

			gap: 0.6rem;

		}



		.vs-label {

			font-size: 0.75rem;

			color: var(--text-dim);

			font-weight: 600;

		}



		.opponent-name {

			font-size: 0.92rem;

			font-weight: 700;

			color: var(--text-main);

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

			gap: 0.4rem;
			margin-top: 0.15rem;
		}
		.btn-match-action {
			flex: 1;
			text-align: center;
			text-decoration: none;
			font-size: 0.8rem;
			padding: 0.4rem 0.6rem;
		}



		.btn-chat-action {

			text-decoration: none;

			font-size: 0.85rem;

			padding: 0.55rem 0.75rem;

		}

		/* Quick Score Panel & Steppers */
		.quick-score-panel {
			background: rgba(0, 0, 0, 0.4);
			border: 1px solid rgba(255, 255, 255, 0.12);
			border-radius: 3px;
			padding: 0.6rem;
			display: flex;
			flex-direction: column;
			gap: 0.5rem;
			animation: fadeIn 0.15s ease-out;
		}

		.quick-score-header {
			display: flex;
			align-items: center;
			justify-content: space-between;
		}

		.quick-score-title {
			font-size: 0.72rem;
			font-weight: 700;
			color: var(--accent);
			display: inline-flex;
			align-items: center;
			gap: 0.3rem;
			text-transform: uppercase;
			letter-spacing: 0.5px;
		}

		.quick-score-close {
			background: none;
			border: none;
			color: var(--text-dim);
			cursor: pointer;
			padding: 0.2rem;
			border-radius: 2px;
			display: flex;
			align-items: center;
			justify-content: center;
		}

		.quick-score-close:hover {
			color: var(--text-main);
		}

		.boolean-score-actions {
			display: flex;
			gap: 0.4rem;
		}

		.btn-bool-score {
			flex: 1;
			display: flex;
			align-items: center;
			justify-content: center;
			gap: 0.35rem;
			padding: 0.5rem 0.4rem;
			font-size: 0.78rem;
			font-weight: 700;
			border-radius: 3px;
			border: 1px solid transparent;
			cursor: pointer;
			transition: all 0.15s;
		}

		.btn-bool-score.win {
			background: rgba(16, 185, 129, 0.18);
			color: #34d399;
			border-color: rgba(16, 185, 129, 0.35);
		}

		.btn-bool-score.win:active {
			background: rgba(16, 185, 129, 0.35);
		}

		.btn-bool-score.loss {
			background: rgba(239, 68, 68, 0.15);
			color: #f87171;
			border-color: rgba(239, 68, 68, 0.3);
		}

		.btn-bool-score.loss:active {
			background: rgba(239, 68, 68, 0.3);
		}

		.btn-bool-score.draw {
			background: rgba(245, 158, 11, 0.15);
			color: #fbbf24;
			border-color: rgba(245, 158, 11, 0.3);
		}

		.numeric-score-row {
			display: flex;
			align-items: center;
			justify-content: space-between;
			gap: 0.4rem;
			background: var(--surface-sunken);
			border-radius: 3px;
			padding: 0.4rem;
		}

		.score-player-col {
			flex: 1;
			display: flex;
			flex-direction: column;
			align-items: center;
			gap: 0.25rem;
			min-width: 0;
		}

		.player-label {
			font-size: 0.68rem;
			font-weight: 700;
			color: var(--text-dim);
			white-space: nowrap;
			overflow: hidden;
			text-overflow: ellipsis;
			max-width: 100px;
		}

		.score-stepper {
			display: flex;
			align-items: center;
			gap: 0.25rem;
		}

		.stepper-btn {
			width: 28px;
			height: 28px;
			display: flex;
			align-items: center;
			justify-content: center;
			background: rgba(255, 255, 255, 0.08);
			border: 1px solid rgba(255, 255, 255, 0.12);
			border-radius: 3px;
			color: white;
			font-size: 0.9rem;
			font-weight: 700;
			cursor: pointer;
		}

		.stepper-btn:active {
			background: rgba(255, 255, 255, 0.18);
		}

		.stepper-input {
			width: 40px;
			height: 28px;
			text-align: center;
			font-size: 0.85rem;
			font-weight: 800;
			background: rgba(0, 0, 0, 0.4);
			border: 1px solid rgba(255, 255, 255, 0.15);
			border-radius: 3px;
			color: var(--accent);
			padding: 0;
			-moz-appearance: textfield;
		}

		.stepper-input::-webkit-inner-spin-button,
		.stepper-input::-webkit-outer-spin-button {
			-webkit-appearance: none;
			margin: 0;
		}

		.score-vs-divider {
			font-size: 0.7rem;
			font-weight: 800;
			color: var(--text-dim);
			padding: 0 0.2rem;
		}

		.btn-submit-quick-score {
			width: 100%;
			height: 32px;
			display: flex;
			align-items: center;
			justify-content: center;
			gap: 0.35rem;
			font-size: 0.78rem;
			font-weight: 700;
			border-radius: 3px !important;
		}

		.btn-tree-action {
			display: inline-flex;
			align-items: center;
			justify-content: center;
			gap: 0.3rem;
			font-size: 0.78rem;
			padding: 0.4rem 0.6rem;
			border-radius: 3px !important;
			white-space: nowrap !important;
		}

		.see-all-link {
			background: none;
			border: none;
			color: var(--accent);
			font-size: 0.72rem;
			cursor: pointer;
			padding: 0;
			display: inline-flex;
			align-items: center;
			gap: 0.2rem;
		}

		.mobile-tourney-card {
			width: 100%;
			background: var(--glass-bg);
			cursor: pointer;
			text-align: left;
			border-radius: 3px !important;
		}

		.match-card {
			border-radius: 3px !important;
		}

		.seat-link {
			border: none;
			cursor: pointer;
			display: inline-flex;
			align-items: center;
			gap: 0.2rem;
			border-radius: 2px !important;
		}

		/* Toast Container */
		.toast-container {
			position: fixed;
			bottom: calc(var(--mobile-nav-h, 48px) + 12px);
			left: 50%;
			transform: translateX(-50%);
			z-index: 9999;
			display: flex;
			flex-direction: column;
			gap: 0.4rem;
			pointer-events: none;
			max-width: 90vw;
		}

		.toast {
			display: flex;
			align-items: center;
			gap: 0.5rem;
			padding: 0.5rem 0.8rem;
			border-radius: 3px;
			font-size: 0.75rem;
			font-weight: 600;
			box-shadow: 0 4px 12px rgba(0, 0, 0, 0.4);
			pointer-events: auto;
			background: #1e293b;
			color: #f8fafc;
			border: 1px solid rgba(255, 255, 255, 0.1);
		}

		.toast.success { background: #064e3b; border-color: #10b981; color: #a7f3d0; }
		.toast.error { background: #7f1d1d; border-color: #ef4444; color: #fecaca; }
		.toast.info { background: #1e3a5f; border-color: #3b82f6; color: #bfdbfe; }

		.toast-enter { animation: toastIn 0.25s ease-out forwards; }
		.toast-leave { animation: toastOut 0.25s ease-in forwards; }

		@keyframes toastIn {
			from { opacity: 0; transform: translateY(10px); }
			to { opacity: 1; transform: translateY(0); }
		}

		@keyframes toastOut {
			from { opacity: 1; transform: translateY(0); }
			to { opacity: 0; transform: translateY(10px); }
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

			border: 1px solid var(--glass-border);

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

			font-size: 0.78rem;

			font-weight: 700;

			color: var(--text-main);

			overflow: hidden;

			text-overflow: ellipsis;

			white-space: nowrap;

		}



		.tourney-sub {

			font-size: 0.75rem;

			color: var(--text-dim);

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

		.mobile-lb-toggle { display: inline-flex; align-items: center; gap: 0.25rem; background: none; border: none; color: var(--accent); font-size: 0.82rem; font-weight: 600; cursor: pointer; padding: 0.2rem 0; }
		.mobile-lb-full { border-radius: 12px; overflow: hidden; }
		/* the section header already says "Classement" */
		.mobile-lb-full :global(.panel-header h2) { display: none; }
		.mobile-podium {

			border-radius: 12px;

			padding: 0.5rem 0.85rem;

			display: flex;

			flex-direction: column;

			gap: 0.5rem;

			border: 1px solid var(--glass-border);

		}



		.podium-row {

			display: flex;

			align-items: center;

			gap: 0.6rem;

			padding: 0.35rem 0;

			font-size: 0.85rem;

		}



		.podium-rank { font-size: 1rem; }

		.podium-name { font-weight: 700; color: var(--text-main); flex: 1; }

		.podium-team { font-size: 0.75rem; color: var(--text-dim); }

		.podium-pts { font-weight: 800; color: #fbbf24; }

	}


	/* === Desktop layout: Mes matchs + tabs on the left, chat on the right === */
	.dash-grid {
		display: grid;
		grid-template-columns: minmax(0, 1fr) minmax(300px, 380px);
		gap: 1.2rem;
		flex: 1;
		min-height: 0;
	}
	.dash-left { display: flex; flex-direction: column; gap: 1rem; min-height: 0; min-width: 0; }
	.dash-right { min-height: 0; display: flex; flex-direction: column; }
	.dash-right > :global(*) { flex: 1; min-height: 0; }

	.my-matches { padding: 0.9rem 1.1rem; display: flex; flex-direction: column; gap: 0.6rem; flex-shrink: 0; max-height: 45%; min-height: 0; }
	.mym-header { display: flex; align-items: center; justify-content: space-between; gap: 1rem; }
	.mym-header h2 { font-size: var(--fs-section); display: inline-flex; align-items: center; gap: 0.5rem; }
	.mym-count { font-family: var(--font-main); font-size: 0.75rem; font-weight: 700; color: var(--accent); background: var(--accent-soft); border-radius: 999px; padding: 0.1rem 0.5rem; }
	.mym-link { background: none; border: none; color: var(--accent); font-weight: 600; font-size: 0.85rem; cursor: pointer; display: inline-flex; align-items: center; gap: 0.2rem; }
	.mym-link:hover { text-decoration: underline; }
	.mym-empty { margin: 0; color: var(--text-dim); display: flex; align-items: center; gap: 0.5rem; font-size: 0.95rem; }
	.mym-list { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 0.4rem; overflow-y: auto; min-height: 0; }
	.mym-row {
		display: flex; flex-wrap: wrap; align-items: center; gap: 0.5rem 1rem;
		padding: 0.45rem 0.75rem; border-radius: var(--radius-md);
		background: var(--surface-raised); border: 1px solid var(--glass-border);
	}
	.mym-row.ready { border-color: var(--accent); }
	/* Game artwork thumbnail: tells the stacked match rows apart at a glance */
	.mym-thumb {
		flex: 0 0 auto; width: 56px; height: 40px; border-radius: var(--radius-sm);
		background: var(--surface-sunken) center / cover no-repeat; border: 1px solid var(--glass-border);
		display: inline-flex; align-items: center; justify-content: center; color: var(--text-muted);
	}
	.mym-main { flex: 1 1 240px; min-width: 0; display: flex; flex-direction: column; gap: 0.15rem; }
	.mym-versus { display: flex; align-items: baseline; gap: 0.4rem; flex-wrap: wrap; }
	.mym-vs { color: var(--text-dim); font-size: 0.85rem; }
	.mym-opponent { font-family: var(--font-title); font-weight: 700; font-size: 1rem; color: var(--text-main); }
	.mym-seat { display: inline-flex; align-items: center; gap: 0.2rem; background: var(--accent-soft); color: var(--accent); border: 1px solid transparent; border-radius: var(--radius-sm); padding: 0.1rem 0.45rem; font-size: 0.78rem; font-weight: 600; cursor: pointer; }
	.mym-seat:hover { border-color: var(--accent); }
	.mym-meta { color: var(--text-muted); font-size: 0.82rem; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
	.mym-status { font-size: 0.78rem; font-weight: 600; color: var(--text-dim); padding: 0.2rem 0.6rem; border-radius: 999px; border: 1px solid var(--glass-border); white-space: nowrap; }
	.mym-status.ready { color: var(--success); border-color: var(--success); }
	.mym-actions { display: flex; gap: 0.5rem; }
	.mym-btn { display: inline-flex; align-items: center; gap: 0.35rem; padding: 0.35rem 0.75rem; font-size: 0.8rem; white-space: nowrap; }
	.mym-score { flex-basis: 100%; display: flex; align-items: center; gap: 0.6rem; flex-wrap: wrap; padding-top: 0.5rem; border-top: 1px solid var(--glass-border); }
	.mym-field { display: flex; align-items: center; gap: 0.4rem; font-size: 0.82rem; color: var(--text-dim); }
	.mym-field span { max-width: 110px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
	.mym-field input { width: 56px; height: 36px; text-align: center; font-size: 1rem; font-weight: 700; padding: 0; border-radius: var(--radius-md); }
	.mym-dash { color: var(--text-dim); }

	.dash-tabs { flex: 1; min-height: 0; display: flex; flex-direction: column; gap: 0.6rem; }
	.dash-tablist { display: flex; gap: 0.4rem; }
	.dash-tab {
		display: inline-flex; align-items: center; gap: 0.4rem;
		padding: 0.45rem 0.9rem; border-radius: var(--radius-md);
		background: transparent; border: 1px solid var(--glass-border);
		color: var(--text-dim); font-weight: 600; font-size: var(--fs-sub); cursor: pointer;
	}
	.dash-tab:hover { color: var(--text-main); border-color: var(--accent); }
	.dash-tab.active { background: var(--accent-soft); color: var(--accent); border-color: var(--accent); }
	.dash-tab-body { flex: 1; min-height: 280px; display: flex; flex-direction: column; }
	.dash-tab-body > :global(*) { flex: 1; min-height: 0; height: 100% !important; }

	@media (min-width: 901px) and (max-width: 1279px) {
		.hq-dashboard { height: auto; }
		.dash-grid { grid-template-columns: 1fr; }
		.my-matches { max-height: 420px; }
		.dash-tab-body { min-height: 480px; }
		.dash-right { height: 560px; }
	}
</style>

