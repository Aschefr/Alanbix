import { redirect } from '@sveltejs/kit';

// The old standalone tournament page was replaced by the Tournaments page;
// keep old links working by opening it with this tournament selected.
export function load({ params }) {
	throw redirect(307, `/dashboard/tournaments?select=${encodeURIComponent(params.id)}`);
}
