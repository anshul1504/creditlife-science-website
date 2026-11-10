"""Order updates by SMS (MSG91) and WhatsApp (Meta Cloud API).

Both are off until their credentials are in .env. Indian rules apply: SMS templates must be DLT-registered and
WhatsApp messages sent outside a customer-started chat must use a template approved by Meta. Template ids/names
come from settings (NOTIFY). Variables are passed in a fixed order, so create templates that match:

    placed  : {{1}} customer name, {{2}} order number, {{3}} total in rupees
    status  : {{1}} customer name, {{2}} order number, {{3}} status text (e.g. Shipped)

The HTTP calls follow the providers' public docs but could not be exercised against live accounts here
(tests use mocks). Send yourself a test order with each channel switched on before telling customers about it.
"""
import logging

import requests
from django.conf import settings

logger = logging.getLogger(__name__)
TIMEOUT = 6

STATUS_TEXT = {"confirmed": "Confirmed", "shipped": "Shipped", "delivered": "Delivered", "cancelled": "Cancelled"}


def _e164(phone):
    digits = "".join(ch for ch in str(phone) if ch.isdigit())
    return digits if digits.startswith("91") and len(digits) == 12 else "91" + digits[-10:]


def sms_enabled():
    return bool(settings.NOTIFY["msg91_authkey"])


def whatsapp_enabled():
    return bool(settings.NOTIFY["whatsapp_token"] and settings.NOTIFY["whatsapp_phone_id"])


def send_sms(phone, template_id, values):
    if not (sms_enabled() and template_id):
        return False
    body = {"template_id": template_id, "recipients": [{"mobiles": _e164(phone), **{f"var{i}": v for i, v in enumerate(values, 1)}}]}
    resp = requests.post("https://control.msg91.com/api/v5/flow/", json=body,
                         headers={"authkey": settings.NOTIFY["msg91_authkey"], "content-type": "application/json"}, timeout=TIMEOUT)
    resp.raise_for_status()
    return True


def send_whatsapp(phone, template_name, values):
    if not (whatsapp_enabled() and template_name):
        return False
    n = settings.NOTIFY
    body = {
        "messaging_product": "whatsapp", "to": _e164(phone), "type": "template",
        "template": {"name": template_name, "language": {"code": n["whatsapp_language"]},
                     "components": [{"type": "body", "parameters": [{"type": "text", "text": str(v)} for v in values]}]},
    }
    resp = requests.post(f"https://graph.facebook.com/v19.0/{n['whatsapp_phone_id']}/messages", json=body,
                         headers={"Authorization": f"Bearer {n['whatsapp_token']}"}, timeout=TIMEOUT)
    resp.raise_for_status()
    return True


def _both(phone, sms_template, wa_template, values):
    for label, fn, template in (("sms", send_sms, sms_template), ("whatsapp", send_whatsapp, wa_template)):
        try:
            fn(phone, template, values)
        except Exception:  # noqa: BLE001 - a messaging outage must never break an order
            logger.exception("Could not send %s update to %s", label, phone)


def order_placed(order):
    n = settings.NOTIFY
    _both(order.phone, n["msg91_template_placed"], n["whatsapp_template_placed"], [order.name.split()[0], order.number, order.total])


def order_status(order):
    text = STATUS_TEXT.get(order.status)
    if not text:
        return
    n = settings.NOTIFY
    _both(order.phone, n["msg91_template_status"], n["whatsapp_template_status"], [order.name.split()[0], order.number, text])


def send_sms_otp(phone, code):
    """Send a sign-in code by SMS. Raises if SMS is not set up, so the caller can tell the customer."""
    template = settings.NOTIFY["msg91_template_otp"]
    if not (sms_enabled() and template):
        raise RuntimeError("SMS codes are not configured.")
    send_sms(phone, template, [code])
