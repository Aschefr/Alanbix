<script>
	// Home page, "Tournaments" tab: one card per tournament (where it stands, the player's next match)
	// instead of a cropped copy of the bracket; the bracket itself is one click away, in large.
	import Icon from '$lib/components/Icon.svelte';
	import { t } from '$lib/i18nStore';
	import { mediaThumb } from '$lib/config';

	export let tournaments = [];
	export let games = [];
	export let myMatches = [];
	export let user = null;

	const ORDER = { RUNNING: 0, OPEN: 1, DONE: 2, CLOSED: 3 };
	$: sorted = [...(tournaments || [])].sort((a, b) => (ORDER[a.status] ?? 9) - (ORDER[b.status] ?? 9));

	function progress(tourney) {
		const matches = (Array.isArray(tourney.bracket) ? tourney.bracket : []).filter(m => !(m.p || []).includes(-1));
		const done = matches.filter(m => Array.isArray(m.score) && m.score.length > 0 && m.score.every(s => s !== null && s !== undefined) && m.score.some(s => s > 0)).length;
		return { done, total: matches.length, pct: matches.length ? Math.round((done / matches.length) * 100) : 0 };
	}

	$: cards = sorted.map(tourney => {
		const game = (games || []).find(g => g.id === tourney.game_id);
		const players = tourney.participants || [];
		return {
			tourney,
			gameName: game?.name || '',
			image: mediaThumb(game?.image_url, 160),
			players: players.length,
			joined: players.some(p => p.user_id === user?.id),
			next: (myMatches || []).find(m => m.tournament_id === tourney.id) || null,
			progress: progress(tourney)
		};
	});

	const statusKey = { OPEN: 'tourneys_status_open', RUNNING: 'tourneys_status_running', DONE: 'tourneys_status_done', CLOSED: 'tourneys_status_closed' };
</script>

<div class="tc-grid">
	{#each cards as c (c.tourney.id)}
		<a class="tc-card" class:mine={!!c.next} class:finished={c.tourney.status === 'DONE' || c.tourney.status === 'CLOSED'} href="/dashboard/tournaments?select={c.tourney.id}">
			<span class="tc-thumb" style={c.image ? `background-image: url(${c.image})` : ''} aria-hidden="true"></span>
			<span class="tc-body">
				<span class="tc-head">
					<span class="tc-name">{c.tourney.name}</span>
					<span class="tc-status {c.tourney.status.toLowerCase()}">{$t(statusKey[c.tourney.status] || 'tourneys_status_done')}</span>
				</span>
				<span class="tc-meta">{c.gameName} · {$t('dash_sum_players', { n: c.players })}</span>

				{#if c.tourney.status === 'RUNNING'}
					<span class="tc-progress" title={$t('dash_sum_progress', { done: c.progress.done, total: c.progress.total })}>
						<span class="tc-bar"><span class="tc-fill" style="width: {c.progress.pct}%"></span></span>
						<span class="tc-count">{$t('dash_sum_progress', { done: c.progress.done, total: c.progress.total })}</span>
					</span>
				{/if}

				<span class="tc-foot">
					{#if c.next}
						<span class="tc-mine"><Icon name="swords" size={13} /> {$t('dash_sum_your_turn')} · {!c.next.is_ffa && c.next.opponent_name ? c.next.opponent_name : c.next.round_label}</span>
					{:else if c.tourney.status === 'OPEN'}
						<span class="tc-note">{c.joined ? $t('dash_joined_waiting') : $t('dash_sum_open')}</span>
					{:else if c.tourney.status === 'RUNNING'}
						<span class="tc-note">{c.joined ? $t('dash_sum_no_match') : $t('dash_sum_watching')}</span>
					{:else}
						<span class="tc-note">{$t('dash_sum_finished')}</span>
					{/if}
					<!-- the whole card opens the bracket: a label is only worth its room when it says something else -->
					<span class="tc-go" title={$t('mobile_match_view_bracket')}>{#if c.tourney.status === 'OPEN' && !c.joined}{$t('tourneys_btn_join_text')}{/if} <Icon name="chevron-right" size={15} /></span>
				</span>
			</span>
		</a>
	{:else}
		<p class="tc-empty">{$t('dash_no_tournament')}</p>
	{/each}
</div>

<style>
	.tc-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(320px, 1fr)); gap: 0.75rem; align-content: start; padding: 0.25rem; overflow-y: auto; }
	.tc-card { display: flex; gap: 0.85rem; padding: 0.75rem; border-radius: var(--radius-md); border: 1px solid var(--glass-border); background: var(--glass-bg); color: var(--text-main); text-decoration: none; min-width: 0; transition: border-color 0.15s, transform 0.15s; }
	.tc-card:hover { border-color: var(--accent); transform: translateY(-1px); }
	.tc-card.mine { border-color: var(--accent); background: var(--accent-soft); }
	.tc-card.finished { opacity: 0.7; }
	.tc-thumb { flex-shrink: 0; width: 72px; align-self: stretch; min-height: 72px; border-radius: 8px; background-color: var(--surface-sunken); background-size: cover; background-position: center; }
	.tc-body { display: flex; flex-direction: column; gap: 0.35rem; min-width: 0; flex: 1; }
	.tc-head { display: flex; align-items: center; justify-content: space-between; gap: 0.5rem; }
	.tc-name { font-family: var(--font-title); font-weight: 800; font-size: 0.95rem; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
	.tc-status { flex-shrink: 0; padding: 0.1rem 0.5rem; border-radius: 20px; font-size: 0.68rem; font-weight: 700; }
	.tc-status.open { background: #166534; color: #dcfce7; }
	.tc-status.running { background: #1d4ed8; color: #fff; }
	.tc-status.done, .tc-status.closed { background: #334155; color: #e2e8f0; }
	.tc-meta { font-size: 0.78rem; color: var(--text-dim); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
	.tc-progress { display: flex; align-items: center; gap: 0.6rem; }
	.tc-bar { flex: 1; height: 6px; border-radius: 999px; background: var(--surface-sunken); overflow: hidden; }
	.tc-fill { display: block; height: 100%; border-radius: 999px; background: var(--accent); }
	.tc-count { font-size: 0.72rem; color: var(--text-dim); white-space: nowrap; font-variant-numeric: tabular-nums; }
	.tc-foot { display: flex; align-items: center; justify-content: space-between; gap: 0.5rem; margin-top: auto; padding-top: 0.15rem; }
	.tc-mine { display: inline-flex; align-items: center; gap: 0.3rem; font-size: 0.8rem; font-weight: 700; color: var(--accent); min-width: 0; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
	.tc-note { font-size: 0.78rem; color: var(--text-dim); min-width: 0; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
	.tc-go { display: inline-flex; align-items: center; gap: 0.15rem; flex-shrink: 0; font-size: 0.78rem; font-weight: 700; color: var(--accent); }
	.tc-empty { color: var(--text-dim); font-size: 0.85rem; padding: 1rem; }
</style>
