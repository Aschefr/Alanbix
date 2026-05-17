<script>
	export let show = false;
	export let title = "Notification";
	export let message = "";
	export let type = "info"; // info, success, error
	export let onConfirm = null;


	function close() {
		show = false;
	}

	function handleConfirm() {
		if (onConfirm) onConfirm();
		close();
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

{#if show}
	<div class="modal-overlay animate-in" use:portal on:click={close}>
		<div class="modal-card glass" on:click|stopPropagation>
			<header class="modal-header {type}">
				<h3>{title}</h3>
				<button class="close-btn" on:click={close}>✕</button>
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
	.modal-overlay {
		position: fixed; top: 0; left: 0; width: 100vw; height: 100vh;
		background: rgba(0, 0, 0, 0.7); backdrop-filter: blur(4px);
		z-index: 9999; display: flex; align-items: center; justify-content: center;
		padding: 2rem;
	}
	.modal-card { 
		width: 400px; max-width: 100%; padding: 0; overflow: hidden; 
		border: 1px solid var(--glass-border); border-radius: 20px;
		box-shadow: 0 20px 50px rgba(0,0,0,0.5);
	}

	.modal-header { padding: 1rem 1.5rem; display: flex; justify-content: space-between; align-items: center; }
	.modal-header.success { background: rgba(16, 185, 129, 0.2); color: #10b981; }
	.modal-header.error { background: rgba(239, 68, 68, 0.2); color: var(--danger); }
	.modal-header.info { background: rgba(59, 130, 246, 0.2); color: var(--accent); }
	
	.modal-body { padding: 2rem 1.5rem; font-size: 0.95rem; }
	.modal-footer { padding: 1rem; display: flex; justify-content: flex-end; border-top: 1px solid var(--glass-border); }
	
	.close-btn { background: none; border: none; color: var(--text-dim); cursor: pointer; font-size: 1.2rem; }
</style>
