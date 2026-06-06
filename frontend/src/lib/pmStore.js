import { writable, derived } from 'svelte/store';

/** Shared store for the sidebar PM unread badge. Updated by both layout (WS) and players page (read). */
export const pmUnreadCount = writable(0);

/** Shared store for group channel unread count (AXE-12). */
export const groupUnreadCount = writable(0);

/** Combined unread count for sidebar badge (P2P + Group). */
export const totalMsgUnread = derived(
	[pmUnreadCount, groupUnreadCount],
	([$pm, $group]) => $pm + $group
);

/** Shared store for general notifications. */
export const notifUnreadCount = writable(0);

/** Shared store for unread AI responses (bot reply or admin message not yet seen).
 *  Incremented in +layout.svelte via WS, reset in /dashboard/ai on mount. */
export const aiUnreadCount = writable(0);
