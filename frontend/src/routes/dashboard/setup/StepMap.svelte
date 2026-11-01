<script>
	import { onMount } from 'svelte';
	import { api } from '$lib/api';
	import { t } from '$lib/i18nStore';
	import Icon from '$lib/components/Icon.svelte';
	import { SEAT_SIZE as SEAT, SEAT_RING, TABLE_DEPTH, seatSlots, tableWidthFor } from '$lib/roomLayout';

	const MAX_SEATS = 60; // tables put end to end form one long table on the map

	let existing = null;
	let mode = 'generate'; // keep | generate
	let tables = 4;
	let perTable = 8;
	let perRow = 2;

	const clamp = (v, lo, hi) => Math.min(hi, Math.max(lo, Math.round(Number(v) || lo)));

	// Long tables with half of the seats along each long side (same slots as the map editor), in rows
	function generate(nTables, nSeats, nPerRow) {
		const w = tableWidthFor(Math.ceil(nSeats / 2));
		const h = TABLE_DEPTH;
		// Every coordinate stays a multiple of the editor's 20 px grid
		const cellW = w + 60;
		const cellH = h + 2 * 80 + 40;
		const out = { tables: [], seats: [], furniture: [] };
		for (let i = 0; i < nTables; i++) {
			const n = i + 1;
			const table = { id: 'T' + n, x: 40 + (i % nPerRow) * cellW, y: 40 + 80 + Math.floor(i / nPerRow) * cellH, w, h, label: 'Table ' + n, rotation: 0 };
			out.tables.push(table);
			seatSlots(table).slice(0, nSeats).forEach((c, s) => {
				out.seats.push({ id: `T${n}_S${s + 1}`, x: c.x - SEAT / 2, y: c.y - SEAT / 2, rotation: 0 });
			});
		}
		return out;
	}

	$: preview = mode === 'keep' && existing ? existing : generate(clamp(tables, 1, 40), clamp(perTable, 1, MAX_SEATS), clamp(perRow, 1, 8));
	$: bounds = (() => {
		const items = [...preview.tables, ...preview.seats.map(s => ({ ...s, w: SEAT, h: SEAT })), ...(preview.furniture || [])];
		if (!items.length) return { x: 0, y: 0, w: 400, h: 200 };
		const x0 = Math.min(...items.map(i => i.x)), y0 = Math.min(...items.map(i => i.y));
		const x1 = Math.max(...items.map(i => i.x + (i.w || SEAT))), y1 = Math.max(...items.map(i => i.y + (i.h || SEAT)));
		return { x: x0 - 20, y: y0 - 20, w: x1 - x0 + 40, h: y1 - y0 + 40 };
	})();

	onMount(async () => {
		try {
			const res = await api.get('/room/layout');
			const l = res.layout || {};
			if ((l.seats || []).length) {
				existing = { tables: l.tables || [], seats: l.seats || [], furniture: l.furniture || [] };
				mode = 'keep';
			}
		} catch {}
	});

	/** Called by the setup page when the admin continues. */
	export async function save() {
		if (mode === 'keep') return true;
		// The old seats disappear: free them so nobody keeps a seat that no longer exists
		if (existing) { try { await api.post('/room/admin-unassign-all', {}); } catch {} }
		await api.post('/room/layout', generate(clamp(tables, 1, 40), clamp(perTable, 1, MAX_SEATS), clamp(perRow, 1, 8)));
		return true;
	}
</script>

{#if existing}
	<div class="choices" role="radiogroup" aria-label={$t('setup_step_map')}>
		<label class="choice" class:active={mode === 'keep'}>
			<input type="radio" bind:group={mode} value="keep" />
			<span class="choice-title">{$t('setup_map_keep')}</span>
			<span class="choice-desc">{$t('setup_map_keep_desc', { tables: existing.tables.length, seats: existing.seats.length })}</span>
		</label>
		<label class="choice" class:active={mode === 'generate'}>
			<input type="radio" bind:group={mode} value="generate" />
			<span class="choice-title">{$t('setup_map_new')}</span>
			<span class="choice-desc">{$t('setup_map_new_desc')}</span>
		</label>
	</div>
{/if}

{#if mode === 'generate'}
	<div class="gen">
		<label class="num">
			<span>{$t('setup_map_tables')}</span>
			<input type="number" min="1" max="40" bind:value={tables} />
		</label>
		<label class="num">
			<span>{$t('setup_map_seats')}</span>
			<input type="number" min="1" max={MAX_SEATS} bind:value={perTable} />
		</label>
		<label class="num">
			<span>{$t('setup_map_per_row')}</span>
			<input type="number" min="1" max="8" bind:value={perRow} />
		</label>
	</div>
	<p class="total">{$t('setup_map_total', { n: clamp(tables, 1, 40) * clamp(perTable, 1, MAX_SEATS) })}</p>
{/if}

<div class="preview" aria-hidden="true">
	<svg viewBox="{bounds.x} {bounds.y} {bounds.w} {bounds.h}" preserveAspectRatio="xMidYMid meet">
		{#each preview.tables as tb}
			<rect x={tb.x} y={tb.y} width={tb.w} height={tb.h} rx="8" fill="var(--map-table-fill)" stroke="var(--map-table-stroke)" transform="rotate({tb.rotation || 0}, {tb.x + tb.w / 2}, {tb.y + tb.h / 2})" />
			<text x={tb.x + tb.w / 2} y={tb.y + tb.h / 2 + 6} text-anchor="middle" font-size="18" font-weight="700" fill="var(--text-dim)">{tb.label}</text>
		{/each}
		{#each preview.furniture || [] as f}
			<rect x={f.x} y={f.y} width={f.w} height={f.h} rx="6" fill="var(--map-table-fill)" stroke="var(--map-table-stroke)" />
		{/each}
		{#each preview.seats as s}
			<rect x={s.x} y={s.y} width={SEAT} height={SEAT} rx="8" fill="var(--map-seat-drop-fill)" stroke="var(--map-seat-drop-stroke)" transform="rotate({s.rotation || 0}, {s.x + SEAT / 2}, {s.y + SEAT / 2})" />
		{/each}
	</svg>
</div>
{#if mode === 'generate' && existing}
	<p class="warn"><Icon name="alert-triangle" size={14} /> {$t('setup_map_replace_warn')}</p>
{/if}
<p class="help">{$t('setup_map_editor_hint')} <a href="/dashboard/map">{$t('setup_map_open')}</a></p>

<style>
	.choices { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 0.6rem; }
	.choice { position: relative; display: flex; flex-direction: column; gap: 0.25rem; padding: 0.8rem 0.9rem; border: 1px solid var(--glass-border); border-radius: var(--radius-md); cursor: pointer; transition: border-color 0.15s, background 0.15s; }
	.choice:hover { border-color: var(--text-muted); }
	.choice.active { border-color: var(--accent); background: color-mix(in srgb, var(--accent) 6%, transparent); }
	.choice input { position: absolute; opacity: 0; pointer-events: none; }
	.choice:focus-within { outline: 2px solid var(--accent); outline-offset: 2px; }
	.choice-title { font-weight: 700; font-size: 0.92rem; }
	.choice-desc { font-size: 0.8rem; color: var(--text-dim); line-height: 1.45; }

	.gen { display: flex; flex-wrap: wrap; gap: 0.8rem 1.2rem; }
	.num { display: flex; flex-direction: column; gap: 0.35rem; font-size: 0.85rem; font-weight: 600; }
	.num input { width: 7.5rem; font-variant-numeric: tabular-nums; }
	.total { margin: 0; font-size: 0.9rem; font-weight: 700; font-variant-numeric: tabular-nums; }

	.preview { height: 260px; border: 1px solid var(--glass-border); border-radius: var(--radius-md); background: var(--map-canvas-bg); padding: 0.5rem; }
	.preview svg { width: 100%; height: 100%; }

	.warn { display: flex; align-items: center; gap: 0.4rem; margin: 0; font-size: 0.82rem; font-weight: 600; color: color-mix(in srgb, var(--warning) 70%, var(--text-main)); }
	.help { margin: 0; font-size: 0.82rem; color: var(--text-dim); line-height: 1.5; max-width: 68ch; }
	.help a { color: var(--accent); font-weight: 600; }

	@media (max-width: 600px) {
		.choices { grid-template-columns: 1fr; }
		.num input { width: 6rem; }
		.preview { height: 200px; }
	}
</style>
