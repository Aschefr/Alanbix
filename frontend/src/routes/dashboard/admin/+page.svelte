<script>
	import { get } from 'svelte/store';
	import { api } from '$lib/api';
	import { onMount, onDestroy } from 'svelte';
	import CreateTournamentWizard from '$lib/components/CreateTournamentWizard.svelte';
	import Modal from '$lib/components/Modal.svelte';
	import EditTournamentModal from '$lib/components/EditTournamentModal.svelte';
	import AddGameModal from '$lib/components/AddGameModal.svelte';
	import { marked } from 'marked';
	import { wsMessageStore } from '$lib/ws';
	import { API_URL } from '$lib/config';
	let wsUnsub = null;

	marked.setOptions({ breaks: true, gfm: true });
	function parseMd(text) { return text ? marked.parse(text) : ''; }

	let games = [];
	let tournaments = [];
	let availableModels = [];
	let activeTab = (typeof localStorage !== 'undefined' && localStorage.getItem('admin_tab')) || 'tournaments';
	if (activeTab === 'games') activeTab = 'tournaments';
	let showAddGameModal = false;
	let EasyMDE = null;
	let editGameEditorInstance = null;

	let settingsSubTab = (typeof localStorage !== 'undefined' && localStorage.getItem('admin_subtab')) || 'general';
	$: if (typeof localStorage !== 'undefined') localStorage.setItem('admin_tab', activeTab);
	$: if (typeof localStorage !== 'undefined') localStorage.setItem('admin_subtab', settingsSubTab);
	$: if (activeTab === 'players') {
		loadPlayers();
	}
	$: if (activeTab === 'conversations') {
		loadAdminConversations();
	}
	$: if (activeTab === 'awards') {
		loadAwardsTab();
	}

	// Player Management
	let allPlayers = [];
	$: existingTeams = Array.from(new Set(allPlayers.map(p => p.team_name?.trim()).filter(Boolean))).sort();
	let editingPlayer = null;
	let editPlayerData = {};
	let resetPwdPlayer = null;
	let resetPwdValue = 'lan2025';
	let overlayMouseDown = false;
	let deleteConfirmPlayerId = null;
	let promoteConfirmPlayerId = null;
	let demoteConfirmPlayerId = null;
	let showCreatePlayer = false;
	let newPlayerData = { username: '', password: 'lan2025', team_name: '' };
	let creatingPlayer = false;
	let generatingPool = false;

	// Team Scoring Mode
	let teamScoringMode = 'weighted';
	let eventName = 'Alanbix LAN';
	let searxngUrl = 'http://searxng:8080';
	let searxngTesting = false;
	let searxngTestResult = null;
	let defaultPts = { pts_winner: 1.5, pts_second: 1.3, pts_third: 1.0, pts_participation: 1.0, pts_per_match: 0.5 };
	let systemPrompt = '';
	let closingPrompt = '';
	let promptPreviewId = null;
	let promptPreviewText = '';
	let promptPreviewTokens = 0;
	let loadingPreview = false;

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

	// Inline Edit (replaces modal)
	let inlineEditId = null;
	
	// Toast Notification System
	let toasts = [];
	let toastId = 0;

	// i18n Config
	import { t, flagMap, customPageTitle } from '$lib/i18nStore';

	$: {
		let baseAdmin = $t('nav_administration') || 'Administration';
		let tabName = baseAdmin;
		if (activeTab === 'tournaments') tabName = `${baseAdmin} - ${$t('admin_tab_tournaments') || 'Tournois & Jeux'}`;
		else if (activeTab === 'players') tabName = `${baseAdmin} - ${$t('admin_tab_players') || 'Gestion Joueurs'}`;
		else if (activeTab === 'settings') tabName = `${baseAdmin} - ${$t('admin_tab_settings') || 'IA & Paramètres'}`;
		else if (activeTab === 'conversations') tabName = `${baseAdmin} - ${$t('admin_tab_conversations') || 'Conversations IA'}`;
		else if (activeTab === 'awards') tabName = `${baseAdmin} - ${$t('admin_tab_awards') || 'Prix & Distinctions'}`;
		customPageTitle.set(tabName);
	}

	// Svelte portal action to avoid transform container clipping (G-49 / scroll fix)
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

	let showModal = false;
	let modalTitle = '';
	let modalMessage = '';
	let modalType = 'info';
	let modalConfirmCallback = null;

	function askConfirm(title, message, type, callback) {
		modalTitle = title;
		modalMessage = message;
		modalType = type;
		modalConfirmCallback = callback;
		showModal = true;
	}

	function toast(message, type = 'info') {
		const id = ++toastId;
		toasts = [...toasts, { id, message, type, leaving: false }];
		setTimeout(() => {
			toasts = toasts.map(t => t.id === id ? { ...t, leaving: true } : t);
			setTimeout(() => { toasts = toasts.filter(t => t.id !== id); }, 400);
		}, 3000);
	}

	// Debounce helper — auto-saves after user stops typing
	let _debounceTimers = {};
	function debounceSave(key, fn, delay = 1200) {
		if (_debounceTimers[key]) clearTimeout(_debounceTimers[key]);
		_debounceTimers[key] = setTimeout(fn, delay);
	}

	let testingConnection = false;
	let deleteConfirmTournamentId = null;
	let deleteConfirmGameId = null;
	let gameToDeleteWithTournaments = null;
	let deleteGameCheckboxConfirmed = false;

	// Edit Tournament State
	let editingTournament = null;
	let editConfig = {};

	function openEditTournament(t) {
		editingTournament = t;
		editConfig = {
			name: t.name,
			game_id: t.game_id,
			status: t.status,
			points_per_win: t.points_per_win || 3,
			use_teams: t.config?.use_teams || false,
			team_size: t.config?.team_size || 1,
			phases: t.config?.phases || 'single',
			group_size: t.config?.group_size || 4,
			advancers_count: t.config?.advancers_count || 2,
			bracket_type: t.config?.bracket_type || 'single_elim',
			pts_winner: t.config?.pts_winner ?? 10,
			pts_second: t.config?.pts_second ?? 6,
			pts_third: t.config?.pts_third ?? 4,
			pts_participation: t.config?.pts_participation ?? 1,
			pts_per_match: t.config?.pts_per_match ?? t.config?.pts_per_goal ?? 1.0,
			lower_score_is_better: t.config?.lower_score_is_better || false,
			boolean_mode: t.config?.boolean_mode || false,
			allow_draws: t.config?.allow_draws || false,
			meet_twice: t.config?.meet_twice || false,
			ffa_group_size: t.config?.ffa_group_size || 4,
			ffa_advancers: t.config?.ffa_advancers || 2
		};
	}

	async function updateTournament() {
		try {
			await api.put(`/tournaments/${editingTournament.id}`, {
				name: editConfig.name,
				status: editConfig.status,
				points_per_win: editConfig.points_per_win,
				config: {
					...editingTournament.config,
					use_teams: editConfig.use_teams,
					team_size: editConfig.team_size,
					phases: editConfig.phases,
					group_size: editConfig.group_size,
					advancers_count: editConfig.advancers_count,
					bracket_type: editConfig.bracket_type,
					pts_winner: editConfig.pts_winner,
					pts_second: editConfig.pts_second,
					pts_third: editConfig.pts_third,
					pts_participation: editConfig.pts_participation,
					pts_per_match: editConfig.pts_per_match,
					lower_score_is_better: editConfig.lower_score_is_better,
					boolean_mode: editConfig.boolean_mode,
					allow_draws: editConfig.allow_draws,
					meet_twice: editConfig.meet_twice,
					ffa_group_size: editConfig.ffa_group_size,
					ffa_advancers: editConfig.ffa_advancers
				}
			});
			toast(get(t)('tourneys_toast_updated'), 'success');
			editingTournament = null;
			loadData();
		} catch (e) { toast(e.message, 'error'); }
	}

	// New Game State
	// (handled via AddGameModal)

	// IA Settings
	let iaConfig = { 
		ollama_host: '', model: '', rag_enabled: true, network_tools_enabled: true,
		auto_moderation_enabled: true,
		temperature: 0.7, context_window: 4096,
		ollama_instances: [], embedding_model: ''
	};
	let newDocContent = '';
	let instanceStatuses = [];
	let knowledgeDocs = [];
	let editingDocId = null;
	let editDocContent = '';
	let editDocLoading = false;
	let editDocSaving = false;
	let uploadingDoc = false;

	// AI Queue admin state (G-52)
	let iaQueueData = { pending: [], active: [], queue_size: 0, active_count: 0, avg_duration: 15 };
	let iaQueueInterval = null;

	let authorized = false;

	onMount(async () => {
		try {
			const mod = await import('easymde');
			EasyMDE = mod.default;
		} catch (e) {
			console.error("Failed to load EasyMDE", e);
		}

		// --- Admin Guard: block non-admin access ---
		try {
			const me = await api.get('/me');
			if (!me.is_admin) {
				window.location.href = '/dashboard';
				return;
			}
			authorized = true;
		} catch {
			window.location.href = '/';
			return;
		}

		loadData();
		// Listen for user messages during admin override to auto-refresh conv view
		wsUnsub = wsMessageStore.subscribe(msg => {
			if (!msg) return;
			if (msg.type === 'user_message_during_override') {
				if (adminActiveConvId === msg.conversation_id) {
					// Admin is watching this conv: refresh messages directly
					selectAdminConv(adminActiveConvId);
				} else {
					// Mark conversation as having a new message in real-time
					const existing = adminConversations.find(c => c.id === msg.conversation_id);
					if (existing) {
						adminConversations = adminConversations.map(c =>
							c.id === msg.conversation_id
								? { ...c, has_new_messages: true, unread_count: (c.unread_count || 0) + 1 }
								: c
						);
					} else {
						loadAdminConversations();
					}
				}
			}
			if (msg.type === 'chat_updated') {
				// msg.role: 'user' = player message (unread for admin), 'bot' = AI response (not unread)
				if (adminActiveConvId && adminActiveConvId === msg.conversation_id) {
					// Admin is watching this conversation — refresh messages view without marking as unread
					// selectAdminConv preserves read state (clears unread before loading)
					selectAdminConv(adminActiveConvId);
				} else {
					// Different conversation from what admin is currently watching
					if (msg.role === 'user') {
						// Only user messages count as unread for the admin
						const existing = adminConversations.find(c => c.id === msg.conversation_id);
						if (existing) {
							adminConversations = adminConversations.map(c =>
								c.id === msg.conversation_id
									? { ...c, has_new_messages: true, unread_count: (c.unread_count || 0) + 1 }
									: c
							);
						} else {
							// Unknown conversation (new one) — do a full reload
							loadAdminConversations();
						}
					}
					// For bot responses to other conversations: no unread badge update needed
				}
			}
			if (msg.type === 'users_updated') {
				loadPlayers();
			}
			if (msg.type === 'games_updated') {
				api.get('/tournaments/games').then(res => { games = res; }).catch(() => {});
			}
			if (msg.type === 'tournament_created' || msg.type === 'tournament_updated' || msg.type === 'tournament_deleted' || msg.type === 'tournament_started' || msg.type === 'tournament_closed' || msg.type === 'tournament_reopened') {
				api.get('/tournaments').then(res => { tournaments = res; }).catch(() => {});
			}
			if (msg.type === 'knowledge_updated') {
				loadKnowledge();
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

	let defaultLang = 'fr';
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

	async function loadData() {
		try { games = await api.get('/tournaments/games'); } catch {}
		try { tournaments = await api.get('/tournaments'); } catch {}
		try {
			iaConfig = await api.get('/ia/config');
			if (!iaConfig.ollama_instances) iaConfig.ollama_instances = [];
			fetchModels();
			loadInstanceStatuses();
		} catch {}
		loadKnowledge();
		loadQueueAdmin();
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
			config = { ...config, pts_winner: defaultPts.pts_winner, pts_second: defaultPts.pts_second, pts_third: defaultPts.pts_third, pts_participation: defaultPts.pts_participation, pts_per_match: defaultPts.pts_per_match };
		} catch {}
		try {
			const sxCfg = await api.get('/admin/config/searxng_url');
			searxngUrl = sxCfg?.value || 'http://searxng:8080';
		} catch {}
		await loadPrompts();
		loadAdminConversations();
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

	async function previewAiPrompt(tournamentId) {
		loadingPreview = true;
		try {
			const res = await api.get(`/tournaments/${tournamentId}/ai-prompt-preview`);
			promptPreviewId = tournamentId;
			promptPreviewText = res.prompt;
			promptPreviewTokens = res.estimated_tokens;
		} catch (e) { toast(e.message || get(t)('admin_toast_preview_error'), 'error'); }
		loadingPreview = false;
	}

	async function retryNotifications(tournamentId) {
		try {
			await api.post(`/tournaments/${tournamentId}/retry-notifications`);
			toast(get(t)('admin_toast_regen_ai_started'), 'success');
		} catch (e) { toast(e.message || 'Erreur retry', 'error'); }
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

	async function fetchModels() {
		const res = await api.get('/ia/models');
		availableModels = res.models || [];
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

	// AI Queue admin polling (G-52)
	async function loadQueueAdmin() {
		try { iaQueueData = await api.get('/ia/queue/admin'); } catch { iaQueueData = { pending: [], active: [], queue_size: 0, active_count: 0, avg_duration: 15 }; }
		// Poll faster when queue has entries
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
		// Re-number priorities
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



	// Nuke state
	let nukeConfirm = { tournaments: false, players: false, games: false, images: false, notifications: false, awards: false };
	let nuking = { tournaments: false, players: false, games: false, images: false, notifications: false, awards: false };

	async function nukeAwards() {
		nuking.awards = true;
		try {
			const res = await api.delete('/admin/nuke/awards');
			toast(`${res.deleted_awards} prix supprimé(s)`, 'success');
			if (activeTab === 'awards') await loadAwardsTab();
		} catch (e) { toast(e.message, 'error'); }
		nuking.awards = false;
		nukeConfirm.awards = false;
	}

	async function nukeTournaments() {
		nuking.tournaments = true;
		try {
			const res = await api.delete('/admin/nuke/tournaments');
			toast(`${res.deleted_tournaments} tournoi(s) supprimé(s), scores réinitialisés`, 'success');
			loadData();
		} catch (e) { toast(e.message, 'error'); }
		nuking.tournaments = false;
		nukeConfirm.tournaments = false;
	}

	async function nukePlayers() {
		nuking.players = true;
		try {
			const res = await api.delete('/admin/nuke/players');
			toast(`${res.deleted_players} joueur(s) supprimé(s)`, 'success');
			loadPlayers();
		} catch (e) { toast(e.message, 'error'); }
		nuking.players = false;
		nukeConfirm.players = false;
	}

	async function nukeGames() {
		nuking.games = true;
		try {
			const res = await api.delete('/admin/nuke/games');
			toast(`${res.deleted_games} jeu(x) et tous les tournois supprimés`, 'success');
			loadData();
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





	async function deleteTournament(id) {
		await api.delete(`/tournaments/${id}`);
		deleteConfirmTournamentId = null;
		loadData();
	}

	async function deleteGame(id, force = false) {
		try {
			await api.delete(`/tournaments/games/${id}${force ? '?force=true' : ''}`);
			deleteConfirmGameId = null;
			gameToDeleteWithTournaments = null;
			deleteGameCheckboxConfirmed = false;
			loadData();
			toast(get(t)('admin_toast_game_deleted'), 'success');
		} catch (e) {
			if (e.message && e.message.includes('confirmer la suppression')) {
				const g = games.find(game => game.id === id);
				const freshTournaments = await api.get('/tournaments');
				const affected = freshTournaments.filter(t => t.game_id && Number(t.game_id) === Number(id));
				gameToDeleteWithTournaments = { game: g, tournaments: affected };
				deleteGameCheckboxConfirmed = false;
			} else {
				toast(e.message || 'Erreur de suppression', 'error');
			}
		}
	}

	function attemptDeleteGame(g) {
		// Rely on the backend 409 Conflict to trigger the modal.
		deleteGame(g.id);
	}

	// Game image modes: 'url' | 'search' | 'upload'
	let gameImageMode = 'search';
	let searchQuery = '';
	let searchResults = [];
	let searching = false;
	let editingGame = null;
	let editGameData = {};

	let searxngNotConfigured = false;

	async function searchCovers() {
		if (!searchQuery.trim()) return;
		searching = true;
		searxngNotConfigured = false;
		try {
			const res = await api.get(`/tournaments/games/search-covers?q=${encodeURIComponent(searchQuery)}`);
			searchResults = res.results || [];
			searxngNotConfigured = !!res.not_configured;
		} catch { searchResults = []; }
		searching = false;
	}

	function pickCover(url) {
		if (editingGame) {
			editGameData.image_url = url;
		} else {
			newGame.image_url = url;
		}
		searchResults = [];
	}

	async function handleFileUpload(e) {
		const file = e.target.files?.[0];
		if (!file) return;
		const formData = new FormData();
		formData.append('file', file);
		try {
			const token = localStorage.getItem('alanbix_token');
			const res = await fetch(`${API_URL}/tournaments/games/upload-image`, {
				method: 'POST', body: formData,
				headers: { 'Authorization': `Bearer ${token}` }
			});
			const data = await res.json();
			const url = `${API_URL}${data.url}`;
			editGameData.image_url = url;
			toast(get(t)('admin_toast_image_uploaded'), 'success');
		} catch (err) { toast(get(t)('admin_toast_upload_error') + err.message, 'error'); }
	}

	function openEditGame(g) {
		editingGame = g;
		editGameData = { name: g.name, rules: g.rules || '', image_url: g.image_url || '' };
		searchResults = [];
		gameImageMode = 'url';
	}

	async function saveEditGame() {
		try {
			await api.put(`/tournaments/games/${editingGame.id}`, editGameData);
			toast(get(t)('admin_toast_game_updated'), 'success');
			editingGame = null;
			loadData();
		} catch (e) { toast(e.message, 'error'); }
	}

	async function saveIAConfig() {
		try {
			await api.post('/ia/config', iaConfig);
			toast(get(t)('admin_toast_ai_saved'), 'success');
		} catch (e) { toast(e.message || get(t)('admin_toast_ai_save_error'), 'error'); }
	}

	// --- Player Management ---
	async function loadPlayers() {
		try { allPlayers = await api.get('/admin/users'); } catch (e) { toast(get(t)('admin_toast_players_load_error'), 'error'); }
	}

	async function savePlayer() {
		try {
			await api.put(`/admin/users/${editingPlayer.id}`, editPlayerData);
			toast(get(t)('admin_toast_player_updated', { name: editPlayerData.username }), 'success');
			editingPlayer = null;
			await loadPlayers();
		} catch (e) { toast(e.message, 'error'); }
	}

	function adminDeleteAvatar(playerId) {
		askConfirm(
			get(t)('admin_confirm_delete_avatar_title') || 'Supprimer l\'avatar',
			get(t)('admin_confirm_delete_avatar') || 'Voulez-vous vraiment supprimer cet avatar ?',
			'error',
			async () => {
				try {
					await api.delete(`/admin/users/${playerId}/avatar`);
					toast(get(t)('admin_toast_avatar_deleted'), 'success');
					if (editingPlayer && editingPlayer.id === playerId) {
						editingPlayer.avatar_url = null;
						editingPlayer = { ...editingPlayer };
					}
					await loadPlayers();
				} catch (e) { toast("Erreur: " + e.message, "error"); }
			}
		);
	}

	async function resetPassword() {
		try {
			await api.post(`/admin/users/${resetPwdPlayer.id}/reset-password`, { password: resetPwdValue });
			toast(get(t)('admin_toast_pwd_reset', { name: resetPwdPlayer.username, pwd: resetPwdValue }), 'success');
			resetPwdPlayer = null;
		} catch (e) { toast(e.message, 'error'); }
	}

	async function deletePlayer(id) {
		try {
			await api.delete(`/admin/users/${id}`);
			toast(get(t)('admin_toast_player_deleted'), 'success');
			deleteConfirmPlayerId = null;
			await loadPlayers();
		} catch (e) { toast(e.message, 'error'); }
	}

	async function createPlayer() {
		if (!newPlayerData.username.trim() || !newPlayerData.password.trim()) return;
		creatingPlayer = true;
		try {
			await api.post('/admin/users/create', newPlayerData);
			toast(get(t)('admin_toast_player_created', { name: newPlayerData.username }), 'success');
			newPlayerData = { username: '', password: 'lan2025', team_name: '' };
			showCreatePlayer = false;
			await loadPlayers();
		} catch (e) { toast(e.message, 'error'); }
		creatingPlayer = false;
	}

	async function generateTestPool() {
		generatingPool = true;
		try {
			const res = await api.post('/admin/users/generate-test-pool');
			toast(get(t)('admin_toast_test_players_generated', { count: res.created_count }), 'success');
			await loadPlayers();
		} catch (e) { toast(e.message, 'error'); }
		generatingPool = false;
	}

	async function toggleAdmin(player) {
		try {
			await api.put(`/admin/users/${player.id}`, { is_admin: !player.is_admin });
			toast(!player.is_admin ? get(t)('admin_toast_promoted', { name: player.username }) : get(t)('admin_toast_demoted', { name: player.username }), 'success');
			await loadPlayers();
		} catch (e) { toast(e.message, 'error'); }
	}

	async function toggleIaBlocked(player) {
		try {
			const newVal = !player.ia_blocked;
			await api.put(`/admin/users/${player.id}`, { ia_blocked: newVal });
			toast(newVal ? get(t)('admin_toast_ai_blocked', { name: player.username }) : get(t)('admin_toast_ai_unblocked', { name: player.username }), 'success');
			await loadPlayers();
		} catch (e) { toast(e.message, 'error'); }
	}

	// --- Admin Conversation Monitoring ---
	let adminConversations = [];
	$: adminUnreadConvsCount = adminConversations.reduce((sum, c) => sum + (c.unread_count || 0), 0);
	let adminActiveConvId = null;
	let adminConvMessages = [];
	let adminConvInfo = null;
	let adminInterveneText = '';
	let adminChatContainer = null;
	let adminPendingImage = null;
	let adminImagePreview = '';
	let adminFileInput = null;

	function handleAdminFileSelect(e) {
		const file = e.target.files?.[0];
		if (!file) return;
		if (file.size > 8 * 1024 * 1024) { toast('Image trop volumineuse (max 8 Mo)', 'error'); return; }
		adminPendingImage = file;
		const reader = new FileReader();
		reader.onload = (ev) => { adminImagePreview = ev.target.result; };
		reader.readAsDataURL(file);
		if (adminFileInput) adminFileInput.value = '';
	}

	function handleAdminPaste(e) {
		const items = e.clipboardData?.items;
		if (!items) return;
		for (const item of items) {
			if (item.type.startsWith('image/')) {
				e.preventDefault();
				const file = item.getAsFile();
				if (file.size > 8 * 1024 * 1024) { toast('Image trop volumineuse (max 8 Mo)', 'error'); return; }
				adminPendingImage = file;
				const reader = new FileReader();
				reader.onload = (ev) => { adminImagePreview = ev.target.result; };
				reader.readAsDataURL(file);
				break;
			}
		}
	}

	import { tick } from 'svelte';
	async function adminScrollToBottom() {
		await tick();
		if (adminChatContainer) adminChatContainer.scrollTop = adminChatContainer.scrollHeight;
	}

	async function loadAdminConversations() {
		try {
			const fresh = await api.get('/ia/admin/conversations');
			// Preserve the read state of the currently active conversation
			// to avoid the server re-introducing the unread badge immediately after click.
			if (adminActiveConvId) {
				adminConversations = fresh.map(c =>
					c.id === adminActiveConvId ? { ...c, has_new_messages: false, unread_count: 0 } : c
				);
			} else {
				adminConversations = fresh;
			}
		} catch (e) { toast('Erreur chargement conversations', 'error'); }
	}

	async function selectAdminConv(id) {
		adminActiveConvId = id;
		// Immediately clear unread badge for instant visual feedback
		adminConversations = adminConversations.map(c =>
			c.id === id ? { ...c, has_new_messages: false, unread_count: 0 } : c
		);
		try {
			const res = await api.get(`/ia/admin/conversations/${id}/messages`);
			adminConvMessages = res.messages;
			adminConvInfo = res.conversation;
			adminScrollToBottom();
			// Refresh list but keep the active conv as read
			await loadAdminConversations();
		} catch (e) { toast(e.message, 'error'); }
	}

	async function adminSendIntervention() {
		if ((!adminInterveneText.trim() && !adminPendingImage) || !adminActiveConvId) return;
		try {
			let imagePath = null;
			if (adminPendingImage) {
				const fd = new FormData();
				fd.append('conversation_id', adminActiveConvId);
				fd.append('file', adminPendingImage);
				const uploadRes = await api.upload('/ia/upload-image', fd);
				imagePath = uploadRes.image_path;
				adminPendingImage = null;
				adminImagePreview = '';
			}
			await api.post(`/ia/admin/conversations/${adminActiveConvId}/intervene`, { content: adminInterveneText || '(image)', image_path: imagePath });
			adminInterveneText = '';
			toast('Message admin envoyé', 'success');
			await selectAdminConv(adminActiveConvId);
		} catch (e) { toast(e.message, 'error'); }
	}

	async function toggleAdminOverride(convId, value) {
		try {
			await api.put(`/ia/admin/conversations/${convId}/override`, { admin_override: value });
			toast(value ? 'Admin prend la main' : 'IA reprend la main', 'success');
			if (adminConvInfo) adminConvInfo.admin_override = value;
			await loadAdminConversations();
		} catch (e) { toast(e.message, 'error'); }
	}

	// --- Awards & Prizes ---
	let awardsList = [];
	let awardsLoading = false;

	function getAwardEmoji(key) {
		const map = {
			premier: '🏆',
			team: '🛡️',
			bourreau: '⚔️',
			coop: '🤝',
			loup: '🐺',
			participate: '🕊️',
			marathon: '🏃',
			gachette: '🎯',
			passoire: '🥅',
			bye: '🍀',
			suisse: '🇨🇭',
			lb: '🩹'
		};
		return map[key] || '🎁';
	}

	async function loadAwardsTab() {
		awardsLoading = true;
		try {
			await loadPlayers();
			awardsList = await api.get('/admin/awards');
		} catch (e) {
			toast(e.message || "Erreur lors du chargement des prix", 'error');
		} finally {
			awardsLoading = false;
		}
	}

	async function saveAwardText(key, title, description) {
		if (!title.trim()) { toast("Le titre ne peut pas être vide", "error"); return; }
		try {
			await api.put(`/admin/awards/${key}`, {
				title: title.trim(),
				description: description.trim()
			});
			toast("Prix enregistré avec succès !", 'success');
			await loadAwardsTab();
		} catch (e) {
			toast(e.message || "Erreur lors de l'enregistrement du prix", 'error');
		}
	}

	async function restoreDefaultText(key) {
		try {
			await api.delete(`/admin/awards/${key}/text`);
			toast("Texte par défaut restauré !", 'success');
			await loadAwardsTab();
		} catch (e) {
			toast(e.message || "Erreur lors de la restauration", 'error');
		}
	}

	async function triggerSync() {
		awardsLoading = true;
		try {
			awardsList = await api.get('/admin/awards');
			toast("Distinctions recalculées et synchronisées !", 'success');
		} catch (e) {
			toast(e.message || "Erreur de synchronisation", 'error');
		} finally {
			awardsLoading = false;
		}
	}

	async function sendAwardsNotifications() {
		awardsLoading = true;
		try {
			const res = await api.post('/admin/awards/notify');
			toast(`Notifications envoyées à ${res.notified_players_count} joueur(s) !`, 'success');
		} catch (e) {
			toast(e.message || "Erreur lors de l'envoi des notifications", 'error');
		} finally {
			awardsLoading = false;
		}
	}

	function setupEditGameEditor(node, currentRules) {
		if (!EasyMDE) return;
		
		editGameEditorInstance = new EasyMDE({
			element: node,
			initialValue: currentRules || '',
			spellChecker: false,
			autofocus: false,
			status: false,
			minHeight: '120px',
			maxHeight: '250px',
			toolbar: [
				'bold', 'italic', 'heading', '|', 
				'quote', 'unordered-list', 'ordered-list', '|', 
				'preview', 'side-by-side', 'fullscreen', '|', 
				'guide'
			]
		});
		
		editGameEditorInstance.codemirror.on('change', () => {
			editGameData.rules = editGameEditorInstance.value();
		});

		return {
			update(newRules) {
				if (editGameEditorInstance && editGameEditorInstance.value() !== newRules) {
					editGameEditorInstance.value(newRules || '');
				}
			},
			destroy() {
				if (editGameEditorInstance) {
					editGameEditorInstance.toTextArea();
					editGameEditorInstance = null;
				}
			}
		};
	}
</script>

<svelte:head>
	<link rel="stylesheet" href="https://unpkg.com/easymde/dist/easymde.min.css" />
</svelte:head>

{#if authorized}
<div class="admin-view">
	<header class="flex-row justify-between items-center">
		<h1 class="title-premium">{$t('admin_title') || 'Administration Centrale'}</h1>
		<div class="tabs glass">
			<button class={activeTab === 'tournaments' ? 'active' : ''} on:click={() => activeTab = 'tournaments'}>{$t('admin_tab_tournaments') || 'Tournois'}</button>
			<button class={activeTab === 'players' ? 'active' : ''} on:click={() => { activeTab = 'players'; loadPlayers(); }}>{$t('admin_tab_players') || 'Gestion Joueurs'}</button>
			<button class={activeTab === 'settings' ? 'active' : ''} on:click={() => activeTab = 'settings'}>{$t('admin_tab_settings') || 'IA & Paramètres'}</button>
			<button class={activeTab === 'conversations' ? 'active' : ''} on:click={() => { activeTab = 'conversations'; loadAdminConversations(); }}>
				{$t('admin_tab_chats')}
				{#if adminUnreadConvsCount > 0}
					<span class="tab-unread-badge" style="background:#22c55e;color:white;padding:0.1rem 0.4rem;border-radius:10px;font-size:0.65rem;font-weight:bold;margin-left:0.4rem">{adminUnreadConvsCount}</span>
				{/if}
			</button>
			<button class={activeTab === 'awards' ? 'active' : ''} on:click={() => activeTab = 'awards'}>🏆 {$t('admin_tab_awards') || 'Prix & Distinctions'}</button>
			<button on:click={() => window.location.href = '/dashboard/admin/languages'}>🌐 {$t('admin_tab_languages')}</button>
		</div>
	</header>

	<div class="tab-content animate-in">
		{#if activeTab === 'tournaments'}
			<div class="admin-grid">
				<section class="wizard glass">
					<div class="list-header">
						<div class="flex-row items-center gap-3">
							<div class="list-icon">✨</div>
							<div>
								<h2 class="text-accent" style="margin:0">{$t("admin_tourneys_wizard")}</h2>
								<span class="text-xs text-dim">{$t("admin_tourneys_wizard_subtitle")}</span>
							</div>
						</div>
					</div>
					<CreateTournamentWizard 
						{games} 
						onSuccess={() => {
							toast(get(t)('tourneys_toast_joined'), 'success');
							loadData();
						}} 
						onGameCreated={async (newGameId) => {
							await loadData();
						}}
						on:toast={(e) => toast(e.detail.message, e.detail.type)}
					/>
				</section>

				<div class="flex-col gap-6" style="display:flex; flex-direction:column; gap:1.5rem;">
					<section class="list glass">
					<div class="list-header">
						<div class="flex-row items-center gap-3">
							<div class="list-icon">🏆</div>
							<div>
								<h2 style="margin:0">{$t("admin_tourneys_mgmt")}</h2>
								<span class="text-xs text-dim">{$t("admin_tourneys_mgmt_subtitle")}</span>
							</div>
						</div>
						<span class="badge-count">{tournaments.length} {$t("admin_tourneys_active", { plural: tournaments.length > 1 ? "s" : "" })}</span>
					</div>
					
					<div class="item-list">
						{#each tournaments as tourney}
							<div class="admin-item-card glass-hover {inlineEditId === tourney.id ? 'editing-expanded' : ''}">
								<div class="card-top-row">
								<div class="game-mini-thumb" style="background-image: url({games.find(g => g.id === tourney.game_id)?.image_url})">
									{#if !games.find(g => g.id === tourney.game_id)?.image_url}
										<span class="thumb-placeholder">🎮</span>
									{/if}
								</div>
								<div class="item-info">
									<div class="flex-row items-center gap-2">
										<span class="item-name">{tourney.name}</span>
										<span class="status-pill-sm {tourney.status.toLowerCase()}">{tourney.status === 'OPEN' ? $t('admin_tourneys_status_pill_open') : tourney.status === 'RUNNING' ? $t('admin_tourneys_status_pill_running') : tourney.status === 'CLOSED' ? $t('admin_tourneys_status_pill_closed') : $t('admin_tourneys_status_pill_done')}</span>
									</div>
									<div class="item-meta">
										{games.find(g => g.id === tourney.game_id)?.name || '—'} • {tourney.participants?.length || 0} Joueur{(tourney.participants?.length || 0) > 1 ? 's' : ''} • 🥇{tourney.config?.pts_winner ?? 10}/🥈{tourney.config?.pts_second ?? 6}/🥉{tourney.config?.pts_third ?? 4} 👤{tourney.config?.pts_participation ?? 1}/m ⚡{tourney.config?.pts_per_match ?? tourney.config?.pts_per_goal ?? 1.0}
									</div>
								</div>
								<div class="item-actions">
									{#if tourney.status === 'CLOSED'}
										<button class="btn-icon-edit" on:click={() => previewAiPrompt(tourney.id)} title="{$t('admin_tourneys_view_ai_prompt')}" disabled={loadingPreview}>
											{loadingPreview && promptPreviewId === tourney.id ? '⏳' : '👁️'}
										</button>
										<button class="btn-icon-edit" on:click={() => retryNotifications(tourney.id)} title="{$t('admin_tourneys_regen_ai_msgs')}">
											🔄
										</button>
									{/if}
									{#if deleteConfirmTournamentId === tourney.id}
										<div class="confirm-delete-row">
											<span class="text-xs text-danger font-bold">{$t("admin_tourneys_confirm_delete")}</span>
											<button class="btn-danger-sm" on:click={() => deleteTournament(tourney.id)}>{$t("admin_tourneys_confirm_yes")}</button>
											<button class="btn-secondary text-xs p-1" on:click={() => deleteConfirmTournamentId = null}>{$t('admin_tourneys_confirm_no')}</button>
										</div>
									{:else}
										<button class="btn-icon-edit" on:click={() => openEditTournament(tourney)} title="{$t('admin_tourneys_tooltip_edit')}">
											<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M11 4H4a2 2 0 00-2 2v14a2 2 0 002 2h14a2 2 0 002-2v-7"/><path d="M18.5 2.5a2.121 2.121 0 013 3L12 15l-4 1 1-4 9.5-9.5z"/></svg>
										</button>
										<button class="btn-icon-danger" on:click={() => deleteConfirmTournamentId = tourney.id} title="{$t('admin_tourneys_tooltip_delete')}">
											<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M3 6h18M19 6v14a2 2 0 01-2 2H7a2 2 0 01-2-2V6m3 0V4a2 2 0 012-2h4a2 2 0 012 2v2M10 11v6M14 11v6"/></svg>
										</button>
									{/if}
								</div>
								</div>

								{#if promptPreviewId === tourney.id && promptPreviewText}
									<div class="prompt-preview-panel">
										<div class="prompt-preview-header">
											<span>👁️ Prompt IA envoyé à Ollama</span>
											<div style="display:flex;align-items:center;gap:0.5rem">
												<span class="prompt-token-badge">~{promptPreviewTokens} tokens</span>
												<button class="close-btn" on:click={() => { promptPreviewId = null; promptPreviewText = ''; }}>✕</button>
											</div>
										</div>
										<textarea class="prompt-preview-textarea" readonly>{promptPreviewText}</textarea>
									</div>
								{/if}

							</div>
						{:else}
							<div class="empty-list">
								<span class="empty-icon">🏟️</span>
								<p>{$t('admin_tourneys_no_created')}</p>
								<span class="text-xs text-dim">{$t("admin_tourneys_wizard_use_wizard")}</span>
							</div>
						{/each}
					</div>
				</section>

				<section class="list glass">
					<div class="list-header">
						<div class="flex-row items-center gap-3">
							<div class="list-icon">🎮</div>
							<div>
								<h2 style="margin:0">{$t("admin_games_library")}</h2>
								<span class="text-xs text-dim">{games.length > 1 ? $t("admin_games_library_count_many", { count: games.length }) : $t("admin_games_library_count_1", { count: games.length })}</span>
							</div>
						</div>
						<button class="btn-primary btn-sm" on:click={() => showAddGameModal = true}>{$t("admin_games_add") || 'Ajouter un Jeu'}</button>
					</div>
					<div class="game-gallery">
						{#each games as g}
							<div class="game-card glass">
								<div class="game-thumb" style="background-image: url({g.image_url})">
									{#if !g.image_url}<span class="thumb-placeholder">🎮</span>{/if}
									<div class="game-card-actions">
										<button class="game-action-btn edit" on:click={() => openEditGame(g)} title="{$t('admin_tourneys_tooltip_edit')}">✏️</button>
										{#if deleteConfirmGameId === g.id}
											<button class="game-action-btn confirm" on:click={() => attemptDeleteGame(g)}>✓</button>
											<button class="game-action-btn cancel" on:click={() => deleteConfirmGameId = null}>✕</button>
										{:else}
											<button class="game-action-btn delete" on:click={() => deleteConfirmGameId = g.id} title="{$t('admin_tourneys_tooltip_delete')}">🗑</button>
										{/if}
									</div>
								</div>
								<div class="game-info">
									<div class="name">{g.name}</div>
								</div>
							</div>
						{:else}
							<div class="game-empty"><span class="text-dim text-xs">Aucun jeu configuré</span></div>
						{/each}
					</div>
				</section>
			</div>

		</div>

		<!-- Delete Game Double Confirmation Modal -->
		{#if gameToDeleteWithTournaments}
			<div class="edit-overlay" use:portal
				on:mousedown={(e) => { if (e.target === e.currentTarget) overlayMouseDown = true; }} 
				on:mouseup={(e) => { if (overlayMouseDown && e.target === e.currentTarget) gameToDeleteWithTournaments = null; overlayMouseDown = false; }}>
				<div class="edit-modal glass" on:click|stopPropagation style="max-width: 480px">
					<header class="edit-modal-header danger-zone" style="border-bottom: 1px solid rgba(239, 68, 68, 0.25);">
						<h3>⚠️ Suppression Critique</h3>
						<button class="close-btn" on:click={() => gameToDeleteWithTournaments = null}>✕</button>
					</header>
					<div class="edit-modal-body">
						<div class="flex-col gap-3">
							<p class="text-sm">
								Vous êtes sur le point de supprimer le jeu <strong class="text-accent">{gameToDeleteWithTournaments.game.name}</strong> de la bibliothèque.
							</p>
							
							<div class="danger-warning-box">
								<strong class="warn-title">⚠️ EFFET EN CASCADE DÉTECTÉ</strong>
								<p class="text-xs text-dim" style="margin: 0.2rem 0 0.6rem;">
									Ce jeu est actuellement utilisé par <strong>{gameToDeleteWithTournaments.tournaments.length}</strong> tournoi(s) :
								</p>
								<ul>
									{#each gameToDeleteWithTournaments.tournaments as t}
										<li>
											<strong>{t.name}</strong>
											<span class="status-badge {t.status.toLowerCase()}">
												{t.status === 'OPEN' ? 'Ouvert' : t.status === 'RUNNING' ? 'En cours' : t.status === 'DONE' ? 'Terminé' : 'Clôturé'}
											</span>
										</li>
									{/each}
								</ul>
								<p class="warning-text text-xs">
									La suppression de ce jeu entraînera la <strong>destruction définitive et irréversible</strong> de ces tournois, incluant :
								</p>
								<div class="consequence-badges">
									<span class="c-badge">👥 Équipes</span>
									<span class="c-badge">👤 Participants</span>
									<span class="c-badge">📊 Scores & Brackets</span>
									<span class="c-badge">⚖️ Conflits</span>
								</div>
							</div>

							<label class="confirm-checkbox-label">
								<input type="checkbox" bind:checked={deleteGameCheckboxConfirmed} />
								<span>{$t('admin_games_nuke_confirm_checkbox')}</span>
							</label>
						</div>
					</div>
					<footer class="edit-modal-footer">
						<button class="btn-secondary" on:click={() => gameToDeleteWithTournaments = null}>{$t('admin_settings_cancel')}</button>
						<button class="btn-danger-full" on:click={() => deleteGame(gameToDeleteWithTournaments.game.id, true)} disabled={!deleteGameCheckboxConfirmed}>{$t('admin_games_nuke_btn_nuke')}</button>
					</footer>
				</div>
			</div>
		{/if}

		<!-- Edit Game Modal -->
		{#if editingGame}
			<div class="edit-overlay" use:portal
				on:mousedown={(e) => { if (e.target === e.currentTarget) overlayMouseDown = true; }} 
				on:mouseup={(e) => { if (overlayMouseDown && e.target === e.currentTarget) editingGame = null; overlayMouseDown = false; }}>
				<div class="edit-modal glass" on:click|stopPropagation>
					<header class="edit-modal-header">
						<h3>✏️ Éditer — {editingGame.name}</h3>
						<button class="close-btn" on:click={() => editingGame = null}>✕</button>
					</header>
					<div class="edit-modal-body">
						<div class="flex-col gap-4">
							<div class="edit-field full-width">
								<label>{$t('admin_tourneys_edit_name')}</label>
								<input type="text" bind:value={editGameData.name} />
							</div>
							<div class="edit-field full-width">
								<label>Image</label>
								<div class="img-mode-tabs">
									<button class="img-tab {gameImageMode === 'search' ? 'active' : ''}" on:click={() => gameImageMode = 'search'}>{$t('admin_games_btn_search')}</button>
									<button class="img-tab {gameImageMode === 'url' ? 'active' : ''}" on:click={() => gameImageMode = 'url'}>{$t('admin_games_btn_url')}</button>
									<button class="img-tab {gameImageMode === 'upload' ? 'active' : ''}" on:click={() => gameImageMode = 'upload'}>{$t('admin_games_btn_file')}</button>
								</div>
								{#if gameImageMode === 'search'}
									<div class="search-bar mt-2">
										<input type="text" bind:value={searchQuery} placeholder="Rechercher..." on:keydown={(e) => e.key === 'Enter' && searchCovers()} />
										<button class="btn-primary btn-sm" on:click={searchCovers} disabled={searching}>{searching ? '...' : '🔍'}</button>
									</div>
									{#if searxngNotConfigured}
										<div class="mt-2" style="font-size: 0.75rem; color: #f59e0b; display: flex; align-items: center; gap: 0.4rem;">
											<span>⚠️</span>
											<span>{$t('admin_games_searxng_not_configured')}</span>
										</div>
									{/if}
									{#if searchResults.length > 0}
										<div class="cover-grid mt-2">
											{#each searchResults as r}
												<button class="cover-pick" on:click={() => pickCover(r.image)}>
													<img src={r.thumbnail || r.image} alt={r.name} loading="lazy" />
													<span class="cover-name">{r.name}</span>
												</button>
											{/each}
										</div>
									{/if}
								{:else if gameImageMode === 'url'}
									<input type="text" class="mt-2" bind:value={editGameData.image_url} placeholder="https://..." />
								{:else}
									<input type="file" class="mt-2" accept="image/*" on:change={(e) => handleFileUpload(e, 'edit')} />
								{/if}
								{#if editGameData.image_url}
									<div class="img-preview mt-2">
										<img src={editGameData.image_url} alt="Preview" />
										<button class="preview-clear" on:click={() => editGameData.image_url = ''}>✕</button>
									</div>
								{/if}
							</div>
							<div class="edit-field full-width editor-container">
								<label>{$t('admin_games_rules_lbl')}</label>
								{#if EasyMDE}
									<textarea use:setupEditGameEditor={editGameData.rules}></textarea>
								{:else}
									<textarea bind:value={editGameData.rules} rows="6"></textarea>
								{/if}
							</div>
						</div>
					</div>
					<footer class="edit-modal-footer">
						<button class="btn-secondary" on:click={() => editingGame = null}>{$t('admin_settings_cancel')}</button>
						<button class="btn-primary" on:click={saveEditGame}>💾 {$t('admin_players_modal_btn_save')}</button>
					</footer>
				</div>
			</div>
		{/if}

		{:else if activeTab === 'players'}
			<div class="players-view glass p-8">
				<datalist id="admin-existing-teams">
					{#each existingTeams as team}
						<option value={team}></option>
					{/each}
				</datalist>
				<div class="flex-row justify-between items-center mb-4">
					<h3>{$t('admin_players_title')} <span class="t-count">{allPlayers.length}</span></h3>
					<div class="flex-row gap-2">
						<button class="btn-secondary btn-sm" on:click={() => showCreatePlayer = !showCreatePlayer}>
							{showCreatePlayer ? $t('admin_players_btn_cancel_close') : $t('admin_players_btn_add')}
						</button>
						<button class="btn-dev btn-sm" on:click={generateTestPool} disabled={generatingPool}>
							{generatingPool ? $t('admin_players_generating') : $t('admin_players_btn_gen20')}
						</button>
					</div>
				</div>

				{#if showCreatePlayer}
					<div class="create-player-form glass-inner">
						<div class="cpf-grid">
							<div class="edit-field">
								<label>{$t("admin_players_modal_pseudo")}</label>
								<input type="text" bind:value={newPlayerData.username} placeholder="{$t('admin_players_pseudo_placeholder')}" />
							</div>
							<div class="edit-field">
								<label>{$t("admin_players_modal_password")}</label>
								<input type="text" bind:value={newPlayerData.password} placeholder="{$t('admin_players_pwd_placeholder')}" />
							</div>
							<div class="edit-field">
								<label>{$t("admin_players_modal_team")}</label>
								<input type="text" bind:value={newPlayerData.team_name} list="admin-existing-teams" placeholder="{$t('admin_players_team_placeholder')}" />
							</div>
							<div class="edit-field cpf-submit">
								<button class="btn-primary" on:click={createPlayer} disabled={creatingPlayer || !newPlayerData.username.trim() || !newPlayerData.password.trim()}>
									{creatingPlayer ? '⏳' : '✅'} {$t("admin_players_modal_btn_create")}
								</button>
							</div>
						</div>
					</div>
				{/if}

				{#if allPlayers.length === 0}
					<p class="text-dim text-xs">{$t("admin_players_none_registered")}</p>
				{:else}
					<div class="players-table">
						<div class="pt-header">
							<span class="pt-col pt-id">#</span>
							<span class="pt-col pt-name">{$t("admin_players_hdr_pseudo")}</span>
							<span class="pt-col pt-team">{$t("admin_players_hdr_team")}</span>
							<span class="pt-col pt-pts">{$t("dash_modal_points_total")}</span>
							<span class="pt-col pt-actions">Actions</span>
						</div>
						{#each allPlayers as p, i}
							<div class="pt-row {p.is_admin ? 'is-admin' : ''}">
								<span class="pt-col pt-id">{i + 1}</span>
								<span class="pt-col pt-name" style="display: flex; align-items: center; gap: 0.4rem;">
									{#if p.avatar_url}
										<div class="admin-avatar-small avatar-shape-{p.avatar_shape || 'circle'}"><img src={p.avatar_url} alt="" /></div>
									{/if}
									<span>{p.username}</span>
									{#if p.is_admin}<span class="admin-badge">⭐</span>{/if}
									{#if p.ia_blocked}<span class="ia-blocked-badge" title="{$t('admin_players_ia_blocked_tooltip')}">🚫</span>{/if}
								</span>
								<span class="pt-col pt-team">{p.team_name || '—'}</span>
								<span class="pt-col pt-pts">{p.points || 0}</span>
								<span class="pt-col pt-actions">
									{#if !p.is_admin}
										<button class="btn-icon" title="{$t('admin_players_tooltip_edit')}" on:click={() => { editingPlayer = p; editPlayerData = { username: p.username, team_name: p.team_name || '', seat_id: p.seat_id || '', points: p.points || 0, is_admin: p.is_admin || false, ia_blocked: p.ia_blocked || false }; }}>✏️</button>
										<button class="btn-icon" title="{$t('admin_players_tooltip_resetpw')}" on:click={() => { resetPwdPlayer = p; resetPwdValue = 'lan2025'; }}>🔑</button>
										<button class="btn-icon {p.ia_blocked ? 'btn-icon-danger' : ''}" title="{p.ia_blocked ? $t('admin_players_tooltip_unblockai') : $t('admin_players_tooltip_blockai')}" on:click={() => toggleIaBlocked(p)}>
											{p.ia_blocked ? '🔓' : '🚫'}
										</button>
										{#if promoteConfirmPlayerId === p.id}
											<button class="btn-primary-sm" on:click={() => { toggleAdmin(p); promoteConfirmPlayerId = null; }}>{$t("admin_players_promote_confirm")}</button>
											<button class="btn-icon" on:click={() => promoteConfirmPlayerId = null}>❌</button>
										{:else}
											<button class="btn-icon btn-icon-promote" title="{$t('admin_players_tooltip_promote')}" on:click={() => { promoteConfirmPlayerId = p.id; deleteConfirmPlayerId = null; demoteConfirmPlayerId = null; }}>👑</button>
										{/if}
										{#if deleteConfirmPlayerId === p.id}
											<button class="btn-danger-sm" on:click={() => deletePlayer(p.id)}>{$t("admin_players_delete_confirm")}</button>
											<button class="btn-icon" on:click={() => deleteConfirmPlayerId = null}>❌</button>
										{:else}
											<button class="btn-icon btn-icon-danger" title="{$t('admin_tourneys_tooltip_delete')}" on:click={() => { deleteConfirmPlayerId = p.id; promoteConfirmPlayerId = null; demoteConfirmPlayerId = null; }}>🗑️</button>
										{/if}
									{:else}
										{#if demoteConfirmPlayerId === p.id}
											<button class="btn-warning-sm" on:click={() => { toggleAdmin(p); demoteConfirmPlayerId = null; }}>{$t("admin_players_demote_confirm")}</button>
											<button class="btn-icon" on:click={() => demoteConfirmPlayerId = null}>❌</button>
										{:else}
											<button class="btn-icon btn-icon-demote" title="{$t('admin_players_tooltip_demote')}" on:click={() => { demoteConfirmPlayerId = p.id; promoteConfirmPlayerId = null; deleteConfirmPlayerId = null; }}>🛡️</button>
										{/if}
									{/if}
								</span>
							</div>
						{/each}
					</div>
				{/if}
			</div>

			{#if editingPlayer}
				<div class="edit-overlay" use:portal
					on:mousedown={(e) => { if (e.target === e.currentTarget) overlayMouseDown = true; }} 
					on:mouseup={(e) => { if (overlayMouseDown && e.target === e.currentTarget) editingPlayer = null; overlayMouseDown = false; }}>
					<div class="edit-modal glass" on:click|stopPropagation style="max-width: 400px">
						<header class="edit-modal-header">
							<h3>✏️ Modifier — {editingPlayer.username}</h3>
							<button class="close-btn" on:click={() => editingPlayer = null}>✕</button>
						</header>
						<div class="edit-modal-body">
							{#if editingPlayer.avatar_url}
								<div class="edit-field mb-3" style="display: flex; align-items: center; gap: 1rem;">
									<div class="admin-avatar-lg avatar-shape-{editingPlayer.avatar_shape || 'circle'}">
										<img src={editingPlayer.avatar_url} alt="" />
									</div>
									<button class="btn-danger-sm" type="button" on:click={() => adminDeleteAvatar(editingPlayer.id)}>Supprimer l'avatar</button>
								</div>
							{/if}
							<div class="edit-field mb-3">
								<label>{$t("admin_players_modal_pseudo")}</label>
								<input type="text" bind:value={editPlayerData.username} />
							</div>
							<div class="edit-field mb-3">
								<label>Nom d'équipe</label>
								<input type="text" bind:value={editPlayerData.team_name} list="admin-existing-teams" placeholder="Aucune équipe" />
							</div>
							<div class="edit-field mb-3">
								<label>Place assignée (Poste ID)</label>
								<input type="text" bind:value={editPlayerData.seat_id} placeholder="Aucun poste (ex: A01)" />
							</div>
							<div class="edit-field mb-3">
								<label>Points cumulés</label>
								<input type="number" bind:value={editPlayerData.points} placeholder="0" />
							</div>
							<div class="edit-field mb-3" style="display: flex; align-items: center; gap: 0.5rem;">
								<input type="checkbox" id="edit-is-admin" bind:checked={editPlayerData.is_admin} style="width: auto;" />
								<label for="edit-is-admin" style="margin: 0; cursor: pointer;">Est Administrateur 👑</label>
							</div>
							<div class="edit-field mb-3" style="display: flex; align-items: center; gap: 0.5rem;">
								<input type="checkbox" id="edit-ia-blocked" bind:checked={editPlayerData.ia_blocked} style="width: auto;" />
								<label for="edit-ia-blocked" style="margin: 0; cursor: pointer;">Bloquer l'accès IA 🚫</label>
							</div>
						</div>
						<footer class="edit-modal-footer">
							<button class="btn-secondary" on:click={() => editingPlayer = null}>{$t('admin_settings_cancel')}</button>
							<button class="btn-primary" on:click={savePlayer}>💾 {$t('admin_players_modal_btn_save')}</button>
						</footer>
					</div>
				</div>
			{/if}

			{#if resetPwdPlayer}
				<div class="edit-overlay" use:portal
					on:mousedown={(e) => { if (e.target === e.currentTarget) overlayMouseDown = true; }} 
					on:mouseup={(e) => { if (overlayMouseDown && e.target === e.currentTarget) resetPwdPlayer = null; overlayMouseDown = false; }}>
					<div class="edit-modal glass" on:click|stopPropagation style="max-width: 400px">
						<header class="edit-modal-header">
							<h3>🔑 Réinitialiser MDP — {resetPwdPlayer.username}</h3>
							<button class="close-btn" on:click={() => resetPwdPlayer = null}>✕</button>
						</header>
						<div class="edit-modal-body">
							<div class="edit-field">
								<label>Nouveau mot de passe</label>
								<input type="text" bind:value={resetPwdValue} />
							</div>
						</div>
						<footer class="edit-modal-footer">
							<button class="btn-secondary" on:click={() => resetPwdPlayer = null}>{$t('admin_settings_cancel')}</button>
							<button class="btn-primary" on:click={resetPassword}>✅ Réinitialiser</button>
						</footer>
					</div>
				</div>
			{/if}

		{:else if activeTab === 'settings'}
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
											<p>{$t("admin_settings_purge_awards_sub") || "Deletes all prizes and distinctions awarded to players"}</p>
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
					<!-- AI Queue Panel (G-52) -->
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
										<span class="queue-row-type">{entry.task_type === 'chat' ? '💬' : entry.task_type === 'compress' ? '🗜️' : '🏆'}</span>
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
										<span class="queue-row-type">{entry.task_type === 'chat' ? '💬' : entry.task_type === 'compress' ? '🗜️' : '🏆'}</span>
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
		{:else if activeTab === 'conversations'}
			<div class="admin-grid">
				<!-- Conversation list -->
				<section class="list glass" style="max-height:80vh;overflow-y:auto">
					<div class="list-header">
						<div class="flex-row items-center gap-3">
							<div class="list-icon">💬</div>
							<div>
								<h2 style="margin:0">{$t("admin_chats_title")}</h2>
								<span class="text-xs text-dim">{$t("admin_chats_subtitle")}</span>
							</div>
						</div>
						<span class="badge-count">{adminConversations.length}</span>
					</div>
					<div class="item-list">
						{#each adminConversations as c}
							<div class="admin-item-card glass-hover {adminActiveConvId === c.id ? 'editing-expanded' : ''}" style="cursor:pointer;flex-direction:column;align-items:stretch;border-left: 4px solid {c.has_new_messages ? '#22c55e' : (c.admin_override ? '#a855f7' : 'rgba(255,255,255,0.05)')}" on:click={() => selectAdminConv(c.id)}>
								<div class="card-top-row" style="display:flex;justify-content:space-between;align-items:center">
									<div class="item-info">
										<div class="flex-row items-center gap-2" style="flex-wrap:wrap">
											<span class="item-name">{c.title}</span>
											{#if c.has_new_messages}
												<span class="status-pill-sm open" style="background:rgba(34,197,94,0.15);color:#22c55e;border:1px solid rgba(34,197,94,0.3)">{c.unread_count > 1 ? $t('admin_chats_unread_plural', { count: c.unread_count }) : $t('admin_chats_unread_singular', { count: c.unread_count })}</span>
											{/if}
											{#if c.admin_override}
												<span class="status-pill-sm" style="background:rgba(168,85,247,0.2);color:#a855f7;border:1px solid #a855f7">🛡️ Admin</span>
											{/if}
										</div>
										<div class="item-meta">👤 {c.username} • {c.message_count} msg • {$t('dash_pill_active')} : {c.last_message_at ? new Date(c.last_message_at).toLocaleString('fr-FR', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' }) : ''}</div>
										{#if c.last_message_preview}
											<div class="last-msg-preview" style="font-size:0.75rem;color:var(--text-dim);margin-top:0.3rem;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;max-width:320px;opacity:0.8">
												<strong>{c.last_message_role === 'user' ? '👤' : c.last_message_role === 'admin' ? '🛡️' : '🤖'}:</strong> {c.last_message_preview}
											</div>
										{/if}
									</div>
								</div>
							</div>
						{:else}
							<div class="empty-list">
								<span class="empty-icon">💬</span>
								<p>{$t('admin_chats_empty')}</p>
							</div>
						{/each}
					</div>
				</section>

				<!-- Conversation detail -->
				<section class="list glass" style="max-height:80vh;display:flex;flex-direction:column">
					{#if adminActiveConvId && adminConvInfo}
						<div class="list-header">
							<div class="flex-row items-center gap-3">
								<div class="list-icon">🔍</div>
								<div>
									<h2 style="margin:0">{adminConvInfo.title}</h2>
									<span class="text-xs text-dim">{$t("admin_chats_player")} {adminConvInfo.username}</span>
								</div>
							</div>
							<div class="flex-row gap-2 items-center">
								{#if adminConvInfo.admin_override}
									<button class="btn-primary btn-xs" on:click={() => toggleAdminOverride(adminActiveConvId, false)}>🤖 {$t('admin_chats_takeover')}</button>
								{:else}
									<button class="btn-sentinel" on:click={() => toggleAdminOverride(adminActiveConvId, true)}>{$t('admin_chats_btn_takeover')}</button>
								{/if}
							</div>
						</div>
						<div bind:this={adminChatContainer} style="flex:1;overflow-y:auto;padding:1rem;display:flex;flex-direction:column;gap:0.75rem">
							{#each adminConvMessages as m}
								<div style="display:flex;gap:0.5rem;{m.role === 'user' ? 'flex-direction:row-reverse' : ''}">
									<div style="font-size:1.1rem">{m.role === 'bot' ? '🤖' : m.role === 'admin' ? '🛡️' : '👤'}</div>
									<div style="display:flex;flex-direction:column;max-width:80%;align-items:{m.role === 'user' ? 'flex-end' : 'flex-start'}">
										{#if m.role === 'user'}
											<span style="font-size:0.7rem;color:var(--text-muted);margin-bottom:2px;font-weight:600;">{adminConvInfo.username}</span>
										{/if}
										<div style="padding:0.6rem 0.8rem;border-radius:12px;font-size:0.85rem;line-height:1.4;{m.role === 'user' ? 'background:rgba(59,130,246,0.15);border:1px solid rgba(59,130,246,0.3)' : m.role === 'admin' ? 'background:rgba(168,85,247,0.12);border:1px solid rgba(168,85,247,0.3)' : 'background:var(--hover-tint);border:1px solid var(--glass-border)'}">
											{#if m.role === 'admin'}<span style="font-size:0.65rem;font-weight:700;color:#a855f7;text-transform:uppercase;margin-bottom:0.2rem;display:block">Admin</span>{/if}
											<div class="admin-conv-md">{@html parseMd(m.content)}</div>
											{#if m.image_path}
												<div style="margin-top:0.4rem">
													<img src="{API_URL}/data/{m.image_path}" alt="" style="max-width:250px;max-height:180px;border-radius:8px;border:1px solid var(--glass-border);cursor:pointer;object-fit:cover" on:click={() => window.open(API_URL + '/data/' + m.image_path, '_blank')} />
												</div>
											{/if}
										</div>
										
										{#if m.role === 'bot' && m.meta}
											<div class="msg-meta-row" style="display:flex;flex-wrap:wrap;gap:0.4rem;font-size:0.65rem;color:var(--text-dim);margin-top:0.2rem;padding:0 0.2rem;opacity:0.8">
												{#if m.meta.model_info}
													<span title="Modèle / Instance" style="background:rgba(255,255,255,0.05);padding:1px 4px;border-radius:4px;border:1px solid var(--glass-border)">🤖 {m.meta.model_info.model || 'Modèle'} ({m.meta.model_info.instance || 'Default'})</span>
												{/if}
												{#if m.meta.duration}
													<span title="Temps de réponse" style="background:rgba(255,255,255,0.05);padding:1px 4px;border-radius:4px;border:1px solid var(--glass-border)">⏱️ {m.meta.duration.toFixed(1)}s</span>
												{/if}
												{#if m.meta.used_tools && m.meta.used_tools.length > 0}
													<span title="Outils utilisés: {m.meta.used_tools.join(', ')}" style="background:rgba(59,130,246,0.1);color:var(--accent);padding:1px 4px;border-radius:4px;border:1px solid rgba(59,130,246,0.2)">🛠️ {m.meta.used_tools.join(', ')}</span>
												{/if}
											</div>
										{/if}
										
										<span style="font-size:0.62rem;color:var(--text-muted);margin-top:0.15rem;align-self:{m.role === 'user' ? 'flex-end' : 'flex-start'};padding:0 0.25rem">
											{m.timestamp ? new Date(m.timestamp).toLocaleString('fr-FR', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit', second: '2-digit' }) : ''}
										</span>
									</div>
								</div>
							{/each}
						</div>
						{#if adminConvInfo.admin_override}
							<div style="padding:0.75rem 1rem;border-top:1px solid var(--glass-border);display:flex;flex-direction:column;gap:0.5rem">
								{#if adminImagePreview}
									<div style="position:relative;display:inline-block">
										<img src={adminImagePreview} alt="Preview" style="max-width:150px;max-height:80px;border-radius:6px;border:2px solid #a855f7;object-fit:cover" />
										<button style="position:absolute;top:-6px;right:-6px;width:20px;height:20px;border-radius:50%;background:rgba(239,68,68,0.9);color:white;border:none;cursor:pointer;font-size:0.65rem;display:flex;align-items:center;justify-content:center" on:click={() => { adminPendingImage = null; adminImagePreview = ''; }}>✕</button>
									</div>
								{/if}
								<div style="display:flex;gap:0.5rem;align-items:center">
									<input type="file" accept="image/*" bind:this={adminFileInput} on:change={handleAdminFileSelect} style="display:none" />
									<button class="btn-attach" style="width:36px;height:36px;font-size:1rem;border-radius:6px" on:click={() => adminFileInput?.click()} title="Joindre une image">📎</button>
									<input type="text" bind:value={adminInterveneText} placeholder="{$t('admin_chats_placeholder')}" style="flex:1" on:keydown={(e) => { if (e.key === 'Enter') adminSendIntervention(); }} on:paste={handleAdminPaste} />
									<button class="btn-primary" on:click={adminSendIntervention}>{$t('ai_btn_send')}</button>
								</div>
							</div>
						{:else}
							<div style="padding:0.75rem 1rem;border-top:1px solid var(--glass-border);text-align:center;font-size:0.8rem;color:var(--text-dim)">
								{$t('admin_chats_system_control')}
							</div>
						{/if}
					{:else}
						<div class="empty-list" style="flex:1;display:flex;flex-direction:column;align-items:center;justify-content:center">
							<span class="empty-icon">🔍</span>
							<p>{$t('admin_chats_no_conv_selected')}</p>
						</div>
					{/if}
				</section>
			</div>
		{:else if activeTab === 'awards'}
			<div class="admin-grid">
				<!-- Explanation and Sync controls -->
				<section class="wizard glass" style="max-height: 85vh; overflow-y: auto;">
					<div class="list-header">
						<div class="flex-row items-center gap-3">
							<div class="list-icon">🎁</div>
							<div>
								<h2 class="text-accent" style="margin:0">{$t("admin_awards_title")}</h2>
								<span class="text-xs text-dim">{$t("admin_awards_subtitle")}</span>
							</div>
						</div>
					</div>

					<div style="display: flex; flex-direction: column; gap: 1rem; margin-top: 1rem;" class="text-sm">
						<p>{$t('admin_awards_desc1')}</p>
						<p>{$t('admin_awards_desc2')}</p>
						<p class="text-dim text-xs" style="border-left: 2px solid var(--accent); padding-left: 0.5rem;">
							💡 Les descriptions supportent l'interpolation de variables de statistiques liées au vainqueur (ex: <code>{"{"}points{"}"}</code>, <code>{"{"}wins{"}"}</code>, <code>{"{"}matches_played{"}"}</code>, <code>{"{"}team_name{"}"}</code>).
						</p>
						<p class="text-dim text-xs" style="border-left: 2px solid var(--success); padding-left: 0.5rem; margin-top: 0.2rem;">
							{$t('admin_awards_desc4')}
						</p>
					</div>

					<button class="btn-primary" style="margin-top: 1.5rem; width: 100%; padding: 0.6rem 1rem;" on:click={triggerSync} disabled={awardsLoading}>
						{$t('admin_awards_btn_recalc')}
					</button>

					<button class="btn-success" style="margin-top: 1rem; width: 100%; padding: 0.6rem 1rem;" on:click={sendAwardsNotifications} disabled={awardsLoading}>
						{$t('admin_awards_btn_broadcast')}
					</button>

					<div style="margin-top: 2rem; border-top: 1px solid rgba(239, 68, 68, 0.2); padding-top: 1rem;">
						{#if nukeConfirm.awards}
							<div class="flex-column gap-2" style="background: rgba(239, 68, 68, 0.08); padding: 0.8rem; border-radius: 8px; border: 1px solid var(--danger);">
								<span class="text-xs text-dim" style="display:block; margin-bottom: 0.5rem; text-align: center; color: var(--danger) !important; font-weight: bold;">{$t("admin_awards_confirm_purge_q")}</span>
								<div style="display: flex; gap: 0.5rem;">
									<button class="btn-danger btn-xs" style="flex:1" on:click={nukeAwards} disabled={nuking.awards}>
										{nuking.awards ? $t('admin_awards_purging') : $t('admin_awards_confirm_purge_yes')}
									</button>
									<button class="btn-secondary btn-xs" style="flex:1" on:click={() => nukeConfirm.awards = false}>
										Annuler
									</button>
								</div>
							</div>
						{:else}
							<button class="btn-danger" style="width: 100%; padding: 0.6rem 1rem;" on:click={() => nukeConfirm.awards = true} disabled={awardsLoading}>
								{$t('admin_awards_btn_purge')}
							</button>
						{/if}
					</div>
				</section>

				<!-- List of automated awards -->
				<section class="list glass" style="max-height: 85vh; overflow-y: auto;">
					<div class="list-header">
						<div class="flex-row items-center gap-3">
							<div class="list-icon">🏆</div>
							<div>
								<h2 style="margin:0">{$t("admin_awards_list")}</h2>
								<span class="text-xs text-dim">{$t("admin_awards_list_sub")}</span>
							</div>
						</div>
						<span class="badge-count">{awardsList.length}</span>
					</div>

					<div class="item-list" style="display: flex; flex-direction: column; gap: 1.2rem;">
						{#each awardsList as award}
							<div class="award-card-editor glass" style="padding: 1.2rem; border-radius: 12px; border: 1px solid var(--glass-border); background: var(--hover-tint); display: flex; flex-direction: column; gap: 1rem;">
								
								<!-- Title Row -->
								<div style="display: flex; justify-content: space-between; align-items: flex-start; gap: 1rem;">
									<div style="flex: 1;">
										<h3 class="text-accent" style="margin: 0; font-size: 1rem; font-weight: 700;">{getAwardEmoji(award.key)} {award.title}</h3>
										<p class="text-xs text-dim" style="margin: 0.2rem 0 0; font-style: italic;">{$t('profile_pts_details')} : {award.criteria}</p>
									</div>
									
									<!-- Recipient Badge -->
									<div style="text-align: right; display: flex; flex-direction: column; align-items: flex-end; min-width: 120px;">
										{#if award.has_recipient}
											<span class="status-pill-sm running" style="font-size: 0.75rem; padding: 0.25rem 0.6rem; font-weight: 700;">
												👤 {award.recipient_name}
											</span>
											{#if award.stats_label}
												<span class="text-xs text-accent" style="font-weight: 700; margin-top: 0.15rem;">
													{award.stats_label}
												</span>
											{/if}
										{:else}
											<span class="status-pill-sm closed" style="font-size: 0.75rem; padding: 0.25rem 0.6rem; opacity: 0.6;">
												{$t('admin_awards_none')}
											</span>
										{/if}
									</div>
								</div>

								<!-- Input Forms -->
								<div style="display: flex; flex-direction: column; gap: 0.8rem;">
									<div class="edit-field full-width" style="margin: 0;">
										<label class="compact-label" style="font-weight: 700; font-size: 0.75rem; color: var(--text-dim);">{$t("admin_awards_edit_title")}</label>
										<input type="text" bind:value={award.title} placeholder={award.default_title} style="width: 100%; padding: 0.4rem 0.6rem; background: var(--surface-sunken); border: 1px solid var(--glass-border); border-radius: 8px; color: var(--text-main); font-size: 0.85rem;" />
									</div>
									
									<div class="edit-field full-width" style="margin: 0;">
										<label class="compact-label" style="font-weight: 700; font-size: 0.75rem; color: var(--text-dim);">{$t("admin_awards_edit_desc")}</label>
										<textarea bind:value={award.description} placeholder={award.default_description} rows="2" style="width: 100%; padding: 0.4rem 0.6rem; background: var(--surface-sunken); border: 1px solid var(--glass-border); border-radius: 8px; color: var(--text-main); font-size: 0.85rem; font-family: inherit; resize: vertical;"></textarea>
									</div>
								</div>

								<!-- Action Row -->
								<div style="display: flex; justify-content: flex-end; gap: 0.5rem; align-items: center;">
									{#if award.custom_title !== null || award.custom_description !== null}
										<button class="btn-secondary btn-xs" style="font-size: 0.75rem; padding: 0.3rem 0.6rem;" on:click={() => restoreDefaultText(award.key)}>
											{$t("admin_awards_restore_default")}
										</button>
									{/if}
									<button class="btn-primary btn-xs" style="font-size: 0.75rem; padding: 0.3rem 0.8rem;" on:click={() => saveAwardText(award.key, award.title, award.description)}>
										{$t("admin_awards_btn_save")}
									</button>
								</div>

							</div>
						{:else}
							<div class="empty-list">
								<span class="empty-icon">📭</span>
								<p>{$t('admin_awards_none_available')}</p>
							</div>
						{/each}
					</div>
				</section>
			</div>
		{/if}
	</div>
</div>
<!-- Edit Tournament Modal -->
<EditTournamentModal
	tournament={editingTournament}
	show={!!editingTournament}
	showStatus={true}
	on:close={() => editingTournament = null}
	on:save={async (e) => {
		editConfig = e.detail.editConfig;
		await updateTournament();
	}}
/>

<!-- Add Game Modal -->
<AddGameModal
	show={showAddGameModal}
	on:close={() => showAddGameModal = false}
	on:success={() => loadData()}
	on:toast={(e) => toast(e.detail.message, e.detail.type)}
/>

<!-- Toast Notifications -->
<div class="toast-container" use:portal>
	{#each toasts as t (t.id)}
		<div class="toast {t.type} {t.leaving ? 'toast-leave' : 'toast-enter'}">
			<span class="toast-icon">
				{#if t.type === 'success'}✅{:else if t.type === 'error'}❌{:else}ℹ️{/if}
			</span>
			<span class="toast-msg">{t.message}</span>
		</div>
	{/each}
</div>

<Modal
	bind:show={showModal}
	title={modalTitle}
	message={modalMessage}
	type={modalType}
	onConfirm={modalConfirmCallback}
/>

{/if}

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
	.admin-view { display: flex; flex-direction: column; gap: 2rem; }
	.tabs { display: flex; padding: 0.3rem; border-radius: 12px; background: var(--surface-sunken); border: 1px solid var(--glass-border); }
	.tabs button { padding: 0.6rem 1.2rem; border: none; background: transparent; color: var(--text-dim); cursor: pointer; font-weight: 600; border-radius: 8px; transition: all 0.2s; font-size: 0.85rem; }
	.tabs button.active { background: var(--accent); color: white; box-shadow: 0 4px 12px var(--accent-glow); }
	.admin-grid { display: grid; grid-template-columns: minmax(380px, 1fr) 2fr; gap: 2rem; }

	.admin-item-card { display: flex; align-items: center; gap: 1rem; padding: 1rem; border-radius: 12px; margin-bottom: 0.75rem; border: 1px solid var(--glass-border); transition: all 0.2s; }

	.admin-item-card:hover { border-color: var(--accent); background: rgba(59, 130, 246, 0.05); }
	.game-mini-thumb { width: 50px; height: 50px; border-radius: 8px; background-size: cover; background-position: center; border: 1px solid var(--glass-border); }
	.item-info { flex-grow: 1; }
	.item-name { font-weight: 700; font-size: 1rem; }
	.item-meta { font-size: 0.75rem; color: var(--text-dim); margin-top: 0.2rem; }
	
	.badge-count { font-size: 0.7rem; background: var(--accent-soft); color: var(--accent); padding: 0.2rem 0.6rem; border-radius: 4px; font-weight: 800; border: 1px solid var(--accent); }
	
	.status-dot { width: 8px; height: 8px; border-radius: 50%; }
	.status-dot.open { background: var(--success); box-shadow: 0 0 8px var(--success); }
	.status-dot.running { background: var(--accent); box-shadow: 0 0 8px var(--accent); }
	.status-dot.done { background: var(--text-muted); }



	.btn-icon-edit { background: rgba(255, 255, 255, 0.05); border: 1px solid var(--glass-border); color: var(--text-muted); cursor: pointer; padding: 0.6rem; border-radius: 8px; transition: all 0.2s; display: flex; align-items: center; justify-content: center; }
	.btn-icon-edit:hover { background: rgba(59, 130, 246, 0.2); color: var(--accent); border-color: var(--accent); }
	.btn-icon-danger { background: rgba(255, 255, 255, 0.05); border: 1px solid var(--glass-border); color: var(--text-muted); cursor: pointer; padding: 0.6rem; border-radius: 8px; transition: all 0.2s; display: flex; align-items: center; justify-content: center; }
	.btn-icon-danger:hover { background: rgba(239, 68, 68, 0.2); color: var(--danger); border-color: var(--danger); }

	.item-actions { display: flex; flex-direction: row; gap: 0.4rem; align-items: center; flex-shrink: 0; }
	.confirm-delete-row { display: flex; align-items: center; gap: 0.4rem; background: rgba(239,68,68,0.05); padding: 0.3rem 0.5rem; border-radius: 8px; border: 1px dashed rgba(239,68,68,0.2); }

	/* List header */
	.list-header { display: flex; justify-content: space-between; align-items: center; padding-bottom: 1rem; margin-bottom: 1rem; border-bottom: 1px solid var(--glass-border); }
	.list-icon { width: 40px; height: 40px; display: flex; align-items: center; justify-content: center; font-size: 1.4rem; background: var(--accent-soft); border-radius: 10px; border: 1px solid rgba(59,130,246,0.15); }

	/* Status pill */
	.status-pill-sm { font-size: 0.6rem; font-weight: 700; text-transform: uppercase; letter-spacing: 0.05em; padding: 0.15rem 0.5rem; border-radius: 20px; }
	.status-pill-sm.open { background: rgba(34,197,94,0.1); color: var(--success); border: 1px solid rgba(34,197,94,0.2); }
	.status-pill-sm.running { background: var(--accent-soft); color: var(--accent); border: 1px solid rgba(59,130,246,0.2); }
	.status-pill-sm.done { background: rgba(100,116,139,0.1); color: var(--text-muted); border: 1px solid rgba(100,116,139,0.2); }
	.status-pill-sm.closed { background: rgba(139,92,246,0.1); color: #a78bfa; border: 1px solid rgba(139,92,246,0.2); }

	/* Thumb placeholder */
	.thumb-placeholder { display: flex; align-items: center; justify-content: center; width: 100%; height: 100%; font-size: 1.2rem; background: var(--surface-sunken); border-radius: 8px; }

	/* Empty state */
	.empty-list { display: flex; flex-direction: column; align-items: center; justify-content: center; padding: 3rem 1rem; gap: 0.5rem; }
	.empty-icon { font-size: 2.5rem; opacity: 0.5; }
	.empty-list p { color: var(--text-dim); font-weight: 600; margin: 0; }

	/* Edit modal */
	.edit-overlay { position: fixed; inset: 0; background: var(--overlay-bg); backdrop-filter: blur(4px); z-index: 9999; display: flex; align-items: center; justify-content: center; padding: 2rem; }
	.edit-modal { width: 580px; max-width: 100%; max-height: 85vh; overflow-y: auto; border-radius: 20px; border: 1px solid var(--glass-border); box-shadow: 0 25px 60px rgba(0,0,0,0.3); }
	.edit-modal-header { display: flex; justify-content: space-between; align-items: center; padding: 1.2rem 1.5rem; border-bottom: 1px solid var(--glass-border); background: rgba(59,130,246,0.08); }
	.edit-modal-header h3 { font-size: 1rem; margin: 0; }
	.close-btn { background: none; border: none; color: var(--text-dim); cursor: pointer; font-size: 1.2rem; padding: 0.2rem; }
	.edit-modal-body { padding: 1.5rem; }
	.edit-modal-footer { display: flex; justify-content: flex-end; gap: 0.75rem; padding: 1rem 1.5rem; border-top: 1px solid var(--glass-border); }
	.edit-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 1rem; }
	.edit-field { display: flex; flex-direction: column; gap: 0.4rem; }
	.edit-field.full-width { grid-column: 1 / -1; }
	.edit-field label { font-size: 0.75rem; font-weight: 700; color: var(--text-dim); text-transform: uppercase; letter-spacing: 0.05em; }
	.edit-toggle-row { display: flex; gap: 0.4rem; flex-wrap: wrap; }
	.edit-toggle { padding: 0.45rem 0.8rem; font-size: 0.75rem; font-weight: 600; border: 1px solid var(--glass-border); border-radius: 8px; background: var(--hover-tint); color: var(--text-dim); cursor: pointer; transition: all 0.15s; }
	.edit-toggle:hover { border-color: var(--accent); background: rgba(59,130,246,0.05); }
	.edit-toggle.active { background: var(--accent-soft); border-color: var(--accent); color: var(--accent); box-shadow: 0 0 8px var(--accent-glow); }

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
	/* Button to open the prompt editor modal from the compact admin card */
	.btn-prompt-edit { font-size: 0.68rem; font-weight: 700; padding: 0.2rem 0.6rem; border-radius: 6px; border: 1px solid rgba(139,92,246,0.3); background: rgba(139,92,246,0.06); color: #a78bfa; cursor: pointer; transition: all 0.15s; white-space: nowrap; }
	.btn-prompt-edit:hover { background: rgba(139,92,246,0.18); border-color: #a78bfa; box-shadow: 0 0 8px rgba(139,92,246,0.2); }

	.wizard { padding: 2rem; min-height: 500px; display: flex; flex-direction: column; }
	.list { padding: 2rem; display: flex; flex-direction: column; }

	.step-box { flex-grow: 1; display: flex; flex-direction: column; justify-content: center; }

	.glass-inner { background: var(--surface-sunken); border-radius: 12px; border: 1px solid var(--glass-border); }
	.grid-2 { display: grid; grid-template-columns: 1fr 1fr; gap: 1rem; }

	.bracket-graphics-grid { display: grid; grid-template-columns: 1fr; gap: 1rem; margin-top: 0.5rem; }
	.graphic-card { background: var(--hover-tint); border: 1px solid var(--glass-border); border-radius: 12px; padding: 1rem; display: flex; flex-direction: column; align-items: center; gap: 0.8rem; cursor: pointer; transition: all 0.2s; color: var(--text-dim); }
	.graphic-card:hover { border-color: var(--accent); background: rgba(59, 130, 246, 0.05); }
	.graphic-card.active { border-color: var(--accent); background: var(--accent-soft); color: var(--accent); box-shadow: 0 0 15px var(--accent-glow); }
	.graphic-card svg { width: 80px; height: 50px; opacity: 0.8; }
	.graphic-card.active svg { stroke: var(--accent); opacity: 1; }
	.graphic-card span { font-weight: 600; font-size: 0.85rem; }

	.nav-btns { display: flex; justify-content: space-between; margin-top: 2rem; border-top: 1px solid var(--glass-border); padding-top: 1.5rem; }

	.settings-view { display: flex; flex-direction: column; gap: 0; }

	/* Settings Sub-Tabs */
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

	/* Instance rows */
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

	/* Toggle switch & Mini version */
	.toggle-switch { position: relative; display: inline-block; width: 32px; height: 18px; cursor: pointer; }
	.toggle-switch input { opacity: 0; width: 0; height: 0; }
	.toggle-slider { position: absolute; inset: 0; background: var(--surface-sunken); border-radius: 9px; transition: 0.2s; }
	.toggle-slider::before { content: ''; position: absolute; height: 14px; width: 14px; left: 2px; bottom: 2px; background: var(--text-dim); border-radius: 50%; transition: 0.2s; }
	.toggle-switch input:checked + .toggle-slider { background: rgba(59,130,246,0.35); }
	.toggle-switch input:checked + .toggle-slider::before { transform: translateX(14px); background: var(--accent); }

	.toggle-switch-mini { position: relative; display: inline-block; width: 28px; height: 16px; cursor: pointer; }
	.toggle-switch-mini input { opacity: 0; width: 0; height: 0; }
	.toggle-switch-mini .toggle-slider { position: absolute; inset: 0; background: var(--surface-sunken); border-radius: 8px; transition: 0.2s; }
	.toggle-switch-mini .toggle-slider::before { content: ''; position: absolute; height: 12px; width: 12px; left: 2px; bottom: 2px; background: var(--text-dim); border-radius: 50%; transition: 0.2s; }
	.toggle-switch-mini input:checked + .toggle-slider { background: rgba(59,130,246,0.35); }
	.toggle-switch-mini input:checked + .toggle-slider::before { transform: translateX(12px); background: var(--accent); }

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
	/* Param display */
	.param-val { margin-left: auto; font-size: 0.85rem; font-weight: 800; color: var(--accent); background: rgba(59,130,246,0.1); padding: 0.15rem 0.5rem; border-radius: 6px; }
	.range-accent { width: 100%; accent-color: var(--accent); }
	.range-labels { display: flex; justify-content: space-between; font-size: 0.6rem; color: var(--text-muted); margin-top: 0.2rem; }

	.compact-label { font-size: 0.72rem; font-weight: 700; color: var(--text-dim); text-transform: uppercase; letter-spacing: 0.04em; margin: 0; }
	.ctx-preset-mini-btn { flex: 1; padding: 0.25rem 0.5rem; font-size: 0.68rem; font-weight: 600; border: 1px solid var(--glass-border); border-radius: 6px; background: var(--hover-tint); color: var(--text-dim); cursor: pointer; transition: all 0.15s; text-align: center; }
	.ctx-preset-mini-btn:hover { border-color: var(--accent); background: rgba(59,130,246,0.05); }
	.ctx-preset-mini-btn.active { background: var(--accent-soft); border-color: var(--accent); color: var(--accent); box-shadow: 0 0 8px var(--accent-glow); }
	.inst-model-select-wide { width: 100%; background: var(--surface-sunken); border: 1px solid var(--glass-border); border-radius: 8px; padding: 0.35rem 0.5rem; color: var(--text-main); font-size: 0.75rem; transition: all 0.2s; }
	.inst-model-select-wide:focus { border-color: var(--accent); outline: none; }
	.prompt-textarea-compact { width: 100%; max-width: 100%; box-sizing: border-box; background: var(--surface-sunken); border: 1px solid var(--glass-border); border-radius: 8px; padding: 0.5rem; color: var(--text-main); font-size: 0.75rem; resize: vertical; font-family: inherit; line-height: 1.4; min-height: 140px; }
	.prompt-textarea-compact:focus { outline: none; border-color: var(--accent); }
	.prompts-container { display: grid; grid-template-columns: minmax(0, 1fr); gap: 0.8rem; width: 100%; }
	@media (min-width: 1024px) {
		.prompts-container { grid-template-columns: repeat(2, minmax(0, 1fr)); }
	}
	.prompt-textarea { width: 100%; background: var(--surface-sunken); border: 1px solid var(--glass-border); border-radius: 10px; padding: 0.7rem; color: var(--text-main); font-size: 0.8rem; resize: vertical; font-family: inherit; line-height: 1.5; min-height: 80px; }
	.prompt-textarea:focus { border-color: var(--accent); outline: none; }

	.game-gallery { display: grid; grid-template-columns: repeat(auto-fill, minmax(140px, 1fr)); gap: 1rem; margin-top: 1rem; }
	.game-card { overflow: hidden; border: 1px solid var(--glass-border); border-radius: 12px; transition: all 0.2s; }
	.game-card:hover { border-color: var(--accent); transform: translateY(-2px); }
	.game-thumb { height: 95px; background-size: cover; background-position: center; position: relative; display: flex; align-items: center; justify-content: center; }
	.game-info { padding: 0.5rem; text-align: center; font-size: 0.78rem; font-weight: 600; }
	.game-empty { grid-column: 1 / -1; padding: 2rem; text-align: center; }

	/* Game card overlay actions */
	.game-card-actions { position: absolute; inset: 0; background: rgba(0,0,0,0.6); display: flex; align-items: center; justify-content: center; gap: 0.3rem; opacity: 0; transition: opacity 0.2s; }
	.game-card:hover .game-card-actions { opacity: 1; }
	.game-action-btn { width: 28px; height: 28px; border: 1px solid rgba(255,255,255,0.2); border-radius: 6px; background: rgba(0,0,0,0.5); color: white; cursor: pointer; font-size: 0.7rem; display: flex; align-items: center; justify-content: center; transition: all 0.15s; }
	.game-action-btn.edit:hover { background: rgba(59,130,246,0.4); border-color: var(--accent); }
	.game-action-btn.delete:hover { background: rgba(239,68,68,0.4); border-color: var(--danger); }
	.game-action-btn.confirm { background: rgba(239,68,68,0.5); border-color: var(--danger); }
	.game-action-btn.cancel { background: rgba(100,116,139,0.4); }

	/* Image mode tabs */
	.img-mode-tabs { display: flex; gap: 0.3rem; }
	.img-tab { padding: 0.35rem 0.7rem; font-size: 0.7rem; font-weight: 600; border: 1px solid var(--glass-border); border-radius: 8px; background: var(--hover-tint); color: var(--text-dim); cursor: pointer; transition: all 0.15s; }
	.img-tab:hover { border-color: var(--accent); }
	.img-tab.active { background: var(--accent-soft); border-color: var(--accent); color: var(--accent); }

	/* Search bar */
	.search-bar { display: flex; gap: 0.4rem; }
	.search-bar input { flex-grow: 1; }
	.btn-sm { padding: 0.4rem 0.8rem; font-size: 0.75rem; }

	/* Cover picker grid */
	.cover-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(110px, 1fr)); gap: 0.5rem; max-height: 220px; overflow-y: auto; }
	.cover-pick { overflow: hidden; border: 2px solid var(--glass-border); border-radius: 8px; cursor: pointer; transition: all 0.15s; background: none; padding: 0; position: relative; }
	.cover-pick:hover { border-color: var(--accent); transform: scale(1.03); }
	.cover-pick img { width: 100%; height: 70px; object-fit: cover; display: block; }
	.cover-name { display: block; padding: 0.2rem 0.3rem; font-size: 0.6rem; font-weight: 600; color: var(--text-dim); text-align: center; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; background: var(--surface-sunken); }

	/* Image preview */
	.img-preview { position: relative; width: 100%; max-height: 120px; border-radius: 8px; overflow: hidden; border: 1px solid var(--glass-border); }
	.img-preview img { width: 100%; height: 100px; object-fit: cover; display: block; }
	.preview-clear { position: absolute; top: 4px; right: 4px; width: 22px; height: 22px; border-radius: 50%; background: rgba(239,68,68,0.8); color: white; border: none; cursor: pointer; font-size: 0.7rem; display: flex; align-items: center; justify-content: center; }

	/* Toast System */
	.toast-container { position: fixed; top: 1.5rem; right: 1.5rem; z-index: 10000; display: flex; flex-direction: column; gap: 0.75rem; pointer-events: none; }
	.toast { display: flex; align-items: center; gap: 0.75rem; padding: 0.8rem 1.4rem; border-radius: 12px; backdrop-filter: blur(16px); border: 1px solid var(--glass-border); box-shadow: 0 10px 30px rgba(0,0,0,0.4); font-size: 0.88rem; font-weight: 600; pointer-events: auto; min-width: 260px; }
	.toast.success { background: rgba(16, 185, 129, 0.15); border-color: rgba(16, 185, 129, 0.3); color: #10b981; }
	.toast.error { background: rgba(239, 68, 68, 0.15); border-color: rgba(239, 68, 68, 0.3); color: var(--danger); }
	.toast.info { background: rgba(59, 130, 246, 0.15); border-color: rgba(59, 130, 246, 0.3); color: var(--accent); }
	.toast-icon { font-size: 1rem; }
	.toast-msg { flex-grow: 1; }

	.toast-enter { animation: toastIn 0.4s cubic-bezier(0.16, 1, 0.3, 1) forwards; }
	.toast-leave { animation: toastOut 0.4s ease-in forwards; }

	@keyframes toastIn {
		from { opacity: 0; transform: translateX(80px) scale(0.9); }
		to { opacity: 1; transform: translateX(0) scale(1); }
	}
	/* Steps Indicator */
	.steps-indicator { display: flex; gap: 1rem; margin: 1.5rem 0; }
	.steps-indicator span { font-size: 0.8rem; color: var(--text-muted); font-weight: 600; padding: 0.4rem 0.8rem; border-radius: 8px; border: 1px solid var(--glass-border); transition: all 0.2s; }
	.steps-indicator span.active { color: var(--accent); border-color: var(--accent); background: var(--accent-soft); box-shadow: 0 0 10px var(--accent-glow); }

	/* Success animation on create button */
	.btn-success-anim { background: var(--success) !important; box-shadow: 0 4px 14px var(--success-glow) !important; }

	/* Glass hover effect for list items */
	.glass-hover { transition: all 0.2s; }
	.glass-hover:hover { background: var(--hover-tint); border-color: var(--glass-border); }

	@keyframes toastOut {
		from { opacity: 1; transform: translateX(0) scale(1); }
		to { opacity: 0; transform: translateX(80px) scale(0.9); }
	}

	/* Points Config */
	.pts-config { margin-top: 0.75rem; padding: 0.75rem; border-radius: 10px; }
	.pts-config summary { cursor: pointer; font-weight: 700; font-size: 0.8rem; color: var(--text-main); margin-bottom: 0.5rem; }
	.pts-grid { display: grid; grid-template-columns: repeat(5, 1fr); gap: 0.5rem; }
	.pts-field { display: flex; flex-direction: column; gap: 0.2rem; }
	.pts-field label { font-size: 0.6rem; font-weight: 700; color: var(--text-muted); }
	.pts-field input { width: 100%; padding: 0.35rem; text-align: center; font-size: 0.8rem; font-weight: 800; background: var(--surface-sunken); border: 1px solid var(--glass-border); border-radius: 6px; color: var(--accent); }
	.pts-hint { font-size: 0.55rem; color: var(--text-dim); margin-top: 0.4rem; font-style: italic; }
	.score-invert-label { display: flex; align-items: center; gap: 0.5rem; font-size: 0.8rem; font-weight: 600; color: var(--text-main); cursor: pointer; margin: 0.5rem 0; }
	.score-invert-label input[type="checkbox"] { width: 16px; height: 16px; accent-color: var(--accent); cursor: pointer; }

	/* === PLAYERS TABLE === */
	.players-view { border-radius: var(--radius-lg); }
	.players-view h3 { font-size: 1rem; font-weight: 800; display: flex; align-items: center; gap: 0.5rem; }
	.players-table { display: flex; flex-direction: column; gap: 0; border-radius: 10px; overflow: hidden; border: 1px solid var(--glass-border); }
	.pt-header { display: flex; padding: 0.6rem 0.8rem; background: var(--surface-sunken); font-weight: 800; font-size: 0.65rem; text-transform: uppercase; letter-spacing: 0.05em; color: var(--text-muted); border-bottom: 1px solid var(--glass-border); }
	.pt-row { display: flex; padding: 0.55rem 0.8rem; align-items: center; border-bottom: 1px solid rgba(255,255,255,0.03); transition: background 0.15s; }
	.pt-row:hover { background: var(--hover-tint); }
	.pt-row:last-child { border-bottom: none; }
	.pt-row.is-admin { background: rgba(59,130,246,0.06); }
	.pt-col { font-size: 0.8rem; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
	.pt-id { width: 36px; flex-shrink: 0; color: var(--text-muted); font-size: 0.7rem; }
	.pt-name { flex: 3; min-width: 0; font-weight: 700; display: flex; align-items: center; gap: 0.4rem; }
	.pt-team { flex: 2; min-width: 0; color: var(--text-dim); }
	.pt-pts { width: 70px; flex-shrink: 0; text-align: center; font-weight: 800; color: var(--accent); }
	.pt-actions { width: 220px; flex-shrink: 0; display: flex; gap: 0.3rem; align-items: center; justify-content: flex-end; flex-wrap: nowrap; }
	.admin-badge { font-size: 0.6rem; padding: 0.1rem 0.3rem; background: rgba(234,179,8,0.15); color: #eab308; border-radius: 6px; font-weight: 800; }
	.btn-icon { background: var(--hover-tint); border: 1px solid var(--glass-border); border-radius: 6px; padding: 0.25rem 0.4rem; cursor: pointer; font-size: 0.75rem; transition: all 0.15s; flex-shrink: 0; }
	.btn-icon:hover { background: var(--accent-soft); border-color: var(--accent); }
	.btn-icon-danger:hover { border-color: var(--danger, #ef4444); background: rgba(239,68,68,0.15); }
	.btn-danger-sm { background: rgba(239,68,68,0.2); color: #ef4444; border: 1px solid rgba(239,68,68,0.3); border-radius: 6px; padding: 0.2rem 0.5rem; font-size: 0.65rem; font-weight: 700; cursor: pointer; white-space: nowrap; }
	.btn-danger-sm:hover { background: rgba(239,68,68,0.35); }
	.btn-primary-sm { background: rgba(59,130,246,0.2); color: #3b82f6; border: 1px solid rgba(59,130,246,0.3); border-radius: 6px; padding: 0.2rem 0.5rem; font-size: 0.65rem; font-weight: 700; cursor: pointer; white-space: nowrap; }
	.btn-primary-sm:hover { background: rgba(59,130,246,0.35); }
	.btn-warning-sm { background: rgba(245,158,11,0.2); color: #f59e0b; border: 1px solid rgba(245,158,11,0.3); border-radius: 6px; padding: 0.2rem 0.5rem; font-size: 0.65rem; font-weight: 700; cursor: pointer; white-space: nowrap; }
	.btn-warning-sm:hover { background: rgba(245,158,11,0.35); }
	.mb-3 { margin-bottom: 0.75rem; }
	.mb-4 { margin-bottom: 1rem; }
	.t-count { font-size: 0.65rem; background: var(--accent-soft); color: var(--accent); padding: 0.1rem 0.4rem; border-radius: 10px; font-weight: 800; border: 1px solid rgba(59,130,246,0.15); }
	.p-8 { padding: 1.5rem; }
	.gap-2 { gap: 0.5rem; }
	.btn-sm { font-size: 0.7rem; padding: 0.35rem 0.7rem; border-radius: 8px; font-weight: 700; white-space: nowrap; }
	.btn-dev { background: rgba(168,85,247,0.15); color: #a855f7; border: 1px solid rgba(168,85,247,0.3); cursor: pointer; transition: all 0.15s; }
	.btn-dev:hover { background: rgba(168,85,247,0.3); border-color: #a855f7; }
	.btn-dev:disabled { opacity: 0.5; cursor: not-allowed; }
	.create-player-form { padding: 1rem; margin-bottom: 1rem; border-radius: 10px; border: 1px solid var(--glass-border); animation: slideDown 0.2s ease; }
	.cpf-grid { display: grid; grid-template-columns: 1fr 1fr 1fr auto; gap: 0.75rem; align-items: end; }
	.cpf-submit { display: flex; align-items: flex-end; }
	.cpf-submit button { height: 38px; }
	@keyframes slideDown { from { opacity: 0; transform: translateY(-8px); } to { opacity: 1; transform: translateY(0); } }


	/* Inline Edit Panel */
	.card-top-row { display: flex; align-items: center; gap: 1rem; }
	.editing-expanded { border-color: var(--accent) !important; background: rgba(59,130,246,0.03) !important; }
	.inline-edit-panel { padding: 1rem 0 0; border-top: 1px solid var(--glass-border); margin-top: 1rem; display: flex; flex-direction: column; gap: 0.75rem; animation: slideDown 0.2s ease-out; }
	@keyframes slideDown { from { opacity: 0; max-height: 0; } to { opacity: 1; max-height: 500px; } }
	.ie-grid { display: grid; grid-template-columns: 2fr 1fr; gap: 0.75rem; }
	.ie-field { display: flex; flex-direction: column; gap: 0.3rem; }
	.ie-field label { font-size: 0.65rem; font-weight: 700; color: var(--text-dim); text-transform: uppercase; letter-spacing: 0.05em; }
	.ie-row { display: flex; gap: 0.75rem; align-items: flex-start; }
	.ie-actions { display: flex; justify-content: flex-end; gap: 0.5rem; padding-top: 0.5rem; border-top: 1px solid var(--glass-border); }
	.btn-icon-edit.active { background: rgba(59,130,246,0.2); color: var(--accent); border-color: var(--accent); }
	.pts-config { border: 1px solid var(--glass-border); border-radius: 10px; padding: 0.75rem; margin-top: 0.5rem; }
	.pts-config summary { font-size: 0.7rem; font-weight: 700; cursor: pointer; color: var(--text-dim); }
	.pts-grid { display: grid; grid-template-columns: repeat(5, 1fr); gap: 0.5rem; margin-top: 0.5rem; }
	.pts-field { display: flex; flex-direction: column; gap: 0.2rem; text-align: center; }
	.pts-field label { font-size: 0.6rem; font-weight: 700; color: var(--text-dim); }
	.pts-field input { text-align: center; padding: 0.3rem; font-size: 0.75rem; }
	.pts-hint { font-size: 0.6rem; color: var(--text-dim); font-style: italic; margin-top: 0.3rem; }
	/* === DANGER ZONE === */
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
	.btn-sentinel { padding: 0.4rem 0.9rem; font-size: 0.7rem; font-weight: 700; color: #a855f7; background: rgba(168,85,247,0.1); border: 1px solid rgba(168,85,247,0.3); border-radius: 8px; cursor: pointer; transition: all 0.2s; white-space: nowrap; }
	.btn-sentinel:hover { background: rgba(168,85,247,0.25); border-color: #a855f7; box-shadow: 0 0 12px rgba(168,85,247,0.2); }
	.admin-conv-md :global(p) { margin: 0.3em 0; }
	.admin-conv-md :global(p:first-child) { margin-top: 0; }
	.admin-conv-md :global(p:last-child) { margin-bottom: 0; }
	.admin-conv-md :global(code) { background: rgba(0,0,0,0.3); padding: 0.1em 0.3em; border-radius: 4px; font-size: 0.85em; }
	.admin-conv-md :global(pre) { background: rgba(0,0,0,0.35); border: 1px solid rgba(255,255,255,0.08); border-radius: 8px; padding: 0.6em; overflow-x: auto; margin: 0.4em 0; }
	.admin-conv-md :global(pre code) { background: none; padding: 0; }
	.admin-conv-md :global(strong) { font-weight: 600; }
	.admin-conv-md :global(ul), .admin-conv-md :global(ol) { margin: 0.3em 0; padding-left: 1.3em; }
	.admin-conv-md :global(blockquote) { border-left: 3px solid var(--accent); padding: 0.2em 0.6em; margin: 0.3em 0; opacity: 0.85; }
	.btn-attach { background: var(--hover-tint); border: 1px solid var(--glass-border); color: var(--text-dim); width: 36px; height: 36px; border-radius: 6px; cursor: pointer; font-size: 1rem; display: flex; align-items: center; justify-content: center; transition: all 0.2s; flex-shrink: 0; }
	.btn-attach:hover { background: var(--accent-soft); border-color: var(--accent); color: var(--accent); }
	.ia-blocked-badge { font-size: 0.7rem; margin-left: 0.3rem; opacity: 0.8; }
	/* Prompt Preview Panel */
	.prompt-preview-panel { margin-top: 0.75rem; border: 1px solid rgba(139,92,246,0.25); border-radius: 12px; background: rgba(139,92,246,0.04); overflow: hidden; animation: slideDown 0.2s ease-out; }
	.prompt-preview-header { display: flex; justify-content: space-between; align-items: center; padding: 0.6rem 0.8rem; background: rgba(139,92,246,0.08); border-bottom: 1px solid rgba(139,92,246,0.15); font-size: 0.75rem; font-weight: 700; color: #a78bfa; }
	.prompt-token-badge { font-size: 0.6rem; font-weight: 800; background: rgba(139,92,246,0.15); color: #a78bfa; padding: 0.15rem 0.5rem; border-radius: 6px; border: 1px solid rgba(139,92,246,0.25); }
	.prompt-preview-textarea { width: 100%; min-height: 200px; max-height: 400px; background: var(--surface-sunken); border: none; padding: 0.8rem; color: var(--text-main); font-size: 0.75rem; font-family: 'Courier New', monospace; line-height: 1.5; resize: vertical; }
	.prompt-preview-textarea:focus { outline: none; }
	/* RAG Knowledge List */
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
	.rag-vectorize-anim {
		position: relative; margin-top: 0.5rem; padding: 0.6rem 0.8rem;
		border-radius: 8px; overflow: hidden;
		background: rgba(99,102,241,0.06); border: 1px solid rgba(99,102,241,0.15);
	}
	.rag-vectorize-bar {
		position: absolute; top: 0; left: 0; height: 100%; width: 40%;
		background: linear-gradient(90deg, transparent, rgba(99,102,241,0.15), rgba(139,92,246,0.2), rgba(99,102,241,0.15), transparent);
		animation: rag-sweep 1.8s ease-in-out infinite;
		border-radius: 8px;
	}
	.rag-vectorize-label {
		position: relative; z-index: 1; font-size: 0.72rem; font-weight: 600;
		color: #a78bfa; display: flex; align-items: center; gap: 0.4rem;
		animation: rag-pulse-text 2s ease-in-out infinite;
	}
	@keyframes rag-sweep {
		0%   { left: -40%; }
		100% { left: 100%; }
	}
	@keyframes rag-pulse-text {
		0%, 100% { opacity: 0.7; }
		50%      { opacity: 1; }
	}
	.rag-empty { display: flex; flex-direction: column; align-items: center; gap: 0.3rem; padding: 1.5rem; color: var(--text-muted); font-size: 0.8rem; }
	.rag-empty span { font-size: 1.5rem; opacity: 0.5; }
	.rag-empty p { margin: 0; }
	.rag-add-section { margin-top: 0.75rem; padding-top: 0.75rem; border-top: 1px solid var(--glass-border); display: flex; flex-direction: column; }

	/* Queue admin panel (G-52) */
	.queue-stats-badges { display: flex; gap: 0.4rem; }
	.queue-stat-badge {
		font-size: 0.65rem; font-weight: 700; padding: 0.15rem 0.5rem;
		border-radius: 6px; font-family: monospace;
	}
	.queue-stat-badge.pending { background: rgba(245,158,11,0.12); color: #f59e0b; border: 1px solid rgba(245,158,11,0.3); }
	.queue-stat-badge.active { background: rgba(16,185,129,0.12); color: #10b981; border: 1px solid rgba(16,185,129,0.3); }
	.queue-stat-badge.avg { background: rgba(99,102,241,0.12); color: #818cf8; border: 1px solid rgba(99,102,241,0.3); }
	.queue-section-label { font-size: 0.7rem; font-weight: 700; color: var(--text-muted); text-transform: uppercase; letter-spacing: 0.05em; margin-bottom: 0.4rem; }
	.queue-row {
		display: flex; align-items: center; gap: 0.6rem;
		padding: 0.5rem 0.6rem; border-radius: 8px;
		background: var(--hover-tint); border: 1px solid transparent;
		margin-bottom: 0.3rem; transition: all 0.2s;
	}
	.queue-row:hover { border-color: var(--glass-border); }
	.queue-row.active { background: rgba(16,185,129,0.06); border: 1px solid rgba(16,185,129,0.2); }
	.queue-row-pos { font-size: 0.7rem; font-weight: 800; color: var(--accent); min-width: 1.5rem; }
	.queue-row-type { font-size: 0.85rem; }
	.queue-row-user { flex: 1; font-size: 0.8rem; font-weight: 600; color: var(--text-main); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
	.queue-row-type-label { font-size: 0.65rem; color: var(--text-muted); padding: 0.1rem 0.4rem; background: var(--surface-sunken); border-radius: 4px; }
	.queue-row-time { font-size: 0.65rem; color: var(--text-dim); font-family: monospace; min-width: 2.5rem; text-align: right; }
	.queue-cancel-btn {
		background: none; border: 1px solid rgba(239,68,68,0.2);
		color: var(--text-muted); border-radius: 6px; padding: 0.15rem 0.4rem;
		font-size: 0.6rem; cursor: pointer; transition: all 0.2s;
	}
	.queue-cancel-btn:hover { background: rgba(239,68,68,0.15); color: #ef4444; border-color: rgba(239,68,68,0.4); }
	.queue-empty { text-align: center; padding: 1rem; font-size: 0.8rem; color: var(--text-muted); }

	/* Double confirmation delete game modal */
	.danger-warning-box {
		background: rgba(239, 68, 68, 0.06);
		border: 1px solid rgba(239, 68, 68, 0.25);
		border-radius: 12px;
		padding: 1.2rem;
		margin: 1rem 0;
	}
	.danger-warning-box strong.warn-title {
		color: #ef4444;
		font-size: 0.95rem;
		display: block;
		margin-bottom: 0.5rem;
	}
	.danger-warning-box ul {
		margin: 0.8rem 0;
		padding-left: 1.5rem;
	}
	.danger-warning-box li {
		color: var(--text-main);
		font-size: 0.8rem;
		margin-bottom: 0.3rem;
	}
	.status-badge {
		font-size: 0.65rem;
		font-weight: 700;
		padding: 0.1rem 0.35rem;
		border-radius: 4px;
		text-transform: uppercase;
		margin-left: 0.3rem;
	}
	.status-badge.open { background: rgba(59,130,246,0.15); color: #3b82f6; }
	.status-badge.running { background: rgba(16,185,129,0.15); color: #10b981; }
	.status-badge.done { background: rgba(139,92,246,0.15); color: #8b5cf6; }
	.status-badge.closed { background: rgba(107,114,128,0.15); color: #9ca3af; }
	
	.warning-text {
		font-size: 0.8rem;
		color: var(--text-dim);
		margin-top: 0.8rem;
	}
	.consequence-badges {
		display: flex;
		flex-wrap: wrap;
		gap: 0.4rem;
		margin-top: 0.5rem;
	}
	.c-badge {
		font-size: 0.65rem;
		font-weight: 700;
		padding: 0.25rem 0.6rem;
		border-radius: 6px;
		background: rgba(239, 68, 68, 0.12);
		color: #fca5a5;
		border: 1px solid rgba(239, 68, 68, 0.2);
	}
	.confirm-checkbox-label {
		display: flex;
		align-items: flex-start;
		gap: 0.6rem;
		margin: 1.2rem 0;
		cursor: pointer;
		font-size: 0.8rem;
		color: var(--text-main);
		user-select: none;
		line-height: 1.4;
	}
	.confirm-checkbox-label input[type="checkbox"] {
		margin-top: 0.2rem;
		cursor: pointer;
	}
	.admin-avatar-small {
		width: 24px;
		height: 24px;
		border-radius: 50%;
		overflow: hidden;
		flex-shrink: 0;
		border: 1px solid var(--glass-border);
	}
	.admin-avatar-small img {
		width: 100%;
		height: 100%;
		object-fit: cover;
		border-radius: 50%;
	}
	.admin-avatar-lg {
		width: 50px;
		height: 50px;
		border-radius: 50%;
		overflow: hidden;
		flex-shrink: 0;
		border: 1px solid var(--accent-soft);
	}
	.admin-avatar-lg img {
		width: 100%;
		height: 100%;
		object-fit: cover;
		border-radius: 50%;
	}
	
	/* EasyMDE theme overrides for dark mode */
	.editor-container :global(.EasyMDEContainer) {
		background: transparent;
		border: 1px solid var(--glass-border);
		border-radius: 8px;
		overflow: hidden;
	}
	.editor-container :global(.EasyMDEContainer .CodeMirror) {
		background: var(--bg-secondary, #0f172a);
		color: var(--text-main, white);
		border: none;
		border-radius: 0;
		font-size: 0.8rem;
	}
	.editor-container :global(.editor-toolbar) {
		background: var(--hover-tint, rgba(255,255,255,0.03));
		border: none;
		border-bottom: 1px solid var(--glass-border);
		opacity: 1;
		padding: 4px;
	}
	.editor-container :global(.editor-toolbar button) {
		color: var(--text-dim, #94a3b8) !important;
		border: none !important;
		width: 26px !important;
		height: 26px !important;
	}
	.editor-container :global(.editor-toolbar button:hover),
	.editor-container :global(.editor-toolbar button.active) {
		background: var(--accent-soft, rgba(59,130,246,0.15)) !important;
		color: var(--accent, #3b82f6) !important;
		border-radius: 4px;
	}
	.editor-container :global(.editor-toolbar i.separator) {
		border-left-color: var(--glass-border) !important;
	}
	.editor-container :global(.CodeMirror-cursor) { border-left-color: var(--accent, #3b82f6); }
	.editor-container :global(.CodeMirror-selected) { background: var(--accent-soft, rgba(59,130,246,0.2)) !important; }
	.editor-container :global(.editor-preview) {
		background: var(--bg-secondary, #0f172a);
		color: var(--text-main, white);
	}
	.editor-container :global(.editor-preview-side) {
		background: var(--bg-secondary, #0f172a);
		color: var(--text-main, white);
		border-left: 1px solid var(--glass-border);
	}
</style>

