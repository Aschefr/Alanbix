<script>
	import { api } from '$lib/api';
	import { onMount, onDestroy, tick } from 'svelte';
	import { marked } from 'marked';

	let content = '';
	let spectatorContent = '';
	let isAdmin = false;
	let editing = false;
	let activeTab = 'main'; // 'main' | 'spectator'
	let saving = false;
	let saveMsg = '';

	// EasyMDE instances
	let editorMain = null;
	let editorSpectator = null;
	let mainTextarea;
	let spectatorTextarea;
	let EasyMDE = null;

	onMount(async () => {
		try {
			const me = await api.get('/me');
			isAdmin = me.is_admin || false;
		} catch {}
		await loadInfo();
		// Dynamically import EasyMDE (avoid SSR issues)
		const mod = await import('easymde');
		EasyMDE = mod.default;
	});

	onDestroy(() => {
		destroyEditors();
	});

	async function loadInfo() {
		try {
			const res = await api.get('/dashboard/info');
			content = res.content || '';
			spectatorContent = res.spectator_content || '';
		} catch {}
	}

	function destroyEditors() {
		if (editorMain) { editorMain.toTextArea(); editorMain = null; }
		if (editorSpectator) { editorSpectator.toTextArea(); editorSpectator = null; }
	}

	function createEditor(textarea, value) {
		return new EasyMDE({
			element: textarea,
			initialValue: value,
			spellChecker: false,
			autofocus: false,
			status: false,
			minHeight: '350px',
			placeholder: 'Rédigez votre contenu en Markdown...',
			toolbar: [
				'bold', 'italic', 'heading', '|',
				'quote', 'unordered-list', 'ordered-list', '|',
				'link', 'image', 'table', 'horizontal-rule', '|',
				'preview', 'side-by-side', 'fullscreen', '|',
				'guide'
			],
			sideBySideFullscreen: false,
		});
	}

	async function startEdit() {
		editing = true;
		activeTab = 'main';
		await tick();
		initEditorForTab('main');
	}

	async function switchTab(tab) {
		// Save current editor content before switching
		if (activeTab === 'main' && editorMain) {
			content = editorMain.value();
		} else if (activeTab === 'spectator' && editorSpectator) {
			spectatorContent = editorSpectator.value();
		}
		destroyEditors();
		activeTab = tab;
		await tick();
		initEditorForTab(tab);
	}

	function initEditorForTab(tab) {
		if (tab === 'main' && mainTextarea && !editorMain) {
			editorMain = createEditor(mainTextarea, content);
		} else if (tab === 'spectator' && spectatorTextarea && !editorSpectator) {
			editorSpectator = createEditor(spectatorTextarea, spectatorContent);
		}
	}

	function cancelEdit() {
		destroyEditors();
		editing = false;
		saveMsg = '';
		loadInfo(); // reload original content
	}

	async function save() {
		saving = true;
		saveMsg = '';
		// Get latest values from editors
		const mainContent = editorMain ? editorMain.value() : content;
		const specContent = editorSpectator ? editorSpectator.value() : spectatorContent;
		// If we're on main tab, spec content might still be the old value
		const finalMain = activeTab === 'main' && editorMain ? editorMain.value() : content;
		const finalSpec = activeTab === 'spectator' && editorSpectator ? editorSpectator.value() : spectatorContent;
		
		try {
			await api.put('/admin/config/info_page_content', { value: finalMain });
			await api.put('/admin/config/info_spectator_content', { value: finalSpec });
			content = finalMain;
			spectatorContent = finalSpec;
			destroyEditors();
			editing = false;
			saveMsg = '✓ Sauvegardé';
			setTimeout(() => saveMsg = '', 3000);
		} catch (e) {
			saveMsg = '✕ Erreur: ' + e.message;
		}
		saving = false;
	}

	let copyToast = '';

	function parseMd(text) {
		if (!text) return '';
		// Pre-process: wrap Windows paths BEFORE marked parsing
		// so that marked doesn't eat the backslashes
		// 1) UNC paths: \\server\share
		text = text.replace(
			/(\\\\[\w.\-]+(?:\\[\w.\-]+)*\\?)/g,
			(match) => `<span class="net-path" data-path="${match}" title="Cliquer pour copier le chemin">${match}</span>`
		);
		// 2) Local drive paths: C:\Games\Something
		text = text.replace(
			/([A-Za-z]:\\[\w.\-\s]+(?:\\[\w.\-\s]+)*\\?)/g,
			(match) => `<span class="net-path" data-path="${match}" title="Cliquer pour copier le chemin">${match}</span>`
		);
		return marked.parse(text, { breaks: true });
	}

	function handleContentClick(e) {
		const el = e.target.closest('.net-path');
		if (!el) return;
		e.preventDefault();
		const path = el.dataset.path;
		navigator.clipboard.writeText(path).then(() => {
			copyToast = path;
			setTimeout(() => copyToast = '', 2000);
		});
	}
</script>

<svelte:head>
	<link rel="stylesheet" href="https://unpkg.com/easymde/dist/easymde.min.css" />
</svelte:head>

<div class="info-page">
	<div class="info-header">
		<h1>📋 Informations</h1>
		{#if saveMsg}
			<span class="save-msg" class:error={saveMsg.startsWith('✕')}>{saveMsg}</span>
		{/if}
		{#if isAdmin && !editing}
			<button class="btn-edit" on:click={startEdit}>✏️ Éditer</button>
		{/if}
	</div>

	{#if editing}
		<div class="editor-area">
			<div class="editor-tabs">
				<button class="tab" class:active={activeTab === 'main'} on:click={() => switchTab('main')}>
					📄 Contenu Principal
				</button>
				<button class="tab" class:active={activeTab === 'spectator'} on:click={() => switchTab('spectator')}>
					📺 Contenu Projecteur
				</button>
			</div>

			<div class="editor-container">
				{#if activeTab === 'main'}
					<textarea bind:this={mainTextarea}></textarea>
				{:else}
					<textarea bind:this={spectatorTextarea}></textarea>
				{/if}
			</div>

			<div class="editor-actions">
				<button class="btn-save" on:click={save} disabled={saving}>
					{saving ? '⏳ Sauvegarde...' : '✓ Sauvegarder'}
				</button>
				<button class="btn-cancel" on:click={cancelEdit}>✕ Annuler</button>
			</div>
		</div>
	{:else}
		<div class="info-content glass">
			{#if content}
				<!-- svelte-ignore a11y-click-events-have-key-events -->
				<div class="markdown-body" on:click={handleContentClick}>
					{@html parseMd(content)}
				</div>
				{#if copyToast}
					<div class="copy-toast">📋 Chemin copié : <strong>{copyToast}</strong></div>
				{/if}
			{:else}
				<div class="empty-state">
					<div class="empty-icon">📋</div>
					{#if isAdmin}
						<p>Aucune information publiée.</p>
						<p class="empty-hint">Cliquez sur <strong>✏️ Éditer</strong> pour rédiger le contenu de cette page en Markdown.</p>
						<button class="btn-edit" on:click={startEdit}>✏️ Commencer à rédiger</button>
					{:else}
						<p>Aucune information publiée pour le moment.</p>
						<p class="empty-hint">L'organisateur n'a pas encore publié d'informations.</p>
					{/if}
				</div>
			{/if}
		</div>
	{/if}
</div>

<style>
	.info-page { max-width: 960px; margin: 0 auto; }

	.info-header {
		display: flex; align-items: center; gap: 1rem; margin-bottom: 2rem;
	}
	.info-header h1 {
		font-size: 1.8rem; font-weight: 800; margin: 0; flex: 1;
		color: var(--accent);
	}
	.save-msg { font-size: 0.85rem; font-weight: 600; color: #10b981; animation: fadeIn 0.3s; }
	.save-msg.error { color: #ef4444; }

	.btn-edit {
		padding: 0.6rem 1.2rem; border-radius: var(--radius-md);
		background: var(--accent); color: white; border: none;
		font-weight: 700; font-size: 0.85rem; cursor: pointer;
		transition: all 0.2s;
	}
	.btn-edit:hover { transform: translateY(-1px); box-shadow: 0 4px 15px var(--accent-glow); }

	/* Editor */
	.editor-area { display: flex; flex-direction: column; gap: 1rem; }

	.editor-tabs { display: flex; gap: 0.3rem; background: var(--glass-bg); border-radius: var(--radius-md); padding: 0.3rem; }
	.tab {
		flex: 1; padding: 0.7rem 1rem; border: none; background: none;
		color: var(--text-dim); font-weight: 700; font-size: 0.85rem;
		border-radius: var(--radius-sm, 6px); cursor: pointer; transition: all 0.2s;
	}
	.tab.active { background: var(--accent-soft); color: var(--accent); }
	.tab:hover:not(.active) { background: var(--hover-tint); }

	.editor-container {
		border: 1px solid var(--glass-border); border-radius: var(--radius-md);
		overflow: hidden; background: var(--glass-bg);
	}

	/* EasyMDE theme overrides for dark mode */
	.editor-container :global(.EasyMDEContainer) { background: transparent; }
	.editor-container :global(.EasyMDEContainer .CodeMirror) {
		background: var(--bg-secondary, #0f172a);
		color: var(--text-main, white);
		border: none;
		border-radius: 0;
		font-size: 0.9rem;
	}
	.editor-container :global(.editor-toolbar) {
		background: var(--hover-tint, rgba(255,255,255,0.03));
		border: none;
		border-bottom: 1px solid var(--glass-border);
		opacity: 1;
	}
	.editor-container :global(.editor-toolbar button) {
		color: var(--text-dim, #94a3b8) !important;
		border: none !important;
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

	.editor-actions { display: flex; gap: 0.75rem; justify-content: flex-end; }
	.btn-save {
		padding: 0.7rem 1.5rem; border-radius: var(--radius-md);
		background: #10b981; color: white; border: none;
		font-weight: 700; font-size: 0.85rem; cursor: pointer; transition: all 0.2s;
	}
	.btn-save:hover { background: #059669; transform: translateY(-1px); }
	.btn-save:disabled { opacity: 0.6; cursor: not-allowed; }
	.btn-cancel {
		padding: 0.7rem 1.5rem; border-radius: var(--radius-md);
		background: transparent; color: var(--text-dim); border: 1px solid var(--glass-border);
		font-weight: 700; font-size: 0.85rem; cursor: pointer; transition: all 0.2s;
	}
	.btn-cancel:hover { border-color: var(--danger); color: var(--danger); }

	/* Content display */
	.info-content { padding: 2rem; border-radius: var(--radius-lg, 16px); }
	.markdown-body { line-height: 1.7; color: var(--text-main); }
	.markdown-body :global(h1) { font-size: 1.8rem; font-weight: 800; margin: 0 0 1rem; color: var(--accent); }
	.markdown-body :global(h2) { font-size: 1.4rem; font-weight: 700; margin: 1.5rem 0 0.75rem; border-bottom: 1px solid var(--glass-border); padding-bottom: 0.3rem; }
	.markdown-body :global(h3) { font-size: 1.1rem; font-weight: 700; margin: 1rem 0 0.5rem; }
	.markdown-body :global(p) { margin: 0.5rem 0; }
	.markdown-body :global(ul), .markdown-body :global(ol) { padding-left: 1.5rem; }
	.markdown-body :global(li) { margin: 0.3rem 0; }
	.markdown-body :global(code) { background: var(--hover-tint); padding: 0.15rem 0.4rem; border-radius: 4px; font-size: 0.85em; }
	.markdown-body :global(pre) { background: var(--surface-sunken, rgba(0,0,0,0.2)); padding: 1rem; border-radius: var(--radius-md); overflow-x: auto; }
	.markdown-body :global(blockquote) { border-left: 3px solid var(--accent); padding-left: 1rem; margin: 0.75rem 0; color: var(--text-dim); font-style: italic; }
	.markdown-body :global(a) { color: var(--accent); text-decoration: none; }
	.markdown-body :global(a:hover) { text-decoration: underline; }
	.markdown-body :global(table) { width: 100%; border-collapse: collapse; margin: 1rem 0; }
	.markdown-body :global(th), .markdown-body :global(td) { padding: 0.5rem 0.75rem; border: 1px solid var(--glass-border); text-align: left; }
	.markdown-body :global(th) { background: var(--hover-tint); font-weight: 700; }
	.markdown-body :global(hr) { border: none; border-top: 1px solid var(--glass-border); margin: 1.5rem 0; }
	.markdown-body :global(img) { max-width: 100%; border-radius: var(--radius-md); }
	.markdown-body :global(.net-path) {
		color: var(--accent); font-weight: 600; font-family: 'JetBrains Mono', monospace;
		background: var(--accent-soft, rgba(59,130,246,0.1)); padding: 0.15rem 0.5rem;
		border-radius: 4px; white-space: nowrap;
	}
	.markdown-body :global(.net-path::before) { content: '📂 '; }
	.markdown-body :global(.net-path:hover) { background: var(--accent-soft, rgba(59,130,246,0.2)); cursor: pointer; }
	.markdown-body :global(.net-path:active) { transform: scale(0.97); }

	/* Copy toast */
	.copy-toast {
		position: fixed; bottom: 2rem; left: 50%; transform: translateX(-50%);
		background: #10b981; color: white; padding: 0.7rem 1.5rem;
		border-radius: var(--radius-md); font-size: 0.85rem; font-weight: 600;
		box-shadow: 0 8px 30px rgba(16,185,129,0.3);
		animation: toastIn 0.3s ease;
		z-index: 999;
	}
	@keyframes toastIn { from { opacity: 0; transform: translateX(-50%) translateY(10px); } to { opacity: 1; transform: translateX(-50%) translateY(0); } }

	/* Empty state */
	.empty-state { text-align: center; padding: 3rem 1rem; }
	.empty-icon { font-size: 4rem; margin-bottom: 1rem; opacity: 0.3; }
	.empty-state p { color: var(--text-dim); font-size: 1.1rem; margin: 0.5rem 0; }
	.empty-hint { font-size: 0.9rem !important; color: var(--text-muted) !important; }

	@keyframes fadeIn { from { opacity: 0; } to { opacity: 1; } }
</style>
