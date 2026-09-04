from django.conf import settings


def company(request):
    return {
        "COMPANY_NAME": settings.COMPANY_NAME,
        "COMPANY_MOTTO": settings.COMPANY_MOTTO,
        "COMPANY_PHONE": settings.COMPANY_PHONE,
        "COMPANY_ADDRESS": settings.COMPANY_ADDRESS,
        "remote_mode": _is_remote(request),
    }


def _is_remote(request):
    """True when a request arrives via the Cloudflare tunnel (public HTTPS),
    rather than on the shop machine's local network."""
    try:
        host = request.get_host()
    except Exception:
        return False
    proto = request.META.get("HTTP_X_FORWARDED_PROTO", "")
    return proto == "https" and (".meatmagic.org" in host or host in ("meatmagic.org",))
