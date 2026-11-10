"""Invoices, courier webhook, legal pages and health check."""
import hmac
import json
import logging

from django.conf import settings
from django.core import signing
from django.db import connection
from django.http import Http404, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, render
from django.utils.dateparse import parse_datetime
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST

from . import invoice
from .models import Order, TrackingEvent

logger = logging.getLogger(__name__)
INVOICE_SALT = "core.invoice"


def invoice_token(order):
    return signing.dumps(order.number, salt=INVOICE_SALT)


def invoice_url(order):
    from django.urls import reverse
    return reverse("invoice", args=[order.number]) + f"?t={invoice_token(order)}"


def invoice_pdf(request, number):
    """Owner (signed in), staff, or anyone holding the signed link we put on the order page / email."""
    order = get_object_or_404(Order, number=number)
    allowed = request.user.is_staff or (request.user.is_authenticated and order.user_id == request.user.id)
    if not allowed:
        try:
            allowed = signing.loads(request.GET.get("t", ""), salt=INVOICE_SALT) == order.number
        except signing.BadSignature:
            allowed = False
    if not allowed:
        raise Http404
    if order.status == Order.Status.CANCELLED:
        raise Http404
    pdf = invoice.render_pdf(order)
    resp = HttpResponse(pdf, content_type="application/pdf")
    resp["Content-Disposition"] = f'inline; filename="invoice-{order.number}.pdf"'
    resp["Cache-Control"] = "private, no-store"
    return resp


# ------------------------------------------------------------------ courier
STATUS_MAP = {
    "PICKED UP": Order.Status.SHIPPED, "SHIPPED": Order.Status.SHIPPED, "IN TRANSIT": Order.Status.SHIPPED,
    "OUT FOR DELIVERY": Order.Status.SHIPPED, "REACHED AT DESTINATION HUB": Order.Status.SHIPPED,
    "DELIVERED": Order.Status.DELIVERED,
}


@csrf_exempt
@require_POST
def courier_webhook(request):
    token = settings.COURIER["webhook_token"]
    given = request.headers.get("x-api-key", "")
    if not token or not hmac.compare_digest(given, token):
        return HttpResponse(status=403)
    try:
        data = json.loads(request.body or b"{}")
    except ValueError:
        return HttpResponse(status=400)
    awb = str(data.get("awb") or "").strip()
    order = Order.objects.filter(awb=awb).first() if awb else None
    if not order:
        return JsonResponse({"ok": True, "matched": False})  # 200 so the courier does not keep retrying
    label = str(data.get("current_status") or "").strip()
    at = parse_datetime(str(data.get("current_timestamp") or "")) or timezone.now()
    if timezone.is_naive(at):
        at = timezone.make_aware(at)
    if label and not TrackingEvent.objects.filter(order=order, status=label[:80], at=at).exists():
        TrackingEvent.objects.create(order=order, status=label[:80], location=str(data.get("location") or "")[:80], at=at)
    new_status = STATUS_MAP.get(label.upper())
    if new_status and order.status not in (Order.Status.CANCELLED, Order.Status.DELIVERED):
        # never move an order backwards (a late "in transit" scan after "delivered")
        order_rank = [Order.Status.PLACED, Order.Status.CONFIRMED, Order.Status.SHIPPED, Order.Status.DELIVERED]
        if order_rank.index(new_status) > order_rank.index(order.status):
            order.status = new_status
            order.save()  # signals email the customer and stamp shipped_at / delivered_at
    return JsonResponse({"ok": True, "matched": True})


# ------------------------------------------------------------------- pages
def terms(request):
    return render(request, "core/terms.html")


def grievance(request):
    return render(request, "core/grievance.html")


def cookies(request):
    return render(request, "core/cookies.html")


@require_GET
def healthz(request):
    """For uptime monitors: 200 only when the database answers."""
    try:
        with connection.cursor() as cur:
            cur.execute("SELECT 1")
    except Exception:  # noqa: BLE001 - any failure means unhealthy
        logger.exception("Health check failed")
        return JsonResponse({"status": "down"}, status=503)
    return JsonResponse({"status": "ok"})


# --------------------------------------------------------------------- PWA
def manifest(request):
    from django.templatetags.static import static
    data = {
        "name": "Credit Lifesciences", "short_name": "Credit Life", "description": "Health and wellness products delivered to your door.",
        "start_url": "/?source=pwa", "scope": "/", "display": "standalone", "orientation": "portrait",
        "background_color": "#ffffff", "theme_color": "#0e7a55", "lang": "en-IN",
        "icons": [
            {"src": static("img/icon-192.png"), "sizes": "192x192", "type": "image/png", "purpose": "any"},
            {"src": static("img/icon-512.png"), "sizes": "512x512", "type": "image/png", "purpose": "any"},
        ],
    }
    return JsonResponse(data, content_type="application/manifest+json")


def service_worker(request):
    from django.conf import settings as s
    resp = render(request, "pwa/sw.js", {"version": s.PWA_VERSION, "static_url": s.STATIC_URL, "media_url": s.MEDIA_URL, "admin_url": s.ADMIN_URL},
                  content_type="application/javascript")
    resp["Service-Worker-Allowed"] = "/"
    resp["Cache-Control"] = "no-cache"
    return resp


def offline(request):
    return render(request, "pwa/offline.html")
