<script>
	import { api } from '$lib/api';
	import { authStore } from '$lib/auth';
	import { getCustomServerUrl, isCapacitorNative } from '$lib/config';
	import ServerConfigModal from '$lib/components/ServerConfigModal.svelte';
	import { onMount } from 'svelte';
	import { goto } from '$app/navigation';
	import { t } from '$lib/i18nStore';
	import Icon from '$lib/components/Icon.svelte';

	let username = '';
	let password = '';
	let mode = 'idle'; // 'idle' | 'login' | 'register'
	let checking = false;
	let error = '';
	let serverDown = false;
	let isDark = true;
	import { themeStore, toggleTheme } from '$lib/theme';

	// A request that never reached a server (wrong or stale address, server off), not an HTTP error
	function isNetworkError(e) {
		return /failed to fetch|networkerror|load failed|network request failed/i.test(e?.message || '');
	}

	async function checkUsername() {
		if (!username.trim()) return;
		error = '';
		serverDown = false;
		checking = true;
		try {
			const res = await api.get(`/check-username/${encodeURIComponent(username.trim())}`);
			mode = res.exists ? 'login' : 'register';
			// Focus password field after transition
			setTimeout(() => {
				const pwInput = document.getElementById('password');
				if (pwInput) pwInput.focus();
			}, 100);
		} catch (e) {
			if (e.message && e.message.includes('429')) {
				// Rate limited, retry after a short delay
				setTimeout(() => checkUsername(), 300);
				return;
			}
			if (isNetworkError(e)) serverDown = true; else error = e.message;
		}
		checking = false;
	}

	async function handleSubmit() {
		error = '';
		serverDown = false;
		if (mode === 'idle') {
			await checkUsername();
			return;
		}
		try {
			if (mode === 'register') {
				await api.post('/register', { username: username.trim(), password });
				await api.login(username.trim(), password);
				// The first account on a new server is the admin: it starts with the guided server setup
				let isAdmin = false;
				try { isAdmin = !!(await api.get('/me')).is_admin; } catch {}
				goto(isAdmin ? '/dashboard/setup' : '/dashboard/welcome', { replaceState: true });
			} else {
				await api.login(username.trim(), password);
				goto('/dashboard', { replaceState: true });
			}
		} catch (e) {
			if (isNetworkError(e)) serverDown = true; else error = e.message;
		}
	}

	function resetToIdle() {
		mode = 'idle';
		password = '';
		error = '';
	}

	$: isDark = $themeStore.theme === 'dark';

	let isCheckingAuth = true;
	let showServerModal = false;
	let currentServerUrl = '';
	let eventName = 'Alanbix LAN';

	onMount(() => {
		currentServerUrl = getCustomServerUrl();
		// Already signed in: switch screen in place (no full page reload)
		if ($authStore) {
			goto('/dashboard', { replaceState: true });
			return;
		}
		// Show the form at once; the event name fills in when the server answers
		isCheckingAuth = false;
		api.get('/dashboard/stats')
			.then((stats) => { eventName = stats.event_name || 'Alanbix LAN'; })
			.catch(() => {
				if (isCapacitorNative() && !currentServerUrl) showServerModal = true;
				else serverDown = true;
			});
	});
</script>

{#if isCheckingAuth}
	<div class="app-loading-screen" style="display:flex;align-items:center;justify-content:center;height:100vh;width:100vw;background:var(--bg-primary);color:var(--text-main);font-weight:700">
		<div style="display:flex;flex-direction:column;align-items:center;gap:1.5rem">
			<div class="logo-alambic loading-logo" style="width:64px;height:64px;">
				<div class="liquid boiling-liquid" style="height:70%"></div>
				<div class="bubble b1"></div>
				<div class="bubble b2"></div>
				<div class="bubble b3"></div>
			</div>
			<span class="loading-text" style="font-size:0.95rem;opacity:0.8;letter-spacing:0.15em;color:var(--accent)">{$t('loading_distillation')}</span>
		</div>
	</div>
{:else}
<main class="login-page">
	<button class="login-theme-toggle" on:click={() => toggleTheme($themeStore.theme)} title={isDark ? $t('theme_switch_light') : $t('theme_switch_dark')} aria-label={isDark ? $t('theme_switch_light') : $t('theme_switch_dark')}>
		<Icon name={isDark ? 'sun' : 'moon'} size={18} />
	</button>
	<div class="login-card glass" class:register-mode={mode === 'register'}>
		<h1 class="title-premium">Alanbix</h1>
		<div style="font-size: 0.75rem; text-transform: uppercase; letter-spacing: 0.05em; color: var(--accent); margin-top: -0.5rem; margin-bottom: 0.8rem; font-weight: 700;">
			🎮 {eventName}
		</div>
		<p class="subtitle" class:subtitle-register={mode === 'register'}>
			{#if mode === 'register'}
				✨ {$t('register_subtitle')}
			{:else}
				{$t('login_subtitle')}
			{/if}
		</p>

		{#if serverDown}
			<div class="server-down" role="alert">
				<Icon name="alert-triangle" size={18} />
				<div class="sd-text">
					<strong>{$t('login_server_down')}</strong>
					<span>{currentServerUrl ? $t('login_server_down_saved', { url: currentServerUrl }) : $t('login_server_down_hint')}</span>
				</div>
				<button type="button" class="sd-btn" on:click={() => (showServerModal = true)}>
					<Icon name="search" size={14} /> {$t('login_server_search')}
				</button>
			</div>
		{/if}
		{#if error}
			<p class="error-msg">{error}</p>
		{/if}

		<form on:submit|preventDefault={handleSubmit}>
			<div class="input-group">
				<label for="username">{$t('login_pseudo_label')}</label>
				<div class="username-row">
					<input
						type="text"
						id="username"
						bind:value={username}
						placeholder={$t('login_pseudo_placeholder')}
						required
						disabled={mode !== 'idle'}
						on:keydown={(e) => { if (e.key === 'Enter' && mode === 'idle') { e.preventDefault(); checkUsername(); } }}
					/>
					{#if mode !== 'idle'}
						<button type="button" class="btn-change-pseudo" on:click={resetToIdle} title={$t('login_change_pseudo')} aria-label={$t('login_change_pseudo')}>
							✏️
						</button>
					{/if}
				</div>
			</div>

			{#if mode !== 'idle'}
				<div class="input-group password-slide">
					<label for="password">
						{mode === 'register' ? $t('register_password_label') : $t('login_password_label')}
					</label>
					<input type="password" id="password" bind:value={password} placeholder="••••••••" required />
				</div>
			{/if}

			<button type="submit" class="btn-primary" class:btn-register={mode === 'register'} disabled={checking}>
				{#if checking}
					<span class="spinner"></span> {$t('login_checking')}
				{:else if mode === 'register'}
					{$t('register_submit')}
				{:else if mode === 'login'}
					{$t('login_submit')}
				{:else}
					{$t('login_next')} →
				{/if}
			</button>
		</form>

		{#if mode !== 'idle'}
			<div class="toggle-mode">
				<button on:click={resetToIdle}>← {$t('login_change_pseudo')}</button>
			</div>
		{/if}
	</div>
	<div class="server-config-footer">
		<button type="button" class="btn-server-config" on:click={() => (showServerModal = true)}>
			📡 {currentServerUrl ? $t('login_server_current', { url: currentServerUrl }) : $t('login_server_default')}
		</button>
	</div>
	<ServerConfigModal bind:isOpen={showServerModal} />
</main>
{/if}

<style>
	.login-page {
		flex-direction: column;
		display: flex;
		align-items: center;
		justify-content: center;
		flex-grow: 1;
		padding: 2rem;
	}

	.login-card {
		width: 100%;
		max-width: 400px;
		padding: 2.5rem;
		text-align: center;
		box-shadow: 0 25px 50px -12px rgba(0, 0, 0, 0.5);
		transition: border-color 0.3s ease, box-shadow 0.3s ease, background 0.3s ease;
	}

	/* ═══ Register Mode Visual Transition ═══ */
	.login-card.register-mode {
		border-color: rgba(34, 197, 94, 0.35);
		box-shadow:
			0 25px 50px -12px rgba(0, 0, 0, 0.5),
			0 0 30px rgba(34, 197, 94, 0.12),
			inset 0 1px 0 rgba(34, 197, 94, 0.15);
		background: linear-gradient(
			180deg,
			rgba(34, 197, 94, 0.06) 0%,
			var(--glass-bg) 100%
		);
	}

	:global([data-theme="light"]) .login-card.register-mode {
		border-color: rgba(22, 163, 74, 0.4);
		box-shadow:
			0 25px 50px -12px rgba(0, 0, 0, 0.1),
			0 0 30px rgba(22, 163, 74, 0.15),
			inset 0 1px 0 rgba(22, 163, 74, 0.2);
		background: linear-gradient(
			180deg,
			rgba(22, 163, 74, 0.08) 0%,
			var(--glass-bg) 100%
		);
	}

	h1 {
		font-size: 3rem;
		margin: 0;
	}

	.subtitle {
		color: var(--text-dim);
		margin-bottom: 2rem;
		font-size: 0.9rem;
		transition: color 0.3s ease;
	}

	.subtitle-register {
		color: var(--success);
		font-weight: 600;
		font-size: 1rem;
	}

	.server-down { display: flex; align-items: center; gap: 0.6rem; flex-wrap: wrap; text-align: left; margin-bottom: 1rem; padding: 0.7rem 0.8rem; border-radius: var(--radius-md); font-size: 0.8125rem; color: var(--text-main); background: color-mix(in srgb, var(--warning) 12%, transparent); border: 1px solid color-mix(in srgb, var(--warning) 45%, transparent); }
	.server-down > :global(svg) { color: var(--warning); flex-shrink: 0; }
	.sd-text { display: flex; flex-direction: column; gap: 0.15rem; flex: 1 1 12rem; min-width: 0; overflow-wrap: anywhere; }
	.sd-text span { color: var(--text-dim); }
	.sd-btn { display: inline-flex; align-items: center; gap: 0.35rem; padding: 0.45rem 0.8rem; border-radius: var(--radius-md); border: 1px solid var(--accent); background: transparent; color: var(--accent); font-weight: 600; font-size: 0.8125rem; cursor: pointer; }
	.sd-btn:hover { background: color-mix(in srgb, var(--accent) 12%, transparent); }
	.error-msg {
		color: var(--danger);
		background: rgba(239, 68, 68, 0.1);
		padding: 0.5rem;
		border-radius: 4px;
		font-size: 0.8rem;
		margin-bottom: 1rem;
	}

	.input-group {
		text-align: left;
		margin-bottom: 1.5rem;
	}

	.username-row {
		display: flex;
		gap: 0.5rem;
		align-items: center;
	}

	.username-row input {
		flex: 1;
	}

	.btn-change-pseudo {
		width: 40px;
		height: 40px;
		border-radius: 8px;
		background: var(--bg-tertiary);
		border: 1px solid var(--glass-border);
		cursor: pointer;
		font-size: 1rem;
		display: flex;
		align-items: center;
		justify-content: center;
		transition: all 0.2s;
		flex-shrink: 0;
	}

	.btn-change-pseudo:hover {
		background: var(--accent);
		border-color: var(--accent);
		transform: scale(1.05);
	}

	label {
		display: block;
		margin-bottom: 0.5rem;
		font-size: 0.8rem;
		color: var(--text-dim);
		text-transform: uppercase;
		letter-spacing: 0.05em;
	}

	input {
		width: 100%;
		padding: 0.75rem;
		background: var(--input-bg);
		border: 1px solid var(--glass-border);
		border-radius: 4px;
		color: var(--input-color);
		outline: none;
		transition: border-color 0.2s;
	}

	input:focus {
		border-color: var(--accent);
		box-shadow: 0 0 0 2px var(--accent-glow);
	}

	input:disabled {
		opacity: 0.7;
		cursor: default;
	}

	/* Password slide-in animation */
	.password-slide {
		animation: slideDown 0.25s ease-out;
	}

	@keyframes slideDown {
		from {
			opacity: 0;
			transform: translateY(-10px);
			max-height: 0;
		}
		to {
			opacity: 1;
			transform: translateY(0);
			max-height: 120px;
		}
	}

	.btn-primary {
		width: 100%;
		padding: 0.75rem;
		background: var(--accent);
		color: white;
		border: none;
		border-radius: 4px;
		font-weight: 600;
		cursor: pointer;
		transition: transform 0.1s, background-color 0.3s, box-shadow 0.3s;
		display: flex;
		align-items: center;
		justify-content: center;
		gap: 0.5rem;
	}

	.btn-primary:hover {
		background-color: #2563eb;
	}

	.btn-primary:active {
		transform: scale(0.98);
	}

	.btn-primary:disabled {
		opacity: 0.7;
		cursor: wait;
	}

	/* Register mode button — green */
	.btn-register {
		background: var(--success);
		box-shadow: 0 4px 14px var(--success-glow);
	}

	.btn-register:hover {
		background-color: #16a34a;
		box-shadow: 0 6px 20px var(--success-glow);
	}

	/* Spinner */
	.spinner {
		width: 16px;
		height: 16px;
		border: 2px solid rgba(255, 255, 255, 0.3);
		border-top-color: white;
		border-radius: 50%;
		animation: spin 0.6s linear infinite;
	}

	@keyframes spin {
		to { transform: rotate(360deg); }
	}

	.toggle-mode {
		margin-top: 1.5rem;
	}

	.toggle-mode button {
		background: none;
		border: none;
		color: var(--text-dim);
		font-size: 0.85rem;
		cursor: pointer;
		text-decoration: underline;
	}

	.toggle-mode button:hover {
		color: var(--text-main);
	}

	.login-theme-toggle {
		position: absolute;
		top: 1.5rem;
		right: 1.5rem;
		width: 42px;
		height: 42px;
		border-radius: 50%;
		background: var(--glass-bg);
		border: 1px solid var(--glass-border);
		backdrop-filter: blur(12px);
		cursor: pointer;
		font-size: 1.2rem;
		display: flex;
		align-items: center;
		justify-content: center;
		transition: all 0.25s ease;
		z-index: 10;
	}
	.login-theme-toggle:hover {
		transform: scale(1.1) rotate(15deg);
		box-shadow: 0 0 15px var(--accent-glow);
		border-color: var(--accent);
	}
	.server-config-footer {
		margin-top: 1rem;
		text-align: center;
	}

	.btn-server-config {
		background: var(--glass-bg);
		border: 1px solid var(--glass-border);
		border-radius: 8px;
		padding: 0.5rem 1rem;
		color: var(--text-dim);
		font-size: 0.8rem;
		cursor: pointer;
		transition: all 0.2s ease;
	}

	.btn-server-config:hover {
		color: var(--text-main);
		border-color: var(--accent);
	}
</style>
