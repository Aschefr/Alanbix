<script>
	import { onMount } from 'svelte';
	import { api } from '$lib/api';
	import { t } from '$lib/i18nStore';
	import { renderMarkdown } from '$lib/markdown';
	import Icon from '$lib/components/Icon.svelte';
	import BuiltinModelInstall from '$lib/components/BuiltinModelInstall.svelte';

	// Questions the Infos page template does not cover; the admin answers those that apply
	const QUESTIONS = ['contact', 'gear', 'parking', 'sleep'];
	let answers = {};
	let existing = 0;

	async function loadCount() {
		try { existing = (await api.get('/ia/knowledge')).length; } catch {}
	}
	onMount(loadCount);

	/** Called by the setup page when the admin continues: each answer becomes an entry. */
	export async function save() {
		for (const id of QUESTIONS) {
			const answer = (answers[id] || '').trim();
			if (!answer) continue;
			await api.post('/ia/upload-document', { content: `Q: ${$t(`setup_knowledge_q_${id}`)}\nR: ${answer}` });
			answers[id] = '';
		}
		answers = answers;
		await loadCount();
		return true;
	}
</script>

<section class="block">
	<h3><Icon name="sparkles" size={16} /> {$t('setup_knowledge_what_title')}</h3>
	<div class="md">{@html renderMarkdown($t('setup_knowledge_what_md'))}</div>
</section>

<section class="block">
	<h3><Icon name="search" size={16} /> {$t('setup_knowledge_search_title')}</h3>
	<BuiltinModelInstall />
</section>

<section class="block">
	<h3><Icon name="pencil" size={16} /> {$t('setup_knowledge_first_title')}</h3>
	<p class="help">{$t('setup_knowledge_first_help')}</p>
	{#if existing > 0}
		<p class="help existing">{$t('setup_knowledge_existing', { n: existing })}</p>
	{/if}
	<div class="questions">
		{#each QUESTIONS as id}
			<label class="field">
				<span class="field-label">{$t(`setup_knowledge_q_${id}`)}</span>
				<textarea rows="2" bind:value={answers[id]} placeholder={$t(`setup_knowledge_ph_${id}`)}></textarea>
			</label>
		{/each}
	</div>
</section>

<style>
	.block { display: flex; flex-direction: column; gap: 0.7rem; padding-bottom: 1.4rem; border-bottom: 1px solid var(--glass-border); }
	.block:last-of-type { border-bottom: none; padding-bottom: 0; }
	h3 { display: flex; align-items: center; gap: 0.5rem; margin: 0; font-size: 1rem; font-weight: 700; }
	h3 :global(svg) { color: var(--accent); }
	.md { font-size: 0.88rem; line-height: 1.55; color: var(--text-dim); max-width: 68ch; }
	.md :global(ul) { margin: 0.3rem 0; padding-left: 1.2rem; }
	.md :global(p) { margin: 0.4rem 0; }
	.md :global(strong) { color: var(--text-main); }
	.help { margin: 0; font-size: 0.85rem; line-height: 1.5; color: var(--text-dim); max-width: 68ch; }
	.existing { color: var(--text-main); font-weight: 600; }
	.questions { display: flex; flex-direction: column; gap: 0.9rem; }
	.field { display: flex; flex-direction: column; gap: 0.35rem; max-width: 620px; }
	.field-label { font-weight: 600; font-size: 0.88rem; }
	textarea { width: 100%; box-sizing: border-box; resize: vertical; font: inherit; font-size: 0.88rem; line-height: 1.45; }
</style>
