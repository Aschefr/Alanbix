import { writable } from 'svelte/store';

export const tutorialActive = writable(false);
export const tutorialStepIndex = writable(0);

export const TUTORIAL_STEPS = [
	{
		selector: 'a.nav-item[href^="/dashboard/tournaments"]',
		title: 'Tournois 🏆',
		content: 'Inscris-toi aux tournois, suis les arbres de matchs en direct et gère tes scores.'
	},
	{
		selector: 'a.nav-item[href^="/dashboard/players"]',
		title: 'Équipes & Chats 👥',
		content: 'Discute en privé ou en groupe avec les autres participants et les admins.'
	},
	{
		selector: 'a.nav-item[href^="/dashboard/ai"]',
		title: 'Assistant IA 🤖',
		content: 'Pose tes questions sur la LAN, les jeux ou le réseau à notre bot local.'
	},
	{
		selector: 'a.nav-item[href^="/dashboard/map"]',
		title: 'Plan de Salle 📍',
		content: 'Repère ta place et visualise la disposition de la salle interactive.'
	}
];

export function startTutorial() {
	tutorialStepIndex.set(0);
	tutorialActive.set(true);
}

export function stopTutorial() {
	tutorialActive.set(false);
}

export function nextTutorialStep() {
	tutorialStepIndex.update(n => {
		if (n < TUTORIAL_STEPS.length - 1) return n + 1;
		tutorialActive.set(false);
		return n;
	});
}

export function prevTutorialStep() {
	tutorialStepIndex.update(n => Math.max(0, n - 1));
}
