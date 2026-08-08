from django.http import JsonResponse
from django.conf import settings


class GlobalErrorMiddleware:
    """
    Catch unexpected server errors only.

    Do not put:
    - validation logic
    - database queries
    - business rules
    here.
    """

    def __init__(self, get_response):
        self.get_response = get_response


    def __call__(self, request):

        try:
            response = self.get_response(request)

        except Exception:

            return JsonResponse(
                {
                    "success": False,
                    "message": "Internal server error.",
                    "errors": {},
                },
                status=500,
            )

        return response