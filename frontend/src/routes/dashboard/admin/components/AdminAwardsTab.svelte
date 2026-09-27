<script>
	import { onMount } from 'svelte';
	import { api } from '$lib/api';
	import { t } from '$lib/i18nStore';

	export let toast = (msg, type) => {};

	let awardsList = [];
	let awardsLoading = false;
	let nukeConfirm = { awards: false };
	let nuking = { awards: false };

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
			toast(e.message || "Erreur lors du chargement des prix", 'error');
		} finally {
			awardsLoading = false;
		}
	}

	async function saveAwardText(key, title, description) {
		if (!title.trim()) { toast("Le titre ne peut pas être vide", "error"); return; }
		try {
			await api.put(`/admin/awards/${key}`, {
				title: title.trim(),
				description: description.trim()
			});
			toast("Prix enregistré avec succès !", 'success');
			await loadAwardsTab();
		} catch (e) {
			toast(e.message || "Erreur lors de l'enregistrement du prix", 'error');
		}
	}

	async function restoreDefaultText(key) {
		try {
			await api.delete(`/admin/awards/${key}/text`);
			toast("Texte par défaut restauré !", 'success');
			await loadAwardsTab();
		} catch (e) {
			toast(e.message || "Erreur lors de la restauration", 'error');
		}
	}

	async function triggerSync() {
		awardsLoading = true;
		try {
			awardsList = await api.get('/admin/awards');
			toast("Distinctions recalculées et synchronisées !", 'success');
		} catch (e) {
			toast(e.message || "Erreur de synchronisation", 'error');
		} finally {
			awardsLoading = false;
		}
	}

	async function sendAwardsNotifications() {
		awardsLoading = true;
		try {
			const res = await api.post('/admin/awards/notify');
			toast(`Notifications envoyées à ${res.notified_players_count} joueur(s) !`, 'success');
		} catch (e) {
			toast(e.message || "Erreur lors de l'envoi des notifications", 'error');
		} finally {
			awardsLoading = false;
		}
	}

	async function nukeAwards() {
		nuking.awards = true;
		try {
			const res = await api.delete('/admin/nuke/awards');
			toast(`${res.deleted_awards} prix supprimé(s)`, 'success');
			await loadAwardsTab();
		} catch (e) { toast(e.message, 'error'); }
		nuking.awards = false;
		nukeConfirm.awards = false;
	}
</script>

<div class="admin-grid">
	<!-- Explanation and Sync controls -->
	<section class="wizard glass" style="max-height: 85vh; overflow-y: auto;">
		<div class="list-header">
			<div class="flex-row items-center gap-3">
				<div class="list-icon">🎁</div>
				<div>
					<h2 class="text-accent" style="margin:0">{$t("admin_awards_title")}</h2>
					<span class="text-xs text-dim">{$t("admin_awards_subtitle")}</span>
				</div>
			</div>
		</div>

		<div style="display: flex; flex-direction: column; gap: 1rem; margin-top: 1rem;" class="text-sm">
			<p>{$t('admin_awards_desc1')}</p>
			<p>{$t('admin_awards_desc2')}</p>
			<p class="text-dim text-xs" style="border-left: 2px solid var(--accent); padding-left: 0.5rem;">
				💡 Les descriptions supportent l'interpolation de variables de statistiques liées au vainqueur (ex: <code>{"{"}points{"}"}</code>, <code>{"{"}wins{"}"}</code>, <code>{"{"}matches_played{"}"}</code>, <code>{"{"}team_name{"}"}</code>).
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

		<div style="margin-top: 2rem; border-top: 1px solid rgba(239, 68, 68, 0.2); padding-top: 1rem;">
			{#if nukeConfirm.awards}
				<div class="flex-column gap-2" style="background: rgba(239, 68, 68, 0.08); padding: 0.8rem; border-radius: 8px; border: 1px solid var(--danger);">
					<span class="text-xs text-dim" style="display:block; margin-bottom: 0.5rem; text-align: center; color: var(--danger) !important; font-weight: bold;">{$t("admin_awards_confirm_purge_q")}</span>
					<div style="display: flex; gap: 0.5rem;">
						<button class="btn-danger btn-xs" style="flex:1" on:click={nukeAwards} disabled={nuking.awards}>
							{nuking.awards ? $t('admin_awards_purging') : $t('admin_awards_confirm_purge_yes')}
						</button>
						<button class="btn-secondary btn-xs" style="flex:1" on:click={() => nukeConfirm.awards = false}>
							Annuler
						</button>
					</div>
				</div>
			{:else}
				<button class="btn-danger" style="width: 100%; padding: 0.6rem 1rem;" on:click={() => nukeConfirm.awards = true} disabled={awardsLoading}>
					{$t('admin_awards_btn_purge')}
				</button>
			{/if}
		</div>
	</section>

	<!-- List of automated awards -->
	<section class="list glass" style="max-height: 85vh; overflow-y: auto;">
		<div class="list-header">
			<div class="flex-row items-center gap-3">
				<div class="list-icon">🏆</div>
				<div>
					<h2 style="margin:0">{$t("admin_awards_list")}</h2>
					<span class="text-xs text-dim">{$t("admin_awards_list_sub")}</span>
				</div>
			</div>
			<span class="badge-count">{awardsList.length}</span>
		</div>

		<div class="item-list" style="display: flex; flex-direction: column; gap: 1.2rem;">
			{#each awardsList as award}
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
									👤 {award.recipient_name}
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
							<label class="compact-label" style="font-weight: 700; font-size: 0.75rem; color: var(--text-dim);">{$t("admin_awards_edit_title")}</label>
							<input type="text" bind:value={award.title} placeholder={award.default_title} style="width: 100%; padding: 0.4rem 0.6rem; background: var(--surface-sunken); border: 1px solid var(--glass-border); border-radius: 8px; color: var(--text-main); font-size: 0.85rem;" />
						</div>
						
						<div class="edit-field full-width" style="margin: 0;">
							<label class="compact-label" style="font-weight: 700; font-size: 0.75rem; color: var(--text-dim);">{$t("admin_awards_edit_desc")}</label>
							<textarea bind:value={award.description} placeholder={award.default_description} rows="2" style="width: 100%; padding: 0.4rem 0.6rem; background: var(--surface-sunken); border: 1px solid var(--glass-border); border-radius: 8px; color: var(--text-main); font-size: 0.85rem; font-family: inherit; resize: vertical;"></textarea>
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
					<span class="empty-icon">📭</span>
					<p>{$t('admin_awards_none_available')}</p>
				</div>
			{/each}
		</div>
	</section>
</div>

<style>
	.admin-grid { display: grid; grid-template-columns: minmax(380px, 1fr) 2fr; gap: 2rem; }
	.wizard { padding: 2rem; min-height: 500px; display: flex; flex-direction: column; }
	.list { padding: 2rem; display: flex; flex-direction: column; }
	.list-header { display: flex; justify-content: space-between; align-items: center; padding-bottom: 1rem; margin-bottom: 1rem; border-bottom: 1px solid var(--glass-border); }
	.list-icon { width: 40px; height: 40px; display: flex; align-items: center; justify-content: center; font-size: 1.4rem; background: var(--accent-soft); border-radius: 10px; border: 1px solid rgba(59,130,246,0.15); }
	.badge-count { font-size: 0.7rem; background: var(--accent-soft); color: var(--accent); padding: 0.2rem 0.6rem; border-radius: 4px; font-weight: 800; border: 1px solid var(--accent); }
	.compact-label { font-size: 0.72rem; font-weight: 700; color: var(--text-dim); text-transform: uppercase; letter-spacing: 0.04em; margin: 0; }
	.status-pill-sm { font-size: 0.6rem; font-weight: 700; text-transform: uppercase; letter-spacing: 0.05em; padding: 0.15rem 0.5rem; border-radius: 20px; }
	.status-pill-sm.running { background: var(--accent-soft); color: var(--accent); border: 1px solid rgba(59,130,246,0.2); }
	.status-pill-sm.closed { background: rgba(139,92,246,0.1); color: #a78bfa; border: 1px solid rgba(139,92,246,0.2); }
	.empty-list { display: flex; flex-direction: column; align-items: center; justify-content: center; padding: 3rem 1rem; gap: 0.5rem; }
	.empty-icon { font-size: 2.5rem; opacity: 0.5; }
	.empty-list p { color: var(--text-dim); font-weight: 600; margin: 0; }
</style>
