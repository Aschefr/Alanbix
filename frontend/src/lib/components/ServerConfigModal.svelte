<script lang="ts">
	import { createEventDispatcher, onMount } from 'svelte';
	import {
		getCustomServerUrl,
		setCustomServerUrl,
		isDemoMode,
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
	let statusMessage = '';
	let statusType: 'info' | 'success' | 'error' = 'info';
	let discoveredServers: Array<{ url: string; name: string; version: string; hostname: string }> = [];

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

	function normalizeUrl(raw: string): string {
		let val = (raw || '').trim().replace(/\/+$/, '');
		if (!val) return '';
		if (!val.startsWith('http://') && !val.startsWith('https://')) {
			val = `http://${val}`;
		}
		// Add default Alanbix port 41481 if no port is specified on an IP address
		try {
			const u = new URL(val);
			if (!u.port && /^\d+\.\d+\.\d+\.\d+$/.test(u.hostname)) {
				u.port = '41481';
				return u.toString().replace(/\/+$/, '');
			}
		} catch {}
		return val;
	}

	async function probeServer(baseUrl: string, timeoutMs = 1500) {
		const controller = new AbortController();
		const timer = setTimeout(() => controller.abort(), timeoutMs);
		try {
			const res = await fetch(`${baseUrl}/api/system/discovery`, {
				method: 'GET',
				signal: controller.signal
			});
			clearTimeout(timer);
			if (res.ok) {
				const data = await res.json();
				if (data && (data.app === 'Alanbix' || data.status === 'ok')) {
					return {
						url: baseUrl,
						name: data.name || 'Alanbix LAN',
						version: data.version || '',
						hostname: data.hostname || ''
					};
				}
			}
		} catch {
			clearTimeout(timer);
		}

		// Fallback to /health for older Alanbix servers
		const hcController = new AbortController();
		const hcTimer = setTimeout(() => hcController.abort(), timeoutMs);
		try {
			const res = await fetch(`${baseUrl}/health`, {
				method: 'GET',
				signal: hcController.signal
			});
			clearTimeout(hcTimer);
			if (res.ok) {
				const data = await res.json();
				if (data && data.status === 'ok') {
					return {
						url: baseUrl,
						name: 'Alanbix LAN',
						version: data.version || '',
						hostname: baseUrl
					};
				}
			}
		} catch {
			clearTimeout(hcTimer);
		}
		return null;
	}

	async function scanLan() {
		if (scanning) return;
		scanning = true;
		discoveredServers = [];
		statusType = 'info';
		statusMessage = `Recherche de serveurs Alanbix sur ${subnetPrefix}.x (port 41481)...`;

		const candidates: string[] = [];
		const cleanPrefix = subnetPrefix.trim().replace(/\.+$/, '');
		for (let i = 1; i <= 254; i++) {
			candidates.push(`http://${cleanPrefix}.${i}:41481`);
		}

		const batchSize = 32;
		for (let i = 0; i < candidates.length; i += batchSize) {
			const batch = candidates.slice(i, i + batchSize);
			const results = await Promise.all(batch.map((url) => probeServer(url, 950)));
			for (const found of results) {
				if (found && !discoveredServers.some((s) => s.url === found.url)) {
					discoveredServers = [...discoveredServers, found];
				}
			}
		}

		scanning = false;
		if (discoveredServers.length > 0) {
			statusType = 'success';
			statusMessage = `${discoveredServers.length} serveur(s) Alanbix détecté(s) sur le réseau local.`;
			if (!serverInput) {
				serverInput = discoveredServers[0].url;
			}
		} else {
			statusType = 'error';
			statusMessage = 'Aucun serveur détecté automatiquement. Saisissez l’IP manuellement ou lancez le Mode Démo.';
		}
	}

	async function testAndSave() {
		const raw = serverInput.trim();
		if (!raw) {
			// Reset to default same-origin
			setCustomServerUrl('');
			disableDemoMode();
			statusType = 'success';
			statusMessage = 'Configuration réinitialisée (origine par défaut).';
			setTimeout(() => window.location.reload(), 400);
			return;
		}

		// Reviewer shortcut: entering "demo" activates Offline Demo Mode
		if (raw.toLowerCase() === 'demo' || raw.toLowerCase() === 'demo.alanbix.local') {
			startDemoMode();
			return;
		}

		const normalized = normalizeUrl(raw);
		testing = true;
		statusType = 'info';
		statusMessage = `Vérification de la connexion à ${normalized}...`;

		const found = await probeServer(normalized, 3000);
		testing = false;

		if (found) {
			setCustomServerUrl(normalized);
			statusType = 'success';
			statusMessage = `Connecté à ${found.name} (${found.version || 'OK'}) ! Rechargement...`;
			dispatch('connected', { url: normalized });
			setTimeout(() => {
				window.location.reload();
			}, 500);
		} else {
			statusType = 'error';
			statusMessage = `Impossible de joindre un serveur Alanbix sur ${normalized}. Vérifiez l’IP et le Wi-Fi.`;
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
		statusMessage = 'Mode Démo Hors-Ligne activé ! Ouverture du tableau de bord...';
		setTimeout(() => {
			window.location.href = '/dashboard';
		}, 350);
	}
</script>

{#if isOpen}
	<div class="server-modal-backdrop" on:click|self={close} role="presentation">
		<div class="server-modal-card glass" role="dialog" aria-modal="true" aria-labelledby="server-modal-title">
			<div class="modal-header">
				<h2 id="server-modal-title">📡 Connexion au serveur Alanbix</h2>
				<button type="button" class="close-btn" on:click={close} aria-label="Fermer">✕</button>
			</div>

			<p class="modal-desc">
				Connectez l’application mobile à votre serveur <strong>Alanbix LAN</strong> sur votre réseau Wi-Fi local (port <code>41481</code>), ou explorez l’application hors-ligne.
			</p>

			{#if statusMessage}
				<div class="status-banner {statusType}">
					{statusMessage}
				</div>
			{/if}

			<div class="section-block">
				<label for="lan-subnet">Recherche automatique Wi-Fi (Sous-réseau LAN)</label>
				<div class="row-inline">
					<input
						id="lan-subnet"
						type="text"
						bind:value={subnetPrefix}
						placeholder="192.168.1"
						class="subnet-input"
					/>
					<button type="button" class="btn-scan" on:click={scanLan} disabled={scanning}>
						{scanning ? '🔄 Scan en cours...' : '🔍 Scanner le LAN'}
					</button>
				</div>
			</div>

			{#if discoveredServers.length > 0}
				<div class="discovered-list">
					{#each discoveredServers as srv}
						<button type="button" class="discovered-item" on:click={() => selectDiscovered(srv)}>
							<div class="srv-info">
								<strong>🎮 {srv.name}</strong>
								<span>{srv.url} {srv.version ? `• v${srv.version}` : ''}</span>
							</div>
							<span class="srv-connect">Rejoindre →</span>
						</button>
					{/each}
				</div>
			{/if}

			<div class="section-block">
				<label for="manual-server-url">Adresse IP ou URL du serveur Alanbix</label>
				<input
					id="manual-server-url"
					type="text"
					bind:value={serverInput}
					placeholder="Ex: http://192.168.1.50:41481"
				/>
			</div>

			<div class="modal-actions">
				<button type="button" class="btn-save" on:click={testAndSave} disabled={testing}>
					{testing ? 'Vérification...' : '✅ Tester & Enregistrer'}
				</button>

				<div class="demo-divider">
					<span>Pas de serveur LAN à proximité ?</span>
				</div>

				<button type="button" class="btn-demo" on:click={startDemoMode}>
					✨ Explorer le Mode Démo (Sans serveur)
				</button>
			</div>
		</div>
	</div>
{/if}

<style>
	.server-modal-backdrop {
		position: fixed;
		inset: 0;
		background: rgba(0, 0, 0, 0.72);
		backdrop-filter: blur(6px);
		display: flex;
		align-items: center;
		justify-content: center;
		z-index: 9999;
		padding: 1rem;
	}

	.server-modal-card {
		width: 100%;
		max-width: 460px;
		background: var(--bg-secondary, #181b23);
		border: 1px solid var(--glass-border, rgba(255, 255, 255, 0.12));
		border-radius: 14px;
		padding: 1.5rem;
		color: var(--text-main, #f3f4f6);
		box-shadow: 0 25px 50px -12px rgba(0, 0, 0, 0.65);
		text-align: left;
	}

	.modal-header {
		display: flex;
		align-items: center;
		justify-content: space-between;
		margin-bottom: 0.75rem;
	}

	.modal-header h2 {
		margin: 0;
		font-size: 1.2rem;
	}

	.close-btn {
		background: transparent;
		border: none;
		color: var(--text-dim, #9ca3af);
		font-size: 1.15rem;
		cursor: pointer;
		padding: 0.25rem 0.5rem;
	}

	.modal-desc {
		font-size: 0.85rem;
		color: var(--text-dim, #9ca3af);
		margin-bottom: 1rem;
		line-height: 1.45;
	}

	.status-banner {
		padding: 0.65rem 0.85rem;
		border-radius: 8px;
		font-size: 0.82rem;
		margin-bottom: 1rem;
	}
	.status-banner.info {
		background: rgba(59, 130, 246, 0.15);
		border: 1px solid rgba(59, 130, 246, 0.35);
		color: #93c5fd;
	}
	.status-banner.success {
		background: rgba(34, 197, 94, 0.15);
		border: 1px solid rgba(34, 197, 94, 0.35);
		color: #86efac;
	}
	.status-banner.error {
		background: rgba(239, 68, 68, 0.15);
		border: 1px solid rgba(239, 68, 68, 0.35);
		color: #fca5a5;
	}

	.section-block {
		margin-bottom: 1rem;
	}

	label {
		display: block;
		font-size: 0.75rem;
		text-transform: uppercase;
		letter-spacing: 0.05em;
		color: var(--text-dim, #9ca3af);
		margin-bottom: 0.4rem;
	}

	.row-inline {
		display: flex;
		gap: 0.5rem;
	}

	input {
		width: 100%;
		padding: 0.65rem 0.75rem;
		background: var(--input-bg, rgba(0, 0, 0, 0.3));
		border: 1px solid var(--glass-border, rgba(255, 255, 255, 0.15));
		border-radius: 8px;
		color: var(--text-main, #fff);
		font-size: 0.9rem;
	}

	.subnet-input {
		flex: 1;
	}

	.btn-scan {
		padding: 0.65rem 0.9rem;
		background: var(--bg-tertiary, #262b38);
		border: 1px solid var(--glass-border, rgba(255, 255, 255, 0.15));
		border-radius: 8px;
		color: var(--text-main, #fff);
		font-weight: 600;
		font-size: 0.85rem;
		cursor: pointer;
		white-space: nowrap;
	}

	.discovered-list {
		display: flex;
		flex-direction: column;
		gap: 0.5rem;
		margin-bottom: 1rem;
		max-height: 150px;
		overflow-y: auto;
	}

	.discovered-item {
		display: flex;
		align-items: center;
		justify-content: space-between;
		padding: 0.65rem 0.85rem;
		background: rgba(59, 130, 246, 0.1);
		border: 1px solid rgba(59, 130, 246, 0.3);
		border-radius: 8px;
		color: var(--text-main, #fff);
		cursor: pointer;
		text-align: left;
	}

	.srv-info {
		display: flex;
		flex-direction: column;
		gap: 0.15rem;
	}

	.srv-info span {
		font-size: 0.75rem;
		color: var(--text-dim, #9ca3af);
	}

	.srv-connect {
		font-size: 0.8rem;
		font-weight: 600;
		color: var(--accent, #3b82f6);
	}

	.modal-actions {
		display: flex;
		flex-direction: column;
		gap: 0.75rem;
		margin-top: 1.2rem;
	}

	.btn-save {
		width: 100%;
		padding: 0.75rem;
		background: var(--accent, #3b82f6);
		color: #fff;
		border: none;
		border-radius: 8px;
		font-weight: 600;
		cursor: pointer;
	}

	.demo-divider {
		display: flex;
		align-items: center;
		justify-content: center;
		font-size: 0.75rem;
		color: var(--text-dim, #9ca3af);
		margin: 0.15rem 0;
	}

	.btn-demo {
		width: 100%;
		padding: 0.7rem;
		background: rgba(16, 185, 129, 0.14);
		border: 1px solid rgba(16, 185, 129, 0.4);
		color: #34d399;
		border-radius: 8px;
		font-weight: 600;
		cursor: pointer;
	}
</style>

