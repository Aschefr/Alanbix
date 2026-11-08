/**
 * Title and text of a notification in the language of whoever reads it.
 * The server stores one language only, the LAN's. Notifications built with localized_text()
 * (data.i18n), match-ready and AI failure ones carry what is needed to rewrite them;
 * older ones are shown as stored. A body without a key is someone's own message, kept as is.
 */
export function localizedNotif(category, data, title, body, tFunc) {
	const i18n = data?.i18n;
	if (i18n?.title) {
		const text = tFunc(i18n.title, i18n.params || {});
		return {
			title: i18n.icon ? `${i18n.icon} ${text}` : text,
			body: i18n.body ? tFunc(i18n.body, i18n.params || {}) : body
		};
	}
	if (category === 'match_ready' && data?.opponent && data?.tournament_name) {
		return {
			title: `⚔️ ${tFunc('notif_match_ready_title')}`,
			body: tFunc('notif_match_ready_body', { opponent: data.opponent, tournament: data.tournament_name })
		};
	}
	if (data?.error && data?.tournament_name) {
		return {
			title: `⚠️ ${tFunc('notif_ai_failed_title', { tournament: data.tournament_name })}`,
			body: `${tFunc('notif_ai_failed_body')}\n${data.error_detail || ''}`.trim()
		};
	}
	return { title, body };
}
