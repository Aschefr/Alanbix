// Room map geometry shared by the map editor and the guided-setup generator.
// Seats sit around a table: one row along the top edge, then one along the bottom edge.
// A seat belongs to its table by id (T3_S7 belongs to T3), so moving or rotating a table carries them.

// Every seat centre lands on the editor's 20 px grid, so dragging a seat keeps it in line with the others.
export const GRID = 20;
export const SEAT_SIZE = 50;
export const SEAT_GAP = 10;      // between two seats
export const SEAT_PITCH = 60;    // seat + gap, a multiple of GRID
export const SEAT_OFFSET = 40;   // from the table edge to the centre of its seats (15 px of air), a multiple of GRID
export const SEAT_RING = SEAT_OFFSET + SEAT_SIZE / 2; // room a table needs above and below it for its seats
export const TABLE_DEPTH = 80;   // default depth of a table: the seats are outside it

type Table = { x: number; y: number; w: number; h: number; rotation?: number };
type Seat = { id: string; x: number; y: number; rotation?: number };

/** Seats that fit along one long side of a table. */
export function seatsPerSide(width: number): number {
	return Math.max(1, Math.floor((width + SEAT_PITCH - SEAT_SIZE) / SEAT_PITCH));
}

/** Width of a table holding `perSide` seats on each long side. */
export function tableWidthFor(perSide: number): number {
	return perSide * SEAT_PITCH + 2 * SEAT_GAP;
}

/** Seat slot centres in the table's own (unrotated) frame: the top row left to right, then the bottom row.
 *  `extraRows` adds rows further out (above, then below, and so on) for seats beyond the table's capacity. */
export function seatSlots(table: Table, extraRows = 0): { x: number; y: number }[] {
	const cols = seatsPerSide(table.w);
	const span = cols * SEAT_PITCH - SEAT_GAP;
	// Centred on the table, then rounded onto the grid (tables themselves snap to it)
	const x0 = table.x + Math.round(((table.w - span) / 2 + SEAT_SIZE / 2) / GRID) * GRID;
	const top = table.y - SEAT_OFFSET;
	const bottom = table.y + table.h + SEAT_OFFSET;
	const rows = [top, bottom];
	for (let k = 1; k <= extraRows; k++) rows.push(top - k * SEAT_PITCH, bottom + k * SEAT_PITCH);
	const slots = [];
	for (const y of rows) {
		for (let c = 0; c < cols; c++) slots.push({ x: x0 + c * SEAT_PITCH, y });
	}
	return slots;
}

/** Seat (top-left corner and rotation) for a slot centre, turned with the table. */
export function seatAt(table: Table, slot: { x: number; y: number }) {
	const rot = ((table.rotation || 0) * Math.PI) / 180;
	const tcx = table.x + table.w / 2, tcy = table.y + table.h / 2;
	const dx = slot.x - tcx, dy = slot.y - tcy;
	return {
		x: tcx + dx * Math.cos(rot) - dy * Math.sin(rot) - SEAT_SIZE / 2,
		y: tcy + dx * Math.sin(rot) + dy * Math.cos(rot) - SEAT_SIZE / 2,
		rotation: table.rotation || 0,
	};
}

const seatNumber = (s: Seat) => parseInt(s.id.split('_S')[1], 10) || 0;

/** "Auto seats": as many seats as the table's length holds, laid out around it.
 *  Free seats beyond that are dropped; a seat someone sits on is never dropped and goes to an extra row. */
export function autoSeatLayout(table: Table & { id: string }, tableSeats: Seat[], isOccupied: (id: string) => boolean): Seat[] {
	const n = 2 * seatsPerSide(table.w);
	const sorted = [...tableSeats].sort((a, b) => seatNumber(a) - seatNumber(b));
	const kept = sorted.slice(0, n);
	const occupiedExtra = sorted.slice(n).filter(s => isOccupied(s.id));
	const used = new Set(sorted.map(s => s.id));
	while (kept.length < n) {
		let k = 1;
		while (used.has(`${table.id}_S${k}`)) k++;
		const id = `${table.id}_S${k}`;
		used.add(id);
		kept.push({ id, x: 0, y: 0 });
	}
	const all = [...kept, ...occupiedExtra];
	const slots = seatSlots(table, Math.ceil(occupiedExtra.length / Math.max(1, seatsPerSide(table.w))));
	return all.map((s, i) => ({ ...s, ...seatAt(table, slots[i]) }));
}

/** Seat centre brought back into the table's unrotated frame. */
function localCentre(table: Table, seat: Seat) {
	const cx = seat.x + SEAT_SIZE / 2, cy = seat.y + SEAT_SIZE / 2;
	const rot = -((table.rotation || 0) * Math.PI) / 180;
	if (Math.abs(rot) < 0.0001) return { x: cx, y: cy };
	const tcx = table.x + table.w / 2, tcy = table.y + table.h / 2;
	const dx = cx - tcx, dy = cy - tcy;
	return { x: tcx + dx * Math.cos(rot) - dy * Math.sin(rot), y: tcy + dx * Math.sin(rot) + dy * Math.cos(rot) };
}

/** First free slot around the table (centre, unrotated frame), or null when both rows are full.
 *  `blocked` lets the caller skip a slot that something else (another table, a seat) already covers. */
export function firstFreeSlot(table: Table, seatsOfTable: Seat[], blocked: (slot: { x: number; y: number }) => boolean = () => false, extraRows = 0) {
	const taken = seatsOfTable.map(s => localCentre(table, s));
	return seatSlots(table, extraRows).find(slot =>
		!taken.some(p => Math.abs(p.x - slot.x) < 5 && Math.abs(p.y - slot.y) < 5) && !blocked(slot)
	) || null;
}
