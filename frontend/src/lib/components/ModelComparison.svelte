<script>
	// "How these models were chosen": the measured scores behind the recommended models. The detail stays
	// visible: the note simplifies the reading, it must not hide which tests and weights make it.
	import { t, currentLang } from '$lib/i18nStore';

	export let data; // comparison() of backend/app/ia_model_comparison.py

	$: tasks = Object.entries(data.tasks);
	$: num = (v, digits = 1) => v.toLocaleString($currentLang, { minimumFractionDigits: digits, maximumFractionDigits: digits });

	// One value when both passes agree, a range when they differ
	function score(m, task) {
		const values = m.passes.map((p) => p[task]);
		const lo = Math.min(...values), hi = Math.max(...values);
		return lo === hi ? `${lo}` : `${lo}–${hi}`;
	}

	const flagged = (m, task) => m.excluded.some((e) => e.tasks.includes(task));
</script>

<details class="compare">
	<summary>{$t('model_compare_title')}</summary>
	<p class="help">{$t('model_compare_intro')}</p>
	<div class="scroll" role="region" aria-label={$t('model_compare_title')} tabindex="0">
		<table>
			<thead>
				<tr>
					<th scope="col" class="sticky name">{$t('model_compare_col_model')}</th>
					<th scope="col" class="sticky note">{$t('model_compare_col_note')}</th>
					{#each tasks as [task, spec]}
						<th scope="col" class="num">
							{$t(`model_compare_task_${task}`)}
							<span class="sub">{$t('model_compare_task_head', { questions: spec.questions, weight: Math.round(spec.weight * 100) })}</span>
						</th>
					{/each}
					<th scope="col" class="num">{$t('model_compare_col_seconds')}</th>
					<th scope="col" class="num">{$t('model_compare_col_memory')}</th>
					<th scope="col">{$t('model_compare_col_choice')}</th>
				</tr>
			</thead>
			<tbody>
				{#each data.models as m (m.name)}
					<tr class:out={m.excluded.length}>
						<th scope="row" class="sticky name"><code>{m.name}</code></th>
						<td class="sticky note">{num(m.note)}</td>
						{#each tasks as [task]}
							<td class="num" class:flag={flagged(m, task)}>{score(m, task)}</td>
						{/each}
						<td class="num">{$t('model_compare_seconds', { seconds: num(m.seconds) })}</td>
						<td class="num">
							{#if m.memory_gb == null}—{:else}{$t('model_compare_memory', { memory: num(m.memory_gb), quant: m.quantization })}{/if}
						</td>
						<td class="choice">
							{#if m.excluded.length}
								<span class="why">{$t('model_compare_not_kept')}</span>
								{#each m.excluded as e}
									<span class="reason">{$t(`model_compare_why_${e.code}`, e.params)}</span>
								{/each}
							{:else}
								{#each m.labels as label}
									<span class="label" class:main={label === 'recommended'}>{$t(`model_compare_label_${label}`)}</span>
								{/each}
							{/if}
						</td>
					</tr>
				{/each}
			</tbody>
		</table>
	</div>
	<p class="note">{$t('model_compare_rules', { tie: num(data.tie), seconds: data.fast_seconds })}</p>
	<p class="note">{$t('model_compare_legend')}</p>
</details>

<style>
	.compare { margin: 0.2rem 0 0.6rem; }
	summary { cursor: pointer; font-size: 0.8rem; font-weight: 600; color: var(--text-dim); min-height: 28px; display: inline-flex; align-items: center; }
	summary:hover { color: var(--text-main); }
	.help, .note { margin: 0.35rem 0; font-size: 0.78rem; line-height: 1.5; color: var(--text-muted); max-width: 72ch; }
	.help { color: var(--text-dim); }
	.scroll { overflow-x: auto; border: 1px solid var(--glass-border); border-radius: 8px; max-width: 100%; }
	.scroll:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
	table { border-collapse: separate; border-spacing: 0; font-size: 0.78rem; min-width: 100%; }
	th, td { padding: 0.4rem 0.55rem; text-align: left; vertical-align: top; border-bottom: 1px solid var(--glass-border); white-space: nowrap; }
	tbody tr:last-child > * { border-bottom: none; }
	thead th { font-weight: 600; color: var(--text-dim); vertical-align: bottom; white-space: normal; min-width: 5.5rem; }
	.sub { display: block; font-weight: 500; color: var(--text-muted); white-space: nowrap; }
	.num { text-align: right; font-variant-numeric: tabular-nums; }
	thead .num { text-align: right; }
	/* Model and note stay in view while the detail scrolls sideways on a phone */
	.sticky { position: sticky; background: var(--bg-secondary); z-index: 1; }
	.sticky.name { left: 0; }
	.sticky.note { left: var(--name-width, 9.5rem); text-align: right; font-weight: 700; color: var(--text-main); border-right: 1px solid var(--glass-border); font-variant-numeric: tabular-nums; }
	thead .sticky.note { min-width: 3.5rem; }
	th.name { width: 9.5rem; min-width: 9.5rem; max-width: 9.5rem; }
	code { font-size: 0.78rem; font-weight: 700; color: var(--text-main); white-space: normal; overflow-wrap: anywhere; }
	tr.out code, tr.out .sticky.note { color: var(--text-dim); }
	td.flag { color: var(--danger); font-weight: 700; background: color-mix(in srgb, var(--danger) 12%, transparent); }
	.choice { white-space: normal; min-width: 11rem; }
	.label { display: inline-block; margin: 0 0.25rem 0.2rem 0; font-size: 0.72rem; font-weight: 700; padding: 0.05rem 0.45rem; border-radius: 999px; border: 1px solid var(--glass-border); color: var(--text-dim); }
	.label.main { color: var(--accent); border-color: var(--accent); }
	@media (max-width: 480px) {
		.scroll { --name-width: 6.5rem; }
		th.name { width: 6.5rem; min-width: 6.5rem; max-width: 6.5rem; padding-right: 0.3rem; }
		.sticky.note { padding-left: 0.3rem; }
		thead .sticky.note { min-width: 3rem; }
	}
	.why { display: block; font-weight: 700; color: var(--text-dim); }
	.reason { display: block; color: var(--text-muted); }
</style>
