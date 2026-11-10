# Credit Lifesciences store: gap analysis and build roadmap

Compared against Amazon-level ecommerce and pharmacy-level sites (PharmEasy, Tata 1mg, Apollo Pharmacy).
Audit date: 29 Oct 2026. Based on the actual code in this repository, not assumptions.

**Progress update, 30 Oct 2026:** since this audit the following gaps were closed: online payments (Razorpay) with refunds,
coupons and sale pricing, one-time-code sign-in (login, sign-up, reset, email verification) in a popup flow, the premium UI
redesign with a fixed mega menu and hero slider, PostgreSQL support, WhiteNoise, security headers, Docker and CI. See
`PENDING-PLAN.md` for the current open list and what the client still has to provide.

---

## 1. Where we stand today

**What exists and works (verified by 27 automated tests and browser runs):**

| Area | Status |
|---|---|
| Catalogue | 6 products, 3 categories, MRP / selling price / discount, per-product gallery (2 to 4 images), composition, directions, safety, manufacturer table |
| Discovery | Header search (text match), category filter, sort, related products |
| Product page | Gallery with zoom and lightbox, reviews with verified-purchase badge, PIN code format check, sticky mobile buy bar, Product JSON-LD |
| Cart and checkout | Session cart, free-delivery meter, guest and account checkout, saved addresses, COD only |
| Accounts | Email sign-up / sign-in, email verification, forgot / change password, lockout after 5 failures, profile, addresses, orders (cancel, re-order), wishlist |
| Orders | Order numbers, status workflow, tracking by order no. + mobile, admin bulk status actions |
| Emails | 9 transactional emails (HTML + text) incl. status-change emails triggered from admin |
| Admin | Products + images, orders, reviews moderation, enquiries, profiles |
| Quality | 27 end-to-end tests, CSRF, honeypot, flat Poppins design system |

**Honest summary:** this is a solid, working *brand store MVP*. It is **not yet launch-ready for real customers and real money**, and it is far from Amazon / PharmEasy scale. The gaps below are grouped so you can see what blocks launch versus what is growth.

**Important framing.** Credit Lifesciences is a *manufacturer / marketer* selling its own 4 OTC products. PharmEasy and 1mg are *licensed e-pharmacy marketplaces* with thousands of SKUs, prescription workflows, pharmacists and logistics networks. Copying them one-to-one is a different business. The realistic target is **"a premium brand D2C store with pharmacy-grade trust and Amazon-grade checkout"**. Section 6 marks which pharmacy features are essential for that and which only matter if the client wants to become an e-pharmacy.

Priority legend: **P0** = blocks launch. **P1** = needed in the first 2 months. **P2** = growth / scale. **P3** = long-term / only if business model changes.

---

## 2. Gap analysis, A to Z

### A. Legal, regulatory and trust (pharmacy-critical)

| Gap | Today | Benchmark | Priority |
|---|---|---|---|
| Drug / AYUSH / FSSAI licence numbers shown on site | Only a Mfg. Lic. no. in the product table | Licence numbers + licensed entity + pharmacist name in footer and About | **P0** |
| Online sale permission | Not verified | E-pharmacy registration / state drug-licence cover for online sale of OTC and ayurvedic products | **P0** (client to confirm) |
| Terms of Sale / Terms of Use | Missing | Full legal terms | **P0** |
| Privacy policy aligned to DPDP Act 2023 | One short notice | Consent, data-retention, deletion request, grievance contact | **P0** |
| Grievance officer + contact (IT Rules) | Missing | Named officer, email, response timelines | **P0** |
| Refund / cancellation / shipping policy reviewed by a lawyer | Draft text only | Reviewed policy with exact timelines | **P0** |
| GSTIN, company address, CIN on site and invoices | Address is empty in settings | Full legal entity block in footer | **P0** |
| Tax invoice (GST) PDF per order | Missing | Auto-generated, emailed, downloadable | **P0** |
| Cookie consent banner | Missing | Granular consent | P1 |
| Claims review (health claims on ayurvedic / supplement pages) | Softened once | Legal / regulatory sign-off on every claim | **P0** |
| Prescription handling for Rx products | Rx hidden, enquiry only | Upload + pharmacist verification (only if selling Rx) | P3 |

### B. Catalogue and product page

| Gap | Today | Benchmark | Priority |
|---|---|---|---|
| Real product photography (angles, in-hand, lifestyle, leaflet) | Crops of client artwork | 5 to 8 studio images + 360 / video | **P0** for premium feel |
| Pack-size / variant selector | One pack per product | Variants with their own price and stock | P1 |
| Per-product FAQs | None | 5 to 8 FAQs (also feeds FAQ schema for SEO) | P1 |
| Leaflet / package insert download (PDF) | Image only for Dr. GAS Liquid | PDF per product | P1 |
| Certificates / lab-test reports | None | Batch COA or certificate badges | P1 |
| "Frequently bought together", bundles | None | Bundle offers | P2 |
| Salt substitutes / alternatives | None | Shown on every medicine page (only relevant for a marketplace) | P3 |
| Q&A on product page | None | Customer questions answered by team | P2 |
| Review photos, helpful votes, sort / filter reviews | Text reviews only | All three | P2 |
| Low-stock message and back-in-stock alerts | `in_stock` flag only | "Only 3 left" + notify me | P1 |
| Recently viewed | None | Strip on home and PDP | P2 |
| Breadcrumb schema, FAQ schema, per-product Open Graph image | Product + Organization only | Full structured data | P1 |

### C. Discovery and navigation

| Gap | Today | Benchmark | Priority |
|---|---|---|---|
| Search autosuggest, typo tolerance, synonyms (e.g. "gas", "acidity", "hemoglobin") | Plain substring match, no suggestions | Instant suggestions with thumbnails (Postgres trigram / Meilisearch / Algolia) | P1 |
| Filters: price, rating, availability, brand | Category only | Faceted filters with counts | P1 |
| Dedicated category pages with SEO copy | One shop page with client-side filter | `/shop/digestive-care/` etc. with unique content | P1 |
| Pagination / infinite scroll | Not needed at 6 SKUs | Required past about 24 SKUs | P2 |
| Collections (best sellers, new, offers) | None | Curated collections | P2 |
| Personalised recommendations | None | "Based on your orders" | P3 |

### D. Cart and checkout

| Gap | Today | Benchmark | Priority |
|---|---|---|---|
| **Online payments** (UPI, cards, net-banking, wallets) | COD only | Razorpay / PayU with retry, saved methods | **P0** |
| Coupons and offers engine | None | Promo codes, first-order discount, bank offers | P1 |
| Cart saved to account across devices | Session only | Persistent cart | P1 |
| PIN code to city / state auto-fill and real serviceability | Format check; ETA is a placeholder (3 to 7 days) | Serviceability table from courier + real ETA | **P0** |
| COD controls (max value, COD fee, prepaid nudge) | None | Configurable | P1 |
| Abandoned-cart recovery emails / WhatsApp | None | 3-step sequence | P1 |
| Save for later, quantity limits per product, stock check at checkout | Max qty only; no stock decrement | Live stock reservation | **P0** |
| Order edit / address change before shipping | Cancel only | Edit window | P2 |
| Gift options, GST number capture for business buyers | None | Optional | P2 |
| Subscribe and Save (monthly refills) | None | Strong fit for supplements | P2 |
| Wallet / loyalty points / referral | None | Points + referral rewards | P2 |

### E. Payments and finance

| Gap | Priority |
|---|---|
| Payment gateway integration, webhooks, signature verification | **P0** |
| Refund flow (full / partial) wired to the gateway | **P0** |
| COD cash-collection reconciliation with courier remittance | P1 |
| GST-correct pricing and invoice numbering series | **P0** |
| Settlement and revenue reports | P1 |

### F. Orders, inventory and fulfilment

| Gap | Today | Benchmark | Priority |
|---|---|---|---|
| **Inventory with batch and expiry (FEFO)** | None | Pharma-grade stock by batch, expiry-aware picking | **P0** |
| Courier integration (Shiprocket / Delhivery): AWB, labels, pickup | Free-text tracking note | API-driven, live tracking events | **P0** |
| Real tracking timeline from courier | 4 static steps | Event-level scan history | P1 |
| Returns / replacement (RMA) workflow | Email / phone only | Self-serve request with photos, status, refund | P1 |
| NDR (non-delivery) handling | None | Automated re-attempt flow | P1 |
| SMS and WhatsApp order updates | Email only | WhatsApp Business API templates | P1 |
| Partial shipment, split orders | None | Supported | P3 |
| Picking / packing slips | None | Printable | P1 |

### G. Accounts and authentication

| Gap | Today | Benchmark | Priority |
|---|---|---|---|
| **Phone OTP login** (India-first) | Email + password only | OTP is the default on PharmEasy / 1mg / Amazon India | P1 |
| Social login (Google) | None | One-tap sign-in | P2 |
| Remember me / session length control | Always default session | Checkbox | **in this redesign** |
| Verify-pending and verified pages | Banner and flash message | Dedicated, polished pages with resend cooldown | **in this redesign** |
| Password strength meter, show / hide | None | Present | **in this redesign** |
| Change-email flow, delete-account (DPDP right to erasure) | None | Self-serve | P1 |
| Login history, active sessions, sign out everywhere | None | Present | P2 |
| 2FA for staff / admin | None | TOTP for admin users | **P0** for admin |
| IP-level rate limiting + CAPTCHA on sign-up / login / forms | Per-email lockout only; honeypot on enquiry | django-axes or a WAF, hCaptcha / Turnstile | P1 |
| Breached-password check | Django validators only | HIBP k-anonymity | P2 |
| Patient / family profiles, prescription locker | None | Core on pharmacy sites | P3 |

### H. Content, SEO and marketing

| Gap | Today | Priority |
|---|---|---|
| `robots.txt`, `sitemap.xml`, canonical URLs, per-page meta descriptions | All missing or generic | **P0** |
| Blog / health library (acidity, anaemia, joint care) with medical review | None | P1 |
| Hindi version of site and product pages | English only; labels are bilingual | P1 |
| Analytics: GA4, Meta Pixel / CAPI, conversion events, Search Console | None | **P0** |
| Newsletter capture and campaigns (Mailchimp / Brevo) | None | P1 |
| Landing pages for ads, UTM capture on orders | None | P2 |
| Social proof blocks (real reviews, press, certifications) | Placeholder-free by design, but empty | P1 |
| Referral and affiliate tracking | None | P2 |

### I. Performance and infrastructure

| Gap | Today | Benchmark | Priority |
|---|---|---|---|
| Image pipeline (WebP / AVIF, responsive `srcset`, fixed dimensions to prevent layout shift) | Raw JPEG / PNG, about 4 MB of images in total | Resized variants via CDN | P1 |
| CDN and long-lived cache headers, Brotli / gzip | Django dev static serving | CDN + hashed static files (WhiteNoise / S3) | **P0** |
| Self-hosted Bootstrap, icons and fonts | Loaded from third-party CDNs (privacy, render-blocking) | Self-hosted, subset, preloaded | P1 |
| Database | SQLite | PostgreSQL with backups and point-in-time recovery | **P0** |
| Caching | In-process memory cache only | Redis for cache, sessions, rate limits, queues | P1 |
| Background jobs | Emails sent inside the request | Celery / RQ queue with retries | P1 |
| Query efficiency | 6 to 11 queries per page, rating stats queried per card | Annotated queries, fragment caching | P1 |
| Core Web Vitals budget (LCP under 2.5 s on 4G) | Not measured | Lighthouse CI gate | P1 |
| Installable PWA / offline shell | None | Add-to-home-screen, offline cart view | P2 |

### J. Security and compliance engineering

Findings from `manage.py check --deploy` and code review:

| Gap | Priority |
|---|---|
| HSTS include-subdomains / preload not set; secret key must be 50+ random chars | **P0** |
| No Content-Security-Policy, Referrer-Policy, Permissions-Policy headers | P1 |
| Admin at the default `/admin/` URL, no 2FA, no IP allow-list | **P0** |
| No audit log of staff actions (price changes, refunds, status edits) | P1 |
| No error monitoring (Sentry), uptime checks or alerting | **P0** |
| No automated database / media backups or restore drill | **P0** |
| Secrets in plain environment, no secret manager | P1 |
| Dependency and vulnerability scanning (pip-audit, Dependabot) | P1 |
| PII minimisation, data-retention jobs, encrypted backups | P1 |
| Uploaded files: type / size validation and malware scan (needed for Rx uploads later) | P2 |
| Penetration test before launch | P1 |

### K. Admin and operations

| Gap | Priority |
|---|---|
| Dashboard: sales, orders by status, AOV, top products, repeat rate | P1 |
| Role-based access: support, warehouse, pharmacist, marketing | P1 |
| Coupon, banner, homepage, FAQ and page CMS (no code changes for content) | P1 |
| Bulk product / price import and export (CSV) | P1 |
| Inventory screens: stock by batch, low-stock alerts, expiry alerts | **P0** |
| Customer 360 view (orders, tickets, reviews in one screen) | P2 |
| Internal order notes and activity log | P1 |
| Refund and replacement UI | P1 |
| Editable email templates from admin | P2 |

### L. Customer support

| Gap | Today | Priority |
|---|---|---|
| Help centre / FAQ hub | Home FAQ only | P1 |
| Ticketing (Freshdesk / Zoho Desk) linked to orders | Phone, email, WhatsApp button | P1 |
| WhatsApp Business API (automated order updates, catalogue) | Click-to-chat link | P1 |
| Callback request, support hours display | Enquiry form | P1 |
| CSAT / NPS after delivery | None | P2 |
| Chatbot / AI assistant for product and order queries | None | P3 |

### M. Accessibility, UX polish and quality

| Gap | Priority |
|---|---|
| Full WCAG 2.2 AA audit (contrast, focus order, form errors announced, skip links exist) | P1 |
| Custom 404 exists, **500 page missing** | **P0** |
| Skeleton loaders, optimistic UI, better empty states | P2 |
| Form UX: inline validation, input masks, autofill hints | **in this redesign** (auth) |
| Microcopy and error-message review | P1 |
| Dark mode | P3 |
| Native app or TWA wrapper | P3 |

### N. Engineering and delivery

| Gap | Today | Priority |
|---|---|---|
| Dockerfile, docker-compose, `.env.example`, `.gitignore` | Missing | **P0** |
| CI pipeline (tests, lint, type check, security scan) | None | **P0** |
| Staging environment and release process, migrations policy | None | **P0** |
| Linting / formatting (ruff, black), type hints, pre-commit | None | P1 |
| Browser tests (Playwright) for checkout and auth in CI | Manual runs only | P1 |
| Load test of checkout (Locust / k6) | None | P1 |
| Pinned dependencies, lock file | `Django>=5.2,<6.0` only | P1 |
| Observability: structured logs, request IDs, metrics | None | P1 |

### O. Data and analytics

| Gap | Priority |
|---|---|
| Funnel (view → add to cart → checkout → paid), cohort retention, LTV | P1 |
| Search analytics (no-result queries) | P2 |
| Server-side conversion events to ad platforms | P1 |
| BI dashboard (Metabase / Looker Studio) | P2 |

### P. Amazon-level capabilities (long-term)

One-click buy with saved payment, Subscribe and Save, membership programme with free delivery, deals and timers, A/B testing platform, recommendation engine, marketplace / seller onboarding, multi-warehouse routing, international shipping, gift cards. All **P2 to P3**, to be considered once there are 50+ SKUs and steady order volume.

---

## 3. UI and UX gaps (what this redesign addresses)

| Gap found in the current UI | Fix |
|---|---|
| Visuals are clean but generic: limited depth, no signature element, hero is a plain 2x2 grid | Premium design system: refined type scale, 8-pt spacing, layered surfaces, restrained gold accent, richer hero, mega-menu |
| Header is functional but dense; shop dropdown is a plain list | Mega-menu with product thumbnails and prices |
| Product cards lack hover affordances and quick actions | Refined cards: image zoom, quick add, clearer price hierarchy, rating row |
| Footer is link-only | Newsletter capture, trust badges, payment / delivery notes, back-to-top |
| Auth pages are a centred card with plain inputs | Split-screen layout with brand panel, floating labels, show / hide password, strength meter, remember me, inline validation, verify-pending and verified pages, polished reset flow |
| No 500 page, plain empty states | Branded error pages and illustrated empty states |
| Motion is minimal | Subtle, reduced-motion-safe transitions |

---

## 4. Roadmap

Assumes 1 to 2 developers. Durations are working days and include testing.

### Phase 0: UI redesign and perfect authentication (this iteration)
Premium design system, new header / mega-menu, home page, product cards, footer with newsletter, split-screen auth pages, verify-pending / verified pages, remember me, strength meter, branded 404 / 500, updated tests. **About 5 days.**

### Phase 1: Launch readiness (P0 items), 4 to 6 weeks
1. **Legal pack (week 1, client-led):** licences on site, Terms, DPDP privacy policy, grievance officer, reviewed policies, GST invoice format. *Client dependency.*
2. **Real prices, stock and photography (week 1 to 2):** replace placeholder prices; studio photos; leaflets and certificates.
3. **Payments (week 2 to 3):** Razorpay checkout, webhooks, refunds, payment-failure retry, COD rules.
4. **Inventory and batches (week 2 to 3):** stock per batch with expiry, decrement on order, low-stock and expiry alerts, FEFO picking list.
5. **Shipping (week 3 to 4):** Shiprocket / Delhivery API: serviceability by PIN, ETA, AWB, labels, tracking events into the order timeline.
6. **GST invoice PDF (week 3):** numbering series, emailed on dispatch, downloadable in account.
7. **Production platform (week 4):** PostgreSQL, Redis, Docker, CI, staging, WhiteNoise / S3 + CDN, HTTPS, hardened settings, admin 2FA and custom URL, backups, Sentry, uptime checks.
8. **SEO and analytics foundations (week 4):** robots, sitemap, canonicals, meta, GA4 + Pixel events, Search Console.
9. **Security pass (week 5):** CSP and headers, rate limiting + CAPTCHA, `check --deploy` clean, penetration test.
10. **Launch QA (week 6):** Playwright suite, load test, accessibility fixes, soft launch to a small audience.

### Phase 2: Conversion and retention (weeks 7 to 14)
Coupons and first-order offer, abandoned-cart emails, phone OTP login, search autosuggest and filters, category pages, per-product FAQs and FAQ schema, WhatsApp / SMS order updates, returns portal, newsletter campaigns, blog (first 10 medically reviewed articles), Hindi site, image pipeline (WebP / srcset), self-hosted assets, background job queue, help centre and ticketing, admin dashboard, role-based access.

### Phase 3: Scale (weeks 15 to 26)
Subscribe and Save, loyalty and referral, bundles, review photos and Q&A, CMS for banners / pages, bulk import, customer 360, PWA, A/B testing, BI dashboards, CSAT, recently viewed and recommendations.

### Phase 4: Only if the client wants an e-pharmacy
Prescription upload and pharmacist verification, patient profiles, Rx order workflow, schedule-wise controls, e-pharmacy registration, multi-vendor catalogue, drug database and substitutes. This is a separate programme (6+ months) with heavy regulatory work.

---

## 5. What the client must provide (blocks Phase 1)

1. Drug / AYUSH / FSSAI licence numbers and confirmation that online sale is permitted for each product.
2. GSTIN, CIN, registered address, authorised signatory, grievance officer.
3. Final MRP and selling prices, and the approved product claims.
4. Studio product photography, leaflets and certificates.
5. Payment-gateway account (Razorpay / PayU) with KYC completed.
6. Courier / logistics partner account and pickup address.
7. A real SMTP / transactional email account (SES, Brevo, Postmark) and a verified sending domain.
8. Domain name, hosting preference and budget.
9. Lawyer-reviewed Terms, Privacy and Returns policies.
10. Decision: brand store only, or become an e-pharmacy (Phase 4).

---

## 6. Pharmacy features: essential versus marketplace-only

| Feature | Essential for a brand store? |
|---|---|
| Licences and pharmacist / entity details visible | **Yes** |
| Rx products not sold online, clear messaging | **Yes** (already done) |
| Batch and expiry traceability | **Yes** |
| Verified reviews, genuine-product assurance, clear returns for damaged / expired items | **Yes** |
| Health content with medical review | **Yes** (SEO and trust) |
| Prescription upload and verification | Only if selling Rx |
| Teleconsultation, lab tests, refill reminders, family profiles | No (marketplace / care-platform features) |
| Salt substitutes and drug database | No |

---

## 7. Suggested success metrics

Conversion rate above 2%, checkout completion above 60%, cart abandonment recovery above 8%, LCP under 2.5 s, 99.9% uptime, RTO (return-to-origin) under 8%, support first response under 1 hour, repeat purchase rate above 25% after 90 days.
