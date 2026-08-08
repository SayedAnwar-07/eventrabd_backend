from django.db import DatabaseError
from django.db.utils import IntegrityError

from rest_framework.views import exception_handler
from rest_framework.exceptions import (
    ValidationError,
    AuthenticationFailed,
    NotAuthenticated,
    NotFound,
    PermissionDenied as DRFPermissionDenied,
    Throttled,
    APIException,
)

from apps.core.responses import error_response


def _extract_error_message(data):
    """
    Extract first meaningful error message.
    """

    if isinstance(data, dict):
        for value in data.values():
            if isinstance(value, list) and value:
                return str(value[0])

            if isinstance(value, str):
                return value

    if isinstance(data, list) and data:
        return str(data[0])

    return "Request failed."


def custom_exception_handler(exc, context):
    """
    Global DRF exception handler.
    """

    response = exception_handler(exc, context)

    # -----------------------------
    # DRF handled exceptions
    # -----------------------------

    if response is not None:

        message = "Request failed."

        if isinstance(exc, ValidationError):
            message = _extract_error_message(response.data)

        elif isinstance(exc, AuthenticationFailed):
            message = "Authentication failed."

        elif isinstance(exc, NotAuthenticated):
            message = "Authentication credentials were not provided."

        elif isinstance(exc, NotFound):
            message = _extract_error_message(response.data)
            
        elif isinstance(exc, DRFPermissionDenied):
            message = _extract_error_message(response.data)

        elif isinstance(exc, Throttled):
            message = "Too many requests. Please try again later."

        elif isinstance(exc, APIException):
            message = _extract_error_message(response.data)

        return error_response(
            message=message,
            errors=response.data,
            status_code=response.status_code,
        )


    # -----------------------------
    # Unexpected database errors
    # -----------------------------

    if isinstance(exc, (
        DatabaseError,
        IntegrityError,
    )):

        return error_response(
            message="Database error occurred.",
            errors={},
            status_code=500,
        )


    # -----------------------------
    # Unknown exception
    # Middleware will handle it
    # -----------------------------

    return None