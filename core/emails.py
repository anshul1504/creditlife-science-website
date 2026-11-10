"""All transactional emails. Each one has an HTML and a plain-text template under templates/emails/."""
import logging

from django.conf import settings
from django.core.mail import EmailMultiAlternatives, send_mail
from django.template.loader import render_to_string
from django.urls import reverse

from . import notify
from .tokens import make_unsub_token, make_verify_token
from .views_ops import invoice_url
from . import sitecfg

logger = logging.getLogger(__name__)


def abs_url(path):
    return settings.SITE_URL.rstrip("/") + path


def _send(subject, template, context, to):
    to = [addr for addr in to if addr]
    if not to:
        return
    ctx = {"SITE": sitecfg.site(), "SITE_URL": settings.SITE_URL.rstrip("/"), "subject": subject, **context}
    try:
        text = render_to_string(f"emails/{template}.txt", ctx)
        html = render_to_string(f"emails/{template}.html", ctx)
        # The sender is a no-reply mailbox, so replies are routed to the support address.
        if settings.EMAIL_QUEUE:
            from .models import EmailJob
            EmailJob.objects.create(to=to, subject=subject, text=text, html=html, reply_to=[sitecfg.site()["email"]])
            return
        msg = EmailMultiAlternatives(subject, text, settings.DEFAULT_FROM_EMAIL, to, reply_to=[sitecfg.site()["email"]])
        msg.attach_alternative(html, "text/html")
        msg.send()
    except Exception:  # an email problem must never break checkout or sign-up
        logger.exception("Could not send %s email to %s", template, to)


def send_verification(user):
    url = abs_url(reverse("verify_email", args=[make_verify_token(user)]))
    _send("Verify your email for Credit Lifesciences", "verify_email", {"user": user, "verify_url": url}, [user.email])


OTP_LABELS = {"login": "sign-in", "signup": "sign-up", "reset": "password reset", "verify": "email verification"}


def send_otp(email, code, purpose, minutes):
    label = OTP_LABELS.get(purpose, "verification")
    _send(f"{code} is your Credit Lifesciences {label} code", "otp", {"code": code, "minutes": minutes, "purpose_label": label}, [email])


def send_welcome(user):
    _send(
        "Welcome to Credit Lifesciences",
        "welcome",
        {"user": user, "shop_url": abs_url(reverse("products")), "account_url": abs_url(reverse("account"))},
        [user.email],
    )


def send_newsletter_welcome(subscriber):
    _send(
        "You are subscribed to Credit Lifesciences updates",
        "newsletter_welcome",
        {
            "shop_url": abs_url(reverse("products")),
            "unsubscribe_url": abs_url(reverse("newsletter_unsubscribe", args=[make_unsub_token(subscriber.email)])),
        },
        [subscriber.email],
    )


def send_password_changed(user):
    _send(
        "Your Credit Lifesciences password was changed",
        "password_changed",
        {"user": user, "reset_url": abs_url(reverse("password_reset"))},
        [user.email],
    )


def _order_email_address(order):
    return order.email or (order.user.email if order.user_id else "")


def send_order_placed(order):
    notify.order_placed(order)
    ctx = {
        "order": order,
        "items": list(order.items.all()),
        "track_url": abs_url(reverse("track")),
        "orders_url": abs_url(reverse("account_orders")) if order.user_id else "",
    }
    _send(f"Order {order.number} received", "order_placed", ctx, [_order_email_address(order)])
    lines = "\n".join(f"  {i.quantity} x {i.product_name} ({i.pack}) - Rs {i.line_total}" for i in order.items.all())
    send_mail(
        f"New order {order.number} - Rs {order.total} ({'PAID online' if order.paid_online else 'Cash on delivery'})",
        f"Order {order.number}\n\n{lines}\n\nSubtotal: Rs {order.subtotal}\nShipping: Rs {order.shipping}\n"
        f"Discount: Rs {order.discount} ({order.coupon_code or '-'})\nTotal: Rs {order.total} ({order.get_payment_method_display()})\n\nShip to:\n{order.name}\n{order.address}\n"
        f"{order.city}, {order.state} - {order.pincode}\nPhone: {order.phone}\nEmail: {order.email or '-'}\n"
        f"Admin: {abs_url('/admin/core/order/')}",
        None,
        sitecfg.site()["order_recipients"],
        fail_silently=True,
    )


STATUS_COPY = {
    "confirmed": ("Your order is confirmed", "We have confirmed your order and are getting it ready."),
    "shipped": ("Your order is on its way", "Your order has been shipped and is on its way to you."),
    "delivered": ("Your order was delivered", "Your order has been delivered. We hope you are happy with it."),
    "cancelled": ("Your order was cancelled", "Your order has been cancelled. If you did not ask for this, please call us."),
}


def send_order_status(order):
    notify.order_status(order)
    copy = STATUS_COPY.get(order.status)
    if not copy:
        return
    heading, message = copy
    ctx = {
        "order": order,
        "items": list(order.items.all()),
        "heading": heading,
        "message": message,
        "refunded": order.payment_status == "refunded",
        "track_url": abs_url(reverse("track")),
        "invoice_url": abs_url(invoice_url(order)) if order.status in ("shipped", "delivered") else "",
        "review_urls": [(i.product_name, abs_url(i.product.get_absolute_url() + "#reviews")) for i in order.items.all() if i.product_id] if order.status == "delivered" else [],
    }
    _send(f"Order {order.number}: {heading.lower()}", "order_status", ctx, [_order_email_address(order)])


def send_enquiry_received(enquiry):
    _send("We received your enquiry", "enquiry_received", {"enquiry": enquiry}, [enquiry.email])
    send_mail(
        f"New website enquiry ({enquiry.get_topic_display()}): {enquiry.name}",
        f"Name: {enquiry.name}\nOrganisation: {enquiry.organisation}\nEnquiry type: {enquiry.get_topic_display()} | I am a: {enquiry.get_kind_display()}\n"
        f"Phone: {enquiry.phone}\nEmail: {enquiry.email}\nCity: {enquiry.city}\n"
        f"Product: {enquiry.product or 'General'}\n\n{enquiry.message}",
        None,
        sitecfg.site()["enquiry_recipients"],
        fail_silently=True,
    )


def send_abandoned_cart(user, rows):
    _send(
        "Your cart is waiting",
        "abandoned_cart",
        {
            "name": user.first_name or "there",
            "rows": rows,
            "cart_url": abs_url(reverse("cart")),
            "unsubscribe_url": abs_url(reverse("newsletter_unsubscribe", args=[make_unsub_token(user.email)])),
        },
        [user.email],
    )


RETURN_COPY = {
    "approved": ("Your return request is approved", "We have approved your request. Our team will contact you to arrange the {resolution}."),
    "pickup": ("Pickup arranged for your return", "We have arranged a pickup. {pickup} Please keep the item in its original packaging."),
    "received": ("We received your returned item", "We have received and checked the returned item. We are now arranging the {resolution}."),
    "withdrawn": ("Your return request was withdrawn", "As requested, we have closed this return request."),
    "rejected": ("Your return request was not approved", "We could not approve this request. {note}"),
    "resolved": ("Your return request is complete", "Your request is complete. Resolution: {resolution}."),
}


def send_return_received(req):
    ctx = {"req": req, "order": req.order, "heading": "We received your return request", "message": "Our team will review it and reply within 1 working day."}
    _send(f"Return request {req.reference} received for order {req.order.number}", "return_update", ctx, [_order_email_address(req.order)])
    send_mail(
        f"New return request {req.order.number} - {req.item.product_name}",
        "\n".join([
            f"{req.order.name} ({req.order.phone}) asked to return {req.quantity} x {req.item.product_name}.",
            f"Reason: {req.get_reason_display()}",
            req.details,
        ]),
        None, sitecfg.site()["order_recipients"], fail_silently=True,
    )


def send_return_update(req):
    copy = RETURN_COPY.get(req.status)
    if not copy:
        return
    heading, message = copy
    pickup = "Courier: %s, tracking %s%s." % (req.pickup_courier or "our partner", req.pickup_awb or "to follow",
                                             (", pickup on %s" % req.pickup_date.strftime("%d %b %Y")) if req.pickup_date else "") if (req.pickup_awb or req.pickup_date) else "Our team will confirm the pickup date."
    message = message.format(resolution=(req.get_resolution_display() or "agreed with you").lower(), note=req.staff_note, pickup=pickup)
    ctx = {"req": req, "order": req.order, "heading": heading, "message": message}
    _send(f"Return update for order {req.order.number}", "return_update", ctx, [_order_email_address(req.order)])


def send_return_refund(req):
    message = "We have started a refund of Rs. %s for return %s. %s" % (
        req.refund_value, req.reference,
        "It reaches your original payment method in 5 to 7 working days." if req.refund_id else "Our team will pay it to you directly and confirm with you.")
    ctx = {"req": req, "order": req.order, "heading": "Your refund has been started", "message": message}
    _send(f"Refund started for return {req.reference}", "return_update", ctx, [_order_email_address(req.order)])


def send_replacement_shipped(req):
    message = "Your replacement for %s x %s has been dispatched.%s" % (
        req.quantity, req.item.product_name, (" Courier: %s, tracking %s." % (req.replacement_courier or "our partner", req.replacement_awb)) if req.replacement_awb else "")
    ctx = {"req": req, "order": req.order, "heading": "Your replacement is on its way", "message": message}
    _send(f"Replacement dispatched for return {req.reference}", "return_update", ctx, [_order_email_address(req.order)])


def _notice(subject, user, heading, message):
    name = user.get_full_name() or user.email
    _send(subject, "account_notice", {"heading": heading, "message": message, "name": name}, [user.email])


def send_kyc_submitted(user):
    _notice("We received your business details", user, "Business details received",
            "Our team will check your GST and drug licence documents and get back to you within 1 working day.")
    p = user.profile
    send_mail(f"Business verification to review: {p.business_name}", chr(10).join([
        f"{user.get_full_name() or user.email} ({user.email}, {p.phone or '-'}) submitted their business details.",
        f"Type: {p.get_account_type_display()}", f"Business: {p.business_name}", f"GSTIN: {p.gstin}", f"Drug licence: {p.drug_licence_no}",
        "Review it in Admin > Customers > Profiles (filter: Under review)."]), None, sitecfg.site()["enquiry_recipients"], fail_silently=True)


def send_kyc_decision(user):
    p = user.profile
    if p.kyc_status == p.Kyc.APPROVED:
        _notice("Your business account is approved", user, "Your business account is approved", "You can now place orders. Thank you for choosing Credit Lifesciences.")
    elif p.kyc_status == p.Kyc.REJECTED:
        _notice("Your business details need changes", user, "We could not approve your details yet",
                "Please open Account > Business verification, fix the points below and submit again. " + (p.kyc_note or ""))


def send_question_to_team(q):
    send_mail(
        f"New product question: {q.product.name}",
        "\n".join([f"{q.user.get_full_name() or q.user.email} asked about {q.product.name}:", "", q.question, "",
                   "Answer it in the admin under Product questions."]),
        None, sitecfg.site()["enquiry_recipients"], fail_silently=True,
    )


def send_question_answered(q):
    ctx = {"q": q, "product_url": abs_url(q.product.get_absolute_url() + "#qa")}
    _send(f"Your question about {q.product.name} was answered", "question_answered", ctx, [q.user.email])


def send_subscription_reminder(sub):
    ctx = {"sub": sub, "account_url": abs_url(reverse("account_subscriptions")),
           "unit": sub.unit_price, "total": sub.unit_price * sub.quantity}
    _send(f"Your next {sub.product.name} delivery is coming up", "subscription_reminder", ctx, [sub.user.email])


def send_distributor_enquiry(enq):
    _send("We received your distributor enquiry", "distributor_ack", {"enq": enq}, [enq.email])
    send_mail(
        f"New distributor enquiry: {enq.firm_name} ({enq.district}, {enq.state})",
        "\n".join([
            f"Name: {enq.full_name}", f"Firm: {enq.firm_name}", f"Mobile: {enq.mobile}", f"Email: {enq.email}",
            f"State / district: {enq.state} / {enq.district}", f"GST: {enq.gst_number}", f"Drug licence: {enq.licence_number or '-'}",
            f"Experience: {enq.experience_years} years",
        ]),
        None, sitecfg.site()["enquiry_recipients"], fail_silently=True,
    )


def send_career_application(app):
    from django.core.mail import EmailMessage
    to = [sitecfg.site()["careers_email"]] if sitecfg.site().get("careers_email") else sitecfg.site()["enquiry_recipients"]
    msg = EmailMessage(
        f"New job application: {app.position} - {app.full_name}",
        "\n".join([
            f"Name: {app.full_name}", f"Mobile: {app.mobile}", f"Email: {app.email}", f"Location: {app.location}",
            f"Position: {app.position}", f"Experience: {app.experience_years} years", f"Qualification: {app.qualification}", "", app.message,
        ]),
        settings.DEFAULT_FROM_EMAIL, to, reply_to=[app.email],
    )
    try:
        app.resume.open("rb")
        msg.attach(app.resume.name.rsplit("/", 1)[-1], app.resume.read())
        app.resume.close()
        msg.send()
    except Exception:  # the application is already saved; an email problem must not lose it
        logger.exception("Could not email career application %s", app.pk)
