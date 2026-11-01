<script>
	import { onMount } from 'svelte';
	import { api } from '$lib/api';
	import { t } from '$lib/i18nStore';
	import MarkdownEditor from '$lib/components/MarkdownEditor.svelte';

	export let eventName = '';
	export let wifiSsids = '';
	export let playerUrl = '';

	let content = '';
	let hadContent = false;
	let loaded = false;

	function template() {
		return $t('setup_info_template', {
			event: eventName || 'LAN',
			wifi: wifiSsids || '…',
			url: playerUrl || '…',
		});
	}

	onMount(async () => {
		try { content = (await api.get('/dashboard/info')).content || ''; } catch {}
		hadContent = !!content.trim();
		if (!hadContent) content = template();
		loaded = true;
	});

	/** Called by the setup page when the admin continues. */
	export async function save() {
		await api.put('/admin/config/info_page_content', { value: content });
		return true;
	}
</script>

{#if loaded}
	{#if hadContent}
		<div class="note">
			<span>{$t('setup_info_existing')}</span>
			<button class="link-btn" on:click={() => { content = template(); hadContent = false; }}>{$t('setup_info_use_template')}</button>
		</div>
	{:else}
		<p class="help">{$t('setup_info_template_help')}</p>
	{/if}
	<MarkdownEditor id="setup-info" bind:value={content} rows={16} label={$t('setup_step_info')} />
{/if}

<style>
	.help { margin: 0; font-size: 0.85rem; color: var(--text-dim); line-height: 1.5; max-width: 65ch; }
	.note { display: flex; flex-wrap: wrap; align-items: center; gap: 0.4rem 0.8rem; font-size: 0.85rem; color: var(--text-dim); }
	.link-btn { background: none; border: none; padding: 0; color: var(--accent); font: inherit; font-weight: 600; cursor: pointer; text-decoration: underline; text-underline-offset: 3px; }
</style>
