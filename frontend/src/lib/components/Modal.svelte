<script>
	export let show = false;
	export let title = "Notification";
	export let message = "";
	export let type = "info"; // info, success, error
	export let onConfirm = null;

	let overlayMouseDown = false;

	function close() {
		show = false;
	}

	function handleConfirm() {
		if (onConfirm) onConfirm();
		close();
	}

	// Escape key listener for accessibility
	function handleKeydown(e) {
		if (show && e.key === 'Escape') {
			close();
		}
	}

	// Svelte portal action to avoid transform containing block clipping (G-49 / scroll fix)
	function portal(node) {
		document.body.appendChild(node);
		return {
			destroy() {
				if (node.parentNode) {
					node.parentNode.removeChild(node);
				}
			}
		};
	}
</script>

<svelte:window on:keydown={handleKeydown} />

{#if show}
	<!-- svelte-ignore a11y-no-noninteractive-element-interactions -->
	<!-- svelte-ignore a11y-click-events-have-key-events -->
	<div class="modal-overlay-global" use:portal role="dialog" aria-modal="true"
		on:mousedown={(e) => { if (e.target === e.currentTarget) overlayMouseDown = true; }}
		on:mouseup={(e) => { if (overlayMouseDown && e.target === e.currentTarget) close(); overlayMouseDown = false; }}>
		<div class="modal-card-global glass" style="width: 400px;" on:click|stopPropagation>
			<header class="modal-header {type}">
				<h3>{title}</h3>
				<button class="close-btn" on:click={close} aria-label="Fermer">✕</button>
			</header>
			<div class="modal-body">
				<p>{message}</p>
			</div>
			<footer class="modal-footer gap-2">
				<button class="btn-secondary" on:click={close}>Annuler</button>
				{#if onConfirm}
					<button class="btn-primary {type === 'error' ? 'danger' : ''}" on:click={handleConfirm}>Confirmer</button>
				{:else}
					<button class="btn-primary" on:click={close}>D'accord</button>
				{/if}
			</footer>
		</div>
	</div>
{/if}


<style>
	.modal-header { padding: 1rem 1.5rem; display: flex; justify-content: space-between; align-items: center; }
	.modal-header.success { background: rgba(16, 185, 129, 0.2); color: #10b981; }
	.modal-header.error { background: rgba(239, 68, 68, 0.2); color: var(--danger); }
	.modal-header.info { background: rgba(59, 130, 246, 0.2); color: var(--accent); }
	
	.modal-body { padding: 2rem 1.5rem; font-size: 0.95rem; }
	.modal-footer { padding: 1rem; display: flex; justify-content: flex-end; border-top: 1px solid var(--glass-border); }
	
	.close-btn { background: none; border: none; color: var(--text-dim); cursor: pointer; font-size: 1.2rem; }
</style>

