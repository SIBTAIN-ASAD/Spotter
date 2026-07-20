"""Application-wide exception types and DRF handler."""

import logging

from rest_framework import status
from rest_framework.exceptions import APIException
from rest_framework.response import Response
from rest_framework.views import exception_handler

logger = logging.getLogger(__name__)


class ServiceUnavailableError(APIException):
    status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    default_detail = "An upstream service is temporarily unavailable."
    default_code = "service_unavailable"


class ExternalServiceError(APIException):
    status_code = status.HTTP_502_BAD_GATEWAY
    default_detail = "An upstream service returned an invalid response."
    default_code = "external_service_error"


class BusinessRuleError(APIException):
    status_code = status.HTTP_422_UNPROCESSABLE_ENTITY
    default_detail = "The request could not be processed."
    default_code = "business_rule_violation"


def custom_exception_handler(exc, context):
    response = exception_handler(exc, context)

    request = context.get("request")
    request_id = getattr(request, "request_id", None) if request else None

    if response is not None:
        payload = {
            "error": {
                "code": getattr(exc, "default_code", "error"),
                "message": _extract_message(response.data),
                "details": response.data if isinstance(response.data, dict) else None,
            },
            "request_id": request_id,
        }
        response.data = payload
        return response

    logger.exception("Unhandled exception", extra={"request_id": request_id})
    return Response(
        {
            "error": {
                "code": "internal_server_error",
                "message": "An unexpected error occurred.",
                "details": None,
            },
            "request_id": request_id,
        },
        status=status.HTTP_500_INTERNAL_SERVER_ERROR,
    )


def _extract_message(data) -> str:
    if isinstance(data, dict):
        if "detail" in data:
            return str(data["detail"])
        if "non_field_errors" in data:
            return str(data["non_field_errors"][0])
        first_key = next(iter(data))
        first_value = data[first_key]
        if isinstance(first_value, list):
            return str(first_value[0])
        return str(first_value)
    if isinstance(data, list):
        return str(data[0])
    return str(data)
