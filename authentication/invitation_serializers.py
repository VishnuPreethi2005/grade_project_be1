"""
Serializers for user invitation and role assignment system.
"""

from rest_framework import serializers
from authentication.models import User, UserInvitation


class UserSearchSerializer(serializers.ModelSerializer):
    """
    Serializer for user search results
    """
    class Meta:
        model = User
        fields = ['id', 'email', 'username', 'full_name']


class UserInvitationSerializer(serializers.ModelSerializer):
    """
    Serializer for displaying user invitations
    """
    user_email = serializers.EmailField(source='user.email', read_only=True)
    user_name = serializers.CharField(source='user.username', read_only=True)
    user_full_name = serializers.CharField(source='user.full_name', read_only=True)
    organization_name = serializers.CharField(source='organization.name', read_only=True)
    invited_by_email = serializers.EmailField(source='invited_by.email', read_only=True)
    invited_by_name = serializers.CharField(source='invited_by.username', read_only=True)
    
    class Meta:
        model = UserInvitation
        fields = [
            'id',
            'user_email',
            'user_name',
            'user_full_name',
            'organization_name',
            'invited_by_email',
            'invited_by_name',
            'roles',
            'status',
            'message',
            'created_at',
            'expires_at',
            'accepted_at',
            'declined_at'
        ]


class CreateInvitationSerializer(serializers.Serializer):
    """
    Serializer for creating new invitations
    """
    user_id = serializers.IntegerField()
    roles = serializers.ListField(
        child=serializers.ChoiceField(choices=[
            'student',
            'evaluator',
            'mentor',
            'qp_uploader'
        ]),
        min_length=1,
        max_length=4
    )
    message = serializers.CharField(required=False, allow_blank=True, max_length=1000)
    
    def validate_roles(self, value):
        """Ensure roles are unique"""
        if len(value) != len(set(value)):
            raise serializers.ValidationError("Duplicate roles are not allowed")
        return value


class InvitationListSerializer(serializers.ModelSerializer):
    """
    Serializer for listing invitations with minimal details
    """
    user = UserSearchSerializer(read_only=True)
    invited_by_name = serializers.CharField(source='invited_by.username', read_only=True)
    time_remaining = serializers.SerializerMethodField()
    
    class Meta:
        model = UserInvitation
        fields = [
            'id',
            'user',
            'invited_by_name',
            'roles',
            'status',
            'created_at',
            'expires_at',
            'time_remaining'
        ]
    
    def get_time_remaining(self, obj):
        """Calculate time remaining until expiration"""
        from django.utils import timezone
        from datetime import timedelta
        
        if obj.status != 'pending':
            return None
        
        now = timezone.now()
        if now >= obj.expires_at:
            return "Expired"
        
        delta = obj.expires_at - now
        
        days = delta.days
        hours = delta.seconds // 3600
        minutes = (delta.seconds % 3600) // 60
        
        if days > 0:
            return f"{days} day{'s' if days != 1 else ''} {hours}h"
        elif hours > 0:
            return f"{hours}h {minutes}m"
        else:
            return f"{minutes}m"


class AcceptInvitationSerializer(serializers.Serializer):
    """
    Serializer for accepting invitations
    """
    invitation_token = serializers.CharField()
