<script>
	import Icon from '$lib/components/Icon.svelte';
	import { onMount } from 'svelte';
	import { api } from '$lib/api';
	import { t } from '$lib/i18nStore';

	export let toast = (msg, type) => {};

	let awardsList = [];
	let awardsLoading = false;

	function getAwardEmoji(key) {
		const map = {
			premier: '🏆',
			team: '🛡️',
			bourreau: '⚔️',
			coop: '🤝',
			loup: '🐺',
			participate: '🕊️',
			marathon: '🏃',
			gachette: '🎯',
			passoire: '🥅',
			bye: '🍀',
			suisse: '🇨🇭',
			lb: '🩹'
		};
		return map[key] || '🎁';
	}

	onMount(() => {
		loadAwardsTab();
	});

	export async function loadAwardsTab() {
		awardsLoading = true;
		try {
			awardsList = await api.get('/admin/awards');
		} catch (e) {
			toast(e.message || $t('admin_awards_load_error'), 'error');
		} finally {
			awardsLoading = false;
		}
	}

	async function saveAwardText(key, title, description) {
		if (!title.trim()) { toast($t('admin_awards_title_required'), 'error'); return; }
		try {
			await api.put(`/admin/awards/${key}`, {
				title: title.trim(),
				description: description.trim()
			});
			toast($t('admin_awards_saved'), 'success');
			await loadAwardsTab();
		} catch (e) {
			toast(e.message || $t('admin_awards_save_error'), 'error');
		}
	}

	async function restoreDefaultText(key) {
		try {
			await api.delete(`/admin/awards/${key}/text`);
			toast($t('admin_awards_restored'), 'success');
			await loadAwardsTab();
		} catch (e) {
			toast(e.message || $t('admin_awards_restore_error'), 'error');
		}
	}

	async function triggerSync() {
		awardsLoading = true;
		try {
			awardsList = await api.get('/admin/awards');
			toast($t('admin_awards_synced'), 'success');
		} catch (e) {
			toast(e.message || $t('admin_awards_sync_error'), 'error');
		} finally {
			awardsLoading = false;
		}
	}

	async function sendAwardsNotifications() {
		awardsLoading = true;
		try {
			const res = await api.post('/admin/awards/notify');
			toast($t('admin_awards_notified', { count: res.notified_players_count }), 'success');
		} catch (e) {
			toast(e.message || $t('admin_awards_notify_error'), 'error');
		} finally {
			awardsLoading = false;
		}
	}
</script>

<div class="admin-grid">
	<!-- Explanation and Sync controls -->
	<section class="wizard glass" style="max-height: 85vh; overflow-y: auto;">
		<div class="list-header">
			<div class="flex-row items-center gap-3">
				<div class="list-icon"><Icon name="gift" size={20} /></div>
				<div>
					<h2>{$t("admin_awards_title")}</h2>
					<span class="list-sub">{$t("admin_awards_subtitle")}</span>
				</div>
			</div>
		</div>

		<div style="display: flex; flex-direction: column; gap: 1rem; margin-top: 1rem;" class="text-sm">
			<p>{$t('admin_awards_desc1')}</p>
			<p>{$t('admin_awards_desc2')}</p>
			<p class="text-dim text-xs" style="border-left: 2px solid var(--accent); padding-left: 0.5rem;">
				<span class="btn-ic"><Icon name="lightbulb" size={14} /> {$t('admin_awards_interpolation_tip')}</span>
			</p>
			<p class="text-dim text-xs" style="border-left: 2px solid var(--success); padding-left: 0.5rem; margin-top: 0.2rem;">
				{$t('admin_awards_desc4')}
			</p>
		</div>

		<button class="btn-primary" style="margin-top: 1.5rem; width: 100%; padding: 0.6rem 1rem;" on:click={triggerSync} disabled={awardsLoading}>
			{$t('admin_awards_btn_recalc')}
		</button>

		<button class="btn-success" style="margin-top: 1rem; width: 100%; padding: 0.6rem 1rem;" on:click={sendAwardsNotifications} disabled={awardsLoading}>
			{$t('admin_awards_btn_broadcast')}
		</button>

	</section>

	<!-- List of automated awards -->
	<section class="list glass" style="max-height: 85vh; overflow-y: auto;">
		<div class="list-header">
			<div class="flex-row items-center gap-3">
				<div class="list-icon"><Icon name="trophy" size={20} /></div>
				<div>
					<h2>{$t("admin_awards_list")}</h2>
					<span class="list-sub">{$t("admin_awards_list_sub")}</span>
				</div>
			</div>
			<span class="badge-count">{awardsList.length}</span>
		</div>

		<div class="item-list" style="display: flex; flex-direction: column; gap: 1.2rem;">
			{#each awardsList as award, ai}
				<div class="award-card-editor glass" style="padding: 1.2rem; border-radius: 12px; border: 1px solid var(--glass-border); background: var(--hover-tint); display: flex; flex-direction: column; gap: 1rem;">
					
					<!-- Title Row -->
					<div style="display: flex; justify-content: space-between; align-items: flex-start; gap: 1rem;">
						<div style="flex: 1;">
							<h3 class="text-accent" style="margin: 0; font-size: 1rem; font-weight: 700;">{getAwardEmoji(award.key)} {award.title}</h3>
							<p class="text-xs text-dim" style="margin: 0.2rem 0 0; font-style: italic;">{$t('profile_pts_details')} : {award.criteria}</p>
						</div>
						
						<!-- Recipient Badge -->
						<div style="text-align: right; display: flex; flex-direction: column; align-items: flex-end; min-width: 120px;">
							{#if award.has_recipient}
								<span class="status-pill-sm running" style="font-size: 0.75rem; padding: 0.25rem 0.6rem; font-weight: 700;">
									<span class="btn-ic"><Icon name="user" size={13} /> {award.recipient_name}</span>
								</span>
								{#if award.stats_label}
									<span class="text-xs text-accent" style="font-weight: 700; margin-top: 0.15rem;">
										{award.stats_label}
									</span>
								{/if}
							{:else}
								<span class="status-pill-sm closed" style="font-size: 0.75rem; padding: 0.25rem 0.6rem; opacity: 0.6;">
									{$t('admin_awards_none')}
								</span>
							{/if}
						</div>
					</div>

					<!-- Input Forms -->
					<div style="display: flex; flex-direction: column; gap: 0.8rem;">
						<div class="edit-field full-width" style="margin: 0;">
							<label class="compact-label" for="award-title-{ai}">{$t("admin_awards_edit_title")}</label>
							<input id="award-title-{ai}" type="text" bind:value={award.title} placeholder={award.default_title} class="award-input" />
						</div>
						
						<div class="edit-field full-width" style="margin: 0;">
							<label class="compact-label" for="award-desc-{ai}">{$t("admin_awards_edit_desc")}</label>
							<textarea id="award-desc-{ai}" bind:value={award.description} placeholder={award.default_description} rows="2" class="award-textarea"></textarea>
						</div>
					</div>

					<!-- Action Row -->
					<div style="display: flex; justify-content: flex-end; gap: 0.5rem; align-items: center;">
						{#if award.custom_title !== null || award.custom_description !== null}
							<button class="btn-secondary btn-xs" style="font-size: 0.75rem; padding: 0.3rem 0.6rem;" on:click={() => restoreDefaultText(award.key)}>
								{$t("admin_awards_restore_default")}
							</button>
						{/if}
						<button class="btn-primary btn-xs" style="font-size: 0.75rem; padding: 0.3rem 0.8rem;" on:click={() => saveAwardText(award.key, award.title, award.description)}>
							{$t("admin_awards_btn_save")}
						</button>
					</div>

				</div>
			{:else}
				<div class="empty-list">
					<span class="empty-icon"><Icon name="inbox" size={40} /></span>
					<p>{$t('admin_awards_none_available')}</p>
				</div>
			{/each}
		</div>
	</section>
</div>

<style>
	.admin-grid { display: grid; grid-template-columns: minmax(380px, 1fr) 2fr; gap: 2rem; }
	@media (max-width: 1100px) { .admin-grid { grid-template-columns: minmax(0, 1fr); gap: 1rem; } }
	.wizard { padding: 1.5rem; display: flex; flex-direction: column; }
	.list { padding: 1.5rem; display: flex; flex-direction: column; }
	.list-header h2 { margin: 0; font-size: var(--fs-section); }
	.list-sub { font-size: 0.875rem; color: var(--text-dim); }
	.list-header { display: flex; justify-content: space-between; align-items: center; padding-bottom: 1rem; margin-bottom: 1rem; border-bottom: 1px solid var(--glass-border); }
	.list-icon { width: 40px; height: 40px; flex-shrink: 0; display: flex; align-items: center; justify-content: center; background: var(--accent-soft); color: var(--accent); border-radius: var(--radius-lg); }
	.badge-count { font-size: 0.75rem; background: var(--accent-soft); color: var(--accent); padding: 0.2rem 0.6rem; border-radius: 4px; font-weight: 800; border: 1px solid var(--accent); }
	.compact-label { font-size: 0.85rem; font-weight: 600; color: var(--text-dim);  margin: 0; }
	.status-pill-sm { font-size: 0.75rem; font-weight: 700; text-transform: uppercase; letter-spacing: 0.05em; padding: 0.15rem 0.5rem; border-radius: 20px; }
	.status-pill-sm.running { background: var(--accent-soft); color: var(--accent); border: 1px solid rgba(59,130,246,0.2); }
	.status-pill-sm.closed { background: rgba(139,92,246,0.1); color: #a78bfa; border: 1px solid rgba(139,92,246,0.2); }
	.empty-list { display: flex; flex-direction: column; align-items: center; justify-content: center; padding: 3rem 1rem; gap: 0.5rem; }
	.empty-icon { display: inline-flex; color: var(--text-muted); opacity: 0.6; }
	.empty-list p { color: var(--text-dim); font-weight: 600; margin: 0; }
	.award-input, .award-textarea {
		width: 100%;
		padding: 0.5rem 0.75rem;
		background: var(--input-bg);
		border: 1px solid var(--glass-border);
		border-radius: var(--radius-md);
		color: var(--input-color);
		font-family: var(--font-main);
		font-size: 0.85rem;
		transition: all 0.2s;
		box-sizing: border-box;
	}
	.award-input:focus, .award-textarea:focus {
		outline: none;
		border-color: var(--accent);
		box-shadow: 0 0 0 3px var(--accent-soft);
	}
</style>
