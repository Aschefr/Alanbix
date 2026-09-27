<script>
	import { t } from '$lib/i18nStore';

	export let roomLayout = { seats: [], tables: [], furniture: [] };
	export let allUsers = [];
	export let user = null;
	export let hoveredSeatId = null;
	export let activePulsingSeats = {};
	export let activeBeams = [];
	export let isDraggingSplitter = false;
	export let chatSplitRatio = 55;

	function getOccupant(seatId) {
		return (allUsers || []).find(u => u.seat_id === seatId);
	}

	$: occupiedSeats = (roomLayout?.seats || []).filter(s => getOccupant(s.id)).length;
	$: totalSeats = (roomLayout?.seats || []).length;

	// Pan/Zoom for map preview
	let mapVb = { x: 0, y: 0, w: 900, h: 600 };
	let mapVbInit = false;
	let mapPan = null;

	$: if (!mapVbInit && roomLayout && (roomLayout.seats?.length > 0 || roomLayout.tables?.length > 0)) {
		const items = [
			...(roomLayout.seats || []).map(s => ({ x: s.x, y: s.y, w: 50, h: 50 })),
			...(roomLayout.tables || []).map(t => ({ x: t.x, y: t.y, w: t.w, h: t.h })),
			...(roomLayout.furniture || []).map(f => ({ x: f.x, y: f.y, w: f.w, h: f.h }))
		];
		if (items.length > 0) {
			const pad = 40;
			mapVb = {
				x: Math.min(...items.map(i => i.x)) - pad,
				y: Math.min(...items.map(i => i.y)) - pad,
				w: Math.max(...items.map(i => i.x + i.w)) + pad - (Math.min(...items.map(i => i.x)) - pad),
				h: Math.max(...items.map(i => i.y + i.h)) + pad - (Math.min(...items.map(i => i.y)) - pad)
			};
			mapVbInit = true;
		}
	}

	function mapWheel(e) {
		e.preventDefault();
		const svg = e.currentTarget;
		const rect = svg.getBoundingClientRect();
		const mx = (e.clientX - rect.left) / rect.width;
		const my = (e.clientY - rect.top) / rect.height;
		const factor = e.deltaY > 0 ? 1.15 : 0.87;
		const nw = mapVb.w * factor, nh = mapVb.h * factor;
		mapVb.x += (mapVb.w - nw) * mx;
		mapVb.y += (mapVb.h - nh) * my;
		mapVb.w = nw; mapVb.h = nh;
	}

	function mapDown(e) {
		if (e.button === 0) {
			mapPan = { x: e.clientX, y: e.clientY, vx: mapVb.x, vy: mapVb.y };
		}
	}

	function mapMove(e) {
		if (!mapPan) return;
		const svg = e.currentTarget;
		const r = svg.getBoundingClientRect();
		const sx = mapVb.w / r.width, sy = mapVb.h / r.height;
		mapVb.x = mapPan.vx - (e.clientX - mapPan.x) * sx;
		mapVb.y = mapPan.vy - (e.clientY - mapPan.y) * sy;
	}

	function mapUp() {
		mapPan = null;
	}
</script>

<section class="panel map-panel glass" class:no-transition={isDraggingSplitter} style="height: calc({100 - chatSplitRatio}% - 14px);">
	<div class="panel-header">
		<div>
			<h2>{$t('dash_map_title')}</h2>
			<span class="subtitle">{$t('dash_map_subtitle')}</span>
		</div>
		<div class="flex-row gap-2">
			<a href="/dashboard/map" class="btn-chip">{$t('dash_map_open')}</a>
		</div>
	</div>
	<div class="map-preview-canvas">
		<!-- svelte-ignore a11y-no-static-element-interactions -->
		<svg viewBox="{mapVb.x} {mapVb.y} {mapVb.w} {mapVb.h}" class="mini-map"
			on:wheel={mapWheel}
			on:mousedown={mapDown}
			on:mousemove={mapMove}
			on:mouseup={mapUp}
			on:mouseleave={mapUp}
			style="cursor: {mapPan ? 'grabbing' : 'grab'}"
		>
			<defs>
				<pattern id="dash-grid" width="40" height="40" patternUnits="userSpaceOnUse">
					<path d="M 40 0 L 0 0 0 40" fill="none" stroke="var(--map-grid-stroke)" stroke-width="1"/>
				</pattern>
				<filter id="neon-glow" x="-50%" y="-50%" width="200%" height="200%">
					<feGaussianBlur in="SourceGraphic" stdDeviation="3" result="blur1" />
					<feGaussianBlur in="SourceGraphic" stdDeviation="6" result="blur2" />
					<feMerge>
						<feMergeNode in="blur2" />
						<feMergeNode in="blur1" />
						<feMergeNode in="SourceGraphic" />
					</feMerge>
				</filter>
				<linearGradient id="bubble-grad" x1="0%" y1="0%" x2="100%" y2="100%">
					<stop offset="0%" stop-color="#38bdf8" />
					<stop offset="50%" stop-color="#6366f1" />
					<stop offset="100%" stop-color="#a855f7" />
				</linearGradient>
			</defs>
			<rect width="100%" height="100%" fill="url(#dash-grid)"/>

			{#each (roomLayout?.tables || []) as table}
				{@const cx = table.x + table.w / 2}
				{@const cy = table.y + table.h / 2}
				<g transform="rotate({table.rotation || 0}, {cx}, {cy})">
					<rect x={table.x} y={table.y} width={table.w} height={table.h} rx="6"
						fill="var(--map-table-fill)" stroke="var(--map-table-stroke)" stroke-width="1.5"/>
					<text x={cx} y={cy + 4} text-anchor="middle" fill="var(--text-muted)" font-size="10" font-weight="700">{table.label}</text>
				</g>
			{/each}

			{#each (roomLayout?.furniture || []) as furn}
				{@const fcx = furn.x + furn.w / 2}
				{@const fcy = furn.y + furn.h / 2}
				<g transform="rotate({furn.rotation || 0}, {fcx}, {fcy})">
					<rect x={furn.x} y={furn.y} width={furn.w} height={furn.h} rx="4"
						fill="rgba(245,158,11,0.1)" stroke="rgba(245,158,11,0.4)" stroke-width="1.5" stroke-dasharray="4 2"/>
					<foreignObject x={furn.x} y={furn.y} width={furn.w} height={furn.h} style="pointer-events:none">
						<div style="display:flex;flex-direction:column;align-items:center;justify-content:center;width:100%;height:100%;line-height:1.1;">
							<span style="font-size: {furn.h <= 40 ? '18px' : '26px'};">{furn.icon}</span>
							<span style="font-size: {furn.h <= 40 ? '10px' : '12px'};font-weight:700;color:#f59e0b;margin-top:2px;text-align:center;word-break:break-all;padding:0 4px;">{furn.label}</span>
						</div>
					</foreignObject>
				</g>
			{/each}

			{#each (roomLayout?.seats || []) as seat}
				{@const occ = getOccupant(seat.id)}
				{@const isMine = occ && user && occ.id === user.id}
				{@const isTeammate = occ && !isMine && user?.team_name && occ.team_name === user.team_name}
				{@const isPulsing = activePulsingSeats[seat.id]}
				{@const isHovered = hoveredSeatId === seat.id}
				{@const scx = seat.x + 25}
				{@const scy = seat.y + 25}
				<g transform="rotate({seat.rotation || 0}, {scx}, {scy})" class="seat-node {isPulsing ? 'pulse-active' : ''} {isHovered ? 'hover-active' : ''}">
					<rect x={seat.x} y={seat.y} width="50" height="50" rx="6"
						fill={isPulsing ? 'rgba(56, 189, 248, 0.45)' : isHovered ? 'rgba(168, 85, 247, 0.35)' : isMine ? 'var(--map-seat-mine-fill)' : isTeammate ? 'var(--map-seat-teammate-fill)' : occ ? 'var(--map-seat-mine-fill)' : 'var(--map-seat-fill)'}
						stroke={isPulsing ? '#38bdf8' : isHovered ? '#c084fc' : isMine ? 'var(--accent)' : isTeammate ? 'var(--map-seat-teammate-stroke)' : occ ? 'var(--accent)' : 'var(--map-seat-stroke)'}
						stroke-width={isPulsing || isHovered ? '3' : isTeammate ? '2' : '1.5'}
						filter={isPulsing || isHovered ? 'url(#neon-glow)' : null}
					/>
					<clipPath id="dclip-{seat.id}">
						<rect x={seat.x + 2} y={seat.y} width="46" height="50"/>
					</clipPath>
					<g clip-path="url(#dclip-{seat.id})">
						{#if occ}
							{#if occ.avatar_url}
								<text x={scx} y={seat.y + 9} text-anchor="middle" fill="var(--text-muted)" font-size="5" font-weight="800">{seat.id}</text>
								<clipPath id="davatar-clip-{seat.id}">
									{#if occ.avatar_shape === 'rounded'}
										<rect x={scx - 9} y={seat.y + 11} width="18" height="18" rx="3" ry="3" />
									{:else if occ.avatar_shape === 'square'}
										<rect x={scx - 9} y={seat.y + 11} width="18" height="18" />
									{:else}
										<circle cx={scx} cy={seat.y + 20} r="9" />
									{/if}
								</clipPath>
								<image href={occ.avatar_url} x={scx - 9} y={seat.y + 11} width="18" height="18" clip-path="url(#davatar-clip-{seat.id})" />
								<text x={scx} y={seat.y + 39} text-anchor="middle" fill="var(--map-seat-player-fill)" font-size="6" font-weight="700"
									textLength={occ.username.length > 7 ? 44 : null}
									lengthAdjust="spacingAndGlyphs"
								>{occ.username}</text>
								{#if occ.team_name}
									<text x={scx} y={seat.y + 46} text-anchor="middle" fill="var(--accent)" font-size="4.5" opacity="0.7"
										textLength={occ.team_name.length > 8 ? 42 : null}
										lengthAdjust="spacingAndGlyphs"
									>{occ.team_name}</text>
								{/if}
							{:else}
								<text x={scx} y={seat.y + 13} text-anchor="middle" fill="var(--text-muted)" font-size="6" font-weight="800">{seat.id}</text>
								<text x={scx} y={seat.y + 28} text-anchor="middle" fill="var(--map-seat-player-fill)" font-size="7" font-weight="700"
									textLength={occ.username.length > 7 ? 44 : null}
									lengthAdjust="spacingAndGlyphs"
								>{occ.username}</text>
								{#if occ.team_name}
									<text x={scx} y={seat.y + 38} text-anchor="middle" fill="var(--accent)" font-size="5" opacity="0.7"
										textLength={occ.team_name.length > 8 ? 42 : null}
										lengthAdjust="spacingAndGlyphs"
									>{occ.team_name}</text>
								{/if}
							{/if}
						{:else}
							<text x={scx} y={seat.y + 13} text-anchor="middle" fill="var(--text-muted)" font-size="6" font-weight="800">{seat.id}</text>
							<text x={scx} y={seat.y + 32} text-anchor="middle" fill="var(--text-muted)" font-size="7">{$t('dash_map_legend_free')}</text>
						{/if}
					</g>
				</g>
			{/each}

			<!-- Floating Chat Bubble icon rising from Seat to Top towards Chat -->
			{#each activeBeams as bubble (bubble.id)}
				<g transform="translate({bubble.x}, {bubble.startY})">
					<g
						class="chat-bubble-flyer"
						style="--fly-dist: {bubble.endY - bubble.startY}px;"
					>
						<!-- Chat Bubble Vector -->
						<path
							d="M -11,-9 h 22 a 6,6 0 0 1 6,6 v 8 a 6,6 0 0 1 -6,6 h -13 l -5,5 v -5 a 6,6 0 0 1 -4,-6 v -8 a 6,6 0 0 1 6,-6 z"
							fill="url(#bubble-grad)"
							stroke="#ffffff"
							stroke-width="1.2"
							filter="url(#neon-glow)"
						/>
						<!-- 3 glowing dots inside bubble -->
						<circle cx="-5" cy="-2" r="1.5" fill="#ffffff" />
						<circle cx="0" cy="-2" r="1.5" fill="#ffffff" />
						<circle cx="5" cy="-2" r="1.5" fill="#ffffff" />
					</g>
				</g>
			{/each}
		</svg>
	</div>
	<div class="map-footer">
		<div class="map-legend">
			<span class="lg-item"><span class="lg-dot occupied"></span> {$t('dash_map_legend_occupied')} ({occupiedSeats})</span>
			<span class="lg-item"><span class="lg-dot free"></span> {$t('dash_map_legend_free')} ({totalSeats - occupiedSeats})</span>
			{#if user?.team_name}
				<span class="lg-item"><span class="lg-dot teammate"></span> {$t('map_legend_teammates')}</span>
			{/if}
		</div>
	</div>
</section>

<style>
	.panel {
		display: flex;
		flex-direction: column;
		border-radius: 16px;
		overflow: hidden;
		min-height: 0;
	}
	.panel-header {
		padding: 0.8rem 1.2rem;
		border-bottom: 1px solid var(--glass-border);
		display: flex;
		justify-content: space-between;
		align-items: flex-start;
		flex-shrink: 0;
	}
	.panel-header h2 {
		font-size: 0.85rem;
		font-weight: 800;
		text-transform: uppercase;
		letter-spacing: 0.08em;
	}
	.panel-header .subtitle {
		font-size: 0.65rem;
		color: var(--text-muted);
		text-transform: uppercase;
		letter-spacing: 0.05em;
	}

	.map-panel {
		min-height: 90px;
		min-width: 0;
		display: flex;
		flex-direction: column;
		transition: height 0.1s ease-out;
	}
	.no-transition {
		transition: none !important;
	}

	.map-preview-canvas {
		flex-grow: 1;
		padding: 0.4rem;
		min-height: 0;
	}
	.mini-map {
		width: 100%;
		height: 100%;
		border-radius: 8px;
		background: var(--surface-sunken);
	}
	.map-footer {
		padding: 0.4rem 1rem;
		border-top: 1px solid var(--glass-border);
		flex-shrink: 0;
	}
	.map-legend {
		display: flex;
		gap: 1.5rem;
		justify-content: center;
		font-size: 0.7rem;
		color: var(--text-dim);
	}
	.lg-item {
		display: flex;
		align-items: center;
		gap: 0.4rem;
	}
	.lg-dot {
		width: 10px;
		height: 10px;
		border-radius: 3px;
	}
	.lg-dot.occupied { background: rgba(59, 130, 246, 0.4); border: 1px solid var(--accent); }
	.lg-dot.free { background: var(--map-seat-fill); border: 1px solid var(--map-seat-stroke); }
	.lg-dot.teammate { background: var(--map-seat-teammate-fill); border: 1px solid var(--map-seat-teammate-stroke); }

	.btn-chip {
		display: inline-flex;
		align-items: center;
		gap: 0.4rem;
		padding: 0.35rem 0.8rem;
		background: var(--map-badge-bg);
		border: 1px solid var(--map-badge-border);
		color: var(--accent);
		border-radius: 8px;
		font-size: 0.7rem;
		font-weight: 700;
		text-decoration: none;
		transition: all 0.15s;
		cursor: pointer;
	}
	.btn-chip:hover {
		background: var(--map-badge-hover);
	}

	/* Interactive Seat Highlight & Luminous Orb Animation */
	.seat-node {
		transition: transform 0.25s ease-out, filter 0.25s ease-out;
		transform-box: fill-box;
		transform-origin: center center;
	}
	.seat-node.pulse-active {
		animation: seatQuickHighlight 0.75s ease-out forwards;
	}
	.seat-node.hover-active {
		transform: translateY(-3px);
		filter: drop-shadow(0 0 10px #c084fc);
	}
	@keyframes seatQuickHighlight {
		0% {
			transform: translateY(0);
			filter: drop-shadow(0 0 2px #38bdf8);
		}
		30% {
			transform: translateY(-4px);
			filter: drop-shadow(0 0 14px #38bdf8) drop-shadow(0 0 20px rgba(99, 102, 241, 0.6));
		}
		100% {
			transform: translateY(0);
			filter: drop-shadow(0 0 0px transparent);
		}
	}

	/* Floating Chat Bubble rising toward Chat */
	.chat-bubble-flyer {
		animation: bubblePopAndFly 0.95s cubic-bezier(0.2, 0.8, 0.25, 1) forwards;
		pointer-events: none;
	}
	@keyframes bubblePopAndFly {
		0% {
			transform: translate(0, 0) scale(0.25);
			opacity: 0;
		}
		25% {
			transform: translate(0, -18px) scale(1.15);
			opacity: 1;
		}
		45% {
			transform: translate(0, -24px) scale(1);
			opacity: 1;
		}
		100% {
			transform: translate(0, calc(var(--fly-dist, -250px) - 20px)) scale(0.6);
			opacity: 0;
		}
	}
</style>
