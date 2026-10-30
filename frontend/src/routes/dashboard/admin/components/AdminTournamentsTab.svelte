<script>
	import { get } from 'svelte/store';
	import { api } from '$lib/api';
	import { API_URL, resolveMediaUrl, mediaThumb } from '$lib/config';
	import { t } from '$lib/i18nStore';
	import CreateTournamentWizard from '$lib/components/CreateTournamentWizard.svelte';
	import EditTournamentModal from '$lib/components/EditTournamentModal.svelte';
	import AddGameModal from '$lib/components/AddGameModal.svelte';
	import Icon from '$lib/components/Icon.svelte';

	export let games = [];
	export let tournaments = [];
	export let onReload = () => {};
	export let toast = (msg, type) => {};

	let showAddGameModal = false;
	let overlayMouseDown = false;
	let tournamentToDelete = null;

	// Tournament Editing
	let editingTournament = null;
	let editConfig = {};

	// AI Prompt preview
	let promptPreviewId = null;
	let promptPreviewText = '';
	let promptPreviewTokens = 0;
	let loadingPreview = false;

	// Game management
	let deleteConfirmGameId = null;
	let gameToDeleteWithTournaments = null;
	let deleteGameCheckboxConfirmed = false;
	let editingGame = null;

	function handleKeydown(e) {
		if (e.key === 'Escape') {
			if (tournamentToDelete) tournamentToDelete = null;
			else if (editingGame) editingGame = null;
			else if (gameToDeleteWithTournaments) gameToDeleteWithTournaments = null;
			else if (editingTournament) editingTournament = null;
		}
	}

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

	function openEditTournament(tItem) {
		editingTournament = tItem;
		editConfig = {
			name: tItem.name,
			game_id: tItem.game_id,
			status: tItem.status,
			points_per_win: tItem.points_per_win || 3,
			use_teams: tItem.config?.use_teams || false,
			team_size: tItem.config?.team_size || 1,
			phases: tItem.config?.phases || 'single',
			group_size: tItem.config?.group_size || 4,
			advancers_count: tItem.config?.advancers_count || 2,
			bracket_type: tItem.config?.bracket_type || 'single_elim',
			pts_winner: tItem.config?.pts_winner ?? 1.5,
			pts_second: tItem.config?.pts_second ?? 1.3,
			pts_third: tItem.config?.pts_third ?? 1.0,
			pts_participation: tItem.config?.pts_participation ?? 1.0,
			pts_per_match: tItem.config?.pts_per_match ?? 0.5,
			lower_score_is_better: tItem.config?.lower_score_is_better || false,
			boolean_mode: tItem.config?.boolean_mode || false,
			allow_draws: tItem.config?.allow_draws || false,
			meet_twice: tItem.config?.meet_twice || false,
			ffa_group_size: tItem.config?.ffa_group_size || 4,
			ffa_advancers: tItem.config?.ffa_advancers || 2
		};
	}

	async function updateTournament() {
		try {
			await api.put(`/tournaments/${editingTournament.id}`, {
				name: editConfig.name,
				game_id: editConfig.game_id,
				status: editConfig.status,
				points_per_win: editConfig.points_per_win,
				config: {
					...editingTournament.config,
					use_teams: editConfig.use_teams,
					team_size: editConfig.team_size,
					custom_rules: editConfig.custom_rules,
					team_lock_mode: editConfig.team_lock_mode,
					phases: editConfig.phases,
					group_size: editConfig.group_size,
					advancers_count: editConfig.advancers_count,
					bracket_type: editConfig.bracket_type,
					pts_winner: editConfig.pts_winner,
					pts_second: editConfig.pts_second,
					pts_third: editConfig.pts_third,
					pts_participation: editConfig.pts_participation,
					pts_per_match: editConfig.pts_per_match,
					lower_score_is_better: editConfig.lower_score_is_better,
					boolean_mode: editConfig.boolean_mode,
					allow_draws: editConfig.allow_draws,
					meet_twice: editConfig.meet_twice,
					ffa_group_size: editConfig.ffa_group_size,
					ffa_advancers: editConfig.ffa_advancers
				}
			});
			toast(get(t)('tourneys_toast_updated'), 'success');
			editingTournament = null;
			onReload();
		} catch (e) { toast(e.message, 'error'); }
	}

	async function deleteTournament(id) {
		try {
			await api.delete(`/tournaments/${id}`);
			tournamentToDelete = null;
			toast(get(t)('admin_toast_tournament_deleted'), 'success');
			onReload();
		} catch (e) { toast(e.message, 'error'); }
	}

	async function previewAiPrompt(tournamentId) {
		loadingPreview = true;
		try {
			const res = await api.get(`/tournaments/${tournamentId}/ai-prompt-preview`);
			promptPreviewId = tournamentId;
			promptPreviewText = res.prompt;
			promptPreviewTokens = res.estimated_tokens;
		} catch (e) { toast(e.message || get(t)('admin_toast_preview_error'), 'error'); }
		loadingPreview = false;
	}

	async function retryNotifications(tournamentId) {
		try {
			await api.post(`/tournaments/${tournamentId}/retry-notifications`);
			toast(get(t)('admin_toast_regen_ai_started'), 'success');
		} catch (e) { toast(e.message || get(t)('admin_retry_error'), 'error'); }
	}

	async function deleteGame(id, force = false, unlink = false) {
		try {
			const q = unlink ? '?unlink=true' : (force ? '?force=true' : '');
			await api.delete(`/tournaments/games/${id}${q}`);
			deleteConfirmGameId = null;
			gameToDeleteWithTournaments = null;
			deleteGameCheckboxConfirmed = false;
			onReload();
			toast(unlink ? get(t)('admin_games_unlink_success') : get(t)('admin_toast_game_deleted'), 'success');
		} catch (e) {
			if (e.message && (e.message.includes('confirmer la suppression') || e.message.includes('délier'))) { // i18n-ignore: matches the server error text
				const g = games.find(game => game.id === id);
				const freshTournaments = await api.get('/tournaments');
				const affected = freshTournaments.filter(tItem => tItem.game_id && Number(tItem.game_id) === Number(id));
				gameToDeleteWithTournaments = { game: g, tournaments: affected };
				deleteGameCheckboxConfirmed = false;
			} else {
				toast(e.message || get(t)('admin_delete_error'), 'error');
			}
		}
	}

	function attemptDeleteGame(g) {
		deleteGame(g.id);
	}

	function openEditGame(g) {
		editingGame = g;
	}

	// Live state of a running tournament for the admin list (replaces the coefficient string)
	function liveState(tr) {
		const cfg = tr.config || {};
		const played = (m) => {
			const a = m.score?.[0] ?? null, b = m.score?.[1] ?? null;
			return a !== null && b !== null && (a !== 0 || b !== 0) && (a !== b || !!cfg.allow_draws);
		};
		const playable = (tr.bracket || []).filter(m => (m.p || []).length >= 2 && !m.p.includes(0));
		const pending = playable.filter(m => !played(m));
		const first = pending[0];
		const sameRound = (m) => first && m.id?.s === first.id?.s && m.id?.r === first.id?.r;
		let round = $t('regie_round_finished');
		if (first) {
			round = cfg.bracket_type === 'round_robin' ? $t('spec_matchday_num', { num: first.id?.r || 1 })
				: first.id?.s === 2 ? $t('tourneys_bracket_lb_round', { n: first.id?.r || 1 })
				: $t('tourneys_round_n', { n: first.id?.r || 1 });
		}
		return { round, done: playable.length - pending.length, total: playable.length, waiting: pending.filter(sameRound).length };
	}
</script>

<svelte:window on:keydown={handleKeydown} />

<div class="admin-grid">
	<section class="wizard glass">
		<div class="list-header">
			<div class="flex-row items-center gap-3">
				<div class="list-icon"><Icon name="sparkles" size={20} /></div>
				<div>
					<h2>{$t("admin_tourneys_wizard")}</h2>
					<span class="list-sub">{$t("admin_tourneys_wizard_subtitle")}</span>
				</div>
			</div>
		</div>
		<CreateTournamentWizard 
			{games} 
			onSuccess={() => {
				toast(get(t)('tourneys_toast_joined'), 'success');
				onReload();
			}} 
			onGameCreated={async () => {
				await onReload();
			}}
			on:toast={(e) => toast(e.detail.message, e.detail.type)}
		/>
	</section>

	<div class="flex-col gap-6" style="display:flex; flex-direction:column; gap:1.5rem;">
		<section class="list glass">
			<div class="list-header">
				<div class="flex-row items-center gap-3">
					<div class="list-icon"><Icon name="trophy" size={20} /></div>
					<div>
						<h2>{$t("admin_tourneys_mgmt")}</h2>
						<span class="list-sub">{$t("admin_tourneys_mgmt_subtitle")}</span>
					</div>
				</div>
				<span class="badge-count">{tournaments.length} {$t("admin_tourneys_active", { plural: tournaments.length > 1 ? "s" : "" })}</span>
			</div>
			
			<div class="item-list">
				{#each tournaments as tourney}
					<div class="admin-item-card glass-hover">
						<div class="card-top-row">
							<div class="game-mini-thumb" style="background-image: url({mediaThumb(games.find(g => g.id === tourney.game_id)?.image_url, 160)})">
								{#if !games.find(g => g.id === tourney.game_id)?.image_url}
									<span class="thumb-placeholder"><Icon name="gamepad" size={20} /></span>
								{/if}
							</div>
							<div class="item-info">
								<div class="flex-row items-center gap-2">
									<span class="item-name">{tourney.name}</span>
									<span class="status-pill-sm {tourney.status.toLowerCase()}">{tourney.status === 'OPEN' ? $t('admin_tourneys_status_pill_open') : tourney.status === 'RUNNING' ? $t('admin_tourneys_status_pill_running') : tourney.status === 'CLOSED' ? $t('admin_tourneys_status_pill_closed') : $t('admin_tourneys_status_pill_done')}</span>
								</div>
								<div class="item-meta">
									{games.find(g => g.id === tourney.game_id)?.name || '—'} · {$t('admin_tourneys_players_count', { count: tourney.participants?.length || 0, plural: (tourney.participants?.length || 0) > 1 ? 's' : '' })}
									{#if tourney.status === 'RUNNING'}
										{@const st = liveState(tourney)}
										· {st.round} · {$t('admin_tourneys_live_progress', { done: st.done, total: st.total })}
										{#if st.waiting > 0}<span class="live-waiting">{$t('admin_tourneys_live_waiting', { n: st.waiting })}</span>{/if}
									{/if}
								</div>
							</div>
							<div class="item-actions">
								{#if tourney.status === 'CLOSED'}
									<button class="btn-icon-edit" on:click={() => previewAiPrompt(tourney.id)} title="{$t('admin_tourneys_view_ai_prompt')}" disabled={loadingPreview}>
										<Icon name={loadingPreview && promptPreviewId === tourney.id ? 'hourglass' : 'eye'} size={16} />
									</button>
									<button class="btn-icon-edit" on:click={() => retryNotifications(tourney.id)} title="{$t('admin_tourneys_regen_ai_msgs')}" aria-label="{$t('admin_tourneys_regen_ai_msgs')}">
										<Icon name="refresh" size={16} />
									</button>
								{/if}
								<button class="btn-icon-edit" on:click={() => openEditTournament(tourney)} title="{$t('admin_tourneys_tooltip_edit')}" aria-label="{$t('admin_tourneys_tooltip_edit')}">
									<Icon name="pencil" size={16} />
								</button>
								<button class="btn-icon-danger" on:click={() => tournamentToDelete = tourney} title="{$t('admin_tourneys_tooltip_delete')}" aria-label="{$t('admin_tourneys_tooltip_delete')}">
									<Icon name="trash" size={16} />
								</button>
							</div>
						</div>

						{#if promptPreviewId === tourney.id && promptPreviewText}
							<div class="prompt-preview-panel">
								<div class="prompt-preview-header">
									<span class="btn-ic"><Icon name="eye" size={15} /> {$t('admin_prompt_preview_title')}</span>
									<div style="display:flex;align-items:center;gap:0.5rem">
										<span class="prompt-token-badge">~{$t('ai_tokens_count', { n: promptPreviewTokens })}</span>
										<button class="close-btn" on:click={() => { promptPreviewId = null; promptPreviewText = ''; }} aria-label={$t('common_close')}><Icon name="x" size={16} /></button>
									</div>
								</div>
								<textarea class="prompt-preview-textarea" readonly>{promptPreviewText}</textarea>
							</div>
						{/if}
					</div>
				{:else}
					<div class="empty-list">
						<span class="empty-icon"><Icon name="trophy" size={40} /></span>
						<p>{$t('admin_tourneys_no_created')}</p>
						<span class="text-xs text-dim">{$t("admin_tourneys_wizard_use_wizard")}</span>
					</div>
				{/each}
			</div>
		</section>

		<section class="list glass">
			<div class="list-header">
				<div class="flex-row items-center gap-3">
					<div class="list-icon"><Icon name="gamepad" size={20} /></div>
					<div>
						<h2>{$t("admin_games_library")}</h2>
						<span class="list-sub">{games.length > 1 ? $t("admin_games_library_count_many", { count: games.length }) : $t("admin_games_library_count_1", { count: games.length })}</span>
					</div>
				</div>
				<button class="btn-primary btn-compact btn-ic" on:click={() => showAddGameModal = true}><Icon name="plus" size={15} /> {$t("admin_games_add")}</button>
			</div>
			<div class="game-gallery">
				{#each games as g}
					<div class="game-card glass">
						<div class="game-thumb" style="background-image: url({mediaThumb(g.image_url, 320)})">
							{#if !g.image_url}<span class="thumb-placeholder"><Icon name="gamepad" size={24} /></span>{/if}
							<div class="game-card-actions" class:is-confirming={deleteConfirmGameId === g.id}>
								<button class="game-action-btn edit" on:click={() => openEditGame(g)} title="{$t('admin_tourneys_tooltip_edit')}" aria-label="{$t('admin_tourneys_tooltip_edit')}"><Icon name="pencil" size={14} /></button>
								{#if deleteConfirmGameId === g.id}
									<button class="game-action-btn confirm" on:click={() => attemptDeleteGame(g)} aria-label={$t('admin_tourneys_confirm_yes')}><Icon name="check" size={14} /></button>
									<button class="game-action-btn cancel" on:click={() => deleteConfirmGameId = null} aria-label={$t('admin_tourneys_confirm_no')}><Icon name="x" size={14} /></button>
								{:else}
									<button class="game-action-btn delete" on:click={() => deleteConfirmGameId = g.id} title="{$t('admin_tourneys_tooltip_delete')}" aria-label="{$t('admin_tourneys_tooltip_delete')}"><Icon name="trash" size={14} /></button>
								{/if}
							</div>
						</div>
						<div class="game-info">
							<div class="name">{g.name}</div>
						</div>
					</div>
				{:else}
					<div class="game-empty"><span class="text-dim text-xs">{$t('admin_games_empty')}</span></div>
				{/each}
			</div>
		</section>
	</div>
</div>

<!-- Delete Game Double Confirmation Modal -->
{#if gameToDeleteWithTournaments}
	<!-- svelte-ignore a11y-no-noninteractive-element-interactions -->
	<!-- svelte-ignore a11y-click-events-have-key-events -->
	<div class="modal-overlay-global" use:portal role="dialog" aria-modal="true"
		on:mousedown={(e) => { if (e.target === e.currentTarget) overlayMouseDown = true; }} 
		on:mouseup={(e) => { if (overlayMouseDown && e.target === e.currentTarget) gameToDeleteWithTournaments = null; overlayMouseDown = false; }}>
		<div class="modal-card-global narrow glass" on:click|stopPropagation>
			<header class="edit-modal-header danger-zone">
				<div class="mh-main">
					<span class="mh-ic"><Icon name="alert-triangle" size={20} /></span>
					<div class="mh-text"><h3>{$t('admin_games_nuke_title')}</h3></div>
				</div>
				<button class="close-btn" on:click={() => gameToDeleteWithTournaments = null} aria-label={$t('common_close')}><Icon name="x" size={18} /></button>
			</header>
			<div class="edit-modal-body">
				<div class="flex-col gap-3">
					<p class="text-sm">
						{$t('admin_games_delete_intro', { name: gameToDeleteWithTournaments.game.name })}
					</p>
					
					<div class="danger-warning-box">
						<strong class="warn-title"><Icon name="alert-triangle" size={15} /> {$t('admin_games_cascade_title')}</strong>
						<p class="text-xs text-dim" style="margin: 0.2rem 0 0.6rem;">
							{$t('admin_games_cascade_used_by', { count: gameToDeleteWithTournaments.tournaments.length })}
						</p>
						<ul>
							{#each gameToDeleteWithTournaments.tournaments as tItem}
								<li>
									<strong>{tItem.name}</strong>
									<span class="status-badge {tItem.status.toLowerCase()}">
										{tItem.status === 'OPEN' ? $t('admin_tourneys_status_pill_open') : tItem.status === 'RUNNING' ? $t('admin_tourneys_status_pill_running') : tItem.status === 'DONE' ? $t('admin_tourneys_status_pill_done') : $t('admin_tourneys_status_pill_closed')}
									</span>
								</li>
							{/each}
						</ul>
						<p class="warning-text text-xs">
							{$t('admin_games_cascade_warning')}
						</p>
						<div class="consequence-badges">
							<span class="c-badge"><Icon name="users" size={13} /> {$t('admin_games_cascade_teams')}</span>
							<span class="c-badge"><Icon name="user" size={13} /> {$t('admin_games_cascade_participants')}</span>
							<span class="c-badge"><Icon name="bar-chart" size={13} /> {$t('admin_games_cascade_scores')}</span>
							<span class="c-badge"><Icon name="scale" size={13} /> {$t('admin_games_cascade_conflicts')}</span>
						</div>
					</div>

					<label class="confirm-checkbox-label">
						<input type="checkbox" bind:checked={deleteGameCheckboxConfirmed} />
						<span>{$t('admin_games_nuke_confirm_checkbox')}</span>
					</label>
				</div>
			</div>
			<footer class="edit-modal-footer">
				<button class="btn-secondary" on:click={() => gameToDeleteWithTournaments = null}>{$t('admin_settings_cancel')}</button>
				<button class="btn-primary" on:click={() => deleteGame(gameToDeleteWithTournaments.game.id, false, true)} title={$t('admin_games_unlink_tooltip')}>{$t('admin_games_nuke_unlink_btn')}</button>
				<button class="btn-danger btn-ic" on:click={() => deleteGame(gameToDeleteWithTournaments.game.id, true, false)} disabled={!deleteGameCheckboxConfirmed}><Icon name="trash" size={15} /> {$t('admin_games_nuke_btn_nuke')}</button>
			</footer>
		</div>
	</div>
{/if}

<!-- Delete Tournament Confirmation -->
{#if tournamentToDelete}
	<!-- svelte-ignore a11y-no-noninteractive-element-interactions -->
	<!-- svelte-ignore a11y-click-events-have-key-events -->
	<div class="modal-overlay-global" use:portal role="dialog" aria-modal="true"
		on:mousedown={(e) => { if (e.target === e.currentTarget) overlayMouseDown = true; }}
		on:mouseup={(e) => { if (overlayMouseDown && e.target === e.currentTarget) tournamentToDelete = null; overlayMouseDown = false; }}>
		<div class="modal-card-global narrow glass" on:click|stopPropagation>
			<header class="edit-modal-header danger-zone">
				<div class="mh-main">
					<span class="mh-ic"><Icon name="trash" size={20} /></span>
					<div class="mh-text">
						<h3>{$t('admin_tourneys_delete_title')}</h3>
						<span class="mh-sub">{tournamentToDelete.name}</span>
					</div>
				</div>
				<button class="close-btn" on:click={() => tournamentToDelete = null} aria-label={$t('common_close')}><Icon name="x" size={18} /></button>
			</header>
			<div class="edit-modal-body">
				<p class="delete-text">{$t('admin_tourneys_delete_body')}</p>
				{#if tournamentToDelete.status === 'RUNNING'}
					{@const st = liveState(tournamentToDelete)}
					<div class="danger-warning-box">
						<strong class="warn-title"><Icon name="alert-triangle" size={15} /> {$t('admin_tourneys_delete_running', { done: st.done, total: st.total })}</strong>
					</div>
				{/if}
			</div>
			<footer class="edit-modal-footer">
				<button class="btn-secondary" on:click={() => tournamentToDelete = null}>{$t('admin_settings_cancel')}</button>
				<button class="btn-danger btn-ic" on:click={() => deleteTournament(tournamentToDelete.id)}><Icon name="trash" size={15} /> {$t('admin_tourneys_delete_confirm_btn')}</button>
			</footer>
		</div>
	</div>
{/if}

<!-- Edit Tournament Modal -->

<EditTournamentModal
	tournament={editingTournament}
	{games}
	show={!!editingTournament}
	showStatus={true}
	on:close={() => editingTournament = null}
	on:save={async (e) => {
		editConfig = e.detail.editConfig;
		await updateTournament();
	}}
/>

<!-- Add Game Modal -->
<AddGameModal
	show={showAddGameModal || !!editingGame}
	game={editingGame}
	on:close={() => { showAddGameModal = false; editingGame = null; }}
	on:success={() => onReload()}
	on:toast={(e) => toast(e.detail.message, e.detail.type)}
/>

<style>
	.admin-grid { display: grid; grid-template-columns: minmax(380px, 1fr) 2fr; gap: 2rem; }
	@media (max-width: 1100px) { .admin-grid { grid-template-columns: minmax(0, 1fr); gap: 1rem; } }
	@media (max-width: 640px) {
		.wizard, .list { padding: 1rem; }
		.card-top-row { flex-wrap: wrap; gap: 0.6rem 0.8rem; }
		.item-info { flex: 1 1 0; }
		.item-actions { flex-basis: 100%; justify-content: flex-end; }
	}
	.wizard { padding: 1.5rem; display: flex; flex-direction: column; align-self: start; }
	.list { padding: 1.5rem; display: flex; flex-direction: column; }
	.list-header { display: flex; justify-content: space-between; align-items: center; padding-bottom: 1rem; margin-bottom: 1rem; border-bottom: 1px solid var(--glass-border); }
	.list-icon { width: 40px; height: 40px; flex-shrink: 0; display: flex; align-items: center; justify-content: center; background: var(--accent-soft); color: var(--accent); border-radius: var(--radius-lg); }
	.list-header h2 { margin: 0; font-size: var(--fs-section); }
	.list-sub { font-size: 0.875rem; color: var(--text-dim); }
	.btn-compact { padding: 0.4rem 0.8rem; font-size: 0.8125rem; }
	.delete-text { margin: 0; font-size: 0.9375rem; color: var(--text-main); line-height: 1.5; }
	.badge-count { font-size: 0.75rem; background: var(--accent-soft); color: var(--accent); padding: 0.2rem 0.6rem; border-radius: 4px; font-weight: 800; border: 1px solid var(--accent); }
	.admin-item-card { display: flex; flex-direction: column; gap: 0.5rem; padding: 1rem; border-radius: 12px; margin-bottom: 0.75rem; border: 1px solid var(--glass-border); transition: all 0.2s; }
	.admin-item-card:hover { border-color: var(--accent); background: rgba(59, 130, 246, 0.05); }
	.card-top-row { display: flex; align-items: center; gap: 1rem; }
	.game-mini-thumb { width: 50px; height: 50px; border-radius: 8px; background-size: cover; background-position: center; border: 1px solid var(--glass-border); flex-shrink: 0; }
	.thumb-placeholder { display: flex; align-items: center; justify-content: center; width: 100%; height: 100%; color: var(--text-dim); background: var(--surface-sunken); border-radius: 8px; }
	.item-info { flex-grow: 1; min-width: 0; }
	.item-name { font-weight: 700; font-size: 0.9375rem; }
	.item-meta { font-size: 0.8125rem; color: var(--text-dim); margin-top: 0.2rem; }
	.item-actions { display: flex; flex-direction: row; gap: 0.4rem; align-items: center; flex-shrink: 0; }
	.status-pill-sm { font-size: 0.75rem; font-weight: 700; text-transform: uppercase; letter-spacing: 0.05em; padding: 0.15rem 0.5rem; border-radius: 20px; }
	.status-pill-sm.open { background: rgba(34,197,94,0.1); color: var(--success); border: 1px solid rgba(34,197,94,0.2); }
	.status-pill-sm.running { background: var(--accent-soft); color: var(--accent); border: 1px solid rgba(59,130,246,0.2); }
	.status-pill-sm.done { background: rgba(100,116,139,0.1); color: var(--text-muted); border: 1px solid rgba(100,116,139,0.2); }
	.status-pill-sm.closed { background: rgba(139,92,246,0.1); color: #a78bfa; border: 1px solid rgba(139,92,246,0.2); }
	.btn-icon-edit { background: rgba(255, 255, 255, 0.05); border: 1px solid var(--glass-border); color: var(--text-muted); cursor: pointer; padding: 0.6rem; border-radius: 8px; transition: all 0.2s; display: flex; align-items: center; justify-content: center; }
	.btn-icon-edit:hover { background: rgba(59, 130, 246, 0.2); color: var(--accent); border-color: var(--accent); }
	.btn-icon-danger { background: rgba(255, 255, 255, 0.05); border: 1px solid var(--glass-border); color: var(--text-muted); cursor: pointer; padding: 0.6rem; border-radius: 8px; transition: all 0.2s; display: flex; align-items: center; justify-content: center; }
	.btn-icon-danger:hover { background: rgba(239, 68, 68, 0.2); color: var(--danger); border-color: var(--danger); }
	.confirm-delete-row { display: flex; align-items: center; gap: 0.4rem; background: rgba(239,68,68,0.05); padding: 0.3rem 0.5rem; border-radius: 8px; border: 1px dashed rgba(239,68,68,0.2); }
	.btn-danger-sm { background: rgba(239,68,68,0.2); color: #ef4444; border: 1px solid rgba(239,68,68,0.3); border-radius: 6px; padding: 0.2rem 0.5rem; font-size: 0.75rem; font-weight: 700; cursor: pointer; white-space: nowrap; }
	.btn-danger-sm:hover { background: rgba(239,68,68,0.35); }
	.empty-list { display: flex; flex-direction: column; align-items: center; justify-content: center; padding: 3rem 1rem; gap: 0.5rem; }
	.empty-icon { color: var(--text-muted); opacity: 0.6; display: inline-flex; }
	.empty-list p { color: var(--text-dim); font-weight: 600; margin: 0; }
	.game-gallery { display: grid; grid-template-columns: repeat(auto-fill, minmax(140px, 1fr)); gap: 1rem; margin-top: 1rem; }
	.game-card { overflow: hidden; border: 1px solid var(--glass-border); border-radius: 12px; transition: all 0.2s; }
	.game-card:hover { border-color: var(--accent); transform: translateY(-2px); }
	.game-thumb { height: 95px; background-size: cover; background-position: center; position: relative; display: flex; align-items: center; justify-content: center; }
	.game-info { padding: 0.5rem; text-align: center; font-size: 0.8125rem; font-weight: 600; }
	.game-empty { grid-column: 1 / -1; padding: 2rem; text-align: center; }
	.game-card-actions { position: absolute; inset: 0; background: rgba(0,0,0,0.6); display: flex; align-items: center; justify-content: center; gap: 0.3rem; opacity: 0; transition: opacity 0.2s; }
	.game-card:hover .game-card-actions, .game-card-actions.is-confirming { opacity: 1 !important; pointer-events: auto !important; }
	.game-action-btn { width: 28px; height: 28px; border: 1px solid rgba(255,255,255,0.2); border-radius: 6px; background: rgba(0,0,0,0.5); color: white; cursor: pointer; display: flex; align-items: center; justify-content: center; transition: all 0.15s; }
	.game-action-btn.edit:hover { background: rgba(59,130,246,0.4); border-color: var(--accent); }
	.game-action-btn.delete:hover { background: rgba(239,68,68,0.4); border-color: var(--danger); }
	.game-action-btn.confirm { background: rgba(239,68,68,0.5); border-color: var(--danger); }
	.game-action-btn.cancel { background: rgba(100,116,139,0.4); }
	.prompt-preview-panel { margin-top: 0.75rem; border: 1px solid rgba(139,92,246,0.25); border-radius: 12px; background: rgba(139,92,246,0.04); overflow: hidden; }
	.prompt-preview-header { display: flex; justify-content: space-between; align-items: center; padding: 0.6rem 0.8rem; background: rgba(139,92,246,0.08); border-bottom: 1px solid rgba(139,92,246,0.15); font-size: 0.75rem; font-weight: 700; color: #a78bfa; }
	.prompt-token-badge { font-size: 0.75rem; font-weight: 800; background: rgba(139,92,246,0.15); color: #a78bfa; padding: 0.15rem 0.5rem; border-radius: 6px; border: 1px solid rgba(139,92,246,0.25); }
	.prompt-preview-textarea { width: 100%; min-height: 200px; max-height: 400px; background: var(--surface-sunken); border: none; padding: 0.8rem; color: var(--text-main); font-size: 0.75rem; font-family: 'Courier New', monospace; line-height: 1.5; resize: vertical; }
	.prompt-preview-textarea:focus { outline: none; }
	.danger-warning-box { background: color-mix(in srgb, var(--danger) 8%, transparent); border: 1px solid color-mix(in srgb, var(--danger) 30%, transparent); border-radius: 12px; padding: 1rem 1.1rem; }
	.danger-warning-box strong.warn-title { color: var(--danger); font-size: 0.9375rem; display: flex; align-items: center; gap: 0.4rem; margin-bottom: 0.5rem; }
	.danger-warning-box ul { margin: 0.8rem 0; padding-left: 1.5rem; }
	.danger-warning-box li { color: var(--text-main); font-size: 0.875rem; margin-bottom: 0.3rem; }
	.status-badge { font-size: 0.75rem; font-weight: 700; padding: 0.1rem 0.35rem; border-radius: 4px; text-transform: uppercase; margin-left: 0.3rem; }
	.status-badge.open { background: rgba(59,130,246,0.15); color: #3b82f6; }
	.status-badge.running { background: rgba(16,185,129,0.15); color: #10b981; }
	.status-badge.done { background: rgba(139,92,246,0.15); color: #8b5cf6; }
	.status-badge.closed { background: rgba(107,114,128,0.15); color: #9ca3af; }
	.warning-text { font-size: 0.8125rem; color: var(--text-dim); margin-top: 0.8rem; }
	.consequence-badges { display: flex; flex-wrap: wrap; gap: 0.4rem; margin-top: 0.5rem; }
	.c-badge { font-size: 0.75rem; font-weight: 700; padding: 0.25rem 0.6rem; border-radius: 6px; background: rgba(239, 68, 68, 0.12); color: var(--danger); border: 1px solid color-mix(in srgb, var(--danger) 25%, transparent); display: inline-flex; align-items: center; gap: 0.3rem; }
	.confirm-checkbox-label { display: flex; align-items: flex-start; gap: 0.6rem; cursor: pointer; font-size: 0.875rem; color: var(--text-main); user-select: none; line-height: 1.4; }
	.confirm-checkbox-label input[type="checkbox"] { margin-top: 0.2rem; cursor: pointer; }
	.live-waiting { margin-left: 0.4rem; color: var(--warning); font-weight: 600; }
</style>
