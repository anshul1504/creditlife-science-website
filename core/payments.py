"""Razorpay integration.

Flow: we create a Razorpay order for the amount -> the customer pays in Razorpay Checkout -> the browser sends back
the payment id + signature, which we verify with our secret (a forged success cannot pass) -> the webhook is a second,
server-to-server confirmation so a payment is never lost if the customer closes the tab.
"""
import hashlib
import hmac
import logging

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from .models import Order

logger = logging.getLogger(__name__)


class PaymentError(Exception):
    pass


def enabled():
    return bool(settings.RAZORPAY["key_id"] and settings.RAZORPAY["key_secret"])


def _client():
    import razorpay

    client = razorpay.Client(auth=(settings.RAZORPAY["key_id"], settings.RAZORPAY["key_secret"]))
    client.set_app_details({"title": "CreditLifesciences", "version": "1.0"})
    return client


def create_gateway_order(order):
    """Create (or reuse) the Razorpay order for this store order and remember its id."""
    if order.razorpay_order_id:
        return order.razorpay_order_id
    try:
        data = _client().order.create({
            "amount": order.total * 100,  # paise
            "currency": "INR",
            "receipt": order.number,
            "notes": {"order_number": order.number},
        })
    except Exception as exc:
        logger.exception("Razorpay order creation failed for %s", order.number)
        raise PaymentError("We could not start the payment. Please try again in a moment.") from exc
    order.razorpay_order_id = data["id"]
    order.save(update_fields=["razorpay_order_id", "updated_at"])
    return order.razorpay_order_id


def _sign(secret, message):
    return hmac.new(secret.encode(), message.encode() if isinstance(message, str) else message, hashlib.sha256).hexdigest()


def signature_is_valid(razorpay_order_id, payment_id, signature):
    if not (razorpay_order_id and payment_id and signature):
        return False
    expected = _sign(settings.RAZORPAY["key_secret"], f"{razorpay_order_id}|{payment_id}")
    return hmac.compare_digest(expected, signature)


def webhook_is_valid(body, signature):
    secret = settings.RAZORPAY["webhook_secret"]
    if not (secret and signature):
        return False
    return hmac.compare_digest(_sign(secret, body), signature)


@transaction.atomic
def mark_paid(order, payment_id):
    """Idempotent: returns True only for the call that actually flips the order to paid."""
    updated = Order.objects.filter(
        pk=order.pk, payment_status__in=[Order.PaymentStatus.PENDING, Order.PaymentStatus.FAILED]
    ).update(
        payment_status=Order.PaymentStatus.PAID, razorpay_payment_id=payment_id, payment_error="", paid_at=timezone.now()
    )
    order.refresh_from_db()
    return bool(updated)


def mark_failed(order, reason=""):
    Order.objects.filter(pk=order.pk, payment_status=Order.PaymentStatus.PENDING).update(
        payment_status=Order.PaymentStatus.FAILED, payment_error=(reason or "Payment failed")[:300]
    )
    order.refresh_from_db()


def refund(order):
    """Refund the full amount of a paid online order. Raises PaymentError if Razorpay refuses."""
    if not order.paid_online or not order.razorpay_payment_id:
        return False
    try:
        data = _client().payment.refund(order.razorpay_payment_id, {
            "amount": order.total * 100,
            "notes": {"order_number": order.number, "reason": "Order cancelled"},
        })
    except Exception as exc:
        logger.exception("Razorpay refund failed for %s", order.number)
        raise PaymentError("The refund could not be started automatically.") from exc
    order.refund_id = data.get("id", "")
    order.payment_status = Order.PaymentStatus.REFUNDED
    order.refunded_at = timezone.now()
    order.save(update_fields=["refund_id", "payment_status", "refunded_at", "updated_at"])
    return True


def refund_amount(order, rupees, note=""):
    """Refund part of a paid online order (for an approved return). Returns the Razorpay refund id, or "" when the
    order was paid by other means and the team must pay the customer back manually. Raises PaymentError on failure."""
    if not order.paid_online or not order.razorpay_payment_id:
        return ""
    rupees = min(int(rupees), order.total)
    try:
        data = _client().payment.refund(order.razorpay_payment_id, {
            "amount": rupees * 100,
            "notes": {"order_number": order.number, "reason": (note or "Return")[:100]},
        })
    except Exception as exc:
        logger.exception("Razorpay partial refund failed for %s", order.number)
        raise PaymentError("The refund could not be started automatically.") from exc
    return data.get("id", "")
