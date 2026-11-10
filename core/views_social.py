"""Sign in with Google (OAuth 2.0 authorisation-code flow).

Only an email address that Google itself reports as verified is trusted. The `state` value stops forged callbacks.
The token exchange and the id_token check call Google's endpoints; they could not be run against a live Google
project here, so the tests mock them. Try it once with real credentials before announcing it.
"""
import logging
import secrets
from urllib.parse import urlencode

import requests
from django.conf import settings
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.shortcuts import redirect
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_GET

from . import loyalty
from .views_account import _mark_verified, _sign_in

logger = logging.getLogger(__name__)
User = get_user_model()
AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
TOKENINFO_URL = "https://oauth2.googleapis.com/tokeninfo"
STATE_KEY = "google_state"
NEXT_KEY = "google_next"


def enabled():
    return bool(settings.GOOGLE["client_id"] and settings.GOOGLE["client_secret"])


def _redirect_uri():
    return settings.SITE_URL.rstrip("/") + reverse("google_callback")


@require_GET
def google_start(request):
    if not enabled():
        messages.error(request, "Google sign-in is not available. Please use your email address.")
        return redirect("login")
    state = secrets.token_urlsafe(24)
    request.session[STATE_KEY] = state
    nxt = request.GET.get("next", "")
    if nxt and url_has_allowed_host_and_scheme(nxt, allowed_hosts={request.get_host()}):
        request.session[NEXT_KEY] = nxt
    params = {
        "client_id": settings.GOOGLE["client_id"], "redirect_uri": _redirect_uri(), "response_type": "code",
        "scope": "openid email profile", "state": state, "prompt": "select_account",
    }
    return redirect(f"{AUTH_URL}?{urlencode(params)}")


def _identity_from_code(code):
    """Exchange the code, then ask Google to validate the id_token. Returns the verified claims or raises ValueError."""
    resp = requests.post(TOKEN_URL, data={
        "code": code, "client_id": settings.GOOGLE["client_id"], "client_secret": settings.GOOGLE["client_secret"],
        "redirect_uri": _redirect_uri(), "grant_type": "authorization_code",
    }, timeout=10)
    if resp.status_code != 200 or "id_token" not in resp.json():
        raise ValueError("token exchange failed")
    info = requests.get(TOKENINFO_URL, params={"id_token": resp.json()["id_token"]}, timeout=10)
    if info.status_code != 200:
        raise ValueError("id_token rejected")
    claims = info.json()
    if claims.get("aud") != settings.GOOGLE["client_id"]:
        raise ValueError("token was issued for another app")
    if claims.get("iss") not in ("accounts.google.com", "https://accounts.google.com"):
        raise ValueError("unexpected issuer")
    if str(claims.get("email_verified")).lower() != "true" or not claims.get("email"):
        raise ValueError("Google has not verified this email address")
    return claims


@require_GET
def google_callback(request):
    expected = request.session.pop(STATE_KEY, None)
    nxt = request.session.pop(NEXT_KEY, None)
    if request.GET.get("error") or not expected or not secrets.compare_digest(expected, request.GET.get("state", "")):
        messages.error(request, "Google sign-in was cancelled or could not be verified. Please try again.")
        return redirect("login")
    try:
        claims = _identity_from_code(request.GET.get("code", ""))
    except (ValueError, requests.RequestException):
        logger.exception("Google sign-in failed")
        messages.error(request, "We could not sign you in with Google. Please try again or use your email address.")
        return redirect("login")

    email = claims["email"].lower()
    user = User.objects.filter(email__iexact=email).first()
    created = user is None
    if created:
        user = User.objects.create_user(username=email, email=email, password=None, first_name=(claims.get("given_name") or claims.get("name") or "")[:150])
        loyalty.attach_referrer(request, user)
    elif not user.is_active:
        messages.error(request, "This account is disabled. Please contact support.")
        return redirect("login")
    _mark_verified(user)  # Google has proven the customer owns this address
    _sign_in(request, user)
    messages.success(request, "Welcome to Credit Lifesciences!" if created else "You are signed in.")
    return redirect(nxt or "account")
