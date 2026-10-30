<script>
	import { t } from '$lib/i18nStore';
	import { api } from '$lib/api';
	import { API_URL } from '$lib/config';
	import { get } from 'svelte/store';
	import { createEventDispatcher, onMount } from 'svelte';

	import Icon from '$lib/components/Icon.svelte';

	export let show = false;
	// edit mode when a game is given: same form, saved with PUT
	export let game = null;

	const dispatch = createEventDispatcher();

	let newGame = { name: '', rules: '', image_url: '' };
	let gameImageMode = 'search'; // 'url' | 'search' | 'upload'
	let wasShown = false;

	$: if (show !== wasShown) {
		wasShown = show;
		if (show) {
			newGame = game
				? { name: game.name, rules: game.rules || '', image_url: game.image_url || '' }
				: { name: '', rules: '', image_url: '' };
			gameImageMode = game ? 'url' : 'search';
			searchResults = [];
		}
	}
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
			dispatch('toast', { message: get(t)('admin_toast_image_uploaded'), type: 'success' });
		} catch (err) {
			dispatch('toast', { message: get(t)('admin_toast_upload_error') + ' ' + err.message, type: 'error' });
		}
	}

	async function createGame() {
		try {
			const res = game
				? await api.put(`/tournaments/games/${game.id}`, newGame)
				: await api.post('/tournaments/games', newGame);
			if (game) dispatch('toast', { message: get(t)('admin_toast_game_updated'), type: 'success' });
			dispatch('success', res);
			closeModal();
		} catch (e) {
			dispatch('toast', { message: e.message || $t('addgame_create_error'), type: 'error' });
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
				<div class="mh-main">
					<span class="mh-ic"><Icon name={game ? 'pencil' : 'gamepad'} size={20} /></span>
					<div class="mh-text">
						<h3>{game ? $t('admin_games_edit_modal_title') : $t('admin_games_add')}</h3>
						{#if game}<span class="mh-sub">{game.name}</span>{/if}
					</div>
				</div>
				<button class="close-btn" on:click={closeModal} aria-label={$t('common_close')}><Icon name="x" size={18} /></button>
			</header>
			<div class="edit-modal-body">
				<div class="edit-field">
					<label for="game-name">{$t('admin_games_name_lbl')}</label>
					<input id="game-name" type="text" bind:value={newGame.name} placeholder={$t('addgame_name_placeholder')} on:input={() => { if (!game) searchQuery = newGame.name; }} />
				</div>

				<div class="edit-field">
					<span class="edit-label">{$t('admin_games_illus_lbl')}</span>
					<div class="img-mode-tabs">
						<button type="button" class="img-tab {gameImageMode === 'search' ? 'active' : ''}" on:click={() => gameImageMode = 'search'}>{$t('admin_games_btn_search')}</button>
						<button type="button" class="img-tab {gameImageMode === 'url' ? 'active' : ''}" on:click={() => gameImageMode = 'url'}>{$t('admin_games_btn_url')}</button>
						<button type="button" class="img-tab {gameImageMode === 'upload' ? 'active' : ''}" on:click={() => gameImageMode = 'upload'}>{$t('admin_games_btn_file')}</button>
					</div>

					{#if gameImageMode === 'search'}
						<div class="search-bar">
							<input type="text" bind:value={searchQuery} placeholder="{$t('admin_games_search_placeholder')}" on:keydown={(e) => e.key === 'Enter' && searchCovers()} />
							<button type="button" class="btn-primary btn-sm btn-ic" on:click={searchCovers} disabled={searching} aria-label={$t('admin_games_btn_search')}>
								<Icon name={searching ? 'hourglass' : 'search'} size={16} />
							</button>
						</div>
						{#if searxngNotConfigured}
							<div class="warn-line">
								<Icon name="alert-triangle" size={14} />
								<span>{$t('admin_games_searxng_not_configured')}</span>
							</div>
						{/if}
						{#if searchResults.length > 0}
							<div class="cover-grid">
								{#each searchResults as r}
									<button type="button" class="cover-pick" on:click={() => pickCover(r.image)}>
										<img src={r.thumbnail || r.image} alt={r.name} loading="lazy" />
										<span class="cover-name">{r.name}</span>
									</button>
								{/each}
							</div>
						{/if}
					{:else if gameImageMode === 'url'}
						<input type="text" bind:value={newGame.image_url} placeholder="https://..." /><!-- i18n-ignore -->
					{:else}
						<input type="file" accept="image/*" on:change={handleFileUpload} />
					{/if}

					{#if newGame.image_url}
						<div class="img-preview">
							<img src={newGame.image_url} alt={$t('chat_preview_alt')} />
							<button type="button" class="preview-clear" on:click={() => newGame.image_url = ''} aria-label={$t('common_close')}><Icon name="x" size={14} /></button>
						</div>
					{/if}
				</div>

				<div class="edit-field editor-container">
					<span class="edit-label">{$t('admin_games_rules_lbl')}</span>
					{#if EasyMDE}
						<textarea use:setupEditor={newGame.rules}></textarea>
					{:else}
						<textarea bind:value={newGame.rules} rows="4" placeholder={$t('addgame_rules_placeholder')}></textarea>
					{/if}
				</div>
			</div>
			<footer class="edit-modal-footer">
				<button type="button" class="btn-secondary" on:click={closeModal}>{$t('admin_settings_cancel')}</button>
				<button type="button" class="btn-primary btn-ic" on:click={createGame} disabled={!newGame.name}>
					<Icon name={game ? 'save' : 'plus'} size={16} /> {game ? $t('admin_players_modal_btn_save') : $t('admin_games_btn_submit')}
				</button>
			</footer>
		</div>
	</div>
{/if}

<style>
	.warn-line { display: flex; align-items: center; gap: 0.4rem; font-size: 0.75rem; color: var(--warning); }

	/* Search bar */
	.search-bar { display: flex; gap: 0.4rem; }
	.search-bar input { flex-grow: 1; }
	.btn-sm { padding: 0.4rem 0.8rem; font-size: 0.8125rem; }

	/* Cover picker grid */
	.cover-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(110px, 1fr)); gap: 0.5rem; max-height: 220px; overflow-y: auto; }
	.cover-pick { overflow: hidden; border: 2px solid var(--glass-border); border-radius: 8px; cursor: pointer; transition: all 0.15s; background: none; padding: 0; position: relative; }
	.cover-pick:hover { border-color: var(--accent); transform: scale(1.03); }
	.cover-pick img { width: 100%; height: 70px; object-fit: cover; display: block; }
	.cover-name { display: block; padding: 0.2rem 0.3rem; font-size: 0.75rem; font-weight: 600; color: var(--text-dim); text-align: center; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; background: var(--surface-sunken); font-family: var(--font-main); }

	/* Image preview */
	.img-preview { position: relative; width: 100%; max-height: 120px; border-radius: 8px; overflow: hidden; border: 1px solid var(--glass-border); }
	.img-preview img { width: 100%; height: 100px; object-fit: cover; display: block; }
	.preview-clear { position: absolute; top: 4px; right: 4px; width: 22px; height: 22px; border-radius: 50%; background: rgba(239, 68, 68, 0.8); color: white; border: none; cursor: pointer; display: flex; align-items: center; justify-content: center; }

	/* EasyMDE theme overrides for dark and light modes */
	.editor-container :global(.EasyMDEContainer) {
		background: transparent;
		border: 1px solid var(--glass-border);
		border-radius: 8px;
		overflow: hidden;
	}
	.editor-container :global(.EasyMDEContainer .CodeMirror) {
		background: var(--input-bg);
		color: var(--input-color);
		border: none;
		border-radius: 0;
		font-size: 0.85rem;
		font-family: var(--font-main);
	}
	.editor-container :global(.editor-toolbar) {
		background: var(--hover-tint);
		border: none;
		border-bottom: 1px solid var(--glass-border);
		opacity: 1;
		padding: 4px;
	}
	.editor-container :global(.editor-toolbar button) {
		color: var(--text-dim) !important;
		border: none !important;
		width: 26px !important;
		height: 26px !important;
	}
	.editor-container :global(.editor-toolbar button:hover),
	.editor-container :global(.editor-toolbar button.active) {
		background: var(--accent-soft) !important;
		color: var(--accent) !important;
		border-radius: 4px;
	}
	.editor-container :global(.editor-toolbar i.separator) {
		border-left-color: var(--glass-border) !important;
	}
	.editor-container :global(.CodeMirror-cursor) { border-left-color: var(--accent); }
	.editor-container :global(.CodeMirror-selected) { background: var(--accent-soft) !important; }
	.editor-container :global(.editor-preview) {
		background: var(--input-bg);
		color: var(--input-color);
	}
	.editor-container :global(.editor-preview-side) {
		background: var(--input-bg);
		color: var(--input-color);
		border-left: 1px solid var(--glass-border);
	}
</style>
