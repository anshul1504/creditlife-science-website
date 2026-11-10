"""Generate the site's brand artwork: hero slides, social-share image and favicons.

Run from the project root:  python scripts/generate_assets.py
Outputs go to static/img/ (hero/, og-default.jpg, favicon.ico, apple-touch-icon.png, icon-192.png, icon-512.png).
"""
import io
import os
import sys
import urllib.request

from PIL import Image, ImageDraw, ImageFilter, ImageFont

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
IMG = os.path.join(ROOT, "static", "img")
FONTS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fonts")
SS = 2  # supersampling factor for smooth edges

PALETTE = {
    "npr-hb-syrup": "#C2670A",
    "dr-gas-liquid": "#0E7A55",
    "tumlanta-mps": "#B5457A",
    "mahajoint-oil": "#9A6B12",
}
SOURCES = {  # slug -> (source file, max card width, max card height)
    "npr-hb-syrup": ("npr-hb.jpg", 740, 740),
    "dr-gas-liquid": ("drgas-liquid.jpg", 680, 770),
    "tumlanta-mps": ("tumlanta.jpg", 520, 800),
    "mahajoint-oil": ("mahajoint.jpg", 800, 600),
}


def hex_rgb(value):
    value = value.lstrip("#")
    return tuple(int(value[i:i + 2], 16) for i in (0, 2, 4))


def mix(color, amount, base=(255, 255, 255)):
    """Blend `color` into `base` (amount 0..1 of colour)."""
    return tuple(round(c * amount + b * (1 - amount)) for c, b in zip(color, base))


def font(weight, size):
    """Poppins if it can be fetched, otherwise a system font."""
    names = {"semibold": "Poppins-SemiBold.ttf", "regular": "Poppins-Regular.ttf"}
    os.makedirs(FONTS, exist_ok=True)
    path = os.path.join(FONTS, names[weight])
    if not os.path.exists(path):
        url = "https://cdn.jsdelivr.net/gh/google/fonts@main/ofl/poppins/" + names[weight]
        try:
            with urllib.request.urlopen(url, timeout=20) as r, open(path, "wb") as fh:
                fh.write(r.read())
        except Exception:
            path = None
    if path and os.path.exists(path):
        return ImageFont.truetype(path, size)
    for candidate in ("segoeuib.ttf" if weight == "semibold" else "segoeui.ttf", "arialbd.ttf" if weight == "semibold" else "arial.ttf"):
        try:
            return ImageFont.truetype(os.path.join(os.environ.get("WINDIR", "C:/Windows"), "Fonts", candidate), size)
        except OSError:
            continue
    return ImageFont.load_default()


def rounded(im, radius):
    mask = Image.new("L", im.size, 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, im.width - 1, im.height - 1), radius=radius, fill=255)
    out = im.convert("RGBA")
    out.putalpha(mask)
    return out


def shadow(size, radius, blur, opacity, offset=(0, 0)):
    layer = Image.new("RGBA", (size[0] + blur * 4, size[1] + blur * 4), (0, 0, 0, 0))
    ImageDraw.Draw(layer).rounded_rectangle((blur * 2, blur * 2, blur * 2 + size[0], blur * 2 + size[1]), radius=radius, fill=(11, 34, 57, int(255 * opacity)))
    return layer.filter(ImageFilter.GaussianBlur(blur)), (offset[0] - blur * 2, offset[1] - blur * 2)


def hero_art(slug):
    src_name, max_w, max_h = SOURCES[slug]
    accent = hex_rgb(PALETTE[slug])
    W, H = 1200, 1100
    canvas = Image.new("RGBA", (W * SS, H * SS), (0, 0, 0, 0))
    d = ImageDraw.Draw(canvas)
    cx, cy = 600 * SS, 560 * SS

    def circle(x, y, r, fill=None, outline=None, width=0):
        d.ellipse((x - r, y - r, x + r, y + r), fill=fill, outline=outline, width=width)

    circle(cx, cy, 470 * SS, fill=mix(accent, .16) + (255,))
    circle(cx, cy, 540 * SS, outline=mix(accent, .30) + (255,), width=3 * SS)
    for row in range(5):  # dot grids give the artwork some texture without gradients
        for col in range(5):
            circle((90 + col * 38) * SS, (110 + row * 38) * SS, 5 * SS, fill=mix(accent, .45) + (255,))
            circle((900 + col * 38) * SS, (860 + row * 38) * SS, 5 * SS, fill=mix(accent, .45) + (255,))
    circle(1040 * SS, 190 * SS, 30 * SS, fill=accent + (255,))
    circle(150 * SS, 930 * SS, 16 * SS, fill=accent + (255,))
    circle(1110 * SS, 620 * SS, 10 * SS, fill=mix(accent, .6) + (255,))
    canvas = canvas.resize((W, H), Image.LANCZOS)

    photo = Image.open(os.path.join(IMG, src_name)).convert("RGB")
    scale = min(max_w / photo.width, max_h / photo.height)
    photo = photo.resize((round(photo.width * scale), round(photo.height * scale)), Image.LANCZOS)
    card = rounded(photo.resize((photo.width * SS, photo.height * SS), Image.LANCZOS), 54 * SS).resize(photo.size, Image.LANCZOS)

    sh, off = shadow(card.size, 54, 34, .30, (0, 36))
    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    pos = ((W - card.width) // 2, (H - card.height) // 2 + 10)
    layer.alpha_composite(sh, (pos[0] + off[0], pos[1] + off[1]))
    layer.alpha_composite(card, pos)
    layer = layer.rotate(-3, resample=Image.BICUBIC, center=(W // 2, H // 2))
    canvas.alpha_composite(layer)

    out_dir = os.path.join(IMG, "hero")
    os.makedirs(out_dir, exist_ok=True)
    canvas.save(os.path.join(out_dir, f"{slug}.webp"), quality=92, method=6)
    print("hero", slug)


def og_image():
    W, H = 1200, 630
    navy, green, gold = (11, 34, 57), (14, 122, 85), (233, 215, 168)
    im = Image.new("RGB", (W * SS, H * SS), navy)
    d = ImageDraw.Draw(im)
    d.ellipse((760 * SS, -260 * SS, 1460 * SS, 440 * SS), outline=(255, 255, 255, 0), width=0, fill=(18, 48, 79))
    d.ellipse((-200 * SS, 360 * SS, 300 * SS, 860 * SS), fill=(15, 42, 70))
    im = im.resize((W, H), Image.LANCZOS)
    rgba = im.convert("RGBA")

    # product cards on the right
    cards = [("drgas-liquid.jpg", (700, 95), 270, -5), ("npr-hb.jpg", (880, 215), 290, 3), ("mahajoint.jpg", (735, 350), 235, -2)]
    for name, (x, y), size, angle in cards:
        photo = Image.open(os.path.join(IMG, name)).convert("RGB")
        photo.thumbnail((size, size), Image.LANCZOS)
        card = rounded(photo, 30)
        pad = Image.new("RGBA", (card.width + 12, card.height + 12), (255, 255, 255, 0))
        ImageDraw.Draw(pad).rounded_rectangle((0, 0, pad.width - 1, pad.height - 1), radius=36, fill=(255, 255, 255, 255))
        pad.alpha_composite(card, (6, 6))
        sh, off = shadow(pad.size, 36, 20, .5, (0, 18))
        tile = Image.new("RGBA", (pad.width + 160, pad.height + 160), (0, 0, 0, 0))
        tile.alpha_composite(sh, (80 + off[0], 80 + off[1]))
        tile.alpha_composite(pad, (80, 80))
        tile = tile.rotate(angle, resample=Image.BICUBIC, expand=True)
        rgba.alpha_composite(tile, (x - 80, y - 80))

    # logo plate + text
    logo = Image.open(os.path.join(IMG, "logo-credit.png")).convert("RGBA")
    logo.thumbnail((120, 96), Image.LANCZOS)
    plate = Image.new("RGBA", (logo.width + 40, logo.height + 24), (255, 255, 255, 0))
    ImageDraw.Draw(plate).rounded_rectangle((0, 0, plate.width - 1, plate.height - 1), radius=22, fill=(255, 255, 255, 255))
    plate.alpha_composite(logo, (20, 12))
    rgba.alpha_composite(plate, (70, 64))
    d = ImageDraw.Draw(rgba)
    d.text((70 + plate.width + 20, 74), "Credit Lifesciences", font=font("semibold", 34), fill=(255, 255, 255, 255))
    d.text((70 + plate.width + 20, 118), "A DIVISION OF VOLKSCURE PVT. LTD.", font=font("regular", 16), fill=gold + (255,))
    head = font("semibold", 58)
    for i, line in enumerate(("Everyday health,", "delivered to", "your door.")):
        d.text((70, 215 + i * 78), line, font=head, fill=(255, 255, 255, 255))
    d.rounded_rectangle((70, 470, 70 + 330, 470 + 58), radius=16, fill=green + (255,))
    d.text((70 + 28, 481), "Shop now  •  Pay on delivery", font=font("semibold", 22), fill=(255, 255, 255, 255))
    d.text((70, 560), "Digestive care  ·  Nutrition  ·  Joint care", font=font("regular", 22), fill=(189, 203, 219, 255))
    rgba.convert("RGB").save(os.path.join(IMG, "og-default.jpg"), quality=90, optimize=True)
    print("og-default.jpg")


def favicons():
    logo = Image.open(os.path.join(IMG, "logo-credit.png")).convert("RGBA")

    def icon(size):
        base = Image.new("RGBA", (size * SS, size * SS), (255, 255, 255, 0))
        ImageDraw.Draw(base).rounded_rectangle((0, 0, size * SS - 1, size * SS - 1), radius=int(size * SS * .22), fill=(255, 255, 255, 255))
        inner = logo.copy()
        inner.thumbnail((int(size * SS * .86), int(size * SS * .86)), Image.LANCZOS)
        base.alpha_composite(inner, ((size * SS - inner.width) // 2, (size * SS - inner.height) // 2))
        return base.resize((size, size), Image.LANCZOS)

    icon(512).save(os.path.join(IMG, "icon-512.png"), optimize=True)
    icon(192).save(os.path.join(IMG, "icon-192.png"), optimize=True)
    icon(180).save(os.path.join(IMG, "apple-touch-icon.png"), optimize=True)
    icon(256).save(os.path.join(IMG, "favicon.ico"), sizes=[(16, 16), (32, 32), (48, 48), (64, 64)])
    print("favicons")


if __name__ == "__main__":
    only = sys.argv[1:] or ["hero", "og", "icons"]
    if "hero" in only:
        for slug in PALETTE:
            hero_art(slug)
    if "og" in only:
        og_image()
    if "icons" in only:
        favicons()
