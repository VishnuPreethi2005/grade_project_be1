"""
Utility functions for audit logging and request handling
"""

def get_client_ip(request):
    """
    Extract client IP address from request.
    
    Handles proxy forwarding (X-Forwarded-For header).
    
    Args:
        request: Django HttpRequest object
        
    Returns:
        str: Client IP address
    """
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        # X-Forwarded-For can contain multiple IPs, take the first one
        ip = x_forwarded_for.split(',')[0].strip()
    else:
        ip = request.META.get('REMOTE_ADDR', '')
    return ip


def log_audit(request, action, target_model=None, target_id=None, **details):
    """
    Convenience function for creating audit log entries.
    
    Usage:
        log_audit(request, 'USER_LOGIN')
        log_audit(request, 'TEST_CREATE', 'Test', test.id, test_name=test.title)
    
    Args:
        request: Django HttpRequest object
        action: Action type (should match AuditLog.ACTION_CHOICES)
        target_model: Model name that was affected (optional)
        target_id: ID of the affected object (optional)
        **details: Additional context to store in details JSON field
    """
    from authentication.models import AuditLog
    
    # Get actor (authenticated user or None for anonymous)
    actor = request.user if request.user.is_authenticated else None
    
    # Extract request metadata
    ip_address = get_client_ip(request)
    user_agent = request.META.get('HTTP_USER_AGENT', '')[:500]  # Limit length
    
    # Create audit log entry
    return AuditLog.log_action(
        actor=actor,
        action=action,
        target_model=target_model,
        target_object_id=str(target_id) if target_id else None,
        ip_address=ip_address,
        user_agent=user_agent,
        details=details
    )
