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


def render_alambic_symbol(symbol_px: int) -> Image.Image:
    """
    Rastérise avec suréchantillonnage 4x le symbole vectoriel exact de favicon.svg :
      viewBox 0 0 80 80, forme 64x64 centrée et inclinée de -15° :
      - Cercle supérieur + coin inférieur droit arrondi + coin inférieur gauche (rayon 6.4)
      - Liquide bleu (#3b82f6, opacité 0.65) sur les 60% inférieurs
      - Bulles de distillation
      - Contour bleu (#3b82f6, épaisseur 4/64)
    """
    ss = max(512, symbol_px * 4)
    shape_canvas = Image.new("RGBA", (ss, ss), (0, 0, 0, 0))

    # Dimensions de la goutte dans le repère 64 units sur un canevas 80 units
    pad = int(ss * (8.0 / 80.0))
    box_size = ss - 2 * pad
    r_main = box_size // 2
    r_corner = max(4, int(box_size * (6.4 / 64.0)))
    stroke_w = max(4, int(box_size * (4.2 / 64.0)))

    # Masque intérieur de la fiole (3 coins arrondis rayon r_main, coin bas-gauche rayon r_corner)
    mask = Image.new("L", (box_size, box_size), 0)
    mdraw = ImageDraw.Draw(mask)
    mdraw.ellipse((0, 0, box_size - 1, box_size - 1), fill=255)
    mdraw.rounded_rectangle((0, r_main, r_main, box_size - 1), radius=r_corner, fill=255)

    # Liquide bleu (60% inférieurs : y = 25.6/64 -> 0.40)
    liquid_layer = Image.new("RGBA", (box_size, box_size), (0, 0, 0, 0))
    ldraw = ImageDraw.Draw(liquid_layer)
    liquid_top = int(box_size * 0.40)
    ldraw.rectangle((0, liquid_top, box_size, box_size), fill=ACCENT_BLUE + (170,))

    # Bulles de distillation dans le liquide
    bubbles = [
        (0.36, 0.74, 0.055),
        (0.56, 0.66, 0.042),
        (0.45, 0.53, 0.034),
    ]
    for bx, by, br in bubbles:
        cx, cy, cr = int(box_size * bx), int(box_size * by), max(2, int(box_size * br))
        ldraw.ellipse((cx - cr, cy - cr, cx + cr, cy + cr), fill=(255, 255, 255, 195))

    clipped_liquid = Image.new("RGBA", (box_size, box_size), (0, 0, 0, 0))
    clipped_liquid.paste(liquid_layer, (0, 0), mask)

    # Contour vectoriel par différence de masques (extérieur - intérieur érodé de stroke_w)
    inner_mask = Image.new("L", (box_size, box_size), 0)
    idraw = ImageDraw.Draw(inner_mask)
    idraw.ellipse(
        (stroke_w, stroke_w, box_size - 1 - stroke_w, box_size - 1 - stroke_w),
        fill=255,
    )
    idraw.rounded_rectangle(
        (stroke_w, r_main, r_main, box_size - 1 - stroke_w),
        radius=max(2, r_corner - stroke_w // 2),
        fill=255,
    )

    stroke_layer = Image.new("RGBA", (box_size, box_size), ACCENT_BLUE + (255,))
    stroke_alpha = Image.composite(Image.new("L", (box_size, box_size), 0), mask, inner_mask)
    clipped_liquid.paste(stroke_layer, (0, 0), stroke_alpha)

    shape_canvas.alpha_composite(clipped_liquid, (pad, pad))
    # Rotation de -15° dans le sens SVG (horaire inverse PIL = +15°)
    rotated = shape_canvas.rotate(15, resample=Image.Resampling.BICUBIC, expand=False)
    return rotated.resize((symbol_px, symbol_px), Image.Resampling.LANCZOS)


def make_square_icon(size: int, symbol_ratio: float = 0.72, circular_mask: bool = False) -> Image.Image:
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
    sym_px = max(32, int(size * 0.56))
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
    icon_1024_rgb = make_square_icon(1024, symbol_ratio=0.72).convert("RGB")
    icon_1024_rgb.save(res_dir / "icon-1024.png", format="PNG")
    icon_512_rgb = make_square_icon(512, symbol_ratio=0.72).convert("RGB")
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
            make_square_icon(launcher_px, symbol_ratio=0.72).save(target_dir / "ic_launcher.png", format="PNG")
            make_square_icon(launcher_px, symbol_ratio=0.72, circular_mask=True).save(
                target_dir / "ic_launcher_round.png", format="PNG"
            )
            make_adaptive_foreground(fg_px).save(target_dir / "ic_launcher_foreground.png", format="PNG")

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

