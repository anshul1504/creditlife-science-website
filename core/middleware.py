"""Small security middleware."""
from django.conf import settings
from django.http import HttpResponseNotFound


def client_ip(request):
    """The caller's address. X-Forwarded-For is only believed when TRUST_PROXY_IP=1 (we sit behind our own proxy);
    the last entry is the one our proxy appended, earlier ones can be forged."""
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
    if settings.TRUST_PROXY_IP and forwarded:
        return forwarded.split(",")[-1].strip()
    return request.META.get("REMOTE_ADDR", "")


class AdminIPAllowlistMiddleware:
    """When ADMIN_ALLOWED_IPS is set, the admin answers 404 to everyone else (it does not even admit it exists)."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        allowed = settings.ADMIN_ALLOWED_IPS
        if allowed and request.path.startswith(f"/{settings.ADMIN_URL}/") and client_ip(request) not in allowed:
            return HttpResponseNotFound()
        return self.get_response(request)


class ContentSecurityPolicyMiddleware:
    """Adds a Content-Security-Policy header. Everything is self-hosted except Razorpay's checkout.

    CSP_MODE (env): "enforce" (default), "report-only" (log violations, block nothing) or "off".
    Admin pages are left alone: Django's admin uses inline scripts.
    """

    def __init__(self, get_response):
        self.get_response = get_response
        rzp = "https://*.razorpay.com"
        self.policy = "; ".join([
            "default-src 'self'",
            f"script-src 'self' {rzp}",
            "style-src 'self' 'unsafe-inline'",   # a few inline style attributes are used for per-product colours
            f"img-src 'self' data: https: {rzp}",
            "font-src 'self' data:",
            f"connect-src 'self' {rzp}",
            f"frame-src 'self' {rzp}",
            f"form-action 'self' {rzp}",
            "frame-ancestors 'self'",
            "base-uri 'self'",
            "object-src 'none'",
        ])

    def __call__(self, request):
        response = self.get_response(request)
        mode = settings.CSP_MODE
        if mode == "off" or request.path.startswith(f"/{settings.ADMIN_URL}/"):
            return response
        header = "Content-Security-Policy-Report-Only" if mode == "report-only" else "Content-Security-Policy"
        response.headers.setdefault(header, self.policy)
        return response


class ReferralCaptureMiddleware:
    """Remember ?ref=CODE so the code can be attached when the visitor signs up."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        from . import loyalty
        loyalty.remember_referrer(request)
        return self.get_response(request)
