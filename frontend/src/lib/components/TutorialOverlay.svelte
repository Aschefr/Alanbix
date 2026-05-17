<script>
	import { onMount, onDestroy } from 'svelte';
	import { tutorialActive, tutorialStepIndex, TUTORIAL_STEPS, stopTutorial, nextTutorialStep, prevTutorialStep } from '$lib/tutorialStore';

	let active = false;
	let stepIndex = 0;
	
	let targetRect = null;
	let windowWidth = typeof window !== 'undefined' ? window.innerWidth : 1000;
	let windowHeight = typeof window !== 'undefined' ? window.innerHeight : 1000;

	// Floating panel coordinates
	let panelX = 0;
	let panelY = 0;

	const PADDING = 8;

	// Subscriptions
	const unsubActive = tutorialActive.subscribe(v => {
		active = v;
		if (active) setTimeout(updatePosition, 100);
	});
	const unsubStep = tutorialStepIndex.subscribe(v => {
		stepIndex = v;
		if (active) setTimeout(updatePosition, 100);
	});

	function updatePosition() {
		if (!active || typeof document === 'undefined') return;
		
		const step = TUTORIAL_STEPS[stepIndex];
		const el = document.querySelector(step.selector);
		
		if (el) {
			const rect = el.getBoundingClientRect();
			targetRect = {
				x: rect.x - PADDING,
				y: rect.y - PADDING,
				w: rect.width + PADDING * 2,
				h: rect.height + PADDING * 2
			};

			// Calculate panel position (prefer right of the element, otherwise bottom)
			if (targetRect.x + targetRect.w + 350 < windowWidth) {
				panelX = targetRect.x + targetRect.w + 20;
				panelY = targetRect.y;
			} else {
				panelX = Math.max(20, targetRect.x);
				panelY = targetRect.y + targetRect.h + 20;
			}
		} else {
			// Fallback if element not found: center
			targetRect = null;
			panelX = windowWidth / 2 - 160;
			panelY = windowHeight / 2 - 100;
		}
	}

	function onResize() {
		windowWidth = window.innerWidth;
		windowHeight = window.innerHeight;
		updatePosition();
	}

	onMount(() => {
		window.addEventListener('resize', onResize);
		updatePosition();
	});

	onDestroy(() => {
		unsubActive();
		unsubStep();
		if (typeof window !== 'undefined') {
			window.removeEventListener('resize', onResize);
		}
	});

	$: currentStep = TUTORIAL_STEPS[stepIndex];
</script>

{#if active}
<!-- svelte-ignore a11y-no-static-element-interactions -->
<div class="tutorial-overlay" on:click={stopTutorial}>
	<svg class="tutorial-mask" width="100%" height="100%">
		<defs>
			<mask id="cutout">
				<rect x="0" y="0" width="100%" height="100%" fill="white" />
				{#if targetRect}
					<rect 
						x={targetRect.x} 
						y={targetRect.y} 
						width={targetRect.w} 
						height={targetRect.h} 
						rx="8" 
						fill="black" 
					/>
				{/if}
			</mask>
		</defs>
		<rect x="0" y="0" width="100%" height="100%" fill="rgba(0,0,0,0.85)" mask="url(#cutout)" />
		
		{#if targetRect}
			<rect 
				x={targetRect.x} 
				y={targetRect.y} 
				width={targetRect.w} 
				height={targetRect.h} 
				rx="8" 
				fill="none" 
				stroke="var(--accent)" 
				stroke-width="2" 
				stroke-dasharray="6 4"
				class="highlight-border"
			/>
		{/if}
	</svg>

	<div 
		class="tutorial-panel glass animate-in" 
		style="left: {panelX}px; top: {panelY}px;"
		on:click|stopPropagation
	>
		<div class="panel-header">
			<h3>{currentStep.title}</h3>
			<span class="step-count">{stepIndex + 1} / {TUTORIAL_STEPS.length}</span>
		</div>
		<p>{currentStep.content}</p>
		
		<div class="panel-actions">
			<button class="btn-link text-dim" on:click={stopTutorial}>Quitter</button>
			<div class="nav-buttons">
				{#if stepIndex > 0}
					<button class="btn-secondary btn-sm" on:click={prevTutorialStep}>Précédent</button>
				{/if}
				<button class="btn-primary btn-sm" on:click={nextTutorialStep}>
					{stepIndex === TUTORIAL_STEPS.length - 1 ? 'Terminer 🎉' : 'Suivant →'}
				</button>
			</div>
		</div>
	</div>
</div>
{/if}

<style>
	.tutorial-overlay {
		position: fixed;
		top: 0;
		left: 0;
		width: 100vw;
		height: 100vh;
		z-index: 9999;
		pointer-events: auto;
		cursor: pointer;
	}

	.tutorial-mask {
		position: absolute;
		top: 0;
		left: 0;
		width: 100%;
		height: 100%;
		pointer-events: none;
	}

	.highlight-border {
		animation: dash 1s linear infinite;
	}

	@keyframes dash {
		to {
			stroke-dashoffset: -10;
		}
	}

	.tutorial-panel {
		position: absolute;
		width: 320px;
		padding: 1.5rem;
		border-radius: 12px;
		background: var(--bg-secondary);
		box-shadow: 0 15px 50px rgba(0,0,0,0.5);
		border: 1px solid var(--accent);
		transition: left 0.3s cubic-bezier(0.4, 0, 0.2, 1), top 0.3s cubic-bezier(0.4, 0, 0.2, 1);
		z-index: 10000;
		cursor: default;
	}

	.panel-header {
		display: flex;
		justify-content: space-between;
		align-items: center;
		margin-bottom: 0.75rem;
	}

	.panel-header h3 {
		margin: 0;
		font-size: 1.1rem;
		color: var(--text-main);
	}

	.step-count {
		font-size: 0.8rem;
		color: var(--accent);
		font-weight: bold;
		background: var(--accent-soft);
		padding: 0.2rem 0.6rem;
		border-radius: 10px;
	}

	.tutorial-panel p {
		margin: 0 0 1.5rem 0;
		font-size: 0.9rem;
		color: var(--text-dim);
		line-height: 1.5;
	}

	.panel-actions {
		display: flex;
		justify-content: space-between;
		align-items: center;
	}

	.nav-buttons {
		display: flex;
		gap: 0.5rem;
	}

	.btn-sm {
		padding: 0.4rem 0.8rem;
		font-size: 0.85rem;
	}
</style>
