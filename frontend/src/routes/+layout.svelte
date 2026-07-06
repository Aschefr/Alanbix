<script>
	import '../app.css';
	import { onMount } from 'svelte';
	import { initI18n, eventName, customPageTitle, t } from '$lib/i18nStore';
	import { page } from '$app/stores';

	onMount(async () => {
		const saved = localStorage.getItem('alanbix_theme') || 'dark';
		document.documentElement.setAttribute('data-theme', saved);
		await initI18n();
	});

	// Reset custom page title on navigation
	$: if ($page.url.pathname) {
		customPageTitle.set('');
	}

	function getPageTitle(path, $t) {
		if (path === '/') return $t('login_submit') || 'Connexion';
		if (path === '/dashboard') return $t('nav_dashboard') || 'Dashboard';
		if (path === '/dashboard/info') return $t('nav_infos') || 'Infos';
		if (path === '/dashboard/tournaments') return $t('nav_tournaments') || 'Tournois';
		if (path.startsWith('/dashboard/tournaments/')) {
			return $t('nav_tournaments') || 'Tournois';
		}
		if (path === '/dashboard/players') return $t('nav_players') || 'Joueurs';
		if (path === '/dashboard/notifications') return $t('nav_notifications') || 'Notifications';
		if (path === '/dashboard/ai') return $t('nav_ai_assistant') || 'Assistant IA';
		if (path === '/dashboard/map') return $t('nav_map') || 'Plan Salle';
		if (path === '/dashboard/profile') return $t('profile_title') || 'Mon Profil';
		if (path === '/dashboard/admin') return $t('nav_administration') || 'Administration';
		if (path === '/dashboard/admin/languages') return $t('admin_tab_languages') || 'Langues';
		if (path === '/dashboard/welcome') return 'Choix du poste';
		if (path === '/spectator') return $t('nav_spectator') || 'Projecteur';
		if (path === '/map') return $t('map_public_title') || 'Plan de la salle';
		
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

	$: pageName = $customPageTitle || getPageTitle($page.url.pathname, $t);
	$: documentTitle = pageName ? `${$eventName} - ${pageName}` : $eventName;
</script>

<svelte:head>
	<title>{documentTitle}</title>
</svelte:head>

<div class="app-container">
	<slot />
</div>

<style>
	:global(body) {
		margin: 0;
		padding: 0;
		background-color: var(--bg-primary);
		color: var(--text-main);
		font-family: 'Inter', sans-serif;
		-webkit-font-smoothing: antialiased;
	}

	.app-container {
		min-height: 100vh;
		display: flex;
		flex-direction: column;
	}
</style>
