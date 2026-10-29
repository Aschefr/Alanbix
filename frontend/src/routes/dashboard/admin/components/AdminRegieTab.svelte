<script>
	// Régie: what needs the organiser's attention right now during the LAN
	// (help calls, scores to enter, quick moderation, tournament progress).
	import { onMount, onDestroy } from 'svelte';
	import { api } from '$lib/api';
	import { wsMessageStore } from '$lib/ws';
	import { t } from '$lib/i18nStore';
	import Icon from '$lib/components/Icon.svelte';

	export let tournaments = [];
	export let onReload = () => {};
	export let onOpenConversation = (convId) => {};
	export let toast = (msg, type) => {};
	export let pendingCount = 0;

	let calls = [];
	let users = [];
	let playerQuery = '';
	let scoreDraft = {};
	let savingKey = null;
	let wsUnsub = null;

	async function loadCalls() {
		try { calls = await api.get('/ia/admin-calls?status=pending'); } catch { calls = []; }
	}
	async function loadUsers() {
		try { users = await api.get('/admin/users'); } catch { users = []; }
	}

	onMount(() => {
		loadCalls();
		loadUsers();
		wsUnsub = wsMessageStore.subscribe(msg => {
			if (!msg) return;
			if (msg.type === 'admin_calls_updated') loadCalls();
			if (msg.type === 'users_updated') loadUsers();
		});
	});
	onDestroy(() => { if (wsUnsub) wsUnsub(); });

	async function resolveCall(id) {
		try { await api.put(`/ia/admin-calls/${id}/resolve`, { note: '' }); await loadCalls(); }
		catch (e) { toast(e.message || $t('regie_error_generic'), 'error'); }
	}
	async function dismissCall(id) {
		try { await api.put(`/ia/admin-calls/${id}/dismiss`, {}); await loadCalls(); }
		catch (e) { toast(e.message || $t('regie_error_generic'), 'error'); }
	}

	const isDone = (m, cfg) => {
		const a = m.score?.[0] ?? null, b = m.score?.[1] ?? null;
		return a !== null && b !== null && (a !== 0 || b !== 0) && (a !== b || !!cfg?.allow_draws);
	};
	const roundOf = (m) => `${m.id?.s ?? 1}_${m.id?.r ?? 1}`;

	function nameOf(pid, tourney, users) {
		if (pid < 0) return tourney.config?._team_map?.[String(pid)] || `#${Math.abs(pid)}`;
		return users.find(u => u.id === pid)?.username || `#${pid}`;
	}
	function roundLabel(m, tourney) {
		if (tourney.config?.bracket_type === 'round_robin') return $t('spec_matchday_num', { num: m.id?.r || 1 });
		if (m.id?.s === 2) return $t('tourneys_bracket_lb_round', { n: m.id?.r || 1 });
		return $t('tourneys_round_n', { n: m.id?.r || 1 });
	}

	$: running = (tournaments || []).filter(tr => tr.status === 'RUNNING' && Array.isArray(tr.bracket));

	// For each running tournament: the 1v1 matches of its current round that still need a score
	$: toScore = running.flatMap(tr => {
		const playable = tr.bracket.filter(m => (m.p || []).length === 2 && !m.p.includes(0));
		const pending = playable.filter(m => !isDone(m, tr.config));
		if (!pending.length) return [];
		const current = roundOf(pending[0]);
		return pending.filter(m => roundOf(m) === current).map(m => ({ tr, m, key: `${tr.id}_${m.id?.s}_${m.id?.r}_${m.id?.m}` }));
	});

	$: progress = running.map(tr => {
		const playable = tr.bracket.filter(m => (m.p || []).length >= 2 && !m.p.includes(0));
		const done = playable.filter(m => isDone(m, tr.config)).length;
		const firstPending = playable.find(m => !isDone(m, tr.config));
		return { tr, done, total: playable.length, current: firstPending ? roundLabel(firstPending, tr) : $t('regie_round_finished') };
	});

	$: pendingCount = calls.length + toScore.length;
	$: for (const item of toScore) if (!scoreDraft[item.key]) scoreDraft[item.key] = { a: '', b: '' };

	async function submitScore(item) {
		const d = scoreDraft[item.key] || {};
		const a = parseInt(d.a, 10), b = parseInt(d.b, 10);
		if (Number.isNaN(a) || Number.isNaN(b)) return;
		savingKey = item.key;
		try {
			await api.put(`/tournaments/${item.tr.id}/score`, { match_s: item.m.id.s, match_r: item.m.id.r, match_m: item.m.id.m, score: [a, b] });
			delete scoreDraft[item.key];
			scoreDraft = scoreDraft;
			await onReload();
		} catch (e) {
			toast(e.message || $t('regie_error_generic'), 'error');
		} finally {
			savingKey = null;
		}
	}

	const isMuted = (u) => u.public_chat_muted_until && new Date(u.public_chat_muted_until) > new Date();
	$: players = users.filter(u => !u.is_admin);
	$: mutedPlayers = players.filter(isMuted);
	$: foundPlayers = playerQuery.trim()
		? players.filter(u => `${u.username} ${u.team_name || ''}`.toLowerCase().includes(playerQuery.trim().toLowerCase())).slice(0, 6)
		: mutedPlayers;

	async function toggleMute(u) {
		const muted = isMuted(u);
		try {
			await api.post(`/public-chat/mute/${u.id}`, { duration_minutes: muted ? 0 : 30 });
			toast(muted ? $t('regie_unmuted', { name: u.username }) : $t('regie_muted', { name: u.username }), 'success');
			await loadUsers();
		} catch (e) {
			toast(e.message || $t('regie_error_generic'), 'error');
		}
	}
	const timeAgo = (iso) => new Date(iso).toLocaleTimeString('fr-FR', { hour: '2-digit', minute: '2-digit' });
</script>

<div class="regie">
	<section class="rg-block glass" class:alert={calls.length > 0}>
		<header><h2><Icon name="bell" size={16} /> {$t('regie_calls_title')}</h2>{#if calls.length}<span class="rg-count alert">{calls.length}</span>{/if}</header>
		{#if calls.length === 0}
			<p class="rg-empty">{$t('ai_admin_calls_empty')}</p>
		{:else}
			<ul class="rg-list">
				{#each calls as call (call.id)}
					<li class="rg-item">
						<div class="rg-item-main">
							<strong>{call.username}</strong> <span class="rg-time">{timeAgo(call.created_at)}</span>
							<p class="rg-question">{call.question}</p>
						</div>
						<div class="rg-actions">
							{#if call.conversation_id}
								<button class="btn-secondary rg-btn" on:click={() => onOpenConversation(call.conversation_id)}>{$t('regie_reply')}</button>
							{/if}
							<button class="btn-primary rg-btn" on:click={() => resolveCall(call.id)}>{$t('ai_call_admin_resolve_btn')}</button>
							<button class="rg-link" on:click={() => dismissCall(call.id)}>{$t('ai_call_admin_dismiss_btn')}</button>
						</div>
					</li>
				{/each}
			</ul>
		{/if}
	</section>

	<section class="rg-block glass">
		<header><h2><Icon name="swords" size={16} /> {$t('regie_scores_title')}</h2>{#if toScore.length}<span class="rg-count">{toScore.length}</span>{/if}</header>
		{#if toScore.length === 0}
			<p class="rg-empty">{$t('regie_scores_empty')}</p>
		{:else}
			<ul class="rg-list">
				{#each toScore as item (item.key)}
					<li class="rg-item rg-score-item">
						<div class="rg-item-main">
							<span class="rg-meta">{item.tr.name} · {roundLabel(item.m, item.tr)}</span>
							<span class="rg-versus">{nameOf(item.m.p[0], item.tr, users)} <span class="rg-vs">vs</span> {nameOf(item.m.p[1], item.tr, users)}</span>
						</div>
						<form class="rg-score" on:submit|preventDefault={() => submitScore(item)}>
							<input type="number" min="0" inputmode="numeric" bind:value={scoreDraft[item.key].a} aria-label={nameOf(item.m.p[0], item.tr, users)} />
							<span>–</span>
							<input type="number" min="0" inputmode="numeric" bind:value={scoreDraft[item.key].b} aria-label={nameOf(item.m.p[1], item.tr, users)} />
							<button class="btn-primary rg-btn" type="submit" disabled={savingKey === item.key || scoreDraft[item.key].a === '' || scoreDraft[item.key].b === '' || scoreDraft[item.key].a == null || scoreDraft[item.key].b == null}>{$t('regie_validate')}</button>
						</form>
					</li>
				{/each}
			</ul>
		{/if}
	</section>

	<section class="rg-block glass">
		<header><h2><Icon name="shield" size={16} /> {$t('regie_moderation_title')}</h2>{#if mutedPlayers.length}<span class="rg-count">{$t('regie_muted_count', { n: mutedPlayers.length })}</span>{/if}</header>
		<input class="rg-search" type="search" bind:value={playerQuery} placeholder={$t('admin_players_search_placeholder')} aria-label={$t('admin_players_search_placeholder')} />
		{#if foundPlayers.length === 0}
			<p class="rg-empty">{playerQuery.trim() ? $t('admin_players_no_match') : $t('regie_no_muted')}</p>
		{:else}
			<ul class="rg-list">
				{#each foundPlayers as u (u.id)}
					<li class="rg-item rg-player">
						<span><strong>{u.username}</strong>{#if u.team_name} <span class="rg-meta">· {u.team_name}</span>{/if}</span>
						<button class="rg-btn {isMuted(u) ? 'btn-secondary' : 'btn-outline-danger'}" on:click={() => toggleMute(u)}>
							{isMuted(u) ? $t('admin_players_tooltip_unmute') : $t('admin_players_tooltip_mute')}
						</button>
					</li>
				{/each}
			</ul>
		{/if}
	</section>

	<section class="rg-block glass">
		<header><h2><Icon name="trophy" size={16} /> {$t('dash_tab_tournaments')}</h2></header>
		{#if progress.length === 0}
			<p class="rg-empty">{$t('dash_no_tournament')}</p>
		{:else}
			<ul class="rg-list">
				{#each progress as p (p.tr.id)}
					<li class="rg-progress">
						<div class="rg-progress-top">
							<strong>{p.tr.name}</strong>
							<span class="rg-meta">{p.current} · {p.done}/{p.total}</span>
						</div>
						<div class="rg-bar"><span style="width: {p.total ? (p.done / p.total) * 100 : 0}%"></span></div>
					</li>
				{/each}
			</ul>
		{/if}
	</section>
</div>

<style>
	.regie { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 1rem; align-items: start; }
	.rg-block { padding: 1rem 1.1rem; border-radius: var(--radius-lg); display: flex; flex-direction: column; gap: 0.75rem; min-width: 0; }
	.rg-block.alert { border-color: var(--danger); }
	.rg-block header { display: flex; align-items: center; justify-content: space-between; gap: 0.75rem; }
	.rg-block h2 { font-size: 1rem; display: inline-flex; align-items: center; gap: 0.5rem; margin: 0; }
	.rg-count { font-size: 0.78rem; font-weight: 700; color: var(--accent); background: var(--accent-soft); border-radius: 999px; padding: 0.1rem 0.55rem; }
	.rg-count.alert { color: #fff; background: var(--danger); }
	.rg-empty { margin: 0; color: var(--text-dim); font-size: 0.9rem; }
	.rg-list { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 0.5rem; max-height: 420px; overflow-y: auto; }
	.rg-item { display: flex; align-items: center; justify-content: space-between; gap: 0.75rem; flex-wrap: wrap; padding: 0.55rem 0.75rem; border-radius: var(--radius-md); background: var(--surface-sunken); border: 1px solid var(--glass-border); }
	.rg-item-main { min-width: 0; flex: 1 1 200px; display: flex; flex-direction: column; gap: 0.15rem; }
	.rg-time, .rg-meta { color: var(--text-muted); font-size: 0.82rem; }
	.rg-question { margin: 0.2rem 0 0; font-size: 0.9rem; color: var(--text-main); line-height: 1.4; }
	.rg-versus { font-weight: 700; color: var(--text-main); }
	.rg-vs { color: var(--text-dim); font-weight: 500; margin: 0 0.2rem; }
	.rg-actions { display: flex; align-items: center; gap: 0.4rem; }
	.rg-btn { padding: 0.35rem 0.8rem; font-size: 0.82rem; white-space: nowrap; }
	.rg-link { background: none; border: none; color: var(--text-dim); font-size: 0.82rem; cursor: pointer; text-decoration: underline; }
	.rg-score { display: flex; align-items: center; gap: 0.4rem; }
	.rg-score input { width: 52px; height: 34px; text-align: center; font-weight: 700; padding: 0; }
	.rg-search { width: 100%; padding: 0.45rem 0.7rem; font-size: 0.9rem; }
	.rg-progress { display: flex; flex-direction: column; gap: 0.35rem; }
	.rg-progress-top { display: flex; justify-content: space-between; gap: 0.75rem; }
	.rg-bar { height: 6px; border-radius: 999px; background: var(--surface-sunken); overflow: hidden; }
	.rg-bar span { display: block; height: 100%; background: var(--accent); border-radius: inherit; }
	@media (max-width: 1100px) { .regie { grid-template-columns: 1fr; } }
</style>
