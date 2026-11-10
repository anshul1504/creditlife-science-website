# Credit Lifesciences website: kya bana hai, kya baaki hai, kal live ho sakta hai ya nahi

Date: 4 Nov 2026. Yeh ek simple status document hai. Detail ke liye `PENDING-PLAN.md` aur `OPERATIONS.md` dekhein.

## 0. Latest update (10 Nov 2026)

**Naya kya hua**
- **Content admin se manage hota hai:** Site settings, Hero slides, Team messages (Founder & CEO aur Director), Highlights, Timeline, FAQs, Job roles, Banners, Announcements, Pages, Districts, Distributor listings. Code badalne ki zaroorat nahi.
- **Admin theme:** Jazzmin (navy + green, Poppins). Login: `/admin/`. Local sample login: `admin` / `Admin@12345` aur customer `demo@example.com` / `Demo@12345` (sirf local DB, live par naya superuser banayein: `python manage.py createsuperuser`).
- **Razorpay LIVE keys:** `.env` me lagi hain (git me nahi jaati). **Webhook secret abhi set nahi hai**: bina uske browser band hone par payment auto-confirm nahi hoga. Razorpay dashboard me webhook banakar `RAZORPAY_WEBHOOK_SECRET` set karein.
- **Founder aur Director alag log hain:** Prakash Harendra Singh (Founder & CEO) aur Prabhat Harendra Singh (Director). Dono messages About aur Home par hain.
- **Return / replacement system (e-commerce level):** har request ka reference (RR-xxxxxxx), customer ke account me "Returns" list + timeline, request withdraw, admin me status (Requested, Approved, Pickup arranged, Received and checked, Resolved, Not approved, Withdrawn), pickup courier/AWB, partial refund (Razorpay se, COD/other me manual ka warning), replacement dispatch (stock apne aap kam hota hai) aur har step par customer ko email. Policy ab bhi: sirf damaged goods + unboxing video.
- **Newsletter section hata diya gaya.** Hero carousel auto-rotate hota hai, sab pages flat design (koi dots/circles nahi), TV/4K screens par width badhti hai.
- **Check:** 281 se zyada automated tests pass, `check --deploy` aur `collectstatic` (DEBUG=0) clean, `makemigrations --check` clean.

**Abhi bhi aapse chahiye**
1. **Hero photos:** slide 1, 3, 4, 5 par real photos hain (Wikimedia Commons). Slide 2 aur 6 abhi product collage hain. Apni real photos Admin > Hero slides me upload karein. Slide 4 (CC BY-SA 4.0, Haryana paddy road) aur slide 5 (CC BY 4.0, Pamban bridge) ko attribution chahiye, ya unhe apni photo se badal dein.
2. **Distributor details:** 19 listings hidden hain. Consent aur contact aane par admin me "consent given" aur "published" tick karein.
3. **Volkscure Private Limited:** Founder ki designation me naam hai, confirm karein ki site par rakhna hai.
4. **Social links:** X, Threads, LinkedIn khaali hain (Site settings > Social media).
5. **Keys rotate karein:** Razorpay live secret aur mailbox password chat me share hue the.
6. **Production setup:** server + domain + HTTPS, PostgreSQL (`DATABASE_URL`), naya `DJANGO_SECRET_KEY`, `DJANGO_DEBUG=0`, admin 2FA / IP allowlist.


## 1. Seedha jawab: kal live?

**Phase 1 (kal live ho sakta hai):** company website + products (price/MRP ke saath) + Distribution Network + Become a Distributor form + Contact/Careers/FAQ + legal pages + WhatsApp se order. Iske liye sirf yeh chahiye: **hosting + domain + SSL** (neeche section 4) aur aapka **content approval** (section 3).

**Phase 2 (kal nahi):** online cart + checkout + payment (UPI/card/net banking). Yeh tab tak band rahega jab tak Razorpay keys, shipping charges aur kuch policy answers nahi milte. Site is baat ko khud sambhalti hai: checkout par likha aata hai "Online ordering opens shortly" aur WhatsApp / enquiry se order ka rasta dikhta hai. Koi galat order nahi banega.

**"Project close" kal nahi hoga**, kyunki kuch cheezein sirf client de sakta hai (keys, approvals, answers). Code ka kaam Phase 1 ke liye taiyaar hai; Phase 2 ka code bhi taiyaar hai, bas switch on karne ke inputs baaki hain.

**Check kiya gaya:** 281+ automated tests pass, 17 pages desktop + phone par browser me dekhe (koi JS / CSP error nahi, koi horizontal scroll nahi, 14 screen widths par audit), production static build theek.

## 2. Aaj ke brief ke hisaab se kya kiya gaya

| Brief ki baat | Website par |
|---|---|
| Tagline "Serving Health" (Hindi me bhi English) | Header, footer, titles me lagi |
| B2B pehle, distributors | Home hero: "Building Trusted Partnerships. Serving Health." + 6 rotating themes + CTAs (Become a Distributor / Explore Products / Network / Contact). Hero me Rs 5 lakh nahi dikhaya |
| Company details | Address, askus@ / sales@ email, 9936360600 (phone + WhatsApp), 17 saal, 2009, founder, footer me sab |
| About Us | Overview, founder story (draft), founder message (approved copy), journey, vision, mission, values, commitment. Alag Quality page hata diya (purane link About par jaate hain) |
| Distributor page | Intro, benefits, Rs 5,00,000 minimum, eligibility (GST, Form 20B/21B...), support, 9 field ka enquiry form (GST number format check ke saath). "Form bharne se distributorship nahi milti" likha hai |
| Distribution Network | 20 districts (list), 3 status (Active / Open for appointment / Upcoming) filter ke saath, directory (sirf consent ke baad), expansion invitation |
| Products | Ayurvedic / Allopathic filter, composition filter, health problem filter, card: image, naam, MRP, View Details. "Request catalogue" button |
| Contact | Enquiry type (Product / Order / Business Partnership / General / Complaint), email required, floating WhatsApp |
| Careers | 7 roles, 9 field ka form, CV upload (PDF/Word, 5 MB) |
| FAQs | 8 sawal, brief ke facts se likhe jawab |
| Legal & Regulatory | Form 20B (UP5120B001001), Form 21B (UP5121B001001), GSTIN 09KWDPS4937K1ZM, registered office. "Yeh quality certificate nahi hain" likha hai. ISO / WHO-GMP ka koi claim nahi |
| Ordering rules | Sirf registered user order kare (login zaroori), prices sabko dikhte hain, payment sirf online (COD band), shipping buyer ki, delivery 5-7 business days, free-delivery ka koi offer nahi |
| Damaged goods | Sirf damaged goods ka replacement, **unboxing video zaroori**. Refund / dusre reasons ka koi promise nahi |
| Footer | Brief ke saare links + Careers + FAQs + Facebook / Instagram / YouTube / WhatsApp icons |
| Products ka data | Dr Gas Plus (Rabeprazole 20 mg + Domperidone 30 mg), Dr Gas 2X (Pantoprazole 40 mg + Domperidone 30 mg), Tumlanta (poori composition, 200 ml), MahaJoint (poori herb list) PDFs se update kiye |
| Consumer features | Subscriptions, rewards/points, bundles ko default me band kiya (brief me nahi hain, site D2C jaisi nahi dikhni chahiye). Code hata nahi, ek switch se wapas aa sakte hain |

## 3. Kal se pehle aapko yeh confirm / dena hai (Phase 1 ke liye)

Yeh sab chhoti baatein hain par live se pehle sahi honi chahiye:

1. **Founder ka naam:** brief me "Prakash Harendra Singh" hai, lekin Form 20B / 21B aur GST me "Prabhat Harendra Singh" hai. Site par brief wala naam laga hai. Kaunsa sahi hai? Dono alag likhna legal documents se mismatch dikhayega.
2. **"Volkscure Pvt. Ltd." / "division of"**: nayi brief me yeh kahin nahi hai aur licences "Credit Lifesciences (Proprietor)" ke naam hain. Maine "division of Volkscure" wali line site se hata di. Product packs par Volkscure ka naam hai, wo packs ki photo me dikhega. Kya Volkscure ka zikr rakhna hai?
3. **Founder biography draft** hai: aapko padhkar approve karna hai. Founder message approved copy hai (as it is lagi hai).
4. **Licences site par dikhane ki permission** (Form 20B / 21B / GST number public page par).
5. **9936360600:** toll-free nahi likha hai. Agar toll-free hai to bataiye.
6. **Social links:** Facebook, Instagram, YouTube mil gaye. **X (Twitter), Threads, LinkedIn** ke link nahi mile, wo icons abhi nahi dikhte.
7. **District status:** 20 districts abhi sab "Active" hain. Har district ka sahi status (Active / Open for appointment / Upcoming) admin me set karna hai.
8. **Prices / MRP:** abhi jo price aur MRP site par hain wo **placeholder** hain (jaise Rs 225 / Rs 250). Brief ke hisaab se card par MRP dikhta hai, isliye **asli MRP list** chahiye. Dr Gas Plus / 2X ka price nahi hai (Rx).
9. **Pack sizes:** NPR-HB 300 ml, Dr Gas Liquid 450 ml, MahaJoint 50 ml purani files se hain. PDFs me pack size nahi di. Tumlanta 200 ml PDF se hai. Sahi pack size confirm karein.
10. **HR email:** careers applications abhi sales@ / askus@ par aayengi. HR ka email dein.

## 4. Phase 1 live karne ke liye zaroori (technical)

| # | Cheez | Kaun |
|---|---|---|
| 1 | **Hosting decision** (VPS / cloud) aur access. Abhi tak hosting tay nahi hai, yeh kal live ka sabse bada rukawat hai | Aap |
| 2 | **Domain** creditlifesciences.com ka DNS access (A record) | Aap |
| 3 | SSL (free, server par lagta hai) | Hum, hosting milte hi |
| 4 | Server par deploy, database, nightly backup, uptime monitor | Hum, hosting milte hi (~2 ghante) |
| 5 | **Mailbox password badalna** (chat me share hua tha); naya `.env` me | Aap + hum |
| 6 | Admin ka custom URL, IP allow-list, 2FA on karna | Hum |
| 7 | Ek baar poori site par final check (phone, laptop) | Hum |

Agar hosting aur domain access aaj mil jaye to Phase 1 kal live ho sakta hai. Nahi mile to jis din mile, usi din (kuch ghante ka kaam).

## 5. Phase 2 (online ordering) ke liye baaki

| # | Cheez | Kaun |
|---|---|---|
| 1 | **Razorpay keys** (test pehle, phir live) + webhook secret | Aap |
| 2 | **Shipping charge kaise lagega** (flat / weight / courier rate) aur courier account (Shiprocket / Delhivery). Abhi flat Rs 49 placeholder hai | Aap |
| 3 | 5-7 business days **order confirmation se ya dispatch se** gine jaayenge? | Aap |
| 4 | Damaged goods report karne ki **last date** (kitne din) aur replacement kitne din me | Aap |
| 5 | **Distributor pricing:** MRP wahi hai ya trade price alag? Koi discount? | Aap |
| 6 | Invoice download portal me dena hai ya nahi (code taiyaar hai, chalu rakhna hai?) | Aap |
| 7 | **Compliance check:** brief me self-registration (Gmail + phone) se turant portal access hai. Pharma trade ordering me licence verify kiye bina access dena risk hai (brief khud ye flag karta hai). Salaah: registration ke baad admin approval, ya GST / licence number check. Aap batayein | Aap + legal |
| 8 | **Rx products (Dr Gas Plus, Dr Gas 2X):** public ko prescription medicine online bechna / advertise karna illegal ho sakta hai. Site par yeh online order nahi hote, sirf details + enquiry. Distributors ke liye bhi abhi cart band hai. Agar licensed distributors ko Rx order dene hain to alag verified-login chahiye | Aap + legal |
| 9 | Ek asli test order (test card se) aur refund test | Hum + aap |

Yeh inputs milne ke baad Phase 2 **1 se 2 din** me live ho sakta hai.

## 6. Jo abhi poora nahi hai (seedhi baat)

- **Interactive India map:** abhi districts ka filter wala list/tile view hai, geographic map nahi. Asli map ke liye district boundary data chahiye; baad me add ho sakta hai. Page par yeh saaf likha hai.
- **Hindi:** header, footer, cart, product cards translate hain. Nayi B2B pages (distributor, network, careers, FAQs, about) abhi English me hain. Pura Hindi alag kaam hai, aur Hindi text kisi Hindi-bhashi se review hona chahiye.
- **Legal pages** (Privacy, Terms, Disclaimer, Cookie, Shipping & replacement) **draft** hain. Brief ke hisaab se likhe hain par **lawyer ka approval** chahiye. Staff ko page par "draft" note dikhta hai (public ko nahi).
- **Distributor testimonials:** nahi daale (brief ke hisaab se future).
- **Margins / sales assistance %:** site par nahi hai (brief ke hisaab se).
- **Pen-test aur server par load test:** baaki hai.
- **Health library ke 3 articles draft** hain, publish nahi kiye. Pharma site par inhe review ke baad hi publish karein.

## 7. Kya kal ke liye jaruri nahi

Subscriptions, rewards, bundles, SMS / WhatsApp updates, Google sign-in, mobile-number login: yeh sab bane hain par B2B launch ke liye zaroori nahi, band hain ya account ka intezaar karte hain.

## 8. Mera suggestion

1. Aaj: hosting + domain access aur section 3 ke jawab (khaaskar founder naam, Volkscure, MRP) bhej dein.
2. Kal: Phase 1 live (website + enquiries + WhatsApp order).
3. Razorpay keys + shipping + damaged-goods answers milne par: Phase 2 (online ordering) 1-2 din me.
4. Phir lawyer review ke baad legal pages ka "draft" note hata kar final.
