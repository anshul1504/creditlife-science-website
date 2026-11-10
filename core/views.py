import json
import re

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import redirect_to_login
from django.core.paginator import Paginator
from django.db.models import Avg, Count, Max, Min, Q
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.http import Http404, HttpResponse, JsonResponse
from django.templatetags.static import static
from django.urls import reverse
from django.utils import timezone
from urllib.parse import quote
from django.views.decorators.csrf import csrf_exempt
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_GET, require_POST

from . import emails, orders, payments, shipping
from . import search as search_service
from .cart import Cart
from .forms import CheckoutForm, EnquiryForm, QuestionForm, ReviewForm, SubscribeForm, TrackForm
from .models import Banner, District, Enquiry, Highlight, HeroSlide, TeamMessage, Order, OrderItem, Product, ReviewVote, Subscriber, Wishlist
from .tokens import read_unsub_token


def _is_ajax(request):
    return request.headers.get("x-requested-with") == "XMLHttpRequest"


def _qty(request, default=1):
    try:
        return max(1, min(int(request.POST.get("qty", default)), settings.SHOP["max_qty"]))
    except (TypeError, ValueError):
        return default


def order_timeline(order):
    steps = [
        (Order.Status.PLACED, "Order placed"),
        (Order.Status.CONFIRMED, "Confirmed"),
        (Order.Status.SHIPPED, "Shipped"),
        (Order.Status.DELIVERED, "Delivered"),
    ]
    reached = []
    if order and order.status != Order.Status.CANCELLED:
        keys = [k for k, _ in steps]
        reached = keys[: keys.index(order.status) + 1]
    return steps, reached


# ------------------------------------------------------------------ pages

CONCERNS = [
    ("digestive", "Acidity, gas & indigestion", "Everyday stomach comfort", "bi-heart-pulse"),
    ("nutrition", "Weakness & low haemoglobin", "Iron, folic acid, B12 and zinc", "bi-droplet-half"),
    ("pain", "Joint & muscle pain", "Ayurvedic oil with 29 herbs", "bi-activity"),
]


def active_banners():
    now = timezone.now()
    return [b for b in Banner.objects.filter(is_active=True)
            if (b.starts_at is None or b.starts_at <= now) and (b.ends_at is None or b.ends_at >= now)]


def home(request):
    products = list(Product.objects.filter(is_active=True))
    # a curated mix across Ayurvedic and Allopathic: round-robin so both appear near the top
    allo = [p for p in products if p.system == Product.System.ALLOPATHIC]
    ayur = [p for p in products if p.system == Product.System.AYURVEDIC]
    featured = []
    for i in range(max(len(allo), len(ayur))):
        featured += [lst[i] for lst in (allo, ayur) if i < len(lst)]
    districts = list(District.objects.all())
    counts = {key: sum(1 for d in districts if d.status == key) for key, _ in District.Status.choices}
    return render(request, "core/home.html", {
        "featured": featured[:6], "allopathic_count": len(allo), "ayurvedic_count": len(ayur),
        "districts": districts, "district_counts": counts, "banners": active_banners(),
        "slides": list(HeroSlide.objects.filter(is_active=True)), "product_count": len(products),
        "allo_products": allo[:3], "ayur_products": ayur[:3], "enquiry_form": EnquiryForm(),
        "why": Highlight.objects.filter(kind="why", is_active=True),
        "home_message": TeamMessage.objects.filter(is_published=True, show_on_home=True).first(),
    })


def about(request):
    from .models import Highlight, TeamMessage, TimelineItem
    return render(request, "core/about.html", {
        "messages_list": TeamMessage.objects.filter(is_published=True),
        "values": Highlight.objects.filter(kind="value", is_active=True),
        "principles": Highlight.objects.filter(kind="principle", is_active=True),
        "timeline": TimelineItem.objects.filter(is_active=True),
    })


def quality(request):
    # the brief asks for no separate quality page; the commitment now lives on the About page
    return redirect(reverse("about") + "#quality", permanent=True)


def policies(request):
    return render(request, "core/policies.html")


SORTS = {
    "popular": ("Relevance", ("order", "name")),
    "price_asc": ("Price: low to high", ("price", "name")),
    "price_desc": ("Price: high to low", ("-price", "name")),
    "rating": ("Customer rating", ("-avg_rating", "name")),
    "name": ("Name: A to Z", ("name",)),
}
PAGE_SIZE = 12


def _int_or_none(value):
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return None


def _drop_param(params, key, value=None):
    """URL (query string) of the current filters with one filter removed."""
    q = params.copy()
    if value is None:
        q.pop(key, None)
    else:
        q.setlist(key, [v for v in q.getlist(key) if v != value])
    q.pop("page", None)
    return "?" + q.urlencode() if q else "?"


def product_list(request):
    params = request.GET
    labels = dict(Product.Category.choices)
    cats = [c for c in params.getlist("cat") if c in labels]
    sys_labels = dict(Product.System.choices)
    systems = [x for x in params.getlist("system") if x in sys_labels]
    ingredient = params.get("ing", "").strip()[:60]
    pmin, pmax = _int_or_none(params.get("min")), _int_or_none(params.get("max"))
    avail = params.get("avail") == "1"
    sale = params.get("sale") == "1"
    ptype = params.get("type") if params.get("type") in ("otc", "rx") else ""
    rating = int(params["rating"]) if params.get("rating") in ("3", "4") else None
    sort = params.get("sort") if params.get("sort") in SORTS else "popular"

    base = Product.objects.filter(is_active=True)
    qs = base.annotate(avg_rating=Avg("reviews__rating", filter=Q(reviews__is_visible=True)))
    if cats:
        qs = qs.filter(category__in=cats)
    if systems:
        qs = qs.filter(system__in=systems)
    if ingredient:
        qs = qs.filter(composition__icontains=ingredient)
    if pmin:
        qs = qs.filter(price__gte=pmin)
    if pmax:
        qs = qs.filter(price__gt=0, price__lte=pmax)
    if avail:
        qs = qs.filter(is_rx=False, in_stock=True, price__gt=0)
    if sale:
        qs = qs.on_sale()
    if ptype == "otc":
        qs = qs.filter(is_rx=False)
    elif ptype == "rx":
        qs = qs.filter(is_rx=True)
    if rating:
        qs = qs.filter(avg_rating__gte=rating)
    qs = qs.order_by(*SORTS[sort][1])

    page = Paginator(qs, PAGE_SIZE).get_page(params.get("page"))

    counts = dict(base.values_list("category").annotate(n=Count("id")))
    sys_counts = dict(base.values_list("system").annotate(n=Count("id")))
    bounds = base.filter(price__gt=0).aggregate(lo=Min("price"), hi=Max("price"))
    lo = (bounds["lo"] or 0) // 10 * 10
    hi = -(-(bounds["hi"] or 0) // 10) * 10

    chips = [(labels[c], _drop_param(params, "cat", c)) for c in cats]
    chips += [(sys_labels[x], _drop_param(params, "system", x)) for x in systems]
    if ingredient:
        chips.append((f"Ingredient: {ingredient}", _drop_param(params, "ing")))
    if pmin or pmax:
        text = f"₹{pmin or lo} - ₹{pmax or hi}"
        q = params.copy()
        q.pop("min", None)
        q.pop("max", None)
        q.pop("page", None)
        chips.append((text, "?" + q.urlencode() if q else "?"))
    if avail:
        chips.append(("Available online", _drop_param(params, "avail")))
    if sale:
        chips.append(("On sale", _drop_param(params, "sale")))
    if ptype:
        chips.append(("Prescription (Rx)" if ptype == "rx" else "Non-prescription", _drop_param(params, "type")))
    if rating:
        chips.append((f"{rating}★ & above", _drop_param(params, "rating")))

    nopage = params.copy()
    nopage.pop("page", None)
    keep_sort = f"?sort={sort}" if sort != "popular" else "?"
    return render(
        request,
        "core/products.html",
        {
            "page": page,
            "products": page.object_list,
            "total": page.paginator.count,
            "categories": [(v, labels[v], counts.get(v, 0), v in cats) for v, _ in Product.Category.choices],
            "systems": [(v, sys_labels[v], sys_counts.get(v, 0), v in systems) for v, _ in Product.System.choices],
            "ingredient": ingredient,
            "price_lo": lo,
            "price_hi": hi,
            "pmin": pmin,
            "pmax": pmax,
            "avail": avail,
            "sale": sale,
            "ptype": ptype,
            "rating": rating,
            "sort": sort,
            "sorts": [(k, v[0]) for k, v in SORTS.items()],
            "chips": chips,
            "clear_url": keep_sort,
            "qs_nopage": nopage.urlencode(),
        },
    )


def search(request):
    query = request.GET.get("q", "").strip()[:80]
    products, shown, corrected = search_service.search(query) if query else ([], "", False)
    return render(request, "core/search.html", {"query": query, "products": products, "shown": shown, "corrected": corrected})


@require_GET
def search_suggest(request):
    """Small JSON list for the header search box as the customer types."""
    query = request.GET.get("q", "").strip()[:60]
    if len(query) < 2:
        return JsonResponse({"results": []})
    products, shown, corrected = search_service.search(query)
    results = [
        {"name": p.name, "sub": p.subtitle, "pack": p.pack, "url": p.get_absolute_url(), "image": static(p.image),
         "price": p.effective_price if p.sellable else None}
        for p in products[:6]
    ]
    return JsonResponse({"results": results, "corrected": shown if corrected else "", "all": reverse("search") + "?q=" + quote(shown)})


def product_detail(request, slug):
    product = get_object_or_404(Product, slug=slug, is_active=True)
    related = Product.objects.filter(is_active=True).exclude(pk=product.pk)
    same = [p for p in related if p.category == product.category]
    others = [p for p in related if p.category != product.category]

    reviews = list(product.reviews.filter(is_visible=True).select_related("user")[:30])
    stats = product.rating_stats
    dist = {n: 0 for n in range(5, 0, -1)}
    for r in product.reviews.filter(is_visible=True).values_list("rating", flat=True):
        dist[r] += 1
    bars = [(n, c, round(c * 100 / stats["count"]) if stats["count"] else 0) for n, c in dist.items()]

    verified_ids = set(
        OrderItem.objects.filter(product=product, order__user__in=[r.user_id for r in reviews])
        .exclude(order__status=Order.Status.CANCELLED).values_list("order__user_id", flat=True)
    )
    user_review = None
    can_review = False
    if request.user.is_authenticated:
        user_review = product.reviews.filter(user=request.user).first()
        can_review = request.user.profile.email_verified
    review_form = ReviewForm(instance=user_review) if can_review else None

    return render(
        request,
        "core/product_detail.html",
        {
            "product": product,
            "gallery": product.gallery,
            "faqs": list(product.faqs.all()),
            "questions": list(product.questions.filter(is_visible=True).exclude(answer="").select_related("user")[:20]),
            "question_form": QuestionForm(),
            "subscribe_form": SubscribeForm(),
            "voted_ids": set(ReviewVote.objects.filter(user=request.user, review__product=product).values_list("review_id", flat=True)) if request.user.is_authenticated else set(),
            "related": (same + others)[:4],
            "reviews": reviews,
            "stats": stats,
            "bars": bars,
            "verified_ids": verified_ids,
            "user_review": user_review,
            "can_review": can_review,
            "review_form": review_form,
            "manufacturer_rows": [tuple(p.strip() for p in ln.partition("|")[::2]) for ln in product.manufacturer.splitlines() if ln.strip()],
        },
    )


@login_required
@require_POST
def review_submit(request, slug):
    product = get_object_or_404(Product, slug=slug, is_active=True)
    if not request.user.profile.email_verified:
        messages.error(request, "Please verify your email address before writing a review.")
        return redirect(product)
    existing = product.reviews.filter(user=request.user).first()
    form = ReviewForm(request.POST, request.FILES, instance=existing)
    if form.is_valid():
        review = form.save(commit=False)
        review.product, review.user = product, request.user
        review.save()
        messages.success(request, "Thank you! Your review has been saved.")
    else:
        messages.error(request, "Please choose a star rating (and a photo under 5 MB, if you add one) to submit your review.")
    return redirect(product.get_absolute_url() + "#reviews")


@require_GET
def pincode_check(request):
    pin = request.GET.get("pin", "").strip()
    if not re.fullmatch(r"[1-9]\d{5}", pin):
        return JsonResponse({"ok": False, "message": "Please enter a valid 6-digit PIN code."})
    info = shipping.check_pincode(pin)
    if not info["serviceable"]:
        return JsonResponse({"ok": True, "serviceable": False, "message": f"Sorry, we cannot deliver to {pin} yet."})
    if info["source"] == "courier":
        message = f"Delivery available to {pin}. Estimated delivery in {info['min_days']}-{info['max_days']} days" + (" (cash on delivery available)." if info["cod"] else ".")
    else:
        message = f"Delivery available to {pin}. Usually delivered in {info['min_days']}-{info['max_days']} business days. Shipping charges are shown before payment."
    return JsonResponse({"ok": True, "serviceable": True, "message": message, "date": info["date"]})


@require_POST
def wishlist_toggle(request, slug):
    product = get_object_or_404(Product, slug=slug, is_active=True)
    if not request.user.is_authenticated:
        if _is_ajax(request):
            return JsonResponse({"ok": False, "login": True, "message": "Please sign in to save products."}, status=401)
        return redirect_to_login(product.get_absolute_url())
    item, created = Wishlist.objects.get_or_create(user=request.user, product=product)
    if not created:
        item.delete()
    if _is_ajax(request):
        return JsonResponse({"ok": True, "saved": created, "message": f"{product.name} {'saved to' if created else 'removed from'} your wishlist."})
    return redirect(request.META.get("HTTP_REFERER") or product.get_absolute_url())


# ------------------------------------------------------------------- cart

def _back(request, default="cart"):
    target = request.POST.get("next", "")
    if target and url_has_allowed_host_and_scheme(target, {request.get_host()}):
        return redirect(target)
    return redirect(default)


def cart_view(request):
    cart = Cart(request)
    return render(request, "core/cart.html", {"cart": cart, "offers": cart.available_offers()})


@require_POST
def coupon_apply(request):
    cart = Cart(request)
    ok, message = cart.apply_coupon(request.POST.get("code"))
    if _is_ajax(request):
        return JsonResponse({"ok": ok, "message": message}, status=200 if ok else 400)
    (messages.success if ok else messages.error)(request, message)
    return _back(request)


@require_POST
def points_apply(request):
    cart = Cart(request)
    try:
        ok, message = cart.apply_points(request.POST.get("points", "max"))
    except ValueError:
        ok, message = False, "Please enter a whole number of points."
    (messages.success if ok else messages.error)(request, message)
    return _back(request)


@require_POST
def points_remove(request):
    Cart(request).remove_points()
    return _back(request)


@require_POST
def coupon_remove(request):
    Cart(request).remove_coupon()
    if _is_ajax(request):
        return JsonResponse({"ok": True})
    return _back(request)


@require_POST
def cart_add(request, slug):
    product = get_object_or_404(Product, slug=slug, is_active=True)
    cart = Cart(request)
    if not (product.sellable and product.in_stock):
        message = f"{product.name} is not available for online purchase."
        if _is_ajax(request):
            return JsonResponse({"ok": False, "message": message}, status=400)
        messages.error(request, message)
        return redirect(product)
    cart.add(product, _qty(request))
    message = f"{product.name} added to your cart."
    if _is_ajax(request):
        return JsonResponse({"ok": True, "message": message, "count": cart.count})
    if request.POST.get("next") == "checkout":
        return redirect("checkout")
    messages.success(request, message)
    return redirect("cart")


@require_POST
def cart_update(request, slug):
    product = get_object_or_404(Product, slug=slug)
    cart = Cart(request)
    try:
        qty = int(request.POST.get("qty", 1))
    except (TypeError, ValueError):
        qty = 1
    cart.set(product, qty)
    return redirect("cart")


@require_POST
def cart_remove(request, slug):
    Cart(request).remove(slug)
    return redirect("cart")


# --------------------------------------------------------------- checkout

def _checkout_initial(user):
    if not user.is_authenticated:
        return {}
    initial = {"name": user.get_full_name(), "email": user.email, "phone": user.profile.phone}
    default = user.addresses.filter(is_default=True).first() or user.addresses.first()
    if default:
        initial.update(
            name=default.name, phone=default.phone, address=default.address,
            city=default.city, state=default.state, pincode=default.pincode,
        )
    return initial


def checkout(request):
    cart = Cart(request)
    if not cart.items:
        messages.info(request, "Your cart is empty. Add a product to continue.")
        return redirect("products")

    if settings.SHOP["require_login_to_order"] and not request.user.is_authenticated:
        messages.info(request, "Online ordering is for registered distributors and business partners. Please register or sign in to continue.")
        return redirect_to_login(reverse("checkout"))
    if settings.SHOP["require_kyc_to_order"] and not request.user.profile.kyc_approved:
        messages.info(request, "Ordering is open to verified business accounts. Please complete your business verification and we will approve it quickly.")
        return redirect("account_business")
    ordering_open = settings.SHOP["cod_enabled"] or settings.SHOP["online_payment_enabled"]

    if request.method == "POST" and ordering_open:
        form = CheckoutForm(request.POST)
        if form.is_valid():
            try:
                order = orders.place_order(request, form, cart)
            except orders.CouponChanged as exc:
                cart.remove_coupon()
                messages.error(request, f"Your coupon could not be applied: {exc} Please review your order.")
                return redirect("checkout")
            except orders.PointsChanged as exc:
                cart.remove_points()
                messages.error(request, f"{exc} We removed the credit points from your order. Please review it.")
                return redirect("checkout")
            except orders.StockError as exc:
                messages.error(request, f"Sorry, {exc} Please update your cart.")
                return redirect("cart")
            request.session["last_order"] = order.number
            if order.payment_method == Order.Payment.ONLINE and payments.enabled():
                return redirect("pay", number=order.number)  # the cart stays until the payment succeeds
            cart.clear()
            emails.send_order_placed(order)
            return redirect("order_success", number=order.number)
    else:
        form = CheckoutForm(initial=_checkout_initial(request.user))
    addresses = request.user.addresses.all() if request.user.is_authenticated else []
    return render(request, "core/checkout.html", {"cart": cart, "form": form, "addresses": addresses, "offers": cart.available_offers(), "ordering_open": ordering_open})


def _own_order(request, number):
    """The order this visitor just placed, or one that belongs to the signed-in customer."""
    order = get_object_or_404(Order, number=number)
    if request.session.get("last_order") == number or (request.user.is_authenticated and order.user_id == request.user.id):
        return order
    raise Http404


def pay(request, number):
    order = _own_order(request, number)
    if order.payment_status == Order.PaymentStatus.PAID:
        request.session["last_order"] = number
        return redirect("order_success", number=number)
    if not (order.awaiting_payment and payments.enabled()):
        messages.info(request, "This order does not need an online payment.")
        return redirect("track")
    try:
        gateway_order_id = payments.create_gateway_order(order)
    except payments.PaymentError as exc:
        messages.error(request, str(exc))
        return redirect("checkout" if Cart(request).items else "products")
    config = {
        "key": settings.RAZORPAY["key_id"],
        "order_id": gateway_order_id,
        "amount": order.total * 100,
        "name": settings.SITE["name"],
        "description": f"Order {order.number}",
        "prefill": {"name": order.name, "email": order.email, "contact": "+91" + order.phone},
        "verify_url": reverse("pay_verify", args=[number]),
        "failed_url": reverse("pay_failed", args=[number]),
        "cancel_url": reverse("cart"),
    }
    return render(request, "core/pay.html", {"order": order, "rz": config})


@require_POST
def pay_verify(request, number):
    order = _own_order(request, number)
    gateway_order_id = request.POST.get("razorpay_order_id", "")
    payment_id = request.POST.get("razorpay_payment_id", "")
    signature = request.POST.get("razorpay_signature", "")
    if gateway_order_id != order.razorpay_order_id or not payments.signature_is_valid(gateway_order_id, payment_id, signature):
        payments.mark_failed(order, "Payment could not be verified")
        return JsonResponse({"ok": False, "message": "We could not verify this payment. If money was deducted, it will be returned to you automatically. Please contact us if it does not."}, status=400)
    if payments.mark_paid(order, payment_id):
        orders.finalize_online_payment(order)
    Cart(request).clear()
    request.session["last_order"] = order.number
    return JsonResponse({"ok": True, "redirect": reverse("order_success", args=[number])})


@require_POST
def pay_failed(request, number):
    order = _own_order(request, number)
    payments.mark_failed(order, request.POST.get("reason", ""))
    return JsonResponse({"ok": True})


@csrf_exempt
@require_POST
def razorpay_webhook(request):
    """Server-to-server confirmation from Razorpay, so a payment is never lost if the customer closes the tab."""
    if not payments.webhook_is_valid(request.body, request.headers.get("X-Razorpay-Signature", "")):
        return HttpResponse(status=400)
    try:
        event = json.loads(request.body)
    except ValueError:
        return HttpResponse(status=400)
    kind = event.get("event", "")
    payload = event.get("payload", {})
    payment = payload.get("payment", {}).get("entity", {})
    order = None
    if payment.get("order_id"):
        order = Order.objects.filter(razorpay_order_id=payment["order_id"]).first()
    if order:
        if kind in ("payment.captured", "order.paid"):
            if payments.mark_paid(order, payment.get("id", "")):
                orders.finalize_online_payment(order)
        elif kind == "payment.failed":
            payments.mark_failed(order, payment.get("error_description", ""))
    return HttpResponse("ok")


def order_success(request, number):
    if request.session.get("last_order") != number:
        return redirect("track")
    order = get_object_or_404(Order, number=number)
    if order.awaiting_payment:
        return redirect("pay", number=number)
    return render(request, "core/order_success.html", {"order": order})


def track(request):
    order = None
    form = TrackForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        order = Order.objects.filter(number=form.cleaned_data["number"], phone=form.cleaned_data["phone"]).first()
        if not order:
            form.add_error(None, "We could not find an order with those details. Please check and try again.")
    steps, reached = order_timeline(order)
    return render(request, "core/track.html", {"form": form, "order": order, "steps": steps, "reached": reached})


# ---------------------------------------------------------------- contact

def contact(request):
    if request.method == "POST":
        form = EnquiryForm(request.POST)
        if form.is_valid():
            enquiry = form.save()
            emails.send_enquiry_received(enquiry)
            messages.success(request, "Thank you. Our team will call you back shortly.")
            return redirect("contact_thanks")
    else:
        initial = {}
        if request.GET.get("topic") in dict(Enquiry.Topic.choices):
            initial["topic"] = request.GET["topic"]
        slug = request.GET.get("product")
        if slug:
            product = Product.objects.filter(slug=slug, is_active=True).first()
            if product:
                initial["product"] = product.pk
        if request.user.is_authenticated:
            initial.update(name=request.user.get_full_name(), email=request.user.email, phone=request.user.profile.phone)
        form = EnquiryForm(initial=initial)
    return render(request, "core/contact.html", {"form": form})


def contact_thanks(request):
    return render(request, "core/thanks.html")


def disclaimer(request):
    return render(request, "core/disclaimer.html")


def privacy(request):
    return render(request, "core/privacy.html")


def not_found(request, exception):
    return render(request, "404.html", status=404)


# -------------------------------------------------------------- newsletter / seo

@require_POST
def newsletter_subscribe(request):
    ajax = _is_ajax(request)
    email = (request.POST.get("email") or "").strip().lower()
    if request.POST.get("website"):  # honeypot: pretend success, store nothing
        ok, message = True, "Thank you! You are subscribed."
    else:
        try:
            validate_email(email)
            sub, created = Subscriber.objects.get_or_create(email=email, defaults={"source": "footer"})
            if not created and not sub.is_active:
                sub.is_active, created = True, True
                sub.save(update_fields=["is_active"])
            if created:
                emails.send_newsletter_welcome(sub)
            ok, message = True, ("Thank you! You are subscribed." if created else "You are already subscribed.")
        except ValidationError:
            ok, message = False, "Please enter a valid email address."
    if ajax:
        return JsonResponse({"ok": ok, "message": message}, status=200 if ok else 400)
    (messages.success if ok else messages.error)(request, message)
    back = request.META.get("HTTP_REFERER", "")
    if back and url_has_allowed_host_and_scheme(back, {request.get_host()}):
        return redirect(back)
    return redirect("home")


def newsletter_unsubscribe(request, token):
    email = read_unsub_token(token)
    if email:
        # create the row if missing so customers who never subscribed (cart reminders) can opt out too
        Subscriber.objects.update_or_create(email=email, defaults={"is_active": False})
    return render(request, "core/unsubscribed.html", {"valid": bool(email)})


def robots_txt(request):
    return render(request, "robots.txt", {"site_url": settings.SITE_URL.rstrip("/")}, content_type="text/plain")
