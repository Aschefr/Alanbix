<script>
	import { t } from '$lib/i18nStore';

	export let mode = 'live'; // 'live' | 'results'
	export let selected;
	export let displayStandings = [];
	export let results = [];
	export let teams = [];
	export let useTeams = false;

	let expandedTeams = {};

	function toggleTeamExpand(entityId) {
		expandedTeams[entityId] = !expandedTeams[entityId];
		expandedTeams = expandedTeams;
	}
</script>

{#if mode === 'results'}
	{#if selected?.status === 'CLOSED' && results && results.length > 0}
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
				{#each results as r}
					{@const teamId = useTeams ? -r.entity_id : null}
					{@const teamObj = useTeams ? teams.find(t => t.id === teamId) : null}
					<!-- svelte-ignore a11y-click-events-have-key-events -->
					<!-- svelte-ignore a11y-no-static-element-interactions -->
					<div class="res-row {r.rank === 1 ? 'gold' : r.rank === 2 ? 'silver' : r.rank === 3 ? 'bronze' : ''} {useTeams && teamObj ? 'clickable-row' : ''}"
						on:click={() => { if(useTeams && teamObj) toggleTeamExpand(r.entity_id); }}>
						<span class="res-rank">{r.rank != null && r.rank <= 3 ? ['🥇','🥈','🥉'][r.rank-1] : r.rank != null ? '#' + r.rank : '—'}</span>
						<span class="res-name">
							{#if useTeams && teamObj}
								{expandedTeams[r.entity_id] ? '▼' : '▶'} 
							{/if}
							{r.name}
						</span>
						<span class="res-pts">{r.placement_pts}</span>
						<span class="res-pts">{r.score_pts}</span>
						<span class="res-pts">{r.participation_pts}</span>
						<span class="res-total">{r.total}</span>
					</div>
					{#if useTeams && teamObj && expandedTeams[r.entity_id]}
						<div class="team-members-standings-list">
							{#each teamObj.members || [] as m}
								<div class="tms-member-row">
									<span class="tms-name">👤 {m.username}</span>
									<div class="tms-stats">
										{#if r.placement_pts > 0}<span class="ls-bp ls-bp-place" title="Placement">🏅{r.placement_pts}</span>{/if}
										<span class="ls-bp ls-bp-parti" title="Participation">👤{r.participation_pts}</span>
										{#if r.score_pts > 0}<span class="ls-bp ls-bp-score" title="Score">⚡{r.score_pts}</span>{/if}
										<span class="tms-total-pts">{r.total || 0} pts</span>
									</div>
								</div>
							{/each}
						</div>
					{/if}
				{/each}
			</div>
		</div>
	{/if}
{:else}
	<div class="live-standings glass">
		<div class="section-title">
			<h3>📊 {$t(selected?.status === 'RUNNING' ? 'tourneys_standings_live' : 'tourneys_standings_final')}</h3>
			{#if selected?.status === 'RUNNING'}
				<span class="live-badge">⚡ LIVE</span>
			{:else}
				<span class="live-badge final-badge">✅ FINAL</span>
			{/if}
		</div>
		<div class="ls-config-summary">
			<span class="ls-cfg" title={$t('tourneys_pts_1st_tooltip')}>🥇 {selected?.config?.pts_winner ?? 1.5}</span>
			<span class="ls-cfg" title={$t('tourneys_pts_2nd_tooltip')}>🥈 {selected?.config?.pts_second ?? 1.3}</span>
			<span class="ls-cfg" title={$t('tourneys_pts_3rd_tooltip')}>🥉 {selected?.config?.pts_third ?? 1.0}</span>
			<span class="ls-cfg" title={$t('tourneys_pts_participation_tooltip')}>👤 {selected?.config?.pts_participation ?? 1.0}{$t('tourneys_per_match')}</span>
			<span class="ls-cfg" title={$t('tourneys_pts_bonus_tooltip')}>⚡ {selected?.config?.pts_per_match ?? 0.5} {$t('admin_tourneys_wizard_points_bonus')}</span>
		</div>
		<div class="ls-list">
			{#each displayStandings as entry}
				{@const teamId = useTeams ? -entry.id : null}
				{@const teamObj = useTeams ? teams.find(t => t.id === teamId) : null}
				<!-- svelte-ignore a11y-click-events-have-key-events -->
				<!-- svelte-ignore a11y-no-static-element-interactions -->
				<div class="ls-row {entry.rank && entry.rank <= 3 ? 'ls-top' : ''} {useTeams && teamObj ? 'clickable-row' : ''}"
					on:click={() => { if(useTeams && teamObj) toggleTeamExpand(entry.id); }}>
					<span class="ls-rank {entry.rank === 1 ? 'gold' : entry.rank === 2 ? 'silver' : entry.rank === 3 ? 'bronze' : ''}">{entry.rank || '—'}</span>
					<div class="ls-info">
						<span class="ls-name">
							{#if useTeams && teamObj}
								{expandedTeams[entry.id] ? '▼' : '▶'} 
							{/if}
							{entry.name}
						</span>
						<div class="ls-breakdown">
							{#if entry.placement_pts > 0}<span class="ls-bp ls-bp-place" title="Placement : top {entry.rank}">🏅{entry.placement_pts}</span>{/if}
							<span class="ls-bp ls-bp-parti" title={$t('tourneys_participation_tooltip_detail', { count: entry.matches_played, plural: entry.matches_played > 1 ? 's' : '', pts: selected?.config?.pts_participation ?? 1 })}>👤{entry.participation_pts}</span>
							{#if entry.score_pts > 0}<span class="ls-bp ls-bp-score" title={$t('tourneys_pts_bonus_detail_tooltip', { score: entry.cumulated_score, floor: entry.pts_per_match, ceiling: Math.round(entry.pts_per_match * 2 * 10) / 10 })}>⚡{entry.score_pts}</span>{/if}
						</div>
					</div>
					<span class="ls-pts">{entry.pts} pts</span>
				</div>
				{#if useTeams && teamObj && expandedTeams[entry.id]}
					<div class="team-members-standings-list">
						{#each teamObj.members || [] as m}
							<div class="tms-member-row">
								<span class="tms-name">👤 {m.username}</span>
								<div class="tms-stats">
									{#if entry.placement_pts > 0}<span class="ls-bp ls-bp-place" title="Placement">🏅{entry.placement_pts}</span>{/if}
									<span class="ls-bp ls-bp-parti" title="Participation">👤{entry.participation_pts}</span>
									{#if entry.score_pts > 0}<span class="ls-bp ls-bp-score" title="Score">⚡{entry.score_pts}</span>{/if}
									<span class="tms-total-pts">{entry.pts || 0} pts</span>
								</div>
							</div>
						{/each}
					</div>
				{/if}
			{/each}
		</div>
	</div>
{/if}

<style>
	/* Results Section */
	.results-section { padding: 1rem; border-radius: 12px; }
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

	/* Live Standings */
	.live-standings { padding: 1.2rem; border-radius: var(--radius-lg); border: 1px solid rgba(59,130,246,0.15); }
	.section-title { display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.75rem; }
	.section-title h3 { font-size: 0.8rem; font-weight: 700; text-transform: uppercase; letter-spacing: 0.04em; color: var(--text-dim); margin: 0; }
	.live-badge { font-size: 0.55rem; font-weight: 800; color: #10b981; background: rgba(16,185,129,0.1); padding: 0.15rem 0.5rem; border-radius: 20px; border: 1px solid rgba(16,185,129,0.2); animation: pulse-live 2s infinite; }
	.live-badge.final-badge { color: #3b82f6; background: rgba(59,130,246,0.1); border-color: rgba(59,130,246,0.2); animation: none; }
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

	/* Collapsible team members */
	.clickable-row { cursor: pointer; }
	.team-members-standings-list {
		display: flex;
		flex-direction: column;
		gap: 0.25rem;
		padding: 0.35rem 0.5rem 0.5rem 2rem;
		background: rgba(255, 255, 255, 0.01);
		border-left: 2px dashed var(--glass-border);
		margin-left: 1.2rem;
		margin-bottom: 0.25rem;
		border-radius: 0 0 8px 8px;
	}
	.tms-member-row {
		display: flex;
		align-items: center;
		justify-content: space-between;
		font-size: 0.72rem;
		padding: 0.2rem 0.4rem;
		color: var(--text-dim);
	}
	.tms-name {
		font-weight: 500;
	}
	.tms-stats {
		display: flex;
		align-items: center;
		gap: 0.35rem;
	}
	.tms-total-pts {
		font-weight: 700;
		color: var(--accent);
		min-width: 45px;
		text-align: right;
	}
</style>
