from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand

from core.images import write_variants

SKIP = ("logo", "icon", "favicon", "og-", "apple-touch")


class Command(BaseCommand):
    help = "Create responsive WebP versions of the product artwork in static/img (written to an opt/ folder beside each original)."

    def handle(self, *args, **options):
        base = Path(settings.BASE_DIR) / "static" / "img"
        count = 0
        for src in sorted(list(base.glob("*.jpg")) + list(base.glob("*.png")) + list((base / "gallery").glob("*.jpg"))):
            if any(src.name.startswith(prefix) or prefix in src.name for prefix in SKIP):
                continue
            widths = write_variants(src, src.parent / "opt", src.stem)  # next to the original, so the tag finds it
            count += 1
            self.stdout.write(f"{src.relative_to(base)} -> {widths}")
        self.stdout.write(self.style.SUCCESS(f"Optimised {count} image(s). Run collectstatic when deploying."))
