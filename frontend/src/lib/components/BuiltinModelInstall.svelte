<script>
	// Install the built-in embedding model: button, progress, result. Used by the knowledge base
	// section of the admin and by the guided setup.
	import { createEventDispatcher, onDestroy, onMount } from 'svelte';
	import { api } from '$lib/api';
	import { t } from '$lib/i18nStore';
	import Icon from '$lib/components/Icon.svelte';

	const dispatch = createEventDispatcher();

	let state = null;
	let pollTimer = null;
	let starting = false;

	$: percent = state?.total ? Math.min(100, Math.round((state.downloaded / state.total) * 100)) : 0;
	$: busy = starting || state?.downloading;

	async function refresh() {
		try { state = await api.get('/ia/knowledge/builtin'); } catch {}
		return state;
	}

	function poll() {
		clearTimeout(pollTimer);
		pollTimer = setTimeout(async () => {
			const before = state?.installed;
			await refresh();
			starting = false;
			if (state?.downloading) poll();
			else if (state?.installed && !before) dispatch('installed');
		}, 1000);
	}

	async function install() {
		starting = true;
		try {
			state = await api.post('/ia/knowledge/builtin/install', {});
			poll();
		} catch (e) {
			starting = false;
			state = { ...(state || {}), error: e.message };
		}
	}

	onMount(async () => {
		await refresh();
		if (state?.downloading) poll();
	});
	onDestroy(() => clearTimeout(pollTimer));
</script>

{#if state?.installed}
	<p class="done" role="status"><Icon name="check-circle" size={16} /> {$t('builtin_model_installed')}</p>
{:else if state}
	<div class="install">
		<p class="why">{$t('builtin_model_why')}</p>
		{#if busy}
			<div class="progress" role="progressbar" aria-valuenow={percent} aria-valuemin="0" aria-valuemax="100" aria-label={$t('builtin_model_install')}>
				<div class="progress-fill" style="width: {percent}%"></div>
			</div>
			<p class="note" aria-live="polite">{$t('builtin_model_downloading', { percent })}</p>
		{:else}
			{#if state.error}
				<p class="error" role="alert"><Icon name="alert-triangle" size={14} /> {$t('builtin_model_error', { error: state.error })}</p>
			{/if}
			<div class="actions">
				<button type="button" class="btn-secondary btn-sm" on:click={install}>
					<Icon name="download" size={15} /> {state.error ? $t('builtin_model_retry') : $t('builtin_model_install')}
				</button>
				<span class="note">{$t('builtin_model_cost')}</span>
			</div>
		{/if}
	</div>
{/if}

<style>
	.install { display: flex; flex-direction: column; gap: 0.6rem; }
	.why { margin: 0; font-size: 0.85rem; line-height: 1.5; color: var(--text-dim); max-width: 68ch; }
	.actions { display: flex; flex-wrap: wrap; align-items: center; gap: 0.5rem 0.8rem; }
	.actions button { display: inline-flex; align-items: center; gap: 0.4rem; }
	.note { margin: 0; font-size: 0.78rem; color: var(--text-muted); font-variant-numeric: tabular-nums; }
	.done { display: flex; align-items: center; gap: 0.45rem; margin: 0; font-size: 0.85rem; font-weight: 600; color: var(--success, #16a34a); }
	.error { display: flex; align-items: flex-start; gap: 0.4rem; margin: 0; font-size: 0.82rem; color: var(--danger); line-height: 1.45; overflow-wrap: anywhere; }
	.error :global(svg) { flex-shrink: 0; margin-top: 0.15rem; }
	.progress { height: 6px; max-width: 420px; border-radius: 3px; background: var(--glass-border); overflow: hidden; }
	.progress-fill { height: 100%; background: var(--accent-solid); transition: width 0.4s ease-out; }
	@media (prefers-reduced-motion: reduce) { .progress-fill { transition: none; } }
</style>
