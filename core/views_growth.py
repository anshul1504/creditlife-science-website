"""Bundles, Subscribe & Save, rewards, review votes and product Q&A."""
from datetime import timedelta

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from . import emails, loyalty
from .cart import Cart
from .forms import QuestionForm, SubscribeForm
from .models import Bundle, LoyaltyEntry, Product, Review, ReviewVote, Subscription


# ------------------------------------------------------------------ bundles
def bundles(request):
    items = [b for b in Bundle.objects.filter(is_active=True) if b.valid]
    return render(request, "core/bundles.html", {"bundles": items})


@require_POST
def bundle_add(request, slug):
    bundle = get_object_or_404(Bundle, slug=slug, is_active=True)
    if not bundle.valid:
        messages.error(request, "Sorry, this bundle is not available right now.")
        return redirect("bundles")
    cart = Cart(request)
    for line in bundle.lines:
        cart.add(line.product, line.quantity)
    messages.success(request, f"{bundle.name} added to your cart. You save Rs {bundle.saving}.")
    return redirect("cart")


# ------------------------------------------------------------ subscriptions
@login_required
@require_POST
def subscribe(request, slug):
    product = get_object_or_404(Product, slug=slug, is_active=True)
    if not (product.sellable and product.in_stock):
        messages.error(request, "This product is not available for subscription right now.")
        return redirect(product)
    form = SubscribeForm(request.POST)
    if not form.is_valid():
        messages.error(request, "Please choose how often you want it delivered.")
        return redirect(product)
    address = request.user.addresses.filter(is_default=True).first() or request.user.addresses.first()
    if address is None:
        messages.info(request, "Add a delivery address first, then subscribe again.")
        return redirect("address_new")
    interval = form.cleaned_data["interval_days"]
    existing =Subscription.objects.filter(user=request.user, product=product).exclude(status=Subscription.Status.CANCELLED).first()
    if existing:
        messages.info(request, f"You already subscribe to {product.name}. You can change it here.")
        return redirect("account_subscriptions")
    Subscription.objects.create(
        user=request.user, product=product, quantity=form.cleaned_data["quantity"], interval_days=interval, address=address,
        next_date=timezone.localdate() + timedelta(days=interval),
    )
    messages.success(request, f"Subscribed. Your first delivery of {product.name} is planned for "
                              f"{(timezone.localdate() + timedelta(days=interval)):%d %b}. Cancel any time.")
    return redirect("account_subscriptions")


@login_required
def subscriptions(request):
    subs = request.user.subscriptions.exclude(status=Subscription.Status.CANCELLED).select_related("product", "address")
    return render(request, "accounts/subscriptions.html", {"subs": subs, "discount_pct": settings.SHOP["subscribe_discount_pct"]})


@login_required
@require_POST
def subscription_action(request, pk, action):
    sub = get_object_or_404(Subscription, pk=pk, user=request.user)
    if sub.status == Subscription.Status.CANCELLED:
        return redirect("account_subscriptions")
    if action == "pause":
        sub.status = Subscription.Status.PAUSED
        messages.success(request, "Subscription paused.")
    elif action == "resume":
        sub.status = Subscription.Status.ACTIVE
        sub.next_date = max(sub.next_date, timezone.localdate() + timedelta(days=1))
        messages.success(request, "Subscription resumed.")
    elif action == "skip":
        sub.next_date += timedelta(days=sub.interval_days)
        messages.success(request, f"Skipped. Next delivery: {sub.next_date:%d %b}.")
    elif action == "cancel":
        sub.status = Subscription.Status.CANCELLED
        messages.success(request, "Subscription cancelled.")
    else:
        return redirect("account_subscriptions")
    sub.save()
    return redirect("account_subscriptions")


# ------------------------------------------------------------------ rewards
@login_required
def rewards(request):
    profile = request.user.profile
    link = f"{settings.SITE_URL.rstrip('/')}/?ref={profile.referral_code}"
    return render(request, "accounts/rewards.html", {
        "balance": loyalty.balance(request.user), "entries": LoyaltyEntry.objects.filter(user=request.user)[:50],
        "referral_link": link, "referral_count": request.user.referrals.count(), "shop": settings.SHOP,
    })


# ------------------------------------------------------------ review votes
@require_POST
def review_helpful(request, pk):
    review = get_object_or_404(Review, pk=pk, is_visible=True)
    if not request.user.is_authenticated:
        return JsonResponse({"ok": False, "login": True, "message": "Please sign in to vote."}, status=401)
    if review.user_id == request.user.id:
        return JsonResponse({"ok": False, "message": "You cannot vote on your own review."}, status=400)
    vote, created = ReviewVote.objects.get_or_create(review=review, user=request.user)
    if not created:
        vote.delete()
    return JsonResponse({"ok": True, "voted": created, "count": review.votes.count()})


# -------------------------------------------------------------------- Q&A
@login_required
@require_POST
def ask_question(request, slug):
    product = get_object_or_404(Product, slug=slug, is_active=True)
    if not request.user.profile.email_verified:
        messages.error(request, "Please verify your email address before asking a question.")
        return redirect(product)
    form = QuestionForm(request.POST)
    if form.is_valid():
        q = form.save(commit=False)
        q.product, q.user = product, request.user
        q.save()
        emails.send_question_to_team(q)
        messages.success(request, "Thank you. Our team will answer your question and email you. Answers appear on this page.")
    else:
        messages.error(request, "Please type your question (at least 10 characters).")
    return redirect(product.get_absolute_url() + "#qa")
