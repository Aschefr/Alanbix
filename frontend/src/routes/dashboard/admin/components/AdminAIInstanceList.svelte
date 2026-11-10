<script>
	// The AI servers of the AI tab: order, address, model, key, test, and the recommended models of each.
	// A server that answers without the model it needs says so here: that is not a connection error.
	import { get } from 'svelte/store';
	import { api } from '$lib/api';
	import { t } from '$lib/i18nStore';
	import Icon from '$lib/components/Icon.svelte';
	import OllamaModelCatalog from '$lib/components/OllamaModelCatalog.svelte';

	let { config = $bindable(), statuses = [], models = [], onsave, onstatuses, onmodels, toast } = $props();

	// Embedding models cannot chat: a server with only those has no usable model
	const chatModels = (names) => (names || []).filter(m => !/embed/i.test(m));
	const has = (names, model) => names.some(n => n === model || n === `${model}:latest`);

	// What is wrong with a server that answers: no model at all, or not the one chosen ('' when fine)
	function modelProblem(inst, status) {
		if (!status?.online) return '';
		const names = chatModels(status.available_models);
		if (!names.length) return 'none';
		if (inst.model && !has(names, inst.model)) return 'missing';
		return '';
	}

	// The chosen model stays visible in the list even when the server lacks it
	function choices(inst, status) {
		const names = status?.available_models || models.map(m => m.name);
		return inst.model && !has(names, inst.model) ? [inst.model, ...names] : names;
	}

	async function useCatalogModel(idx, name) {
		config.ollama_instances[idx].model = name;
		await onstatuses();
		await onsave();
	}

	async function testInstance(idx) {
		const inst = config.ollama_instances[idx];
		if (!inst) return;
		const name = inst.label || inst.url;
		const res = await api.post('/ia/test-connection', { url: inst.url, api_key: inst.api_key || '' });
		if (res.status === 'ok' && !chatModels(res.models).length) {
			// Reached, but nothing to chat with: the catalog below opens to download a model
			toast(get(t)('admin_instance_test_no_model', { name }), 'info');
			onstatuses();
		} else if (res.status === 'ok') {
			toast(get(t)('admin_instance_test_ok', { name, ms: res.latency_ms }), 'success');
			onstatuses();
			onmodels();
		} else {
			toast(get(t)('admin_instance_test_failed', { name }), 'error');
		}
	}

	// API keys are write-only: the server keeps them and only says whether one is saved
	async function saveInstanceKey(idx) {
		const inst = config.ollama_instances[idx];
		if (!inst?.api_key?.trim()) return;
		await onsave();
		inst.has_api_key = true;
		inst.api_key = '';
		onstatuses();
		onmodels();
	}

	async function clearInstanceKey(idx) {
		const inst = config.ollama_instances[idx];
		inst.clear_api_key = true;
		await onsave();
		delete inst.clear_api_key;
		inst.has_api_key = false;
	}

	async function removeInstance(idx) {
		config.ollama_instances = config.ollama_instances.filter((_, i) => i !== idx);
		config.ollama_instances.forEach((inst, i) => inst.priority = i);
		await onsave();
	}

	async function moveInstance(idx, dir) {
		const arr = [...config.ollama_instances];
		const target = idx + dir;
		if (target < 0 || target >= arr.length) return;
		[arr[idx], arr[target]] = [arr[target], arr[idx]];
		arr.forEach((inst, i) => inst.priority = i);
		config.ollama_instances = arr;
		await onsave();
	}
</script>

{#each config.ollama_instances as inst, idx}
	{@const status = statuses.find(s => s.url === inst.url)}
	{@const problem = modelProblem(inst, status)}
	<div class="inst-row" class:disabled={!inst.enabled}>
		<div class="inst-prio">
			<button class="reorder-btn" onclick={() => moveInstance(idx, -1)} disabled={idx === 0}>▲</button>
			<span class="prio-num">{inst.priority ?? idx}</span>
			<button class="reorder-btn" onclick={() => moveInstance(idx, 1)} disabled={idx === config.ollama_instances.length - 1}>▼</button>
		</div>
		<div class="inst-status"><span class="status-dot" class:on={status?.online}></span></div>
		<div class="inst-main">
			<input type="text" class="inst-name-input" bind:value={inst.label} onchange={onsave} placeholder="{$t('admin_settings_instances_gpu_placeholder')}" />
			<div class="inst-meta">
				<input type="text" class="inst-url-input" bind:value={inst.url} onchange={onsave} placeholder="http://..." /><!-- i18n-ignore -->
				<select bind:value={inst.model} onchange={onsave} class="inst-model-select">
					<option value="">{$t('admin_ai_model_placeholder')}</option>
					{#each choices(inst, status) as mName}
						<option value={mName}>{mName}</option>
					{/each}
				</select>
				<span class="inst-key">
					<input type="password" class="inst-key-input" bind:value={inst.api_key} onchange={() => saveInstanceKey(idx)} autocomplete="off" spellcheck="false"
						placeholder={inst.has_api_key ? $t('admin_ai_api_key_saved') : $t('admin_ai_api_key_ph')} aria-label={$t('admin_ai_api_key')} />
					{#if inst.has_api_key && !inst.api_key}
						<button class="inst-btn-mini" onclick={() => clearInstanceKey(idx)} title={$t('admin_ai_api_key_remove')} aria-label={$t('admin_ai_api_key_remove')}><Icon name="trash" size={13} /></button>
					{/if}
				</span>
				{#if status?.online}
					<span class="inst-ping">{status.latency_ms}ms</span>
				{/if}
				{#if status?.avg_duration !== undefined && status?.avg_duration !== null}
					<span class="inst-ping" style="background: rgba(139, 92, 246, 0.15); color: #c084fc; border-color: rgba(139, 92, 246, 0.35);"><Icon name="clock" size={11} /> {status.avg_duration}s</span>
				{/if}
			</div>
		</div>
		<div class="inst-actions">
			<label class="toggle-switch-mini">
				<input type="checkbox" bind:checked={inst.enabled} onchange={onsave} />
				<span class="toggle-slider"></span>
			</label>
			<button class="inst-btn-mini" onclick={() => testInstance(idx)} title={$t('admin_ai_test_instance')} aria-label={$t('admin_ai_test_instance')}><Icon name="search" size={14} /></button>
			<button class="inst-btn-mini danger" onclick={() => removeInstance(idx)} title="{$t('admin_tourneys_tooltip_delete')}" aria-label="{$t('admin_tourneys_tooltip_delete')}"><Icon name="x" size={14} /></button>
		</div>
	</div>
	{#if problem}
		<p class="inst-warn" role="status"><Icon name="info" size={14} /> {problem === 'none' ? $t('admin_instance_no_model') : $t('admin_instance_model_missing', { model: inst.model })}</p>
	{/if}
	<OllamaModelCatalog url={inst.url} current={inst.model} open={!!problem} on:use={(e) => useCatalogModel(idx, e.detail)} on:installed={onstatuses} />
{:else}
	<div class="inst-empty">{$t("admin_settings_instances_empty")}</div>
{/each}

<style>
	.inst-row { display: flex; align-items: center; gap: 0.6rem; padding: 0.6rem 0.8rem; border-radius: 10px; background: var(--hover-tint); border: 1px solid transparent; transition: all 0.2s; margin-bottom: 0.4rem; }
	.inst-row:hover { background: var(--accent-soft); border-color: var(--glass-border); }
	.inst-row.disabled { opacity: 0.4; }
	.inst-prio { display: flex; flex-direction: column; align-items: center; gap: 1px; }
	.prio-num { font-size: 0.75rem; font-weight: 800; color: var(--accent); min-width: 1rem; text-align: center; }
	.reorder-btn { background: none; border: 1px solid var(--glass-border); border-radius: 4px; color: var(--text-dim); font-size: 0.75rem; padding: 0.05rem 0.2rem; cursor: pointer; line-height: 1; transition: all 0.15s; }
	.reorder-btn:hover:not(:disabled) { color: var(--accent); border-color: var(--accent); }
	.reorder-btn:disabled { opacity: 0.15; cursor: default; }
	.inst-status { font-size: 0.75rem; }
	.status-dot { display: inline-block; width: 10px; height: 10px; border-radius: 50%; background: var(--danger); }
	.status-dot.on { background: var(--success); box-shadow: 0 0 6px color-mix(in srgb, var(--success) 60%, transparent); }
	.inst-main { flex: 1; min-width: 0; }
	.inst-name-input { width: 100%; background: transparent; border: none; border-bottom: 1px solid var(--glass-border); color: var(--text-main); font-size: 0.8rem; font-weight: 700; padding: 0.1rem 0; }
	.inst-name-input:focus { border-color: var(--accent); outline: none; }
	.inst-meta { display: flex; align-items: center; flex-wrap: wrap; gap: 0.4rem; margin-top: 0.3rem; }
	.inst-key { display: inline-flex; align-items: center; gap: 0.25rem; flex: 0 1 190px; min-width: 120px; }
	.inst-key-input { flex: 1; min-width: 0; background: var(--surface-sunken); border: 1px solid var(--glass-border); border-radius: 6px; padding: 0.2rem 0.4rem; color: var(--text-dim); font-size: 0.75rem; }
	.inst-url-input { flex: 1; min-width: 80px; background: var(--surface-sunken); border: 1px solid var(--glass-border); border-radius: 6px; padding: 0.2rem 0.4rem; color: var(--text-dim); font-size: 0.75rem; font-family: monospace; }
	.inst-model-select { background: var(--surface-sunken); border: 1px solid var(--glass-border); border-radius: 6px; padding: 0.2rem 0.4rem; color: var(--text-main); font-size: 0.75rem; max-width: 120px; min-width: 80px; }
	.inst-model-select option { background: var(--bg-secondary); color: var(--text-main); }
	.inst-ping { display: inline-flex; align-items: center; gap: 0.25rem; font-size: 0.75rem; color: #10b981; font-weight: 700; padding: 0.1rem 0.35rem; background: rgba(16,185,129,0.1); border-radius: 4px; }
	.inst-actions { display: flex; align-items: center; gap: 0.3rem; }
	.inst-btn-mini { background: var(--hover-tint); border: 1px solid var(--glass-border); border-radius: 6px; width: 22px; height: 22px; display: flex; align-items: center; justify-content: center; cursor: pointer; font-size: 0.75rem; transition: all 0.15s; }
	.inst-btn-mini:hover { background: rgba(59,130,246,0.15); border-color: var(--accent); }
	.inst-btn-mini.danger:hover { background: rgba(239,68,68,0.2); border-color: var(--danger); }
	.inst-warn { display: flex; gap: 0.4rem; align-items: flex-start; margin: -0.1rem 0 0.4rem; padding: 0 0.8rem; font-size: 0.78rem; line-height: 1.45; color: var(--text-dim); overflow-wrap: anywhere; }
	.inst-warn :global(svg) { flex-shrink: 0; margin-top: 0.12rem; color: var(--accent); }
	.inst-empty { text-align: center; padding: 1.5rem; color: var(--text-muted); font-size: 0.8rem; }
	.toggle-switch-mini { position: relative; display: inline-block; width: 32px; height: 18px; cursor: pointer; flex-shrink: 0; }
	.toggle-switch-mini input { opacity: 0; width: 0; height: 0; position: absolute; pointer-events: none; }
	.toggle-switch-mini .toggle-slider { position: absolute; inset: 0; background: var(--surface-sunken); border: 1px solid var(--glass-border); border-radius: 18px; transition: all 0.25s cubic-bezier(0.16, 1, 0.3, 1); pointer-events: none; }
	.toggle-switch-mini .toggle-slider::before { content: ''; position: absolute; height: 12px; width: 12px; left: 2px; bottom: 2px; background: var(--text-dim); border-radius: 50%; transition: all 0.25s cubic-bezier(0.16, 1, 0.3, 1); }
	.toggle-switch-mini input:checked + .toggle-slider { background: var(--accent); border-color: var(--accent); box-shadow: 0 0 10px var(--accent-glow); }
	.toggle-switch-mini input:checked + .toggle-slider::before { transform: translateX(14px); background: #ffffff; }
</style>
