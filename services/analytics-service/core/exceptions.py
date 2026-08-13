from rest_framework.views import exception_handler
from rest_framework.response import Response


def custom_exception_handler(exc, context):
    response = exception_handler(exc, context)
    if response is not None:
        return Response(
            {"success": False, "message": str(exc), "errors": response.data},
            status=response.status_code,
        )
    return response
