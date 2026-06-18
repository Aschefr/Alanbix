<script>
	import { onMount } from 'svelte';
	import { api } from '$lib/api';
	import { t, initI18n } from '$lib/i18nStore';

	let layout = { seats: [] };
	let user = null;
	let selectedSeat = null;

	onMount(async () => {
		await initI18n();
		const res = await api.get('/room/layout');
		layout = res.layout || { seats: [] };
		user = await api.get('/me');
		selectedSeat = user.seat_id;
	});

	async function selectSeat(id) {
		try {
			await api.post('/room/assign-seat', { seat_id: id });
			selectedSeat = id;
		} catch (e) {
			alert(e.message);
		}
	}

	// Mock seats if layout is empty
	$: displaySeats = layout.seats.length > 0 ? layout.seats : Array.from({length: 48}, (_, i) => ({
		id: `S${i+1}`,
		x: (i % 8) * 60 + 50,
		y: Math.floor(i / 8) * 60 + 50,
		occupied: false
	}));
</script>

<div class="map-view">
	<header>
		<h1>{$t('map_public_title')}</h1>
		<p class="text-dim">{$t('map_public_subtitle')}</p>
	</header>

	<div class="map-container glass">
		<svg width="600" height="450" viewBox="0 0 600 450">
			{#each displaySeats as seat}
				<g 
					class="seat {selectedSeat === seat.id ? 'selected' : ''}" 
					on:click={() => selectSeat(seat.id)}
				>
					<rect 
						x={seat.x} 
						y={seat.y} 
						width="40" 
						height="40" 
						rx="4"
					/>
					<text x={seat.x + 20} y={seat.y + 25} text-anchor="middle" class="seat-id">
						{seat.id}
					</text>
				</g>
			{/each}
		</svg>
	</div>

	<div class="legend">
		<div class="item"><span class="box selected"></span> {$t('map_legend_yourseat')}</div>
		<div class="item"><span class="box free"></span> {$t('map_legend_free')}</div>
		<div class="item"><span class="box occupied"></span> {$t('map_legend_occupied')}</div>
	</div>
</div>

<style>
	.map-view {
		display: flex;
		flex-direction: column;
		align-items: center;
		gap: 2rem;
	}

	header {
		text-align: center;
	}

	.map-container {
		padding: 2rem;
		overflow: auto;
		max-width: 100%;
	}

	svg {
		background: rgba(15, 23, 42, 0.3);
		border-radius: 8px;
	}

	.seat {
		cursor: pointer;
		transition: transform 0.1s;
	}

	.seat:hover {
		transform: scale(1.05);
	}

	.seat rect {
		fill: var(--bg-secondary);
		stroke: rgba(255, 255, 255, 0.1);
		stroke-width: 1;
	}

	.seat.selected rect {
		fill: var(--accent);
		stroke: var(--accent-glow);
		stroke-width: 2;
	}

	.seat-id {
		fill: var(--text-dim);
		font-size: 10px;
		font-weight: 700;
		pointer-events: none;
	}

	.seat.selected .seat-id {
		fill: white;
	}

	.legend {
		display: flex;
		gap: 2rem;
		font-size: 0.8rem;
		color: var(--text-dim);
	}

	.legend .item {
		display: flex;
		align-items: center;
		gap: 0.5rem;
	}

	.box {
		width: 12px;
		height: 12px;
		border-radius: 2px;
		display: inline-block;
	}

	.box.selected { background: var(--accent); }
	.box.free { background: var(--bg-secondary); border: 1px solid rgba(255, 255, 255, 0.1); }
	.box.occupied { background: var(--danger); opacity: 0.5; }
</style>
