from urllib.parse import parse_qs

from channels.middleware import BaseMiddleware
from channels.db import database_sync_to_async

from rest_framework_simplejwt.authentication import JWTAuthentication


@database_sync_to_async
def get_user_from_token(token):
    from django.contrib.auth.models import AnonymousUser

    try:
        validated_token = JWTAuthentication().get_validated_token(
            token
        )

        user = JWTAuthentication().get_user(
            validated_token
        )

        return user

    except Exception:
        return AnonymousUser()


class JWTAuthMiddleware(BaseMiddleware):

    async def __call__(
        self,
        scope,
        receive,
        send,
    ):
        from django.contrib.auth.models import AnonymousUser

        query_string = scope["query_string"].decode()

        query_params = parse_qs(query_string)

        token = None

        if "token" in query_params:
            token = query_params["token"][0]

        if token:
            scope["user"] = await get_user_from_token(
                token
            )

        else:
            scope["user"] = AnonymousUser()

        return await super().__call__(
            scope,
            receive,
            send,
        )


def JWTAuthMiddlewareStack(inner):
    return JWTAuthMiddleware(inner)