<script>
	import Icon from '$lib/components/Icon.svelte';
	import { onMount } from 'svelte';
	import { api } from '$lib/api';
	import { t } from '$lib/i18nStore';

	export let toast = (msg, type) => {};

	let awardsList = [];
	let awardsLoading = false;
	// which awards have their text form open
	let openKeys = {};
	function toggleOpen(key) { openKeys = { ...openKeys, [key]: !openKeys[key] }; }

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

<div class="awards-page">
	<!-- Actions and explanation -->
	<section class="aw-top glass">
		<div class="aw-top-row">
			<div class="flex-row items-center gap-3">
				<div class="list-icon"><Icon name="gift" size={20} /></div>
				<div>
					<h2>{$t("admin_awards_title")}</h2>
					<span class="list-sub">{$t("admin_awards_subtitle")}</span>
				</div>
			</div>
			<div class="aw-actions">
				<button class="btn-primary" on:click={triggerSync} disabled={awardsLoading}>
					{$t('admin_awards_btn_recalc')}
				</button>
				<button class="btn-success" on:click={sendAwardsNotifications} disabled={awardsLoading}>
					{$t('admin_awards_btn_broadcast')}
				</button>
			</div>
		</div>

		<details class="awards-help">
			<summary><Icon name="info" size={14} /> {$t('admin_awards_help_title')}</summary>
			<div class="aw-help-body text-sm">
				<p>{$t('admin_awards_desc1')}</p>
				<p>{$t('admin_awards_desc2')}</p>
				<p class="text-dim text-xs aw-note aw-note-accent">
					<span class="btn-ic"><Icon name="lightbulb" size={14} /> {$t('admin_awards_interpolation_tip')}</span>
				</p>
				<p class="text-dim text-xs aw-note aw-note-ok">
					{$t('admin_awards_desc4')}
				</p>
			</div>
		</details>
	</section>

	<!-- List of automated awards: one compact row each, the text form opens on demand -->
	<section class="list glass">
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

		<div class="aw-grid">
			{#each awardsList as award, ai (award.key)}
				<article class="aw-card" class:open={openKeys[award.key]} class:won={award.has_recipient}>
					<div class="aw-row">
						<span class="aw-emoji" aria-hidden="true">{getAwardEmoji(award.key)}</span>
						<div class="aw-main">
							<h3>
								{award.title}
								{#if award.custom_title !== null || award.custom_description !== null}
									<span class="aw-custom" title={$t('admin_awards_customised')} aria-label={$t('admin_awards_customised')}></span>
								{/if}
							</h3>
							<p class="aw-crit">{award.criteria}</p>
						</div>
						<div class="aw-winner">
							{#if award.has_recipient}
								<span class="status-pill-sm running">
									<span class="btn-ic"><Icon name="user" size={13} /> {award.recipient_name}</span>
								</span>
								{#if award.stats_label}
									<span class="aw-stats">{award.stats_label}</span>
								{/if}
							{:else}
								<span class="status-pill-sm closed">{$t('admin_awards_none')}</span>
							{/if}
						</div>
						<button type="button" class="aw-edit" aria-expanded={!!openKeys[award.key]} aria-label={$t('admin_tourneys_tooltip_edit')} title={$t('admin_tourneys_tooltip_edit')} on:click={() => toggleOpen(award.key)}>
							<Icon name={openKeys[award.key] ? 'chevron-up' : 'pencil'} size={15} />
						</button>
					</div>

					{#if openKeys[award.key]}
						<div class="aw-form">
							<div class="edit-field full-width">
								<label class="compact-label" for="award-title-{ai}">{$t("admin_awards_edit_title")}</label>
								<input id="award-title-{ai}" type="text" bind:value={award.title} placeholder={award.default_title} class="award-input" />
							</div>
							<div class="edit-field full-width">
								<label class="compact-label" for="award-desc-{ai}">{$t("admin_awards_edit_desc")}</label>
								<textarea id="award-desc-{ai}" bind:value={award.description} placeholder={award.default_description} rows="2" class="award-textarea"></textarea>
							</div>
							<div class="aw-form-actions">
								{#if award.custom_title !== null || award.custom_description !== null}
									<button class="btn-secondary btn-xs" on:click={() => restoreDefaultText(award.key)}>
										{$t("admin_awards_restore_default")}
									</button>
								{/if}
								<button class="btn-primary btn-xs" on:click={() => saveAwardText(award.key, award.title, award.description)}>
									{$t("admin_awards_btn_save")}
								</button>
							</div>
						</div>
					{/if}
				</article>
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
	.awards-page { display: flex; flex-direction: column; gap: 1rem; }
	.aw-top { padding: 1.1rem 1.5rem; display: flex; flex-direction: column; gap: 0.75rem; }
	.aw-top-row { display: flex; align-items: center; justify-content: space-between; gap: 1rem; flex-wrap: wrap; }
	.aw-top-row h2 { margin: 0; font-size: var(--fs-section); }
	.aw-actions { display: flex; gap: 0.6rem; flex-wrap: wrap; }
	.aw-actions button { padding: 0.55rem 1rem; }
	.awards-help summary { display: inline-flex; align-items: center; gap: 0.4rem; cursor: pointer; font-weight: 600; font-size: 0.85rem; color: var(--text-dim); padding: 0.25rem 0; }
	.awards-help[open] summary { color: var(--text-main); }
	.aw-help-body { display: flex; flex-direction: column; gap: 0.8rem; margin-top: 0.75rem; }
	.aw-note { margin: 0; padding-left: 0.5rem; }
	.aw-note-accent { border-left: 2px solid var(--accent); }
	.aw-note-ok { border-left: 2px solid var(--success); }
	@media (max-width: 700px) {
		.aw-top { padding: 0.9rem 1rem; }
		.aw-actions { width: 100%; }
		.aw-actions button { flex: 1 1 100%; }
	}
	.list { padding: 1.25rem 1.5rem; display: flex; flex-direction: column; }
	.list-header h2 { margin: 0; font-size: var(--fs-section); }
	.list-sub { font-size: 0.875rem; color: var(--text-dim); }
	.list-header { display: flex; justify-content: space-between; align-items: center; padding-bottom: 1rem; margin-bottom: 1rem; border-bottom: 1px solid var(--glass-border); }
	.list-icon { width: 40px; height: 40px; flex-shrink: 0; display: flex; align-items: center; justify-content: center; background: var(--accent-soft); color: var(--accent); border-radius: var(--radius-lg); }
	.badge-count { font-size: 0.75rem; background: var(--accent-soft); color: var(--accent); padding: 0.2rem 0.6rem; border-radius: 4px; font-weight: 800; border: 1px solid var(--accent); }
	.compact-label { font-size: 0.85rem; font-weight: 600; color: var(--text-dim);  margin: 0; }
	.status-pill-sm { font-size: 0.75rem; font-weight: 700; text-transform: uppercase; letter-spacing: 0.05em; padding: 0.15rem 0.6rem; border-radius: 20px; }
	.status-pill-sm.running { background: var(--accent-soft); color: var(--accent); border: 1px solid color-mix(in srgb, var(--accent) 30%, transparent); }
	.status-pill-sm.closed { background: rgba(139,92,246,0.1); color: #a78bfa; border: 1px solid rgba(139,92,246,0.2); opacity: 0.7; }
	.empty-list { display: flex; flex-direction: column; align-items: center; justify-content: center; padding: 3rem 1rem; gap: 0.5rem; grid-column: 1 / -1; }
	.empty-icon { display: inline-flex; color: var(--text-muted); opacity: 0.6; }
	.empty-list p { color: var(--text-dim); font-weight: 600; margin: 0; }

	/* one compact row per award */
	.aw-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 0.6rem; align-items: start; }
	@media (max-width: 1100px) { .aw-grid { grid-template-columns: minmax(0, 1fr); } }
	.aw-card { border-radius: 12px; border: 1px solid var(--glass-border); background: var(--hover-tint); overflow: hidden; }
	.aw-card.open { grid-column: 1 / -1; border-color: color-mix(in srgb, var(--accent) 45%, transparent); }
	.aw-row { display: grid; grid-template-columns: auto minmax(0, 1fr) auto auto; align-items: center; gap: 0.2rem 0.8rem; padding: 0.7rem 0.9rem; }
	.aw-emoji { font-size: 1.7rem; line-height: 1; width: 2.2rem; text-align: center; }
	.aw-main { min-width: 0; }
	.aw-main h3 { margin: 0; font-size: 0.95rem; font-weight: 700; color: var(--text-main); display: flex; align-items: center; gap: 0.4rem; }
	.aw-custom { width: 8px; height: 8px; border-radius: 50%; background: var(--accent); flex-shrink: 0; }
	.aw-crit { margin: 0.15rem 0 0; font-size: 0.78rem; font-style: italic; color: var(--text-dim); line-height: 1.3; }
	.aw-winner { display: flex; flex-direction: column; align-items: flex-end; gap: 0.15rem; min-width: 0; }
	.aw-stats { font-size: 0.75rem; font-weight: 700; color: var(--accent); }
	.aw-edit { width: 34px; height: 34px; display: inline-flex; align-items: center; justify-content: center; border-radius: 8px; border: 1px solid var(--glass-border); background: var(--surface-sunken); color: var(--text-dim); cursor: pointer; }
	.aw-edit:hover, .aw-edit[aria-expanded="true"] { color: var(--accent); border-color: var(--accent); }
	@media (max-width: 600px) {
		.aw-row { grid-template-columns: auto minmax(0, 1fr) auto; }
		.aw-winner { grid-column: 2 / 3; grid-row: 2; align-items: flex-start; flex-direction: row; flex-wrap: wrap; gap: 0.4rem; margin-top: 0.2rem; }
		.aw-edit { grid-column: 3; grid-row: 1; }
	}
	.aw-form { display: flex; flex-direction: column; gap: 0.7rem; padding: 0.2rem 0.9rem 0.9rem; border-top: 1px solid var(--glass-border); padding-top: 0.8rem; }
	.aw-form-actions { display: flex; justify-content: flex-end; gap: 0.5rem; }
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
