<script>
	// Server state and network tests run by hand. They run from the Alanbix server, not from the
	// admin's or a player's computer.
	import { onDestroy, onMount } from 'svelte';
	import { api } from '$lib/api';
	import { t, currentLang } from '$lib/i18nStore';
	import Icon from '$lib/components/Icon.svelte';

	const TESTS = [
		{ id: 'ping', icon: 'wifi', label: 'diag_ping', help: 'diag_ping_help' },
		{ id: 'traceroute', icon: 'route', label: 'diag_traceroute', help: 'diag_traceroute_help' },
		{ id: 'dns', icon: 'globe', label: 'diag_dns', help: 'diag_dns_help' },
	];
	const INTERNET_HOST = '1.1.1.1';

	let server = null;
	let serverError = false;
	let timer = null;
	let host = '';
	let running = '';
	let result = null; // { tool, host, data } or { error }

	$: fmt = (n, digits = 1) => Number(n ?? 0).toLocaleString($currentLang, { maximumFractionDigits: digits });
	$: ramPercent = server?.ram_total_mb ? Math.round((server.ram_used_mb / server.ram_total_mb) * 100) : 0;
	$: rawOutput = result?.data ? [result.data.stdout, result.data.stderr].filter(Boolean).join('\n').trim() : '';

	async function loadServer() {
		try {
			server = await api.get('/diagnostics/server');
			serverError = false;
		} catch {
			serverError = true;
		}
	}

	async function run(tool) {
		const target = host.trim();
		result = null;
		if (!/^[a-zA-Z0-9][a-zA-Z0-9.-]*$/.test(target)) {
			result = { error: $t('diag_bad_address') };
			return;
		}
		running = tool;
		try {
			const data = await api.post('/diagnostics/run', { tool, host: target });
			result = data.error ? { error: data.error } : { tool, host: target, data };
		} catch (e) {
			result = { error: e.message };
		}
		running = '';
	}

	function testInternet() {
		host = INTERNET_HOST;
		run('ping');
	}

	onMount(() => {
		loadServer();
		timer = setInterval(loadServer, 15000);
	});
	onDestroy(() => clearInterval(timer));
</script>

<div class="diag">
	<section class="card glass">
		<div class="card-head">
			<h2><Icon name="server" size={17} /> {$t('diag_server_title')}</h2>
			<button type="button" class="btn-secondary btn-sm" on:click={loadServer}><Icon name="refresh" size={14} /> {$t('common_refresh')}</button>
		</div>
		{#if serverError}
			<p class="message error" role="alert"><Icon name="alert-triangle" size={14} /> {$t('diag_server_error')}</p>
		{:else if server}
			<div class="tiles">
				<div class="tile">
					<span class="tile-label">{$t('diag_cpu')}</span>
					<strong>{$t('diag_cpu_value', { load: fmt(server.cpu_load_1m, 2), cores: server.cpu_count })}</strong>
					<span class="tile-note">{$t('diag_cpu_help')}</span>
				</div>
				<div class="tile">
					<span class="tile-label">{$t('diag_memory')}</span>
					<strong>{$t('diag_used_of', { used: fmt(server.ram_used_mb / 1024), total: fmt(server.ram_total_mb / 1024) })}</strong>
					<div class="bar" class:high={ramPercent >= 90} aria-hidden="true"><div style="width: {ramPercent}%"></div></div>
				</div>
				<div class="tile">
					<span class="tile-label">{$t('diag_disk')}</span>
					<strong>{$t('diag_used_of', { used: fmt(server.disk_used_gb, 0), total: fmt(server.disk_total_gb, 0) })}</strong>
					<div class="bar" class:high={server.disk_use_percent >= 90} aria-hidden="true"><div style="width: {server.disk_use_percent}%"></div></div>
				</div>
			</div>
		{/if}
	</section>

	<section class="card glass">
		<h2><Icon name="wifi" size={17} /> {$t('diag_network_title')}</h2>
		<p class="help">{$t('diag_network_help')}</p>
		<form class="address" on:submit|preventDefault={() => run('ping')}>
			<label for="diag-host">{$t('diag_address')}</label>
			<div class="address-row">
				<input id="diag-host" type="text" bind:value={host} placeholder={$t('diag_address_placeholder')} autocomplete="off" autocapitalize="off" spellcheck="false" />
				<button type="button" class="btn-secondary btn-sm" on:click={testInternet} disabled={!!running}>{$t('diag_test_internet')}</button>
			</div>
		</form>
		<ul class="tests">
			{#each TESTS as test (test.id)}
				<li>
					<button type="button" class="btn-secondary btn-sm" on:click={() => run(test.id)} disabled={!!running || !host.trim()}>
						<Icon name={running === test.id ? 'hourglass' : test.icon} size={15} /> {$t(test.label)}
					</button>
					<span class="help">{$t(test.help)}</span>
				</li>
			{/each}
		</ul>

		<div aria-live="polite">
			{#if running}
				<p class="message"><Icon name="hourglass" size={14} /> {$t('diag_running')}</p>
			{:else if result?.error}
				<p class="message error" role="alert"><Icon name="alert-triangle" size={14} /> {result.error}</p>
			{:else if result?.tool === 'ping'}
				{#if result.data.success}
					<p class="message ok"><Icon name="check-circle" size={14} /> {$t('diag_ping_ok', { host: result.host, ms: fmt(result.data.avg_ms), loss: fmt(result.data.loss_percent, 0) })}</p>
				{:else}
					<p class="message error"><Icon name="alert-triangle" size={14} /> {$t('diag_ping_fail', { host: result.host })}</p>
				{/if}
			{:else if result?.tool === 'dns'}
				<p class="message ok"><Icon name="check-circle" size={14} /> {$t('diag_dns_ok', { host: result.host, ips: (result.data.ips || []).join(', ') })}</p>
			{:else if result?.tool === 'traceroute'}
				<p class="message">{$t('diag_traceroute_read')}</p>
			{/if}
			{#if !running && rawOutput}
				<details class="raw" open={result?.tool === 'traceroute'}>
					<summary>{$t('diag_raw')}</summary>
					<pre>{rawOutput}</pre>
				</details>
			{/if}
		</div>
	</section>
</div>

<style>
	.diag { display: flex; flex-direction: column; gap: 1rem; max-width: 900px; }
	.card { display: flex; flex-direction: column; gap: 0.7rem; padding: 1rem 1.1rem; border-radius: 12px; }
	.card-head { display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: 0.5rem; }
	h2 { display: flex; align-items: center; gap: 0.5rem; margin: 0; font-size: 1rem; font-weight: 700; color: var(--text-main); }
	h2 :global(svg) { color: var(--accent); }
	.help { margin: 0; font-size: 0.82rem; line-height: 1.5; color: var(--text-dim); max-width: 68ch; }
	button :global(svg) { flex-shrink: 0; }
	button.btn-sm { display: inline-flex; align-items: center; gap: 0.4rem; }

	.tiles { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 0.6rem; }
	.tile { display: flex; flex-direction: column; gap: 0.3rem; min-width: 0; padding: 0.7rem 0.8rem; border: 1px solid var(--glass-border); border-radius: 8px; }
	.tile-label { font-size: 0.78rem; font-weight: 600; color: var(--text-dim); }
	.tile strong { font-size: 0.95rem; color: var(--text-main); font-variant-numeric: tabular-nums; }
	.tile-note { font-size: 0.75rem; line-height: 1.4; color: var(--text-muted); }
	.bar { height: 6px; border-radius: 3px; background: var(--glass-border); overflow: hidden; }
	.bar > div { height: 100%; background: var(--accent-solid); }
	.bar.high > div { background: var(--danger); }

	.address { display: flex; flex-direction: column; gap: 0.3rem; }
	.address label { font-size: 0.82rem; font-weight: 600; color: var(--text-main); }
	.address-row { display: flex; flex-wrap: wrap; gap: 0.5rem; }
	.address-row input { flex: 1 1 220px; min-width: 0; padding: 0.5rem 0.7rem; border: 1px solid var(--glass-border); border-radius: 8px; background: var(--surface-sunken); color: var(--text-main); font-size: 0.88rem; }

	.tests { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 0.45rem; }
	.tests li { display: flex; flex-wrap: wrap; align-items: center; gap: 0.3rem 0.7rem; }
	.tests button { min-width: 125px; justify-content: flex-start; }
	.tests .help { flex: 1 1 240px; }

	.message { display: flex; align-items: flex-start; gap: 0.45rem; margin: 0.2rem 0 0; font-size: 0.86rem; line-height: 1.5; color: var(--text-dim); overflow-wrap: anywhere; }
	.message :global(svg) { flex-shrink: 0; margin-top: 0.2rem; }
	.message.ok { color: var(--success, var(--accent)); font-weight: 600; }
	.message.error { color: var(--danger); }
	.raw { margin-top: 0.5rem; }
	.raw summary { cursor: pointer; font-size: 0.8rem; font-weight: 600; color: var(--text-dim); min-height: 28px; }
	.raw pre { margin: 0.3rem 0 0; padding: 0.6rem 0.8rem; border-radius: 8px; background: var(--bg-tertiary); color: var(--text-main); font-size: 0.75rem; line-height: 1.45; overflow-x: auto; }

	@media (max-width: 700px) {
		.tiles { grid-template-columns: 1fr; }
	}
</style>
