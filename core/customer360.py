"""Customer 360 for staff: everything about one customer on one page."""
from django.contrib import admin
from django.contrib.auth import get_user_model
from django.db.models import Avg, Sum
from django.shortcuts import get_object_or_404, render

from . import loyalty
from .models import Order, ProductQuestion, ReturnRequest, Review, SavedCart

User = get_user_model()


def customer_360(request, user_id):
    customer = get_object_or_404(User, pk=user_id)
    live = Order.objects.filter(user=customer).exclude(status=Order.Status.CANCELLED)
    agg = live.aggregate(spent=Sum("total"), aov=Avg("total"))
    context = {
        **admin.site.each_context(request),
        "title": f"Customer: {customer.get_full_name() or customer.email}",
        "c": customer,
        "orders": Order.objects.filter(user=customer)[:25],
        "order_count": live.count(),
        "spent": agg["spent"] or 0,
        "aov": round(agg["aov"] or 0),
        "returns": ReturnRequest.objects.filter(order__user=customer)[:10],
        "reviews": Review.objects.filter(user=customer).select_related("product")[:10],
        "questions": ProductQuestion.objects.filter(user=customer).select_related("product")[:10],
        "points": loyalty.balance(customer),
        "subscriptions": customer.subscriptions.select_related("product"),
        "addresses": customer.addresses.all(),
        "saved_cart": SavedCart.objects.filter(user=customer).first(),
        "referred_by": customer.profile.referred_by,
        "referrals": customer.referrals.count(),
    }
    return render(request, "admin/customer360.html", context)
