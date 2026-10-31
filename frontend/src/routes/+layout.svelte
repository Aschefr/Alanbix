<script>
	import '../app.css';
	import { onMount } from 'svelte';
	import { initI18n, eventName, customPageTitle, t } from '$lib/i18nStore';
	import { isDemoMode, disableDemoMode } from '$lib/config';
	import { initTheme } from '$lib/theme';
	import { page } from '$app/stores';

	let demoActive = false;

	onMount(async () => {
		initTheme();
		demoActive = isDemoMode();
		if (typeof window !== 'undefined' && window.Capacitor) {
			try {
				const plugins = window.Capacitor.Plugins || {};
				if (plugins.SplashScreen && typeof plugins.SplashScreen.hide === 'function') {
					setTimeout(() => plugins.SplashScreen.hide().catch(() => {}), 300);
				}
				if (plugins.App && typeof plugins.App.addListener === 'function') {
					plugins.App.addListener('backButton', ({ canGoBack }) => {
						if (canGoBack && window.location.pathname !== '/' && window.location.pathname !== '/dashboard') {
							window.history.back();
						} else if (typeof plugins.App.minimizeApp === 'function') {
							plugins.App.minimizeApp().catch(() => {});
						}
					});
				}
			} catch {}
		}
		await initI18n();
	});

	function exitDemoMode() {
		disableDemoMode();
		demoActive = false;
		window.location.href = '/';
	}

	// Reset custom page title on navigation
	$: if ($page && $page.url && $page.url.pathname) {
		customPageTitle.set('');
		demoActive = isDemoMode();
	}

	function getPageTitle(path, $t) {
		if (path === '/') return $t('login_submit');
		if (path === '/dashboard') return $t('nav_dashboard');
		if (path === '/dashboard/info') return $t('nav_infos');
		if (path === '/dashboard/tournaments') return $t('nav_tournaments');
		if (path.startsWith('/dashboard/tournaments/')) {
			return $t('nav_tournaments');
		}
		if (path === '/dashboard/players') return $t('nav_players');
		if (path === '/dashboard/notifications') return $t('nav_notifications');
		if (path === '/dashboard/ai') return $t('nav_ai_assistant');
		if (path === '/dashboard/map') return $t('nav_map');
		if (path === '/dashboard/profile') return $t('profile_title');
		if (path === '/dashboard/settings') return $t('settings_page_title');
		if (path === '/dashboard/admin') return $t('nav_administration');
		if (path === '/dashboard/admin/languages') return $t('admin_tab_languages');
		if (path === '/dashboard/welcome') return $t('page_title_welcome');
		if (path === '/spectator') return $t('nav_spectator');
		if (path === '/map') return $t('map_public_title');
		
		// Fallback capitalizing pathname segments
		const segments = path.split('/').filter(Boolean);
		if (segments.length > 0) {
			let last = segments[segments.length - 1];
			if (/^\d+$/.test(last) && segments.length > 1) {
				last = segments[segments.length - 2];
			}
			return last.charAt(0).toUpperCase() + last.slice(1);
		}
		return '';
	}

	$: pageName = $customPageTitle || getPageTitle($page?.url?.pathname || '', $t);
	$: documentTitle = pageName ? `${$eventName} - ${pageName}` : $eventName;
</script>

<svelte:head>
	<title>{documentTitle}</title>
</svelte:head>

<div class="app-container">
	{#if demoActive}
		<div class="demo-mode-banner">
			<span>✨ <strong>{$t('demo_banner_title')}</strong> {$t('demo_banner_desc')}</span>
			<button type="button" class="demo-exit-btn" on:click={exitDemoMode}>
				{$t('demo_banner_connect')}
			</button>
		</div>
	{/if}
	<slot />
</div>

<style>
	:global(body) {
		margin: 0;
		padding: 0;
		background-color: transparent; /* the page colour is on <html>, so the fixed mesh gradient shows everywhere */
		color: var(--text-main);
		font-family: 'Inter', sans-serif;
		-webkit-font-smoothing: antialiased;
	}

	.app-container {
		min-height: 100vh;
		display: flex;
		flex-direction: column;
	}

	.demo-mode-banner {
		display: flex;
		align-items: center;
		justify-content: center;
		gap: 1rem;
		padding: 0.45rem 1rem;
		background: linear-gradient(90deg, rgba(16, 185, 129, 0.2), rgba(59, 130, 246, 0.2));
		border-bottom: 1px solid rgba(16, 185, 129, 0.35);
		font-size: 0.8rem;
		color: var(--text-main);
		z-index: 1000;
		flex-wrap: wrap;
	}

	.demo-exit-btn {
		padding: 0.25rem 0.65rem;
		border-radius: 6px;
		border: 1px solid rgba(255, 255, 255, 0.25);
		background: rgba(0, 0, 0, 0.25);
		color: inherit;
		font-size: 0.75rem;
		font-weight: 600;
		cursor: pointer;
	}
</style>
