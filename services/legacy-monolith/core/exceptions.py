import logging
from rest_framework.views import exception_handler
from rest_framework.response import Response
from rest_framework import status

logger = logging.getLogger(__name__)


def custom_exception_handler(exc, context):
    response = exception_handler(exc, context)

    if response is not None:
        data = response.data
        if isinstance(data, dict):
            message = data.get("detail", str(exc))
            if hasattr(message, "code"):
                message = str(message)
        elif isinstance(data, list):
            message = data[0] if data else str(exc)
            message = str(message)
        else:
            message = str(data)

        response.data = {
            "success": False,
            "message": message,
        }
        if isinstance(data, dict) and "detail" not in data:
            response.data["errors"] = data

        return response

    logger.exception("Unhandled exception", exc_info=exc)
    return Response(
        {"success": False, "message": "An unexpected error occurred. Please try again."},
        status=status.HTTP_500_INTERNAL_SERVER_ERROR,
    )
