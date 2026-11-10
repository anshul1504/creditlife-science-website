from django.conf import settings

_asset_v = None


def asset_version():
    """Newest modification time of our own CSS and JS, so browsers fetch fresh files after every change."""
    global _asset_v
    if _asset_v is None or settings.DEBUG:
        files = list((settings.BASE_DIR / "static" / "css").glob("*.css")) + list((settings.BASE_DIR / "static" / "js").glob("*.js"))
        _asset_v = str(int(max((f.stat().st_mtime for f in files), default=0)))
    return _asset_v

from .cart import Cart
from .models import Announcement, Product, Wishlist
from . import sitecfg


def site(request):
    user = getattr(request, "user", None)
    authed = bool(user and user.is_authenticated)
    return {
        "ASSET_V": asset_version(),
        "SITE": sitecfg.site(),
        "SELLER": settings.SELLER,
        "SHOP": settings.SHOP,
        "GOOGLE_ENABLED": bool(settings.GOOGLE["client_id"] and settings.GOOGLE["client_secret"]),
        "SMS_LOGIN": bool(settings.NOTIFY["msg91_authkey"] and settings.NOTIFY["msg91_template_otp"]),
        "NAV_PRODUCTS": Product.objects.filter(is_active=True),
        "ANNOUNCEMENTS": list(Announcement.objects.filter(is_active=True)[:4]),
        "CART_COUNT": Cart(request).count,
        "WISHLIST_IDS": set(Wishlist.objects.filter(user=user).values_list("product_id", flat=True)) if authed else set(),
        "EMAIL_UNVERIFIED": authed and not getattr(getattr(user, "profile", None), "email_verified", True),
    }
