"""Category landing pages, blog and the self-serve returns portal."""
from datetime import timedelta

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Sum
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_http_methods

from . import emails
from .forms import ReturnForm
from .models import Article, CategoryPage, Order, OrderItem, Product, ReturnRequest


def category(request, key):
    page = get_object_or_404(CategoryPage, category=key)
    products = Product.objects.filter(is_active=True, category=key)
    others = CategoryPage.objects.exclude(pk=page.pk)
    return render(request, "core/category.html", {"page": page, "products": products, "others": others})


def blog_list(request):
    qs = Article.objects.all() if request.user.is_staff else Article.objects.filter(is_published=True, published_at__lte=timezone.now())
    page = Paginator(qs, 9).get_page(request.GET.get("page"))
    return render(request, "core/blog_list.html", {"page_obj": page})


def article(request, slug):
    art = get_object_or_404(Article, slug=slug)
    if not (art.is_published and art.published_at <= timezone.now()) and not request.user.is_staff:
        raise Http404
    more = Article.objects.filter(is_published=True, published_at__lte=timezone.now()).exclude(pk=art.pk)[:3]
    products = Product.objects.filter(is_active=True)[:3]
    return render(request, "core/article.html", {"article": art, "more": more, "products": products})


# ------------------------------------------------------------------ returns
def returnable_items(order):
    """Items of a delivered order that can still be returned, with how many units are left to claim."""
    if order.status != Order.Status.DELIVERED or not order.delivered_at:
        return []
    if timezone.now() > order.delivered_at + timedelta(days=settings.RETURN_WINDOW_DAYS):
        return []
    claimed = {
        row["item"]: row["n"]
        for row in ReturnRequest.objects.filter(order=order).exclude(status=ReturnRequest.Status.REJECTED).values("item").annotate(n=Sum("quantity"))
    }
    out = []
    for item in order.items.all():
        left = item.quantity - claimed.get(item.pk, 0)
        if left > 0:
            out.append((item, left))
    return out


@login_required
@require_http_methods(["GET", "POST"])
def return_new(request, number, item_id):
    order = get_object_or_404(Order, number=number, user=request.user)
    options = {item.pk: (item, left) for item, left in returnable_items(order)}
    if item_id not in options:
        messages.error(request, "This item cannot be returned any more. Damage reports are open for %d days after delivery." % settings.RETURN_WINDOW_DAYS)
        return redirect("account_order", number=number)
    item, left = options[item_id]
    form = ReturnForm(request.POST or None, request.FILES or None, max_qty=left)
    if request.method == "POST" and form.is_valid():
        req = form.save(commit=False)
        req.order, req.item = order, get_object_or_404(OrderItem, pk=item_id, order=order)
        req.reason = ReturnRequest.Reason.DAMAGED  # replacements are for damaged goods only
        req.save()
        emails.send_return_received(req)
        messages.success(request, "We received your request %s. Our team will review it and email you within 1 working day." % req.reference)
        return redirect("account_return", reference=req.reference)
    return render(request, "accounts/return_form.html", {"order": order, "item": item, "left": left, "form": form})


@login_required
def returns_list(request):
    rows = ReturnRequest.objects.filter(order__user=request.user).select_related("order", "item")
    return render(request, "accounts/returns.html", {"returns": rows})


@login_required
def return_detail(request, reference):
    req = get_object_or_404(ReturnRequest.objects.select_related("order", "item"), reference=reference, order__user=request.user)
    return render(request, "accounts/return_detail.html", {"req": req, "events": req.events.all()})


@login_required
@require_http_methods(["POST"])
def return_withdraw(request, reference):
    req = get_object_or_404(ReturnRequest, reference=reference, order__user=request.user)
    if req.can_withdraw:
        req.status = ReturnRequest.Status.WITHDRAWN
        req.staff_note = "Withdrawn by the customer"
        req.save()
        messages.success(request, "Your return request was withdrawn.")
    else:
        messages.error(request, "This request can no longer be withdrawn. Please contact us.")
    return redirect("account_return", reference=reference)


def cms_page(request, slug):
    from .models import Page
    page = get_object_or_404(Page, slug=slug)
    if not page.is_published and not request.user.is_staff:
        raise Http404
    return render(request, "core/cms_page.html", {"page": page})
