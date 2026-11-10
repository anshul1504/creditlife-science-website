import os
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent


def _load_dotenv(path):
    """Minimal .env reader (no extra dependency). Real environment variables always win."""
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, _, value = line.partition("=")
            os.environ.setdefault(key.strip(), value.strip().strip("\"'"))


_load_dotenv(BASE_DIR / ".env")

SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "dev-only-change-me-before-deploy")
DEBUG = os.environ.get("DJANGO_DEBUG", "1") == "1"
ALLOWED_HOSTS = [h for h in os.environ.get("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1").split(",") if h]

INSTALLED_APPS = [
    "jazzmin",                         # admin theme (must come before django.contrib.admin)
    "core",                            # our own admin pages (dashboard, customer 360, import) live in core/templates/admin
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.sitemaps",
    "django_otp",                      # staff two-factor (TOTP), enforced when ADMIN_2FA=1
    "django_otp.plugins.otp_totp",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",  # serves static files efficiently (compressed, long-cached) in production
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.locale.LocaleMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django_otp.middleware.OTPMiddleware",
    "core.middleware.AdminIPAllowlistMiddleware",
    "core.middleware.ContentSecurityPolicyMiddleware",
    "core.middleware.ReferralCaptureMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.i18n",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "core.context_processors.site",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

def _database_from_env():
    """DATABASE_URL=postgres://user:password@host:5432/dbname selects PostgreSQL; otherwise local SQLite."""
    url = os.environ.get("DATABASE_URL", "")
    if url.startswith(("postgres://", "postgresql://")):
        from urllib.parse import unquote, urlparse

        parsed = urlparse(url)
        return {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": parsed.path.lstrip("/"),
            "USER": unquote(parsed.username or ""),
            "PASSWORD": unquote(parsed.password or ""),
            "HOST": parsed.hostname or "localhost",
            "PORT": str(parsed.port or 5432),
            "CONN_MAX_AGE": 60,
        }
    return {"ENGINE": "django.db.backends.sqlite3", "NAME": BASE_DIR / "db.sqlite3"}


DATABASES = {"default": _database_from_env()}

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "en-in"
TIME_ZONE = "Asia/Kolkata"
LANGUAGES = [("en", "English"), ("hi", "हिन्दी")]
LOCALE_PATHS = [BASE_DIR / "locale"]
USE_I18N = True
USE_TZ = True

MEDIA_URL = "media/"
MEDIA_ROOT = BASE_DIR / "media"

STATIC_URL = "static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# ---------------------------------------------------------------- email
# Set EMAIL_HOST (and the rest) in the environment to send real mail; otherwise emails print to the console.
EMAIL_HOST = os.environ.get("EMAIL_HOST", "")
EMAIL_PORT = int(os.environ.get("EMAIL_PORT", "587"))
EMAIL_HOST_USER = os.environ.get("EMAIL_HOST_USER", "")
EMAIL_HOST_PASSWORD = os.environ.get("EMAIL_HOST_PASSWORD", "")
EMAIL_USE_SSL = os.environ.get("EMAIL_USE_SSL", "0") == "1"  # port 465 (implicit SSL)
EMAIL_USE_TLS = os.environ.get("EMAIL_USE_TLS", "0" if EMAIL_USE_SSL else "1") == "1" and not EMAIL_USE_SSL  # port 587 (STARTTLS)
EMAIL_TIMEOUT = 15  # emails are sent inside the request, so never hang on a slow mail server
EMAIL_BACKEND = os.environ.get(
    "DJANGO_EMAIL_BACKEND",
    "django.core.mail.backends.smtp.EmailBackend" if EMAIL_HOST else "django.core.mail.backends.console.EmailBackend",
)
DEFAULT_FROM_EMAIL = os.environ.get("DJANGO_FROM_EMAIL", "Credit Lifesciences <no-reply@creditlifesciences.example>")
SITE_URL = os.environ.get("SITE_URL", "http://localhost:8000")  # absolute links used inside emails

# ------------------------------------------------------------------ auth
AUTHENTICATION_BACKENDS = [
    "core.auth_backends.EmailBackend",  # customers sign in with their email
    "django.contrib.auth.backends.ModelBackend",  # keeps /admin/ username login working
]
LOGIN_URL = "login"
LOGIN_REDIRECT_URL = "account"
LOGOUT_REDIRECT_URL = "home"

CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}

SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "strict-origin-when-cross-origin"
X_FRAME_OPTIONS = "DENY"
CSRF_TRUSTED_ORIGINS = [o for o in os.environ.get("DJANGO_CSRF_TRUSTED_ORIGINS", "").split(",") if o]

if not DEBUG:
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")  # the app sits behind nginx / a load balancer
    SECURE_SSL_REDIRECT = os.environ.get("DJANGO_SSL_REDIRECT", "1") == "1"
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_HSTS_SECONDS = 31536000
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True
    STORAGES = {
        "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
        "staticfiles": {"BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"},
    }

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {"plain": {"format": "%(asctime)s %(levelname)s %(name)s: %(message)s"}},
    "handlers": {"console": {"class": "logging.StreamHandler", "formatter": "plain"}},
    "root": {"handlers": ["console"], "level": os.environ.get("DJANGO_LOG_LEVEL", "INFO")},
    "loggers": {"django.request": {"handlers": ["console"], "level": "WARNING", "propagate": False}},
}

# Optional error monitoring: set SENTRY_DSN (and `pip install sentry-sdk`) to receive crash reports.
if os.environ.get("SENTRY_DSN"):
    try:
        import sentry_sdk

        sentry_sdk.init(dsn=os.environ["SENTRY_DSN"], send_default_pii=False, traces_sample_rate=0.0)
    except ImportError:
        pass

# The commercial defaults below follow the client's content brief (B2B trade site: online payment only, the buyer
# pays shipping, 5-7 business days, ordering for registered business users). The automated tests keep the older
# consumer-store values so the checkout, coupon and loyalty code stays covered; tests of the brief rules override them.
TESTING = "test" in sys.argv

# Storefront rules (amounts in rupees).
SHOP = {
    "free_shipping_above": 499 if TESTING else 0,   # 0 = delivery is never free: the buyer bears shipping
    "shipping_fee": 49,                              # PLACEHOLDER flat charge until courier rates are supplied
    "max_qty": 10,
    "delivery_days": (3, 7) if TESTING else (5, 7),  # brief: 5-7 business days (confirm: from confirmation or dispatch)
    "cod_enabled": TESTING or os.environ.get("COD_ENABLED", "0") == "1",   # brief lists UPI, cards and net banking only
    "require_kyc_to_order": (not TESTING) and os.environ.get("REQUIRE_KYC_TO_ORDER", "0") == "1",  # only approved business accounts may order
    "require_login_to_order": (not TESTING) and os.environ.get("REQUIRE_LOGIN_TO_ORDER", "1") == "1",
    "consumer_features": TESTING or os.environ.get("CONSUMER_FEATURES", "0") == "1",  # subscriptions, rewards, bundles
    "subscribe_discount_pct": 5,   # Subscribe & Save
    "points_per_100": 2,           # credit points earned per Rs 100 paid, when the order is delivered
    "point_value": 1,              # Rs value of one point at checkout
    "max_points_pct": 20,          # at most this share of an order can be paid with points
    "referral_reward": 100,        # points for the referrer and the new customer, after the new customer's first delivery
    "min_shelf_life_days": 30,   # batches closer to expiry than this are not sold
    "low_stock_threshold": 10,   # admin alert level, in units
    "expiry_alert_days": 90,
    "online_payment_enabled": (not TESTING) and bool(os.environ.get("RAZORPAY_KEY_ID") and os.environ.get("RAZORPAY_KEY_SECRET")),
}

# ------------------------------------------------------- one-time passcodes
OTP = {
    "length": 6,
    "ttl_seconds": 600,      # a code is valid for 10 minutes
    "max_attempts": 5,       # wrong guesses allowed per code
    "resend_seconds": 30,    # minimum gap between two codes for the same email and purpose
    "max_per_hour": 6,       # codes per email per hour
}

# --------------------------------------------------------------- Razorpay
# Put the real keys in .env (never in code). Online payment switches on automatically once both keys exist.
# Real keys are never used by the automated tests (they use a fake gateway), so a test run can never touch live money.
RAZORPAY = {
    "key_id": "" if TESTING else os.environ.get("RAZORPAY_KEY_ID", ""),
    "key_secret": "" if TESTING else os.environ.get("RAZORPAY_KEY_SECRET", ""),
    "webhook_secret": "" if TESTING else os.environ.get("RAZORPAY_WEBHOOK_SECRET", ""),
}
UNPAID_ORDER_EXPIRY_MINUTES = 120  # online orders still unpaid after this long are cancelled by `expire_unpaid_orders`

# Company details used across the site (see core/context_processors.py).
SITE = {
    "name": "Credit Lifesciences",
    "parent": "",            # the brief names no parent company; the old "Volkscure" line is left out until confirmed
    "tagline": "Serving Health",   # stays in English in the Hindi version too
    "established": 2009,
    "years": 17,             # "17 years since 2009 (as of 2026)"
    "founder": "Mr. Prakash Harendra Singh",
    "phones": [("+91 99363 60600", "+919936360600")],   # confirm whether this is a toll-free number before saying so
    "email": "askus@creditlifesciences.com",
    "sales_email": "sales@creditlifesciences.com",
    "careers_email": "",     # HR email is pending
    "enquiry_recipients": ["sales@creditlifesciences.com", "askus@creditlifesciences.com"],
    "order_recipients": ["sales@creditlifesciences.com", "askus@creditlifesciences.com"],
    "website": "www.creditlifesciences.com",
    "address": "KH. 58, Basdeva Kunwar, PS - Harraiya, District - Basti, Uttar Pradesh - 272155, India",
    "whatsapp": "919936360600",
    "social": [   # empty links are not shown (Twitter, Threads and LinkedIn are still pending from the client)
        ("Facebook", "bi-facebook", "https://www.facebook.com/DrGasSyrup"),
        ("Instagram", "bi-instagram", "https://www.instagram.com/drgassyrup"),
        ("YouTube", "bi-youtube", "https://www.youtube.com/@DrGASOfficial"),
        ("X (Twitter)", "bi-twitter-x", ""),
        ("Threads", "bi-threads", ""),
        ("LinkedIn", "bi-linkedin", ""),
    ],
}

# Legal / tax details printed on invoices and the legal pages. Leave blank until the client confirms them:
# anything blank is left off the invoice instead of being invented.
SELLER = {
    "legal_name": os.environ.get("SELLER_LEGAL_NAME", "Credit Lifesciences (Proprietor: Prabhat Harendra Singh)"),
    "gstin": os.environ.get("SELLER_GSTIN", "09KWDPS4937K1ZM"),
    "cin": os.environ.get("SELLER_CIN", ""),
    "licence": os.environ.get("SELLER_LICENCE", "Wholesale Drug Licence Form 20B No. UP5120B001001 and Form 21B No. UP5121B001001"),
    "address": os.environ.get("SELLER_ADDRESS", "Ground Floor, KH-58, Basdeva Kunwar, Amari Bazar, Harraiya, Basti, Uttar Pradesh - 272155"),
    "state": os.environ.get("SELLER_STATE", "Uttar Pradesh"),   # decides CGST+SGST (same state) vs IGST
    "pincode": os.environ.get("SELLER_PINCODE", "272155"),        # pickup PIN, used for courier serviceability
    "grievance_name": os.environ.get("GRIEVANCE_NAME", ""),
    "grievance_email": os.environ.get("GRIEVANCE_EMAIL", "askus@creditlifesciences.com"),
    "grievance_phone": os.environ.get("GRIEVANCE_PHONE", "+91 99363 60600"),
}

# Courier: "static" estimates delivery from the PIN code; "shiprocket" talks to Shiprocket (needs the credentials).
COURIER = {
    "provider": os.environ.get("COURIER_PROVIDER", "static"),
    "email": os.environ.get("SHIPROCKET_EMAIL", ""),
    "password": os.environ.get("SHIPROCKET_PASSWORD", ""),
    "webhook_token": os.environ.get("COURIER_WEBHOOK_TOKEN", ""),
    "timeout": 8,
}

# SMS (MSG91) and WhatsApp (Meta Cloud API) order updates; each stays off until its credentials are set. See core/notify.py.
NOTIFY = {
    "msg91_authkey": os.environ.get("MSG91_AUTHKEY", ""),
    "msg91_template_placed": os.environ.get("MSG91_TEMPLATE_PLACED", ""),
    "msg91_template_status": os.environ.get("MSG91_TEMPLATE_STATUS", ""),
    "msg91_template_otp": os.environ.get("MSG91_TEMPLATE_OTP", ""),   # var1 = the code
    "whatsapp_token": os.environ.get("WHATSAPP_TOKEN", ""),
    "whatsapp_phone_id": os.environ.get("WHATSAPP_PHONE_ID", ""),
    "whatsapp_language": os.environ.get("WHATSAPP_LANGUAGE", "en"),
    "whatsapp_template_placed": os.environ.get("WHATSAPP_TEMPLATE_PLACED", ""),
    "whatsapp_template_status": os.environ.get("WHATSAPP_TEMPLATE_STATUS", ""),
}

# Google sign-in (OAuth 2.0). Create an OAuth client in Google Cloud Console and add
# <SITE_URL>/account/google/callback/ as an authorised redirect URI. The button appears only when both are set.
GOOGLE = {
    "client_id": os.environ.get("GOOGLE_CLIENT_ID", ""),
    "client_secret": os.environ.get("GOOGLE_CLIENT_SECRET", ""),
}

# Self-serve returns: how long after delivery a customer may open a request
RETURN_WINDOW_DAYS = 7

# Admin hardening
ADMIN_URL = os.environ.get("ADMIN_URL", "admin").strip("/") or "admin"
ADMIN_ALLOWED_IPS = [ip.strip() for ip in os.environ.get("ADMIN_ALLOWED_IPS", "").split(",") if ip.strip()]
# EMAIL_QUEUE=1 stores emails in the database and a worker (`manage.py run_worker`) sends them, so requests never wait on SMTP.
EMAIL_QUEUE = os.environ.get("EMAIL_QUEUE", "0") == "1"
PWA_VERSION = "1"  # bump to make every browser drop its cached pages after a big release
CSP_MODE = os.environ.get("CSP_MODE", "enforce")  # enforce | report-only | off
TRUST_PROXY_IP = os.environ.get("TRUST_PROXY_IP", "0") == "1"
ADMIN_2FA = os.environ.get("ADMIN_2FA", "0") == "1"


# ---------------------------------------------------------------- admin theme (django-jazzmin)
JAZZMIN_SETTINGS = {
    "site_title": "Credit Lifesciences Admin",
    "site_header": "Credit Lifesciences",
    "site_brand": "Credit Lifesciences",
    "site_logo": "img/logo-credit.png",
    "login_logo": "img/logo-credit.png",
    "site_icon": "img/favicon.ico",
    "welcome_sign": "Credit Lifesciences admin: sign in to manage the website",
    "copyright": "Credit Lifesciences",
    "search_model": ["core.Product", "core.Order"],
    "user_avatar": None,
    "topmenu_links": [
        {"name": "Dashboard", "url": "sales_dashboard", "permissions": ["core.view_order"]},
        {"name": "View website", "url": "/", "new_window": True},
    ],
    "show_sidebar": True,
    "navigation_expanded": False,
    "order_with_respect_to": [
        "core.SiteSettings", "core.HeroSlide", "core.TeamMessage", "core.Highlight", "core.TimelineItem", "core.FAQ", "core.Banner", "core.Announcement", "core.Page",
        "core.DistributorEnquiry", "core.District", "core.DistributorListing", "core.CareerApplication", "core.JobRole", "core.Enquiry",
        "core.Product", "core.Batch", "core.Order", "core.ReturnRequest", "core.Coupon", "auth",
    ],
    "icons": {
        "auth": "fas fa-users-cog", "auth.user": "fas fa-user", "auth.group": "fas fa-users",
        "core.SiteSettings": "fas fa-sliders-h", "core.HeroSlide": "fas fa-images", "core.TeamMessage": "fas fa-comment-dots", "core.Highlight": "fas fa-star",
        "core.TimelineItem": "fas fa-stream", "core.FAQ": "fas fa-question-circle", "core.Banner": "fas fa-bullhorn", "core.Announcement": "fas fa-bell", "core.Page": "fas fa-file-alt",
        "core.DistributorEnquiry": "fas fa-handshake", "core.District": "fas fa-map-marked-alt", "core.DistributorListing": "fas fa-store", "core.CareerApplication": "fas fa-id-badge",
        "core.JobRole": "fas fa-briefcase", "core.Enquiry": "fas fa-envelope-open-text", "core.Product": "fas fa-capsules", "core.Batch": "fas fa-boxes",
        "core.Order": "fas fa-shopping-bag", "core.ReturnRequest": "fas fa-undo", "core.Coupon": "fas fa-ticket-alt", "core.Review": "fas fa-star-half-alt",
    },
    "default_icon_parents": "fas fa-folder",
    "default_icon_children": "fas fa-circle-notch",
    "related_modal_active": True,
    "custom_css": "admin/css/credit-admin.css",
    "show_ui_builder": False,
    "use_google_fonts_cdn": False,
    "changeform_format": "horizontal_tabs",
}
JAZZMIN_UI_TWEAKS = {
    "navbar_small_text": False, "footer_small_text": False, "body_small_text": False, "brand_small_text": False,
    "brand_colour": "navbar-success", "accent": "accent-success", "navbar": "navbar-white navbar-light", "no_navbar_border": True,
    "navbar_fixed": True, "layout_boxed": False, "footer_fixed": False, "sidebar_fixed": True,
    "sidebar": "sidebar-dark-success", "sidebar_nav_small_text": False, "sidebar_disable_expand": False,
    "sidebar_nav_child_indent": True, "sidebar_nav_compact_style": True, "sidebar_nav_legacy_style": False, "sidebar_nav_flat_style": False,
    "theme": "default", "button_classes": {
        "primary": "btn-success", "secondary": "btn-outline-secondary", "info": "btn-outline-info",
        "warning": "btn-outline-warning", "danger": "btn-outline-danger", "success": "btn-success",
    },
}
