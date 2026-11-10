"""Sprint A: inventory, invoice, courier, legal pages, admin hardening, ops commands."""
import json
import tempfile
from datetime import timedelta
from io import StringIO
from pathlib import Path
from unittest import mock

from django.conf import settings
from django.core import mail
from django.core.management import call_command
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone

from . import orders, shipping
from .models import Batch, Order, OrderAllocation, Product, TrackingEvent
from .tests import Base

SLUG = "npr-hb-syrup"
SHIPROCKET = {**settings.COURIER, "provider": "shiprocket", "email": "a@b.c", "password": "x"}


def stock(slug=SLUG, **batches):
    """stock(name=(qty, days_to_expiry), ...) -> the product, with tracked batches."""
    product = Product.objects.get(slug=slug)
    product.track_inventory = True
    product.save()
    for no, (qty, days) in batches.items():
        Batch.objects.create(product=product, batch_no=no, quantity=qty, expiry=timezone.localdate() + timedelta(days=days))
    product.refresh_from_db()
    return product


class InventoryTests(Base):
    def test_untracked_products_behave_as_before(self):
        self.assertIsNone(Product.objects.get(slug=SLUG).available_qty)
        self.assertEqual(self.place_cod_order().items.count(), 1)

    def test_available_ignores_expired_and_near_expiry_batches(self):
        p = stock(old=(50, -5), soon=(40, 10), good=(7, 400))
        self.assertEqual(p.available_qty, 7)

    def test_order_takes_stock_from_earliest_expiry_first(self):
        stock(late=(10, 400), early=(3, 100))
        order = self.place_cod_order(qty=5)
        self.assertEqual(Batch.objects.get(batch_no="early").quantity, 0)
        self.assertEqual(Batch.objects.get(batch_no="late").quantity, 8)
        self.assertEqual(OrderAllocation.objects.filter(item__order=order).count(), 2)

    def test_selling_the_last_unit_marks_product_out_of_stock(self):
        stock(only=(2, 300))
        self.place_cod_order(qty=2)
        self.assertFalse(Product.objects.get(slug=SLUG).in_stock)

    def test_cart_quantity_is_capped_at_stock(self):
        stock(few=(3, 300))
        self.add(SLUG, 9)
        self.assertEqual(self.client.session["cart"][SLUG], 3)

    def test_cart_adjusts_to_what_is_left_at_checkout(self):
        stock(few=(5, 300))
        self.add(SLUG, 4)
        Batch.objects.filter(batch_no="few").update(quantity=1)  # someone else bought most of it meanwhile
        order = None
        self.client.post(reverse("checkout"), self.checkout_data())
        self.assertEqual(Order.objects.latest("created_at").items.get().quantity, 1)
        self.assertIsNone(order)

    def test_oversell_inside_the_transaction_rolls_the_order_back(self):
        from .models import OrderItem
        stock(few=(5, 300))
        self.add(SLUG, 4)
        before = Order.objects.count()
        real = orders.allocate_stock

        def lose_the_race(item):
            Batch.objects.filter(batch_no="few").update(quantity=1)
            return real(item)
        with mock.patch("core.orders.allocate_stock", side_effect=lose_the_race):
            r = self.client.post(reverse("checkout"), self.checkout_data())
        self.assertRedirects(r, reverse("cart"), fetch_redirect_response=False)
        self.assertEqual(Order.objects.count(), before)
        self.assertFalse(OrderItem.objects.filter(order__isnull=True).exists())
        self.assertEqual(Batch.objects.get(batch_no="few").quantity, 5)  # the whole transaction, stock change included, rolled back

    def test_cancelling_returns_stock_once(self):
        stock(b1=(10, 300))
        order = self.place_cod_order(qty=4)
        self.assertEqual(Batch.objects.get(batch_no="b1").quantity, 6)
        orders.cancel_order(order)
        self.assertEqual(Batch.objects.get(batch_no="b1").quantity, 10)
        order.refresh_from_db()
        orders.release_stock(order)  # a second call must not restore twice
        self.assertEqual(Batch.objects.get(batch_no="b1").quantity, 10)
        self.assertTrue(Product.objects.get(slug=SLUG).in_stock)

    def test_admin_status_change_to_cancelled_restores_stock(self):
        stock(b1=(10, 300))
        order = self.place_cod_order(qty=2)
        order.status = Order.Status.CANCELLED
        order.save()
        self.assertEqual(Batch.objects.get(batch_no="b1").quantity, 10)

    def test_alert_command_reports_low_stock_and_expiry(self):
        stock(b1=(3, 40))
        out = StringIO()
        call_command("stock_alerts", "--dry-run", stdout=out)
        self.assertIn("LOW STOCK", out.getvalue())
        self.assertIn("EXPIRY", out.getvalue())
        mail.outbox.clear()
        call_command("stock_alerts", stdout=StringIO())
        self.assertEqual(len(mail.outbox), 1)


class InvoiceTests(Base):
    def test_invoice_number_is_sequential_and_stable(self):
        from . import invoice
        o1, o2 = self.place_cod_order(), self.place_cod_order()
        n1, n2 = invoice.ensure_invoice_no(o1), invoice.ensure_invoice_no(o2)
        self.assertRegex(n1, r"^CL/\d\d-\d\d/00001$")
        self.assertTrue(n2.endswith("00002"))
        self.assertEqual(invoice.ensure_invoice_no(o1), n1)

    def test_tax_split_adds_up(self):
        from . import invoice
        order = self.place_cod_order(qty=3)
        for line in invoice.build_lines(order):
            self.assertEqual(line["taxable"] + line["tax"], line["gross"] - line["discount"])

    def test_cgst_sgst_when_same_state_else_igst(self):
        from . import invoice
        order = self.place_cod_order()
        with override_settings(SELLER={**settings.SELLER, "state": "Uttar Pradesh"}):
            self.assertTrue(invoice.intra_state(order))
        with override_settings(SELLER={**settings.SELLER, "state": "Delhi"}):
            self.assertFalse(invoice.intra_state(order))

    def test_pdf_renders_in_both_tax_modes(self):
        from . import invoice
        order = self.place_cod_order()
        for state in ("Uttar Pradesh", "Delhi", ""):
            with override_settings(SELLER={**settings.SELLER, "state": state}):
                self.assertTrue(invoice.render_pdf(order).startswith(b"%PDF"))

    def test_owner_gets_pdf_stranger_does_not(self):
        user = self.sign_in()
        self.add(SLUG)
        self.client.post(reverse("checkout"), self.checkout_data())
        order = Order.objects.latest("created_at")
        self.assertEqual(order.user_id, user.pk)
        r = self.client.get(reverse("invoice", args=[order.number]))
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r["Content-Type"], "application/pdf")
        self.assertTrue(r.content.startswith(b"%PDF"))
        self.client.logout()
        self.assertEqual(self.client.get(reverse("invoice", args=[order.number])).status_code, 404)

    def test_signed_link_works_for_guests_and_bad_token_does_not(self):
        from .views_ops import invoice_url
        order = self.place_cod_order()
        self.assertEqual(self.client.get(invoice_url(order)).status_code, 200)
        self.assertEqual(self.client.get(reverse("invoice", args=[order.number]) + "?t=bad").status_code, 404)

    def test_no_invoice_for_cancelled_order(self):
        from .views_ops import invoice_url
        order = self.place_cod_order()
        url = invoice_url(order)
        orders.cancel_order(order)
        self.assertEqual(self.client.get(url).status_code, 404)

    def test_shipped_email_has_invoice_and_courier(self):
        order = self.place_cod_order()
        order.courier, order.awb = "Delhivery", "AWB123"
        order.tracking_url = "https://track.example.com/AWB123"
        mail.outbox.clear()
        order.status = Order.Status.SHIPPED
        order.save()
        body = mail.outbox[0].body
        self.assertIn("AWB123", body)
        self.assertIn("/invoice/", body)
        order.refresh_from_db()
        self.assertIsNotNone(order.shipped_at)


class CourierTests(Base):
    def test_static_estimate_is_default(self):
        info = shipping.check_pincode("226001")
        self.assertTrue(info["serviceable"])
        self.assertEqual(info["source"], "estimate")

    @override_settings(COURIER=SHIPROCKET, SELLER={**settings.SELLER, "pincode": "110001"})
    def test_shiprocket_serviceability_uses_courier_days(self):
        def fake(method, url, **kw):
            return mock.Mock(status_code=200, json=lambda: {"data": {"available_courier_companies": [
                {"estimated_delivery_days": 2}, {"estimated_delivery_days": 4}]}})
        with mock.patch("core.shipping.requests.post", return_value=mock.Mock(status_code=200, json=lambda: {"token": "t"})), \
             mock.patch("core.shipping.requests.request", side_effect=fake):
            info = shipping.check_pincode("560001")
        self.assertEqual((info["source"], info["min_days"]), ("courier", 2))

    @override_settings(COURIER=SHIPROCKET, SELLER={**settings.SELLER, "pincode": "110001"})
    def test_courier_outage_falls_back_to_estimate(self):
        import requests
        with mock.patch("core.shipping.requests.post", side_effect=requests.ConnectionError()):
            info = shipping.check_pincode("560002")
        self.assertEqual(info["source"], "estimate")

    @override_settings(COURIER=SHIPROCKET)
    def test_create_shipment_stores_awb(self):
        order = self.place_cod_order()

        def fake(method, url, **kw):
            if url.endswith("/orders/create/adhoc"):
                return mock.Mock(status_code=200, json=lambda: {"shipment_id": 77})
            return mock.Mock(status_code=200, json=lambda: {"response": {"data": {"awb_code": "AWB9", "courier_name": "Delhivery"}}})
        with mock.patch("core.shipping.requests.post", return_value=mock.Mock(status_code=200, json=lambda: {"token": "t"})), \
             mock.patch("core.shipping.requests.request", side_effect=fake):
            shipping.create_shipment(order)
        order.refresh_from_db()
        self.assertEqual((order.awb, order.courier), ("AWB9", "Delhivery"))

    def test_create_shipment_without_courier_raises(self):
        with self.assertRaises(shipping.CourierError):
            shipping.create_shipment(self.place_cod_order())

    @override_settings(COURIER={**settings.COURIER, "webhook_token": "sekret"})
    def test_webhook_updates_status_and_events(self):
        order = self.place_cod_order()
        order.awb = "AWB1"
        order.status = Order.Status.CONFIRMED
        order.save()
        url = reverse("courier_webhook")

        def post(payload, key="sekret"):
            return self.client.post(url, json.dumps(payload), content_type="application/json", headers={"x-api-key": key})
        self.assertEqual(post({"awb": "AWB1"}, key="wrong").status_code, 403)
        self.assertEqual(post({"awb": "AWB1", "current_status": "IN TRANSIT", "current_timestamp": "2026-10-30 10:00:00"}).status_code, 200)
        order.refresh_from_db()
        self.assertEqual(order.status, Order.Status.SHIPPED)
        post({"awb": "AWB1", "current_status": "DELIVERED", "current_timestamp": "2026-10-31 10:00:00"})
        post({"awb": "AWB1", "current_status": "IN TRANSIT", "current_timestamp": "2026-10-31 11:00:00"})  # late scan
        order.refresh_from_db()
        self.assertEqual(order.status, Order.Status.DELIVERED)
        self.assertEqual(TrackingEvent.objects.filter(order=order).count(), 3)
        self.assertFalse(post({"awb": "UNKNOWN", "current_status": "DELIVERED"}).json()["matched"])

    def test_webhook_is_closed_without_a_configured_token(self):
        r = self.client.post(reverse("courier_webhook"), "{}", content_type="application/json", headers={"x-api-key": ""})
        self.assertEqual(r.status_code, 403)

    def test_tracking_page_shows_courier_details(self):
        order = self.place_cod_order()
        order.awb, order.courier, order.status = "AWB5", "Delhivery", Order.Status.SHIPPED
        order.save()
        TrackingEvent.objects.create(order=order, status="Out for delivery", location="Lucknow")
        r = self.client.post(reverse("track"), {"number": order.number, "phone": order.phone})
        self.assertContains(r, "AWB5")
        self.assertContains(r, "Out for delivery")


class LegalAndOpsTests(Base):
    def test_legal_pages_render_and_are_linked(self):
        for name in ("terms", "grievance", "cookies"):
            self.assertEqual(self.client.get(reverse(name)).status_code, 200, name)
        home = self.client.get(reverse("home")).content.decode()
        for name in ("terms", "grievance", "cookies"):
            self.assertIn(reverse(name), home)
        self.assertIn('id="cookieBar"', home)

    def test_draft_notice_is_staff_only(self):
        self.assertNotContains(self.client.get(reverse("terms")), "working draft")
        staff = self.make_user("staff@example.com")
        staff.is_staff = True
        staff.save()
        self.sign_in(staff)
        self.assertContains(self.client.get(reverse("terms")), "working draft")

    def test_grievance_page_uses_configured_officer(self):
        with override_settings(SELLER={**settings.SELLER, "grievance_name": "A. Sharma"}):
            self.assertContains(self.client.get(reverse("grievance")), "A. Sharma")

    def test_healthz(self):
        r = self.client.get(reverse("healthz"))
        self.assertEqual((r.status_code, r.json()["status"]), (200, "ok"))

    def test_admin_ip_allowlist(self):
        with override_settings(ADMIN_ALLOWED_IPS=["10.0.0.1"]):
            self.assertEqual(self.client.get("/admin/login/", REMOTE_ADDR="9.9.9.9").status_code, 404)
            self.assertEqual(self.client.get("/admin/login/", REMOTE_ADDR="10.0.0.1").status_code, 200)

    def test_forwarded_header_ignored_unless_trusted(self):
        with override_settings(ADMIN_ALLOWED_IPS=["10.0.0.1"]):
            r = self.client.get("/admin/login/", REMOTE_ADDR="9.9.9.9", HTTP_X_FORWARDED_FOR="10.0.0.1")
            self.assertEqual(r.status_code, 404)
        with override_settings(ADMIN_ALLOWED_IPS=["10.0.0.1"], TRUST_PROXY_IP=True):
            r = self.client.get("/admin/login/", REMOTE_ADDR="127.0.0.1", HTTP_X_FORWARDED_FOR="1.2.3.4, 10.0.0.1")
            self.assertEqual(r.status_code, 200)

    def test_backup_command_writes_files(self):
        with tempfile.TemporaryDirectory() as d:
            call_command("backup_db", "--dir", d, stdout=StringIO())
            folder = next(Path(d).iterdir())
            self.assertTrue((folder / "db.sqlite3").exists() or (folder / "db.sql").exists())

    def test_admin_pages_open(self):
        boss = self.make_user("boss@example.com")
        boss.is_staff = boss.is_superuser = True
        boss.save()
        self.sign_in(boss)
        self.place_cod_order()
        self.sign_in(boss)
        for url in ("/admin/core/order/", "/admin/core/batch/", "/admin/core/product/"):
            self.assertEqual(self.client.get(url).status_code, 200, url)


class SecurityHeaderTests(Base):
    def test_csp_is_sent_and_only_razorpay_is_external(self):
        csp = self.client.get(reverse("home"))["Content-Security-Policy"]
        self.assertIn("default-src 'self'", csp)
        self.assertNotIn("cdn.jsdelivr", csp)
        self.assertIn("https://*.razorpay.com", csp)

    @override_settings(CSP_MODE="report-only")
    def test_report_only_mode(self):
        r = self.client.get(reverse("home"))
        self.assertIn("Content-Security-Policy-Report-Only", r)
        self.assertNotIn("Content-Security-Policy", r)

    def test_pages_do_not_load_third_party_assets(self):
        html = self.client.get(reverse("home")).content.decode()
        for host in ("cdn.jsdelivr.net", "fonts.googleapis.com", "fonts.gstatic.com"):
            self.assertNotIn(host, html)
