from django.contrib.auth import get_user_model
from django.contrib.auth.backends import ModelBackend


class EmailBackend(ModelBackend):
    """Authenticate with an email address (case-insensitive) and password."""

    def authenticate(self, request, username=None, password=None, **kwargs):
        email = (username or kwargs.get("email") or "").strip().lower()
        if not email or "@" not in email or password is None:
            return None
        User = get_user_model()
        user = User.objects.filter(email__iexact=email).order_by("id").first()
        if user and user.check_password(password) and self.user_can_authenticate(user):
            return user
        return None
