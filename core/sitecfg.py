"""Company details that staff edit in Admin > Site settings, merged over the defaults in settings.SITE.

Every template sees the result as `SITE`, and Python code (emails, WhatsApp links, FAQs) calls `site()`. A blank field in
the admin simply falls back to the default, so an empty row never breaks the site.
"""
import re

from django.conf import settings
from django.core.cache import cache
from django.utils import timezone

CACHE_KEY = "site_settings_row"


def _row():
    from .models import SiteSettings
    if settings.TESTING:  # tests roll the database back between cases, a cache would leak a row from one test to the next
        return SiteSettings.objects.first()
    row = cache.get(CACHE_KEY)
    if row is None:
        row = SiteSettings.objects.first() or False
        cache.set(CACHE_KEY, row, 60)
    return row or None


def clear():
    cache.delete(CACHE_KEY)


def _tel(display):
    digits = re.sub(r"[^0-9+]", "", display or "")
    return digits if digits.startswith("+") else ("+91" + digits[-10:] if len(digits) >= 10 else digits)


def site():
    cfg = dict(settings.SITE)
    row = _row()
    if row:
        text = lambda v, default: (v or "").strip() or default
        cfg["name"] = text(row.company_name, cfg["name"])
        cfg["tagline"] = text(row.tagline, cfg["tagline"])
        cfg["established"] = row.established or cfg["established"]
        cfg["founder"] = text(row.founder_name, cfg["founder"])
        if row.phone.strip():
            cfg["phones"] = [(row.phone.strip(), _tel(row.phone))]
        cfg["whatsapp"] = re.sub(r"\D", "", row.whatsapp) or cfg["whatsapp"]
        cfg["email"] = text(row.email, cfg["email"])
        cfg["sales_email"] = text(row.sales_email, cfg["sales_email"])
        cfg["careers_email"] = (row.careers_email or "").strip()
        cfg["website"] = text(row.website, cfg["website"])
        cfg["address"] = text(row.address, cfg["address"])
        recipients = [e.strip() for e in re.split(r"[,\n;]", row.enquiry_recipients or "") if e.strip()]
        if recipients:
            cfg["enquiry_recipients"] = recipients
            cfg["order_recipients"] = recipients
        cfg["social"] = [
            ("Facebook", "bi-facebook", row.facebook), ("Instagram", "bi-instagram", row.instagram), ("YouTube", "bi-youtube", row.youtube),
            ("X (Twitter)", "bi-twitter-x", row.twitter), ("Threads", "bi-threads", row.threads), ("LinkedIn", "bi-linkedin", row.linkedin),
        ]
        cfg["vision"] = (row.vision or "").strip()
        cfg["mission"] = [ln.strip() for ln in (row.mission or "").splitlines() if ln.strip()]
        cfg["overview"] = (row.overview or "").strip()
        cfg["min_purchase"] = text(row.min_purchase, "5,00,000")
    else:
        cfg.setdefault("vision", "")
        cfg.setdefault("mission", [])
        cfg.setdefault("overview", "")
        cfg["min_purchase"] = "5,00,000"
    cfg["years"] = timezone.now().year - int(cfg["established"])  # grows by itself every January
    return cfg
