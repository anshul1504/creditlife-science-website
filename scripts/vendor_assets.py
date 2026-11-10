"""Download Bootstrap, Bootstrap Icons and Poppins into static/vendor so the site serves them itself.

Run once (and whenever a version is bumped):  python scripts/vendor_assets.py
Self-hosting is what lets the Content-Security-Policy stay strict and removes a third-party dependency
(and a privacy leak to Google) from every page view.
"""
import re
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent / "static" / "vendor"
BS = "https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist"
ICONS = "https://cdn.jsdelivr.net/npm/bootstrap-icons@1.11.3/font"
FONTS_CSS = "https://fonts.googleapis.com/css2?family=Poppins:ital,wght@0,300;0,400;0,500;0,600;0,700;1,400;1,500&display=swap"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36"  # asks Google for woff2


def get(url, **kw):
    r = requests.get(url, timeout=30, **kw)
    r.raise_for_status()
    return r


SOURCE_MAP = re.compile(r" *(?://#|/[*]#) *sourceMappingURL=.*")


def save(path, data):
    # production collectstatic fails on references to .map files we do not ship
    if path.suffix in (".css", ".js") and isinstance(data, bytes):
        data = SOURCE_MAP.sub("", data.decode("utf-8")).encode("utf-8")
    elif path.suffix in (".css", ".js"):
        data = SOURCE_MAP.sub("", data)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data if isinstance(data, bytes) else data.encode("utf-8"))
    print("wrote", path.relative_to(ROOT.parent.parent), len(data))


def main():
    save(ROOT / "bootstrap" / "bootstrap.min.css", get(f"{BS}/css/bootstrap.min.css").content)
    save(ROOT / "bootstrap" / "bootstrap.bundle.min.js", get(f"{BS}/js/bootstrap.bundle.min.js").content)

    css = get(f"{ICONS}/bootstrap-icons.min.css").text
    for ext in ("woff2", "woff"):
        save(ROOT / "bootstrap-icons" / "fonts" / f"bootstrap-icons.{ext}", get(f"{ICONS}/fonts/bootstrap-icons.{ext}").content)
    css = re.sub(r"\?[0-9a-f]{20,}", "", css)  # cache-busting hash is not needed for a file we version ourselves
    css = css.replace("./fonts/", "fonts/")
    save(ROOT / "bootstrap-icons" / "bootstrap-icons.min.css", css)

    gf = get(FONTS_CSS, headers={"User-Agent": UA}).text
    out = []
    for block in re.findall(r"/\*\s*([\w-]+)\s*\*/\s*(@font-face\s*\{.*?\})", gf, flags=re.S):
        subset, face = block
        if subset not in ("latin", "latin-ext", "devanagari"):
            continue
        url = re.search(r"url\((https://[^)]+\.woff2)\)", face).group(1)
        weight = re.search(r"font-weight:\s*(\d+)", face).group(1)
        style = re.search(r"font-style:\s*(\w+)", face).group(1)
        name = f"poppins-{subset}-{weight}{'i' if style == 'italic' else ''}.woff2"
        save(ROOT / "poppins" / name, get(url).content)
        out.append(face.replace(url, name))
    save(ROOT / "poppins" / "poppins.css", "\n".join(out))


if __name__ == "__main__":
    main()
