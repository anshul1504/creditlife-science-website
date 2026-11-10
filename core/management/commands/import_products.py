from django.core.management.base import BaseCommand, CommandError

from core import bulk


class Command(BaseCommand):
    help = "Update prices, GST details and batches from a CSV file. See core/bulk.py for the columns. Use --dry-run first."

    def add_arguments(self, parser):
        parser.add_argument("csv_file")
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, **opts):
        try:
            with open(opts["csv_file"], "rb") as fh:
                changes, errors = bulk.import_products(fh, dry_run=opts["dry_run"])
        except OSError as exc:
            raise CommandError(str(exc)) from exc
        for line in changes:
            self.stdout.write(line)
        if errors:
            for line in errors:
                self.stderr.write(line)
            raise CommandError(f"{len(errors)} problem(s); nothing was saved.")
        self.stdout.write(self.style.SUCCESS(("Dry run OK, " if opts["dry_run"] else "Saved, ") + f"{len(changes)} change(s)."))
