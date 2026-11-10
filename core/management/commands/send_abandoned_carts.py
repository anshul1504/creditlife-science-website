from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from core import emails
from core.models import Order, Product, SavedCart, Subscriber


class Command(BaseCommand):
    help = "Remind customers about carts they left 2+ hours ago (once per cart). Run hourly."

    def add_arguments(self, parser):
        parser.add_argument("--after-hours", type=float, default=2)
        parser.add_argument("--max-days", type=int, default=7)
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, **opts):
        now = timezone.now()
        quiet = {e.lower() for e in Subscriber.objects.filter(is_active=False).values_list("email", flat=True)}
        carts = SavedCart.objects.filter(
            reminded_at__isnull=True, updated_at__lte=now - timedelta(hours=opts["after_hours"]),
            updated_at__gte=now - timedelta(days=opts["max_days"]),
        ).select_related("user")
        sent = 0
        for saved in carts:
            user = saved.user
            if not user.email or not user.is_active or user.email.lower() in quiet:
                continue
            if Order.objects.filter(user=user, created_at__gte=saved.updated_at).exists():
                continue  # they bought something since; the cart is stale
            products = {p.slug: p for p in Product.objects.filter(slug__in=saved.data, is_active=True)}
            rows = [
                {"name": products[slug].name, "pack": products[slug].pack, "qty": qty, "line": products[slug].effective_price * qty}
                for slug, qty in saved.data.items()
                if slug in products and products[slug].sellable and products[slug].in_stock
            ]
            if not rows:
                continue
            if not opts["dry_run"]:
                emails.send_abandoned_cart(user, rows)
                SavedCart.objects.filter(pk=saved.pk).update(reminded_at=now)
            sent += 1
        self.stdout.write(self.style.SUCCESS(f"{'Would remind' if opts['dry_run'] else 'Reminded'} {sent} customer(s)."))
