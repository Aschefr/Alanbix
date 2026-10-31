<script>
	import { get } from 'svelte/store';
	import { onMount, onDestroy } from 'svelte';
	import { api } from '$lib/api';
	import { t } from '$lib/i18nStore';
	import { formatPoints } from '$lib/utils';
	import { wsMessageStore } from '$lib/ws';
	import Icon from '$lib/components/Icon.svelte';

	export let toast = (msg, type) => {};
	export let initialQuery = '';

	let allPlayers = [];
	$: existingTeams = Array.from(new Set(allPlayers.map(p => p.team_name?.trim()).filter(Boolean))).sort();

	let editingPlayer = null;
	let editPlayerData = {};
	let resetPwdPlayer = null;
	let resetPwdValue = 'lan2025';
	let overlayMouseDown = false;

	let deleteConfirmPlayerId = null;
	let promoteConfirmPlayerId = null;
	let demoteConfirmPlayerId = null;
	let deleteAvatarConfirm = false;

	let showCreatePlayer = false;
	let newPlayerData = { username: '', password: 'lan2025', team_name: '' };
	let creatingPlayer = false;
	let generatingPool = false;
	let playerQuery = initialQuery;
	let openActionsId = null;
	$: filteredPlayers = playerQuery.trim()
		? allPlayers.filter(p => `${p.username} ${p.team_name || ''}`.toLowerCase().includes(playerQuery.trim().toLowerCase()))
		: allPlayers;

	function openEditPlayer(p) {
		editingPlayer = p;
		editPlayerData = { username: p.username, team_name: p.team_name || '', seat_id: p.seat_id || '', points: formatPoints(p.points || 0), is_admin: p.is_admin || false, ia_blocked: p.ia_blocked || false };
	}

	function handleKeydown(e) {
		if (e.key === 'Escape') {
			if (editingPlayer) editingPlayer = null;
			else if (resetPwdPlayer) resetPwdPlayer = null;
		}
	}

	let wsUnsub = null;
	onMount(() => {
		loadPlayers();
		wsUnsub = wsMessageStore.subscribe(msg => {
			if (!msg) return;
			if (msg.type === 'user_presence' && msg.user_id !== undefined) {
				const p = allPlayers.find(x => x.id === msg.user_id);
				if (p && p.is_online !== msg.is_online) {
					p.is_online = msg.is_online;
					allPlayers = allPlayers;
				}
			}
		});
	});

	onDestroy(() => {
		if (wsUnsub) wsUnsub();
	});

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

	export async function loadPlayers() {
		try {
			allPlayers = await api.get('/admin/users');
		} catch (e) {
			toast(get(t)('admin_toast_players_load_error'), 'error');
		}
	}

	async function savePlayer() {
		try {
			await api.put(`/admin/users/${editingPlayer.id}`, editPlayerData);
			toast(get(t)('admin_toast_player_updated', { name: editPlayerData.username }), 'success');
			editingPlayer = null;
			await loadPlayers();
		} catch (e) {
			toast(e.message, 'error');
		}
	}

	function adminDeleteAvatar(playerId) {
		deleteAvatarConfirm = false;
		api.delete(`/admin/users/${playerId}/avatar`).then(() => {
			toast(get(t)('admin_toast_avatar_deleted'), 'success');
			if (editingPlayer && editingPlayer.id === playerId) {
				editingPlayer.avatar_url = null;
				editingPlayer = { ...editingPlayer };
			}
			loadPlayers();
		}).catch((e) => toast("Erreur: " + e.message, "error"));
	}

	async function resetPassword() {
		try {
			await api.post(`/admin/users/${resetPwdPlayer.id}/reset-password`, { password: resetPwdValue });
			toast(get(t)('admin_toast_pwd_reset', { name: resetPwdPlayer.username, pwd: resetPwdValue }), 'success');
			resetPwdPlayer = null;
		} catch (e) {
			toast(e.message, 'error');
		}
	}

	async function deletePlayer(id) {
		try {
			await api.delete(`/admin/users/${id}`);
			toast(get(t)('admin_toast_player_deleted'), 'success');
			deleteConfirmPlayerId = null;
			await loadPlayers();
		} catch (e) {
			toast(e.message, 'error');
		}
	}

	async function createPlayer() {
		if (!newPlayerData.username.trim() || !newPlayerData.password.trim()) return;
		creatingPlayer = true;
		try {
			await api.post('/admin/users/create', newPlayerData);
			toast(get(t)('admin_toast_player_created', { name: newPlayerData.username }), 'success');
			newPlayerData = { username: '', password: 'lan2025', team_name: '' };
			showCreatePlayer = false;
			await loadPlayers();
		} catch (e) {
			toast(e.message, 'error');
		}
		creatingPlayer = false;
	}

	async function generateTestPool() {
		generatingPool = true;
		try {
			const res = await api.post('/admin/users/generate-test-pool');
			toast(get(t)('admin_toast_test_players_generated', { count: res.created_count }), 'success');
			await loadPlayers();
		} catch (e) {
			toast(e.message, 'error');
		}
		generatingPool = false;
	}

	async function toggleAdmin(player) {
		try {
			await api.put(`/admin/users/${player.id}`, { is_admin: !player.is_admin });
			toast(!player.is_admin ? get(t)('admin_toast_promoted', { name: player.username }) : get(t)('admin_toast_demoted', { name: player.username }), 'success');
			await loadPlayers();
		} catch (e) {
			toast(e.message, 'error');
		}
	}

	async function toggleIaBlocked(player) {
		try {
			const newVal = !player.ia_blocked;
			await api.put(`/admin/users/${player.id}`, { ia_blocked: newVal });
			toast(newVal ? get(t)('admin_toast_ai_blocked', { name: player.username }) : get(t)('admin_toast_ai_unblocked', { name: player.username }), 'success');
			await loadPlayers();
		} catch (e) {
			toast(e.message, 'error');
		}
	}

	async function toggleMutePlayer(p) {
		const isMuted = p.public_chat_muted_until && new Date(p.public_chat_muted_until) > new Date();
		const minutes = isMuted ? 0 : 30;
		try {
			await api.post(`/public-chat/mute/${p.id}`, { duration_minutes: minutes });
			toast(isMuted ? $t('admin_players_toast_unmuted', { name: p.username }) : $t('admin_players_toast_muted', { name: p.username }), 'success');
			await loadPlayers();
		} catch (e) {
			toast(e.message, 'error');
		}
	}
</script>

<svelte:window on:keydown={handleKeydown} />

<div class="players-view glass p-8">
	<datalist id="admin-existing-teams">
		{#each existingTeams as team}
			<option value={team}></option>
		{/each}
	</datalist>
	<div class="flex-row justify-between items-center mb-4 pt-toolbar">
		<h3><span class="head-ic"><Icon name="users" size={20} /></span> {$t('admin_players_title')} <span class="t-count">{allPlayers.length}</span></h3>
		<div class="flex-row gap-2 pt-tools">
			<div class="pt-search-wrap">
				<Icon name="search" size={15} />
				<input class="pt-search" type="search" bind:value={playerQuery} placeholder={$t('admin_players_search_placeholder')} aria-label={$t('admin_players_search_placeholder')} />
			</div>
			<button class="btn-primary btn-compact btn-ic" on:click={() => showCreatePlayer = !showCreatePlayer}>
				<Icon name={showCreatePlayer ? 'x' : 'plus'} size={15} />
				{showCreatePlayer ? $t('admin_players_btn_cancel_close') : $t('admin_players_btn_add')}
			</button>
		</div>
	</div>

	{#if showCreatePlayer}
		<div class="create-player-form glass-inner">
			<div class="cpf-grid">
				<div class="edit-field">
					<label>{$t("admin_players_modal_pseudo")}</label>
					<input type="text" bind:value={newPlayerData.username} placeholder="{$t('admin_players_pseudo_placeholder')}" />
				</div>
				<div class="edit-field">
					<label>{$t("admin_players_modal_password")}</label>
					<input type="text" bind:value={newPlayerData.password} placeholder="{$t('admin_players_pwd_placeholder')}" />
				</div>
				<div class="edit-field">
					<label>{$t("admin_players_modal_team")}</label>
					<input type="text" bind:value={newPlayerData.team_name} list="admin-existing-teams" placeholder="{$t('admin_players_team_placeholder')}" />
				</div>
				<div class="edit-field cpf-submit">
					<button class="btn-primary btn-ic" on:click={createPlayer} disabled={creatingPlayer || !newPlayerData.username.trim() || !newPlayerData.password.trim()}>
						<Icon name={creatingPlayer ? 'hourglass' : 'check'} size={16} /> {$t("admin_players_modal_btn_create")}
					</button>
				</div>
			</div>
		</div>
	{/if}

	{#if allPlayers.length === 0}
		<p class="text-dim text-xs">{$t("admin_players_none_registered")}</p>
	{:else}
		<div class="players-table">
			<div class="pt-header">
				<span class="pt-col pt-id">#</span>
				<span class="pt-col pt-name">{$t("admin_players_hdr_pseudo")}</span>
				<span class="pt-col pt-team">{$t("admin_players_hdr_team")}</span>
				<span class="pt-col pt-pts">{$t("dash_modal_points_total")}</span>
				<span class="pt-col pt-actions">{$t('admin_players_hdr_actions')}</span>
			</div>
			{#each filteredPlayers as p, i (p.id)}
				<div class="pt-row {p.is_admin ? 'is-admin' : ''}">
					<span class="pt-col pt-id">{i + 1}</span>
					<span class="pt-col pt-name" style="display: flex; align-items: center; gap: 0.4rem;">
						{#if p.avatar_url}
							<div class="admin-avatar-small avatar-shape-{p.avatar_shape || 'circle'}"><img src={p.avatar_url} alt="" /></div>
						{/if}
						<span>{p.username}</span>
						{#if p.is_online}
							<span class="online-dot" title={$t('players_status_online')}></span>
						{/if}
						{#if p.is_admin}<span class="admin-badge" title={$t('role_admin')}><Icon name="crown" size={13} /></span>{/if}
						{#if p.ia_blocked}<span class="ia-blocked-badge" title="{$t('admin_players_ia_blocked_tooltip')}"><Icon name="ban" size={14} /></span>{/if}
						{#if p.public_chat_muted_until && new Date(p.public_chat_muted_until) > new Date()}
							<span class="chat-muted-badge" title={$t('admin_players_muted_badge')}><Icon name="volume-x" size={14} /></span>
						{/if}
					</span>
					<span class="pt-col pt-team">{p.team_name || '—'}</span>
					<span class="pt-col pt-pts">{formatPoints(p.points || 0)}</span>
					<span class="pt-col pt-actions">
						{#if !p.is_admin}
							{#if promoteConfirmPlayerId === p.id}
								<button class="btn-primary-sm" on:click={() => { toggleAdmin(p); promoteConfirmPlayerId = null; }}>{$t("admin_players_promote_confirm")}</button>
								<button class="btn-icon" on:click={() => promoteConfirmPlayerId = null} aria-label={$t('common_close')}><Icon name="x" size={14} /></button>
							{:else if deleteConfirmPlayerId === p.id}
								<button class="btn-danger-sm" on:click={() => deletePlayer(p.id)}>{$t('admin_players_action_delete')} ?</button>
								<button class="btn-icon" on:click={() => deleteConfirmPlayerId = null} aria-label={$t('common_close')}><Icon name="x" size={14} /></button>
							{:else}
								<button class="btn-row" on:click={() => openEditPlayer(p)}>{$t('admin_players_tooltip_edit')}</button>
								<button class="btn-row btn-more" class:open={openActionsId === p.id} aria-expanded={openActionsId === p.id} title={$t('admin_players_actions_more')} aria-label={$t('admin_players_actions_more')} on:click={() => openActionsId = openActionsId === p.id ? null : p.id}><Icon name={openActionsId === p.id ? 'chevron-up' : 'chevron-down'} size={15} /></button>
							{/if}
						{:else}
							{#if demoteConfirmPlayerId === p.id}
								<button class="btn-warning-sm" on:click={() => { toggleAdmin(p); demoteConfirmPlayerId = null; }}>{$t("admin_players_demote_confirm")}</button>
								<button class="btn-icon" on:click={() => demoteConfirmPlayerId = null} aria-label={$t('common_close')}><Icon name="x" size={14} /></button>
							{:else}
								<button class="btn-row" on:click={() => { demoteConfirmPlayerId = p.id; promoteConfirmPlayerId = null; deleteConfirmPlayerId = null; }}>{$t('admin_players_tooltip_demote')}</button>
							{/if}
						{/if}
					</span>
				</div>
				{#if openActionsId === p.id && !p.is_admin}
					{@const muted = p.public_chat_muted_until && new Date(p.public_chat_muted_until) > new Date()}
					<div class="pt-actions-drawer">
						<button class="btn-row" on:click={() => { resetPwdPlayer = p; resetPwdValue = 'lan2025'; openActionsId = null; }}>{$t('admin_players_tooltip_resetpw')}</button>
						<button class="btn-row" class:warn={p.ia_blocked} on:click={() => toggleIaBlocked(p)}>{p.ia_blocked ? $t('admin_players_tooltip_unblockai') : $t('admin_players_tooltip_blockai')}</button>
						<button class="btn-row" class:warn={muted} on:click={() => toggleMutePlayer(p)}>{muted ? $t('admin_players_tooltip_unmute') : $t('admin_players_tooltip_mute')}</button>
						<button class="btn-row" on:click={() => { promoteConfirmPlayerId = p.id; deleteConfirmPlayerId = null; openActionsId = null; }}>{$t('admin_players_tooltip_promote')}</button>
						<span class="drawer-sep"></span>
						<button class="btn-row danger" on:click={() => { deleteConfirmPlayerId = p.id; promoteConfirmPlayerId = null; openActionsId = null; }}>{$t('admin_players_action_delete')}</button>
					</div>
				{/if}
			{:else}
				<p class="text-dim pt-empty">{$t('admin_players_no_match')}</p>
			{/each}
		</div>
	{/if}

	<details class="test-tools">
		<summary>{$t('admin_players_test_tools')}</summary>
		<p class="text-dim">{$t('admin_players_test_tools_hint')}</p>
		<button class="btn-dev btn-sm" on:click={generateTestPool} disabled={generatingPool}>
			{generatingPool ? $t('admin_players_generating') : $t('admin_players_btn_gen20')}
		</button>
	</details>
</div>

{#if editingPlayer}
	<!-- svelte-ignore a11y-no-noninteractive-element-interactions -->
	<!-- svelte-ignore a11y-click-events-have-key-events -->
	<div class="modal-overlay-global" use:portal role="dialog" aria-modal="true"
		on:mousedown={(e) => { if (e.target === e.currentTarget) overlayMouseDown = true; }}
		on:mouseup={(e) => { if (overlayMouseDown && e.target === e.currentTarget) editingPlayer = null; overlayMouseDown = false; }}>
		<div class="modal-card-global narrow glass" on:click|stopPropagation>
			<header class="edit-modal-header">
				<div class="mh-main">
					<span class="mh-ic"><Icon name="pencil" size={20} /></span>
					<div class="mh-text">
						<h3>{$t('admin_players_modal_edit_title_short')}</h3>
						<span class="mh-sub">{editingPlayer.username}</span>
					</div>
				</div>
				<button class="close-btn" on:click={() => editingPlayer = null} aria-label={$t('common_close')}><Icon name="x" size={18} /></button>
			</header>
			<div class="edit-modal-body">
				{#if editingPlayer.avatar_url}
					<div class="avatar-row">
						<div class="admin-avatar-lg avatar-shape-{editingPlayer.avatar_shape || 'circle'}">
							<img src={editingPlayer.avatar_url} alt="" />
						</div>
						{#if deleteAvatarConfirm}
							<button class="btn-danger-sm" type="button" on:click={() => adminDeleteAvatar(editingPlayer.id)}>{$t('admin_confirm_delete_avatar_btn')}</button>
							<button class="btn-icon" type="button" on:click={() => deleteAvatarConfirm = false} aria-label={$t('common_close')}><Icon name="x" size={14} /></button>
						{:else}
							<button class="btn-row" type="button" on:click={() => deleteAvatarConfirm = true}><Icon name="trash" size={14} /> {$t('admin_players_modal_delete_avatar')}</button>
						{/if}
					</div>
				{/if}
				<div class="edit-field">
					<label for="pl-name">{$t("admin_players_modal_pseudo")}</label>
					<input id="pl-name" type="text" bind:value={editPlayerData.username} />
				</div>
				<div class="edit-grid-2col">
					<div class="edit-field">
						<label for="pl-team">{$t('admin_players_modal_team_name')}</label>
						<input id="pl-team" type="text" bind:value={editPlayerData.team_name} list="admin-existing-teams" placeholder="{$t('admin_players_modal_no_team')}" />
					</div>
					<div class="edit-field">
						<label for="pl-seat">{$t('admin_players_modal_seat')}</label>
						<input id="pl-seat" type="text" bind:value={editPlayerData.seat_id} placeholder="{$t('admin_players_modal_no_seat')}" />
					</div>
				</div>
				<div class="edit-field">
					<label for="pl-pts">{$t('admin_players_modal_points')}</label>
					<input id="pl-pts" type="number" step="any" bind:value={editPlayerData.points} placeholder="0" />
				</div>
				<div class="edit-section toggles">
					<label class="player-toggle-row">
						<span class="player-toggle-label"><Icon name="crown" size={16} /> {$t('admin_players_modal_is_admin')}</span>
						<span class="switch"><input type="checkbox" bind:checked={editPlayerData.is_admin} /><span class="slider"></span></span>
					</label>
					<label class="player-toggle-row">
						<span class="player-toggle-label"><Icon name="ban" size={16} /> {$t('admin_players_modal_block_ai')}</span>
						<span class="switch"><input type="checkbox" bind:checked={editPlayerData.ia_blocked} /><span class="slider"></span></span>
					</label>
				</div>
			</div>
			<footer class="edit-modal-footer">
				<button class="btn-secondary" on:click={() => editingPlayer = null}>{$t('admin_settings_cancel')}</button>
				<button class="btn-primary btn-ic" on:click={savePlayer}><Icon name="save" size={16} /> {$t('admin_players_modal_btn_save')}</button>
			</footer>
		</div>
	</div>
{/if}

{#if resetPwdPlayer}
	<!-- svelte-ignore a11y-no-noninteractive-element-interactions -->
	<!-- svelte-ignore a11y-click-events-have-key-events -->
	<div class="modal-overlay-global" use:portal role="dialog" aria-modal="true"
		on:mousedown={(e) => { if (e.target === e.currentTarget) overlayMouseDown = true; }}
		on:mouseup={(e) => { if (overlayMouseDown && e.target === e.currentTarget) resetPwdPlayer = null; overlayMouseDown = false; }}>
		<div class="modal-card-global narrow glass" on:click|stopPropagation>
			<header class="edit-modal-header">
				<div class="mh-main">
					<span class="mh-ic"><Icon name="key" size={20} /></span>
					<div class="mh-text">
						<h3>{$t('admin_players_modal_reset_pwd_title_short')}</h3>
						<span class="mh-sub">{resetPwdPlayer.username}</span>
					</div>
				</div>
				<button class="close-btn" on:click={() => resetPwdPlayer = null} aria-label={$t('common_close')}><Icon name="x" size={18} /></button>
			</header>
			<div class="edit-modal-body">
				<div class="edit-field">
					<label for="pl-newpwd">{$t('admin_players_modal_new_pwd')}</label>
					<input id="pl-newpwd" type="text" bind:value={resetPwdValue} />
				</div>
			</div>
			<footer class="edit-modal-footer">
				<button class="btn-secondary" on:click={() => resetPwdPlayer = null}>{$t('admin_settings_cancel')}</button>
				<button class="btn-primary btn-ic" on:click={resetPassword}><Icon name="check" size={16} /> {$t('admin_players_modal_reset_btn')}</button>
			</footer>
		</div>
	</div>
{/if}

<style>
	.players-view { border-radius: var(--radius-lg); }
	.players-view h3 { font-size: var(--fs-section); font-weight: 700; display: flex; align-items: center; gap: 0.6rem; margin: 0; }
	.players-table { display: flex; flex-direction: column; gap: 0; border-radius: 10px; overflow: hidden; border: 1px solid var(--glass-border); }
	.pt-header { display: flex; padding: 0.6rem 0.8rem; background: var(--surface-sunken); font-weight: 700; font-size: 0.8125rem; text-transform: uppercase; letter-spacing: 0.04em; color: var(--text-dim); border-bottom: 1px solid var(--glass-border); }
	.pt-row { display: flex; padding: 0.55rem 0.8rem; align-items: center; border-bottom: 1px solid rgba(255,255,255,0.03); transition: background 0.15s; }
	.pt-row:hover { background: var(--hover-tint); }
	.pt-row:last-child { border-bottom: none; }
	.pt-row.is-admin { background: rgba(59,130,246,0.06); }
	.pt-col { font-size: 0.875rem; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
	.pt-id { width: 36px; flex-shrink: 0; color: var(--text-muted); font-size: 0.8rem; }
	.pt-name { flex: 3; min-width: 0; font-weight: 700; display: flex; align-items: center; gap: 0.4rem; }
	.pt-team { flex: 2; min-width: 0; color: var(--text-dim); }
	.pt-pts { width: 120px; flex-shrink: 0; text-align: center; font-weight: 800; color: var(--accent); }
	.pt-actions { width: 240px; flex-shrink: 0; display: flex; gap: 0.3rem; align-items: center; justify-content: flex-end; flex-wrap: nowrap; }
	.admin-badge { display: inline-flex; align-items: center; padding: 0.15rem 0.35rem; background: rgba(234,179,8,0.15); color: #eab308; border-radius: 6px; }
	.pt-search { width: 260px; padding: 0.45rem 0.7rem; font-size: 0.875rem; border-radius: var(--radius-md); }
	.btn-row { display: inline-flex; align-items: center; gap: 0.35rem; background: var(--hover-tint); border: 1px solid var(--glass-border); color: var(--text-main); border-radius: var(--radius-md); padding: 0.35rem 0.8rem; font-size: 0.8125rem; font-weight: 600; cursor: pointer; white-space: nowrap; }
	.btn-row:hover, .btn-row.open { border-color: var(--accent); color: var(--accent); }
	.btn-row.warn { color: var(--warning); border-color: var(--warning); }
	.btn-row.danger { color: var(--danger); border-color: rgba(239,68,68,0.4); }
	.btn-row.danger:hover { background: rgba(239,68,68,0.12); border-color: var(--danger); }
	.btn-more { display: inline-flex; align-items: center; padding: 0.3rem 0.5rem; }
	.pt-actions-drawer { display: flex; flex-wrap: wrap; align-items: center; gap: 0.4rem; justify-content: flex-end; padding: 0.5rem 0.8rem 0.7rem; background: var(--surface-sunken); border-bottom: 1px solid var(--glass-border); }
	.drawer-sep { width: 1px; align-self: stretch; background: var(--glass-border); margin: 0 0.2rem; }
	.pt-empty { padding: 1rem; margin: 0; font-size: 0.9rem; }
	.test-tools { margin-top: 1.5rem; font-size: 0.85rem; color: var(--text-dim); }
	.test-tools summary { cursor: pointer; font-weight: 600; }
	.test-tools p { margin: 0.5rem 0; }
	.btn-icon { background: var(--hover-tint); border: 1px solid var(--glass-border); border-radius: 6px; padding: 0.25rem 0.4rem; cursor: pointer; font-size: 0.75rem; transition: all 0.15s; flex-shrink: 0; }
	.btn-icon:hover { background: var(--accent-soft); border-color: var(--accent); }
	.btn-icon-danger:hover { border-color: var(--danger, #ef4444); background: rgba(239,68,68,0.15); }
	.btn-danger-sm { background: rgba(239,68,68,0.2); color: #ef4444; border: 1px solid rgba(239,68,68,0.3); border-radius: 6px; padding: 0.2rem 0.5rem; font-size: 0.75rem; font-weight: 700; cursor: pointer; white-space: nowrap; }
	.btn-danger-sm:hover { background: rgba(239,68,68,0.35); }
	.btn-primary-sm { background: rgba(59,130,246,0.2); color: #3b82f6; border: 1px solid rgba(59,130,246,0.3); border-radius: 6px; padding: 0.2rem 0.5rem; font-size: 0.75rem; font-weight: 700; cursor: pointer; white-space: nowrap; }
	.btn-primary-sm:hover { background: rgba(59,130,246,0.35); }
	.btn-warning-sm { background: rgba(245,158,11,0.2); color: #f59e0b; border: 1px solid rgba(245,158,11,0.3); border-radius: 6px; padding: 0.2rem 0.5rem; font-size: 0.75rem; font-weight: 700; cursor: pointer; white-space: nowrap; }
	.btn-warning-sm:hover { background: rgba(245,158,11,0.35); }
	.mb-3 { margin-bottom: 0.75rem; }
	.mb-4 { margin-bottom: 1rem; }
	.t-count { font-size: 0.75rem; background: var(--accent-soft); color: var(--accent); padding: 0.1rem 0.4rem; border-radius: 10px; font-weight: 800; border: 1px solid rgba(59,130,246,0.15); }
	.p-8 { padding: 1.5rem; }
	.gap-2 { gap: 0.5rem; }
	.btn-sm { font-size: 0.7rem; padding: 0.35rem 0.7rem; border-radius: 8px; font-weight: 700; white-space: nowrap; }
	.btn-dev { background: rgba(168,85,247,0.15); color: #a855f7; border: 1px solid rgba(168,85,247,0.3); cursor: pointer; transition: all 0.15s; }
	.btn-dev:hover { background: rgba(168,85,247,0.3); border-color: #a855f7; }
	.btn-dev:disabled { opacity: 0.5; cursor: not-allowed; }
	.create-player-form { padding: 1rem; margin-bottom: 1rem; border-radius: 10px; border: 1px solid var(--glass-border); animation: slideDown 0.2s ease; }
	.cpf-grid { display: grid; grid-template-columns: 1fr 1fr 1fr auto; gap: 0.75rem; align-items: end; }
	.cpf-submit { display: flex; align-items: flex-end; }
	.cpf-submit button { height: 38px; }
	@keyframes slideDown { from { opacity: 0; transform: translateY(-8px); } to { opacity: 1; transform: translateY(0); } }
	.admin-avatar-small { width: 24px; height: 24px; border-radius: 50%; overflow: hidden; flex-shrink: 0; border: 1px solid var(--glass-border); }
	.admin-avatar-small img { width: 100%; height: 100%; object-fit: cover; border-radius: 50%; }
	.admin-avatar-lg { width: 50px; height: 50px; border-radius: 50%; overflow: hidden; flex-shrink: 0; border: 1px solid var(--accent-soft); }
	.admin-avatar-lg img { width: 100%; height: 100%; object-fit: cover; border-radius: 50%; }
	.ia-blocked-badge { display: inline-flex; color: var(--warning); margin-left: 0.3rem; }
	.chat-muted-badge { display: inline-flex; color: var(--text-dim); margin-left: 0.2rem; }

	/* Player modal toggles: same switch as the Settings page */
	.edit-section.toggles { gap: 0; padding: 0.25rem 1.1rem; }
	.player-toggle-row { display: flex; align-items: center; justify-content: space-between; gap: 1rem; padding: 0.7rem 0; cursor: pointer; }
	.player-toggle-row + .player-toggle-row { border-top: 1px solid var(--glass-border); }
	.player-toggle-label { display: inline-flex; align-items: center; gap: 0.5rem; font-size: 0.9375rem; font-weight: 600; color: var(--text-main); font-family: var(--font-main); }
	.switch { position: relative; display: inline-block; width: 44px; height: 24px; min-width: 44px; flex-shrink: 0; }
	.switch input { position: absolute; opacity: 0; width: 100%; height: 100%; margin: 0; cursor: pointer; z-index: 1; }
	.slider { position: absolute; inset: 0; background-color: var(--text-muted); opacity: 0.45; transition: background-color 0.2s, opacity 0.2s; border-radius: 12px; pointer-events: none; }
	.slider:before { position: absolute; content: ""; height: 18px; width: 18px; left: 3px; top: 3px; background-color: #fff; transition: transform 0.2s; border-radius: 50%; box-shadow: 0 1px 3px rgba(0, 0, 0, 0.25); }
	input:checked + .slider { background-color: var(--accent-solid); opacity: 1; }
	input:checked + .slider:before { transform: translateX(20px); }
	input:focus-visible + .slider { outline: 2px solid var(--accent); outline-offset: 2px; }
	.avatar-row { display: flex; align-items: center; gap: 1rem; }
	.head-ic { display: inline-flex; align-items: center; justify-content: center; width: 36px; height: 36px; border-radius: 10px; background: var(--accent-soft); color: var(--accent); }
	.online-dot { width: 8px; height: 8px; border-radius: 50%; background: var(--success); box-shadow: 0 0 6px color-mix(in srgb, var(--success) 60%, transparent); flex-shrink: 0; }
	.pt-search-wrap { position: relative; display: flex; align-items: center; color: var(--text-muted); }
	.pt-search-wrap :global(svg) { position: absolute; left: 0.65rem; pointer-events: none; }
	.pt-search-wrap .pt-search { padding-left: 2rem; }
	.btn-compact { padding: 0.4rem 0.8rem; font-size: 0.8125rem; }
	@media (max-width: 900px) {
		.players-view { padding: 1rem !important; }
		.players-view > .flex-row { flex-wrap: wrap; gap: 0.6rem; }
		.pt-tools { width: 100%; flex-wrap: wrap; }
		.pt-tools > * { flex: 1 1 100%; }
		.pt-search-wrap, .pt-search { width: 100%; }
		.pt-id, .pt-team, .pt-pts { display: none; }
		.pt-actions { width: auto; }
		.cpf-grid { grid-template-columns: 1fr; }
	}
</style>
