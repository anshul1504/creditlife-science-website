from django.conf import settings
from django.db import migrations


def backfill(apps, schema_editor):
    """Every account needs a Profile (superusers made with createsuperuser before the signal existed had none)."""
    User = apps.get_model(*settings.AUTH_USER_MODEL.split("."))
    Profile = apps.get_model("core", "Profile")
    for user in User.objects.filter(profile__isnull=True):
        Profile.objects.create(user=user)


class Migration(migrations.Migration):
    dependencies = [("core", "0016_business_profile")]
    operations = [migrations.RunPython(backfill, migrations.RunPython.noop)]
