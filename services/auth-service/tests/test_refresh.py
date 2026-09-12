import pytest
import json
from django.test import Client
from django.urls import resolve

from authentication.throttling import TokenRefreshThrottle
from authentication.views import TokenRefreshView


def _login(email, password, role):
    client = Client()
    resp = client.post(
        "/api/auth/login/",
        data=json.dumps({"email": email, "password": password, "role": role}),
        content_type="application/json",
    )
    return resp.json()["data"]


@pytest.mark.django_db
def test_token_refresh_returns_new_access(admin_user):
    tokens = _login("admin@test.com", "Admin@pass1", "admin")
    client = Client()
    resp = client.post(
        "/api/auth/token/refresh/",
        data=json.dumps({"refresh": tokens["refresh_token"]}),
        content_type="application/json",
    )
    assert resp.status_code == 200
    new_data = resp.json()
    assert "access" in new_data


@pytest.mark.django_db
def test_invalid_refresh_token_returns_401():
    client = Client()
    resp = client.post(
        "/api/auth/token/refresh/",
        data=json.dumps({"refresh": "notavalidtoken"}),
        content_type="application/json",
    )
    assert resp.status_code == 401


@pytest.mark.django_db
def test_blacklisted_refresh_returns_401(admin_user):
    tokens = _login("admin@test.com", "Admin@pass1", "admin")
    # Blacklist the refresh token via logout
    client = Client()
    client.post(
        "/api/auth/logout/",
        data=json.dumps({"refresh_token": tokens["refresh_token"]}),
        content_type="application/json",
        HTTP_AUTHORIZATION=f"Bearer {tokens['access_token']}",
    )
    # Try to refresh with blacklisted token
    resp = client.post(
        "/api/auth/token/refresh/",
        data=json.dumps({"refresh": tokens["refresh_token"]}),
        content_type="application/json",
    )
    assert resp.status_code == 401
    # SimpleJWT's InvalidToken sets .detail to a dict of ErrorDetail objects
    # (not a plain string) — a naive exception handler that builds the
    # top-level "message" via str(exc) leaks Python's raw repr straight to
    # the frontend toast: "{'detail': ErrorDetail(string='Token is
    # blacklisted', code='token_not_valid'), 'code': ErrorDetail(...)}".
    # Real bug, caught live in the admin UI. message must be clean text.
    message = resp.json()["message"]
    assert "ErrorDetail" not in message
    assert "{'detail'" not in message
    assert message == "Token is blacklisted"


# ── Rate-limit wiring (2026-09-12) ──────────────────────────────────────────
#
# Regression coverage for the shared-exam-hall-IP fix: this endpoint must
# NOT silently fall back to the global "anon" 60/min throttle (the bug
# that undermined the nginx-level fix until this was caught). Asserting
# the wiring directly, rather than firing 121 requests to observe a 429,
# keeps this deterministic and fast while still failing loudly if someone
# reverts urls.py to the raw rest_framework_simplejwt view or removes
# throttle_classes from the subclass.

def test_token_refresh_url_resolves_to_the_subclassed_view():
    match = resolve("/api/auth/token/refresh/")
    assert match.func.view_class is TokenRefreshView


def test_token_refresh_view_uses_dedicated_throttle_not_global_anon_default():
    assert TokenRefreshView.throttle_classes == [TokenRefreshThrottle]


def test_token_refresh_throttle_rate_is_120_per_min_not_the_60_per_min_anon_default():
    rate = TokenRefreshThrottle().get_rate()
    assert rate == "120/min", (
        f"Expected the dedicated token_refresh scope (120/min, parity with "
        f"gateway/nginx.conf's token_refresh_zone) — got {rate!r}. If this "
        f"reads '60/min' the DEFAULT_THROTTLE_RATES['token_refresh'] entry "
        f"is missing and the view has silently fallen back to the global "
        f"anon default, reintroducing the original bug."
    )
