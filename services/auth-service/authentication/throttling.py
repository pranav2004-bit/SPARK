from rest_framework.throttling import SimpleRateThrottle


class LoginAttemptThrottle(SimpleRateThrottle):
    """
    Per-account login throttle — independent of nginx's per-IP auth_zone.

    nginx's auth_zone (gateway/nginx.conf, nginx.dev.conf) keys on client IP,
    so it can't stop an attacker who spreads guesses against ONE account
    across many source IPs. This throttle keys on the identifier actually
    submitted (student_id or email) instead, so repeated attempts against a
    single account are limited regardless of where they come from.

    Deliberately separate from IP-based throttling rather than a replacement
    for it — the two protect against different attack shapes (one attacker
    hammering many accounts vs. many attackers/IPs hammering one account).
    """

    scope = "login"

    def get_cache_key(self, request, view):
        identifier = (
            request.data.get("student_id") or request.data.get("email") or ""
        )
        identifier = identifier.strip().lower()
        if not identifier:
            # No identifier submitted — serializer validation will reject the
            # request anyway; don't throttle on an empty key, which would
            # create one bucket shared by every malformed request.
            return None
        return self.cache_format % {"scope": self.scope, "ident": identifier}
