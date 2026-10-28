/**
 * Service de gestion des notifications locales et push pour Alanbix Companion (Web & Mobile).
 * Stocke les préférences utilisateur exclusivement sur l'appareil (localStorage).
 */

import { api } from './api';
import { isCapacitorNative } from './config';

export interface NotificationCategories {
	match_ready: boolean;
	private_message: boolean;
	team_message: boolean;
	public_mention: 'mentions' | 'all' | 'none';
	ai_reply: boolean;
	admin_message: boolean;
	tournaments: boolean;
}

export interface NotificationPreferences {
	enabled: boolean;
	sound: boolean;
	vibration: boolean;
	dnd_enabled: boolean;
	dnd_start: string; // "02:00"
	dnd_end: string;   // "09:00"
	dnd_bypass_matches: boolean;
	dnd_bypass_admin: boolean;
	categories: NotificationCategories;
}

export const NOTIF_PREFS_STORAGE_KEY = 'alanbix_notif_prefs';
export const DEVICE_TOKEN_STORAGE_KEY = 'alanbix_device_token';

const DEFAULT_PREFERENCES: NotificationPreferences = {
	enabled: true,
	sound: true,
	vibration: true,
	dnd_enabled: false,
	dnd_start: '02:00',
	dnd_end: '09:00',
	dnd_bypass_matches: true,
	dnd_bypass_admin: true,
	categories: {
		match_ready: true,
		private_message: true,
		team_message: true,
		public_mention: 'mentions',
		ai_reply: true,
		admin_message: true,
		tournaments: true
	}
};

// Set en mémoire pour dédoublonner les alertes reçues par différents canaux
const seenPushIds = new Set<string>();

export function getNotificationPreferences(): NotificationPreferences {
	if (typeof window === 'undefined') return DEFAULT_PREFERENCES;
	try {
		const raw = localStorage.getItem(NOTIF_PREFS_STORAGE_KEY);
		if (!raw) return DEFAULT_PREFERENCES;
		const parsed = JSON.parse(raw);
		return {
			...DEFAULT_PREFERENCES,
			...parsed,
			categories: {
				...DEFAULT_PREFERENCES.categories,
				...(parsed.categories || {})
			}
		};
	} catch {
		return DEFAULT_PREFERENCES;
	}
}

export function saveNotificationPreferences(prefs: NotificationPreferences): void {
	if (typeof window === 'undefined') return;
	try {
		localStorage.setItem(NOTIF_PREFS_STORAGE_KEY, JSON.stringify(prefs));
	} catch (e) {
		console.error('[Alanbix Push] Failed to save preferences:', e);
	}
}

export function isDndActive(prefs: NotificationPreferences): boolean {
	if (!prefs.dnd_enabled) return false;
	const now = new Date();
	const currentMinutes = now.getHours() * 60 + now.getMinutes();

	const [sH, sM] = (prefs.dnd_start || '02:00').split(':').map(Number);
	const [eH, eM] = (prefs.dnd_end || '09:00').split(':').map(Number);
	const startMinutes = (sH || 0) * 60 + (sM || 0);
	const endMinutes = (eH || 0) * 60 + (eM || 0);

	if (startMinutes <= endMinutes) {
		return currentMinutes >= startMinutes && currentMinutes < endMinutes;
	} else {
		// Intervalle traversant minuit (ex: 23:00 -> 08:00)
		return currentMinutes >= startMinutes || currentMinutes < endMinutes;
	}
}

export function shouldNotify(category: string, prefs: NotificationPreferences): boolean {
	if (!prefs.enabled) return false;

	// Vérification de la plage "Ne pas déranger"
	if (isDndActive(prefs)) {
		if (category === 'match_ready' && prefs.dnd_bypass_matches) {
			// Autoriser le réveil pour match
		} else if (category === 'admin_message' && prefs.dnd_bypass_admin) {
			// Autoriser message admin urgent
		} else {
			return false;
		}
	}

	const cats = prefs.categories;
	switch (category) {
		case 'match_ready':
		case 'match_called':
		case 'score_dispute':
			return cats.match_ready !== false;
		case 'private_message':
			return cats.private_message !== false;
		case 'team_message':
			return cats.team_message !== false;
		case 'public_mention':
			return cats.public_mention !== 'none';
		case 'public_chat_all':
			return cats.public_mention === 'all';
		case 'ai_reply':
			return cats.ai_reply !== false;
		case 'admin_message':
		case 'announcement':
			return cats.admin_message !== false;
		case 'tournaments':
		case 'tournament_closed':
		case 'tournament_started':
			return cats.tournaments !== false;
		default:
			return true;
	}
}

export function triggerVibration(pattern: number[] = [80, 40, 80]): void {
	if (typeof window !== 'undefined' && 'vibrate' in navigator) {
		try {
			navigator.vibrate(pattern);
		} catch {}
	}
}

export function triggerNotificationSound(): void {
	if (typeof window === 'undefined') return;
	try {
		const audio = new Audio('/sounds/notification.mp3');
		audio.volume = 0.5;
		audio.play().catch(() => {});
	} catch {}
}

export interface PushEventPayload {
	id?: string;
	notification_id?: number;
	category?: string;
	title: string;
	body: string;
	link?: string;
	data?: any;
	created_at?: string;
}

export function handleIncomingPush(event: PushEventPayload, onNavigate?: (url: string) => void): boolean {
	if (!event || !event.title) return false;

	// Dédoublonnage
	const eventId = event.id || `${event.category || 'push'}_${event.title}_${event.created_at || Date.now()}`;
	if (seenPushIds.has(eventId)) return false;
	seenPushIds.add(eventId);
	if (seenPushIds.size > 200) {
		// Élagage de sécurité
		const first = seenPushIds.values().next().value;
		if (first) seenPushIds.delete(first);
	}

	const prefs = getNotificationPreferences();
	const category = event.category || 'system';

	if (!shouldNotify(category, prefs)) {
		return false;
	}

	// Vibration / Son si activés
	if (prefs.vibration) {
		triggerVibration();
	}
	if (prefs.sound) {
		triggerNotificationSound();
	}

	// Si l'API Web Notification est supportée (fallback navigateur / desktop)
	if (typeof window !== 'undefined' && 'Notification' in window && Notification.permission === 'granted') {
		try {
			const absoluteLink = event.link ? new URL(event.link, window.location.origin).href : null;
			const options: any = {
				body: event.body,
				icon: '/favicon.svg',
				tag: eventId,
				renotify: true,
				data: { url: absoluteLink }
			};

			const showFallback = () => {
				const n = new Notification(event.title, options);
				if (event.link) {
					n.onclick = (e) => {
						e.preventDefault();
						localStorage.setItem('alanbix_notif_nav', event.link!);
						window.focus();
						n.close();
						if (onNavigate && event.link) {
							onNavigate(event.link);
						}
					};
				}
			};

			if ('serviceWorker' in navigator) {
				navigator.serviceWorker.getRegistration().then((reg) => {
					if (reg && reg.showNotification) {
						reg.showNotification(event.title, options);
					} else {
						showFallback();
					}
				}).catch(() => showFallback());
			} else {
				showFallback();
			}
		} catch {}
	}

	return true;
}

/**
 * Enregistrement ou récupération du jeton d'appareil (device_token) pour la session courante.
 */
export async function getOrRegisterDeviceToken(): Promise<string | null> {
	if (typeof window === 'undefined') return null;
	const existing = localStorage.getItem(DEVICE_TOKEN_STORAGE_KEY);
	if (existing && existing.startsWith('dev_')) {
		return existing;
	}

	try {
		const platform = isCapacitorNative() ? (window as any).Capacitor?.getPlatform() || 'android' : 'web';
		const name = isCapacitorNative() ? 'Alanbix Companion App' : navigator.userAgent.slice(0, 40);
		const res = await api.post('/devices', { platform, name });
		if (res && res.token) {
			localStorage.setItem(DEVICE_TOKEN_STORAGE_KEY, res.token);
			return res.token;
		}
	} catch (e) {
		console.warn('[Alanbix Push] Device registration skipped/failed:', e);
	}
	return null;
}

/**
 * Révocation du jeton d'appareil lors de la déconnexion.
 */
export async function revokeCurrentDeviceToken(): Promise<void> {
	if (typeof window === 'undefined') return;
	const token = localStorage.getItem(DEVICE_TOKEN_STORAGE_KEY);
	if (!token) return;
	try {
		await api.post('/devices/revoke-token', { token });
	} catch {}
	localStorage.removeItem(DEVICE_TOKEN_STORAGE_KEY);
}

