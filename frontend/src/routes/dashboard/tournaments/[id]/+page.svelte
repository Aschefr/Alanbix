<script>
	import { page } from '$app/stores';
	import { api } from '$lib/api';
	import { onMount } from 'svelte';
	import Modal from '$lib/components/Modal.svelte';

	let id = $page.params.id;
	let tournament = null;
	let participants = [];
	let allUsers = [];
	let currentUser = null;
	let saving = false;

	let showModal = false;
	let modalTitle = '';
	let modalMessage = '';
	let modalType = 'info';
	let modalConfirmCallback = null;

	let activeTab = 'bracket'; // 'bracket', 'settings', 'players'
	let showDeleteConfirm = false;

	// Pan & Zoom state
	let scale = 1;
	let panX = 0;
	let panY = 0;
	let isDragging = false;
	let startX, startY;
	let viewportEl, canvasEl;

	onMount(async () => {
		loadData();
	});

	async function loadData() {
		try {
			tournament = await api.get(`/tournaments/${id}`);
			participants = await api.get(`/tournaments/${id}/participants`);
			currentUser = await api.get('/me');
			if (currentUser?.is_admin) {
				allUsers = await api.get('/room/users');
			}
		} catch (e) {
			notify('Erreur', 'Tournoi introuvable.', 'error');
		}
	}

	async function forceAddPlayer(userId) {
		try {
			await api.post(`/tournaments/${id}/join`, { user_id: userId });
			await loadData();
		} catch (e) {
			notify('Erreur', e.message || 'Impossible d\'ajouter ce joueur.', 'error');
		}
	}

	$: unregisteredUsers = allUsers.filter(u => !participants.find(p => p.user_id === u.id));

	function notify(title, message, type = 'info') {
		modalTitle = title;
		modalMessage = message;
		modalType = type;
		modalConfirmCallback = null;
		showModal = true;
	}

	async function saveTournament() {
		try {
			saving = true;
			await api.put(`/tournaments/${id}`, {
				name: tournament.name,
				status: tournament.status
			});
			saving = false;
			notify('Succès', 'Tournoi mis à jour.', 'success');
		} catch (e) {
			saving = false;
			notify('Erreur', e.message, 'error');
		}
	}

	async function confirmDeleteTournament() {
		try {
			await api.delete(`/tournaments/${id}`);
			window.location.href = '/dashboard/tournaments';
		} catch (e) {
			notify('Erreur', e.message, 'error');
		}
	}

	async function removePlayer(userId, username) {
		modalTitle = 'Expulser le joueur ?';
		modalMessage = `Voulez-vous désinscrire ${username} du tournoi ?`;
		modalType = 'error';
		modalConfirmCallback = async () => {
			try {
				await api.delete(`/tournaments/${id}/participants/${userId}`);
				await loadData();
			} catch (e) {
				notify('Erreur', e.message, 'error');
			}
		};
		showModal = true;
	}

	// Pan & Zoom Handlers (AXE-29: clamped)
	const ZOOM_MIN = 0.4, ZOOM_MAX = 2.5;
	function clampPan() {
		if (!viewportEl || !canvasEl) return;
		const vw = viewportEl.clientWidth;
		const vh = viewportEl.clientHeight;
		const cw = canvasEl.scrollWidth * scale;
		const ch = canvasEl.scrollHeight * scale;
		const margin = 100;
		panX = Math.min(margin, Math.max(panX, vw - cw - margin));
		panY = Math.min(margin, Math.max(panY, vh - ch - margin));
	}
	function onWheel(e) {
		e.preventDefault();
		const zoomIntensity = 0.1;
		if (e.deltaY < 0) {
			scale *= (1 + zoomIntensity);
		} else {
			scale /= (1 + zoomIntensity);
		}
		scale = Math.min(Math.max(ZOOM_MIN, scale), ZOOM_MAX);
		clampPan();
	}

	function onMouseDown(e) {
		isDragging = true;
		startX = e.clientX - panX;
		startY = e.clientY - panY;
	}

	function onMouseMove(e) {
		if (!isDragging) return;
		panX = e.clientX - startX;
		panY = e.clientY - startY;
		clampPan();
	}

	function onMouseUp() {
		isDragging = false;
	}

	function resetZoom() {
		if (!viewportEl || !canvasEl) return;
		const vw = viewportEl.clientWidth;
		const vh = viewportEl.clientHeight;
		const cw = canvasEl.scrollWidth;
		const ch = canvasEl.scrollHeight;
		if (cw === 0 || ch === 0) {
			scale = 1;
			panX = 0;
			panY = 0;
			return;
		}

		// Calculate optimal scale factor to fit within viewport with margins
		const scaleX = (vw - 40) / cw;
		const scaleY = (vh - 40) / ch;
		let optimalScale = Math.min(scaleX, scaleY);

		// Clamp optimalScale so that text remains readable (min 0.55, max 1.25)
		optimalScale = Math.max(0.55, Math.min(optimalScale, 1.25));
		scale = optimalScale;

		// Center the bracket canvas in the viewport
		panX = (vw - cw * scale) / 2;
		panY = (vh - ch * scale) / 2;

		clampPan();
	}

	function panTo(dx, dy) { panX += dx; panY += dy; clampPan(); }

	// AXE-29: Directional arrows
	$: arrowLeft = panX < -10;
	$: arrowRight = viewportEl && canvasEl ? (panX + canvasEl.scrollWidth * scale > viewportEl.clientWidth + 10) : false;
	$: arrowUp = panY < -10;
	$: arrowDown = viewportEl && canvasEl ? (panY + canvasEl.scrollHeight * scale > viewportEl.clientHeight + 10) : false;
	$: if (panX !== undefined || panY !== undefined || scale) { arrowLeft = panX < -10; arrowRight = viewportEl && canvasEl ? (panX + canvasEl.scrollWidth * scale > viewportEl.clientWidth + 10) : false; arrowUp = panY < -10; arrowDown = viewportEl && canvasEl ? (panY + canvasEl.scrollHeight * scale > viewportEl.clientHeight + 10) : false; }

	// Auto-fit and center bracket on load
	$: if (tournament && viewportEl) {
		setTimeout(() => resetZoom(), 150);
	}

	// Helper to group matches by round
	function getRounds() {
		if (!tournament?.config) return [];
		const matches = tournament.config;
		const rounds = {};
		matches.forEach(m => {
			if (!rounds[m.id.r]) rounds[m.id.r] = [];
			rounds[m.id.r].push(m);
		});
		return Object.keys(rounds).sort((a,b) => a-b).map(k => rounds[k]);
	}

	function getPlayerName(userId) {
		if (userId === 0) return 'TBD';
		const p = participants.find(part => part.user_id === userId);
		return p ? p.username : `Joueur ${userId}`;
	}
</script>

<div class="tournament-view">
	<header class="flex-row justify-between items-center mb-6">
		<h1 class="title-premium">{tournament?.name || 'Chargement...'}</h1>
		<a href="/dashboard/admin" class="btn-secondary">Retour Admin</a>
	</header>

	{#if tournament}
		<div class="tabs glass mb-6">
			<button class={activeTab === 'bracket' ? 'active' : ''} on:click={() => activeTab = 'bracket'}>Arbre de Tournoi</button>
			<button class={activeTab === 'players' ? 'active' : ''} on:click={() => activeTab = 'players'}>Joueurs ({participants.length})</button>
			<button class={activeTab === 'settings' ? 'active' : ''} on:click={() => activeTab = 'settings'}>Paramètres</button>
		</div>

		<div class="tab-content">
			<!-- BRACKET TAB -->
			{#if activeTab === 'bracket'}
				<div class="bracket-wrapper glass">
					<div class="bracket-controls">
						<button class="btn-secondary" on:click={resetZoom}>Recentrer</button>
						<span class="text-dim text-xs">Utilisez la molette pour zoomer et glissez pour vous déplacer</span>
					</div>
					
					<!-- svelte-ignore a11y-no-static-element-interactions -->
					<div class="bracket-viewport" bind:this={viewportEl}
						on:wheel={onWheel} 
						on:mousedown={onMouseDown} 
						on:mousemove={onMouseMove} 
						on:mouseup={onMouseUp} 
						on:mouseleave={onMouseUp}>
						
						<div class="bracket-canvas" bind:this={canvasEl} style="transform: translate({panX}px, {panY}px) scale({scale});">
							{#if tournament.config && tournament.config.length > 0}
								<div class="rounds-container">
									{#each getRounds() as roundMatches, roundIndex}
										<div class="round-col">
											<div class="round-header">Round {roundIndex + 1}</div>
											<div class="matches-col">
												{#each roundMatches as match}
													<div class="bracket-match">
														<div class="player {match.p[0] ? 'filled' : ''}">{getPlayerName(match.p[0])}</div>
														<div class="player {match.p[1] ? 'filled' : ''}">{getPlayerName(match.p[1])}</div>
													</div>
												{/each}
											</div>
										</div>
									{/each}
								</div>
							{:else}
								<div class="empty-bracket">
									Le bracket n'a pas encore été généré. Démarrez le tournoi pour le visualiser.
								</div>
							{/if}
						</div>
					</div>
					{#if arrowLeft}<div class="pan-arrow pan-arrow-left" on:click={() => panTo(150, 0)}>‹</div>{/if}
					{#if arrowRight}<div class="pan-arrow pan-arrow-right" on:click={() => panTo(-150, 0)}>›</div>{/if}
					{#if arrowUp}<div class="pan-arrow pan-arrow-up" on:click={() => panTo(0, 150)}>‹</div>{/if}
					{#if arrowDown}<div class="pan-arrow pan-arrow-down" on:click={() => panTo(0, -150)}>‹</div>{/if}
				</div>

				<!-- Unregistered users bar (admin only) -->
				{#if currentUser?.is_admin && unregisteredUsers.length > 0}
					<div class="unregistered-bar glass">
						<div class="unreg-header">
							<span class="unreg-label">👥 Joueurs non inscrits</span>
							<span class="unreg-hint">Cliquez pour forcer l'inscription</span>
						</div>
						<div class="unreg-badges">
							{#each unregisteredUsers as u}
								<button class="unreg-badge" on:click={() => forceAddPlayer(u.id)} title="Ajouter {u.username} au tournoi">
									<span class="unreg-avatar">👤</span>
									<span class="unreg-name">{u.username}</span>
									{#if u.team_name}
										<span class="unreg-team">• {u.team_name}</span>
									{/if}
									<span class="unreg-plus">+</span>
								</button>
							{/each}
						</div>
					</div>
				{/if}

			<!-- SETTINGS TAB -->
			{:else if activeTab === 'settings'}
				<div class="grid-2 gap-6">
					<section class="glass p-6">
						<h2 class="text-accent mb-4">Configuration Générale</h2>
						<div class="flex-col gap-4">
							<div class="input-group">
								<label>Nom du Tournoi</label>
								<input type="text" bind:value={tournament.name} class="input" />
							</div>
							<div class="input-group">
								<label>Statut</label>
								<select bind:value={tournament.status} class="input">
									<option value="OPEN">Ouvert (Inscriptions)</option>
									<option value="RUNNING">En Cours</option>
									<option value="DONE">Terminé</option>
								</select>
							</div>
							<button class="btn-primary mt-2" on:click={saveTournament} disabled={saving}>
								{saving ? 'Enregistrement...' : 'Enregistrer les modifications'}
							</button>
						</div>
					</section>

					<section class="glass p-6 border-danger">
						<h2 class="text-danger mb-4">Zone de Danger</h2>
						<p class="text-dim text-sm mb-4">La suppression du tournoi est définitive. Elle effacera tous les scores et expulsera tous les participants.</p>
						
						{#if !showDeleteConfirm}
							<button class="btn-danger-full" on:click={() => showDeleteConfirm = true}>Supprimer le Tournoi</button>
						{:else}
							<div class="confirm-box p-4">
								<p class="font-bold text-danger mb-3">Êtes-vous absolument sûr ?</p>
								<div class="flex-row gap-2">
									<button class="btn-secondary flex-grow" on:click={() => showDeleteConfirm = false}>Annuler</button>
									<button class="btn-primary danger flex-grow" style="background: var(--danger); border-color: var(--danger);" on:click={confirmDeleteTournament}>Oui, supprimer</button>
								</div>
							</div>
						{/if}
					</section>
				</div>

			<!-- PLAYERS TAB -->
			{:else if activeTab === 'players'}
				<section class="glass p-6">
					<div class="flex-row justify-between mb-4">
						<h2 class="text-accent">Participants ({participants.length})</h2>
					</div>
					
					<div class="players-list">
						{#each participants as p}
							<div class="player-card glass-inner flex-row justify-between items-center p-4">
								<div class="flex-row items-center gap-3">
									<div class="avatar-small avatar-shape-{p.avatar_shape || 'circle'}">
										{#if p.avatar_url}
											<img src={p.avatar_url} alt="" class="avatar-small-img" />
										{:else}
											👤
										{/if}
									</div>
									<span class="font-bold">{p.username}</span>
								</div>
								<button class="btn-danger-sm" on:click={() => removePlayer(p.user_id, p.username)}>Expulser</button>
							</div>
						{:else}
							<p class="text-dim">Aucun participant n'est inscrit pour le moment.</p>
						{/each}
					</div>
				</section>
			{/if}
		</div>
	{:else}
		<p>Chargement...</p>
	{/if}
</div>

<Modal 
	bind:show={showModal} 
	title={modalTitle} 
	message={modalMessage} 
	type={modalType} 
	onConfirm={modalConfirmCallback} 
/>

<style>
	.tournament-view { display: flex; flex-direction: column; gap: 1rem; }
	.grid-2 { display: grid; grid-template-columns: 1fr 1fr; }
	
	.tabs { display: inline-flex; padding: 0.3rem; border-radius: 12px; }
	.tabs button { padding: 0.6rem 1.2rem; border: none; background: transparent; color: var(--text-dim); cursor: pointer; font-weight: 600; border-radius: 8px; transition: all 0.2s; font-size: 0.9rem; }
	.tabs button.active { background: var(--accent); color: white; box-shadow: 0 4px 12px var(--accent-glow); }

	.input { padding: 0.8rem; background: var(--input-bg); border: 1px solid var(--glass-border); border-radius: 8px; color: var(--input-color); width: 100%; }
	.border-danger { border-color: rgba(239, 68, 68, 0.3); }
	.confirm-box { background: rgba(239, 68, 68, 0.05); border: 1px dashed var(--danger); border-radius: 8px; }
	.flex-grow { flex-grow: 1; }

	.avatar-small { width: 32px; height: 32px; background: var(--surface-raised); border-radius: 50%; display: flex; align-items: center; justify-content: center; overflow: hidden; }
	.avatar-small-img { width: 100%; height: 100%; object-fit: cover; border-radius: 50%; }

	/* Bracket Pan/Zoom Styles */
	.bracket-wrapper { position: relative; flex-grow: 1; min-height: 500px; overflow: hidden; border-radius: 12px; display: flex; flex-direction: column; }
	.bracket-controls { position: absolute; top: 1rem; left: 1rem; z-index: 10; display: flex; align-items: center; gap: 1rem; background: var(--glass-bg); padding: 0.5rem; border-radius: 8px; backdrop-filter: blur(4px); }
	.bracket-viewport { flex-grow: 1; overflow: hidden; cursor: grab; background: var(--surface-sunken); user-select: none; -webkit-user-select: none; }
	.bracket-viewport:active { cursor: grabbing; }
	.bracket-canvas { transform-origin: 0 0; transition: transform 0.1s ease-out; padding: 4rem; display: inline-block; min-width: 100%; min-height: 100%; }
	
	.empty-bracket { position: absolute; top: 50%; left: 50%; transform: translate(-50%, -50%); color: var(--text-dim); text-align: center; }

	.rounds-container { display: flex; gap: 4rem; }
	.round-col { display: flex; flex-direction: column; gap: 1rem; }
	.round-header { text-align: center; font-weight: 700; color: var(--accent); margin-bottom: 1rem; text-transform: uppercase; font-size: 0.85rem; letter-spacing: 1px; }
	
	.matches-col { display: flex; flex-direction: column; justify-content: space-around; flex-grow: 1; gap: 2rem; position: relative; }

	.bracket-match { width: 220px; background: var(--surface-raised); border: 1px solid var(--glass-border); border-radius: 8px; overflow: hidden; display: flex; flex-direction: column; box-shadow: 0 4px 6px rgba(0,0,0,0.15); z-index: 2; position: relative; }
	
	/* Connection lines styling */
	.matches-col:not(:last-child) .bracket-match::after {
		content: ''; position: absolute; right: -2rem; top: 50%; width: 2rem; height: 2px; background: var(--glass-border);
	}
	.round-col:not(:first-child) .matches-col::before {
		content: ''; position: absolute; left: -2rem; top: 25%; bottom: 25%; width: 2px; background: var(--glass-border);
	}

	.player { padding: 0.75rem 1.2rem; font-size: 1.0rem; border-bottom: 1px solid var(--glass-border); background: var(--surface-sunken); color: var(--text-muted); }
	.player:last-child { border-bottom: none; }
	.player.filled { color: var(--text-main); background: var(--accent-soft); }

	/* AXE-29: Directional pan arrows */
	.pan-arrow { position: absolute; display: flex; align-items: center; justify-content: center; color: var(--accent); font-size: 1.4rem; font-weight: 900; opacity: 0.6; pointer-events: auto; cursor: pointer; z-index: 5; animation: panArrowPulse 1.5s ease-in-out infinite; transition: opacity 0.15s, transform 0.15s; }
	.pan-arrow:hover { opacity: 1; animation: none; }
	.pan-arrow-left { left: 6px; top: 50%; transform: translateY(-50%); width: 28px; height: 50px; background: linear-gradient(90deg, rgba(59,130,246,0.15), transparent); border-radius: 6px; }
	.pan-arrow-right { right: 6px; top: 50%; transform: translateY(-50%); width: 28px; height: 50px; background: linear-gradient(-90deg, rgba(59,130,246,0.15), transparent); border-radius: 6px; }
	.pan-arrow-up { top: 6px; left: 50%; transform: translateX(-50%) rotate(90deg); width: 28px; height: 50px; background: linear-gradient(90deg, rgba(59,130,246,0.15), transparent); border-radius: 6px; }
	.pan-arrow-down { bottom: 6px; left: 50%; transform: translateX(-50%) rotate(-90deg); width: 28px; height: 50px; background: linear-gradient(90deg, rgba(59,130,246,0.15), transparent); border-radius: 6px; }
	@keyframes panArrowPulse { 0%, 100% { opacity: 0.4; } 50% { opacity: 0.85; } }

	/* Unregistered users bar */
	.unregistered-bar { margin-top: 1rem; padding: 1rem; border-radius: 12px; }
	.unreg-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.75rem; }
	.unreg-label { font-size: 0.8rem; font-weight: 700; color: var(--text-main); }
	.unreg-hint { font-size: 0.65rem; color: var(--text-muted); font-style: italic; }
	.unreg-badges { display: flex; flex-wrap: wrap; gap: 0.4rem; }
	.unreg-badge {
		display: flex; align-items: center; gap: 0.35rem;
		padding: 0.3rem 0.6rem; border-radius: 20px; font-size: 0.75rem; font-weight: 600;
		background: var(--surface-raised); border: 1px solid var(--glass-border);
		color: var(--text-dim); cursor: pointer; transition: all 0.2s;
	}
	.unreg-badge:hover { background: var(--map-user-option-hover); border-color: var(--accent); color: var(--accent); }
	.unreg-avatar { font-size: 0.7rem; }
	.unreg-name { color: inherit; }
	.unreg-team { color: var(--text-muted); font-weight: 500; font-size: 0.65rem; }
	.unreg-badge:hover .unreg-team { color: var(--text-dim); }
	.unreg-plus { color: var(--accent); font-weight: 800; font-size: 0.85rem; margin-left: 0.15rem; opacity: 0; transition: opacity 0.2s; }
	.unreg-badge:hover .unreg-plus { opacity: 1; }
</style>
