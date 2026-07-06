<script>
	import { t } from '$lib/i18nStore';
	import { createEventDispatcher } from 'svelte';

	const dispatch = createEventDispatcher();

	export let tournament = null;
	export let show = false;
	export let showStatus = false;

	let editConfig = {};
	let lastTournamentId = null;
	let lastShow = false;

	$: if (tournament && (tournament.id !== lastTournamentId || (show && !lastShow))) {
		editConfig = {
			name: tournament.name,
			game_id: tournament.game_id,
			status: tournament.status,
			points_per_win: tournament.points_per_win || 3,
			use_teams: tournament.config?.use_teams || false,
			team_size: tournament.config?.team_size || 1,
			phases: tournament.config?.phases || 'single',
			group_size: tournament.config?.group_size || 4,
			advancers_count: tournament.config?.advancers_count || 2,
			bracket_type: tournament.config?.bracket_type || 'single_elim',
			pts_winner: tournament.config?.pts_winner ?? 10,
			pts_second: tournament.config?.pts_second ?? 6,
			pts_third: tournament.config?.pts_third ?? 4,
			pts_participation: tournament.config?.pts_participation ?? 1,
			pts_per_match: tournament.config?.pts_per_match ?? tournament.config?.pts_per_goal ?? 1.0,
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

{#if show && tournament}
	<div class="edit-overlay" use:portal on:click={close}>
		<div class="edit-modal glass" on:click|stopPropagation>
			<header class="edit-modal-header">
				<div class="header-title-wrapper">
					<span class="header-emoji">✏️</span>
					<div>
						<h3>{$t("tourneys_btn_edit") || "Éditer"}</h3>
						<span class="header-subtitle">{tournament.name}</span>
					</div>
				</div>
				<button class="close-btn" on:click={close}>✕</button>
			</header>
			<div class="edit-modal-body">
				<!-- Section: Général -->
				<div class="edit-section-card">
					<h4 class="section-title">⚙️ {$t("tourneys_detail_settings_general") || "Configuration Générale"}</h4>
					<div class="edit-grid-2col">
						<div class="edit-field">
							<label for="edit-name">{$t("admin_tourneys_wizard_name_lbl") || "Nom du Tournoi"}</label>
							<input id="edit-name" type="text" bind:value={editConfig.name} placeholder={$t("admin_tourneys_wizard_name_placeholder") || "Nom du tournoi..."} />
						</div>

						{#if showStatus}
							<div class="edit-field">
								<label for="edit-status">{$t('admin_tourneys_edit_status') || "Statut"}</label>
								<select id="edit-status" bind:value={editConfig.status}>
									<option value="OPEN">{$t("admin_tourneys_status_pill_open") || "Ouvert"}</option>
									<option value="RUNNING">{$t("admin_tourneys_status_pill_running") || "En cours"}</option>
									<option value="DONE">{$t("admin_tourneys_status_pill_done") || "Terminé"}</option>
									<option value="CLOSED">{$t("admin_tourneys_status_pill_closed") || "Clôturé"}</option>
								</select>
							</div>
						{/if}

						<div class="edit-field">
							<label>{$t("admin_tourneys_wizard_mode_lbl") || "Mode de Match"}</label>
							<div class="edit-toggle-row">
								<button type="button" class="edit-toggle {!editConfig.use_teams ? 'active' : ''}" on:click={() => editConfig.use_teams = false}>👤 {$t("admin_tourneys_wizard_mode_solo") || "Solo"}</button>
								<button type="button" class="edit-toggle {editConfig.use_teams ? 'active' : ''}" on:click={() => editConfig.use_teams = true}>👥 {$t("admin_tourneys_wizard_mode_teams") || "Équipes"}</button>
							</div>
						</div>
					</div>

					{#if editConfig.use_teams}
						<div class="edit-sub-row anim-fade-in">
							<div class="edit-field narrow">
								<label for="edit-team-size">{$t("admin_tourneys_wizard_team_size") || "Taille d'équipe"}</label>
								<input id="edit-team-size" type="number" bind:value={editConfig.team_size} min="2" max="16" />
							</div>
						</div>
					{/if}
				</div>

				<!-- Section: Format -->
				<div class="edit-section-card">
					<h4 class="section-title">🏆 {$t("admin_tourneys_wizard_format") || "Format"}</h4>
					<div class="edit-field full-width">
						<label>{$t("admin_tourneys_wizard_format_lbl") || "Format d'arbre"}</label>
						<div class="edit-toggle-row">
							<button type="button" class="edit-toggle {editConfig.bracket_type === 'single_elim' ? 'active' : ''}" on:click={() => editConfig.bracket_type = 'single_elim'}>{$t("admin_tourneys_wizard_format_single") || "Élimination Directe"}</button>
							<button type="button" class="edit-toggle {editConfig.bracket_type === 'double_elim' ? 'active' : ''}" on:click={() => editConfig.bracket_type = 'double_elim'}>{$t("admin_tourneys_wizard_format_double") || "Double Élimination"}</button>
							<button type="button" class="edit-toggle {editConfig.bracket_type === 'round_robin' ? 'active' : ''}" on:click={() => editConfig.bracket_type = 'round_robin'}>{$t("admin_tourneys_wizard_format_championship") || "Championnat"}</button>
							<button type="button" class="edit-toggle {editConfig.bracket_type === 'ffa' ? 'active' : ''}" on:click={() => editConfig.bracket_type = 'ffa'}>FFA</button>
						</div>
					</div>

					<!-- Option Toggles Grid -->
					<div class="edit-options-grid">
						<button type="button" class="option-card {editConfig.lower_score_is_better ? 'active' : ''}" on:click={() => editConfig.lower_score_is_better = !editConfig.lower_score_is_better}>
							<div class="option-icon">🔄</div>
							<div class="option-content">
								<div class="option-label">{$t("tourneys_opt_reverse") || "Score Inversé"}</div>
								<div class="option-desc">{$t("admin_tourneys_wizard_opt_reverse_desc") || "(plus petit score gagne)"}</div>
							</div>
						</button>

						<button type="button" class="option-card {editConfig.boolean_mode ? 'active' : ''}" on:click={() => editConfig.boolean_mode = !editConfig.boolean_mode}>
							<div class="option-icon">🎯</div>
							<div class="option-content">
								<div class="option-label">{$t("admin_tourneys_wizard_opt_boolean") || "Mode G/N/P"}</div>
								<div class="option-desc">{$t("admin_tourneys_wizard_opt_boolean_desc") || "(boutons au lieu des scores)"}</div>
							</div>
						</button>
					</div>

					<!-- Suffix configs for formats -->
					{#if editConfig.bracket_type === 'round_robin'}
						<div class="edit-format-specific-panel anim-fade-in">
							<h5 class="specific-title">⚙️ {$t("admin_tourneys_wizard_format_championship") || "Championnat"}</h5>
							<div class="edit-grid-2col">
								<div class="edit-field">
									<label for="edit-group-size">{$t('tournaments.config.group_size') || "Taille des Groupes"}</label>
									<input id="edit-group-size" type="number" bind:value={editConfig.group_size} min="2" />
								</div>
								<div class="edit-options-grid simple-grid">
									<button type="button" class="option-card {editConfig.meet_twice ? 'active' : ''}" on:click={() => editConfig.meet_twice = !editConfig.meet_twice}>
										<div class="option-icon">🔁</div>
										<div class="option-content">
											<div class="option-label">{$t('tournaments.config.meet_twice') || "Aller-Retour"}</div>
										</div>
									</button>
									<button type="button" class="option-card {editConfig.allow_draws ? 'active' : ''}" on:click={() => editConfig.allow_draws = !editConfig.allow_draws}>
										<div class="option-icon">🤝</div>
										<div class="option-content">
											<div class="option-label">{$t("admin_tourneys_wizard_opt_draws") || "Matchs Nuls"}</div>
										</div>
									</button>
								</div>
							</div>
						</div>
					{/if}

					{#if editConfig.bracket_type === 'ffa'}
						<div class="edit-format-specific-panel anim-fade-in">
							<h5 class="specific-title">⚙️ FFA</h5>
							<div class="edit-grid-2col">
								<div class="edit-field">
									<label for="edit-ffa-group-size">{$t('tournaments.config.ffa_group_size') || "Taille Salon"}</label>
									<input id="edit-ffa-group-size" type="number" bind:value={editConfig.ffa_group_size} min="2" />
								</div>
								<div class="edit-field">
									<label for="edit-ffa-advancers">{$t('tournaments.config.ffa_advancers') || "Qualifiés par Salon"}</label>
									<input id="edit-ffa-advancers" type="number" bind:value={editConfig.ffa_advancers} min="1" />
								</div>
							</div>
						</div>
					{/if}
				</div>

				<!-- Section: Structure Globale -->
				<div class="edit-section-card">
					<h4 class="section-title">⛓️ {$t("admin_tourneys_wizard_struct_lbl") || "Structure"}</h4>
					<div class="edit-field full-width">
						<label>{$t("admin_tourneys_wizard_struct_lbl") || "Structure"}</label>
						<div class="edit-toggle-row">
							<button type="button" class="edit-toggle {editConfig.phases === 'single' ? 'active' : ''}" on:click={() => editConfig.phases = 'single'}>{$t("admin_tourneys_wizard_struct_ffa") || "Phase Directe"}</button>
							<button type="button" class="edit-toggle {editConfig.phases === 'double' ? 'active' : ''}" on:click={() => editConfig.phases = 'double'}>{$t("admin_tourneys_wizard_struct_groups") || "Groupes + Finale"}</button>
						</div>
					</div>

					{#if editConfig.phases === 'double'}
						<div class="edit-format-specific-panel anim-fade-in">
							<h5 class="specific-title">⚙️ {$t("admin_tourneys_wizard_struct_groups") || "Groupes + Finale"}</h5>
							<div class="edit-grid-2col">
								<div class="edit-field">
									<label for="edit-group-size-double">{$t("admin_tourneys_wizard_group_size") || "Taille Groupes"}</label>
									<input id="edit-group-size-double" type="number" bind:value={editConfig.group_size} min="2" max="16" />
								</div>
								<div class="edit-field">
									<label for="edit-advancers-count-double">{$t("admin_tourneys_wizard_advancers") || "Qualifiés"}</label>
									<input id="edit-advancers-count-double" type="number" bind:value={editConfig.advancers_count} min="1" max="8" />
								</div>
							</div>
						</div>
					{/if}
				</div>

				<!-- Section: Points -->
				<div class="edit-section-card">
					<h4 class="section-title">🏅 {$t("admin_tourneys_wizard_points_lbl") || "Points"}</h4>
					<div class="edit-pts-grid-modern">
						<div class="edit-pts-card">
							<label>🥇 {$t("admin_tourneys_wizard_points_1st") || "1er"}</label>
							<input type="number" bind:value={editConfig.pts_winner} min="0" />
						</div>
						<div class="edit-pts-card">
							<label>🥈 {$t("admin_tourneys_wizard_points_2nd") || "2e"}</label>
							<input type="number" bind:value={editConfig.pts_second} min="0" />
						</div>
						<div class="edit-pts-card">
							<label>🥉 {$t("admin_tourneys_wizard_points_3rd") || "3e"}</label>
							<input type="number" bind:value={editConfig.pts_third} min="0" />
						</div>
						<div class="edit-pts-card">
							<label>👤 {$t("admin_tourneys_wizard_points_part") || "Parti."}</label>
							<input type="number" bind:value={editConfig.pts_participation} min="0" />
						</div>
						<div class="edit-pts-card">
							<label>⚡ {$t("admin_tourneys_wizard_points_bonus") || "Bonus/Score"}</label>
							<input type="number" bind:value={editConfig.pts_per_match} min="0" step="0.1" />
						</div>
					</div>
				</div>
			</div>
			<footer class="edit-modal-footer">
				<button class="btn-secondary" on:click={close}>{$t("info_btn_cancel") || "Annuler"}</button>
				<button class="btn-primary" on:click={save}>💾 {$t("info_btn_save") || "Enregistrer"}</button>
			</footer>
		</div>
	</div>
{/if}

<style>
	.edit-overlay {
		position: fixed;
		inset: 0;
		background: rgba(0, 0, 0, 0.45);
		backdrop-filter: blur(8px);
		-webkit-backdrop-filter: blur(8px);
		z-index: 9999;
		display: flex;
		align-items: center;
		justify-content: center;
		padding: 1.5rem;
		animation: modalFadeIn 0.2s ease-out forwards;
	}
	@keyframes modalFadeIn {
		from { opacity: 0; }
		to { opacity: 1; }
	}
	.edit-modal {
		width: 580px;
		max-width: 100%;
		max-height: 85vh;
		border-radius: 16px;
		border: 1px solid var(--glass-border);
		box-shadow: 0 30px 70px rgba(0, 0, 0, 0.45);
		background: var(--bg-primary);
		display: flex;
		flex-direction: column;
		overflow: hidden;
		animation: modalSlideUp 0.3s cubic-bezier(0.16, 1, 0.3, 1) forwards;
	}
	@keyframes modalSlideUp {
		from { transform: translateY(20px) scale(0.97); }
		to { transform: translateY(0) scale(1); }
	}
	.edit-modal-header {
		display: flex;
		justify-content: space-between;
		align-items: center;
		padding: 1.25rem 1.5rem;
		border-bottom: 1px solid var(--glass-border);
		background: var(--surface-sunken);
		flex-shrink: 0;
	}
	.header-title-wrapper {
		display: flex;
		align-items: center;
		gap: 0.75rem;
	}
	.header-emoji {
		font-size: 1.3rem;
	}
	.header-subtitle {
		font-size: 0.72rem;
		color: var(--text-dim);
		font-weight: 500;
	}
	.close-btn {
		background: var(--hover-tint);
		border: 1px solid var(--glass-border);
		color: var(--text-dim);
		cursor: pointer;
		font-size: 0.85rem;
		width: 30px;
		height: 30px;
		display: flex;
		align-items: center;
		justify-content: center;
		border-radius: 50%;
		transition: all 0.2s;
	}
	.close-btn:hover {
		background: var(--accent-soft);
		color: var(--accent);
		border-color: var(--accent);
		transform: rotate(90deg);
	}
	.edit-modal-body {
		padding: 1.5rem 1.5rem 2.5rem 1.5rem;
		display: flex;
		flex-direction: column;
		gap: 1.25rem;
		overflow-y: auto;
		flex: 1;
		min-height: 0;
	}
	.edit-section-card {
		background: var(--surface-raised);
		border: 1px solid var(--glass-border);
		border-radius: 12px;
		padding: 1.25rem;
		display: flex;
		flex-direction: column;
		gap: 1rem;
		box-shadow: 0 4px 15px rgba(0, 0, 0, 0.05);
	}
	.section-title {
		font-size: 0.75rem;
		font-weight: 800;
		color: var(--text-main);
		margin: 0;
		text-transform: uppercase;
		letter-spacing: 0.05em;
		border-bottom: 1px solid var(--glass-border);
		padding-bottom: 0.4rem;
		display: flex;
		align-items: center;
		gap: 0.4rem;
	}
	.edit-grid-2col {
		display: grid;
		grid-template-columns: repeat(2, 1fr);
		gap: 1rem;
	}
	.edit-field {
		display: flex;
		flex-direction: column;
		gap: 0.35rem;
	}
	.edit-field.full-width {
		grid-column: 1 / -1;
	}
	.edit-field label {
		font-size: 0.65rem;
		font-weight: 700;
		color: var(--text-dim);
		text-transform: uppercase;
		letter-spacing: 0.05em;
	}
	.edit-field input[type="text"],
	.edit-field input[type="number"],
	.edit-field select {
		width: 100%;
		padding: 0.5rem 0.75rem;
		font-size: 0.8rem;
		background: var(--surface-sunken);
		border: 1px solid var(--glass-border);
		border-radius: 8px;
		color: var(--text-main);
		transition: all 0.2s;
	}
	.edit-field input:focus,
	.edit-field select:focus {
		outline: none;
		border-color: var(--accent);
		box-shadow: 0 0 0 3px var(--accent-glow);
	}
	.edit-sub-row {
		display: flex;
		gap: 1rem;
		margin-top: -0.25rem;
	}
	.edit-field.narrow {
		max-width: 150px;
	}
	.edit-toggle-row {
		display: flex;
		gap: 0.3rem;
		background: var(--surface-sunken);
		padding: 0.2rem;
		border-radius: 8px;
		border: 1px solid var(--glass-border);
		width: 100%;
	}
	.edit-toggle {
		flex: 1;
		padding: 0.4rem 0.6rem;
		font-size: 0.7rem;
		font-weight: 700;
		border: none;
		border-radius: 6px;
		background: transparent;
		color: var(--text-dim);
		cursor: pointer;
		transition: all 0.15s;
		white-space: nowrap;
	}
	.edit-toggle:hover {
		color: var(--text-main);
		background: var(--hover-tint);
	}
	.edit-toggle.active {
		background: var(--bg-primary);
		color: var(--accent);
		box-shadow: 0 2px 6px rgba(0, 0, 0, 0.1), 0 0 0 1px var(--glass-border);
	}
	.edit-options-grid {
		display: grid;
		grid-template-columns: repeat(2, 1fr);
		gap: 0.75rem;
		width: 100%;
	}
	.edit-options-grid.simple-grid {
		grid-column: 2;
		align-content: end;
	}
	.option-card {
		display: flex;
		align-items: flex-start;
		gap: 0.6rem;
		padding: 0.6rem 0.8rem;
		background: var(--surface-sunken);
		border: 1px solid var(--glass-border);
		border-radius: 8px;
		cursor: pointer;
		text-align: left;
		transition: all 0.2s;
	}
	.option-card:hover {
		border-color: var(--accent);
		background: var(--hover-tint);
	}
	.option-card.active {
		border-color: var(--accent);
		background: var(--accent-soft);
		box-shadow: 0 0 8px var(--accent-glow);
	}
	.option-icon {
		font-size: 1rem;
		margin-top: 0.05rem;
	}
	.option-content {
		display: flex;
		flex-direction: column;
		gap: 0.1rem;
	}
	.option-label {
		font-size: 0.72rem;
		font-weight: 700;
		color: var(--text-main);
	}
	.option-desc {
		font-size: 0.6rem;
		color: var(--text-muted);
		line-height: 1.2;
	}
	.edit-format-specific-panel {
		background: var(--surface-sunken);
		border: 1px solid var(--glass-border);
		border-radius: 8px;
		padding: 0.8rem;
		margin-top: 0.25rem;
		display: flex;
		flex-direction: column;
		gap: 0.6rem;
		width: 100%;
	}
	.specific-title {
		font-size: 0.7rem;
		font-weight: 800;
		color: var(--text-dim);
		margin: 0;
		text-transform: uppercase;
		letter-spacing: 0.05em;
	}
	.edit-pts-grid-modern {
		display: grid;
		grid-template-columns: repeat(5, 1fr);
		gap: 0.6rem;
		width: 100%;
	}
	.edit-pts-card {
		background: var(--surface-sunken);
		border: 1px solid var(--glass-border);
		border-radius: 8px;
		padding: 0.5rem;
		display: flex;
		flex-direction: column;
		align-items: center;
		gap: 0.25rem;
		transition: all 0.2s;
	}
	.edit-pts-card:hover {
		border-color: var(--accent);
	}
	.edit-pts-card.full-row {
		grid-column: 1 / -1;
		flex-direction: row;
		justify-content: space-between;
		padding: 0.5rem 0.8rem;
	}
	.edit-pts-card.full-row label {
		margin-bottom: 0;
	}
	.edit-pts-card.full-row input {
		width: 80px;
		text-align: right;
	}
	.edit-pts-card label {
		font-size: 0.6rem;
		font-weight: 700;
		color: var(--text-dim);
		display: flex;
		align-items: center;
		justify-content: center;
		gap: 0.25rem;
		white-space: nowrap;
	}
	.edit-pts-card input {
		width: 100%;
		padding: 0.35rem;
		text-align: center;
		font-size: 0.8rem;
		font-weight: 800;
		background: var(--bg-primary);
		border: 1px solid var(--glass-border);
		border-radius: 6px;
		color: var(--accent);
		transition: all 0.2s;
	}
	.edit-pts-card input:focus {
		outline: none;
		border-color: var(--accent);
		box-shadow: 0 0 0 2px var(--accent-glow);
	}
	.edit-modal-footer {
		display: flex;
		justify-content: flex-end;
		gap: 0.6rem;
		padding: 1rem 1.5rem;
		border-top: 1px solid var(--glass-border);
		background: var(--bg-secondary);
		flex-shrink: 0;
	}
	.anim-fade-in {
		animation: quickFadeIn 0.2s ease-out forwards;
	}
	@keyframes quickFadeIn {
		from { opacity: 0; transform: translateY(4px); }
		to { opacity: 1; transform: translateY(0); }
	}
</style>
