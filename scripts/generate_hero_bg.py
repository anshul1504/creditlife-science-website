"""Generate the six flat full-screen hero backgrounds (1920x1080) for the home page.

    python scripts/generate_hero_bg.py

Flat colours only (no gradients). Each background has its own motif: partnership, quality, trust, villages,
network and product portfolio. Replace any of them from Admin > Hero slides by uploading your own photo.
"""
import math
import random
from pathlib import Path

from PIL import Image, ImageDraw

OUT = Path(__file__).resolve().parent.parent / "static" / "img" / "hero"
W, H, S = 1920, 1080, 2  # drawn at 2x and scaled down for smooth edges

NAVY, DEEP = (11, 34, 57), (8, 26, 44)
GREEN, MINT, TEAL, SAND, GOLD = (14, 122, 85), (110, 200, 160), (22, 112, 130), (236, 230, 214), (224, 161, 0)


def canvas(base=NAVY):
    img = Image.new("RGBA", (W * S, H * S), base + (255,))
    return img, ImageDraw.Draw(img, "RGBA")


def px(v):
    return int(v * S)


def circle(d, x, y, r, fill):
    d.ellipse([px(x - r), px(y - r), px(x + r), px(y + r)], fill=fill)


def capsule(d, cx, cy, length, width, angle, fill):
    # a rotated capsule drawn as a polygon of its outline
    pts = []
    r = width / 2
    for side, sign in ((0, 1), (1, -1)):
        for i in range(0, 181, 6):
            a = math.radians(i - 90) if side == 0 else math.radians(i + 90)
            pts.append((sign * (length / 2 - r) + r * math.cos(a) * sign * 1, r * math.sin(a)))
    pts = [(x * 1, y) for x, y in pts]
    ca, sa = math.cos(math.radians(angle)), math.sin(math.radians(angle))
    rot = [(px(cx + x * ca - y * sa), px(cy + x * sa + y * ca)) for x, y in pts]
    d.polygon(rot, fill=fill)


def dots(d, x0, y0, cols, rows, gap, r, fill):
    return  # decorative dot grids were removed on request


def finish(img, name):
    img = img.resize((W, H), Image.LANCZOS).convert("RGB")
    OUT.mkdir(parents=True, exist_ok=True)
    img.save(OUT / name, "JPEG", quality=84, optimize=True, progressive=True)
    print("wrote", name)


def bg1():  # partnership: overlapping circles
    img, d = canvas()
    circle(d, 1450, 520, 360, GREEN + (150,))
    circle(d, 1720, 640, 300, TEAL + (150,))
    circle(d, 1560, 330, 190, MINT + (70,))
    circle(d, 1280, 760, 120, SAND + (40,))
    dots(d, 980, 120, 12, 6, 46, 3, (255, 255, 255, 40))
    finish(img, "bg-1.jpg")


def bg2():  # quality & affordability: concentric rings and a check ring
    img, d = canvas(DEEP)
    for i, r in enumerate((520, 420, 320, 220)):
        circle(d, 1500, 540, r, [(14, 122, 85, 60), (14, 122, 85, 90), (110, 200, 160, 70), (14, 122, 85, 160)][i])
    circle(d, 1500, 540, 130, SAND + (235,))
    d.line([(px(1450), px(545)), (px(1485), px(585)), (px(1555), px(500))], fill=GREEN + (255,), width=px(22), joint="curve")
    dots(d, 160, 840, 14, 5, 46, 3, (255, 255, 255, 35))
    finish(img, "bg-2.jpg")


def bg3():  # trust and experience: rising bars / years
    img, d = canvas()
    heights = [140, 200, 270, 350, 450, 560, 680]
    for i, h in enumerate(heights):
        x = 1040 + i * 120
        d.rounded_rectangle([px(x), px(H - 120 - h), px(x + 80), px(H - 120)], radius=px(14), fill=(GREEN if i % 2 else TEAL) + (190,))
    circle(d, 1750, 220, 90, GOLD + (220,))
    dots(d, 1000, 110, 8, 3, 46, 3, (255, 255, 255, 40))
    d.rectangle([px(980), px(H - 120), px(1900), px(H - 114)], fill=(255, 255, 255, 60))
    finish(img, "bg-3.jpg")


def bg4():  # healthcare accessibility: layered hills and a small village
    img, d = canvas(DEEP)
    circle(d, 1560, 250, 110, GOLD + (230,))
    for base, col in ((760, (22, 112, 130, 255)), (860, (14, 122, 85, 255)), (960, (11, 90, 66, 255))):
        pts = [(0, H)] + [(x, base + 50 * math.sin(x / 210 + base)) for x in range(0, W + 40, 40)] + [(W, H)]
        d.polygon([(px(x), px(y)) for x, y in pts], fill=col)
    for hx, hy in ((1180, 790), (1290, 820), (1420, 800), (1560, 835)):
        d.rectangle([px(hx), px(hy), px(hx + 60), px(hy + 44)], fill=SAND + (255,))
        d.polygon([(px(hx - 8), px(hy)), (px(hx + 30), px(hy - 30)), (px(hx + 68), px(hy))], fill=(190, 80, 60, 255))
    finish(img, "bg-4.jpg")


def bg5():  # distribution network: nodes and links
    img, d = canvas()
    rnd = random.Random(7)
    nodes = [(1000 + rnd.random() * 860, 90 + rnd.random() * 900) for _ in range(34)]
    for i, a in enumerate(nodes):
        near = sorted(nodes, key=lambda b: (a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2)[1:3]
        for b in near:
            d.line([(px(a[0]), px(a[1])), (px(b[0]), px(b[1]))], fill=(110, 200, 160, 90), width=px(2))
    for i, (x, y) in enumerate(nodes):
        circle(d, x, y, 9 if i % 5 else 16, (GOLD if i % 11 == 0 else MINT if i % 3 else GREEN) + (230,))
    finish(img, "bg-5.jpg")


def bg6():  # product portfolio: capsules and leaves
    img, d = canvas(DEEP)
    specs = [(1250, 330, 330, 120, -28, GREEN), (1560, 500, 380, 130, 22, SAND), (1380, 760, 300, 110, -12, TEAL), (1730, 250, 240, 90, 40, MINT),
             (1700, 800, 260, 100, -35, GREEN)]
    for cx, cy, ln, wd, ang, col in specs:
        capsule(d, cx, cy, ln, wd, ang, col + (225,))
        capsule(d, cx + 8, cy + 8, ln * 0.9, wd * 0.35, ang, (255, 255, 255, 50))
    dots(d, 980, 880, 12, 3, 46, 3, (255, 255, 255, 40))
    finish(img, "bg-6.jpg")


if __name__ == "__main__":
    for fn in (bg1, bg2, bg3, bg4, bg5, bg6):
        fn()
