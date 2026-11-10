import re
from functools import lru_cache
from pathlib import PurePosixPath

from django import template
from django.contrib.staticfiles import finders
from django.templatetags.static import static
from django.utils.html import escape, format_html
from django.utils.safestring import mark_safe

register = template.Library()
BOLD = re.compile(r"[*][*](.+?)[*][*]")


@register.filter
def lines(value):
    """Split a multi-line text field into a list of non-empty stripped lines."""
    return [ln.strip() for ln in (value or "").splitlines() if ln.strip()]


@register.filter
def pairs(value):
    """Split 'Left | Right' lines into (left, right) tuples."""
    out = []
    for ln in lines(value):
        left, _, right = ln.partition("|")
        out.append((left.strip(), right.strip()))
    return out


@register.filter
def csv(value):
    return [v.strip() for v in (value or "").split(",") if v.strip()]


@register.filter
def stars_pct(rating):
    """Convert a 1-5 rating to the width percentage used by the star display."""
    try:
        return int(rating) * 20
    except (TypeError, ValueError):
        return 0


@register.filter
def getlist(querydict, key):
    """All values of a repeated query parameter, e.g. request.GET|getlist:'cat'."""
    return querydict.getlist(key)


@register.filter
def invoice_link(order):
    """Signed link to the order's invoice PDF (works for guests too)."""
    from core.views_ops import invoice_url
    return invoice_url(order)


def _inline(text):
    return BOLD.sub(lambda m: "<strong>" + m.group(1) + "</strong>", escape(text))


@register.filter
def rich(value):
    """Plain admin-entered text -> safe HTML: blank-line separated paragraphs, '## ' sub-headings, '- ' bullet lists."""
    out = []
    text = "\n".join((value or "").splitlines())  # normalises Windows line endings
    for block in text.split("\n\n"):
        block = block.strip()
        if not block:
            continue
        rows = block.splitlines()
        if block.startswith("## "):
            out.append("<h2>" + _inline(block[3:].strip()) + "</h2>")
        elif all(row.lstrip().startswith("- ") for row in rows):
            out.append("<ul>" + "".join("<li>" + _inline(row.lstrip()[2:]) + "</li>" for row in rows) + "</ul>")
        else:
            out.append("<p>" + "<br>".join(_inline(row) for row in rows) + "</p>")
    return mark_safe("".join(out))


@lru_cache(maxsize=512)
def _variants(path):
    """Widths for which an optimised WebP of this static image exists (see `manage.py optimize_images`)."""
    p = PurePosixPath(path)
    found = []
    for w in (320, 640, 1000):
        if finders.find(f"{p.parent}/opt/{p.stem}-{w}.webp"):
            found.append(w)
    return tuple(found)


@register.simple_tag
def picture(path, alt="", sizes="(min-width: 992px) 25vw, 50vw", css="", lazy=True):
    """<picture> with WebP sources when optimised copies exist, otherwise a plain <img> of the original."""
    p = PurePosixPath(path)
    widths = _variants(str(path))
    attrs = format_html(' alt="{}"', alt)
    if css:
        attrs += format_html(' class="{}"', css)
    if lazy:
        attrs += mark_safe(' loading="lazy" decoding="async"')
    img = format_html('<img src="{}"{}>', static(path), attrs)
    if not widths:
        return img
    srcset = ", ".join(f"{static(f'{p.parent}/opt/{p.stem}-{w}.webp')} {w}w" for w in widths)
    return format_html('<picture><source type="image/webp" srcset="{}" sizes="{}">{}</picture>', srcset, sizes, img)
