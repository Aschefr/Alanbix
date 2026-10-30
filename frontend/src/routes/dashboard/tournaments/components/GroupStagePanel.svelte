<script>
	import { createEventDispatcher } from 'svelte';
	import { api } from '$lib/api';
	import { t } from '$lib/i18nStore';
	import Icon from '$lib/components/Icon.svelte';

	export let selected;
	export let isAdmin = false;

	const dispatch = createEventDispatcher();

	let data = null;
	let busy = false;
	let confirmingRollback = false;
	let loadedKey = '';

	$: cfg = selected?.config || {};
	$: enabled = cfg.phases === 'double' && !!cfg.stage;
	$: stage = cfg.stage;
	// reload whenever a group score changes or the stage changes
	$: signature = selected ? `${selected.id}|${stage}|${JSON.stringify((selected.bracket || []).filter(m => m.id.s >= 100).map(m => m.score))}` : '';
	$: if (enabled && signature !== loadedKey) load(signature);

	async function load(key) {
		loadedKey = key;
		try {
			data = await api.get(`/tournaments/${selected.id}/group-stage`);
			dispatch('loaded', data);
		} catch (e) {
			data = null;
		}
	}

	$: groupMatches = (selected?.bracket || []).filter(m => m.id.s >= 100);
	$: isPlayed = (m) => m.score?.[0] !== null && m.score?.[1] !== null && (m.score?.[0] || m.score?.[1]);
	$: total = groupMatches.length;
	$: played = groupMatches.filter(isPlayed).length;
	$: remaining = total - played;
	$: percent = total ? Math.round((played / total) * 100) : 0;

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
	<section class="group-bar glass">
		<span class="gs-ic"><Icon name="layers" size={18} /></span>
		<div class="gs-main">
			<div class="gs-title">
				<h3>{$t('groups_title')}</h3>
				<span class="gs-sub">{$t(data.advancers === 1 ? 'groups_subtitle_one' : 'groups_subtitle', { n: data.advancers })}</span>
			</div>
			{#if stage === 'groups'}
				<div class="gs-progress" title={$t('groups_remaining', { n: remaining })}>
					<div class="gs-bar"><div class="gs-fill" style="width: {percent}%"></div></div>
					<span class="gs-count">{played}/{total}</span>
				</div>
			{/if}
		</div>

		<div class="gs-actions">
			{#if stage === 'groups'}
				{#if data.complete}
					{#if isAdmin}
						<button class="btn-primary btn-ic" on:click={startKnockout} disabled={busy}>
							<Icon name="play" size={15} /> {$t('groups_start_knockout')}
						</button>
					{:else}
						<span class="gs-note ok"><Icon name="check-circle" size={15} /> {$t('groups_waiting_admin')}</span>
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
		</div>
	</section>
{/if}

<style>
	.group-bar { display: flex; align-items: center; gap: 0.9rem; padding: 0.7rem 1rem; border-radius: var(--radius-lg); margin-bottom: 0.9rem; flex-wrap: wrap; }
	.gs-ic { display: inline-flex; align-items: center; justify-content: center; width: 36px; height: 36px; border-radius: 10px; background: var(--accent-soft); color: var(--accent); flex-shrink: 0; }
	.gs-main { flex: 1 1 260px; min-width: 0; display: flex; flex-direction: column; gap: 0.4rem; }
	.gs-title { display: flex; align-items: baseline; flex-wrap: wrap; gap: 0.2rem 0.8rem; }
	.gs-title h3 { margin: 0; font-size: var(--fs-section); }
	.gs-sub { font-size: 0.8125rem; color: var(--text-dim); }
	.gs-progress { display: flex; align-items: center; gap: 0.6rem; }
	.gs-bar { flex: 1; min-width: 140px; max-width: 320px; height: 6px; border-radius: 999px; background: var(--surface-sunken); border: 1px solid var(--glass-border); box-sizing: content-box; overflow: hidden; }
	.gs-fill { height: 100%; background: var(--accent-solid); border-radius: 999px; transition: width 0.3s; }
	.gs-count { font-size: 0.8125rem; font-weight: 700; color: var(--text-dim); font-variant-numeric: tabular-nums; }
	.gs-actions { display: flex; align-items: center; flex-wrap: wrap; gap: 0.6rem; margin-left: auto; }
	.gs-note { display: inline-flex; align-items: center; gap: 0.4rem; font-size: 0.8125rem; color: var(--text-dim); }
	.gs-note.ok { color: var(--success); }
	.btn-ic { display: inline-flex; align-items: center; gap: 0.4rem; }
	@media (max-width: 640px) {
		/* phones keep the room for the groups: one slim line */
		.group-bar { padding: 0.45rem 0.7rem; gap: 0.5rem; margin-bottom: 0.5rem; }
		.gs-ic, .gs-sub { display: none; }
		.gs-actions { margin-left: 0; width: 100%; }
		.gs-actions .btn-primary, .gs-actions .btn-secondary, .gs-actions .btn-danger { flex: 1 1 auto; justify-content: center; }
	}
</style>
