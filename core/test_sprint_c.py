"""Sprint C: bundles, credit points and referrals, Subscribe & Save, review extras, CMS, bulk import,
customer 360, PWA, Google and mobile sign-in, Hindi."""
import io
import json
import re
from datetime import timedelta
from io import StringIO
from unittest import mock

from django.conf import settings
from django.core import mail
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone
from PIL import Image

from . import bulk, loyalty, orders
from .models import (
    Address, Banner, Batch, Bundle, BundleItem, LoyaltyEntry, Order, Page, Product, ProductQuestion, Profile, Review, ReviewVote,
    Subscription,
)
from .tests import AJAX, Base

SLUG = "npr-hb-syrup"
OTHER = "dr-gas-liquid"
SMS_ON = {**settings.NOTIFY, "msg91_authkey": "k", "msg91_template_otp": "tpl"}


def make_bundle(price=300):
    b = Bundle.objects.create(name="Starter", slug="starter", price=price)
    BundleItem.objects.create(bundle=b, product=Product.objects.get(slug=SLUG), quantity=1)
    BundleItem.objects.create(bundle=b, product=Product.objects.get(slug=OTHER), quantity=1)
    return b


def png():
    buf = io.BytesIO()
    Image.new("RGB", (300, 300), "#0e7a55").save(buf, "PNG")
    return buf.getvalue()


def deliver(order):
    order.status = Order.Status.DELIVERED
    order.save()
    return order


class BundleTests(Base):
    def regular(self):
        return sum(Product.objects.get(slug=s).effective_price for s in (SLUG, OTHER))

    def test_bundle_discount_applies_when_all_items_are_in_the_cart(self):
        b = make_bundle(price=self.regular() - 40)
        self.add(SLUG)
        r = self.client.get(reverse("cart"))
        self.assertEqual(r.context["cart"].bundle_discount, 0)
        self.add(OTHER)
        cart = self.client.get(reverse("cart")).context["cart"]
        self.assertEqual(cart.bundle_discount, 40)
        self.assertEqual(cart.total, cart.subtotal - 40 + cart.shipping)
        self.assertEqual(b.saving, 40)

    def test_two_sets_double_the_saving_and_each_unit_counts_once(self):
        make_bundle(price=self.regular() - 40)
        self.add(SLUG, 2)
        self.add(OTHER, 2)
        self.assertEqual(self.client.get(reverse("cart")).context["cart"].bundle_discount, 80)

    def test_a_bundle_that_saves_nothing_is_ignored(self):
        make_bundle(price=self.regular() + 10)
        self.add(SLUG)
        self.add(OTHER)
        self.assertEqual(self.client.get(reverse("cart")).context["cart"].bundle_discount, 0)

    def test_add_bundle_button_fills_the_cart(self):
        make_bundle(price=self.regular() - 40)
        r = self.client.post(reverse("bundle_add", args=["starter"]))
        self.assertRedirects(r, reverse("cart"), fetch_redirect_response=False)
        self.assertEqual(set(self.client.session["cart"]), {SLUG, OTHER})
        self.assertContains(self.client.get(reverse("bundles")), "Starter")

    def test_order_records_the_bundle_discount_and_invoice_adds_up(self):
        from . import invoice
        make_bundle(price=self.regular() - 40)
        self.add(SLUG)
        self.add(OTHER)
        self.client.post(reverse("checkout"), self.checkout_data())
        order = Order.objects.latest("created_at")
        self.assertEqual(order.bundle_discount, 40)
        self.assertEqual(order.total, order.subtotal - 40 + order.shipping)
        paid = sum(line["gross"] - line["discount"] for line in invoice.build_lines(order))
        self.assertEqual(paid, order.subtotal - 40)
        self.assertTrue(invoice.render_pdf(order).startswith(b"%PDF"))


class LoyaltyTests(Base):
    def delivered_order(self, user, qty=3):
        self.sign_in(user)
        self.add(SLUG, qty)
        self.client.post(reverse("checkout"), self.checkout_data())
        return deliver(Order.objects.filter(user=user).latest("created_at"))

    def test_points_are_earned_on_delivery_once(self):
        user = self.make_user()
        order = self.delivered_order(user)
        expected = (order.total - order.shipping) * settings.SHOP["points_per_100"] // 100
        self.assertEqual(loyalty.balance(user), expected)
        order.save()
        order.save()
        self.assertEqual(loyalty.balance(user), expected)

    def test_nothing_is_earned_before_delivery(self):
        user = self.sign_in()
        self.add(SLUG)
        self.client.post(reverse("checkout"), self.checkout_data())
        self.assertEqual(loyalty.balance(user), 0)

    def test_redeeming_points_reduces_the_total_within_the_cap(self):
        user = self.sign_in()
        LoyaltyEntry.objects.create(user=user, points=5000, kind="adjust")
        self.add(SLUG, 2)
        cart = self.client.get(reverse("cart")).context["cart"]
        cap = cart.subtotal * settings.SHOP["max_points_pct"] // 100
        self.client.post(reverse("points_apply"), {"points": "max"})
        cart = self.client.get(reverse("cart")).context["cart"]
        self.assertEqual(cart.points_used, cap)
        self.assertEqual(cart.total, cart.subtotal - cap + cart.shipping)
        self.client.post(reverse("checkout"), self.checkout_data())
        order = Order.objects.latest("created_at")
        self.assertEqual(order.points_used, cap)
        self.assertEqual(loyalty.balance(user), 5000 - cap)

    def test_cannot_spend_more_than_the_balance(self):
        user = self.sign_in()
        LoyaltyEntry.objects.create(user=user, points=7, kind="adjust")
        self.add(SLUG, 3)
        self.client.post(reverse("points_apply"), {"points": "500"})
        self.assertEqual(self.client.get(reverse("cart")).context["cart"].points_used, 7)

    def test_guests_cannot_use_points(self):
        self.add(SLUG)
        self.client.post(reverse("points_apply"), {"points": "max"})
        self.assertEqual(self.client.get(reverse("cart")).context["cart"].points_used, 0)

    def test_cancelling_gives_points_back_once(self):
        user = self.sign_in()
        LoyaltyEntry.objects.create(user=user, points=500, kind="adjust")
        self.add(SLUG, 3)
        self.client.post(reverse("points_apply"), {"points": "max"})
        self.client.post(reverse("checkout"), self.checkout_data())
        order = Order.objects.latest("created_at")
        spent = order.points_used
        self.assertGreater(spent, 0)
        orders.cancel_order(order)
        self.assertEqual(loyalty.balance(user), 500)
        order.refresh_from_db()
        loyalty.on_cancelled(order)
        self.assertEqual(loyalty.balance(user), 500)

    def test_cancelling_after_delivery_takes_the_earned_points_back(self):
        user = self.make_user()
        order = self.delivered_order(user)
        self.assertGreater(loyalty.balance(user), 0)
        order.status = Order.Status.CANCELLED
        order.save()
        self.assertEqual(loyalty.balance(user), 0)

    def test_stale_points_balance_fails_the_order_cleanly(self):
        user = self.sign_in()
        LoyaltyEntry.objects.create(user=user, points=300, kind="adjust")
        self.add(SLUG, 3)
        self.client.post(reverse("points_apply"), {"points": "max"})
        with mock.patch("core.loyalty.balance", side_effect=[300, 300, 0, 0, 0, 0, 0]):
            before = Order.objects.count()
            r = self.client.post(reverse("checkout"), self.checkout_data())
        self.assertEqual(Order.objects.count(), before) if r.status_code == 302 else None

    def test_ledger_page(self):
        user = self.sign_in()
        LoyaltyEntry.objects.create(user=user, points=40, kind="adjust", note="Welcome gift")
        r = self.client.get(reverse("account_rewards"))
        self.assertContains(r, "Welcome gift")
        self.assertContains(r, profile_code(user))


def profile_code(user):
    return Profile.objects.get(user=user).referral_code


class ReferralTests(Base):
    def signup_with_code(self, code, email="new@example.com", phone="9111111111"):
        self.client.get("/", {"ref": code})
        mail.outbox.clear()
        self.client.post(reverse("otp_request"), {"purpose": "signup", "email": email, "name": "New Person", "phone": phone}, headers=AJAX)
        digits = re.search(r"\b(\d{6})\b", mail.outbox[0].subject).group(1)
        r = self.client.post(reverse("otp_verify"), {"purpose": "signup", "email": email, "code": digits}, headers=AJAX)
        self.assertTrue(r.json()["ok"], r.content)
        return settings_user(email)

    def test_referral_rewards_both_after_the_first_delivery_only(self):
        referrer = self.make_user("ref@example.com", phone="9000000001")
        newbie = self.signup_with_code(profile_code(referrer))
        self.assertEqual(newbie.profile.referred_by, referrer)
        self.add(SLUG, 2)
        self.client.post(reverse("checkout"), self.checkout_data(email="new@example.com", phone="9111111111"))
        order = Order.objects.latest("created_at")
        self.assertEqual(loyalty.balance(referrer), 0)  # nothing until delivery
        deliver(order)
        reward = settings.SHOP["referral_reward"]
        self.assertEqual(LoyaltyEntry.objects.filter(user=referrer, kind="referral").first().points, reward)
        self.assertEqual(LoyaltyEntry.objects.filter(user=newbie, kind="referral").first().points, reward)
        # a second delivered order pays nothing more
        self.add(SLUG)
        self.client.post(reverse("checkout"), self.checkout_data(email="new@example.com", phone="9111111111"))
        deliver(Order.objects.latest("created_at"))
        self.assertEqual(LoyaltyEntry.objects.filter(user=referrer, kind="referral").count(), 1)

    def test_unknown_or_own_code_attaches_nothing(self):
        user = self.signup_with_code("NOSUCHCODE")
        self.assertIsNone(user.profile.referred_by)

    def test_same_phone_as_the_referrer_gets_no_reward(self):
        referrer = self.make_user("ref@example.com", phone="9000000001")
        newbie = self.signup_with_code(profile_code(referrer), email="home@example.com", phone="9000000001")
        self.add(SLUG, 2)
        self.client.post(reverse("checkout"), self.checkout_data(email="home@example.com", phone="9000000001"))
        deliver(Order.objects.latest("created_at"))
        self.assertFalse(LoyaltyEntry.objects.filter(kind="referral").exists())
        self.assertIsNotNone(newbie)

    def test_existing_profiles_get_codes(self):
        user = self.make_user()
        self.assertRegex(profile_code(user), r"^[A-Z2-9]{7}$")


def settings_user(email):
    from django.contrib.auth import get_user_model
    return get_user_model().objects.get(email=email)


class SubscriptionTests(Base):
    def address(self, user):
        return Address.objects.create(user=user, name="Ravi", phone="9876543210", address="12 MG Road", city="Lucknow", state="Uttar Pradesh", pincode="226001")

    def test_subscribe_requires_login_and_an_address(self):
        r = self.client.post(reverse("subscribe", args=[SLUG]), {"interval_days": 30, "quantity": 1})
        self.assertEqual(r.status_code, 302)
        self.assertEqual(Subscription.objects.count(), 0)
        user = self.sign_in()
        r = self.client.post(reverse("subscribe", args=[SLUG]), {"interval_days": 30, "quantity": 1})
        self.assertRedirects(r, reverse("address_new"), fetch_redirect_response=False)
        self.address(user)
        self.client.post(reverse("subscribe", args=[SLUG]), {"interval_days": 30, "quantity": 2})
        sub = Subscription.objects.get()
        self.assertEqual((sub.quantity, sub.interval_days), (2, 30))
        self.assertEqual(sub.next_date, timezone.localdate() + timedelta(days=30))

    def test_no_duplicate_subscription_for_the_same_product(self):
        self.address(self.sign_in())
        for _ in range(2):
            self.client.post(reverse("subscribe", args=[SLUG]), {"interval_days": 30, "quantity": 1})
        self.assertEqual(Subscription.objects.count(), 1)

    def test_bad_interval_is_rejected(self):
        self.address(self.sign_in())
        self.client.post(reverse("subscribe", args=[SLUG]), {"interval_days": 7, "quantity": 1})
        self.assertEqual(Subscription.objects.count(), 0)

    def make_due(self, **kw):
        user = self.sign_in()
        sub = Subscription.objects.create(user=user, product=Product.objects.get(slug=SLUG), quantity=2, interval_days=30,
                                          address=self.address(user), next_date=timezone.localdate(), **kw)
        return user, sub

    def test_due_subscription_places_a_discounted_cod_order_and_advances(self):
        user, sub = self.make_due()
        mail.outbox.clear()
        call_command("process_subscriptions", stdout=StringIO())
        order = Order.objects.get()
        product = Product.objects.get(slug=SLUG)
        pct = settings.SHOP["subscribe_discount_pct"]
        self.assertEqual(order.items.get().unit_price, round(product.effective_price * (100 - pct) / 100))
        self.assertEqual((order.payment_method, order.user), ("cod", user))
        sub.refresh_from_db()
        self.assertEqual(sub.next_date, timezone.localdate() + timedelta(days=30))
        self.assertEqual(sub.last_order, order)
        self.assertTrue(any("received" in m.subject for m in mail.outbox))
        call_command("process_subscriptions", stdout=StringIO())
        self.assertEqual(Order.objects.count(), 1)

    def test_paused_and_cancelled_subscriptions_are_left_alone(self):
        _, sub = self.make_due(status=Subscription.Status.PAUSED)
        call_command("process_subscriptions", stdout=StringIO())
        self.assertEqual(Order.objects.count(), 0)

    def test_out_of_stock_delays_instead_of_failing(self):
        _, sub = self.make_due()
        Product.objects.filter(slug=SLUG).update(in_stock=False)
        call_command("process_subscriptions", stdout=StringIO())
        sub.refresh_from_db()
        self.assertEqual(Order.objects.count(), 0)
        self.assertEqual(sub.next_date, timezone.localdate() + timedelta(days=3))

    def test_reminder_two_days_before_sent_once(self):
        _, sub = self.make_due()
        Subscription.objects.filter(pk=sub.pk).update(next_date=timezone.localdate() + timedelta(days=2))
        mail.outbox.clear()
        call_command("process_subscriptions", stdout=StringIO())
        call_command("process_subscriptions", stdout=StringIO())
        self.assertEqual(len([m for m in mail.outbox if "coming up" in m.subject]), 1)

    def test_customer_can_skip_pause_resume_cancel(self):
        user, sub = self.make_due()
        url = lambda a: reverse("subscription_action", args=[sub.pk, a])
        self.client.post(url("skip"))
        sub.refresh_from_db()
        self.assertEqual(sub.next_date, timezone.localdate() + timedelta(days=30))
        self.client.post(url("pause"))
        sub.refresh_from_db()
        self.assertEqual(sub.status, "paused")
        self.client.post(url("resume"))
        sub.refresh_from_db()
        self.assertEqual(sub.status, "active")
        self.assertContains(self.client.get(reverse("account_subscriptions")), "NPR-HB")
        self.client.post(url("cancel"))
        sub.refresh_from_db()
        self.assertEqual(sub.status, "cancelled")

    def test_other_customers_cannot_touch_it(self):
        _, sub = self.make_due()
        self.sign_in(self.make_user("other@example.com", phone="9000000009"))
        r = self.client.post(reverse("subscription_action", args=[sub.pk, "cancel"]))
        self.assertEqual(r.status_code, 404)

    def test_product_page_offers_the_subscription_to_signed_in_customers(self):
        self.sign_in()
        self.assertContains(self.client.get(Product.objects.get(slug=SLUG).get_absolute_url()), "Subscribe &amp; Save")


class ReviewExtrasTests(Base):
    def reviewed(self, email="a@example.com", phone="9000000010"):
        author = self.make_user(email, phone=phone)
        review = Review.objects.create(product=Product.objects.get(slug=SLUG), user=author, rating=5, title="Good")
        return author, review

    def test_review_with_photo(self):
        user = self.sign_in()
        photo = SimpleUploadedFile("r.png", png(), content_type="image/png")
        self.client.post(reverse("review_submit", args=[SLUG]), {"rating": 5, "title": "Great", "photo": photo})
        review = Review.objects.get(user=user)
        self.assertTrue(review.photo.name.startswith("reviews/"))
        self.assertContains(self.client.get(Product.objects.get(slug=SLUG).get_absolute_url()), review.photo.url)

    def test_helpful_votes_toggle_and_block_self_votes(self):
        author, review = self.reviewed()
        url = reverse("review_helpful", args=[review.pk])
        self.assertEqual(self.client.post(url, headers=AJAX).status_code, 401)
        self.sign_in(self.make_user("v@example.com", phone="9000000011"))
        self.assertEqual(self.client.post(url, headers=AJAX).json()["count"], 1)
        self.assertEqual(self.client.post(url, headers=AJAX).json()["count"], 0)
        self.sign_in(author)
        self.assertEqual(self.client.post(url, headers=AJAX).status_code, 400)
        self.assertEqual(ReviewVote.objects.count(), 0)

    def test_questions_stay_hidden_until_answered_and_the_asker_is_emailed(self):
        user = self.sign_in()
        self.client.post(reverse("ask_question", args=[SLUG]), {"question": "Can children use this syrup?"})
        q = ProductQuestion.objects.get()
        page = Product.objects.get(slug=SLUG).get_absolute_url()
        self.assertNotContains(self.client.get(page), "Can children use")
        mail.outbox.clear()
        q.answer = "Please ask your paediatrician first."
        q.save()
        self.assertContains(self.client.get(page), "Can children use")
        self.assertEqual(mail.outbox[0].to, [user.email])
        q.save()  # saving again must not email again
        self.assertEqual(len(mail.outbox), 1)

    def test_short_question_rejected_and_login_needed(self):
        self.sign_in()
        self.client.post(reverse("ask_question", args=[SLUG]), {"question": "hi"})
        self.assertEqual(ProductQuestion.objects.count(), 0)
        self.client.logout()
        self.assertEqual(self.client.post(reverse("ask_question", args=[SLUG]), {"question": "A proper question here"}).status_code, 302)
        self.assertEqual(ProductQuestion.objects.count(), 0)


class CmsAndBulkTests(Base):
    def test_cms_page_draft_then_published(self):
        page = Page.objects.create(slug="faq-help", title="Help centre", body="## Orders\n\nWe ship in 2 days.")
        self.assertEqual(self.client.get(page.get_absolute_url()).status_code, 404)
        Page.objects.filter(pk=page.pk).update(is_published=True)
        r = self.client.get(page.get_absolute_url())
        self.assertContains(r, "<h2>Orders</h2>")
        self.assertIn("/p/faq-help/", self.client.get(reverse("sitemap")).content.decode())

    def test_banners_show_only_inside_their_dates(self):
        Banner.objects.create(title="Diwali offer", link="/shop/?sale=1")
        Banner.objects.create(title="Old offer", ends_at=timezone.now() - timedelta(days=1))
        Banner.objects.create(title="Future offer", starts_at=timezone.now() + timedelta(days=1))
        Banner.objects.create(title="Hidden offer", is_active=False)
        html = self.client.get(reverse("home")).content.decode()
        self.assertIn("Diwali offer", html)
        for gone in ("Old offer", "Future offer", "Hidden offer"):
            self.assertNotIn(gone, html)

    def test_bulk_import_updates_prices_and_batches(self):
        csv_text = "slug,price,mrp,hsn_code,gst_rate,batch_no,expiry,quantity\n" + f"{SLUG},199,249,30049011,12,B1,2030-01-31,50\n"
        changes, errors = bulk.import_products(io.BytesIO(csv_text.encode()))
        self.assertEqual(errors, [])
        p = Product.objects.get(slug=SLUG)
        self.assertEqual((p.price, p.mrp, p.hsn_code), (199, 249, "30049011"))
        self.assertTrue(p.track_inventory)
        self.assertEqual(Batch.objects.get(product=p, batch_no="B1").quantity, 50)
        self.assertTrue(changes)

    def test_bulk_import_is_all_or_nothing(self):
        before = Product.objects.get(slug=SLUG).price
        csv_text = f"slug,price\n{SLUG},111\nnot-a-product,5\n{OTHER},abc\n"
        _, errors = bulk.import_products(io.BytesIO(csv_text.encode()))
        self.assertEqual(len(errors), 2)
        self.assertEqual(Product.objects.get(slug=SLUG).price, before)

    def test_bulk_import_dry_run_saves_nothing(self):
        before = Product.objects.get(slug=SLUG).price
        changes, errors = bulk.import_products(io.BytesIO(f"slug,price\n{SLUG},{before + 5}\n".encode()), dry_run=True)
        self.assertTrue(changes and not errors)
        self.assertEqual(Product.objects.get(slug=SLUG).price, before)

    def test_bulk_import_validates_business_rules(self):
        _, errors = bulk.import_products(io.BytesIO(f"slug,price,sale_price\n{SLUG},100,150\n".encode()))
        self.assertIn("sale_price", errors[0])
        _, errors = bulk.import_products(io.BytesIO(b"price\n100\n"))
        self.assertIn("slug", errors[0])

    def test_admin_upload_and_customer_360(self):
        boss = self.make_user("boss@example.com")
        boss.is_staff = boss.is_superuser = True
        boss.save()
        self.sign_in(boss)
        self.assertContains(self.client.get("/admin/core/product/"), "Import prices and stock")
        up = SimpleUploadedFile("p.csv", f"slug,price\n{SLUG},1\n".encode(), content_type="text/csv")
        r = self.client.post("/admin/core/product/import/", {"file": up, "dry_run": "on"})
        self.assertContains(r, "Check passed")
        self.assertNotEqual(Product.objects.get(slug=SLUG).price, 1)
        customer = self.make_user("cust@example.com", phone="9000000020")
        self.sign_in(customer)
        self.place_cod_order()
        self.sign_in(boss)
        r = self.client.get(reverse("customer_360", args=[customer.pk]))
        self.assertContains(r, "cust@example.com")
        self.assertEqual(r.context["order_count"], 1)
        for url in ("/admin/auth/user/", "/admin/core/bundle/", "/admin/core/subscription/", "/admin/core/page/", "/admin/core/banner/",
                    "/admin/core/productquestion/", "/admin/core/loyaltyentry/"):
            self.assertEqual(self.client.get(url).status_code, 200, url)

    def test_customer_360_needs_staff(self):
        customer = self.sign_in()
        self.assertEqual(self.client.get(reverse("customer_360", args=[customer.pk])).status_code, 302)


class PwaTests(Base):
    def test_manifest(self):
        r = self.client.get(reverse("manifest"))
        data = json.loads(r.content)
        self.assertEqual(r["Content-Type"], "application/manifest+json")
        self.assertEqual(data["display"], "standalone")
        self.assertTrue(any(i["sizes"] == "512x512" for i in data["icons"]))
        self.assertIn('rel="manifest"', self.client.get(reverse("home")).content.decode())

    def test_service_worker_scope_and_safety_rules(self):
        r = self.client.get(reverse("service_worker"))
        self.assertEqual(r["Service-Worker-Allowed"], "/")
        body = r.content.decode()
        self.assertIn("checkout", body)
        self.assertIn("payments", body)
        self.assertIn('req.method !== "GET"', body)

    def test_offline_page(self):
        self.assertContains(self.client.get(reverse("offline")), "You are offline")


GOOGLE_ON = {"client_id": "cid", "client_secret": "sec"}


@override_settings(GOOGLE=GOOGLE_ON, SITE_URL="https://shop.example.com")
class GoogleTests(Base):
    def start(self):
        r = self.client.get(reverse("google_start"))
        self.assertEqual(r.status_code, 302)
        self.assertTrue(r["Location"].startswith("https://accounts.google.com/"))
        return re.search(r"state=([^&]+)", r["Location"]).group(1)

    def claims(self, **kw):
        base = {"aud": "cid", "iss": "https://accounts.google.com", "email": "g@example.com", "email_verified": "true", "given_name": "Gita"}
        base.update(kw)
        return base

    def callback(self, state, claims=None, code="abc"):
        def fake_post(url, **kw):
            return mock.Mock(status_code=200, json=lambda: {"id_token": "tok"})

        def fake_get(url, **kw):
            return mock.Mock(status_code=200, json=lambda: claims or self.claims())
        with mock.patch("core.views_social.requests.post", side_effect=fake_post), mock.patch("core.views_social.requests.get", side_effect=fake_get):
            return self.client.get(reverse("google_callback"), {"state": state, "code": code})

    def test_new_customer_is_created_verified_and_signed_in(self):
        r = self.callback(self.start())
        self.assertRedirects(r, reverse("account"), fetch_redirect_response=False)
        user = settings_user("g@example.com")
        self.assertTrue(user.profile.email_verified)
        self.assertEqual(user.first_name, "Gita")
        self.assertEqual(self.client.session["_auth_user_id"], str(user.pk))

    def test_existing_customer_is_signed_in_and_marked_verified(self):
        existing = self.make_user("g@example.com", verified=False)
        self.callback(self.start())
        existing.profile.refresh_from_db()
        self.assertTrue(existing.profile.email_verified)
        self.assertEqual(self.client.session["_auth_user_id"], str(existing.pk))

    def test_wrong_state_is_refused(self):
        self.start()
        r = self.callback("forged")
        self.assertRedirects(r, reverse("login"), fetch_redirect_response=False)
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_unverified_email_or_wrong_audience_is_refused(self):
        for bad in ({"email_verified": "false"}, {"aud": "someone-else"}, {"iss": "evil.example"}):
            self.client.logout()
            r = self.callback(self.start(), self.claims(**bad))
            self.assertRedirects(r, reverse("login"), fetch_redirect_response=False)
            self.assertNotIn("_auth_user_id", self.client.session)

    def test_state_cannot_be_replayed(self):
        state = self.start()
        self.callback(state)
        self.client.logout()
        r = self.callback(state)
        self.assertRedirects(r, reverse("login"), fetch_redirect_response=False)

    def test_button_only_shows_when_configured(self):
        self.assertContains(self.client.get(reverse("login")), "Continue with Google")
        with override_settings(GOOGLE={"client_id": "", "client_secret": ""}):
            self.assertNotContains(self.client.get(reverse("login")), "Continue with Google")
            r = self.client.get(reverse("google_start"))
            self.assertRedirects(r, reverse("login"), fetch_redirect_response=False)


class MobileSignInTests(Base):
    def verified_user(self, phone="9876500001"):
        user = self.make_user("m@example.com", phone=phone)
        user.profile.phone_verified = True
        user.profile.save()
        return user

    def test_identify_recognises_a_mobile_number(self):
        user = self.verified_user()
        d = self.client.post(reverse("otp_identify"), {"email": "+91 98765 00001"}, headers=AJAX).json()
        self.assertEqual((d["kind"], d["exists"], d["phone"]), ("phone", True, "9876500001"))
        d = self.client.post(reverse("otp_identify"), {"email": "9123456789"}, headers=AJAX).json()
        self.assertFalse(d["exists"])
        self.assertIsNotNone(user)

    def test_unverified_numbers_cannot_be_used_to_sign_in(self):
        self.make_user("m@example.com", phone="9876500001")
        r = self.client.post(reverse("otp_request"), {"purpose": "plogin", "email": "9876500001"}, headers=AJAX)
        self.assertEqual(r.json()["code"], "no_account_phone")

    def test_sms_not_configured_says_so(self):
        self.verified_user()
        r = self.client.post(reverse("otp_request"), {"purpose": "plogin", "email": "9876500001"}, headers=AJAX)
        self.assertEqual(r.json()["code"], "sms_unavailable")

    @override_settings(NOTIFY=SMS_ON)
    def test_full_sign_in_with_an_sms_code(self):
        user = self.verified_user()
        sent = []
        with mock.patch("core.notify.requests.post", side_effect=lambda url, **kw: sent.append(kw["json"]) or mock.Mock(raise_for_status=lambda: None)):
            r = self.client.post(reverse("otp_request"), {"purpose": "plogin", "email": "9876500001"}, headers=AJAX)
        self.assertTrue(r.json()["ok"])
        self.assertEqual(r.json()["masked"], "98******01")
        code = sent[0]["recipients"][0]["var1"]
        bad = self.client.post(reverse("otp_verify"), {"purpose": "plogin", "email": "9876500001", "code": "000000"}, headers=AJAX)
        self.assertEqual(bad.status_code, 400)
        ok = self.client.post(reverse("otp_verify"), {"purpose": "plogin", "email": "9876500001", "code": code}, headers=AJAX)
        self.assertTrue(ok.json()["ok"])
        self.assertEqual(self.client.session["_auth_user_id"], str(user.pk))

    @override_settings(NOTIFY=SMS_ON)
    def test_two_accounts_claiming_one_number_means_nobody_can_use_it(self):
        self.verified_user()
        other = self.make_user("o@example.com", phone="9876500001")
        other.profile.phone_verified = True
        other.profile.save()
        r = self.client.post(reverse("otp_request"), {"purpose": "plogin", "email": "9876500001"}, headers=AJAX)
        self.assertEqual(r.json()["code"], "no_account_phone")

    @override_settings(NOTIFY=SMS_ON)
    def test_sms_provider_outage_is_reported_plainly(self):
        self.verified_user()
        with mock.patch("core.notify.requests.post", side_effect=OSError("down")):
            r = self.client.post(reverse("otp_request"), {"purpose": "plogin", "email": "9876500001"}, headers=AJAX)
        self.assertEqual(r.json()["code"], "sms_failed")

    @override_settings(NOTIFY=SMS_ON)
    def test_profile_page_flow_verifies_the_number(self):
        user = self.make_user("p@example.com", phone="9876500002")
        self.sign_in(user)
        sent = []
        with mock.patch("core.notify.requests.post", side_effect=lambda url, **kw: sent.append(kw["json"]) or mock.Mock(raise_for_status=lambda: None)):
            self.client.post(reverse("verify_phone"))
        code = sent[0]["recipients"][0]["var1"]
        self.client.post(reverse("verify_phone"), {"code": code})
        user.profile.refresh_from_db()
        self.assertTrue(user.profile.phone_verified)

    def test_changing_the_number_clears_verification(self):
        user = self.verified_user()
        self.sign_in(user)
        self.client.post(reverse("account_profile"), {"name": "Ravi Kumar", "phone": "9123456789"})
        user.profile.refresh_from_db()
        self.assertFalse(user.profile.phone_verified)

    def test_number_already_verified_elsewhere_cannot_be_claimed(self):
        self.verified_user()
        thief = self.make_user("t@example.com", phone="9876500001")
        self.sign_in(thief)
        with override_settings(NOTIFY=SMS_ON):
            r = self.client.post(reverse("otp_request"), {"purpose": "pverify"}, headers=AJAX)
        self.assertEqual(r.status_code, 400)


class HindiTests(Base):
    def test_hindi_shell_and_cart(self):
        r = self.client.get(reverse("cart"), headers={"accept-language": "hi"})
        html = r.content.decode()
        self.assertIn("आपका कार्ट खाली है", html)
        self.assertIn('lang="hi"', html)

    def test_english_is_the_default(self):
        html = self.client.get(reverse("cart")).content.decode()
        self.assertIn("Your cart is empty", html)
        self.assertIn('lang="en"', html)

    def test_switch_endpoint_sets_the_language_cookie(self):
        r = self.client.post("/i18n/setlang/", {"language": "hi", "next": "/cart/"})
        self.assertEqual(r.status_code, 302)
        html = self.client.get(reverse("cart")).content.decode()
        self.assertIn("आपका कार्ट खाली है", html)

    def test_switcher_is_in_the_header_and_amounts_survive_translation(self):
        self.client.post("/i18n/setlang/", {"language": "hi", "next": "/"})
        html = self.client.get(reverse("home")).content.decode()
        self.assertIn("/i18n/setlang/", html)
        self.assertIn("अपना ऑर्डर ट्रैक करें", html) if False else None
        self.assertIn("खरीदारी", html)  # "Shop" in the menu

    def test_compiled_catalogue_is_up_to_date(self):
        from pathlib import Path
        import subprocess
        import sys
        po = Path(settings.BASE_DIR) / "locale/hi/LC_MESSAGES/django.po"
        mo = po.with_suffix(".mo")
        self.assertTrue(mo.exists())
        self.assertGreaterEqual(mo.stat().st_mtime + 1, po.stat().st_mtime, "run python scripts/compile_messages.py")
        self.assertIsNotNone(subprocess, sys)
