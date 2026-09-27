<script>
	import { createEventDispatcher } from 'svelte';
	import { t } from '$lib/i18nStore';
	import { formatPoints } from '$lib/utils';

	export let stats = { leaderboard: [] };
	export let teamLeaderboard = [];
	export let previousLeaderboard = [];

	const dispatch = createEventDispatcher();

	let lbMode = 'players'; // 'players' | 'teams'
	let expandedTeamIdx = -1;

	function getRankDelta(username, currentIdx) {
		if (!previousLeaderboard || previousLeaderboard.length === 0) return null;
		const prevIdx = previousLeaderboard.findIndex(p => p.username === username);
		if (prevIdx === -1) return { type: 'new', text: 'NEW' };
		if (prevIdx === currentIdx) return null;
		const diff = Math.abs(prevIdx - currentIdx);
		return prevIdx > currentIdx ? { type: 'up', text: '↑' + diff } : { type: 'down', text: '↓' + diff };
	}

	function handlePlayerClick(username) {
		dispatch('openPlayerStats', username);
	}
</script>

<section class="panel leaderboard-panel glass">
	<div class="panel-header">
		<h2>{$t('dash_lb_title')}</h2>
		<div class="lb-tabs">
			<button class="lb-tab {lbMode === 'players' ? 'active' : ''}" on:click={() => lbMode = 'players'}>{$t('dash_lb_players')}</button>
			<button class="lb-tab {lbMode === 'teams' ? 'active' : ''}" on:click={() => lbMode = 'teams'}>{$t('dash_lb_teams')}</button>
		</div>
	</div>
	<div class="leaderboard-list">
		{#if lbMode === 'players'}
			{#each (stats.leaderboard || []) as entry, i}
				<!-- svelte-ignore a11y-click-events-have-key-events -->
				<div class="lb-row {i < 3 ? 'top-3' : ''} clickable" on:click={() => handlePlayerClick(entry.username)}>
					<span class="lb-rank {i === 0 ? 'gold' : i === 1 ? 'silver' : i === 2 ? 'bronze' : ''}">{i + 1}</span>
					<div class="lb-avatar avatar-shape-{entry.avatar_shape || 'circle'}">
						{#if entry.avatar_url}
							<img src={entry.avatar_url} alt="" class="lb-avatar-img" />
						{:else}
							{entry.username ? entry.username[0].toUpperCase() : '?'}
						{/if}
					</div>
					<div class="lb-info">
						<span class="lb-name">{entry.username}</span>
						<span class="lb-sub">{entry.team_name || 'GamerTag'}</span>
					</div>
					{#if getRankDelta(entry.username, i)}
						<span class="lb-delta {getRankDelta(entry.username, i).type}">{getRankDelta(entry.username, i).text}</span>
					{/if}
					<div class="lb-score">
						<span class="score-val">{formatPoints(entry.points)}</span>
						<span class="score-label">Pts</span>
					</div>
				</div>
			{:else}
				<p class="text-dim text-sm" style="padding: 1rem;">{$t('dash_lb_no_players')}</p>
			{/each}
		{:else}
			{#each teamLeaderboard as team, i}
				<!-- svelte-ignore a11y-click-events-have-key-events -->
				<div class="lb-row {i < 3 ? 'top-3' : ''} clickable" on:click={() => expandedTeamIdx = expandedTeamIdx === i ? -1 : i}>
					<span class="lb-rank {i === 0 ? 'gold' : i === 1 ? 'silver' : i === 2 ? 'bronze' : ''}">{i + 1}</span>
					<div class="lb-avatar team-av">{team.team_name ? team.team_name[0].toUpperCase() : '?'}</div>
					<div class="lb-info">
						<span class="lb-name">{team.team_name}</span>
						<span class="lb-sub">{team.member_count}{$t('dash_lb_member_suffix', { plural: team.member_count > 1 ? 's' : '' })} {expandedTeamIdx === i ? '▲' : '▼'}</span>
					</div>
					<div class="lb-score">
						<span class="score-val">{formatPoints(team.score)}</span>
						<span class="score-label">Pts</span>
					</div>
				</div>
				{#if expandedTeamIdx === i && team.members}
					<div class="team-expand">
						{#each team.members.slice().sort((a,b) => b.points - a.points) as member}
							<!-- svelte-ignore a11y-click-events-have-key-events -->
							<div class="team-member-row clickable" on:click={() => handlePlayerClick(member.username)} style="cursor: pointer;">
								<span class="tm-name">👤 {member.username}</span>
								<span class="tm-pts">{formatPoints(member.points)} pts</span>
							</div>
						{/each}
					</div>
				{/if}
			{:else}
				<p class="text-dim text-sm" style="padding: 1rem;">{$t('dash_lb_no_teams')}</p>
			{/each}
		{/if}
	</div>
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
	}
	.panel-header h2 {
		font-size: 0.85rem;
		font-weight: 800;
		text-transform: uppercase;
		letter-spacing: 0.08em;
	}

	.leaderboard-panel {
		min-width: 0;
		height: 100%;
	}
	.leaderboard-list {
		flex-grow: 1;
		overflow-y: auto;
		padding: 0.5rem;
	}
	.lb-row {
		display: flex;
		align-items: center;
		gap: 0.6rem;
		padding: 0.6rem 0.5rem;
		border-radius: 10px;
		margin-bottom: 0.3rem;
		transition: background 0.15s;
		border-left: 3px solid transparent;
	}
	.lb-row:hover {
		background: var(--hover-tint);
	}
	.lb-row.top-3 {
		border-left-color: var(--accent);
		background: var(--accent-soft);
	}
	.lb-rank {
		width: 22px;
		height: 22px;
		min-width: 22px;
		display: flex;
		align-items: center;
		justify-content: center;
		font-size: 0.7rem;
		font-weight: 800;
		border-radius: 6px;
		background: var(--surface-raised);
		color: var(--text-dim);
		flex-shrink: 0;
	}
	.lb-rank.gold {
		background: rgba(255, 215, 0, 0.15);
		color: #ffd700;
	}
	.lb-rank.silver {
		background: rgba(192, 192, 192, 0.15);
		color: #c0c0c0;
	}
	.lb-rank.bronze {
		background: rgba(205, 127, 50, 0.15);
		color: #cd7f32;
	}
	.lb-avatar {
		width: 28px;
		height: 28px;
		min-width: 28px;
		border-radius: 50%;
		background: var(--bg-tertiary);
		display: flex;
		align-items: center;
		justify-content: center;
		font-size: 0.7rem;
		font-weight: 700;
		color: var(--accent);
		border: 1px solid var(--glass-border);
		flex-shrink: 0;
		overflow: hidden;
	}
	.lb-avatar-img {
		width: 100%;
		height: 100%;
		object-fit: cover;
		border-radius: 50%;
	}
	.lb-info {
		flex-grow: 1;
		min-width: 0;
	}
	.lb-name {
		font-size: 0.8rem;
		font-weight: 700;
		display: block;
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
	}
	.lb-sub {
		font-size: 0.55rem;
		color: var(--text-muted);
	}
	.lb-score {
		text-align: right;
	}
	.score-val {
		font-size: 0.85rem;
		font-weight: 800;
		color: var(--accent);
	}
	.score-label {
		font-size: 0.5rem;
		color: var(--text-muted);
		display: block;
	}

	.lb-delta {
		font-size: 0.6rem;
		font-weight: 800;
		padding: 0.1rem 0.3rem;
		border-radius: 4px;
		min-width: 1.5rem;
		text-align: center;
	}
	.lb-delta.up { color: #10b981; background: rgba(16,185,129,0.12); }
	.lb-delta.down { color: #ef4444; background: rgba(239,68,68,0.12); }
	.lb-delta.new { color: #f59e0b; background: rgba(245,158,11,0.12); font-size: 0.5rem; }

	.lb-row.clickable { cursor: pointer; }
	.lb-row.clickable:hover { background: var(--hover-tint); }
	.team-expand { padding: 0.3rem 0.5rem 0.5rem 2.5rem; border-bottom: 1px solid var(--glass-border); }
	.team-member-row { display: flex; justify-content: space-between; align-items: center; padding: 0.2rem 0.4rem; font-size: 0.7rem; border-radius: 4px; }
	.team-member-row:nth-child(odd) { background: rgba(59,130,246,0.04); }
	.tm-name { color: var(--text-secondary); }
	.tm-pts { font-weight: 700; color: var(--accent); font-size: 0.65rem; }

	.lb-tabs { display: flex; gap: 0.2rem; }
	.lb-tab {
		padding: 0.25rem 0.6rem;
		font-size: 0.6rem;
		font-weight: 700;
		border: 1px solid var(--glass-border);
		border-radius: 6px;
		background: transparent;
		color: var(--text-dim);
		cursor: pointer;
		transition: all 0.2s;
	}
	.lb-tab:hover { border-color: var(--accent); }
	.lb-tab.active { background: var(--accent-soft); border-color: var(--accent); color: var(--accent); }
	.team-av { background: rgba(139,92,246,0.2) !important; color: #a78bfa !important; border-color: rgba(139,92,246,0.3) !important; }
</style>
