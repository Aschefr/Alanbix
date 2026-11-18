<script>
	// Top bar of the "tree in large" layout (desktop): tournament name, then what the full page showed at all times
	import { createEventDispatcher } from 'svelte';
	import Icon from '$lib/components/Icon.svelte';
	import { t } from '$lib/i18nStore';

	export let selected;
	export let gameName = '';
	export let playerCount = 0;
	export let tournamentCount = 0;
	export let hasStandings = false;
	export let standingsShown = false;
	export let isAdmin = false;

	const dispatch = createEventDispatcher();
</script>

<div class="tree-bar glass">
	<!-- A labelled button: a bare burger icon did not say "the other tournaments are here" -->
	<button class="tree-list-btn" on:click={() => dispatch('list')} title={$t('tourneys_switch_hint')}>
		<Icon name="trophy" size={14} />
		<span>{$t('tourneys_title')}</span>
		<span class="tree-count">{tournamentCount}</span>
		<Icon name="chevron-down" size={13} />
	</button>
	<span class="tree-name">{selected.name}</span>
	<span class="tree-status {selected.status.toLowerCase()}">
		{selected.status === 'RUNNING' ? $t('tourneys_status_running') : selected.status === 'CLOSED' ? $t('tourneys_status_closed') : $t('tourneys_status_done')}
	</span>
	<span class="tree-game">{gameName}</span>
	<div class="tree-actions">
		<button class="tree-chip" on:click={() => dispatch('rules')} title={$t('tourneys_mobile_rules_info')}>
			<Icon name="info" size={13} /> <span>{$t('tourneys_tab_rules')}</span>
		</button>
		<button class="tree-chip" on:click={() => dispatch('players')} title={$t('tourneys_mobile_players_teams')}>
			<Icon name="users" size={13} /> <span>{$t('dash_stat_players')} ({playerCount})</span>
		</button>
		{#if hasStandings}
			<button class="tree-chip" class:on={standingsShown} aria-pressed={standingsShown} on:click={() => dispatch('standings')} title={$t('tourneys_show_standings')}>
				<Icon name="trophy" size={13} /> <span>{$t('tourneys_show_standings')}</span>
			</button>
		{/if}
		{#if isAdmin}
			<button class="tree-chip admin" on:click={() => dispatch('admin')} title={$t('nav_administration')}>
				<Icon name="gear" size={13} /> <span>{$t('tourneys_mobile_admin_chip')}</span>
			</button>
		{/if}
		<button class="tree-chip full" on:click={() => dispatch('fullView')} title={$t('tourneys_full_view_hint')}>
			<Icon name="minimize" size={13} /> <span>{$t('tourneys_btn_full_view')}</span>
		</button>
	</div>
</div>

<style>
	.tree-bar { display: flex; align-items: center; gap: 0.7rem; padding: 0.45rem 0.6rem; border-radius: var(--radius-md); flex-shrink: 0; min-width: 0; }
	.tree-list-btn { display: inline-flex; align-items: center; gap: 0.4rem; flex-shrink: 0; padding: 0.4rem 0.7rem; border-radius: 8px; border: 1px solid var(--accent); background: var(--accent-soft); color: var(--accent); font-size: 0.8rem; font-weight: 700; cursor: pointer; white-space: nowrap; }
	.tree-list-btn:hover { background: var(--accent); color: #fff; }
	.tree-count { min-width: 1.25rem; padding: 0 0.3rem; border-radius: 999px; background: var(--accent); color: #fff; font-size: 0.7rem; line-height: 1.25rem; text-align: center; }
	.tree-list-btn:hover .tree-count { background: #fff; color: var(--accent); }
	.tree-name { min-width: 0; color: var(--text-main); font-size: 1.05rem; font-weight: 800; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
	.tree-status { flex-shrink: 0; padding: 0.2rem 0.6rem; border-radius: 20px; font-size: 0.72rem; font-weight: 700; }
	.tree-status.running { background: #1d4ed8; color: #ffffff; border: 1px solid #3b82f6; }
	.tree-status.done { background: #334155; color: #e2e8f0; border: 1px solid #64748b; }
	.tree-status.closed { background: #065f46; color: #d1fae5; border: 1px solid #10b981; }
	.tree-game { color: var(--text-dim); font-size: 0.8rem; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; flex-shrink: 1; min-width: 0; }
	.tree-actions { display: flex; align-items: center; gap: 0.4rem; margin-left: auto; flex-shrink: 0; }
	.tree-chip { display: inline-flex; align-items: center; gap: 0.35rem; padding: 0.4rem 0.7rem; border-radius: 8px; border: 1px solid var(--glass-border); background: var(--glass-bg); color: var(--text-main); font-size: 0.78rem; font-weight: 600; cursor: pointer; white-space: nowrap; }
	.tree-chip:hover, .tree-chip.on { border-color: var(--accent); color: var(--accent); background: var(--accent-soft); }
	@media (max-width: 1250px) {
		.tree-game { display: none; }
		.tree-chip span { display: none; }
		.tree-chip { padding: 0.45rem 0.55rem; }
	}
</style>
