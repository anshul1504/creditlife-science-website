from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from core.models import OTP


class Command(BaseCommand):
    help = "Delete one-time codes older than a day. Run it daily."

    def handle(self, *args, **options):
        deleted, _ = OTP.objects.filter(created_at__lt=timezone.now() - timedelta(days=1)).delete()
        self.stdout.write(self.style.SUCCESS(f"Deleted {deleted} old one-time code(s)."))
