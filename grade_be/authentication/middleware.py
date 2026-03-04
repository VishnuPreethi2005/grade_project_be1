import logging
import uuid
from django.utils.deprecation import MiddlewareMixin
from django.http import JsonResponse
from authentication.models import Tenant, User
from rest_framework_simplejwt.tokens import AccessToken
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError

logger = logging.getLogger(__name__)

class TenantMiddleware(MiddlewareMixin):
    """
    Middleware to resolve the Tenant from the request header X-Tenant-ID.
    Falls back to extracting tenant from JWT token if header is missing.
    """
    
    PUBLIC_PATHS = [
        '/admin/',
        '/favicon.ico', 
        '/api/login/', 
        '/api/signup/',
        '/api/verify-otp/',
        '/api/resend-otp/',
        '/api/forgot-password/',
        '/api/reset-password/',
        '/api/auth/check-user/',
        '/api/organization/register/',
        '/health/',
        # Platform Admin Endpoints (Cross-Tenant)
        '/api/user-count/',
        '/api/user-role-counts/',
        '/api/organization/list/',
        '/api/grade/main-requests/',
        '/api/feedback/list/',
        '/api/grade/get-evaluators/',
        '/api/grade/unassigned-answers/',
        # User Role Management
        '/api/update-user-roles/',
        '/api/update-active-role/',
        '/api/add_role/',
        '/api/update-profile/',
        '/api/grade/sample/',
        '/api/organization/students/accept_invitation/',
        '/api/organization/students/decline_invitation/',
        '/docs',
        '/openapi.json',
        '/mini_ide',
        '/open_folder',
        '/list_files',
        '/create_folder_workspace',
        '/pick_folder',
        '/create_item',
        '/save_file',
        '/view_file',
        '/run_file',
        '/delete_item',
        '/get_host_root',
        '/update_host_root',
        '/pick_host_root',
        '/close_workspace',
        '/module2',
    ]

    def _get_user_from_token(self, request):
        """Extract user from JWT token in Authorization header."""
        auth_header = request.headers.get('Authorization', '')
        if not auth_header.startswith('Bearer '):
            return None
        
        token_str = auth_header.split(' ')[1]
        try:
            token = AccessToken(token_str)
            user_id = token.get('user_id')
            if user_id:
                return User.objects.get(id=user_id)
        except (InvalidToken, TokenError, User.DoesNotExist) as e:
            logger.debug(f"Could not extract user from token: {e}")
        return None

    def process_request(self, request):
        path = request.path_info
        
        # Check if path is public
        is_public = False
        for public_path in self.PUBLIC_PATHS:
            if path.startswith(public_path) or (path + '/').startswith(public_path):
                is_public = True
                break
        
        # Additional programming paths that should allow no-tenant access
        PROGRAMMING_PATHS = [
            '/api/questions/',
            '/api/run_code/',
            '/api/grade_code/',
            '/api/generate_questions/',
            '/api/submissions/', 
            '/api/user/credits/',
        ]
        
        for prog_path in PROGRAMMING_PATHS:
            if path.startswith(prog_path) or (path + '/').startswith(prog_path):
                is_public = True
                break
        
        # Explicitly allow root path
        if path == '/' or path == '':
            is_public = True

        tenant_id = request.headers.get('X-Tenant-ID')

        if tenant_id:
            try:
                # Validate UUID format
                uuid_obj = uuid.UUID(tenant_id)
                request.tenant = Tenant.objects.get(id=uuid_obj)
            except (ValueError, Tenant.DoesNotExist):
                return JsonResponse({'error': 'Invalid Tenant ID'}, status=404)
        else:
            # Fallback: Try to get tenant from JWT token
            request.tenant = None
            
            # First try to get user from JWT token (since JWT auth happens in view layer)
            user = self._get_user_from_token(request)
            
            # If no user from token, try request.user (in case session auth is used)
            if not user and hasattr(request, 'user') and request.user.is_authenticated:
                user = request.user
            
            # If we have a user, try to get their tenant
            if user:
                if hasattr(user, 'tenant') and user.tenant:
                    request.tenant = user.tenant
                elif hasattr(user, 'organization') and user.organization and hasattr(user.organization, 'tenant') and user.organization.tenant:
                    request.tenant = user.organization.tenant

            # If still no tenant and path is not public, return error
            if not request.tenant and not is_public:
                logger.warning(f"No tenant found for path {path}, user: {user}")
                return JsonResponse({
                    'error': 'X-Tenant-ID header is missing and could not be inferred from user context',
                    'detail': 'Please ensure you are logged in with a valid account that has a tenant assigned.'
                }, status=400)

        return None
