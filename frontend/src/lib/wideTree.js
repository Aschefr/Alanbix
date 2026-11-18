// "Tree in large" display preference of the tournaments page: kept per browser, on by default.
const KEY = 'alanbix_wide_tree';

export function getWideTree() {
	return typeof localStorage === 'undefined' || localStorage.getItem(KEY) !== 'false';
}

export function setWideTree(on) {
	localStorage.setItem(KEY, String(!!on));
}
