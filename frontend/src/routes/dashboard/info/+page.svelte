<script>
	import { api } from '$lib/api';
	import { onMount, onDestroy, tick } from 'svelte';
	import { marked } from 'marked';
	import { t } from '$lib/i18nStore';

	let content = '';
	let spectatorContent = '';
	let isAdmin = false;
	let editing = false;
	let activeTab = 'main'; // 'main' | 'spectator'
	let saving = false;
	let saveMsg = '';

	// File manager (AXE-13)
	let files = [];
	let uploading = false;
	let deleteConfirm = null; // filename to confirm
	let nukeConfirm = false;
	let fileInput;

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
		await loadFiles();
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

	// --- File Manager (AXE-13) ---
	async function loadFiles() {
		try { files = await api.get('/dashboard/info/files'); } catch { files = []; }
	}

	async function uploadFile() {
		if (!fileInput?.files?.length) return;
		uploading = true;
		const formData = new FormData();
		formData.append('file', fileInput.files[0]);
		try {
			await api.upload('/dashboard/info/files/upload', formData);
			await loadFiles();
			fileInput.value = ''; // reset
		} catch (e) {
			saveMsg = '✕ Erreur upload: ' + e.message;
			setTimeout(() => saveMsg = '', 3000);
		}
		uploading = false;
	}

	async function deleteFile(name) {
		try {
			await api.delete(`/dashboard/info/files/${encodeURIComponent(name)}`);
			deleteConfirm = null;
			await loadFiles();
		} catch (e) {
			saveMsg = '✕ Erreur suppression: ' + e.message;
			setTimeout(() => saveMsg = '', 3000);
		}
	}

	async function nukeFiles() {
		try {
			await api.delete('/dashboard/info/files');
			nukeConfirm = false;
			await loadFiles();
		} catch (e) {
			saveMsg = '✕ Erreur nuke: ' + e.message;
			setTimeout(() => saveMsg = '', 3000);
		}
	}

	function fileIcon(name) {
		const ext = (name.split('.').pop() || '').toLowerCase();
		if (['torrent'].includes(ext)) return '🎮';
		if (['pdf'].includes(ext)) return '📄';
		if (['exe', 'msi', 'bat', 'sh'].includes(ext)) return '🔧';
		if (['zip', 'rar', '7z', 'tar', 'gz'].includes(ext)) return '📦';
		if (['png', 'jpg', 'jpeg', 'gif', 'webp', 'svg'].includes(ext)) return '🖼️';
		if (['mp4', 'avi', 'mkv', 'mov'].includes(ext)) return '🎬';
		if (['mp3', 'wav', 'flac', 'ogg'].includes(ext)) return '🎵';
		if (['txt', 'md', 'log', 'cfg', 'ini', 'yaml', 'json'].includes(ext)) return '📝';
		return '📁';
	}

	function formatSize(bytes) {
		if (bytes < 1024) return bytes + ' B';
		if (bytes < 1048576) return (bytes / 1024).toFixed(1) + ' KB';
		if (bytes < 1073741824) return (bytes / 1048576).toFixed(1) + ' MB';
		return (bytes / 1073741824).toFixed(2) + ' GB';
	}

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
		<h1>{$t('info_title')}</h1>
		{#if saveMsg}
			<span class="save-msg" class:error={saveMsg.startsWith('✕')}>{saveMsg}</span>
		{/if}
		{#if isAdmin && !editing}
			<button class="btn-edit" on:click={startEdit}>{$t('info_btn_edit')}</button>
		{/if}
	</div>

	{#if editing}
		<div class="editor-area">
			<div class="editor-tabs">
				<button class="tab" class:active={activeTab === 'main'} on:click={() => switchTab('main')}>
					{$t('info_tab_main')}
				</button>
				<button class="tab" class:active={activeTab === 'spectator'} on:click={() => switchTab('spectator')}>
					{$t('info_tab_projector')}
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
					{saving ? $t('info_saving') : $t('info_btn_save')}
				</button>
				<button class="btn-cancel" on:click={cancelEdit}>{$t('info_btn_cancel')}</button>
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
					<div class="copy-toast">{@html $t('info_toast_copied', { path: copyToast })}</div>
				{/if}
			{:else}
				<div class="empty-state">
					<div class="empty-icon">📋</div>
					{#if isAdmin}
						<p>{$t('info_empty_no_info')}</p>
						<p class="empty-hint">{@html $t('info_empty_edit_hint')}</p>
						<button class="btn-edit" on:click={startEdit}>{$t('info_empty_start_writing')}</button>
					{:else}
						<p>{$t('info_empty_no_info_yet')}</p>
						<p class="empty-hint">{$t('info_empty_organizer_hint')}</p>
					{/if}
				</div>
			{/if}
		</div>
	{/if}

	<!-- File Manager (AXE-13) -->
	{#if files.length > 0 || isAdmin}
		<div class="files-section glass">
			<div class="files-header">
				<h2>{$t('info_files_title')}</h2>
				{#if isAdmin}
					<div class="files-admin-btns">
						<label class="btn-upload" class:uploading>
							{uploading ? '⏳ Upload...' : $t('info_files_add')}
							<input type="file" bind:this={fileInput} on:change={uploadFile} style="display:none" />
						</label>
						{#if files.length > 0}
							{#if nukeConfirm}
								<button class="btn-nuke confirm" on:click={nukeFiles}>✓ Confirmer ({files.length})</button>
								<button class="btn-nuke cancel" on:click={() => nukeConfirm = false}>✕</button>
							{:else}
								<button class="btn-nuke" on:click={() => nukeConfirm = true} title={$t('info_files_nuke_tooltip')}>☢️ Nuke</button>
							{/if}
						{/if}
					</div>
				{/if}
			</div>
			{#if files.length === 0}
				<p class="files-empty">{$t('info_files_empty')}</p>
			{:else}
				<div class="files-list">
					{#each files as f}
						<div class="file-card">
							<span class="file-icon">{fileIcon(f.name)}</span>
							<div class="file-info">
								<a href="{f.url}" download class="file-name" title="{$t('info_files_download_tooltip')} {f.name}">{f.name}</a>
								<span class="file-size">{formatSize(f.size)}</span>
							</div>
							<a href="{f.url}" download class="file-dl" title={$t('info_files_download_tooltip')}>⬇️</a>
							{#if isAdmin}
								{#if deleteConfirm === f.name}
									<button class="file-del confirm" on:click={() => deleteFile(f.name)}>✓ Confirmer</button>
									<button class="file-del cancel" on:click={() => deleteConfirm = null}>✕</button>
								{:else}
									<button class="file-del" on:click={() => deleteConfirm = f.name} title={$t('info_files_delete_tooltip')}>🗑️</button>
								{/if}
							{/if}
						</div>
					{/each}
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

	/* File Manager (AXE-13) */
	.files-section { margin-top: 2rem; padding: 1.5rem; border-radius: var(--radius-lg, 16px); }
	.files-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 1rem; }
	.files-header h2 { margin: 0; font-size: 1.1rem; font-weight: 800; color: var(--accent); }
	.btn-upload {
		padding: 0.5rem 1rem; border-radius: var(--radius-md);
		background: linear-gradient(135deg, #8b5cf6, #6d28d9); color: white;
		font-weight: 700; font-size: 0.8rem; cursor: pointer;
		transition: all 0.2s; border: none; display: inline-block;
	}
	.btn-upload:hover { transform: translateY(-1px); box-shadow: 0 4px 15px rgba(139,92,246,0.4); }
	.btn-upload.uploading { opacity: 0.6; cursor: wait; }
	.files-empty { color: var(--text-muted); font-size: 0.85rem; font-style: italic; text-align: center; padding: 1rem; }
	.files-list { display: flex; flex-direction: column; gap: 0.4rem; }
	.file-card {
		display: flex; align-items: center; gap: 0.7rem;
		padding: 0.6rem 0.8rem; border-radius: var(--radius-md, 8px);
		background: var(--hover-tint, rgba(255,255,255,0.03));
		border: 1px solid var(--glass-border); transition: all 0.15s;
	}
	.file-card:hover { border-color: rgba(139,92,246,0.3); background: rgba(139,92,246,0.04); }
	.file-icon { font-size: 1.3rem; flex-shrink: 0; }
	.file-info { flex: 1; min-width: 0; }
	.file-name {
		display: block; font-weight: 700; font-size: 0.85rem; color: var(--accent);
		text-decoration: none; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
	}
	.file-name:hover { text-decoration: underline; }
	.file-size { font-size: 0.65rem; color: var(--text-muted); }
	.file-dl {
		font-size: 1rem; text-decoration: none; padding: 0.3rem;
		border-radius: 6px; transition: all 0.15s; flex-shrink: 0;
	}
	.file-dl:hover { background: rgba(59,130,246,0.1); transform: scale(1.15); }
	.file-del {
		background: none; border: 1px solid var(--glass-border); border-radius: 6px;
		font-size: 0.75rem; padding: 0.25rem 0.4rem; cursor: pointer; transition: all 0.15s; color: var(--text-dim);
	}
	.file-del:hover { border-color: var(--danger); color: var(--danger); }
	.file-del.confirm { background: var(--danger); color: white; border-color: var(--danger); font-weight: 700; }
	.file-del.cancel { font-weight: 700; }
	.files-admin-btns { display: flex; gap: 0.5rem; align-items: center; }
	.btn-nuke {
		padding: 0.5rem 0.8rem; border-radius: var(--radius-md);
		background: transparent; color: var(--danger, #ef4444); border: 1px solid var(--danger, #ef4444);
		font-weight: 700; font-size: 0.75rem; cursor: pointer; transition: all 0.2s;
	}
	.btn-nuke:hover { background: rgba(239,68,68,0.1); transform: translateY(-1px); }
	.btn-nuke.confirm { background: var(--danger); color: white; }
	.btn-nuke.cancel { border-color: var(--glass-border); color: var(--text-dim); }
</style>
