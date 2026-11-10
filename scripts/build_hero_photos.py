"""Build photographic hero backgrounds (1920x1080).

    python scripts/build_hero_photos.py

* bg-1.jpg: a business-partnership photo (Wikimedia Commons, CC0 / public domain: no attribution needed)
* bg-2.jpg and bg-6.jpg: collages of the company's own product photographs on a flat navy backdrop
These replace the flat artwork from generate_hero_bg.py for those slides. Upload your own photos in Admin > Hero slides any time.
"""
import io
from pathlib import Path

import requests
from PIL import Image, ImageDraw, ImageFilter, ImageOps

ROOT = Path(__file__).resolve().parent.parent
IMG = ROOT / "static" / "img"
OUT = IMG / "hero"
W, H = 1920, 1080
NAVY = (11, 34, 57)
HEADERS = {"User-Agent": "CreditLifesciencesSite/1.0 (website build)"}
HANDSHAKE = "File:Business agreement handshake at coffee shop.jpg"  # CC0


def commons_url(title):
    r = requests.get("https://commons.wikimedia.org/w/api.php", params={
        "action": "query", "format": "json", "titles": title, "prop": "imageinfo", "iiprop": "url", "iiurlwidth": 2400}, headers=HEADERS, timeout=30).json()
    page = next(iter(r["query"]["pages"].values()))
    info = page["imageinfo"][0]
    return info.get("thumburl") or info["url"]


def cover(im, size=(W, H), focus=(0.5, 0.5)):
    return ImageOps.fit(im, size, Image.LANCZOS, centering=focus)


def partnership():
    im = Image.open(io.BytesIO(requests.get(commons_url(HANDSHAKE), headers=HEADERS, timeout=90).content)).convert("RGB")
    im = cover(im, focus=(0.62, 0.5))
    im.save(OUT / "bg-1.jpg", "JPEG", quality=84, optimize=True, progressive=True)
    print("wrote bg-1.jpg")


def tile(path, size, radius=28):
    im = ImageOps.fit(Image.open(path).convert("RGB"), (size, size), Image.LANCZOS)
    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, size, size], radius=radius, fill=255)
    out = Image.new("RGBA", (size, size))
    out.paste(im, (0, 0), mask)
    return out


def shadowed(canvas, im, xy, angle=0):
    if angle:
        im = im.rotate(angle, expand=True, resample=Image.BICUBIC)
    sh = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    blob = Image.new("RGBA", im.size, (0, 0, 0, 110))
    blob.putalpha(im.getchannel("A").point(lambda v: 110 if v else 0))
    sh.paste(blob, (xy[0] + 14, xy[1] + 22), blob)
    canvas.alpha_composite(sh.filter(ImageFilter.GaussianBlur(22)))
    canvas.alpha_composite(im, xy)


def collage(name, layout):
    canvas = Image.new("RGBA", (W, H), NAVY + (255,))
    for src, size, xy, angle in layout:
        shadowed(canvas, tile(IMG / src, size), xy, angle)
    canvas.convert("RGB").save(OUT / name, "JPEG", quality=86, optimize=True, progressive=True)
    print("wrote", name)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    partnership()
    collage("bg-2.jpg", [("npr-hb.jpg", 470, (1080, 130), -4), ("drgas-liquid.jpg", 400, (1420, 420), 5), ("tumlanta.jpg", 360, (1030, 590), 3)])
    collage("bg-6.jpg", [("mahajoint.jpg", 410, (1010, 150), 4), ("npr-hb.jpg", 360, (1430, 110), -5), ("drgas-liquid.jpg", 400, (1380, 520), 3),
                         ("tumlanta.jpg", 340, (1030, 600), -4)])


if __name__ == "__main__":
    main()
