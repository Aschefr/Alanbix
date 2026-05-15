import { writable } from 'svelte/store';

/** Shared store for the sidebar PM unread badge. Updated by both layout (WS) and players page (read). */
export const pmUnreadCount = writable(0);
