from django.contrib.auth.models import Group, Permission
from django.core.management.base import BaseCommand

# role -> {model: actions}. Staff get no access to anything not listed (users, groups, 2FA devices stay superuser-only).
ROLES = {
    "Catalogue manager": {
        "product": "view add change", "productimage": "view add change delete", "batch": "view add change delete",
        "productfaq": "view add change delete", "categorypage": "view change", "review": "view change delete",
        "article": "view add change delete", "productquestion": "view change", "page": "view add change delete",
    },
    "Order desk": {
        "order": "view change", "orderitem": "view", "trackingevent": "view add change", "returnrequest": "view change",
        "enquiry": "view change", "address": "view", "loyaltyentry": "view add", "subscription": "view change",
    },
    "Marketing": {
        "coupon": "view add change", "couponredemption": "view", "announcement": "view add change delete", "banner": "view add change delete", "bundle": "view add change delete", "bundleitem": "view add change delete", "page": "view add change delete",
        "subscriber": "view change", "article": "view add change delete", "categorypage": "view change",
    },
}


class Command(BaseCommand):
    help = "Create (or refresh) the staff roles: Catalogue manager, Order desk, Marketing. Then add staff users to a role in the admin."

    def handle(self, *args, **options):
        for role, models in ROLES.items():
            group, _ = Group.objects.get_or_create(name=role)
            perms = []
            for model, actions in models.items():
                for action in actions.split():
                    code = f"{action}_{model}"
                    perm = Permission.objects.filter(content_type__app_label="core", codename=code).first()
                    if perm is None:
                        self.stderr.write(f"Missing permission {code}")
                        continue
                    perms.append(perm)
            group.permissions.set(perms)
            self.stdout.write(f"{role}: {len(perms)} permissions")
        self.stdout.write(self.style.SUCCESS("Roles ready. Staff need 'Staff status' ticked and one of these groups."))
