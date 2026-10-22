import { writable, get } from 'svelte/store';
import { t } from './i18nStore';

function getStoredPref(): boolean {
	if (typeof window === 'undefined') return false;
	const val = localStorage.getItem('alanbix_filter_profanity');
	return val === 'true';
}

export const profanityFilterEnabled = writable<boolean>(getStoredPref());

export function toggleProfanityFilter(val?: boolean) {
	profanityFilterEnabled.update(curr => {
		const next = val !== undefined ? val : !curr;
		if (typeof window !== 'undefined') {
			localStorage.setItem('alanbix_filter_profanity', String(next));
		}
		return next;
	});
}

function escapeRegex(str: string): string {
	return str.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

export function maskWord(word: string): string {
	if (word.length <= 2) {
		return '*'.repeat(word.length);
	}
	return word[0] + '*'.repeat(word.length - 2) + word[word.length - 1];
}

export function filterProfanityText(text: string, forceEnable: boolean = false): string {
	if (!text) return '';
	const enabled = forceEnable || get(profanityFilterEnabled);
	if (!enabled) return text;

	const wordsListStr = get(t)('profanity_words_list') || '';
	if (!wordsListStr) return text;

	const words = wordsListStr
		.split(';')
		.map(w => w.trim())
		.filter(w => w.length > 0);

	if (words.length === 0) return text;

	// Build regex with word boundaries
	// Note: in French/multilingual, accents can be part of words, so we support matching with \b or unicode boundaries
	const pattern = words.map(escapeRegex).join('|');
	const regex = new RegExp(`(?<=^|[\\s.,!?;:()[\\]{}"'«»—–-])${pattern}(?=[\\s.,!?;:()[\\]{}"'«»—–-]|$)`, 'gi');

	return text.replace(regex, (match) => maskWord(match));
}
