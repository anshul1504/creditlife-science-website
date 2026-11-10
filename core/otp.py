"""One-time passcodes sent by email, used for sign-in, sign-up, password reset and email verification.

Codes are never stored in plain text: only an HMAC (keyed with SECRET_KEY) is saved. Every code expires, allows a
small number of wrong guesses, and the number of codes an address can request is limited, so guessing is impractical.
"""
import hashlib
import hmac
import secrets
from datetime import timedelta

from django.conf import settings
from django.utils import timezone

from . import emails, notify
from .models import OTP


class OTPError(Exception):
    def __init__(self, message, code="invalid", retry_after=0):
        super().__init__(message)
        self.message = message
        self.code = code
        self.retry_after = retry_after


def _digest(email, purpose, code):
    return hmac.new(settings.SECRET_KEY.encode(), f"{email}:{purpose}:{code}".encode(), hashlib.sha256).hexdigest()


def mask_email(email):
    local, _, domain = email.partition("@")
    if len(local) <= 2:
        return f"{local[:1]}*@{domain}"
    return f"{local[0]}{'*' * min(len(local) - 2, 6)}{local[-1]}@{domain}"


def mask_phone(phone):
    return f"{phone[:2]}{'*' * 6}{phone[-2:]}" if len(phone) >= 6 else phone


def issue(email, purpose, payload=None, ip=None, channel="email"):
    """Create a fresh code, invalidate older ones and send it by email (or SMS when channel="sms", where `email`
    holds the 10-digit mobile number). Raises OTPError when asked too often."""
    cfg = settings.OTP
    email = email.strip().lower()
    now = timezone.now()

    latest = OTP.objects.filter(email=email, purpose=purpose).first()
    if latest:
        waited = int((now - latest.created_at).total_seconds())
        if waited < cfg["resend_seconds"]:
            wait = cfg["resend_seconds"] - waited
            raise OTPError(f"Please wait {wait} seconds before asking for another code.", "cooldown", wait)
    if OTP.objects.filter(email=email, created_at__gte=now - timedelta(hours=1)).count() >= cfg["max_per_hour"]:
        raise OTPError("You have requested too many codes. Please try again in an hour.", "rate_limited", 3600)

    if channel == "sms" and not (notify.sms_enabled() and settings.NOTIFY["msg91_template_otp"]):
        raise OTPError("Sign-in by mobile number is not available yet. Please use your email address.", "sms_unavailable")
    OTP.objects.filter(email=email, purpose=purpose, used_at__isnull=True).update(used_at=now)
    code = f"{secrets.randbelow(10 ** cfg['length']):0{cfg['length']}d}"
    otp = OTP.objects.create(
        email=email, purpose=purpose, code_hash=_digest(email, purpose, code), payload=payload or {}, ip=ip,
        expires_at=now + timedelta(seconds=cfg["ttl_seconds"]),
    )
    if channel == "sms":
        try:
            notify.send_sms_otp(email, code)
        except Exception as exc:  # noqa: BLE001 - the customer sees a plain message, the log has the detail
            otp.delete()
            raise OTPError("We could not send the SMS right now. Please try again or use your email address.", "sms_failed") from exc
    else:
        emails.send_otp(email, code, purpose, cfg["ttl_seconds"] // 60)
    return otp


def verify(email, purpose, code):
    """Check a code. Returns the OTP row (and burns it) or raises OTPError with a message fit for the customer."""
    cfg = settings.OTP
    email = email.strip().lower()
    code = "".join(ch for ch in str(code or "") if ch.isdigit())
    now = timezone.now()

    otp = OTP.objects.filter(email=email, purpose=purpose, used_at__isnull=True).first()
    if otp is None or otp.expires_at < now:
        raise OTPError("This code has expired. Please ask for a new one.", "expired")
    if otp.attempts >= cfg["max_attempts"]:
        raise OTPError("Too many wrong attempts. Please ask for a new code.", "locked")

    otp.attempts += 1
    if len(code) != cfg["length"] or not hmac.compare_digest(otp.code_hash, _digest(email, purpose, code)):
        otp.save(update_fields=["attempts"])
        left = cfg["max_attempts"] - otp.attempts
        if left <= 0:
            raise OTPError("Too many wrong attempts. Please ask for a new code.", "locked")
        raise OTPError(f"That code is not correct. {left} attempt{'s' if left != 1 else ''} left.", "invalid")

    otp.used_at = now
    otp.save(update_fields=["attempts", "used_at"])
    return otp
