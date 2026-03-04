"""
Django signals for authentication app.

Handles automatic creation of related models and audit logging.
"""

from django.db.models.signals import post_save
from django.dispatch import receiver
from authentication.models import User, UserPII


@receiver(post_save, sender=User)
def create_user_pii(sender, instance, created, **kwargs):
    """
    Automatically create UserPII record when a new user is created.
    
    This ensures every user has a PII record ready for profile data,
    supporting GDPR-compliant data separation.
    
    Args:
        sender: User model class
        instance: The User instance being saved
        created: Boolean indicating if this is a new instance
        **kwargs: Additional signal kwargs
    """
    if created:
        UserPII.objects.get_or_create(user=instance)

# Audit Log Signals
from django.contrib.auth.signals import user_logged_in, user_logged_out, user_login_failed
from authentication.models import AuditLog

@receiver(user_logged_in)
def log_user_login(sender, request, user, **kwargs):
    """Log user login events"""
    ip = get_client_ip(request)
    AuditLog.log_action(
        actor=user,
        action='USER_LOGIN',
        ip_address=ip,
        user_agent=request.META.get('HTTP_USER_AGENT', ''),
        details={'method': 'login'}
    )

@receiver(user_logged_out)
def log_user_logout(sender, request, user, **kwargs):
    """Log user logout events"""
    ip = get_client_ip(request)
    if user:
         AuditLog.log_action(
            actor=user,
            action='USER_LOGOUT',
            ip_address=ip,
            user_agent=request.META.get('HTTP_USER_AGENT', ''),
            details={'method': 'logout'}
        )

@receiver(user_login_failed)
def log_login_failed(sender, credentials, request, **kwargs):
    """Log failed login attempts"""
    ip = get_client_ip(request)
    # Note: user is None here, so actor is None. details needed.
    # We can try to find user by email/username in credentials if needed, 
    # but for security just log the attempt.
    AuditLog.log_action(
        actor=None,
        action='OTHER', # Or add LOGIN_FAILED choice
        ip_address=ip,
        user_agent=request.META.get('HTTP_USER_AGENT', ''),
        details={'event': 'LOGIN_FAILED', 'credentials_keys': list(credentials.keys())}
    )

def get_client_ip(request):
    """Get client IP from request"""
    if not request:
        return None
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        ip = x_forwarded_for.split(',')[0]
    else:
        ip = request.META.get('REMOTE_ADDR')
    return ip
