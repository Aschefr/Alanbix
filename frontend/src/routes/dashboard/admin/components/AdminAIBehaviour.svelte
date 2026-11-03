<script>
	// What the assistant may do: network tests, blocking, calling an admin, suggesting entries.
	// Each option says what it does, where it applies and what it needs.
	import { createEventDispatcher } from 'svelte';
	import { t } from '$lib/i18nStore';
	import Icon from '$lib/components/Icon.svelte';

	export let config;

	const dispatch = createEventDispatcher();
	const save = () => dispatch('change');

	const OPTIONS = [
		{ key: 'network_tools_enabled', icon: 'globe', label: 'admin_settings_ai_tools', desc: 'admin_settings_ai_tools_desc' },
		{ key: 'auto_moderation_enabled', icon: 'shield', label: 'admin_settings_ai_moderation', desc: 'admin_settings_ai_moderation_desc' },
		{ key: 'call_admin_enabled', icon: 'megaphone', label: 'ai_setting_call_admin_tool_enabled', desc: 'ai_setting_call_admin_tool_desc' },
		{ key: 'call_admin_button_enabled', icon: 'bell', label: 'ai_setting_call_admin_btn_enabled', desc: 'ai_setting_call_admin_btn_desc' },
		{ key: 'rag_suggestion_enabled', icon: 'lightbulb', label: 'ai_setting_rag_suggestion_enabled', desc: 'ai_setting_rag_suggestion_desc' },
	];
	const LIMITS = [
		{ key: 'call_admin_cooldown_minutes', label: 'ai_setting_call_admin_cooldown', max: 1440 },
		{ key: 'call_admin_daily_limit', label: 'ai_setting_call_admin_daily', max: 50 },
		{ key: 'call_admin_global_hourly_limit', label: 'ai_setting_call_admin_global_hourly', max: 500 },
	];
</script>

<p class="intro">{$t('admin_ai_behaviour_intro')}</p>
<div class="options">
	{#each OPTIONS as opt (opt.key)}
		<label class="option">
			<span class="option-icon"><Icon name={opt.icon} size={15} /></span>
			<span class="option-text">
				<span class="option-label">{$t(opt.label)}</span>
				<span class="option-desc">{$t(opt.desc)}</span>
			</span>
			<span class="toggle-switch-mini">
				<input type="checkbox" bind:checked={config[opt.key]} on:change={save} />
				<span class="toggle-slider"></span>
			</span>
		</label>
	{/each}
</div>

{#if config.call_admin_enabled || config.call_admin_button_enabled}
	<div class="limits">
		<h4>{$t('ai_setting_call_admin_antispam_section_title')}</h4>
		<p class="option-desc">{$t('ai_setting_call_admin_antispam_desc')}</p>
		<div class="limit-fields">
			{#each LIMITS as limit (limit.key)}
				<label class="limit">
					<span>{$t(limit.label)}</span>
					<input type="number" min="1" max={limit.max} bind:value={config[limit.key]} on:change={save} />
				</label>
			{/each}
		</div>
	</div>
{/if}

<style>
	.intro { margin: 0 0 0.7rem; font-size: 0.82rem; line-height: 1.5; color: var(--text-dim); max-width: 75ch; }
	.options { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 0.6rem; }
	.option { display: flex; align-items: flex-start; gap: 0.6rem; padding: 0.7rem 0.9rem; border-radius: 10px; background: var(--hover-tint); border: 1px solid var(--glass-border); cursor: pointer; }
	.option-icon { flex-shrink: 0; margin-top: 0.1rem; color: var(--accent); }
	.option-text { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 0.2rem; }
	.option-label { font-size: 0.82rem; font-weight: 700; color: var(--text-main); }
	.option-desc { font-size: 0.76rem; line-height: 1.45; color: var(--text-dim); }

	.limits { display: flex; flex-direction: column; gap: 0.35rem; margin-top: 0.6rem; padding: 0.7rem 0.9rem; border-radius: 10px; border: 1px solid var(--glass-border); }
	.limits h4 { margin: 0; font-size: 0.82rem; font-weight: 700; color: var(--text-main); }
	.limit-fields { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 0.5rem 1.5rem; margin-top: 0.3rem; }
	.limit { display: flex; align-items: center; justify-content: space-between; gap: 0.6rem; font-size: 0.76rem; font-weight: 600; color: var(--text-dim); }
	.limit input { width: 70px; flex-shrink: 0; }

	.toggle-switch-mini { position: relative; display: inline-block; width: 32px; height: 18px; cursor: pointer; flex-shrink: 0; margin-top: 0.1rem; }
	.toggle-switch-mini input { position: absolute; inset: 0; width: 100%; height: 100%; margin: 0; opacity: 0; cursor: pointer; }
	.toggle-switch-mini input:focus-visible + .toggle-slider { outline: 2px solid var(--accent); outline-offset: 2px; }
	.toggle-switch-mini .toggle-slider { position: absolute; inset: 0; background: var(--surface-sunken); border: 1px solid var(--glass-border); border-radius: 18px; transition: all 0.25s cubic-bezier(0.16, 1, 0.3, 1); pointer-events: none; }
	.toggle-switch-mini .toggle-slider::before { content: ''; position: absolute; height: 12px; width: 12px; left: 2px; bottom: 2px; background: var(--text-dim); border-radius: 50%; transition: all 0.25s cubic-bezier(0.16, 1, 0.3, 1); }
	.toggle-switch-mini input:checked + .toggle-slider { background: var(--accent); border-color: var(--accent); }
	.toggle-switch-mini input:checked + .toggle-slider::before { transform: translateX(14px); background: #ffffff; }

	@media (max-width: 900px) {
		.options, .limit-fields { grid-template-columns: minmax(0, 1fr); }
	}
</style>
