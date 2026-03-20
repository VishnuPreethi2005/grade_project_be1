# executor/utils/auth.py
from rest_framework.response import Response
from functools import wraps
from django.conf import settings

def require_api_key(view_func):
    @wraps(view_func)
    def _wrapped_view(request, *args, **kwargs):
        token = request.headers.get("Authorization")

        valid_keys = [
            f"Bearer {settings.GEMINI_API_KEY}",
            f"Bearer {settings.COHERE_API_KEY}"
        ]

        if token not in valid_keys:
            return Response({'error': 'Unauthorized - Invalid API key'}, status=401)

        return view_func(request, *args, **kwargs)
    return _wrapped_view
