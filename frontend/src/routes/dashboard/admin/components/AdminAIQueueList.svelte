<script>
	// Requests in the AI queue, processing then pending. Part of the AI settings of the admin.
	import { createEventDispatcher } from 'svelte';
	import { t } from '$lib/i18nStore';
	import Icon from '$lib/components/Icon.svelte';

	export let queue = { pending: [], active: [] };

	const dispatch = createEventDispatcher();
</script>

{#if queue.active.length > 0}
	<div class="queue-section-label">{$t("admin_settings_queue_processing")}</div>
	{#each queue.active as entry}
		<div class="queue-row active">
			<span class="queue-row-type"><Icon name={entry.task_type === 'chat' ? 'chat' : entry.task_type === 'compress' ? 'layers' : (entry.task_type === 'title_suggestion' || entry.task_type === 'auto_title') ? 'pencil' : 'trophy'} size={16} /></span>
			<span class="queue-row-user">{entry.username || '—'}</span>
			<span class="queue-row-type-label">{entry.task_type}</span>
			<span class="queue-row-time">{entry.processing_since}s</span>
			<button class="queue-cancel-btn" on:click|stopPropagation={() => dispatch('cancel', entry.id)} title="{$t('admin_settings_queue_cancel_tooltip')}" aria-label="{$t('admin_settings_queue_cancel_tooltip')}"><Icon name="x" size={14} /></button>
		</div>
	{/each}
{/if}
{#if queue.pending.length > 0}
	<div class="queue-section-label" style="margin-top:{queue.active.length > 0 ? '0.75rem' : '0'}">{$t("admin_settings_queue_pending")}</div>
	{#each queue.pending as entry}
		<div class="queue-row">
			<span class="queue-row-pos">#{entry.position}</span>
			<span class="queue-row-type"><Icon name={entry.task_type === 'chat' ? 'chat' : entry.task_type === 'compress' ? 'layers' : (entry.task_type === 'title_suggestion' || entry.task_type === 'auto_title') ? 'pencil' : 'trophy'} size={16} /></span>
			<span class="queue-row-user">{entry.username || '—'}</span>
			<span class="queue-row-type-label">{entry.task_type}</span>
			<span class="queue-row-time">{entry.waiting_since}s</span>
			<button class="queue-cancel-btn" on:click|stopPropagation={() => dispatch('cancel', entry.id)} title="{$t('admin_settings_queue_cancel_tooltip')}" aria-label="{$t('admin_settings_queue_cancel_tooltip')}"><Icon name="x" size={14} /></button>
		</div>
	{/each}
{/if}
{#if queue.active.length === 0 && queue.pending.length === 0}
	<div class="queue-empty"><Icon name="check-circle" size={16} /> {$t("admin_settings_ai_queue_empty")}</div>
{/if}

<style>
	.queue-section-label { font-size: 0.75rem; font-weight: 700; color: var(--text-muted); text-transform: uppercase; letter-spacing: 0.05em; margin-bottom: 0.4rem; }
	.queue-row { display: flex; align-items: center; gap: 0.6rem; padding: 0.5rem 0.6rem; border-radius: 8px; background: var(--hover-tint); border: 1px solid transparent; margin-bottom: 0.3rem; transition: all 0.2s; }
	.queue-row:hover { border-color: var(--glass-border); }
	.queue-row.active { background: rgba(16,185,129,0.06); border: 1px solid rgba(16,185,129,0.2); }
	.queue-row-pos { font-size: 0.75rem; font-weight: 800; color: var(--accent); min-width: 1.5rem; }
	.queue-row-type { font-size: 0.85rem; }
	.queue-row-user { flex: 1; font-size: 0.8rem; font-weight: 600; color: var(--text-main); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
	.queue-row-type-label { font-size: 0.75rem; color: var(--text-muted); padding: 0.1rem 0.4rem; background: var(--surface-sunken); border-radius: 4px; }
	.queue-row-time { font-size: 0.75rem; color: var(--text-dim); font-family: monospace; min-width: 2.5rem; text-align: right; }
	.queue-cancel-btn { background: none; border: 1px solid rgba(239,68,68,0.2); color: var(--text-muted); border-radius: 6px; padding: 0.15rem 0.4rem; font-size: 0.75rem; cursor: pointer; transition: all 0.2s; }
	.queue-cancel-btn:hover { background: rgba(239,68,68,0.15); color: #ef4444; border-color: rgba(239,68,68,0.4); }
	.queue-empty { text-align: center; padding: 1rem; font-size: 0.8rem; color: var(--text-muted); }
</style>
