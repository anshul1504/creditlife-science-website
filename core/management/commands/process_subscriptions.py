from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from core import emails, orders
from core.models import Subscription

REMIND_DAYS_BEFORE = 2
RETRY_DAYS = 3  # when a delivery cannot be placed (out of stock), try again after this many days


class Command(BaseCommand):
    help = "Place due Subscribe & Save orders and send reminders for upcoming ones. Run once a day."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, **opts):
        today = timezone.localdate()
        placed = skipped = reminded = 0

        for sub in Subscription.objects.filter(status=Subscription.Status.ACTIVE, next_date__lte=today).select_related("user", "product", "address"):
            try:
                if opts["dry_run"]:
                    placed += 1
                    continue
                order = orders.place_subscription_order(sub)
            except (orders.SubscriptionSkipped, orders.StockError) as exc:
                self.stdout.write(f"Skipped {sub}: {exc}")
                sub.next_date = today + timedelta(days=RETRY_DAYS)
                sub.save(update_fields=["next_date"])
                skipped += 1
                continue
            sub.last_order = order
            sub.next_date = today + timedelta(days=sub.interval_days)
            sub.save(update_fields=["last_order", "next_date"])
            emails.send_order_placed(order)
            placed += 1

        upcoming = Subscription.objects.filter(status=Subscription.Status.ACTIVE, next_date=today + timedelta(days=REMIND_DAYS_BEFORE)).select_related("user", "product")
        for sub in upcoming:
            if sub.reminded_for == sub.next_date:
                continue
            if not opts["dry_run"]:
                emails.send_subscription_reminder(sub)
                Subscription.objects.filter(pk=sub.pk).update(reminded_for=sub.next_date)
            reminded += 1

        self.stdout.write(self.style.SUCCESS(f"Placed {placed} order(s), skipped {skipped}, sent {reminded} reminder(s)."))
