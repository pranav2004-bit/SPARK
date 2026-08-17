from rest_framework.views import exception_handler
from rest_framework.response import Response


def _clean_message(data, exc):
    """A short, human-readable summary for the top-level "message" field —
    never str(exc). Some DRF exceptions (e.g. SimpleJWT's InvalidToken on a
    blacklisted/invalid refresh token) set .detail to a dict of ErrorDetail
    objects, and str(exc) on those renders Python's raw repr —
    "{'detail': ErrorDetail(string='Token is blacklisted', ...), ...}" —
    straight into the API response and onto a user's screen. response.data
    (built from exc.detail by DRF's own exception_handler) already holds
    the individually-clean rendered strings; just pick one out."""
    if isinstance(data, dict):
        if "detail" in data:
            return str(data["detail"])
        first = next(iter(data.values()), None)
        if isinstance(first, list) and first:
            return str(first[0])
        if first is not None:
            return str(first)
        return str(exc)
    if isinstance(data, list):
        return str(data[0]) if data else str(exc)
    return str(data)


def custom_exception_handler(exc, context):
    response = exception_handler(exc, context)
    if response is not None:
        return Response(
            {"success": False, "message": _clean_message(response.data, exc), "errors": response.data},
            status=response.status_code,
        )
    return response
