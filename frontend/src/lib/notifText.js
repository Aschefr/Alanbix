/**
 * Title and text of a notification in the language of whoever reads it.
 * The server stores one language only, the LAN's. Match-ready notifications carry what is
 * needed to rewrite them; older ones, and every other type, are shown as stored.
 */
export function localizedNotif(category, data, title, body, tFunc) {
	if (category === 'match_ready' && data?.opponent && data?.tournament_name) {
		return {
			title: `⚔️ ${tFunc('notif_match_ready_title')}`,
			body: tFunc('notif_match_ready_body', { opponent: data.opponent, tournament: data.tournament_name })
		};
	}
	return { title, body };
}
