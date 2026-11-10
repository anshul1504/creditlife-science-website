"""Order lifecycle helpers shared by the checkout, account and admin code."""
import logging

from django.conf import settings
from django.core.mail import send_mail
from django.db import models, transaction

from . import emails, loyalty, payments
from .models import Address, Batch, CouponRedemption, Order, OrderAllocation, OrderItem, Product, StockMovement, log_stock
from . import sitecfg

logger = logging.getLogger(__name__)


class CouponChanged(Exception):
    """The coupon stopped being valid between adding it and placing the order."""


class PointsChanged(Exception):
    """The customer no longer has the credit points the cart was counting on."""


class StockError(Exception):
    """Not enough stock for a line, by the time the customer pressed Place order."""


def allocate_stock(item):
    """Take the item's units from the batches that expire first. Must run inside a transaction."""
    product = item.product
    if product is None or not product.track_inventory:
        return
    need = item.quantity
    batches = Batch.objects.select_for_update().filter(pk__in=product.batches.sellable().values("pk")).order_by("expiry", "id")
    for batch in batches:
        take = min(batch.quantity, need)
        if take:
            batch.quantity -= take
            batch.save(update_fields=["quantity"])
            OrderAllocation.objects.create(item=item, batch=batch, quantity=take)
            log_stock(product, -take, StockMovement.Reason.SALE, batch=batch, reference=item.order.number)
            need -= take
        if not need:
            break
    if need:
        raise StockError(f"Only {item.quantity - need} unit(s) of {product.name} are left.")
    product.refresh_stock_flag()


def take_stock(product, quantity, reference="", user=None):
    """Take units out of the batches that expire first, for a replacement that is being sent (no order line). Returns units taken."""
    if product is None or not product.track_inventory:
        return quantity
    need = quantity
    with transaction.atomic():
        for batch in Batch.objects.select_for_update().filter(pk__in=product.batches.sellable().values("pk")).order_by("expiry", "id"):
            take = min(batch.quantity, need)
            if take:
                batch.quantity -= take
                batch.save(update_fields=["quantity"])
                log_stock(product, -take, StockMovement.Reason.REPLACEMENT, batch=batch, reference=reference, user=user)
                need -= take
            if not need:
                break
        product.refresh_stock_flag()
    return quantity - need


def release_stock(order):
    """Put an order's units back into the batches they came from (once)."""
    if order.stock_released:
        return
    with transaction.atomic():
        touched = set()
        for alloc in OrderAllocation.objects.select_for_update().filter(item__order=order).select_related("batch__product"):
            Batch.objects.filter(pk=alloc.batch_id).update(quantity=models.F("quantity") + alloc.quantity)
            log_stock(alloc.batch.product, alloc.quantity, StockMovement.Reason.CANCEL, batch=alloc.batch, reference=order.number)
            touched.add(alloc.batch.product_id)
        Order.objects.filter(pk=order.pk).update(stock_released=True)
        order.stock_released = True
        for product in Product.objects.filter(pk__in=touched):
            product.refresh_stock_flag()


def place_order(request, form, cart):
    """Create the order, its lines and the coupon redemption in one transaction."""
    rows = cart.items
    coupon = cart.coupon
    user = request.user if request.user.is_authenticated else None
    with transaction.atomic():
        order = form.save(commit=False)
        order.user = user
        order.subtotal = cart.subtotal
        order.discount = cart.discount
        order.bundle_discount = cart.bundle_discount
        order.points_used = cart.points_used
        order.shipping = cart.shipping
        order.total = cart.total
        order.coupon_code = coupon.code if coupon else ""
        online = order.payment_method == Order.Payment.ONLINE
        order.payment_status = Order.PaymentStatus.PENDING if online else Order.PaymentStatus.COD
        if coupon:  # check again with the contact details so a guest cannot reuse a one-per-customer code
            _, error = coupon.evaluate(cart.subtotal, user, order.email, order.phone)
            if error:
                raise CouponChanged(error)
        order.save()
        for row in rows:
            item = OrderItem.objects.create(
                order=order, product=row["product"], product_name=row["product"].name, pack=row["product"].pack,
                unit_price=row["unit"], quantity=row["qty"], hsn_code=row["product"].hsn_code, gst_rate=row["product"].gst_rate,
            )
            allocate_stock(item)  # raises StockError, which rolls the whole order back
        if order.points_used:
            try:
                loyalty.redeem(order, user, order.points_used)
            except ValueError as exc:
                raise PointsChanged(str(exc)) from exc
        if coupon:
            CouponRedemption.objects.create(coupon=coupon, order=order, user=user, email=order.email, phone=order.phone, discount=order.discount)
        if user and form.cleaned_data.get("save_address"):
            d = form.cleaned_data
            Address.objects.get_or_create(
                user=user, address=d["address"], pincode=d["pincode"],
                defaults={"name": d["name"], "phone": d["phone"], "city": d["city"], "state": d["state"], "label": "Home"},
            )
    return order


def cancel_order(order):
    """Cancel an order, release its coupon and refund it if it was paid online.

    Returns "refunded", "refund_failed" or "" so the caller can tell the customer what happened.
    """
    outcome = ""
    if order.paid_online:
        try:
            payments.refund(order)
            outcome = "refunded"
        except payments.PaymentError:
            outcome = "refund_failed"
            order.payment_error = "Refund needs manual action"
            send_mail(
                f"Refund needed for order {order.number}",
                f"Order {order.number} (Rs {order.total}) was cancelled but the automatic Razorpay refund failed.\\n"
                f"Payment id: {order.razorpay_payment_id}\\nPlease refund it from the Razorpay dashboard.",
                None, sitecfg.site()["order_recipients"], fail_silently=True,
            )
    with transaction.atomic():
        CouponRedemption.objects.filter(order=order).delete()  # the code becomes usable again
        order.status = Order.Status.CANCELLED
        order.save()  # the status-change signal emails the customer
    release_stock(order)
    return outcome


def finalize_online_payment(order):
    """Runs once, when an online payment is confirmed."""
    emails.send_order_placed(order)


class SubscriptionSkipped(Exception):
    """A subscription delivery could not be placed (product unavailable, no address...)."""


def place_subscription_order(sub):
    """Create the cash-on-delivery order for one due Subscribe & Save delivery."""
    product, user, addr = sub.product, sub.user, sub.address
    if addr is None:
        raise SubscriptionSkipped("no delivery address")
    if not (product.sellable and product.in_stock):
        raise SubscriptionSkipped(f"{product.name} is not available")
    subtotal = sub.unit_price * sub.quantity
    threshold = settings.SHOP["free_shipping_above"]
    shipping = 0 if (threshold and subtotal >= threshold) else settings.SHOP["shipping_fee"]
    with transaction.atomic():
        order = Order.objects.create(
            user=user, name=addr.name, phone=addr.phone, email=user.email, address=addr.address, city=addr.city, state=addr.state,
            pincode=addr.pincode, notes="Subscribe & Save", payment_method=Order.Payment.COD, payment_status=Order.PaymentStatus.COD,
            subtotal=subtotal, shipping=shipping, total=subtotal + shipping,
        )
        item = OrderItem.objects.create(
            order=order, product=product, product_name=product.name, pack=product.pack, unit_price=sub.unit_price,
            quantity=sub.quantity, hsn_code=product.hsn_code, gst_rate=product.gst_rate,
        )
        allocate_stock(item)
    return order
