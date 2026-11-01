<script>
	import { onMount } from 'svelte';
	import { goto } from '$app/navigation';
	import { api } from '$lib/api';
	import { t, flagMap, refreshEventName, customPageTitle } from '$lib/i18nStore';
	import Icon from '$lib/components/Icon.svelte';
	import { SETUP_STEPS, loadSetup, saveSetup } from '$lib/adminSetup';
	import StepInfo from './StepInfo.svelte';
	import StepGames from './StepGames.svelte';

	// Steps with their own component expose save(); errors from their actions show under the step
	let stepRef = null;
	const stepToast = (msg, type) => { if (type === 'error') error = msg; };

	let ready = false;
	let setup = { status: 'in_progress', current: 'event', steps: {} };
	let saving = false;
	let error = '';

	// Step 1: event
	let eventName = '';
	let defaultLang = 'fr';
	let languages = ['fr', 'en'];

	// Step 2: network
	let wifiSsids = '';
	let playerUrl = '';
	$: localOnly = /^(https?:\/\/)?(localhost|127\.|\[?::1)/i.test(playerUrl.trim());

	$: index = Math.max(0, SETUP_STEPS.findIndex(s => s.id === setup.current));
	$: step = SETUP_STEPS[index];
	$: doneCount = SETUP_STEPS.filter(s => setup.steps[s.id] === 'done').length;
	$: customPageTitle.set($t('setup_title'));

	onMount(async () => {
		try {
			const me = await api.get('/me');
			if (!me.is_admin) { goto('/dashboard', { replaceState: true }); return; }
		} catch { goto('/', { replaceState: true }); return; }

		setup = await loadSetup();
		if (setup.status !== 'in_progress') setup = { ...setup, status: 'in_progress' };
		try {
			const stats = await api.get('/dashboard/stats');
			eventName = stats.event_name || '';
			defaultLang = stats.lan_default_language || 'fr';
			wifiSsids = (stats.lan_wifi_ssids || []).join(', ');
		} catch {}
		try { languages = (await api.get('/i18n/languages')).languages || languages; } catch {}
		try { playerUrl = (await api.get('/admin/config/player_url'))?.value || ''; } catch {}
		if (!playerUrl) playerUrl = window.location.origin;
		ready = true;
	});

	function goTo(id) {
		setup = { ...setup, current: id };
		saveSetup(setup);
		error = '';
	}

	// Saves what the current step edits; returns false to stay on the step
	async function saveStep() {
		if (step.id === 'event') {
			if (!eventName.trim()) { error = $t('setup_event_name_required'); return false; }
			await api.put('/admin/config/event_name', { value: eventName.trim() });
			await api.put('/admin/config/lan_default_language', { value: defaultLang });
			refreshEventName();
		} else if (step.id === 'network') {
			const list = wifiSsids.split(',').map(s => s.trim()).filter(Boolean);
			await api.put('/admin/config/lan_wifi_ssids', { value: list });
			await api.put('/admin/config/player_url', { value: playerUrl.trim().replace(/\/+$/, '') });
		} else if (stepRef?.save) {
			return await stepRef.save();
		}
		return true;
	}

	async function next(status = 'done') {
		saving = true;
		error = '';
		try {
			if (status === 'done' && !(await saveStep())) { saving = false; return; }
			const following = SETUP_STEPS[index + 1];
			setup = { ...setup, steps: { ...setup.steps, [step.id]: status }, current: following ? following.id : step.id };
			await saveSetup(setup);
		} catch (e) {
			error = e.message || $t('admin_error_save');
		}
		saving = false;
	}

	async function finish(target) {
		setup = { ...setup, status: 'done' };
		await saveSetup(setup);
		goto(target);
	}

	async function skipAll() {
		setup = { ...setup, status: 'skipped' };
		await saveSetup(setup);
		goto('/dashboard/admin');
	}

	let copied = false;
	async function copyUrl() {
		try { await navigator.clipboard.writeText(playerUrl); copied = true; setTimeout(() => copied = false, 2000); } catch {}
	}

	function stepState(id) {
		return setup.steps[id] || 'todo';
	}
</script>

{#if ready}
<div class="setup">
	<header class="setup-head">
		<div>
			<h1>{$t('setup_title')}</h1>
			<p class="lead">{$t('setup_lead')}</p>
		</div>
		<button class="btn-quiet" on:click={skipAll}>{$t('setup_skip_all')}</button>
	</header>

	<div class="setup-body">
		<nav class="rail" aria-label={$t('setup_title')}>
			<ol>
				{#each SETUP_STEPS as s, i}
					<li>
						<button class="rail-item" class:current={s.id === step.id} on:click={() => goTo(s.id)} aria-current={s.id === step.id ? 'step' : undefined}>
							<span class="rail-mark {stepState(s.id)}">
								{#if stepState(s.id) === 'done'}<Icon name="check" size={14} strokeWidth={3} />{:else}{i + 1}{/if}
							</span>
							<span class="rail-text">
								<span class="rail-label">{$t(`setup_step_${s.id}`)}</span>
								{#if s.optional}<span class="rail-hint">{$t('setup_optional')}</span>{/if}
								{#if stepState(s.id) === 'skipped'}<span class="rail-hint">{$t('setup_state_skipped')}</span>{/if}
							</span>
						</button>
					</li>
				{/each}
			</ol>
		</nav>

		<!-- Phone: the rail becomes a progress line -->
		<div class="progress-line" aria-hidden="true">
			<span>{$t('setup_progress', { n: index + 1, total: SETUP_STEPS.length })}</span>
			<div class="bar"><div style="width: {((index + 1) / SETUP_STEPS.length) * 100}%"></div></div>
		</div>

		<section class="panel">
			<div class="panel-head">
				<span class="panel-icon"><Icon name={step.icon} size={22} /></span>
				<div>
					<h2>{$t(`setup_step_${step.id}`)}</h2>
					<p class="panel-desc">{$t(`setup_${step.id}_desc`)}</p>
				</div>
			</div>

			<div class="panel-content">
				{#if step.id === 'event'}
					<label class="field">
						<span class="field-label">{$t('setup_event_name')}</span>
						<input type="text" bind:value={eventName} placeholder={$t('setup_event_name_ph')} maxlength="60" />
					</label>
					<label class="field">
						<span class="field-label">{$t('setup_event_lang')}</span>
						<select bind:value={defaultLang}>
							{#each languages as l}<option value={l}>{flagMap[l] || l.toUpperCase()}</option>{/each}
						</select>
						<span class="field-help">{$t('setup_event_lang_help')}</span>
					</label>

				{:else if step.id === 'network'}
					<label class="field">
						<span class="field-label">{$t('setup_network_ssids')}</span>
						<input type="text" bind:value={wifiSsids} placeholder={$t('setup_network_ssids_ph')} />
						<span class="field-help">{$t('setup_network_ssids_help')}</span>
					</label>
					<label class="field">
						<span class="field-label">{$t('setup_network_url')}</span>
						<input type="url" bind:value={playerUrl} placeholder="http://192.168.1.10:41481" spellcheck="false" /><!-- i18n-ignore -->
						<span class="field-help">{$t('setup_network_url_help')}</span>
						{#if localOnly}<span class="field-warn"><Icon name="alert-triangle" size={14} /> {$t('setup_network_url_local')}</span>{/if}
					</label>

				{:else if step.id === 'recap'}
					<ul class="recap">
						{#each SETUP_STEPS.filter(s => s.id !== 'recap') as s}
							<li>
								<button class="recap-item" on:click={() => goTo(s.id)}>
									<span class="rail-mark {stepState(s.id)}">
										{#if stepState(s.id) === 'done'}<Icon name="check" size={14} strokeWidth={3} />{:else}<Icon name={s.icon} size={14} />{/if}
									</span>
									<span class="recap-label">{$t(`setup_step_${s.id}`)}</span>
									<span class="recap-state {stepState(s.id)}">{$t(`setup_state_${stepState(s.id)}`)}</span>
								</button>
							</li>
						{/each}
					</ul>
					<p class="field-help">{$t('setup_recap_later')}</p>

				{:else if step.id === 'info'}
					<StepInfo bind:this={stepRef} {eventName} {wifiSsids} {playerUrl} />

				{:else if step.id === 'games'}
					<StepGames bind:this={stepRef} toast={stepToast} />

				{:else if step.id === 'invite'}
					<div class="address">
						<code>{playerUrl}</code>
						<button class="btn-secondary" on:click={copyUrl}><Icon name={copied ? 'check' : 'clipboard'} size={16} /> {$t(copied ? 'setup_invite_copied' : 'setup_invite_copy')}</button>
					</div>
					<p class="field-help">{$t('setup_invite_help')}</p>

				{:else}
					<!-- Steps not yet guided here: open the screen that holds the setting -->
					<a class="open-screen" href={step.screen}>
						<Icon name="external-link" size={16} /> {$t(`setup_${step.id}_open`)}
					</a>
				{/if}

				{#if error}<p class="field-error" role="alert">{error}</p>{/if}
			</div>

			<footer class="panel-foot">
				{#if step.id === 'recap'}
					<button class="btn-secondary" on:click={() => finish('/dashboard/admin')}>{$t('setup_finish')}</button>
					<button class="btn-primary" on:click={() => finish('/dashboard/welcome')}>{$t('setup_join_too')}</button>
				{:else}
					{#if index > 0}
						<button class="btn-quiet" on:click={() => goTo(SETUP_STEPS[index - 1].id)}><Icon name="chevron-left" size={16} /> {$t('setup_back')}</button>
					{/if}
					<span class="spacer"></span>
					<button class="btn-quiet" on:click={() => next('skipped')} disabled={saving}>{$t('setup_skip_step')}</button>
					<button class="btn-primary" on:click={() => next('done')} disabled={saving}>
						{saving ? '…' : $t('setup_continue')}
					</button>
				{/if}
			</footer>
		</section>
	</div>
	<p class="setup-foot">{$t('setup_saved_hint', { done: doneCount, total: SETUP_STEPS.length - 1 })}</p>
</div>
{/if}

<style>
	.setup { max-width: 1040px; margin: 0 auto; display: flex; flex-direction: column; gap: 1.5rem; }
	.setup-head { display: flex; justify-content: space-between; align-items: flex-start; gap: 1rem; }
	.setup-head h1 { margin: 0 0 0.35rem; font-size: 1.75rem; font-weight: 800; letter-spacing: -0.02em; }
	.lead { margin: 0; color: var(--text-dim); max-width: 60ch; line-height: 1.5; }

	.setup-body { display: grid; grid-template-columns: 240px 1fr; gap: 1.5rem; align-items: start; }

	.rail ol { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 0.15rem; }
	.rail-item { width: 100%; display: flex; align-items: center; gap: 0.7rem; padding: 0.55rem 0.7rem; border: 1px solid transparent; border-radius: var(--radius-md); background: transparent; color: var(--text-dim); text-align: left; cursor: pointer; font: inherit; transition: background 0.15s, color 0.15s; }
	.rail-item:hover { background: var(--hover-tint); color: var(--text-main); }
	.rail-item.current { background: var(--surface-sunken); border-color: var(--glass-border); color: var(--text-main); }
	.rail-item:focus-visible, .recap-item:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
	.rail-mark { flex-shrink: 0; width: 26px; height: 26px; border-radius: 50%; display: inline-flex; align-items: center; justify-content: center; font-size: 0.78rem; font-weight: 700; border: 1.5px solid var(--glass-border); color: var(--text-dim); font-variant-numeric: tabular-nums; }
	.current .rail-mark { border-color: var(--accent); color: var(--accent); }
	.rail-mark.done { background: var(--accent-solid); border-color: var(--accent-solid); color: white; }
	.rail-mark.skipped { border-style: dashed; }
	.rail-text { display: flex; flex-direction: column; min-width: 0; }
	.rail-label { font-weight: 600; font-size: 0.92rem; }
	.rail-hint { font-size: 0.74rem; color: var(--text-muted); }

	.progress-line { display: none; }

	.panel { border: 1px solid var(--glass-border); border-radius: var(--radius-lg, 16px); background: var(--surface-raised); padding: 1.75rem; display: flex; flex-direction: column; gap: 1.5rem; min-width: 0; }
	.panel-head { display: flex; gap: 1rem; align-items: flex-start; }
	.panel-icon { flex-shrink: 0; width: 44px; height: 44px; border-radius: 12px; display: inline-flex; align-items: center; justify-content: center; background: var(--accent-soft); color: var(--accent); }
	.panel-head h2 { margin: 0 0 0.3rem; font-size: 1.3rem; font-weight: 800; }
	.panel-desc { margin: 0; color: var(--text-dim); line-height: 1.55; max-width: 65ch; }

	.panel-content { display: flex; flex-direction: column; gap: 1.25rem; }
	.field { display: flex; flex-direction: column; gap: 0.4rem; max-width: 520px; }
	.field-label { font-weight: 600; font-size: 0.9rem; }
	.field-help { font-size: 0.82rem; color: var(--text-dim); line-height: 1.5; max-width: 65ch; }
	.field-warn { display: inline-flex; align-items: center; gap: 0.4rem; font-size: 0.82rem; font-weight: 600; color: color-mix(in srgb, var(--warning) 70%, var(--text-main)); }
	.field-error { margin: 0; font-size: 0.85rem; font-weight: 600; color: var(--danger); }

	.open-screen { align-self: flex-start; display: inline-flex; align-items: center; gap: 0.5rem; padding: 0.6rem 1rem; border: 1px solid var(--glass-border); border-radius: var(--radius-md); color: var(--text-main); text-decoration: none; font-weight: 600; }
	.open-screen:hover { border-color: var(--accent); color: var(--accent); }

	.address { display: flex; align-items: center; gap: 0.75rem; flex-wrap: wrap; }
	.address code { padding: 0.6rem 0.9rem; border-radius: var(--radius-md); background: var(--surface-sunken); border: 1px solid var(--glass-border); font-size: 1rem; font-weight: 600; overflow-wrap: anywhere; }
	.address .btn-secondary { display: inline-flex; align-items: center; gap: 0.4rem; color: var(--text-main); }

	.recap { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; border: 1px solid var(--glass-border); border-radius: var(--radius-md); overflow: hidden; }
	.recap li + li { border-top: 1px solid var(--glass-border); }
	.recap-item { width: 100%; display: flex; align-items: center; gap: 0.75rem; padding: 0.7rem 0.9rem; background: transparent; border: none; color: var(--text-main); font: inherit; text-align: left; cursor: pointer; }
	.recap-item:hover { background: var(--hover-tint); }
	.recap-label { flex: 1; font-weight: 600; }
	.recap-state { font-size: 0.8rem; color: var(--text-dim); }
	.recap-state.done { color: var(--success, #16a34a); font-weight: 600; }

	.panel-foot { display: flex; align-items: center; gap: 0.6rem; flex-wrap: wrap; padding-top: 1.25rem; border-top: 1px solid var(--glass-border); }
	.panel-foot .btn-primary:first-of-type:last-child { margin-left: auto; }
	.spacer { flex: 1; }
	.btn-quiet { display: inline-flex; align-items: center; gap: 0.3rem; background: transparent; border: 1px solid transparent; color: var(--text-dim); padding: 0.55rem 0.9rem; border-radius: var(--radius-md); font: inherit; font-weight: 600; cursor: pointer; }
	.btn-quiet:hover:not(:disabled) { color: var(--text-main); background: var(--hover-tint); }
	.btn-quiet:disabled, .panel-foot .btn-primary:disabled { opacity: 0.55; cursor: default; }

	.setup-foot { margin: 0; text-align: center; font-size: 0.8rem; color: var(--text-muted); }

	@media (max-width: 900px) {
		.setup { gap: 1rem; }
		.setup-head { flex-direction: column; gap: 0.5rem; }
		.setup-head h1 { font-size: 1.35rem; }
		.setup-head .btn-quiet { align-self: flex-start; padding-left: 0; }
		.setup-body { grid-template-columns: 1fr; gap: 0.75rem; }
		.rail { display: none; }
		.progress-line { display: flex; flex-direction: column; gap: 0.4rem; font-size: 0.8rem; font-weight: 600; color: var(--text-dim); }
		.bar { height: 4px; border-radius: 2px; background: var(--glass-border); overflow: hidden; }
		.bar div { height: 100%; background: var(--accent-solid); transition: width 0.3s cubic-bezier(0.16, 1, 0.3, 1); }
		.panel { padding: 1.1rem; gap: 1.1rem; }
		.panel-icon { width: 38px; height: 38px; }
		.panel-head h2 { font-size: 1.15rem; }
		.panel-foot .spacer { display: none; }
		.panel-foot { justify-content: flex-end; }
		.panel-foot > .btn-quiet:first-child { margin-right: auto; }
		.panel-foot .btn-primary { flex: 1 1 100%; order: 3; }
	}
</style>
