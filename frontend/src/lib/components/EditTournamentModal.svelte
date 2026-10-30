<script>
	import { t } from '$lib/i18nStore';
	import { createEventDispatcher } from 'svelte';
	import Icon from '$lib/components/Icon.svelte';

	const dispatch = createEventDispatcher();

	export let tournament = null;
	export let show = false;
	export let showStatus = false;
	export let games = [];

	let editConfig = {};
	let lastTournamentId = null;
	let lastShow = false;
	let overlayMouseDown = false;

	$: if (tournament && (tournament.id !== lastTournamentId || (show && !lastShow))) {
		editConfig = {
			name: tournament.name,
			game_id: tournament.game_id,
			custom_rules: tournament.config?.custom_rules ?? '',
			team_lock_mode: tournament.config?.team_lock_mode || 'captain',
			status: tournament.status,
			points_per_win: tournament.points_per_win || 3,
			use_teams: tournament.config?.use_teams || false,
			team_size: tournament.config?.team_size || 1,
			phases: tournament.config?.phases || 'single',
			group_size: tournament.config?.group_size || 4,
			advancers_count: tournament.config?.advancers_count || 2,
			bracket_type: tournament.config?.bracket_type || 'single_elim',
			pts_winner: tournament.config?.pts_winner ?? 1.5,
			pts_second: tournament.config?.pts_second ?? 1.3,
			pts_third: tournament.config?.pts_third ?? 1.0,
			pts_participation: tournament.config?.pts_participation ?? 1.0,
			pts_per_match: tournament.config?.pts_per_match ?? 0.5,
			lower_score_is_better: tournament.config?.lower_score_is_better || false,
			boolean_mode: tournament.config?.boolean_mode || false,
			allow_draws: tournament.config?.allow_draws || false,
			meet_twice: tournament.config?.meet_twice || false,
			ffa_group_size: tournament.config?.ffa_group_size || 4,
			ffa_advancers: tournament.config?.ffa_advancers || 2
		};
		lastTournamentId = tournament.id;
	}

	$: if (!tournament) {
		lastTournamentId = null;
	}

	$: lastShow = show;

	function close() {
		dispatch('close');
	}

	function save() {
		dispatch('save', { editConfig });
	}

	function handleKeydown(e) {
		if (show && e.key === 'Escape') {
			close();
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
</script>

<svelte:window on:keydown={handleKeydown} />

{#if show && tournament}
	<!-- svelte-ignore a11y-no-noninteractive-element-interactions -->
	<!-- svelte-ignore a11y-click-events-have-key-events -->
	<div class="modal-overlay-global" use:portal role="dialog" aria-modal="true"
		on:mousedown={(e) => { if (e.target === e.currentTarget) overlayMouseDown = true; }} 
		on:mouseup={(e) => { if (overlayMouseDown && e.target === e.currentTarget) close(); overlayMouseDown = false; }}>
		<div class="modal-card-global wide glass" on:click|stopPropagation>
			<header class="edit-modal-header">
				<div class="mh-main">
					<span class="mh-ic"><Icon name="pencil" size={20} /></span>
					<div class="mh-text">
						<h3>{$t("admin_tourneys_edit_modal_title")}</h3>
						<span class="mh-sub">{tournament.name}</span>
					</div>
				</div>
				<button class="close-btn" on:click={close} aria-label={$t('common_close')}><Icon name="x" size={18} /></button>
			</header>
			<div class="edit-modal-body">
				<!-- General -->
				<section class="edit-section">
					<h4 class="edit-section-title"><Icon name="settings" size={16} /> {$t("tourneys_detail_settings_general")}</h4>
					<div class="edit-grid-2col">
						<div class="edit-field">
							<label for="edit-name">{$t("admin_tourneys_wizard_name_lbl")}</label>
							<input id="edit-name" type="text" bind:value={editConfig.name} placeholder={$t("admin_tourneys_wizard_name_placeholder")} />
						</div>

						<div class="edit-field">
							<label for="edit-game"><Icon name="gamepad" size={14} /> {$t("tourneys_edit_game_lbl")}</label>
							<select id="edit-game" bind:value={editConfig.game_id}>
								<option value={null}>{$t('edit_tourney_no_game')}</option>
								{#each games as g}
									<option value={g.id}>{g.name}</option>
								{/each}
							</select>
						</div>

						{#if showStatus}
							<div class="edit-field">
								<label for="edit-status">{$t('admin_tourneys_edit_status')}</label>
								<select id="edit-status" bind:value={editConfig.status}>
									<option value="OPEN">{$t("admin_tourneys_status_pill_open")}</option>
									<option value="RUNNING">{$t("admin_tourneys_status_pill_running")}</option>
									<option value="DONE">{$t("admin_tourneys_status_pill_done")}</option>
									<option value="CLOSED">{$t("admin_tourneys_status_pill_closed")}</option>
								</select>
							</div>
						{/if}

						<div class="edit-field">
							<span class="edit-label">{$t("admin_tourneys_wizard_mode_lbl")}</span>
							<div class="edit-toggle-row">
								<button type="button" class="edit-toggle {!editConfig.use_teams ? 'active' : ''}" on:click={() => editConfig.use_teams = false}><Icon name="user" size={14} /> {$t("admin_tourneys_wizard_mode_solo")}</button>
								<button type="button" class="edit-toggle {editConfig.use_teams ? 'active' : ''}" on:click={() => editConfig.use_teams = true}><Icon name="users" size={14} /> {$t("admin_tourneys_wizard_mode_teams")}</button>
							</div>
						</div>

						{#if editConfig.use_teams}
							<div class="edit-field anim-fade-in">
								<label for="edit-team-size">{$t("admin_tourneys_wizard_team_size")}</label>
								<input id="edit-team-size" type="number" bind:value={editConfig.team_size} min="2" max="16" />
							</div>
							<div class="edit-field anim-fade-in">
								<label for="edit-lock-mode"><Icon name="lock" size={14} /> {$t("tourneys_edit_lock_mode_lbl")}</label>
								<select id="edit-lock-mode" bind:value={editConfig.team_lock_mode}>
									<option value="captain">{$t("tourneys_lock_mode_captain")}</option>
									<option value="admin">{$t("tourneys_lock_mode_admin")}</option>
									<option value="open">{$t("tourneys_lock_mode_open")}</option>
								</select>
							</div>
						{/if}

						<div class="edit-field full-width">
							<label for="edit-rules"><Icon name="book-open" size={14} /> {$t("tourneys_edit_rules_lbl")}</label>
							<textarea id="edit-rules" bind:value={editConfig.custom_rules} placeholder={$t("tourneys_edit_rules_placeholder")} rows="3"></textarea>
						</div>
					</div>
				</section>

				<!-- Format -->
				<section class="edit-section">
					<h4 class="edit-section-title"><Icon name="trophy" size={16} /> {$t("admin_tourneys_edit_format_title")}</h4>
					<div class="edit-field">
						<span class="edit-label">{$t("admin_tourneys_wizard_format_lbl")}</span>
						<div class="edit-toggle-row">
							<button type="button" class="edit-toggle {editConfig.bracket_type === 'single_elim' ? 'active' : ''}" on:click={() => editConfig.bracket_type = 'single_elim'}>{$t("admin_tourneys_wizard_format_single")}</button>
							<button type="button" class="edit-toggle {editConfig.bracket_type === 'double_elim' ? 'active' : ''}" on:click={() => editConfig.bracket_type = 'double_elim'}>{$t("admin_tourneys_wizard_format_double")}</button>
							<button type="button" class="edit-toggle {editConfig.bracket_type === 'round_robin' ? 'active' : ''}" on:click={() => editConfig.bracket_type = 'round_robin'}>{$t("admin_tourneys_wizard_format_championship")}</button>
							<button type="button" class="edit-toggle {editConfig.bracket_type === 'ffa' ? 'active' : ''}" on:click={() => editConfig.bracket_type = 'ffa'}>FFA</button>
						</div>
					</div>

					<div class="edit-grid-2col">
						<button type="button" class="option-card {editConfig.lower_score_is_better ? 'active' : ''}" on:click={() => editConfig.lower_score_is_better = !editConfig.lower_score_is_better}>
							<span class="option-icon"><Icon name="swap" size={18} /></span>
							<span class="option-content">
								<span class="option-label">{$t("tourneys_opt_reverse")}</span>
								<span class="option-desc">{$t("admin_tourneys_wizard_opt_reverse_desc")}</span>
							</span>
						</button>

						<button type="button" class="option-card {editConfig.boolean_mode ? 'active' : ''}" on:click={() => editConfig.boolean_mode = !editConfig.boolean_mode}>
							<span class="option-icon"><Icon name="target" size={18} /></span>
							<span class="option-content">
								<span class="option-label">{$t("admin_tourneys_wizard_opt_boolean")}</span>
								<span class="option-desc">{$t("admin_tourneys_wizard_opt_boolean_desc")}</span>
							</span>
						</button>
					</div>

					{#if editConfig.bracket_type === 'round_robin'}
						<div class="edit-grid-2col anim-fade-in">
							<div class="edit-field">
								<label for="edit-group-size">{$t('tournaments.config.group_size')}</label>
								<input id="edit-group-size" type="number" bind:value={editConfig.group_size} min="2" />
							</div>
							<div class="edit-field">
								<span class="edit-label">{$t('admin_tourneys_edit_rr_options')}</span>
								<div class="edit-toggle-row">
									<button type="button" class="edit-toggle {editConfig.meet_twice ? 'active' : ''}" on:click={() => editConfig.meet_twice = !editConfig.meet_twice}><Icon name="repeat" size={14} /> {$t('tournaments.config.meet_twice')}</button>
									<button type="button" class="edit-toggle {editConfig.allow_draws ? 'active' : ''}" on:click={() => editConfig.allow_draws = !editConfig.allow_draws}><Icon name="scale" size={14} /> {$t("admin_tourneys_wizard_opt_draws")}</button>
								</div>
							</div>
						</div>
					{/if}

					{#if editConfig.bracket_type === 'ffa'}
						<div class="edit-grid-2col anim-fade-in">
							<div class="edit-field">
								<label for="edit-ffa-group-size">{$t('tournaments.config.ffa_group_size')}</label>
								<input id="edit-ffa-group-size" type="number" bind:value={editConfig.ffa_group_size} min="2" />
							</div>
							<div class="edit-field">
								<label for="edit-ffa-advancers">{$t('tournaments.config.ffa_advancers')}</label>
								<input id="edit-ffa-advancers" type="number" bind:value={editConfig.ffa_advancers} min="1" />
							</div>
						</div>
					{/if}
				</section>

				<!-- Structure -->
				<section class="edit-section">
					<h4 class="edit-section-title"><Icon name="layers" size={16} /> {$t("admin_tourneys_wizard_struct_lbl")}</h4>
					<div class="edit-toggle-row">
						<button type="button" class="edit-toggle {editConfig.phases === 'single' ? 'active' : ''}" on:click={() => editConfig.phases = 'single'}>{$t("admin_tourneys_wizard_struct_ffa")}</button>
						<button type="button" class="edit-toggle {editConfig.phases === 'double' ? 'active' : ''}" on:click={() => editConfig.phases = 'double'}>{$t("admin_tourneys_wizard_struct_groups")}</button>
					</div>

					{#if editConfig.phases === 'double'}
						<div class="edit-grid-2col anim-fade-in">
							<div class="edit-field">
								<label for="edit-group-size-double">{$t("admin_tourneys_wizard_group_size")}</label>
								<input id="edit-group-size-double" type="number" bind:value={editConfig.group_size} min="2" max="16" />
							</div>
							<div class="edit-field">
								<label for="edit-advancers-count-double">{$t("admin_tourneys_wizard_advancers")}</label>
								<input id="edit-advancers-count-double" type="number" bind:value={editConfig.advancers_count} min="1" max="8" />
							</div>
						</div>
					{/if}
				</section>

				<!-- Points -->
				<section class="edit-section">
					<h4 class="edit-section-title"><Icon name="medal" size={16} /> {$t("admin_tourneys_wizard_points_lbl")}</h4>
					<div class="edit-pts-grid">
						<div class="edit-field">
							<label for="pts-1">{$t("admin_tourneys_wizard_points_1st")}</label>
							<input id="pts-1" type="number" bind:value={editConfig.pts_winner} min="0" />
						</div>
						<div class="edit-field">
							<label for="pts-2">{$t("admin_tourneys_wizard_points_2nd")}</label>
							<input id="pts-2" type="number" bind:value={editConfig.pts_second} min="0" />
						</div>
						<div class="edit-field">
							<label for="pts-3">{$t("admin_tourneys_wizard_points_3rd")}</label>
							<input id="pts-3" type="number" bind:value={editConfig.pts_third} min="0" />
						</div>
						<div class="edit-field">
							<label for="pts-part">{$t("admin_tourneys_wizard_points_part")}</label>
							<input id="pts-part" type="number" bind:value={editConfig.pts_participation} min="0" />
						</div>
						<div class="edit-field">
							<label for="pts-bonus">{$t("admin_tourneys_wizard_points_bonus")}</label>
							<input id="pts-bonus" type="number" bind:value={editConfig.pts_per_match} min="0" step="0.1" />
						</div>
					</div>
				</section>
			</div>
			<footer class="edit-modal-footer">
				<button class="btn-secondary" on:click={close}>{$t("info_btn_cancel")}</button>
				<button class="btn-primary btn-ic" on:click={save}><Icon name="save" size={16} /> {$t("info_btn_save")}</button>
			</footer>
		</div>
	</div>
{/if}

<style>
	.edit-pts-grid { display: grid; grid-template-columns: repeat(5, minmax(0, 1fr)); gap: 0.75rem; }
	@media (max-width: 640px) { .edit-pts-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); } }
	.edit-field textarea { resize: vertical; }
	.anim-fade-in { animation: quickFadeIn 0.2s ease-out forwards; }
	@keyframes quickFadeIn {
		from { opacity: 0; transform: translateY(4px); }
		to { opacity: 1; transform: translateY(0); }
	}
</style>
