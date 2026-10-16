"""Rate-accounting source only. Never mutates ASGI peer, identity or development guards."""

from ipaddress import ip_address


def auth_source(settings, request):
    peer = request.client.host if request.client else "unknown"
    try:
        peer = str(ip_address(peer))
    except ValueError:
        return peer
    trusted = settings.auth_trusted_proxy_ips.split(",") if settings.auth_trusted_proxy_ips else []
    if peer not in trusted:
        return peer
    # Duplicate/list/invalid values must not provide fresh arbitrary rate identities.
    values = request.headers.getlist("x-local-shop-client-ip")
    if len(values) != 1:
        return peer
    try:
        value = ip_address(values[0])
        if "%" in values[0]:
            return peer
        return str(value)
    except ValueError:
        return peer
