from rest_framework import permissions
from .models import UserRoleAssignment

class IsTenantMember(permissions.BasePermission):
    """
    Allows access only to users who belong to the current request's tenant.
    """
    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        
        # Superusers bypass tenant check (optional, but good for admin)
        if request.user.is_superuser:
            return True

        if not hasattr(request, 'tenant') or not request.tenant:
            # If no tenant context (public URL), deny if strict, or handled by middleware?
            # If middleware didn't block it, it might be a public endpoint, 
            # but this permission is explicit.
            return False
        
        # Check if user's tenant matches request tenant
        return request.user.tenant_id == request.tenant.id


class HasRole(permissions.BasePermission):
    """
    Usage:
        class MyView(APIView):
            permission_classes = [HasRole]
            required_roles = ['COORDINATOR', 'ADMIN']
    """
    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
            
        required_roles = getattr(view, 'required_roles', [])
        if not required_roles:
            return True # No specific role required

        # Check if user has any of the required roles logic
        # We need to query UserRoleAssignment
        return UserRoleAssignment.objects.filter(
            user=request.user,
            role__name__in=required_roles,
            tenant=request.tenant # Scope to current tenant
        ).exists()
