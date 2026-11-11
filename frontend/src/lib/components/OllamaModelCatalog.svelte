<script>
	// Recommended models for one AI server, with a download button. Shows nothing unless the server is
	// Ollama: it is the only one with a download command. Used by the AI settings and the guided setup.
	import { createEventDispatcher, onDestroy } from 'svelte';
	import { api } from '$lib/api';
	import { t, currentLang } from '$lib/i18nStore';
	import Icon from '$lib/components/Icon.svelte';
	import ModelComparison from '$lib/components/ModelComparison.svelte';

	export let url = '';
	export let current = ''; // model the instance uses now
	export let open = false;

	const dispatch = createEventDispatcher();

	let items = [];
	let supported = false;
	let comparison = null;
	let timer = null;
	let seq = 0;
	let requestError = '';

	// The address can be typed in the settings: wait for the end of the typing
	$: schedule(url);

	function schedule(target) {
		clearTimeout(timer);
		timer = setTimeout(() => load(target), 400);
	}

	async function load(target) {
		const mine = ++seq;
		clearTimeout(timer);
		if (!target) { supported = false; items = []; return; }
		try {
			const res = await api.get(`/ia/model-catalog?url=${encodeURIComponent(target)}`);
			if (mine !== seq) return;
			const justInstalled = res.models.filter(m => m.installed && items.some(i => i.name === m.name && !i.installed));
			supported = res.supported;
			items = res.models;
			comparison = res.comparison || null;
			justInstalled.forEach(m => dispatch('installed', m.name));
			if (items.some(m => m.downloading)) timer = setTimeout(() => load(url), 1000);
		} catch {
			if (mine === seq) { supported = false; items = []; }
		}
	}

	async function download(name) {
		requestError = '';
		try {
			await api.post('/ia/model-catalog/pull', { url, model: name });
			await load(url);
		} catch (e) {
			requestError = e.message;
		}
	}

	onDestroy(() => { seq++; clearTimeout(timer); });
</script>

{#if supported}
	<details class="catalog" {open}>
		<summary><Icon name="download" size={14} /> {$t('model_catalog_title')}</summary>
		<p class="help">{$t('model_catalog_help')}</p>
		<ul>
			{#each items as m (m.name)}
				<li>
					<div class="head">
						<code>{m.name}</code>
						<span class="tier" class:recommended={m.tier === 'recommended'}>{$t(`model_tier_${m.tier}`)}</span>
						<span class="size">{$t('model_catalog_size', { size: m.size_gb.toLocaleString($currentLang) })}</span>
					</div>
					<p class="desc">{$t(`model_tier_${m.tier}_desc`, { memory: m.memory_gb.toLocaleString($currentLang) })}</p>
					<p class="facts">
						<span>{$t('model_catalog_temperature', { value: m.temperature.toLocaleString($currentLang) })}</span>
						<span>{$t('model_catalog_speed', { seconds: m.typical_seconds.toLocaleString($currentLang) })}</span>
					</p>
					{#if m.downloading}
						<div class="progress" role="progressbar" aria-valuenow={m.percent} aria-valuemin="0" aria-valuemax="100" aria-label={m.name}>
							<div class="progress-fill" style="width: {m.percent}%"></div>
						</div>
						<p class="note" aria-live="polite">{$t('model_catalog_downloading', { percent: m.percent })}</p>
					{:else if m.installed}
						<div class="actions">
							{#if m.name === current}
								<span class="done"><Icon name="check-circle" size={15} /> {$t('model_catalog_in_use')}</span>
							{:else}
								<span class="note">{$t('model_catalog_installed')}</span>
								<button type="button" class="btn-secondary btn-sm" on:click={() => dispatch('use', m.name)}>{$t('model_catalog_use')}</button>
							{/if}
						</div>
					{:else}
						{#if m.error}
							<p class="error" role="alert"><Icon name="alert-triangle" size={14} /> {$t('model_catalog_error', { error: m.error })}</p>
						{/if}
						<div class="actions">
							<button type="button" class="btn-secondary btn-sm" on:click={() => download(m.name)}>
								<Icon name="download" size={15} /> {m.error ? $t('builtin_model_retry') : $t('model_catalog_download')}
							</button>
						</div>
					{/if}
				</li>
			{/each}
		</ul>
		{#if comparison}<ModelComparison data={comparison} />{/if}
		{#if requestError}
			<p class="error" role="alert"><Icon name="alert-triangle" size={14} /> {requestError}</p>
		{/if}
		<p class="note">{$t('model_catalog_where')}</p>
	</details>
{/if}

<style>
	.catalog { margin-top: 0.45rem; font-size: 0.85rem; }
	summary { display: inline-flex; align-items: center; gap: 0.4rem; cursor: pointer; font-size: 0.8rem; font-weight: 600; color: var(--text-dim); min-height: 28px; }
	summary:hover { color: var(--text-main); }
	.help { margin: 0.35rem 0 0.6rem; font-size: 0.8rem; line-height: 1.5; color: var(--text-dim); max-width: 68ch; }
	ul { list-style: none; margin: 0 0 0.5rem; padding: 0; display: flex; flex-direction: column; gap: 0.5rem; }
	li { display: flex; flex-direction: column; gap: 0.35rem; padding: 0.6rem 0.75rem; border: 1px solid var(--glass-border); border-radius: 8px; }
	.head { display: flex; flex-wrap: wrap; align-items: center; gap: 0.3rem 0.55rem; }
	code { font-size: 0.85rem; font-weight: 700; color: var(--text-main); overflow-wrap: anywhere; }
	.tier { font-size: 0.72rem; font-weight: 700; padding: 0.05rem 0.45rem; border-radius: 999px; border: 1px solid var(--glass-border); color: var(--text-dim); }
	.tier.recommended { color: var(--accent); border-color: var(--accent); }
	.size { font-size: 0.78rem; color: var(--text-muted); font-variant-numeric: tabular-nums; }
	.desc { margin: 0; font-size: 0.8rem; line-height: 1.45; color: var(--text-dim); max-width: 68ch; }
	.facts { display: flex; flex-wrap: wrap; gap: 0.15rem 1rem; margin: 0; font-size: 0.78rem; font-weight: 600; color: var(--text-main); font-variant-numeric: tabular-nums; }
	.actions { display: flex; flex-wrap: wrap; align-items: center; gap: 0.4rem 0.7rem; }
	.actions button { display: inline-flex; align-items: center; gap: 0.4rem; }
	.note { margin: 0; font-size: 0.78rem; color: var(--text-muted); font-variant-numeric: tabular-nums; }
	.done { display: inline-flex; align-items: center; gap: 0.4rem; font-size: 0.8rem; font-weight: 600; color: var(--success, var(--accent)); }
	.error { display: flex; align-items: flex-start; gap: 0.4rem; margin: 0; font-size: 0.8rem; color: var(--danger); line-height: 1.45; overflow-wrap: anywhere; }
	.error :global(svg) { flex-shrink: 0; margin-top: 0.15rem; }
	.progress { height: 6px; max-width: 420px; border-radius: 3px; background: var(--glass-border); overflow: hidden; }
	.progress-fill { height: 100%; background: var(--accent-solid); transition: width 0.4s ease-out; }
	@media (prefers-reduced-motion: reduce) { .progress-fill { transition: none; } }
</style>
