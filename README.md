# Credit Lifesciences store (Django)

A D2C pharmacy-style storefront: catalogue, cart, coupons and sales, checkout (cash on delivery or Razorpay), email-OTP
sign-in, accounts, reviews, order tracking and transactional emails.

See `docs/PENDING-PLAN.md` for what is done and what is left, `docs/OPERATIONS.md` for running the store (legal setup, inventory, courier, admin security, backups, jobs) and `docs/GAP-ANALYSIS-AND-ROADMAP.md` for the full analysis.

## Run locally
    pip install -r requirements.txt
    copy .env.example .env              # then fill it in (never commit .env)
    python manage.py migrate
    python manage.py seed_products      # products, gallery images, hero artwork (placeholder prices)
    python manage.py seed_offers        # optional: example coupons (inactive) and the default announcement
    python manage.py seed_brief         # the client brief: 20 districts, Ayurvedic/Allopathic tags, PDF product details (seed_products runs it too)
    python manage.py seed_content       # optional: category pages, product FAQs, draft articles
    python manage.py setup_roles        # optional: staff roles
    python manage.py createsuperuser    # for /admin/
    python manage.py runserver
    python manage.py test core          # 273 tests; they never send real email, SMS or call Razorpay/Google/courier APIs

While developing, run with `DJANGO_EMAIL_BACKEND=django.core.mail.backends.console.EmailBackend` so emails (and the
sign-in codes) print in the terminal instead of being sent.

## Configuration (`.env`)
| Variable | Purpose |
|---|---|
| `EMAIL_HOST`, `EMAIL_PORT`, `EMAIL_USE_SSL`, `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD`, `DJANGO_FROM_EMAIL` | the one mailbox every site email is sent from. `python manage.py send_test_email you@example.com` checks it |
| `SITE_URL` | public address, used for links inside emails |
| `RAZORPAY_KEY_ID`, `RAZORPAY_KEY_SECRET`, `RAZORPAY_WEBHOOK_SECRET` | online payments switch on when both keys are present |
| `DATABASE_URL` | `postgres://user:pass@host:5432/db` for PostgreSQL; SQLite is used when unset |
| `DJANGO_DEBUG`, `DJANGO_SECRET_KEY`, `DJANGO_ALLOWED_HOSTS`, `DJANGO_CSRF_TRUSTED_ORIGINS` | production basics |
| `SENTRY_DSN` | optional crash reporting |
| `SELLER_*`, `GRIEVANCE_*` | legal and tax details for invoices and legal pages |
| `ADMIN_URL`, `ADMIN_ALLOWED_IPS`, `ADMIN_2FA`, `TRUST_PROXY_IP`, `CSP_MODE` | admin and header hardening |
| `COURIER_PROVIDER`, `SHIPROCKET_*`, `COURIER_WEBHOOK_TOKEN` | courier |
| `MSG91_*`, `WHATSAPP_*`, `GOOGLE_*`, `EMAIL_QUEUE` | SMS/WhatsApp, Google sign-in, background email queue |

Every variable is listed in `.env.example`.

## What is built
- **Sign-in:** one popup flow (also shown as a popup-style page on direct visits): email, one-time code, new-customer
  details, password option, forgot password, email verification. Codes are hashed, expire in 10 minutes, allow 5 tries
  and are rate-limited.
- **Shop:** hero slider, mega menu, sidebar filters (category, price slider, availability, on sale, type, rating) with a
  mobile drawer, compact cards, search, sorting, pagination, multi-image product pages with reviews.
- **Offers:** coupon codes (`/admin/` > Coupons), sale prices with countdowns (set Sale price / Sale ends on a product),
  rotating announcement bar (`/admin/` > Announcements).
- **Checkout:** cash on delivery or Razorpay (signature-verified, webhook-confirmed, refunds on cancel).
- **Accounts:** profile, saved addresses, order history with cancel and re-order, wishlist.
- **Emails (HTML + text):** codes, welcome, order received, status updates, password changed, newsletter, enquiries.
- **Ops:** admin for products, batches, orders (bulk status, refund and courier actions), coupons, reviews, subscribers; sales
  dashboard, Customer 360, CSV price/stock import, staff roles, optional two-factor and IP allow-list.
- **Fulfilment:** GST invoice PDFs, batch/expiry stock with first-expiry-first picking, courier AWB and tracking, returns portal.
- **Growth:** persistent cart and abandoned-cart emails, search suggestions with typo tolerance, category pages, health library,
  bundles, Subscribe & Save, credit points and referrals, review photos and Q&A, promo banners and content pages.
- **Reach:** Hindi (partial), installable app (PWA), Google and mobile-number sign-in, SMS/WhatsApp order updates (each needs the
  provider's account).

## Scheduled jobs (details in docs/OPERATIONS.md)
    python manage.py expire_unpaid_orders   # every 15 minutes
    python manage.py send_abandoned_carts   # hourly
    python manage.py process_subscriptions  # daily
    python manage.py stock_alerts           # daily
    python manage.py backup_db              # nightly
    python manage.py purge_otps             # daily
    python manage.py run_worker             # always on, only when EMAIL_QUEUE=1

## Brand artwork
`python scripts/generate_assets.py` regenerates the hero slides, social-share image and favicons from the product images.

## Deploy
    docker compose up --build               # web + PostgreSQL, see docker-compose.yml
or run `gunicorn config.wsgi` behind nginx with `DJANGO_DEBUG=0`. CI (`.github/workflows/ci.yml`) runs lint, checks and tests.

## Admin theme and returns

* The admin uses django-jazzmin (`JAZZMIN_SETTINGS` in `config/settings.py`, extra CSS in `static/admin/css/credit-admin.css`).
* Returns: customers open a request from a delivered order; staff handle it in Admin > Return requests (approve, pickup details, mark received, issue refund, dispatch replacement). Every step is logged on the customer's timeline and emailed.
