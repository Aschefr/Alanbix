<script lang="ts">
	import { createEventDispatcher, onMount } from 'svelte';
	import { get } from 'svelte/store';
	import { t } from '$lib/i18nStore';
	import {
		getCustomServerUrl,
		setCustomServerUrl,
		enableDemoMode,
		disableDemoMode
	} from '$lib/config';
	import { authStore } from '$lib/auth';

	export let isOpen = false;

	const dispatch = createEventDispatcher();

	let serverInput = '';
	let subnetPrefix = '192.168.1';
	let scanning = false;
	let testing = false;
	let showAdvanced = false;
	let statusMessage = '';
	let statusType: 'info' | 'success' | 'error' = 'info';
	let discoveredServers: Array<{ url: string; name: string; version: string; hostname: string }> = [];

	let wasOpen = false;
	$: if (isOpen && !wasOpen) {
		wasOpen = true;
		onModalOpen();
	} else if (!isOpen) {
		wasOpen = false;
	}

	function portal(node: HTMLElement) {
		document.body.appendChild(node);
		return {
			destroy() {
				if (node.parentNode) {
					node.parentNode.removeChild(node);
				}
			}
		};
	}

	onMount(() => {
		const saved = getCustomServerUrl();
		if (saved) {
			serverInput = saved;
			const m = saved.match(/^https?:\/\/(\d+\.\d+\.\d+)\.\d+/);
			if (m) subnetPrefix = m[1];
		}
	});

	function close() {
		isOpen = false;
		dispatch('close');
	}

	async function onModalOpen() {
		const saved = getCustomServerUrl();
		if (saved) {
			serverInput = saved;
			const m = saved.match(/^https?:\/\/(\d+\.\d+\.\d+)\.\d+/);
			if (m) subnetPrefix = m[1];
		}
		// Automatically run discovery without user having to click anything
		await startAutoDiscovery();
	}

	function normalizeUrl(raw: string): string {
		let val = (raw || '').trim().replace(/\/+$/, '');
		if (!val) return '';
		if (!val.startsWith('http://') && !val.startsWith('https://')) {
			val = `http://${val}`;
		}
		try {
			const u = new URL(val);
			if (!u.port && /^\d+\.\d+\.\d+\.\d+$/.test(u.hostname)) {
				u.port = '41481';
				return u.toString().replace(/\/+$/, '');
			}
		} catch {}
		return val;
	}

	async function getLocalIPSubnets(): Promise<string[]> {
		const subnets = new Set<string>();
		const saved = getCustomServerUrl();
		if (saved) {
			const m = saved.match(/^https?:\/\/(\d+\.\d+\.\d+)\.\d+/);
			if (m) subnets.add(m[1]);
		}
		if (subnetPrefix) subnets.add(subnetPrefix);

		if (typeof window === 'undefined' || typeof RTCPeerConnection === 'undefined') {
			['192.168.1', '192.168.0', '192.168.20', '10.0.2'].forEach((s) => subnets.add(s));
			return Array.from(subnets);
		}

		return new Promise((resolve) => {
			try {
				const pc = new RTCPeerConnection({ iceServers: [] });
				pc.createDataChannel('alanbix_discovery');
				pc.createOffer().then((offer) => pc.setLocalDescription(offer)).catch(() => {});

				const finish = () => {
					try { pc.close(); } catch {}
					['192.168.1', '192.168.0', '192.168.20', '10.0.2'].forEach((s) => subnets.add(s));
					resolve(Array.from(subnets));
				};

				const timer = setTimeout(finish, 650);

				pc.onicecandidate = (event) => {
					if (!event || !event.candidate || !event.candidate.candidate) {
						clearTimeout(timer);
						finish();
						return;
					}
					const cand = event.candidate.candidate;
					const match = cand.match(/([0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3})/);
					if (match) {
						const ip = match[1];
						if (!ip.startsWith('127.') && !ip.startsWith('0.')) {
							const prefix = ip.split('.').slice(0, 3).join('.');
							subnets.add(prefix);
							subnetPrefix = prefix;
						}
					}
				};
			} catch {
				['192.168.1', '192.168.0', '192.168.20', '10.0.2'].forEach((s) => subnets.add(s));
				resolve(Array.from(subnets));
			}
		});
	}

	async function probeServer(baseUrl: string, timeoutMs = 2500) {
		const controller = new AbortController();
		const timer = setTimeout(() => controller.abort(), timeoutMs);
		try {
			const res = await fetch(`${baseUrl}/api/system/discovery`, {
				method: 'GET',
				headers: { 'Accept': 'application/json' },
				mode: 'cors',
				credentials: 'omit',
				signal: controller.signal
			});
			clearTimeout(timer);
			if (res.ok) {
				const data = await res.json();
				if (data && (data.app === 'Alanbix' || data.status === 'ok')) {
					const srv = {
						url: baseUrl,
						name: data.name || 'Alanbix LAN',
						version: data.version || '',
						hostname: data.hostname || ''
					};
					console.log('[Alanbix Discovery] Found server:', srv);
					return srv;
				}
			}
		} catch {
			clearTimeout(timer);
		}

		// Fallback to /health for older Alanbix instances
		const hcController = new AbortController();
		const hcTimer = setTimeout(() => hcController.abort(), timeoutMs);
		try {
			const res = await fetch(`${baseUrl}/health`, {
				method: 'GET',
				headers: { 'Accept': 'application/json' },
				mode: 'cors',
				credentials: 'omit',
				signal: hcController.signal
			});
			clearTimeout(hcTimer);
			if (res.ok) {
				const data = await res.json();
				if (data && data.status === 'ok') {
					const srv = {
						url: baseUrl,
						name: 'Alanbix LAN',
						version: data.version || '',
						hostname: baseUrl
					};
					console.log('[Alanbix Discovery] Found server via health:', srv);
					return srv;
				}
			}
		} catch {
			clearTimeout(hcTimer);
		}
		return null;
	}

	function addDiscovered(srv: { url: string; name: string; version: string; hostname: string }) {
		if (!discoveredServers.some((s) => s.url === srv.url)) {
			discoveredServers = [...discoveredServers, srv];
			if (!serverInput) {
				serverInput = srv.url;
			}
		}
	}

	async function startAutoDiscovery() {
		if (scanning) return;
		scanning = true;
		statusType = 'info';
		statusMessage = get(t)('server_modal_searching');

		// 1. Detect subnets
		const detected = await getLocalIPSubnets();
		const primarySubnet = detected[0] || '192.168.1';
		subnetPrefix = primarySubnet;

		// 2. Phase 1: High-probability candidates with generous 2500ms timeout
		const priorityList: string[] = [];
		const saved = getCustomServerUrl();
		if (saved) {
			const norm = normalizeUrl(saved);
			if (norm && !priorityList.includes(norm)) priorityList.push(norm);
		}

		[
			'http://10.0.2.2:41481',
			'http://10.0.2.2:8000',
			'http://alanbix.local:41481',
			'http://alanbix.local:8000',
			'http://unraid.local:41481'
		].forEach((u) => {
			if (!priorityList.includes(u)) priorityList.push(u);
		});

		// Gateways & common host IPs on top detected subnets
		for (const sub of detected.slice(0, 3)) {
			[
				`http://${sub}.168:41481`,
				`http://${sub}.1:41481`,
				`http://${sub}.100:41481`,
				`http://${sub}.2:41481`,
				`http://${sub}.254:41481`,
				`http://${sub}.168:8000`,
				`http://${sub}.1:8000`
			].forEach((u) => {
				if (!priorityList.includes(u)) priorityList.push(u);
			});
		}

		// Probe priority targets concurrently
		const priorityResults = await Promise.all(priorityList.map((url) => probeServer(url, 2500)));
		for (const found of priorityResults) {
			if (found) addDiscovered(found);
		}

		// If priority probe found our server, stop immediately!
		if (discoveredServers.length > 0) {
			scanning = false;
			statusType = 'success';
			statusMessage = get(t)('server_modal_status_found', { count: discoveredServers.length });
			return;
		}

		// 3. Phase 2: Subnet sweep on the primary subnet only
		const cleanPrefix = primarySubnet.trim().replace(/\.+$/, '');
		const candidates: string[] = [];
		for (let i = 1; i <= 254; i++) {
			const candidateUrl = `http://${cleanPrefix}.${i}:41481`;
			if (!priorityList.includes(candidateUrl)) {
				candidates.push(candidateUrl);
			}
		}

		const batchSize = 36;
		for (let i = 0; i < candidates.length; i += batchSize) {
			const batch = candidates.slice(i, i + batchSize);
			const results = await Promise.all(batch.map((url) => probeServer(url, 1200)));
			for (const found of results) {
				if (found) addDiscovered(found);
			}
			if (discoveredServers.length > 0) {
				break;
			}
		}

		scanning = false;
		if (discoveredServers.length > 0) {
			statusType = 'success';
			statusMessage = get(t)('server_modal_status_found', { count: discoveredServers.length });
		} else {
			statusType = 'error';
			statusMessage = get(t)('server_modal_status_none');
		}
	}

	async function testAndSave() {
		const raw = serverInput.trim();
		if (!raw) {
			setCustomServerUrl('');
			disableDemoMode();
			statusType = 'success';
			statusMessage = get(t)('server_modal_status_reset');
			setTimeout(() => window.location.reload(), 400);
			return;
		}

		if (raw.toLowerCase() === 'demo' || raw.toLowerCase() === 'demo.alanbix.local') {
			startDemoMode();
			return;
		}

		const normalized = normalizeUrl(raw);
		testing = true;
		statusType = 'info';
		statusMessage = get(t)('server_modal_status_checking', { url: normalized });

		const found = await probeServer(normalized, 3000);
		testing = false;

		if (found) {
			setCustomServerUrl(normalized);
			statusType = 'success';
			statusMessage = get(t)('server_modal_status_connected', { name: found.name, version: found.version || 'OK' });
			dispatch('connected', { url: normalized });
			setTimeout(() => {
				window.location.reload();
			}, 500);
		} else {
			statusType = 'error';
			statusMessage = get(t)('server_modal_status_unreachable', { url: normalized });
		}
	}

	function selectDiscovered(srv: { url: string; name: string }) {
		serverInput = srv.url;
		testAndSave();
	}

	function startDemoMode() {
		enableDemoMode();
		authStore.login('demo-alanbix-token');
		statusType = 'success';
		statusMessage = get(t)('server_modal_status_demo');
		setTimeout(() => {
			window.location.href = '/dashboard';
		}, 350);
	}

	function resetLocalData() {
		try {
			setCustomServerUrl('');
			disableDemoMode();
			authStore.logout();
			localStorage.clear();
			sessionStorage.clear();
		} catch {}
		window.location.href = '/';
	}
</script>

{#if isOpen}
	<div class="server-modal-backdrop" use:portal on:click|self={close} role="presentation">
		<div class="server-modal-card" role="dialog" aria-modal="true" aria-labelledby="server-modal-title">
			<div class="modal-header">
				<div class="modal-title-group">
					<h2 id="server-modal-title">📡 {$t('server_modal_title')}</h2>
					<span class="modal-subtitle">{$t('server_modal_desc')}</span>
				</div>
				<button type="button" class="close-btn" on:click={close} aria-label={$t('common_cancel')}>✕</button>
			</div>

			<!-- Discovered Servers List (Primary Hero Block) -->
			{#if discoveredServers.length > 0}
				<div class="discovered-section">
					<div class="section-label">
						<span>🎮 {$t('server_modal_servers_detected')} ({discoveredServers.length})</span>
						<span class="live-tag">{$t('server_modal_online')}</span>
					</div>
					<div class="discovered-list">
						{#each discoveredServers as srv, idx}
							<div class="discovered-card" class:recommended={idx === 0}>
								<div class="srv-info">
									<div class="srv-title-row">
										<strong class="srv-name">{srv.name}</strong>
										{#if idx === 0}
											<span class="badge-recommended">{$t('server_modal_recommended')}</span>
										{/if}
									</div>
									<div class="srv-meta">
										<span class="srv-url">{srv.url}</span>
										{#if srv.version}
											<span class="srv-ver">v{srv.version}</span>
										{/if}
									</div>
								</div>
								<button type="button" class="btn-join" on:click={() => selectDiscovered(srv)}>
									{$t('server_modal_join')} →
								</button>
							</div>
						{/each}
					</div>
				</div>
			{/if}

			<!-- Dynamic Scanning Indicator -->
			{#if scanning}
				<div class="radar-box">
					<div class="radar-pulse"></div>
					<div class="radar-text">
						<strong>{$t('server_modal_searching')}</strong>
						<span>Scan rapide du réseau Wi-Fi local sans configuration...</span>
					</div>
				</div>
			{:else if discoveredServers.length === 0 && statusType === 'error'}
				<div class="status-banner error">
					{statusMessage}
				</div>
			{/if}

			{#if statusMessage && statusType === 'success' && !scanning}
				<div class="status-banner success">
					{statusMessage}
				</div>
			{/if}

			<!-- Collapsible Manual & Advanced Settings -->
			<div class="advanced-toggle-row">
				<button type="button" class="btn-toggle-advanced" on:click={() => (showAdvanced = !showAdvanced)}>
					<span>{showAdvanced ? '▲ ' + $t('server_modal_manual_toggle_hide') : '⚙️ ' + $t('server_modal_manual_toggle_show')}</span>
				</button>
			</div>

			{#if showAdvanced}
				<div class="advanced-panel">
					<div class="section-block">
						<label for="manual-server-url">{$t('server_modal_manual_label')}</label>
						<input
							id="manual-server-url"
							type="text"
							bind:value={serverInput}
							placeholder="Ex: http://192.168.1.50:41481"
						/>
					</div>

					<div class="section-block">
						<label for="lan-subnet">{$t('server_modal_auto_scan')}</label>
						<div class="row-inline">
							<input
								id="lan-subnet"
								type="text"
								bind:value={subnetPrefix}
								placeholder="192.168.1"
								class="subnet-input"
							/>
							<button type="button" class="btn-scan" on:click={startAutoDiscovery} disabled={scanning}>
								{scanning ? '🔄 ' + $t('server_modal_btn_scanning') : '🔍 ' + $t('server_modal_btn_scan')}
							</button>
						</div>
					</div>

					<button type="button" class="btn-save" on:click={testAndSave} disabled={testing}>
						{testing ? $t('server_modal_testing') : '✅ ' + $t('server_modal_btn_test')}
					</button>
				</div>
			{/if}

			<div class="modal-actions">
				<div class="demo-divider">
					<span>{$t('server_modal_no_lan_nearby')}</span>
				</div>

				<button type="button" class="btn-demo" on:click={startDemoMode}>
					✨ {$t('server_modal_btn_demo')}
				</button>

				<button type="button" class="btn-reset-local" on:click={resetLocalData}>
					🗑️ {$t('server_modal_btn_reset')}
				</button>
			</div>
		</div>
	</div>
{/if}

<style>
	.server-modal-backdrop {
		position: fixed;
		top: 0;
		left: 0;
		right: 0;
		bottom: 0;
		width: 100vw;
		height: 100vh;
		background: rgba(0, 0, 0, 0.78);
		backdrop-filter: blur(6px);
		display: flex;
		align-items: center;
		justify-content: center;
		z-index: 99999;
		padding: 1rem;
		box-sizing: border-box;
	}

	.server-modal-card {
		width: 100%;
		max-width: 460px;
		background: var(--bg-secondary, #181b23);
		border: 1px solid var(--glass-border, rgba(255, 255, 255, 0.12));
		border-radius: 4px;
		padding: 1.25rem;
		color: var(--text-main, #f3f4f6);
		box-shadow: 0 20px 40px -10px rgba(0, 0, 0, 0.7);
		text-align: left;
		box-sizing: border-box;
	}

	.modal-header {
		display: flex;
		align-items: flex-start;
		justify-content: space-between;
		gap: 0.5rem;
		margin-bottom: 0.85rem;
	}

	.modal-title-group h2 {
		margin: 0 0 0.2rem 0;
		font-size: 1.15rem;
		font-weight: 700;
	}

	.modal-subtitle {
		font-size: 0.75rem;
		color: var(--text-dim, #9ca3af);
		line-height: 1.35;
		display: block;
	}

	.close-btn {
		background: transparent;
		border: none;
		color: var(--text-dim, #9ca3af);
		font-size: 1.15rem;
		cursor: pointer;
		padding: 0.2rem 0.4rem;
		border-radius: 3px;
	}

	.radar-box {
		display: flex;
		align-items: center;
		gap: 0.75rem;
		background: rgba(59, 130, 246, 0.1);
		border: 1px solid rgba(59, 130, 246, 0.3);
		border-radius: 4px;
		padding: 0.65rem 0.85rem;
		margin-bottom: 0.85rem;
	}

	.radar-pulse {
		width: 14px;
		height: 14px;
		border-radius: 50%;
		background: #3b82f6;
		box-shadow: 0 0 0 rgba(59, 130, 246, 0.7);
		animation: radar-pulse-anim 1.5s infinite;
		flex-shrink: 0;
	}

	@keyframes radar-pulse-anim {
		0% {
			transform: scale(0.9);
			box-shadow: 0 0 0 0 rgba(59, 130, 246, 0.7);
		}
		70% {
			transform: scale(1);
			box-shadow: 0 0 0 10px rgba(59, 130, 246, 0);
		}
		100% {
			transform: scale(0.9);
			box-shadow: 0 0 0 0 rgba(59, 130, 246, 0);
		}
	}

	.radar-text {
		display: flex;
		flex-direction: column;
		gap: 0.15rem;
		font-size: 0.75rem;
	}

	.radar-text strong {
		color: #93c5fd;
		font-size: 0.8rem;
	}

	.radar-text span {
		color: var(--text-dim, #9ca3af);
	}

	.discovered-section {
		margin-bottom: 0.85rem;
	}

	.section-label {
		display: flex;
		align-items: center;
		justify-content: space-between;
		font-size: 0.72rem;
		text-transform: uppercase;
		letter-spacing: 0.05em;
		color: var(--text-dim, #9ca3af);
		font-weight: 700;
		margin-bottom: 0.4rem;
	}

	.live-tag {
		background: rgba(34, 197, 94, 0.15);
		color: #4ade80;
		border: 1px solid rgba(34, 197, 94, 0.3);
		padding: 0.1rem 0.35rem;
		border-radius: 3px;
		font-size: 0.65rem;
		font-weight: 700;
	}

	.discovered-list {
		display: flex;
		flex-direction: column;
		gap: 0.5rem;
		max-height: 220px;
		overflow-y: auto;
	}

	.discovered-card {
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: 0.75rem;
		padding: 0.7rem 0.85rem;
		background: rgba(255, 255, 255, 0.04);
		border: 1px solid var(--glass-border, rgba(255, 255, 255, 0.12));
		border-radius: 4px;
		transition: border-color 0.2s, background 0.2s;
	}

	.discovered-card.recommended {
		border-color: rgba(59, 130, 246, 0.55);
		background: linear-gradient(90deg, rgba(59, 130, 246, 0.12) 0%, rgba(255, 255, 255, 0.03) 100%);
	}

	.srv-info {
		display: flex;
		flex-direction: column;
		gap: 0.2rem;
		min-width: 0;
		flex: 1;
	}

	.srv-title-row {
		display: flex;
		align-items: center;
		gap: 0.45rem;
		flex-wrap: wrap;
	}

	.srv-name {
		font-size: 0.92rem;
		font-weight: 700;
		color: var(--text-main, #fff);
		line-height: 1.2;
	}

	.badge-recommended {
		background: #2563eb;
		color: #fff;
		font-size: 0.6rem;
		font-weight: 800;
		padding: 0.1rem 0.35rem;
		border-radius: 3px;
		text-transform: uppercase;
		letter-spacing: 0.04em;
	}

	.srv-meta {
		display: flex;
		align-items: center;
		gap: 0.4rem;
		font-size: 0.75rem;
		color: var(--text-dim, #9ca3af);
		font-family: monospace;
	}

	.srv-ver {
		color: var(--accent, #3b82f6);
		font-weight: 600;
	}

	.btn-join {
		padding: 0.5rem 0.9rem;
		background: var(--accent, #3b82f6);
		color: #fff;
		border: none;
		border-radius: 4px;
		font-size: 0.85rem;
		font-weight: 700;
		cursor: pointer;
		flex-shrink: 0;
		transition: background 0.2s, transform 0.1s;
	}

	.btn-join:hover {
		background: #2563eb;
		transform: scale(1.02);
	}

	.status-banner {
		padding: 0.55rem 0.75rem;
		border-radius: 4px;
		font-size: 0.78rem;
		margin-bottom: 0.75rem;
		line-height: 1.35;
	}
	.status-banner.info {
		background: rgba(59, 130, 246, 0.12);
		border: 1px solid rgba(59, 130, 246, 0.3);
		color: #93c5fd;
	}
	.status-banner.success {
		background: rgba(34, 197, 94, 0.12);
		border: 1px solid rgba(34, 197, 94, 0.3);
		color: #86efac;
	}
	.status-banner.error {
		background: rgba(239, 68, 68, 0.12);
		border: 1px solid rgba(239, 68, 68, 0.3);
		color: #fca5a5;
	}

	.advanced-toggle-row {
		margin-top: 0.5rem;
		margin-bottom: 0.5rem;
		text-align: center;
	}

	.btn-toggle-advanced {
		background: transparent;
		border: none;
		color: var(--text-dim, #9ca3af);
		font-size: 0.75rem;
		font-weight: 600;
		cursor: pointer;
		padding: 0.3rem 0.5rem;
		text-decoration: underline;
		transition: color 0.2s;
	}

	.btn-toggle-advanced:hover {
		color: var(--text-main, #fff);
	}

	.advanced-panel {
		background: rgba(0, 0, 0, 0.2);
		border: 1px solid var(--glass-border, rgba(255, 255, 255, 0.08));
		border-radius: 4px;
		padding: 0.85rem;
		margin-bottom: 0.85rem;
	}

	.section-block {
		margin-bottom: 0.75rem;
	}

	label {
		display: block;
		font-size: 0.7rem;
		text-transform: uppercase;
		letter-spacing: 0.05em;
		color: var(--text-dim, #9ca3af);
		margin-bottom: 0.35rem;
		font-weight: 600;
	}

	.row-inline {
		display: flex;
		gap: 0.5rem;
	}

	input {
		width: 100%;
		padding: 0.55rem 0.65rem;
		background: var(--input-bg, rgba(0, 0, 0, 0.3));
		border: 1px solid var(--glass-border, rgba(255, 255, 255, 0.15));
		border-radius: 4px;
		color: var(--text-main, #fff);
		font-size: 0.85rem;
		box-sizing: border-box;
	}

	.subnet-input {
		flex: 1;
	}

	.btn-scan {
		padding: 0.55rem 0.8rem;
		background: var(--bg-tertiary, #262b38);
		border: 1px solid var(--glass-border, rgba(255, 255, 255, 0.15));
		border-radius: 4px;
		color: var(--text-main, #fff);
		font-weight: 600;
		font-size: 0.8rem;
		cursor: pointer;
		white-space: nowrap;
	}

	.btn-save {
		width: 100%;
		padding: 0.65rem;
		background: var(--accent, #3b82f6);
		color: #fff;
		border: none;
		border-radius: 4px;
		font-weight: 700;
		font-size: 0.85rem;
		cursor: pointer;
	}

	.modal-actions {
		display: flex;
		flex-direction: column;
		gap: 0.55rem;
		margin-top: 0.85rem;
	}

	.demo-divider {
		display: flex;
		align-items: center;
		justify-content: center;
		font-size: 0.7rem;
		color: var(--text-dim, #9ca3af);
		margin: 0.1rem 0;
	}

	.btn-demo {
		width: 100%;
		padding: 0.6rem;
		background: rgba(16, 185, 129, 0.14);
		border: 1px solid rgba(16, 185, 129, 0.4);
		color: #34d399;
		border-radius: 4px;
		font-weight: 700;
		font-size: 0.82rem;
		cursor: pointer;
	}

	.btn-reset-local {
		width: 100%;
		padding: 0.5rem;
		background: rgba(239, 68, 68, 0.1);
		border: 1px solid rgba(239, 68, 68, 0.35);
		color: #fca5a5;
		border-radius: 4px;
		font-size: 0.75rem;
		font-weight: 600;
		cursor: pointer;
	}
</style>
