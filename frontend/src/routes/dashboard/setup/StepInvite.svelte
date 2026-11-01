<script>
	import { t } from '$lib/i18nStore';
	import Icon from '$lib/components/Icon.svelte';
	import QrCode from '$lib/components/QrCode.svelte';

	export let playerUrl = '';
	export let eventName = '';
	export let wifiSsids = '';

	// The poster lives directly in <body> so printing can hide the whole app around it
	function portal(node) {
		document.body.appendChild(node);
		return { destroy() { node.remove(); } };
	}

	let copied = false;
	async function copyUrl() {
		try { await navigator.clipboard.writeText(playerUrl); copied = true; setTimeout(() => copied = false, 2000); } catch {}
	}
</script>

<div class="invite">
	<div class="qr-box">
		<QrCode value={playerUrl} size={176} label={$t('setup_invite_qr_label')} />
	</div>
	<div class="invite-side">
		<code>{playerUrl}</code>
		<div class="actions">
			<button class="btn-secondary" on:click={copyUrl}><Icon name={copied ? 'check' : 'clipboard'} size={16} /> {$t(copied ? 'setup_invite_copied' : 'setup_invite_copy')}</button>
			<button class="btn-secondary" on:click={() => window.print()}><Icon name="image" size={16} /> {$t('setup_invite_print')}</button>
		</div>
		<p class="help">{$t('setup_invite_help')}</p>
		<p class="help">{$t('setup_invite_qr_help')}</p>
	</div>
</div>

<!-- Printed poster only (Print button) -->
<div class="poster setup-poster" use:portal>
	<h1>{eventName}</h1>
	<p class="poster-lead">{$t('setup_invite_poster_lead')}</p>
	<QrCode value={playerUrl} size={420} />
	<p class="poster-url">{playerUrl}</p>
	{#if wifiSsids}<p class="poster-wifi">{$t('setup_invite_poster_wifi', { wifi: wifiSsids })}</p>{/if}
</div>

<style>
	.invite { display: flex; gap: 1.5rem; align-items: flex-start; flex-wrap: wrap; }
	.qr-box { padding: 0.6rem; border: 1px solid var(--glass-border); border-radius: 14px; background: #fff; }
	.invite-side { flex: 1 1 260px; display: flex; flex-direction: column; gap: 0.75rem; min-width: 0; }
	code { align-self: flex-start; max-width: 100%; padding: 0.6rem 0.9rem; border-radius: var(--radius-md); background: var(--surface-sunken); border: 1px solid var(--glass-border); font-size: 1rem; font-weight: 600; overflow-wrap: anywhere; }
	.actions { display: flex; flex-wrap: wrap; gap: 0.5rem; }
	.actions .btn-secondary { display: inline-flex; align-items: center; gap: 0.4rem; color: var(--text-main); }
	.help { margin: 0; font-size: 0.82rem; color: var(--text-dim); line-height: 1.5; max-width: 60ch; }

	.poster { display: none; }
	@media print {
		:global(body > :not(.setup-poster)) { display: none !important; }
		:global(html), :global(body) { background: #fff !important; }
		.poster { display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 1.2rem; position: fixed; inset: 0; background: #fff; color: #000; text-align: center; padding: 2cm; }
		.poster h1 { margin: 0; font-size: 42pt; font-weight: 800; color: #000; }
		.poster-lead { margin: 0; font-size: 20pt; }
		.poster-url { margin: 0; font-size: 22pt; font-weight: 700; font-family: ui-monospace, monospace; }
		.poster-wifi { margin: 0; font-size: 16pt; }
	}
	@media (max-width: 600px) {
		.qr-box { align-self: center; }
		code { font-size: 0.85rem; }
	}
</style>
