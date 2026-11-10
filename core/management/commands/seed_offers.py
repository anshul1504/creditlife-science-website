from django.core.management.base import BaseCommand

from core.models import Announcement, Coupon

EXAMPLES = [
    dict(code="WELCOME10", description="10% off on your first order", kind="percent", value=10, min_order=299, max_discount=100,
         first_order_only=True, per_user_limit=1, public=True),
    dict(code="SAVE50", description="Flat Rs 50 off on orders above Rs 599", kind="flat", value=50, min_order=599, per_user_limit=0, public=True),
    dict(code="FREESHIP", description="Free delivery on any order", kind="flat", value=0, min_order=0, free_shipping=True, per_user_limit=0, public=False),
]


class Command(BaseCommand):
    help = "Create example coupons (inactive unless --activate is given) so the offers can be reviewed in /admin/."

    def add_arguments(self, parser):
        parser.add_argument("--activate", action="store_true", help="Make the examples live straight away.")

    def handle(self, *args, **options):
        for data in EXAMPLES:
            coupon, created = Coupon.objects.get_or_create(code=data["code"], defaults={**data, "active": options["activate"]})
            self.stdout.write(f"{'Created' if created else 'Exists '}: {coupon.code} ({'active' if coupon.active else 'inactive'})")
        if not Announcement.objects.exists():
            Announcement.objects.create(text="Building Trusted Partnerships. Serving Health.", link="/become-a-distributor/", order=1)
            self.stdout.write("Created the default announcement.")
