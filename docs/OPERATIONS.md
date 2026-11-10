# Operations guide

How to run the store safely. Commands run from the project folder.

## 1. First-time legal and tax setup (`.env`)
```
SELLER_LEGAL_NAME=Volkscure Pvt. Ltd.
SELLER_GSTIN=...            # printed on invoices; blank = left off
SELLER_CIN=...
SELLER_LICENCE=Drug Lic. ..., FSSAI ...
SELLER_ADDRESS=...
SELLER_STATE=Uttar Pradesh  # same state as the buyer -> CGST + SGST, otherwise IGST
SELLER_PINCODE=226001       # courier pickup PIN
GRIEVANCE_NAME=...  GRIEVANCE_EMAIL=...  GRIEVANCE_PHONE=...
```
Then in the admin set each product's **HSN code** and **GST %** (default 12). Invoices are numbered `CL/26-27/00001`
per financial year. **Have your accountant check one sample invoice** (delivery-charge tax treatment in particular)
before invoices are used for filing. Staff see a yellow "working draft" note on Terms, Grievance and Cookie pages
until the text is approved: remove `_draft_notice.html` includes once your lawyer signs off.

## 2. Inventory
Product > tick **Track inventory** > add **Batches** (batch no, expiry, quantity). From then on:
* the site sells only what the batches hold, earliest expiry first; batches closer to expiry than 30 days are not sold;
* the product flips to *Out of stock* at zero and back when stock is added;
* cancelling an order (customer, admin or the unpaid-order job) puts units back into the same batches.
Products without "Track inventory" behave as before (unlimited).
Daily: `python manage.py stock_alerts` emails low-stock and near-expiry batches to the order recipients.

## 3. Courier
Default is **static**: the PIN checker shows an estimate and staff type the courier/AWB into the order (the customer
sees it on the tracking page and in the shipped email). To connect Shiprocket set
`COURIER_PROVIDER=shiprocket`, `SHIPROCKET_EMAIL`, `SHIPROCKET_PASSWORD`, `SELLER_PINCODE`, and make sure the pickup
location is named `Primary` in Shiprocket. Then Admin > Orders > action **Create courier shipment (AWB)**.
For live status updates point the courier webhook at `https://<domain>/shipping/webhook/` with header
`x-api-key: <COURIER_WEBHOOK_TOKEN>`. *The Shiprocket calls were written to its public API and tested with mocks only;
run them once against your real account in test mode before relying on them.*

## 4. Admin hardening
| Setting | Effect |
|---|---|
| `ADMIN_URL=ops-9f3k` | admin moves from `/admin/` to `/ops-9f3k/` |
| `ADMIN_ALLOWED_IPS=1.2.3.4,5.6.7.8` | everyone else gets a 404 on the admin. Set `TRUST_PROXY_IP=1` only when the app sits behind your own nginx/load balancer (otherwise the header can be forged) |
| `ADMIN_2FA=1` | staff need an authenticator app. First create a device: `python manage.py shell`, then `from django_otp.plugins.otp_totp.models import TOTPDevice; d = TOTPDevice.objects.create(user=<user>, name='phone'); print(d.config_url)` and turn that URL into a QR code (or type the key) in Google Authenticator. **Create the device before switching 2FA on** or you lock yourself out |

## 5. Security headers
A Content-Security-Policy is sent on every page (admin excluded). All CSS, JS, icons and fonts are served from this
site (`python scripts/vendor_assets.py` re-downloads them). Only Razorpay's checkout is allowed from outside.
`CSP_MODE=report-only` logs violations without blocking, `off` disables it. **Test one real Razorpay payment after
deploying; if the checkout window is blocked, switch to report-only and tell us what the browser console says.**

## 6. Backups and restore drill
Nightly: `python manage.py backup_db` (database + uploaded images into `backups/<timestamp>/`, keeps 14 days;
`--dir` and `--keep-days` change that). Copy `backups/` off the server (object storage or another machine). A backup
that lives only on the same disk is not a backup.
**Restore drill (do this once before launch, then every quarter):**
1. Copy the newest backup folder to a spare machine or folder.
2. SQLite: stop the site, replace `db.sqlite3` with the backup's. PostgreSQL: `createdb restore_test && psql restore_test < db.sql`.
3. Unzip `media.zip` into `media/`.
4. Start the site against the restored data, open the home page, a product, and one recent order in the admin.
5. Write down how long it took. That is your real recovery time.

## 6b. Email queue, reminders and subscriptions
* **Queue:** set `EMAIL_QUEUE=1` and keep `python manage.py run_worker` running (systemd, supervisor or a second Docker
  service). Emails are then stored first and sent by the worker with retries after 1, 5, 30 and 120 minutes; failures
  are visible under Admin > Email jobs (with a Retry action). **If the worker is not running, nothing is sent**, so leave
  the switch at 0 until the worker is set up.
* **Abandoned carts:** `send_abandoned_carts` (hourly) emails a signed-in customer once, 2 hours to 7 days after they left
  items. People who clicked "stop these reminders", or who have ordered since, are skipped.
* **Subscribe & Save:** `process_subscriptions` (daily) places the cash-on-delivery order for every due subscription at
  the subscriber price and sends a reminder two days before. Out-of-stock deliveries are retried after 3 days.
  Customers manage subscriptions in My account > Subscriptions.

## 6c. Content, offers and staff
* **Roles:** run `python manage.py setup_roles` once, then in Admin > Users tick *Staff status* and add the person to
  *Catalogue manager*, *Order desk* or *Marketing*. Only superusers can touch users, groups and two-factor devices.
* **Sales dashboard:** Admin home > Open the sales dashboard. **Customer 360:** Admin > Users > Customer 360 > Open.
* **Prices and stock in bulk:** Admin > Products > Import prices and stock (CSV). Tick *Check only* first. The columns are
  documented on that page; the same import runs from the terminal: `python manage.py import_products file.csv --dry-run`.
* **Banners and pages:** Admin > Banners (home page promo strip, with start/end dates) and Pages (published at `/p/<slug>/`).
* **Blog and category pages:** `python manage.py seed_content` creates category copy, product FAQs and 3 *draft* articles.
  Articles go public only when *Published* is ticked.
* **Bundles:** Admin > Bundles. The saving applies automatically whenever a cart holds every item in the bundle.
* **Credit points and referrals:** rates live in `settings.SHOP` (`points_per_100`, `point_value`, `max_points_pct`,
  `referral_reward`). Support can add or remove points with Admin > Loyalty entries (kind *Manual adjustment*).
* **Returns:** Admin > Return requests. Approving or rejecting emails the customer. Reviews, Q&A answers and returns all
  email the customer when you change their status.
* **Product images:** after adding artwork run `python manage.py optimize_images`; admin uploads get WebP copies automatically.

## 6d. Sign-in options
* **Email code** (always on). **Password** is optional.
* **Google:** create an OAuth client in Google Cloud Console, add `<SITE_URL>/account/google/callback/` as an authorised
  redirect URI, then set `GOOGLE_CLIENT_ID` and `GOOGLE_CLIENT_SECRET`. The button appears by itself.
* **Mobile number:** needs MSG91 (`MSG91_AUTHKEY`, `MSG91_TEMPLATE_OTP` = a DLT-approved template whose first variable is the
  code). A customer first verifies their number in My account > Profile; only verified numbers can sign in, and a number
  claimed by two accounts is refused for both.
* **SMS / WhatsApp order updates:** `MSG91_TEMPLATE_PLACED`, `MSG91_TEMPLATE_STATUS`, `WHATSAPP_TOKEN`, `WHATSAPP_PHONE_ID`,
  `WHATSAPP_TEMPLATE_PLACED`, `WHATSAPP_TEMPLATE_STATUS`. Template variables, in order: customer name, order number,
  then total (placed) or status text (status). These calls were written to the public documentation of both providers and
  tested with mocks; send one test order per channel before announcing it.

## 6e. Hindi
Everything translatable lives in `locale/hi/LC_MESSAGES/django.po`. After editing it run
`python scripts/compile_messages.py` (no GNU gettext needed) and restart. To translate another template: wrap its text in
`{% trans "..." %}` (after `{% load i18n %}`), add the same English text and its Hindi to the `.po` file, compile. The
current translation covers the header, footer, cart and product cards and **has not been reviewed by a native speaker**.

## 6f. App install (PWA)
The site can be installed from the browser menu (Add to Home screen) and shows an offline page without a connection.
Pages are cached only for offline fallback; checkout, payments, accounts and the admin are never cached. Raise
`PWA_VERSION` in settings after a big release to make every browser drop old copies. It needs HTTPS in production.

## 7. Monitoring
* **Uptime:** point UptimeRobot / BetterStack at `https://<domain>/healthz/` (200 `{"status":"ok"}` only when the database answers), 1-minute interval, alert to email + phone.
* **Errors:** create a free Sentry project and put its DSN in `SENTRY_DSN`.
* **Scheduled jobs** (cron or the host's scheduler):

| Command | When |
|---|---|
| `expire_unpaid_orders` | every 15 minutes |
| `run_worker` | always running (only with `EMAIL_QUEUE=1`) |
| `send_abandoned_carts` | hourly |
| `process_subscriptions` | daily, morning |
| `stock_alerts` | daily, morning |
| `purge_otps` | daily |
| `backup_db` | nightly |

## 8. Testing before launch
* `python manage.py test core` (all automated tests) and `python manage.py check --deploy`.
* **Load test (staging only):** `python scripts/loadtest.py https://staging.example.com --users 50 --rounds 10`.
  It exercises browse and cart, not checkout. A run on the development laptop (SQLite, single process) handled
  ~55 requests/second with a 95th percentile of ~0.4 s and no errors; that says nothing about production hardware,
  so repeat it on the real server. Checkout concurrency is covered by tests (stock cannot be oversold; a coupon cannot be over-used).
* **Penetration test:** we have not had an outside party test this site. Before launch, commission one (a freelance
  tester or a firm can do a small shop in 2 to 4 days). Give them this checklist as a starting point: authentication
  and OTP brute force, session handling, IDOR on orders/invoices (invoice links are signed), payment tampering
  (amount, signature, webhook replay), coupon abuse, stored XSS in reviews/enquiries, file upload (product images),
  admin exposure, rate limits, TLS configuration.
