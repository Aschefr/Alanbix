<script>
	import { t } from '$lib/i18nStore';
	import { createEventDispatcher } from 'svelte';

	export let selected;
	export let teams = [];
	export let unassignedPlayers = [];
	export let groupedUnassigned = [];
	export let currentUser = null;
	export let isAdmin = false;
	export let isParticipant = false;
	export let myTeam = null;
	export let liveStandings = [];
	export let getPlayerPts = () => 0;

	const dispatch = createEventDispatcher();
	let newTeamName = '';
	let collapsedTeams = {}; // teamId -> boolean

	function toggleCollapse(teamId) {
		collapsedTeams[teamId] = !collapsedTeams[teamId];
		collapsedTeams = { ...collapsedTeams };
	}

	function collapseAll() {
		const next = {};
		teams.forEach(t => { next[t.id] = true; });
		collapsedTeams = next;
	}

	function expandAll() {
		collapsedTeams = {};
	}

	function handleCreateTeam() {
		if (!newTeamName.trim()) return;
		dispatch('createTeam', { name: newTeamName.trim() });
		newTeamName = '';
	}

	function handleDeleteTeam(teamId) {
		dispatch('deleteTeam', { teamId });
	}

	function handleAddMember(teamId, userId) {
		dispatch('addMember', { teamId, userId });
	}

	function handleRemoveMember(teamId, userId) {
		dispatch('removeMember', { teamId, userId });
	}

	function handleRandomize() {
		dispatch('randomizeTeams');
	}

	function handleToggleLock(team) {
		dispatch('toggleTeamLock', { teamId: team.id, isLocked: !team.is_locked });
	}

	function handleSetCaptain(teamId, captainId) {
		dispatch('setTeamCaptain', { teamId, captainId });
	}

	function canManageLock(team) {
		if (isAdmin) return true;
		const lockMode = selected?.config?.team_lock_mode || 'captain';
		if (lockMode === 'admin' || lockMode === 'open') return false;
		return team.captain_id === currentUser?.id || team.created_by === currentUser?.id;
	}

	function canManageCaptain(team) {
		if (isAdmin) return true;
		return team.captain_id === currentUser?.id || team.created_by === currentUser?.id;
	}
</script>

<div class="teams-section glass">
	<div class="section-title">
		<div class="title-with-actions">
			<h3>👥 {$t('tourneys_tab_teams')} <span class="teams-count">({teams.length})</span></h3>
			{#if teams.length > 1}
				<div class="collapse-actions">
					<button class="btn-ghost-xs" on:click={collapseAll} title={$t('tourneys_teams_collapse_all')}>
						📁 {$t('tourneys_teams_collapse_all')}
					</button>
					<button class="btn-ghost-xs" on:click={expandAll} title={$t('tourneys_teams_expand_all')}>
						📂 {$t('tourneys_teams_expand_all')}
					</button>
				</div>
			{/if}
		</div>
		{#if isAdmin && selected?.status === 'OPEN'}
			<div style="display:flex;gap:0.5rem;">
				<button class="btn-secondary btn-xs" on:click={handleRandomize}>🎲 {$t('tourneys_btn_randomize')}</button>
			</div>
		{/if}
	</div>

	{#if selected?.status === 'OPEN' && (isAdmin || isParticipant)}
		<div class="team-create-row">
			<input type="text" placeholder="{$t('profile_team_placeholder')}" bind:value={newTeamName} class="team-input" on:keydown={(e) => e.key === 'Enter' && handleCreateTeam()} />
			<button class="btn-primary btn-xs" on:click={handleCreateTeam}>+ {$t('tourneys_btn_create_team')}</button>
		</div>
	{/if}

	<div class="teams-grid">
		{#each teams as team (team.id)}
			{@const isCollapsed = !!collapsedTeams[team.id]}
			{@const memberCount = (team.members || []).length}
			{@const userCanLock = canManageLock(team)}
			{@const userCanCaptain = canManageCaptain(team)}
			{@const isFull = selected?.config?.team_size && memberCount >= selected.config.team_size}

			<div class="team-card glass" class:is-collapsed={isCollapsed} class:team-locked={team.is_locked}
				on:dragover|preventDefault={(e) => { if(isAdmin && selected?.status === 'OPEN') e.currentTarget.classList.add('drag-over'); }}
				on:dragleave={(e) => e.currentTarget.classList.remove('drag-over')}
				on:drop|preventDefault={(e) => {
					e.currentTarget.classList.remove('drag-over');
					if(isAdmin && selected?.status === 'OPEN') {
						const uid = e.dataTransfer.getData('userId');
						if(uid) handleAddMember(team.id, parseInt(uid));
					}
				}}>

				<div class="team-card-header">
					<!-- Collapse toggle & Team name -->
					<!-- svelte-ignore a11y-click-events-have-key-events -->
					<div class="team-header-left" on:click={() => toggleCollapse(team.id)}>
						<span class="collapse-chevron">{isCollapsed ? '▶' : '▼'}</span>
						<span class="team-name">{team.name}</span>
						<span class="team-badge-count">({memberCount}{selected?.config?.team_size ? `/${selected.config.team_size}` : ''})</span>
					</div>

					<div class="team-header-actions">
						<!-- Lock toggle / status -->
						{#if userCanLock && selected?.status === 'OPEN'}
							<button 
								class="btn-lock-toggle {team.is_locked ? 'is-locked' : 'is-open'}"
								on:click|stopPropagation={() => handleToggleLock(team)}
								title={team.is_locked ? $t('tourneys_team_unlock_btn') : $t('tourneys_team_lock_btn')}
							>
								{team.is_locked ? '🔒' : '🔓'}
							</button>
						{:else if team.is_locked}
							<span class="lock-indicator" title={$t('tourneys_team_locked')}>🔒</span>
						{/if}

						<!-- Join button -->
						{#if selected?.status === 'OPEN' && isParticipant && !myTeam}
							{#if team.is_locked && !isAdmin}
								<span class="locked-chip" title={$t('tourneys_team_locked')}>🔒</span>
							{:else if isFull && !isAdmin}
								<span class="full-chip">{$t('tourneys_team_full')}</span>
							{:else}
								<button class="btn-join" on:click|stopPropagation={() => handleAddMember(team.id, currentUser.id)} title={$t("tourneys_btn_join_text")}>
									⭐ {$t("tourneys_btn_join_text")}
								</button>
							{/if}
						{/if}

						<!-- Delete team -->
						{#if selected?.status === 'OPEN' && (isAdmin || team.created_by === currentUser?.id || team.captain_id === currentUser?.id)}
							<button class="team-delete" on:click|stopPropagation={() => handleDeleteTeam(team.id)} title={$t("btn_delete")}>✕</button>
						{/if}
					</div>
				</div>

				{#if !isCollapsed}
					<div class="team-members">
						{#each team.members || [] as m}
							{@const isCapt = m.user_id === team.captain_id}
							<div class="team-member" class:is-captain={isCapt}>
								<div class="member-info">
									<span>👤 {m.username}</span>
									{#if isCapt}
										<span class="captain-badge" title={$t('tourneys_team_captain_tooltip')}>👑 {$t('tourneys_team_captain')}</span>
									{/if}
								</div>
								<div class="member-actions">
									{#if selected?.status !== 'OPEN'}
										<span class="member-pts">{getPlayerPts(m.user_id, liveStandings)} {$t('common_pts')}</span>
									{/if}
									{#if userCanCaptain && !isCapt && selected?.status === 'OPEN'}
										<button class="btn-make-captain" on:click={() => handleSetCaptain(team.id, m.user_id)} title={$t('tourneys_make_captain')} aria-label={$t('tourneys_make_captain')}>👑</button>
									{/if}
									{#if selected?.status === 'OPEN' && (isAdmin || m.user_id === currentUser?.id || (userCanCaptain && !team.is_locked))}
										<button class="member-remove" on:click={() => handleRemoveMember(team.id, m.user_id)} title={$t('tourneys_remove_member')} aria-label={$t('tourneys_remove_member')}>✕</button>
									{/if}
								</div>
							</div>
						{:else}
							<div class="empty-team-hint text-dim text-xs">{$t('tourneys_team_empty')}</div>
						{/each}
					</div>

					{#if isAdmin && selected?.status === 'OPEN' && unassignedPlayers.length > 0}
						<select class="team-add-select" on:change={(e) => { if (e.target.value) { handleAddMember(team.id, parseInt(e.target.value)); e.target.value = ''; } }}>
							<option value="">{$t('tourneys_add_member_placeholder')}</option>
							{#each groupedUnassigned as [groupName, members]}
								<optgroup label={groupName || $t('dash_modal_team_fallback')}>
									{#each members as p}
										<option value={p.user_id}>{p.username}</option>
									{/each}
								</optgroup>
							{/each}
						</select>
					{/if}
				{/if}
			</div>
		{:else}
			<span class="text-dim text-sm">{$t("tourneys_no_teams")}</span>
		{/each}
	</div>

	{#if isAdmin && selected?.status === 'OPEN' && unassignedPlayers.length > 0}
		<div class="unassigned-hint">⚠️ {$t('tourneys_unassigned_players', { count: unassignedPlayers.length, plural: unassignedPlayers.length > 1 ? 's' : '' })}</div>
	{/if}
</div>

<style>
	.teams-section { padding: 1rem; border-radius: 14px; }
	.section-title { display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.75rem; flex-wrap: wrap; gap: 0.5rem; }
	.title-with-actions { display: flex; align-items: center; gap: 0.75rem; }
	.section-title h3 { font-size: 0.8rem; font-weight: 700; text-transform: uppercase; letter-spacing: 0.04em; color: var(--text-dim); margin: 0; display: flex; align-items: center; gap: 0.3rem; }
	.teams-count { font-weight: 800; color: var(--accent); }
	.collapse-actions { display: flex; gap: 0.3rem; }
	.btn-ghost-xs { background: rgba(255,255,255,0.06); border: 1px solid var(--glass-border); border-radius: 6px; padding: 0.2rem 0.5rem; font-size: 0.65rem; color: var(--text-dim); cursor: pointer; transition: all 0.15s; }
	.btn-ghost-xs:hover { background: rgba(255,255,255,0.12); color: var(--text-main); }
	.btn-xs { padding: 0.3rem 0.6rem; font-size: 0.7rem; }
	.team-create-row { display: flex; gap: 0.5rem; margin-bottom: 0.8rem; }
	.team-input { flex: 1; padding: 0.5rem 0.8rem; border-radius: 8px; border: 1px solid var(--glass-border); background: var(--surface-sunken); color: var(--input-color); font-size: 0.8rem; }
	.teams-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(220px, 1fr)); gap: 0.75rem; }
	.team-card { padding: 0.75rem; border-radius: 10px; transition: border-color 0.2s, box-shadow 0.2s, background 0.2s, transform 0.2s; border: 1px solid var(--glass-border); }
	.team-card.team-locked { border-color: rgba(245, 158, 11, 0.4); background: rgba(245, 158, 11, 0.03); }
	.team-card.is-collapsed { padding: 0.5rem 0.75rem; }
	:global(.team-card.drag-over) { border-color: rgba(6, 182, 212, 0.8) !important; box-shadow: 0 0 15px rgba(6, 182, 212, 0.4), inset 0 0 10px rgba(6, 182, 212, 0.1) !important; background: rgba(6, 182, 212, 0.05) !important; transform: scale(1.02); }
	.team-card-header { display: flex; justify-content: space-between; align-items: center; }
	.team-card:not(.is-collapsed) .team-card-header { margin-bottom: 0.5rem; padding-bottom: 0.4rem; border-bottom: 1px solid var(--glass-border); }
	.team-header-left { display: flex; align-items: center; gap: 0.4rem; cursor: pointer; user-select: none; flex-grow: 1; min-width: 0; }
	.collapse-chevron { font-size: 0.65rem; color: var(--text-dim); transition: transform 0.15s; }
	.team-name { font-weight: 800; font-size: 0.85rem; color: var(--accent); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
	.team-badge-count { font-size: 0.7rem; font-weight: 700; color: var(--text-dim); }
	.team-header-actions { display: flex; gap: 0.3rem; align-items: center; flex-shrink: 0; }
	.btn-lock-toggle { background: rgba(255,255,255,0.06); border: 1px solid var(--glass-border); border-radius: 6px; padding: 0.15rem 0.4rem; font-size: 0.7rem; cursor: pointer; transition: all 0.15s; }
	.btn-lock-toggle.is-locked { background: rgba(245, 158, 11, 0.2); border-color: rgba(245, 158, 11, 0.4); }
	.lock-indicator { font-size: 0.75rem; opacity: 0.8; }
	.locked-chip { font-size: 0.65rem; padding: 0.1rem 0.35rem; border-radius: 4px; background: rgba(245, 158, 11, 0.15); color: #f59e0b; font-weight: 700; }
	.full-chip { font-size: 0.65rem; padding: 0.1rem 0.35rem; border-radius: 4px; background: rgba(100, 116, 139, 0.2); color: var(--text-dim); font-weight: 700; }
	.team-delete { background: none; border: none; color: var(--danger); cursor: pointer; font-size: 0.75rem; opacity: 0.5; padding: 0.2rem; }
	.team-delete:hover { opacity: 1; }
	.btn-join { background: rgba(16,185,129,0.15); border: 1px solid rgba(16,185,129,0.3); color: #10b981; border-radius: 6px; padding: 0.15rem 0.5rem; font-size: 0.6rem; font-weight: 700; cursor: pointer; transition: all 0.15s; }
	.btn-join:hover { background: rgba(16,185,129,0.3); }
	.team-members { display: flex; flex-direction: column; gap: 0.3rem; margin-bottom: 0.5rem; }
	.team-member { display: flex; justify-content: space-between; align-items: center; font-size: 0.75rem; padding: 0.25rem 0.4rem; background: rgba(59,130,246,0.08); border-radius: 6px; border: 1px solid transparent; }
	.team-member.is-captain { border-color: rgba(251, 191, 36, 0.3); background: rgba(251, 191, 36, 0.06); }
	.member-info { display: flex; align-items: center; gap: 0.35rem; min-width: 0; }
	.member-info span { white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
	.captain-badge { font-size: 0.6rem; font-weight: 800; color: #fbbf24; background: rgba(251, 191, 36, 0.15); padding: 0.05rem 0.3rem; border-radius: 4px; white-space: nowrap; }
	.member-actions { display: flex; align-items: center; gap: 0.3rem; flex-shrink: 0; }
	.btn-make-captain { background: none; border: none; cursor: pointer; font-size: 0.7rem; opacity: 0.4; padding: 0.1rem; }
	.btn-make-captain:hover { opacity: 1; transform: scale(1.15); }
	.member-remove { background: none; border: none; color: var(--danger); cursor: pointer; font-size: 0.65rem; opacity: 0.4; padding: 0.1rem; }
	.member-remove:hover { opacity: 1; }
	.member-pts { font-size: 0.65rem; font-weight: 800; color: #fbbf24; background: rgba(251,191,36,0.1); padding: 0.1rem 0.4rem; border-radius: 4px; white-space: nowrap; }
	.team-add-select { width: 100%; padding: 0.35rem; border-radius: 6px; border: 1px solid var(--glass-border); background: var(--input-bg); color: var(--input-color); font-size: 0.7rem; appearance: none; -webkit-appearance: none; background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='10' height='6'%3E%3Cpath d='M0 0l5 6 5-6z' fill='%23888'/%3E%3C/svg%3E"); background-repeat: no-repeat; background-position: right 0.5rem center; padding-right: 1.5rem; cursor: pointer; }
	.team-add-select option { background: var(--bg-secondary); color: var(--text-main); padding: 0.4rem; }
	.empty-team-hint { padding: 0.4rem; text-align: center; }
	.unassigned-hint { margin-top: 0.75rem; padding: 0.5rem 0.75rem; background: rgba(245,158,11,0.1); border: 1px solid rgba(245,158,11,0.2); border-radius: 8px; color: #f59e0b; font-size: 0.75rem; font-weight: 600; }

	@media (max-width: 900px) {
		.teams-section { padding: 0.5rem; border-radius: 3px !important; }
		.section-title {
			flex-direction: column;
			align-items: stretch;
			gap: 0.35rem;
			margin-bottom: 0.35rem;
		}
		.section-actions {
			display: flex;
			flex-wrap: wrap;
			gap: 0.3rem;
			width: 100%;
		}
		.section-actions button {
			flex: 1;
			white-space: nowrap !important;
			border-radius: 3px !important;
			font-size: 0.7rem !important;
			height: 28px;
			padding: 0 0.4rem;
		}
		.team-card {
			border-radius: 3px !important;
			padding: 0.4rem 0.5rem;
		}
		.btn-join, .btn-lock-toggle, .team-member {
			border-radius: 3px !important;
		}
		.captain-badge, .locked-chip, .full-chip {
			border-radius: 2px !important;
		}
	}
</style>
