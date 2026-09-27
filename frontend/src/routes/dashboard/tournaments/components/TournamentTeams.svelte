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
</script>

<div class="teams-section glass">
	<div class="section-title">
		<h3>👥 {$t('tourneys_tab_teams')}</h3>
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
		{#each teams as team}
			<div class="team-card glass"
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
					<span class="team-name">{team.name}</span>
					<div style="display:flex;gap:0.3rem;align-items:center;">
						{#if selected?.status === 'OPEN' && isParticipant && !myTeam}
							<button class="btn-join" on:click={() => handleAddMember(team.id, currentUser.id)} title={$t("tourneys_btn_join_text")}>⭐ {$t("tourneys_btn_join_text")}</button>
						{/if}
						{#if selected?.status === 'OPEN' && (isAdmin || team.created_by === currentUser?.id)}
							<button class="team-delete" on:click={() => handleDeleteTeam(team.id)} title={$t("btn_delete")}>✕</button>
						{/if}
					</div>
				</div>
				<div class="team-members">
					{#each team.members || [] as m}
						<div class="team-member">
							<span>👤 {m.username}</span>
							<div style="display:flex;align-items:center;gap:0.4rem">
								{#if selected?.status !== 'OPEN'}
									<span class="member-pts">{getPlayerPts(m.user_id, liveStandings)} pts</span>
								{/if}
							{#if selected?.status === 'OPEN' && (isAdmin || m.user_id === currentUser?.id)}
								<button class="member-remove" on:click={() => handleRemoveMember(team.id, m.user_id)}>✕</button>
							{/if}
							</div>
						</div>
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
	.section-title { display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.75rem; }
	.section-title h3 { font-size: 0.8rem; font-weight: 700; text-transform: uppercase; letter-spacing: 0.04em; color: var(--text-dim); margin: 0; }
	.btn-xs { padding: 0.3rem 0.6rem; font-size: 0.7rem; }
	.team-create-row { display: flex; gap: 0.5rem; margin-bottom: 0.8rem; }
	.team-input { flex: 1; padding: 0.5rem 0.8rem; border-radius: 8px; border: 1px solid var(--glass-border); background: var(--surface-sunken); color: var(--input-color); font-size: 0.8rem; }
	.teams-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(200px, 1fr)); gap: 0.75rem; }
	.team-card { padding: 0.75rem; border-radius: 10px; transition: border-color 0.2s, box-shadow 0.2s, background 0.2s, transform 0.2s; }
	:global(.team-card.drag-over) { border-color: rgba(6, 182, 212, 0.8) !important; box-shadow: 0 0 15px rgba(6, 182, 212, 0.4), inset 0 0 10px rgba(6, 182, 212, 0.1) !important; background: rgba(6, 182, 212, 0.05) !important; transform: scale(1.02); }
	.team-card-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.5rem; padding-bottom: 0.4rem; border-bottom: 1px solid var(--glass-border); }
	.team-name { font-weight: 800; font-size: 0.85rem; color: var(--accent); }
	.team-delete { background: none; border: none; color: var(--danger); cursor: pointer; font-size: 0.75rem; opacity: 0.5; }
	.team-delete:hover { opacity: 1; }
	.btn-join { background: rgba(16,185,129,0.15); border: 1px solid rgba(16,185,129,0.3); color: #10b981; border-radius: 6px; padding: 0.15rem 0.5rem; font-size: 0.6rem; font-weight: 700; cursor: pointer; transition: all 0.15s; }
	.btn-join:hover { background: rgba(16,185,129,0.3); }
	.team-members { display: flex; flex-direction: column; gap: 0.3rem; margin-bottom: 0.5rem; }
	.team-member { display: flex; justify-content: space-between; align-items: center; font-size: 0.75rem; padding: 0.25rem 0.4rem; background: rgba(59,130,246,0.08); border-radius: 6px; }
	.member-remove { background: none; border: none; color: var(--danger); cursor: pointer; font-size: 0.65rem; opacity: 0.4; }
	.member-remove:hover { opacity: 1; }
	.member-pts { font-size: 0.65rem; font-weight: 800; color: #fbbf24; background: rgba(251,191,36,0.1); padding: 0.1rem 0.4rem; border-radius: 4px; white-space: nowrap; }
	.team-add-select { width: 100%; padding: 0.35rem; border-radius: 6px; border: 1px solid var(--glass-border); background: var(--input-bg); color: var(--input-color); font-size: 0.7rem; appearance: none; -webkit-appearance: none; background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='10' height='6'%3E%3Cpath d='M0 0l5 6 5-6z' fill='%23888'/%3E%3C/svg%3E"); background-repeat: no-repeat; background-position: right 0.5rem center; padding-right: 1.5rem; cursor: pointer; }
	.team-add-select option { background: var(--bg-secondary); color: var(--text-main); padding: 0.4rem; }
	.unassigned-hint { margin-top: 0.75rem; padding: 0.5rem 0.75rem; background: rgba(245,158,11,0.1); border: 1px solid rgba(245,158,11,0.2); border-radius: 8px; color: #f59e0b; font-size: 0.75rem; font-weight: 600; }
</style>
