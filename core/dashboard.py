"""Staff sales dashboard: revenue, orders, average order value, repeat rate, top products, things that need attention."""
from datetime import timedelta

from django.conf import settings
from django.contrib import admin
from django.db.models import Count, F, Sum
from django.db.models.functions import TruncDate
from django.shortcuts import render
from django.utils import timezone

from .models import CouponRedemption, Enquiry, Order, OrderItem, Product, ReturnRequest


def compute(days=30):
    now = timezone.now()
    since = now - timedelta(days=days)
    live = Order.objects.exclude(status=Order.Status.CANCELLED).exclude(
        payment_method=Order.Payment.ONLINE, payment_status__in=[Order.PaymentStatus.PENDING, Order.PaymentStatus.FAILED])
    period = live.filter(created_at__gte=since)
    agg = period.aggregate(revenue=Sum("total"), n=Count("id"))
    revenue, n = agg["revenue"] or 0, agg["n"] or 0

    # repeat rate: of the customers who ordered in the period, how many had also ordered before (or twice in it)
    phones = list(period.order_by().values_list("phone", flat=True).distinct())
    repeaters = live.filter(phone__in=phones).order_by().values("phone").annotate(c=Count("id")).filter(c__gt=1).count()

    per_day = {row["d"]: row for row in period.annotate(d=TruncDate("created_at")).values("d").annotate(rev=Sum("total"), c=Count("id"))}
    series = []
    peak = max([r["rev"] for r in per_day.values()] or [1])
    for i in range(days):
        day = timezone.localtime(since + timedelta(days=i + 1)).date()
        row = per_day.get(day)
        rev = row["rev"] if row else 0
        series.append({"day": day, "rev": rev, "orders": row["c"] if row else 0, "pct": round(rev * 100 / peak) if peak else 0})

    top = (OrderItem.objects.filter(order__in=period).values("product_name")
           .annotate(units=Sum("quantity"), sales=Sum(F("quantity") * F("unit_price"))).order_by("-units")[:6])
    statuses = {row["status"]: row["c"] for row in Order.objects.filter(created_at__gte=since).values("status").annotate(c=Count("id"))}
    payments = {row["payment_method"]: row["c"] for row in period.values("payment_method").annotate(c=Count("id"))}

    low = []
    for p in Product.objects.filter(track_inventory=True, is_active=True):
        if p.available_qty <= settings.SHOP["low_stock_threshold"]:
            low.append(p)

    return {
        "days": days,
        "revenue": revenue, "orders": n, "aov": round(revenue / n) if n else 0,
        "customers": len(phones), "repeat_rate": round(repeaters * 100 / len(phones)) if phones else 0,
        "discounts": CouponRedemption.objects.filter(created_at__gte=since).aggregate(s=Sum("discount"))["s"] or 0,
        "series": series, "top": list(top),
        "statuses": [(label, statuses.get(key, 0)) for key, label in Order.Status.choices],
        "payments": [(label, payments.get(key, 0)) for key, label in Order.Payment.choices],
        "todo": {
            "new_orders": Order.objects.filter(status=Order.Status.PLACED).count(),
            "returns": ReturnRequest.objects.filter(status=ReturnRequest.Status.REQUESTED).count(),
            "enquiries": Enquiry.objects.filter(handled=False).count(),
            "low_stock": low,
        },
    }


def dashboard_view(request):
    try:
        days = min(max(int(request.GET.get("days", 30)), 7), 365)
    except ValueError:
        days = 30
    context = {**admin.site.each_context(request), "title": "Sales dashboard", "d": compute(days)}
    return render(request, "admin/dashboard.html", context)
