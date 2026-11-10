from django.conf import settings
from django.core.mail import send_mail
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Send a test email through the configured SMTP account to confirm email delivery works."

    def add_arguments(self, parser):
        parser.add_argument("to", help="Recipient email address")

    def handle(self, *args, **options):
        self.stdout.write(f"Backend: {settings.EMAIL_BACKEND}")
        self.stdout.write(f"Server : {settings.EMAIL_HOST}:{settings.EMAIL_PORT} (SSL={settings.EMAIL_USE_SSL}, TLS={settings.EMAIL_USE_TLS})")
        self.stdout.write(f"From   : {settings.DEFAULT_FROM_EMAIL}")
        try:
            sent = send_mail(
                "Credit Lifesciences: email delivery test",
                "If you are reading this, the store can send email through the configured mailbox.",
                None,
                [options["to"]],
            )
        except Exception as exc:  # show the real reason (auth, firewall, TLS...) instead of a stack trace
            raise CommandError(f"Sending failed: {exc}") from exc
        self.stdout.write(self.style.SUCCESS(f"Sent {sent} message to {options['to']}."))
