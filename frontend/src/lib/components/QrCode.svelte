<script>
	import qrcode from 'qrcode-generator';

	export let value = '';
	export let size = 200;
	export let label = '';

	// Always dark modules on white with a quiet zone: phone cameras read it in both themes
	const MARGIN = 2;
	let count = 0;
	let path = '';
	$: {
		try {
			const qr = qrcode(0, 'M');
			qr.addData(value || ' ');
			qr.make();
			count = qr.getModuleCount();
			let d = '';
			for (let r = 0; r < count; r++)
				for (let c = 0; c < count; c++)
					if (qr.isDark(r, c)) d += `M${c + MARGIN} ${r + MARGIN}h1v1h-1z`;
			path = d;
		} catch {
			count = 0;
			path = '';
		}
	}
</script>

{#if count}
	<svg class="qr" width={size} height={size} viewBox="0 0 {count + MARGIN * 2} {count + MARGIN * 2}" role="img" aria-label={label || value} shape-rendering="crispEdges">
		<rect width="100%" height="100%" fill="#fff" />
		<path d={path} fill="#000" />
	</svg>
{/if}

<style>
	.qr { display: block; border-radius: 8px; max-width: 100%; height: auto; }
</style>
