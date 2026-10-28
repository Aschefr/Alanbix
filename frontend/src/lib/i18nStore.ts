import { writable, derived, get } from 'svelte/store';
import { API_URL, resolveApiUrl, isDemoMode } from './config';

export const currentLang = writable<string>('fr');
export const i18nDict = writable<Record<string, string>>({});
export const lanMultilingual = writable<boolean>(false);
export const availableLanguages = writable<string[]>(['fr', 'en']);
export const eventName = writable<string>('Alanbix LAN');
export const customPageTitle = writable<string>('');

export const flagMap: Record<string, string> = {
	fr: 'Français',
	en: 'English',
	es: 'Español',
	de: 'Deutsch',
	it: 'Italiano',
	pt: 'Português',
	nl: 'Nederlands',
	ru: 'Русский',
	ja: '日本語',
	zh: '中文',
};

// Derived store for translating
export const t = derived(i18nDict, ($dict) => {
	return (key: string, replacements?: Record<string, string | number>) => {
		let text = $dict[key] || key;
		if (replacements) {
			Object.entries(replacements).forEach(([k, v]) => {
				text = text.replace(new RegExp(`{${k}}`, 'g'), String(v));
			});
		}
		return text;
	};
});

// Load the dictionary for a specific language
export async function loadLocale(lang: string) {
	if (isDemoMode()) {
		currentLang.set(lang);
		localStorage.setItem('alanbix_lang', lang);
		return;
	}
	try {
		const baseUrl = resolveApiUrl() || API_URL;
		// Prevent cache issues in dev/prod by fetching with a query param
		const res = await fetch(`${baseUrl}/api/i18n/${lang}?v=${Date.now()}`);
		if (!res.ok) throw new Error(`Could not load locale ${lang}`);
		const dict = await res.json();
		i18nDict.set(dict);
		currentLang.set(lang);
		localStorage.setItem('alanbix_lang', lang);
	} catch (e) {
		console.error(`Failed to load locale ${lang}:`, e);
	}
}

// Refresh the LAN event name
export async function refreshEventName() {
	if (isDemoMode()) {
		eventName.set('Alanbix LAN (Démo)');
		return;
	}
	try {
		const baseUrl = resolveApiUrl() || API_URL;
		const res = await fetch(`${baseUrl}/dashboard/stats`);
		if (res.ok) {
			const stats = await res.json();
			eventName.set(stats.event_name || 'Alanbix LAN');
		}
	} catch (e) {
		console.error('Failed to refresh event name:', e);
	}
}

// Initialize i18n using config settings & local preferences
export async function initI18n() {
	if (isDemoMode()) {
		eventName.set('Alanbix LAN (Démo)');
		const savedLang = localStorage.getItem('alanbix_lang') || 'fr';
		currentLang.set(savedLang);
		return;
	}

	let lang: string = 'fr';
	const baseUrl = resolveApiUrl() || API_URL;

	try {
		const [langRes, statsRes] = await Promise.all([
			fetch(`${baseUrl}/i18n/languages`).catch(() => null),
			fetch(`${baseUrl}/dashboard/stats`).catch(() => null)
		]);

		if (langRes && langRes.ok) {
			const data = await langRes.json();
			if (data.languages && Array.isArray(data.languages)) {
				availableLanguages.set(data.languages);
			}
		}

		if (statsRes && statsRes.ok) {
			const stats = await statsRes.json();
			lanMultilingual.set(!!stats.lan_multilingual);
			eventName.set(stats.event_name || 'Alanbix LAN');
			
			const savedLang = localStorage.getItem('alanbix_lang');
			const list = get(availableLanguages);
			
			if (savedLang && list.includes(savedLang)) {
				lang = savedLang;
			} else {
				lang = stats.lan_default_language || 'fr';
			}
		} else {
			const savedLang = localStorage.getItem('alanbix_lang');
			lang = savedLang || 'fr';
		}
	} catch (e) {
		console.error('Failed to initialize i18n config:', e);
		const savedLang = localStorage.getItem('alanbix_lang');
		lang = savedLang || 'fr';
	}

	await loadLocale(lang);
}
