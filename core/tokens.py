from django.contrib.auth import get_user_model
from django.core import signing

SALT = "core.verify-email"
MAX_AGE = 60 * 60 * 24 * 3  # links stay valid for 3 days


def make_verify_token(user):
    return signing.dumps({"uid": user.pk, "email": user.email.lower()}, salt=SALT)


UNSUB_SALT = "core.unsubscribe"


def make_unsub_token(email):
    return signing.dumps(email.lower(), salt=UNSUB_SALT)


def read_unsub_token(token):
    try:
        return signing.loads(token, salt=UNSUB_SALT)
    except signing.BadSignature:
        return None


def read_verify_token(token):
    """Return the user the token was issued for, or None if it is invalid, expired or stale."""
    try:
        data = signing.loads(token, salt=SALT, max_age=MAX_AGE)
    except signing.BadSignature:
        return None
    user = get_user_model().objects.filter(pk=data.get("uid"), email__iexact=data.get("email", "")).first()
    return user
