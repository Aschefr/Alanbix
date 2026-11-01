// Room map geometry shared by the map editor and the guided-setup generator.
// Seats sit around a table: one row along the top edge, then one along the bottom edge.
// A seat belongs to its table by id (T3_S7 belongs to T3), so moving or rotating a table carries them.

export const SEAT_SIZE = 50;
export const SEAT_GAP = 10;    // between two seats, and between a seat and the table edge
export const SEAT_PITCH = SEAT_SIZE + SEAT_GAP;
export const TABLE_DEPTH = 80; // default depth of a table: the seats are outside it

type Table = { x: number; y: number; w: number; h: number; rotation?: number };
type Seat = { id: string; x: number; y: number };

/** Seats that fit along one long side of a table. */
export function seatsPerSide(width: number): number {
	return Math.max(1, Math.floor((width + SEAT_PITCH - SEAT_SIZE) / SEAT_PITCH));
}

/** Width of a table holding `perSide` seats on each long side. */
export function tableWidthFor(perSide: number): number {
	return perSide * SEAT_PITCH + SEAT_GAP;
}

/** Seat slot centres in the table's own (unrotated) frame: the top row left to right, then the bottom row. */
export function seatSlots(table: Table): { x: number; y: number }[] {
	const cols = seatsPerSide(table.w);
	const span = cols * SEAT_PITCH - SEAT_GAP;
	const x0 = table.x + (table.w - span) / 2 + SEAT_SIZE / 2;
	const top = table.y - SEAT_GAP - SEAT_SIZE / 2;
	const bottom = table.y + table.h + SEAT_GAP + SEAT_SIZE / 2;
	const slots = [];
	for (const y of [top, bottom]) {
		for (let c = 0; c < cols; c++) slots.push({ x: x0 + c * SEAT_PITCH, y });
	}
	return slots;
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
export function firstFreeSlot(table: Table, seatsOfTable: Seat[], blocked: (slot: { x: number; y: number }) => boolean = () => false) {
	const taken = seatsOfTable.map(s => localCentre(table, s));
	return seatSlots(table).find(slot =>
		!taken.some(p => Math.abs(p.x - slot.x) < 5 && Math.abs(p.y - slot.y) < 5) && !blocked(slot)
	) || null;
}
