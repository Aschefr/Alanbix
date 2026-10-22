import { writable } from 'svelte/store';

export const tutorialActive = writable(false);
export const tutorialStepIndex = writable(0);

export const TUTORIAL_STEPS = [
	{
		selector: 'a.nav-item[href^="/dashboard/tournaments"]',
		title: 'Tournois 🏆',
		content: 'Inscris-toi aux tournois, crée ou rejoins ton équipe avec son référent, et suis les scores en direct.'
	},
	{
		selector: 'a.nav-item[href^="/dashboard/players"]',
		title: 'Joueurs & Équipes 👥',
		content: 'Retrouve la liste des participants, consulte les équipes de la LAN et échange en messagerie.'
	},
	{
		selector: 'a.nav-item[href^="/dashboard/ai"]',
		title: 'Assistant IA 🤖',
		content: 'Pose tes questions sur la LAN, les règles des jeux ou le réseau à notre bot local.'
	},
	{
		selector: 'a.nav-item[href^="/dashboard/map"]',
		title: 'Plan de Salle 📍',
		content: 'Repère ta place et visualise la disposition interactive de la salle.'
	},
	{
		selector: 'a.user-profile',
		title: 'Profil & Filtre anti-propos 🛡️',
		content: 'Personnalise ton profil, vérifie ton équipe et active le filtre anti-propos insultants à ta convenance.'
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
