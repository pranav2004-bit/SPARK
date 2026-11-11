"""
Django's own built-in DATA_UPLOAD_MAX_MEMORY_SIZE guard does not actually
engage under this platform's uvicorn/ASGI deployment (confirmed empirically
on assessment-service with real end-to-end requests through the live
gateway, not just a unit test — see that service's core/middleware.py for
the full incident writeup). Nginx's own `client_max_body_size` is still the
primary defense, but per this project's established "nginx primary,
app-level defense-in-depth" convention, a working app-level backstop is
still expected — implemented directly here rather than relying on the
framework default that doesn't fire.
"""
from django.http import JsonResponse

MAX_REQUEST_BODY_BYTES = 2 * 1024 * 1024  # 2MB — every real payload this service
                                            # accepts is small structured JSON (an
                                            # essay response, a rubric prompt); the
                                            # largest legitimate one is nowhere close.


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
