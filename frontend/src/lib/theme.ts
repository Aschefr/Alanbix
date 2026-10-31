import { writable } from 'svelte/store';

/**
 * One place for the colour theme.
 * The preference is 'system' (follow the device, the default), 'dark' or 'light'.
 * `theme` is what is really displayed once 'system' is resolved.
 */
export type ThemePref = 'system' | 'dark' | 'light';
export type Theme = 'dark' | 'light';

const KEY = 'alanbix_theme';
const BG: Record<Theme, string> = { dark: '#0f172a', light: '#f1f5f9' };

export function getThemePref(): ThemePref {
	try {
		const v = localStorage.getItem(KEY);
		return v === 'dark' || v === 'light' ? v : 'system';
	} catch {
		return 'system';
	}
}

export function resolveTheme(pref: ThemePref): Theme {
	if (pref !== 'system') return pref;
	try {
		return window.matchMedia('(prefers-color-scheme: light)').matches ? 'light' : 'dark';
	} catch {
		return 'dark';
	}
}

export const themeStore = writable<{ pref: ThemePref; theme: Theme }>({ pref: 'system', theme: 'dark' });

function paintNative(theme: Theme) {
	const w = window as any;
	const bar = w.Capacitor?.Plugins?.StatusBar;
	if (!bar) return;
	try {
		bar.setBackgroundColor?.({ color: BG[theme] })?.catch?.(() => {});
		// 'DARK' = light icons for a dark bar
		bar.setStyle?.({ style: theme === 'dark' ? 'DARK' : 'LIGHT' })?.catch?.(() => {});
	} catch {}
}

export function applyTheme(pref: ThemePref = getThemePref()): Theme {
	const theme = resolveTheme(pref);
	const root = document.documentElement;
	root.setAttribute('data-theme', theme);
	root.style.background = BG[theme];
	document.querySelector('meta[name="theme-color"]')?.setAttribute('content', BG[theme]);
	paintNative(theme);
	themeStore.set({ pref, theme });
	return theme;
}

export function setThemePref(pref: ThemePref) {
	try {
		if (pref === 'system') localStorage.removeItem(KEY);
		else localStorage.setItem(KEY, pref);
	} catch {}
	applyTheme(pref);
}

/** Flip between dark and light from the quick toggle (this makes the choice explicit). */
export function toggleTheme(current: Theme) {
	setThemePref(current === 'dark' ? 'light' : 'dark');
}

let started = false;
/** Apply the saved preference and keep following the device while it is on 'system'. */
export function initTheme() {
	applyTheme();
	if (started || typeof window === 'undefined') return;
	started = true;
	try {
		window.matchMedia('(prefers-color-scheme: light)').addEventListener('change', () => {
			if (getThemePref() === 'system') applyTheme('system');
		});
	} catch {}
	// another tab changed it
	window.addEventListener('storage', (e) => { if (e.key === KEY) applyTheme(); });
}
