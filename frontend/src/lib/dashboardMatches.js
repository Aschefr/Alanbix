import { mediaThumb } from '$lib/config';

/**
 * The matches of the signed-in player on the home page, one entry per match of the
 * running or open tournaments, finished ones included (shown as results).
 */
export function buildMyMatches(user, tournaments, games, allUsers, myTeamSlots, tFunc) {
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
				if (useTeams && pid < 0 && myTeamSlots[tourney.id] !== undefined) {
					if (pid === myTeamSlots[tourney.id]) { mySlot = i; break; }
					continue;
				}
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
			const gameName = gameObj?.name || tourney.game || tFunc('common_game_fallback');
			let roundLabel = tFunc('mobile_round_match');
			if (m.id?.s === 2) {
				roundLabel = tFunc('tourneys_bracket_lb_round', { n: m.id.r || '?' });
			} else if (m.id?.s >= 100) {
				roundLabel = `${tFunc('spec_group_num', { group: String.fromCharCode(64 + m.id.s - 100) })} · ${tFunc('tourneys_round_n', { n: m.id.r || '?' })}`;
			} else if (m.id?.s === 3) {
				roundLabel = tFunc('mobile_round_gf');
			} else if (m.id?.r) {
				roundLabel = tFunc('tourneys_round_n', { n: m.id.r });
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
				my_name: user?.username || tFunc('chat_you'),
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
}
