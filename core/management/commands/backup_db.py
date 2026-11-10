import shutil
import subprocess
import zipfile
from datetime import datetime, timedelta
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Back up the database and uploaded media into one timestamped folder, and prune old backups. Run it nightly."

    def add_arguments(self, parser):
        parser.add_argument("--dir", default=str(settings.BASE_DIR / "backups"))
        parser.add_argument("--keep-days", type=int, default=14)

    def handle(self, *args, **options):
        root = Path(options["dir"])
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        target = root / stamp
        target.mkdir(parents=True)
        db = settings.DATABASES["default"]
        if db["ENGINE"].endswith("sqlite3"):
            import sqlite3
            src = sqlite3.connect(db["NAME"])
            dst = sqlite3.connect(target / "db.sqlite3")
            with dst:
                src.backup(dst)  # consistent copy even while the site is running
            dst.close()
            src.close()
        elif "postgresql" in db["ENGINE"]:
            if not shutil.which("pg_dump"):
                raise CommandError("pg_dump is not installed on this machine.")
            env = {"PGPASSWORD": str(db.get("PASSWORD", "")), "PATH": str(Path(shutil.which("pg_dump")).parent)}
            with open(target / "db.sql", "wb") as out:
                subprocess.run(["pg_dump", "-h", db.get("HOST") or "localhost", "-p", str(db.get("PORT") or 5432),
                                "-U", db.get("USER", ""), db["NAME"]], check=True, stdout=out, env=env)
        else:
            raise CommandError(f"Unsupported database engine {db['ENGINE']}.")
        media = Path(settings.MEDIA_ROOT)
        if media.exists():
            with zipfile.ZipFile(target / "media.zip", "w", zipfile.ZIP_DEFLATED) as z:
                for f in media.rglob("*"):
                    if f.is_file():
                        z.write(f, f.relative_to(media))
        cutoff = datetime.now() - timedelta(days=options["keep_days"])
        for old in root.iterdir():
            try:
                if old.is_dir() and datetime.strptime(old.name, "%Y%m%d-%H%M%S") < cutoff:
                    shutil.rmtree(old)
            except ValueError:
                continue
        self.stdout.write(self.style.SUCCESS(f"Backup written to {target}"))
