<script>
	import { t } from '$lib/i18nStore';
	import { get } from 'svelte/store';
	import { api } from '$lib/api';
	import { onMount, onDestroy } from 'svelte';
	import { goto } from '$app/navigation';
	import Modal from '$lib/components/Modal.svelte';
	import { wsMessageStore } from '$lib/ws';

	let user = null;
	let teamName = '';
	let saving = false;
	let saved = false;
	let pointsData = null;
	let existingTeams = [];
	let wsUnsub = null;
	let uploadingAvatar = false;

	let pendingFile = null;
	let showCropModal = false;
	let cropZoom = 1.0;
	let cropX = 0;
	let cropY = 0;
	let isDraggingCrop = false;
	let dragStartX = 0;
	let dragStartY = 0;
	let selectedShape = 'circle';
	let cropCanvasElement;
	let cropImageObj = null;
	let bgColor = 'transparent';

	let showModal = false;
	let modalTitle = '';
	let modalMessage = '';
	let modalType = 'info';
	let modalConfirmCallback = null;

	function askConfirm(title, message, type, callback) {
		modalTitle = title;
		modalMessage = message;
		modalType = type;
		modalConfirmCallback = callback;
		showModal = true;
	}

	async function handleAvatarUpload(event) {
		const file = event.target.files[0];
		if (!file) return;

		if (file.size > 10 * 1024 * 1024) {
			alert(get(t)('profile_avatar_too_large'));
			return;
		}

		pendingFile = file;
		
		const reader = new FileReader();
		reader.onload = (e) => {
			cropImageObj = new Image();
			cropImageObj.onload = () => {
				cropZoom = 1.0;
				cropX = 0;
				cropY = 0;
				bgColor = 'transparent';
				selectedShape = user.avatar_shape || 'circle';
				showCropModal = true;
				setTimeout(drawCropCanvas, 50);
			};
			cropImageObj.src = e.target.result;
		};
		reader.readAsDataURL(file);
	}

	function openEditorWithCurrentAvatar() {
		if (!user || !user.avatar_url) return;
		cropImageObj = new Image();
		cropImageObj.crossOrigin = 'anonymous';
		cropImageObj.onload = () => {
			cropZoom = 1.0;
			cropX = 0;
			cropY = 0;
			bgColor = 'transparent';
			selectedShape = user.avatar_shape || 'circle';
			showCropModal = true;
			setTimeout(drawCropCanvas, 50);
		};
		cropImageObj.src = user.avatar_url;
	}

	function handleAvatarChangeInModal(event) {
		const file = event.target.files[0];
		if (!file) return;
		if (file.size > 10 * 1024 * 1024) {
			alert(get(t)('profile_avatar_too_large'));
			return;
		}
		pendingFile = file;
		const reader = new FileReader();
		reader.onload = (e) => {
			cropImageObj = new Image();
			cropImageObj.onload = () => {
				cropZoom = 1.0;
				cropX = 0;
				cropY = 0;
				bgColor = 'transparent';
				selectedShape = selectedShape || user.avatar_shape || 'circle';
				drawCropCanvas();
			};
			cropImageObj.src = e.target.result;
		};
		reader.readAsDataURL(file);
	}

	function drawCropCanvas() {
		if (!cropCanvasElement || !cropImageObj) return;
		const ctx = cropCanvasElement.getContext('2d');
		const width = cropCanvasElement.width;
		const height = cropCanvasElement.height;
		
		ctx.clearRect(0, 0, width, height);
		
		const centerX = width / 2;
		const centerY = height / 2;
		const r = width / 2 - 10;

		// 1. Draw solid background color clipped to shape
		if (bgColor !== 'transparent') {
			ctx.save();
			ctx.beginPath();
			if (selectedShape === 'circle') {
				ctx.arc(centerX, centerY, r, 0, Math.PI * 2);
			} else if (selectedShape === 'rounded') {
				const rx = centerX - r;
				const ry = centerY - r;
				const size = r * 2;
				const radius = 16;
				ctx.moveTo(rx + radius, ry);
				ctx.arcTo(rx + size, ry, rx + size, ry + size, radius);
				ctx.arcTo(rx + size, ry + size, rx, ry + size, radius);
				ctx.arcTo(rx, ry + size, rx, ry, radius);
				ctx.arcTo(rx, ry, rx + size, ry, radius);
			} else {
				const rx = centerX - r;
				const ry = centerY - r;
				const size = r * 2;
				ctx.rect(rx, ry, size, size);
			}
			ctx.closePath();
			ctx.fillStyle = bgColor;
			ctx.fill();
			ctx.restore();
		}
		
		// 2. Draw the image (clipped to the shape as well)
		ctx.save();
		ctx.beginPath();
		if (selectedShape === 'circle') {
			ctx.arc(centerX, centerY, r, 0, Math.PI * 2);
		} else if (selectedShape === 'rounded') {
			const rx = centerX - r;
			const ry = centerY - r;
			const size = r * 2;
			const radius = 16;
			ctx.moveTo(rx + radius, ry);
			ctx.arcTo(rx + size, ry, rx + size, ry + size, radius);
			ctx.arcTo(rx + size, ry + size, rx, ry + size, radius);
			ctx.arcTo(rx, ry + size, rx, ry, radius);
			ctx.arcTo(rx, ry, rx + size, ry, radius);
		} else {
			const rx = centerX - r;
			const ry = centerY - r;
			const size = r * 2;
			ctx.rect(rx, ry, size, size);
		}
		ctx.closePath();
		ctx.clip();
		
		const imgRatio = cropImageObj.width / cropImageObj.height;
		let imgW = width;
		let imgH = height;
		if (cropImageObj.width > cropImageObj.height) {
			imgH = width / imgRatio;
		} else {
			imgW = height * imgRatio;
		}
		
		const sw = imgW * cropZoom;
		const sh = imgH * cropZoom;
		const x = centerX - sw / 2 + cropX;
		const y = centerY - sh / 2 + cropY;
		
		ctx.drawImage(cropImageObj, x, y, sw, sh);
		ctx.restore();
		
		// 3. Draw semi-transparent overlay outside the shape
		ctx.fillStyle = 'rgba(15, 23, 42, 0.7)';
		ctx.beginPath();
		ctx.rect(width, 0, -width, height);
		
		if (selectedShape === 'circle') {
			ctx.arc(centerX, centerY, r, 0, Math.PI * 2, false);
		} else if (selectedShape === 'rounded') {
			const rx = centerX - r;
			const ry = centerY - r;
			const size = r * 2;
			const radius = 16;
			ctx.moveTo(rx + radius, ry);
			ctx.arcTo(rx + size, ry, rx + size, ry + size, radius);
			ctx.arcTo(rx + size, ry + size, rx, ry + size, radius);
			ctx.arcTo(rx, ry + size, rx, ry, radius);
			ctx.arcTo(rx, ry, rx + size, ry, radius);
		} else {
			const rx = centerX - r;
			const ry = centerY - r;
			const size = r * 2;
			ctx.rect(rx, ry, size, size);
		}
		ctx.closePath();
		ctx.fill();
		
		ctx.strokeStyle = '#3b82f6';
		ctx.lineWidth = 2;
		ctx.beginPath();
		if (selectedShape === 'circle') {
			ctx.arc(centerX, centerY, r, 0, Math.PI * 2);
		} else if (selectedShape === 'rounded') {
			const rx = centerX - r;
			const ry = centerY - r;
			const size = r * 2;
			const radius = 16;
			ctx.moveTo(rx + radius, ry);
			ctx.arcTo(rx + size, ry, rx + size, ry + size, radius);
			ctx.arcTo(rx + size, ry + size, rx, ry + size, radius);
			ctx.arcTo(rx, ry + size, rx, ry, radius);
			ctx.arcTo(rx, ry, rx + size, ry, radius);
		} else {
			const rx = centerX - r;
			const ry = centerY - r;
			const size = r * 2;
			ctx.rect(rx, ry, size, size);
		}
		ctx.stroke();
	}

	function handleMouseDown(e) {
		e.preventDefault();
		isDraggingCrop = true;
		dragStartX = e.clientX - cropX;
		dragStartY = e.clientY - cropY;
	}
	function handleMouseMove(e) {
		if (!isDraggingCrop) return;
		cropX = e.clientX - dragStartX;
		cropY = e.clientY - dragStartY;
		drawCropCanvas();
	}
	function handleMouseUp() {
		isDraggingCrop = false;
	}
	function handleTouchStart(e) {
		if (e.touches.length === 1) {
			isDraggingCrop = true;
			dragStartX = e.touches[0].clientX - cropX;
			dragStartY = e.touches[0].clientY - cropY;
		}
	}
	function handleTouchMove(e) {
		if (!isDraggingCrop || e.touches.length !== 1) return;
		cropX = e.touches[0].clientX - dragStartX;
		cropY = e.touches[0].clientY - dragStartY;
		drawCropCanvas();
	}

	function handleWheel(e) {
		const zoomFactor = 0.05;
		if (e.deltaY < 0) {
			cropZoom = Math.min(4.0, cropZoom + zoomFactor);
		} else {
			cropZoom = Math.max(0.5, cropZoom - zoomFactor);
		}
		drawCropCanvas();
	}

	function generateCroppedBlob() {
		return new Promise((resolve, reject) => {
			const exportCanvas = document.createElement('canvas');
			exportCanvas.width = 128;
			exportCanvas.height = 128;
			const ctx = exportCanvas.getContext('2d');
			
			// Fill background color if not transparent
			if (bgColor !== 'transparent') {
				ctx.fillStyle = bgColor;
				ctx.fillRect(0, 0, 128, 128);
			}
			
			const scaleFactor = 128 / 280;
			const imgRatio = cropImageObj.width / cropImageObj.height;
			let imgW = 300;
			let imgH = 300;
			if (cropImageObj.width > cropImageObj.height) {
				imgH = 300 / imgRatio;
			} else {
				imgW = 300 * imgRatio;
			}
			
			const sw = imgW * cropZoom * scaleFactor;
			const sh = imgH * cropZoom * scaleFactor;
			const x = 64 - sw / 2 + cropX * scaleFactor;
			const y = 64 - sh / 2 + cropY * scaleFactor;
			
			ctx.drawImage(cropImageObj, x, y, sw, sh);
			
			exportCanvas.toBlob((blob) => {
				if (blob) resolve(blob);
				else reject(new Error("Export failed"));
			}, 'image/png');
		});
	}

	async function saveCroppedAvatar() {
		uploadingAvatar = true;
		showCropModal = false;
		try {
			const croppedBlob = await generateCroppedBlob();
			const formData = new FormData();
			const filename = pendingFile ? (pendingFile.name.split('.').slice(0, -1).join('.') + '.png') : 'avatar.png';
			formData.append('file', croppedBlob, filename);
			
			const uploadRes = await api.upload('/me/avatar', formData);
			await api.put('/me/profile', { avatar_shape: selectedShape });
			
			user.avatar_url = uploadRes.avatar_url;
			user.avatar_shape = selectedShape;
			user = { ...user };
			
			window.dispatchEvent(new CustomEvent('user-updated'));
		} catch (err) {
			alert(get(t)('profile_avatar_save_error') + err.message);
		} finally {
			uploadingAvatar = false;
			pendingFile = null;
		}
	}

	function deleteAvatar() {
		askConfirm(
			get(t)('profile_avatar_delete_title') || 'Supprimer l\'avatar',
			get(t)('profile_avatar_delete_confirm') || 'Voulez-vous vraiment supprimer votre avatar ?',
			'error',
			async () => {
				try {
					await api.delete('/me/avatar');
					user.avatar_url = null;
					user = { ...user };
					window.dispatchEvent(new CustomEvent('user-updated'));
				} catch (err) {
					alert(get(t)('profile_avatar_delete_error') + err.message);
				}
			}
		);
	}

	onMount(async () => {
		user = await api.get('/me');
		teamName = user.team_name || '';
		try {
			pointsData = await api.get('/me/points-history');
		} catch { pointsData = { total_points: 0, history: [] }; }
		try {
			existingTeams = await api.get('/players/teams');
		} catch { existingTeams = []; }

		wsUnsub = wsMessageStore.subscribe(async msg => {
			if (!msg) return;
			if (msg.type === 'tournament_closed' || msg.type === 'tournament_reopened' || msg.type === 'users_updated') {
				try {
					user = await api.get('/me');
					pointsData = await api.get('/me/points-history');
				} catch {}
			}
		});
	});

	onDestroy(() => {
		if (wsUnsub) wsUnsub();
	});

	async function saveProfile() {
		saving = true;
		await api.put('/me/profile', { team_name: teamName });
		user.team_name = teamName;
		
		const trimmedTeam = teamName.trim();
		if (trimmedTeam && !existingTeams.includes(trimmedTeam)) {
			existingTeams = [...existingTeams, trimmedTeam];
		}
		
		saving = false;
		saved = true;
		setTimeout(() => saved = false, 2000);
	}

	function getRankEmoji(rank) {
		if (rank === 1) return '🥇';
		if (rank === 2) return '🥈';
		if (rank === 3) return '🥉';
		return rank ? `#${rank}` : '—';
	}

	function goToTournament(id) {
		goto(`/dashboard/tournaments?select=${id}`);
	}
</script>

{#if user}
<div class="profile-page animate-in">
	<header class="profile-header glass">
		<div class="avatar-container">
			<div class="avatar-lg avatar-shape-{user.avatar_shape || 'circle'}">
				{#if user.avatar_url}
					<img src={user.avatar_url} alt={user.username} class="avatar-img" />
				{:else}
					{user.username[0].toUpperCase()}
				{/if}
				{#if user.avatar_url}
					<button class="avatar-upload-overlay" class:uploading={uploadingAvatar} on:click={openEditorWithCurrentAvatar} disabled={uploadingAvatar} type="button">
						<span>{uploadingAvatar ? '⏳...' : '✏️'}</span>
					</button>
				{:else}
					<label class="avatar-upload-overlay" class:uploading={uploadingAvatar}>
						<span>{uploadingAvatar ? '⏳...' : '✏️'}</span>
						<input type="file" accept="image/*" on:change={handleAvatarUpload} style="display: none;" disabled={uploadingAvatar} />
					</label>
				{/if}
			</div>
			{#if user.avatar_url}
				<button class="btn-danger-icon" on:click={deleteAvatar} title="{$t('profile_avatar_delete_tooltip')}" type="button">🗑️</button>
			{/if}
		</div>
		<div class="header-info">
			<h1 class="title-premium">{user.username}</h1>
			<span class="role-badge {user.is_admin ? 'admin' : 'player'}">
				{user.is_admin ? '👑 ' + $t('role_admin') : '🎮 ' + $t('role_player')}
			</span>
		</div>
		{#if pointsData}
			<div class="total-pts-badge">
			<span class="pts-number">{pointsData.history.reduce((s, h) => s + (h.total || 0), 0)}</span>
				<span class="pts-label">{$t("profile_pts_points")}</span>
			</div>
		{/if}
	</header>

	<div class="profile-grid">
		<section class="profile-card glass">
			<h2 class="card-title">{$t("profile_team_title")}</h2>
			<p class="text-dim text-sm mb-4">{$t("profile_team_desc")}</p>
			<div class="input-row">
				<input 
					type="text" class="input" placeholder="{$t('profile_team_placeholder')}"
					bind:value={teamName} list="existing-teams"
				/>
				<datalist id="existing-teams">
					{#each existingTeams as team}
						<option value={team}></option>
					{/each}
				</datalist>
				<button class="btn-primary" on:click={saveProfile} disabled={saving}>
					{#if saving}
						⏳
					{:else if saved}
						{$t("profile_saved_toast")}
					{:else}
						{$t("profile_btn_save")}
					{/if}
				</button>
			</div>
		</section>

		<section class="profile-card glass">
			<h2 class="card-title">{$t("info_title")}</h2>
			<div class="info-grid">
				<div class="info-item">
					<span class="info-label">{$t("profile_lbl_username")}</span>
					<span class="info-value">{user.username}</span>
				</div>
				<div class="info-item">
					<span class="info-label">{$t("profile_lbl_role")}</span>
					<span class="info-value">{user.is_admin ? $t("role_admin") : $t("role_player")}</span>
				</div>
				<div class="info-item">
					<span class="info-label">{$t("profile_lbl_seat")}</span>
					<span class="info-value">{user.seat_id || $t('profile_no_seat')}</span>
				</div>
				<div class="info-item">
					<span class="info-label">{$t("profile_lbl_team")}</span>
					<span class="info-value">{user.team_name || $t('profile_no_team')}</span>
				</div>
			</div>
			<div style="margin-top: 1.5rem; text-align: right;">
				<button class="btn-secondary" on:click={() => goto('/dashboard/welcome')} style="font-size: 0.8rem; padding: 0.5rem 1rem;">
					{$t("profile_btn_tutorial")}
				</button>
			</div>
		</section>
	</div>

	<!-- Points History -->
	{#if pointsData}
		<section class="points-history glass">
			<h2 class="card-title">{$t("profile_pts_history")}</h2>
			{#if pointsData.history.length === 0}
				<p class="text-dim text-sm">{$t("profile_pts_empty")}</p>
			{:else}
				<div class="history-table-wrap">
					<table class="history-table">
						<thead>
							<tr>
								<th>{$t("profile_pts_rank")}</th>
								<th>{$t("profile_pts_tournament")}</th>
								<th class="pts-col">{$t("profile_pts_details")}</th>
								<th class="pts-col total-col">{$t("dash_modal_points_total")}</th>
								<th></th>
							</tr>
						</thead>
						<tbody>
							{#each pointsData.history as h}
								<tr class="history-row">
									<td class="rank-cell">
										<span class="rank-badge rank-{h.rank}">{getRankEmoji(h.rank)}</span>
									</td>
									<td class="tourney-cell">
										<div class="tourney-name">
											{h.tournament_name}
											{#if h.live}<span class="live-badge">{$t("profile_pts_running")}</span>{/if}
										</div>
										{#if h.game_name}<div class="tourney-game">{h.game_name}</div>{/if}
										{#if h.team_name}<div class="tourney-team">👥 {h.team_name}</div>{/if}
									</td>
									<td class="pts-col">
										<div class="ph-breakdown">
											{#if h.placement_pts > 0}<span class="ph-bp ph-bp-place" title="Placement : top {h.rank}">🏅+{h.placement_pts}</span>{/if}
											<span class="ph-bp ph-bp-parti" title="Points de participation">👤+{h.participation_pts}</span>
											{#if h.score_pts > 0}<span class="ph-bp ph-bp-score" title="Bonus/Score — distribué selon le score cumulé">⚡+{h.score_pts}</span>{/if}
										</div>
									</td>
									<td class="pts-col total-col"><strong>{h.live ? '~' : '+'}{h.total}</strong></td>
									<td>
										<button class="btn-goto" on:click={() => goToTournament(h.tournament_id)} title="{$t('profile_pts_tooltip_view')}">
											→
										</button>
									</td>
								</tr>
							{/each}
						</tbody>
					</table>
				</div>
			{/if}
		</section>
	{/if}
</div>
{/if}

<style>
	.profile-page { display: flex; flex-direction: column; gap: 1.5rem; }
	.profile-header { display: flex; align-items: center; gap: 1.5rem; padding: 2rem; border-radius: 16px; }
	.avatar-container { display: flex; align-items: center; gap: 1rem; position: relative; }
	.avatar-lg { width: 64px; height: 64px; background: var(--bg-tertiary); border-radius: 50%; display: flex; align-items: center; justify-content: center; font-size: 1.8rem; font-weight: 800; color: var(--accent); border: 2px solid var(--accent-soft); position: relative; overflow: hidden; cursor: pointer; }
	.avatar-img { width: 100%; height: 100%; object-fit: cover; border-radius: 50%; }
	.avatar-upload-overlay { position: absolute; top: 0; left: 0; width: 100%; height: 100%; background: rgba(0, 0, 0, 0.6); color: white; font-size: 0.75rem; font-weight: 700; display: flex; align-items: center; justify-content: center; opacity: 0; transition: opacity 0.2s; border-radius: 50%; cursor: pointer; pointer-events: none; border: none; padding: 0; outline: none; }
	.avatar-upload-overlay.uploading { opacity: 1; pointer-events: auto; }
	.avatar-lg:hover .avatar-upload-overlay { opacity: 1; pointer-events: auto; }
	.btn-danger-icon { background: rgba(239, 68, 68, 0.1); border: 1px solid rgba(239, 68, 68, 0.2); color: #ef4444; width: 32px; height: 32px; border-radius: 50%; display: flex; align-items: center; justify-content: center; cursor: pointer; transition: all 0.15s; font-size: 0.9rem; margin-left: -0.5rem; }
	.btn-danger-icon:hover { background: rgba(239, 68, 68, 0.2); transform: scale(1.08); }
	.header-info { flex: 1; }
	.header-info h1 { margin-bottom: 0.3rem; }
	.role-badge { display: inline-block; padding: 0.3rem 0.8rem; border-radius: 20px; font-size: 0.75rem; font-weight: 700; }
	.role-badge.admin { background: rgba(251, 191, 36, 0.1); color: #fbbf24; border: 1px solid rgba(251, 191, 36, 0.2); }
	.role-badge.player { background: rgba(59, 130, 246, 0.1); color: var(--accent); border: 1px solid rgba(59, 130, 246, 0.2); }

	.total-pts-badge { display: flex; flex-direction: column; align-items: center; padding: 0.8rem 1.5rem; background: linear-gradient(135deg, rgba(251,191,36,0.15), rgba(245,158,11,0.08)); border: 1px solid rgba(251,191,36,0.3); border-radius: 16px; }
	.pts-number { font-size: 2rem; font-weight: 900; color: #fbbf24; line-height: 1; }
	.pts-label { font-size: 0.65rem; font-weight: 700; text-transform: uppercase; letter-spacing: 0.1em; color: var(--text-dim); margin-top: 0.2rem; }

	.profile-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 1.5rem; }
	.profile-card { padding: 1.5rem; border-radius: 16px; }
	.card-title { font-size: 0.85rem; font-weight: 800; text-transform: uppercase; letter-spacing: 0.08em; margin-bottom: 0.75rem; color: var(--text-main); }

	.input-row { display: flex; gap: 0.75rem; }
	.input { flex-grow: 1; padding: 0.7rem 1rem; background: var(--input-bg); border: 1px solid var(--glass-border); border-radius: 8px; color: var(--input-color); font-size: 0.9rem; }
	.input:focus { outline: none; border-color: var(--accent); box-shadow: 0 0 0 3px var(--accent-soft); }

	.info-grid { display: flex; flex-direction: column; gap: 0.75rem; }
	.info-item { display: flex; justify-content: space-between; padding: 0.6rem 0; border-bottom: 1px solid var(--glass-border); }
	.info-item:last-child { border-bottom: none; }
	.info-label { font-size: 0.8rem; color: var(--text-muted); }
	.info-value { font-size: 0.85rem; font-weight: 700; }

	/* Points History */
	.points-history { padding: 1.5rem; border-radius: 16px; }
	.history-table-wrap { overflow-x: auto; }
	.history-table { width: 100%; border-collapse: collapse; font-size: 0.85rem; }
	.history-table thead th { font-size: 0.65rem; font-weight: 800; text-transform: uppercase; letter-spacing: 0.08em; color: var(--text-dim); padding: 0.5rem 0.75rem; text-align: left; border-bottom: 2px solid var(--glass-border); }
	.history-table .pts-col { text-align: center; color: var(--text-dim); font-size: 0.8rem; }
	.history-table .total-col { color: #fbbf24; font-weight: 800; }
	.history-row { transition: background 0.15s; }
	.history-row:hover { background: rgba(59,130,246,0.05); }
	.history-row td { padding: 0.75rem; border-bottom: 1px solid var(--glass-border); vertical-align: middle; }

	.rank-cell { text-align: center; }
	.rank-badge { font-size: 1.2rem; }

	.tourney-cell { min-width: 180px; }
	.tourney-name { font-weight: 700; color: var(--text-main); display: flex; align-items: center; gap: 0.5rem; }
	.tourney-game { font-size: 0.7rem; color: var(--text-dim); margin-top: 0.15rem; }
	.tourney-team { font-size: 0.7rem; color: var(--accent); margin-top: 0.1rem; }

	.live-badge { font-size: 0.55rem; font-weight: 800; color: #22c55e; background: rgba(34,197,94,0.1); border: 1px solid rgba(34,197,94,0.2); padding: 0.1rem 0.4rem; border-radius: 10px; animation: pulse-live 2s ease-in-out infinite; white-space: nowrap; }
	@keyframes pulse-live { 0%, 100% { opacity: 1; } 50% { opacity: 0.5; } }

	.btn-goto { background: rgba(59,130,246,0.1); border: 1px solid rgba(59,130,246,0.2); color: var(--accent); padding: 0.3rem 0.6rem; border-radius: 6px; cursor: pointer; font-weight: 800; font-size: 0.8rem; transition: all 0.15s; }
	.btn-goto:hover { background: rgba(59,130,246,0.2); transform: translateX(2px); }

	/* Points history breakdown chips */
	.ph-breakdown { display: flex; gap: 0.3rem; flex-wrap: wrap; justify-content: center; }
	.ph-bp { font-size: 0.65rem; font-weight: 700; padding: 0.1rem 0.4rem; border-radius: 4px; cursor: help; white-space: nowrap; }
	.ph-bp-place { color: #fbbf24; background: rgba(251,191,36,0.1); }
	.ph-bp-score { color: #818cf8; background: rgba(129,140,248,0.1); }
	.ph-bp-parti { color: var(--text-muted); background: var(--surface-sunken); }

	/* Crop Modal Styling */
	.crop-modal-overlay {
		position: fixed;
		top: 0; left: 0; right: 0; bottom: 0;
		background: rgba(0, 0, 0, 0.9);
		display: flex;
		align-items: center;
		justify-content: center;
		z-index: 1000;
		user-select: none;
		-webkit-user-select: none;
		-moz-user-select: none;
		-ms-user-select: none;
	}
	.crop-modal-content {
		padding: 2rem;
		border-radius: var(--radius-xl);
		display: flex;
		flex-direction: column;
		align-items: center;
		gap: 1.5rem;
		max-width: 400px;
		width: 90%;
		border: 1px solid var(--glass-border);
		box-shadow: 0 20px 50px rgba(0, 0, 0, 0.4);
	}
	.crop-modal-title {
		font-size: 1.25rem;
		font-weight: 800;
		text-transform: uppercase;
		letter-spacing: 0.05em;
		background: linear-gradient(135deg, #fff 0%, var(--accent) 100%);
		-webkit-background-clip: text;
		-webkit-text-fill-color: transparent;
		margin: 0;
	}
	.canvas-wrapper {
		background: #090d16;
		border-radius: var(--radius-lg);
		overflow: hidden;
		border: 2px solid var(--glass-border);
		box-shadow: inset 0 0 20px rgba(0,0,0,0.6);
		width: 300px;
		height: 300px;
	}
	.crop-controls {
		width: 100%;
		display: flex;
		flex-direction: column;
		gap: 1.2rem;
	}
	.control-group {
		display: flex;
		flex-direction: column;
		gap: 0.5rem;
	}
	.control-group label {
		font-size: 0.75rem;
		font-weight: 800;
		text-transform: uppercase;
		color: var(--text-dim);
		letter-spacing: 0.05em;
	}
	.control-group input[type="range"] {
		width: 100%;
		accent-color: var(--accent);
		background: var(--surface-sunken);
		height: 6px;
		border-radius: 3px;
		outline: none;
		border: none;
		padding: 0;
	}
	.shape-selector {
		display: grid;
		grid-template-columns: 1fr 1fr 1fr;
		gap: 0.5rem;
	}
	.shape-btn {
		background: var(--surface-sunken);
		border: 1px solid var(--glass-border);
		color: var(--text-dim);
		padding: 0.6rem 0.3rem;
		border-radius: var(--radius-md);
		cursor: pointer;
		font-size: 0.75rem;
		font-weight: 700;
		transition: all 0.2s;
		display: flex;
		align-items: center;
		justify-content: center;
		gap: 0.3rem;
	}
	.shape-btn:hover {
		background: var(--hover-tint);
		color: var(--text-main);
		border-color: var(--text-muted);
	}
	.shape-btn.active {
		background: var(--accent-soft);
		border-color: var(--accent);
		color: var(--accent);
		box-shadow: 0 0 10px rgba(59, 130, 246, 0.2);
	}
	.crop-actions {
		display: flex;
		gap: 1rem;
		width: 100%;
		margin-top: 0.5rem;
	}
	.crop-actions button {
		flex: 1;
		padding: 0.8rem;
		font-weight: 700;
	}
	.bg-color-selector {
		display: flex;
		align-items: center;
		gap: 0.6rem;
		flex-wrap: wrap;
	}
	.color-btn {
		width: 32px;
		height: 32px;
		border-radius: 50%;
		border: 2px solid var(--glass-border);
		cursor: pointer;
		padding: 0;
		transition: all 0.2s;
		box-shadow: 0 2px 6px rgba(0,0,0,0.15);
	}
	.color-btn:hover {
		transform: scale(1.1);
		border-color: var(--text-muted);
	}
	.color-btn.active {
		transform: scale(1.1);
		border-color: var(--accent);
		box-shadow: 0 0 10px var(--accent-glow);
	}
	.transparent-btn {
		background: #eee;
		color: #555;
		font-size: 1.1rem;
		display: flex;
		align-items: center;
		justify-content: center;
	}
	.color-picker-label {
		width: 32px;
		height: 32px;
		border-radius: 50%;
		border: 2px solid var(--glass-border);
		background: var(--surface-sunken);
		cursor: pointer;
		display: flex;
		align-items: center;
		justify-content: center;
		font-size: 1.1rem;
		position: relative;
		transition: all 0.2s;
		box-shadow: 0 2px 6px rgba(0,0,0,0.15);
	}
	.color-picker-label:hover {
		transform: scale(1.1);
		border-color: var(--text-muted);
	}
	.color-picker-input {
		position: absolute;
		opacity: 0;
		width: 100%;
		height: 100%;
		cursor: pointer;
		top: 0;
		left: 0;
		padding: 0;
		border: none;
	}
</style>

{#if showCropModal}
<div class="crop-modal-overlay">
	<div class="crop-modal-content glass animate-in">
		<h3 class="crop-modal-title">{$t("profile_crop_title")}</h3>
		
		<div class="canvas-wrapper">
			<canvas 
				bind:this={cropCanvasElement}
				width="300"
				height="300"
				on:mousedown={handleMouseDown}
				on:mousemove={handleMouseMove}
				on:mouseup={handleMouseUp}
				on:mouseleave={handleMouseUp}
				on:touchstart|preventDefault={handleTouchStart}
				on:touchmove|preventDefault={handleTouchMove}
				on:touchend={handleMouseUp}
				on:wheel|preventDefault={handleWheel}
				style="cursor: move;"
			></canvas>
		</div>
		
		<div class="crop-controls">
			<div class="control-group">
				<label for="zoom-slider">{$t("profile_crop_zoom")}</label>
				<input 
					type="range" 
					id="zoom-slider"
					min="0.5" 
					max="4" 
					step="0.05" 
					bind:value={cropZoom}
					on:input={drawCropCanvas}
				/>
			</div>
			
			<div class="control-group">
				<label>{$t("profile_crop_shape")}</label>
				<div class="shape-selector">
					<button 
						class="shape-btn" 
						class:active={selectedShape === 'circle'} 
						on:click={() => { selectedShape = 'circle'; drawCropCanvas(); }}
						type="button"
					>
						{$t("profile_crop_shape_circle")}
					</button>
					<button 
						class="shape-btn" 
						class:active={selectedShape === 'rounded'} 
						on:click={() => { selectedShape = 'rounded'; drawCropCanvas(); }}
						type="button"
					>
						⬜ {$t("profile_crop_shape_rounded")}
					</button>
					<button 
						class="shape-btn" 
						class:active={selectedShape === 'square'} 
						on:click={() => { selectedShape = 'square'; drawCropCanvas(); }}
						type="button"
					>
						⬛ {$t("profile_crop_shape_square")}
					</button>
				</div>
			</div>

			<div class="control-group">
				<label>{$t("profile_crop_bg")}</label>
				<div class="bg-color-selector">
					<button 
						class="color-btn transparent-btn" 
						class:active={bgColor === 'transparent'} 
						on:click={() => { bgColor = 'transparent'; drawCropCanvas(); }}
						type="button"
						title="{$t('profile_crop_bg_transparent')}"
					>
						🏁
					</button>
					<button 
						class="color-btn" 
						class:active={bgColor === '#ffffff'} 
						style="background-color: #ffffff;"
						on:click={() => { bgColor = '#ffffff'; drawCropCanvas(); }}
						type="button"
						title="{$t('profile_crop_bg_white')}"
					></button>
					<button 
						class="color-btn" 
						class:active={bgColor === '#000000'} 
						style="background-color: #000000;"
						on:click={() => { bgColor = '#000000'; drawCropCanvas(); }}
						type="button"
						title="{$t('profile_crop_bg_black')}"
					></button>
					<button 
						class="color-btn" 
						class:active={bgColor === '#3b82f6'} 
						style="background-color: #3b82f6;"
						on:click={() => { bgColor = '#3b82f6'; drawCropCanvas(); }}
						type="button"
						title="{$t('profile_crop_bg_blue')}"
					></button>
					<button 
						class="color-btn" 
						class:active={bgColor === '#1e293b'} 
						style="background-color: #1e293b;"
						on:click={() => { bgColor = '#1e293b'; drawCropCanvas(); }}
						type="button"
						title="{$t('profile_crop_bg_dark')}"
					></button>
					
					<label class="color-picker-label" title="{$t('profile_crop_bg_custom')}">
						🎨
						<input 
							type="color" 
							bind:value={bgColor} 
							on:input={drawCropCanvas}
							class="color-picker-input"
						/>
					</label>
				</div>
			</div>
			
			<div class="control-group">
				<label>{$t("profile_crop_change_image") || "Changer d'image"}</label>
				<label class="shape-btn" style="cursor: pointer; width: 100%; display: flex; align-items: center; justify-content: center; gap: 0.5rem; box-sizing: border-box;">
					📁 {$t("profile_crop_choose_file") || "Choisir un fichier"}
					<input 
						type="file" 
						accept="image/*" 
						on:change={handleAvatarChangeInModal} 
						style="display: none;" 
					/>
				</label>
			</div>
		</div>
		
		<div class="crop-actions">
			<button class="btn-secondary" on:click={() => showCropModal = false} type="button">{$t("info_btn_cancel")}</button>
			<button class="btn-primary" on:click={saveCroppedAvatar} type="button">{$t("profile_crop_btn_save")}</button>
		</div>
	</div>
</div>
{/if}

<Modal
	bind:show={showModal}
	title={modalTitle}
	message={modalMessage}
	type={modalType}
	onConfirm={modalConfirmCallback}
/>
