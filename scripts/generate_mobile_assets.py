"""
Génère l'ensemble des icônes et splash screens natifs Android & iOS (ainsi que
les icônes Store 1024x1024 et 512x512) en rastérisant le tracé vectoriel du logo
Alambic (favicon.svg : goutte/alambic inclinée à -15°, liquide #3b82f6 et bulles)
sur le fond sombre officiel d'Alanbix (#0f172a).
"""
from pathlib import Path
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parent.parent
FRONTEND_DIR = ROOT / "frontend"
BG_COLOR = (15, 23, 42)        # #0f172a (--bg-primary), splash screens
ICON_BG = (255, 255, 255)      # launcher and store icons: white plate like system apps
ACCENT_BLUE = (59, 130, 246)   # #3b82f6 (--accent)


LOGO_MASTER = FRONTEND_DIR / "resources" / "logo-symbol-2048.png"


def _master_geometry():
    """Alpha-weighted centre of the logo and the radius of the smallest circle
    around that centre that contains every visible pixel."""
    master = Image.open(LOGO_MASTER).convert("RGBA")
    alpha = master.getchannel("A")
    w, h = master.size
    px = alpha.load()
    sx = sy = n = 0
    pts = []
    for y in range(0, h, 4):
        for x in range(0, w, 4):
            if px[x, y] > 40:
                sx += x; sy += y; n += 1; pts.append((x, y))
    cx, cy = sx / n, sy / n
    r = max(((x - cx) ** 2 + (y - cy) ** 2) ** 0.5 for x, y in pts) + 6
    return master, cx, cy, r


def place_symbol(canvas_px: int, radius_ratio: float) -> Image.Image:
    """
    Transparent canvas with the logo centred on its visual centre, scaled so the
    whole outline (including the rotated bottom-left tip) fits in a circle of
    radius radius_ratio * canvas_px. Launchers crop icons to circles, so fitting
    a circle rather than the bounding box keeps the tip from being cut.
    The source is frontend/resources/logo-symbol-2048.png, a browser rendering of
    frontend/static/favicon.svg: re-render it whenever the logo changes.
    """
    master, cx, cy, r = _master_geometry()
    scale = (radius_ratio * canvas_px) / r
    sym = master.resize((max(1, round(master.width * scale)), max(1, round(master.height * scale))), Image.Resampling.LANCZOS)
    out = Image.new("RGBA", (canvas_px, canvas_px), (0, 0, 0, 0))
    out.alpha_composite(sym, (round(canvas_px / 2 - cx * scale), round(canvas_px / 2 - cy * scale)))
    return out


def make_monochrome(size: int) -> Image.Image:
    """Android 13 themed icon layer: the symbol as a single-colour silhouette."""
    fg = make_adaptive_foreground(size)
    white = Image.new("RGBA", fg.size, (255, 255, 255, 255))
    white.putalpha(fg.getchannel("A"))
    return white


def make_square_icon(size: int, circular_mask: bool = False) -> Image.Image:
    canvas = Image.new("RGBA", (size, size), ICON_BG + (255,))
    canvas.alpha_composite(place_symbol(size, 0.34))

    if circular_mask:
        mask = Image.new("L", (size, size), 0)
        draw = ImageDraw.Draw(mask)
        draw.ellipse((0, 0, size - 1, size - 1), fill=255)
        out = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        out.paste(canvas, (0, 0), mask)
        return out

    return canvas


def make_adaptive_foreground(size: int) -> Image.Image:
    # Adaptive icons are 108dp and only the central 66dp circle (radius 0.305)
    # is guaranteed visible: the whole logo stays inside a 0.26 radius, with breathing room.
    return place_symbol(size, 0.26)


def make_splash(width: int, height: int) -> Image.Image:
    canvas = Image.new("RGBA", (width, height), BG_COLOR + (255,))
    side = min(width, height)
    sym = place_symbol(side, 0.13)
    canvas.alpha_composite(sym, ((width - side) // 2, (height - side) // 2))
    return canvas.convert("RGB")


def main() -> None:
    # 1. Store Master Assets (frontend/resources/)
    res_dir = FRONTEND_DIR / "resources"
    res_dir.mkdir(exist_ok=True)
    icon_1024_rgb = make_square_icon(1024).convert("RGB")
    icon_1024_rgb.save(res_dir / "icon-1024.png", format="PNG")
    icon_512_rgb = make_square_icon(512).convert("RGB")
    icon_512_rgb.save(res_dir / "icon-512.png", format="PNG")
    splash_2732 = make_splash(2732, 2732)
    splash_2732.save(res_dir / "splash-2732.png", format="PNG")

    # 2. iOS Assets
    ios_icon_path = FRONTEND_DIR / "ios" / "App" / "App" / "Assets.xcassets" / "AppIcon.appiconset" / "AppIcon-512@2x.png"
    if ios_icon_path.parent.exists():
        icon_1024_rgb.save(ios_icon_path, format="PNG")

    ios_splash_dir = FRONTEND_DIR / "ios" / "App" / "App" / "Assets.xcassets" / "Splash.imageset"
    if ios_splash_dir.exists():
        for fname in ("splash-2732x2732.png", "splash-2732x2732-1.png", "splash-2732x2732-2.png"):
            splash_2732.save(ios_splash_dir / fname, format="PNG")

    # 3. Android Mipmap Icons
    android_res = FRONTEND_DIR / "android" / "app" / "src" / "main" / "res"
    mipmap_specs = {
        "mipmap-mdpi": (48, 108),
        "mipmap-hdpi": (72, 162),
        "mipmap-xhdpi": (96, 216),
        "mipmap-xxhdpi": (144, 324),
        "mipmap-xxxhdpi": (192, 432),
    }
    for folder, (launcher_px, fg_px) in mipmap_specs.items():
        target_dir = android_res / folder
        if target_dir.exists():
            make_square_icon(launcher_px).save(target_dir / "ic_launcher.png", format="PNG")
            make_square_icon(launcher_px, circular_mask=True).save(
                target_dir / "ic_launcher_round.png", format="PNG"
            )
            make_adaptive_foreground(fg_px).save(target_dir / "ic_launcher_foreground.png", format="PNG")
            make_monochrome(fg_px).save(target_dir / "ic_launcher_monochrome.png", format="PNG")

    adaptive_xml = (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<adaptive-icon xmlns:android="http://schemas.android.com/apk/res/android">\n'
        '    <background android:drawable="@color/ic_launcher_background"/>\n'
        '    <foreground android:drawable="@mipmap/ic_launcher_foreground"/>\n'
        '    <monochrome android:drawable="@mipmap/ic_launcher_monochrome"/>\n'
        "</adaptive-icon>\n"
    )
    for name in ("ic_launcher.xml", "ic_launcher_round.xml"):
        xml_path = android_res / "mipmap-anydpi-v26" / name
        if xml_path.parent.exists():
            xml_path.write_text(adaptive_xml, encoding="utf-8")

    v24_fg = android_res / "drawable-v24" / "ic_launcher_foreground.xml"
    if v24_fg.exists():
        v24_fg.unlink()

    bg_xml = android_res / "values" / "ic_launcher_background.xml"
    if bg_xml.parent.exists():
        bg_xml.write_text(
            '<?xml version="1.0" encoding="utf-8"?>\n'
            "<resources>\n"
            '    <color name="ic_launcher_background">#FFFFFF</color>\n'
            "</resources>\n",
            encoding="utf-8",
        )

    # 4. Android Splash Screens
    for splash_file in android_res.glob("drawable*/splash.png"):
        with Image.open(splash_file) as existing:
            w, h = existing.size
        make_splash(w, h).save(splash_file, format="PNG")

    print("[Alanbix Assets] Generated iOS, Android, and Store icons/splash screens successfully.")


if __name__ == "__main__":
    main()

