from datetime import timedelta

from django.conf import settings
from django.core.mail import send_mail
from django.core.management.base import BaseCommand
from django.utils import timezone

from core.models import Batch, Product
from core import sitecfg


class Command(BaseCommand):
    help = "Email the team about low stock and batches close to expiry (run daily). Use --dry-run to only print."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, **options):
        shop = settings.SHOP
        today = timezone.localdate()
        lines = []
        for product in Product.objects.filter(track_inventory=True, is_active=True):
            qty = product.available_qty
            if qty <= shop["low_stock_threshold"]:
                lines.append(f"LOW STOCK: {product.name} {product.pack} has {qty} sellable unit(s) left.")
        soon = today + timedelta(days=shop["expiry_alert_days"])
        for batch in Batch.objects.filter(quantity__gt=0, expiry__lte=soon).select_related("product").order_by("expiry"):
            status = "EXPIRED" if batch.expiry < today else f"expires in {batch.days_left} days"
            lines.append(f"EXPIRY: {batch.product.name} batch {batch.batch_no} ({batch.quantity} units) {status} on {batch.expiry:%d %b %Y}.")
        if not lines:
            self.stdout.write("Stock and expiry look fine.")
            return
        body = "\n".join(lines)
        self.stdout.write(body)
        if not options["dry_run"]:
            send_mail("Credit Lifesciences stock and expiry alert", body, None, sitecfg.site()["order_recipients"], fail_silently=False)
