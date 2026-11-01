<script>
	// Markdown editor for organiser texts: a plain textarea (best with phone keyboards), a toolbar
	// that inserts Markdown syntax, and a preview rendered exactly like the players will see it.
	// No third-party editor: nothing is downloaded, and it follows the app's themes and icons.
	import { tick } from 'svelte';
	import { t } from '$lib/i18nStore';
	import Icon from '$lib/components/Icon.svelte';
	import { renderMarkdown } from '$lib/markdown';

	export let value = '';
	export let placeholder = '';
	export let id = undefined;
	export let label = '';
	export let rows = 10;
	/** Same renderer as the page that shows the text (the info page adds clickable network paths) */
	export let render = renderMarkdown;

	let textarea;
	let mode = 'write';

	const TOOLS = [
		{ key: 'bold', icon: 'bold', title: 'md_bold' },
		{ key: 'italic', icon: 'italic', title: 'md_italic' },
		{ key: 'heading', icon: 'heading', title: 'md_heading' },
		null,
		{ key: 'quote', icon: 'text-quote', title: 'md_quote' },
		{ key: 'list', icon: 'list', title: 'md_list' },
		{ key: 'ordered', icon: 'list-ordered', title: 'md_list_ordered' },
		null,
		{ key: 'link', icon: 'link', title: 'md_link' },
		{ key: 'image', icon: 'image', title: 'md_image' },
		{ key: 'table', icon: 'table', title: 'md_table' },
		{ key: 'rule', icon: 'minus', title: 'md_rule' }
	];

	$: html = mode === 'preview' ? render(value) : '';

	// Replace the current selection; execCommand keeps the browser's undo history (Ctrl+Z)
	function replaceSelection(text, selStart, selEnd) {
		textarea.focus();
		const start = textarea.selectionStart;
		let done = false;
		try { done = document.execCommand('insertText', false, text); } catch { done = false; }
		if (!done) {
			textarea.setRangeText(text, textarea.selectionStart, textarea.selectionEnd, 'end');
			textarea.dispatchEvent(new Event('input', { bubbles: true }));
		}
		if (selStart !== undefined) textarea.setSelectionRange(start + selStart, start + selEnd);
	}

	function wrap(marker, sampleKey) {
		const s = textarea.selectionStart, e = textarea.selectionEnd;
		const sel = textarea.value.slice(s, e) || $t(sampleKey);
		replaceSelection(marker + sel + marker, marker.length, marker.length + sel.length);
	}

	// Add (or remove, when every line already has it) a prefix on each selected line
	function prefixLines(pattern, makePrefix) {
		const v = textarea.value;
		const s = textarea.selectionStart;
		// a selection ending right after a line break does not include the next line
		const e = textarea.selectionEnd > s && v[textarea.selectionEnd - 1] === '\n' ? textarea.selectionEnd - 1 : textarea.selectionEnd;
		const start = v.lastIndexOf('\n', s - 1) + 1;
		let end = v.indexOf('\n', e);
		if (end === -1) end = v.length;
		const lines = v.slice(start, end).split('\n');
		const all = lines.every((l) => pattern.test(l));
		const out = lines.map((l, i) => (all ? l.replace(pattern, '') : makePrefix(i) + l.replace(pattern, ''))).join('\n');
		textarea.setSelectionRange(start, end);
		replaceSelection(out, 0, out.length);
	}

	function insertBlock(block) {
		const s = textarea.selectionStart;
		const before = textarea.value.slice(0, s);
		const lead = before === '' ? '' : before.endsWith('\n\n') ? '' : before.endsWith('\n') ? '\n' : '\n\n';
		replaceSelection(lead + block + '\n', lead.length, lead.length + block.length);
	}

	function insertLink(image) {
		const s = textarea.selectionStart, e = textarea.selectionEnd;
		const text = textarea.value.slice(s, e) || $t(image ? 'md_sample_image' : 'md_sample_link');
		const head = (image ? '![' : '[') + text + '](';
		replaceSelection(head + 'https://)', head.length, head.length + 8);
	}

	function apply(key) {
		if (mode !== 'write' || !textarea) return;
		if (key === 'bold') wrap('**', 'md_sample_text');
		else if (key === 'italic') wrap('*', 'md_sample_text');
		else if (key === 'heading') prefixLines(/^#{1,6}\s/, () => '## ');
		else if (key === 'quote') prefixLines(/^>\s?/, () => '> ');
		else if (key === 'list') prefixLines(/^[-*+]\s/, () => '- ');
		else if (key === 'ordered') prefixLines(/^\d+\.\s/, (i) => `${i + 1}. `);
		else if (key === 'link') insertLink(false);
		else if (key === 'image') insertLink(true);
		else if (key === 'table') {
			const c = $t('md_table_column');
			insertBlock(`| ${c} 1 | ${c} 2 |\n| --- | --- |\n|  |  |`);
		} else if (key === 'rule') insertBlock('---');
	}

	function onKeydown(e) {
		if (!(e.ctrlKey || e.metaKey) || e.altKey) return;
		const k = e.key.toLowerCase();
		if (k === 'b' || k === 'i') {
			e.preventDefault();
			apply(k === 'b' ? 'bold' : 'italic');
		}
	}

	async function setMode(m) {
		mode = m;
		if (m === 'write') { await tick(); textarea?.focus(); }
	}
</script>

<div class="md-editor">
	<div class="md-bar">
		<div class="md-modes" role="tablist" aria-label={label}>
			<button type="button" role="tab" class="md-mode" class:active={mode === 'write'} aria-selected={mode === 'write'} on:click={() => setMode('write')}>
				<Icon name="pencil" size={14} /> {$t('md_tab_write')}
			</button>
			<button type="button" role="tab" class="md-mode" class:active={mode === 'preview'} aria-selected={mode === 'preview'} on:click={() => setMode('preview')}>
				<Icon name="eye" size={14} /> {$t('md_tab_preview')}
			</button>
		</div>
		{#if mode === 'write'}
			<div class="md-tools">
				{#each TOOLS as tool}
					{#if tool}
						<button type="button" class="md-tool" title={$t(tool.title)} aria-label={$t(tool.title)} on:mousedown|preventDefault on:click={() => apply(tool.key)}>
							<Icon name={tool.icon} size={16} />
						</button>
					{:else}
						<span class="md-sep" aria-hidden="true"></span>
					{/if}
				{/each}
			</div>
		{/if}
	</div>

	{#if mode === 'write'}
		<textarea {id} bind:this={textarea} bind:value {placeholder} {rows} aria-label={label || undefined} on:keydown={onKeydown}></textarea>
	{:else}
		<div class="md-preview" style="min-height: {rows * 1.6}em">
			{#if value && value.trim()}
				<slot name="preview" {html}>
					<div class="md-preview-default">{@html html}</div>
				</slot>
			{:else}
				<p class="md-empty">{$t('md_preview_empty')}</p>
			{/if}
		</div>
	{/if}
</div>

<style>
	.md-editor { display: flex; flex-direction: column; border: 1px solid var(--glass-border); border-radius: var(--radius-md); background: var(--input-bg); overflow: hidden; }
	.md-editor:focus-within { border-color: var(--accent); box-shadow: 0 0 0 3px var(--accent-soft); }
	.md-bar { display: flex; flex-wrap: wrap; align-items: center; gap: 0.35rem 0.75rem; padding: 0.35rem 0.4rem; border-bottom: 1px solid var(--glass-border); background: var(--hover-tint); }
	.md-modes { display: inline-flex; gap: 0.2rem; }
	.md-mode { display: inline-flex; align-items: center; gap: 0.35rem; padding: 0.3rem 0.65rem; border: 1px solid transparent; border-radius: 8px; background: transparent; color: var(--text-dim); font: inherit; font-size: 0.82rem; font-weight: 600; cursor: pointer; }
	.md-mode.active { background: var(--bg-secondary, var(--input-bg)); border-color: var(--glass-border); color: var(--text-main); }
	.md-tools { display: flex; flex-wrap: wrap; align-items: center; gap: 0.1rem; }
	.md-tool { width: 32px; height: 32px; display: inline-flex; align-items: center; justify-content: center; border: none; border-radius: 6px; background: transparent; color: var(--text-dim); cursor: pointer; }
	.md-tool:hover { background: var(--accent-soft); color: var(--accent); }
	.md-sep { width: 1px; height: 18px; background: var(--glass-border); margin: 0 0.2rem; }
	textarea { display: block; width: 100%; box-sizing: border-box; border: none; outline: none; resize: vertical; padding: 0.75rem 0.85rem; background: transparent; color: var(--input-color, var(--text-main)); font-family: var(--font-main, inherit); font-size: 0.92rem; line-height: 1.6; }
	.md-preview { padding: 0.75rem 0.95rem; overflow-wrap: anywhere; }
	.md-empty { margin: 0; color: var(--text-dim); font-style: italic; font-size: 0.9rem; }
	.md-preview-default { font-size: 0.92rem; line-height: 1.6; color: var(--text-main); }
	.md-preview-default :global(h1), .md-preview-default :global(h2), .md-preview-default :global(h3) { margin: 0.6em 0 0.3em; line-height: 1.3; }
	.md-preview-default :global(p) { margin: 0.4em 0; }
	.md-preview-default :global(ul), .md-preview-default :global(ol) { margin: 0.4em 0; padding-left: 1.3em; }
	.md-preview-default :global(blockquote) { margin: 0.5em 0; padding-left: 0.8em; border-left: 3px solid var(--glass-border); color: var(--text-dim); }
	.md-preview-default :global(table) { border-collapse: collapse; margin: 0.5em 0; }
	.md-preview-default :global(th), .md-preview-default :global(td) { border: 1px solid var(--glass-border); padding: 0.3em 0.6em; }
	.md-preview-default :global(img) { max-width: 100%; }
	.md-preview-default :global(a) { color: var(--accent); }
	@media (max-width: 600px) {
		/* one row of tools that scrolls sideways, instead of wrapping over several rows */
		.md-bar { gap: 0.3rem; }
		.md-tools { width: 100%; flex-wrap: nowrap; overflow-x: auto; scrollbar-width: none; -webkit-mask-image: linear-gradient(to right, #000 calc(100% - 28px), transparent); mask-image: linear-gradient(to right, #000 calc(100% - 28px), transparent); padding-right: 24px; }
		.md-tools::-webkit-scrollbar { display: none; }
		.md-tool { width: 36px; height: 36px; flex-shrink: 0; }
		.md-sep { flex-shrink: 0; }
	}
</style>
