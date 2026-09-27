<script>
	import { get } from 'svelte/store';
	import { onMount, onDestroy } from 'svelte';
	import { api } from '$lib/api';
	import { t } from '$lib/i18nStore';
	import { wsMessageStore } from '$lib/ws';

	export let toast = (msg, type) => {};
	export let settingsSubTab = (typeof localStorage !== 'undefined' && localStorage.getItem('admin_subtab')) || 'general';
	export let onDataReset = () => {};

	$: if (typeof localStorage !== 'undefined') localStorage.setItem('admin_subtab', settingsSubTab);

	let wsUnsub = null;

	// Debounce helper — auto-saves after user stops typing
	let _debounceTimers = {};
	function debounceSave(key, fn, delay = 1200) {
		if (_debounceTimers[key]) clearTimeout(_debounceTimers[key]);
		_debounceTimers[key] = setTimeout(fn, delay);
	}

	function portal(node) {
		document.body.appendChild(node);
		return {
			destroy() {
				if (node.parentNode) {
					node.parentNode.removeChild(node);
				}
			}
		};
	}

	// General Settings
	let teamScoringMode = 'weighted';
	let eventName = 'Alanbix LAN';
	let searxngUrl = 'http://searxng:8080';
	let searxngTesting = false;
	let searxngTestResult = null;
	let defaultPts = { pts_winner: 1.5, pts_second: 1.3, pts_third: 1.0, pts_participation: 1.0, pts_per_match: 0.5 };

	// Public Chat Admin State
	let publicChatConfig = {
		enabled: true,
		slowmode_seconds: 3,
		max_length: 250,
		block_duplicates: true,
		banned_words_text: '',
		ai_mention_enabled: true,
		ai_cooldown_seconds: 15
	};

	// IA Settings
	let iaConfig = { 
		ollama_host: '', model: '', rag_enabled: true, network_tools_enabled: true,
		auto_moderation_enabled: true,
		temperature: 0.7, context_window: 4096,
		ollama_instances: [], embedding_model: '',
		tool_calling_mode: 'stream_intercept',
		call_admin_enabled: true,
		call_admin_button_enabled: true,
		call_admin_cooldown_minutes: 30,
		call_admin_daily_limit: 3,
		call_admin_global_hourly_limit: 15,
		rag_suggestion_enabled: true
	};
	let availableModels = [];
	let instanceStatuses = [];
	let testingConnection = false;

	// System & Tournament Closing Prompts
	let defaultLang = 'fr';
	let systemPrompt = '';
	let closingPrompt = '';

	// System Prompt Editor Modal
	let showPromptModal = false;
	let promptModalDraft = '';

	const DEFAULT_PROMPT_SECTIONS = [
		{ key: 'identity', icon: '🧙' },
		{ key: 'context', icon: '🗺️' },
		{ key: 'style', icon: '🎭' },
		{ key: 'rules', icon: '⚖️' },
	];

	function openPromptModal() {
		promptModalDraft = systemPrompt;
		showPromptModal = true;
	}

	async function savePromptFromModal() {
		systemPrompt = promptModalDraft;
		showPromptModal = false;
		await saveSystemPrompt();
	}

	function insertSection(sectionKey) {
		const sectionHeader = get(t)(`admin_prompt_modal_section_${sectionKey}`);
		const block = `\n${sectionHeader}\n`;
		promptModalDraft += block;
	}

	// Knowledge / RAG
	let knowledgeDocs = [];
	let newDocContent = '';
	let editingDocId = null;
	let editDocContent = '';
	let editDocLoading = false;
	let editDocSaving = false;
	let uploadingDoc = false;

	// AI Queue Admin State
	let iaQueueData = { pending: [], active: [], queue_size: 0, active_count: 0, avg_duration: 15 };
	let iaQueueInterval = null;

	// Nuke State
	let nukeConfirm = { tournaments: false, players: false, games: false, images: false, notifications: false, awards: false };
	let nuking = { tournaments: false, players: false, games: false, images: false, notifications: false, awards: false };

	onMount(async () => {
		await loadData();

		wsUnsub = wsMessageStore.subscribe(msg => {
			if (!msg) return;
			if (msg.type === 'knowledge_updated') {
				loadKnowledge();
			}
			if (msg.type === 'ia_queue_update') {
				loadQueueAdmin();
			}
			if (msg.type === 'public_chat_config_updated') {
				loadPublicChatConfig();
			}
			if (msg.type === 'config_updated') {
				api.get('/dashboard/stats').then(stats => {
					teamScoringMode = stats.team_scoring_mode || 'weighted';
					eventName = stats.event_name || 'Alanbix LAN';
				}).catch(() => {});
				api.get('/admin/config/searxng_url').then(sxCfg => {
					searxngUrl = sxCfg?.value || 'http://searxng:8080';
				}).catch(() => {});
				api.get('/admin/config/default_tournament_pts').then(dpCfg => {
					if (dpCfg?.value) {
						const parsed = typeof dpCfg.value === 'string' ? JSON.parse(dpCfg.value) : dpCfg.value;
						defaultPts = { ...defaultPts, ...parsed };
					}
				}).catch(() => {});
				loadPrompts().catch(() => {});
			}
			if (msg.type === 'ia_config_updated') {
				api.get('/ia/config').then(res => {
					iaConfig = res;
					if (!iaConfig.ollama_instances) iaConfig.ollama_instances = [];
					fetchModels();
					loadInstanceStatuses();
				}).catch(() => {});
				loadPrompts().catch(() => {});
			}
		});
	});

	onDestroy(() => {
		if (wsUnsub) wsUnsub();
		if (iaQueueInterval) clearInterval(iaQueueInterval);
	});

	async function loadData() {
		try {
			const stats = await api.get('/dashboard/stats');
			teamScoringMode = stats.team_scoring_mode || 'weighted';
			eventName = stats.event_name || 'Alanbix LAN';
			try {
				const dpCfg = await api.get('/admin/config/default_tournament_pts');
				if (dpCfg?.value) {
					const parsed = typeof dpCfg.value === 'string' ? JSON.parse(dpCfg.value) : dpCfg.value;
					defaultPts = { ...defaultPts, ...parsed };
				}
			} catch {}
		} catch {}

		try {
			const sxCfg = await api.get('/admin/config/searxng_url');
			searxngUrl = sxCfg?.value || 'http://searxng:8080';
		} catch {}

		await loadPublicChatConfig();
		await loadPrompts();

		try {
			iaConfig = await api.get('/ia/config');
			if (!iaConfig.ollama_instances) iaConfig.ollama_instances = [];
			fetchModels();
			loadInstanceStatuses();
		} catch {}

		loadKnowledge();
		loadQueueAdmin();
	}

	async function loadPrompts() {
		try {
			const stats = await api.get('/dashboard/stats');
			defaultLang = stats.lan_default_language || 'fr';
			const translations = await api.get(`/api/i18n/${defaultLang}`);
			systemPrompt = translations.system_prompt || "Tu es Alanbix, l'IA de gestion de LAN.";
			closingPrompt = translations.tournament_closing_prompt || "";
		} catch (err) {
			console.error('Failed to load prompts from default language:', err);
		}
	}

	async function saveTeamScoringMode() {
		try {
			await api.put('/admin/config/team_scoring_mode', { value: teamScoringMode });
			toast(get(t)('admin_toast_team_scoring_saved'), 'success');
		} catch { toast('Erreur sauvegarde.', 'error'); }
	}

	async function saveEventName() {
		try {
			await api.put('/admin/config/event_name', { value: eventName });
			toast(get(t)('admin_toast_lan_name_saved'), 'success');
		} catch { toast('Erreur sauvegarde.', 'error'); }
	}

	async function saveSearxngUrl() {
		try {
			await api.put('/admin/config/searxng_url', { value: searxngUrl });
			toast(get(t)('admin_toast_searxng_url_saved') || 'URL de l\'instance SearXNG enregistree.', 'success');
		} catch { toast('Erreur sauvegarde URL SearXNG.', 'error'); }
	}

	async function testSearxng() {
		searxngTesting = true;
		searxngTestResult = null;
		try {
			const res = await api.post('/admin/config/test-searxng', { url: searxngUrl });
			if (res.ok) {
				searxngTestResult = { ok: true, message: res.message || 'Instance SearXNG valide et fonctionnelle.' };
				toast(res.message || 'SearXNG testé avec succès.', 'success');
			} else {
				searxngTestResult = { ok: false, message: res.error || 'Erreur inconnue.' };
				toast(res.error || 'Test SearXNG échoué.', 'error');
			}
		} catch (err) {
			searxngTestResult = { ok: false, message: 'Erreur réseau lors de la communication avec le serveur backend.' };
			toast('Erreur test SearXNG.', 'error');
		} finally {
			searxngTesting = false;
		}
	}

	async function saveDefaultPts() {
		try {
			await api.put('/admin/config/default_tournament_pts', { value: JSON.stringify(defaultPts) });
			toast(get(t)('admin_toast_default_points_saved'), 'success');
		} catch { toast('Erreur sauvegarde.', 'error'); }
	}

	async function saveSystemPrompt() {
		try {
			const translations = await api.get(`/api/i18n/${defaultLang}`);
			translations.system_prompt = systemPrompt;
			await api.put(`/api/i18n/${defaultLang}`, translations);
			toast(get(t)('admin_toast_system_prompt_saved'), 'success');
		} catch (err) {
			console.error('Failed to save system prompt:', err);
			toast('Erreur sauvegarde prompt.', 'error');
		}
	}

	async function saveClosingPrompt() {
		try {
			const translations = await api.get(`/api/i18n/${defaultLang}`);
			translations.tournament_closing_prompt = closingPrompt;
			await api.put(`/api/i18n/${defaultLang}`, translations);
			toast(get(t)('admin_toast_closing_prompt_saved'), 'success');
		} catch (err) {
			console.error('Failed to save closing prompt:', err);
			toast('Erreur sauvegarde.', 'error');
		}
	}

	async function loadPublicChatConfig() {
		try {
			const res = await api.get('/public-chat/config');
			if (res) {
				publicChatConfig = {
					...res,
					banned_words_text: (res.banned_words || []).join(', ')
				};
			}
		} catch (e) {
			console.error("Failed to load public chat config in admin:", e);
		}
	}

	async function savePublicChatConfig() {
		try {
			const words = (publicChatConfig.banned_words_text || '')
				.split(',')
				.map(w => w.trim())
				.filter(Boolean);
			const payload = {
				enabled: publicChatConfig.enabled,
				slowmode_seconds: Number(publicChatConfig.slowmode_seconds) || 0,
				max_length: Number(publicChatConfig.max_length) || 250,
				block_duplicates: !!publicChatConfig.block_duplicates,
				banned_words: words,
				ai_mention_enabled: !!publicChatConfig.ai_mention_enabled,
				ai_cooldown_seconds: Number(publicChatConfig.ai_cooldown_seconds) || 15
			};
			await api.put('/public-chat/config', payload);
			toast('Paramètres du Chat Public enregistrés', 'success');
		} catch (e) {
			toast(e.message || 'Erreur de sauvegarde', 'error');
		}
	}

	async function clearChatHistoryAdmin() {
		if (!confirm(get(t)('dash_chat_clear_confirm') || 'Effacer tout l\'historique du chat public ?')) return;
		try {
			await api.post('/public-chat/clear', {});
			toast('Historique du chat public purgé', 'success');
		} catch (e) {
			toast(e.message, 'error');
		}
	}

	async function saveIAConfig() {
		try {
			await api.post('/ia/config', iaConfig);
			toast(get(t)('admin_toast_ai_saved'), 'success');
		} catch (e) { toast(e.message || get(t)('admin_toast_ai_save_error'), 'error'); }
	}

	async function fetchModels() {
		try {
			const res = await api.get('/ia/models');
			availableModels = res.models || [];
		} catch {}
	}

	async function testConnection() {
		testingConnection = true;
		const res = await api.post('/ia/test-connection', iaConfig);
		testingConnection = false;
		if (res.status === 'ok') {
			toast(get(t)('admin_toast_ollama_success'), 'success');
			fetchModels();
		} else {
			toast(get(t)('admin_toast_ollama_fail') + res.detail, 'error');
		}
	}

	async function loadInstanceStatuses() {
		try { instanceStatuses = await api.get('/ia/instances/status'); } catch { instanceStatuses = []; }
	}

	async function testInstance(idx) {
		const inst = iaConfig.ollama_instances[idx];
		if (!inst) return;
		const res = await api.post('/ia/test-connection', { url: inst.url });
		if (res.status === 'ok') {
			toast(`${inst.label || inst.url} — OK (${res.latency_ms}ms)`, 'success');
			loadInstanceStatuses();
			fetchModels();
		} else {
			toast(`${inst.label || inst.url} — Échec`, 'error');
		}
	}

	async function addInstance() {
		const nextPriority = iaConfig.ollama_instances.length;
		iaConfig.ollama_instances = [...iaConfig.ollama_instances, { url: 'http://', label: '', model: '', enabled: true, priority: nextPriority }];
		await saveIAConfig();
	}

	async function removeInstance(idx) {
		iaConfig.ollama_instances = iaConfig.ollama_instances.filter((_, i) => i !== idx);
		iaConfig.ollama_instances.forEach((inst, i) => inst.priority = i);
		iaConfig.ollama_instances = iaConfig.ollama_instances;
		await saveIAConfig();
	}

	async function moveInstance(idx, dir) {
		const arr = [...iaConfig.ollama_instances];
		const target = idx + dir;
		if (target < 0 || target >= arr.length) return;
		[arr[idx], arr[target]] = [arr[target], arr[idx]];
		arr.forEach((inst, i) => inst.priority = i);
		iaConfig.ollama_instances = arr;
		await saveIAConfig();
	}

	async function loadQueueAdmin() {
		try { iaQueueData = await api.get('/ia/queue/admin'); } catch { iaQueueData = { pending: [], active: [], queue_size: 0, active_count: 0, avg_duration: 15 }; }
		const nextMs = iaQueueData.queue_size > 0 || iaQueueData.active_count > 0 ? 3000 : 15000;
		if (iaQueueInterval) clearInterval(iaQueueInterval);
		iaQueueInterval = setInterval(loadQueueAdmin, nextMs);
	}

	async function cancelQueueEntry(entryId) {
		try {
			await api.delete(`/ia/queue/${entryId}`);
			toast(get(t)('admin_toast_request_cancelled'), 'success');
			await loadQueueAdmin();
		} catch (e) {
			toast('Erreur: ' + e.message, 'error');
		}
	}

	async function loadKnowledge() {
		try {
			knowledgeDocs = await api.get('/ia/knowledge');
		} catch { knowledgeDocs = []; }
	}

	async function deleteKnowledge(docId) {
		try {
			await api.delete(`/ia/knowledge/${docId}`);
			toast(get(t)('admin_toast_rag_deleted'), 'success');
			loadKnowledge();
		} catch (e) { toast(e.message || get(t)('admin_toast_delete_error'), 'error'); }
	}

	async function editKnowledge(docId) {
		if (editingDocId === docId) { editingDocId = null; return; }
		editDocLoading = true;
		editingDocId = docId;
		try {
			const doc = await api.get(`/ia/knowledge/${docId}`);
			editDocContent = doc.content;
		} catch (e) { toast(get(t)('admin_toast_load_doc_error'), 'error'); editingDocId = null; }
		editDocLoading = false;
	}

	async function saveKnowledgeEdit() {
		if (!editDocContent.trim() || !editingDocId) return;
		editDocSaving = true;
		try {
			const res = await api.put(`/ia/knowledge/${editingDocId}`, { content: editDocContent });
			if (res.warning) {
				toast(`⚠️ ${res.warning}`, 'error');
			} else if (res.chunks > 1) {
				toast(`Document re-vectorisé en ${res.chunks} chunks (${res.content_length} car.)`, 'success');
			} else {
				toast(get(t)('admin_toast_rag_updated'), 'success');
			}
			editingDocId = null;
			editDocContent = '';
			loadKnowledge();
		} catch (e) { toast(e.message || 'Erreur mise à jour', 'error'); }
		editDocSaving = false;
	}

	async function uploadRagDoc() {
		if (!newDocContent.trim()) return;
		uploadingDoc = true;
		try {
			const res = await api.post('/ia/upload-document', { content: newDocContent });
			newDocContent = '';
			if (res.warning) {
				toast(`⚠️ ${res.warning}`, 'error');
			} else if (res.chunks > 1) {
				toast(`Document vectorisé en ${res.chunks} chunks (${res.content_length} car.) et ajouté à la base RAG.`, 'success');
			} else {
				toast(get(t)('admin_toast_rag_added'), 'success');
			}
			loadKnowledge();
		} catch (e) { toast(e.message || 'Erreur vectorisation', 'error'); }
		uploadingDoc = false;
	}

	// Danger Zone Nukes
	async function nukeAwards() {
		nuking.awards = true;
		try {
			const res = await api.delete('/admin/nuke/awards');
			toast(`${res.deleted_awards} prix supprimé(s)`, 'success');
			onDataReset();
		} catch (e) { toast(e.message, 'error'); }
		nuking.awards = false;
		nukeConfirm.awards = false;
	}

	async function nukeTournaments() {
		nuking.tournaments = true;
		try {
			const res = await api.delete('/admin/nuke/tournaments');
			toast(`${res.deleted_tournaments} tournoi(s) supprimé(s), scores réinitialisés`, 'success');
			onDataReset();
		} catch (e) { toast(e.message, 'error'); }
		nuking.tournaments = false;
		nukeConfirm.tournaments = false;
	}

	async function nukePlayers() {
		nuking.players = true;
		try {
			const res = await api.delete('/admin/nuke/players');
			toast(`${res.deleted_players} joueur(s) supprimé(s)`, 'success');
			onDataReset();
		} catch (e) { toast(e.message, 'error'); }
		nuking.players = false;
		nukeConfirm.players = false;
	}

	async function nukeGames() {
		nuking.games = true;
		try {
			const res = await api.delete('/admin/nuke/games');
			toast(`${res.deleted_games} jeu(x) et tous les tournois supprimés`, 'success');
			onDataReset();
		} catch (e) { toast(e.message, 'error'); }
		nuking.games = false;
		nukeConfirm.games = false;
	}

	async function nukeImages() {
		nuking.images = true;
		try {
			await api.delete('/ia/admin/nuke-images');
			toast('Toutes les images du chat ont été supprimées', 'success');
		} catch (e) { toast(e.message, 'error'); }
		nuking.images = false;
		nukeConfirm.images = false;
	}

	async function nukeNotifications() {
		nuking.notifications = true;
		try {
			const res = await api.delete('/admin/nuke/notifications');
			toast(`${res.deleted_notifications} notification(s) supprimée(s)`, 'success');
		} catch (e) { toast(e.message, 'error'); }
		nuking.notifications = false;
		nukeConfirm.notifications = false;
	}

	function handleKeydown(e) {
		if (e.key === 'Escape') {
			if (showPromptModal) showPromptModal = false;
			else if (editingDocId) editingDocId = null;
		}
	}
</script>

<svelte:window on:keydown={handleKeydown} />

<div class="settings-view">
	<!-- Settings Sub-Tabs -->
	<div class="settings-tabs">
		<button class="stab" class:active={!settingsSubTab || settingsSubTab === 'general'} on:click={() => settingsSubTab = 'general'}>
			<span class="stab-icon">⚙️</span> {$t("admin_settings_tab_general")}
		</button>
		<button class="stab" class:active={settingsSubTab === 'ia'} on:click={() => settingsSubTab = 'ia'}>
			<span class="stab-icon">🤖</span> {$t("admin_settings_tab_ai")}
		</button>
	</div>

	<!-- GENERAL TAB -->
	{#if !settingsSubTab || settingsSubTab === 'general'}
	<div class="stab-content">
		<div class="sc glass">
			<div class="sc-head">
				<div class="sc-icon">🏷️</div>
				<div>
					<h3>{$t("admin_settings_lan_name")}</h3>
					<p class="sc-sub">{$t("admin_settings_lan_name_sub")}</p>
				</div>
			</div>
			<div class="sc-body">
				<div class="flex-row gap-2">
					<input type="text" bind:value={eventName} on:input={() => debounceSave('eventName', saveEventName)} placeholder="{$t('admin_settings_lan_name_placeholder')}" style="flex:1" />
				</div>
			</div>
		</div>

		<div class="sc glass">
			<div class="sc-head">
				<div class="sc-icon">📊</div>
				<div>
					<h3>{$t("admin_settings_team_scoring")}</h3>
					<p class="sc-sub">{$t("admin_settings_team_scoring_sub")}</p>
				</div>
			</div>
			<div class="sc-body">
				<div class="scoring-toggle">
					<button class="score-opt {teamScoringMode === 'weighted' ? 'active' : ''}" on:click={() => { teamScoringMode = 'weighted'; saveTeamScoringMode(); }}>
						<span class="score-opt-icon">📊</span>
						<span class="score-opt-label">{$t("admin_settings_scoring_weighted_label")}</span>
						<span class="score-opt-desc">{$t("admin_settings_scoring_weighted_desc")}</span>
					</button>
					<button class="score-opt {teamScoringMode === 'raw' ? 'active' : ''}" on:click={() => { teamScoringMode = 'raw'; saveTeamScoringMode(); }}>
						<span class="score-opt-icon">📈</span>
						<span class="score-opt-label">{$t("admin_settings_scoring_raw_label")}</span>
						<span class="score-opt-desc">{$t("admin_settings_scoring_raw_desc")}</span>
					</button>
				</div>
			</div>
		</div>

		<div class="sc glass sc-full">
			<div class="sc-head">
				<div class="sc-icon">🏆</div>
				<div>
					<h3>{$t("admin_settings_default_pts")}</h3>
					<p class="sc-sub">{$t("admin_settings_default_pts_sub")}</p>
				</div>
			</div>
			<div class="sc-body">
				<div class="default-pts-grid">
					<div class="dpt-field"><label>{$t("admin_settings_points_1st")}</label><input type="number" bind:value={defaultPts.pts_winner} on:change={saveDefaultPts} min="0" /></div>
					<div class="dpt-field"><label>{$t("admin_settings_points_2nd")}</label><input type="number" bind:value={defaultPts.pts_second} on:change={saveDefaultPts} min="0" /></div>
					<div class="dpt-field"><label>{$t("admin_settings_points_3rd")}</label><input type="number" bind:value={defaultPts.pts_third} on:change={saveDefaultPts} min="0" /></div>
					<div class="dpt-field"><label>{$t("admin_settings_points_part")}</label><input type="number" bind:value={defaultPts.pts_participation} on:change={saveDefaultPts} min="0" /></div>
					<div class="dpt-field"><label>{$t("admin_settings_points_bonus")}</label><input type="number" bind:value={defaultPts.pts_per_match} on:change={saveDefaultPts} min="0" step="0.1" /></div>
				</div>
			</div>
		</div>

		<div class="sc glass sc-full">
			<div class="sc-head">
				<div class="sc-icon">🔍</div>
				<div>
					<h3>{$t("admin_settings_searxng_title")}</h3>
					<p class="sc-sub">{$t("admin_settings_searxng_sub")}</p>
				</div>
			</div>
			<div class="sc-body">
				<div class="flex-column gap-2" style="width: 100%;">
					<div class="flex-row gap-2" style="width: 100%;">
						<input type="text" bind:value={searxngUrl} on:input={() => debounceSave('searxngUrl', saveSearxngUrl)} placeholder="{$t('admin_settings_searxng_placeholder')}" style="flex:1" />
						<button class="btn-primary" on:click={testSearxng} disabled={searxngTesting}>
							{#if searxngTesting}
								{$t("admin_settings_searxng_testing")}
							{:else}
								{$t("admin_settings_searxng_test_btn")}
							{/if}
						</button>
					</div>
					
					{#if searxngTestResult}
						{#if searxngTestResult.ok}
							<div style="padding: 0.75rem; border-radius: 6px; font-size: 0.9rem; border: 1px solid rgba(16, 185, 129, 0.25); background: rgba(16, 185, 129, 0.08); color: #34d399; margin-top: 0.5rem; text-align: left; width: 100%;">
								✅ {searxngTestResult.message}
							</div>
						{:else}
							<div style="padding: 0.75rem; border-radius: 6px; font-size: 0.9rem; border: 1px solid rgba(239, 68, 68, 0.25); background: rgba(239, 68, 68, 0.08); color: #f87171; margin-top: 0.5rem; text-align: left; width: 100%;">
								❌ {searxngTestResult.message}
							</div>
						{/if}
					{/if}
				</div>
			</div>
		</div>

		<!-- Public Chat & Anti-Spam Settings -->
		<div class="sc glass sc-full">
			<div class="sc-head">
				<div class="sc-icon">💬</div>
				<div>
					<h3>{$t("admin_public_chat_title") || 'Chat Public & Anti-Spam'}</h3>
					<p class="sc-sub">{$t("admin_public_chat_sub") || 'Modération en temps réel, filtres anti-spam et IA participante'}</p>
				</div>
			</div>
			<div class="sc-body">
				<div class="public-chat-admin-grid">
					<div class="pca-row full-width">
						<label class="toggle-label">
							<input type="checkbox" bind:checked={publicChatConfig.enabled} />
							<span><strong>{$t("admin_public_chat_enable") || 'Activer le Chat Public'}</strong> — {$t("admin_public_chat_enable_sub") || "Permettre aux joueurs d'écrire dans le chat central"}</span>
						</label>
					</div>

					<div class="pca-field">
						<label>{$t("admin_public_chat_slowmode") || 'Slowmode (secondes par message)'}</label>
						<input type="number" bind:value={publicChatConfig.slowmode_seconds} min="0" max="120" />
					</div>

					<div class="pca-field">
						<label>{$t("admin_public_chat_max_len") || 'Longueur max message (caractères)'}</label>
						<input type="number" bind:value={publicChatConfig.max_length} min="10" max="1000" />
					</div>

					<div class="pca-row full-width">
						<label class="toggle-label">
							<input type="checkbox" bind:checked={publicChatConfig.block_duplicates} />
							<span>{$t("admin_public_chat_block_dup") || 'Bloquer les messages consécutifs identiques'}</span>
						</label>
					</div>

					<div class="pca-field full-width">
						<label>{$t("admin_public_chat_banned_words") || 'Mots interdits (séparés par une virgule)'}</label>
						<input type="text" bind:value={publicChatConfig.banned_words_text} placeholder="ex: spam, hack, insult..." />
					</div>

					<div class="pca-row full-width">
						<label class="toggle-label">
							<input type="checkbox" bind:checked={publicChatConfig.ai_mention_enabled} />
							<span><strong>{$t("admin_public_chat_ai_mention") || "Activer l'IA @Alanbix"}</strong> — {$t("admin_public_chat_ai_mention_sub") || "L'IA répond quand mentionnée (@Alanbix) dans le chat public"}</span>
						</label>
					</div>

					{#if publicChatConfig.ai_mention_enabled}
						<div class="pca-field">
							<label>{$t("admin_public_chat_ai_cooldown") || 'Cooldown IA @Alanbix (secondes)'}</label>
							<input type="number" bind:value={publicChatConfig.ai_cooldown_seconds} min="5" max="300" />
						</div>
					{/if}

					<div class="pca-actions full-width flex-row gap-3 mt-3">
						<button class="btn-primary" on:click={savePublicChatConfig}>
							💾 {$t("admin_public_chat_save_btn") || 'Enregistrer les paramètres du chat'}
						</button>
						<button class="btn-outline-danger" on:click={clearChatHistoryAdmin}>
							🗑️ {$t("admin_public_chat_purge_btn") || 'Vider les messages du chat'}
						</button>
					</div>
				</div>
			</div>
		</div>

		<!-- Danger Zone -->
		<div class="sc danger-zone sc-full">
			<div class="sc-head">
				<div class="sc-icon">☢️</div>
				<div>
					<h3 style="color: var(--danger)">{$t("admin_settings_danger_zone")}</h3>
					<p class="sc-sub">{$t("admin_settings_danger_zone_sub")}</p>
				</div>
			</div>
			<div class="sc-body">
				<div class="nuke-grid">
					<!-- Nuke Tournaments -->
					<div class="nuke-card">
						<div class="nuke-info">
							<span class="nuke-icon">🏆</span>
							<div>
								<strong>{$t("admin_settings_del_tourneys")}</strong>
								<p>{$t("admin_settings_del_tourneys_sub")}</p>
							</div>
						</div>
						{#if nukeConfirm.tournaments}
							<div class="nuke-confirm">
								<span class="text-danger text-xs font-bold">{$t("admin_settings_confirm_delete_q")}</span>
								<button class="btn-danger-sm" on:click={nukeTournaments} disabled={nuking.tournaments}>
									{nuking.tournaments ? '⏳...' : $t("admin_settings_del_tourneys_btn_confirm")}
								</button>
								<button class="btn-secondary btn-xs" on:click={() => nukeConfirm.tournaments = false}>{$t('admin_settings_cancel')}</button>
							</div>
						{:else}
							<button class="btn-outline-danger" on:click={() => nukeConfirm.tournaments = true}>{$t('admin_settings_del_tourneys_btn')}</button>
						{/if}
					</div>

					<!-- Nuke Players -->
					<div class="nuke-card">
						<div class="nuke-info">
							<span class="nuke-icon">👥</span>
							<div>
								<strong>{$t("admin_settings_del_players")}</strong>
								<p>{$t("admin_settings_del_players_sub")}</p>
							</div>
						</div>
						{#if nukeConfirm.players}
							<div class="nuke-confirm">
								<span class="text-danger text-xs font-bold">{$t("admin_settings_confirm_delete_q")}</span>
								<button class="btn-danger-sm" on:click={nukePlayers} disabled={nuking.players}>
									{nuking.players ? '⏳...' : $t("admin_settings_del_tourneys_btn_confirm")}
								</button>
								<button class="btn-secondary btn-xs" on:click={() => nukeConfirm.players = false}>{$t('admin_settings_cancel')}</button>
							</div>
						{:else}
							<button class="btn-outline-danger" on:click={() => nukeConfirm.players = true}>{$t('admin_settings_del_players_btn')}</button>
						{/if}
					</div>

					<!-- Nuke Games -->
					<div class="nuke-card">
						<div class="nuke-info">
							<span class="nuke-icon">🎮</span>
							<div>
								<strong>{$t("admin_settings_del_games")}</strong>
								<p>{$t("admin_settings_del_games_sub")}</p>
							</div>
						</div>
						{#if nukeConfirm.games}
							<div class="nuke-confirm">
								<span class="text-danger text-xs font-bold">{$t("admin_settings_delete_confirm_warning")}</span>
								<button class="btn-danger-sm" on:click={nukeGames} disabled={nuking.games}>
									{nuking.games ? '⏳...' : $t("admin_settings_del_games_btn_confirm")}
								</button>
								<button class="btn-secondary btn-xs" on:click={() => nukeConfirm.games = false}>{$t('admin_settings_cancel')}</button>
							</div>
						{:else}
							<button class="btn-outline-danger" on:click={() => nukeConfirm.games = true}>{$t('admin_settings_del_games_btn')}</button>
						{/if}
					</div>

					<!-- Nuke Images -->
					<div class="nuke-card">
						<div class="nuke-info">
							<span class="nuke-icon">🗑️</span>
							<div>
								<strong>{$t("admin_settings_purge_chat")}</strong>
								<p>{$t("admin_settings_purge_chat_sub")}</p>
							</div>
						</div>
						{#if nukeConfirm.images}
							<div class="nuke-confirm">
								<span class="text-danger text-xs font-bold">{$t("admin_settings_delete_confirm_images")}</span>
								<button class="btn-danger-sm" on:click={nukeImages} disabled={nuking.images}>
									{nuking.images ? '⏳...' : $t("admin_settings_del_games_btn_confirm")}
								</button>
								<button class="btn-secondary btn-xs" on:click={() => nukeConfirm.images = false}>{$t('admin_settings_cancel')}</button>
							</div>
						{:else}
							<button class="btn-outline-danger" on:click={() => nukeConfirm.images = true}>{$t('admin_settings_purge_chat_btn')}</button>
						{/if}
					</div>

					<!-- Nuke Notifications -->
					<div class="nuke-card">
						<div class="nuke-info">
							<span class="nuke-icon">🔔</span>
							<div>
								<strong>{$t("admin_settings_purge_notifs")}</strong>
								<p>{$t("admin_settings_purge_notifs_sub")}</p>
							</div>
						</div>
						{#if nukeConfirm.notifications}
							<div class="nuke-confirm">
								<span class="text-danger text-xs font-bold">{$t("admin_settings_delete_confirm_notifs")}</span>
								<button class="btn-danger-sm" on:click={nukeNotifications} disabled={nuking.notifications}>
									{nuking.notifications ? '⏳...' : $t("admin_settings_del_games_btn_confirm")}
								</button>
								<button class="btn-secondary btn-xs" on:click={() => nukeConfirm.notifications = false}>{$t('admin_settings_cancel')}</button>
							</div>
						{:else}
							<button class="btn-outline-danger" on:click={() => nukeConfirm.notifications = true}>{$t('admin_settings_purge_notifs')}</button>
						{/if}
					</div>

					<!-- Nuke Awards -->
					<div class="nuke-card">
						<div class="nuke-info">
							<span class="nuke-icon">🏆</span>
							<div>
								<strong>{$t("admin_settings_purge_awards") || $t("admin_settings_purge_notifs")}</strong>
								<p>{$t("admin_settings_purge_awards_sub") || "Supprime l'ensemble des prix et distinctions décernés"}</p>
							</div>
						</div>
						{#if nukeConfirm.awards}
							<div class="nuke-confirm">
								<span class="text-danger text-xs font-bold">{$t("admin_settings_delete_confirm_awards")}</span>
								<button class="btn-danger-sm" on:click={nukeAwards} disabled={nuking.awards}>
									{nuking.awards ? '⏳...' : $t("admin_settings_del_games_btn_confirm")}
								</button>
								<button class="btn-secondary btn-xs" on:click={() => nukeConfirm.awards = false}>{$t('admin_settings_cancel')}</button>
							</div>
						{:else}
							<button class="btn-outline-danger" on:click={() => nukeConfirm.awards = true}>{$t('admin_settings_purge_awards') || 'Purger les prix'}</button>
						{/if}
					</div>
				</div>
			</div>
		</div>
	</div>

	<!-- IA TAB -->
	{:else if settingsSubTab === 'ia'}
	<div class="stab-content">
		<!-- AI Queue Panel -->
		<div class="sc glass">
			<div class="sc-head">
				<div class="sc-icon">📋</div>
				<div style="flex:1">
					<h3>{$t('admin_settings_ai_queue')}</h3>
					<p class="sc-sub">{$t("admin_settings_ai_queue_sub")}</p>
				</div>
				<div class="queue-stats-badges">
					<span class="queue-stat-badge pending" title="{$t('admin_settings_queue_pending')}">⏳ {iaQueueData.queue_size}</span>
					<span class="queue-stat-badge active" title="{$t('admin_settings_queue_processing')}">⚡ {iaQueueData.active_count}</span>
					<span class="queue-stat-badge avg" title="{$t('admin_settings_queue_avg_duration')}">⏱️ {iaQueueData.avg_duration}s</span>
				</div>
			</div>
			<div class="sc-body">
				{#if iaQueueData.active.length > 0}
					<div class="queue-section-label">{$t("admin_settings_queue_processing")}</div>
					{#each iaQueueData.active as entry}
						<div class="queue-row active">
							<span class="queue-row-type">{entry.task_type === 'chat' ? '💬' : entry.task_type === 'compress' ? '🗜️' : (entry.task_type === 'title_suggestion' || entry.task_type === 'auto_title') ? '📝' : '🏆'}</span>
							<span class="queue-row-user">{entry.username || '—'}</span>
							<span class="queue-row-type-label">{entry.task_type}</span>
							<span class="queue-row-time">{entry.processing_since}s</span>
							<button class="queue-cancel-btn" on:click|stopPropagation={() => cancelQueueEntry(entry.id)} title="{$t('admin_settings_queue_cancel_tooltip')}">❌</button>
						</div>
					{/each}
				{/if}
				{#if iaQueueData.pending.length > 0}
					<div class="queue-section-label" style="margin-top:{iaQueueData.active.length > 0 ? '0.75rem' : '0'}">{$t("admin_settings_queue_pending")}</div>
					{#each iaQueueData.pending as entry}
						<div class="queue-row">
							<span class="queue-row-pos">#{entry.position}</span>
							<span class="queue-row-type">{entry.task_type === 'chat' ? '💬' : entry.task_type === 'compress' ? '🗜️' : (entry.task_type === 'title_suggestion' || entry.task_type === 'auto_title') ? '📝' : '🏆'}</span>
							<span class="queue-row-user">{entry.username || '—'}</span>
							<span class="queue-row-type-label">{entry.task_type}</span>
							<span class="queue-row-time">{entry.waiting_since}s</span>
							<button class="queue-cancel-btn" on:click|stopPropagation={() => cancelQueueEntry(entry.id)} title="{$t('admin_settings_queue_cancel_tooltip')}">❌</button>
						</div>
					{/each}
				{/if}
				{#if iaQueueData.active.length === 0 && iaQueueData.pending.length === 0}
					<div class="queue-empty">✅ {$t("admin_settings_ai_queue_empty")}</div>
				{/if}
			</div>
		</div>

		<!-- Ollama Instances -->
		<div class="sc glass">
			<div class="sc-head">
				<div class="sc-icon">🖥️</div>
				<div style="flex:1">
					<h3>{$t('admin_settings_ai_instances')}</h3>
					<p class="sc-sub">{$t("admin_settings_ai_instances_sub")}</p>
				</div>
				<button class="btn-add btn-xs" on:click={addInstance}>+ Ajouter</button>
			</div>
			<div class="sc-body">
				{#each iaConfig.ollama_instances as inst, idx}
					{@const status = instanceStatuses.find(s => s.url === inst.url)}
					<div class="inst-row" class:disabled={!inst.enabled}>
						<div class="inst-prio">
							<button class="reorder-btn" on:click={() => moveInstance(idx, -1)} disabled={idx === 0}>▲</button>
							<span class="prio-num">{inst.priority ?? idx}</span>
							<button class="reorder-btn" on:click={() => moveInstance(idx, 1)} disabled={idx === iaConfig.ollama_instances.length - 1}>▼</button>
						</div>
						<div class="inst-status">{status?.online ? '🟢' : '🔴'}</div>
						<div class="inst-main">
							<input type="text" class="inst-name-input" bind:value={inst.label} on:change={saveIAConfig} placeholder="{$t('admin_settings_instances_gpu_placeholder')}" />
							<div class="inst-meta">
								<input type="text" class="inst-url-input" bind:value={inst.url} on:change={saveIAConfig} placeholder="http://..." />
								<select bind:value={inst.model} on:change={saveIAConfig} class="inst-model-select">
									<option value="">— Modèle —</option>
									{#each (status?.available_models || availableModels.map(m => m.name)) as mName}
										<option value={mName}>{mName}</option>
									{/each}
								</select>
								{#if status?.online}
									<span class="inst-ping">{status.latency_ms}ms</span>
								{/if}
								{#if status?.avg_duration !== undefined && status?.avg_duration !== null}
									<span class="inst-ping" style="background: rgba(139, 92, 246, 0.15); color: #c084fc; border-color: rgba(139, 92, 246, 0.35);">⏱️ {status.avg_duration}s</span>
								{/if}
							</div>
						</div>
						<div class="inst-actions">
							<label class="toggle-switch-mini">
								<input type="checkbox" bind:checked={inst.enabled} on:change={saveIAConfig} />
								<span class="toggle-slider"></span>
							</label>
							<button class="inst-btn-mini" on:click={() => testInstance(idx)} title="Tester">🔍</button>
							<button class="inst-btn-mini danger" on:click={() => removeInstance(idx)} title="{$t('admin_tourneys_tooltip_delete')}">✕</button>
						</div>
					</div>
				{:else}
					<div class="inst-empty">{$t("admin_settings_instances_empty")}</div>
				{/each}
			</div>
		</div>

		<!-- Configuration du Modèle -->
		<div class="sc glass">
			<div class="sc-head compact">
				<div class="sc-icon sm">⚙️</div>
				<div style="flex:1">
					<h3>{$t('admin_settings_ai_model_cfg')}</h3>
					<p class="sc-sub">{$t('admin_settings_ai_model_cfg_sub')}</p>
				</div>
			</div>
			<div class="sc-body" style="gap: 0.8rem;">
				<!-- Temperature -->
				<div>
					<div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.2rem;">
						<label class="compact-label">{$t('admin_settings_ai_temp')} <strong>{iaConfig.temperature}</strong></label>
						<span class="range-hint text-xs" style="color: var(--text-muted); font-size: 0.65rem;">
							{iaConfig.temperature <= 0.3 ? $t('admin_settings_ai_temp_precise') : iaConfig.temperature >= 0.7 ? $t('admin_settings_ai_temp_creative') : $t('admin_settings_ai_temp_balanced')}
						</span>
					</div>
					<input type="range" bind:value={iaConfig.temperature} on:change={saveIAConfig} min="0" max="1" step="0.1" class="range-accent" style="width: 100%;" />
				</div>

				<!-- Context Window -->
				<div>
					<div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.2rem;">
						<label class="compact-label">{$t('admin_settings_ai_context')} <strong>{iaConfig.context_window} tokens</strong></label>
						<input 
							type="number" 
							bind:value={iaConfig.context_window} 
							on:change={saveIAConfig} 
							min="512" 
							step="256"
							style="width: 80px; background: var(--surface-sunken); border: 1px solid var(--glass-border); border-radius: 6px; padding: 0.15rem 0.4rem; color: var(--text-main); font-size: 0.72rem; font-weight: 700; text-align: right;" 
						/>
					</div>
					<div class="ctx-presets-grid" style="display: flex; gap: 0.25rem;">
						{#each [2048, 4096, 8192, 16384, 32768] as size}
							<button 
								type="button" 
								class="ctx-preset-mini-btn" 
								class:active={iaConfig.context_window === size}
								on:click={() => { iaConfig.context_window = size; saveIAConfig(); }}
							>
								{size >= 1024 ? (size / 1024) + 'K' : size}
							</button>
						{/each}
					</div>
					<span class="range-hint text-xs" style="color: var(--text-muted); font-size: 0.65rem; display: block; margin-top: 0.25rem; line-height: 1.2;">
						{$t('admin_settings_ai_context_hint')}
					</span>
				</div>

				<!-- Embedding Model -->
				<div>
					<label class="compact-label" style="margin-bottom: 0.2rem; display: block;">{$t('admin_settings_ai_rag_model')}</label>
					<select bind:value={iaConfig.embedding_model} on:change={saveIAConfig} class="inst-model-select-wide">
						<option value="">— Auto (nomic-embed-text) —</option>
						{#each availableModels.filter(m => m.name.includes('embed')) as m}
							<option value={m.name}>{m.name}</option>
						{/each}
					</select>
				</div>

				<!-- Tool Calling Mode -->
				<div>
					<label class="compact-label" style="margin-bottom: 0.2rem; display: block;">{$t('admin_settings_ai_tool_mode')}</label>
					<select bind:value={iaConfig.tool_calling_mode} on:change={saveIAConfig} class="inst-model-select-wide">
						<option value="stream_intercept">{$t('admin_settings_ai_tool_mode_intercept')}</option>
						<option value="legacy_double">{$t('admin_settings_ai_tool_mode_legacy')}</option>
						<option value="disabled">{$t('admin_settings_ai_tool_mode_disabled')}</option>
					</select>
				</div>

				<!-- Network Tools -->
				<div style="display: flex; align-items: center; justify-content: space-between; padding-top: 0.4rem; border-top: 1px solid var(--glass-border);">
					<span class="compact-label" style="font-weight: 600;">{$t('admin_settings_ai_tools')}</span>
					<label class="toggle-switch-mini">
						<input type="checkbox" bind:checked={iaConfig.network_tools_enabled} on:change={saveIAConfig} />
						<span class="toggle-slider"></span>
					</label>
				</div>

				<!-- Auto-moderation -->
				<div style="display: flex; align-items: center; justify-content: space-between; padding-top: 0.4rem; border-top: 1px solid var(--glass-border);">
					<span class="compact-label" style="font-weight: 600;">{$t('admin_settings_ai_moderation')}</span>
					<label class="toggle-switch-mini">
						<input type="checkbox" bind:checked={iaConfig.auto_moderation_enabled} on:change={saveIAConfig} />
						<span class="toggle-slider"></span>
					</label>
				</div>

				<!-- Appel Admin Outil -->
				<div style="display: flex; align-items: center; justify-content: space-between; padding-top: 0.4rem; border-top: 1px solid var(--glass-border);">
					<span class="compact-label" style="font-weight: 600;">{$t('ai_setting_call_admin_tool_enabled')}</span>
					<label class="toggle-switch-mini">
						<input type="checkbox" bind:checked={iaConfig.call_admin_enabled} on:change={saveIAConfig} />
						<span class="toggle-slider"></span>
					</label>
				</div>

				<!-- Appel Admin Bouton Manuel -->
				<div style="display: flex; align-items: center; justify-content: space-between; padding-top: 0.4rem; border-top: 1px solid var(--glass-border);">
					<span class="compact-label" style="font-weight: 600;">{$t('ai_setting_call_admin_btn_enabled')}</span>
					<label class="toggle-switch-mini">
						<input type="checkbox" bind:checked={iaConfig.call_admin_button_enabled} on:change={saveIAConfig} />
						<span class="toggle-slider"></span>
					</label>
				</div>
				{#if iaConfig.call_admin_enabled || iaConfig.call_admin_button_enabled}
				<div style="padding: 0.6rem; margin-top: 0.4rem; background: rgba(255, 255, 255, 0.03); border: 1px dashed var(--glass-border); border-radius: 4px; display: flex; flex-direction: column; gap: 0.5rem;">
					<span class="compact-label" style="font-weight: 600; font-size: 0.75rem; text-transform: uppercase; letter-spacing: 0.05em; color: var(--text-muted);">
						{$t('ai_setting_call_admin_antispam_section_title')}
					</span>
					<div style="display: flex; flex-direction: column; gap: 0.4rem;">
						<label class="compact-label" style="display: flex; align-items: center; justify-content: space-between;">
							<span>{$t('ai_setting_call_admin_cooldown')}</span>
							<input type="number" min="1" max="1440" bind:value={iaConfig.call_admin_cooldown_minutes} on:change={saveIAConfig} style="width:70px;" />
						</label>
						<label class="compact-label" style="display: flex; align-items: center; justify-content: space-between;">
							<span>{$t('ai_setting_call_admin_daily')}</span>
							<input type="number" min="1" max="50" bind:value={iaConfig.call_admin_daily_limit} on:change={saveIAConfig} style="width:70px;" />
						</label>
						<label class="compact-label" style="display: flex; align-items: center; justify-content: space-between;">
							<span>{$t('ai_setting_call_admin_global_hourly')}</span>
							<input type="number" min="1" max="500" bind:value={iaConfig.call_admin_global_hourly_limit} on:change={saveIAConfig} style="width:70px;" />
						</label>
					</div>
				</div>
				{/if}

				<!-- Suggestions RAG -->
				<div style="display: flex; align-items: center; justify-content: space-between; padding-top: 0.4rem; border-top: 1px solid var(--glass-border);">
					<span class="compact-label" style="font-weight: 600;">{$t('ai_setting_rag_suggestion_enabled')}</span>
					<label class="toggle-switch-mini">
						<input type="checkbox" bind:checked={iaConfig.rag_suggestion_enabled} on:change={saveIAConfig} />
						<span class="toggle-slider"></span>
					</label>
				</div>
			</div>
		</div>

		<!-- Prompts de l'IA -->
		<div class="sc glass">
			<div class="sc-head compact">
				<div class="sc-icon sm">💬</div>
				<div style="flex:1">
					<h3>{$t('admin_settings_ai_prompts')}</h3>
					<p class="sc-sub">{$t('admin_settings_ai_prompts_sub')}</p>
				</div>
			</div>
			<div class="sc-body" style="gap: 0.75rem; flex: 1; display: flex; flex-direction: column;">
				<div class="prompts-container" style="flex: 1;">
					<div style="display: flex; flex-direction: column; gap: 0.3rem; min-width: 0; flex: 1;">
						<div style="display: flex; align-items: center; justify-content: space-between; margin-bottom: 0.3rem;">
							<label class="compact-label">{$t('admin_settings_ai_prompt_sys')}</label>
							<button class="btn-prompt-edit" on:click={openPromptModal} title="{$t('admin_prompt_modal_open')}">✏️ {$t('admin_prompt_modal_open')}</button>
						</div>
						<textarea class="prompt-textarea-compact" bind:value={systemPrompt} on:input={() => debounceSave('systemPrompt', saveSystemPrompt)} placeholder="{$t('admin_settings_ai_prompt_sys_placeholder')}" rows="8" style="flex: 1; height: 100%; resize: none;"></textarea>
					</div>
					<div style="display: flex; flex-direction: column; gap: 0.3rem; min-width: 0; flex: 1;">
						<label class="compact-label">{$t('admin_settings_ai_prompt_close')}</label>
						<textarea class="prompt-textarea-compact" bind:value={closingPrompt} on:input={() => debounceSave('closingPrompt', saveClosingPrompt)} placeholder="{$t('admin_settings_ai_prompt_close_placeholder')}" rows="6" style="flex: 1; height: 100%; resize: none;"></textarea>
					</div>
				</div>
			</div>
		</div>

		<!-- RAG -->
		<div class="sc glass sc-full">
			<div class="sc-head">
				<div class="sc-icon">📚</div>
				<div style="flex:1">
					<h3>{$t('admin_settings_ai_rag')}</h3>
					<p class="sc-sub">{$t('admin_settings_ai_rag_sub')}</p>
				</div>
				<span class="badge-count">{knowledgeDocs.length}</span>
			</div>
			<div class="sc-body">
				<!-- Existing documents -->
				{#if knowledgeDocs.length > 0}
					<div class="rag-list">
						{#each knowledgeDocs as doc}
							<div class="rag-item {editingDocId === doc.id ? 'rag-item-editing' : ''}">
								<div class="rag-item-main">
									<div class="rag-item-header">
										<span class="rag-id">#{doc.id}</span>
										<span class="rag-size">{doc.content_length} {$t("admin_settings_ai_rag_chars")}</span>
										{#if doc.has_embedding}
											<span class="rag-embed-badge">{$t("admin_settings_ai_rag_vectorized")}</span>
										{:else}
											<span class="rag-embed-badge no">{$t("admin_settings_ai_rag_non_vectorized")}</span>
										{/if}
									</div>
									{#if editingDocId === doc.id}
										{#if editDocLoading}
											<div class="rag-edit-loading">{$t("admin_settings_ai_rag_edit_loading")}</div>
										{:else}
											<textarea class="rag-edit-textarea" bind:value={editDocContent} rows="8" disabled={editDocSaving}></textarea>
											{#if editDocSaving}
												<div class="rag-vectorize-anim">
													<div class="rag-vectorize-bar"></div>
													<span class="rag-vectorize-label">{$t("admin_settings_ai_rag_vectorizing")}</span>
												</div>
											{:else}
												<div class="rag-edit-actions">
													<span class="rag-edit-chars">{editDocContent.length} {$t("admin_settings_ai_rag_chars")}</span>
													<button class="btn-secondary btn-xs" on:click={() => { editingDocId = null; editDocContent = ''; }}>✕ {$t('admin_settings_cancel')}</button>
													<button class="btn-primary btn-xs" on:click={saveKnowledgeEdit} disabled={!editDocContent.trim()}>{$t("admin_settings_ai_rag_btn_save_vectorize")}</button>
												</div>
											{/if}
										{/if}
									{:else}
										<p class="rag-preview">{doc.content}</p>
									{/if}
								</div>
								<div class="rag-item-actions">
									<button class="btn-icon" title="{$t('admin_tourneys_tooltip_edit')}" on:click={() => editKnowledge(doc.id)}>{editingDocId === doc.id ? '✕' : '✏️'}</button>
									<button class="btn-icon btn-icon-danger" title="{$t('admin_tourneys_tooltip_delete')}" on:click={() => deleteKnowledge(doc.id)}>🗑️</button>
								</div>
							</div>
						{/each}
					</div>
				{:else}
					<div class="rag-empty">
						<span>📭</span>
						<p>{$t("admin_settings_ai_rag_empty")}</p>
					</div>
				{/if}

				<!-- Add new document -->
				<div class="rag-add-section">
					<textarea bind:value={newDocContent} placeholder="{$t('admin_settings_ai_rag_placeholder')}" class="prompt-textarea" rows="3" disabled={uploadingDoc}></textarea>
					{#if uploadingDoc}
						<div class="rag-vectorize-anim">
							<div class="rag-vectorize-bar"></div>
							<span class="rag-vectorize-label">{$t("admin_settings_ai_rag_vectorizing_new", { count: newDocContent.length })}</span>
						</div>
					{:else}
						<button class="btn-primary btn-xs" on:click={uploadRagDoc} style="align-self:flex-end;margin-top:0.5rem;" disabled={!newDocContent.trim()}>{$t("admin_settings_ai_rag_btn_add")}</button>
					{/if}
				</div>
			</div>
		</div>
	</div>
	{/if}
</div>

<!-- System Prompt Editor Modal -->
{#if showPromptModal}
<div class="prompt-modal-overlay" use:portal on:mousedown|self={() => showPromptModal = false} role="dialog" aria-modal="true">
	<div class="prompt-modal">
		<!-- Header -->
		<div class="prompt-modal-header">
			<div class="prompt-modal-title-group">
				<span class="prompt-modal-icon">🧪</span>
				<div>
					<h2 class="prompt-modal-title">{$t('admin_prompt_modal_title')}</h2>
					<p class="prompt-modal-subtitle">{$t('admin_prompt_modal_subtitle')}</p>
				</div>
			</div>
			<button class="prompt-modal-close" on:click={() => showPromptModal = false}>✕</button>
		</div>

		<!-- Body: two-column layout -->
		<div class="prompt-modal-body">
			<!-- LEFT: Textarea -->
			<div class="prompt-modal-editor">
				<div class="prompt-modal-char-count">{$t('admin_prompt_modal_char_count').replace('{count}', promptModalDraft.length)}</div>
				<textarea
					class="prompt-modal-textarea"
					bind:value={promptModalDraft}
					placeholder="{$t('admin_settings_ai_prompt_sys_placeholder')}"
					spellcheck="false"
				></textarea>
			</div>

			<!-- RIGHT: Guide panel -->
			<div class="prompt-modal-guide">
				<!-- Section blocks -->
				<div class="pmg-section">
					<h4 class="pmg-section-title">📐 {$t('admin_prompt_modal_guide_title')}</h4>
					<p class="pmg-intro">{$t('admin_prompt_modal_guide_intro')}</p>
					<div class="pmg-blocks">
						{#each DEFAULT_PROMPT_SECTIONS as sec}
							<div class="pmg-block">
								<div class="pmg-block-header">
									<span class="pmg-block-icon">{sec.icon}</span>
									<code class="pmg-block-tag">{$t(`admin_prompt_modal_section_${sec.key}`)}</code>
									<button class="pmg-insert-btn" on:click={() => insertSection(sec.key)} title="{$t('admin_prompt_modal_insert')}">
										+ {$t('admin_prompt_modal_insert')}
									</button>
								</div>
								<p class="pmg-block-desc">{$t(`admin_prompt_modal_section_${sec.key}_desc`)}</p>
							</div>
						{/each}
					</div>
				</div>

				<!-- Tips -->
				<div class="pmg-section pmg-tips">
					<h4 class="pmg-section-title">{$t('admin_prompt_modal_tip_title')}</h4>
					<ul class="pmg-tip-list">
						<li>{$t('admin_prompt_modal_tip_1')}</li>
						<li>{$t('admin_prompt_modal_tip_2')}</li>
						<li>{$t('admin_prompt_modal_tip_3')}</li>
						<li>{$t('admin_prompt_modal_tip_4')}</li>
					</ul>
				</div>
			</div>
		</div>

		<!-- Footer -->
		<div class="prompt-modal-footer">
			<button class="btn-secondary" on:click={() => showPromptModal = false}>{$t('admin_prompt_modal_cancel')}</button>
			<button class="btn-primary" on:click={savePromptFromModal}>{$t('admin_prompt_modal_save')}</button>
		</div>
	</div>
</div>
{/if}

<style>
	.settings-view { display: flex; flex-direction: column; gap: 0; }
	.settings-tabs { display: flex; gap: 0.25rem; padding: 0.25rem; background: var(--surface-sunken); border-radius: 12px; margin-bottom: 1.5rem; }
	.stab { flex: 1; padding: 0.7rem 1rem; background: none; border: none; color: var(--text-dim); font-size: 0.85rem; font-weight: 600; cursor: pointer; border-radius: 10px; transition: all 0.2s; display: flex; align-items: center; justify-content: center; gap: 0.4rem; }
	.stab:hover { color: var(--text-main); background: var(--hover-tint); }
	.stab.active { background: rgba(59,130,246,0.12); color: var(--accent); box-shadow: 0 0 12px rgba(59,130,246,0.1); }
	.stab-icon { font-size: 1rem; }
	.stab-content {
		display: grid;
		grid-template-columns: minmax(0, 1fr);
		gap: 1rem;
		align-items: stretch;
		animation: fadeIn 0.2s ease;
	}
	@media (min-width: 800px) {
		.stab-content {
			grid-template-columns: repeat(2, minmax(0, 1fr));
		}
	}
	@keyframes fadeIn { from { opacity: 0; transform: translateY(4px); } to { opacity: 1; transform: translateY(0); } }

	/* Settings Card */
	.sc { display: flex; flex-direction: column; height: 100%; border-radius: 12px; padding: 0; overflow: hidden; border: 1px solid var(--glass-border); }
	.sc.sc-full { grid-column: 1 / -1; }
	.sc-head { display: flex; align-items: center; gap: 0.6rem; padding: 0.75rem 1rem; border-bottom: 1px solid var(--glass-border); background: var(--hover-tint); }
	.sc-head.compact { padding: 0.5rem 0.8rem; }
	.sc-head h3 { font-size: 0.9rem; color: var(--text-main); margin: 0; }
	.sc-icon { font-size: 1rem; width: 28px; height: 28px; display: flex; align-items: center; justify-content: center; background: rgba(59,130,246,0.08); border-radius: 8px; flex-shrink: 0; }
	.sc-icon.sm { font-size: 0.85rem; width: 22px; height: 22px; border-radius: 6px; }
	.sc-sub { font-size: 0.68rem; color: var(--text-muted); margin: 0.1rem 0 0; }
	.sc-body { flex: 1; padding: 0.8rem 1rem; display: flex; flex-direction: column; }

	/* Scoring toggle */
	.scoring-toggle { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 0.6rem; }
	.score-opt { display: flex; flex-direction: column; align-items: center; gap: 0.2rem; padding: 0.8rem; background: var(--hover-tint); border: 1px solid var(--glass-border); border-radius: 12px; cursor: pointer; transition: all 0.2s; color: var(--text-main); }
	.score-opt:hover { border-color: rgba(59,130,246,0.3); background: rgba(59,130,246,0.04); }
	.score-opt.active { border-color: var(--accent); background: rgba(59,130,246,0.1); box-shadow: 0 0 15px rgba(59,130,246,0.1); }
	.score-opt-icon { font-size: 1.2rem; }
	.score-opt-label { font-size: 0.85rem; font-weight: 700; color: var(--text-main); }
	.score-opt-desc { font-size: 0.65rem; color: var(--text-muted); }

	/* Default Points Grid */
	.default-pts-grid { display: grid; grid-template-columns: repeat(5, minmax(0, 1fr)); gap: 0.5rem; }
	.dpt-field { display: flex; flex-direction: column; gap: 0.25rem; }
	.dpt-field label { font-size: 0.7rem; font-weight: 700; color: var(--text-muted); text-align: center; }
	.dpt-field input { background: var(--surface-sunken); border: 1px solid var(--glass-border); border-radius: 8px; padding: 0.4rem; color: var(--text-main); font-size: 0.9rem; font-weight: 700; text-align: center; width: 100%; transition: border-color 0.2s; }
	.dpt-field input:focus { border-color: var(--accent); outline: none; }

	/* Compact Labels & Selects */
	.compact-label { font-size: 0.72rem; font-weight: 700; color: var(--text-dim); text-transform: uppercase; letter-spacing: 0.04em; margin: 0; }
	.ctx-preset-mini-btn { flex: 1; padding: 0.25rem 0.5rem; font-size: 0.68rem; font-weight: 600; border: 1px solid var(--glass-border); border-radius: 6px; background: var(--hover-tint); color: var(--text-dim); cursor: pointer; transition: all 0.15s; text-align: center; }
	.ctx-preset-mini-btn:hover { border-color: var(--accent); background: rgba(59,130,246,0.05); }
	.ctx-preset-mini-btn.active { background: var(--accent-soft); border-color: var(--accent); color: var(--accent); box-shadow: 0 0 8px var(--accent-glow); }
	.inst-model-select-wide { width: 100%; background: var(--surface-sunken); border: 1px solid var(--glass-border); border-radius: 8px; padding: 0.35rem 0.5rem; color: var(--text-main); font-size: 0.75rem; transition: all 0.2s; }
	.inst-model-select-wide:focus { border-color: var(--accent); outline: none; }
	.range-accent { width: 100%; accent-color: var(--accent); }

	/* Prompts */
	.prompt-textarea-compact { width: 100%; max-width: 100%; box-sizing: border-box; background: var(--surface-sunken); border: 1px solid var(--glass-border); border-radius: 8px; padding: 0.5rem; color: var(--text-main); font-size: 0.75rem; resize: vertical; font-family: inherit; line-height: 1.4; min-height: 140px; }
	.prompt-textarea-compact:focus { outline: none; border-color: var(--accent); }
	.prompts-container { display: grid; grid-template-columns: minmax(0, 1fr); gap: 0.8rem; width: 100%; }
	@media (min-width: 1024px) {
		.prompts-container { grid-template-columns: repeat(2, minmax(0, 1fr)); }
	}
	.prompt-textarea { width: 100%; background: var(--surface-sunken); border: 1px solid var(--glass-border); border-radius: 10px; padding: 0.7rem; color: var(--text-main); font-size: 0.8rem; resize: vertical; font-family: inherit; line-height: 1.5; min-height: 80px; }
	.prompt-textarea:focus { border-color: var(--accent); outline: none; }
	.btn-prompt-edit { font-size: 0.68rem; font-weight: 700; padding: 0.2rem 0.6rem; border-radius: 6px; border: 1px solid rgba(139,92,246,0.3); background: rgba(139,92,246,0.06); color: #a78bfa; cursor: pointer; transition: all 0.15s; white-space: nowrap; }
	.btn-prompt-edit:hover { background: rgba(139,92,246,0.18); border-color: #a78bfa; box-shadow: 0 0 8px rgba(139,92,246,0.2); }

	/* Instances */
	.inst-row { display: flex; align-items: center; gap: 0.6rem; padding: 0.6rem 0.8rem; border-radius: 10px; background: var(--hover-tint); border: 1px solid transparent; transition: all 0.2s; margin-bottom: 0.4rem; }
	.inst-row:hover { background: var(--accent-soft); border-color: var(--glass-border); }
	.inst-row.disabled { opacity: 0.4; }
	.inst-prio { display: flex; flex-direction: column; align-items: center; gap: 1px; }
	.prio-num { font-size: 0.6rem; font-weight: 800; color: var(--accent); min-width: 1rem; text-align: center; }
	.reorder-btn { background: none; border: 1px solid var(--glass-border); border-radius: 4px; color: var(--text-dim); font-size: 0.5rem; padding: 0.05rem 0.2rem; cursor: pointer; line-height: 1; transition: all 0.15s; }
	.reorder-btn:hover:not(:disabled) { color: var(--accent); border-color: var(--accent); }
	.reorder-btn:disabled { opacity: 0.15; cursor: default; }
	.inst-status { font-size: 0.65rem; }
	.inst-main { flex: 1; min-width: 0; }
	.inst-name-input { width: 100%; background: transparent; border: none; border-bottom: 1px solid var(--glass-border); color: var(--text-main); font-size: 0.8rem; font-weight: 700; padding: 0.1rem 0; }
	.inst-name-input:focus { border-color: var(--accent); outline: none; }
	.inst-meta { display: flex; align-items: center; gap: 0.4rem; margin-top: 0.3rem; }
	.inst-url-input { flex: 1; min-width: 80px; background: var(--surface-sunken); border: 1px solid var(--glass-border); border-radius: 6px; padding: 0.2rem 0.4rem; color: var(--text-dim); font-size: 0.7rem; font-family: monospace; }
	.inst-model-select { background: var(--surface-sunken); border: 1px solid var(--glass-border); border-radius: 6px; padding: 0.2rem 0.4rem; color: var(--text-main); font-size: 0.7rem; max-width: 120px; min-width: 80px; }
	.inst-model-select option { background: var(--bg-secondary); color: var(--text-main); }
	.inst-ping { font-size: 0.6rem; color: #10b981; font-weight: 700; padding: 0.1rem 0.35rem; background: rgba(16,185,129,0.1); border-radius: 4px; }
	.inst-actions { display: flex; align-items: center; gap: 0.3rem; }
	.inst-btn-mini { background: var(--hover-tint); border: 1px solid var(--glass-border); border-radius: 6px; width: 22px; height: 22px; display: flex; align-items: center; justify-content: center; cursor: pointer; font-size: 0.65rem; transition: all 0.15s; }
	.inst-btn-mini:hover { background: rgba(59,130,246,0.15); border-color: var(--accent); }
	.inst-btn-mini.danger:hover { background: rgba(239,68,68,0.2); border-color: var(--danger); }
	.inst-empty { text-align: center; padding: 1.5rem; color: var(--text-muted); font-size: 0.8rem; }
	.btn-add { background: rgba(59,130,246,0.1); border: 1px dashed rgba(59,130,246,0.3); color: var(--accent); border-radius: 8px; padding: 0.35rem 0.8rem; font-size: 0.75rem; font-weight: 700; cursor: pointer; transition: all 0.2s; }
	.btn-add:hover { background: rgba(59,130,246,0.2); border-style: solid; }
	.btn-add.btn-xs { padding: 0.2rem 0.5rem; font-size: 0.65rem; border-radius: 6px; }

	/* Switches */
	.toggle-switch-mini { position: relative; display: inline-block; width: 28px; height: 16px; cursor: pointer; }
	.toggle-switch-mini input { opacity: 0; width: 0; height: 0; }
	.toggle-switch-mini .toggle-slider { position: absolute; inset: 0; background: var(--surface-sunken); border-radius: 8px; transition: 0.2s; }
	.toggle-switch-mini .toggle-slider::before { content: ''; position: absolute; height: 12px; width: 12px; left: 2px; bottom: 2px; background: var(--text-dim); border-radius: 50%; transition: 0.2s; }
	.toggle-switch-mini input:checked + .toggle-slider { background: rgba(59,130,246,0.35); }
	.toggle-switch-mini input:checked + .toggle-slider::before { transform: translateX(12px); background: var(--accent); }

	/* Queue */
	.queue-stats-badges { display: flex; gap: 0.4rem; }
	.queue-stat-badge { font-size: 0.65rem; font-weight: 700; padding: 0.15rem 0.5rem; border-radius: 6px; font-family: monospace; }
	.queue-stat-badge.pending { background: rgba(245,158,11,0.12); color: #f59e0b; border: 1px solid rgba(245,158,11,0.3); }
	.queue-stat-badge.active { background: rgba(16,185,129,0.12); color: #10b981; border: 1px solid rgba(16,185,129,0.3); }
	.queue-stat-badge.avg { background: rgba(99,102,241,0.12); color: #818cf8; border: 1px solid rgba(99,102,241,0.3); }
	.queue-section-label { font-size: 0.7rem; font-weight: 700; color: var(--text-muted); text-transform: uppercase; letter-spacing: 0.05em; margin-bottom: 0.4rem; }
	.queue-row { display: flex; align-items: center; gap: 0.6rem; padding: 0.5rem 0.6rem; border-radius: 8px; background: var(--hover-tint); border: 1px solid transparent; margin-bottom: 0.3rem; transition: all 0.2s; }
	.queue-row:hover { border-color: var(--glass-border); }
	.queue-row.active { background: rgba(16,185,129,0.06); border: 1px solid rgba(16,185,129,0.2); }
	.queue-row-pos { font-size: 0.7rem; font-weight: 800; color: var(--accent); min-width: 1.5rem; }
	.queue-row-type { font-size: 0.85rem; }
	.queue-row-user { flex: 1; font-size: 0.8rem; font-weight: 600; color: var(--text-main); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
	.queue-row-type-label { font-size: 0.65rem; color: var(--text-muted); padding: 0.1rem 0.4rem; background: var(--surface-sunken); border-radius: 4px; }
	.queue-row-time { font-size: 0.65rem; color: var(--text-dim); font-family: monospace; min-width: 2.5rem; text-align: right; }
	.queue-cancel-btn { background: none; border: 1px solid rgba(239,68,68,0.2); color: var(--text-muted); border-radius: 6px; padding: 0.15rem 0.4rem; font-size: 0.6rem; cursor: pointer; transition: all 0.2s; }
	.queue-cancel-btn:hover { background: rgba(239,68,68,0.15); color: #ef4444; border-color: rgba(239,68,68,0.4); }
	.queue-empty { text-align: center; padding: 1rem; font-size: 0.8rem; color: var(--text-muted); }

	/* RAG List */
	.badge-count { font-size: 0.7rem; background: var(--accent-soft); color: var(--accent); padding: 0.2rem 0.6rem; border-radius: 4px; font-weight: 800; border: 1px solid var(--accent); }
	.rag-list { display: flex; flex-direction: column; gap: 0.4rem; margin-bottom: 1rem; max-height: 300px; overflow-y: auto; }
	.rag-item { display: flex; align-items: flex-start; gap: 0.5rem; padding: 0.6rem 0.7rem; border-radius: 8px; background: var(--hover-tint); border: 1px solid var(--glass-border); transition: all 0.15s; }
	.rag-item:hover { border-color: rgba(59,130,246,0.2); background: rgba(59,130,246,0.03); }
	.rag-item-main { flex: 1; min-width: 0; }
	.rag-item-header { display: flex; align-items: center; gap: 0.4rem; margin-bottom: 0.2rem; }
	.rag-id { font-size: 0.6rem; font-weight: 800; color: var(--accent); background: rgba(59,130,246,0.1); padding: 0.1rem 0.3rem; border-radius: 4px; }
	.rag-size { font-size: 0.6rem; color: var(--text-muted); }
	.rag-embed-badge { font-size: 0.55rem; font-weight: 700; padding: 0.1rem 0.35rem; border-radius: 4px; background: rgba(16,185,129,0.1); color: #10b981; }
	.rag-embed-badge.no { background: rgba(245,158,11,0.1); color: #f59e0b; }
	.rag-preview { font-size: 0.7rem; color: var(--text-dim); line-height: 1.4; margin: 0; overflow: hidden; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; word-break: break-word; }
	.rag-item-actions { display: flex; flex-direction: column; gap: 0.2rem; }
	.rag-item-editing { border-color: rgba(59,130,246,0.3); background: rgba(59,130,246,0.05); }
	.rag-edit-textarea { width: 100%; min-height: 120px; resize: vertical; border-radius: 6px; border: 1px solid var(--glass-border); background: var(--bg-secondary); color: var(--text-main); padding: 0.5rem; font-size: 0.75rem; font-family: inherit; line-height: 1.5; margin-top: 0.3rem; }
	.rag-edit-textarea:focus { outline: none; border-color: var(--accent); }
	.rag-edit-actions { display: flex; align-items: center; gap: 0.4rem; margin-top: 0.4rem; justify-content: flex-end; }
	.rag-edit-chars { font-size: 0.6rem; color: var(--text-muted); margin-right: auto; }
	.rag-edit-loading { font-size: 0.75rem; color: var(--text-muted); padding: 0.5rem 0; }
	.rag-vectorize-anim { position: relative; margin-top: 0.5rem; padding: 0.6rem 0.8rem; border-radius: 8px; overflow: hidden; background: rgba(99,102,241,0.06); border: 1px solid rgba(99,102,241,0.15); }
	.rag-vectorize-bar { position: absolute; top: 0; left: 0; height: 100%; width: 40%; background: linear-gradient(90deg, transparent, rgba(99,102,241,0.15), rgba(139,92,246,0.2), rgba(99,102,241,0.15), transparent); animation: rag-sweep 1.8s ease-in-out infinite; border-radius: 8px; }
	.rag-vectorize-label { position: relative; z-index: 1; font-size: 0.72rem; font-weight: 600; color: #a78bfa; display: flex; align-items: center; gap: 0.4rem; animation: rag-pulse-text 2s ease-in-out infinite; }
	@keyframes rag-sweep { 0% { left: -40%; } 100% { left: 100%; } }
	@keyframes rag-pulse-text { 0%, 100% { opacity: 0.7; } 50% { opacity: 1; } }
	.rag-empty { display: flex; flex-direction: column; align-items: center; gap: 0.3rem; padding: 1.5rem; color: var(--text-muted); font-size: 0.8rem; }
	.rag-empty span { font-size: 1.5rem; opacity: 0.5; }
	.rag-empty p { margin: 0; }
	.rag-add-section { margin-top: 0.75rem; padding-top: 0.75rem; border-top: 1px solid var(--glass-border); display: flex; flex-direction: column; }
	.btn-icon { background: var(--hover-tint); border: 1px solid var(--glass-border); border-radius: 6px; padding: 0.25rem 0.4rem; cursor: pointer; font-size: 0.75rem; transition: all 0.15s; flex-shrink: 0; }
	.btn-icon:hover { background: var(--accent-soft); border-color: var(--accent); }
	.btn-icon-danger:hover { border-color: var(--danger, #ef4444); background: rgba(239,68,68,0.15); }

	/* Public Chat Grid */
	.public-chat-admin-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 1.25rem; width: 100%; }
	.pca-field { display: flex; flex-direction: column; gap: 0.4rem; }
	.pca-field label { font-size: 0.82rem; color: var(--text-dim, #94a3b8); font-weight: 500; }
	.pca-field input[type="text"], .pca-field input[type="number"] { width: 100%; padding: 0.6rem 0.8rem; border-radius: var(--radius-sm, 6px); background: rgba(15, 23, 42, 0.6); border: 1px solid var(--glass-border); color: var(--text-main, white); font-size: 0.9rem; }
	.pca-row { display: flex; align-items: center; }
	.full-width { grid-column: 1 / -1; }
	.toggle-label { display: flex; align-items: center; gap: 0.6rem; cursor: pointer; font-size: 0.9rem; color: var(--text-main, white); }
	.toggle-label input[type="checkbox"] { width: 18px; height: 18px; cursor: pointer; accent-color: var(--accent, #6366f1); }

	/* Danger Zone */
	.danger-zone { border: 1px solid rgba(239, 68, 68, 0.2) !important; background: rgba(239, 68, 68, 0.03) !important; }
	.nuke-grid { display: flex; flex-direction: column; gap: 0.8rem; }
	.nuke-card { display: flex; align-items: center; justify-content: space-between; gap: 1rem; padding: 0.8rem 1rem; border-radius: 10px; border: 1px solid var(--glass-border); background: var(--hover-tint); }
	.nuke-info { display: flex; align-items: center; gap: 0.8rem; flex: 1; }
	.nuke-icon { font-size: 1.5rem; }
	.nuke-info strong { font-size: 0.8rem; color: var(--text-main); display: block; }
	.nuke-info p { font-size: 0.65rem; color: var(--text-muted); margin: 0.15rem 0 0; }
	.nuke-confirm { display: flex; align-items: center; gap: 0.5rem; }
	.btn-outline-danger { padding: 0.4rem 0.9rem; font-size: 0.7rem; font-weight: 700; color: var(--danger); background: transparent; border: 1px solid rgba(239, 68, 68, 0.3); border-radius: 8px; cursor: pointer; transition: all 0.2s; white-space: nowrap; }
	.btn-outline-danger:hover { background: rgba(239, 68, 68, 0.1); border-color: var(--danger); }
	.btn-danger-sm { background: rgba(239,68,68,0.2); color: #ef4444; border: 1px solid rgba(239,68,68,0.3); border-radius: 6px; padding: 0.2rem 0.5rem; font-size: 0.65rem; font-weight: 700; cursor: pointer; white-space: nowrap; }
	.btn-danger-sm:hover { background: rgba(239,68,68,0.35); }

	/* Prompt Editor Modal */
	.prompt-modal-overlay { position: fixed; inset: 0; background: rgba(0,0,0,0.6); backdrop-filter: blur(6px); z-index: 9998; display: flex; align-items: center; justify-content: center; padding: 1.5rem; }
	.prompt-modal { width: min(1100px, 100%); max-height: 90vh; display: flex; flex-direction: column; border-radius: 20px; border: 1px solid var(--glass-border); background: var(--bg-secondary); box-shadow: 0 30px 80px rgba(0,0,0,0.5); animation: pmSlideIn 0.25s cubic-bezier(0.16,1,0.3,1); overflow: hidden; }
	@keyframes pmSlideIn { from { opacity: 0; transform: translateY(20px) scale(0.97); } to { opacity: 1; transform: translateY(0) scale(1); } }
	.prompt-modal-header { display: flex; align-items: center; justify-content: space-between; padding: 1rem 1.4rem; background: rgba(139,92,246,0.08); border-bottom: 1px solid rgba(139,92,246,0.2); flex-shrink: 0; }
	.prompt-modal-title-group { display: flex; align-items: center; gap: 0.8rem; }
	.prompt-modal-icon { font-size: 1.6rem; }
	.prompt-modal-title { font-size: 1rem; font-weight: 800; margin: 0; color: var(--text-main); }
	.prompt-modal-subtitle { font-size: 0.7rem; color: var(--text-muted); margin: 0.1rem 0 0; }
	.prompt-modal-close { background: none; border: 1px solid var(--glass-border); color: var(--text-dim); cursor: pointer; font-size: 1rem; width: 32px; height: 32px; border-radius: 8px; display: flex; align-items: center; justify-content: center; transition: all 0.15s; }
	.prompt-modal-close:hover { background: rgba(239,68,68,0.1); border-color: var(--danger); color: var(--danger); }
	.prompt-modal-body { display: grid; grid-template-columns: 1fr 340px; flex: 1; min-height: 0; overflow: hidden; }
	@media (max-width: 800px) { .prompt-modal-body { grid-template-columns: 1fr; } }
	.prompt-modal-editor { display: flex; flex-direction: column; padding: 1rem; border-right: 1px solid var(--glass-border); min-height: 0; }
	.prompt-modal-char-count { font-size: 0.65rem; color: var(--text-muted); font-variant-numeric: tabular-nums; margin-bottom: 0.4rem; text-align: right; font-weight: 600; }
	.prompt-modal-textarea { flex: 1; width: 100%; min-height: 400px; max-height: 100%; background: var(--surface-sunken); border: 1px solid var(--glass-border); border-radius: 10px; padding: 0.8rem; color: var(--text-main); font-size: 0.8rem; font-family: 'Courier New', 'Consolas', monospace; line-height: 1.6; resize: none; transition: border-color 0.2s; }
	.prompt-modal-textarea:focus { outline: none; border-color: rgba(139,92,246,0.5); box-shadow: 0 0 0 3px rgba(139,92,246,0.08); }
	.prompt-modal-guide { overflow-y: auto; padding: 1rem; display: flex; flex-direction: column; gap: 0.8rem; background: rgba(139,92,246,0.02); }
	.pmg-section { background: var(--hover-tint); border: 1px solid var(--glass-border); border-radius: 12px; padding: 0.8rem 0.9rem; }
	.pmg-section-title { font-size: 0.8rem; font-weight: 800; color: var(--text-main); margin: 0 0 0.4rem; }
	.pmg-intro { font-size: 0.7rem; color: var(--text-dim); margin: 0 0 0.6rem; line-height: 1.4; }
	.pmg-blocks { display: flex; flex-direction: column; gap: 0.5rem; }
	.pmg-block { padding: 0.55rem 0.65rem; border-radius: 8px; background: var(--surface-sunken); border: 1px solid var(--glass-border); transition: border-color 0.15s; }
	.pmg-block:hover { border-color: rgba(139,92,246,0.3); }
	.pmg-block-header { display: flex; align-items: center; gap: 0.4rem; margin-bottom: 0.3rem; }
	.pmg-block-icon { font-size: 0.85rem; }
	.pmg-block-tag { font-size: 0.65rem; font-weight: 700; color: #a78bfa; background: rgba(139,92,246,0.1); padding: 0.1rem 0.4rem; border-radius: 4px; font-family: monospace; flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
	.pmg-insert-btn { font-size: 0.6rem; font-weight: 700; padding: 0.15rem 0.45rem; border-radius: 5px; border: 1px solid rgba(139,92,246,0.3); background: rgba(139,92,246,0.08); color: #a78bfa; cursor: pointer; transition: all 0.15s; white-space: nowrap; flex-shrink: 0; }
	.pmg-insert-btn:hover { background: rgba(139,92,246,0.2); border-color: #a78bfa; }
	.pmg-block-desc { font-size: 0.65rem; color: var(--text-muted); margin: 0; line-height: 1.4; }
	.pmg-tips { border-color: rgba(245,158,11,0.2); background: rgba(245,158,11,0.03); }
	.pmg-tips .pmg-section-title { color: #f59e0b; }
	.pmg-tip-list { margin: 0; padding-left: 1.1rem; display: flex; flex-direction: column; gap: 0.3rem; }
	.pmg-tip-list li { font-size: 0.68rem; color: var(--text-dim); line-height: 1.4; }
	.prompt-modal-footer { display: flex; justify-content: flex-end; gap: 0.6rem; padding: 0.8rem 1.2rem; border-top: 1px solid var(--glass-border); background: var(--hover-tint); flex-shrink: 0; }
</style>
