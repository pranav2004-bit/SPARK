from rest_framework.throttling import AnonRateThrottle, SimpleRateThrottle

from core.throttling_resilience import ResilientThrottleMixin


class TokenRefreshThrottle(ResilientThrottleMixin, AnonRateThrottle):
    """
    Dedicated, generously-sized bucket for POST /api/auth/token/refresh/
    (2026-09-12 fix) — independent of DEFAULT_THROTTLE_RATES["anon"].

    Without this, TokenRefreshView (rest_framework_simplejwt, used as-is —
    see urls.py) fell through to the global anon default of 60/min per IP,
    same as every other unauthenticated endpoint. That default was sized
    for general API abuse protection, not reasoned about this endpoint's
    actual traffic shape: access tokens live 15 min (SIMPLE_JWT above), so
    every logged-in browser calls this automatically roughly every <15 min
    for the length of an exam, and students in one exam hall/lab commonly
    share a single public IP (school NAT/gateway) whose refresh calls
    cluster together near exam start.

    This is the same fix as gateway/nginx.conf's token_refresh_zone, at the
    application layer — nginx's per-IP limit_req and this DRF throttle both
    apply to the same request, so leaving this one at the tighter 60/min
    anon default would have silently capped the endpoint there regardless
    of how generous the nginx zone was made. Kept at parity with nginx's
    120/min so neither layer is the surprise bottleneck.

    A refresh token isn't a guessable secret, so brute-force isn't the
    threat model here (unlike login) — this exists to keep pace with
    legitimate concurrent exam traffic, not to gate credential guessing.
    """

    scope = "token_refresh"


class LoginAttemptThrottle(ResilientThrottleMixin, SimpleRateThrottle):
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
