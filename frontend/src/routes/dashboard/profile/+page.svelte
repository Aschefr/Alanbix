<script>
	import { api } from '$lib/api';
	import { onMount } from 'svelte';
	import { goto } from '$app/navigation';

	let user = null;
	let teamName = '';
	let saving = false;
	let saved = false;
	let pointsData = null;
	let existingTeams = [];

	onMount(async () => {
		user = await api.get('/me');
		teamName = user.team_name || '';
		try {
			pointsData = await api.get('/me/points-history');
		} catch { pointsData = { total_points: 0, history: [] }; }
		try {
			existingTeams = await api.get('/players/teams');
		} catch { existingTeams = []; }
	});

	async function saveProfile() {
		saving = true;
		await api.put('/me/profile', { team_name: teamName });
		user.team_name = teamName;
		
		const trimmedTeam = teamName.trim();
		if (trimmedTeam && !existingTeams.includes(trimmedTeam)) {
			existingTeams = [...existingTeams, trimmedTeam];
		}
		
		saving = false;
		saved = true;
		setTimeout(() => saved = false, 2000);
	}

	function getRankEmoji(rank) {
		if (rank === 1) return '🥇';
		if (rank === 2) return '🥈';
		if (rank === 3) return '🥉';
		return rank ? `#${rank}` : '—';
	}

	function goToTournament(id) {
		goto(`/dashboard/tournaments?select=${id}`);
	}
</script>

{#if user}
<div class="profile-page animate-in">
	<header class="profile-header glass">
		<div class="avatar-lg">{user.username[0].toUpperCase()}</div>
		<div class="header-info">
			<h1 class="title-premium">{user.username}</h1>
			<span class="role-badge {user.is_admin ? 'admin' : 'player'}">
				{user.is_admin ? '👑 Administrateur' : '🎮 Joueur'}
			</span>
		</div>
		{#if pointsData}
			<div class="total-pts-badge">
			<span class="pts-number">{pointsData.history.reduce((s, h) => s + (h.total || 0), 0)}</span>
				<span class="pts-label">points</span>
			</div>
		{/if}
	</header>

	<div class="profile-grid">
		<section class="profile-card glass">
			<h2 class="card-title">Mon Équipe</h2>
			<p class="text-dim text-sm mb-4">Ce nom apparaîtra sur ta place dans le plan de salle et sur tes badges de tournoi.</p>
			<div class="input-row">
				<input 
					type="text" class="input" placeholder="Nom d'équipe..."
					bind:value={teamName} list="existing-teams"
				/>
				<datalist id="existing-teams">
					{#each existingTeams as team}
						<option value={team}></option>
					{/each}
				</datalist>
				<button class="btn-primary" on:click={saveProfile} disabled={saving}>
					{#if saving}
						⏳
					{:else if saved}
						✓ Sauvé
					{:else}
						Enregistrer
					{/if}
				</button>
			</div>
		</section>

		<section class="profile-card glass">
			<h2 class="card-title">Informations</h2>
			<div class="info-grid">
				<div class="info-item">
					<span class="info-label">Pseudo</span>
					<span class="info-value">{user.username}</span>
				</div>
				<div class="info-item">
					<span class="info-label">Rôle</span>
					<span class="info-value">{user.is_admin ? 'Administrateur' : 'Joueur'}</span>
				</div>
				<div class="info-item">
					<span class="info-label">Place assignée</span>
					<span class="info-value">{user.seat_id || 'Aucune'}</span>
				</div>
				<div class="info-item">
					<span class="info-label">Équipe</span>
					<span class="info-value">{user.team_name || 'Non définie'}</span>
				</div>
			</div>
		</section>
	</div>

	<!-- Points History -->
	{#if pointsData}
		<section class="points-history glass">
			<h2 class="card-title">🏆 Historique des Points</h2>
			{#if pointsData.history.length === 0}
				<p class="text-dim text-sm">Aucun tournoi clôturé pour le moment.</p>
			{:else}
				<div class="history-table-wrap">
					<table class="history-table">
						<thead>
							<tr>
								<th>Rang</th>
								<th>Tournoi</th>
								<th class="pts-col">Détails</th>
								<th class="pts-col total-col">Total</th>
								<th></th>
							</tr>
						</thead>
						<tbody>
							{#each pointsData.history as h}
								<tr class="history-row">
									<td class="rank-cell">
										<span class="rank-badge rank-{h.rank}">{getRankEmoji(h.rank)}</span>
									</td>
									<td class="tourney-cell">
										<div class="tourney-name">
											{h.tournament_name}
											{#if h.live}<span class="live-badge">● EN COURS</span>{/if}
										</div>
										{#if h.game_name}<div class="tourney-game">{h.game_name}</div>{/if}
										{#if h.team_name}<div class="tourney-team">👥 {h.team_name}</div>{/if}
									</td>
									<td class="pts-col">
										<div class="ph-breakdown">
											{#if h.placement_pts > 0}<span class="ph-bp ph-bp-place" title="Placement : top {h.rank}">🏅+{h.placement_pts}</span>{/if}
											<span class="ph-bp ph-bp-parti" title="Points de participation">👤+{h.participation_pts}</span>
											{#if h.score_pts > 0}<span class="ph-bp ph-bp-score" title="Bonus/Score — distribué selon le score cumulé">⚡+{h.score_pts}</span>{/if}
										</div>
									</td>
									<td class="pts-col total-col"><strong>{h.live ? '~' : '+'}{h.total}</strong></td>
									<td>
										<button class="btn-goto" on:click={() => goToTournament(h.tournament_id)} title="Voir le tournoi">
											→
										</button>
									</td>
								</tr>
							{/each}
						</tbody>
					</table>
				</div>
			{/if}
		</section>
	{/if}
</div>
{/if}

<style>
	.profile-page { display: flex; flex-direction: column; gap: 1.5rem; }
	.profile-header { display: flex; align-items: center; gap: 1.5rem; padding: 2rem; border-radius: 16px; }
	.avatar-lg { width: 64px; height: 64px; background: var(--bg-tertiary); border-radius: 50%; display: flex; align-items: center; justify-content: center; font-size: 1.8rem; font-weight: 800; color: var(--accent); border: 2px solid var(--accent-soft); }
	.header-info { flex: 1; }
	.header-info h1 { margin-bottom: 0.3rem; }
	.role-badge { display: inline-block; padding: 0.3rem 0.8rem; border-radius: 20px; font-size: 0.75rem; font-weight: 700; }
	.role-badge.admin { background: rgba(251, 191, 36, 0.1); color: #fbbf24; border: 1px solid rgba(251, 191, 36, 0.2); }
	.role-badge.player { background: rgba(59, 130, 246, 0.1); color: var(--accent); border: 1px solid rgba(59, 130, 246, 0.2); }

	.total-pts-badge { display: flex; flex-direction: column; align-items: center; padding: 0.8rem 1.5rem; background: linear-gradient(135deg, rgba(251,191,36,0.15), rgba(245,158,11,0.08)); border: 1px solid rgba(251,191,36,0.3); border-radius: 16px; }
	.pts-number { font-size: 2rem; font-weight: 900; color: #fbbf24; line-height: 1; }
	.pts-label { font-size: 0.65rem; font-weight: 700; text-transform: uppercase; letter-spacing: 0.1em; color: var(--text-dim); margin-top: 0.2rem; }

	.profile-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 1.5rem; }
	.profile-card { padding: 1.5rem; border-radius: 16px; }
	.card-title { font-size: 0.85rem; font-weight: 800; text-transform: uppercase; letter-spacing: 0.08em; margin-bottom: 0.75rem; color: var(--text-main); }

	.input-row { display: flex; gap: 0.75rem; }
	.input { flex-grow: 1; padding: 0.7rem 1rem; background: var(--input-bg); border: 1px solid var(--glass-border); border-radius: 8px; color: var(--input-color); font-size: 0.9rem; }
	.input:focus { outline: none; border-color: var(--accent); box-shadow: 0 0 0 3px var(--accent-soft); }

	.info-grid { display: flex; flex-direction: column; gap: 0.75rem; }
	.info-item { display: flex; justify-content: space-between; padding: 0.6rem 0; border-bottom: 1px solid var(--glass-border); }
	.info-item:last-child { border-bottom: none; }
	.info-label { font-size: 0.8rem; color: var(--text-muted); }
	.info-value { font-size: 0.85rem; font-weight: 700; }

	/* Points History */
	.points-history { padding: 1.5rem; border-radius: 16px; }
	.history-table-wrap { overflow-x: auto; }
	.history-table { width: 100%; border-collapse: collapse; font-size: 0.85rem; }
	.history-table thead th { font-size: 0.65rem; font-weight: 800; text-transform: uppercase; letter-spacing: 0.08em; color: var(--text-dim); padding: 0.5rem 0.75rem; text-align: left; border-bottom: 2px solid var(--glass-border); }
	.history-table .pts-col { text-align: center; color: var(--text-dim); font-size: 0.8rem; }
	.history-table .total-col { color: #fbbf24; font-weight: 800; }
	.history-row { transition: background 0.15s; }
	.history-row:hover { background: rgba(59,130,246,0.05); }
	.history-row td { padding: 0.75rem; border-bottom: 1px solid var(--glass-border); vertical-align: middle; }

	.rank-cell { text-align: center; }
	.rank-badge { font-size: 1.2rem; }

	.tourney-cell { min-width: 180px; }
	.tourney-name { font-weight: 700; color: var(--text-main); display: flex; align-items: center; gap: 0.5rem; }
	.tourney-game { font-size: 0.7rem; color: var(--text-dim); margin-top: 0.15rem; }
	.tourney-team { font-size: 0.7rem; color: var(--accent); margin-top: 0.1rem; }

	.live-badge { font-size: 0.55rem; font-weight: 800; color: #22c55e; background: rgba(34,197,94,0.1); border: 1px solid rgba(34,197,94,0.2); padding: 0.1rem 0.4rem; border-radius: 10px; animation: pulse-live 2s ease-in-out infinite; white-space: nowrap; }
	@keyframes pulse-live { 0%, 100% { opacity: 1; } 50% { opacity: 0.5; } }

	.btn-goto { background: rgba(59,130,246,0.1); border: 1px solid rgba(59,130,246,0.2); color: var(--accent); padding: 0.3rem 0.6rem; border-radius: 6px; cursor: pointer; font-weight: 800; font-size: 0.8rem; transition: all 0.15s; }
	.btn-goto:hover { background: rgba(59,130,246,0.2); transform: translateX(2px); }

	/* Points history breakdown chips */
	.ph-breakdown { display: flex; gap: 0.3rem; flex-wrap: wrap; justify-content: center; }
	.ph-bp { font-size: 0.65rem; font-weight: 700; padding: 0.1rem 0.4rem; border-radius: 4px; cursor: help; white-space: nowrap; }
	.ph-bp-place { color: #fbbf24; background: rgba(251,191,36,0.1); }
	.ph-bp-score { color: #818cf8; background: rgba(129,140,248,0.1); }
	.ph-bp-parti { color: var(--text-muted); background: var(--surface-sunken); }
</style>
