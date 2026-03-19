"""
User invitation views for role-based organization invitations.

Allows Course Incharges to search Lysa platform users and invite them
to join their organization with specific role assignments.
"""

import secrets
from datetime import timedelta
from django.utils import timezone
from django.db.models import Q
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from authentication.models import User, UserInvitation, OrganizationMember
from authentication.utils import log_audit
from .invitation_serializers import (
    UserSearchSerializer,
    UserInvitationSerializer,
    CreateInvitationSerializer,
    InvitationListSerializer
)
import logging

logger = logging.getLogger(__name__)


class UserInvitationViewSet(viewsets.ViewSet):
    """
    API endpoints for user search and role-based invitations
    """
    permission_classes = [IsAuthenticated]
    
    def _get_organization(self, request):
        """Get organization from user's context"""
        user = request.user
        
        # Direct organization from user
        if hasattr(user, 'organization') and user.organization:
            return user.organization
        
        # Try to get from organization memberships
        try:
            member = OrganizationMember.objects.filter(user=user).first()
            if member:
                return member.organization
        except Exception as e:
            logger.error(f"Error getting organization: {e}")
        
        return None
    
    @action(detail=False, methods=['get'], url_path='search')
    def search_users(self, request):
        """
        Search Lysa platform users by email, username, or name.
        Excludes users already in the current organization.
        
        GET /api/auth/invitations/search/?q=john@example.com
        
        Returns: List of users (max 50)
        """
        query = request.GET.get('q', '').strip()
        
        if not query or len(query) < 2:
            return Response({
                'status': 'error',
                'message': 'Search query must be at least 2 characters'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        organization = self._get_organization(request)
        if not organization:
            return Response({
                'status': 'error',
                'message': 'No organization associated with user'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Get existing member user IDs for this organization
        existing_member_ids = OrganizationMember.objects.filter(
            organization=organization
        ).values_list('user_id', flat=True)
        
        # Get pending invitation user IDs
        pending_invitation_ids = UserInvitation.objects.filter(
            organization=organization,
            status='pending',
            expires_at__gt=timezone.now()
        ).values_list('user_id', flat=True)
        
        # Combine exclusion lists
        excluded_ids = list(existing_member_ids) + list(pending_invitation_ids)
        
        # Search users (case-insensitive, cross-tenant)
        users = User.objects.exclude(
            id__in=excluded_ids
        ).filter(
            Q(email__icontains=query) |
            Q(username__icontains=query) |
            Q(full_name__icontains=query)
        ).filter(
            is_active=True
        )[:50]  # Limit to 50 results
        
        serializer = UserSearchSerializer(users, many=True)
        
        return Response({
            'status': 'success',
            'data': serializer.data,
            'count': len(serializer.data)
        })
    
    @action(detail=False, methods=['post'], url_path='invite')
    def invite_user(self, request):
        """
        Invite a user to organization with specific role(s).
        
        POST /api/auth/invitations/invite/
        {
            "user_id": 123,
            "roles": ["evaluator", "mentor"],
            "message": "Join our CS department"
        }
        """
        organization = self._get_organization(request)
        if not organization:
            return Response({
                'status': 'error',
                'message': 'No organization associated with user'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Validate request data
        serializer = CreateInvitationSerializer(data=request.data)
        if not serializer.is_valid():
            return Response({
                'status': 'error',
                'errors': serializer.errors
            }, status=status.HTTP_400_BAD_REQUEST)
        
        user_id = serializer.validated_data['user_id']
        roles = serializer.validated_data['roles']
        message = serializer.validated_data.get('message', '')
        
        # Check if user exists
        try:
            user = User.objects.get(id=user_id)
        except User.DoesNotExist:
            return Response({
                'status': 'error',
                'message': 'User not found'
            }, status=status.HTTP_404_NOT_FOUND)
        
        # Check if user is already a member
        if OrganizationMember.objects.filter(organization=organization, user=user).exists():
            return Response({
                'status': 'error',
                'message': 'User is already a member of this organization'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Check if there's already a pending invitation
        existing_invitation = UserInvitation.objects.filter(
            organization=organization,
            user=user,
            status='pending',
            expires_at__gt=timezone.now()
        ).first()
        
        if existing_invitation:
            return Response({
                'status': 'error',
                'message': 'User already has a pending invitation'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Generate unique invitation token
        invitation_token = secrets.token_urlsafe(32)
        
        # Create invitation
        invitation = UserInvitation.objects.create(
            user=user,
            organization=organization,
            invited_by=request.user,
            roles=roles,
            invitation_token=invitation_token,
            message=message,
            expires_at=timezone.now() + timedelta(days=7)
        )
        
        # TODO: Send invitation email
        # send_invitation_email(invitation)
        
        logger.info(f"Invitation created: {invitation.id} for user {user.email} by {request.user.email}")
        
        return Response({
            'status': 'success',
            'message': 'Invitation sent successfully',
            'data': UserInvitationSerializer(invitation).data
        }, status=status.HTTP_201_CREATED)
    
    @action(detail=False, methods=['get'], url_path='pending')
    def pending_invitations(self, request):
        """
        List all pending invitations for the organization.
        
        GET /api/auth/invitations/pending/
        """
        organization = self._get_organization(request)
        if not organization:
            return Response({
                'status': 'error',
                'message': 'No organization associated with user'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        invitations = UserInvitation.objects.filter(
            organization=organization,
            status='pending',
            expires_at__gt=timezone.now()
        ).select_related('user', 'invited_by').order_by('-created_at')
        
        serializer = InvitationListSerializer(invitations, many=True)
        
        return Response({
            'status': 'success',
            'data': serializer.data
        })
    
    @action(detail=True, methods=['post'], url_path='resend')
    def resend_invitation(self, request, pk=None):
        """
        Resend an invitation email and extend expiry.
        
        POST /api/auth/invitations/{id}/resend/
        """
        organization = self._get_organization(request)
        if not organization:
            return Response({
                'status': 'error',
                'message': 'No organization associated with user'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            invitation = UserInvitation.objects.get(
                id=pk,
                organization=organization,
                status='pending'
            )
        except UserInvitation.DoesNotExist:
            return Response({
                'status': 'error',
                'message': 'Invitation not found'
            }, status=status.HTTP_404_NOT_FOUND)
        
        # Extend expiry by 7 days from now
        invitation.expires_at = timezone.now() + timedelta(days=7)
        invitation.save()
        
        # TODO: Resend email
        # send_invitation_email(invitation)
        
        logger.info(f"Invitation resent: {invitation.id}")
        
        return Response({
            'status': 'success',
            'message': 'Invitation resent successfully',
            'data': UserInvitationSerializer(invitation).data
        })
    
    @action(detail=True, methods=['post'], url_path='cancel')
    def cancel_invitation(self, request, pk=None):
        """
        Cancel a pending invitation.
        
        POST /api/auth/invitations/{id}/cancel/
        """
        organization = self._get_organization(request)
        if not organization:
            return Response({
                'status': 'error',
                'message': 'No organization associated with user'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            invitation = UserInvitation.objects.get(
                id=pk,
                organization=organization,
                status='pending'
            )
        except UserInvitation.DoesNotExist:
            return Response({
                'status': 'error',
                'message': 'Invitation not found'
            }, status=status.HTTP_404_NOT_FOUND)
        
        invitation.status = 'cancelled'
        invitation.save()
        
        logger.info(f"Invitation cancelled: {invitation.id}")
        
        return Response({
            'status': 'success',
            'message': 'Invitation cancelled successfully'
        })
    
    @action(detail=False, methods=['post'], url_path='accept')
    def accept_invitation(self, request):
        """
        Accept an invitation and join organization with assigned roles.
        
        POST /api/auth/invitations/accept/
        {
            "invitation_token": "abc123..."
        }
        """
        token = request.data.get('invitation_token')
        if not token:
            return Response({
                'status': 'error',
                'message': 'Invitation token required'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            invitation = UserInvitation.objects.get(
                invitation_token=token,
                status='pending'
            )
        except UserInvitation.DoesNotExist:
            return Response({
                'status': 'error',
                'message': 'Invalid or expired invitation'
            }, status=status.HTTP_404_NOT_FOUND)
        
        # Check if invitation is expired
        if not invitation.can_be_accepted():
            invitation.status = 'expired'
            invitation.save()
            return Response({
                'status': 'error',
                'message': 'This invitation has expired'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Check if user is already a member
        if OrganizationMember.objects.filter(
            user=invitation.user,
            organization=invitation.organization
        ).exists():
            return Response({
                'status': 'error',
                'message': 'User is already a member of this organization'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Create organization membership
        member = OrganizationMember.objects.create(
            user=invitation.user,
            organization=invitation.organization
        )
        
        # Assign roles to user
        user = invitation.user
        for role in invitation.roles:
            if role == 'student':
                user.is_student = True
            elif role == 'evaluator':
                user.is_evaluator = True
            elif role == 'mentor':
                user.is_mentor = True
            elif role == 'qp_uploader':
                user.is_qp_uploader = True
        
        # Set organization and active role
        if not user.organization:
            user.organization = invitation.organization
        
        # Set active role to first role if not set
        if not user.active_role and invitation.roles:
            role_mapping = {
                'student': 'student',
                'evaluator': 'evaluator',
                'mentor': 'mentor',
                'qp_uploader': 'qp_uploader'
            }
            user.active_role = role_mapping.get(invitation.roles[0])
        
        user.save()
        
        # Mark invitation as accepted
        invitation.status = 'accepted'
        invitation.accepted_at = timezone.now()
        invitation.save()
        
        logger.info(f"Invitation {invitation.id} accepted by {user.email}")
        
        return Response({
            'status': 'success',
            'message': 'Invitation accepted successfully',
            'data': {
                'organization': invitation.organization.name,
                'roles': invitation.roles
            }
        })

