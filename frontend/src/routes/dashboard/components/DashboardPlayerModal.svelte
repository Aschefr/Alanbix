<script>
	import { createEventDispatcher } from 'svelte';
	import { t } from '$lib/i18nStore';

	export let show = false;
	export let selectedPlayerStats = null;
	export let loadingPlayerStats = false;
	export let allUsers = [];

	const dispatch = createEventDispatcher();
	let overlayMouseDown = false;

	function close() {
		show = false;
		dispatch('close');
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

{#if show}
	<!-- svelte-ignore a11y-no-noninteractive-element-interactions -->
	<!-- svelte-ignore a11y-click-events-have-key-events -->
	<div class="modal-overlay-global" use:portal role="dialog" aria-modal="true"
		on:mousedown={(e) => { if (e.target === e.currentTarget) overlayMouseDown = true; }} 
		on:mouseup={(e) => { if (overlayMouseDown && e.target === e.currentTarget) close(); overlayMouseDown = false; }}>
		<div class="player-modal-card glass" on:click|stopPropagation>
			<header class="player-modal-header">
				<div class="player-modal-profile">
					<div class="player-modal-avatar avatar-shape-{allUsers.find(u => u.username === selectedPlayerStats?.username)?.avatar_shape || 'circle'}">
						{#if allUsers.find(u => u.username === selectedPlayerStats?.username)?.avatar_url}
							<img src={allUsers.find(u => u.username === selectedPlayerStats?.username).avatar_url} alt="" class="player-modal-avatar-img" />
						{:else}
							{selectedPlayerStats?.username ? selectedPlayerStats.username[0].toUpperCase() : '?'}
						{/if}
					</div>
					<div class="player-modal-identity">
						<h3>{selectedPlayerStats?.username || 'Chargement...'}</h3>
						<span class="player-modal-team">{allUsers.find(u => u.username === selectedPlayerStats?.username)?.team_name || $t('dash_modal_team_fallback')}</span>
					</div>
				</div>
				<button class="player-modal-close" on:click={close}>✕</button>
			</header>

			<div class="player-modal-body">
				{#if loadingPlayerStats}
					<div class="player-modal-loading">
						<div class="spinner"></div>
						<span>{$t('dash_modal_stats_loading')}</span>
					</div>
				{:else if selectedPlayerStats}
					<!-- Stats cards summary -->
					<div class="player-modal-summary">
						<div class="summary-stat-card">
							<span class="val accent-gradient">{selectedPlayerStats.total_points}</span>
							<span class="lbl">{$t('dash_modal_points_total')}</span>
						</div>
						<div class="summary-stat-card">
							<span class="val">{selectedPlayerStats.history?.length || 0}</span>
							<span class="lbl">{$t('dash_modal_participations')}</span>
						</div>
						<div class="summary-stat-card">
							<span class="val">{selectedPlayerStats.awards?.length || 0}</span>
							<span class="lbl">{$t('dash_modal_trophies')}</span>
						</div>
					</div>

					<div class="player-modal-details">
						<!-- Tournaments Section -->
						<div class="details-section">
							<h4>{$t('dash_modal_tournaments_title')}</h4>
							<div class="tournaments-list-scroll">
								{#each (selectedPlayerStats.history || []) as hist}
									<div class="tournament-stat-row">
										<div class="t-main">
											<span class="t-game-emoji">🎮</span>
											<div class="t-names">
												<span class="t-name">{hist.tournament_name}</span>
												<span class="t-game">{hist.game_name || 'Jeu inconnu'}</span>
											</div>
										</div>
										<div class="t-details">
											{#if hist.status === 'OPEN'}
												<span class="status-badge open">{$t('tourneys_status_open').toUpperCase()}</span>
											{:else if hist.status === 'RUNNING'}
												<span class="status-badge running">{$t('tourneys_status_running').toUpperCase()}</span>
											{:else}
												<span class="status-badge closed">{$t('tourneys_status_done').toUpperCase()}</span>
											{/if}

											<div class="t-rank-pts">
												<span class="t-rank">{hist.rank ? `#${hist.rank}` : '—'}</span>
												<span class="t-pts-total">{hist.total} pts</span>
											</div>
										</div>
									</div>
									<div class="pts-breakdown">
										<span>{@html $t('dash_modal_points_breakdown', { p: hist.participation_pts, pl: hist.placement_pts })}</span>
										{#if hist.score_pts > 0}
											<span>{@html $t('dash_modal_points_bonus', { b: hist.score_pts })}</span>
										{/if}
										{#if hist.team_name}
											<span class="team-lbl">{@html $t('dash_modal_team_lbl', { name: hist.team_name })}</span>
										{/if}
									</div>
								{:else}
									<p class="empty-msg">{$t('dash_modal_no_tournaments')}</p>
								{/each}
							</div>
						</div>

						<!-- Awards Section -->
						<div class="details-section">
							<h4>{$t('dash_modal_awards_title')}</h4>
							<div class="awards-list-scroll">
								{#each (selectedPlayerStats.awards || []) as award}
									<div class="award-item-card">
										<span class="award-icon">⭐</span>
										<div class="award-info">
											<span class="award-title">{award.title}</span>
											<p class="award-desc">{award.description || ''}</p>
										</div>
									</div>
								{:else}
									<p class="empty-msg">{$t('dash_modal_no_awards')}</p>
								{/each}
							</div>
						</div>
					</div>
				{/if}
			</div>
		</div>
	</div>
{/if}

<style>
	.player-modal-card {
		width: 90%;
		max-width: 800px;
		max-height: 85vh;
		background: var(--bg-primary);
		border: 1px solid var(--glass-border);
		border-radius: var(--radius-xl);
		display: flex;
		flex-direction: column;
		overflow: hidden;
		box-shadow: 0 20px 50px rgba(0, 0, 0, 0.5), 0 0 35px var(--accent-soft);
		animation: scaleUp 0.3s cubic-bezier(0.34, 1.56, 0.64, 1) forwards;
		font-family: var(--font-main);
	}
	@keyframes scaleUp {
		from { transform: scale(0.95); opacity: 0; }
		to { transform: scale(1); opacity: 1; }
	}
	.player-modal-header {
		display: flex;
		justify-content: space-between;
		align-items: center;
		padding: 1.2rem 1.5rem;
		border-bottom: 1px solid var(--glass-border);
		background: var(--surface-sunken);
	}
	.player-modal-profile {
		display: flex;
		align-items: center;
		gap: 1rem;
	}
	.player-modal-avatar {
		width: 48px;
		height: 48px;
		border-radius: 50%;
		background: var(--accent-soft);
		color: var(--accent);
		border: 1px solid var(--accent);
		display: flex;
		align-items: center;
		justify-content: center;
		font-size: 1.4rem;
		font-weight: 800;
		box-shadow: 0 0 10px var(--accent-glow);
		overflow: hidden;
	}
	.player-modal-avatar-img {
		width: 100%;
		height: 100%;
		object-fit: cover;
		border-radius: 50%;
	}
	.player-modal-identity h3 {
		margin: 0;
		font-family: var(--font-title);
		font-size: 1.3rem;
		font-weight: 800;
		color: var(--text-main);
	}
	.player-modal-team {
		font-family: var(--font-main);
		font-size: 0.75rem;
		color: var(--accent);
		font-weight: 600;
	}
	.player-modal-close {
		background: none;
		border: none;
		color: var(--text-muted);
		font-size: 1.3rem;
		cursor: pointer;
		transition: color 0.15s;
	}
	.player-modal-close:hover {
		color: var(--danger);
	}
	.player-modal-body {
		flex: 1;
		overflow-y: auto;
		padding: 1.5rem;
		display: flex;
		flex-direction: column;
		gap: 1.5rem;
	}
	.player-modal-loading {
		display: flex;
		flex-direction: column;
		align-items: center;
		justify-content: center;
		gap: 1rem;
		padding: 4rem 1rem;
		color: var(--text-muted);
	}
	.player-modal-loading .spinner {
		width: 35px;
		height: 35px;
		border: 3px solid var(--glass-border);
		border-top-color: var(--accent);
		border-radius: 50%;
		animation: spin 1s linear infinite;
	}
	@keyframes spin { to { transform: rotate(360deg); } }

	.player-modal-summary {
		display: grid;
		grid-template-columns: 1fr 1fr 1fr;
		gap: 1rem;
	}
	.summary-stat-card {
		background: var(--surface-raised);
		border: 1px solid var(--glass-border);
		border-radius: 12px;
		padding: 1rem;
		display: flex;
		flex-direction: column;
		align-items: center;
		justify-content: center;
	}
	.summary-stat-card .val {
		font-family: var(--font-title);
		font-size: 1.8rem;
		font-weight: 800;
		color: var(--text-main);
	}
	.summary-stat-card .val.accent-gradient {
		color: var(--accent);
		text-shadow: 0 0 10px var(--accent-glow);
	}
	.summary-stat-card .lbl {
		font-family: var(--font-main);
		font-size: 0.7rem;
		color: var(--text-muted);
		text-transform: uppercase;
		font-weight: 700;
		margin-top: 0.2rem;
	}
	.player-modal-details {
		display: grid;
		grid-template-columns: 1.2fr 0.8fr;
		gap: 1.5rem;
		min-height: 250px;
	}
	@media (max-width: 600px) {
		.player-modal-details {
			grid-template-columns: 1fr;
		}
		.player-modal-summary {
			grid-template-columns: 1fr;
		}
	}
	.details-section {
		display: flex;
		flex-direction: column;
		gap: 0.8rem;
	}
	.details-section h4 {
		margin: 0;
		font-family: var(--font-title);
		font-size: 0.85rem;
		font-weight: 800;
		text-transform: uppercase;
		letter-spacing: 0.05em;
		color: var(--text-secondary);
		border-bottom: 1px solid var(--glass-border);
		padding-bottom: 0.4rem;
	}
	.tournaments-list-scroll, .awards-list-scroll {
		display: flex;
		flex-direction: column;
		gap: 0.6rem;
		overflow-y: auto;
		max-height: 250px;
		padding-right: 0.25rem;
	}
	.tournament-stat-row {
		display: flex;
		justify-content: space-between;
		align-items: center;
		background: var(--surface-raised);
		border: 1px solid var(--glass-border);
		border-radius: 8px;
		padding: 0.6rem 0.8rem;
		gap: 0.5rem;
	}
	.t-main {
		display: flex;
		align-items: center;
		gap: 0.6rem;
		min-width: 0;
	}
	.t-game-emoji {
		font-size: 1.1rem;
	}
	.t-names {
		display: flex;
		flex-direction: column;
		min-width: 0;
	}
	.t-name {
		font-size: 0.8rem;
		font-weight: 700;
		color: var(--text-main);
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
	}
	.t-game {
		font-size: 0.65rem;
		color: var(--text-muted);
	}
	.t-details {
		display: flex;
		align-items: center;
		gap: 0.6rem;
		flex-shrink: 0;
	}
	.t-rank-pts {
		display: flex;
		flex-direction: column;
		align-items: flex-end;
	}
	.t-rank {
		font-size: 0.8rem;
		font-weight: 800;
		color: var(--accent);
	}
	.t-pts-total {
		font-size: 0.7rem;
		font-weight: 700;
		color: var(--text-secondary);
	}
	.pts-breakdown {
		display: flex;
		flex-wrap: wrap;
		gap: 0.8rem;
		font-size: 0.65rem;
		color: var(--text-muted);
		padding: 0.2rem 0.8rem 0.5rem 0.8rem;
		border-bottom: 1px dashed var(--glass-border);
		margin-top: -0.4rem;
		margin-bottom: 0.2rem;
	}
	.pts-breakdown strong {
		color: var(--text-secondary);
	}
	.pts-breakdown .team-lbl {
		color: var(--accent);
		font-style: italic;
	}
	.status-badge.open {
		background: rgba(59, 130, 246, 0.12);
		color: #3b82f6;
		border: 1px solid rgba(59, 130, 246, 0.25);
		font-size: 0.55rem;
		padding: 0.1rem 0.35rem;
		border-radius: 4px;
		font-weight: 800;
	}
	.status-badge.closed {
		background: rgba(156, 163, 175, 0.12);
		color: #9ca3af;
		border: 1px solid rgba(156, 163, 175, 0.25);
		font-size: 0.55rem;
		padding: 0.1rem 0.35rem;
		border-radius: 4px;
		font-weight: 800;
	}
	.status-badge.running {
		background: rgba(59, 130, 246, 0.1);
		color: var(--accent);
		border: 1px solid rgba(59, 130, 246, 0.25);
		font-size: 0.55rem;
		padding: 0.1rem 0.35rem;
		border-radius: 4px;
		font-weight: 800;
	}
	.award-item-card {
		display: flex;
		align-items: flex-start;
		gap: 0.6rem;
		background: rgba(251, 191, 36, 0.05);
		border: 1px solid rgba(251, 191, 36, 0.2);
		border-radius: 8px;
		padding: 0.6rem 0.8rem;
	}
	.award-icon {
		font-size: 1.2rem;
		color: #fbbf24;
		text-shadow: 0 0 8px rgba(251, 191, 36, 0.5);
	}
	.award-info {
		display: flex;
		flex-direction: column;
	}
	.award-title {
		font-size: 0.8rem;
		font-weight: 700;
		color: #fbbf24;
	}
	.award-desc {
		margin: 0.15rem 0 0 0;
		font-size: 0.68rem;
		color: var(--text-dim);
		line-height: 1.3;
	}
	.empty-msg {
		font-size: 0.75rem;
		color: var(--text-muted);
		font-style: italic;
		margin: 1rem 0;
		text-align: center;
	}
</style>
