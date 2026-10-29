<script lang="ts">
	import { onMount } from 'svelte';
	import { goto } from '$app/navigation';
	import { api } from '$lib/api';
	import { authStore } from '$lib/auth';
	import { t, currentLang, availableLanguages, flagMap, loadLocale } from '$lib/i18nStore';
	import {
		getCustomServerUrl,
		isCapacitorNative,
		isDemoMode
	} from '$lib/config';
	import {
		getNotificationPreferences,
		saveNotificationPreferences,
		type NotificationPreferences,
		triggerVibration,
		triggerNotificationSound,
		revokeCurrentDeviceToken,
		syncNativePreferences,
		getNativePushStatus,
		openBatterySettings,
		openSystemNotificationSettings,
		startNativePushService,
		stopNativePushService,
		getOrRegisterDeviceToken
	} from '$lib/push';
	import ServerConfigModal from '$lib/components/ServerConfigModal.svelte';

	let user: any = null;
	let loading = true;
	let isDark = true;
	let showServerModal = false;
	let testLoading = false;
	let testSuccess = false;
	let nativeStatus: any = null;
	let nativeLoading = false;

	// Permission système
	let systemNotifSupport = false;
	let systemNotifPermission = 'default';

	// Préférences de notification locales
	let prefs: NotificationPreferences = getNotificationPreferences();

	// Serveur & Réseau
	let currentServer = '';
	let lanWifiSsids: string[] = [];
	let serverVersion = '1.33.1';
	let pingMs: number | null = null;

	onMount(async () => {
		isDark = (localStorage.getItem('alanbix_theme') || 'dark') === 'dark';
		currentServer = getCustomServerUrl() || (typeof window !== 'undefined' ? window.location.origin : '');

		if (typeof window !== 'undefined' && 'Notification' in window) {
			systemNotifSupport = true;
			systemNotifPermission = Notification.permission;
		}

		try {
			user = await api.get('/me');
		} catch (e) {
			console.warn('[Settings] Failed to fetch current user:', e);
		}

		// Ping & Découverte des SSIDs
		try {
			const start = performance.now();
			const stats = await api.get('/dashboard/stats');
			pingMs = Math.round(performance.now() - start);
			if (stats?.lan_wifi_ssids) {
				lanWifiSsids = Array.isArray(stats.lan_wifi_ssids) ? stats.lan_wifi_ssids : [];
			}
		} catch {
			pingMs = null;
		}

		try {
			const health = await api.get('/health');
			if (health?.version) serverVersion = health.version;
		} catch {}

		if (isCapacitorNative()) {
			nativeStatus = await getNativePushStatus();
		}
		loading = false;
	});

	function updatePrefs() {
		saveNotificationPreferences(prefs);
		syncNativePreferences(prefs);
	}

	async function toggleNativeService(enable: boolean) {
		nativeLoading = true;
		try {
			if (enable) {
				const devToken = await getOrRegisterDeviceToken();
				const srvUrl = getCustomServerUrl() || (typeof window !== 'undefined' ? window.location.origin : '');
				await startNativePushService(srvUrl, devToken || '', 'Alanbix LAN');
			} else {
				await stopNativePushService();
			}
			nativeStatus = await getNativePushStatus();
		} finally {
			nativeLoading = false;
		}
	}

	async function requestSystemPermission() {
		if (typeof window !== 'undefined' && 'Notification' in window) {
			try {
				const perm = await Notification.requestPermission();
				systemNotifPermission = perm;
				if (perm === 'granted') {
					prefs.enabled = true;
					updatePrefs();
					triggerVibration();
				}
			} catch (e) {
				console.error('[Settings] Permission request error:', e);
			}
		}
	}

	async function sendTestNotification() {
		testLoading = true;
		testSuccess = false;
		try {
			// Déclenche le son et la vibration immédiatement si activés
			if (prefs.vibration) triggerVibration();
			if (prefs.sound) triggerNotificationSound();

			await api.post('/notifications/test', {});
			testSuccess = true;
			setTimeout(() => { testSuccess = false; }, 3500);
		} catch (e) {
			console.error('[Settings] Test notification failed:', e);
		} finally {
			testLoading = false;
		}
	}

	function toggleTheme() {
		isDark = !isDark;
		const theme = isDark ? 'dark' : 'light';
		localStorage.setItem('alanbix_theme', theme);
		document.documentElement.setAttribute('data-theme', theme);
	}

	async function handleLogout() {
		await revokeCurrentDeviceToken();
		authStore.logout();
		goto('/');
	}
</script>

<svelte:head>
	<title>{$t('settings_page_title')} — Alanbix</title>
</svelte:head>

<div class="settings-page">
	<div class="settings-header">
		<button class="back-btn" on:click={() => goto('/dashboard')} title={$t('settings_back_to_home')}>
			← {$t('common_home')}
		</button>
		<div class="header-title-box">
			<h1>⚙️ {$t('settings_page_title')}</h1>
			<p class="subtitle">{$t('settings_subtitle')}</p>
		</div>
	</div>

	<div class="settings-content">
		<!-- SECTION NOTIFICATIONS -->
		<section class="settings-section glass">
			<div class="section-title-row">
				<div class="icon">🔔</div>
				<div class="title-text">
					<h2>{$t('settings_section_notifs')}</h2>
					<p>{$t('settings_section_notifs_desc')}</p>
				</div>
				<label class="switch">
					<input type="checkbox" bind:checked={prefs.enabled} on:change={updatePrefs} />
					<span class="slider"></span>
				</label>
			</div>

			<!-- Statut de la permission système -->
			<div class="permission-box">
				<div class="perm-status">
					<span class="label">{$t('settings_perm_label')}</span>
					{#if systemNotifPermission === 'granted'}
						<span class="badge badge-green">✅ {$t('settings_perm_granted')}</span>
					{:else if systemNotifPermission === 'denied'}
						<span class="badge badge-red">❌ {$t('settings_perm_denied')}</span>
					{:else}
						<span class="badge badge-yellow">⚠️ {$t('settings_perm_default')}</span>
					{/if}
				</div>
				{#if systemNotifSupport && systemNotifPermission !== 'granted'}
					<button class="btn btn-sm btn-primary" on:click={requestSystemPermission}>
						{$t('settings_btn_enable_notifs')}
					</button>
				{/if}
				<button class="btn btn-sm btn-ghost" on:click={sendTestNotification} disabled={testLoading}>
					{#if testLoading}
						{$t('settings_btn_testing')}
					{:else if testSuccess}
						✅ {$t('settings_btn_test_success')}
					{:else}
						🔔 {$t('settings_btn_test_alert')}
					{/if}
				</button>
			</div>

			{#if isCapacitorNative()}
				<div class="native-service-card">
					<div class="service-header-row">
						<div class="service-info">
							<span class="service-title">⚡ {$t('settings_bg_service_title')}</span>
							<span class="service-desc">{$t('settings_bg_service_desc')}</span>
						</div>
						<label class="switch">
							<input type="checkbox" checked={nativeStatus?.isRunning ?? true} on:change={(e) => toggleNativeService(e.currentTarget.checked)} disabled={nativeLoading} />
							<span class="slider"></span>
						</label>
					</div>
					<div class="service-status-pill">
						{#if nativeStatus?.isConnected}
							<span class="badge badge-green">🟢 {$t('settings_service_connected')}</span>
						{:else if nativeStatus?.isRunning}
							<span class="badge badge-yellow">🟡 {$t('settings_service_waiting')}</span>
						{:else}
							<span class="badge badge-red">⚪ {$t('settings_service_stopped')}</span>
						{/if}
					</div>
					<div class="native-actions-row">
						<button class="btn btn-sm btn-ghost" on:click={openBatterySettings} title={$t('settings_btn_battery_title')}>
							🔋 {$t('settings_btn_battery')}
						</button>
						<button class="btn btn-sm btn-ghost" on:click={openSystemNotificationSettings} title={$t('settings_btn_channels_title')}>
							⚙️ {$t('settings_btn_channels')}
						</button>
					</div>
				</div>
			{/if}

			{#if prefs.enabled}
				<div class="settings-subgroup">
					<h3>{$t('settings_alert_types_title')}</h3>
					
					<div class="toggle-list">
						<label class="toggle-item">
							<div class="item-info">
								<span class="item-title">⚔️ {$t('settings_cat_matches_title')}</span>
								<span class="item-desc">{$t('settings_cat_matches_desc')}</span>
							</div>
							<input type="checkbox" bind:checked={prefs.categories.match_ready} on:change={updatePrefs} />
						</label>

						<label class="toggle-item">
							<div class="item-info">
								<span class="item-title">💬 {$t('settings_cat_pm_title')}</span>
								<span class="item-desc">{$t('settings_cat_pm_desc')}</span>
							</div>
							<input type="checkbox" bind:checked={prefs.categories.private_message} on:change={updatePrefs} />
						</label>

						<label class="toggle-item">
							<div class="item-info">
								<span class="item-title">🛡️ {$t('settings_cat_team_title')}</span>
								<span class="item-desc">{$t('settings_cat_team_desc')}</span>
							</div>
							<input type="checkbox" bind:checked={prefs.categories.team_message} on:change={updatePrefs} />
						</label>

						<div class="select-item">
							<div class="item-info">
								<span class="item-title">🌐 {$t('settings_cat_public_title')}</span>
								<span class="item-desc">{$t('settings_cat_public_desc')}</span>
							</div>
							<select bind:value={prefs.categories.public_mention} on:change={updatePrefs}>
								<option value="mentions">{$t('settings_cat_public_mentions')}</option>
								<option value="all">{$t('settings_cat_public_all')}</option>
								<option value="none">{$t('settings_cat_public_none')}</option>
							</select>
						</div>

						<label class="toggle-item">
							<div class="item-info">
								<span class="item-title">🤖 {$t('settings_cat_ai_title')}</span>
								<span class="item-desc">{$t('settings_cat_ai_desc')}</span>
							</div>
							<input type="checkbox" bind:checked={prefs.categories.ai_reply} on:change={updatePrefs} />
						</label>

						<label class="toggle-item">
							<div class="item-info">
								<span class="item-title">📢 {$t('settings_cat_admin_title')}</span>
								<span class="item-desc">{$t('settings_cat_admin_desc')}</span>
							</div>
							<input type="checkbox" bind:checked={prefs.categories.admin_message} on:change={updatePrefs} />
						</label>

						<label class="toggle-item">
							<div class="item-info">
								<span class="item-title">🏆 {$t('settings_cat_tournaments_title')}</span>
								<span class="item-desc">{$t('settings_cat_tournaments_desc')}</span>
							</div>
							<input type="checkbox" bind:checked={prefs.categories.tournaments} on:change={updatePrefs} />
						</label>
					</div>
				</div>

				<div class="settings-subgroup">
					<h3>{$t('settings_behavior_title')}</h3>
					<div class="toggle-list">
						<label class="toggle-item">
							<div class="item-info">
								<span class="item-title">📳 {$t('settings_vibration_title')}</span>
								<span class="item-desc">{$t('settings_vibration_desc')}</span>
							</div>
							<input type="checkbox" bind:checked={prefs.vibration} on:change={updatePrefs} />
						</label>

						<label class="toggle-item">
							<div class="item-info">
								<span class="item-title">🔊 {$t('settings_sound_title')}</span>
								<span class="item-desc">{$t('settings_sound_desc')}</span>
							</div>
							<input type="checkbox" bind:checked={prefs.sound} on:change={updatePrefs} />
						</label>

						<label class="toggle-item">
							<div class="item-info">
								<span class="item-title">🌙 {$t('settings_dnd_title')}</span>
								<span class="item-desc">{$t('settings_dnd_desc')}</span>
							</div>
							<input type="checkbox" bind:checked={prefs.dnd_enabled} on:change={updatePrefs} />
						</label>

						{#if prefs.dnd_enabled}
							<div class="dnd-config">
								<div class="time-row">
									<label>
										{$t('settings_dnd_from')}
										<input type="time" bind:value={prefs.dnd_start} on:change={updatePrefs} />
									</label>
									<label>
										{$t('settings_dnd_to')}
										<input type="time" bind:value={prefs.dnd_end} on:change={updatePrefs} />
									</label>
								</div>
								<label class="sub-toggle">
									<input type="checkbox" bind:checked={prefs.dnd_bypass_matches} on:change={updatePrefs} />
									<span>{$t('settings_dnd_bypass_matches')}</span>
								</label>
								<label class="sub-toggle">
									<input type="checkbox" bind:checked={prefs.dnd_bypass_admin} on:change={updatePrefs} />
									<span>{$t('settings_dnd_bypass_admin')}</span>
								</label>
							</div>
						{/if}
					</div>
				</div>
			{/if}
		</section>

		<!-- SECTION SERVEUR LAN -->
		<section class="settings-section glass">
			<div class="section-title-row">
				<div class="icon">🌐</div>
				<div class="title-text">
					<h2>{$t('settings_section_server')}</h2>
					<p>{$t('settings_section_server_desc')}</p>
				</div>
			</div>

			<div class="server-card">
				<div class="server-meta">
					<div class="meta-row">
						<span class="meta-label">{$t('settings_server_addr')}</span>
						<span class="meta-val font-mono">{currentServer}</span>
					</div>
					<div class="meta-row">
						<span class="meta-label">{$t('settings_server_status')}</span>
						<span class="badge badge-green">
							🟢 {$t('settings_server_connected')} {pingMs !== null ? `(${pingMs} ms)` : ''}
						</span>
					</div>
					{#if lanWifiSsids.length > 0}
						<div class="meta-row">
							<span class="meta-label">{$t('settings_wifi_declared')}</span>
							<span class="ssids-list">
								{#each lanWifiSsids as ssid}
									<span class="ssid-pill">📶 {ssid}</span>
								{/each}
							</span>
						</div>
					{/if}
				</div>

				<div class="server-actions">
					<button class="btn btn-secondary" on:click={() => { showServerModal = true; }}>
						📡 {$t('settings_btn_change_server')}
					</button>
				</div>
			</div>
		</section>

		<!-- SECTION APPARENCE & LANGUE -->
		<section class="settings-section glass">
			<div class="section-title-row">
				<div class="icon">🎨</div>
				<div class="title-text">
					<h2>{$t('settings_section_appearance')}</h2>
					<p>{$t('settings_section_appearance_desc')}</p>
				</div>
			</div>

			<div class="appearance-grid">
				<div class="app-item">
					<span class="app-label">{$t('settings_theme_label')}</span>
					<button class="btn btn-secondary" on:click={toggleTheme}>
						{#if isDark}🌙 {$t('settings_theme_dark')}{:else}☀️ {$t('settings_theme_light')}{/if}
					</button>
				</div>

				<div class="app-item">
					<span class="app-label">{$t('settings_lang_label')}</span>
					<div class="lang-selector">
						{#each $availableLanguages as lang}
							<button
								class="btn btn-sm {$currentLang === lang ? 'btn-primary' : 'btn-ghost'}"
								on:click={() => loadLocale(lang)}
							>
								{flagMap[lang] || lang.toUpperCase()}
							</button>
						{/each}
					</div>
				</div>
			</div>
		</section>

		<!-- SECTION COMPTE & SESSION -->
		{#if user}
			<section class="settings-section glass">
				<div class="section-title-row">
					<div class="icon">👤</div>
					<div class="title-text">
						<h2>{$t('settings_section_account')}</h2>
						<p>{$t('settings_section_account_desc')}</p>
					</div>
				</div>

				<div class="account-card">
					<div class="user-summary">
						<div class="user-avatar">
							{#if user.avatar_url}
								<img src={user.avatar_url} alt={user.username} />
							{:else}
								<span>{user.username.slice(0, 2).toUpperCase()}</span>
							{/if}
						</div>
						<div class="user-details">
							<span class="user-name">{user.username}</span>
							<span class="user-sub">
								{#if user.is_admin}👑 {$t('settings_user_admin_badge')} · {/if}
								{user.team_name ? `🛡️ ${user.team_name}` : $t('settings_user_solo')}
								{user.seat_id ? ` · 🪑 {$t('settings_user_seat_prefix')} ${user.seat_id}` : ''}
							</span>
						</div>
					</div>

					<div class="account-actions">
						<button class="btn btn-secondary" on:click={() => goto('/dashboard/profile')}>
							🏆 {$t('settings_btn_view_profile')}
						</button>
						<button class="btn btn-danger" on:click={handleLogout}>
							🚪 {$t('settings_btn_logout')}
						</button>
					</div>
				</div>
			</section>
		{/if}

		<!-- SECTION À PROPOS -->
		<section class="settings-section glass about-section">
			<div class="section-title-row">
				<div class="icon">ℹ️</div>
				<div class="title-text">
					<h2>{$t('settings_section_about')}</h2>
					<p>Alanbix Companion LAN Management System</p>
				</div>
			</div>

			<div class="about-grid font-mono">
				<div class="about-row">
					<span>{$t('settings_server_version')}</span>
					<span>v{serverVersion}</span>
				</div>
				<div class="about-row">
					<span>{$t('settings_app_type')}</span>
					<span>{isCapacitorNative() ? '📱 Alanbix Mobile' : '💻 Alanbix Web'}</span>
				</div>
				<div class="about-row">
					<span>App ID :</span>
					<span>com.amifystudio.alanbix</span>
				</div>
			</div>
		</section>
	</div>
</div>

<ServerConfigModal isOpen={showServerModal} on:close={() => { showServerModal = false; }} />

<style>
	.settings-page {
		max-width: 860px;
		margin: 0 auto;
		padding: 1.5rem 1rem 6rem;
	}

	.settings-header {
		display: flex;
		align-items: center;
		gap: 1rem;
		margin-bottom: 2rem;
	}

	.back-btn {
		background: rgba(255, 255, 255, 0.08);
		border: 1px solid rgba(255, 255, 255, 0.12);
		color: #e2e8f0;
		padding: 0.5rem 0.9rem;
		border-radius: 8px;
		cursor: pointer;
		font-weight: 500;
		transition: background 0.2s;
	}
	.back-btn:hover {
		background: rgba(255, 255, 255, 0.16);
	}

	.header-title-box h1 {
		font-size: 1.75rem;
		font-weight: 700;
		margin: 0;
		color: #f8fafc;
	}
	.header-title-box .subtitle {
		margin: 0.2rem 0 0;
		font-size: 0.9rem;
		color: #94a3b8;
	}

	.settings-content {
		display: flex;
		flex-direction: column;
		gap: 1.5rem;
	}

	.settings-section {
		background: rgba(15, 23, 42, 0.65);
		backdrop-filter: blur(12px);
		border: 1px solid rgba(255, 255, 255, 0.08);
		border-radius: 14px;
		padding: 1.5rem;
		transition: border-color 0.2s;
	}

	.section-title-row {
		display: flex;
		align-items: center;
		gap: 1rem;
		margin-bottom: 1.25rem;
	}
	.section-title-row .icon {
		font-size: 1.8rem;
	}
	.section-title-row .title-text {
		flex: 1;
	}
	.section-title-row h2 {
		font-size: 1.2rem;
		margin: 0;
		color: #f1f5f9;
	}
	.section-title-row p {
		margin: 0.2rem 0 0;
		font-size: 0.85rem;
		color: #94a3b8;
	}

	.native-service-card {
		background: var(--surface-sunken);
		border: 1px solid var(--border-color);
		border-radius: 12px;
		padding: 1rem;
		margin: 1rem 0;
		display: flex;
		flex-direction: column;
		gap: 0.75rem;
	}
	.service-header-row {
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: 1rem;
	}
	.service-title {
		font-weight: 700;
		font-size: 0.95rem;
		color: var(--text-main);
		display: block;
	}
	.service-desc {
		font-size: 0.8rem;
		color: var(--text-dim);
		display: block;
	}
	.service-status-pill {
		display: flex;
		align-items: center;
	}
	.native-actions-row {
		display: flex;
		gap: 0.5rem;
		flex-wrap: wrap;
	}
	.permission-box {
		background: rgba(0, 0, 0, 0.25);
		border: 1px solid rgba(255, 255, 255, 0.06);
		border-radius: 10px;
		padding: 0.85rem 1rem;
		display: flex;
		align-items: center;
		gap: 0.85rem;
		flex-wrap: wrap;
		margin-bottom: 1.25rem;
	}
	.perm-status {
		display: flex;
		align-items: center;
		gap: 0.5rem;
		flex: 1;
		min-width: 220px;
	}
	.perm-status .label {
		font-size: 0.85rem;
		color: #94a3b8;
	}

	.badge {
		font-size: 0.75rem;
		padding: 0.2rem 0.55rem;
		border-radius: 6px;
		font-weight: 600;
	}
	.badge-green { background: rgba(34, 197, 94, 0.2); color: #4ade80; border: 1px solid rgba(34, 197, 94, 0.3); }
	.badge-red { background: rgba(239, 68, 68, 0.2); color: #f87171; border: 1px solid rgba(239, 68, 68, 0.3); }
	.badge-yellow { background: rgba(234, 179, 8, 0.2); color: #facc15; border: 1px solid rgba(234, 179, 8, 0.3); }

	.settings-subgroup {
		margin-top: 1.25rem;
		padding-top: 1rem;
		border-top: 1px solid rgba(255, 255, 255, 0.06);
	}
	.settings-subgroup h3 {
		font-size: 0.95rem;
		font-weight: 600;
		color: #cbd5e1;
		margin: 0 0 0.75rem;
		text-transform: uppercase;
		letter-spacing: 0.05em;
	}

	.toggle-list {
		display: flex;
		flex-direction: column;
		gap: 0.65rem;
	}
	.toggle-item, .select-item {
		display: flex;
		align-items: center;
		justify-content: space-between;
		padding: 0.75rem 0.9rem;
		background: rgba(255, 255, 255, 0.03);
		border: 1px solid rgba(255, 255, 255, 0.05);
		border-radius: 8px;
		cursor: pointer;
		gap: 1rem;
	}
	.toggle-item:hover, .select-item:hover {
		background: rgba(255, 255, 255, 0.06);
	}
	.item-info {
		display: flex;
		flex-direction: column;
		gap: 0.2rem;
	}
	.item-title {
		font-size: 0.92rem;
		font-weight: 600;
		color: #f1f5f9;
	}
	.item-desc {
		font-size: 0.8rem;
		color: #94a3b8;
	}
	.select-item select {
		background: #1e293b;
		border: 1px solid rgba(255, 255, 255, 0.15);
		color: #f1f5f9;
		padding: 0.4rem 0.6rem;
		border-radius: 6px;
		font-size: 0.85rem;
	}

	.dnd-config {
		background: rgba(0, 0, 0, 0.3);
		border: 1px dashed rgba(255, 255, 255, 0.1);
		border-radius: 8px;
		padding: 0.85rem;
		margin-top: 0.4rem;
		display: flex;
		flex-direction: column;
		gap: 0.6rem;
	}
	.time-row {
		display: flex;
		gap: 1.5rem;
	}
	.time-row label {
		font-size: 0.85rem;
		color: #cbd5e1;
		display: flex;
		align-items: center;
		gap: 0.5rem;
	}
	.time-row input[type="time"] {
		background: #1e293b;
		border: 1px solid rgba(255, 255, 255, 0.15);
		color: #fff;
		padding: 0.25rem 0.5rem;
		border-radius: 6px;
	}
	.sub-toggle {
		display: flex;
		align-items: center;
		gap: 0.5rem;
		font-size: 0.82rem;
		color: #94a3b8;
		cursor: pointer;
	}

	/* Switch component */
	.switch {
		position: relative;
		display: inline-block;
		width: 44px;
		height: 24px;
	}
	.switch input {
		opacity: 0;
		width: 0;
		height: 0;
	}
	.slider {
		position: absolute;
		cursor: pointer;
		top: 0; left: 0; right: 0; bottom: 0;
		background-color: rgba(255, 255, 255, 0.2);
		transition: 0.2s;
		border-radius: 24px;
	}
	.slider:before {
		position: absolute;
		content: "";
		height: 18px;
		width: 18px;
		left: 3px;
		bottom: 3px;
		background-color: white;
		transition: 0.2s;
		border-radius: 50%;
	}
	input:checked + .slider {
		background-color: #3b82f6;
	}
	input:checked + .slider:before {
		transform: translateX(20px);
	}

	/* Server Card */
	.server-card {
		display: flex;
		flex-direction: column;
		gap: 1rem;
	}
	.server-meta {
		display: flex;
		flex-direction: column;
		gap: 0.5rem;
	}
	.meta-row {
		display: flex;
		align-items: center;
		gap: 0.75rem;
		font-size: 0.88rem;
	}
	.meta-label {
		color: #94a3b8;
		min-width: 150px;
	}
	.meta-val {
		color: #f1f5f9;
		word-break: break-all;
	}
	.ssids-list {
		display: flex;
		gap: 0.4rem;
		flex-wrap: wrap;
	}
	.ssid-pill {
		background: rgba(59, 130, 246, 0.15);
		border: 1px solid rgba(59, 130, 246, 0.3);
		color: #60a5fa;
		padding: 0.2rem 0.5rem;
		border-radius: 6px;
		font-size: 0.8rem;
		font-weight: 500;
	}

	/* Appearance */
	.appearance-grid {
		display: flex;
		flex-direction: column;
		gap: 1rem;
	}
	.app-item {
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: 1rem;
		flex-wrap: wrap;
	}
	.app-label {
		font-size: 0.9rem;
		color: #cbd5e1;
	}
	.lang-selector {
		display: flex;
		gap: 0.5rem;
		flex-wrap: wrap;
	}

	/* Account */
	.account-card {
		display: flex;
		flex-direction: column;
		gap: 1.25rem;
	}
	.user-summary {
		display: flex;
		align-items: center;
		gap: 1rem;
	}
	.user-avatar {
		width: 48px;
		height: 48px;
		border-radius: 50%;
		background: #3b82f6;
		display: flex;
		align-items: center;
		justify-content: center;
		font-weight: 700;
		color: #fff;
		overflow: hidden;
	}
	.user-avatar img {
		width: 100%;
		height: 100%;
		object-fit: cover;
	}
	.user-details {
		display: flex;
		flex-direction: column;
	}
	.user-name {
		font-size: 1.1rem;
		font-weight: 700;
		color: #f8fafc;
	}
	.user-sub {
		font-size: 0.82rem;
		color: #94a3b8;
	}
	.account-actions {
		display: flex;
		gap: 0.75rem;
		flex-wrap: wrap;
	}

	/* Buttons */
	.btn {
		padding: 0.55rem 1rem;
		border-radius: 8px;
		font-weight: 600;
		font-size: 0.88rem;
		cursor: pointer;
		transition: 0.2s;
		border: none;
	}
	.btn-sm {
		padding: 0.35rem 0.7rem;
		font-size: 0.8rem;
	}
	.btn-primary {
		background: #3b82f6;
		color: #fff;
	}
	.btn-primary:hover {
		background: #2563eb;
	}
	.btn-secondary {
		background: rgba(255, 255, 255, 0.08);
		border: 1px solid rgba(255, 255, 255, 0.12);
		color: #e2e8f0;
	}
	.btn-secondary:hover {
		background: rgba(255, 255, 255, 0.14);
	}
	.btn-ghost {
		background: transparent;
		border: 1px solid rgba(255, 255, 255, 0.1);
		color: #94a3b8;
	}
	.btn-ghost:hover {
		color: #fff;
		border-color: rgba(255, 255, 255, 0.25);
	}
	.btn-danger {
		background: rgba(239, 68, 68, 0.15);
		border: 1px solid rgba(239, 68, 68, 0.3);
		color: #f87171;
	}
	.btn-danger:hover {
		background: rgba(239, 68, 68, 0.25);
	}

	/* About */
	.about-grid {
		display: flex;
		flex-direction: column;
		gap: 0.4rem;
		font-size: 0.82rem;
		color: #94a3b8;
	}
	.about-row {
		display: flex;
		justify-content: space-between;
		padding: 0.3rem 0;
		border-bottom: 1px solid rgba(255, 255, 255, 0.04);
	}
	.font-mono {
		font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
	}

	@media (max-width: 640px) {
		.settings-page {
			padding: 1rem 0.75rem 6.5rem;
		}
		.section-title-row {
			align-items: flex-start;
		}
		.meta-row {
			flex-direction: column;
			align-items: flex-start;
			gap: 0.2rem;
		}
		.meta-label {
			min-width: auto;
		}
		.account-actions {
			flex-direction: column;
		}
		.account-actions button {
			width: 100%;
		}
	}
</style>

