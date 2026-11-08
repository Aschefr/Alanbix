<script>
	// Model settings of the AI tab: temperature, context size and the advanced options.
	// Rendered inside the parent's two-column grid (each top-level block is one cell).
	import { t, currentLang } from '$lib/i18nStore';

	// Same value as RECOMMENDED_TEMPERATURE in backend/app/ia_model_catalog.py
	const RECOMMENDED_TEMPERATURE = 0.2;

	let { config = $bindable(), models = [], onchange } = $props();

	// Ollama's thinking, split by whether the task uses tools (measured on 2026-11-08, see the help texts)
	const THINKING = [
		{ key: 'think_chat', label: 'admin_settings_ai_think_chat', desc: 'admin_settings_ai_think_chat_desc' },
		{ key: 'think_tasks', label: 'admin_settings_ai_think_tasks', desc: 'admin_settings_ai_think_tasks_desc' },
	];
</script>

<!-- Temperature -->
<div>
	<div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.2rem;">
		<label class="compact-label">{$t('admin_settings_ai_temp')} <strong>{Number(config.temperature).toLocaleString($currentLang)}</strong></label>
		<span class="range-hint text-xs" style="color: var(--text-muted); font-size: 0.75rem;">
			{config.temperature <= 0.3 ? $t('admin_settings_ai_temp_precise') : config.temperature >= 0.7 ? $t('admin_settings_ai_temp_creative') : $t('admin_settings_ai_temp_balanced')}
		</span>
	</div>
	<input type="range" bind:value={config.temperature} onchange={onchange} min="0" max="1" step="0.1" class="range-accent" style="width: 100%;" />
	<div class="temp-advice">
		<span class="range-hint text-xs">{$t('admin_settings_ai_temp_hint', { value: RECOMMENDED_TEMPERATURE.toLocaleString($currentLang) })}</span>
		{#if config.temperature !== RECOMMENDED_TEMPERATURE}
			<button type="button" class="btn-secondary btn-sm" onclick={() => { config.temperature = RECOMMENDED_TEMPERATURE; onchange(); }}>{$t('admin_settings_ai_temp_apply', { value: RECOMMENDED_TEMPERATURE.toLocaleString($currentLang) })}</button>
		{/if}
	</div>
</div>

<!-- Context Window -->
<div>
	<div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.2rem;">
		<label class="compact-label">{$t('admin_settings_ai_context')} <strong>{$t('ai_tokens_count', { n: config.context_window })}</strong></label>
		<input 
			type="number" 
			bind:value={config.context_window} 
			onchange={onchange} 
			min="16384" 
			step="256"
			style="width: 80px; background: var(--surface-sunken); border: 1px solid var(--glass-border); border-radius: 6px; padding: 0.15rem 0.4rem; color: var(--text-main); font-size: 0.72rem; font-weight: 700; text-align: right;" 
		/>
	</div>
	<div class="ctx-presets-grid" style="display: flex; flex-wrap: wrap; gap: 0.25rem;">
		{#each [16384, 32768, 65536, 131072] as size}
			<button 
				type="button" 
				class="ctx-preset-mini-btn" 
				class:active={config.context_window === size}
				onclick={() => { config.context_window = size; onchange(); }}
			>
				{size >= 1024 ? (size / 1024) + 'K' : size}
			</button>
		{/each}
	</div>
	<span class="range-hint text-xs" style="color: var(--text-muted); font-size: 0.75rem; display: block; margin-top: 0.25rem; line-height: 1.2;">
		{$t('admin_settings_ai_context_hint')}
	</span>
</div>

<!-- Thinking -->
<div class="thinking">
	<span class="compact-label">{$t('admin_settings_ai_think_title')}</span>
	<span class="thinking-hint">{$t('admin_settings_ai_think_hint')}</span>
	<div class="thinking-options">
		{#each THINKING as opt (opt.key)}
			<label class="option">
				<span class="option-text">
					<span class="option-label">{$t(opt.label)}</span>
					<span class="option-desc">{$t(opt.desc)}</span>
				</span>
				<span class="toggle-switch-mini">
					<input type="checkbox" bind:checked={config[opt.key]} onchange={onchange} />
					<span class="toggle-slider"></span>
				</span>
			</label>
		{/each}
	</div>
</div>

<details class="ai-advanced">
	<summary>{$t('admin_settings_ai_advanced')}</summary>
	<p class="ai-advanced-hint">{$t('admin_settings_ai_advanced_hint')}</p>
	<div class="ai-advanced-body">
<!-- Embedding Model -->
<div>
	<label class="compact-label" style="margin-bottom: 0.2rem; display: block;">{$t('admin_settings_ai_rag_model')}</label>
	<select bind:value={config.embedding_model} onchange={onchange} class="inst-model-select-wide">
		<option value="">{$t('admin_ai_embed_auto')}</option>
		{#each models.filter(m => m.name.includes('embed')) as m}
			<option value={m.name}>{m.name}</option>
		{/each}
	</select>
</div>

<!-- Knowledge base relevance threshold -->
<div>
	<label class="compact-label" for="rag-min-score" style="margin-bottom: 0.2rem; display: block;">{$t('admin_settings_ai_rag_min_score')} : {Number(config.rag_min_score ?? 0.65).toFixed(2)}</label>
	<input id="rag-min-score" type="range" bind:value={config.rag_min_score} onchange={onchange} min="0.4" max="0.9" step="0.01" class="range-accent" style="width: 100%;" />
	<span class="range-hint text-xs" style="color: var(--text-muted); font-size: 0.75rem; display: block; margin-top: 0.25rem; line-height: 1.2;">
		{$t('admin_settings_ai_rag_min_score_hint')}
	</span>
</div>

<!-- Tool Calling Mode -->
<div>
	<label class="compact-label" style="margin-bottom: 0.2rem; display: block;">{$t('admin_settings_ai_tool_mode')}</label>
	<select bind:value={config.tool_calling_mode} onchange={onchange} class="inst-model-select-wide">
		<option value="stream_intercept">{$t('admin_settings_ai_tool_mode_intercept')}</option>
		<option value="legacy_double">{$t('admin_settings_ai_tool_mode_legacy')}</option>
		<option value="disabled">{$t('admin_settings_ai_tool_mode_disabled')}</option>
	</select>
	<span class="range-hint text-xs" style="color: var(--text-muted); font-size: 0.75rem; display: block; margin-top: 0.25rem; line-height: 1.2;">
		{$t('admin_settings_ai_tool_mode_hint')}
	</span>
</div>
	</div>
</details>

<style>
	.compact-label { font-size: 0.75rem; font-weight: 700; color: var(--text-dim);  margin: 0; }
	.ctx-preset-mini-btn { flex: 1; padding: 0.25rem 0.5rem; font-size: 0.75rem; font-weight: 600; border: 1px solid var(--glass-border); border-radius: 6px; background: var(--hover-tint); color: var(--text-dim); cursor: pointer; transition: all 0.15s; text-align: center; }
	.ctx-preset-mini-btn:hover { border-color: var(--accent); background: rgba(59,130,246,0.05); }
	.ctx-preset-mini-btn.active { background: var(--accent-soft); border-color: var(--accent); color: var(--accent); box-shadow: 0 0 8px var(--accent-glow); }
	.inst-model-select-wide { width: 100%; background: var(--surface-sunken); border: 1px solid var(--glass-border); border-radius: 8px; padding: 0.35rem 0.5rem; color: var(--text-main); font-size: 0.75rem; transition: all 0.2s; }
	.inst-model-select-wide:focus { border-color: var(--accent); outline: none; }
	.range-accent { width: 100%; accent-color: var(--accent); }
	.temp-advice { display: flex; flex-wrap: wrap; align-items: center; gap: 0.4rem 0.8rem; margin-top: 0.35rem; }
	.temp-advice .range-hint { flex: 1 1 240px; font-size: 0.75rem; line-height: 1.35; color: var(--text-muted); }
	.ai-advanced { grid-column: 1 / -1; }
	.ai-advanced summary { cursor: pointer; font-size: 0.8rem; font-weight: 700; color: var(--text-dim); min-height: 28px; }
	.ai-advanced-hint { margin: 0.2rem 0 0.6rem; font-size: 0.76rem; color: var(--text-muted); }
	.ai-advanced-body { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 0.8rem 1.2rem; }

	.thinking { grid-column: 1 / -1; display: flex; flex-direction: column; gap: 0.25rem; }
	.thinking-hint { font-size: 0.75rem; line-height: 1.35; color: var(--text-muted); }
	.thinking-options { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 0.6rem; margin-top: 0.2rem; }
	.option { display: flex; align-items: flex-start; gap: 0.6rem; padding: 0.7rem 0.9rem; border-radius: 10px; background: var(--hover-tint); border: 1px solid var(--glass-border); cursor: pointer; }
	.option-text { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 0.2rem; }
	.option-label { font-size: 0.82rem; font-weight: 700; color: var(--text-main); }
	.option-desc { font-size: 0.76rem; line-height: 1.45; color: var(--text-dim); }
	.toggle-switch-mini { position: relative; display: inline-block; width: 32px; height: 18px; cursor: pointer; flex-shrink: 0; margin-top: 0.1rem; }
	.toggle-switch-mini input { position: absolute; inset: 0; width: 100%; height: 100%; margin: 0; opacity: 0; cursor: pointer; }
	.toggle-switch-mini input:focus-visible + .toggle-slider { outline: 2px solid var(--accent); outline-offset: 2px; }
	.toggle-switch-mini .toggle-slider { position: absolute; inset: 0; background: var(--surface-sunken); border: 1px solid var(--glass-border); border-radius: 18px; transition: all 0.25s cubic-bezier(0.16, 1, 0.3, 1); pointer-events: none; }
	.toggle-switch-mini .toggle-slider::before { content: ''; position: absolute; height: 12px; width: 12px; left: 2px; bottom: 2px; background: var(--text-dim); border-radius: 50%; transition: all 0.25s cubic-bezier(0.16, 1, 0.3, 1); }
	.toggle-switch-mini input:checked + .toggle-slider { background: var(--accent); border-color: var(--accent); }
	.toggle-switch-mini input:checked + .toggle-slider::before { transform: translateX(14px); background: #ffffff; }
	/* after the two-column rules, so that it wins on a phone */
	@media (max-width: 900px) { .ai-advanced-body, .thinking-options { grid-template-columns: minmax(0, 1fr); } }
</style>
