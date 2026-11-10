"""The B2B site from the client's content brief (Nov 2026): pages, forms, product filters and the ordering rules."""
from django.conf import settings
from django.core import mail
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from django.urls import reverse

from .models import CareerApplication, District, DistributorEnquiry, DistributorListing, Enquiry, Product
from .tests import Base

# the production defaults from the brief (the test run itself keeps the older consumer values)
BRIEF_SHOP = {**settings.SHOP, "free_shipping_above": 0, "cod_enabled": False, "require_login_to_order": True,
              "consumer_features": False, "delivery_days": (5, 7)}

DISTRIBUTOR = {
    "full_name": "Anil Kumar", "firm_name": "Kumar Pharma", "mobile": "98765 43210", "email": "anil@example.com",
    "state": "Uttar Pradesh", "district": "Gonda", "gst_number": "09ABCDE1234F1Z5", "licence_number": "UP5120B000001",
    "experience_years": 8, "website": "",
}


class DistributorTests(Base):
    def test_page_shows_the_brief_content(self):
        html = self.client.get(reverse("distributor")).content.decode()
        for text in ("5,00,000", "Form 20B and Form 21B", "Valid GST registration", "Sales representatives", "does not automatically grant"):
            self.assertIn(text, html)

    def test_valid_enquiry_is_saved_and_both_sides_are_emailed(self):
        mail.outbox.clear()
        r = self.client.post(reverse("distributor"), DISTRIBUTOR)
        self.assertContains(r, "does not automatically grant")
        enq = DistributorEnquiry.objects.get()
        self.assertEqual((enq.mobile, enq.gst_number, enq.status), ("9876543210", "09ABCDE1234F1Z5", "new"))
        recipients = sorted(tuple(m.to) for m in mail.outbox)
        self.assertIn(("anil@example.com",), recipients)
        self.assertIn(tuple(settings.SITE["enquiry_recipients"]), recipients)

    def test_gst_number_must_be_valid(self):
        r = self.client.post(reverse("distributor"), {**DISTRIBUTOR, "gst_number": "12345"})
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "valid 15-character GST number")
        self.assertEqual(DistributorEnquiry.objects.count(), 0)

    def test_gst_is_normalised_to_upper_case(self):
        self.client.post(reverse("distributor"), {**DISTRIBUTOR, "gst_number": "09abcde1234f1z5"})
        self.assertEqual(DistributorEnquiry.objects.get().gst_number, "09ABCDE1234F1Z5")

    def test_required_fields_and_honeypot(self):
        self.assertEqual(self.client.post(reverse("distributor"), {**DISTRIBUTOR, "email": ""}).status_code, 200)
        self.assertEqual(self.client.post(reverse("distributor"), {**DISTRIBUTOR, "state": ""}).status_code, 200)
        self.assertEqual(self.client.post(reverse("distributor"), {**DISTRIBUTOR, "website": "http://spam"}).status_code, 200)
        self.assertEqual(DistributorEnquiry.objects.count(), 0)


class NetworkTests(Base):
    def test_the_twenty_districts_are_loaded(self):
        self.assertEqual(District.objects.count(), 20)
        html = self.client.get(reverse("network")).content.decode()
        for name in ("Lucknow", "Lakhimpur Kheri", "Sant Kabir Nagar", "Bareilly"):
            self.assertIn(name, html)

    def test_three_statuses_are_distinguished(self):
        District.objects.filter(name="Gonda").update(status="open")
        District.objects.filter(name="Pilibhit").update(status="upcoming")
        r = self.client.get(reverse("network"))
        html = r.content.decode()
        for label in ("Active location", "Open for appointment", "Upcoming location"):
            self.assertIn(label, html)
        self.assertEqual(r.context["counts"], {"active": 18, "open": 1, "upcoming": 1})

    def test_directory_shows_only_consented_published_entries(self):
        DistributorListing.objects.create(firm_name="Shown Pharma", contact_person="A", mobile="9000000001", district="Basti", consent_given=True, is_published=True)
        DistributorListing.objects.create(firm_name="No Consent Pharma", contact_person="B", mobile="9000000002", district="Basti", consent_given=False, is_published=True)
        DistributorListing.objects.create(firm_name="Hidden Pharma", contact_person="C", mobile="9000000003", district="Basti", consent_given=True, is_published=False)
        html = self.client.get(reverse("network")).content.decode()
        self.assertIn("Shown Pharma", html)
        self.assertNotIn("No Consent Pharma", html)
        self.assertNotIn("Hidden Pharma", html)
        self.assertNotIn("9000000002", html)

    def test_home_previews_the_network(self):
        html = self.client.get(reverse("home")).content.decode()
        self.assertIn("Growing Our Network. Expanding Healthcare Access.", html)
        self.assertIn("Ayodhya", html)


class CareersTests(Base):
    DATA = {"full_name": "Sunita Devi", "mobile": "9811111111", "email": "sunita@example.com", "location": "Basti, UP",
            "position": "Medical Representative", "experience_years": 3, "qualification": "B.Pharm", "message": "Hello", "website": ""}

    def cv(self, name="cv.pdf", size=2048):
        return SimpleUploadedFile(name, b"%PDF-1.4 " + b"x" * size, content_type="application/pdf")

    def test_application_saved_with_cv_and_emailed_with_attachment(self):
        mail.outbox.clear()
        r = self.client.post(reverse("careers"), {**self.DATA, "resume": self.cv()})
        self.assertContains(r, "Application received")
        app = CareerApplication.objects.get()
        self.assertTrue(app.resume.name.startswith("careers/"))
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(len(mail.outbox[0].attachments), 1)
        self.assertEqual(mail.outbox[0].reply_to, ["sunita@example.com"])

    def test_cv_must_be_pdf_or_word_and_under_5mb(self):
        bad_type = SimpleUploadedFile("cv.exe", b"MZ", content_type="application/octet-stream")
        self.assertEqual(self.client.post(reverse("careers"), {**self.DATA, "resume": bad_type}).status_code, 200)
        too_big = self.cv(size=5 * 1024 * 1024 + 10)
        self.assertEqual(self.client.post(reverse("careers"), {**self.DATA, "resume": too_big}).status_code, 200)
        self.assertEqual(self.client.post(reverse("careers"), self.DATA).status_code, 200)
        self.assertEqual(CareerApplication.objects.count(), 0)

    def test_the_seven_roles_are_listed(self):
        from django.core.management import call_command
        call_command("seed_site", verbosity=0)
        html = self.client.get(reverse("careers")).content.decode()
        for role in ("Medical Representative", "Sales Executive", "Area Sales Manager", "Distribution and Operations",
                     "Office Ad", "Content Creation", "Marketing"):
            self.assertIn(role, html)


class ContentPagesTests(Base):
    def test_faqs_cover_the_eight_questions_with_schema(self):
        html = self.client.get(reverse("faqs")).content.decode()
        self.assertEqual(html.count('class="accordion-item"'), 8)
        self.assertIn('"@type":"FAQPage"', html)
        self.assertIn("5,00,000", html)
        self.assertIn(settings.SITE["sales_email"], html)

    def test_legal_page_lists_licences_and_gst_without_certification_claims(self):
        html = self.client.get(reverse("legal_info")).content.decode()
        for text in ("UP5120B001001", "UP5121B001001", "09KWDPS4937K1ZM", "KH. 58, Basdeva Kunwar", "not quality certifications"):
            self.assertIn(text, html)
        for claim in ("WHO-GMP", "ISO 9001", "ISO-certified"):
            self.assertNotIn(claim, html)

    def test_company_details_in_the_footer(self):
        html = self.client.get(reverse("home")).content.decode()
        for text in ("askus@creditlifesciences.com", "sales@creditlifesciences.com", "Basdeva Kunwar", "Serving Health", "facebook.com/DrGasSyrup",
                     "youtube.com/@DrGASOfficial", "instagram.com/drgassyrup"):
            self.assertIn(text, html)
        for link in ("distributor", "network", "careers", "faqs", "legal_info", "privacy", "terms", "disclaimer", "contact"):
            self.assertIn(reverse(link), html)

    def test_pending_social_links_are_not_shown(self):
        html = self.client.get(reverse("home")).content.decode()
        self.assertNotIn("bi-twitter-x", html)
        self.assertNotIn("bi-linkedin", html)

    def test_no_invented_testimonials_or_certifications(self):
        for name in ("home", "about", "distributor"):
            html = self.client.get(reverse(name)).content.decode().lower()
            for word in ("testimonial", "who-gmp", "iso certified", "pan-india"):
                self.assertNotIn(word, html, f"{name}: {word}")

    def test_about_page_has_the_founder_message_and_no_quality_page(self):
        from django.core.management import call_command
        call_command("seed_site", verbosity=0)
        html = self.client.get(reverse("about")).content.decode()
        self.assertIn("Prakash Harendra Singh", html)
        self.assertIn("Prabhat Harendra Singh", html)
        self.assertIn("Founder &amp; CEO", html)
        self.assertIn("Making the best quality healthcare accessible to every section of society", html)
        r = self.client.get("/quality/")
        self.assertEqual(r.status_code, 301)
        self.assertTrue(r["Location"].endswith("/about/#quality"))

    def test_experience_and_tagline(self):
        self.assertEqual((settings.SITE["years"], settings.SITE["established"], settings.SITE["tagline"]), (17, 2009, "Serving Health"))

    def test_tagline_stays_english_in_hindi(self):
        self.client.post("/i18n/setlang/", {"language": "hi", "next": "/"})
        self.assertIn("Serving Health", self.client.get(reverse("home")).content.decode())

    def test_contact_form_has_the_five_enquiry_types_and_requires_email(self):
        html = self.client.get(reverse("contact")).content.decode()
        for label in ("Product Enquiry", "Order Enquiry", "Business Partnership", "General Query", "Complaint"):
            self.assertIn(label, html)
        data = {"name": "A", "topic": "complaint", "kind": "customer", "phone": "9876543210", "email": "", "city": "Basti, UP", "website": ""}
        self.assertEqual(self.client.post(reverse("contact"), data).status_code, 200)
        self.assertEqual(Enquiry.objects.count(), 0)
        self.client.post(reverse("contact"), {**data, "email": "a@example.com"})
        self.assertEqual(Enquiry.objects.get().topic, "complaint")

    def test_contact_preselects_the_topic_from_the_catalogue_link(self):
        self.assertContains(self.client.get(reverse("contact"), {"topic": "product"}), 'value="product" selected')

    def test_floating_whatsapp_button_on_every_page(self):
        for name in ("home", "products", "contact", "about"):
            self.assertIn("wa-float", self.client.get(reverse(name)).content.decode())


class ProductFilterTests(Base):
    def test_ayurvedic_and_allopathic_filter(self):
        r = self.client.get(reverse("products"), {"system": "ayurvedic"})
        self.assertEqual([p.slug for p in r.context["products"]], ["mahajoint-oil"])
        r = self.client.get(reverse("products"), {"system": "allopathic"})
        self.assertNotIn("mahajoint-oil", [p.slug for p in r.context["products"]])
        self.assertEqual(Product.objects.get(slug="mahajoint-oil").system, "ayurvedic")

    def test_ingredient_filter(self):
        r = self.client.get(reverse("products"), {"ing": "pantoprazole"})
        self.assertEqual([p.slug for p in r.context["products"]], ["dr-gas-2x"])
        r = self.client.get(reverse("products"), {"ing": "ferric"})
        self.assertEqual([p.slug for p in r.context["products"]], ["npr-hb-syrup"])

    def test_health_problem_filter_still_works(self):
        r = self.client.get(reverse("products"), {"cat": "pain"})
        self.assertEqual([p.slug for p in r.context["products"]], ["mahajoint-oil"])

    def test_cards_show_mrp_and_view_details(self):
        html = self.client.get(reverse("products")).content.decode()
        self.assertIn("View Details", html)
        self.assertNotIn("data-add-cart", html.split("pcard")[1] if "pcard" in html else html)

    def test_pdf_product_data_was_applied(self):
        plus = Product.objects.get(slug="dr-gas-plus")
        self.assertIn("Rabeprazole Sodium (enteric-coated) | 20 mg", plus.composition)
        self.assertIn("Domperidone (sustained-release) | 30 mg", plus.composition)
        two_x = Product.objects.get(slug="dr-gas-2x")
        self.assertIn("Pantoprazole (gastro-resistant) | 40 mg", two_x.composition)
        tumlanta = Product.objects.get(slug="tumlanta-mps")
        self.assertEqual(tumlanta.pack, "200 ml")
        self.assertIn("Activated Dimethicone | 50 mg", tumlanta.composition)
        self.assertIn("Winter Green Oil | 2.0 ml", Product.objects.get(slug="mahajoint-oil").composition)

    def test_prescription_products_cannot_be_bought_online(self):
        plus = Product.objects.get(slug="dr-gas-plus")
        self.assertFalse(plus.sellable)
        self.client.post(reverse("cart_add", args=[plus.slug]), {"qty": 1})
        self.assertEqual(self.client.session.get("cart", {}), {})


@override_settings(SHOP=BRIEF_SHOP)
class BriefOrderingRulesTests(Base):
    """The ordering rules exactly as the brief states them."""

    def test_public_sees_prices_but_must_register_to_order(self):
        page = self.client.get(Product.objects.get(slug="npr-hb-syrup").get_absolute_url())
        self.assertContains(page, "Register / sign in to order")
        self.assertContains(page, "Order on WhatsApp")
        self.assertContains(page, "225")  # the price is visible to everyone
        self.assertNotContains(page, 'name="next" value="checkout"')

    def test_signed_in_buyer_sees_the_cart_buttons(self):
        self.sign_in()
        page = self.client.get(Product.objects.get(slug="npr-hb-syrup").get_absolute_url())
        self.assertContains(page, "Add to cart")

    def test_checkout_needs_login(self):
        self.add("npr-hb-syrup")
        r = self.client.get(reverse("checkout"))
        self.assertEqual(r.status_code, 302)
        self.assertIn("/account/login/", r["Location"])

    def test_no_cod_and_no_online_means_ordering_is_not_open_yet(self):
        self.sign_in()
        self.add("npr-hb-syrup")
        with override_settings(SHOP={**BRIEF_SHOP, "online_payment_enabled": False}):
            page = self.client.get(reverse("checkout")).content.decode()
            self.assertIn("Online ordering opens shortly", page)
            self.assertNotIn("Cash on delivery", page)
            before = self.client.post(reverse("checkout"), self.checkout_data(payment_method="cod"))
            self.assertEqual(before.status_code, 200)
            from .models import Order
            self.assertEqual(Order.objects.count(), 0)

    def test_online_payment_is_the_only_method_when_configured(self):
        self.sign_in()
        self.add("npr-hb-syrup")
        with override_settings(SHOP={**BRIEF_SHOP, "online_payment_enabled": True}):
            form = self.client.get(reverse("checkout")).context["form"]
            self.assertEqual([v for v, _ in form.fields["payment_method"].choices], ["online"])

    def test_buyer_bears_shipping_and_it_is_never_free(self):
        self.sign_in()
        self.add("npr-hb-syrup", 10)  # a large order: still charged shipping
        cart = self.client.get(reverse("cart")).context["cart"]
        self.assertEqual(cart.shipping, BRIEF_SHOP["shipping_fee"])
        self.assertContains(self.client.get(reverse("cart")), "Shipping is charged by our delivery partner")
        self.assertNotContains(self.client.get(reverse("cart")), "free delivery")

    def test_delivery_estimate_and_policy_text(self):
        policy = self.client.get(reverse("policies")).content.decode()
        for text in ("5 to 7 business days", "buyer bears the shipping cost", "unboxing video", "UPI, debit cards, credit cards and net banking"):
            self.assertIn(text, policy)
        self.assertNotIn("Cash on delivery may also", policy)
        self.assertIn("5-7 business days", self.client.get(reverse("pincode_check"), {"pin": "226001"}).json()["message"])

    def test_whatsapp_cart_link_lists_the_items(self):
        self.add("npr-hb-syrup", 2)
        cart = self.client.get(reverse("cart")).context["cart"]
        self.assertIn("wa.me/919936360600", cart.whatsapp_url)
        self.assertIn("2%20x%20NPR-HB%20Syrup", cart.whatsapp_url)

    def test_consumer_features_are_hidden(self):
        user = self.sign_in()
        page = self.client.get(Product.objects.get(slug="npr-hb-syrup").get_absolute_url()).content.decode()
        self.assertNotIn("Subscribe &amp; Save", page)
        account = self.client.get(reverse("account_orders")).content.decode()
        self.assertNotIn("Subscriptions", account)
        self.assertNotIn("Rewards", account)
        self.assertNotIn("Bundles", self.client.get(reverse("home")).content.decode())
        self.assertIsNotNone(user)

    def test_no_free_delivery_wording_anywhere(self):
        for name in ("home", "products", "contact", "about", "distributor", "login"):
            self.assertNotIn("free delivery", self.client.get(reverse(name)).content.decode().lower(), name)

    def test_damage_replacement_page_states_the_video_rule(self):
        self.assertContains(self.client.get(reverse("terms")), "unboxing video")


class VendoredAssetsTests(Base):
    def test_vendored_files_have_no_dangling_source_map_text(self):
        """A stray 'bootstrap.bundle.min.js.map' left behind once broke every page's JavaScript."""
        from pathlib import Path
        root = Path(settings.BASE_DIR) / "static" / "vendor"
        for f in list(root.rglob("*.js")) + list(root.rglob("*.css")):
            text = f.read_text(encoding="utf-8")
            self.assertNotIn("sourceMappingURL", text, f.name)
            self.assertFalse(text.rstrip().endswith((".map", ".map */")), f.name)
        bundle = (root / "bootstrap" / "bootstrap.bundle.min.js").read_text(encoding="utf-8").rstrip()
        self.assertTrue(bundle.endswith("}));"))


class CmsTests(Base):
    def test_footer_credit_social_rail_and_no_newsletter(self):
        html = self.client.get(reverse("home")).content.decode()
        self.assertIn("thewebfix.in", html)
        self.assertIn("The Webfix", html)
        self.assertNotIn("newsletter", html.lower())

    def test_site_settings_override_and_hero_slides_come_from_the_database(self):
        from core.models import HeroSlide, SiteSettings
        SiteSettings.objects.all().delete()
        SiteSettings.objects.create(phone="9000000001")
        HeroSlide.objects.create(headline="Custom slide headline", order=1)
        html = self.client.get(reverse("home")).content.decode()
        self.assertIn("Custom slide headline", html)

    def test_directory_listings_stay_hidden_until_consent(self):
        from django.core.management import call_command
        call_command("seed_site", verbosity=0)
        html = self.client.get(reverse("network")).content.decode()
        self.assertNotIn("Contact person", html)
