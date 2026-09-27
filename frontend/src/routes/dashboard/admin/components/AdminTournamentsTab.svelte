<script>
	import { get } from 'svelte/store';
	import { onMount } from 'svelte';
	import { api } from '$lib/api';
	import { API_URL } from '$lib/config';
	import { t } from '$lib/i18nStore';
	import CreateTournamentWizard from '$lib/components/CreateTournamentWizard.svelte';
	import EditTournamentModal from '$lib/components/EditTournamentModal.svelte';
	import AddGameModal from '$lib/components/AddGameModal.svelte';

	export let games = [];
	export let tournaments = [];
	export let onReload = () => {};
	export let toast = (msg, type) => {};

	let EasyMDE = null;
	let editGameEditorInstance = null;
	let showAddGameModal = false;
	let overlayMouseDown = false;

	// Tournament Editing
	let editingTournament = null;
	let editConfig = {};
	let deleteConfirmTournamentId = null;

	// AI Prompt preview
	let promptPreviewId = null;
	let promptPreviewText = '';
	let promptPreviewTokens = 0;
	let loadingPreview = false;

	// Game management
	let deleteConfirmGameId = null;
	let gameToDeleteWithTournaments = null;
	let deleteGameCheckboxConfirmed = false;
	let editingGame = null;
	let editGameData = {};
	let gameImageMode = 'search';
	let searchQuery = '';
	let searchResults = [];
	let searching = false;
	let searxngNotConfigured = false;

	function handleKeydown(e) {
		if (e.key === 'Escape') {
			if (editingGame) editingGame = null;
			else if (gameToDeleteWithTournaments) gameToDeleteWithTournaments = null;
			else if (editingTournament) editingTournament = null;
		}
	}

	onMount(async () => {
		try {
			const mod = await import('easymde');
			EasyMDE = mod.default;
		} catch (e) {
			console.error("Failed to load EasyMDE", e);
		}
	});

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

	function openEditTournament(tItem) {
		editingTournament = tItem;
		editConfig = {
			name: tItem.name,
			game_id: tItem.game_id,
			status: tItem.status,
			points_per_win: tItem.points_per_win || 3,
			use_teams: tItem.config?.use_teams || false,
			team_size: tItem.config?.team_size || 1,
			phases: tItem.config?.phases || 'single',
			group_size: tItem.config?.group_size || 4,
			advancers_count: tItem.config?.advancers_count || 2,
			bracket_type: tItem.config?.bracket_type || 'single_elim',
			pts_winner: tItem.config?.pts_winner ?? 1.5,
			pts_second: tItem.config?.pts_second ?? 1.3,
			pts_third: tItem.config?.pts_third ?? 1.0,
			pts_participation: tItem.config?.pts_participation ?? 1.0,
			pts_per_match: tItem.config?.pts_per_match ?? 0.5,
			lower_score_is_better: tItem.config?.lower_score_is_better || false,
			boolean_mode: tItem.config?.boolean_mode || false,
			allow_draws: tItem.config?.allow_draws || false,
			meet_twice: tItem.config?.meet_twice || false,
			ffa_group_size: tItem.config?.ffa_group_size || 4,
			ffa_advancers: tItem.config?.ffa_advancers || 2
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
			onReload();
		} catch (e) { toast(e.message, 'error'); }
	}

	async function deleteTournament(id) {
		try {
			await api.delete(`/tournaments/${id}`);
			deleteConfirmTournamentId = null;
			toast(get(t)('admin_toast_tournament_deleted') || 'Tournoi supprimé', 'success');
			onReload();
		} catch (e) { toast(e.message, 'error'); }
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

	async function deleteGame(id, force = false) {
		try {
			await api.delete(`/tournaments/games/${id}${force ? '?force=true' : ''}`);
			deleteConfirmGameId = null;
			gameToDeleteWithTournaments = null;
			deleteGameCheckboxConfirmed = false;
			onReload();
			toast(get(t)('admin_toast_game_deleted'), 'success');
		} catch (e) {
			if (e.message && e.message.includes('confirmer la suppression')) {
				const g = games.find(game => game.id === id);
				const freshTournaments = await api.get('/tournaments');
				const affected = freshTournaments.filter(tItem => tItem.game_id && Number(tItem.game_id) === Number(id));
				gameToDeleteWithTournaments = { game: g, tournaments: affected };
				deleteGameCheckboxConfirmed = false;
			} else {
				toast(e.message || 'Erreur de suppression', 'error');
			}
		}
	}

	function attemptDeleteGame(g) {
		deleteGame(g.id);
	}

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
			onReload();
		} catch (e) { toast(e.message, 'error'); }
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

<svelte:window on:keydown={handleKeydown} />

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
				onReload();
			}} 
			onGameCreated={async () => {
				await onReload();
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
					<div class="admin-item-card glass-hover">
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
									{games.find(g => g.id === tourney.game_id)?.name || '—'} • {tourney.participants?.length || 0} Joueur{(tourney.participants?.length || 0) > 1 ? 's' : ''} • 🥇{tourney.config?.pts_winner ?? 1.5}/🥈{tourney.config?.pts_second ?? 1.3}/🥉{tourney.config?.pts_third ?? 1.0} 👤{tourney.config?.pts_participation ?? 1.0}/m ⚡{tourney.config?.pts_per_match ?? 0.5}
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
	<!-- svelte-ignore a11y-no-noninteractive-element-interactions -->
	<!-- svelte-ignore a11y-click-events-have-key-events -->
	<div class="modal-overlay-global" use:portal role="dialog" aria-modal="true"
		on:mousedown={(e) => { if (e.target === e.currentTarget) overlayMouseDown = true; }} 
		on:mouseup={(e) => { if (overlayMouseDown && e.target === e.currentTarget) gameToDeleteWithTournaments = null; overlayMouseDown = false; }}>
		<div class="modal-card-global glass" on:click|stopPropagation style="max-width: 480px">
			<header class="edit-modal-header danger-zone" style="border-bottom: 1px solid rgba(239, 68, 68, 0.25);">
				<h3>⚠️ Suppression Critique</h3>
				<button class="close-btn" on:click={() => gameToDeleteWithTournaments = null} aria-label="Fermer">✕</button>
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
							{#each gameToDeleteWithTournaments.tournaments as tItem}
								<li>
									<strong>{tItem.name}</strong>
									<span class="status-badge {tItem.status.toLowerCase()}">
										{tItem.status === 'OPEN' ? 'Ouvert' : tItem.status === 'RUNNING' ? 'En cours' : tItem.status === 'DONE' ? 'Terminé' : 'Clôturé'}
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
	<!-- svelte-ignore a11y-no-noninteractive-element-interactions -->
	<!-- svelte-ignore a11y-click-events-have-key-events -->
	<div class="modal-overlay-global" use:portal role="dialog" aria-modal="true"
		on:mousedown={(e) => { if (e.target === e.currentTarget) overlayMouseDown = true; }} 
		on:mouseup={(e) => { if (overlayMouseDown && e.target === e.currentTarget) editingGame = null; overlayMouseDown = false; }}>
		<div class="modal-card-global glass" on:click|stopPropagation>
			<header class="edit-modal-header">
				<h3>✏️ Éditer — {editingGame.name}</h3>
				<button class="close-btn" on:click={() => editingGame = null} aria-label="Fermer">✕</button>
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
							<input type="file" class="mt-2" accept="image/*" on:change={handleFileUpload} />
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
	on:success={() => onReload()}
	on:toast={(e) => toast(e.detail.message, e.detail.type)}
/>

<style>
	.admin-grid { display: grid; grid-template-columns: minmax(380px, 1fr) 2fr; gap: 2rem; }
	.wizard { padding: 2rem; min-height: 500px; display: flex; flex-direction: column; }
	.list { padding: 2rem; display: flex; flex-direction: column; }
	.list-header { display: flex; justify-content: space-between; align-items: center; padding-bottom: 1rem; margin-bottom: 1rem; border-bottom: 1px solid var(--glass-border); }
	.list-icon { width: 40px; height: 40px; display: flex; align-items: center; justify-content: center; font-size: 1.4rem; background: var(--accent-soft); border-radius: 10px; border: 1px solid rgba(59,130,246,0.15); }
	.badge-count { font-size: 0.7rem; background: var(--accent-soft); color: var(--accent); padding: 0.2rem 0.6rem; border-radius: 4px; font-weight: 800; border: 1px solid var(--accent); }
	.admin-item-card { display: flex; flex-direction: column; gap: 0.5rem; padding: 1rem; border-radius: 12px; margin-bottom: 0.75rem; border: 1px solid var(--glass-border); transition: all 0.2s; }
	.admin-item-card:hover { border-color: var(--accent); background: rgba(59, 130, 246, 0.05); }
	.card-top-row { display: flex; align-items: center; gap: 1rem; }
	.game-mini-thumb { width: 50px; height: 50px; border-radius: 8px; background-size: cover; background-position: center; border: 1px solid var(--glass-border); flex-shrink: 0; }
	.thumb-placeholder { display: flex; align-items: center; justify-content: center; width: 100%; height: 100%; font-size: 1.2rem; background: var(--surface-sunken); border-radius: 8px; }
	.item-info { flex-grow: 1; min-width: 0; }
	.item-name { font-weight: 700; font-size: 1rem; }
	.item-meta { font-size: 0.75rem; color: var(--text-dim); margin-top: 0.2rem; }
	.item-actions { display: flex; flex-direction: row; gap: 0.4rem; align-items: center; flex-shrink: 0; }
	.status-pill-sm { font-size: 0.6rem; font-weight: 700; text-transform: uppercase; letter-spacing: 0.05em; padding: 0.15rem 0.5rem; border-radius: 20px; }
	.status-pill-sm.open { background: rgba(34,197,94,0.1); color: var(--success); border: 1px solid rgba(34,197,94,0.2); }
	.status-pill-sm.running { background: var(--accent-soft); color: var(--accent); border: 1px solid rgba(59,130,246,0.2); }
	.status-pill-sm.done { background: rgba(100,116,139,0.1); color: var(--text-muted); border: 1px solid rgba(100,116,139,0.2); }
	.status-pill-sm.closed { background: rgba(139,92,246,0.1); color: #a78bfa; border: 1px solid rgba(139,92,246,0.2); }
	.btn-icon-edit { background: rgba(255, 255, 255, 0.05); border: 1px solid var(--glass-border); color: var(--text-muted); cursor: pointer; padding: 0.6rem; border-radius: 8px; transition: all 0.2s; display: flex; align-items: center; justify-content: center; }
	.btn-icon-edit:hover { background: rgba(59, 130, 246, 0.2); color: var(--accent); border-color: var(--accent); }
	.btn-icon-danger { background: rgba(255, 255, 255, 0.05); border: 1px solid var(--glass-border); color: var(--text-muted); cursor: pointer; padding: 0.6rem; border-radius: 8px; transition: all 0.2s; display: flex; align-items: center; justify-content: center; }
	.btn-icon-danger:hover { background: rgba(239, 68, 68, 0.2); color: var(--danger); border-color: var(--danger); }
	.confirm-delete-row { display: flex; align-items: center; gap: 0.4rem; background: rgba(239,68,68,0.05); padding: 0.3rem 0.5rem; border-radius: 8px; border: 1px dashed rgba(239,68,68,0.2); }
	.btn-danger-sm { background: rgba(239,68,68,0.2); color: #ef4444; border: 1px solid rgba(239,68,68,0.3); border-radius: 6px; padding: 0.2rem 0.5rem; font-size: 0.65rem; font-weight: 700; cursor: pointer; white-space: nowrap; }
	.btn-danger-sm:hover { background: rgba(239,68,68,0.35); }
	.empty-list { display: flex; flex-direction: column; align-items: center; justify-content: center; padding: 3rem 1rem; gap: 0.5rem; }
	.empty-icon { font-size: 2.5rem; opacity: 0.5; }
	.empty-list p { color: var(--text-dim); font-weight: 600; margin: 0; }
	.game-gallery { display: grid; grid-template-columns: repeat(auto-fill, minmax(140px, 1fr)); gap: 1rem; margin-top: 1rem; }
	.game-card { overflow: hidden; border: 1px solid var(--glass-border); border-radius: 12px; transition: all 0.2s; }
	.game-card:hover { border-color: var(--accent); transform: translateY(-2px); }
	.game-thumb { height: 95px; background-size: cover; background-position: center; position: relative; display: flex; align-items: center; justify-content: center; }
	.game-info { padding: 0.5rem; text-align: center; font-size: 0.78rem; font-weight: 600; }
	.game-empty { grid-column: 1 / -1; padding: 2rem; text-align: center; }
	.game-card-actions { position: absolute; inset: 0; background: rgba(0,0,0,0.6); display: flex; align-items: center; justify-content: center; gap: 0.3rem; opacity: 0; transition: opacity 0.2s; }
	.game-card:hover .game-card-actions { opacity: 1; }
	.game-action-btn { width: 28px; height: 28px; border: 1px solid rgba(255,255,255,0.2); border-radius: 6px; background: rgba(0,0,0,0.5); color: white; cursor: pointer; font-size: 0.7rem; display: flex; align-items: center; justify-content: center; transition: all 0.15s; }
	.game-action-btn.edit:hover { background: rgba(59,130,246,0.4); border-color: var(--accent); }
	.game-action-btn.delete:hover { background: rgba(239,68,68,0.4); border-color: var(--danger); }
	.game-action-btn.confirm { background: rgba(239,68,68,0.5); border-color: var(--danger); }
	.game-action-btn.cancel { background: rgba(100,116,139,0.4); }
	.img-mode-tabs { display: flex; gap: 0.3rem; }
	.img-tab { padding: 0.35rem 0.7rem; font-size: 0.7rem; font-weight: 600; border: 1px solid var(--glass-border); border-radius: 8px; background: var(--hover-tint); color: var(--text-dim); cursor: pointer; transition: all 0.15s; }
	.img-tab:hover { border-color: var(--accent); }
	.img-tab.active { background: var(--accent-soft); border-color: var(--accent); color: var(--accent); }
	.search-bar { display: flex; gap: 0.4rem; }
	.search-bar input { flex-grow: 1; }
	.btn-sm { padding: 0.4rem 0.8rem; font-size: 0.75rem; }
	.cover-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(110px, 1fr)); gap: 0.5rem; max-height: 220px; overflow-y: auto; }
	.cover-pick { overflow: hidden; border: 2px solid var(--glass-border); border-radius: 8px; cursor: pointer; transition: all 0.15s; background: none; padding: 0; position: relative; }
	.cover-pick:hover { border-color: var(--accent); transform: scale(1.03); }
	.cover-pick img { width: 100%; height: 70px; object-fit: cover; display: block; }
	.cover-name { display: block; padding: 0.2rem 0.3rem; font-size: 0.6rem; font-weight: 600; color: var(--text-dim); text-align: center; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; background: var(--surface-sunken); }
	.img-preview { position: relative; width: 100%; max-height: 120px; border-radius: 8px; overflow: hidden; border: 1px solid var(--glass-border); }
	.img-preview img { width: 100%; height: 100px; object-fit: cover; display: block; }
	.preview-clear { position: absolute; top: 4px; right: 4px; width: 22px; height: 22px; border-radius: 50%; background: rgba(239,68,68,0.8); color: white; border: none; cursor: pointer; font-size: 0.7rem; display: flex; align-items: center; justify-content: center; }
	.prompt-preview-panel { margin-top: 0.75rem; border: 1px solid rgba(139,92,246,0.25); border-radius: 12px; background: rgba(139,92,246,0.04); overflow: hidden; }
	.prompt-preview-header { display: flex; justify-content: space-between; align-items: center; padding: 0.6rem 0.8rem; background: rgba(139,92,246,0.08); border-bottom: 1px solid rgba(139,92,246,0.15); font-size: 0.75rem; font-weight: 700; color: #a78bfa; }
	.prompt-token-badge { font-size: 0.6rem; font-weight: 800; background: rgba(139,92,246,0.15); color: #a78bfa; padding: 0.15rem 0.5rem; border-radius: 6px; border: 1px solid rgba(139,92,246,0.25); }
	.prompt-preview-textarea { width: 100%; min-height: 200px; max-height: 400px; background: var(--surface-sunken); border: none; padding: 0.8rem; color: var(--text-main); font-size: 0.75rem; font-family: 'Courier New', monospace; line-height: 1.5; resize: vertical; }
	.prompt-preview-textarea:focus { outline: none; }
	.danger-warning-box { background: rgba(239, 68, 68, 0.06); border: 1px solid rgba(239, 68, 68, 0.25); border-radius: 12px; padding: 1.2rem; margin: 1rem 0; }
	.danger-warning-box strong.warn-title { color: #ef4444; font-size: 0.95rem; display: block; margin-bottom: 0.5rem; }
	.danger-warning-box ul { margin: 0.8rem 0; padding-left: 1.5rem; }
	.danger-warning-box li { color: var(--text-main); font-size: 0.8rem; margin-bottom: 0.3rem; }
	.status-badge { font-size: 0.65rem; font-weight: 700; padding: 0.1rem 0.35rem; border-radius: 4px; text-transform: uppercase; margin-left: 0.3rem; }
	.status-badge.open { background: rgba(59,130,246,0.15); color: #3b82f6; }
	.status-badge.running { background: rgba(16,185,129,0.15); color: #10b981; }
	.status-badge.done { background: rgba(139,92,246,0.15); color: #8b5cf6; }
	.status-badge.closed { background: rgba(107,114,128,0.15); color: #9ca3af; }
	.warning-text { font-size: 0.8rem; color: var(--text-dim); margin-top: 0.8rem; }
	.consequence-badges { display: flex; flex-wrap: wrap; gap: 0.4rem; margin-top: 0.5rem; }
	.c-badge { font-size: 0.65rem; font-weight: 700; padding: 0.25rem 0.6rem; border-radius: 6px; background: rgba(239, 68, 68, 0.12); color: #fca5a5; border: 1px solid rgba(239, 68, 68, 0.2); }
	.confirm-checkbox-label { display: flex; align-items: flex-start; gap: 0.6rem; margin: 1.2rem 0; cursor: pointer; font-size: 0.8rem; color: var(--text-main); user-select: none; line-height: 1.4; }
	.confirm-checkbox-label input[type="checkbox"] { margin-top: 0.2rem; cursor: pointer; }
	.edit-modal-header { display: flex; justify-content: space-between; align-items: center; padding: 1.2rem 1.5rem; border-bottom: 1px solid var(--glass-border); background: rgba(59,130,246,0.08); }
	.edit-modal-header h3 { font-size: 1rem; margin: 0; }
	.close-btn { background: none; border: none; color: var(--text-dim); cursor: pointer; font-size: 1.2rem; padding: 0.2rem; }
	.edit-modal-body { padding: 1.5rem; }
	.edit-modal-footer { display: flex; justify-content: flex-end; gap: 0.75rem; padding: 1rem 1.5rem; border-top: 1px solid var(--glass-border); }
	.edit-field { display: flex; flex-direction: column; gap: 0.4rem; }
	.edit-field.full-width { grid-column: 1 / -1; }
	.edit-field label { font-size: 0.75rem; font-weight: 700; color: var(--text-dim); text-transform: uppercase; letter-spacing: 0.05em; }
	.editor-container :global(.EasyMDEContainer) { background: transparent; border: 1px solid var(--glass-border); border-radius: 8px; overflow: hidden; }
	.editor-container :global(.EasyMDEContainer .CodeMirror) { background: var(--bg-secondary, #0f172a); color: var(--text-main, white); border: none; border-radius: 0; font-size: 0.8rem; }
	.editor-container :global(.editor-toolbar) { background: var(--hover-tint, rgba(255,255,255,0.03)); border: none; border-bottom: 1px solid var(--glass-border); opacity: 1; padding: 4px; }
	.editor-container :global(.editor-toolbar button) { color: var(--text-dim, #94a3b8) !important; border: none !important; width: 26px !important; height: 26px !important; }
	.editor-container :global(.editor-toolbar button:hover), .editor-container :global(.editor-toolbar button.active) { background: var(--accent-soft, rgba(59,130,246,0.15)) !important; color: var(--accent, #3b82f6) !important; border-radius: 4px; }
</style>
