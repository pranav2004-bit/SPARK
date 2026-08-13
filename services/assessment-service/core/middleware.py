"""
Task 12.2's API-abuse-hardening audit found that Django's own built-in
DATA_UPLOAD_MAX_MEMORY_SIZE guard (settings.py; the standard framework
protection against huge request bodies) does not actually engage in this
service's deployment — confirmed empirically with real end-to-end requests
through the live gateway, not just a unit test: a 6MB JSON body reached
full application-level processing every time, never rejected at the
transport layer. This service runs under `uvicorn core.asgi:application`
(entrypoint.sh), and Django's ASGI request handling does not populate
CONTENT_LENGTH into request.META the same way its WSGI handling does,
which is exactly the value `HttpRequest.body`'s built-in size check reads —
so the check silently no-ops here. Nginx's own `client_max_body_size 50M`
(gateway/nginx.conf, nginx.dev.conf) is still the primary defense and
already works (a battle-tested nginx feature, not something specific to
this app), but per this project's own established "nginx primary, app-level
defense-in-depth" convention (core/settings.py's REST_FRAMEWORK throttle
comment states this explicitly for rate limiting), a working app-level
backstop is still expected — this middleware is that backstop, implemented
directly rather than relying on the framework default that doesn't fire.
"""
from django.http import JsonResponse

MAX_REQUEST_BODY_BYTES = 2 * 1024 * 1024  # 2MB — every real payload this service
                                            # accepts is small structured JSON; the
                                            # largest legitimate one (a 100-event
                                            # activity-log batch) is nowhere close.


class MaxBodySizeMiddleware:
    """Rejects any request whose declared Content-Length exceeds
    MAX_REQUEST_BODY_BYTES with a clean 400, before the body is read or
    the view (and its DB queries, serializers, etc.) ever runs."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        content_length = request.META.get("CONTENT_LENGTH")
        if content_length:
            try:
                length = int(content_length)
            except (TypeError, ValueError):
                length = None
            if length is not None and length > MAX_REQUEST_BODY_BYTES:
                return JsonResponse(
                    {
                        "success": False,
                        "message": f"Request body too large (max {MAX_REQUEST_BODY_BYTES} bytes).",
                    },
                    status=400,
                )
        return self.get_response(request)
