<script>
	import { t } from '$lib/i18nStore';

	export let show = false;
	export let title = "Notification";
	export let message = "";
	export let type = "info"; // info, success, error
	export let onConfirm = null;
	export let cancelText = null;
	export let confirmText = null;

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
		<div class="modal-card-global glass" style="width: 420px;" on:click|stopPropagation>
			<header class="modal-header {type}">
				<h3 class="modal-title">{title}</h3>
				<button class="close-btn" on:click={close} aria-label="Fermer">✕</button>
			</header>
			<div class="modal-body">
				<p>{message}</p>
			</div>
			<footer class="modal-footer gap-2">
				{#if onConfirm}
					<button class="btn-secondary" on:click={close}>{cancelText || $t('cancel')}</button>
					<button class="btn-primary {type === 'error' ? 'danger' : ''}" on:click={handleConfirm}>{confirmText || $t('info_confirm')}</button>
				{:else}
					<button class="btn-primary" on:click={close}>{confirmText || $t('modal_ok')}</button>
				{/if}
			</footer>
		</div>
	</div>
{/if}

<style>
	.modal-header {
		padding: 1.1rem 1.5rem;
		display: flex;
		justify-content: space-between;
		align-items: center;
		border-bottom: 1px solid var(--glass-border);
		flex-shrink: 0;
	}
	.modal-header.success { background: rgba(16, 185, 129, 0.12); color: #10b981; border-bottom-color: rgba(16, 185, 129, 0.25); }
	.modal-header.error { background: rgba(239, 68, 68, 0.12); color: var(--danger); border-bottom-color: rgba(239, 68, 68, 0.25); }
	.modal-header.info { background: rgba(59, 130, 246, 0.12); color: var(--accent); border-bottom-color: rgba(59, 130, 246, 0.25); }
	
	.modal-title {
		font-family: var(--font-title);
		font-size: 1.15rem;
		font-weight: 800;
		margin: 0;
	}

	.modal-body {
		padding: 1.75rem 1.5rem;
		font-size: 0.95rem;
		line-height: 1.5;
		color: var(--text-main);
		font-family: var(--font-main);
	}
	.modal-body p { margin: 0; }

	.modal-footer {
		padding: 1rem 1.5rem;
		display: flex;
		justify-content: flex-end;
		border-top: 1px solid var(--glass-border);
		background: var(--surface-sunken);
		flex-shrink: 0;
	}
	.modal-footer button {
		font-family: var(--font-main);
		font-weight: 700;
	}
</style>

