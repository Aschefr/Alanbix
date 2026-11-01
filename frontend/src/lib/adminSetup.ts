import { api } from '$lib/api';

// Guided server setup for the first admin. Progress lives in the `admin_setup` system config.
export type SetupState = {
	status: 'in_progress' | 'done' | 'skipped';
	current: string;
	steps: Record<string, 'done' | 'skipped'>;
};

export const SETUP_STEPS = [
	{ id: 'event', icon: 'flag' },
	{ id: 'network', icon: 'wifi' },
	{ id: 'info', icon: 'book-open' },
	{ id: 'games', icon: 'gamepad' },
	{ id: 'ai', icon: 'bot', optional: true },
	{ id: 'map', icon: 'map', optional: true, screen: '/dashboard/map' },
	{ id: 'invite', icon: 'users' },
	{ id: 'recap', icon: 'check-circle' },
];

const FRESH: SetupState = { status: 'in_progress', current: 'event', steps: {} };

/** Returns the saved progress, or null when the setup was never started on this server. */
export async function loadSetupRaw(): Promise<SetupState | null> {
	try {
		const res = await api.get('/admin/config/admin_setup');
		return res?.value ? { ...FRESH, ...res.value } : null;
	} catch {
		return null;
	}
}

export async function loadSetup(): Promise<SetupState> {
	return (await loadSetupRaw()) || { ...FRESH };
}

export async function saveSetup(state: SetupState) {
	try {
		await api.put('/admin/config/admin_setup', { value: state });
	} catch {}
}
