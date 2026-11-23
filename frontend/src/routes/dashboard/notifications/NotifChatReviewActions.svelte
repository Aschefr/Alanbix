<script>
	// Under an alert of the AI's chat review: an administrator silences the player, extends the
	// silence or lifts it, without leaving the notifications (same route as the administration's mute).
	import { api } from '$lib/api';
	import { t } from '$lib/i18nStore';
	import Icon from '$lib/components/Icon.svelte';

	export let review; // { user_id, username, is_admin }

	let busy = false;
	let result = '';
	let failed = false;

	async function mute(minutes) {
		busy = true;
		failed = false;
		try {
			await api.post(`/public-chat/mute/${review.user_id}`, { duration_minutes: minutes });
			result = minutes > 0
				? $t('chat_review_done_muted', { username: review.username, n: minutes })
				: $t('chat_review_done_unmuted', { username: review.username });
		} catch (e) {
			failed = true;
			result = $t('chat_review_failed', { error: e?.message || e });
		}
		busy = false;
	}
</script>

{#if review?.user_id && !review.is_admin}
	<!-- svelte-ignore a11y-click-events-have-key-events a11y-no-static-element-interactions -->
	<div class="review-actions" on:click|stopPropagation>
		<button class="review-btn" disabled={busy} on:click={() => mute(15)}><Icon name="ban" size={13} /> {$t('chat_review_btn_mute', { n: 15 })}</button>
		<button class="review-btn" disabled={busy} on:click={() => mute(60)}><Icon name="ban" size={13} /> {$t('chat_review_btn_mute', { n: 60 })}</button>
		<button class="review-btn lift" disabled={busy} on:click={() => mute(0)}><Icon name="check" size={13} /> {$t('chat_review_btn_unmute')}</button>
		{#if result}<span class="review-result" class:failed role="status">{result}</span>{/if}
	</div>
{/if}

<style>
	.review-actions { display: flex; flex-wrap: wrap; align-items: center; gap: 0.4rem; margin-top: 0.5rem; }
	.review-btn { display: inline-flex; align-items: center; gap: 0.3rem; padding: 0.3rem 0.6rem; border-radius: 6px; border: 1px solid rgba(239,68,68,0.35); background: rgba(239,68,68,0.1); color: var(--danger, #ef4444); font-size: 0.75rem; font-weight: 700; cursor: pointer; }
	.review-btn.lift { border-color: var(--glass-border); background: var(--glass-bg); color: var(--text-main); }
	.review-btn:hover:not(:disabled) { transform: translateY(-1px); }
	.review-btn:disabled { opacity: 0.5; cursor: default; }
	.review-result { font-size: 0.75rem; color: var(--text-dim); }
	.review-result.failed { color: var(--danger, #ef4444); }
</style>
