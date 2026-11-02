<script>
	// Knowledge base entries (RAG): list, edit, add. The card around it stays in AdminSettingsTab.
	import Icon from '$lib/components/Icon.svelte';
	import { get } from 'svelte/store';
	import { onMount, onDestroy } from 'svelte';
	import { api } from '$lib/api';
	import { t } from '$lib/i18nStore';
	import { wsMessageStore } from '$lib/ws';

	export let docs = [];
	export let toast = (msg, type) => {};

	let newDocContent = '';
	let editingDocId = null;
	let editDocContent = '';
	let editDocLoading = false;
	let editDocSaving = false;
	let uploadingDoc = false;

	async function loadKnowledge() {
		try {
			docs = await api.get('/ia/knowledge');
		} catch { docs = []; }
		loadStatus();
	}

	// Which search works (meaning and/or keywords) and how many entries the current model has not indexed
	let status = null;
	let reindexing = false;
	async function loadStatus() {
		try { status = await api.get('/ia/knowledge/status'); } catch { status = null; }
	}
	async function reindex() {
		reindexing = true;
		try {
			const res = await api.post('/ia/knowledge/reindex', {});
			if (res.indexed > 0) toast(get(t)('admin_rag_reindex_done', { indexed: res.indexed, total: res.total, plural: res.indexed > 1 ? 's' : '' }), 'success');
			else toast(get(t)('admin_rag_reindex_failed'), 'error');
		} catch (e) { toast(e.message || get(t)('admin_rag_reindex_failed'), 'error'); }
		reindexing = false;
		loadKnowledge();
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
			if (res.has_embedding === false) {
				toast(get(t)('admin_rag_saved_keywords'), 'info');
			} else if (res.chunks > 1) {
				toast(get(t)('admin_rag_reindexed', { chunks: res.chunks, chars: res.content_length }), 'success');
			} else {
				toast(get(t)('admin_toast_rag_updated'), 'success');
			}
			editingDocId = null;
			editDocContent = '';
			loadKnowledge();
		} catch (e) { toast(e.message || get(t)('admin_rag_update_error'), 'error'); }
		editDocSaving = false;
	}

	async function uploadRagDoc() {
		if (!newDocContent.trim()) return;
		uploadingDoc = true;
		try {
			const res = await api.post('/ia/upload-document', { content: newDocContent });
			newDocContent = '';
			if (res.has_embedding === false) {
				toast(get(t)('admin_rag_saved_keywords'), 'info');
			} else if (res.chunks > 1) {
				toast(get(t)('admin_rag_indexed', { chunks: res.chunks, chars: res.content_length }), 'success');
			} else {
				toast(get(t)('admin_toast_rag_added'), 'success');
			}
			loadKnowledge();
		} catch (e) { toast(e.message || get(t)('admin_rag_index_error'), 'error'); }
		uploadingDoc = false;
	}

	let wsUnsub = null;
	onMount(() => {
		loadKnowledge();
		wsUnsub = wsMessageStore.subscribe(msg => {
			if (msg?.type === 'knowledge_updated') loadKnowledge();
		});
	});
	onDestroy(() => { if (wsUnsub) wsUnsub(); });
</script>

<svelte:window on:keydown={(e) => { if (e.key === 'Escape' && editingDocId) editingDocId = null; }} />

{#if status}
	<div class="rag-status" class:keywords-only={status.rag_enabled && status.semantic !== 'ok'} class:off={!status.rag_enabled} role="status">
		<span class="rag-status-icon"><Icon name={!status.rag_enabled ? 'info' : status.semantic === 'ok' ? 'check-circle' : 'search'} size={15} /></span>
		<div class="rag-status-text">
			{#if !status.rag_enabled}
				<span>{$t('admin_rag_status_disabled')}</span>
			{:else if status.semantic === 'ok'}
				<span>{$t('admin_rag_status_both', { model: status.model })}</span>
				{#if status.to_index > 0}
					<span class="rag-status-detail">{$t('admin_rag_status_to_index', { count: status.to_index, plural: status.to_index > 1 ? 's' : '' })}</span>
				{/if}
			{:else}
				<span>{$t('admin_rag_status_keywords', { model: status.model })}</span>
				{#if status.error}<span class="rag-status-detail" title={status.error}>{status.error}</span>{/if}
			{/if}
		</div>
		{#if status.rag_enabled && status.semantic === 'ok' && status.to_index > 0}
			<button class="btn-secondary btn-xs" on:click={reindex} disabled={reindexing}>
				<Icon name="refresh" size={13} /> {$t('admin_rag_reindex')}
			</button>
		{/if}
	</div>
{/if}

<!-- Existing documents -->
{#if docs.length > 0}
	<div class="rag-list">
		{#each docs as doc}
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
									<button class="btn-secondary btn-xs" on:click={() => { editingDocId = null; editDocContent = ''; }}><Icon name="x" size={13} /> {$t('admin_settings_cancel')}</button>
									<button class="btn-primary btn-xs" on:click={saveKnowledgeEdit} disabled={!editDocContent.trim()}>{$t("admin_settings_ai_rag_btn_save_vectorize")}</button>
								</div>
							{/if}
						{/if}
					{:else}
						<p class="rag-preview">{doc.content}</p>
					{/if}
				</div>
				<div class="rag-item-actions">
					<button class="btn-icon" title="{$t('admin_tourneys_tooltip_edit')}" on:click={() => editKnowledge(doc.id)} aria-label={$t('admin_tourneys_tooltip_edit')}><Icon name={editingDocId === doc.id ? 'x' : 'pencil'} size={14} /></button>
					<button class="btn-icon btn-icon-danger" title="{$t('admin_tourneys_tooltip_delete')}" on:click={() => deleteKnowledge(doc.id)} aria-label={$t('admin_tourneys_tooltip_delete')}><Icon name="trash" size={14} /></button>
				</div>
			</div>
		{/each}
	</div>
{:else}
	<div class="rag-empty">
		<span><Icon name="inbox" size={22} /></span>
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

<style>
	.prompt-textarea { width: 100%; background: var(--surface-sunken); border: 1px solid var(--glass-border); border-radius: 10px; padding: 0.7rem; color: var(--text-main); font-size: 0.8rem; resize: vertical; font-family: inherit; line-height: 1.5; min-height: 80px; }
	.prompt-textarea:focus { border-color: var(--accent); outline: none; }
	.rag-list { display: flex; flex-direction: column; gap: 0.4rem; margin-bottom: 1rem; max-height: 300px; overflow-y: auto; }
	.rag-item { display: flex; align-items: flex-start; gap: 0.5rem; padding: 0.6rem 0.7rem; border-radius: 8px; background: var(--hover-tint); border: 1px solid var(--glass-border); transition: all 0.15s; }
	.rag-item:hover { border-color: rgba(59,130,246,0.2); background: rgba(59,130,246,0.03); }
	.rag-item-main { flex: 1; min-width: 0; }
	.rag-item-header { display: flex; align-items: center; gap: 0.4rem; margin-bottom: 0.2rem; }
	.rag-id { font-size: 0.75rem; font-weight: 800; color: var(--accent); background: rgba(59,130,246,0.1); padding: 0.1rem 0.3rem; border-radius: 4px; }
	.rag-size { font-size: 0.75rem; color: var(--text-muted); }
	.rag-embed-badge { font-size: 0.75rem; font-weight: 700; padding: 0.1rem 0.35rem; border-radius: 4px; background: rgba(16,185,129,0.1); color: #10b981; }
	.rag-embed-badge.no { background: rgba(245,158,11,0.1); color: #f59e0b; }
	.rag-preview { font-size: 0.75rem; color: var(--text-dim); line-height: 1.4; margin: 0; overflow: hidden; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; word-break: break-word; }
	.rag-item-actions { display: flex; flex-direction: column; gap: 0.2rem; }
	.rag-item-editing { border-color: rgba(59,130,246,0.3); background: rgba(59,130,246,0.05); }
	.rag-edit-textarea { width: 100%; min-height: 120px; resize: vertical; border-radius: 6px; border: 1px solid var(--glass-border); background: var(--bg-secondary); color: var(--text-main); padding: 0.5rem; font-size: 0.75rem; font-family: inherit; line-height: 1.5; margin-top: 0.3rem; }
	.rag-edit-textarea:focus { outline: none; border-color: var(--accent); }
	.rag-edit-actions { display: flex; align-items: center; flex-wrap: wrap; gap: 0.4rem; margin-top: 0.4rem; justify-content: flex-end; }
	.rag-edit-actions button { max-width: 100%; white-space: normal; }
	.rag-list:has(.rag-item-editing) { max-height: none; }
	.rag-edit-chars { font-size: 0.75rem; color: var(--text-muted); margin-right: auto; }
	.rag-edit-loading { font-size: 0.75rem; color: var(--text-muted); padding: 0.5rem 0; }
	.rag-vectorize-anim { position: relative; margin-top: 0.5rem; padding: 0.6rem 0.8rem; border-radius: 8px; overflow: hidden; background: rgba(99,102,241,0.06); border: 1px solid rgba(99,102,241,0.15); }
	.rag-vectorize-bar { position: absolute; top: 0; left: 0; height: 100%; width: 40%; background: linear-gradient(90deg, transparent, rgba(99,102,241,0.15), rgba(139,92,246,0.2), rgba(99,102,241,0.15), transparent); animation: rag-sweep 1.8s ease-in-out infinite; border-radius: 8px; }
	.rag-vectorize-label { position: relative; z-index: 1; font-size: 0.75rem; font-weight: 600; color: #a78bfa; display: flex; align-items: center; gap: 0.4rem; animation: rag-pulse-text 2s ease-in-out infinite; }
	@keyframes rag-sweep { 0% { left: -40%; } 100% { left: 100%; } }
	@keyframes rag-pulse-text { 0%, 100% { opacity: 0.7; } 50% { opacity: 1; } }
	.rag-empty { display: flex; flex-direction: column; align-items: center; gap: 0.3rem; padding: 1.5rem; color: var(--text-muted); font-size: 0.8rem; }
	.rag-empty span { font-size: 1.5rem; opacity: 0.5; }
	.rag-empty p { margin: 0; }
	.rag-add-section { margin-top: 0.75rem; padding-top: 0.75rem; border-top: 1px solid var(--glass-border); display: flex; flex-direction: column; }
	.btn-icon { background: var(--hover-tint); border: 1px solid var(--glass-border); border-radius: 6px; padding: 0.25rem 0.4rem; cursor: pointer; font-size: 0.75rem; transition: all 0.15s; flex-shrink: 0; }
	.btn-icon:hover { background: var(--accent-soft); border-color: var(--accent); }
	.btn-icon-danger:hover { border-color: var(--danger, #ef4444); background: rgba(239,68,68,0.15); }
	.rag-status { display: flex; align-items: center; gap: 0.6rem; padding: 0.55rem 0.75rem; margin-bottom: 0.75rem; border-radius: 8px; background: color-mix(in srgb, #10b981 8%, transparent); border: 1px solid color-mix(in srgb, #10b981 22%, transparent); font-size: 0.8rem; color: var(--text-main); }
	.rag-status.keywords-only { background: color-mix(in srgb, #f59e0b 8%, transparent); border-color: color-mix(in srgb, #f59e0b 25%, transparent); }
	.rag-status.off { background: var(--surface-sunken); border-color: var(--glass-border); }
	.rag-status-icon { display: inline-flex; color: #10b981; flex-shrink: 0; }
	.rag-status.keywords-only .rag-status-icon { color: #f59e0b; }
	.rag-status.off .rag-status-icon { color: var(--text-muted); }
	.rag-status-text { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 0.1rem; line-height: 1.35; }
	.rag-status-detail { font-size: 0.75rem; color: var(--text-muted); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
	.rag-status .btn-xs { flex-shrink: 0; display: inline-flex; align-items: center; gap: 0.3rem; }
</style>
