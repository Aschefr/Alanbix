<script>
	import { t } from '$lib/i18nStore';
	import { createEventDispatcher } from 'svelte';

	export let selected;
	export let participants = [];
	export let poolPlayers = [];
	export let groupedPoolPlayers = [];
	export let unregisteredUsers = [];
	export let useTeams = false;
	export let isAdmin = false;

	const dispatch = createEventDispatcher();

	let confirmJoinAll = false;
	let confirmLeaveAll = false;

	function handleJoinAll() {
		confirmJoinAll = false;
		dispatch('joinAll');
	}

	function handleLeaveAll() {
		confirmLeaveAll = false;
		dispatch('leaveAll');
	}

	function handleRemovePlayer(userId) {
		dispatch('removePlayer', { userId });
	}

	function handleAddPlayer(userId) {
		dispatch('addPlayer', { userId });
	}
</script>

{#if !useTeams || selected?.status === 'OPEN' || isAdmin}
	<div class="participants-section glass">
		<div class="section-title">
			<h3>👥 {useTeams ? $t('tourneys_tab_registered') : $t('dash_modal_tournaments_title')} <span class="part-count">{participants.length} {$t('changelog_fallback_name').toLowerCase()}{#if useTeams && participants.length > 0}, {poolPlayers.length} {$t('tourneys_unassigned_players', { count: poolPlayers.length, plural: poolPlayers.length > 1 ? 's' : '' })}{/if}</span></h3>
			{#if isAdmin && selected?.status === 'OPEN'}
				<div class="part-bulk-actions">
					{#if confirmJoinAll}
						<span class="inline-confirm">
							<span class="inline-confirm-label">{$t("tourneys_confirm_join_all")}</span>
							<button class="admin-btn confirm-yes" on:click={handleJoinAll}>✓</button>
							<button class="admin-btn confirm-no" on:click={() => confirmJoinAll = false}>✕</button>
						</span>
					{:else}
						<button class="admin-btn start btn-xs" on:click={() => confirmJoinAll = true} disabled={unregisteredUsers.length === 0}>📥 {$t("tourneys_btn_join_all")}</button>
					{/if}
					{#if confirmLeaveAll}
						<span class="inline-confirm">
							<span class="inline-confirm-label">{$t("tourneys_confirm_leave_all")}</span>
							<button class="admin-btn confirm-yes" on:click={handleLeaveAll}>✓</button>
							<button class="admin-btn confirm-no" on:click={() => confirmLeaveAll = false}>✕</button>
						</span>
					{:else}
						<button class="admin-btn stop btn-xs" on:click={() => confirmLeaveAll = true} disabled={participants.length === 0}>📤 {$t("tourneys_btn_leave_all")}</button>
					{/if}
				</div>
			{/if}
		</div>
		{#if poolPlayers.length === 0}
			<span class="text-dim text-sm">{useTeams && participants.length > 0 ? $t('tourneys_all_placed') : $t('tourneys_no_registered')}</span>
		{:else}
			<div class="part-cards-grid">
				{#each groupedPoolPlayers as [teamName, members]}
					<div class="part-card glass">
						<div class="part-card-header">
							<span class="part-card-name">{teamName || $t('dash_modal_team_fallback')}</span>
							<span class="part-card-count">{members.length}</span>
						</div>
						<div class="part-card-members">
							{#each members as p}
								<div class="part-member-row pool-badge" draggable={isAdmin && selected?.status === 'OPEN' && useTeams} on:dragstart={(e) => { e.dataTransfer.setData('userId', p.user_id); e.target.classList.add('dragging'); }} on:dragend={(e) => e.target.classList.remove('dragging')}>
									<span>👤 {p.username}</span>
									{#if isAdmin && selected?.status === 'OPEN'}
										<button class="part-member-remove" on:click={() => handleRemovePlayer(p.user_id)} title={$t('tourneys_unregister_player', { name: p.username })}>✕</button>
									{/if}
								</div>
							{/each}
						</div>
					</div>
				{/each}
			</div>
		{/if}
	</div>
{/if}

<!-- Admin: unregistered users to register -->
{#if isAdmin && selected?.status === 'OPEN' && unregisteredUsers.length > 0}
	<div class="unreg-section glass">
		<div class="section-title">
			<h3>➕ {$t('tourneys_available_players')}</h3>
			<span class="unreg-hint">{$t('tourneys_click_to_register')}</span>
		</div>
		<div class="unreg-badges">
			{#each unregisteredUsers as u}
				<button class="unreg-badge" on:click={() => handleAddPlayer(u.id)} title={$t('tourneys_detail_unregistered_add_title', { name: u.username })}>
					<span>👤</span>
					<span class="unreg-name">{u.username}</span>
					{#if u.team_name}<span class="unreg-team">• {u.team_name}</span>{/if}
					<span class="unreg-plus">+</span>
				</button>
			{/each}
		</div>
	</div>
{/if}

<style>
	.participants-section { padding: 1rem; border-radius: 14px; }
	.section-title { display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.75rem; }
	.section-title h3 { font-size: 0.8rem; font-weight: 700; text-transform: uppercase; letter-spacing: 0.04em; color: var(--text-dim); margin: 0; }
	.btn-xs { padding: 0.3rem 0.6rem; font-size: 0.7rem; }
	.part-count { font-size: 0.6rem; background: var(--accent-soft); color: var(--accent); padding: 0.1rem 0.4rem; border-radius: 10px; font-weight: 800; border: 1px solid rgba(59,130,246,0.15); margin-left: 0.3rem; }
	.part-bulk-actions { display: flex; gap: 0.4rem; align-items: center; }
	.part-cards-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(200px, 1fr)); gap: 0.75rem; }
	.part-card { padding: 0.75rem; border-radius: 10px; }
	.part-card-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.5rem; padding-bottom: 0.4rem; border-bottom: 1px solid var(--glass-border); }
	.part-card-name { font-weight: 800; font-size: 0.85rem; color: var(--accent); }
	.part-card-count { font-size: 0.6rem; background: rgba(255,255,255,0.06); padding: 0.1rem 0.4rem; border-radius: 8px; color: var(--text-muted); font-weight: 700; }
	.part-card-members { display: flex; flex-direction: column; gap: 0.3rem; }
	.part-member-row { display: flex; justify-content: space-between; align-items: center; font-size: 0.75rem; padding: 0.25rem 0.4rem; background: rgba(59,130,246,0.08); border-radius: 6px; font-weight: 600; color: var(--text-main); }
	.part-member-remove { background: none; border: none; color: var(--text-muted); cursor: pointer; font-size: 0.65rem; opacity: 0.4; transition: all 0.15s; }
	.part-member-remove:hover { opacity: 1; color: var(--danger, #ef4444); }

	.pool-badge[draggable="true"] { cursor: grab; transition: opacity 0.2s, transform 0.2s; }
	.pool-badge[draggable="true"]:active { cursor: grabbing; }
	:global(.pool-badge.dragging) { opacity: 0.4; transform: scale(0.95); }

	.admin-btn { padding: 0.4rem 0.8rem; font-size: 0.72rem; font-weight: 700; border-radius: 8px; border: 1px solid var(--glass-border); cursor: pointer; transition: all 0.2s; background: var(--surface-raised); color: var(--text-dim); }
	.admin-btn:hover { transform: translateY(-1px); }
	.admin-btn:disabled { opacity: 0.4; cursor: not-allowed; transform: none; }
	.admin-btn.start { border-color: rgba(34,197,94,0.3); color: var(--success); }
	.admin-btn.start:hover:not(:disabled) { background: rgba(34,197,94,0.15); }
	.admin-btn.stop { border-color: rgba(239,68,68,0.3); color: var(--danger); }
	.admin-btn.stop:hover { background: rgba(239,68,68,0.15); }
	.inline-confirm { display: inline-flex; align-items: center; gap: 0.4rem; animation: fadeIn 0.15s ease-out; }
	.inline-confirm-label { font-size: 0.65rem; font-weight: 700; color: var(--text-main); white-space: nowrap; }
	.admin-btn.confirm-yes { border-color: rgba(34,197,94,0.4); color: var(--success); font-weight: 800; }
	.admin-btn.confirm-yes:hover { background: rgba(34,197,94,0.2); }
	.admin-btn.confirm-no { border-color: rgba(239,68,68,0.3); color: var(--danger); padding: 0.2rem 0.5rem; min-width: unset; }
	.admin-btn.confirm-no:hover { background: rgba(239,68,68,0.15); }
	@keyframes fadeIn { from { opacity: 0; transform: translateX(-5px); } to { opacity: 1; transform: translateX(0); } }

	/* Unreg Section */
	.unreg-section { padding: 1rem; border-radius: 14px; }
	.unreg-hint { font-size: 0.6rem; color: var(--text-muted); font-style: italic; }
	.unreg-badges { display: flex; flex-wrap: wrap; gap: 0.35rem; }
	.unreg-badge { display: flex; align-items: center; gap: 0.3rem; padding: 0.3rem 0.6rem; border-radius: 20px; font-size: 0.72rem; font-weight: 600; background: var(--surface-raised); border: 1px solid var(--glass-border); color: var(--text-dim); cursor: pointer; transition: all 0.2s; }
	.unreg-badge:hover { background: var(--map-user-option-hover); border-color: var(--accent); color: var(--accent); }
	.unreg-name { color: inherit; }
	.unreg-team { color: var(--text-muted); font-size: 0.6rem; }
	.unreg-badge:hover .unreg-team { color: var(--text-dim); }
	.unreg-plus { color: var(--accent); font-weight: 800; font-size: 0.8rem; opacity: 0; transition: opacity 0.15s; }
	.unreg-badge:hover .unreg-plus { opacity: 1; }
</style>
