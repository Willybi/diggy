from slowapi import Limiter


def get_real_ip(request) -> str:
    """Use X-Forwarded-For from Nginx, fall back to direct client IP."""
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host


limiter = Limiter(key_func=get_real_ip)
