"""
Génère l'ensemble des icônes et splash screens natifs Android & iOS (ainsi que
les icônes Store 1024x1024 et 512x512) en rastérisant le tracé vectoriel du logo
Alambic (favicon.svg : goutte/alambic inclinée à -15°, liquide #3b82f6 et bulles)
sur le fond sombre officiel d'Alanbix (#0f172a).
"""
from pathlib import Path
from PIL import Image, ImageDraw, ImageFilter

ROOT = Path(__file__).resolve().parent.parent
FRONTEND_DIR = ROOT / "frontend"
BG_COLOR = (15, 23, 42)        # #0f172a (--bg-primary), splash screens
ADAPTIVE_RADIUS = 0.28          # inside the 0.305 safe circle of a 108dp adaptive icon
ICON_BG = (255, 255, 255)      # launcher and store icons: white plate like system apps
ACCENT_BLUE = (59, 130, 246)   # #3b82f6 (--accent)


LOGO_MASTER = FRONTEND_DIR / "resources" / "logo-symbol-2048.png"


def _master_geometry():
    """
    The logo is an open circle with a square corner attached at the bottom left.
    In favicon.svg the circle's centre lands exactly on the centre of the 80x80
    viewBox, so it is the centre of the master image. Returns that centre and the
    distance to the farthest visible pixel (the tip of the corner).
    """
    master = Image.open(LOGO_MASTER).convert("RGBA")
    w, h = master.size
    cx, cy = w / 2, h / 2
    px = master.getchannel("A").load()
    r = max(
        ((x - cx) ** 2 + (y - cy) ** 2) ** 0.5
        for y in range(0, h, 4) for x in range(0, w, 4) if px[x, y] > 40
    ) + 6
    return master, cx, cy, r


def place_symbol(canvas_px: int, radius_ratio: float, shadow: bool = False) -> Image.Image:
    """
    Transparent canvas with the logo's circle centred, scaled so the whole logo
    (corner tip included) fits in a circle of radius radius_ratio * canvas_px:
    launchers crop icons to circles, so this keeps the tip visible.
    With shadow, a soft drop shadow sits under the logo for depth.
    The source is frontend/resources/logo-symbol-2048.png, a browser rendering of
    frontend/static/favicon.svg: re-render it whenever the logo changes.
    """
    master, cx, cy, r = _master_geometry()
    scale = (radius_ratio * canvas_px) / r
    sym = master.resize((max(1, round(master.width * scale)), max(1, round(master.height * scale))), Image.Resampling.LANCZOS)
    pos = (round(canvas_px / 2 - cx * scale), round(canvas_px / 2 - cy * scale))
    out = Image.new("RGBA", (canvas_px, canvas_px), (0, 0, 0, 0))
    if shadow:
        sh_alpha = Image.new("L", (canvas_px, canvas_px), 0)
        sh_alpha.paste(sym.getchannel("A").point(lambda a: int(a * 0.28)), (pos[0], pos[1] + round(canvas_px * 0.018)))
        sh_alpha = sh_alpha.filter(ImageFilter.GaussianBlur(canvas_px * 0.022))
        shade = Image.new("RGBA", (canvas_px, canvas_px), (15, 23, 42, 255))
        shade.putalpha(sh_alpha)
        out.alpha_composite(shade)
    out.alpha_composite(sym, pos)
    return out


def make_monochrome(size: int) -> Image.Image:
    """Android 13 themed icon layer: the symbol as a single-colour silhouette."""
    fg = place_symbol(size, ADAPTIVE_RADIUS)  # no shadow: the system recolours it
    white = Image.new("RGBA", fg.size, (255, 255, 255, 255))
    white.putalpha(fg.getchannel("A"))
    return white


def make_square_icon(size: int, circular_mask: bool = False) -> Image.Image:
    canvas = Image.new("RGBA", (size, size), ICON_BG + (255,))
    canvas.alpha_composite(place_symbol(size, 0.34, shadow=True))

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
    return place_symbol(size, ADAPTIVE_RADIUS, shadow=True)


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

