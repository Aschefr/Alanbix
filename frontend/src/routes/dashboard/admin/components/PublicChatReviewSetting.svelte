<script>
	// Public chat settings: what Alanbix may do when he reviews the general chat on his own
	// (backend ia_chat_review). Three choices, saved by the parent.
	import { createEventDispatcher } from 'svelte';
	import { t } from '$lib/i18nStore';

	export let mode = 'off';

	const dispatch = createEventDispatcher();
	const MODES = ['off', 'alert', 'mute'];
</script>

<div class="review-field">
	<span class="compact-label" id="pca-review-label">{$t('admin_public_chat_review_label')}</span>
	<div class="review-choices" role="radiogroup" aria-labelledby="pca-review-label">
		{#each MODES as m}
			<button type="button" role="radio" aria-checked={mode === m} class="review-choice" class:active={mode === m}
				on:click={() => { if (mode !== m) dispatch('change', m); }}>
				{$t(`admin_public_chat_review_${m}`)}
			</button>
		{/each}
	</div>
	<span class="review-hint">{$t('admin_public_chat_review_hint')}</span>
</div>

<style>
	.review-field { display: flex; flex-direction: column; gap: 0.35rem; }
	.review-choices { display: flex; flex-wrap: wrap; gap: 0.4rem; }
	.review-choice { padding: 0.45rem 0.8rem; border-radius: var(--radius-sm, 8px); border: 1px solid var(--glass-border); background: var(--glass-bg); color: var(--text-main); font-size: 0.8rem; font-weight: 600; cursor: pointer; transition: border-color 0.15s, background 0.15s; }
	.review-choice:hover { border-color: var(--accent); }
	.review-choice.active { border-color: var(--accent); background: var(--accent-soft); color: var(--accent); }
	.review-hint { font-size: 0.72rem; color: var(--text-dim); line-height: 1.4; }
</style>
