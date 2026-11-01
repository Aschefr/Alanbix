<script>
	import { onMount } from 'svelte';
	import { api } from '$lib/api';
	import { t } from '$lib/i18nStore';
	import { renderMarkdown } from '$lib/markdown';
	import { mediaThumb } from '$lib/config';
	import Icon from '$lib/components/Icon.svelte';
	import AddGameModal from '$lib/components/AddGameModal.svelte';
	import CreateTournamentWizard from '$lib/components/CreateTournamentWizard.svelte';
	import MarkdownEditor from '$lib/components/MarkdownEditor.svelte';

	export let toast = (msg, type) => {};

	// 1. Cover search (SearXNG)
	let searxUrl = 'http://searxng:8080';
	let searxState = 'testing'; // testing | ok | fail
	let searxMsg = '';
	let searxEdited = false;

	async function testSearx(saveIfOk = false) {
		searxState = 'testing';
		try {
			const res = await api.post('/admin/config/test-searxng', { url: searxUrl });
			searxState = res.ok ? 'ok' : 'fail';
			searxMsg = res.ok ? '' : (res.error || '');
			if (res.ok && saveIfOk) {
				await api.put('/admin/config/searxng_url', { value: searxUrl });
				searxEdited = false;
				toast($t('admin_toast_searxng_url_saved'), 'success');
			}
		} catch (e) {
			searxState = 'fail';
			searxMsg = e.message || '';
		}
	}

	// 2. Games
	let games = [];
	let showAddGame = false;
	async function loadGames() {
		try { games = await api.get('/tournaments/games'); } catch {}
	}

	// 3. Formats and rule examples
	const FORMATS = ['single_elim', 'double_elim', 'round_robin', 'ffa'];
	let exampleFormat = 'single_elim';

	// 4. First tournament, then its rules
	let created = null;
	let rules = '';
	let savingRules = false;
	let rulesSaved = false;
	function onCreated(res) {
		created = res;
		rules = $t(`setup_rules_${res?.config?.bracket_type || 'single_elim'}`);
		rulesSaved = false;
	}
	async function saveRules() {
		savingRules = true;
		try {
			await api.put(`/tournaments/${created.id}`, { config: { ...(created.config || {}), custom_rules: rules } });
			rulesSaved = true;
		} catch (e) {
			toast(e.message || $t('admin_error_save'), 'error');
		}
		savingRules = false;
	}

	// 5. Points scale
	let pts = { pts_winner: 1.5, pts_second: 1.3, pts_third: 1.0, pts_participation: 1.0, pts_per_match: 0.5 };
	const fmt = (n) => Number(n).toLocaleString(undefined, { maximumFractionDigits: 1 });
	$: exampleTotal = Math.round((pts.pts_winner + 3 * pts.pts_participation + 2 * pts.pts_per_match) * 10) / 10;

	onMount(async () => {
		try { searxUrl = (await api.get('/admin/config/searxng_url'))?.value || searxUrl; } catch {}
		testSearx();
		loadGames();
		try {
			const v = (await api.get('/admin/config/default_tournament_pts'))?.value;
			if (v) pts = { ...pts, ...(typeof v === 'string' ? JSON.parse(v) : v) };
		} catch {}
	});

	export async function save() {
		if (created && rules.trim() && !rulesSaved) await saveRules();
		return true;
	}
</script>

<!-- 1. Cover search -->
<section class="block">
	<h3><Icon name="search" size={16} /> {$t('setup_games_searx_title')}</h3>
	<p class="help">{$t('setup_games_searx_help')}</p>
	<div class="status {searxState}" role="status">
		{#if searxState === 'testing'}<Icon name="hourglass" size={15} /> {$t('setup_games_searx_testing')}
		{:else if searxState === 'ok'}<Icon name="check-circle" size={15} /> {$t('setup_games_searx_ok')}
		{:else}<Icon name="alert-triangle" size={15} /> {$t('setup_games_searx_fail')}{/if}
	</div>
	{#if searxState === 'fail' || searxEdited}
		<div class="row">
			<input type="url" bind:value={searxUrl} on:input={() => searxEdited = true} spellcheck="false" aria-label={$t('setup_games_searx_url')} />
			<button class="btn-secondary" on:click={() => testSearx(true)}>{$t('setup_games_searx_test')}</button>
		</div>
		{#if searxMsg}<p class="error-detail">{searxMsg}</p>{/if}
		<details class="howto">
			<summary>{$t('setup_games_searx_install')}</summary>
			<div class="howto-body">{@html renderMarkdown($t('setup_games_searx_install_md'))}</div>
		</details>
	{/if}
</section>

<!-- 2. Games -->
<section class="block">
	<h3><Icon name="gamepad" size={16} /> {$t('setup_games_list_title')}</h3>
	{#if games.length}
		<ul class="games">
			{#each games as g (g.id)}
				<li>
					{#if g.image_url}<img src={mediaThumb(g.image_url, 160)} alt="" loading="lazy" />{:else}<span class="cover-ph"><Icon name="gamepad" size={16} /></span>{/if}
					<span>{g.name}</span>
				</li>
			{/each}
		</ul>
	{:else}
		<p class="help">{$t('setup_games_none')}</p>
	{/if}
	<button class="btn-secondary add" on:click={() => showAddGame = true}><Icon name="plus" size={15} /> {$t('admin_games_add')}</button>
</section>

<!-- 3. Formats -->
<section class="block">
	<h3><Icon name="layers" size={16} /> {$t('setup_games_formats_title')}</h3>
	<div class="seg" role="tablist">
		{#each FORMATS as f}
			<button role="tab" aria-selected={exampleFormat === f} class:active={exampleFormat === f} on:click={() => exampleFormat = f}>{$t(`setup_format_${f}`)}</button>
		{/each}
	</div>
	<p class="help">{$t(`setup_format_${exampleFormat}_when`)}</p>
	<div class="example markdown-body">{@html renderMarkdown($t(`setup_rules_${exampleFormat}`))}</div>
</section>

<!-- 4. Points -->
<section class="block">
	<h3><Icon name="trophy" size={16} /> {$t('setup_points_title')}</h3>
	<p class="help">{$t('setup_points_intro')}</p>
	<dl class="points">
		<dt>{$t('setup_points_podium')}</dt><dd>{$t('setup_points_podium_val', { a: fmt(pts.pts_winner), b: fmt(pts.pts_second), c: fmt(pts.pts_third) })}</dd>
		<dt>{$t('setup_points_participation')}</dt><dd>{$t('setup_points_participation_val', { n: fmt(pts.pts_participation) })}</dd>
		<dt>{$t('setup_points_score')}</dt><dd>{$t('setup_points_score_val', { min: fmt(pts.pts_per_match), max: fmt(pts.pts_per_match * 2) })}</dd>
	</dl>
	<p class="help">{$t('setup_points_example', { total: fmt(exampleTotal), w: fmt(pts.pts_winner), p: fmt(3 * pts.pts_participation), s: fmt(2 * pts.pts_per_match) })}</p>
	<p class="help">{$t('setup_points_change')}</p>
</section>

<!-- 5. First tournament -->
<section class="block">
	<h3><Icon name="swords" size={16} /> {$t('setup_tournament_title')}</h3>
	{#if created}
		<p class="status ok"><Icon name="check-circle" size={15} /> {$t('setup_tournament_created', { name: created.name })}</p>
		<label class="field-label" for="setup-rules">{$t('setup_tournament_rules')}</label>
		<MarkdownEditor id="setup-rules" bind:value={rules} rows={9} label={$t('setup_tournament_rules')} />
		<div class="row end">
			{#if rulesSaved}<span class="saved"><Icon name="check" size={14} /> {$t('setup_saved')}</span>{/if}
			<button class="btn-secondary" on:click={saveRules} disabled={savingRules}>{$t('setup_tournament_rules_save')}</button>
			<button class="link-btn" on:click={() => created = null}>{$t('setup_tournament_another')}</button>
		</div>
	{:else if games.length}
		<p class="help">{$t('setup_tournament_help')}</p>
		<div class="wizard-wrap">
			<CreateTournamentWizard {games} onSuccess={onCreated} onGameCreated={loadGames} on:toast={(e) => toast(e.detail.message, e.detail.type)} />
		</div>
	{:else}
		<p class="help">{$t('setup_tournament_need_game')}</p>
	{/if}
</section>

<AddGameModal show={showAddGame} on:close={() => showAddGame = false} on:success={() => { showAddGame = false; loadGames(); }} on:toast={(e) => toast(e.detail.message, e.detail.type)} />

<style>
	.block { display: flex; flex-direction: column; gap: 0.7rem; padding-bottom: 1.4rem; border-bottom: 1px solid var(--glass-border); }
	.block:last-of-type { border-bottom: none; padding-bottom: 0; }
	h3 { display: flex; align-items: center; gap: 0.5rem; margin: 0; font-size: 1rem; font-weight: 700; }
	h3 :global(svg) { color: var(--accent); }
	.help { margin: 0; font-size: 0.85rem; color: var(--text-dim); line-height: 1.55; max-width: 68ch; }
	.status { display: inline-flex; align-items: center; gap: 0.45rem; margin: 0; font-size: 0.88rem; font-weight: 600; color: var(--text-dim); }
	.status.ok { color: var(--success, #16a34a); }
	.status.fail { color: color-mix(in srgb, var(--warning) 70%, var(--text-main)); }
	.row { display: flex; gap: 0.6rem; flex-wrap: wrap; align-items: center; }
	.row input { flex: 1 1 240px; min-width: 0; }
	.row.end { justify-content: flex-end; }
	.error-detail { margin: 0; font-size: 0.8rem; color: var(--text-dim); overflow-wrap: anywhere; }
	.howto { border: 1px solid var(--glass-border); border-radius: var(--radius-md); background: var(--surface-sunken); }
	.howto summary { cursor: pointer; padding: 0.65rem 0.9rem; font-weight: 600; font-size: 0.88rem; }
	.howto-body { padding: 0 0.9rem 0.8rem; font-size: 0.85rem; line-height: 1.55; color: var(--text-dim); }
	.howto-body :global(code), .example :global(code) { font-size: 0.82em; padding: 0.1em 0.35em; border-radius: 4px; background: var(--bg-tertiary); color: var(--text-main); overflow-wrap: anywhere; }
	.howto-body :global(pre) { overflow-x: auto; padding: 0.6rem 0.8rem; border-radius: 8px; background: var(--bg-tertiary); }
	.howto-body :global(pre code) { padding: 0; background: none; }
	.howto-body :global(p), .howto-body :global(ol), .howto-body :global(ul) { margin: 0.5rem 0; }

	.games { list-style: none; margin: 0; padding: 0; display: flex; flex-wrap: wrap; gap: 0.5rem; }
	.games li { display: inline-flex; align-items: center; gap: 0.5rem; padding: 0.3rem 0.7rem 0.3rem 0.3rem; border: 1px solid var(--glass-border); border-radius: 10px; font-size: 0.88rem; font-weight: 600; }
	.games img, .cover-ph { width: 28px; height: 36px; border-radius: 5px; object-fit: cover; background: var(--surface-sunken); display: inline-flex; align-items: center; justify-content: center; color: var(--text-dim); }
	.add { align-self: flex-start; display: inline-flex; align-items: center; gap: 0.4rem; color: var(--text-main); }

	.seg { display: flex; flex-wrap: wrap; gap: 0.3rem; padding: 0.25rem; border-radius: 10px; background: var(--surface-sunken); border: 1px solid var(--glass-border); align-self: flex-start; max-width: 100%; }
	.seg button { border: none; background: transparent; color: var(--text-dim); font: inherit; font-size: 0.85rem; font-weight: 600; padding: 0.4rem 0.75rem; border-radius: 7px; cursor: pointer; }
	.seg button:hover:not(.active) { color: var(--text-main); }
	.seg button.active { background: var(--accent-solid); color: white; }
	.example { padding: 0.8rem 1rem; border: 1px solid var(--glass-border); border-radius: var(--radius-md); font-size: 0.88rem; line-height: 1.55; }
	.example :global(h1), .example :global(h2), .example :global(h3) { font-size: 0.95rem; margin: 0.4rem 0; }
	.example :global(ul), .example :global(ol) { margin: 0.3rem 0; padding-left: 1.2rem; }
	.example :global(p) { margin: 0.3rem 0; }

	.points { display: grid; grid-template-columns: max-content 1fr; gap: 0.4rem 1rem; margin: 0; font-size: 0.88rem; }
	.points dt { font-weight: 700; }
	.points dd { margin: 0; color: var(--text-dim); font-variant-numeric: tabular-nums; }

	.field-label { font-weight: 600; font-size: 0.9rem; }
	.saved { display: inline-flex; align-items: center; gap: 0.3rem; font-size: 0.85rem; font-weight: 600; color: var(--success, #16a34a); }
	.link-btn { background: none; border: none; padding: 0.4rem; color: var(--accent); font: inherit; font-weight: 600; cursor: pointer; }
	.wizard-wrap { border: 1px solid var(--glass-border); border-radius: var(--radius-md); padding: 1rem; }

	@media (max-width: 600px) {
		.points { grid-template-columns: 1fr; gap: 0.1rem; }
		.points dd { margin-bottom: 0.5rem; }
		.wizard-wrap { padding: 0.6rem; }
	}
</style>
