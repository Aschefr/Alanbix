<script>
	// "Consignes de l'IA": the editor of the admin-editable personality (split out of AdminSettingsTab.svelte)
	import { get } from 'svelte/store';
	import Icon from '$lib/components/Icon.svelte';
	import { t } from '$lib/i18nStore';

	let { value = '', onsave, onclose } = $props();
	let draft = $state(value);

	const DEFAULT_PROMPT_SECTIONS = [
		{ key: 'identity', icon: 'user' },
		{ key: 'context', icon: 'map' },
		{ key: 'style', icon: 'sparkles' },
		{ key: 'rules', icon: 'scale' },
	];

	function insertSection(sectionKey) {
		const sectionHeader = get(t)(`admin_prompt_modal_section_${sectionKey}`);
		draft += `\n${sectionHeader}\n`;
	}

	function portal(node) {
		document.body.appendChild(node);
		return {
			destroy() {
				if (node.parentNode) {
					node.parentNode.removeChild(node);
				}
			}
		};
	}
</script>

<svelte:window onkeydown={(e) => { if (e.key === 'Escape') onclose(); }} />

<div class="prompt-modal-overlay" use:portal onmousedown={(e) => { if (e.target === e.currentTarget) onclose(); }} role="dialog" aria-modal="true">
	<div class="prompt-modal">
		<!-- Header -->
		<div class="prompt-modal-header">
			<div class="prompt-modal-title-group">
				<span class="prompt-modal-icon"><Icon name="flask" size={22} /></span>
				<div>
					<h2 class="prompt-modal-title">{$t('admin_prompt_modal_title')}</h2>
					<p class="prompt-modal-subtitle">{$t('admin_prompt_modal_subtitle')}</p>
				</div>
			</div>
			<button class="prompt-modal-close" onclick={onclose} aria-label={$t('common_close')}><Icon name="x" size={18} /></button>
		</div>

		<!-- Body: two-column layout -->
		<div class="prompt-modal-body">
			<!-- LEFT: Textarea -->
			<div class="prompt-modal-editor">
				<div class="prompt-modal-char-count">{$t('admin_prompt_modal_char_count').replace('{count}', draft.length)}</div>
				<textarea
					class="prompt-modal-textarea"
					bind:value={draft}
					placeholder="{$t('admin_settings_ai_prompt_sys_placeholder')}"
					spellcheck="false"
				></textarea>
			</div>

			<!-- RIGHT: Guide panel -->
			<div class="prompt-modal-guide">
				<!-- Section blocks -->
				<div class="pmg-section">
					<h4 class="pmg-section-title"><Icon name="layers" size={15} /> {$t('admin_prompt_modal_guide_title')}</h4>
					<p class="pmg-intro">{$t('admin_prompt_modal_guide_intro')}</p>
					<div class="pmg-blocks">
						{#each DEFAULT_PROMPT_SECTIONS as sec}
							<div class="pmg-block">
								<div class="pmg-block-header">
									<span class="pmg-block-icon"><Icon name={sec.icon} size={16} /></span>
									<code class="pmg-block-tag">{$t(`admin_prompt_modal_section_${sec.key}`)}</code>
									<button class="pmg-insert-btn" onclick={() => insertSection(sec.key)} title="{$t('admin_prompt_modal_insert')}">
										+ {$t('admin_prompt_modal_insert')}
									</button>
								</div>
								<p class="pmg-block-desc">{$t(`admin_prompt_modal_section_${sec.key}_desc`)}</p>
							</div>
						{/each}
					</div>
				</div>

				<!-- Tips -->
				<div class="pmg-section pmg-tips">
					<h4 class="pmg-section-title">{$t('admin_prompt_modal_tip_title')}</h4>
					<ul class="pmg-tip-list">
						<li>{$t('admin_prompt_modal_tip_1')}</li>
						<li>{$t('admin_prompt_modal_tip_2')}</li>
						<li>{$t('admin_prompt_modal_tip_3')}</li>
						<li>{$t('admin_prompt_modal_tip_4')}</li>
					</ul>
				</div>
			</div>
		</div>

		<!-- Footer -->
		<div class="prompt-modal-footer">
			<button class="btn-secondary" onclick={onclose}>{$t('admin_prompt_modal_cancel')}</button>
			<button class="btn-primary" onclick={() => onsave(draft)}>{$t('admin_prompt_modal_save')}</button>
		</div>
	</div>
</div>

<style>
	.prompt-modal-overlay { position: fixed; inset: 0; background: rgba(0,0,0,0.6); backdrop-filter: blur(6px); z-index: 9998; display: flex; align-items: center; justify-content: center; padding: 1.5rem; }
	.prompt-modal { width: min(1100px, 100%); max-height: 90vh; display: flex; flex-direction: column; border-radius: 20px; border: 1px solid var(--glass-border); background: var(--bg-secondary); box-shadow: 0 30px 80px rgba(0,0,0,0.5); animation: pmSlideIn 0.25s cubic-bezier(0.16,1,0.3,1); overflow: hidden; }
	@keyframes pmSlideIn { from { opacity: 0; transform: translateY(20px) scale(0.97); } to { opacity: 1; transform: translateY(0) scale(1); } }
	.prompt-modal-header { display: flex; align-items: center; justify-content: space-between; padding: 1rem 1.4rem; background: rgba(139,92,246,0.08); border-bottom: 1px solid rgba(139,92,246,0.2); flex-shrink: 0; }
	.prompt-modal-title-group { display: flex; align-items: center; gap: 0.8rem; }
	.prompt-modal-icon { display: inline-flex; color: var(--accent); }
	.prompt-modal-title { font-size: 1rem; font-weight: 800; margin: 0; color: var(--text-main); }
	.prompt-modal-subtitle { font-size: 0.75rem; color: var(--text-muted); margin: 0.1rem 0 0; }
	.prompt-modal-close { background: none; border: 1px solid var(--glass-border); color: var(--text-dim); cursor: pointer; font-size: 1rem; width: 32px; height: 32px; border-radius: 8px; display: flex; align-items: center; justify-content: center; transition: all 0.15s; }
	.prompt-modal-close:hover { background: rgba(239,68,68,0.1); border-color: var(--danger); color: var(--danger); }
	.prompt-modal-body { display: grid; grid-template-columns: 1fr 340px; flex: 1; min-height: 0; overflow: hidden; }
	@media (max-width: 800px) { .prompt-modal-body { grid-template-columns: 1fr; } }
	/* Phone: one column that scrolls as a whole (the editor and the guide used to overlap), a near full-screen sheet */
	@media (max-width: 800px) {
		.prompt-modal-overlay { padding: 0.5rem; align-items: stretch; }
		.prompt-modal { max-height: none; height: 100%; width: 100%; border-radius: 16px; }
		.prompt-modal-header { padding: 0.8rem 1rem; }
		.prompt-modal-body { display: flex; flex-direction: column; overflow-y: auto; -webkit-overflow-scrolling: touch; }
		.prompt-modal-editor { flex: none; border-right: none; border-bottom: 1px solid var(--glass-border); padding: 0.75rem; }
		.prompt-modal-textarea { min-height: 280px; font-size: 0.85rem; }
		.prompt-modal-guide { flex: none; overflow: visible; padding: 0.75rem; }
		.prompt-modal-footer { padding: 0.7rem 1rem calc(0.7rem + var(--safe-bottom, 0px)); }
	}
	.prompt-modal-editor { display: flex; flex-direction: column; padding: 1rem; border-right: 1px solid var(--glass-border); min-height: 0; }
	.prompt-modal-char-count { font-size: 0.75rem; color: var(--text-muted); font-variant-numeric: tabular-nums; margin-bottom: 0.4rem; text-align: right; font-weight: 600; }
	.prompt-modal-textarea { flex: 1; width: 100%; min-height: 400px; max-height: 100%; background: var(--surface-sunken); border: 1px solid var(--glass-border); border-radius: 10px; padding: 0.8rem; color: var(--text-main); font-size: 0.8rem; font-family: monospace; line-height: 1.6; resize: none; transition: border-color 0.2s; }
	.prompt-modal-textarea:focus { outline: none; border-color: rgba(139,92,246,0.5); box-shadow: 0 0 0 3px rgba(139,92,246,0.08); }
	.prompt-modal-guide { overflow-y: auto; padding: 1rem; display: flex; flex-direction: column; gap: 0.8rem; background: rgba(139,92,246,0.02); }
	.pmg-section { background: var(--hover-tint); border: 1px solid var(--glass-border); border-radius: 12px; padding: 0.8rem 0.9rem; }
	.pmg-section-title { font-size: 0.8rem; font-weight: 800; color: var(--text-main); margin: 0 0 0.4rem; }
	.pmg-intro { font-size: 0.75rem; color: var(--text-dim); margin: 0 0 0.6rem; line-height: 1.4; }
	.pmg-blocks { display: flex; flex-direction: column; gap: 0.5rem; }
	.pmg-block { padding: 0.55rem 0.65rem; border-radius: 8px; background: var(--surface-sunken); border: 1px solid var(--glass-border); transition: border-color 0.15s; }
	.pmg-block:hover { border-color: rgba(139,92,246,0.3); }
	.pmg-block-header { display: flex; align-items: center; gap: 0.4rem; margin-bottom: 0.3rem; }
	.pmg-block-icon { font-size: 0.85rem; }
	.pmg-block-tag { font-size: 0.75rem; font-weight: 700; color: #a78bfa; background: rgba(139,92,246,0.1); padding: 0.1rem 0.4rem; border-radius: 4px; font-family: monospace; flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
	.pmg-insert-btn { font-size: 0.75rem; font-weight: 700; padding: 0.15rem 0.45rem; border-radius: 5px; border: 1px solid rgba(139,92,246,0.3); background: rgba(139,92,246,0.08); color: #a78bfa; cursor: pointer; transition: all 0.15s; white-space: nowrap; flex-shrink: 0; }
	.pmg-insert-btn:hover { background: rgba(139,92,246,0.2); border-color: #a78bfa; }
	.pmg-block-desc { font-size: 0.75rem; color: var(--text-muted); margin: 0; line-height: 1.4; }
	.pmg-tips { border-color: rgba(245,158,11,0.2); background: rgba(245,158,11,0.03); }
	.pmg-tips .pmg-section-title { color: #f59e0b; }
	.pmg-tip-list { margin: 0; padding-left: 1.1rem; display: flex; flex-direction: column; gap: 0.3rem; }
	.pmg-tip-list li { font-size: 0.75rem; color: var(--text-dim); line-height: 1.4; }
	.prompt-modal-footer { display: flex; justify-content: flex-end; gap: 0.6rem; padding: 0.8rem 1.2rem; border-top: 1px solid var(--glass-border); background: var(--hover-tint); flex-shrink: 0; }
</style>
