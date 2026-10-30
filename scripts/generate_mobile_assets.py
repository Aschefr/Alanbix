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
BG_COLOR = (15, 23, 42)        # #0f172a (--bg-primary)
ACCENT_BLUE = (59, 130, 246)   # #3b82f6 (--accent)


LOGO_MASTER = FRONTEND_DIR / "resources" / "logo-symbol-2048.png"


def render_alambic_symbol(symbol_px: int) -> Image.Image:
    """
    Returns the Alambic symbol, trimmed to its visible outline and fitted in a
    symbol_px square. The source is frontend/resources/logo-symbol-2048.png, a
    browser rendering of frontend/static/favicon.svg (transparent background):
    re-render it from the SVG whenever the logo changes, so the app icons stay
    identical to the website logo.
    """
    master = Image.open(LOGO_MASTER).convert("RGBA")
    master = master.crop(master.getchannel("A").getbbox())
    scale = symbol_px / max(master.size)
    w, h = max(1, round(master.width * scale)), max(1, round(master.height * scale))
    sym = master.resize((w, h), Image.Resampling.LANCZOS)
    out = Image.new("RGBA", (symbol_px, symbol_px), (0, 0, 0, 0))
    out.alpha_composite(sym, ((symbol_px - w) // 2, (symbol_px - h) // 2))
    return out


def make_monochrome(size: int) -> Image.Image:
    """Android 13 themed icon layer: the symbol as a single-colour silhouette."""
    fg = make_adaptive_foreground(size)
    white = Image.new("RGBA", fg.size, (255, 255, 255, 255))
    white.putalpha(fg.getchannel("A"))
    return white


def make_square_icon(size: int, symbol_ratio: float = 0.66, circular_mask: bool = False) -> Image.Image:
    canvas = Image.new("RGBA", (size, size), BG_COLOR + (255,))
    sym_px = max(32, int(size * symbol_ratio))
    sym = render_alambic_symbol(sym_px)
    offset = ((size - sym_px) // 2, (size - sym_px) // 2)
    canvas.alpha_composite(sym, offset)

    if circular_mask:
        mask = Image.new("L", (size, size), 0)
        draw = ImageDraw.Draw(mask)
        draw.ellipse((0, 0, size - 1, size - 1), fill=255)
        out = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        out.paste(canvas, (0, 0), mask)
        return out

    return canvas


def make_adaptive_foreground(size: int) -> Image.Image:
    canvas = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    # Adaptive icons are 108dp; only the central 66dp circle is always visible.
    # The symbol fills that safe zone (~60% of the layer) like other launcher icons.
    sym_px = max(32, int(size * 0.60))
    sym = render_alambic_symbol(sym_px)
    offset = ((size - sym_px) // 2, (size - sym_px) // 2)
    canvas.alpha_composite(sym, offset)
    return canvas


def make_splash(width: int, height: int) -> Image.Image:
    canvas = Image.new("RGBA", (width, height), BG_COLOR + (255,))
    min_dim = min(width, height)
    sym_px = max(96, int(min_dim * 0.24))
    sym = render_alambic_symbol(sym_px)
    offset = ((width - sym_px) // 2, (height - sym_px) // 2)
    canvas.alpha_composite(sym, offset)
    return canvas.convert("RGB")


def main() -> None:
    # 1. Store Master Assets (frontend/resources/)
    res_dir = FRONTEND_DIR / "resources"
    res_dir.mkdir(exist_ok=True)
    icon_1024_rgb = make_square_icon(1024, symbol_ratio=0.66).convert("RGB")
    icon_1024_rgb.save(res_dir / "icon-1024.png", format="PNG")
    icon_512_rgb = make_square_icon(512, symbol_ratio=0.66).convert("RGB")
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
            '    <color name="ic_launcher_background">#0F172A</color>\n'
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

