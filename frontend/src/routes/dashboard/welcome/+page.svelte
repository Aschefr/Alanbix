<script>
	import { onMount } from 'svelte';
	import { goto } from '$app/navigation';
	import { api } from '$lib/api';
	import { startTutorial } from '$lib/tutorialStore';
	import { eventName, t } from '$lib/i18nStore';

	let step = 1;
	let user = null;
	
	// Step 1: Team
	let teamName = '';
	let existingTeams = [];
	let savingTeam = false;

	// Step 2: Map
	let layout = { seats: [], tables: [], furniture: [] };
	let allUsers = [];
	let selectedSeat = null;
	let savingSeat = false;

	// Map rendering
	const SEAT_SIZE = 50;
	let vbX = 0, vbY = 0, vbW = 900, vbH = 600;
	let isPanning = false;
	let panMoved = false;
	let panStart = { x: 0, y: 0 };
	let panVbStart = { x: 0, y: 0 };

	onMount(async () => {
		user = await api.get('/me');
		teamName = user.team_name || '';
		selectedSeat = user.seat_id;

		try { existingTeams = await api.get('/players/teams'); } catch {}
		
		try {
			const res = await api.get('/room/layout');
			layout = res.layout || { seats: [], tables: [], furniture: [] };
			if (!layout.tables) layout.tables = [];
			if (!layout.seats) layout.seats = [];
			if (!layout.furniture) layout.furniture = [];
		} catch {}

		try { allUsers = await api.get('/room/users'); } catch {}
	});

	async function saveTeam() {
		savingTeam = true;
		try {
			await api.put('/me/profile', { team_name: teamName });
			if (user) user.team_name = teamName;
			step = 2;
		} catch (e) {
			console.error(e);
		}
		savingTeam = false;
	}

	function skipTeam() {
		step = 2;
	}

	function getOccupant(seatId) {
		return allUsers.find(u => u.seat_id === seatId);
	}

	async function claimSeat(seatId) {
		if (savingSeat) return;
		savingSeat = true;
		try {
			await api.post('/room/assign-seat', { seat_id: seatId });
			selectedSeat = seatId;
			await refreshUsers();
			setTimeout(() => { step = 3; savingSeat = false; }, 600);
		} catch (e) {
			console.error(e);
			savingSeat = false;
		}
	}

	async function refreshUsers() {
		try { allUsers = await api.get('/room/users'); } catch {}
	}

	function skipSeat() {
		step = 3;
	}

	function finishWizard() {
		goto('/dashboard').then(() => {
			startTutorial();
		});
	}

	// Map Pan Logic
	function onWheel(e) {
		e.preventDefault();
		const svg = document.querySelector('.wizard-canvas');
		if (!svg) return;
		const pt = svg.createSVGPoint();
		pt.x = e.clientX; pt.y = e.clientY;
		const svgPt = pt.matrixTransform(svg.getScreenCTM().inverse());
		
		const factor = e.deltaY > 0 ? 1.12 : 0.88;
		const newW = Math.max(200, Math.min(3000, vbW * factor));
		const newH = Math.max(133, Math.min(2000, vbH * factor));
		const ratio = newW / vbW;
		vbX = svgPt.x - (svgPt.x - vbX) * ratio;
		vbY = svgPt.y - (svgPt.y - vbY) * ratio;
		vbW = newW;
		vbH = newH;
	}

	function onPanStart(e) {
		if (e.button !== 0) return;
		isPanning = true;
		panStart = { x: e.clientX, y: e.clientY };
		panVbStart = { x: vbX, y: vbY };
		panMoved = false;
	}

	function onPanMove(e) {
		if (!isPanning) return;
		const rawDx = e.clientX - panStart.x;
		const rawDy = e.clientY - panStart.y;
		if (Math.abs(rawDx) > 3 || Math.abs(rawDy) > 3) panMoved = true;
		const svg = document.querySelector('.wizard-canvas');
		const ctm = svg.getScreenCTM();
		const dx = rawDx / ctm.a;
		const dy = rawDy / ctm.d;
		vbX = panVbStart.x - dx;
		vbY = panVbStart.y - dy;
	}

	function onMouseUp() {
		isPanning = false;
	}
</script>

<div class="welcome-wizard">
	<div class="wizard-header">
		<h1 class="title-premium">Bienvenue à l'évènement {$eventName} !</h1>
		<div class="steps-indicator">
			<div class="step-dot {step >= 1 ? 'active' : ''}">1</div>
			<div class="step-line {step >= 2 ? 'active' : ''}"></div>
			<div class="step-dot {step >= 2 ? 'active' : ''}">2</div>
			<div class="step-line {step >= 3 ? 'active' : ''}"></div>
			<div class="step-dot {step >= 3 ? 'active' : ''}">3</div>
		</div>
	</div>

	<div class="wizard-content glass animate-in {step === 2 ? 'wide' : ''}">
		{#if step === 1}
			<div class="step-panel">
				<h2>{$t("welcome_step1_title")}</h2>
				<p class="text-dim text-sm mb-4">{$t("welcome_step1_desc")}</p>
				
				<div class="input-group">
					<input 
						type="text" class="input-lg" placeholder={$t("welcome_team_placeholder")}
						bind:value={teamName}
						on:keydown={(e) => e.key === 'Enter' && saveTeam()}
					/>
				</div>

				{#if existingTeams.length > 0}
					<div class="existing-teams-wrap">
						<span class="existing-teams-label">{$t("welcome_team_join_existing")}</span>
						<div class="existing-teams-list">
							{#each existingTeams as t}
								<button 
									type="button"
									class="btn-team-select {teamName === t ? 'active' : ''}" 
									on:click={() => teamName = t}
								>
									👥 {t}
								</button>
							{/each}
						</div>
					</div>
				{/if}

				<div class="wizard-actions">
					<button class="btn-link" on:click={skipTeam}>{$t("welcome_btn_skip_step")}</button>
					<button class="btn-primary" on:click={saveTeam} disabled={savingTeam}>{$t("welcome_btn_next")}</button>
				</div>
			</div>

		{:else if step === 2}
			<div class="step-panel step-map">
				<h2>{$t("welcome_step2_title")}</h2>
				<p class="text-dim text-sm mb-2">{$t("welcome_step2_desc")}</p>
				
				<div class="map-container" on:mouseleave={onMouseUp} on:mouseup={onMouseUp} role="presentation">
					<!-- svelte-ignore a11y-no-static-element-interactions -->
					<svg 
						viewBox="{vbX} {vbY} {vbW} {vbH}" 
						class="wizard-canvas"
						on:mousemove={onPanMove}
						on:mousedown={onPanStart}
						on:wheel|preventDefault={onWheel}
					>
						<defs>
							<pattern id="grid-wiz" width="40" height="40" patternUnits="userSpaceOnUse">
								<path d="M 40 0 L 0 0 0 40" fill="none" stroke="var(--map-grid-stroke)" stroke-width="1"/>
							</pattern>
						</defs>
						<rect width="100%" height="100%" fill="url(#grid-wiz)"/>

						{#each layout.tables as table}
							{@const cx = table.x + table.w / 2}
							{@const cy = table.y + table.h / 2}
							<g transform="rotate({table.rotation || 0}, {cx}, {cy})">
								<rect x={table.x} y={table.y} width={table.w} height={table.h} rx="8" fill="var(--map-table-fill)" stroke="var(--map-table-stroke)"/>
								<text x={cx} y={cy + 5} text-anchor="middle" fill="var(--text-dim)" font-size="14" font-weight="bold">{table.label}</text>
							</g>
						{/each}

						{#each layout.furniture as furn}
							{@const fcx = furn.x + furn.w / 2}
							{@const fcy = furn.y + furn.h / 2}
							<g transform="rotate({furn.rotation || 0}, {fcx}, {fcy})">
								<rect x={furn.x} y={furn.y} width={furn.w} height={furn.h} rx="6" fill="var(--map-table-fill)" stroke="var(--map-table-stroke)"/>
								<text x={fcx} y={fcy - 2} text-anchor="middle" font-size="16" style="pointer-events:none">{furn.icon}</text>
								<text x={fcx} y={fcy + 12} text-anchor="middle" fill="var(--text-dim)" font-size="10">{furn.label}</text>
							</g>
						{/each}

						{#each layout.seats as seat}
							{@const occupant = getOccupant(seat.id)}
							{@const isMine = selectedSeat === seat.id}
							{@const isOccupied = !!occupant}
							{@const isTeammate = !isMine && isOccupied && user?.team_name && occupant.team_name === user.team_name}
							{@const scx = seat.x + SEAT_SIZE / 2}
							{@const scy = seat.y + SEAT_SIZE / 2}
							<!-- svelte-ignore a11y-no-static-element-interactions -->
							<g 
								transform="rotate({seat.rotation || 0}, {scx}, {scy})"
								on:click={() => {
									if (panMoved || isOccupied) return;
									claimSeat(seat.id);
								}}
								style="cursor: {isOccupied && !isMine ? 'not-allowed' : 'pointer'}"
							>
								<rect x={seat.x} y={seat.y} width={SEAT_SIZE} height={SEAT_SIZE} rx="8" 
									fill={isMine ? 'var(--map-seat-mine-fill)' : isTeammate ? 'var(--map-seat-teammate-fill)' : isOccupied ? 'var(--map-seat-occupied-fill)' : 'var(--map-seat-drop-fill)'} 
									stroke={isMine ? 'var(--accent)' : isTeammate ? 'var(--map-seat-teammate-stroke)' : isOccupied ? 'var(--map-seat-occupied-stroke)' : 'var(--map-seat-drop-stroke)'}
									stroke-width={isMine || isTeammate ? "2" : "1"}
								/>
								<text x={scx} y={seat.y + 13} text-anchor="middle" fill={isMine ? "var(--map-seat-player-fill)" : "var(--text-dim)"} font-size="10" font-weight="bold">{seat.id}</text>
								{#if occupant}
									<text x={scx} y={seat.y + 28} text-anchor="middle" fill="var(--map-seat-player-fill)" font-size="10" font-weight="bold"
										textLength={occupant.username.length > 6 ? 44 : null}
										lengthAdjust="spacingAndGlyphs"
									>{occupant.username}</text>
									{#if occupant.team_name}
										<text x={scx} y={seat.y + 39} text-anchor="middle" fill="var(--accent)" font-size="7" opacity="0.8"
											textLength={occupant.team_name.length > 8 ? 42 : null}
											lengthAdjust="spacingAndGlyphs"
										>{occupant.team_name}</text>
									{/if}
								{:else}
									<text x={scx} y={seat.y + 32} text-anchor="middle" fill="var(--map-seat-drop-stroke)" font-size="10" font-weight="bold">{$t("welcome_seat_free")}</text>
								{/if}
							</g>
						{/each}
					</svg>
				</div>

				<div class="wizard-actions">
					<button class="btn-link" on:click={skipSeat}>{$t("welcome_btn_skip_step")}</button>
					<button class="btn-primary" on:click={skipSeat}>{$t("welcome_seat_btn_continue")}</button>
				</div>
			</div>

		{:else if step === 3}
			<div class="step-panel tutorial-panel" style="text-align: center;">
				<h2 style="font-size: 2rem; margin-bottom: 1rem;">{$t("welcome_step3_title")} 🚀</h2>
				<p class="text-dim mb-6" style="font-size: 1.1rem;">
					{$t("welcome_step3_desc")}
				</p>
				
				<div class="wizard-actions mt-6" style="justify-content: center;">
					<button class="btn-primary btn-large" style="max-width: 300px;" on:click={finishWizard}>
						{$t("welcome_btn_guided")} 🔦
					</button>
				</div>
				<div style="margin-top: 1rem;">
					<button class="btn-link text-dim" on:click={() => goto('/dashboard')}>
						{$t("welcome_btn_skip")}
					</button>
				</div>
			</div>
		{/if}
	</div>
</div>

<style>
	.welcome-wizard { display: flex; flex-direction: column; align-items: center; justify-content: center; min-height: 80vh; padding: 2rem; }
	.wizard-header { text-align: center; margin-bottom: 2rem; }
	.steps-indicator { display: flex; align-items: center; justify-content: center; gap: 0.5rem; margin-top: 1rem; }
	.step-dot { width: 32px; height: 32px; border-radius: 50%; background: var(--bg-tertiary); color: var(--text-dim); display: flex; align-items: center; justify-content: center; font-weight: 800; border: 2px solid var(--glass-border); transition: all 0.3s; }
	.step-dot.active { background: var(--accent); color: white; border-color: var(--accent-soft); box-shadow: 0 0 10px var(--accent-glow); }
	.step-line { width: 50px; height: 4px; background: var(--glass-border); border-radius: 2px; transition: all 0.3s; }
	.step-line.active { background: var(--accent); }

	.wizard-content { width: 100%; max-width: 600px; padding: 2.5rem; border-radius: 16px; transition: max-width 0.3s ease; }
	.wizard-content.wide { max-width: 900px; }
	
	.step-panel h2 { margin-bottom: 0.5rem; font-size: 1.5rem; font-weight: 800; }
	.input-lg { width: 100%; padding: 1rem; background: var(--input-bg); border: 1px solid var(--glass-border); border-radius: 8px; color: var(--input-color); font-size: 1.1rem; margin-bottom: 1.5rem; }
	.input-lg:focus { outline: none; border-color: var(--accent); box-shadow: 0 0 0 3px var(--accent-soft); }
	
	.existing-teams-wrap { margin-bottom: 1.5rem; display: flex; flex-direction: column; gap: 0.5rem; }
	.existing-teams-label { font-size: 0.8rem; color: var(--text-dim); }
	.existing-teams-list { display: flex; flex-wrap: wrap; gap: 0.5rem; }
	.btn-team-select {
		padding: 0.4rem 0.8rem; font-size: 0.8rem; border-radius: 20px;
		border: 1px solid var(--glass-border); background: var(--surface-raised);
		color: var(--text-dim); cursor: pointer; transition: all 0.2s; display: inline-flex; align-items: center; gap: 0.3rem;
	}
	.btn-team-select:hover { border-color: var(--accent); color: var(--text-main); }
	.btn-team-select.active { background: var(--accent); border-color: var(--accent); color: white; }

	.wizard-actions { display: flex; justify-content: space-between; align-items: center; margin-top: 1.5rem; }
	.btn-large { padding: 1rem 2rem; font-size: 1.1rem; width: 100%; }

	.btn-link {
		background: transparent;
		border: 1px solid transparent;
		color: var(--text-dim);
		padding: 0.55rem 1.2rem;
		font-size: 0.9rem;
		font-weight: 600;
		border-radius: 8px;
		cursor: pointer;
		transition: all 0.2s;
	}
	.btn-link:hover {
		color: var(--text-main);
		background: var(--hover-tint);
		border-color: var(--glass-border);
	}

	/* Map step */
	.step-map { width: 100%; }
	.map-container { height: 450px; border-radius: 12px; background: var(--map-canvas-bg); border: 1px solid var(--glass-border); overflow: hidden; position: relative; cursor: grab; }
	.map-container:active { cursor: grabbing; }
	.wizard-canvas { width: 100%; height: 100%; user-select: none; }

	/* Tutorial step removed static grid styles */

	@media (min-width: 768px) {
		.wizard-content { padding: 3rem; }
	}
</style>
