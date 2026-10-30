<script>
	import { createEventDispatcher } from 'svelte';
	import { api } from '$lib/api';
	import { t } from '$lib/i18nStore';
	import Icon from '$lib/components/Icon.svelte';

	export let selected;
	export let nameMap = {};
	export let isAdmin = false;

	const dispatch = createEventDispatcher();

	let data = null;
	let busy = false;
	let confirmingRollback = false;
	let loadedKey = '';

	$: cfg = selected?.config || {};
	$: enabled = cfg.phases === 'double' && !!cfg.stage;
	$: stage = cfg.stage;
	// reload whenever the bracket changes (a group score was entered, the knockout started...)
	$: signature = selected ? `${selected.id}|${stage}|${JSON.stringify((selected.bracket || []).filter(m => m.id.s >= 100).map(m => m.score))}` : '';
	$: if (enabled && signature !== loadedKey) load(signature);

	async function load(key) {
		loadedKey = key;
		try {
			data = await api.get(`/tournaments/${selected.id}/group-stage`);
		} catch (e) {
			data = null;
		}
	}

	// reactive: the names arrive after the first render
	$: label = (id) => nameMap[id] ?? nameMap[String(id)] ?? `#${Math.abs(id)}`;

	$: remaining = (selected?.bracket || []).filter(m => m.id.s >= 100 && !(m.score?.[0] !== null && m.score?.[1] !== null && (m.score?.[0] || m.score?.[1]))).length;

	async function startKnockout() {
		busy = true;
		try {
			await api.post(`/tournaments/${selected.id}/start-knockout`);
			dispatch('changed', { toast: $t('groups_toast_knockout_started') });
		} catch (e) {
			dispatch('changed', { error: e.message || e.detail });
		} finally {
			busy = false;
		}
	}

	async function rollback() {
		busy = true;
		confirmingRollback = false;
		try {
			await api.post(`/tournaments/${selected.id}/groups-rollback`);
			dispatch('changed', { toast: $t('groups_toast_rolled_back') });
		} catch (e) {
			dispatch('changed', { error: e.message || e.detail });
		} finally {
			busy = false;
		}
	}
</script>

{#if enabled && data}
	<section class="group-stage glass">
		<header class="gs-head">
			<span class="gs-ic"><Icon name="layers" size={18} /></span>
			<div class="gs-title">
				<h3>{$t('groups_title')}</h3>
				<span>{$t('groups_subtitle', { n: data.advancers })}</span>
			</div>
		</header>

		<div class="gs-grid">
			{#each data.groups as g}
				<div class="gs-table">
					<h4>{$t('spec_group_num', { group: String.fromCharCode(64 + g.group) })}</h4>
					<table>
						<thead>
							<tr>
								<th class="pos">#</th>
								<th class="name">{$t('groups_col_player')}</th>
								<th title={$t('groups_col_played_tip')}>{$t('groups_col_played')}</th>
								<th title={$t('groups_col_wins_tip')}>{$t('groups_col_wins')}</th>
								<th title={$t('groups_col_draws_tip')}>{$t('groups_col_draws')}</th>
								<th title={$t('groups_col_losses_tip')}>{$t('groups_col_losses')}</th>
								<th title={$t('groups_col_diff_tip')}>{$t('groups_col_diff')}</th>
								<th class="pts">{$t('groups_col_points')}</th>
							</tr>
						</thead>
						<tbody>
							{#each g.table as row}
								<tr class:qualified={row.position <= data.advancers}>
									<td class="pos">{row.position}</td>
									<td class="name">{label(row.entity_id)}</td>
									<td>{row.played}</td>
									<td>{row.wins}</td>
									<td>{row.draws}</td>
									<td>{row.losses}</td>
									<td>{row.diff > 0 ? `+${row.diff}` : row.diff}</td>
									<td class="pts">{row.points}</td>
								</tr>
							{/each}
						</tbody>
					</table>
				</div>
			{/each}
		</div>

		<footer class="gs-foot">
			{#if stage === 'groups'}
				{#if data.complete}
					<span class="gs-note ok"><Icon name="check-circle" size={15} /> {$t('groups_all_played')}</span>
					{#if isAdmin}
						<button class="btn-primary btn-ic" on:click={startKnockout} disabled={busy}>
							<Icon name="play" size={15} /> {$t('groups_start_knockout')}
						</button>
					{:else}
						<span class="gs-note">{$t('groups_waiting_admin')}</span>
					{/if}
				{:else}
					<span class="gs-note"><Icon name="clock" size={15} /> {$t('groups_remaining', { n: remaining })}</span>
				{/if}
			{:else if isAdmin}
				{#if confirmingRollback}
					<span class="gs-note">{$t('groups_rollback_confirm')}</span>
					<button class="btn-danger btn-ic" on:click={rollback} disabled={busy}>{$t('groups_rollback_yes')}</button>
					<button class="btn-secondary" on:click={() => confirmingRollback = false}>{$t('admin_settings_cancel')}</button>
				{:else}
					<button class="btn-secondary btn-ic" on:click={() => confirmingRollback = true} disabled={busy}>
						<Icon name="chevron-left" size={15} /> {$t('groups_back_to_groups')}
					</button>
				{/if}
			{/if}
		</footer>
	</section>
{/if}

<style>
	.group-stage { border-radius: var(--radius-lg); padding: 1rem 1.1rem; display: flex; flex-direction: column; gap: 0.9rem; margin-bottom: 1rem; }
	.gs-head { display: flex; align-items: center; gap: 0.8rem; }
	.gs-ic { display: inline-flex; align-items: center; justify-content: center; width: 36px; height: 36px; border-radius: 10px; background: var(--accent-soft); color: var(--accent); flex-shrink: 0; }
	.gs-title h3 { margin: 0; font-size: var(--fs-section); }
	.gs-title span { font-size: 0.8125rem; color: var(--text-dim); }
	.gs-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(320px, 1fr)); gap: 0.9rem; }
	.gs-table h4 { margin: 0 0 0.4rem; font-size: var(--fs-sub); color: var(--text-main); }
	table { width: 100%; border-collapse: collapse; font-size: 0.8125rem; }
	th { text-align: center; font-weight: 600; color: var(--text-dim); padding: 0.3rem 0.35rem; border-bottom: 1px solid var(--glass-border); white-space: nowrap; }
	td { text-align: center; padding: 0.35rem; border-bottom: 1px solid color-mix(in srgb, var(--glass-border) 60%, transparent); color: var(--text-main); }
	.name { text-align: left; max-width: 160px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
	.pos { width: 1.6rem; color: var(--text-dim); }
	.pts { font-weight: 800; color: var(--accent); }
	tr.qualified td { background: color-mix(in srgb, var(--success) 8%, transparent); }
	tr.qualified .pos { color: var(--success); font-weight: 800; }
	.gs-foot { display: flex; align-items: center; flex-wrap: wrap; gap: 0.6rem; justify-content: flex-end; }
	.gs-note { display: inline-flex; align-items: center; gap: 0.4rem; margin-right: auto; font-size: 0.8125rem; color: var(--text-dim); }
	.gs-note.ok { color: var(--success); }
	.btn-ic { display: inline-flex; align-items: center; gap: 0.4rem; }
	@media (max-width: 640px) {
		.gs-grid { grid-template-columns: minmax(0, 1fr); }
		.gs-foot .btn-primary, .gs-foot .btn-secondary, .gs-foot .btn-danger { flex: 1 1 auto; justify-content: center; }
	}
</style>
