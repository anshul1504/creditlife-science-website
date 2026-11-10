"""Inventory screen for staff: what is on hand, what is running low or expiring, and quick stock in / out."""
from datetime import timedelta

from django import forms
from django.conf import settings
from django.contrib import admin, messages
from django.contrib.admin.views.decorators import staff_member_required
from django.db import transaction
from django.db.models import Sum
from django.shortcuts import redirect, render
from django.utils import timezone

from .models import Batch, Product, StockMovement, log_stock


class ReceiveForm(forms.Form):
    product = forms.ModelChoiceField(Product.objects.none())
    batch_no = forms.CharField(max_length=40)
    expiry = forms.DateField(widget=forms.DateInput(attrs={"type": "date"}))
    mfg_date = forms.DateField(required=False, widget=forms.DateInput(attrs={"type": "date"}), label="Manufactured on")
    quantity = forms.IntegerField(min_value=1)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["product"].queryset = Product.objects.filter(track_inventory=True).order_by("name")


class AdjustForm(forms.Form):
    batch = forms.ModelChoiceField(Batch.objects.none())
    change = forms.IntegerField(help_text="Plus adds, minus removes")
    reason = forms.ChoiceField(choices=[(StockMovement.Reason.ADJUSTMENT, "Manual correction"), (StockMovement.Reason.DAMAGED, "Damaged or expired, written off")])
    note = forms.CharField(max_length=200, required=False)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["batch"].queryset = Batch.objects.select_related("product").order_by("product__name", "expiry")


def build_rows():
    shop, today = settings.SHOP, timezone.localdate()
    soon = today + timedelta(days=shop["expiry_alert_days"])
    rows = []
    for p in Product.objects.filter(is_active=True).order_by("name").prefetch_related("batches"):
        batches = [b for b in p.batches.all() if b.quantity > 0]
        on_hand = sum(b.quantity for b in batches)
        next_expiry = min((b.expiry for b in batches), default=None)
        if not p.track_inventory:
            state = "untracked"
        elif on_hand == 0:
            state = "out"
        elif on_hand <= shop["low_stock_threshold"]:
            state = "low"
        elif next_expiry and next_expiry <= soon:
            state = "expiring"
        else:
            state = "ok"
        rows.append({"product": p, "on_hand": on_hand, "batches": batches, "next_expiry": next_expiry, "state": state})
    return rows


@staff_member_required
def inventory(request):
    receive, adjust = ReceiveForm(prefix="r"), AdjustForm(prefix="a")
    if request.method == "POST":
        if "receive" in request.POST:
            receive = ReceiveForm(request.POST, prefix="r")
            if receive.is_valid():
                d = receive.cleaned_data
                with transaction.atomic():
                    batch, _ = Batch.objects.get_or_create(product=d["product"], batch_no=d["batch_no"],
                                                           defaults={"expiry": d["expiry"], "mfg_date": d["mfg_date"], "quantity": 0})
                    batch.quantity += d["quantity"]
                    batch.expiry = d["expiry"]
                    batch.save()
                    log_stock(d["product"], d["quantity"], StockMovement.Reason.RECEIVED, batch=batch, user=request.user, note="Added from the inventory screen")
                    d["product"].refresh_stock_flag()
                messages.success(request, f"Added {d['quantity']} unit(s) of {d['product'].name} to batch {batch.batch_no}.")
                return redirect("inventory")
        elif "adjust" in request.POST:
            adjust = AdjustForm(request.POST, prefix="a")
            if adjust.is_valid():
                d = adjust.cleaned_data
                with transaction.atomic():
                    batch = Batch.objects.select_for_update().get(pk=d["batch"].pk)
                    if batch.quantity + d["change"] < 0:
                        adjust.add_error("change", f"Batch {batch.batch_no} only holds {batch.quantity} unit(s).")
                    else:
                        batch.quantity += d["change"]
                        batch.save(update_fields=["quantity"])
                        log_stock(batch.product, d["change"], d["reason"], batch=batch, user=request.user, note=d["note"])
                        batch.product.refresh_stock_flag()
                        messages.success(request, "Stock updated.")
                        return redirect("inventory")
    rows = build_rows()
    counts = {k: sum(1 for r in rows if r["state"] == k) for k in ("out", "low", "expiring")}
    ctx = {
        **admin.site.each_context(request), "title": "Inventory", "rows": rows, "counts": counts, "receive": receive, "adjust": adjust,
        "movements": StockMovement.objects.select_related("product", "batch", "user")[:25],
        "threshold": settings.SHOP["low_stock_threshold"],
        "units": Batch.objects.aggregate(n=Sum("quantity"))["n"] or 0,
    }
    return render(request, "admin/inventory.html", ctx)
