from rest_framework.response import Response


def error_response(
    message="Something went wrong.",
    errors=None,
    status_code=400,
):
    return Response(
        {
            "success": False,
            "message": message,
            "errors": errors or {},
        },
        status=status_code,
    )


def success_response(
    message="Success.",
    data=None,
    status_code=200,
):
    return Response(
        {
            "success": True,
            "message": message,
            "data": data or {},
        },
        status=status_code,
    )