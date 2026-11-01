<script lang="ts">
	import Icon from '$lib/components/Icon.svelte';
	import { themeStore, setThemePref } from '$lib/theme';
	import pkg from '../../../../package.json';
	import { onMount, onDestroy } from 'svelte';
	import { goto } from '$app/navigation';
	import { api } from '$lib/api';
	import { authStore } from '$lib/auth';
	import { t, currentLang, availableLanguages, flagMap, loadLocale } from '$lib/i18nStore';
	import {
		getCustomServerUrl,
		isCapacitorNative,
		isDemoMode,
		enableDemoMode,
		disableDemoMode,
		resolveMediaUrl
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
		getOrRegisterDeviceToken,
		requestNativeNotificationPermission
	} from '$lib/push';
	import ServerConfigModal from '$lib/components/ServerConfigModal.svelte';
	import Modal from '$lib/components/Modal.svelte';

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
	let appVersion = pkg.version; // bundled with the app, always in step with the release
	let serverVersion = '1.34.0';
	let pingMs: number | null = null;
	let demoActive = false;

	// Modal confirmation
	let showModal = false;
	let modalTitle = '';
	let modalMessage = '';
	let modalType = 'info';
	let modalConfirmCallback: any = null;

	onMount(async () => {
		currentServer = getCustomServerUrl() || (typeof window !== 'undefined' ? window.location.origin : '');
		demoActive = isDemoMode();

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
			systemNotifSupport = true;
			nativeStatus = await getNativePushStatus();
			if (nativeStatus?.notificationPermission) {
				systemNotifPermission = nativeStatus.notificationPermission;
			}
		}
		loading = false;

		// the user may change the system permission while the app is in the background
		document.addEventListener('visibilitychange', refreshPermission);
		window.addEventListener('focus', refreshPermission);
	});

	onDestroy(() => {
		if (typeof document === 'undefined') return;
		document.removeEventListener('visibilitychange', refreshPermission);
		window.removeEventListener('focus', refreshPermission);
	});

	async function refreshPermission() {
		if (document.visibilityState === 'hidden') return;
		if (isCapacitorNative()) {
			nativeStatus = await getNativePushStatus();
			if (nativeStatus?.notificationPermission) systemNotifPermission = nativeStatus.notificationPermission;
		} else if ('Notification' in window) {
			systemNotifPermission = Notification.permission;
		}
	}

	function updatePrefs() {
		saveNotificationPreferences(prefs);
		syncNativePreferences(prefs);
		if (!prefs.enabled && isCapacitorNative()) {
			stopNativePushService().then(() => getNativePushStatus().then(st => { nativeStatus = st; }));
		}
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
		if (isCapacitorNative()) {
			const perm = await requestNativeNotificationPermission();
			systemNotifPermission = perm;
			if (perm === 'granted') {
				prefs.enabled = true;
				updatePrefs();
				triggerVibration();
			} else if (perm === 'denied') {
				await openSystemNotificationSettings();
			}
			return;
		}
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

	$: isDark = $themeStore.theme === 'dark';

	async function handleLogout() {
		await stopNativePushService();
		await revokeCurrentDeviceToken();
		authStore.logout();
		goto('/');
	}

	function confirmDeleteAccount() {
		modalTitle = $t('profile_delete_account_title');
		modalMessage = $t('profile_delete_account_desc');
		modalType = 'error';
		modalConfirmCallback = async () => {
			try {
				await stopNativePushService();
				await revokeCurrentDeviceToken();
				await api.delete('/me');
				authStore.logout();
				goto('/');
			} catch (err: any) {
				modalTitle = $t('error');
				modalMessage = err.message || $t('profile_delete_account_err');
				modalType = 'error';
				modalConfirmCallback = null;
				showModal = true;
			}
		};
		showModal = true;
	}

	function toggleDemoMode() {
		if (demoActive) {
			disableDemoMode();
			demoActive = false;
			goto('/');
		} else {
			enableDemoMode();
			demoActive = true;
			goto('/dashboard');
		}
	}

	// Rows rendered by the template: one list per group keeps every row identical
	const alertRows = [
		{ key: 'match_ready', icon: 'swords', title: 'settings_cat_matches_title', desc: 'settings_cat_matches_desc' },
		{ key: 'private_message', icon: 'chat', title: 'settings_cat_pm_title', desc: 'settings_cat_pm_desc' },
		{ key: 'team_message', icon: 'shield', title: 'settings_cat_team_title', desc: 'settings_cat_team_desc' },
		{ key: 'public_mention', icon: 'globe', title: 'settings_cat_public_title', desc: 'settings_cat_public_desc', select: true },
		{ key: 'ai_reply', icon: 'bot', title: 'settings_cat_ai_title', desc: 'settings_cat_ai_desc' },
		{ key: 'admin_message', icon: 'megaphone', title: 'settings_cat_admin_title', desc: 'settings_cat_admin_desc' },
		{ key: 'tournaments', icon: 'trophy', title: 'settings_cat_tournaments_title', desc: 'settings_cat_tournaments_desc' }
	];
	const behaviorRows = [
		{ key: 'vibration', icon: 'vibrate', title: 'settings_vibration_title', desc: 'settings_vibration_desc' },
		{ key: 'sound', icon: 'volume-2', title: 'settings_sound_title', desc: 'settings_sound_desc' },
		{ key: 'lockscreen_preview', icon: 'lock', title: 'settings_lockscreen_title', desc: 'settings_lockscreen_desc' },
		{ key: 'dnd_enabled', icon: 'moon', title: 'settings_dnd_title', desc: 'settings_dnd_desc' }
	];
	// Labels are stored as "Label :"; rows show them without the colon
	const lbl = (txt) => String(txt).replace(/\s*:\s*$/, '');

	// Public privacy policy (GitHub Pages): French version for French, English for the other languages
	$: privacyUrl = $currentLang === 'fr' ? 'https://aschefr.github.io/Alanbix/' : 'https://aschefr.github.io/Alanbix/en.html';
</script>

<svelte:head>
	<title>{$t('settings_page_title')} — Alanbix</title>
</svelte:head>

<div class="settings-page">
	<header class="settings-header">
		<button class="back-btn" on:click={() => goto('/dashboard')} title={$t('settings_back_to_home')} aria-label={$t('settings_back_to_home')}>
			<Icon name="chevron-left" size={18} />
		</button>
		<div class="header-title-box">
			<h1 class="page-title-icon"><Icon name="gear" size={24} /> {$t('settings_page_title')}</h1>
			<p class="subtitle">{$t('settings_subtitle')}</p>
		</div>
	</header>

	<div class="settings-content">
		<div class="settings-col">
			<!-- NOTIFICATIONS -->
			<section class="settings-section glass">
				<header class="section-head">
					<span class="section-ic"><Icon name="bell" size={20} /></span>
					<div class="title-text">
						<h2>{$t('settings_section_notifs')}</h2>
						<p>{$t('settings_section_notifs_desc')}</p>
					</div>
					<label class="switch">
						<input type="checkbox" bind:checked={prefs.enabled} on:change={updatePrefs} aria-label={$t('settings_section_notifs')} />
						<span class="slider"></span>
					</label>
				</header>

				<div class="rows">
					<div class="row static">
						<span class="row-ic"><Icon name="shield-check" size={18} /></span>
						<span class="row-text"><span class="row-title">{lbl($t('settings_perm_label'))}</span></span>
						{#if systemNotifPermission === 'granted'}
							<span class="badge badge-green"><Icon name="check-circle" size={13} /> {$t('settings_perm_granted')}</span>
						{:else if systemNotifPermission === 'denied'}
							<span class="badge badge-red"><Icon name="x-circle" size={13} /> {$t('settings_perm_denied')}</span>
						{:else}
							<span class="badge badge-yellow"><Icon name="alert-triangle" size={13} /> {$t('settings_perm_default')}</span>
						{/if}
					</div>
					<div class="row-sub">
						{#if systemNotifSupport && systemNotifPermission !== 'granted'}
							<button class="btn-primary btn-compact btn-ic" on:click={requestSystemPermission}>
								<Icon name="bell" size={15} /> {$t('settings_btn_enable_notifs')}
							</button>
						{/if}
						<button class="btn-secondary btn-compact btn-ic" on:click={sendTestNotification} disabled={testLoading}>
							{#if testLoading}
								{$t('settings_btn_testing')}
							{:else if testSuccess}
								<Icon name="check" size={15} /> {$t('settings_btn_test_success')}
							{:else}
								<Icon name="send" size={15} /> {$t('settings_btn_test_alert')}
							{/if}
						</button>
					</div>

					{#if isCapacitorNative()}
						<label class="row">
							<span class="row-ic"><Icon name="zap" size={18} /></span>
							<span class="row-text">
								<span class="row-title">{$t('settings_bg_service_title')}</span>
								<span class="row-desc">{$t('settings_bg_service_desc')}</span>
							</span>
							<span class="switch">
								<input type="checkbox" checked={nativeStatus?.isRunning ?? true} on:change={(e) => toggleNativeService(e.currentTarget.checked)} disabled={nativeLoading} />
								<span class="slider"></span>
							</span>
						</label>
						<div class="row-sub">
							{#if nativeStatus?.isConnected}
								<span class="badge badge-green"><Icon name="check-circle" size={13} /> {$t('settings_service_connected')}</span>
							{:else if nativeStatus?.isRunning}
								<span class="badge badge-yellow"><Icon name="clock" size={13} /> {$t('settings_service_waiting')}</span>
							{:else}
								<span class="badge badge-red"><Icon name="x-circle" size={13} /> {$t('settings_service_stopped')}</span>
							{/if}
							<button class="btn-secondary btn-compact btn-ic" on:click={openBatterySettings} title={$t('settings_btn_battery_title')}>
								<Icon name="battery" size={15} /> {$t('settings_btn_battery')}
							</button>
							<button class="btn-secondary btn-compact btn-ic" on:click={openSystemNotificationSettings} title={$t('settings_btn_channels_title')}>
								<Icon name="gear" size={15} /> {$t('settings_btn_channels')}
							</button>
						</div>
					{/if}
				</div>

				{#if prefs.enabled}
					<div class="settings-subgroup">
						<h3>{$t('settings_alert_types_title')}</h3>
						<div class="rows">
							{#each alertRows as r (r.key)}
								{#if r.select}
									<div class="row static">
										<span class="row-ic"><Icon name={r.icon} size={18} /></span>
										<span class="row-text">
											<span class="row-title">{$t(r.title)}</span>
											<span class="row-desc">{$t(r.desc)}</span>
										</span>
										<select class="field" bind:value={prefs.categories.public_mention} on:change={updatePrefs} aria-label={$t(r.title)}>
											<option value="mentions">{$t('settings_cat_public_mentions')}</option>
											<option value="all">{$t('settings_cat_public_all')}</option>
											<option value="none">{$t('settings_cat_public_none')}</option>
										</select>
									</div>
								{:else}
									<label class="row">
										<span class="row-ic"><Icon name={r.icon} size={18} /></span>
										<span class="row-text">
											<span class="row-title">{$t(r.title)}</span>
											<span class="row-desc">{$t(r.desc)}</span>
										</span>
										<span class="switch">
											<input type="checkbox" bind:checked={prefs.categories[r.key]} on:change={updatePrefs} />
											<span class="slider"></span>
										</span>
									</label>
								{/if}
							{/each}
						</div>
					</div>

					<div class="settings-subgroup">
						<h3>{$t('settings_behavior_title')}</h3>
						<div class="rows">
							{#each behaviorRows as r (r.key)}
								<label class="row">
									<span class="row-ic"><Icon name={r.icon} size={18} /></span>
									<span class="row-text">
										<span class="row-title">{$t(r.title)}</span>
										<span class="row-desc">{$t(r.desc)}</span>
									</span>
									<span class="switch">
										<input type="checkbox" bind:checked={prefs[r.key]} on:change={updatePrefs} />
										<span class="slider"></span>
									</span>
								</label>
							{/each}

							{#if prefs.dnd_enabled}
								<div class="row-sub dnd-times">
									<label class="time-field">
										<span>{$t('settings_dnd_from')}</span>
										<input class="field" type="time" bind:value={prefs.dnd_start} on:change={updatePrefs} />
									</label>
									<label class="time-field">
										<span>{$t('settings_dnd_to')}</span>
										<input class="field" type="time" bind:value={prefs.dnd_end} on:change={updatePrefs} />
									</label>
								</div>
								<label class="row nested">
									<span class="row-text"><span class="row-title">{$t('settings_dnd_bypass_matches')}</span></span>
									<span class="switch">
										<input type="checkbox" bind:checked={prefs.dnd_bypass_matches} on:change={updatePrefs} />
										<span class="slider"></span>
									</span>
								</label>
								<label class="row nested">
									<span class="row-text"><span class="row-title">{$t('settings_dnd_bypass_admin')}</span></span>
									<span class="switch">
										<input type="checkbox" bind:checked={prefs.dnd_bypass_admin} on:change={updatePrefs} />
										<span class="slider"></span>
									</span>
								</label>
							{/if}
						</div>
					</div>
				{/if}
			</section>
		</div>

		<div class="settings-col">
			<!-- SERVEUR LAN -->
			<section class="settings-section glass">
				<header class="section-head">
					<span class="section-ic"><Icon name="server" size={20} /></span>
					<div class="title-text">
						<h2>{$t('settings_section_server')}</h2>
						<p>{$t('settings_section_server_desc')}</p>
					</div>
				</header>

				<div class="rows">
					<div class="row static">
						<span class="row-ic"><Icon name="globe" size={18} /></span>
						<span class="row-text"><span class="row-title">{lbl($t('settings_server_addr'))}</span></span>
						<span class="row-val font-mono">{currentServer}</span>
					</div>
					<div class="row static">
						<span class="row-ic"><Icon name="check-circle" size={18} /></span>
						<span class="row-text"><span class="row-title">{lbl($t('settings_server_status'))}</span></span>
						<span class="badge badge-green"><Icon name="check-circle" size={13} /> {$t('settings_server_connected')} {pingMs !== null ? `(${pingMs} ms)` : ''}</span>
					</div>
					{#if lanWifiSsids.length > 0}
						<div class="row static">
							<span class="row-ic"><Icon name="wifi" size={18} /></span>
							<span class="row-text"><span class="row-title">{lbl($t('settings_wifi_declared'))}</span></span>
							<span class="ssids-list">
								{#each lanWifiSsids as ssid}
									<span class="badge badge-blue">{ssid}</span>
								{/each}
							</span>
						</div>
					{/if}
				</div>
				<div class="row-sub">
					<button class="btn-secondary btn-compact btn-ic" on:click={() => { showServerModal = true; }}>
						<Icon name="refresh" size={15} /> {$t('settings_btn_change_server')}
					</button>
				</div>
			</section>

			<!-- APPARENCE & LANGUE -->
			<section class="settings-section glass">
				<header class="section-head">
					<span class="section-ic"><Icon name="palette" size={20} /></span>
					<div class="title-text">
						<h2>{$t('settings_section_appearance')}</h2>
						<p>{$t('settings_section_appearance_desc')}</p>
					</div>
				</header>

				<div class="rows">
					<div class="row static">
						<span class="row-ic"><Icon name={isDark ? 'moon' : 'sun'} size={18} /></span>
						<span class="row-text"><span class="row-title">{lbl($t('settings_theme_label'))}</span></span>
						<div class="seg" role="group" aria-label={$t('settings_theme_label')}>
							<button type="button" class="seg-btn" class:on={$themeStore.pref === 'system'} aria-pressed={$themeStore.pref === 'system'} title={$t('settings_theme_system_hint')} on:click={() => setThemePref('system')}>
								<Icon name="monitor" size={15} /> {$t('settings_theme_opt_system')}
							</button>
							<button type="button" class="seg-btn" class:on={$themeStore.pref === 'dark'} aria-pressed={$themeStore.pref === 'dark'} on:click={() => setThemePref('dark')}>
								<Icon name="moon" size={15} /> {$t('settings_theme_opt_dark')}
							</button>
							<button type="button" class="seg-btn" class:on={$themeStore.pref === 'light'} aria-pressed={$themeStore.pref === 'light'} on:click={() => setThemePref('light')}>
								<Icon name="sun" size={15} /> {$t('settings_theme_opt_light')}
							</button>
						</div>
					</div>
					<div class="row static">
						<span class="row-ic"><Icon name="globe" size={18} /></span>
						<span class="row-text"><span class="row-title">{lbl($t('settings_lang_label'))}</span></span>
						<div class="seg" role="group" aria-label={$t('settings_lang_label')}>
							{#each $availableLanguages as lang}
								<button type="button" class="seg-btn" class:on={$currentLang === lang} aria-pressed={$currentLang === lang} on:click={() => loadLocale(lang)}>
									{flagMap[lang] || lang.toUpperCase()}
								</button>
							{/each}
						</div>
					</div>
				</div>
			</section>

			<!-- COMPTE & SESSION -->
			{#if user}
				<section class="settings-section glass">
					<header class="section-head">
						<span class="section-ic"><Icon name="user" size={20} /></span>
						<div class="title-text">
							<h2>{$t('settings_section_account')}</h2>
							<p>{$t('settings_section_account_desc')}</p>
						</div>
					</header>

					<div class="user-summary">
						<div class="user-avatar avatar-shape-{user.avatar_shape || 'circle'}" class:has-img={!!user.avatar_url}>
							{#if user.avatar_url}
								<img src={resolveMediaUrl(user.avatar_url)} alt={user.username} />
							{:else}
								<span>{user.username.slice(0, 2).toUpperCase()}</span>
							{/if}
						</div>
						<div class="user-details">
							<span class="user-name">{user.username}</span>
							<span class="user-sub">
								{#if user.is_admin}<span class="meta-chip"><Icon name="crown" size={13} /> {$t('settings_user_admin_badge')}</span>{/if}
								<span class="meta-chip"><Icon name={user.team_name ? 'shield' : 'user'} size={13} /> {user.team_name || $t('settings_user_solo')}</span>
								{#if user.seat_id}
									<a class="meta-chip meta-link" href="/dashboard/map?highlight={encodeURIComponent(user.seat_id)}" title={$t('tourneys_view_on_map')}><Icon name="pin" size={13} /> {$t('settings_user_seat_prefix')} {user.seat_id}</a>
								{/if}
							</span>
						</div>
					</div>

					<div class="row-sub account-actions">
						<button class="btn-secondary btn-compact btn-ic" on:click={() => goto('/dashboard/profile')}>
							<Icon name="trophy" size={15} /> {$t('settings_btn_view_profile')}
						</button>
						<button class="btn-secondary btn-compact btn-ic" on:click={handleLogout}>
							<Icon name="logout" size={15} /> {$t('settings_btn_logout')}
						</button>
						{#if !user.is_admin}
							<button class="btn-outline-danger btn-compact btn-ic" on:click={confirmDeleteAccount}>
								<Icon name="trash" size={15} /> {$t('profile_btn_delete_account')}
							</button>
						{/if}
					</div>
				</section>
			{/if}

			<!-- À PROPOS -->
			<section class="settings-section glass">
				<header class="section-head">
					<span class="section-ic"><Icon name="info" size={20} /></span>
					<div class="title-text">
						<h2>{$t('settings_section_about')}</h2>
						<p>Alanbix Companion LAN Management System</p><!-- i18n-ignore: product name -->
					</div>
				</header>

				<div class="rows about-rows">
					<div class="row static compact">
						<span class="row-text"><span class="row-title">{lbl($t('settings_app_version'))}</span></span>
						<span class="row-val font-mono">v{appVersion}</span>
					</div>
					<div class="row static compact">
						<span class="row-text"><span class="row-title">{lbl($t('settings_server_version'))}</span></span>
						<span class="row-val font-mono">v{serverVersion}</span>
					</div>
					<div class="row static compact">
						<span class="row-text"><span class="row-title">{lbl($t('settings_app_type'))}</span></span>
						<span class="row-val"><Icon name={isCapacitorNative() ? 'smartphone' : 'monitor'} size={14} /> {isCapacitorNative() ? 'Alanbix Mobile' : 'Alanbix Web'}</span><!-- i18n-ignore: product name -->
					</div>
					<div class="row static compact">
						<span class="row-text"><span class="row-title">{lbl($t('settings_demo_mode_label'))}</span></span>
						<button class="btn-secondary btn-compact btn-ic" on:click={toggleDemoMode} type="button">
							<Icon name="flask" size={15} /> {demoActive ? $t('settings_demo_disable') : $t('settings_demo_enable')}
						</button>
					</div>
					<div class="row static compact">
						<span class="row-text"><span class="row-title">{lbl($t('settings_license_label'))}</span></span>
						<span class="row-val">MIT · Open Source</span><!-- i18n-ignore: licence name -->
					</div>
					<div class="row static compact">
						<span class="row-text"><span class="row-title">{lbl($t('settings_privacy_label'))}</span></span>
						<a class="btn-secondary btn-compact btn-ic privacy-link" href={privacyUrl} target="_blank" rel="noopener noreferrer">
							<Icon name="shield" size={15} /> {$t('settings_privacy_open')}
						</a>
					</div>
					<div class="row static compact">
						<span class="row-text"><span class="row-title">App ID</span></span><!-- i18n-ignore: technical identifier -->
						<span class="row-val font-mono">com.amifystudio.alanbix</span><!-- i18n-ignore -->
					</div>
				</div>
			</section>
		</div>
	</div>
</div>

<ServerConfigModal isOpen={showServerModal} on:close={() => { showServerModal = false; }} />
<Modal bind:show={showModal} title={modalTitle} message={modalMessage} type={modalType} onConfirm={modalConfirmCallback} />

<style>
	/* Settings: one pattern everywhere.
	   Section card -> flat rows (icon tile, title + hint, control on the right)
	   separated by hairlines. Type scale: section title --fs-section, row title
	   0.9375rem, hint 0.8125rem, values and buttons 0.875rem, badges 0.75rem. */
	.settings-page {
		--tile: 36px;
		max-width: 1180px;
		margin: 0 auto;
		padding: 0 0 6rem;
	}

	/* Header */
	.settings-header {
		display: flex;
		align-items: center;
		gap: 0.9rem;
		margin-bottom: 1.25rem;
	}
	.back-btn {
		display: inline-flex;
		align-items: center;
		justify-content: center;
		width: 38px;
		height: 38px;
		flex-shrink: 0;
		background: var(--surface-raised);
		border: 1px solid var(--glass-border);
		color: var(--text-dim);
		border-radius: var(--radius-md);
		cursor: pointer;
		transition: color 0.15s, border-color 0.15s;
	}
	.back-btn:hover { color: var(--accent); border-color: var(--accent); }
	.header-title-box { min-width: 0; }
	.header-title-box h1 { margin: 0; color: var(--text-main); }
	.header-title-box .subtitle {
		margin: 0.15rem 0 0;
		font-size: 0.875rem;
		color: var(--text-dim);
	}

	/* Layout: two columns on wide screens, one on phones */
	.settings-content {
		display: grid;
		grid-template-columns: minmax(0, 1fr);
		gap: 1rem;
		align-items: start;
	}
	.settings-col {
		display: flex;
		flex-direction: column;
		gap: 1rem;
		min-width: 0;
	}
	@media (min-width: 1100px) {
		.settings-content { grid-template-columns: minmax(0, 1.35fr) minmax(0, 1fr); }
	}

	.settings-section {
		border-radius: var(--radius-lg);
		padding: 1.25rem 1.5rem 1rem;
	}

	/* Section head */
	.section-head {
		display: flex;
		align-items: center;
		gap: 0.9rem;
		margin-bottom: 0.75rem;
	}
	.section-ic {
		display: inline-flex;
		align-items: center;
		justify-content: center;
		width: 40px;
		height: 40px;
		flex-shrink: 0;
		border-radius: var(--radius-lg);
		background: var(--accent-soft);
		color: var(--accent);
	}
	.section-head .title-text { flex: 1; min-width: 0; }
	.section-head h2 {
		font-size: var(--fs-section);
		margin: 0;
		color: var(--text-main);
	}
	.section-head p {
		margin: 0.15rem 0 0;
		font-size: 0.875rem;
		color: var(--text-dim);
	}

	/* Sub-groups inside a section */
	.settings-subgroup { margin-top: 0.5rem; padding-top: 1rem; border-top: 1px solid var(--glass-border); }
	.settings-subgroup h3 {
		font-size: var(--fs-sub);
		font-weight: 700;
		color: var(--text-muted);
		margin: 0 0 0.25rem;
		text-transform: uppercase;
		letter-spacing: 0.06em;
	}

	/* Rows */
	.rows { display: flex; flex-direction: column; }
	.row {
		display: flex;
		align-items: center;
		gap: 0.85rem;
		padding: 0.8rem 0;
		min-height: 3.25rem;
	}
	.rows > .row + .row,
	.rows > .row-sub + .row { border-top: 1px solid var(--glass-border); }
	label.row { cursor: pointer; }
	label.row:hover .row-title { color: var(--accent); }
	.row.compact { min-height: 0; padding: 0.55rem 0; }
	.row.nested { padding-left: calc(var(--tile) + 0.85rem); min-height: 0; }
	.row-ic {
		display: inline-flex;
		align-items: center;
		justify-content: center;
		width: var(--tile);
		height: var(--tile);
		flex-shrink: 0;
		border-radius: 10px;
		background: var(--accent-soft);
		color: var(--accent);
	}
	.row-text {
		flex: 1;
		min-width: 0;
		display: flex;
		flex-direction: column;
		gap: 0.15rem;
	}
	.row-title { font-size: 0.9375rem; font-weight: 600; color: var(--text-main); transition: color 0.15s; }
	.row-desc { font-size: 0.8125rem; color: var(--text-dim); line-height: 1.35; }
	.row-val {
		font-size: 0.875rem;
		color: var(--text-main);
		text-align: right;
		word-break: break-all;
		display: inline-flex;
		align-items: center;
		gap: 0.35rem;
		min-width: 0;
	}
	.about-rows .row-title { font-weight: 500; color: var(--text-dim); }

	/* Action line under a row, aligned with the row text */
	.row-sub {
		display: flex;
		flex-wrap: wrap;
		align-items: center;
		gap: 0.5rem;
		padding: 0 0 0.85rem calc(var(--tile) + 0.85rem);
	}
	.row-sub:last-child { padding-bottom: 0.5rem; }
	.section-head + .row-sub,
	.user-summary + .row-sub { padding-left: 0; }
	.account-actions { padding-left: 0; padding-top: 0.75rem; }
	.about-rows .row:last-child { padding-bottom: 0; }

	/* Buttons: global .btn-primary / .btn-secondary / .btn-outline-danger, compact here */
	.btn-compact { padding: 0.4rem 0.8rem; font-size: 0.8125rem; }
	.btn-ic { display: inline-flex; align-items: center; gap: 0.4rem; }
	.btn-ic:disabled { opacity: 0.55; cursor: default; }

	/* Badges */
	.badge {
		display: inline-flex;
		align-items: center;
		gap: 0.3rem;
		font-size: 0.75rem;
		padding: 0.2rem 0.6rem;
		border-radius: 999px;
		font-weight: 600;
		border: 1px solid transparent;
		white-space: nowrap;
	}
	.badge-green { color: var(--success); background: color-mix(in srgb, var(--success) 14%, transparent); border-color: color-mix(in srgb, var(--success) 35%, transparent); }
	.badge-red { color: var(--danger); background: color-mix(in srgb, var(--danger) 12%, transparent); border-color: color-mix(in srgb, var(--danger) 35%, transparent); }
	.badge-yellow { color: var(--warning); background: color-mix(in srgb, var(--warning) 14%, transparent); border-color: color-mix(in srgb, var(--warning) 38%, transparent); }
	.badge-blue { color: var(--accent); background: var(--accent-soft); border-color: color-mix(in srgb, var(--accent) 35%, transparent); }
	.ssids-list { display: flex; gap: 0.4rem; flex-wrap: wrap; justify-content: flex-end; }

	/* Form fields */
	.field {
		background: var(--surface-sunken);
		border: 1px solid var(--glass-border);
		color: var(--text-main);
		padding: 0.4rem 0.65rem;
		border-radius: var(--radius-md);
		font-size: 0.875rem;
		font-family: inherit;
		max-width: 280px;
		flex-shrink: 0;
	}
	.field:focus-visible { outline: 2px solid var(--accent); outline-offset: 1px; }
	.dnd-times { gap: 1rem; }
	.time-field { display: inline-flex; align-items: center; gap: 0.5rem; font-size: 0.875rem; color: var(--text-dim); }

	/* Segmented control (theme, language): the selected option is tinted */
	.seg {
		display: inline-flex;
		padding: 3px;
		gap: 2px;
		border-radius: var(--radius-md);
		background: var(--surface-sunken);
		border: 1px solid var(--glass-border);
		flex-shrink: 0;
	}
	.seg-btn {
		display: inline-flex;
		align-items: center;
		gap: 0.4rem;
		padding: 0.35rem 0.75rem;
		border: 1px solid transparent;
		border-radius: calc(var(--radius-md) - 2px);
		background: transparent;
		color: var(--text-dim);
		font-size: 0.8125rem;
		font-weight: 600;
		cursor: pointer;
		transition: color 0.15s, background 0.15s, border-color 0.15s;
	}
	.seg-btn:hover { color: var(--text-main); }
	.seg-btn.on { background: var(--accent-soft); border-color: var(--accent); color: var(--accent); }
	.seg-btn:focus-visible { outline: 2px solid var(--accent); outline-offset: 1px; }

	/* Switch */
	.switch {
		position: relative;
		display: inline-block;
		width: 44px;
		height: 24px;
		min-width: 44px;
		flex-shrink: 0;
	}
	.switch input {
		position: absolute;
		opacity: 0;
		width: 100%;
		height: 100%;
		margin: 0;
		cursor: pointer;
		z-index: 1;
	}
	.slider {
		position: absolute;
		inset: 0;
		background-color: var(--text-muted);
		opacity: 0.45;
		transition: background-color 0.2s, opacity 0.2s;
		border-radius: 12px;
		pointer-events: none;
	}
	.slider:before {
		position: absolute;
		content: "";
		height: 18px;
		width: 18px;
		left: 3px;
		top: 3px;
		background-color: #fff;
		transition: transform 0.2s;
		border-radius: 50%;
		box-shadow: 0 1px 3px rgba(0, 0, 0, 0.25);
	}
	input:checked + .slider { background-color: var(--accent-solid); opacity: 1; }
	input:checked + .slider:before { transform: translateX(20px); }
	input:disabled + .slider { opacity: 0.35; }
	input:focus-visible + .slider { outline: 2px solid var(--accent); outline-offset: 2px; }

	/* Account */
	.user-summary {
		display: flex;
		align-items: center;
		gap: 0.9rem;
		padding: 0.75rem 0;
		border-top: 1px solid var(--glass-border);
	}
	.user-avatar {
		width: 48px;
		height: 48px;
		flex-shrink: 0;
		border-radius: 50%;
		background: var(--accent-solid);
		display: flex;
		align-items: center;
		justify-content: center;
		font-weight: 700;
		color: #fff;
		overflow: hidden;
	}
	/* a picture keeps the shape and the transparency chosen on the profile: no solid colour behind it */
	.user-avatar.has-img { background: var(--bg-tertiary); }
	.user-avatar img { width: 100%; height: 100%; object-fit: cover; }
	.user-details { display: flex; flex-direction: column; gap: 0.25rem; min-width: 0; }
	.user-name { font-size: 1.0625rem; font-weight: 700; color: var(--text-main); }
	.user-sub { display: flex; flex-wrap: wrap; gap: 0.35rem 0.75rem; font-size: 0.8125rem; color: var(--text-dim); }
	.meta-chip { display: inline-flex; align-items: center; gap: 0.3rem; }
	.meta-link { color: var(--accent); text-decoration: none; font-weight: 600; }
	.meta-link:hover { text-decoration: underline; }

	.font-mono { font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace; }

	@media (max-width: 640px) {
		.settings-page { padding-bottom: 6.5rem; }
		.settings-section { padding: 1rem 1rem 0.75rem; }
		.settings-header { margin-bottom: 1rem; }
		.row-sub { padding-left: 0; }
		.row.static { flex-wrap: wrap; row-gap: 0.4rem; }
		/* the text keeps a minimum width, so a wide badge wraps below instead of overlapping it */
		.row.static > .row-text { flex: 1 1 9rem; }
		.row.static > .badge { margin-left: auto; }
		/* controls that do not fit beside the title drop to their own line */
		.row.static > .seg,
		.row.static > .field { margin-left: calc(var(--tile) + 0.85rem); }
		.field { max-width: 100%; }
		.row.static > .row-val,
		.row.static > .ssids-list { flex-basis: 100%; text-align: left; justify-content: flex-start; margin-left: calc(var(--tile) + 0.85rem); }
		.about-rows .row.static { flex-wrap: nowrap; }
		.about-rows .row.static > .row-val { flex-basis: auto; margin-left: 0; text-align: right; }
		.account-actions button { flex: 1 1 100%; justify-content: center; }
	}
	.privacy-link { text-decoration: none; white-space: nowrap; }
</style>
