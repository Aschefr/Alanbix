<script>
	import { t, flagMap } from '$lib/i18nStore';
	import { api } from '$lib/api';
	import { API_URL } from '$lib/config';
	import { onMount } from 'svelte';
	import { beforeNavigate } from '$app/navigation';

	let languages = ['fr', 'en'];
	let refLang = 'fr';
	let targetLang = 'en';
	let refData = {};
	let targetData = {};
	
	let searchQuery = '';
	
	let newLangCode = '';
	let creatingLang = false;
	let selectedAddCode = '';

	$: addableLanguages = Object.keys(flagMap)
		.filter(code => !languages.includes(code))
		.map(code => ({ code, label: `${flagMap[code]} (${code.toUpperCase()})` }));

	let toasts = [];
	let toastId = 0;
	function toast(message, type = 'info') {
		const id = ++toastId;
		toasts = [...toasts, { id, message, type, leaving: false }];
		setTimeout(() => {
			toasts = toasts.map(t => t.id === id ? { ...t, leaving: true } : t);
			setTimeout(() => { toasts = toasts.filter(t => t.id !== id); }, 400);
		}, 3000);
	}

	let authorized = false;

	let lanMultilingual = false;
	let lanDefaultLanguage = 'fr';

	// ─── Category definitions ──────────────────────────────────
	const CATEGORY_MAP = {
		system:       { label: 'Prompts Système IA',     icon: '🤖', order: 0 },
		login:        { label: 'Connexion',              icon: '🔑', order: 1 },
		register:     { label: 'Inscription',            icon: '📝', order: 2 },
		nav:          { label: 'Navigation',             icon: '🧭', order: 3 },
		dash:         { label: 'Dashboard',              icon: '📊', order: 4 },
		tourneys:     { label: 'Tournois (Joueur)',      icon: '🏆', order: 5 },
		tournament:   { label: 'Tournois (Détails)',     icon: '🏅', order: 6 },
		map:          { label: 'Plan de Salle',          icon: '🗺️', order: 7 },
		players:      { label: 'Joueurs',                icon: '👥', order: 8 },
		ai:           { label: 'Assistant IA',           icon: '💬', order: 9 },
		ia:           { label: 'Configuration IA',       icon: '⚙️', order: 10 },
		profile:      { label: 'Profil',                 icon: '👤', order: 11 },
		info:         { label: 'Page Infos',             icon: 'ℹ️', order: 12 },
		spec:         { label: 'Vue Projecteur',         icon: '📺', order: 13 },
		welcome:      { label: 'Tutoriel Accueil',       icon: '👋', order: 14 },
		admin:        { label: 'Administration',         icon: '🛠️', order: 15 },
		notif:        { label: 'Notifications',          icon: '🔔', order: 16 },
		notifs:       { label: 'Notifications (Liste)',  icon: '📋', order: 17 },
		award:        { label: 'Prix & Distinctions',    icon: '🎖️', order: 18 },
		stats:        { label: 'Statistiques',           icon: '📈', order: 19 },
		changelog:    { label: 'Historique Versions',    icon: '📦', order: 20 },
		distillation: { label: 'Distillation (Loading)', icon: '⏳', order: 21 },
	};
	const OTHER_CATEGORY = { label: 'Divers', icon: '📎', order: 999 };

	const KEY_CATEGORY_OVERRIDES = {
		'tournament_closing_prompt': 'system',
	};

	function getCategoryForKey(key) {
		if (KEY_CATEGORY_OVERRIDES[key]) return KEY_CATEGORY_OVERRIDES[key];
		const prefix = key.split('_')[0];
		return CATEGORY_MAP[prefix] ? prefix : '_other';
	}

	function getCategoryMeta(cat, t_func) {
		const meta = CATEGORY_MAP[cat] || OTHER_CATEGORY;
		const key = cat === '_other' || cat === 'other' ? 'admin_languages_cat_other' : `admin_languages_cat_${cat}`;
		return {
			...meta,
			label: t_func(key) || meta.label
		};
	}

	// ─── Active category (sidebar navigation) ──────────────────
	let activeCategory = null;

	function selectCategory(cat) {
		activeCategory = cat;
		// Scroll to top of editor
		const el = document.querySelector('.editor-main');
		if (el) el.scrollTop = 0;
	}

	// ─── Dirty tracking ──────────────────────────────────
	let hasUnsavedChanges = false;
	let savedSnapshot = '{}';

	function markDirty() {
		hasUnsavedChanges = JSON.stringify(targetData) !== savedSnapshot;
	}

	function handleFieldInput(key, e) {
		targetData[key] = e.target.value;
		targetData = targetData;
		markDirty();
	}

	onMount(async () => {
		try {
			const me = await api.get('/me');
			if (!me.is_admin) {
				window.location.href = '/dashboard';
				return;
			}
			authorized = true;
		} catch (err) {
			window.location.href = '/';
			return;
		}
		const savedRef = localStorage.getItem('alanbix_ref_lang');
		const savedTarget = localStorage.getItem('alanbix_target_lang');
		if (savedRef) refLang = savedRef;
		if (savedTarget) targetLang = savedTarget;
		loadLanguages();
		loadSettings();
	});

	beforeNavigate((navigation) => {
		if (hasUnsavedChanges) {
			const confirmLeave = confirm($t('admin_languages_unsaved_warning') || "Vous avez des modifications non enregistrées. Voulez-vous vraiment quitter cette page ?");
			if (!confirmLeave) {
				navigation.cancel();
			}
		}
	});

	async function loadSettings() {
		try {
			const stats = await api.get('/dashboard/stats');
			lanMultilingual = !!stats.lan_multilingual;
			lanDefaultLanguage = stats.lan_default_language || 'fr';
		} catch (err) {
			console.error('Failed to load settings:', err);
		}
	}

	async function saveLanMultilingual() {
		try {
			await api.put('/admin/config/lan_multilingual', { value: lanMultilingual });
			toast($t('admin_languages_toast_setting_saved'), 'success');
		} catch { toast($t('admin_languages_toast_save_error', { error: '' }), 'error'); }
	}

	async function saveLanDefaultLanguage() {
		try {
			await api.put('/admin/config/lan_default_language', { value: lanDefaultLanguage });
			toast($t('admin_languages_toast_setting_saved'), 'success');
		} catch { toast($t('admin_languages_toast_save_error', { error: '' }), 'error'); }
	}

	async function loadLanguages() {
		try {
			const res = await api.get('/i18n/languages');
			languages = res.languages || ['fr', 'en'];
			if (!languages.includes(refLang)) refLang = languages[0] || 'fr';
			if (!languages.includes(targetLang)) targetLang = languages[1] || languages[0] || 'en';
			await Promise.all([loadRefData(), loadTargetData()]);
		} catch (err) {
			toast($t('admin_languages_toast_load_error', { error: err.message }), 'error');
		}
	}

	async function loadRefData() {
		try {
			const res = await api.get(`/api/i18n/${refLang}`);
			refData = res || {};
		} catch (err) {
			toast($t('admin_languages_toast_load_error', { error: err.message }), 'error');
		}
	}

	async function loadTargetData() {
		try {
			const res = await api.get(`/api/i18n/${targetLang}`);
			targetData = res || {};
			savedSnapshot = JSON.stringify(targetData);
			hasUnsavedChanges = false;
		} catch (err) {
			toast($t('admin_languages_toast_load_error', { error: err.message }), 'error');
		}
	}

	async function createLang() {
		const code = (selectedAddCode === 'custom' ? newLangCode : selectedAddCode).trim().toLowerCase();
		if (!code) return;
		creatingLang = true;
		try {
			await api.post(`/api/i18n/${code}`);
			toast($t('admin_languages_toast_created', { code: code.toUpperCase() }), 'success');
			newLangCode = '';
			selectedAddCode = '';
			await loadLanguages();
			targetLang = code;
			localStorage.setItem('alanbix_target_lang', targetLang);
			await loadTargetData();
		} catch (err) {
			toast($t('admin_languages_toast_create_error', { error: err.message }), 'error');
		} finally {
			creatingLang = false;
		}
	}

	let showDeleteConfirm = false;

	async function confirmDeleteLang() {
		showDeleteConfirm = false;
		const lang = targetLang;
		try {
			await api.delete(`/api/i18n/${lang}`);
			toast($t('admin_languages_toast_deleted', { lang: lang.toUpperCase() }), 'success');
			if (targetLang === lang) {
				targetLang = 'en';
				localStorage.setItem('alanbix_target_lang', targetLang);
			}
			await loadLanguages();
		} catch (err) {
			toast($t('admin_languages_toast_delete_error', { error: err.message }), 'error');
		}
	}

	let isSaving = false;
	async function saveTargetData() {
		isSaving = true;
		try {
			await api.put(`/api/i18n/${targetLang}`, targetData);
			savedSnapshot = JSON.stringify(targetData);
			hasUnsavedChanges = false;
			toast($t('admin_languages_toast_saved'), 'success');
		} catch (err) {
			toast($t('admin_languages_toast_save_error', { error: err.message }), 'error');
		} finally {
			isSaving = false;
		}
	}

	async function handleRefChange(e) {
		refLang = e.target.value;
		localStorage.setItem('alanbix_ref_lang', refLang);
		await loadRefData();
	}

	async function handleTargetChange(e) {
		targetLang = e.target.value;
		localStorage.setItem('alanbix_target_lang', targetLang);
		await loadTargetData();
	}

	// ─── Keys, search, grouping ──────────────────────────────────
	$: allKeys = Array.from(new Set([...Object.keys(refData), ...Object.keys(targetData)]));
	$: filteredKeys = allKeys.filter(key => {
		const q = searchQuery.toLowerCase();
		if (!q) return true;
		const refVal = (refData[key] || '').toLowerCase();
		const targetVal = (targetData[key] || '').toLowerCase();
		return key.toLowerCase().includes(q) || refVal.includes(q) || targetVal.includes(q);
	});

	// Group keys by category
	$: groupedKeys = (() => {
		const groups = {};
		for (const key of filteredKeys) {
			const cat = getCategoryForKey(key);
			if (!groups[cat]) groups[cat] = [];
			groups[cat].push(key);
		}
		// Sort keys inside each category alphabetically
		for (const cat in groups) {
			groups[cat].sort((a, b) => a.localeCompare(b));
		}
		const sortedEntries = Object.entries(groups).sort((a, b) => {
			const ma = getCategoryMeta(a[0], $t);
			const mb = getCategoryMeta(b[0], $t);
			return ma.order - mb.order;
		});
		return sortedEntries;
	})();

	// Auto-select first category if none active or active no longer in list
	$: {
		const cats = groupedKeys.map(([c]) => c);
		if (!activeCategory || !cats.includes(activeCategory)) {
			activeCategory = cats[0] || null;
		}
	}

	// Active category keys
	$: activeCategoryKeys = groupedKeys.find(([c]) => c === activeCategory)?.[1] || [];

	// Global stats
	$: totalKeys = allKeys.length;
	$: translatedCount = allKeys.filter(k => targetData[k] && targetData[k].trim() !== '').length;
	$: missingCount = allKeys.filter(k => !targetData[k] || targetData[k].trim() === '').length;
	// Keys that exist in ref but are completely absent from target file (structural sync needed)
	$: structuralMissingCount = Object.keys(refData).filter(k => !(k in targetData)).length;

	function catMissingCount(keys) {
		return keys.filter(k => !targetData[k] || targetData[k].trim() === '').length;
	}

	// autoResize directive
	function autoResize(node, value) {
		const resize = () => {
			node.style.height = 'auto';
			node.style.height = node.scrollHeight + 'px';
		};
		setTimeout(resize, 0);
		return {
			update(newValue) { setTimeout(resize, 0); },
			destroy() {}
		};
	}

	let showAutoTranslateModal = false;
	let isTranslating = false;
	let translateCurrent = 0;
	let translateTotal = 0;
	let translateProgress = 0;
	let translateInstances = 0;
	let bulkAbortController = null;

	async function translateSingleKey(key) {
		const sourceText = refData[key];
		if (!sourceText) {
			toast($t('admin_languages_toast_source_empty'), 'error');
			return;
		}
		try {
			const res = await api.post('/api/i18n/auto-translate', {
				text: sourceText,
				source_lang: refLang,
				target_lang: targetLang
			});
			targetData[key] = res.translated_text;
			targetData = { ...targetData };
			markDirty();
			toast($t('admin_languages_toast_translated_single'), 'success');
		} catch (err) {
			toast($t('admin_languages_toast_translate_error', { error: err.message }), 'error');
		}
	}

	async function runBulkTranslation(onlyEmpty) {
		showAutoTranslateModal = false;
		const keys = allKeys.filter(key => {
			if (onlyEmpty) return !targetData[key] || targetData[key].trim() === '';
			return true;
		});

		if (keys.length === 0) {
			toast($t('admin_languages_toast_no_fields'), 'info');
			return;
		}

		// Build source_data map for only the keys we need
		const sourceData = {};
		for (const key of keys) {
			sourceData[key] = refData[key] || '';
		}

		isTranslating = true;
		translateTotal = keys.length;
		translateCurrent = 0;
		translateProgress = 0;
		translateInstances = 0;

		// AbortController for cancellation
		bulkAbortController = new AbortController();

		try {
			const token = localStorage.getItem('alanbix_token');

			const response = await fetch(`${API_URL}/api/i18n/bulk-translate`, {
				method: 'POST',
				headers: {
					'Content-Type': 'application/json',
					'Authorization': `Bearer ${token}`
				},
				body: JSON.stringify({
					keys,
					source_lang: refLang,
					target_lang: targetLang,
					source_data: sourceData
				}),
				signal: bulkAbortController.signal
			});

			if (!response.ok) {
				const err = await response.json().catch(() => ({ detail: 'Unknown error' }));
				throw new Error(err.detail || `HTTP ${response.status}`);
			}

			const reader = response.body.getReader();
			const decoder = new TextDecoder();
			let buffer = '';

			while (true) {
				const { done, value } = await reader.read();
				if (done) break;

				buffer += decoder.decode(value, { stream: true });
				const lines = buffer.split('\n');
				buffer = lines.pop() || '';

				for (const line of lines) {
					if (!line.startsWith('data: ')) continue;
					try {
						const data = JSON.parse(line.slice(6));

						if (data.type === 'start') {
							translateTotal = data.total;
							translateInstances = data.instances;
						} else if (data.type === 'result') {
							targetData[data.key] = data.translation;
							targetData = { ...targetData };
							translateCurrent = data.progress;
							translateProgress = Math.round((data.progress / data.total) * 100);
						} else if (data.type === 'error') {
							console.warn(`Translation error for key '${data.key}' on ${data.instance}:`, data.error);
							translateCurrent = data.progress;
							translateProgress = Math.round((data.progress / data.total) * 100);
						} else if (data.type === 'instance_lost') {
							translateInstances = Math.max(0, translateInstances - 1);
							toast(`⚠️ Instance ${data.instance} perdue, poursuite avec ${translateInstances} instance(s)`, 'warning');
						} else if (data.type === 'done') {
							translateCurrent = data.completed;
							translateProgress = 100;
						} else if (data.type === 'cancelled') {
							break;
						}
					} catch (e) {
						// Ignore parse errors (keepalive comments etc.)
					}
				}
			}
		} catch (err) {
			if (err.name === 'AbortError') {
				toast($t('admin_languages_progress_banner_cancel'), 'info');
			} else {
				toast($t('admin_languages_toast_translate_error', { error: err.message }), 'error');
			}
		} finally {
			isTranslating = false;
			bulkAbortController = null;
			markDirty();
			if (translateProgress >= 100) {
				toast($t('admin_languages_toast_bulk_done'), 'success');
				saveTargetData();
			}
		}
	}

	function cancelBulkTranslation() {
		if (bulkAbortController) {
			bulkAbortController.abort();
		}
	}

	// ─── Sync missing keys ──────────────────────────────────
	let isSyncing = false;
	async function syncMissingKeys() {
		isSyncing = true;
		try {
			const res = await api.post(`/api/i18n/${targetLang}/sync`);
			if (res.missing_count > 0) {
				toast($t('admin_languages_toast_sync_done', { count: res.missing_count }), 'success');
				await loadTargetData();
			} else {
				toast($t('admin_languages_toast_sync_uptodate'), 'info');
			}
		} catch (err) {
			toast($t('admin_languages_toast_sync_error', { error: err.message }), 'error');
		} finally {
			isSyncing = false;
		}
	}

	function portal(node) {
		document.body.appendChild(node);
		return {
			destroy() {
				if (node.parentNode) node.parentNode.removeChild(node);
			}
		};
	}

	function langFullName(code) {
		return flagMap[code] || code.toUpperCase();
	}
</script>

<svelte:window on:beforeunload={(e) => {
	if (hasUnsavedChanges) {
		e.preventDefault();
		e.returnValue = '';
	}
}} />

{#if authorized}
<div class="lang-page">
	<!-- ─── Title bar ──────────────────────────────────────── -->
	<div class="header-title-bar">
		<a href="/dashboard/admin" class="back-link">← {$t('admin_languages_back')}</a>
		<h1 class="page-title"><span class="title-icon">🌍</span> {$t('admin_languages_title')}</h1>
		<div class="header-spacer"></div>
		<div class="add-lang-group">
			<select bind:value={selectedAddCode} class="input-select compact">
				<option value="" disabled selected>{$t('admin_languages_select_to_add') || 'Ajouter une langue...'}</option>
				{#each addableLanguages as lang}
					<option value={lang.code}>{lang.label}</option>
				{/each}
				<option value="custom">Autre / Custom...</option>
			</select>
			{#if selectedAddCode === 'custom'}
				<input type="text" bind:value={newLangCode} placeholder={$t('admin_languages_code_placeholder')} class="new-lang-input" maxlength="5" />
			{/if}
			<button class="btn-primary btn-sm" on:click={createLang} disabled={creatingLang || !selectedAddCode || (selectedAddCode === 'custom' && !newLangCode.trim())}>
				➕ {$t('admin_languages_btn_add')}
			</button>
		</div>
	</div>

	<!-- ─── Toolbar: language pair + actions ──────────────────── -->
	<div class="toolbar">
		<!-- Left: settings toggles -->
		<div class="toolbar-section settings-section">
			<div class="setting-item">
				<span class="setting-label">{$t("admin_settings_multilang")}</span>
				<label class="toggle-switch-mini">
					<input type="checkbox" bind:checked={lanMultilingual} on:change={saveLanMultilingual} />
					<span class="toggle-slider"></span>
				</label>
			</div>
			<div class="toolbar-divider"></div>
			<div class="setting-item">
				<span class="setting-label">{$t('admin_settings_default_lang')}</span>
				<select bind:value={lanDefaultLanguage} on:change={saveLanDefaultLanguage} class="input-select compact">
					{#each languages as lang}
						<option value={lang}>{langFullName(lang)} ({lang.toUpperCase()})</option>
					{/each}
				</select>
			</div>
		</div>

		<!-- Center: language comparison pair -->
		<div class="toolbar-section lang-pair-section">
			<div class="lang-pair-card">
				<div class="lang-slot">
					<span class="lang-slot-label">{$t('admin_languages_ref_label')}</span>
					<select value={refLang} on:change={handleRefChange} class="lang-select">
						{#each languages as l}
							<option value={l}>{langFullName(l)} ({l.toUpperCase()})</option>
						{/each}
					</select>
				</div>
				<div class="lang-pair-arrow">
					<svg width="20" height="16" viewBox="0 0 20 16" fill="none">
						<path d="M12 1L19 8L12 15M1 8H19" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
					</svg>
				</div>
				<div class="lang-slot target">
					<span class="lang-slot-label">{$t('admin_languages_target_label')}</span>
					<select value={targetLang} on:change={handleTargetChange} class="lang-select">
						{#each languages as l}
							<option value={l}>{langFullName(l)} ({l.toUpperCase()})</option>
						{/each}
					</select>
				</div>
			</div>
		</div>

		<!-- Right: actions -->
		<div class="toolbar-section actions-section">
			<div class="search-box">
				<span class="search-icon">🔍</span>
				<input type="text" bind:value={searchQuery} placeholder={$t('admin_languages_search_placeholder')} class="search-field" />
			</div>
			{#if targetLang !== 'fr' && targetLang !== 'en'}
				<div style="position: relative; display: inline-block;">
					<button class="toolbar-btn danger" on:click={() => showDeleteConfirm = !showDeleteConfirm} title="Supprimer {targetLang.toUpperCase()}">🗑️</button>
					{#if showDeleteConfirm}
						<div class="confirm-popover" style="position: absolute; right: 0; top: calc(100% + 8px); width: 280px; padding: 1rem; border-radius: 12px; border: 1px solid var(--glass-border); background: var(--bg-secondary) !important; box-shadow: 0 8px 30px rgba(0,0,0,0.35); z-index: 1000; text-align: left; opacity: 1; backdrop-filter: none;">
							<p style="margin: 0 0 0.75rem 0; font-size: 0.85rem; line-height: 1.4; color: var(--text-dim);">
								{$t('admin_languages_toast_confirm_delete', { lang: targetLang.toUpperCase() })}
							</p>
							<div style="display: flex; gap: 0.5rem; justify-content: flex-end;">
								<button class="btn-secondary btn-sm" style="font-size: 0.8rem; padding: 0.3rem 0.6rem;" on:click={() => showDeleteConfirm = false}>Annuler</button>
								<button class="btn-primary danger btn-sm" style="font-size: 0.8rem; padding: 0.3rem 0.6rem;" on:click={confirmDeleteLang}>Confirmer</button>
							</div>
						</div>
					{/if}
				</div>
			{/if}
			<button class="toolbar-btn" on:click={() => showAutoTranslateModal = true} title={$t('admin_languages_btn_autotranslate')}>🪄</button>
			<button class="toolbar-btn primary" on:click={saveTargetData} disabled={isSaving} title={$t('admin_languages_btn_save')}>
				{#if isSaving}<span class="spinner-sm"></span>{:else}💾{/if}
				{targetLang.toUpperCase()}
				{#if hasUnsavedChanges}<span class="unsaved-dot-inline"></span>{/if}
			</button>
		</div>
	</div>

	<!-- ─── Stats strip ──────────────────────────────────────── -->
	<div class="stats-strip">
		<div class="stats-strip-left">
			<span class="stat-pill">{totalKeys} clés</span>
			<span class="stat-pill good">✅ {translatedCount}</span>
			{#if missingCount > 0}
				<span class="stat-pill warn">⚠️ {missingCount} non traduites</span>
			{/if}
			{#if structuralMissingCount > 0}
				<span class="stat-pill danger">🔑 {structuralMissingCount} absentes</span>
			{/if}
		</div>
		{#if structuralMissingCount > 0}
			<button class="btn-sync" on:click={syncMissingKeys} disabled={isSyncing}>
				{#if isSyncing}<span class="spinner-sm"></span>{:else}🔄{/if}
				{$t('admin_languages_btn_sync')}
			</button>
		{/if}
		<!-- Translation progress bar (inline) -->
		{#if translatedCount > 0 || missingCount > 0}
			<div class="progress-mini-bar" title="{Math.round(translatedCount / totalKeys * 100)}%">
				<div class="progress-mini-fill" style="width: {totalKeys ? (translatedCount / totalKeys * 100) : 0}%"></div>
			</div>
		{/if}
	</div>

	<!-- ─── Alert: structural missing keys ──────────────────── -->
	{#if structuralMissingCount > 0}
		<div class="sync-alert">
			<div class="sync-alert-icon">🔑</div>
			<div class="sync-alert-content">
				<strong>{structuralMissingCount} clé{structuralMissingCount > 1 ? 's' : ''} manquante{structuralMissingCount > 1 ? 's' : ''}</strong>
				<span class="sync-alert-desc">
					Le fichier {targetLang.toUpperCase()} ne contient pas toutes les clés de la langue de référence.
					Cliquez sur « {$t('admin_languages_btn_sync')} » pour ajouter les clés manquantes avec des valeurs vides.
				</span>
			</div>
			<button class="btn-sync compact" on:click={syncMissingKeys} disabled={isSyncing}>
				{#if isSyncing}<span class="spinner-sm"></span>{:else}🔄{/if}
				{$t('admin_languages_btn_sync')}
			</button>
		</div>
	{/if}

	{#if isTranslating}
		<div class="translation-progress-banner">
			<div class="flex-row justify-between items-center mb-2">
				<div class="flex-row items-center gap-2">
					<span class="spinner"></span>
					<span class="font-semibold text-sm" style="color: var(--text-main);">{$t('admin_languages_progress_banner_title', { current: translateCurrent, total: translateTotal, progress: translateProgress })}</span>
					{#if translateInstances > 0}
						<span class="instances-badge">⚡ {translateInstances} instance{translateInstances > 1 ? 's' : ''}</span>
					{/if}
				</div>
				<button class="btn-danger-sm" on:click={cancelBulkTranslation}>
					🛑 {$t('admin_languages_progress_banner_cancel')}
				</button>
			</div>
			<div class="progress-bar-container">
				<div class="progress-bar-fill" style="width: {translateProgress}%"></div>
			</div>
		</div>
	{/if}

	<!-- ─── Main layout: sidebar + editor ──────────────────── -->
	<div class="main-layout">
		<!-- Sidebar -->
		<nav class="sidebar">
			{#each groupedKeys as [cat, keys] (cat)}
				{@const meta = getCategoryMeta(cat, $t)}
				{@const missing = catMissingCount(keys)}
				<button
					class="sidebar-item"
					class:active={activeCategory === cat}
					class:has-missing={missing > 0}
					on:click={() => selectCategory(cat)}
					type="button"
				>
					<span class="sidebar-icon">{meta.icon}</span>
					<span class="sidebar-label">{meta.label}</span>
					<span class="sidebar-count">{keys.length}</span>
					{#if missing > 0}
						<span class="sidebar-missing">⚠️ {missing}</span>
					{/if}
				</button>
			{/each}
		</nav>

		<!-- Editor -->
		<div class="editor-main">
			{#if activeCategory}
				{@const meta = getCategoryMeta(activeCategory, $t)}
				<div class="editor-header">
					<div class="editor-header-left">
						<span class="editor-header-icon">{meta.icon}</span>
						<h2 class="editor-header-title">{meta.label}</h2>
						<span class="editor-header-count">{activeCategoryKeys.length} clés</span>
					</div>
					<button class="btn-primary btn-sm" on:click={saveTargetData} disabled={isSaving}>
						{#if isSaving}<span class="spinner-sm"></span>{:else}💾{/if}
						{$t('admin_languages_btn_save')}
					</button>
				</div>
				<div class="editor-keys">
					{#each activeCategoryKeys as key (key)}
						{@const isMissing = !targetData[key] || targetData[key].trim() === ''}
						<div class="trans-row" class:row-missing={isMissing}>
							<div class="trans-key" title={key}>{key}</div>
							<div class="trans-cols">
								<div class="trans-col ref-col">
									<textarea use:autoResize={refData[key]} readonly rows="1">{refData[key] || ''}</textarea>
								</div>
								<div class="trans-col target-col">
									<textarea
										use:autoResize={targetData[key]}
										value={targetData[key] || ''}
										on:input={(e) => handleFieldInput(key, e)}
										rows="1"
										placeholder={$t('admin_languages_missing_translation')}
									></textarea>
									<button class="btn-wand" type="button" title="Auto-traduire" on:click={() => translateSingleKey(key)}>🪄</button>
								</div>
							</div>
						</div>
					{/each}
				</div>
				<!-- Bottom save (always visible, sticky) -->
				<div class="editor-footer">
					<button class="btn-primary" on:click={saveTargetData} disabled={isSaving}>
						{#if isSaving}<span class="spinner-sm"></span>{:else}💾{/if}
						{$t('admin_languages_btn_save')} {targetLang.toUpperCase()}
						{#if hasUnsavedChanges}<span class="unsaved-dot-inline"></span>{/if}
					</button>
				</div>
			{:else}
				<div class="editor-empty">
					<p class="text-dim">{$t('admin_languages_no_results')}</p>
				</div>
			{/if}
		</div>
	</div>
</div>

<!-- Modal de traduction automatique -->
{#if showAutoTranslateModal}
	<div class="modal-overlay" use:portal on:click|self={() => showAutoTranslateModal = false}>
		<div class="modal-content glass">
			<h2 class="title-premium" style="margin-top: 0; margin-bottom: 1rem; font-size: 1.5rem;"><span class="title-icon">🪄</span> {$t('admin_languages_modal_autotranslate_title')}</h2>
			<p class="text-sm text-dim mb-4" style="line-height: 1.5;">
				{$t('admin_languages_modal_autotranslate_desc')}
			</p>
			<div style="display: flex; flex-direction: column; gap: 0.75rem; margin-bottom: 1.5rem;">
				<button class="btn-primary w-full" style="text-align: left; padding: 0.8rem 1rem;" on:click={() => runBulkTranslation(true)}>
					📥 {$t('admin_languages_modal_autotranslate_btn_empty')}
				</button>
				<button class="btn-secondary w-full" style="text-align: left; padding: 0.8rem 1rem;" on:click={() => runBulkTranslation(false)}>
					🔄 {$t('admin_languages_modal_autotranslate_btn_all')}
				</button>
			</div>
			<div style="display: flex; justify-content: flex-end;">
				<button class="btn-secondary btn-sm" on:click={() => showAutoTranslateModal = false}>
					{$t('admin_languages_modal_autotranslate_btn_cancel')}
				</button>
			</div>
		</div>
	</div>
{/if}

{/if}

<style>
	/* ─── Page layout ──────────────────────────────────── */
	.lang-page {
		display: flex;
		flex-direction: column;
		height: 100%;
		overflow: hidden;
	}

	/* ─── Title bar ──────────────────────────────────── */
	.header-title-bar {
		display: flex;
		align-items: center;
		gap: 0.75rem;
		padding: 0.55rem 1rem;
		background: var(--surface-raised);
		border-bottom: 1px solid var(--glass-border);
		flex-shrink: 0;
	}
	.back-link {
		color: var(--text-dim);
		text-decoration: none;
		font-size: 0.82rem;
		font-weight: 500;
		padding: 0.25rem 0.6rem;
		border-radius: 6px;
		border: 1px solid var(--glass-border);
		transition: all 0.15s;
		white-space: nowrap;
	}
	.back-link:hover {
		background: var(--hover-tint);
		color: var(--text-main);
		border-color: var(--accent);
	}
	.page-title {
		margin: 0;
		font-size: 1.2rem;
		font-weight: 700;
		color: var(--text-main);
		display: flex;
		align-items: center;
		gap: 0.4rem;
		white-space: nowrap;
	}
	.header-spacer { flex: 1; }
	.add-lang-group {
		display: flex;
		align-items: center;
		gap: 0.4rem;
	}

	/* ─── Toolbar ──────────────────────────────────── */
	.toolbar {
		display: flex;
		align-items: center;
		gap: 0.5rem;
		padding: 0.4rem 1rem;
		background: var(--bg-secondary);
		border-bottom: 1px solid var(--glass-border);
		flex-shrink: 0;
		flex-wrap: wrap;
	}
	.toolbar-section {
		display: flex;
		align-items: center;
		gap: 0.5rem;
	}
	.toolbar-divider {
		width: 1px;
		height: 22px;
		background: var(--glass-border);
		margin: 0 0.15rem;
	}
	.settings-section {
		margin-right: auto;
	}
	.setting-item {
		display: flex;
		align-items: center;
		gap: 0.35rem;
	}
	.setting-label {
		font-size: 0.75rem;
		font-weight: 500;
		color: var(--text-dim);
		white-space: nowrap;
	}

	/* Language pair card */
	.lang-pair-section {
		flex-shrink: 0;
	}
	.lang-pair-card {
		display: flex;
		align-items: center;
		gap: 0.15rem;
		background: var(--surface-raised);
		border: 1px solid var(--glass-border);
		border-radius: 10px;
		padding: 0.15rem 0.25rem;
	}
	.lang-slot {
		display: flex;
		flex-direction: column;
		align-items: center;
		gap: 0;
	}
	.lang-slot-label {
		font-size: 0.6rem;
		font-weight: 600;
		color: var(--text-dim);
		text-transform: uppercase;
		letter-spacing: 0.04em;
		line-height: 1;
		padding-top: 0.15rem;
	}
	.lang-select {
		background: transparent;
		border: none;
		color: var(--text-main);
		font-size: 0.82rem;
		font-weight: 600;
		padding: 0.15rem 0.3rem;
		cursor: pointer;
		text-align: center;
		min-width: 120px;
	}
	.lang-select:focus { outline: none; }
	.lang-select option {
		background: var(--bg-secondary);
		color: var(--text-main);
	}
	.lang-pair-arrow {
		display: flex;
		align-items: center;
		justify-content: center;
		color: var(--accent);
		padding: 0 0.2rem;
	}
	.lang-slot.target .lang-slot-label {
		color: var(--accent);
	}
	.lang-slot.target .lang-select {
		color: var(--accent);
	}

	/* Actions */
	.actions-section {
		margin-left: auto;
		gap: 0.3rem;
	}
	.search-box {
		display: flex;
		align-items: center;
		background: var(--input-bg);
		border: 1px solid var(--glass-border);
		border-radius: 8px;
		padding: 0 0.5rem;
		transition: border-color 0.15s;
	}
	.search-box:focus-within {
		border-color: var(--accent);
	}
	.search-icon {
		font-size: 0.75rem;
		flex-shrink: 0;
	}
	.search-field {
		background: transparent;
		border: none;
		color: var(--input-color);
		padding: 0.3rem 0.35rem;
		font-size: 0.8rem;
		width: 140px;
		outline: none;
	}
	.toolbar-btn {
		display: inline-flex;
		align-items: center;
		justify-content: center;
		gap: 0.25rem;
		padding: 0.3rem 0.55rem;
		border-radius: 7px;
		border: 1px solid var(--glass-border);
		background: var(--surface-raised);
		color: var(--text-main);
		font-size: 0.8rem;
		font-weight: 600;
		cursor: pointer;
		transition: all 0.15s;
		white-space: nowrap;
	}
	.toolbar-btn:hover:not(:disabled) {
		background: var(--hover-tint);
		border-color: var(--accent);
	}
	.toolbar-btn:disabled { opacity: 0.5; cursor: wait; }
	.toolbar-btn.primary {
		background: var(--accent);
		color: #fff;
		border-color: var(--accent);
	}
	.toolbar-btn.primary:hover:not(:disabled) {
		filter: brightness(1.15);
	}
	.toolbar-btn.danger {
		color: #f87171;
		border-color: rgba(248, 113, 113, 0.3);
	}
	.toolbar-btn.danger:hover:not(:disabled) {
		background: rgba(248, 113, 113, 0.1);
		border-color: #f87171;
	}

	/* ─── Stats strip ──────────────────────────────────── */
	.stats-strip {
		display: flex;
		align-items: center;
		gap: 0.5rem;
		padding: 0.25rem 1rem;
		border-bottom: 1px solid var(--glass-border);
		flex-shrink: 0;
		background: var(--surface-raised);
	}
	.stats-strip-left {
		display: flex;
		align-items: center;
		gap: 0.4rem;
	}
	.stat-pill {
		font-size: 0.7rem;
		font-weight: 700;
		color: var(--text-dim);
		padding: 0.1rem 0.45rem;
		border-radius: 9px;
		background: var(--surface-sunken);
		letter-spacing: 0.01em;
	}
	.stat-pill.good { color: #4ade80; background: rgba(74, 222, 128, 0.08); }
	.stat-pill.warn { color: #fb923c; background: rgba(251, 146, 60, 0.08); }
	.btn-sync {
		display: inline-flex;
		align-items: center;
		gap: 0.25rem;
		padding: 0.12rem 0.5rem;
		border-radius: 6px;
		border: 1px solid var(--accent);
		background: rgba(59, 130, 246, 0.06);
		color: var(--accent);
		font-size: 0.7rem;
		font-weight: 600;
		cursor: pointer;
		transition: background 0.15s;
	}
	.btn-sync:hover:not(:disabled) { background: rgba(59, 130, 246, 0.15); }
	.btn-sync:disabled { opacity: 0.5; cursor: wait; }
	.progress-mini-bar {
		flex: 1;
		max-width: 200px;
		height: 4px;
		background: var(--surface-sunken);
		border-radius: 2px;
		overflow: hidden;
		margin-left: auto;
	}
	.progress-mini-fill {
		height: 100%;
		background: linear-gradient(90deg, #4ade80, #3b82f6);
		border-radius: 2px;
		transition: width 0.5s ease;
	}
	.stat-pill.danger { color: #f87171; background: rgba(248, 113, 113, 0.1); }

	/* ─── Sync alert banner ──────────────────────────────── */
	.sync-alert {
		display: flex;
		align-items: center;
		gap: 0.75rem;
		padding: 0.6rem 1rem;
		background: rgba(248, 113, 113, 0.06);
		border-bottom: 1px solid rgba(248, 113, 113, 0.2);
		flex-shrink: 0;
	}
	.sync-alert-icon {
		font-size: 1.3rem;
		flex-shrink: 0;
	}
	.sync-alert-content {
		flex: 1;
		display: flex;
		flex-direction: column;
		gap: 0.15rem;
	}
	.sync-alert-content strong {
		font-size: 0.82rem;
		color: #f87171;
	}
	.sync-alert-desc {
		font-size: 0.72rem;
		color: var(--text-dim);
		line-height: 1.3;
	}
	.btn-sync.compact {
		padding: 0.3rem 0.75rem;
		font-size: 0.75rem;
		white-space: nowrap;
		flex-shrink: 0;
	}
	/* Unsaved indicator */
	.unsaved-dot-inline {
		width: 6px;
		height: 6px;
		border-radius: 50%;
		background: #fb923c;
		display: inline-block;
		margin-left: 0.25rem;
		animation: pulse-dot 1.5s infinite;
	}
	@keyframes pulse-dot {
		0%, 100% { opacity: 1; }
		50% { opacity: 0.3; }
	}

	/* ─── Main layout ──────────────────────────────────── */
	.main-layout {
		display: flex;
		flex: 1;
		overflow: hidden;
	}

	/* ─── Sidebar ──────────────────────────────────── */
	.sidebar {
		width: 230px;
		min-width: 230px;
		overflow-y: auto;
		border-right: 1px solid var(--glass-border);
		background: var(--surface-raised);
		padding: 0.25rem 0;
		flex-shrink: 0;
	}
	.sidebar-item {
		display: flex;
		align-items: center;
		gap: 0.4rem;
		width: 100%;
		padding: 0.4rem 0.65rem;
		border: none;
		background: none;
		color: var(--text-main);
		font-size: 0.78rem;
		cursor: pointer;
		text-align: left;
		transition: background 0.12s;
		border-left: 3px solid transparent;
	}
	.sidebar-item:hover {
		background: var(--hover-tint);
	}
	.sidebar-item.active {
		background: var(--hover-tint);
		border-left-color: var(--accent);
		font-weight: 600;
	}
	.sidebar-icon { font-size: 0.9rem; flex-shrink: 0; }
	.sidebar-label { flex: 1; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
	.sidebar-count {
		font-size: 0.65rem;
		color: var(--text-dim);
		background: var(--surface-sunken);
		padding: 0.05rem 0.3rem;
		border-radius: 8px;
		flex-shrink: 0;
	}
	.sidebar-missing {
		font-size: 0.6rem;
		color: #fb923c;
		flex-shrink: 0;
	}

	/* ─── Editor ──────────────────────────────────── */
	.editor-main {
		flex: 1;
		overflow: hidden;
		display: flex;
		flex-direction: column;
	}
	.editor-header {
		display: flex;
		align-items: center;
		justify-content: space-between;
		padding: 0.5rem 0.8rem;
		background: var(--bg-secondary);
		border-bottom: 1px solid var(--glass-border);
		flex-shrink: 0;
		z-index: 5;
	}
	.editor-header-left {
		display: flex;
		align-items: center;
		gap: 0.45rem;
	}
	.editor-header-icon { font-size: 1.1rem; }
	.editor-header-title {
		margin: 0;
		font-size: 0.95rem;
		font-weight: 700;
		color: var(--text-main);
	}
	.editor-header-count {
		font-size: 0.68rem;
		color: var(--text-dim);
		background: var(--surface-sunken);
		padding: 0.1rem 0.4rem;
		border-radius: 8px;
	}
	.editor-keys {
		flex: 1;
		overflow-y: auto;
	}
	.editor-footer {
		padding: 0.5rem 0.8rem;
		border-top: 1px solid var(--glass-border);
		background: var(--surface-raised);
		display: flex;
		justify-content: flex-end;
		flex-shrink: 0;
	}
	.editor-empty {
		flex: 1;
		display: flex;
		align-items: center;
		justify-content: center;
	}

	/* ─── Translation rows ──────────────────────────────── */
	.editor-keys { flex: 1; }
	.trans-row {
		display: flex;
		flex-direction: column;
		border-bottom: 1px solid var(--glass-border);
		transition: background 0.12s;
	}
	.trans-row:focus-within { background: var(--hover-tint); }
	.trans-row.row-missing { background: rgba(251, 146, 60, 0.035); }
	.trans-row.row-missing .trans-key { color: #fb923c; }
	.trans-key {
		background: var(--bg-secondary);
		padding: 0.12rem 0.5rem;
		font-family: 'Fira Code', 'Cascadia Code', monospace;
		font-size: 0.68rem;
		color: var(--text-muted);
		border-bottom: 1px solid var(--glass-border);
		word-break: break-all;
	}
	.trans-cols {
		display: flex;
		flex-direction: row;
		width: 100%;
	}
	.trans-col {
		flex: 1;
		padding: 0;
		display: flex;
		position: relative;
	}
	.ref-col {
		border-right: 1px solid var(--glass-border);
		background: var(--surface-sunken);
	}
	.trans-col textarea {
		width: 100%;
		resize: none;
		background: transparent;
		border: none;
		color: var(--text-main);
		padding: 0.3rem 0.45rem;
		font-family: inherit;
		font-size: 0.8rem;
		min-height: 24px;
		line-height: 1.4;
		overflow: hidden;
	}
	.trans-col textarea:focus { outline: none; }
	.ref-col textarea { color: var(--text-dim); }
	.target-col { padding-right: 1.6rem; }
	.btn-wand {
		position: absolute;
		right: 0.2rem;
		top: 50%;
		transform: translateY(-50%);
		background: none;
		border: none;
		cursor: pointer;
		font-size: 0.85rem;
		color: var(--accent);
		padding: 0.1rem;
		transition: transform 0.2s;
		opacity: 0.4;
	}
	.trans-row:hover .btn-wand { opacity: 1; }
	.btn-wand:hover { transform: translateY(-50%) scale(1.2); }

	@media (max-width: 900px) {
		.sidebar { width: 170px; min-width: 170px; }
		.trans-cols { flex-direction: column; }
		.ref-col { border-right: none; border-bottom: 1px solid var(--glass-border); }
		.toolbar { flex-direction: column; align-items: stretch; }
		.settings-section, .actions-section { margin: 0; justify-content: center; }
	}
	@media (max-width: 600px) {
		.sidebar { display: none; }
	}

	/* ─── Inputs ──────────────────────────────────── */
	.new-lang-input {
		width: 72px;
		background: var(--input-bg);
		border: 1px solid var(--glass-border);
		color: var(--input-color);
		padding: 0.3rem 0.45rem;
		border-radius: 6px;
		font-size: 0.8rem;
	}
	.input-select {
		background: var(--input-bg);
		border: 1px solid var(--glass-border);
		color: var(--input-color);
		padding: 0.25rem 0.5rem;
		border-radius: 6px;
		display: block;
		margin-top: 0;
		font-size: 0.8rem;
	}
	.input-select.compact {
		padding: 0.2rem 0.4rem;
		font-size: 0.78rem;
	}
	.input-select option {
		background: var(--bg-secondary);
		color: var(--text-main);
	}

	/* ─── Progress ──────────────────────────────────── */
	.translation-progress-banner {
		padding: 0.45rem 1rem;
		border-bottom: 1px solid var(--accent);
		background: var(--surface-raised);
		flex-shrink: 0;
	}
	.progress-bar-container {
		width: 100%;
		height: 5px;
		background: var(--surface-sunken);
		border-radius: 3px;
		overflow: hidden;
	}
	.progress-bar-fill {
		height: 100%;
		background: linear-gradient(90deg, var(--accent), #a78bfa);
		transition: width 0.3s ease;
	}

	/* ─── Modal ──────────────────────────────────── */
	.modal-overlay {
		position: fixed;
		top: 0; left: 0; right: 0; bottom: 0;
		background: rgba(0, 0, 0, 0.55);
		backdrop-filter: blur(6px);
		display: flex;
		align-items: center;
		justify-content: center;
		z-index: 1000;
	}
	.modal-content {
		max-width: 480px;
		width: 90%;
		padding: 1.8rem;
		border-radius: 14px;
		background: var(--surface-raised);
		border: 1px solid var(--glass-border);
		box-shadow: 0 12px 40px rgba(0, 0, 0, 0.35);
	}

	/* ─── Spinners ──────────────────────────────────── */
	.spinner {
		width: 14px; height: 14px;
		border: 2px solid var(--text-dim);
		border-top: 2px solid var(--accent);
		border-radius: 50%;
		animation: spin 0.8s linear infinite;
		display: inline-block;
	}
	.spinner-sm {
		width: 11px; height: 11px;
		border: 2px solid var(--text-dim);
		border-top: 2px solid var(--accent);
		border-radius: 50%;
		animation: spin 0.8s linear infinite;
		display: inline-block;
	}
	@keyframes spin {
		0% { transform: rotate(0deg); }
		100% { transform: rotate(360deg); }
	}
	.w-full { width: 100%; }

	/* ─── Toggle switch ──────────────────────────────────── */
	.toggle-switch-mini { position: relative; display: inline-block; width: 28px; height: 16px; cursor: pointer; }
	.toggle-switch-mini input { opacity: 0; width: 0; height: 0; }
	.toggle-switch-mini .toggle-slider { position: absolute; inset: 0; background: var(--surface-sunken); border-radius: 8px; transition: 0.2s; }
	.toggle-switch-mini .toggle-slider::before { content: ''; position: absolute; height: 12px; width: 12px; left: 2px; bottom: 2px; background: var(--text-dim); border-radius: 50%; transition: 0.2s; }
	.toggle-switch-mini input:checked + .toggle-slider { background: rgba(59,130,246,0.35); }
	.toggle-switch-mini input:checked + .toggle-slider::before { transform: translateX(12px); background: var(--accent); }

	/* ─── Instances badge ──────────────────────────────────── */
	.instances-badge {
		font-size: 0.7rem;
		font-weight: 700;
		color: #a78bfa;
		background: rgba(167, 139, 250, 0.1);
		padding: 0.1rem 0.5rem;
		border-radius: 9px;
		letter-spacing: 0.01em;
		white-space: nowrap;
	}
</style>

<!-- Toasts -->
<div class="toast-container">
	{#each toasts as t (t.id)}
		<div class="toast {t.type} {t.leaving ? 'leaving' : ''}">
			{t.message}
		</div>
	{/each}
</div>
