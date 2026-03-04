# executor/throttles.py
from rest_framework.throttling import SimpleRateThrottle

class CodeRunRateThrottle(SimpleRateThrottle):
    scope = 'code_run'

    def get_cache_key(self, request, view):
        if request.user and request.user.is_authenticated:
            # Use user ID as throttle key
            return self.cache_format % {
                'scope': self.scope,
                'ident': request.user.pk
            }
        # Fallback to IP-based for anonymous users
        return self.cache_format % {
            'scope': self.scope,
            'ident': self.get_ident(request)
        }
