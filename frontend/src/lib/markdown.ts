import { marked } from 'marked';

/**
 * Markdown written by organisers (info page, projector text, game and tournament rules).
 * One renderer for the editor preview and for what players see, so the preview is exact.
 * Single line breaks are kept, as admins type them in a plain text field.
 * Only admins can write this content, so the HTML is not sanitised (same as before).
 */
export function renderMarkdown(text: string | null | undefined): string {
	if (!text) return '';
	return marked.parse(text, { breaks: true, async: false }) as string;
}
