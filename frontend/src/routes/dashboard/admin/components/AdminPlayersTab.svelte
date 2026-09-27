<script>
	import { get } from 'svelte/store';
	import { onMount } from 'svelte';
	import { api } from '$lib/api';
	import { t } from '$lib/i18nStore';

	export let toast = (msg, type) => {};

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

	let showCreatePlayer = false;
	let newPlayerData = { username: '', password: 'lan2025', team_name: '' };
	let creatingPlayer = false;
	let generatingPool = false;

	function handleKeydown(e) {
		if (e.key === 'Escape') {
			if (editingPlayer) editingPlayer = null;
			else if (resetPwdPlayer) resetPwdPlayer = null;
		}
	}

	onMount(() => {
		loadPlayers();
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
		if (!confirm(get(t)('admin_confirm_delete_avatar') || 'Voulez-vous vraiment supprimer cet avatar ?')) return;
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
			toast(isMuted ? `${p.username} est démuté du chat public` : `${p.username} est muté pour 30 minutes`, 'success');
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
	<div class="flex-row justify-between items-center mb-4">
		<h3>{$t('admin_players_title')} <span class="t-count">{allPlayers.length}</span></h3>
		<div class="flex-row gap-2">
			<button class="btn-secondary btn-sm" on:click={() => showCreatePlayer = !showCreatePlayer}>
				{showCreatePlayer ? $t('admin_players_btn_cancel_close') : $t('admin_players_btn_add')}
			</button>
			<button class="btn-dev btn-sm" on:click={generateTestPool} disabled={generatingPool}>
				{generatingPool ? $t('admin_players_generating') : $t('admin_players_btn_gen20')}
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
					<button class="btn-primary" on:click={createPlayer} disabled={creatingPlayer || !newPlayerData.username.trim() || !newPlayerData.password.trim()}>
						{creatingPlayer ? '⏳' : '✅'} {$t("admin_players_modal_btn_create")}
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
				<span class="pt-col pt-actions">Actions</span>
			</div>
			{#each allPlayers as p, i}
				<div class="pt-row {p.is_admin ? 'is-admin' : ''}">
					<span class="pt-col pt-id">{i + 1}</span>
					<span class="pt-col pt-name" style="display: flex; align-items: center; gap: 0.4rem;">
						{#if p.avatar_url}
							<div class="admin-avatar-small avatar-shape-{p.avatar_shape || 'circle'}"><img src={p.avatar_url} alt="" /></div>
						{/if}
						<span>{p.username}</span>
						{#if p.is_online}
							<span style="color:#10b981; font-size:0.8rem; text-shadow: 0 0 6px rgba(16,185,129,0.6);" title={$t('players_status_online')}>●</span>
						{/if}
						{#if p.is_admin}<span class="admin-badge">👑</span>{/if}
						{#if p.ia_blocked}<span class="ia-blocked-badge" title="{$t('admin_players_ia_blocked_tooltip')}">🚫</span>{/if}
						{#if p.public_chat_muted_until && new Date(p.public_chat_muted_until) > new Date()}
							<span class="chat-muted-badge" title="Mute chat public">🔇</span>
						{/if}
					</span>
					<span class="pt-col pt-team">{p.team_name || '—'}</span>
					<span class="pt-col pt-pts">{p.points || 0}</span>
					<span class="pt-col pt-actions">
						{#if !p.is_admin}
							<button class="btn-icon" title="{$t('admin_players_tooltip_edit')}" on:click={() => { editingPlayer = p; editPlayerData = { username: p.username, team_name: p.team_name || '', seat_id: p.seat_id || '', points: p.points || 0, is_admin: p.is_admin || false, ia_blocked: p.ia_blocked || false }; }}>✏️</button>
							<button class="btn-icon" title="{$t('admin_players_tooltip_resetpw')}" on:click={() => { resetPwdPlayer = p; resetPwdValue = 'lan2025'; }}>🔑</button>
							<button class="btn-icon {p.ia_blocked ? 'btn-icon-danger' : ''}" title="{p.ia_blocked ? $t('admin_players_tooltip_unblockai') : $t('admin_players_tooltip_blockai')}" on:click={() => toggleIaBlocked(p)}>
								{p.ia_blocked ? '🔓' : '🚫'}
							</button>
							<button class="btn-icon {p.public_chat_muted_until && new Date(p.public_chat_muted_until) > new Date() ? 'btn-icon-danger' : ''}" title="{p.public_chat_muted_until && new Date(p.public_chat_muted_until) > new Date() ? ($t('admin_players_tooltip_unmute') || 'Démuter') : ($t('admin_players_tooltip_mute') || 'Muter 30m')}" on:click={() => toggleMutePlayer(p)}>
								{p.public_chat_muted_until && new Date(p.public_chat_muted_until) > new Date() ? '🔇' : '🎙️'}
							</button>
							{#if promoteConfirmPlayerId === p.id}
								<button class="btn-primary-sm" on:click={() => { toggleAdmin(p); promoteConfirmPlayerId = null; }}>{$t("admin_players_promote_confirm")}</button>
								<button class="btn-icon" on:click={() => promoteConfirmPlayerId = null}>❌</button>
							{:else}
								<button class="btn-icon btn-icon-promote" title="{$t('admin_players_tooltip_promote')}" on:click={() => { promoteConfirmPlayerId = p.id; deleteConfirmPlayerId = null; demoteConfirmPlayerId = null; }}>👑</button>
							{/if}
							{#if deleteConfirmPlayerId === p.id}
								<button class="btn-danger-sm" on:click={() => deletePlayer(p.id)}>{$t("admin_players_delete_confirm")}</button>
								<button class="btn-icon" on:click={() => deleteConfirmPlayerId = null}>❌</button>
							{:else}
								<button class="btn-icon btn-icon-danger" title="{$t('admin_tourneys_tooltip_delete')}" on:click={() => { deleteConfirmPlayerId = p.id; promoteConfirmPlayerId = null; demoteConfirmPlayerId = null; }}>🗑️</button>
							{/if}
						{:else}
							{#if demoteConfirmPlayerId === p.id}
								<button class="btn-warning-sm" on:click={() => { toggleAdmin(p); demoteConfirmPlayerId = null; }}>{$t("admin_players_demote_confirm")}</button>
								<button class="btn-icon" on:click={() => demoteConfirmPlayerId = null}>❌</button>
							{:else}
								<button class="btn-icon btn-icon-demote" title="{$t('admin_players_tooltip_demote')}" on:click={() => { demoteConfirmPlayerId = p.id; promoteConfirmPlayerId = null; deleteConfirmPlayerId = null; }}>🛡️</button>
							{/if}
						{/if}
					</span>
				</div>
			{/each}
		</div>
	{/if}
</div>

{#if editingPlayer}
	<!-- svelte-ignore a11y-no-noninteractive-element-interactions -->
	<!-- svelte-ignore a11y-click-events-have-key-events -->
	<div class="modal-overlay-global" use:portal role="dialog" aria-modal="true"
		on:mousedown={(e) => { if (e.target === e.currentTarget) overlayMouseDown = true; }} 
		on:mouseup={(e) => { if (overlayMouseDown && e.target === e.currentTarget) editingPlayer = null; overlayMouseDown = false; }}>
		<div class="modal-card-global glass" on:click|stopPropagation style="max-width: 400px">
			<header class="edit-modal-header">
				<h3>✏️ Modifier — {editingPlayer.username}</h3>
				<button class="close-btn" on:click={() => editingPlayer = null} aria-label="Fermer">✕</button>
			</header>
			<div class="edit-modal-body">
				{#if editingPlayer.avatar_url}
					<div class="edit-field mb-3" style="display: flex; align-items: center; gap: 1rem;">
						<div class="admin-avatar-lg avatar-shape-{editingPlayer.avatar_shape || 'circle'}">
							<img src={editingPlayer.avatar_url} alt="" />
						</div>
						<button class="btn-danger-sm" type="button" on:click={() => adminDeleteAvatar(editingPlayer.id)}>Supprimer l'avatar</button>
					</div>
				{/if}
				<div class="edit-field mb-3">
					<label>{$t("admin_players_modal_pseudo")}</label>
					<input type="text" bind:value={editPlayerData.username} />
				</div>
				<div class="edit-field mb-3">
					<label>Nom d'équipe</label>
					<input type="text" bind:value={editPlayerData.team_name} list="admin-existing-teams" placeholder="Aucune équipe" />
				</div>
				<div class="edit-field mb-3">
					<label>Place assignée (Poste ID)</label>
					<input type="text" bind:value={editPlayerData.seat_id} placeholder="Aucun poste (ex: A01)" />
				</div>
				<div class="edit-field mb-3">
					<label>Points cumulés</label>
					<input type="number" bind:value={editPlayerData.points} placeholder="0" />
				</div>
				<div class="edit-field mb-3" style="display: flex; align-items: center; gap: 0.5rem;">
					<input type="checkbox" id="edit-is-admin" bind:checked={editPlayerData.is_admin} style="width: auto;" />
					<label for="edit-is-admin" style="margin: 0; cursor: pointer;">Est Administrateur 👑</label>
				</div>
				<div class="edit-field mb-3" style="display: flex; align-items: center; gap: 0.5rem;">
					<input type="checkbox" id="edit-ia-blocked" bind:checked={editPlayerData.ia_blocked} style="width: auto;" />
					<label for="edit-ia-blocked" style="margin: 0; cursor: pointer;">Bloquer l'accès IA 🚫</label>
				</div>
			</div>
			<footer class="edit-modal-footer">
				<button class="btn-secondary" on:click={() => editingPlayer = null}>{$t('admin_settings_cancel')}</button>
				<button class="btn-primary" on:click={savePlayer}>💾 {$t('admin_players_modal_btn_save')}</button>
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
		<div class="modal-card-global glass" on:click|stopPropagation style="max-width: 400px">
			<header class="edit-modal-header">
				<h3>🔑 Réinitialiser MDP — {resetPwdPlayer.username}</h3>
				<button class="close-btn" on:click={() => resetPwdPlayer = null} aria-label="Fermer">✕</button>
			</header>
			<div class="edit-modal-body">
				<div class="edit-field">
					<label>Nouveau mot de passe</label>
					<input type="text" bind:value={resetPwdValue} />
				</div>
			</div>
			<footer class="edit-modal-footer">
				<button class="btn-secondary" on:click={() => resetPwdPlayer = null}>{$t('admin_settings_cancel')}</button>
				<button class="btn-primary" on:click={resetPassword}>✅ Réinitialiser</button>
			</footer>
		</div>
	</div>
{/if}

<style>
	.players-view { border-radius: var(--radius-lg); }
	.players-view h3 { font-size: 1rem; font-weight: 800; display: flex; align-items: center; gap: 0.5rem; margin: 0; }
	.players-table { display: flex; flex-direction: column; gap: 0; border-radius: 10px; overflow: hidden; border: 1px solid var(--glass-border); }
	.pt-header { display: flex; padding: 0.6rem 0.8rem; background: var(--surface-sunken); font-weight: 800; font-size: 0.65rem; text-transform: uppercase; letter-spacing: 0.05em; color: var(--text-muted); border-bottom: 1px solid var(--glass-border); }
	.pt-row { display: flex; padding: 0.55rem 0.8rem; align-items: center; border-bottom: 1px solid rgba(255,255,255,0.03); transition: background 0.15s; }
	.pt-row:hover { background: var(--hover-tint); }
	.pt-row:last-child { border-bottom: none; }
	.pt-row.is-admin { background: rgba(59,130,246,0.06); }
	.pt-col { font-size: 0.8rem; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
	.pt-id { width: 36px; flex-shrink: 0; color: var(--text-muted); font-size: 0.7rem; }
	.pt-name { flex: 3; min-width: 0; font-weight: 700; display: flex; align-items: center; gap: 0.4rem; }
	.pt-team { flex: 2; min-width: 0; color: var(--text-dim); }
	.pt-pts { width: 70px; flex-shrink: 0; text-align: center; font-weight: 800; color: var(--accent); }
	.pt-actions { width: 220px; flex-shrink: 0; display: flex; gap: 0.3rem; align-items: center; justify-content: flex-end; flex-wrap: nowrap; }
	.admin-badge { font-size: 0.6rem; padding: 0.1rem 0.3rem; background: rgba(234,179,8,0.15); color: #eab308; border-radius: 6px; font-weight: 800; }
	.btn-icon { background: var(--hover-tint); border: 1px solid var(--glass-border); border-radius: 6px; padding: 0.25rem 0.4rem; cursor: pointer; font-size: 0.75rem; transition: all 0.15s; flex-shrink: 0; }
	.btn-icon:hover { background: var(--accent-soft); border-color: var(--accent); }
	.btn-icon-danger:hover { border-color: var(--danger, #ef4444); background: rgba(239,68,68,0.15); }
	.btn-danger-sm { background: rgba(239,68,68,0.2); color: #ef4444; border: 1px solid rgba(239,68,68,0.3); border-radius: 6px; padding: 0.2rem 0.5rem; font-size: 0.65rem; font-weight: 700; cursor: pointer; white-space: nowrap; }
	.btn-danger-sm:hover { background: rgba(239,68,68,0.35); }
	.btn-primary-sm { background: rgba(59,130,246,0.2); color: #3b82f6; border: 1px solid rgba(59,130,246,0.3); border-radius: 6px; padding: 0.2rem 0.5rem; font-size: 0.65rem; font-weight: 700; cursor: pointer; white-space: nowrap; }
	.btn-primary-sm:hover { background: rgba(59,130,246,0.35); }
	.btn-warning-sm { background: rgba(245,158,11,0.2); color: #f59e0b; border: 1px solid rgba(245,158,11,0.3); border-radius: 6px; padding: 0.2rem 0.5rem; font-size: 0.65rem; font-weight: 700; cursor: pointer; white-space: nowrap; }
	.btn-warning-sm:hover { background: rgba(245,158,11,0.35); }
	.mb-3 { margin-bottom: 0.75rem; }
	.mb-4 { margin-bottom: 1rem; }
	.t-count { font-size: 0.65rem; background: var(--accent-soft); color: var(--accent); padding: 0.1rem 0.4rem; border-radius: 10px; font-weight: 800; border: 1px solid rgba(59,130,246,0.15); }
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
	.edit-modal-header { display: flex; justify-content: space-between; align-items: center; padding: 1.2rem 1.5rem; border-bottom: 1px solid var(--glass-border); background: rgba(59,130,246,0.08); }
	.edit-modal-header h3 { font-size: 1rem; margin: 0; }
	.close-btn { background: none; border: none; color: var(--text-dim); cursor: pointer; font-size: 1.2rem; padding: 0.2rem; }
	.edit-modal-body { padding: 1.5rem; }
	.edit-modal-footer { display: flex; justify-content: flex-end; gap: 0.75rem; padding: 1rem 1.5rem; border-top: 1px solid var(--glass-border); }
	.edit-field { display: flex; flex-direction: column; gap: 0.4rem; }
	.edit-field label { font-size: 0.75rem; font-weight: 700; color: var(--text-dim); text-transform: uppercase; letter-spacing: 0.05em; }
	.ia-blocked-badge { font-size: 0.7rem; margin-left: 0.3rem; opacity: 0.8; }
	.chat-muted-badge { font-size: 0.85rem; margin-left: 0.2rem; }
</style>
