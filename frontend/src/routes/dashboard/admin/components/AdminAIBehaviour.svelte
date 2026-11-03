<script>
	// What the assistant may do: network tests, blocking, calling an admin, suggesting entries.
	import { createEventDispatcher } from 'svelte';
	import { t } from '$lib/i18nStore';
	import Icon from '$lib/components/Icon.svelte';

	export let config;

	const dispatch = createEventDispatcher();
</script>

<div class="ai-opts">
<!-- Network Tools -->
<div style="display: flex; align-items: center; justify-content: space-between; padding-top: 0.4rem; border-top: 1px solid var(--glass-border);">
	<span class="compact-label ai-opt-label" style="font-weight: 600;"><Icon name="globe" size={15} /> {$t('admin_settings_ai_tools')}</span>
	<label class="toggle-switch-mini">
		<input type="checkbox" bind:checked={config.network_tools_enabled} on:change={() => dispatch('change')} />
		<span class="toggle-slider"></span>
	</label>
</div>

<!-- Auto-moderation -->
<div style="display: flex; align-items: center; justify-content: space-between; padding-top: 0.4rem; border-top: 1px solid var(--glass-border);">
	<span class="compact-label ai-opt-label" style="font-weight: 600;"><Icon name="shield" size={15} /> {$t('admin_settings_ai_moderation')}</span>
	<label class="toggle-switch-mini">
		<input type="checkbox" bind:checked={config.auto_moderation_enabled} on:change={() => dispatch('change')} />
		<span class="toggle-slider"></span>
	</label>
</div>

<!-- Appel Admin Outil -->
<div style="display: flex; align-items: center; justify-content: space-between; padding-top: 0.4rem; border-top: 1px solid var(--glass-border);">
	<span class="compact-label ai-opt-label" style="font-weight: 600;"><Icon name="megaphone" size={15} /> {$t('ai_setting_call_admin_tool_enabled')}</span>
	<label class="toggle-switch-mini">
		<input type="checkbox" bind:checked={config.call_admin_enabled} on:change={() => dispatch('change')} />
		<span class="toggle-slider"></span>
	</label>
</div>

<!-- Appel Admin Bouton Manuel -->
<div style="display: flex; align-items: center; justify-content: space-between; padding-top: 0.4rem; border-top: 1px solid var(--glass-border);">
	<span class="compact-label ai-opt-label" style="font-weight: 600;"><Icon name="bell" size={15} /> {$t('ai_setting_call_admin_btn_enabled')}</span>
	<label class="toggle-switch-mini">
		<input type="checkbox" bind:checked={config.call_admin_button_enabled} on:change={() => dispatch('change')} />
		<span class="toggle-slider"></span>
	</label>
</div>
{#if config.call_admin_enabled || config.call_admin_button_enabled}
<div class="ai-antispam" style="padding: 0.6rem; margin-top: 0.4rem; background: rgba(255, 255, 255, 0.03); border: 1px dashed var(--glass-border); border-radius: 4px; display: flex; flex-direction: column; gap: 0.5rem;">
	<span class="compact-label" style="font-weight: 600; font-size: 0.85rem; letter-spacing: 0.05em; color: var(--text-muted);">
		{$t('ai_setting_call_admin_antispam_section_title')}
	</span>
	<div style="display: flex; flex-direction: column; gap: 0.4rem;">
		<label class="compact-label" style="display: flex; align-items: center; justify-content: space-between;">
			<span>{$t('ai_setting_call_admin_cooldown')}</span>
			<input type="number" min="1" max="1440" bind:value={config.call_admin_cooldown_minutes} on:change={() => dispatch('change')} style="width:70px;" />
		</label>
		<label class="compact-label" style="display: flex; align-items: center; justify-content: space-between;">
			<span>{$t('ai_setting_call_admin_daily')}</span>
			<input type="number" min="1" max="50" bind:value={config.call_admin_daily_limit} on:change={() => dispatch('change')} style="width:70px;" />
		</label>
		<label class="compact-label" style="display: flex; align-items: center; justify-content: space-between;">
			<span>{$t('ai_setting_call_admin_global_hourly')}</span>
			<input type="number" min="1" max="500" bind:value={config.call_admin_global_hourly_limit} on:change={() => dispatch('change')} style="width:70px;" />
		</label>
	</div>
</div>
{/if}

<!-- Suggestions RAG -->
<div style="display: flex; align-items: center; justify-content: space-between; padding-top: 0.4rem; border-top: 1px solid var(--glass-border);">
	<span class="compact-label ai-opt-label" style="font-weight: 600;"><Icon name="lightbulb" size={15} /> {$t('ai_setting_rag_suggestion_enabled')}</span>
	<label class="toggle-switch-mini">
		<input type="checkbox" bind:checked={config.rag_suggestion_enabled} on:change={() => dispatch('change')} />
		<span class="toggle-slider"></span>
	</label>
</div>
</div>

<style>
	.compact-label { font-size: 0.75rem; font-weight: 700; color: var(--text-dim);  margin: 0; }
	.toggle-switch-mini { position: relative; display: inline-block; width: 32px; height: 18px; cursor: pointer; flex-shrink: 0; }
	.toggle-switch-mini input { opacity: 0; width: 0; height: 0; position: absolute; pointer-events: none; }
	.toggle-switch-mini .toggle-slider { position: absolute; inset: 0; background: var(--surface-sunken); border: 1px solid var(--glass-border); border-radius: 18px; transition: all 0.25s cubic-bezier(0.16, 1, 0.3, 1); pointer-events: none; }
	.toggle-switch-mini .toggle-slider::before { content: ''; position: absolute; height: 12px; width: 12px; left: 2px; bottom: 2px; background: var(--text-dim); border-radius: 50%; transition: all 0.25s cubic-bezier(0.16, 1, 0.3, 1); }
	.toggle-switch-mini input:checked + .toggle-slider { background: var(--accent); border-color: var(--accent); box-shadow: 0 0 10px var(--accent-glow); }
	.toggle-switch-mini input:checked + .toggle-slider::before { transform: translateX(14px); background: #ffffff; }
	.ai-opts { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 0.6rem; }
	.ai-opts > div { border-top: none !important; padding-top: 0 !important; }
	.ai-opts > div:not(.ai-antispam) { padding: 0.65rem 0.9rem !important; border-radius: 10px; background: var(--hover-tint); border: 1px solid var(--glass-border) !important; }
	.ai-opts > .ai-antispam { grid-column: 1 / -1; margin-top: 0 !important; }
	.ai-antispam > div { display: grid !important; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 0.5rem 1.5rem !important; }
	@media (max-width: 900px) { .ai-antispam > div { grid-template-columns: minmax(0, 1fr); } }
	.ai-opt-label { display: inline-flex; align-items: center; gap: 0.5rem; }
	.ai-opt-label :global(svg) { color: var(--accent); flex-shrink: 0; }
	@media (max-width: 900px) { .ai-opts { grid-template-columns: minmax(0, 1fr); } }
</style>
