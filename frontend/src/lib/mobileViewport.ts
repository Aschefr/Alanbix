// Phone viewport helpers: on-screen keyboard detection and "fit this pane between its top and the tab bar".
//
// Browsers disagree on what the keyboard does: some shrink the page (Chrome, Android WebView), others only shrink
// the *visual* viewport and pan the page (Firefox, iOS). Everything here is measured from visualViewport so both
// behave the same: the bottom tab bar steps aside, and a pane ends exactly where the keyboard starts.

import { writable } from 'svelte/store';

export const keyboardOpen = writable(false);

const PHONE_MAX = 900;
const KEYBOARD_MIN = 120;
const NON_TEXT_INPUTS = ['checkbox', 'radio', 'file', 'button', 'submit', 'range', 'color', 'image', 'reset'];

let started = false;
let tallest = 0;
const listeners = new Set<() => void>();

function isTyping(el: Element | null): boolean {
	if (!el) return false;
	if (el.tagName === 'TEXTAREA') return true;
	return el.tagName === 'INPUT' && !NON_TEXT_INPUTS.includes((el as HTMLInputElement).type);
}

function viewportHeight(): number {
	return window.visualViewport ? window.visualViewport.height : window.innerHeight;
}

function update() {
	const root = document.documentElement;
	const h = viewportHeight();
	tallest = Math.max(tallest, window.innerHeight, h);
	const open = window.innerWidth <= PHONE_MAX && isTyping(document.activeElement) && tallest - h > KEYBOARD_MIN;
	root.classList.toggle('kb-open', open);
	keyboardOpen.set(open);
	listeners.forEach(fn => fn());
}

/** Starts listening once for the whole app. Safe to call several times. */
export function initMobileViewport() {
	if (started || typeof window === 'undefined') return;
	started = true;
	const vv = window.visualViewport;
	vv?.addEventListener('resize', update);
	vv?.addEventListener('scroll', update);
	window.addEventListener('resize', update);
	window.addEventListener('orientationchange', () => { tallest = 0; setTimeout(update, 300); });
	document.addEventListener('focusin', update);
	// the keyboard takes a moment to close: let the viewport settle before reading it
	document.addEventListener('focusout', () => setTimeout(update, 120));
	update();
}

/** True on a phone or tablet (touch keyboard): there Enter should add a line, the send button sends. */
export function isTouchKeyboard(): boolean {
	return typeof window !== 'undefined' && !!window.matchMedia && window.matchMedia('(pointer: coarse)').matches;
}

/**
 * Svelte action: on a phone, gives the node a `--pane-h` custom property equal to the room left between its top
 * and the bottom tab bar (or the keyboard when it is open). Measured rather than hard-coded because a banner may
 * sit above the page and ancestors are animated, which rules out position: fixed.
 */
export function fitPane(node: HTMLElement, enabled: boolean = true) {
	let on = enabled;
	let observer: MutationObserver | null = null;
	const root = document.documentElement;

	function measure() {
		if (!on || window.innerWidth > PHONE_MAX) {
			node.style.removeProperty('--pane-h');
			return;
		}
		if (root.classList.contains('kb-open') && window.scrollY !== 0) window.scrollTo(0, 0);
		const area = document.querySelector('.content-area');
		const open = root.classList.contains('kb-open');
		const bottomPad = open ? 8 : (area ? parseFloat(getComputedStyle(area).paddingBottom) || 0 : 0);
		const top = node.getBoundingClientRect().top;
		node.style.setProperty('--pane-h', `${Math.max(200, Math.round(viewportHeight() - top - bottomPad))}px`);
	}

	function apply() {
		root.classList.toggle('pane-fit', on);
		listeners.delete(measure);
		observer?.disconnect();
		observer = null;
		if (on) {
			listeners.add(measure);
			// the notification banner above the page can appear or be dismissed
			const area = document.querySelector('.content-area');
			if (area && 'MutationObserver' in window) {
				observer = new MutationObserver(measure);
				observer.observe(area, { childList: true });
			}
			measure();
			setTimeout(measure, 80);
		} else {
			measure();
		}
	}

	initMobileViewport();
	apply();

	return {
		update(value: boolean) {
			on = value;
			apply();
		},
		destroy() {
			on = false;
			apply();
		}
	};
}
