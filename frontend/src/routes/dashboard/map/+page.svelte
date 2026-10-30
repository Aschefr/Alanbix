<script>
	import { t } from '$lib/i18nStore';
	import { get } from 'svelte/store';
	import { onMount, onDestroy } from 'svelte';
	import { api } from '$lib/api';
	import { page } from '$app/stores';
	import { wsMessageStore } from '$lib/ws';

	let layout = { seats: [], tables: [], furniture: [] };

	// AXE-09: Furniture type presets
	const FURNITURE_TYPES = [
		{ type: 'door', icon: '🚪', label: get(t)('map_furniture_door'), w: 80, h: 40 },
		{ type: 'kitchen', icon: '🍳', label: get(t)('map_furniture_kitchen'), w: 160, h: 100 },
		{ type: 'bar', icon: '🍺', label: get(t)('map_furniture_bar'), w: 200, h: 60 },
		{ type: 'wc', icon: '🚻', label: get(t)('map_furniture_wc'), w: 80, h: 80 },
		{ type: 'rack', icon: '🖥️', label: get(t)('map_furniture_rack'), w: 60, h: 80 },
		{ type: 'screen', icon: '📺', label: get(t)('map_furniture_screen'), w: 160, h: 40 },
		{ type: 'generic', icon: '📦', label: get(t)('map_furniture_generic'), w: 100, h: 80 },
	];
	let selectedFurnitureType = 'door';
	let user = null;
	let allUsers = [];
	let editMode = false;
	let selectedSeat = null;
	let draggingUserId = null; // admin drag-drop player badge
	let editingId = null; // seat/table ID being edited
	let editIdValue = '';
	let highlightedSeat = null; // from ?highlight= query param

	let wsUnsub;

	// Interaction state
	let dragging = null;
	let dragType = 'move'; // 'move', 'resize-tl', 'resize-tr', 'resize-bl', 'resize-br', 'rotate'
	let dragStart = { x: 0, y: 0 };
	let dragOriginal = {};

	// Admin assign UI
	let assigningSeatId = null;
	let seatingLocked = false;

	// Pan & Zoom
	let vbX = 0, vbY = 0, vbW = 900, vbH = 600;
	let isPanning = false;
	let panMoved = false;
	let panStart = { x: 0, y: 0 };
	let panVbStart = { x: 0, y: 0 };

	// Toast
	let toasts = [];
	let toastId = 0;

	// Svelte portal action to avoid transform container clipping (G-49 / scroll fix)
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
	function toast(message, type = 'info') {
		const id = ++toastId;
		toasts = [...toasts, { id, message, type, leaving: false }];
		setTimeout(() => {
			toasts = toasts.map(t => t.id === id ? { ...t, leaving: true } : t);
			setTimeout(() => { toasts = toasts.filter(t => t.id !== id); }, 400);
		}, 3000);
	}

	const SNAP_ANGLE = 45;
	const SNAP_DIST = 12;
	const GRID_SIZE = 20; // Half of visible grid (40px) for finer control

	function snapToGrid(val) {
		return Math.round(val / GRID_SIZE) * GRID_SIZE;
	}

	onMount(async () => {
		user = await api.get('/me');
		const res = await api.get('/room/layout');
		layout = res.layout || { seats: [], tables: [], furniture: [] };
		if (!layout.tables) layout.tables = [];
		if (!layout.seats) layout.seats = [];
		if (!layout.furniture) layout.furniture = [];
		// Ensure rotation field exists
		layout.tables.forEach(t => { if (t.rotation === undefined) t.rotation = 0; });
		layout.seats.forEach(s => { if (s.rotation === undefined) s.rotation = 0; });
		layout.furniture.forEach(f => { if (f.rotation === undefined) f.rotation = 0; });
		selectedSeat = user.seat_id;
		await loadUsers();
		try { const lk = await api.get('/room/seating-locked'); seatingLocked = lk.locked; } catch {}
		// Auto-select first table for seat placement
		if (layout.tables.length > 0) targetTableId = layout.tables[0].id;

		// Handle ?highlight=SEAT_ID from bracket seat badges
		const hlParam = $page.url.searchParams.get('highlight');
		if (!hlParam) {
			resetView();
		}
		if (hlParam) {
			const targetSeat = layout.seats.find(s => s.id === hlParam);
			if (targetSeat) {
				// Auto-pan & zoom to the seat
				const cx = targetSeat.x + SEAT_SIZE / 2;
				const cy = targetSeat.y + SEAT_SIZE / 2;
				vbW = 400; vbH = 267;
				vbX = cx - vbW / 2;
				vbY = cy - vbH / 2;
				// Highlight for 5 seconds
				highlightedSeat = hlParam;
				setTimeout(() => { highlightedSeat = null; }, 5000);
			}
		}

		wsUnsub = wsMessageStore.subscribe(msg => {
			if (!msg) return;
			if (msg.type === 'room_updated' || msg.type === 'users_updated') {
				loadUsers();
				api.get('/room/layout').then(res => {
					layout = res.layout || { seats: [], tables: [], furniture: [] };
					if (!layout.tables) layout.tables = [];
					if (!layout.seats) layout.seats = [];
					if (!layout.furniture) layout.furniture = [];
					layout.tables.forEach(t => { if (t.rotation === undefined) t.rotation = 0; });
					layout.seats.forEach(s => { if (s.rotation === undefined) s.rotation = 0; });
					layout.furniture.forEach(f => { if (f.rotation === undefined) f.rotation = 0; });
				}).catch(() => {});
			}
		});

	});

	onDestroy(() => {
		if (wsUnsub) wsUnsub();
	});

	async function loadUsers() {
		allUsers = await api.get('/room/users');
		layout = layout; // trigger reactivity for getOccupant calls
	}

	function getSvgPoint(e) {
		const svg = document.querySelector('.room-canvas');
		const pt = svg.createSVGPoint();
		pt.x = e.clientX; pt.y = e.clientY;
		return pt.matrixTransform(svg.getScreenCTM().inverse());
	}

	// --- Snapping ---
	function snapAngle(angle) {
		return Math.round(angle / SNAP_ANGLE) * SNAP_ANGLE;
	}

	function snapTableEdges(table) {
		const others = layout.tables.filter(t => t.id !== table.id);
		let sx = table.x, sy = table.y;
		for (const o of others) {
			// Right edge → Left edge
			if (Math.abs((table.x + table.w) - o.x) < SNAP_DIST) sx = o.x - table.w;
			// Left edge → Right edge
			if (Math.abs(table.x - (o.x + o.w)) < SNAP_DIST) sx = o.x + o.w;
			// Bottom edge → Top edge
			if (Math.abs((table.y + table.h) - o.y) < SNAP_DIST) sy = o.y - table.h;
			// Top edge → Bottom edge
			if (Math.abs(table.y - (o.y + o.h)) < SNAP_DIST) sy = o.y + o.h;
			// Left align
			if (Math.abs(table.x - o.x) < SNAP_DIST) sx = o.x;
			// Top align
			if (Math.abs(table.y - o.y) < SNAP_DIST) sy = o.y;
		}
		table.x = sx;
		table.y = sy;
	}

	function intersects(r1, r2) {
		return !(r2.x >= r1.x + r1.w ||
		         r2.x + r2.w <= r1.x ||
		         r2.y >= r1.y + r1.h ||
		         r2.y + r2.h <= r1.y);
	}

	function hasCollision(item, x, y, w, h) {
		const r1 = { x, y, w, h };
		const isSeat = item.id && item.id.includes('_S');
		
		if (!isSeat) {
			// Check tables
			if (layout.tables) {
				for (const t of layout.tables) {
					if (t.id !== item.id) {
						if (intersects(r1, { x: t.x, y: t.y, w: t.w, h: t.h })) return true;
					}
				}
			}
			
			// Check furniture
			if (layout.furniture) {
				for (const f of layout.furniture) {
					if (f.id !== item.id) {
						if (intersects(r1, { x: f.x, y: f.y, w: f.w, h: f.h })) return true;
					}
				}
			}
		}
		
		// Check seats
		if (layout.seats) {
			for (const s of layout.seats) {
				if (s.id !== item.id) {
					if (intersects(r1, { x: s.x, y: s.y, w: SEAT_SIZE, h: SEAT_SIZE })) return true;
				}
			}
		}
		
		return false;
	}

	const SEAT_SIZE = 50; // visual seat size
	let targetTableId = ''; // admin selects which table to fill

	// --- Admin Actions ---
	function nextTableNum() {
		let num = 1;
		while (layout.tables.some(t => t.id === 'T' + num)) {
			num++;
		}
		return num;
	}
	function addTable() {
		const n = nextTableNum();
		let x = 120;
		let y = 120;
		const w = 300;
		const h = 140;
		const tempTable = { id: 'T' + n };
		while (hasCollision(tempTable, x, y, w, h)) {
			x += GRID_SIZE;
			y += GRID_SIZE;
		}
		const newTable = { id: 'T' + n, x, y, w, h, label: 'Table ' + n, rotation: 0 };
		layout.tables = [...layout.tables, newTable];
		targetTableId = newTable.id; // auto-select new table
	}

	// AXE-09: Add furniture element
	function nextFurnitureNum() {
		let num = 1;
		while (layout.furniture.some(f => f.id === 'F' + num)) {
			num++;
		}
		return num;
	}
	function addFurniture() {
		const preset = FURNITURE_TYPES.find(t => t.type === selectedFurnitureType) || FURNITURE_TYPES[0];
		const n = nextFurnitureNum();
		let x = 200;
		let y = 200;
		const w = preset.w;
		const h = preset.h;
		const tempFurn = { id: 'F' + n };
		while (hasCollision(tempFurn, x, y, w, h)) {
			x += GRID_SIZE;
			y += GRID_SIZE;
		}
		layout.furniture = [...layout.furniture, {
			id: 'F' + n,
			type: preset.type,
			icon: preset.icon,
			label: preset.label,
			x, y,
			w, h,
			rotation: 0
		}];
	}

	function nextSeatNum(tableId) {
		let num = 1;
		const prefix = tableId + '_S';
		while (layout.seats.some(s => s.id === prefix + num)) {
			num++;
		}
		return num;
	}
	function addSeat() {
		// Use selected table, fallback to first table
		const tId = targetTableId || (layout.tables.length > 0 ? layout.tables[0].id : 'T1');
		const table = layout.tables.find(t => t.id === tId);
		let sx = 200, sy = 200;
		const sn = nextSeatNum(tId);
		
		if (table) {
			const slot = findFirstFreeSlot(table);
			if (slot) {
				const half = SEAT_SIZE / 2;
				const snappedCx = slot.x;
				const snappedCy = slot.y;
				
				// Rotate around table center if table has rotation
				const rot = (table.rotation || 0) * Math.PI / 180;
				if (Math.abs(rot) > 0.01) {
					const tcx = table.x + table.w / 2;
					const tcy = table.y + table.h / 2;
					const dx = snappedCx - tcx;
					const dy = snappedCy - tcy;
					sx = tcx + dx * Math.cos(rot) - dy * Math.sin(rot) - half;
					sy = tcy + dx * Math.sin(rot) + dy * Math.cos(rot) - half;
				} else {
					sx = snappedCx - half;
					sy = snappedCy - half;
				}
			}
		}
		// If ID already exists, find a unique suffix
		let seatId = tId + '_S' + sn;
		let counter = 1;
		while (layout.seats.some(s => s.id === seatId)) {
			seatId = tId + '_S' + sn + '_' + counter;
			counter++;
		}
		
		const tempSeat = { id: seatId };
		while (hasCollision(tempSeat, sx, sy, SEAT_SIZE, SEAT_SIZE)) {
			sx += GRID_SIZE;
			sy += GRID_SIZE;
		}
		
		layout.seats = [...layout.seats, { id: seatId, x: sx, y: sy, rotation: table ? (table.rotation || 0) : 0 }];
	}

	function tryRenameId(item, type, newId) {
		newId = newId.trim().toUpperCase();
		if (!newId) return false;
		const allIds = [...layout.tables.map(t=>t.id), ...layout.seats.map(s=>s.id)];
		const existing = allIds.find(i => i === newId && i !== item.id);
		if (existing) {
			// Permutation: swap IDs
			const other = [...layout.tables, ...layout.seats].find(x => x.id === newId);
			if (other) { other.id = item.id; }
		}
		item.id = newId;
		layout = layout;
		return true;
	}
	async function removeItem(type, id) {
		if (type === 'table') {
			const table = layout.tables.find(t => t.id === id);
			if (table) {
				table.delete_pending = true;
				layout = layout;
			}
			return;
		}
		if (type === 'furniture') layout.furniture = layout.furniture.filter(f => f.id !== id);
		if (type === 'seat') {
			// Unassign player if seated here
			const occupant = getOccupant(id);
			if (occupant) {
				try { await api.post('/room/admin-unassign-seat', { seat_id: id }); } catch {}
				await loadUsers();
			}
			layout.seats = layout.seats.filter(s => s.id !== id);
		}
		layout = layout;
	}

	async function confirmDeleteTable(id) {
		// Find all seats associated with this table
		const seatsToRemove = layout.seats.filter(s => s.id.startsWith(id + '_'));
		// Unassign players for those seats
		for (const s of seatsToRemove) {
			const occupant = getOccupant(s.id);
			if (occupant) {
				try { await api.post('/room/admin-unassign-seat', { seat_id: s.id }); } catch {}
			}
		}
		
		// Filter out seats and the table
		layout.seats = layout.seats.filter(s => !s.id.startsWith(id + '_'));
		layout.tables = layout.tables.filter(t => t.id !== id);
		
		layout = layout;
		await loadUsers();
	}

	function addSeatToTable(tableId) {
		targetTableId = tableId;
		addSeat();
	}
	function findFirstFreeSlot(table) {
		const PAD = 10;
		const half = SEAT_SIZE / 2;
		const step = GRID_SIZE * Math.ceil(SEAT_SIZE / GRID_SIZE);
		const cols = Math.max(1, Math.floor((table.w - PAD * 2) / step));
		const existingOnTable = layout.seats.filter(s => s.id.startsWith(table.id + '_'));
		
		let slotIdx = 0;
		while (true) {
			const col = slotIdx % cols;
			const row = Math.floor(slotIdx / cols);
			
			const localCx = PAD + half + col * step;
			const localCy = PAD + half + row * step;
			
			// If it overflows the table footprint height, it is full
			if (localCy + half > table.h - PAD) {
				return null;
			}
			
			const snappedCx = snapToGrid(table.x + localCx);
			const snappedCy = snapToGrid(table.y + localCy);
			
			// Check if any existing seat occupies this position
			const targetX = snappedCx - half;
			const targetY = snappedCy - half;
			const occupied = existingOnTable.some(s => {
				return Math.abs(s.x - targetX) < 5 && Math.abs(s.y - targetY) < 5;
			});
			
			if (!occupied) {
				return { slotIdx, x: snappedCx, y: snappedCy };
			}
			
			slotIdx++;
			if (slotIdx > 200) return null;
		}
	}

	function getNextSeatPos(table) {
		const slot = findFirstFreeSlot(table);
		if (!slot) return null;
		return { x: slot.x, y: slot.y };
	}

	async function saveLayout() {
		await api.post('/room/layout', layout);
		toast($t('map_save_success'), 'success');
	}

	// --- Drag handlers ---
	let dragChildSeats = []; // original positions of child seats for table move

	function startDragTable(e, table, type = 'move') {
		if (!editMode) return;
		e.preventDefault();
		e.stopPropagation();
		const p = getSvgPoint(e);
		dragging = table;
		dragType = type;
		dragStart = { x: p.x, y: p.y };
		dragOriginal = { x: table.x, y: table.y, w: table.w, h: table.h, rotation: table.rotation || 0 };
		// Capture child seats' original positions for coordinated move or rotation
		if (type === 'move' || type === 'rotate') {
			dragChildSeats = layout.seats
				.filter(s => s.id.startsWith(table.id + '_'))
				.map(s => ({ ref: s, origX: s.x, origY: s.y, origRotation: s.rotation || 0 }));
		} else {
			dragChildSeats = [];
		}
	}
	function startDragSeat(e, seat, type = 'move-seat') {
		if (!editMode) return;
		e.preventDefault();
		e.stopPropagation();
		const p = getSvgPoint(e);
		dragging = seat;
		dragType = type;
		dragStart = { x: p.x, y: p.y };
		dragOriginal = { x: seat.x, y: seat.y, rotation: seat.rotation || 0 };
	}

	function onMouseMove(e) {
		if (!dragging) return;
		const p = getSvgPoint(e);
		const dx = p.x - dragStart.x;
		const dy = p.y - dragStart.y;

		if (dragType === 'move') {
			dragging.x = snapToGrid(dragOriginal.x + dx);
			dragging.y = snapToGrid(dragOriginal.y + dy);
			snapTableEdges(dragging);
			// Move child seats by same delta
			const actualDx = dragging.x - dragOriginal.x;
			const actualDy = dragging.y - dragOriginal.y;
			for (const cs of dragChildSeats) {
				cs.ref.x = cs.origX + actualDx;
				cs.ref.y = cs.origY + actualDy;
			}
		} else if (dragType === 'move-seat') {
			// Snap center of seat to grid, then offset for top-left rendering
			const half = SEAT_SIZE / 2;
			const cx = snapToGrid(dragOriginal.x + half + dx) - half;
			const cy = snapToGrid(dragOriginal.y + half + dy) - half;
			dragging.x = cx;
			dragging.y = cy;
		} else if (dragType.startsWith('resize')) {
			const minW = 60, minH = 40;
			if (dragType === 'resize-br') {
				dragging.w = Math.max(minW, snapToGrid(dragOriginal.w + dx));
				dragging.h = Math.max(minH, snapToGrid(dragOriginal.h + dy));
			} else if (dragType === 'resize-bl') {
				dragging.x = snapToGrid(dragOriginal.x + dx);
				dragging.w = Math.max(minW, snapToGrid(dragOriginal.w - dx));
				dragging.h = Math.max(minH, snapToGrid(dragOriginal.h + dy));
			} else if (dragType === 'resize-tr') {
				dragging.w = Math.max(minW, snapToGrid(dragOriginal.w + dx));
				dragging.y = snapToGrid(dragOriginal.y + dy);
				dragging.h = Math.max(minH, snapToGrid(dragOriginal.h - dy));
			} else if (dragType === 'resize-tl') {
				dragging.x = snapToGrid(dragOriginal.x + dx);
				dragging.y = snapToGrid(dragOriginal.y + dy);
				dragging.w = Math.max(minW, snapToGrid(dragOriginal.w - dx));
				dragging.h = Math.max(minH, snapToGrid(dragOriginal.h - dy));
			}
		} else if (dragType === 'rotate') {
			const cx = dragOriginal.x + dragOriginal.w / 2;
			const cy = dragOriginal.y + dragOriginal.h / 2;
			const angle = Math.atan2(p.y - cy, p.x - cx) * (180 / Math.PI);
			dragging.rotation = snapAngle(angle + 90);

			// Rotate child seats around the table center
			const deltaRot = dragging.rotation - dragOriginal.rotation;
			const rad = deltaRot * Math.PI / 180;
			const half = SEAT_SIZE / 2;
			for (const cs of dragChildSeats) {
				const dx = (cs.origX + half) - cx;
				const dy = (cs.origY + half) - cy;
				const rx = dx * Math.cos(rad) - dy * Math.sin(rad);
				const ry = dx * Math.sin(rad) + dy * Math.cos(rad);
				cs.ref.x = cx + rx - half;
				cs.ref.y = cy + ry - half;
				cs.ref.rotation = snapAngle(cs.origRotation + deltaRot);
			}
		} else if (dragType === 'rotate-seat') {
			const cx = dragOriginal.x + 25;
			const cy = dragOriginal.y + 25;
			const angle = Math.atan2(p.y - cy, p.x - cx) * (180 / Math.PI);
			dragging.rotation = snapAngle(angle + 90);
		}
		layout = layout;
	}

	function onMouseUp(e) {
		if (isPanning) { isPanning = false; return; }
		dragging = null;
	}

	// --- Pan & Zoom ---
	function onWheel(e) {
		e.preventDefault();
		const svg = document.querySelector('.room-canvas');
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
		// Edit mode: middle/right click only (left is for dragging items)
		// View mode: any button can pan
		if (editMode && e.button !== 1 && e.button !== 2) return;
		if (!editMode && e.button === 0) {
			// Left click in view mode — start pan but track for click detection
			isPanning = true;
			panStart = { x: e.clientX, y: e.clientY };
			panVbStart = { x: vbX, y: vbY };
			panMoved = false;
			return;
		}
		e.preventDefault();
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
		const svg = document.querySelector('.room-canvas');
		const ctm = svg.getScreenCTM();
		const dx = rawDx / ctm.a;
		const dy = rawDy / ctm.d;
		vbX = panVbStart.x - dx;
		vbY = panVbStart.y - dy;
	}
	// Touch pan & pinch-zoom state
	let touchInitialDist = 0;
	let touchInitialVbW = 0;
	let touchInitialVbH = 0;
	let touchInitialVbX = 0;
	let touchInitialVbY = 0;
	let touchInitialCenter = { x: 0, y: 0 };
	let activeSeatCard = null; // { seat, occupant, isMine, isOccupied }

	function getTouchDist(t1, t2) {
		const dx = t1.clientX - t2.clientX;
		const dy = t1.clientY - t2.clientY;
		return Math.sqrt(dx * dx + dy * dy);
	}

	function onTouchStart(e) {
		if (editMode) return;
		if (e.touches.length === 1) {
			isPanning = true;
			panMoved = false;
			panStart = { x: e.touches[0].clientX, y: e.touches[0].clientY };
			panVbStart = { x: vbX, y: vbY };
		} else if (e.touches.length === 2) {
			isPanning = false;
			panMoved = true;
			touchInitialDist = getTouchDist(e.touches[0], e.touches[1]);
			touchInitialVbW = vbW;
			touchInitialVbH = vbH;
			touchInitialVbX = vbX;
			touchInitialVbY = vbY;
			const midX = (e.touches[0].clientX + e.touches[1].clientX) / 2;
			const midY = (e.touches[0].clientY + e.touches[1].clientY) / 2;
			const svg = document.querySelector('.room-canvas');
			if (svg) {
				const pt = svg.createSVGPoint();
				pt.x = midX; pt.y = midY;
				const svgPt = pt.matrixTransform(svg.getScreenCTM().inverse());
				touchInitialCenter = { x: svgPt.x, y: svgPt.y };
			}
		}
	}

	function onTouchMove(e) {
		if (editMode) return;
		if (e.touches.length === 1 && isPanning) {
			const rawDx = e.touches[0].clientX - panStart.x;
			const rawDy = e.touches[0].clientY - panStart.y;
			if (Math.abs(rawDx) > 4 || Math.abs(rawDy) > 4) panMoved = true;
			const svg = document.querySelector('.room-canvas');
			if (svg) {
				const ctm = svg.getScreenCTM();
				const dx = rawDx / ctm.a;
				const dy = rawDy / ctm.d;
				vbX = panVbStart.x - dx;
				vbY = panVbStart.y - dy;
			}
			e.preventDefault();
		} else if (e.touches.length === 2 && touchInitialDist > 0) {
			panMoved = true;
			const currentDist = getTouchDist(e.touches[0], e.touches[1]);
			const factor = touchInitialDist / Math.max(currentDist, 10);
			const newW = Math.max(200, Math.min(3000, touchInitialVbW * factor));
			const newH = Math.max(133, Math.min(2000, touchInitialVbH * factor));
			const ratio = newW / touchInitialVbW;
			vbX = touchInitialCenter.x - (touchInitialCenter.x - touchInitialVbX) * ratio;
			vbY = touchInitialCenter.y - (touchInitialCenter.y - touchInitialVbY) * ratio;
			vbW = newW;
			vbH = newH;
			e.preventDefault();
		}
	}

	function onTouchEnd(e) {
		if (e.touches.length === 0) {
			isPanning = false;
			touchInitialDist = 0;
		} else if (e.touches.length === 1) {
			touchInitialDist = 0;
			isPanning = true;
			panStart = { x: e.touches[0].clientX, y: e.touches[0].clientY };
			panVbStart = { x: vbX, y: vbY };
		}
	}

	function centerOnMySeat() {
		const targetSeatId = selectedSeat || user?.seat_id;
		if (!targetSeatId) {
			toast(get(t)('map_toast_no_seat'), "info");
			return;
		}
		const mySeat = layout.seats.find(s => s.id === targetSeatId);
		if (!mySeat) return;
		const cx = mySeat.x + SEAT_SIZE / 2;
		const cy = mySeat.y + SEAT_SIZE / 2;
		vbW = 450;
		vbH = 300;
		vbX = cx - vbW / 2;
		vbY = cy - vbH / 2;
		highlightedSeat = targetSeatId;
		setTimeout(() => { if (highlightedSeat === targetSeatId) highlightedSeat = null; }, 4000);
	}

	function selectSeatInfo(seat) {
		const occupant = getOccupant(seat.id);
		const isMine = seat.id === (selectedSeat || user?.seat_id);
		const isOccupied = !!occupant;
		activeSeatCard = { seat, occupant, isMine, isOccupied };
	}

	function resetView() {
		let minX = Infinity, minY = Infinity;
		let maxX = -Infinity, maxY = -Infinity;

		for (const t of layout.tables) {
			minX = Math.min(minX, t.x);
			minY = Math.min(minY, t.y);
			maxX = Math.max(maxX, t.x + t.w);
			maxY = Math.max(maxY, t.y + t.h);
		}

		for (const f of layout.furniture) {
			minX = Math.min(minX, f.x);
			minY = Math.min(minY, f.y);
			maxX = Math.max(maxX, f.x + f.w);
			maxY = Math.max(maxY, f.y + f.h);
		}

		for (const s of layout.seats) {
			minX = Math.min(minX, s.x);
			minY = Math.min(minY, s.y);
			maxX = Math.max(maxX, s.x + SEAT_SIZE);
			maxY = Math.max(maxY, s.y + SEAT_SIZE);
		}

		if (minX === Infinity || minY === Infinity) {
			vbX = 0; vbY = 0; vbW = 900; vbH = 600;
			return;
		}

		const padding = 15;
		const width = (maxX - minX) + padding * 2;
		const height = (maxY - minY) + padding * 2;

		const finalW = Math.max(900, width);
		const finalH = Math.max(600, height);

		const centerX = minX + (maxX - minX) / 2;
		const centerY = minY + (maxY - minY) / 2;

		vbW = finalW;
		vbH = finalH;
		vbX = centerX - finalW / 2;
		vbY = centerY - finalH / 2;
	}

	// --- User seat interactions ---
	function getOccupant(seatId) {
		return allUsers.find(u => u.seat_id === seatId);
	}

	async function claimSeat(seatId) {
		if (editMode) return;
		if (seatingLocked && !user?.is_admin) { toast($t('map_lock_error_admin'), 'error'); return; }
		try {
			await api.post('/room/assign-seat', { seat_id: seatId });
			selectedSeat = seatId;
			await loadUsers();
			toast($t('map_assign_success'), 'success');
		} catch (e) { toast(e.message, 'error'); }
	}

	async function releaseSeat() {
		await api.post('/room/unassign-seat', {});
		selectedSeat = null;
		await loadUsers();
		toast($t('map_release_success'), 'info');
	}

	async function adminAssign(seatId, userId) {
		await api.post('/room/admin-assign-seat', { seat_id: seatId, user_id: userId });
		assigningSeatId = null;
		await loadUsers();
		toast($t('map_assign_success'), 'success');
	}

	async function adminUnassign(seatId) {
		await api.post('/room/admin-unassign-seat', { seat_id: seatId });
		assigningSeatId = null;
		await loadUsers();
		toast($t('map_release_success'), 'info');
	}

	// Admin drag-drop: drop a player badge onto a seat
	async function dropUserOnSeat(seatId) {
		if (!draggingUserId) return;
		await api.post('/room/admin-assign-seat', { seat_id: seatId, user_id: draggingUserId });
		draggingUserId = null;
		await loadUsers();
		toast($t('map_assign_success'), 'success');
	}

	async function toggleSeatingLock() {
		seatingLocked = !seatingLocked;
		try {
			await api.post('/room/seating-locked', { locked: seatingLocked });
			toast(seatingLocked ? $t('map_lock_status_locked') : $t('map_lock_status_unlocked'), 'success');
		} catch (e) { toast(e.message, 'error'); seatingLocked = !seatingLocked; }
	}

	let confirmFreeAll = false;
	async function unassignAll() {
		confirmFreeAll = false;
		try {
			const res = await api.post('/room/admin-unassign-all', {});
			await loadUsers();
			toast($t('map_unassign_confirm', { count: res.count }), 'success');
		} catch (e) { toast(e.message, 'error'); }
	}

	$: unassignedUsers = allUsers.filter(u => !u.seat_id);
</script>

<div class="map-page">
	<header class="flex-row justify-between items-center mb-4">
		<div>
			<h1 class="title-premium"><span class="title-icon">📍</span> {$t("map_title")}</h1>
			<p class="text-dim text-sm">
				{#if editMode}
					{$t('map_edit_instructions')}
				{:else if selectedSeat}
					{@html $t('map_seat_info', { seat: selectedSeat })} 
					<button class="btn-link" on:click={releaseSeat}>{$t('map_seat_free')}</button>
				{:else}
					{seatingLocked && !user?.is_admin ? $t('map_instructions_view_locked') : $t('map_instructions_view_click') + ' ' + $t('map_instructions_view_pan')}
				{/if}
			</p>
		</div>
		{#if user?.is_admin}
			<div class="flex-row gap-2 flex-wrap">
				{#if !editMode}
					<button class="btn-secondary" on:click={() => { editMode = true; assigningSeatId = null; }}>✏️ {$t("map_btn_edit")}</button>
				{/if}
				{#if editMode}
					<button class="btn-secondary" on:click={addTable}>{$t('map_add_table')}</button>
					<select class="table-select" bind:value={targetTableId}>
						{#each layout.tables as t}
							<option value={t.id}>{t.id} — {t.label}</option>
						{/each}
					</select>
					<button class="btn-secondary" on:click={addSeat}>{$t("map_btn_add_seat")}</button>
					<span class="toolbar-sep">|</span>
					<select class="table-select" bind:value={selectedFurnitureType}>
						{#each FURNITURE_TYPES as ft}
							<option value={ft.type}>{ft.icon} {ft.label}</option>
						{/each}
					</select>
					<button class="btn-secondary" on:click={addFurniture}>{$t("map_btn_add_element")}</button>
					<button class="btn-primary" on:click={saveLayout}>{$t("map_btn_save")}</button>
					<button class="btn-secondary" on:click={() => { editMode = false; assigningSeatId = null; }}>{$t("map_btn_close_editor")}</button>
				{/if}
				{#if !editMode}
					<button class="btn-secondary" on:click={toggleSeatingLock}>{seatingLocked ? $t('map_edit_mode_lock_toggle_unlocked') : $t('map_edit_mode_lock_toggle_locked')}</button>
					{#if confirmFreeAll}
						<span class="free-all-confirm">
							<span>{$t('map_free_all_confirm')}</span>
							<button class="btn-danger" on:click={unassignAll}>{$t('map_free_all_yes')}</button>
							<button class="btn-secondary" on:click={() => confirmFreeAll = false}>{$t('common_cancel')}</button>
						</span>
					{:else}
						<button class="btn-outline-danger" on:click={() => confirmFreeAll = true}>{$t("map_btn_free_all")}</button>
					{/if}
				{/if}
				<button class="btn-secondary" on:click={resetView}>{$t("map_btn_recenter")}</button>
			</div>
		{:else}
			<button class="btn-secondary" on:click={resetView}>{$t("map_btn_recenter")}</button>
		{/if}
	</header>

	<!-- Mobile Quick Action Bar (<= 900px) -->
	<div class="map-mobile-bar glass">
		<!-- svelte-ignore a11y-click-events-have-key-events -->
		<!-- svelte-ignore a11y-no-static-element-interactions -->
		<span class="mobile-my-seat" class:none={!selectedSeat} on:click={centerOnMySeat} title={$t('map_btn_center_title')}>
			🪑 {selectedSeat ? $t('map_sheet_seat_prefix', { id: selectedSeat }) : $t('map_mobile_no_seat')}
		</span>
		<div class="map-mobile-btns">
			{#if selectedSeat}
			<button class="map-top-btn" on:click={centerOnMySeat} title={$t('map_btn_center_title')}>
				🎯 {$t('map_btn_center')}
			</button>
			{/if}
			<button class="map-top-btn" on:click={resetView} title={$t('map_btn_global_title')}>
				🔍 {$t('map_btn_global_title')}
			</button>
		</div>
	</div>

	<div class="canvas-wrapper glass" on:contextmenu|preventDefault>
		{#if !editMode && layout.tables.length === 0 && layout.seats.length === 0}
			<div class="map-empty">
				<p class="map-empty-title">{$t('map_empty_title')}</p>
				<p class="text-dim">{user?.is_admin ? $t('map_empty_admin') : $t('map_empty_player')}</p>
				{#if user?.is_admin}
					<button class="btn-primary" on:click={() => { editMode = true; assigningSeatId = null; }}>{$t('map_empty_draw')}</button>
				{/if}
			</div>
		{/if}
		<!-- svelte-ignore a11y-no-static-element-interactions -->
		<svg 
			viewBox="{vbX} {vbY} {vbW} {vbH}" 
			class="room-canvas {editMode ? 'edit-mode' : ''}"
			on:mousemove={(e) => { onPanMove(e); onMouseMove(e); }}
			on:mouseup={onMouseUp}
			on:mouseleave={onMouseUp}
			on:mousedown={onPanStart}
			on:wheel|preventDefault={onWheel}
			on:touchstart={onTouchStart}
			on:touchmove={onTouchMove}
			on:touchend={onTouchEnd}
			on:touchcancel={onTouchEnd}
		>
			<defs>
				<pattern id="grid" width="40" height="40" patternUnits="userSpaceOnUse">
					<path d="M 40 0 L 0 0 0 40" fill="none" stroke="var(--map-grid-stroke)" stroke-width="1"/>
				</pattern>
			</defs>
			<rect width="100%" height="100%" fill="url(#grid)"/>

			<!-- Tables -->
			{#each layout.tables as table (table.id)}
				{@const cx = table.x + table.w / 2}
				{@const cy = table.y + table.h / 2}
				<g transform="rotate({table.rotation || 0}, {cx}, {cy})">
					<!-- Table body -->
					<!-- svelte-ignore a11y-no-static-element-interactions -->
					<rect 
						x={table.x} y={table.y} width={table.w} height={table.h} rx="8"
						class="table-rect {table.delete_pending ? 'delete-pending' : ''}"
						style="cursor: {editMode ? 'grab' : 'default'}"
						on:mousedown={(e) => startDragTable(e, table, 'move')}
					/>

					{#if editMode && table.delete_pending}
						<!-- Inline delete confirmation overlay inside the table -->
						<rect 
							x={table.x + 2} y={table.y + 2} width={table.w - 4} height={table.h - 4} rx="6"
							fill="rgba(239, 68, 68, 0.15)" stroke="var(--danger)" stroke-width="2" stroke-dasharray="4 2"
							style="pointer-events: none;"
						/>
						
						<!-- Confirmation controls just above the table top-right -->
						<text x={table.x + table.w - 65} y={table.y - 10} text-anchor="end" fill="var(--danger)" font-weight="bold" font-size="12">{$t('map_delete_confirm_prompt')}</text>
						
						<!-- Confirm button (check mark) -->
						<!-- svelte-ignore a11y-no-static-element-interactions -->
						<g class="confirm-delete-btn" on:click|stopPropagation={() => confirmDeleteTable(table.id)} style="cursor: pointer;">
							<circle cx={table.x + table.w - 45} cy={table.y - 14} r="10" fill="var(--success)" stroke="white" stroke-width="1"/>
							<text x={table.x + table.w - 45} y={table.y - 10} text-anchor="middle" fill="white" font-size="12" font-weight="bold">✓</text>
						</g>
						
						<!-- Cancel button (cross mark) -->
						<!-- svelte-ignore a11y-no-static-element-interactions -->
						<g class="cancel-delete-btn" on:click|stopPropagation={() => { table.delete_pending = false; layout = layout; }} style="cursor: pointer;">
							<circle cx={table.x + table.w - 20} cy={table.y - 14} r="10" fill="var(--text-muted)" stroke="white" stroke-width="1"/>
							<text x={table.x + table.w - 20} y={table.y - 10} text-anchor="middle" fill="white" font-size="12" font-weight="bold">✕</text>
						</g>
					{:else}
						<text x={cx} y={cy + 5} text-anchor="middle" class="table-label">{table.label}</text>
						{#if editMode}
							{@const nextPos = getNextSeatPos(table)}
							{#if nextPos}
								<!-- Add seat button "+" at the next free seat position -->
								<!-- svelte-ignore a11y-no-static-element-interactions -->
								<g class="add-seat-btn" on:click|stopPropagation={() => addSeatToTable(table.id)} style="cursor: pointer;">
									<!-- A ghost dashed seat footprint -->
									<rect 
										x={nextPos.x - 25} y={nextPos.y - 25} width="50" height="50" rx="8"
										fill="rgba(34, 197, 94, 0.06)" stroke="var(--success)" stroke-width="1.5" stroke-dasharray="3 2"
									/>
									<!-- The "+" indicator in the center of the ghost seat -->
									<circle cx={nextPos.x} cy={nextPos.y} r="8" fill="var(--success)" stroke="white" stroke-width="1"/>
									<text x={nextPos.x} y={nextPos.y + 3} text-anchor="middle" fill="white" font-size="10" font-weight="bold">+</text>
								</g>
							{/if}

							<!-- Resize handles (corners) -->
							{#each [
								{ type: 'resize-tl', hx: table.x, hy: table.y },
								{ type: 'resize-tr', hx: table.x + table.w, hy: table.y },
								{ type: 'resize-bl', hx: table.x, hy: table.y + table.h },
								{ type: 'resize-br', hx: table.x + table.w, hy: table.y + table.h }
							] as handle}
								<!-- svelte-ignore a11y-no-static-element-interactions -->
								<rect 
									x={handle.hx - 5} y={handle.hy - 5} width="10" height="10" rx="2"
									class="resize-handle"
									style="cursor: {handle.type.includes('tl') || handle.type.includes('br') ? 'nwse-resize' : 'nesw-resize'}"
									on:mousedown={(e) => startDragTable(e, table, handle.type)}
								/>
							{/each}

							<!-- Rotation handle -->
							<!-- svelte-ignore a11y-no-static-element-interactions -->
							<line x1={cx} y1={table.y} x2={cx} y2={table.y - 25} stroke="var(--accent)" stroke-width="2" stroke-dasharray="3 2"/>
							<!-- svelte-ignore a11y-no-static-element-interactions -->
							<circle 
								cx={cx} cy={table.y - 30} r="7"
								class="rotate-handle"
								on:mousedown={(e) => startDragTable(e, table, 'rotate')}
							/>
							<text x={cx} y={table.y - 27} text-anchor="middle" fill="white" font-size="8" font-weight="bold" style="pointer-events:none">↻</text>

							<!-- Remove -->
							<!-- svelte-ignore a11y-no-static-element-interactions -->
							<g class="remove-btn" on:click|stopPropagation={() => removeItem('table', table.id)}>
								<circle cx={table.x + table.w - 8} cy={table.y + 8} r="8" fill="var(--danger)"/>
								<text x={table.x + table.w - 8} y={table.y + 12} text-anchor="middle" fill="white" font-size="10" font-weight="bold">✕</text>
							</g>
						{/if}
					{/if}
				</g>
			{/each}

			<!-- Furniture (AXE-09) -->
			{#each layout.furniture as furn (furn.id)}
				{@const fcx = furn.x + furn.w / 2}
				{@const fcy = furn.y + furn.h / 2}
				<g transform="rotate({furn.rotation || 0}, {fcx}, {fcy})">
					<!-- svelte-ignore a11y-no-static-element-interactions -->
					<rect 
						x={furn.x} y={furn.y} width={furn.w} height={furn.h} rx="6"
						class="furniture-rect"
						style="cursor: {editMode ? 'grab' : 'default'}"
						on:mousedown={(e) => startDragTable(e, furn, 'move')}
					/>
					<foreignObject x={furn.x} y={furn.y} width={furn.w} height={furn.h} style="pointer-events:none">
						<div style="display:flex;flex-direction:column;align-items:center;justify-content:center;width:100%;height:100%;line-height:1.1;">
							<span style="font-size: {furn.h <= 40 ? '18px' : '26px'};">{furn.icon}</span>
							<span style="font-size: {furn.h <= 40 ? '10px' : '12px'};font-weight:700;color:#f59e0b;margin-top:2px;text-align:center;word-break:break-all;padding:0 4px;">{furn.label}</span>
						</div>
					</foreignObject>

					{#if editMode}
						<!-- Resize handles -->
						{#each [
							{ type: 'resize-tl', hx: furn.x, hy: furn.y },
							{ type: 'resize-tr', hx: furn.x + furn.w, hy: furn.y },
							{ type: 'resize-bl', hx: furn.x, hy: furn.y + furn.h },
							{ type: 'resize-br', hx: furn.x + furn.w, hy: furn.y + furn.h }
						] as handle}
							<!-- svelte-ignore a11y-no-static-element-interactions -->
							<rect 
								x={handle.hx - 5} y={handle.hy - 5} width="10" height="10" rx="2"
								class="resize-handle"
								style="cursor: {handle.type.includes('tl') || handle.type.includes('br') ? 'nwse-resize' : 'nesw-resize'}"
								on:mousedown={(e) => startDragTable(e, furn, handle.type)}
							/>
						{/each}

						<!-- Rotation handle -->
						<!-- svelte-ignore a11y-no-static-element-interactions -->
						<line x1={fcx} y1={furn.y} x2={fcx} y2={furn.y - 25} stroke="#f59e0b" stroke-width="2" stroke-dasharray="3 2"/>
						<!-- svelte-ignore a11y-no-static-element-interactions -->
						<circle 
							cx={fcx} cy={furn.y - 30} r="7"
							class="rotate-handle furniture-rotate"
							on:mousedown={(e) => startDragTable(e, furn, 'rotate')}
						/>
						<text x={fcx} y={furn.y - 27} text-anchor="middle" fill="white" font-size="8" font-weight="bold" style="pointer-events:none">↻</text>

						<!-- Remove -->
						<!-- svelte-ignore a11y-no-static-element-interactions -->
						<g class="remove-btn" on:click|stopPropagation={() => removeItem('furniture', furn.id)}>
							<circle cx={furn.x + furn.w - 8} cy={furn.y + 8} r="8" fill="var(--danger)"/>
							<text x={furn.x + furn.w - 8} y={furn.y + 12} text-anchor="middle" fill="white" font-size="10" font-weight="bold">✕</text>
						</g>
					{/if}
				</g>
			{/each}

			<!-- Seats -->
			{#each layout.seats as seat (seat.id)}
				{@const occupant = getOccupant(seat.id)}
				{@const isMine = selectedSeat === seat.id}
				{@const isOccupied = !!occupant}
				{@const isTeammate = !isMine && isOccupied && user?.team_name && occupant.team_name === user.team_name}
				{@const scx = seat.x + SEAT_SIZE / 2}
				{@const scy = seat.y + SEAT_SIZE / 2}
				<!-- svelte-ignore a11y-no-static-element-interactions -->
				<g 
					class="seat-group {isMine ? 'mine' : ''} {isTeammate ? 'teammate' : (isOccupied && !isMine ? 'occupied' : '')} {draggingUserId && !isOccupied ? 'drop-target' : ''} {highlightedSeat === seat.id ? 'highlighted' : ''}"
					transform="rotate({seat.rotation || 0}, {scx}, {scy})"
					on:mousedown={(e) => editMode ? startDragSeat(e, seat) : null}
					on:click={() => {
						if (editMode) return;
						if (panMoved) return;
						selectSeatInfo(seat);
						if (draggingUserId && !isOccupied) { dropUserOnSeat(seat.id); return; }
						if (isMine) return;
						if (isOccupied && user?.is_admin && (typeof window === 'undefined' || window.innerWidth > 900)) { assigningSeatId = seat.id; return; }
						if (!isOccupied && !activeSeatCard) claimSeat(seat.id);
					}}
					style="cursor: {editMode ? 'grab' : draggingUserId ? 'copy' : 'pointer'}"
				>
					<clipPath id="clip-{seat.id}">
						<rect x={seat.x + 2} y={seat.y} width={SEAT_SIZE - 4} height={SEAT_SIZE}/>
					</clipPath>
					<rect x={seat.x} y={seat.y} width={SEAT_SIZE} height={SEAT_SIZE} rx="8" class="seat-rect"/>
					<g clip-path="url(#clip-{seat.id})">
						<text x={scx} y={seat.y + 13} text-anchor="middle" class="seat-label">{seat.id}</text>
						{#if occupant}
							<text x={scx} y={seat.y + 28} text-anchor="middle" class="seat-player"
								textLength={occupant.username.length > 7 ? SEAT_SIZE - 6 : null}
								lengthAdjust="spacingAndGlyphs"
							>{occupant.username}</text>
							{#if occupant.team_name}
								<text x={scx} y={seat.y + 39} text-anchor="middle" class="seat-team"
									textLength={occupant.team_name.length > 8 ? SEAT_SIZE - 8 : null}
									lengthAdjust="spacingAndGlyphs"
								>{occupant.team_name}</text>
							{/if}
						{:else}
							<text x={scx} y={seat.y + 32} text-anchor="middle" class="seat-free">{$t("map_legend_free")}</text>
						{/if}
					</g>

					{#if editMode}
						<!-- Rotation handle -->
						<!-- svelte-ignore a11y-no-static-element-interactions -->
						<line x1={scx} y1={seat.y} x2={scx} y2={seat.y - 16} stroke="var(--accent)" stroke-width="1.5" stroke-dasharray="2 2" class="seat-rotate-line"/>
						<!-- svelte-ignore a11y-no-static-element-interactions -->
						<circle cx={scx} cy={seat.y - 20} r="5" class="rotate-handle"
							on:mousedown|stopPropagation={(e) => startDragSeat(e, seat, 'rotate-seat')}
						/>
						<text x={scx} y={seat.y - 17} text-anchor="middle" fill="white" font-size="6" font-weight="bold" style="pointer-events:none">↻</text>
						<!-- Remove -->
						<!-- svelte-ignore a11y-no-static-element-interactions -->
						<g class="remove-btn" on:click|stopPropagation={() => removeItem('seat', seat.id)}>
							<circle cx={seat.x + SEAT_SIZE - 5} cy={seat.y + 5} r="6" fill="var(--danger)"/>
							<text x={seat.x + SEAT_SIZE - 5} y={seat.y + 8} text-anchor="middle" fill="white" font-size="8" font-weight="bold">✕</text>
						</g>
					{/if}

					<!-- Admin: click occupied seat to reassign -->
					{#if !editMode && user?.is_admin && isOccupied}
						<!-- svelte-ignore a11y-no-static-element-interactions -->
						<rect x={seat.x + SEAT_SIZE - 12} y={seat.y} width="12" height="12" rx="3" fill="var(--accent)" opacity="0.8"
							class="admin-badge"
							on:click|stopPropagation={() => assigningSeatId = seat.id}
						/>
						<text x={seat.x + SEAT_SIZE - 6} y={seat.y + 9} text-anchor="middle" fill="white" font-size="7" font-weight="bold" style="pointer-events:none">⚙</text>
					{/if}
				</g>
			{/each}
		</svg>
	</div>

	{#if activeSeatCard}
		<div class="seat-info-bottom-sheet glass animate-in">
			<div class="sheet-header">
				<div class="sheet-title-row">
					<span class="sheet-seat-badge">🪑 {$t('map_sheet_seat_prefix', { id: activeSeatCard.seat.id })}</span>
					{#if activeSeatCard.isMine}
						<span class="sheet-status-tag mine">{$t('map_sheet_mine')}</span>
					{:else if activeSeatCard.isOccupied}
						<span class="sheet-status-tag occupied">{$t('map_sheet_occupied')}</span>
					{:else}
						<span class="sheet-status-tag free">{$t('map_sheet_free')}</span>
					{/if}
				</div>
				<button class="sheet-close-btn" on:click={() => activeSeatCard = null}>✕</button>
			</div>

			<div class="sheet-body">
				{#if activeSeatCard.isOccupied && activeSeatCard.occupant}
					<div class="sheet-player-info">
						<span class="sheet-avatar">👤</span>
						<div class="sheet-player-names">
							<strong class="sheet-username">{activeSeatCard.occupant.username}</strong>
							{#if activeSeatCard.occupant.team_name}
								<span class="sheet-team">👥 {activeSeatCard.occupant.team_name}</span>
							{/if}
						</div>
					</div>
					<div class="sheet-actions">
						{#if !activeSeatCard.isMine}
							<a href="/dashboard/players?chat={activeSeatCard.occupant.id}" class="btn btn-sm btn-primary">
								💬 {$t('map_sheet_send_msg')}
							</a>
						{/if}
						{#if activeSeatCard.isMine}
							<button class="btn btn-sm btn-secondary text-danger" on:click={() => { releaseSeat(); activeSeatCard = null; }}>
								{$t('map_sheet_release_seat')}
							</button>
						{/if}
					</div>
			{:else}
					<p class="sheet-free-text">{$t('map_sheet_free_desc')}</p>
					<div class="sheet-actions">
						<button class="btn btn-sm btn-primary" on:click={() => { claimSeat(activeSeatCard.seat.id); activeSeatCard = null; }} disabled={seatingLocked && !user?.is_admin}>
							🪑 {$t('map_sheet_claim_btn')}
						</button>
					</div>
				{/if}
			</div>
		</div>
	{/if}

	<!-- Admin assignment popup -->
	{#if assigningSeatId && user?.is_admin}
		<div class="assign-panel glass">
			<div class="flex-row justify-between items-center mb-2">
				<h3 class="text-accent">{$t("map_assign_title", { seat: assigningSeatId })}</h3>
				<button class="btn-link text-dim" on:click={() => assigningSeatId = null}>✕</button>
			</div>
			{#if getOccupant(assigningSeatId)}
				<p class="text-sm mb-2">{@html $t("map_assign_occupied_by", { user: getOccupant(assigningSeatId).username })}</p>
				<button class="btn-danger-sm mb-2" on:click={() => adminUnassign(assigningSeatId)}>{$t("map_assign_release_btn")}</button>
				<hr style="border-color: var(--glass-border); margin: 0.5rem 0;"/>
			{/if}
			<p class="text-xs text-dim mb-1">{$t("map_assign_to_lbl")}</p>
			<div class="user-list">
				{#each unassignedUsers as u}
					<button class="user-option" on:click={() => adminAssign(assigningSeatId, u.id)}>
						{u.username} {u.is_admin ? '👑' : ''}
					</button>
				{/each}
				{#if unassignedUsers.length === 0}
					<p class="text-xs text-dim">{$t("map_assign_all_occupied")}</p>
				{/if}
			</div>
		</div>
	{/if}

	<!-- Legend -->
	<div class="legend">
		<div class="legend-item"><span class="dot mine-dot"></span> {$t("map_legend_yourseat")}</div>
		<div class="legend-item"><span class="dot free-dot"></span> {$t("map_legend_free")}</div>
		<div class="legend-item"><span class="dot occupied-dot"></span> {$t("map_legend_occupied")}</div>
		{#if user?.team_name}
			<div class="legend-item"><span class="dot teammate-dot"></span> {$t('map_legend_teammates')}</div>
		{/if}
		<div class="legend-item"><span class="dot table-dot"></span> {$t('map_legend_table')}</div>
		<div class="legend-item"><span class="dot furniture-dot"></span> {$t("map_legend_element")}</div>
	</div>

	<!-- Admin: Player badge bar for drag-drop -->
	{#if user?.is_admin && !editMode}
		<div class="player-badge-bar glass">
			<span class="badge-label">{$t("map_players_list")}</span>
			{#each unassignedUsers as u}
				<!-- svelte-ignore a11y-no-static-element-interactions -->
				<span 
					class="player-badge {draggingUserId === u.id ? 'active' : ''}"
					on:mousedown={() => draggingUserId = u.id}
					on:mouseup={() => {}}
				>
					{u.username}{#if u.team_name} <span class="badge-team">• {u.team_name}</span>{/if}
				</span>
			{/each}
			{#if draggingUserId}
				<!-- svelte-ignore a11y-no-static-element-interactions -->
				<button class="badge-cancel" on:click={() => draggingUserId = null}>✕ {$t("info_btn_cancel")}</button>
			{/if}
			{#if unassignedUsers.length === 0}
				<span class="text-xs text-dim">{$t("map_assign_all_occupied")}</span>
			{/if}
		</div>
	{/if}
</div>

<!-- Toasts -->
<div class="toast-container" use:portal>
	{#each toasts as t (t.id)}
		<div class="toast {t.type} {t.leaving ? 'toast-leave' : 'toast-enter'}">
			<span>{#if t.type === 'success'}✅{:else if t.type === 'error'}❌{:else}ℹ️{/if}</span>
			<span>{t.message}</span>
		</div>
	{/each}
</div>

<style>
	.map-page { display: flex; flex-direction: column; gap: 1rem; height: 100%; }
	.canvas-wrapper { flex-grow: 1; padding: 0.5rem; overflow: hidden; border-radius: 16px; min-height: 400px; position: relative; }
	.map-empty { position: absolute; inset: 0; z-index: 2; display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 0.6rem; text-align: center; padding: 1.5rem; pointer-events: none; }
	.map-empty > * { pointer-events: auto; margin: 0; max-width: 46ch; }
	.map-empty-title { font-family: var(--font-title); font-size: var(--fs-section); font-weight: 700; color: var(--text-main); }
	.free-all-confirm { display: inline-flex; align-items: center; gap: 0.5rem; font-size: 0.88rem; color: var(--text-main); }
	.room-canvas { width: 100%; height: 100%; background: var(--map-canvas-bg); border-radius: 12px; user-select: none; }
	.room-canvas.edit-mode { outline: 2px dashed rgba(59, 130, 246, 0.3); outline-offset: -2px; }

	/* Harmonize toolbar heights and styles */
	.map-page header button,
	.map-page header select {
		height: 38px;
		padding: 0 1.25rem;
		font-size: 0.75rem;
		font-weight: 700;
		border-radius: var(--radius-md);
		box-sizing: border-box;
		display: inline-flex;
		align-items: center;
		justify-content: center;
		vertical-align: middle;
		margin: 0;
	}
	.map-page header select {
		appearance: none;
		-webkit-appearance: none;
		padding-right: 2.2rem;
		background: var(--map-select-bg);
		border: 1px solid var(--glass-border);
		color: var(--accent);
		cursor: pointer;
		background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' fill='none' viewBox='0 0 24 24' stroke='%233b82f6'%3E%3Cpath stroke-linecap='round' stroke-linejoin='round' stroke-width='2' d='M19 9l-7 7-7-7'/%3E%3C/svg%3E");
		background-repeat: no-repeat;
		background-position: right 0.75rem center;
		background-size: 0.85rem;
	}
	.map-page header select:focus {
		border-color: var(--accent);
		outline: none;
	}
	.map-page header select option { background: var(--map-select-option-bg); color: var(--map-select-option-color); padding: 0.3rem; }

	/* Tables */
	.table-rect {
		fill: var(--map-table-fill);
		stroke: var(--map-table-stroke);
		stroke-width: 2;
		filter: drop-shadow(0 4px 8px rgba(0,0,0,0.3));
	}

	.table-label { fill: var(--text-muted); font-size: 13px; font-weight: 700; pointer-events: none; }
	.table-rect.delete-pending {
		stroke: var(--danger);
		fill: rgba(239, 68, 68, 0.05);
	}
	.add-seat-btn circle {
		transition: filter 0.2s, stroke-width 0.2s;
	}
	.add-seat-btn:hover circle {
		filter: brightness(1.25);
		stroke-width: 1.5;
	}
	.add-seat-btn rect {
		transition: fill 0.2s, stroke-width 0.2s;
	}
	.add-seat-btn:hover rect {
		fill: rgba(34, 197, 94, 0.12);
		stroke-width: 2;
	}

	/* Furniture (AXE-09) */
	.furniture-rect { fill: rgba(245, 158, 11, 0.12); stroke: rgba(245, 158, 11, 0.5); stroke-width: 2; stroke-dasharray: 6 3; filter: drop-shadow(0 2px 6px rgba(0,0,0,0.2)); }
	.furniture-icon { font-size: 16px; }
	.furniture-label { fill: #f59e0b; font-size: 10px; font-weight: 700; pointer-events: none; }
	.furniture-rotate { fill: #f59e0b; }
	.furniture-dot { background: rgba(245, 158, 11, 0.3); border: 2px solid rgba(245, 158, 11, 0.6); }
	.toolbar-sep { color: var(--text-muted); opacity: 0.3; font-size: 1.2rem; align-self: center; }

	/* Resize handles */
	.resize-handle { fill: var(--accent); stroke: white; stroke-width: 1; opacity: 0; transition: opacity 0.15s; }
	g:hover > .resize-handle { opacity: 1; }

	/* Rotate handle */
	.rotate-handle { fill: var(--accent); stroke: white; stroke-width: 1.5; cursor: grab; opacity: 0; transition: opacity 0.15s; }
	.seat-rotate-line { opacity: 0; transition: opacity 0.15s; }
	g:hover > line, g:hover > .rotate-handle, g:hover > .seat-rotate-line { opacity: 1; }

	/* Seats */
	.seat-rect {
		fill: var(--map-seat-fill);
		stroke: var(--map-seat-stroke);
		stroke-width: 1.5;
		transition: all 0.2s;
	}
	.seat-group:hover .seat-rect { stroke: var(--accent); stroke-width: 2; fill: var(--map-seat-hover-fill); }
	.seat-group.mine .seat-rect { fill: var(--map-seat-mine-fill); stroke: var(--accent); stroke-width: 2; filter: drop-shadow(0 0 10px var(--accent-glow)); }
	.seat-group.occupied .seat-rect { fill: var(--map-seat-occupied-fill); stroke: var(--map-seat-occupied-stroke); }
	.seat-group.teammate .seat-rect { fill: var(--map-seat-teammate-fill); stroke: var(--map-seat-teammate-stroke); stroke-width: 2; }
	.seat-group.drop-target .seat-rect { stroke: var(--map-seat-drop-stroke); stroke-width: 2; stroke-dasharray: 4 2; fill: var(--map-seat-drop-fill); }
	.seat-group.highlighted .seat-rect { stroke: #fbbf24; stroke-width: 3; fill: rgba(251,191,36,0.15); animation: seatHighlight 1.2s ease-in-out 4; }
	@keyframes seatHighlight {
		0%, 100% { stroke: #fbbf24; stroke-width: 3; filter: drop-shadow(0 0 6px rgba(251,191,36,0.4)); }
		50% { stroke: #38bdf8; stroke-width: 4; filter: drop-shadow(0 0 14px rgba(56,189,248,0.6)); }
	}

	.seat-label { fill: var(--text-dim); font-size: 8px; font-weight: 800; pointer-events: none; }
	.seat-group.mine .seat-label { fill: var(--accent); }
	.seat-player { fill: var(--map-seat-player-fill); font-size: 9px; font-weight: 700; pointer-events: none; }
	.seat-team { fill: var(--accent); font-size: 7px; font-weight: 600; pointer-events: none; opacity: 0.8; }
	.seat-free { fill: var(--text-muted); font-size: 9px; pointer-events: none; }
	.seat-group.mine .seat-player { fill: var(--map-seat-player-fill); }

	/* Remove btn */
	.remove-btn { cursor: pointer; opacity: 0; transition: opacity 0.2s; }
	g:hover > .remove-btn { opacity: 1; }

	/* Admin badge */
	.admin-badge { opacity: 0; transition: opacity 0.2s; cursor: pointer; }
	.seat-group:hover .admin-badge { opacity: 0.8; }

	/* Legend */
	.legend { display: flex; gap: 1.5rem; justify-content: center; font-size: 0.75rem; color: var(--text-dim); flex-wrap: wrap; }
	.legend-item { display: flex; align-items: center; gap: 0.4rem; }
	.dot { width: 10px; height: 10px; border-radius: 3px; }
	.mine-dot { background: var(--accent); box-shadow: 0 0 6px var(--accent-glow); }
	.free-dot { background: var(--map-free-dot-bg); border: 1px solid var(--map-free-dot-border); }
	.occupied-dot { background: var(--map-seat-occupied-fill); border: 1px solid var(--map-seat-occupied-stroke); }
	.teammate-dot { background: var(--map-seat-teammate-fill); border: 1px solid var(--map-seat-teammate-stroke); }
	.table-dot { background: var(--map-table-dot-bg); border: 2px solid var(--map-table-dot-border); }

	/* Player badge bar (admin drag-drop) */
	.player-badge-bar { display: flex; align-items: center; gap: 0.5rem; padding: 0.6rem 1rem; border-radius: 12px; flex-wrap: wrap; }
	.badge-label { font-size: 0.7rem; font-weight: 700; color: var(--text-muted); white-space: nowrap; }
	.player-badge { padding: 0.3rem 0.7rem; background: var(--map-badge-bg); border: 1px solid var(--map-badge-border); border-radius: 8px; font-size: 0.7rem; font-weight: 700; color: var(--accent); cursor: grab; transition: all 0.15s; user-select: none; }
	.player-badge:hover { background: var(--map-badge-hover); }
	.player-badge.active { background: var(--accent); color: white; box-shadow: 0 0 12px var(--accent-glow); }
	.badge-cancel { padding: 0.25rem 0.6rem; background: rgba(239,68,68,0.1); border: 1px solid rgba(239,68,68,0.2); border-radius: 6px; color: var(--danger); font-size: 0.65rem; font-weight: 700; cursor: pointer; }
	.badge-team { color: var(--text-muted); font-weight: 500; font-size: 0.6rem; }

	/* Team name bar */
	.team-bar { display: flex; align-items: center; gap: 0.75rem; padding: 0.5rem 1rem; border-radius: 10px; }
	.team-input { background: var(--input-bg); border: 1px solid var(--glass-border); border-radius: 6px; padding: 0.3rem 0.6rem; color: var(--input-color); font-size: 0.8rem; width: 200px; }

	/* Assign panel */
	.assign-panel {
		position: fixed; bottom: 2rem; right: 2rem; width: 280px; padding: 1.2rem;
		border-radius: 16px; z-index: 100;
		border: 1px solid var(--glass-border);
		box-shadow: 0 20px 40px rgba(0,0,0,0.5);
		animation: slideUp 0.3s ease-out;
	}
	@keyframes slideUp { from { opacity: 0; transform: translateY(20px); } to { opacity: 1; transform: translateY(0); } }

	.user-list { display: flex; flex-direction: column; gap: 0.3rem; max-height: 200px; overflow-y: auto; }
	.user-option {
		background: var(--map-user-option-bg); border: 1px solid var(--glass-border); border-radius: 8px;
		padding: 0.5rem 0.8rem; color: var(--text-main); cursor: pointer; font-size: 0.8rem; font-weight: 600;
		text-align: left; transition: all 0.15s;
	}
	.user-option:hover { background: var(--map-user-option-hover); border-color: var(--accent); }

	.btn-link { background: none; border: none; color: var(--accent); cursor: pointer; text-decoration: underline; font-size: inherit; padding: 0; }

	/* Toast */
	.toast-container { position: fixed; bottom: 1.5rem; right: 1.5rem; z-index: 10000; display: flex; flex-direction: column-reverse; gap: 0.75rem; pointer-events: none; }
	.toast { display: flex; align-items: center; gap: 0.75rem; padding: 0.8rem 1.4rem; border-radius: 12px; backdrop-filter: blur(16px); border: 1px solid var(--glass-border); box-shadow: 0 10px 30px rgba(0,0,0,0.4); font-size: 0.88rem; font-weight: 600; pointer-events: auto; min-width: 260px; }
	.toast.success { background: rgba(16, 185, 129, 0.15); border-color: rgba(16, 185, 129, 0.3); color: #10b981; }
	.toast.error { background: rgba(239, 68, 68, 0.15); border-color: rgba(239, 68, 68, 0.3); color: var(--danger); }
	.toast.info { background: rgba(59, 130, 246, 0.15); border-color: rgba(59, 130, 246, 0.3); color: var(--accent); }
	.toast-enter { animation: toastIn 0.4s cubic-bezier(0.16, 1, 0.3, 1) forwards; }
	.toast-leave { animation: toastOut 0.4s ease-in forwards; }
	@keyframes toastIn { from { opacity: 0; transform: translateX(80px); } to { opacity: 1; transform: translateX(0); } }
	@keyframes toastOut { from { opacity: 1; } to { opacity: 0; transform: translateX(80px); } }

	/* Mobile Map Action Bar & Bottom Sheet */
	.map-mobile-bar { display: none; }
	.seat-info-bottom-sheet { display: none; }

	@media (max-width: 900px) {
		.map-page { display: flex; flex-direction: column; height: calc(100vh - 96px); gap: 0.5rem; }
		.map-page > header { display: none !important; }
		.player-badge-bar, .assign-panel { display: none !important; }
		.canvas-wrapper {
			flex: 1; min-height: 0; width: 100%; border-radius: 12px;
			touch-action: none !important; -webkit-user-select: none; user-select: none;
		}
		.room-canvas { touch-action: none !important; }

		.map-mobile-bar {
			display: flex; justify-content: space-between; align-items: center;
			padding: 0.5rem 0.8rem; border-radius: 10px; background: var(--surface-raised);
			border: 1px solid var(--glass-border); flex-shrink: 0; gap: 0.5rem;
		}
		.mobile-my-seat {
			font-size: 0.78rem; font-weight: 800; color: var(--accent);
			background: var(--accent-soft); padding: 0.25rem 0.6rem; border-radius: 8px;
			border: 1px solid rgba(59,130,246,0.3); white-space: nowrap; cursor: pointer;
		}
		.mobile-my-seat.none { background: none; border-color: transparent; color: var(--text-muted); font-weight: 600; cursor: default; padding-left: 0.2rem; }
		.mobile-my-seat { min-width: 0; overflow: hidden; text-overflow: ellipsis; }
		.map-mobile-btns { flex-shrink: 0; }
		.map-mobile-btns { display: flex; gap: 0.4rem; }
		.map-top-btn {
			background: var(--surface-sunken); border: 1px solid var(--glass-border);
			color: var(--text-main); font-size: 0.72rem; font-weight: 700;
			padding: 0.3rem 0.6rem; border-radius: 8px; cursor: pointer; white-space: nowrap;
		}

		/* Seat Bottom Sheet Card on mobile */
		.seat-info-bottom-sheet {
			display: flex; flex-direction: column; gap: 0.6rem;
			position: fixed; bottom: 56px; left: 12px; right: 12px;
			background: var(--surface-raised); border: 1px solid var(--glass-border);
			border-radius: 14px; padding: 0.9rem 1rem; z-index: 50;
			box-shadow: 0 12px 30px rgba(0,0,0,0.5); backdrop-filter: blur(12px); -webkit-backdrop-filter: blur(12px);
		}
		.sheet-header { display: flex; justify-content: space-between; align-items: center; }
		.sheet-title-row { display: flex; align-items: center; gap: 0.5rem; }
		.sheet-seat-badge { font-weight: 800; font-size: 0.9rem; color: var(--text-main); }
		.sheet-status-tag { font-size: 0.65rem; font-weight: 800; padding: 0.15rem 0.5rem; border-radius: 6px; text-transform: uppercase; }
		.sheet-status-tag.free { background: rgba(34,197,94,0.15); color: #22c55e; border: 1px solid rgba(34,197,94,0.3); }
		.sheet-status-tag.occupied { background: rgba(239,68,68,0.15); color: #f87171; border: 1px solid rgba(239,68,68,0.3); }
		.sheet-status-tag.mine { background: rgba(59,130,246,0.15); color: #60a5fa; border: 1px solid rgba(59,130,246,0.3); }
		.sheet-close-btn { background: none; border: none; color: var(--text-dim); font-size: 1rem; cursor: pointer; padding: 0.2rem; }
		.sheet-body { display: flex; flex-direction: column; gap: 0.6rem; }
		.sheet-player-info { display: flex; align-items: center; gap: 0.6rem; }
		.sheet-avatar { font-size: 1.4rem; }
		.sheet-player-names { display: flex; flex-direction: column; gap: 0.1rem; }
		.sheet-username { font-size: 0.92rem; color: var(--text-main); }
		.sheet-team { font-size: 0.72rem; color: var(--accent); }
		.sheet-free-text { font-size: 0.8rem; color: var(--text-dim); margin: 0; }
		.sheet-actions { display: flex; gap: 0.5rem; justify-content: flex-end; }
		.sheet-actions .btn { text-decoration: none; display: inline-flex; align-items: center; }
	}

</style>
