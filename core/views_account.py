import time

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import get_user_model, login
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.http import JsonResponse
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import LoginView, PasswordChangeView, PasswordResetConfirmView, PasswordResetView
from django.core.cache import cache
from django.core.paginator import Paginator
from django.db.models import Q, Sum
from django.utils import timezone
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse, reverse_lazy
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from . import emails, loyalty, notify, orders as order_service, otp
from .cart import Cart
from .forms import (
    BusinessForm,
    AddressForm, EmailAuthenticationForm, ProfileForm, SignupDetailsForm,
    StyledPasswordChangeForm, StyledPasswordResetForm, StyledSetPasswordForm,
)
from .models import OTP, Address, Order, Profile, ReturnRequest, Wishlist
from .tokens import read_verify_token
from .views import order_timeline
from .views_content import returnable_items
from . import sitecfg


# --------------------------------------------------------- sign up / in
User = get_user_model()


def _form_errors(form):
    """{'field': ['message', ...], '__all__': [...]} for the JSON used by the sign-in popup."""
    return {k: [e["message"] for e in v] for k, v in form.errors.get_json_data().items()}


def _popup_next(request, default=None):
    target = request.POST.get("next") or ""
    if target and url_has_allowed_host_and_scheme(target, allowed_hosts={request.get_host()}, require_https=request.is_secure()):
        return target
    return default or reverse("home")


def _client_ip(request):
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
    return (forwarded.split(",")[0].strip() or request.META.get("REMOTE_ADDR") or "") or None


def _throttled(request, bucket, limit, seconds=3600):
    """True when this IP has already used up `limit` calls of `bucket` in the window."""
    key = f"throttle:{bucket}:{_client_ip(request)}"
    count = cache.get(key, 0)
    if count >= limit:
        return True
    cache.set(key, count + 1, seconds)
    return False


def _fail(message, status=400, **extra):
    return JsonResponse({"ok": False, "message": message, **extra}, status=status)


def _clean_email(request):
    value = (request.POST.get("email") or "").strip().lower()
    try:
        validate_email(value)
    except ValidationError:
        return None
    return value


def _mark_verified(user):
    """An OTP proves the customer controls the email address."""
    profile = user.profile
    if profile.email_verified:
        return False
    profile.email_verified = True
    profile.save(update_fields=["email_verified"])
    Order.objects.filter(user__isnull=True, email__iexact=user.email).update(user=user)  # attach earlier guest orders
    emails.send_welcome(user)
    return True


def _sign_in(request, user, remember=True):
    login(request, user, backend="core.auth_backends.EmailBackend")
    if not remember:
        request.session.set_expiry(0)  # session ends when the browser closes


@require_POST
def ajax_login(request):
    """Email + password sign-in used by the "use password instead" step."""
    form = EmailAuthenticationForm(request, data=request.POST)
    if not form.is_valid():
        return JsonResponse({"ok": False, "errors": _form_errors(form)}, status=400)
    _sign_in(request, form.get_user(), form.cleaned_data.get("remember"))
    return JsonResponse({"ok": True, "redirect": _popup_next(request)})


@require_POST
def otp_identify(request):
    """Step one of the popup: does this email already have an account?"""
    if _throttled(request, "identify", 40):
        return _fail("Too many attempts. Please try again in a while.", 429)
    mobile = clean_mobile(request.POST.get("email", ""))
    if mobile:
        owner = verified_phone_owner(mobile)
        return JsonResponse({"ok": True, "kind": "phone", "phone": mobile, "exists": bool(owner), "masked": otp.mask_phone(mobile),
                             "sms": notify.sms_enabled()})
    email = _clean_email(request)
    if not email:
        return _fail("Please enter a valid email address or mobile number.", errors={"email": ["Please enter a valid email address or mobile number."]})
    user = User.objects.filter(email__iexact=email).first()
    return JsonResponse({
        "ok": True, "exists": bool(user), "has_password": bool(user and user.has_usable_password()),
        "masked": otp.mask_email(email), "first_name": user.first_name if user else "",
    })


@require_POST
def otp_request(request):
    """Email a one-time code for sign-in, sign-up, password reset or email verification."""
    if _throttled(request, "otp", 25):
        return _fail("Too many attempts. Please try again in a while.", 429)
    purpose = request.POST.get("purpose", "")
    if purpose not in OTP.Purpose.values:
        return _fail("Unknown request.")
    if purpose in PHONE_PURPOSES:
        return phone_otp_request(request, purpose)
    email = _clean_email(request)
    if purpose == "verify":
        if not request.user.is_authenticated:
            return _fail("Please sign in first.", 401)
        if request.user.profile.email_verified:
            return _fail("Your email is already verified.", code="already_verified")
        email = request.user.email.lower()
    if not email:
        return _fail("Please enter a valid email address.", errors={"email": ["Please enter a valid email address."]})

    user = User.objects.filter(email__iexact=email).first()
    payload = {}
    send = True
    if purpose == "login" and not user:
        return _fail("We could not find an account with this email. Create one instead.", code="no_account")
    if purpose == "signup":
        if user:
            return _fail("An account with this email already exists. Please sign in instead.", code="exists")
        form = SignupDetailsForm(request.POST)
        if not form.is_valid():
            return JsonResponse({"ok": False, "errors": _form_errors(form), "message": "Please check your details."}, status=400)
        payload = {"name": form.cleaned_data["name"], "phone": form.cleaned_data["phone"]}
    if purpose == "reset" and not user:
        send = False  # do not reveal which emails have accounts; the code simply never arrives

    cfg = settings.OTP
    if send:
        try:
            otp.issue(email, purpose, payload=payload, ip=_client_ip(request))
        except otp.OTPError as exc:
            status = 429 if exc.code in ("cooldown", "rate_limited") else 400
            return _fail(exc.message, status, code=exc.code, retry_after=exc.retry_after, masked=otp.mask_email(email))
    return JsonResponse({
        "ok": True, "masked": otp.mask_email(email), "cooldown": cfg["resend_seconds"],
        "length": cfg["length"], "ttl_minutes": cfg["ttl_seconds"] // 60,
    })


@require_POST
def otp_verify(request):
    """Check the code and finish the job: sign in, create the account, reset the password or verify the email."""
    if _throttled(request, "otp-verify", 60):
        return _fail("Too many attempts. Please try again in a while.", 429)
    purpose = request.POST.get("purpose", "")
    if purpose not in OTP.Purpose.values:
        return _fail("Unknown request.")
    if purpose in PHONE_PURPOSES:
        return phone_otp_verify(request, purpose)
    email = request.user.email.lower() if (purpose == "verify" and request.user.is_authenticated) else _clean_email(request)
    if not email:
        return _fail("Please enter a valid email address.")
    code = request.POST.get("code", "")

    password_form = None
    if purpose == "reset":
        user = User.objects.filter(email__iexact=email).first()
        if user:  # check the new password first so a typo does not burn the code
            password_form = StyledSetPasswordForm(user, {"new_password1": request.POST.get("new_password1", ""), "new_password2": request.POST.get("new_password2", "")})
            if not password_form.is_valid():
                return JsonResponse({"ok": False, "errors": _form_errors(password_form), "message": "Please check your new password."}, status=400)

    try:
        record = otp.verify(email, purpose, code)
    except otp.OTPError as exc:
        return _fail(exc.message, 400, code=exc.code)

    nxt = _popup_next(request)
    if purpose == "login":
        user = User.objects.filter(email__iexact=email).first()
        if not user or not user.is_active:
            return _fail("We could not sign you in. Please contact support.", 400)
        _mark_verified(user)
        _sign_in(request, user)
        return JsonResponse({"ok": True, "redirect": nxt})

    if purpose == "signup":
        if User.objects.filter(email__iexact=email).exists():
            return _fail("An account with this email already exists. Please sign in instead.", 400, code="exists")
        user = User.objects.create_user(username=email, email=email, password=None, first_name=record.payload.get("name", ""))
        loyalty.attach_referrer(request, user)
        user.profile.phone = record.payload.get("phone", "")
        user.profile.save(update_fields=["phone"])
        _mark_verified(user)
        _sign_in(request, user)
        return JsonResponse({"ok": True, "redirect": nxt, "welcome": True})

    if purpose == "reset":
        user = User.objects.filter(email__iexact=email).first()
        if not user or password_form is None:
            return _fail("This code has expired. Please ask for a new one.", 400, code="expired")
        user = password_form.save()  # the instance that now carries the NEW password hash; the session hash is built from it
        _mark_verified(user)
        emails.send_password_changed(user)
        _sign_in(request, user)
        return JsonResponse({"ok": True, "redirect": nxt})

    # purpose == "verify": the signed-in customer confirms their email address
    _mark_verified(request.user)
    return JsonResponse({"ok": True, "redirect": nxt if request.POST.get("next") else reverse("account")})


def register(request):
    """Sign-up page: the same popup flow, shown as a page for direct visits."""
    if request.user.is_authenticated:
        return redirect("account")
    return render(request, "accounts/register.html", {"flow_next": request.GET.get("next") or reverse("account")})


class EmailLoginView(LoginView):
    template_name = "accounts/login.html"
    authentication_form = EmailAuthenticationForm
    redirect_authenticated_user = True

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["flow_next"] = self.request.GET.get("next") or reverse("account")
        return context

    def form_valid(self, form):
        response = super().form_valid(form)
        if not form.cleaned_data.get("remember"):
            self.request.session.set_expiry(0)  # session ends when the browser closes
        return response


RESEND_COOLDOWN = 60


def _cooldown_left(request):
    return max(0, RESEND_COOLDOWN - int(time.time() - request.session.get("verify_sent_at", 0)))


def verify_email(request, token):
    user = read_verify_token(token)
    if not user:
        return render(request, "accounts/verify_result.html", {"ok": False}, status=400)
    first_time = _mark_verified(user)
    return render(request, "accounts/verify_result.html", {"ok": True, "first_time": first_time, "verified_user": user})


@login_required
def verify_pending(request):
    if request.user.profile.email_verified:
        return redirect("account")
    return render(request, "accounts/verify_pending.html", {"cooldown": _cooldown_left(request)})


@login_required
@require_POST
def resend_verification(request):
    if request.user.profile.email_verified:
        messages.info(request, "Your email is already verified.")
        return redirect("account")
    if _cooldown_left(request):
        messages.info(request, "A verification email was sent a moment ago. Please check your inbox and spam folder.")
    else:
        emails.send_verification(request.user)
        request.session["verify_sent_at"] = time.time()
        messages.success(request, f"A new verification link is on its way to {request.user.email}.")
    return redirect("account_verify_pending")


# ------------------------------------------------- password reset/change

class ResetView(PasswordResetView):
    """The page runs the OTP reset flow; a POST (link by email) still works for anyone without JavaScript."""
    form_class = StyledPasswordResetForm
    template_name = "accounts/password_reset_form.html"
    email_template_name = "emails/password_reset.txt"
    html_email_template_name = "emails/password_reset.html"
    subject_template_name = "emails/password_reset_subject.txt"
    success_url = reverse_lazy("password_reset_done")
    from_email = settings.DEFAULT_FROM_EMAIL
    extra_email_context = {"SITE": sitecfg.site()}


class ResetConfirmView(PasswordResetConfirmView):
    form_class = StyledSetPasswordForm
    template_name = "accounts/password_reset_confirm.html"
    success_url = reverse_lazy("password_reset_complete")

    def form_valid(self, form):
        response = super().form_valid(form)
        emails.send_password_changed(self.user)
        return response


class ChangePasswordView(PasswordChangeView):
    form_class = StyledPasswordChangeForm
    template_name = "accounts/password_change_form.html"
    success_url = reverse_lazy("password_change_done")

    def get_form_class(self):
        # Customers who signed up with an email code have no password yet, so there is no "current password" to ask for.
        return StyledPasswordChangeForm if self.request.user.has_usable_password() else StyledSetPasswordForm

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["setting_first_password"] = not self.request.user.has_usable_password()
        return context

    def form_valid(self, form):
        response = super().form_valid(form)
        emails.send_password_changed(self.request.user)
        return response


# ---------------------------------------------------------------- account

@login_required
def account_home(request):
    user = request.user
    orders = user.orders.all()
    live = orders.exclude(status__in=[Order.Status.CANCELLED, Order.Status.DELIVERED])
    spent = orders.exclude(status=Order.Status.CANCELLED).exclude(payment_status__in=[Order.PaymentStatus.PENDING, Order.PaymentStatus.FAILED, Order.PaymentStatus.REFUNDED]).aggregate(n=Sum("total"))["n"] or 0
    steps = [
        ("Verify your email", user.profile.email_verified, reverse("account_verify_pending")),
        ("Add a mobile number", bool(user.profile.phone), reverse("account_profile")),
        ("Save a delivery address", user.addresses.exists(), reverse("address_new")),
        ("Verify your business", user.profile.kyc_approved, reverse("account_business")),
    ]
    done = sum(1 for _, ok, _ in steps if ok)
    return render(
        request,
        "accounts/home.html",
        {
            "recent_orders": orders[:3],
            "order_count": orders.count(),
            "live_orders": live.count(),
            "spent": spent,
            "open_returns": ReturnRequest.objects.filter(order__user=user).exclude(status__in=["resolved", "rejected", "withdrawn"]).count(),
            "address": user.addresses.filter(is_default=True).first(),
            "wishlist_count": user.wishlist.count(),
            "steps": steps,
            "progress": int(done * 100 / len(steps)),
            "display_name": user.first_name or user.email.split("@")[0],
        },
    )


@login_required
def business(request):
    profile = request.user.profile
    form = BusinessForm(request.POST or None, request.FILES or None, instance=profile)
    if request.method == "POST" and form.is_valid():
        prof = form.save(commit=False)
        prof.kyc_status = Profile.Kyc.PENDING
        prof.kyc_note = ""
        prof.kyc_submitted_at = timezone.now()
        prof.save()
        emails.send_kyc_submitted(request.user)
        messages.success(request, "Thank you. We received your business details and will review them within 1 working day.")
        return redirect("account_business")
    return render(request, "accounts/business.html", {"form": form, "profile": profile})


@login_required
def profile(request):
    user = request.user
    form = ProfileForm(request.POST or None, initial={"name": user.get_full_name(), "phone": user.profile.phone})
    if request.method == "POST" and form.is_valid():
        user.first_name = form.cleaned_data["name"]
        user.save(update_fields=["first_name"])
        if user.profile.phone != form.cleaned_data["phone"]:
            user.profile.phone_verified = False  # a different number has not been proven yet
        user.profile.phone = form.cleaned_data["phone"]
        user.profile.save(update_fields=["phone", "phone_verified"])
        messages.success(request, "Your profile has been updated.")
        return redirect("account_profile")
    return render(request, "accounts/profile.html", {"form": form})


@login_required
def orders(request):
    qs = request.user.orders.prefetch_related("items")
    status, q = request.GET.get("status", ""), request.GET.get("q", "").strip()
    if status in dict(Order.Status.choices):
        qs = qs.filter(status=status)
    if q:
        qs = qs.filter(Q(number__icontains=q) | Q(items__product_name__icontains=q)).distinct()
    page = Paginator(qs, 10).get_page(request.GET.get("page"))
    return render(request, "accounts/orders.html", {"orders": page, "page": page, "status": status, "q": q, "statuses": Order.Status.choices})


@login_required
def order_detail(request, number):
    order = get_object_or_404(Order, number=number, user=request.user)
    steps, reached = order_timeline(order)
    return render(request, "accounts/order_detail.html", {
        "order": order, "steps": steps, "reached": reached,
        "returnable": returnable_items(order), "returns": order.returns.select_related("item"),
    })


@login_required
@require_POST
def order_cancel(request, number):
    order = get_object_or_404(Order, number=number, user=request.user)
    if order.can_cancel:
        outcome = order_service.cancel_order(order)
        if outcome == "refunded":
            messages.success(request, f"Order {order.number} has been cancelled and your refund of Rs {order.total} has been started.")
        elif outcome == "refund_failed":
            messages.warning(request, f"Order {order.number} has been cancelled. Your refund could not start automatically, so our team will process it manually and email you.")
        else:
            messages.success(request, f"Order {order.number} has been cancelled.")
    else:
        messages.error(request, "This order can no longer be cancelled online. Please call us for help.")
    return redirect("account_order", number=number)


@login_required
@require_POST
def order_reorder(request, number):
    order = get_object_or_404(Order, number=number, user=request.user)
    cart = Cart(request)
    added = 0
    for item in order.items.select_related("product"):
        product = item.product
        if product and product.sellable and product.in_stock:
            cart.add(product, item.quantity)
            added += 1
    if added:
        messages.success(request, "The items from this order are back in your cart.")
        return redirect("cart")
    messages.error(request, "Sorry, none of the items in this order are available right now.")
    return redirect("account_order", number=number)


@login_required
def addresses(request):
    return render(request, "accounts/addresses.html", {"addresses": request.user.addresses.all()})


@login_required
def address_edit(request, pk=None):
    instance = get_object_or_404(Address, pk=pk, user=request.user) if pk else None
    initial = {"name": request.user.get_full_name(), "phone": request.user.profile.phone} if not instance else None
    form = AddressForm(request.POST or None, instance=instance, initial=initial)
    if request.method == "POST" and form.is_valid():
        address = form.save(commit=False)
        address.user = request.user
        address.save()
        messages.success(request, "Address saved.")
        next_url = request.POST.get("next") or ""
        if next_url and url_has_allowed_host_and_scheme(next_url, {request.get_host()}):
            return redirect(next_url)
        return redirect("account_addresses")
    return render(request, "accounts/address_form.html", {"form": form, "editing": bool(instance)})


@login_required
@require_POST
def address_delete(request, pk):
    get_object_or_404(Address, pk=pk, user=request.user).delete()
    messages.success(request, "Address removed.")
    return redirect("account_addresses")


@login_required
@require_POST
def address_default(request, pk):
    address = get_object_or_404(Address, pk=pk, user=request.user)
    address.is_default = True
    address.save()
    messages.success(request, "Default address updated.")
    return redirect("account_addresses")


@login_required
def wishlist(request):
    items = Wishlist.objects.filter(user=request.user, product__is_active=True).select_related("product")
    return render(request, "accounts/wishlist.html", {"products": [i.product for i in items]})


# ------------------------------------------------------- mobile number codes
PHONE_PURPOSES = ("plogin", "pverify")


def clean_mobile(raw):
    """10-digit Indian mobile number from what the customer typed, or None."""
    digits = "".join(ch for ch in str(raw or "") if ch.isdigit())
    if len(digits) == 12 and digits.startswith("91"):
        digits = digits[2:]
    return digits if len(digits) == 10 and digits[0] in "6789" else None


def verified_phone_owner(phone):
    """The one account that has proven it owns this number, or None (also None if two accounts claim it)."""
    owners = list(Profile.objects.filter(phone=phone, phone_verified=True).select_related("user")[:2])
    return owners[0].user if len(owners) == 1 else None


def phone_otp_request(request, purpose):
    if _throttled(request, "otp-phone", 15):
        return _fail("Too many attempts. Please try again in a while.", 429)
    if purpose == "pverify":
        if not request.user.is_authenticated:
            return _fail("Please sign in first.", 401)
        phone = clean_mobile(request.user.profile.phone)
        if not phone:
            return _fail("Add a valid mobile number to your profile first.")
        if request.user.profile.phone_verified:
            return _fail("Your mobile number is already verified.", code="already_verified")
        other = Profile.objects.filter(phone=phone, phone_verified=True).exclude(user=request.user).exists()
        if other:
            return _fail("This number is already verified on another account.")
    else:
        phone = clean_mobile(request.POST.get("email", ""))
        if not phone:
            return _fail("Please enter a valid 10-digit mobile number.")
        if not verified_phone_owner(phone):
            return _fail("No account is linked to this verified mobile number. Sign in with your email, then verify your number in Profile.", code="no_account_phone")
    try:
        otp.issue(phone, purpose, ip=_client_ip(request), channel="sms")
    except otp.OTPError as exc:
        status = 429 if exc.code in ("cooldown", "rate_limited") else 400
        return _fail(exc.message, status, code=exc.code, retry_after=exc.retry_after, masked=otp.mask_phone(phone))
    cfg = settings.OTP
    return JsonResponse({"ok": True, "masked": otp.mask_phone(phone), "cooldown": cfg["resend_seconds"], "length": cfg["length"], "ttl_minutes": cfg["ttl_seconds"] // 60})


def phone_otp_verify(request, purpose):
    if _throttled(request, "otp-phone-verify", 40):
        return _fail("Too many attempts. Please try again in a while.", 429)
    if purpose == "pverify":
        if not request.user.is_authenticated:
            return _fail("Please sign in first.", 401)
        phone = clean_mobile(request.user.profile.phone)
    else:
        phone = clean_mobile(request.POST.get("email", ""))
    if not phone:
        return _fail("Please enter a valid mobile number.")
    try:
        otp.verify(phone, purpose, request.POST.get("code", ""))
    except otp.OTPError as exc:
        return _fail(exc.message, 400, code=exc.code)
    if purpose == "pverify":
        if Profile.objects.filter(phone=phone, phone_verified=True).exclude(user=request.user).exists():
            return _fail("This number is already verified on another account.")
        request.user.profile.phone_verified = True
        request.user.profile.save(update_fields=["phone_verified"])
        return JsonResponse({"ok": True, "redirect": reverse("account_profile")})
    owner = verified_phone_owner(phone)
    if owner is None or not owner.is_active:
        return _fail("We could not sign you in. Please use your email address.")
    _sign_in(request, owner)
    return JsonResponse({"ok": True, "redirect": _popup_next(request)})


@login_required
def verify_phone(request):
    """Page for verifying the mobile number on the profile (the code is entered with a plain form)."""
    profile = request.user.profile
    phone = clean_mobile(profile.phone)
    stage = "send"
    if request.method == "POST" and phone and not profile.phone_verified:
        if request.POST.get("code"):
            try:
                otp.verify(phone, "pverify", request.POST["code"])
            except otp.OTPError as exc:
                messages.error(request, exc.message)
                stage = "enter"
            else:
                if Profile.objects.filter(phone=phone, phone_verified=True).exclude(user=request.user).exists():
                    messages.error(request, "This number is already verified on another account.")
                else:
                    profile.phone_verified = True
                    profile.save(update_fields=["phone_verified"])
                    messages.success(request, "Your mobile number is verified. You can now sign in with it.")
                    return redirect("account_profile")
        else:
            try:
                otp.issue(phone, "pverify", ip=_client_ip(request), channel="sms")
                messages.success(request, f"We sent a code to {otp.mask_phone(phone)}.")
                stage = "enter"
            except otp.OTPError as exc:
                messages.error(request, exc.message)
    return render(request, "accounts/verify_phone.html", {"phone": phone, "verified": profile.phone_verified, "stage": stage, "sms_ready": notify.sms_enabled()})
