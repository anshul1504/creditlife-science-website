import hashlib
import hmac
import json
import re
import tempfile
from datetime import timedelta
from types import SimpleNamespace
from unittest import mock

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.staticfiles import finders
from django.core import mail
from django.core.cache import cache
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from . import otp as otp_service
from . import payments
from .models import OTP, Address, Announcement, Coupon, CouponRedemption, Order, Product, Review, Subscriber, Wishlist
from .tokens import make_verify_token

User = get_user_model()
PASSWORD = "Str0ng-Passw0rd!"
AJAX = {"x-requested-with": "XMLHttpRequest"}


@override_settings(MEDIA_ROOT=tempfile.mkdtemp(), SITE_URL="https://shop.example.com")
class Base(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_products", verbosity=0)

    def setUp(self):
        cache.clear()  # login lockout and rate-limit counters live in the cache; keep tests independent

    # ------------------------------------------------------------- helpers
    def make_user(self, email="ravi@example.com", name="Ravi Kumar", phone="9876543210", verified=True, password=PASSWORD):
        user = User.objects.create_user(username=email, email=email, password=password, first_name=name)
        user.profile.phone = phone
        user.profile.email_verified = verified
        user.profile.save()
        return user

    def sign_in(self, user=None):
        user = user or self.make_user()
        self.client.force_login(user, backend="core.auth_backends.EmailBackend")
        return user

    def add(self, slug, qty=1):
        return self.client.post(reverse("cart_add", args=[slug]), {"qty": qty}, headers=AJAX)

    def checkout_data(self, **extra):
        data = {"name": "Ravi Kumar", "phone": "+91 98765 43210", "email": "ravi@example.com", "address": "12 MG Road",
                "city": "Lucknow", "state": "Uttar Pradesh", "pincode": "226001", "payment_method": "cod"}
        data.update(extra)
        return data

    def place_cod_order(self, slug="npr-hb-syrup", qty=1, **extra):
        self.add(slug, qty)
        self.client.post(reverse("checkout"), self.checkout_data(**extra))
        return Order.objects.latest("created_at")


# =================================================================== catalogue
class CatalogueTests(Base):
    def test_public_pages_render(self):
        urls = [reverse(n) for n in ("home", "about", "products", "contact", "track", "policies", "privacy", "disclaimer", "cart", "login", "register", "password_reset",
                                          "distributor", "network", "careers", "faqs", "legal_info")]
        urls += [p.get_absolute_url() for p in Product.objects.all()]
        for url in urls:
            self.assertEqual(self.client.get(url).status_code, 200, url)

    def test_product_gallery_has_multiple_images(self):
        p = Product.objects.get(slug="npr-hb-syrup")
        self.assertGreaterEqual(len(p.gallery), 3)
        html = self.client.get(p.get_absolute_url()).content.decode()
        self.assertEqual(html.count('class="g-thumb '), len(p.gallery))

    def test_search_and_sort(self):
        r = self.client.get(reverse("search"), {"q": "iron"})
        self.assertContains(r, "1 product found")
        self.assertEqual([p.slug for p in r.context["products"]], ["npr-hb-syrup"])
        self.assertContains(self.client.get(reverse("search"), {"q": "zzzz"}), "No products found")

    def test_pincode_api(self):
        self.assertTrue(self.client.get(reverse("pincode_check"), {"pin": "226001"}).json()["ok"])
        self.assertFalse(self.client.get(reverse("pincode_check"), {"pin": "12"}).json()["ok"])

    def test_robots_sitemap_and_error_pages(self):
        robots = self.client.get(reverse("robots"))
        self.assertContains(robots, "Sitemap: https://shop.example.com/sitemap.xml")
        self.assertContains(robots, "Disallow: /checkout/")
        self.assertIn("/shop/npr-hb-syrup/", self.client.get(reverse("sitemap")).content.decode())
        self.assertEqual(self.client.get("/definitely-not-here/").status_code, 404)
        from django.template.loader import render_to_string
        self.assertIn("Something went wrong", render_to_string("500.html"))

    def test_generated_brand_artwork_exists(self):
        for name in ("img/og-default.jpg", "img/favicon.ico", "img/apple-touch-icon.png", "img/icon-192.png"):
            self.assertTrue(finders.find(name), name)
        for product in Product.objects.filter(is_rx=False):
            self.assertTrue(product.hero_image, product.slug)
            self.assertTrue(finders.find(product.hero_image), product.hero_image)

    def test_mega_menu_is_not_right_aligned(self):
        # Regression: Bootstrap's dropdown-menu-end pinned the mega menu to the right edge and pushed it off screen.
        html = self.client.get(reverse("home")).content.decode()
        self.assertIn('class="dropdown-menu mega"', html)
        self.assertNotIn("dropdown-menu-end mega", html)

    def test_home_follows_the_content_brief(self):
        r = self.client.get(reverse("home"))
        html = r.content.decode()
        self.assertIn("Building Trusted Partnerships. Serving Health.", html)
        self.assertEqual(html.count('class="carousel-item'), 6)  # the six rotating themes
        for cta in ("Become a Distributor", "Explore Our Products", "View Distribution Network", "Contact Us"):
            self.assertIn(cta, html)
        self.assertNotIn("5,00,000", html)  # the minimum purchase belongs on the distributor page only
        systems = {p.system for p in r.context["featured"]}
        self.assertEqual(systems, {"allopathic", "ayurvedic"})

    def test_announcements_rotate_in_the_top_bar(self):
        Announcement.objects.create(text="Monsoon health sale is live", link="/shop/?sale=1", order=1)
        Announcement.objects.create(text="Second message", order=2)
        Announcement.objects.create(text="Hidden message", order=3, is_active=False)
        html = self.client.get(reverse("home")).content.decode()
        self.assertIn("Monsoon health sale is live", html)
        self.assertIn("Second message", html)
        self.assertNotIn("Hidden message", html)


class ShopFilterTests(Base):
    def slugs(self, **params):
        r = self.client.get(reverse("products"), params)
        self.assertEqual(r.status_code, 200)
        return [p.slug for p in r.context["products"]], r

    def test_filter_by_category(self):
        self.assertEqual(self.slugs(cat="pain")[0], ["mahajoint-oil"])
        r = self.client.get(reverse("products") + "?cat=pain&cat=nutrition")
        self.assertEqual(sorted(p.slug for p in r.context["products"]), ["mahajoint-oil", "npr-hb-syrup"])

    def test_filter_by_price_range_excludes_rx(self):
        self.assertEqual(self.slugs(min=200, max=230)[0], ["npr-hb-syrup"])
        self.assertEqual(sorted(self.slugs(min=190, max=230)[0]), ["dr-gas-liquid", "npr-hb-syrup"])
        self.assertEqual(self.slugs(min=260)[0], ["mahajoint-oil"])

    def test_filter_availability_and_type(self):
        slugs, _ = self.slugs(avail=1)
        self.assertEqual(len(slugs), 4)
        self.assertEqual(sorted(self.slugs(type="rx")[0]), ["dr-gas-2x", "dr-gas-plus"])
        self.assertEqual(len(self.slugs(type="otc")[0]), 4)
        Product.objects.filter(slug="tumlanta-mps").update(in_stock=False)
        self.assertNotIn("tumlanta-mps", self.slugs(avail=1)[0])

    def test_filter_by_rating(self):
        user = User.objects.create_user("r@example.com", "r@example.com", PASSWORD)
        Review.objects.create(product=Product.objects.get(slug="npr-hb-syrup"), user=user, rating=5)
        self.assertEqual(self.slugs(rating=4)[0], ["npr-hb-syrup"])

    def test_filter_on_sale(self):
        Product.objects.filter(slug="tumlanta-mps").update(sale_price=99)
        slugs, _ = self.slugs(sale=1)
        self.assertEqual(slugs, ["tumlanta-mps"])

    def test_sorting_and_bad_parameters_are_safe(self):
        self.assertEqual(self.slugs(sort="price_asc", avail=1)[0][0], "tumlanta-mps")
        self.assertEqual(self.slugs(sort="price_desc", avail=1)[0][0], "mahajoint-oil")
        slugs, r = self.slugs(sort="drop table", min="abc", max="-5", cat="nonsense", rating="9", type="zzz")
        self.assertEqual(len(slugs), 6)
        self.assertEqual(r.context["chips"], [])

    def test_chips_empty_state_and_pagination(self):
        _, r = self.slugs(cat="digestive", min=100, max=250, avail=1)
        labels = [t for t, _u in r.context["chips"]]
        self.assertIn("Digestive Care", labels)
        self.assertIn("Available online", labels)
        self.assertContains(self.client.get(reverse("products"), {"cat": "pain", "type": "rx"}), "No products match these filters")
        with mock.patch("core.views.PAGE_SIZE", 2):
            r = self.client.get(reverse("products"), {"type": "otc", "page": 2})
        self.assertEqual(len(r.context["products"]), 2)
        self.assertContains(r, "type=otc&amp;page=1")


# ======================================================================= sale
class SaleTests(Base):
    def put_on_sale(self, slug="npr-hb-syrup", price=199, start=None, end=None):
        Product.objects.filter(slug=slug).update(sale_price=price, sale_starts=start, sale_ends=end)
        return Product.objects.get(slug=slug)

    def test_sale_window_decides_the_price(self):
        now = timezone.now()
        self.assertEqual(self.put_on_sale(end=now + timedelta(days=1)).effective_price, 199)
        self.assertEqual(self.put_on_sale(start=now - timedelta(days=3), end=now - timedelta(days=1)).effective_price, 225)  # ended
        self.assertEqual(self.put_on_sale(start=now + timedelta(days=1)).effective_price, 225)  # not started
        self.assertEqual(self.put_on_sale(price=300).effective_price, 225)  # a "sale" above the price is ignored
        self.assertEqual(self.put_on_sale(price=0).effective_price, 225)

    def test_queryset_on_sale(self):
        now = timezone.now()
        self.put_on_sale("npr-hb-syrup", 199, end=now + timedelta(hours=2))
        self.put_on_sale("dr-gas-liquid", 150, end=now - timedelta(hours=2))
        self.assertEqual([p.slug for p in Product.objects.on_sale()], ["npr-hb-syrup"])

    def test_cart_uses_the_sale_price(self):
        self.put_on_sale(end=timezone.now() + timedelta(days=1))
        self.add("npr-hb-syrup", 2)
        cart = self.client.get(reverse("cart")).context["cart"]
        self.assertEqual((cart.subtotal, cart.total), (398, 398 + 49))

    def test_sale_shows_on_the_product_page_cards_and_home(self):
        self.put_on_sale(end=timezone.now() + timedelta(days=2))
        page = self.client.get(Product.objects.get(slug="npr-hb-syrup").get_absolute_url()).content.decode()
        self.assertIn("data-countdown=", page)
        self.assertIn("tag-sale", page)
        self.assertIn("199", page)


# ====================================================================== coupons
class CouponTests(Base):
    def coupon(self, **kw):
        data = dict(code="SAVE10", kind="percent", value=10, min_order=100, max_discount=50, per_user_limit=1)
        data.update(kw)
        return Coupon.objects.create(**data)

    def apply(self, code):
        return self.client.post(reverse("coupon_apply"), {"code": code}, headers=AJAX)

    def test_percent_flat_cap_and_minimum(self):
        percent = self.coupon()
        self.assertEqual(percent.evaluate(450), (45, None))
        self.assertEqual(percent.evaluate(900)[0], 50)  # capped at Rs 50
        self.assertIn("minimum order", percent.evaluate(50)[1])
        flat = self.coupon(code="FLAT60", kind="flat", value=60, min_order=0, max_discount=0)
        self.assertEqual(flat.evaluate(40)[0], 40)  # never more than the cart value

    def test_inactive_expired_future_and_usage_limit(self):
        now = timezone.now()
        self.assertIn("not active", self.coupon(code="A", active=False).evaluate(500)[1])
        self.assertIn("expired", self.coupon(code="B", ends_at=now - timedelta(days=1)).evaluate(500)[1])
        self.assertIn("not valid yet", self.coupon(code="C", starts_at=now + timedelta(days=1)).evaluate(500)[1])
        limited = self.coupon(code="D", usage_limit=1)
        order = self.place_cod_order()
        CouponRedemption.objects.create(coupon=limited, order=order, email="x@example.com", discount=10)
        self.assertIn("usage limit", limited.evaluate(500)[1])

    def test_codes_are_case_insensitive_and_validated_through_the_cart(self):
        self.coupon()
        self.add("npr-hb-syrup", 2)
        self.assertTrue(self.apply("  save10 ").json()["ok"])
        cart = self.client.get(reverse("cart")).context["cart"]
        self.assertEqual((cart.discount, cart.shipping, cart.total), (45, 49, 450 - 45 + 49))
        self.assertFalse(self.apply("NOPE").json()["ok"])
        self.assertEqual(self.client.post(reverse("coupon_remove"), headers=AJAX).json(), {"ok": True})
        self.assertEqual(self.client.get(reverse("cart")).context["cart"].discount, 0)

    def test_coupon_is_dropped_when_the_cart_falls_below_the_minimum(self):
        self.coupon(min_order=400)
        self.add("npr-hb-syrup", 2)
        self.assertTrue(self.apply("SAVE10").json()["ok"])
        self.client.post(reverse("cart_update", args=["npr-hb-syrup"]), {"qty": 1})
        cart = self.client.get(reverse("cart")).context["cart"]
        self.assertEqual(cart.discount, 0)
        self.assertIn("removed", cart.coupon_notice)

    def test_free_shipping_coupon(self):
        self.coupon(code="SHIPFREE", kind="flat", value=0, min_order=0, max_discount=0, free_shipping=True)
        self.add("tumlanta-mps")
        self.assertTrue(self.apply("SHIPFREE").json()["ok"])
        cart = self.client.get(reverse("cart")).context["cart"]
        self.assertEqual((cart.shipping, cart.total), (0, 145))

    def test_public_offers_show_in_the_cart_with_eligibility(self):
        self.coupon(public=True, description="10% off")
        self.coupon(code="BIG", min_order=2000, public=True)
        self.coupon(code="PRIVATE", public=False)
        self.add("npr-hb-syrup")
        offers = self.client.get(reverse("cart")).context["offers"]
        self.assertEqual({o["coupon"].code: o["eligible"] for o in offers}, {"SAVE10": True, "BIG": False})

    def test_order_records_the_discount_and_redemption(self):
        coupon = self.coupon()
        self.add("npr-hb-syrup", 2)
        self.apply("SAVE10")
        self.client.post(reverse("checkout"), self.checkout_data())
        order = Order.objects.get()
        self.assertEqual((order.subtotal, order.discount, order.shipping, order.total, order.coupon_code), (450, 45, 49, 454, "SAVE10"))
        self.assertEqual(CouponRedemption.objects.get().coupon, coupon)
        customer = next(m for m in mail.outbox if m.to == ["ravi@example.com"])
        self.assertIn("SAVE10", customer.alternatives[0][0])
        self.assertIn("Discount", customer.body)

    def test_one_use_per_customer_even_as_guest_and_cancel_releases_it(self):
        self.coupon()
        order = self.place_cod_order(qty=2)  # no coupon yet
        self.client.post(reverse("cart_remove", args=["npr-hb-syrup"]))
        self.add("npr-hb-syrup", 2)
        self.apply("SAVE10")
        self.client.post(reverse("checkout"), self.checkout_data())
        first = Order.objects.exclude(pk=order.pk).get()
        self.assertEqual(first.discount, 45)
        # the same customer (same email/phone) cannot use it again
        self.add("npr-hb-syrup", 2)
        self.assertTrue(self.apply("SAVE10").json()["ok"])  # fine while we do not know who they are...
        r = self.client.post(reverse("checkout"), self.checkout_data(), follow=True)  # ...but checkout knows
        self.assertContains(r, "already used")
        self.assertEqual(Order.objects.count(), 2)
        # cancelling the first order gives the code back
        from . import orders as order_service
        order_service.cancel_order(first)
        self.assertFalse(CouponRedemption.objects.exists())

    def test_first_order_only(self):
        self.coupon(code="FIRST", first_order_only=True)
        user = self.sign_in()
        self.add("npr-hb-syrup", 2)
        self.assertTrue(self.apply("FIRST").json()["ok"])
        self.client.post(reverse("checkout"), self.checkout_data())
        CouponRedemption.objects.all().delete()  # so only the first-order rule can reject the second use
        self.assertIn("first order", Coupon.objects.get(code="FIRST").evaluate(450, user)[1])


# ===================================================================== checkout
class CheckoutTests(Base):
    def test_rx_product_cannot_be_added(self):
        self.assertEqual(self.add("dr-gas-2x").status_code, 400)
        self.assertEqual(self.client.get(reverse("cart")).context["cart"].count, 0)

    def test_guest_checkout_emails_customer_and_team(self):
        self.add("npr-hb-syrup", 2)
        r = self.client.post(reverse("checkout"), self.checkout_data())
        order = Order.objects.get()
        self.assertRedirects(r, reverse("order_success", args=[order.number]))
        self.assertIsNone(order.user)
        self.assertEqual((order.subtotal, order.shipping, order.total, order.payment_status), (450, 49, 499, "cod"))
        self.assertEqual(order.phone, "9876543210")
        self.assertEqual(sorted(tuple(m.to) for m in mail.outbox), [("ravi@example.com",), ("sales@creditlifesciences.com", "askus@creditlifesciences.com")])
        customer = next(m for m in mail.outbox if m.to == ["ravi@example.com"])
        self.assertIn(order.number, customer.subject)

    def test_free_delivery_over_threshold_and_validation(self):
        self.add("npr-hb-syrup", 3)
        self.client.post(reverse("checkout"), self.checkout_data(phone="123", pincode="12"))
        self.assertEqual(Order.objects.count(), 0)
        self.client.post(reverse("checkout"), self.checkout_data())
        self.assertEqual(Order.objects.get().shipping, 0)

    def test_logged_in_order_links_to_account_and_saves_address(self):
        user = self.sign_in()
        order = self.place_cod_order("mahajoint-oil", 2, save_address="on")
        self.assertEqual(order.user, user)
        self.assertTrue(Address.objects.filter(user=user, pincode="226001", is_default=True).exists())
        self.assertContains(self.client.get(reverse("account_orders")), order.number)

    def test_other_users_cannot_see_an_order(self):
        self.sign_in()
        order = self.place_cod_order()
        self.client.post(reverse("logout"))
        self.sign_in(self.make_user("other@example.com", "Other", "9123456780"))
        self.assertEqual(self.client.get(reverse("account_order", args=[order.number])).status_code, 404)

    def test_status_change_emails_customer(self):
        order = self.place_cod_order()
        mail.outbox.clear()
        for status, word in (("confirmed", "confirmed"), ("shipped", "on its way"), ("delivered", "delivered"), ("cancelled", "cancelled")):
            order.status = status
            order.tracking_note = "Courier AWB 12345" if status == "shipped" else ""
            order.save()
            self.assertEqual(len(mail.outbox), 1, status)
            self.assertIn(word, mail.outbox[0].subject.lower())
            mail.outbox.clear()

    def test_cancel_and_reorder_from_account(self):
        self.sign_in()
        order = self.place_cod_order(qty=2)
        mail.outbox.clear()
        self.client.post(reverse("account_order_reorder", args=[order.number]))
        self.assertEqual(self.client.get(reverse("cart")).context["cart"].count, 2)
        self.client.post(reverse("account_order_cancel", args=[order.number]))
        order.refresh_from_db()
        self.assertEqual(order.status, "cancelled")
        self.assertEqual(len(mail.outbox), 1)
        order.status = "shipped"
        order.save()
        self.client.post(reverse("account_order_cancel", args=[order.number]))
        order.refresh_from_db()
        self.assertEqual(order.status, "shipped")

    def test_track_order_needs_matching_phone(self):
        order = self.place_cod_order()
        self.assertContains(self.client.post(reverse("track"), {"number": order.number.lower(), "phone": "98765 43210"}), "Order placed")
        self.assertContains(self.client.post(reverse("track"), {"number": order.number, "phone": "9000000000"}), "could not find")

    def test_wishlist_toggle_and_login_required(self):
        self.assertEqual(self.client.post(reverse("wishlist_toggle", args=["npr-hb-syrup"]), headers=AJAX).status_code, 401)
        self.sign_in()
        url = reverse("wishlist_toggle", args=["npr-hb-syrup"])
        self.assertTrue(self.client.post(url, headers=AJAX).json()["saved"])
        self.assertEqual(Wishlist.objects.count(), 1)
        self.assertFalse(self.client.post(url, headers=AJAX).json()["saved"])

    def test_reviews_need_verified_email_and_show_verified_purchase(self):
        slug = "npr-hb-syrup"
        url = reverse("review_submit", args=[slug])
        user = self.sign_in(self.make_user(verified=False))
        self.client.post(url, {"rating": 5, "title": "Great"})
        self.assertEqual(Review.objects.count(), 0)
        user.profile.email_verified = True
        user.profile.save()
        self.place_cod_order(slug)
        self.client.post(url, {"rating": 4, "title": "Good", "body": "Nice"})
        self.client.post(url, {"rating": 5, "title": "Great", "body": "Even better"})
        self.assertEqual((Review.objects.count(), Review.objects.get().rating), (1, 5))
        page = self.client.get(reverse("product_detail", args=[slug])).content.decode()
        self.assertIn("Verified purchase", page)
        self.client.post(url, {"title": "x"})
        self.assertEqual(Review.objects.get().rating, 5)  # a missing rating changes nothing

    def test_enquiry_acknowledgement_and_honeypot(self):
        data = {"name": "Dr Sen", "topic": "product", "kind": "doctor", "phone": "9876543210", "email": "sen@example.com", "city": "Kolkata", "message": "Need samples", "website": ""}
        self.assertRedirects(self.client.post(reverse("contact"), data), reverse("contact_thanks"))
        self.assertEqual(sorted(tuple(m.to) for m in mail.outbox), [("sales@creditlifesciences.com", "askus@creditlifesciences.com"), ("sen@example.com",)])
        mail.outbox.clear()
        self.assertEqual(self.client.post(reverse("contact"), {**data, "website": "http://spam"}).status_code, 200)
        self.assertEqual(len(mail.outbox), 0)

    def test_newsletter_subscribe_and_unsubscribe(self):
        r = self.client.post(reverse("newsletter_subscribe"), {"email": "Reader@Example.com"}, headers=AJAX)
        self.assertTrue(r.json()["ok"])
        sub = Subscriber.objects.get()
        self.assertEqual(sub.email, "reader@example.com")
        self.assertIn("already", self.client.post(reverse("newsletter_subscribe"), {"email": "reader@example.com"}, headers=AJAX).json()["message"])
        self.assertEqual(len(mail.outbox), 1)
        link = re.search(r"(/newsletter/unsubscribe/[^\s]+)", mail.outbox[0].body).group(1)
        self.assertContains(self.client.get(link), "You are unsubscribed")
        sub.refresh_from_db()
        self.assertFalse(sub.is_active)
        self.assertEqual(self.client.post(reverse("newsletter_subscribe"), {"email": "nope"}, headers=AJAX).status_code, 400)


# ======================================================================== OTP
class OTPTests(Base):
    def request(self, email, purpose, **extra):
        return self.client.post(reverse("otp_request"), {"email": email, "purpose": purpose, **extra}, headers=AJAX)

    def verify(self, email, purpose, code, **extra):
        return self.client.post(reverse("otp_verify"), {"email": email, "purpose": purpose, "code": code, **extra}, headers=AJAX)

    def code(self):
        return re.search(r"\b(\d{6})\b", mail.outbox[-1].subject).group(1)

    def age_codes(self, seconds=120):
        OTP.objects.update(created_at=timezone.now() - timedelta(seconds=seconds))

    def test_identify_tells_new_and_existing_customers_apart(self):
        self.make_user()
        known = self.client.post(reverse("otp_identify"), {"email": "RAVI@example.com"}, headers=AJAX).json()
        self.assertTrue(known["exists"])
        self.assertEqual(known["masked"], "r**i@example.com")
        self.assertTrue(known["has_password"])
        self.assertFalse(self.client.post(reverse("otp_identify"), {"email": "new@example.com"}, headers=AJAX).json()["exists"])
        self.assertEqual(self.client.post(reverse("otp_identify"), {"email": "not-an-email"}, headers=AJAX).status_code, 400)

    def test_login_with_otp(self):
        user = self.make_user(verified=False)
        r = self.request("ravi@example.com", "login")
        self.assertTrue(r.json()["ok"])
        message = mail.outbox[-1]
        self.assertEqual(message.to, ["ravi@example.com"])
        self.assertIn("sign-in code", message.subject)
        self.assertIn(self.code(), message.body)
        self.assertIn(self.code(), message.alternatives[0][0])
        self.assertNotIn("_auth_user_id", self.client.session)
        r = self.verify("ravi@example.com", "login", self.code(), next="/shop/")
        self.assertEqual(r.json(), {"ok": True, "redirect": "/shop/"})
        self.assertEqual(int(self.client.session["_auth_user_id"]), user.pk)
        user.profile.refresh_from_db()
        self.assertTrue(user.profile.email_verified)  # the code proves the address

    def test_login_for_unknown_email_is_refused(self):
        r = self.request("ghost@example.com", "login")
        self.assertEqual((r.status_code, r.json()["code"]), (400, "no_account"))
        self.assertEqual(len(mail.outbox), 0)

    def test_signup_with_otp_creates_a_verified_passwordless_account(self):
        r = self.request("meena@example.com", "signup", name="Meena Iyer", phone="+91 91234 56780")
        self.assertTrue(r.json()["ok"])
        self.assertFalse(User.objects.filter(email="meena@example.com").exists())  # nothing is created before the code is proven
        r = self.verify("meena@example.com", "signup", self.code())
        self.assertTrue(r.json()["welcome"])
        user = User.objects.get(email="meena@example.com")
        self.assertEqual((user.first_name, user.profile.phone, user.profile.email_verified), ("Meena Iyer", "9123456780", True))
        self.assertFalse(user.has_usable_password())
        self.assertEqual(int(self.client.session["_auth_user_id"]), user.pk)
        self.assertTrue(any("Welcome" in m.subject for m in mail.outbox))

    def test_signup_validation_and_existing_email(self):
        bad = self.request("a@example.com", "signup", name="X", phone="12")
        self.assertEqual(bad.status_code, 400)
        self.assertIn("phone", bad.json()["errors"])
        self.assertEqual(len(mail.outbox), 0)
        self.make_user()
        again = self.request("ravi@example.com", "signup", name="Ravi", phone="9876543210")
        self.assertEqual(again.json()["code"], "exists")

    def test_wrong_codes_are_limited_and_the_right_code_stops_working_after_lockout(self):
        self.make_user()
        self.request("ravi@example.com", "login")
        real = self.code()
        wrong = "000000" if real != "000000" else "111111"
        for left in (4, 3, 2, 1):
            r = self.verify("ravi@example.com", "login", wrong)
            self.assertEqual(r.json()["code"], "invalid")
            self.assertIn(f"{left} attempt", r.json()["message"])
        self.assertEqual(self.verify("ravi@example.com", "login", wrong).json()["code"], "locked")
        self.assertEqual(self.verify("ravi@example.com", "login", real).json()["code"], "locked")
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_codes_expire_and_work_only_once(self):
        self.make_user()
        self.request("ravi@example.com", "login")
        code = self.code()
        OTP.objects.update(expires_at=timezone.now() - timedelta(seconds=1))
        self.assertEqual(self.verify("ravi@example.com", "login", code).json()["code"], "expired")
        self.age_codes()
        self.request("ravi@example.com", "login")
        fresh = self.code()
        self.assertTrue(self.verify("ravi@example.com", "login", fresh).json()["ok"])
        self.client.post(reverse("logout"))
        self.assertEqual(self.verify("ravi@example.com", "login", fresh).json()["code"], "expired")  # already used

    def test_a_new_code_cancels_the_old_one(self):
        self.make_user()
        self.request("ravi@example.com", "login")
        old = self.code()
        self.age_codes()
        self.request("ravi@example.com", "login")
        new = self.code()
        if old != new:
            self.assertFalse(self.verify("ravi@example.com", "login", old).json()["ok"])
        self.assertTrue(self.verify("ravi@example.com", "login", new).json().get("ok") or old == new)

    def test_resend_cooldown_and_hourly_limit(self):
        self.make_user()
        self.assertTrue(self.request("ravi@example.com", "login").json()["ok"])
        again = self.request("ravi@example.com", "login")
        self.assertEqual((again.status_code, again.json()["code"]), (429, "cooldown"))
        self.assertGreater(again.json()["retry_after"], 0)
        self.assertEqual(len(mail.outbox), 1)

    @override_settings(OTP={**settings.OTP, "resend_seconds": 0, "max_per_hour": 3})
    def test_hourly_cap(self):
        self.make_user()
        for _ in range(3):
            self.assertTrue(self.request("ravi@example.com", "login").json()["ok"])
        limited = self.request("ravi@example.com", "login")
        self.assertEqual((limited.status_code, limited.json()["code"]), (429, "rate_limited"))

    def test_codes_are_stored_hashed(self):
        self.make_user()
        self.request("ravi@example.com", "login")
        stored = OTP.objects.get()
        self.assertNotEqual(stored.code_hash, self.code())
        self.assertEqual(len(stored.code_hash), 64)
        self.assertNotIn(self.code(), stored.code_hash)
        self.assertEqual(otp_service.mask_email("ab@x.com"), "a*@x.com")

    def test_reset_password_with_otp(self):
        user = self.make_user()
        self.request("ravi@example.com", "reset")
        self.assertIn("password reset code", mail.outbox[-1].subject)
        code = self.code()
        mismatch = self.verify("ravi@example.com", "reset", code, new_password1="An0ther-Str0ng-Pass", new_password2="different")
        self.assertEqual(mismatch.status_code, 400)
        self.assertIn("new_password2", mismatch.json()["errors"])
        weak = self.verify("ravi@example.com", "reset", code, new_password1="123", new_password2="123")
        self.assertEqual(weak.status_code, 400)
        mail.outbox.clear()
        done = self.verify("ravi@example.com", "reset", code, new_password1="An0ther-Str0ng-Pass", new_password2="An0ther-Str0ng-Pass")
        self.assertTrue(done.json()["ok"])  # the typos above did not burn the code
        user.refresh_from_db()
        self.assertTrue(user.check_password("An0ther-Str0ng-Pass"))
        self.assertIn("_auth_user_id", self.client.session)
        # Regression: the session must stay valid on the NEXT request, not only right after the reset.
        self.assertEqual(self.client.get(reverse("account")).status_code, 200)
        self.assertTrue(any("password was changed" in m.subject for m in mail.outbox))

    def test_reset_for_unknown_email_reveals_nothing(self):
        r = self.request("ghost@example.com", "reset")
        self.assertTrue(r.json()["ok"])
        self.assertEqual(len(mail.outbox), 0)
        self.assertEqual(self.verify("ghost@example.com", "reset", "123456", new_password1="An0ther-Str0ng-Pass", new_password2="An0ther-Str0ng-Pass").status_code, 400)

    def test_verify_email_with_otp_and_guest_orders_attach(self):
        guest = self.place_cod_order(email="ravi@example.com")
        self.assertIsNone(guest.user)
        user = self.sign_in(self.make_user(verified=False))
        self.assertTrue(self.request("ravi@example.com", "verify").json()["ok"])
        self.assertTrue(self.verify("ravi@example.com", "verify", self.code()).json()["ok"])
        user.profile.refresh_from_db()
        guest.refresh_from_db()
        self.assertTrue(user.profile.email_verified)
        self.assertEqual(guest.user, user)
        self.assertEqual(self.request("ravi@example.com", "verify").json()["code"], "already_verified")

    def test_verify_purpose_needs_a_signed_in_customer(self):
        self.assertEqual(self.request("ravi@example.com", "verify").status_code, 401)

    def test_guest_orders_attach_when_the_customer_signs_up(self):
        guest = self.place_cod_order(email="newbie@example.com")
        self.client.post(reverse("logout"))
        self.request("newbie@example.com", "signup", name="Newbie", phone="9812345678")
        self.verify("newbie@example.com", "signup", self.code())
        guest.refresh_from_db()
        self.assertEqual(guest.user.email, "newbie@example.com")

    def test_unknown_purpose_and_get_requests_are_rejected(self):
        self.assertEqual(self.request("ravi@example.com", "hack").status_code, 400)
        for name in ("otp_identify", "otp_request", "otp_verify", "ajax_login"):
            self.assertEqual(self.client.get(reverse(name)).status_code, 405)

    def test_otp_email_uses_the_configured_sender_and_reply_to(self):
        self.make_user()
        self.request("ravi@example.com", "login")
        message = mail.outbox[-1]
        self.assertIn("Credit Lifesciences", message.from_email)
        self.assertEqual(message.reply_to, [settings.SITE["email"]])

    def test_purge_command_removes_old_codes(self):
        self.make_user()
        self.request("ravi@example.com", "login")
        OTP.objects.update(created_at=timezone.now() - timedelta(days=2))
        call_command("purge_otps", verbosity=0)
        self.assertEqual(OTP.objects.count(), 0)


# ================================================================ auth screens
class AuthScreenTests(Base):
    def test_password_sign_in_remember_me_and_lockout(self):
        self.make_user()
        bad = self.client.post(reverse("ajax_login"), {"username": "ravi@example.com", "password": "nope"}, headers=AJAX)
        self.assertEqual(bad.status_code, 400)
        ok = self.client.post(reverse("ajax_login"), {"username": "RAVI@example.com", "password": PASSWORD, "remember": "on", "next": "/shop/"}, headers=AJAX)
        self.assertEqual(ok.json(), {"ok": True, "redirect": "/shop/"})
        self.assertGreater(self.client.session.get_expiry_age(), 3600)
        self.client.post(reverse("logout"))
        self.client.post(reverse("ajax_login"), {"username": "ravi@example.com", "password": PASSWORD}, headers=AJAX)
        self.assertTrue(self.client.session.get_expire_at_browser_close())
        self.client.post(reverse("logout"))
        for _ in range(5):
            self.client.post(reverse("ajax_login"), {"username": "ravi@example.com", "password": "wrong"}, headers=AJAX)
        locked = self.client.post(reverse("ajax_login"), {"username": "ravi@example.com", "password": PASSWORD}, headers=AJAX)
        self.assertIn("Too many failed attempts", locked.json()["errors"]["__all__"][0])

    def test_sign_in_never_redirects_off_site(self):
        self.make_user()
        r = self.client.post(reverse("ajax_login"), {"username": "ravi@example.com", "password": PASSWORD, "next": "https://evil.example.com/x"}, headers=AJAX)
        self.assertEqual(r.json()["redirect"], reverse("home"))

    def test_account_pages_require_login(self):
        for name in ("account", "account_orders", "account_addresses", "account_wishlist", "account_profile", "account_verify_pending"):
            r = self.client.get(reverse(name))
            self.assertEqual(r.status_code, 302)
            self.assertIn("/account/login/", r["Location"])

    def test_every_auth_page_is_popup_styled_and_runs_the_flow(self):
        expectations = {"login": "identify", "register": "identify", "password_reset": "reset"}
        for name, start in expectations.items():
            html = self.client.get(reverse(name)).content.decode()
            for marker in ("auth-card2", "am-grid", "data-flow", f'data-start="{start}"', 'data-url-request="/account/otp/request/"'):
                self.assertIn(marker, html, f"{name}: {marker}")
            self.assertNotIn('id="authModal"', html)  # the page card replaces the popup
        self.sign_in(self.make_user(verified=False))
        html = self.client.get(reverse("account_verify_pending")).content.decode()
        for marker in ("data-flow", 'data-start="verify"', 'data-autosend="1"', "ravi@example.com"):
            self.assertIn(marker, html)

    def test_popup_markup_only_for_anonymous_visitors(self):
        html = self.client.get(reverse("home")).content.decode()
        for marker in ('id="authModal"', "data-flow", 'data-step="identify"', 'data-step="otp"', 'data-step="signup"', 'data-step="password"', "data-otp-boxes"):
            self.assertIn(marker, html)
        self.sign_in()
        self.assertNotIn('id="authModal"', self.client.get(reverse("home")).content.decode())

    def test_verify_link_page_and_expired_link(self):
        user = self.make_user(verified=False)
        r = self.client.get(reverse("verify_email", args=[make_verify_token(user)]))
        self.assertContains(r, "Email verified")
        self.assertContains(self.client.get(reverse("verify_email", args=[make_verify_token(user)])), "Already verified")
        self.assertContains(self.client.get(reverse("verify_email", args=["not-a-real-token"])), "invalid or has expired", status_code=400)

    def test_verified_customer_skips_the_pending_page(self):
        self.sign_in()
        self.assertRedirects(self.client.get(reverse("account_verify_pending")), reverse("account"))

    def test_legacy_email_link_reset_still_works(self):
        user = self.make_user()
        mail.outbox.clear()
        self.assertRedirects(self.client.post(reverse("password_reset"), {"email": "ravi@example.com"}), reverse("password_reset_done"))
        self.assertEqual(mail.outbox[0].subject, "Reset your Credit Lifesciences password")
        path = re.search(r"/account/password/reset/[^\s]+", mail.outbox[0].body).group(0)
        r = self.client.get(path, follow=True)
        r = self.client.post(r.redirect_chain[-1][0], {"new_password1": "An0ther-Str0ng-Pass", "new_password2": "An0ther-Str0ng-Pass"})
        self.assertRedirects(r, reverse("password_reset_complete"))
        user.refresh_from_db()
        self.assertTrue(user.check_password("An0ther-Str0ng-Pass"))

    def test_change_password_and_first_password_for_passwordless_accounts(self):
        self.sign_in()
        mail.outbox.clear()
        r = self.client.post(reverse("password_change"), {"old_password": PASSWORD, "new_password1": "Br4nd-New-Passw0rd", "new_password2": "Br4nd-New-Passw0rd"})
        self.assertRedirects(r, reverse("password_change_done"))
        self.assertIn("password was changed", mail.outbox[0].subject)
        passwordless = User.objects.create_user("otp@example.com", "otp@example.com", None, first_name="Otp")
        passwordless.profile.email_verified = True
        passwordless.profile.save()
        self.client.force_login(passwordless, backend="core.auth_backends.EmailBackend")
        self.assertContains(self.client.get(reverse("password_change")), "Set a password")
        mail.outbox.clear()
        r = self.client.post(reverse("password_change"), {"new_password1": "Br4nd-New-Passw0rd", "new_password2": "Br4nd-New-Passw0rd"})
        self.assertRedirects(r, reverse("password_change_done"))
        passwordless.refresh_from_db()
        self.assertTrue(passwordless.has_usable_password())


# ===================================================================== payments
RAZORPAY = {"key_id": "rzp_test_key", "key_secret": "test_secret", "webhook_secret": "whsec_test"}


class FakeRazorpay:
    """Stands in for the Razorpay SDK so tests never touch the network."""

    def __init__(self):
        self.orders, self.refunds, self.fail_refund = [], [], False
        self.order = SimpleNamespace(create=self._create_order)
        self.payment = SimpleNamespace(refund=self._refund)

    def _create_order(self, data):
        self.orders.append(data)
        return {"id": f"order_TEST{len(self.orders)}"}

    def _refund(self, payment_id, data):
        if self.fail_refund:
            raise RuntimeError("gateway down")
        self.refunds.append((payment_id, data))
        return {"id": "rfnd_TEST1"}


@override_settings(RAZORPAY=RAZORPAY, SHOP={**settings.SHOP, "online_payment_enabled": True})
class PaymentTests(Base):
    def setUp(self):
        super().setUp()
        self.gateway = FakeRazorpay()
        patcher = mock.patch("core.payments._client", return_value=self.gateway)
        patcher.start()
        self.addCleanup(patcher.stop)

    def sign(self, rz_order, payment_id):
        return hmac.new(b"test_secret", f"{rz_order}|{payment_id}".encode(), hashlib.sha256).hexdigest()

    def start_online_checkout(self, qty=2, coupon=None):
        self.add("npr-hb-syrup", qty)
        if coupon:
            self.client.post(reverse("coupon_apply"), {"code": coupon})
        r = self.client.post(reverse("checkout"), self.checkout_data(payment_method="online"))
        return Order.objects.latest("created_at"), r

    def pay_ok(self, order, payment_id="pay_TEST1"):
        rz = order.razorpay_order_id
        return self.client.post(reverse("pay_verify", args=[order.number]), {
            "razorpay_order_id": rz, "razorpay_payment_id": payment_id, "razorpay_signature": self.sign(rz, payment_id)}, headers=AJAX)

    def webhook(self, event, order, payment_id="pay_HOOK1", secret="whsec_test"):
        body = json.dumps({"event": event, "payload": {"payment": {"entity": {"id": payment_id, "order_id": order.razorpay_order_id, "error_description": "Card declined"}}}}).encode()
        signature = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
        return self.client.post(reverse("razorpay_webhook"), body, content_type="application/json", headers={"X-Razorpay-Signature": signature})

    def test_online_option_appears_only_when_configured(self):
        self.add("npr-hb-syrup")
        self.assertContains(self.client.get(reverse("checkout")), "Online payment")
        with override_settings(SHOP={**settings.SHOP, "online_payment_enabled": False, "cod_enabled": False}):
            page = self.client.get(reverse("checkout")).content.decode()
            self.assertIn("Online ordering opens shortly", page)
            self.assertIn("disabled", page.split("Place order")[0][-200:])

    def test_checkout_creates_a_pending_order_and_the_gateway_order(self):
        order, r = self.start_online_checkout()
        self.assertRedirects(r, reverse("pay", args=[order.number]))
        self.assertEqual((order.payment_method, order.payment_status, order.total), ("online", "pending", 499))
        self.assertEqual(len(mail.outbox), 0)  # nothing is confirmed until money arrives
        page = self.client.get(reverse("pay", args=[order.number]))
        self.assertContains(page, "order_TEST1")
        self.assertContains(page, "rzp_test_key")
        self.assertEqual(self.gateway.orders[0]["amount"], 49900)  # paise
        self.assertEqual(self.gateway.orders[0]["currency"], "INR")
        self.assertEqual(self.client.get(reverse("cart")).context["cart"].count, 2)  # cart stays until the payment succeeds
        order.refresh_from_db()
        self.assertTrue(order.awaiting_payment)

    def test_gateway_order_is_created_only_once_per_order(self):
        order, _ = self.start_online_checkout()
        self.client.get(reverse("pay", args=[order.number]))
        self.client.get(reverse("pay", args=[order.number]))
        self.assertEqual(len(self.gateway.orders), 1)

    def test_verified_payment_confirms_the_order(self):
        order, _ = self.start_online_checkout()
        self.client.get(reverse("pay", args=[order.number]))
        order.refresh_from_db()
        r = self.pay_ok(order)
        self.assertEqual(r.json(), {"ok": True, "redirect": reverse("order_success", args=[order.number])})
        order.refresh_from_db()
        self.assertEqual((order.payment_status, order.razorpay_payment_id), ("paid", "pay_TEST1"))
        self.assertIsNotNone(order.paid_at)
        customer = next(m for m in mail.outbox if m.to == ["ravi@example.com"])
        self.assertIn("Payment received", customer.alternatives[0][0])
        self.assertTrue(any("PAID online" in m.subject for m in mail.outbox))
        self.assertEqual(self.client.get(reverse("cart")).context["cart"].count, 0)
        self.assertContains(self.client.get(reverse("order_success", args=[order.number])), "Paid online")

    def test_forged_or_mismatched_signature_is_rejected(self):
        order, _ = self.start_online_checkout()
        self.client.get(reverse("pay", args=[order.number]))
        order.refresh_from_db()
        rz = order.razorpay_order_id
        forged = self.client.post(reverse("pay_verify", args=[order.number]), {"razorpay_order_id": rz, "razorpay_payment_id": "pay_X", "razorpay_signature": "0" * 64}, headers=AJAX)
        self.assertEqual(forged.status_code, 400)
        other = self.client.post(reverse("pay_verify", args=[order.number]), {"razorpay_order_id": "order_OTHER", "razorpay_payment_id": "pay_X", "razorpay_signature": self.sign("order_OTHER", "pay_X")}, headers=AJAX)
        self.assertEqual(other.status_code, 400)
        order.refresh_from_db()
        self.assertEqual(order.payment_status, "failed")
        self.assertEqual(len(mail.outbox), 0)
        self.assertTrue(self.pay_ok(order).json()["ok"])  # the customer can still pay properly afterwards

    def test_verifying_twice_does_not_send_duplicate_emails(self):
        order, _ = self.start_online_checkout()
        self.client.get(reverse("pay", args=[order.number]))
        order.refresh_from_db()
        self.pay_ok(order)
        sent = len(mail.outbox)
        self.pay_ok(order)
        self.assertEqual(len(mail.outbox), sent)

    def test_failed_payment_is_recorded_and_can_be_retried(self):
        order, _ = self.start_online_checkout()
        self.client.post(reverse("pay_failed", args=[order.number]), {"reason": "Insufficient funds"}, headers=AJAX)
        order.refresh_from_db()
        self.assertEqual((order.payment_status, order.payment_error), ("failed", "Insufficient funds"))
        self.assertTrue(order.awaiting_payment)
        self.assertEqual(self.client.get(reverse("pay", args=[order.number])).status_code, 200)

    def test_pay_pages_are_private_to_the_customer(self):
        order, _ = self.start_online_checkout()
        self.client.post(reverse("logout"))
        stranger = self.client_class()
        self.assertEqual(stranger.get(reverse("pay", args=[order.number])).status_code, 404)
        self.assertEqual(stranger.post(reverse("pay_verify", args=[order.number]), {}).status_code, 404)

    def test_webhook_confirms_a_payment_the_browser_never_reported(self):
        order, _ = self.start_online_checkout()
        self.client.get(reverse("pay", args=[order.number]))
        order.refresh_from_db()
        self.assertEqual(self.webhook("payment.captured", order).status_code, 200)
        order.refresh_from_db()
        self.assertEqual((order.payment_status, order.razorpay_payment_id), ("paid", "pay_HOOK1"))
        sent = len(mail.outbox)
        self.assertGreaterEqual(sent, 2)
        self.webhook("order.paid", order)  # duplicate delivery
        self.assertEqual(len(mail.outbox), sent)

    def test_webhook_rejects_bad_signatures_and_records_failures(self):
        order, _ = self.start_online_checkout()
        self.client.get(reverse("pay", args=[order.number]))
        order.refresh_from_db()
        self.assertEqual(self.webhook("payment.captured", order, secret="wrong").status_code, 400)
        self.assertEqual(self.client.post(reverse("razorpay_webhook"), b"{}", content_type="application/json").status_code, 400)
        order.refresh_from_db()
        self.assertEqual(order.payment_status, "pending")
        self.webhook("payment.failed", order)
        order.refresh_from_db()
        self.assertEqual((order.payment_status, order.payment_error), ("failed", "Card declined"))
        self.assertEqual(self.webhook("payment.captured", SimpleNamespace(razorpay_order_id="order_UNKNOWN")).status_code, 200)

    def test_coupon_discount_is_what_gets_charged(self):
        Coupon.objects.create(code="SAVE10", kind="percent", value=10, min_order=100, max_discount=50)
        order, _ = self.start_online_checkout(coupon="SAVE10")
        self.client.get(reverse("pay", args=[order.number]))
        self.assertEqual((order.discount, order.total), (45, 454))
        self.assertEqual(self.gateway.orders[0]["amount"], 45400)

    def test_cancelling_a_paid_order_refunds_it(self):
        self.sign_in()
        order, _ = self.start_online_checkout()
        self.client.get(reverse("pay", args=[order.number]))
        order.refresh_from_db()
        self.pay_ok(order)
        mail.outbox.clear()
        r = self.client.post(reverse("account_order_cancel", args=[order.number]), follow=True)
        self.assertContains(r, "refund")
        order.refresh_from_db()
        self.assertEqual((order.status, order.payment_status, order.refund_id), ("cancelled", "refunded", "rfnd_TEST1"))
        self.assertEqual(self.gateway.refunds, [("pay_TEST1", {"amount": 49900, "notes": {"order_number": order.number, "reason": "Order cancelled"}})])
        cancelled = next(m for m in mail.outbox if m.to == ["ravi@example.com"])
        self.assertIn("Refund started", cancelled.alternatives[0][0])

    def test_failed_refund_alerts_the_team_and_still_cancels(self):
        self.sign_in()
        order, _ = self.start_online_checkout()
        self.client.get(reverse("pay", args=[order.number]))
        order.refresh_from_db()
        self.pay_ok(order)
        mail.outbox.clear()
        self.gateway.fail_refund = True
        self.client.post(reverse("account_order_cancel", args=[order.number]))
        order.refresh_from_db()
        self.assertEqual((order.status, order.payment_status), ("cancelled", "paid"))
        self.assertTrue(any("Refund needed" in m.subject for m in mail.outbox))

    def test_cash_on_delivery_cancel_does_not_touch_the_gateway(self):
        self.sign_in()
        order = self.place_cod_order()
        self.client.post(reverse("account_order_cancel", args=[order.number]))
        self.assertEqual(self.gateway.refunds, [])

    def test_unpaid_orders_expire_and_release_their_coupon(self):
        Coupon.objects.create(code="SAVE10", kind="percent", value=10, min_order=100, max_discount=50)
        order, _ = self.start_online_checkout(coupon="SAVE10")
        self.client.post(reverse("coupon_remove"))  # a code can only be used once per customer
        paid, _ = self.start_online_checkout()
        self.assertNotEqual(order.pk, paid.pk)
        self.client.get(reverse("pay", args=[paid.number]))
        paid.refresh_from_db()
        self.pay_ok(paid)
        Order.objects.update(created_at=timezone.now() - timedelta(hours=5))
        call_command("expire_unpaid_orders", verbosity=0)
        order.refresh_from_db()
        paid.refresh_from_db()
        self.assertEqual(order.status, "cancelled")
        self.assertEqual(paid.status, "placed")
        self.assertFalse(CouponRedemption.objects.filter(order=order).exists())

    def test_account_shows_payment_pending_and_a_pay_button(self):
        self.sign_in()
        order, _ = self.start_online_checkout()
        self.assertContains(self.client.get(reverse("account_orders")), "Payment pending")
        detail = self.client.get(reverse("account_order", args=[order.number]))
        self.assertContains(detail, "Complete payment")
        self.assertContains(detail, reverse("pay", args=[order.number]))

    def test_signature_helpers(self):
        self.assertTrue(payments.signature_is_valid("order_1", "pay_1", self.sign("order_1", "pay_1")))
        self.assertFalse(payments.signature_is_valid("order_1", "pay_2", self.sign("order_1", "pay_1")))
        self.assertFalse(payments.signature_is_valid("", "pay_1", "x"))
        self.assertTrue(payments.enabled())
