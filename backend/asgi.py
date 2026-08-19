import os

os.environ.setdefault(
    "DJANGO_SETTINGS_MODULE",
    "backend.settings",
)


from django.core.asgi import get_asgi_application

from channels.routing import ProtocolTypeRouter, URLRouter

from apps.users.websocket_auth import (
    JWTAuthMiddlewareStack,
)

from apps.notifications.routing import websocket_urlpatterns


django_asgi_app = get_asgi_application()


application = ProtocolTypeRouter(
    {
        "http": django_asgi_app,

        "websocket": JWTAuthMiddlewareStack(
            URLRouter(
                websocket_urlpatterns
            )
        ),
    }
)