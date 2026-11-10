"""Courier layer: delivery estimates and shipment creation behind one small interface.

COURIER["provider"]:
  static     (default) estimates from the PIN code, creates nothing; staff enter the AWB by hand.
  shiprocket Shiprocket API (needs SHIPROCKET_EMAIL / SHIPROCKET_PASSWORD and a pickup PIN in SELLER).
The Shiprocket calls follow its public v1 API but could not be run against a live account here, so they are
covered by tests with a mocked HTTP layer only. Test them with real credentials before going live.
"""
import logging
from datetime import timedelta

import requests
from django.conf import settings
from django.core.cache import cache
from django.utils import timezone
from . import sitecfg

logger = logging.getLogger(__name__)
BASE = "https://apiv2.shiprocket.in/v1/external"


class CourierError(Exception):
    pass


# --------------------------------------------------------------- estimates
def _static_days(pin):
    """Without a courier connected, quote the company's own delivery promise (SHOP delivery_days, e.g. 5-7 business days)."""
    lo, hi = settings.SHOP.get("delivery_days") or (3, 7)
    return lo, hi


def check_pincode(pin, weight_kg=0.5, cod=True):
    """-> {"ok", "serviceable", "min_days", "max_days", "date", "cod", "source"}"""
    provider = settings.COURIER["provider"]
    if provider == "shiprocket" and settings.SELLER.get("pincode"):
        cached = cache.get(f"svc:{pin}:{int(cod)}")
        if cached:
            return cached
        try:
            result = _shiprocket_serviceability(pin, weight_kg, cod)
        except (CourierError, requests.RequestException) as exc:
            logger.warning("Courier serviceability failed for %s: %s", pin, exc)
            result = None
        if result:
            cache.set(f"svc:{pin}:{int(cod)}", result, 3600)
            return result
    lo, hi = _static_days(pin)
    return _result(True, lo, hi, True, "estimate")


def _result(serviceable, lo, hi, cod, source):
    today = timezone.localdate()
    return {"serviceable": serviceable, "min_days": lo, "max_days": hi, "cod": cod, "source": source,
            "date": (today + timedelta(days=hi)).isoformat() if serviceable else ""}


# -------------------------------------------------------------- shiprocket
def _token():
    token = cache.get("shiprocket_token")
    if token:
        return token
    c = settings.COURIER
    if not (c["email"] and c["password"]):
        raise CourierError("Shiprocket credentials are not configured.")
    resp = requests.post(f"{BASE}/auth/login", json={"email": c["email"], "password": c["password"]}, timeout=c["timeout"])
    if resp.status_code != 200 or "token" not in resp.json():
        raise CourierError("Shiprocket login failed.")
    token = resp.json()["token"]
    cache.set("shiprocket_token", token, 8 * 24 * 3600 - 3600)  # tokens last 10 days
    return token


def _call(method, path, **kwargs):
    headers = {"Authorization": f"Bearer {_token()}", "Content-Type": "application/json"}
    resp = requests.request(method, f"{BASE}{path}", headers=headers, timeout=settings.COURIER["timeout"], **kwargs)
    if resp.status_code >= 400:
        raise CourierError(f"Shiprocket {path}: HTTP {resp.status_code} {resp.text[:200]}")
    return resp.json()


def _shiprocket_serviceability(pin, weight_kg, cod):
    data = _call("GET", "/courier/serviceability/", params={
        "pickup_postcode": settings.SELLER["pincode"], "delivery_postcode": pin, "weight": weight_kg, "cod": int(cod)})
    companies = (data.get("data") or {}).get("available_courier_companies") or []
    if not companies:
        return _result(False, 0, 0, False, "courier")
    days = [int(c.get("estimated_delivery_days") or 0) for c in companies if c.get("estimated_delivery_days")]
    lo, hi = (min(days), min(days) + 2) if days else _static_days(pin)
    return _result(True, lo, hi, True, "courier")


def create_shipment(order):
    """Push the order to the courier and store AWB / tracking on it. Raises CourierError on any failure."""
    if settings.COURIER["provider"] != "shiprocket":
        raise CourierError("No courier is connected. Enter the AWB by hand or set COURIER_PROVIDER=shiprocket.")
    items = [{"name": i.product_name, "sku": i.product.slug if i.product else i.product_name, "units": i.quantity,
              "selling_price": i.unit_price, "hsn": i.hsn_code} for i in order.items.all()]
    payload = {
        "order_id": order.number, "order_date": timezone.localtime(order.created_at).strftime("%Y-%m-%d %H:%M"),
        "pickup_location": "Primary", "billing_customer_name": order.name, "billing_last_name": "",
        "billing_address": order.address, "billing_city": order.city, "billing_pincode": order.pincode,
        "billing_state": order.state, "billing_country": "India", "billing_email": order.email or sitecfg.site()["email"],
        "billing_phone": order.phone, "shipping_is_billing": True, "order_items": items,
        "payment_method": "COD" if order.payment_method == "cod" else "Prepaid", "sub_total": order.total,
        "length": 15, "breadth": 12, "height": 8, "weight": 0.5,
    }
    created = _call("POST", "/orders/create/adhoc", json=payload)
    shipment_id = created.get("shipment_id")
    if not shipment_id:
        raise CourierError("Courier did not return a shipment id.")
    assigned = _call("POST", "/courier/assign/awb", json={"shipment_id": shipment_id})
    awb = (((assigned.get("response") or {}).get("data")) or {}).get("awb_code", "")
    if not awb:
        raise CourierError("Courier did not assign an AWB.")
    order.courier = (((assigned.get("response") or {}).get("data")) or {}).get("courier_name", "Shiprocket")
    order.awb = awb
    order.tracking_url = f"https://shiprocket.co/tracking/{awb}"
    order.save(update_fields=["courier", "awb", "tracking_url"])
    return awb
