import time
from datetime import timedelta

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.core.management.base import BaseCommand
from django.utils import timezone

from core.models import EmailJob

BACKOFF = [60, 300, 1800, 7200]  # seconds to wait before attempts 2, 3, 4, 5
MAX_ATTEMPTS = len(BACKOFF) + 1


def process_batch(limit=25):
    """Send due emails and return how many went out. Safe with several workers: a job is claimed with one UPDATE."""
    sent = 0
    for job in EmailJob.objects.filter(status=EmailJob.Status.PENDING, run_after__lte=timezone.now())[:limit]:
        claimed = EmailJob.objects.filter(pk=job.pk, status=EmailJob.Status.PENDING, attempts=job.attempts).update(attempts=job.attempts + 1)
        if not claimed:
            continue  # another worker took it
        try:
            msg = EmailMultiAlternatives(job.subject, job.text, settings.DEFAULT_FROM_EMAIL, job.to, reply_to=job.reply_to)
            if job.html:
                msg.attach_alternative(job.html, "text/html")
            msg.send()
        except Exception as exc:  # noqa: BLE001 - record the problem and retry later
            attempts = job.attempts + 1
            if attempts >= MAX_ATTEMPTS:
                EmailJob.objects.filter(pk=job.pk).update(status=EmailJob.Status.FAILED, last_error=str(exc)[:300])
            else:
                EmailJob.objects.filter(pk=job.pk).update(
                    run_after=timezone.now() + timedelta(seconds=BACKOFF[attempts - 1]), last_error=str(exc)[:300])
        else:
            EmailJob.objects.filter(pk=job.pk).update(status=EmailJob.Status.SENT, sent_at=timezone.now())
            sent += 1
    return sent


class Command(BaseCommand):
    help = "Background worker: sends queued emails (EMAIL_QUEUE=1) with retries. Keep it running (systemd / supervisor / docker)."

    def add_arguments(self, parser):
        parser.add_argument("--once", action="store_true", help="process what is due and exit")
        parser.add_argument("--interval", type=float, default=2.0)

    def handle(self, *args, **opts):
        if opts["once"]:
            self.stdout.write(f"Sent {process_batch()} email(s).")
            return
        self.stdout.write("Worker started. Ctrl+C to stop.")
        while True:
            if not process_batch():
                time.sleep(opts["interval"])
