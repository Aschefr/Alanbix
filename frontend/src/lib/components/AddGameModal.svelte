<script>
	import { t } from '$lib/i18nStore';
	import { api } from '$lib/api';
	import { API_URL } from '$lib/config';
	import { get } from 'svelte/store';
	import { createEventDispatcher, onMount } from 'svelte';

	export let show = false;

	const dispatch = createEventDispatcher();

	let newGame = { name: '', rules: '', image_url: '' };
	let gameImageMode = 'search'; // 'url' | 'search' | 'upload'
	let searchQuery = '';
	let searchResults = [];
	let searching = false;
	let overlayMouseDown = false;

	let searxngNotConfigured = false;

	async function searchCovers() {
		if (!searchQuery.trim()) return;
		searching = true;
		searxngNotConfigured = false;
		try {
			const res = await api.get(`/tournaments/games/search-covers?q=${encodeURIComponent(searchQuery)}`);
			searchResults = res.results || [];
			searxngNotConfigured = !!res.not_configured;
		} catch {
			searchResults = [];
		}
		searching = false;
	}

	function pickCover(url) {
		newGame.image_url = url;
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
				method: 'POST',
				body: formData,
				headers: { 'Authorization': `Bearer ${token}` }
			});
			const data = await res.json();
			newGame.image_url = `${API_URL}${data.url}`;
			dispatch('toast', { message: get(t)('admin_toast_image_uploaded') || 'Image téléversée !', type: 'success' });
		} catch (err) {
			dispatch('toast', { message: (get(t)('admin_toast_upload_error') || 'Erreur d\'envoi: ') + err.message, type: 'error' });
		}
	}

	async function createGame() {
		try {
			const res = await api.post('/tournaments/games', newGame);
			dispatch('success', res);
			closeModal();
		} catch (e) {
			dispatch('toast', { message: e.message || 'Erreur lors de la création du jeu', type: 'error' });
		}
	}

	function closeModal() {
		newGame = { name: '', rules: '', image_url: '' };
		searchQuery = '';
		searchResults = [];
		gameImageMode = 'search';
		dispatch('close');
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

	let EasyMDE = null;
	let editorInstance = null;

	onMount(async () => {
		try {
			const mod = await import('easymde');
			EasyMDE = mod.default;
		} catch (e) {
			console.error("Failed to load EasyMDE", e);
		}
	});

	function setupEditor(node, currentRules) {
		if (!EasyMDE) return;
		
		editorInstance = new EasyMDE({
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
		
		editorInstance.codemirror.on('change', () => {
			newGame.rules = editorInstance.value();
		});

		return {
			update(newRules) {
				if (editorInstance && editorInstance.value() !== newRules) {
					editorInstance.value(newRules || '');
				}
			},
			destroy() {
				if (editorInstance) {
					editorInstance.toTextArea();
					editorInstance = null;
				}
			}
		};
	}

	function handleKeydown(e) {
		if (show && e.key === 'Escape') {
			closeModal();
		}
	}
</script>

<svelte:window on:keydown={handleKeydown} />

<svelte:head>
	<link rel="stylesheet" href="https://unpkg.com/easymde/dist/easymde.min.css" />
</svelte:head>

{#if show}
	<!-- svelte-ignore a11y-no-noninteractive-element-interactions -->
	<!-- svelte-ignore a11y-click-events-have-key-events -->
	<div class="modal-overlay-global" use:portal role="dialog" aria-modal="true"
		on:mousedown={(e) => { if (e.target === e.currentTarget) overlayMouseDown = true; }} 
		on:mouseup={(e) => { if (overlayMouseDown && e.target === e.currentTarget) closeModal(); overlayMouseDown = false; }}>
		<div class="modal-card-global glass" on:click|stopPropagation>
			<header class="edit-modal-header">
				<h3>➕ {$t("admin_games_add") || 'Ajouter un Jeu'}</h3>
				<button class="close-btn" on:click={closeModal} aria-label="Fermer">✕</button>
			</header>
			<div class="edit-modal-body">
				<div class="flex-col gap-4">
					<div class="edit-field full-width">
						<label>{$t('admin_games_name_lbl') || 'Nom du Jeu'}</label>
						<input type="text" bind:value={newGame.name} placeholder="Counter-Strike 2, Valorant..." on:input={() => searchQuery = newGame.name} />
					</div>

					<div class="edit-field full-width">
						<!-- Image Source Selector -->
						<label>{$t('admin_games_illus_lbl') || 'Illustration (Couverture)'}</label>
						<div class="img-mode-tabs">
							<button type="button" class="img-tab {gameImageMode === 'search' ? 'active' : ''}" on:click={() => gameImageMode = 'search'}>{$t('admin_games_btn_search') || 'Rechercher'}</button>
							<button type="button" class="img-tab {gameImageMode === 'url' ? 'active' : ''}" on:click={() => gameImageMode = 'url'}>{$t('admin_games_btn_url') || 'Lien'}</button>
							<button type="button" class="img-tab {gameImageMode === 'upload' ? 'active' : ''}" on:click={() => gameImageMode = 'upload'}>{$t('admin_games_btn_file') || 'Fichier'}</button>
						</div>

						{#if gameImageMode === 'search'}
							<div class="search-bar mt-2">
								<input type="text" bind:value={searchQuery} placeholder="{$t('admin_games_search_placeholder') || 'Rechercher...'}" on:keydown={(e) => e.key === 'Enter' && searchCovers()} />
								<button type="button" class="btn-primary btn-sm" on:click={searchCovers} disabled={searching}>{searching ? '...' : '🔍'}</button>
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
										<button type="button" class="cover-pick" on:click={() => pickCover(r.image)}>
											<img src={r.thumbnail || r.image} alt={r.name} loading="lazy" />
											<span class="cover-name">{r.name}</span>
										</button>
									{/each}
								</div>
							{/if}
						{:else if gameImageMode === 'url'}
							<input type="text" class="mt-2" bind:value={newGame.image_url} placeholder="https://..." />
						{:else}
							<input type="file" class="mt-2" accept="image/*" on:change={handleFileUpload} />
						{/if}

						{#if newGame.image_url}
							<div class="img-preview mt-2">
								<img src={newGame.image_url} alt="Preview" />
								<button type="button" class="preview-clear" on:click={() => newGame.image_url = ''}>✕</button>
							</div>
						{/if}
					</div>

					<div class="edit-field full-width editor-container">
						<label>{$t('admin_games_rules_lbl') || 'Règles du Jeu'}</label>
						{#if EasyMDE}
							<textarea use:setupEditor={newGame.rules}></textarea>
						{:else}
							<textarea bind:value={newGame.rules} rows="4" placeholder="# Règles\n- ..."></textarea>
						{/if}
					</div>
				</div>
			</div>
			<footer class="edit-modal-footer">
				<button type="button" class="btn-secondary" on:click={closeModal}>{$t('admin_settings_cancel') || 'Annuler'}</button>
				<button type="button" class="btn-primary" on:click={createGame} disabled={!newGame.name}>{$t('admin_games_btn_submit') || 'Créer le Jeu'}</button>
			</footer>
		</div>
	</div>
{/if}

<style>
	.flex-col { display: flex; flex-direction: column; gap: 0.8rem; }
	.edit-modal-header { display: flex; justify-content: space-between; align-items: center; padding: 1.2rem 1.5rem; border-bottom: 1px solid var(--glass-border); background: rgba(59, 130, 246, 0.08); }
	.edit-modal-header h3 { font-size: 1rem; margin: 0; }
	.close-btn { background: none; border: none; color: var(--text-dim); cursor: pointer; font-size: 1.2rem; padding: 0.2rem; }
	.edit-modal-body { padding: 1.5rem; }
	.edit-modal-footer { display: flex; justify-content: flex-end; gap: 0.75rem; padding: 1rem 1.5rem; border-top: 1px solid var(--glass-border); }
	.edit-field { display: flex; flex-direction: column; gap: 0.4rem; }
	.edit-field.full-width { grid-column: 1 / -1; }
	.edit-field label { font-size: 0.75rem; font-weight: 700; color: var(--text-dim); text-transform: uppercase; letter-spacing: 0.05em; }

	.btn-primary {
		padding: 0.55rem 1.2rem;
		font-size: 0.8rem;
		font-weight: 700;
		border-radius: 8px;
		cursor: pointer;
		border: 1px solid transparent;
		background: var(--accent);
		color: white;
		box-shadow: 0 4px 12px var(--accent-glow);
		transition: all 0.2s;
	}
	.btn-primary:hover:not(:disabled) {
		transform: translateY(-1px);
		box-shadow: 0 6px 16px var(--accent-glow);
	}
	.btn-primary:disabled { opacity: 0.5; cursor: not-allowed; }
	
	.btn-secondary {
		padding: 0.55rem 1.2rem;
		font-size: 0.8rem;
		font-weight: 700;
		border-radius: 8px;
		cursor: pointer;
		border: 1px solid var(--glass-border);
		background: transparent;
		color: var(--text-main);
		transition: all 0.2s;
	}
	.btn-secondary:hover { background: var(--hover-tint); }

	label { font-size: 0.7rem; font-weight: 700; color: var(--text-muted); text-transform: uppercase; letter-spacing: 0.05em; }
	input[type="text"],
	textarea {
		width: 100%;
		padding: 0.5rem 0.8rem;
		border-radius: 8px;
		border: 1px solid var(--glass-border);
		background: var(--surface-sunken);
		color: var(--text-main);
		font-size: 0.8rem;
		outline: none;
		transition: border-color 0.15s;
	}
	input:focus,
	textarea:focus {
		border-color: var(--accent);
	}

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
	.preview-clear { position: absolute; top: 4px; right: 4px; width: 22px; height: 22px; border-radius: 50%; background: rgba(239, 68, 68, 0.8); color: white; border: none; cursor: pointer; font-size: 0.7rem; display: flex; align-items: center; justify-content: center; }

	/* Image mode tabs */
	.img-mode-tabs { display: flex; gap: 0.3rem; }
	.img-tab { padding: 0.35rem 0.7rem; font-size: 0.7rem; font-weight: 600; border: 1px solid var(--glass-border); border-radius: 8px; background: var(--hover-tint); color: var(--text-dim); cursor: pointer; transition: all 0.15s; }
	.img-tab:hover { border-color: var(--accent); }
	.img-tab.active { background: var(--accent-soft); border-color: var(--accent); color: var(--accent); }
	.mt-2 { margin-top: 0.5rem; }

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
