<script>
	import { api } from '$lib/api';
	import { onMount } from 'svelte';

	export let games = [];
	export let onSuccess = (tournament) => {};
	export let onCancel = null;

	let defaultPts = { pts_winner: 10, pts_second: 6, pts_third: 4, pts_participation: 1, pts_per_match: 1.0 };
	
	let step = 1;
	let creatingTournament = false;
	let errorMsg = '';

	let config = { 
		name: '', 
		game_id: null, 
		use_teams: false, 
		team_size: 2, 
		points_per_win: 3, 
		phases: 'single', 
		group_size: 4, 
		advancers_count: 2, 
		bracket_type: 'single_elim',
		pts_winner: defaultPts.pts_winner, 
		pts_second: defaultPts.pts_second, 
		pts_third: defaultPts.pts_third,
		pts_participation: defaultPts.pts_participation, 
		pts_per_match: defaultPts.pts_per_match,
		lower_score_is_better: false,
		boolean_mode: false,
		allow_draws: false
	};

	onMount(async () => {
		try {
			const dpCfg = await api.get('/admin/config/default_tournament_pts');
			if (dpCfg?.value) {
				const parsed = typeof dpCfg.value === 'string' ? JSON.parse(dpCfg.value) : dpCfg.value;
				defaultPts = { ...defaultPts, ...parsed };
				config = { 
					...config, 
					pts_winner: defaultPts.pts_winner, 
					pts_second: defaultPts.pts_second, 
					pts_third: defaultPts.pts_third, 
					pts_participation: defaultPts.pts_participation, 
					pts_per_match: defaultPts.pts_per_match 
				};
			}
		} catch {}
		if (games.length > 0 && !config.game_id) {
			config.game_id = games[0].id;
		}
	});

	async function saveTournament() {
		try {
			creatingTournament = true;
			errorMsg = '';
			const payload = {
				name: config.name || null,
				game_id: Number(config.game_id),
				points_per_win: Number(config.points_per_win),
				config: {
					use_teams: config.use_teams,
					team_size: Number(config.team_size),
					points_per_win: Number(config.points_per_win),
					phases: config.phases,
					group_size: Number(config.group_size),
					advancers_count: Number(config.advancers_count),
					bracket_type: config.bracket_type,
					pts_winner: Number(config.pts_winner),
					pts_second: Number(config.pts_second),
					pts_third: Number(config.pts_third),
					pts_participation: Number(config.pts_participation),
					pts_per_match: Number(config.pts_per_match),
					lower_score_is_better: config.lower_score_is_better,
					boolean_mode: config.boolean_mode,
					allow_draws: config.allow_draws
				}
			};
			const res = await api.post('/tournaments', payload);
			onSuccess(res);
			setTimeout(() => {
				step = 1;
				config = { name: '', game_id: games.length > 0 ? games[0].id : null, use_teams: false, team_size: 2, points_per_win: 3, phases: 'single', group_size: 4, advancers_count: 2, bracket_type: 'single_elim', pts_winner: defaultPts.pts_winner, pts_second: defaultPts.pts_second, pts_third: defaultPts.pts_third, pts_participation: defaultPts.pts_participation, pts_per_match: defaultPts.pts_per_match, lower_score_is_better: false, boolean_mode: false, allow_draws: false };
			}, 1000);
		} catch (e) {
			errorMsg = e.message || 'Erreur lors de la création';
		} finally {
			creatingTournament = false;
		}
	}
</script>

<div class="steps-indicator">
	<span class={step === 1 ? 'active' : ''}>1. Général</span>
	<span class={step === 2 ? 'active' : ''}>2. Format</span>
	<span class={step === 3 ? 'active' : ''}>3. Brackets</span>
</div>

<div class="step-box">
	{#if step === 1}
		<div class="flex-col">
			<label>Nom du Tournoi <span class="opt-label">(optionnel — par défaut : nom du jeu)</span></label>
			<input type="text" bind:value={config.name} placeholder="Nom du jeu par défaut..." />
			
			<label>Jeu de Base</label>
			<select bind:value={config.game_id}>
				<option value={null}>Sélectionner un jeu...</option>
				{#each games as g}
					<option value={g.id}>{g.name}</option>
				{/each}
			</select>
			
			{#if errorMsg}
				<div class="error-banner">{errorMsg}</div>
			{/if}

			<div class="nav-btns">
				{#if onCancel}
					<button class="btn-secondary" on:click={onCancel}>Annuler</button>
				{/if}
				<button class="btn-primary" on:click={() => step = 2} disabled={!config.game_id}>Suivant</button>
			</div>
		</div>
	{:else if step === 2}
		<div class="flex-col">
			<label>Mode de rencontre</label>
			<div class="bracket-graphics-grid" style="grid-template-columns: 1fr 1fr;">
				<button class="graphic-card {!config.use_teams ? 'active' : ''}" on:click={() => config.use_teams = false}>
					<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
						<path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"></path>
						<circle cx="12" cy="7" r="4"></circle>
					</svg>
					<span>Individuel (Solo)</span>
				</button>
				<button class="graphic-card {config.use_teams ? 'active' : ''}" on:click={() => config.use_teams = true}>
					<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
						<path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"></path>
						<circle cx="9" cy="7" r="4"></circle>
						<path d="M23 21v-2a4 4 0 0 0-3-3.87"></path>
						<path d="M16 3.13a4 4 0 0 1 0 7.75"></path>
					</svg>
					<span>Par Équipes</span>
				</button>
			</div>

			{#if config.use_teams}
				<label>Taille d'équipe</label>
				<input type="number" bind:value={config.team_size} min="2" max="16" />
			{/if}

			{#if errorMsg}
				<div class="error-banner">{errorMsg}</div>
			{/if}

			<div class="nav-btns">
				<button class="btn-secondary" on:click={() => step = 1}>Retour</button>
				<button class="btn-primary" on:click={() => step = 3}>Suivant</button>
			</div>
		</div>
	{:else}
		<div class="flex-col">
			<label>Structure Globale</label>
			<select bind:value={config.phases}>
				<option value="single">Phase finale directe</option>
				<option value="double">Groupes + Phase finale</option>
			</select>

			{#if config.phases === 'double'}
				<div class="glass-inner p-4 mt-2">
					<div class="grid-2">
						<div><label>Taille Groupes</label><input type="number" bind:value={config.group_size} /></div>
						<div><label>Qualifiés</label><input type="number" bind:value={config.advancers_count} /></div>
					</div>
				</div>
			{/if}

			<label>Format de l'Arbre</label>
			<div class="bracket-graphics-grid">
				<button class="graphic-card {config.bracket_type === 'single_elim' ? 'active' : ''}" on:click={() => config.bracket_type = 'single_elim'}>
					<svg viewBox="0 0 100 60" fill="none" stroke="currentColor" stroke-width="3">
						<path d="M10 10h20v20H10m20-10h20v30H30m20-15h20m-60 30h20"/>
					</svg>
					<span>Élimination Directe</span>
				</button>
				<button class="graphic-card {config.bracket_type === 'double_elim' ? 'active' : ''}" on:click={() => config.bracket_type = 'double_elim'}>
					<svg viewBox="0 0 100 60" fill="none" stroke="currentColor" stroke-width="3">
						<path d="M10 10h20v20H10m20-10h20v20m-20 20h20v-20m-40 30h20m30-30h20"/>
						<path d="M40 35l10-15" stroke-dasharray="2 2"/>
					</svg>
					<span>Double Élimination</span>
				</button>
				<button class="graphic-card {config.bracket_type === 'round_robin' ? 'active' : ''}" on:click={() => config.bracket_type = 'round_robin'}>
					<svg viewBox="0 0 100 60" fill="none" stroke="currentColor" stroke-width="3">
						<circle cx="50" cy="30" r="15"/>
						<path d="M30 30a20 20 0 0 1 40 0"/>
						<path d="M70 30a20 20 0 0 1-40 0" stroke-dasharray="4 4"/>
					</svg>
					<span>Championnat</span>
				</button>
				<button class="graphic-card {config.bracket_type === 'ffa' ? 'active' : ''}" on:click={() => config.bracket_type = 'ffa'}>
					<svg viewBox="0 0 100 60" fill="none" stroke="currentColor" stroke-width="3">
						<rect x="15" y="32" width="14" height="23" rx="2"/>
						<rect x="43" y="17" width="14" height="38" rx="2"/>
						<rect x="71" y="40" width="14" height="15" rx="2"/>
						<circle cx="22" cy="26" r="4"/><circle cx="50" cy="11" r="4"/><circle cx="78" cy="34" r="4"/>
					</svg>
					<span>Free For All</span>
				</button>
			</div>

			<label class="score-invert-label">
				<input type="checkbox" bind:checked={config.lower_score_is_better} />
				🔄 Score inversé <span class="text-dim text-xs">(le plus petit score gagne, ex: placement, golf)</span>
			</label>

			<label class="score-invert-label">
				<input type="checkbox" bind:checked={config.boolean_mode} />
				🎯 Mode Victoire/Défaite <span class="text-dim text-xs">(boutons V/D/É au lieu de scores numériques)</span>
			</label>

			{#if config.bracket_type === 'round_robin'}
			<label class="score-invert-label">
				<input type="checkbox" bind:checked={config.allow_draws} />
				🤝 Autoriser les égalités <span class="text-dim text-xs">(uniquement en mode Championnat / Round Robin)</span>
			</label>
			{/if}

			<details class="pts-config glass-inner" open>
				<summary>🏅 Répartition des points</summary>
				<div class="pts-grid">
					<div class="pts-field">
						<label>🥇 1er</label>
						<input type="number" bind:value={config.pts_winner} min="0" />
					</div>
					<div class="pts-field">
						<label>🥈 2ème</label>
						<input type="number" bind:value={config.pts_second} min="0" />
					</div>
					<div class="pts-field">
						<label>🥉 3ème</label>
						<input type="number" bind:value={config.pts_third} min="0" />
					</div>
					<div class="pts-field">
						<label>👤 Participation</label>
						<input type="number" bind:value={config.pts_participation} min="0" />
					</div>
					<div class="pts-field">
						<label>⚡ Bonus/Score</label>
						<input type="number" bind:value={config.pts_per_match} min="0" step="0.1" />
					</div>
				</div>
				<p class="pts-hint">Bonus/Score = bonus du plancher (valeur saisie) au plafond (2×) selon le score cumulé de chaque joueur/équipe</p>
			</details>

			{#if errorMsg}
				<div class="error-banner">{errorMsg}</div>
			{/if}

			<div class="nav-btns">
				<button class="btn-secondary" on:click={() => step = 2}>Retour</button>
				<button class="btn-primary {creatingTournament ? 'btn-success-anim' : ''}" on:click={saveTournament} disabled={creatingTournament}>
					{creatingTournament ? '✨ Distillation...' : 'Lancer le Tournoi'}
				</button>
			</div>
		</div>
	{/if}
</div>

<style>
	.flex-col { display: flex; flex-direction: column; gap: 0.8rem; }
	.opt-label { font-weight: 400; font-size: 0.7rem; color: var(--text-muted); }
	.steps-indicator { display: flex; gap: 1rem; margin-bottom: 1.5rem; justify-content: center; }
	.steps-indicator span { font-size: 0.8rem; color: var(--text-muted); font-weight: 600; padding: 0.4rem 0.8rem; border-radius: 8px; border: 1px solid var(--glass-border); transition: all 0.2s; }
	.steps-indicator span.active { color: var(--accent); border-color: var(--accent); background: var(--accent-soft); box-shadow: 0 0 10px var(--accent-glow); }
	
	.step-box { min-height: 280px; display: flex; flex-direction: column; }
	
	.bracket-graphics-grid { display: grid; grid-template-columns: repeat(2, 1fr); gap: 0.6rem; margin-bottom: 0.5rem; }
	.graphic-card {
		display: flex;
		flex-direction: column;
		align-items: center;
		justify-content: center;
		gap: 0.5rem;
		padding: 0.8rem;
		background: rgba(255, 255, 255, 0.02);
		border: 1px solid var(--glass-border);
		border-radius: 12px;
		cursor: pointer;
		transition: all 0.2s;
		color: var(--text-dim);
	}
	.graphic-card svg { width: 32px; height: 32px; stroke: currentColor; opacity: 0.6; transition: all 0.2s; }
	.graphic-card span { font-size: 0.75rem; font-weight: 700; }
	.graphic-card:hover { border-color: rgba(59, 130, 246, 0.4); color: var(--text-main); }
	.graphic-card:hover svg { opacity: 0.9; }
	.graphic-card.active {
		background: var(--accent-soft);
		border-color: var(--accent);
		color: var(--accent);
		box-shadow: 0 0 12px var(--accent-glow);
	}
	.graphic-card.active svg { stroke: var(--accent); opacity: 1; }

	.score-invert-label { display: flex; align-items: center; gap: 0.5rem; font-size: 0.8rem; font-weight: 600; color: var(--text-main); cursor: pointer; margin: 0.5rem 0; }
	.score-invert-label input[type="checkbox"] { width: 16px; height: 16px; accent-color: var(--accent); cursor: pointer; }

	.glass-inner { background: var(--surface-sunken); border: 1px solid var(--glass-border); border-radius: 10px; padding: 0.8rem; }
	.grid-2 { display: grid; grid-template-columns: 1fr 1fr; gap: 0.8rem; }
	.p-4 { padding: 1rem; }
	.mt-2 { margin-top: 0.5rem; }

	/* Points Config */
	.pts-config { margin-top: 0.75rem; padding: 0.75rem; border-radius: 10px; }
	.pts-config summary { cursor: pointer; font-weight: 700; font-size: 0.8rem; color: var(--text-main); margin-bottom: 0.5rem; outline: none; }
	.pts-grid { display: grid; grid-template-columns: repeat(5, 1fr); gap: 0.5rem; }
	.pts-field { display: flex; flex-direction: column; gap: 0.3rem; }
	.pts-field label { 
		font-size: 0.6rem; 
		font-weight: 700; 
		color: var(--text-muted); 
		text-align: center; 
		min-height: 1.8rem; 
		display: flex; 
		align-items: flex-end; 
		justify-content: center; 
		line-height: 1.2;
	}
	.pts-field input { width: 100%; padding: 0.35rem; text-align: center; font-size: 0.8rem; font-weight: 800; background: var(--surface-sunken); border: 1px solid var(--glass-border); border-radius: 6px; color: var(--accent); outline: none; }
	.pts-field input:focus { border-color: var(--accent); }
	.pts-hint { font-size: 0.6rem; color: var(--text-dim); margin-top: 0.4rem; font-style: italic; line-height: 1.3; }

	.error-banner { background: rgba(239, 68, 68, 0.15); border: 1px solid rgba(239, 68, 68, 0.3); color: var(--danger); padding: 0.6rem; border-radius: 8px; font-size: 0.75rem; font-weight: 600; text-align: center; margin-top: 0.5rem; }

	.nav-btns { display: flex; justify-content: flex-end; gap: 0.6rem; margin-top: 1rem; }
	.btn-primary {
		padding: 0.55rem 1.2rem;
		font-size: 0.8rem;
		font-weight: 700;
		border-radius: 8px;
		cursor: pointer;
		border: 1px solid transparent;
		background: var(--accent);
		color: white;
		box-shadow: 0 4px 12px var(--accent-glow);
		transition: all 0.2s;
	}
	.btn-primary:hover:not(:disabled) {
		transform: translateY(-1px);
		box-shadow: 0 6px 16px var(--accent-glow);
	}
	.btn-primary:disabled { opacity: 0.5; cursor: not-allowed; }
	
	.btn-secondary {
		padding: 0.55rem 1.2rem;
		font-size: 0.8rem;
		font-weight: 700;
		border-radius: 8px;
		cursor: pointer;
		border: 1px solid var(--glass-border);
		background: transparent;
		color: var(--text-main);
		transition: all 0.2s;
	}
	.btn-secondary:hover { background: var(--hover-tint); }

	/* Success animation on create button */
	.btn-success-anim { background: var(--success) !important; box-shadow: 0 4px 14px var(--success-glow) !important; }

	label { font-size: 0.7rem; font-weight: 700; color: var(--text-muted); text-transform: uppercase; letter-spacing: 0.05em; }
	input[type="text"],
	input[type="number"],
	select {
		width: 100%;
		padding: 0.5rem 0.8rem;
		border-radius: 8px;
		border: 1px solid var(--glass-border);
		background: var(--surface-sunken);
		color: var(--text-main);
		font-size: 0.8rem;
		outline: none;
		transition: border-color 0.15s;
	}
	input:focus,
	select:focus {
		border-color: var(--accent);
	}
</style>
