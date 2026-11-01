/**
 * Mode Démo Hors-Ligne (Offline Demo Mode) pour Alanbix Mobile Companion.
 * Permet aux testeurs Apple App Store & Google Play Store ainsi qu'aux utilisateurs
 * sans serveur LAN actif d'explorer toutes les fonctionnalités d'Alanbix.
 */

const DEMO_USERS = [
	{ id: 1, username: 'AmifyAdmin', is_admin: true, points: 145, team_name: 'Les Gaulois', seat_id: 'S1', avatar_url: null, avatar_shape: 'circle', ia_blocked: false },
	{ id: 2, username: 'ShadowNinja', is_admin: false, points: 120, team_name: 'CyberWolves', seat_id: 'S2', avatar_url: null, avatar_shape: 'hexagon', ia_blocked: false },
	{ id: 3, username: 'RocketQueen', is_admin: false, points: 110, team_name: 'Les Gaulois', seat_id: 'S3', avatar_url: null, avatar_shape: 'circle', ia_blocked: false },
	{ id: 4, username: 'FragMaster', is_admin: false, points: 95, team_name: 'CyberWolves', seat_id: 'S4', avatar_url: null, avatar_shape: 'square', ia_blocked: false },
	{ id: 5, username: 'PixelHunter', is_admin: false, points: 80, team_name: 'Apex Squad', seat_id: 'S5', avatar_url: null, avatar_shape: 'circle', ia_blocked: false },
	{ id: 6, username: 'GlitchMaster', is_admin: false, points: 65, team_name: 'Apex Squad', seat_id: 'S6', avatar_url: null, avatar_shape: 'hexagon', ia_blocked: false }
];

const DEMO_GAMES = [
	{ id: 1, name: 'Counter-Strike 2', rules: '5v5 Competitive MR12 - BO1 puis Finale BO3', image_url: '' },
	{ id: 2, name: 'Trackmania', rules: 'Time Attack - 15 minutes par circuit (3 maps)', image_url: '' },
	{ id: 3, name: 'Rocket League', rules: '2v2 Soccar Standard - 5 minutes', image_url: '' }
];

const DEMO_TOURNAMENTS = [
	{
		id: 1,
		name: 'Tournoi CS2 Wingman',
		game: 'Counter-Strike 2',
		game_id: 1,
		status: 'RUNNING',
		format: 'SINGLE_ELIMINATION',
		max_players: 16,
		participants_count: 6,
		config: {
			use_teams: true,
			team_size: 2,
			points_distribution: { '1': 50, '2': 30, '3': 15 }
		},
		bracket: {
			rounds: [
				[
					{ id: 'm1', p1: -1, p2: -2, score1: 13, score2: 9, winner: -1, status: 'DONE' },
					{ id: 'm2', p1: -3, p2: null, score1: 1, score2: 0, winner: -3, status: 'DONE' }
				],
				[
					{ id: 'm3', p1: -1, p2: -3, score1: 8, score2: 7, winner: null, status: 'RUNNING' }
				]
			]
		}
	},
	{
		id: 2,
		name: 'Trackmania Cup LAN',
		game: 'Trackmania',
		game_id: 2,
		status: 'OPEN',
		format: 'FFA',
		max_players: 24,
		participants_count: 5,
		config: {
			use_teams: false,
			points_distribution: { '1': 40, '2': 25, '3': 15 }
		},
		bracket: null
	},
	{
		id: 3,
		name: 'Rocket League 2v2',
		game: 'Rocket League',
		game_id: 3,
		status: 'DONE',
		format: 'SINGLE_ELIMINATION',
		max_players: 16,
		participants_count: 6,
		config: {
			use_teams: true,
			team_size: 2,
			points_distribution: { '1': 50, '2': 30, '3': 15 }
		},
		bracket: {
			rounds: [
				[
					{ id: 'rl1', p1: -1, p2: -2, score1: 4, score2: 2, winner: -1, status: 'DONE' }
				]
			]
		}
	}
];

const DEMO_TEAMS = [
	{
		id: 1,
		tournament_id: 1,
		name: 'Les Gaulois',
		captain_id: 1,
		is_locked: true,
		members: [
			{ user_id: 1, username: 'AmifyAdmin', avatar_url: null },
			{ user_id: 3, username: 'RocketQueen', avatar_url: null }
		]
	},
	{
		id: 2,
		tournament_id: 1,
		name: 'CyberWolves',
		captain_id: 2,
		is_locked: true,
		members: [
			{ user_id: 2, username: 'ShadowNinja', avatar_url: null },
			{ user_id: 4, username: 'FragMaster', avatar_url: null }
		]
	},
	{
		id: 3,
		tournament_id: 1,
		name: 'Apex Squad',
		captain_id: 5,
		is_locked: false,
		members: [
			{ user_id: 5, username: 'PixelHunter', avatar_url: null },
			{ user_id: 6, username: 'GlitchMaster', avatar_url: null }
		]
	}
];

let demoPublicMessages = [
	{
		id: 1,
		user_id: 1,
		username: 'AmifyAdmin',
		content: 'Bienvenue sur la démo interactive d’Alanbix LAN ! 🎮',
		created_at: new Date(Date.now() - 1800000).toISOString(),
		reactions: { '🔥': [2, 3] },
		reply_to: null,
		image_path: null
	},
	{
		id: 2,
		user_id: 2,
		username: 'ShadowNinja',
		content: 'Le serveur CS2 est prêt, rejoignez le salon Wingman !',
		created_at: new Date(Date.now() - 900000).toISOString(),
		reactions: { '👍': [1, 4] },
		reply_to: null,
		image_path: null
	},
	{
		id: 3,
		user_id: 3,
		username: 'RocketQueen',
		content: 'Qui est chaud pour un échauffement sur Trackmania après la finale ?',
		created_at: new Date(Date.now() - 300000).toISOString(),
		reactions: { '🏎️': [1, 5] },
		reply_to: null,
		image_path: null
	}
];

let demoRoomLayout = {
	tables: [
		{ id: 'T1', x: 120, y: 120, width: 320, height: 90, label: 'Rangée Alpha' },
		{ id: 'T2', x: 120, y: 280, width: 320, height: 90, label: 'Rangée Beta' }
	],
	seats: [
		{ id: 'S1', x: 160, y: 100, label: 'A1', user_id: 1, username: 'AmifyAdmin' },
		{ id: 'S2', x: 260, y: 100, label: 'A2', user_id: 2, username: 'ShadowNinja' },
		{ id: 'S3', x: 360, y: 100, label: 'A3', user_id: 3, username: 'RocketQueen' },
		{ id: 'S4', x: 160, y: 260, label: 'B1', user_id: 4, username: 'FragMaster' },
		{ id: 'S5', x: 260, y: 260, label: 'B2', user_id: 5, username: 'PixelHunter' },
		{ id: 'S6', x: 360, y: 260, label: 'B3', user_id: 6, username: 'GlitchMaster' }
	],
	furniture: [
		{ id: 'F1', type: 'screen', x: 520, y: 160, width: 40, height: 160, label: 'Écran Géant' }
	]
};

let demoAiMessages: Record<number, Array<any>> = {
	1: [
		{
			id: 1,
			role: 'assistant',
			content: 'Salut Gaulois ! Je suis **Alanbix**, l’assistant IA de ta LAN. Tu explores actuellement le **Mode Démo Hors-Ligne**. Pose-moi une question sur les tournois ou la salle !',
			created_at: new Date(Date.now() - 600000).toISOString()
		}
	]
};

export function handleDemoRequest(rawPath: string, method: string = 'GET', body?: any): any {
	const cleanPath = rawPath.split('?')[0];
	const upperMethod = (method || 'GET').toUpperCase();

	if (cleanPath === '/health') {
		return { status: 'ok', version: '1.20.0-demo' };
	}

	if (cleanPath === '/api/system/discovery' || cleanPath === '/system/discovery') {
		return {
			app: 'Alanbix',
			id: 'com.amifystudio.alanbix',
			name: 'Alanbix Demo LAN',
			hostname: 'demo.alanbix.local',
			ip: '127.0.0.1',
			port: 41481,
			version: '1.20.0',
			lan_wifi_ssids: ['Alanbix-LAN-5GHz', 'Alanbix-LAN-2.4GHz'],
			status: 'ok'
		};
	}

	if (cleanPath.startsWith('/check-username/')) {
		return { exists: true };
	}

	if (cleanPath === '/token' || cleanPath === '/register') {
		return { access_token: 'demo-alanbix-token', token_type: 'bearer' };
	}

	if (cleanPath === '/me') {
		return { ...DEMO_USERS[0] };
	}

	if (cleanPath === '/me/points-history' || cleanPath.endsWith('/points-history')) {
		return {
			total_points: 95,
			history: [
				{
					tournament_name: 'Rocket League 2v2',
					game_name: 'Rocket League',
					rank: 1,
					total: 50,
					placement_pts: 30,
					participation_pts: 10,
					score_pts: 10,
					live: false,
					team_name: 'Alpha Team',
					tournament_id: 1
				},
				{
					tournament_name: 'Quiz Gaming LAN',
					game_name: 'Culture Geek',
					rank: 1,
					total: 45,
					placement_pts: 25,
					participation_pts: 10,
					score_pts: 10,
					live: false,
					tournament_id: 2
				}
			],
			awards: [
				{
					id: 1,
					award_key: 'premier',
					title: 'Grand Champion',
					description: 'A remporté la 1ère place du tournoi Rocket League',
					created_at: new Date(Date.now() - 7200000).toISOString()
				},
				{
					id: 2,
					award_key: 'bourreau',
					title: 'Bourreau de la LAN',
					description: 'A éliminé plus de 10 adversaires en compétition',
					created_at: new Date(Date.now() - 3600000).toISOString()
				},
				{
					id: 3,
					award_key: 'team',
					title: 'Esprit d\'Équipe',
					description: 'A mené son équipe à la victoire avec brio',
					created_at: new Date(Date.now() - 1800000).toISOString()
				}
			]
		};
	}

	if (cleanPath === '/dashboard/stats') {
		return {
			tournaments: DEMO_TOURNAMENTS.length,
			players: DEMO_USERS.length,
			games: DEMO_GAMES.length,
			active: 1,
			event_name: 'Alanbix LAN (Démo)',
			team_scoring_mode: 'weighted',
			lan_multilingual: true,
			lan_default_language: 'fr',
			lan_wifi_ssids: ['Alanbix-LAN-5GHz', 'Alanbix-LAN-2.4GHz'],
			leaderboard: DEMO_USERS.map((u, idx) => ({
				username: u.username,
				points: u.points,
				team_name: u.team_name,
				avatar_url: u.avatar_url,
				avatar_shape: u.avatar_shape,
				rank: idx + 1,
				participations: 3
			}))
		};
	}

	if (cleanPath === '/dashboard/team-leaderboard') {
		return [
			{ team_name: 'Les Gaulois', points: 255, members_count: 2, rank: 1, members: ['AmifyAdmin', 'RocketQueen'] },
			{ team_name: 'CyberWolves', points: 215, members_count: 2, rank: 2, members: ['ShadowNinja', 'FragMaster'] },
			{ team_name: 'Apex Squad', points: 145, members_count: 2, rank: 3, members: ['PixelHunter', 'GlitchMaster'] }
		];
	}

	if (cleanPath === '/dashboard/info') {
		return {
			content: '# 🎮 Bienvenue sur Alanbix LAN (Mode Démo)\n\nVous naviguez actuellement dans le **mode démonstration hors-ligne** de l’application mobile compagnon **Alanbix**.\n\n### Fonctionnalités disponibles :\n- 🏆 **Tournois & Arbres de matchs** en temps réel\n- 🗺️ **Plan interactif de la salle** avec attribution des postes\n- 💬 **Chat public & Messagerie entre joueurs**\n- 🤖 **Assistant IA Alanbix** dédié aux joueurs de la LAN',
			spectator_content: '# 🏆 Alanbix LAN - Écran Spectateur'
		};
	}

	if (cleanPath === '/dashboard/info/files') {
		return [];
	}

	if (cleanPath === '/tournaments') {
		return [...DEMO_TOURNAMENTS];
	}

	if (cleanPath === '/tournaments/games') {
		return [...DEMO_GAMES];
	}

	const tournMatch = cleanPath.match(/^\/tournaments\/(\d+)$/);
	if (tournMatch) {
		const tid = Number(tournMatch[1]);
		return DEMO_TOURNAMENTS.find((t) => t.id === tid) || DEMO_TOURNAMENTS[0];
	}

	if (cleanPath.match(/^\/tournaments\/\d+\/participants$/)) {
		return DEMO_USERS.map((u) => ({
			id: u.id,
			user_id: u.id,
			username: u.username,
			points: u.points,
			team_name: u.team_name,
			avatar_url: u.avatar_url
		}));
	}

	if (cleanPath.match(/^\/tournaments\/\d+\/teams$/)) {
		return [...DEMO_TEAMS];
	}

	if (cleanPath.match(/^\/tournaments\/\d+\/standings$/)) {
		return {
			standings: [
				{ entity_id: -1, name: 'Les Gaulois', rank: 1, total: 50 },
				{ entity_id: -3, name: 'Apex Squad', rank: 2, total: 30 },
				{ entity_id: -2, name: 'CyberWolves', rank: 3, total: 15 }
			]
		};
	}

	if (cleanPath === '/room/layout') {
		return demoRoomLayout;
	}

	if (cleanPath === '/room/users' || cleanPath === '/players' || cleanPath === '/admin/users') {
		return [...DEMO_USERS];
	}

	if (cleanPath === '/room/seating-locked') {
		return { locked: false };
	}

	if (cleanPath === '/players/teams') {
		return ['Les Gaulois', 'CyberWolves', 'Apex Squad'];
	}

	if (cleanPath === '/players/messages/unread-count' || cleanPath === '/players/group/unread-count' || cleanPath === '/notifications/unread-count') {
		return { count: 0, unread_count: 0 };
	}

	if (cleanPath === '/players/messages/conversations') {
		return [
			{ peer_id: 2, username: 'ShadowNinja', last_message: 'Prêt pour la demi-finale ?', unread_count: 0, updated_at: new Date().toISOString() }
		];
	}

	if (cleanPath === '/players/group/channels') {
		return [
			{ name: 'Les Gaulois', unread_count: 0, last_message: 'Go sur le serveur TS !' }
		];
	}

	if (cleanPath.startsWith('/players/messages/')) {
		return [
			{ id: 1, sender_id: 2, receiver_id: 1, content: 'Prêt pour la demi-finale ?', created_at: new Date(Date.now() - 600000).toISOString(), reactions: {} }
		];
	}

	if (cleanPath.startsWith('/players/group/channel/')) {
		return [
			{ id: 1, sender_id: 3, sender_username: 'RocketQueen', content: 'Go sur le serveur TS !', created_at: new Date(Date.now() - 300000).toISOString(), reactions: {} }
		];
	}

	if (cleanPath === '/public-chat/config') {
		return { enabled: true, max_length: 500, allow_images: true };
	}

	if (cleanPath === '/public-chat/pinned') {
		return { pinned_message: demoPublicMessages[0] };
	}

	if (cleanPath === '/public-chat/messages') {
		if (upperMethod === 'POST' && body) {
			const payload = typeof body === 'string' ? JSON.parse(body) : body;
			const newMsg = {
				id: Date.now(),
				user_id: 1,
				username: 'AmifyAdmin',
				content: payload.content || '',
				created_at: new Date().toISOString(),
				reactions: {},
				reply_to: null,
				image_path: null
			};
			demoPublicMessages = [...demoPublicMessages, newMsg];
			return newMsg;
		}
		return [...demoPublicMessages];
	}

	if (cleanPath === '/notifications/archived-count') {
		return { count: 0 };
	}

	if (cleanPath === '/notifications' && rawPath.includes('archived=true')) {
		return [];
	}

	if (cleanPath === '/notifications') {
		return [
			{
				id: 1,
				type: 'match_ready',
				category: 'match_ready',
				title: '⚔️ Match prêt — Tournoi CS2 Wingman !',
				content: 'Votre match contre Apex Squad est prêt à démarrer.',
				message: 'Votre match contre Apex Squad est prêt à démarrer.',
				link: '/dashboard/tournaments/1',
				is_read: false,
				created_at: new Date(Date.now() - 1200000).toISOString()
			}
		];
	}

	if (cleanPath === '/notifications/missed') {
		return {
			since: new Date(Date.now() - 86400000).toISOString(),
			count: 1,
			events: [
				{
					id: 'notif_1',
					notification_id: 1,
					category: 'match_ready',
					title: '⚔️ Match prêt — Tournoi CS2 Wingman !',
					body: 'Votre match contre Apex Squad est prêt à démarrer.',
					link: '/dashboard/tournaments/1',
					data: { tournament_id: 1 },
					created_at: new Date(Date.now() - 1200000).toISOString()
				}
			]
		};
	}

	if (cleanPath === '/notifications/test') {
		return { status: 'sent', notification_id: 999 };
	}

	if (cleanPath === '/devices') {
		return {
			id: 1,
			token: 'dev_demo_token_alanbix',
			platform: 'demo',
			name: 'Demo Mobile Companion'
		};
	}

	if (cleanPath === '/devices/me') {
		return [
			{
				id: 1,
				platform: 'demo',
				name: 'Demo Mobile Companion',
				has_push_token: false,
				created_at: new Date().toISOString(),
				last_seen: new Date().toISOString()
			}
		];
	}

	if (cleanPath === '/devices/revoke-token') {
		return { status: 'revoked' };
	}

	if (cleanPath === '/ia/config') {
		return { enabled: true, model: 'alanbix-demo-llm', instances: [{ url: 'http://demo:11434', enabled: true }] };
	}

	if (cleanPath === '/ia/queue/status' || cleanPath === '/ia/queue/admin') {
		return { position: 0, total_pending: 0, processing: 0, entries: [] };
	}

	if (cleanPath === '/ia/call-admin/check-cooldown') {
		return { on_cooldown: false, remaining_seconds: 0 };
	}

	if (cleanPath === '/ia/conversations' || cleanPath === '/ia/admin/conversations') {
		if (upperMethod === 'POST') {
			const newId = Date.now();
			demoAiMessages[newId] = [];
			return { id: newId, title: 'Nouvelle discussion (Démo)', created_at: new Date().toISOString() };
		}
		return [
			{ id: 1, title: 'Stratégie LAN & Horaires', created_at: new Date(Date.now() - 600000).toISOString(), updated_at: new Date().toISOString() }
		];
	}

	const aiConvMatch = cleanPath.match(/^\/ia\/conversations\/(\d+)\/messages$/);
	if (aiConvMatch) {
		const cid = Number(aiConvMatch[1]);
		return demoAiMessages[cid] || demoAiMessages[1];
	}

	if (cleanPath === '/changelog') {
		return [
			{
				tag_name: 'v1.20.0',
				published_at: '2026-10-28',
				name: 'Version 1.20.0',
				body: '- Application compagnon mobile Android & iOS\n- Découverte automatique du serveur Alanbix sur le réseau local (LAN)\n- Mode Démo hors-ligne intégré'
			}
		];
	}

	if (cleanPath === '/i18n/languages') {
		return { languages: ['fr', 'en', 'es'] };
	}

	if (cleanPath.startsWith('/api/i18n/')) {
		return {};
	}

	return { status: 'ok', success: true };
}

