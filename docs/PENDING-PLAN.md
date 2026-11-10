# Pending plan: what is done, what is left, who does it

> **4 Nov 2026:** the site was reworked to the client content brief (B2B distributor site). Read `GO-LIVE-STATUS.md` first: it says what can go live tomorrow, what is blocked and what we need from the client. The consumer-store features described below are still built but switched off by default.

Updated 30 Oct 2026. Sprints A, B and C are built, tested (231 automated tests) and checked in a browser at desktop and
phone widths. What remains is almost entirely **accounts, content and approvals that only the client can supply**, plus a
few things that can only be proven on the live server. `OPERATIONS.md` explains how to run everything.

Legend: **Done** = built and tested. **Needs X** = built, but switching it on or trusting it needs something from the client.

## 1. Delivered

### Foundation (earlier work)
Premium flat design (Poppins), hero slider, mega menu, sidebar filters, popup sign-in with email codes (OTP), password
option and reset, coupons and sale prices, Razorpay (verified payments, webhook, refunds), emails for every event,
reviews, wishlist, order tracking, production hardening (WhiteNoise, PostgreSQL, security headers, Docker, CI).

### Sprint A: launch readiness
| Item | Status |
|---|---|
| GST tax invoice PDF (CGST+SGST or IGST, sequential numbers per financial year, signed links for guests, attached to shipped/delivered emails) | **Done.** Needs GSTIN, HSN codes and one sample checked by the accountant |
| Inventory with batches and expiry, earliest-expiry-first stock decrement, stock returned on cancel, low-stock and expiry alert emails, cannot oversell | **Done** |
| Courier layer: AWB and tracking shown to the customer, status webhook, timeline events, real delivery estimate in the PIN checker | **Done** with a PIN-zone estimate. Shiprocket adapter **needs a Shiprocket account** and a live test (tested with mocks only) |
| Terms of Sale, Grievance Officer, Cookie policy pages and cookie notice | **Done as drafts.** Needs lawyer-approved text and the legal details |
| Content-Security-Policy; Bootstrap, icons and fonts now served from this site (no third-party requests) | **Done.** One real Razorpay payment must be tested after deploy |
| Admin hardening: custom URL, IP allow-list, two-factor (authenticator app) | **Done.** Switch on in `.env` (see OPERATIONS) |
| Backups (`backup_db`), restore drill written down, `/healthz/` for uptime monitors, Sentry hook | **Done.** Needs the nightly job scheduled, an uptime-monitor account and a Sentry project. The restore drill must be run once on the server |
| Load test | Script written and smoke-tested on a laptop (about 55 requests/s, no errors). **Must be repeated on staging** |
| Penetration test | **Not done.** Needs an outside tester; a checklist is in OPERATIONS |

### Sprint B: conversion and retention
| Item | Status |
|---|---|
| Cart saved for signed-in customers (follows them across devices); abandoned-cart reminder email (once, with one-click stop) | **Done** (schedule `send_abandoned_carts` hourly) |
| Search suggestions as you type and typo tolerance ("mahajont" finds MahaJoint) | **Done** |
| Category pages with SEO copy, per-product FAQs with FAQ markup, health library (blog) | **Done.** The 3 starter articles are **drafts**: have them read by a doctor/lawyer, then tick Published. The plan asked for 10 articles; the other 7 need to be written |
| SMS (MSG91) and WhatsApp (Meta Cloud API) order updates | **Needs accounts.** MSG91 DLT-approved templates and Meta-approved WhatsApp templates; tested with mocks only |
| Self-serve returns (7 days after delivery, photo, staff approve/reject, emails) | **Done** |
| Image pipeline: WebP in three sizes for artwork and for admin uploads, responsive `<picture>` on product cards | **Done** (run `optimize_images` when artwork changes) |
| Background email queue with retries (`EMAIL_QUEUE=1` + `run_worker`) | **Done** as a database queue that needs no extra software. Switch to Celery/Redis only if volume grows |
| Admin sales dashboard (revenue, orders, average order value, repeat rate, top products, things needing attention); staff roles (Catalogue manager, Order desk, Marketing) | **Done** |

### Sprint C: scale
| Item | Status |
|---|---|
| Subscribe & Save (5% off, monthly to 3-monthly, reminder 2 days before, skip/pause/cancel) | **Done.** Subscription orders are **cash on delivery only** (no saved cards) |
| Credit points (earn 2 per Rs 100 on delivery, spend up to 20% of an order), referrals (100 points each after the friend's first delivery; self and same-phone referrals blocked) | **Done.** Rates are in `settings.SHOP`; confirm them with the client |
| Bundles/combos applied automatically in the cart | **Done** (create them under Bundles in the admin) |
| Review photos, helpful votes, product Q&A (answers appear after staff reply, asker is emailed) | **Done** |
| Hindi version with a language switch | **Partly done.** Header, menu, footer, cookie notice, cart and product cards are translated. The other pages (home sections, product pages, checkout, account, emails) are still English. The Hindi text is a **draft that needs a native speaker's review** |
| PWA: installable, offline page, caches only pages and static files, never checkout/payments/accounts | **Done** |
| CMS: promo banners (with dates), editable content pages; bulk price and stock import (CSV, check-first); Customer 360 page; staff roles | **Done** |
| Sign in with a mobile number | **Needs an SMS provider (MSG91).** Works only for numbers a customer has verified from their profile |
| Sign in with Google | **Needs a Google OAuth client** (ID and secret). Tested with mocks only |

## 2. Needs a decision or an account from the client (blocks go-live)

| # | Item | What to send us |
|---|---|---|
| 1 | Razorpay keys | Test keys first, then live keys and the webhook secret. Webhook URL: `/payments/razorpay/webhook/`, events `payment.captured`, `payment.failed`, `order.paid` |
| 2 | Real prices and MRP | Final list (a CSV works: see the import screen) |
| 3 | Licences and legal entity | Drug / AYUSH / FSSAI numbers, GSTIN, CIN, address, state, pickup PIN, grievance officer name and phone, HSN codes |
| 4 | Lawyer-approved Terms, Privacy (DPDP), Returns, Cookie and Grievance text | Approved text |
| 5 | Courier account | Shiprocket (or Delhivery) login and the pickup location name |
| 6 | Studio product photos, leaflets, certificates | Files |
| 7 | Domain, hosting, SSL | Decision and budget |
| 8 | SMS and WhatsApp | MSG91 account with DLT templates (placed, status, code) and a Meta WhatsApp Business number with approved templates |
| 9 | Google sign-in | A Google Cloud OAuth client with the redirect URI `<site>/account/google/callback/` |
| 10 | Change the mailbox password | It was shared in chat; put the new one in `.env` only |
| 11 | Business model decision | Brand store only, or e-pharmacy (decides whether prescription upload is built) |
| 12 | Monitoring accounts | Uptime monitor (UptimeRobot/BetterStack) and a Sentry project |
| 13 | Approval of the offer rules | Subscribe discount, points rates, referral reward, 7-day returns window |

## 3. Still open (not built)
- Penetration test by an outside party (checklist in OPERATIONS).
- Restore drill and load test on the real server.
- 7 more health-library articles (10 were planned), and Hindi for the remaining pages and emails.
- Celery/Redis (only if the database queue becomes a bottleneck).
- Only if the client chooses to become an e-pharmacy: prescription upload and pharmacist verification, patient profiles, Rx order workflow.

## 4. How to switch on online payments (3 steps)
1. Set `RAZORPAY_KEY_ID`, `RAZORPAY_KEY_SECRET` (and `RAZORPAY_WEBHOOK_SECRET`) in `.env`. Restart.
2. In the Razorpay dashboard add the webhook `https://<your-domain>/payments/razorpay/webhook/` with the same secret.
3. Place a test order with a Razorpay test card or UPI id. The order moves to *Paid*, the customer gets the email, and
   cancelling it from My orders starts a refund. Check that the Razorpay window opens (the Content-Security-Policy allows it).

## 5. Routine jobs to schedule on the server
| Command | How often | Purpose |
|---|---|---|
| `expire_unpaid_orders` | every 15 minutes | cancel online orders never paid, give coupons, stock and points back |
| `run_worker` | always running | sends queued emails (only when `EMAIL_QUEUE=1`) |
| `send_abandoned_carts` | hourly | cart reminder emails |
| `process_subscriptions` | daily, morning | place due Subscribe & Save orders, send reminders |
| `stock_alerts` | daily, morning | low-stock and near-expiry email |
| `purge_otps` | daily | delete old one-time codes |
| `backup_db` | nightly | database and uploaded images, keeps 14 days |
