from datetime import timedelta

from django.conf import settings
from django.core.management.base import BaseCommand
from django.utils import timezone

from core import orders
from core.models import Order


class Command(BaseCommand):
    help = "Cancel online orders that were never paid, and give their coupons back. Run it every 15 minutes (cron / scheduler)."

    def add_arguments(self, parser):
        parser.add_argument("--minutes", type=int, default=settings.UNPAID_ORDER_EXPIRY_MINUTES)

    def handle(self, *args, **options):
        cutoff = timezone.now() - timedelta(minutes=options["minutes"])
        stale = Order.objects.filter(
            payment_method=Order.Payment.ONLINE,
            payment_status__in=[Order.PaymentStatus.PENDING, Order.PaymentStatus.FAILED],
            created_at__lt=cutoff,
        ).exclude(status=Order.Status.CANCELLED)
        count = 0
        for order in stale:
            orders.cancel_order(order)
            count += 1
        self.stdout.write(self.style.SUCCESS(f"Cancelled {count} unpaid order(s) older than {options['minutes']} minutes."))
