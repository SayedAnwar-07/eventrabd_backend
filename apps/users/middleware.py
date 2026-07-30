from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.exceptions import TokenError, InvalidToken
from django.http import JsonResponse

class TokenVersionMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        auth_header = request.headers.get('Authorization', '')
        if auth_header.startswith('Bearer '):
            try:
                jwt_auth = JWTAuthentication()
                validated_token = jwt_auth.get_validated_token(
                    auth_header.split(' ')[1]
                )
                user = jwt_auth.get_user(validated_token)
                token_version = validated_token.get('token_version', -1)

                if token_version != user.token_version:
                    return JsonResponse(
                        {'detail': 'Session expired. Please log in again.'},
                        status=401
                    )
            except (TokenError, InvalidToken, Exception):
                pass 

        return self.get_response(request)