"""Responsive WebP variants for product images.

* Static artwork: `python manage.py optimize_images` writes static/img/opt/<name>-<width>.webp.
* Uploaded images (ProductImage): variants are written next to the upload when it is saved.
The `picture` template tag uses the variants when they exist and falls back to the original image otherwise,
so nothing breaks if the command has not been run.
"""
import logging
from pathlib import Path

from PIL import Image

logger = logging.getLogger(__name__)
WIDTHS = (320, 640, 1000)
QUALITY = 80


def write_variants(src, out_dir, stem, widths=WIDTHS):
    """Write <stem>-<w>.webp for every width not larger than the source. Returns the list of widths written."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    written = []
    with Image.open(src) as im:
        im = im.convert("RGBA" if im.mode in ("RGBA", "LA", "P") else "RGB")
        for w in widths:
            if w > im.width and written:
                continue  # never upscale
            target_w = min(w, im.width)
            h = round(im.height * target_w / im.width)
            im.resize((target_w, h), Image.LANCZOS).save(out_dir / f"{stem}-{target_w}.webp", "WEBP", quality=QUALITY, method=6)
            written.append(target_w)
    return sorted(set(written))


def srcset(url_prefix, stem, widths):
    return ", ".join(f"{url_prefix}/{stem}-{w}.webp {w}w" for w in widths)


def upload_variants(image_field):
    """Called after an admin upload. Failures are logged, never raised: the original image still works."""
    try:
        path = Path(image_field.path)
        write_variants(path, path.parent, path.stem)
    except Exception:  # noqa: BLE001
        logger.exception("Could not create image variants for %s", image_field.name)
