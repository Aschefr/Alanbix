/**
 * Format point values cleanly without floating point precision issues (e.g. 24.700000000000003 -> 24.7).
 * Removes unnecessary trailing zeros (e.g. 25.0 -> 25).
 *
 * @param val The points value (number, string, null, or undefined)
 * @param maxDecimals Maximum decimal places (default: 2)
 * @returns Clean number (or 0 if invalid)
 */
export function formatPoints(val: number | string | null | undefined, maxDecimals: number = 2): number {
	if (val === null || val === undefined || val === '') return 0;
	const num = typeof val === 'number' ? val : Number(val);
	if (isNaN(num)) return 0;
	const factor = Math.pow(10, maxDecimals);
	return Math.round(num * factor) / factor;
}
