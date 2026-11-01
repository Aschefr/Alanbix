<script>
	import { onMount, onDestroy } from 'svelte';
	import { api } from '$lib/api';
	import { t } from '$lib/i18nStore';
	import Icon from '$lib/components/Icon.svelte';

	// Defaults used to pre-fill every new tournament (CreateTournamentWizard reads default_tournament_pts)
	let pts = { pts_winner: 1.5, pts_second: 1.3, pts_third: 1.0, pts_participation: 1.0, pts_per_match: 0.5 };
	let teamMode = 'weighted'; // weighted = average per member, sum = raw total (team_scoring_mode)
	let saveState = ''; // '' | saving | saved | error
	let ready = false;

	// Example tournament: single elimination, 6 players from 2 LAN teams
	const PLAYERS = [
		{ name: 'Alice', team: 'a', rank: 1, matches: 3, score: 42, result: 'rank_1' },
		{ name: 'David', team: 'b', rank: 2, matches: 3, score: 35, result: 'rank_2' },
		{ name: 'Bruno', team: 'a', rank: 3, matches: 3, score: 31, result: 'rank_3' },
		{ name: 'Emma', team: 'b', rank: 4, matches: 3, score: 27, result: 'rank_4' },
		{ name: 'Chloé', team: 'a', rank: 5, matches: 1, score: 12, result: 'out_r1' },
		{ name: 'Farid', team: 'b', rank: 5, matches: 1, score: 9, result: 'out_r1' },
	];

	const r1 = (x) => Math.round(x * 10) / 10;
	const num = (v) => { const n = Number(v); return Number.isFinite(n) && n >= 0 ? n : 0; };
	const fmt = (n) => Number(n).toLocaleString(undefined, { minimumFractionDigits: 1, maximumFractionDigits: 1 });

	// Same formula as the server (_compute_projected_standings): podium + participation per match
	// + a score bonus between pts_per_match and twice that, from the cumulated score
	$: rows = (() => {
		const scores = PLAYERS.map(p => p.score).filter(s => s > 0);
		const min = Math.min(...scores), range = Math.max(...scores) - min;
		const podium = { 1: num(pts.pts_winner), 2: num(pts.pts_second), 3: num(pts.pts_third) };
		return PLAYERS.map(p => {
			const bonus = p.score <= 0 ? 0 : r1(num(pts.pts_per_match) * (range > 0 ? 1 + (p.score - min) / range : 2));
			const place = podium[p.rank] || 0;
			const part = r1(num(pts.pts_participation) * p.matches);
			return { ...p, place, part, bonus, total: r1(place + part + bonus) };
		});
	})();
	$: maxTotal = Math.max(...rows.map(r => r.total), 0.1);
	$: teams = ['a', 'b'].map(id => {
		const members = rows.filter(r => r.team === id);
		const sum = r1(members.reduce((s, r) => s + r.total, 0));
		return { id, sum, avg: r1(sum / members.length), score: teamMode === 'weighted' ? r1(sum / members.length) : sum };
	});
	$: leader = teams[0].score === teams[1].score ? null : (teams[0].score > teams[1].score ? 'a' : 'b');

	// Sentence with inline fields: "{winner}" etc. become number inputs bound to pts
	const FIELDS = { winner: 'pts_winner', second: 'pts_second', third: 'pts_third', participation: 'pts_participation', bonus: 'pts_per_match' };
	const split = (text) => text.split(/(\{\w+\})/).filter(Boolean).map(s => {
		const m = s.match(/^\{(\w+)\}$/);
		return m ? { token: m[1] } : { text: s };
	});

	let timer;
	function changed() {
		clearTimeout(timer);
		saveState = 'saving';
		timer = setTimeout(save, 600);
	}
	async function save() {
		const clean = Object.fromEntries(Object.entries(pts).map(([k, v]) => [k, r1(num(v))]));
		try {
			await api.put('/admin/config/default_tournament_pts', { value: JSON.stringify(clean) });
			saveState = 'saved';
		} catch { saveState = 'error'; }
	}
	async function setTeamMode(mode) {
		teamMode = mode;
		try { await api.put('/admin/config/team_scoring_mode', { value: mode }); } catch { saveState = 'error'; }
	}

	onMount(async () => {
		try {
			const v = (await api.get('/admin/config/default_tournament_pts'))?.value;
			if (v) pts = { ...pts, ...(typeof v === 'string' ? JSON.parse(v) : v) };
		} catch {}
		try { teamMode = (await api.get('/dashboard/stats')).team_scoring_mode || 'weighted'; } catch {}
		ready = true;
	});
	onDestroy(() => { if (saveState === 'saving') { clearTimeout(timer); save(); } });
</script>

{#if ready}
<div class="sim">
	<div class="rules">
		{#each ['setup_points_rule_podium', 'setup_points_rule_participation', 'setup_points_rule_bonus'] as key}
			<p>
				{#each split($t(key)) as part}
					{#if part.text}{part.text}
					{:else if part.token === 'bonus_max'}<strong class="derived">{fmt(num(pts.pts_per_match) * 2)}</strong>
					{:else if FIELDS[part.token]}<input class="inline-num" type="number" min="0" max="20" step="0.1" inputmode="decimal"
						bind:value={pts[FIELDS[part.token]]} on:input={changed} aria-label={$t(`setup_points_field_${part.token}`)} />
					{/if}
				{/each}
			</p>
		{/each}
		<p class="hint">
			{$t('setup_points_defaults_hint')}
			{#if saveState === 'saving'}<span class="state">{$t('setup_points_saving')}</span>
			{:else if saveState === 'saved'}<span class="state ok"><Icon name="check" size={13} /> {$t('setup_saved')}</span>
			{:else if saveState === 'error'}<span class="state err">{$t('admin_error_save')}</span>{/if}
		</p>
	</div>

	<div class="board" aria-live="polite">
		<div class="board-head">
			<span>{$t('setup_sim_title')}</span>
			<span class="board-sub">{$t('setup_sim_sub')}</span>
		</div>
		<ol class="players">
			{#each rows as r (r.name)}
				<li class="player">
					<span class="who">
						<span class="dot team-{r.team}" aria-hidden="true"></span>
						<span class="name">{r.name}</span>
						<span class="result">{$t(`setup_sim_${r.result}`)} · {$t('setup_sim_matches', { n: r.matches })} · {$t('setup_sim_score', { n: r.score })}</span>
					</span>
					<span class="calc">
						{#if r.place}<span title={$t('setup_points_podium')}>{fmt(r.place)}</span> + {/if}<span title={$t('setup_points_participation')}>{fmt(r.part)}</span> + <span title={$t('setup_points_score')}>{fmt(r.bonus)}</span>
					</span>
					<strong class="total">{fmt(r.total)}</strong>
					<span class="bar" aria-hidden="true"><span class="team-{r.team}" style="width: {(r.total / maxTotal) * 100}%"></span></span>
				</li>
			{/each}
		</ol>

		<div class="teams-head">
			<span>{$t('setup_sim_teams')}</span>
			<div class="mode" role="radiogroup" aria-label={$t('setup_sim_teams')}>
				<button role="radio" aria-checked={teamMode === 'weighted'} class:active={teamMode === 'weighted'} on:click={() => setTeamMode('weighted')}>{$t('setup_sim_mode_avg')}</button>
				<button role="radio" aria-checked={teamMode === 'sum'} class:active={teamMode === 'sum'} on:click={() => setTeamMode('sum')}>{$t('setup_sim_mode_sum')}</button>
			</div>
		</div>
		<div class="teams">
			{#each teams as tm (tm.id)}
				<div class="team" class:lead={leader === tm.id}>
					<span class="team-name"><span class="dot team-{tm.id}" aria-hidden="true"></span>{$t(`setup_sim_team_${tm.id}`)}</span>
					<strong class="team-score">{fmt(tm.score)}</strong>
					<span class="team-detail">{teamMode === 'weighted' ? $t('setup_sim_team_avg_detail', { sum: fmt(tm.sum), n: 3 }) : $t('setup_sim_team_sum_detail')}</span>
				</div>
			{/each}
		</div>
	</div>
</div>
{/if}

<style>
	.sim { display: flex; flex-direction: column; gap: 1rem; }
	.rules p { margin: 0 0 0.35rem; font-size: 0.9rem; line-height: 1.9; color: var(--text-main); max-width: 68ch; }
	/* Values typed straight into the sentence: underlined accent figures, not boxed fields
	   (doubled class to beat the light theme's global white input background) */
	.rules input.inline-num.inline-num {
		width: 3.2em; height: 1.6em; padding: 0 0.2em; margin: 0 0.1em; vertical-align: baseline; text-align: center;
		font: inherit; font-weight: 700; font-variant-numeric: tabular-nums; color: var(--accent) !important;
		background: color-mix(in srgb, var(--accent) 9%, transparent) !important;
		border: none !important; border-bottom: 2px dashed color-mix(in srgb, var(--accent) 60%, transparent) !important; border-radius: 5px 5px 0 0;
		box-shadow: none; -moz-appearance: textfield; appearance: textfield; transition: background 0.15s;
	}
	.inline-num::-webkit-inner-spin-button, .inline-num::-webkit-outer-spin-button { -webkit-appearance: none; margin: 0; }
	.rules input.inline-num.inline-num:hover { background: color-mix(in srgb, var(--accent) 15%, transparent) !important; }
	.rules input.inline-num.inline-num:focus { outline: none; border-bottom-style: solid !important; border-bottom-color: var(--accent) !important; background: color-mix(in srgb, var(--accent) 15%, transparent) !important; }
	.derived { color: var(--accent); font-variant-numeric: tabular-nums; }
	.hint { font-size: 0.8rem !important; line-height: 1.5 !important; color: var(--text-dim) !important; display: flex; flex-wrap: wrap; gap: 0.3rem 0.6rem; align-items: center; }
	.state { display: inline-flex; align-items: center; gap: 0.25rem; font-weight: 600; color: var(--text-dim); }
	.state.ok { color: var(--success, #16a34a); }
	.state.err { color: var(--danger); }

	.board { border: 1px solid var(--glass-border); border-radius: var(--radius-md); background: var(--surface-sunken); padding: 0.9rem 1rem; display: flex; flex-direction: column; gap: 0.6rem; }
	.board-head, .teams-head { display: flex; align-items: baseline; justify-content: space-between; gap: 0.5rem 1rem; flex-wrap: wrap; font-weight: 700; font-size: 0.9rem; }
	.board-sub { font-weight: 500; font-size: 0.78rem; color: var(--text-dim); }

	.players { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; }
	.player { display: grid; grid-template-columns: 1fr auto 3.2rem; grid-template-rows: auto 3px; column-gap: 0.8rem; align-items: center; padding: 0.45rem 0; border-top: 1px solid var(--glass-border); }
	.player:first-child { border-top: none; }
	.who { display: flex; align-items: baseline; gap: 0.45rem; flex-wrap: wrap; min-width: 0; }
	.name { font-weight: 700; font-size: 0.9rem; }
	.result { font-size: 0.76rem; color: var(--text-dim); }
	.calc { font-size: 0.78rem; color: var(--text-dim); font-variant-numeric: tabular-nums; white-space: nowrap; }
	.total { text-align: right; font-size: 1rem; font-variant-numeric: tabular-nums; }
	.bar { grid-column: 1 / -1; height: 3px; border-radius: 2px; background: color-mix(in srgb, var(--text-dim) 12%, transparent); margin-top: 0.3rem; overflow: hidden; }
	.bar span { display: block; height: 100%; border-radius: 2px; transition: width 0.35s cubic-bezier(0.16, 1, 0.3, 1); }

	.dot { display: inline-block; width: 8px; height: 8px; border-radius: 50%; flex-shrink: 0; align-self: center; }
	.team-a { background: var(--accent-solid); }
	.team-b { background: #0d9488; }

	.teams-head { margin-top: 0.4rem; padding-top: 0.7rem; border-top: 1px solid var(--glass-border); align-items: center; }
	.mode { display: inline-flex; padding: 0.2rem; border-radius: 9px; border: 1px solid var(--glass-border); background: var(--surface-raised); }
	.mode button { border: none; background: transparent; color: var(--text-dim); font: inherit; font-size: 0.78rem; font-weight: 600; padding: 0.3rem 0.65rem; border-radius: 6px; cursor: pointer; }
	.mode button.active { background: var(--accent-solid); color: white; }
	.teams { display: grid; grid-template-columns: 1fr 1fr; gap: 0.6rem; }
	.team { display: flex; flex-direction: column; gap: 0.15rem; padding: 0.65rem 0.8rem; border-radius: 10px; border: 1px solid var(--glass-border); background: var(--surface-raised); transition: border-color 0.2s; }
	.team.lead { border-color: color-mix(in srgb, var(--accent) 55%, var(--glass-border)); }
	.team-name { display: inline-flex; align-items: center; gap: 0.4rem; font-size: 0.82rem; font-weight: 700; }
	.team-score { font-size: 1.35rem; font-variant-numeric: tabular-nums; }
	.team-detail { font-size: 0.74rem; color: var(--text-dim); }

	@media (max-width: 600px) {
		.player { grid-template-columns: 1fr 3rem; grid-template-rows: auto auto 3px; }
		.result { flex-basis: 100%; }
		.teams { grid-template-columns: 1fr; }
		.calc { grid-column: 1; grid-row: 2; }
		.total { grid-column: 2; grid-row: 1 / 3; }
		.board { padding: 0.75rem; }
	}
</style>
