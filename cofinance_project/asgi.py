import os
from django.core.asgi import get_asgi_application

# Set settings environment variable before loading apps
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'cofinance_project.settings')
django_asgi_app = get_asgi_application()

from urllib.parse import parse_qs
from channels.routing import ProtocolTypeRouter, URLRouter
from channels.security.websocket import AllowedHostsOriginValidator
from channels.auth import AuthMiddlewareStack
from channels.db import database_sync_to_async
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser

User = get_user_model()

@database_sync_to_async
def get_user_from_token(token_key):
    try:
        from rest_framework_simplejwt.tokens import AccessToken
        token = AccessToken(token_key)
        user_id = token['user_id']
        return User.objects.get(id=user_id)
    except Exception:
        return AnonymousUser()

class TokenAuthMiddleware:
    """
    Custom WebSocket middleware that authenticates users based on JWT token in query string,
    or falls back to session auth.
    """
    def __init__(self, inner):
        self.inner = inner

    async def __call__(self, scope, receive, send):
        # Read token from query parameters
        query_string = scope.get('query_string', b'').decode()
        query_params = parse_qs(query_string)
        token = query_params.get('token', [None])[0]

        if token:
            scope['user'] = await get_user_from_token(token)
        
        return await self.inner(scope, receive, send)

# Import websocket routing after django setup
from cofinance.routing import websocket_urlpatterns

application = ProtocolTypeRouter({
    "http": django_asgi_app,
    "websocket": AllowedHostsOriginValidator(
        TokenAuthMiddleware(
            AuthMiddlewareStack(
                URLRouter(
                    websocket_urlpatterns
                )
            )
        )
    ),
})
