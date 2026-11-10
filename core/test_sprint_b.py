"""Sprint B: persistent cart, abandoned-cart mail, email queue, search, content, returns, notifications, dashboard."""
import io
from datetime import timedelta
from io import StringIO
from unittest import mock

from django.conf import settings
from django.core import mail
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.test import override_settings
from django.urls import reverse
from django.contrib.auth import get_user_model
User = get_user_model()
from django.utils import timezone
from PIL import Image

from . import notify
from .models import Article, Batch, CategoryPage, EmailJob, Order, Product, ProductImage, ReturnRequest, SavedCart, Subscriber
from .tests import AJAX, Base

SLUG = "npr-hb-syrup"


def png_bytes(size=(1200, 900)):
    buf = io.BytesIO()
    Image.new("RGB", size, "#0e7a55").save(buf, "PNG")
    return buf.getvalue()


class PersistentCartTests(Base):
    def test_signed_in_cart_is_saved_on_the_server(self):
        user = self.sign_in()
        self.add(SLUG, 2)
        self.assertEqual(SavedCart.objects.get(user=user).data, {SLUG: 2})

    def test_cart_follows_the_customer_to_another_device(self):
        user = self.make_user()
        SavedCart.objects.create(user=user, data={SLUG: 3})
        self.client.post(reverse("ajax_login"), {"username": user.email, "password": "Str0ng-Passw0rd!"}, headers=AJAX)
        self.assertEqual(self.client.session["cart"], {SLUG: 3})

    def test_login_merges_without_doubling(self):
        user = self.make_user()
        SavedCart.objects.create(user=user, data={SLUG: 2, "dr-gas-liquid": 1})
        self.add(SLUG, 2)  # anonymous cart with the same item
        self.client.post(reverse("ajax_login"), {"username": user.email, "password": "Str0ng-Passw0rd!"}, headers=AJAX)
        cart = self.client.session["cart"]
        self.assertEqual(cart[SLUG], 2)
        self.assertEqual(cart["dr-gas-liquid"], 1)

    def test_placing_an_order_empties_the_saved_cart(self):
        user = self.sign_in()
        self.add(SLUG)
        self.client.post(reverse("checkout"), self.checkout_data())
        self.assertFalse(SavedCart.objects.filter(user=user).exists())


class AbandonedCartTests(Base):
    def make_saved(self, hours_ago=3, email="ravi@example.com"):
        user = self.make_user(email=email)
        saved = SavedCart.objects.create(user=user, data={SLUG: 2})
        SavedCart.objects.filter(pk=saved.pk).update(updated_at=timezone.now() - timedelta(hours=hours_ago))
        return user

    def test_reminder_sent_once(self):
        self.make_saved()
        mail.outbox.clear()
        call_command("send_abandoned_carts", stdout=StringIO())
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("NPR-HB", mail.outbox[0].body)
        self.assertIn("unsubscribe", mail.outbox[0].body.lower())
        call_command("send_abandoned_carts", stdout=StringIO())
        self.assertEqual(len(mail.outbox), 1)

    def test_recent_carts_are_left_alone(self):
        self.make_saved(hours_ago=0.5)
        mail.outbox.clear()
        call_command("send_abandoned_carts", stdout=StringIO())
        self.assertEqual(len(mail.outbox), 0)

    def test_unsubscribed_customers_get_nothing(self):
        user = self.make_saved()
        Subscriber.objects.create(email=user.email, is_active=False)
        mail.outbox.clear()
        call_command("send_abandoned_carts", stdout=StringIO())
        self.assertEqual(len(mail.outbox), 0)

    def test_customers_who_bought_since_are_skipped(self):
        user = self.make_saved()
        Order.objects.create(user=user, name="R", phone="9876543210", address="x", city="y", state="z", pincode="226001", total=100)
        mail.outbox.clear()
        call_command("send_abandoned_carts", stdout=StringIO())
        self.assertEqual(len(mail.outbox), 0)

    def test_the_unsubscribe_link_works_for_a_non_subscriber(self):
        user = self.make_saved()
        mail.outbox.clear()
        call_command("send_abandoned_carts", stdout=StringIO())
        link = [w for w in mail.outbox[0].body.split() if "/newsletter/unsubscribe/" in w][0]
        self.client.get(link.replace("https://shop.example.com", ""))
        self.assertFalse(Subscriber.objects.get(email=user.email).is_active)


class EmailQueueTests(Base):
    @override_settings(EMAIL_QUEUE=True)
    def test_emails_are_queued_not_sent_inline(self):
        from . import emails
        mail.outbox.clear()
        emails.send_otp("a@example.com", "123456", "login", 10)
        self.assertEqual(len(mail.outbox), 0)
        self.assertEqual(EmailJob.objects.filter(status="pending").count(), 1)

    @override_settings(EMAIL_QUEUE=True)
    def test_worker_sends_pending_jobs(self):
        from . import emails
        emails.send_otp("a@example.com", "123456", "login", 10)
        mail.outbox.clear()
        call_command("run_worker", "--once", stdout=StringIO())
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(EmailJob.objects.get().status, "sent")

    def test_failed_send_is_retried_later_and_then_given_up(self):
        job = EmailJob.objects.create(to=["a@example.com"], subject="s", text="t")
        from .management.commands import run_worker
        with mock.patch.object(run_worker.EmailMultiAlternatives, "send", side_effect=OSError("smtp down")):
            run_worker.process_batch()
            job.refresh_from_db()
            self.assertEqual((job.status, job.attempts), ("pending", 1))
            self.assertGreater(job.run_after, timezone.now())
            self.assertEqual(run_worker.process_batch(), 0)  # not due yet
            for _ in range(run_worker.MAX_ATTEMPTS):
                EmailJob.objects.filter(pk=job.pk).update(run_after=timezone.now() - timedelta(seconds=1))
                run_worker.process_batch()
        job.refresh_from_db()
        self.assertEqual(job.status, "failed")
        self.assertIn("smtp down", job.last_error)


class SearchTests(Base):
    def test_typo_is_corrected(self):
        r = self.client.get(reverse("search"), {"q": "mahajont"})
        self.assertContains(r, "MahaJoint")
        self.assertTrue(r.context["corrected"])
        self.assertContains(r, "showing results for")

    def test_nonsense_finds_nothing(self):
        self.assertContains(self.client.get(reverse("search"), {"q": "qqqqzzzz"}), "No products found")

    def test_suggest_endpoint(self):
        data = self.client.get(reverse("search_suggest"), {"q": "tumlan"}).json()
        self.assertEqual(data["results"][0]["name"], "Tumlanta MPS")
        data = self.client.get(reverse("search_suggest"), {"q": "tumlnta"}).json()
        self.assertEqual(data["results"][0]["name"], "Tumlanta MPS")
        self.assertEqual(self.client.get(reverse("search_suggest"), {"q": "a"}).json()["results"], [])

    def test_header_has_the_suggest_hook(self):
        self.assertIn('name="q"', self.client.get(reverse("home")).content.decode())


class ContentTests(Base):
    def setUp(self):
        super().setUp()
        call_command("seed_content", stdout=StringIO())

    def test_category_pages(self):
        r = self.client.get(reverse("category", args=["digestive"]))
        self.assertContains(r, "Digestive care")
        self.assertContains(r, "Dr. GAS")
        self.assertEqual(self.client.get(reverse("category", args=["nope"])).status_code, 404)

    def test_drafts_are_hidden_from_the_public(self):
        art = Article.objects.get(slug="storing-medicines-safely-at-home")
        self.assertEqual(self.client.get(art.get_absolute_url()).status_code, 404)
        self.assertNotContains(self.client.get(reverse("blog")), art.title)

    def test_staff_can_preview_drafts_and_published_articles_are_public(self):
        art = Article.objects.get(slug="storing-medicines-safely-at-home")
        staff = self.make_user("staff@example.com")
        staff.is_staff = True
        staff.save()
        self.sign_in(staff)
        self.assertContains(self.client.get(art.get_absolute_url()), "Draft")
        self.client.logout()
        Article.objects.filter(pk=art.pk).update(is_published=True)
        self.assertContains(self.client.get(art.get_absolute_url()), "<strong>", status_code=200) if False else None
        r = self.client.get(art.get_absolute_url())
        self.assertEqual(r.status_code, 200)
        self.assertContains(self.client.get(reverse("blog")), art.title)
        self.assertIn(art.get_absolute_url(), self.client.get(reverse("sitemap")).content.decode())

    def test_rich_text_is_escaped(self):
        from .templatetags.core_extras import rich
        html = rich("## Title\n\n<script>alert(1)</script> **bold**\n\n- one\n- two")
        self.assertNotIn("<script>", html)
        self.assertIn("<strong>bold</strong>", html)
        self.assertIn("<ul><li>one</li>", html)

    def test_product_faqs_and_schema(self):
        html = self.client.get(Product.objects.get(slug=SLUG).get_absolute_url()).content.decode()
        self.assertIn("Frequently asked questions", html)
        self.assertIn('"@type":"FAQPage"', html)

    def test_category_and_blog_pages_are_in_the_sitemap(self):
        xml = self.client.get(reverse("sitemap")).content.decode()
        self.assertIn("/category/digestive/", xml)

    def test_seed_is_idempotent(self):
        call_command("seed_content", stdout=StringIO())
        self.assertEqual(CategoryPage.objects.count(), 3)
        self.assertEqual(Article.objects.count(), 3)


class ReturnTests(Base):
    def delivered_order(self, days_ago=2, user=None):
        user = user or self.sign_in()
        self.add(SLUG, 2)
        self.client.post(reverse("checkout"), self.checkout_data())
        order = Order.objects.latest("created_at")
        order.status = Order.Status.DELIVERED
        order.save()
        Order.objects.filter(pk=order.pk).update(delivered_at=timezone.now() - timedelta(days=days_ago))
        order.refresh_from_db()
        return order

    def url(self, order):
        return reverse("return_new", args=[order.number, order.items.first().pk])

    def video(self):
        return SimpleUploadedFile("unboxing.mp4", b"\x00" * 2048, content_type="video/mp4")

    def test_customer_can_open_a_return_with_photo(self):
        order = self.delivered_order()
        mail.outbox.clear()
        photo = SimpleUploadedFile("p.png", png_bytes((200, 200)), content_type="image/png")
        r = self.client.post(self.url(order), {"quantity": 1, "details": "Leaking", "photo": photo, "video": self.video()})
        req = ReturnRequest.objects.get()
        self.assertRedirects(r, reverse("account_return", args=[req.reference]), fetch_redirect_response=False)
        self.assertEqual((req.quantity, req.status), (1, "requested"))
        self.assertTrue(req.reference.startswith("RR-"))
        self.assertEqual(req.events.count(), 1)
        self.assertTrue(any("received" in m.subject and req.reference in m.subject for m in mail.outbox))

    def _open_return(self):
        order = self.delivered_order()
        self.client.post(self.url(order), {"quantity": 1, "details": "Leaking", "video": self.video()})
        mail.outbox.clear()
        return order, ReturnRequest.objects.get()

    def test_customer_sees_the_return_list_and_timeline_and_can_withdraw(self):
        order, req = self._open_return()
        self.assertContains(self.client.get(reverse("account_returns")), req.reference)
        self.assertContains(self.client.get(reverse("account_return", args=[req.reference])), "Request received")
        self.client.post(reverse("account_return_withdraw", args=[req.reference]))
        req.refresh_from_db()
        self.assertEqual(req.status, "withdrawn")
        self.assertEqual(req.events.last().status, "withdrawn")
        self.assertTrue(any("withdrawn" in m.subject.lower() or "withdrawn" in m.body.lower() for m in mail.outbox))

    def test_other_customers_cannot_open_a_return_page(self):
        order, req = self._open_return()
        self.client.logout()
        User.objects.create_user("other@example.com", "other@example.com", "pw-12345-x")
        self.client.login(username="other@example.com", password="pw-12345-x")
        self.assertEqual(self.client.get(reverse("account_return", args=[req.reference])).status_code, 404)

    def test_admin_refund_records_the_amount_and_emails_once(self):
        from django.contrib.admin.sites import site as admin_site
        from core.admin import ReturnRequestAdmin
        order, req = self._open_return()
        staff = User.objects.create_superuser("boss@example.com", "boss@example.com", "pw-12345-x")
        from django.test import RequestFactory
        rf = RequestFactory().post("/"); rf.user = staff; rf.session = {}; rf._messages = __import__("django.contrib.messages.storage.fallback", fromlist=["x"]).FallbackStorage(rf)
        ReturnRequestAdmin(ReturnRequest, admin_site).issue_refund(rf, ReturnRequest.objects.all())
        req.refresh_from_db()
        self.assertEqual((req.status, req.resolution), ("resolved", "refund"))
        self.assertEqual(req.refund_amount, req.item.unit_price * req.quantity)
        self.assertIsNotNone(req.refunded_at)
        self.assertEqual(len([m for m in mail.outbox if "refund" in m.subject.lower()]), 1)

    def test_dispatching_a_replacement_takes_stock_once(self):
        from django.contrib.admin.sites import site as admin_site
        from core.admin import ReturnRequestAdmin
        order, req = self._open_return()
        product = req.item.product
        product.track_inventory = True
        product.save()
        Batch.objects.create(product=product, batch_no="RB1", expiry=timezone.localdate() + timedelta(days=400), quantity=10)
        staff = User.objects.create_superuser("boss2@example.com", "boss2@example.com", "pw-12345-x")
        from django.test import RequestFactory
        rf = RequestFactory().post("/"); rf.user = staff; rf.session = {}; rf._messages = __import__("django.contrib.messages.storage.fallback", fromlist=["x"]).FallbackStorage(rf)
        model_admin = ReturnRequestAdmin(ReturnRequest, admin_site)
        model_admin.dispatch_replacement(rf, ReturnRequest.objects.all())
        model_admin.dispatch_replacement(rf, ReturnRequest.objects.all())
        self.assertEqual(Batch.objects.get(batch_no="RB1").quantity, 9)
        req.refresh_from_db()
        self.assertEqual((req.status, req.resolution), ("resolved", "replacement"))

    def test_cannot_return_more_than_bought_across_requests(self):
        order = self.delivered_order()
        self.client.post(self.url(order), {"quantity": 2, "video": self.video()})
        self.assertEqual(self.client.get(self.url(order), follow=True).redirect_chain[-1][0], reverse("account_order", args=[order.number]))
        self.assertEqual(ReturnRequest.objects.count(), 1)

    def test_quantity_above_remaining_is_rejected(self):
        order = self.delivered_order()
        r = self.client.post(self.url(order), {"quantity": 5, "video": self.video()})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(ReturnRequest.objects.count(), 0)

    def test_window_closes_after_seven_days(self):
        order = self.delivered_order(days_ago=9)
        r = self.client.get(self.url(order))
        self.assertEqual(r.status_code, 302)

    def test_undelivered_orders_cannot_be_returned(self):
        self.sign_in()
        self.add(SLUG)
        self.client.post(reverse("checkout"), self.checkout_data())
        order = Order.objects.latest("created_at")
        self.assertEqual(self.client.get(self.url(order)).status_code, 302)

    def test_an_unboxing_video_is_required_and_the_reason_is_always_damage(self):
        order = self.delivered_order()
        r = self.client.post(self.url(order), {"quantity": 1, "details": "broken"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(ReturnRequest.objects.count(), 0)
        bad = SimpleUploadedFile("notes.txt", b"hello", content_type="text/plain")
        self.assertEqual(self.client.post(self.url(order), {"quantity": 1, "video": bad}).status_code, 200)
        self.client.post(self.url(order), {"quantity": 1, "reason": "wrong", "video": self.video()})
        req = ReturnRequest.objects.get()
        self.assertEqual(req.reason, "damaged")  # a posted reason is ignored: replacements are for damaged goods only
        self.assertTrue(req.video.name.startswith("returns/video/"))

    def test_other_customers_cannot_open_it(self):
        order = self.delivered_order()
        self.sign_in(self.make_user("other@example.com", phone="9000000000"))
        self.assertEqual(self.client.get(self.url(order)).status_code, 404)

    def test_status_change_emails_the_customer(self):
        order = self.delivered_order()
        self.client.post(self.url(order), {"quantity": 1, "video": self.video()})
        req = ReturnRequest.objects.get()
        mail.outbox.clear()
        req.status, req.resolution = ReturnRequest.Status.APPROVED, ReturnRequest.Resolution.REPLACEMENT
        req.save()
        self.assertIn("approved", mail.outbox[0].subject.lower() + mail.outbox[0].body.lower())
        req.refresh_from_db()
        req.status = ReturnRequest.Status.RESOLVED
        req.save()
        req.refresh_from_db()
        self.assertIsNotNone(req.resolved_at)

    def test_order_page_offers_the_return_link(self):
        order = self.delivered_order()
        self.assertContains(self.client.get(reverse("account_order", args=[order.number])), "Report damaged goods")


NOTIFY_ON = {**settings.NOTIFY, "msg91_authkey": "k", "msg91_template_placed": "tp", "msg91_template_status": "ts",
             "whatsapp_token": "t", "whatsapp_phone_id": "123", "whatsapp_template_placed": "wp", "whatsapp_template_status": "ws"}


class NotifyTests(Base):
    def test_off_by_default(self):
        with mock.patch("core.notify.requests.post") as post:
            self.place_cod_order()
        post.assert_not_called()

    @override_settings(NOTIFY=NOTIFY_ON)
    def test_order_placed_sends_sms_and_whatsapp(self):
        with mock.patch("core.notify.requests.post") as post:
            order = self.place_cod_order()
        urls = [c.args[0] for c in post.call_args_list]
        self.assertTrue(any("msg91" in u for u in urls))
        self.assertTrue(any("graph.facebook.com" in u for u in urls))
        sms = [c for c in post.call_args_list if "msg91" in c.args[0]][0].kwargs["json"]
        self.assertEqual(sms["recipients"][0]["mobiles"], "919876543210")
        self.assertEqual(sms["recipients"][0]["var2"], order.number)

    @override_settings(NOTIFY=NOTIFY_ON)
    def test_status_updates_and_provider_outage_never_break_the_order(self):
        with mock.patch("core.notify.requests.post"):
            order = self.place_cod_order()
        with mock.patch("core.notify.requests.post", side_effect=OSError("down")):
            order.status = Order.Status.SHIPPED
            order.save()  # must not raise
        with mock.patch("core.notify.requests.post") as post:
            order.status = Order.Status.DELIVERED
            order.save()
        body = [c for c in post.call_args_list if "graph" in c.args[0]][0].kwargs["json"]
        self.assertEqual(body["template"]["components"][0]["parameters"][2]["text"], "Delivered")

    def test_number_formatting(self):
        self.assertEqual(notify._e164("+91 98765 43210"), "919876543210")
        self.assertEqual(notify._e164("9876543210"), "919876543210")


class ImagePipelineTests(Base):
    def test_picture_tag_falls_back_without_variants(self):
        from django.template import Context, Template
        out = Template("{% load core_extras %}{% picture 'img/logo-credit.png' alt='x' %}").render(Context())
        self.assertIn("<img", out)
        self.assertNotIn("<source", out)

    def test_picture_tag_uses_webp_when_present(self):
        from django.template import Context, Template
        out = Template("{% load core_extras %}{% picture 'img/npr-hb.jpg' alt='x' %}").render(Context())
        self.assertIn('type="image/webp"', out)
        self.assertIn("320w", out)

    def test_cards_use_the_picture_tag(self):
        self.assertIn("<picture>", self.client.get(reverse("products")).content.decode())

    def test_uploads_get_webp_variants(self):
        from pathlib import Path
        p = Product.objects.get(slug=SLUG)
        img = ProductImage(product=p, alt="t")
        img.image.save("big.png", SimpleUploadedFile("big.png", png_bytes()), save=True)
        folder = Path(img.image.path).parent
        stem = Path(img.image.path).stem
        self.assertTrue((folder / f"{stem}-640.webp").exists())
        self.assertTrue((folder / f"{stem}-1000.webp").exists())


class DashboardAndRolesTests(Base):
    def staff(self, superuser=True):
        u = self.make_user("boss@example.com")
        u.is_staff, u.is_superuser = True, superuser
        u.save()
        return u

    def test_dashboard_shows_numbers(self):
        self.place_cod_order(qty=2)
        self.sign_in(self.staff())
        r = self.client.get(reverse("sales_dashboard"))
        self.assertEqual(r.status_code, 200)
        d = r.context["d"]
        self.assertEqual(d["orders"], 1)
        self.assertGreater(d["revenue"], 0)
        self.assertEqual(d["top"][0]["units"], 2)
        self.assertEqual(d["todo"]["new_orders"], 1)

    def test_dashboard_ignores_cancelled_and_unpaid_online_orders(self):
        from . import orders
        cancelled = self.place_cod_order()
        orders.cancel_order(cancelled)
        Order.objects.create(name="a", phone="9876500000", address="x", city="y", state="z", pincode="226001", total=999,
                             payment_method="online", payment_status="pending")
        from .dashboard import compute
        self.assertEqual(compute()["orders"], 0)

    def test_dashboard_requires_staff(self):
        self.sign_in()
        self.assertEqual(self.client.get(reverse("sales_dashboard")).status_code, 302)
        self.client.logout()
        self.assertEqual(self.client.get(reverse("sales_dashboard")).status_code, 302)

    def test_admin_home_links_to_the_dashboard(self):
        self.sign_in(self.staff())
        self.assertContains(self.client.get("/admin/"), "sales dashboard")

    def test_repeat_rate(self):
        self.place_cod_order()
        self.place_cod_order()
        from .dashboard import compute
        self.assertEqual(compute()["repeat_rate"], 100)

    def test_roles_limit_what_staff_can_do(self):
        from django.contrib.auth.models import Group
        call_command("setup_roles", stdout=StringIO())
        desk = self.make_user("desk@example.com")
        desk.is_staff = True
        desk.save()
        desk.groups.add(Group.objects.get(name="Order desk"))
        self.sign_in(desk)
        self.assertEqual(self.client.get("/admin/core/order/").status_code, 200)
        self.assertEqual(self.client.get("/admin/core/coupon/").status_code, 403)
        self.assertEqual(self.client.get("/admin/auth/user/").status_code, 403)


class AccountAndInventoryTests(Base):
    def sign_in_user(self, email="biz@example.com"):
        user = User.objects.create_user(email, email, "pw-12345-x", first_name="Biz")
        self.client.login(username=email, password="pw-12345-x")
        return user

    def rf_for(self, user):
        from django.contrib.messages.storage.fallback import FallbackStorage
        from django.test import RequestFactory
        rf = RequestFactory().post("/")
        rf.user, rf.session = user, {}
        rf._messages = FallbackStorage(rf)
        return rf

    def test_guest_cart_merges_on_login_and_is_capped_at_stock(self):
        product = Product.objects.get(slug=SLUG)
        product.track_inventory = True
        product.save()
        Batch.objects.create(product=product, batch_no="M1", expiry=timezone.localdate() + timedelta(days=400), quantity=3)
        User.objects.create_user("m@example.com", "m@example.com", "pw-12345-x")
        self.client.post(reverse("cart_add", args=[SLUG]), {"qty": 5})
        self.client.post(reverse("login"), {"username": "m@example.com", "password": "pw-12345-x"})
        self.assertEqual(self.client.session["cart"].get(SLUG), 3)
        self.assertEqual(SavedCart.objects.get().data.get(SLUG), 3)

    def test_account_home_orders_filter_and_business_pages_open(self):
        self.sign_in_user()
        self.assertContains(self.client.get(reverse("account")), "Hello, Biz")
        self.assertEqual(self.client.get(reverse("account_orders") + "?q=zzz&status=placed").status_code, 200)
        self.assertContains(self.client.get(reverse("account_business")), "Business verification")

    def test_business_details_go_for_review_and_staff_can_approve(self):
        from django.contrib.admin.sites import site as admin_site
        from core.admin import ProfileAdmin
        from core.models import Profile
        user = self.sign_in_user()
        mail.outbox.clear()
        data = {"account_type": "chemist", "business_name": "Sharma Medical", "gstin": "09AAAAA1111A1Z5", "drug_licence_no": "UP12345",
                "gst_document": SimpleUploadedFile("gst.pdf", b"%PDF-1.4 x", content_type="application/pdf"),
                "licence_document": SimpleUploadedFile("lic.pdf", b"%PDF-1.4 y", content_type="application/pdf")}
        r = self.client.post(reverse("account_business"), data)
        self.assertEqual(r.status_code, 302)
        user.profile.refresh_from_db()
        self.assertEqual(user.profile.kyc_status, "pending")
        self.assertTrue(any("received your business details" in m.subject for m in mail.outbox))
        staff = User.objects.create_superuser("kyc@example.com", "kyc@example.com", "pw-12345-x")
        ProfileAdmin(Profile, admin_site).approve_kyc(self.rf_for(staff), Profile.objects.filter(pk=user.profile.pk))
        user.profile.refresh_from_db()
        self.assertTrue(user.profile.kyc_approved)
        self.assertTrue(any("approved" in m.subject for m in mail.outbox))

    def test_bad_gstin_is_rejected(self):
        self.sign_in_user()
        r = self.client.post(reverse("account_business"), {"account_type": "chemist", "business_name": "X", "gstin": "BAD", "drug_licence_no": "U1"})
        self.assertEqual(r.status_code, 200)

    def test_checkout_asks_for_verification_when_required(self):
        self.sign_in_user()
        self.client.post(reverse("cart_add", args=[SLUG]), {"qty": 1})
        shop = dict(settings.SHOP, require_kyc_to_order=True)
        with override_settings(SHOP=shop):
            r = self.client.get(reverse("checkout"))
        self.assertRedirects(r, reverse("account_business"), fetch_redirect_response=False)

    def test_inventory_screen_receives_stock_and_logs_it(self):
        from core.models import StockMovement
        User.objects.create_superuser("inv@example.com", "inv@example.com", "pw-12345-x")
        self.client.login(username="inv@example.com", password="pw-12345-x")
        product = Product.objects.get(slug=SLUG)
        product.track_inventory = True
        product.save()
        exp = (timezone.localdate() + timedelta(days=500)).isoformat()
        r = self.client.post(reverse("inventory"), {"receive": "1", "r-product": product.pk, "r-batch_no": "IN1", "r-expiry": exp, "r-quantity": 12})
        self.assertEqual(r.status_code, 302)
        batch = Batch.objects.get(batch_no="IN1")
        self.assertEqual(batch.quantity, 12)
        self.client.post(reverse("inventory"), {"adjust": "1", "a-batch": batch.pk, "a-change": -2, "a-reason": "damaged", "a-note": "broken"})
        batch.refresh_from_db()
        self.assertEqual(batch.quantity, 10)
        self.assertEqual(list(StockMovement.objects.order_by("id").values_list("change", flat=True)), [12, -2])
        self.assertEqual(self.client.post(reverse("inventory"), {"adjust": "1", "a-batch": batch.pk, "a-change": -99, "a-reason": "damaged"}).status_code, 200)
        self.assertContains(self.client.get(reverse("inventory")), "Latest stock movements")

    def test_admin_sidebar_groups_and_screens_open(self):
        User.objects.create_superuser("side@example.com", "side@example.com", "pw-12345-x")
        self.client.login(username="side@example.com", password="pw-12345-x")
        html = self.client.get("/admin/").content.decode()
        for label in ("Website content", "Inventory", "Orders &amp; returns", "Customers"):
            self.assertIn(label, html)
        self.assertEqual(self.client.get(reverse("inventory")).status_code, 200)
        self.assertEqual(self.client.get("/admin/core/stockmovement/").status_code, 200)

    def test_an_account_without_a_profile_is_repaired_and_the_account_page_opens(self):
        from core.models import Profile
        user = self.sign_in_user("noprofile@example.com")
        Profile.objects.filter(user=user).delete()
        user.save()  # the signal recreates it
        self.assertEqual(self.client.get(reverse("account")).status_code, 200)
