<script>
	import { onMount } from 'svelte';
	import { api } from '$lib/api';
	import { t } from '$lib/i18nStore';
	import { renderMarkdown } from '$lib/markdown';
	import Icon from '$lib/components/Icon.svelte';

	const PROVIDERS = [
		{ id: 'openai', label: 'OpenAI', url: 'https://api.openai.com/v1' },
		{ id: 'mistral', label: 'Mistral AI', url: 'https://api.mistral.ai/v1' },
		{ id: 'openrouter', label: 'OpenRouter', url: 'https://openrouter.ai/api/v1' },
		{ id: 'groq', label: 'Groq', url: 'https://api.groq.com/openai/v1' },
		{ id: 'other', label: '', url: '' },
	];
	// Same presets as Settings > Artificial Intelligence > Model
	const CONTEXTS = [16384, 32768, 65536, 131072];

	let iaConfig = null;
	let existing = [];
	let mode = 'local'; // keep | none | local | online
	let localUrl = 'http://host.docker.internal:11434';
	let provider = 'openai';
	let onlineUrl = PROVIDERS[0].url;
	let apiKey = '';
	let testState = ''; // '' | testing | ok | fail
	let models = [];
	let model = '';
	let contextWindow = 16384;

	$: url = mode === 'online' ? onlineUrl : localUrl;
	$: if (mode || url || apiKey) resetTest();
	function resetTest() { testState = ''; models = []; model = ''; }

	function pickProvider(p) {
		provider = p.id;
		onlineUrl = p.url;
	}

	onMount(async () => {
		try {
			iaConfig = await api.get('/ia/config');
			existing = iaConfig.ollama_instances || [];
			contextWindow = Math.max(iaConfig.context_window || 16384, 16384);
			if (iaConfig.ollama_host && !existing.length) localUrl = iaConfig.ollama_host;
		} catch {}
		mode = existing.length ? 'keep' : 'local';
	});

	async function test() {
		testState = 'testing';
		try {
			const res = await api.post('/ia/test-connection', { url: url.trim(), api_key: mode === 'online' ? apiKey.trim() : '' });
			if (res.status === 'ok') {
				models = (res.models || []).filter(m => !/embed/i.test(m));
				model = models[0] || '';
				testState = 'ok';
			} else testState = 'fail';
		} catch { testState = 'fail'; }
	}

	/** Called by the setup page when the admin continues. */
	export async function save() {
		if (!iaConfig || mode === 'none') return true;
		const config = { ...iaConfig, context_window: contextWindow };
		if (mode !== 'keep') {
			if (testState !== 'ok' || !model) throw new Error($t('setup_ai_test_first'));
			const clean = url.trim().replace(/\/+$/, '');
			const others = existing.filter(i => (i.url || '').replace(/\/+$/, '') !== clean);
			const label = mode === 'online' ? (PROVIDERS.find(p => p.id === provider)?.label || $t('setup_ai_online')) : $t('setup_ai_local');
			const inst = { url: clean, label, model, enabled: true, priority: others.length };
			if (mode === 'online' && apiKey.trim()) inst.api_key = apiKey.trim();
			config.ollama_instances = [...others, inst];
		}
		await api.post('/ia/config', config);
		return true;
	}
</script>

<section class="block">
	<h3><Icon name="sparkles" size={16} /> {$t('setup_ai_what_title')}</h3>
	<div class="md">{@html renderMarkdown($t('setup_ai_what_md'))}</div>
</section>

<section class="block">
	<h3><Icon name="server" size={16} /> {$t('setup_ai_choice_title')}</h3>
	<div class="choices" role="radiogroup" aria-label={$t('setup_ai_choice_title')}>
		{#if existing.length}
			<label class="choice" class:active={mode === 'keep'}>
				<input type="radio" bind:group={mode} value="keep" />
				<span class="choice-title">{$t('setup_ai_keep')}</span>
				<span class="choice-desc">{existing.map(i => i.label || i.url).join(', ')}</span>
			</label>
		{/if}
		<label class="choice" class:active={mode === 'none'}>
			<input type="radio" bind:group={mode} value="none" />
			<span class="choice-title">{$t('setup_ai_none')}</span>
			<span class="choice-desc">{$t('setup_ai_none_desc')}</span>
		</label>
		<label class="choice" class:active={mode === 'local'}>
			<input type="radio" bind:group={mode} value="local" />
			<span class="choice-title">{$t('setup_ai_local')}</span>
			<span class="choice-desc">{$t('setup_ai_local_desc')}</span>
		</label>
		<label class="choice" class:active={mode === 'online'}>
			<input type="radio" bind:group={mode} value="online" />
			<span class="choice-title">{$t('setup_ai_online')}</span>
			<span class="choice-desc">{$t('setup_ai_online_desc')}</span>
		</label>
	</div>
</section>

{#if mode === 'local' || mode === 'online'}
	<section class="block">
		<h3><Icon name="link" size={16} /> {$t('setup_ai_connect_title')}</h3>
		{#if mode === 'local'}
			<details class="howto">
				<summary>{$t('setup_ai_local_howto')}</summary>
				<div class="md howto-body">{@html renderMarkdown($t('setup_ai_local_howto_md'))}</div>
			</details>
			<label class="field">
				<span class="field-label">{$t('setup_ai_local_url')}</span>
				<input type="url" bind:value={localUrl} spellcheck="false" />
				<span class="help">{$t('setup_ai_local_url_help')}</span>
			</label>
		{:else}
			<div class="seg">
				{#each PROVIDERS as p}
					<button class:active={provider === p.id} on:click={() => pickProvider(p)}>{p.label || $t('setup_ai_provider_other')}</button>
				{/each}
			</div>
			{#if provider === 'other'}
				<label class="field">
					<span class="field-label">{$t('setup_ai_online_url')}</span>
					<input type="url" bind:value={onlineUrl} placeholder="https://…/v1" spellcheck="false" /><!-- i18n-ignore -->
					<span class="help">{$t('setup_ai_online_url_help')}</span>
				</label>
			{/if}
			<label class="field">
				<span class="field-label">{$t('admin_ai_api_key')}</span>
				<input type="password" bind:value={apiKey} autocomplete="off" spellcheck="false" />
				<span class="help">{$t('setup_ai_key_help')}</span>
			</label>
			<p class="note"><Icon name="info" size={14} /> {$t('setup_ai_online_privacy')}</p>
		{/if}

		<div class="row">
			<button class="btn-secondary" on:click={test} disabled={testState === 'testing' || !url.trim()}>
				<Icon name="refresh" size={15} /> {testState === 'testing' ? $t('setup_ai_testing') : $t('setup_ai_test')}
			</button>
			{#if testState === 'ok'}<span class="status ok"><Icon name="check-circle" size={15} /> {$t('setup_ai_test_ok', { n: models.length })}</span>{/if}
			{#if testState === 'fail'}<span class="status fail"><Icon name="alert-triangle" size={15} /> {$t(mode === 'online' ? 'setup_ai_test_fail_online' : 'setup_ai_test_fail_local')}</span>{/if}
		</div>

		{#if testState === 'ok'}
			<label class="field">
				<span class="field-label">{$t('setup_ai_model')}</span>
				{#if models.length}
					<select bind:value={model}>{#each models as m}<option value={m}>{m}</option>{/each}</select>
				{:else}
					<input type="text" bind:value={model} spellcheck="false" />
				{/if}
				<span class="help">{$t(mode === 'online' ? 'setup_ai_model_help_online' : 'setup_ai_model_help_local')}</span>
			</label>
		{/if}
	</section>
{/if}

{#if mode !== 'none'}
	<section class="block">
		<h3><Icon name="layers" size={16} /> {$t('setup_ai_context_title')}</h3>
		<p class="help">{$t('setup_ai_context_help')}</p>
		<div class="seg ctx">
			{#each CONTEXTS as c}
				<button class:active={contextWindow === c} on:click={() => contextWindow = c}>{c / 1024}K</button>
			{/each}
		</div>
		<p class="help">{$t('setup_ai_context_hint')}</p>
	</section>
{/if}

<style>
	.block { display: flex; flex-direction: column; gap: 0.7rem; padding-bottom: 1.4rem; border-bottom: 1px solid var(--glass-border); }
	.block:last-of-type { border-bottom: none; padding-bottom: 0; }
	h3 { display: flex; align-items: center; gap: 0.5rem; margin: 0; font-size: 1rem; font-weight: 700; }
	h3 :global(svg) { color: var(--accent); }
	.help { margin: 0; font-size: 0.82rem; color: var(--text-dim); line-height: 1.5; max-width: 68ch; }
	.md { font-size: 0.88rem; line-height: 1.55; color: var(--text-dim); max-width: 68ch; }
	.md :global(ul), .md :global(ol) { margin: 0.3rem 0; padding-left: 1.2rem; }
	.md :global(p) { margin: 0.4rem 0; }
	.md :global(strong) { color: var(--text-main); }
	.md :global(code) { font-size: 0.82em; padding: 0.1em 0.35em; border-radius: 4px; background: var(--bg-tertiary); color: var(--text-main); overflow-wrap: anywhere; }
	.md :global(pre) { overflow-x: auto; padding: 0.6rem 0.8rem; border-radius: 8px; background: var(--bg-tertiary); }
	.md :global(pre code) { padding: 0; background: none; }
	.md :global(a) { color: var(--accent); }

	.choices { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 0.6rem; }
	@media (max-width: 600px) {
		.choices { grid-template-columns: 1fr; }
	}
	.choice { position: relative; display: flex; flex-direction: column; gap: 0.25rem; padding: 0.8rem 0.9rem; border: 1px solid var(--glass-border); border-radius: var(--radius-md); cursor: pointer; transition: border-color 0.15s, background 0.15s; }
	.choice:hover { border-color: var(--text-muted); }
	.choice.active { border-color: var(--accent); background: color-mix(in srgb, var(--accent) 6%, transparent); }
	.choice input { position: absolute; opacity: 0; pointer-events: none; }
	.choice:focus-within { outline: 2px solid var(--accent); outline-offset: 2px; }
	.choice-title { font-weight: 700; font-size: 0.92rem; }
	.choice-desc { font-size: 0.8rem; color: var(--text-dim); line-height: 1.45; overflow-wrap: anywhere; }

	.field { display: flex; flex-direction: column; gap: 0.4rem; max-width: 520px; }
	.field-label { font-weight: 600; font-size: 0.9rem; }
	.row { display: flex; gap: 0.7rem; flex-wrap: wrap; align-items: center; }
	.row .btn-secondary { display: inline-flex; align-items: center; gap: 0.4rem; color: var(--text-main); }
	.status { display: inline-flex; align-items: center; gap: 0.4rem; font-size: 0.85rem; font-weight: 600; }
	.status.ok { color: var(--success, #16a34a); }
	.status.fail { color: color-mix(in srgb, var(--warning) 70%, var(--text-main)); }
	.note { display: flex; gap: 0.4rem; align-items: flex-start; margin: 0; font-size: 0.8rem; color: var(--text-dim); line-height: 1.45; max-width: 68ch; }
	.note :global(svg) { flex-shrink: 0; margin-top: 0.15rem; }

	.howto { border: 1px solid var(--glass-border); border-radius: var(--radius-md); background: var(--surface-sunken); }
	.howto summary { cursor: pointer; padding: 0.65rem 0.9rem; font-weight: 600; font-size: 0.88rem; }
	.howto-body { padding: 0 0.9rem 0.8rem; }

	.seg { display: flex; flex-wrap: wrap; gap: 0.3rem; padding: 0.25rem; border-radius: 10px; background: var(--surface-sunken); border: 1px solid var(--glass-border); align-self: flex-start; max-width: 100%; }
	.seg button { border: none; background: transparent; color: var(--text-dim); font: inherit; font-size: 0.85rem; font-weight: 600; padding: 0.4rem 0.75rem; border-radius: 7px; cursor: pointer; font-variant-numeric: tabular-nums; }
	.seg button:hover:not(.active) { color: var(--text-main); }
	.seg button.active { background: var(--accent-solid); color: white; }
</style>
