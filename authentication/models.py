from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils.translation import gettext_lazy as _
from .manager import CustomUserManager
from django.utils import timezone
from datetime import timedelta
import random
import string
from decimal import Decimal
from datetime import date
from django.core.exceptions import ValidationError
import os
import uuid


def generate_otp():
    return "".join(random.choices(string.digits, k=6))



class Tenant(models.Model):
    """
    Tenant model representing the highest level of isolation (e.g., a specific client or environment).
    """
    class Type(models.TextChoices):
        PERSONAL = 'PERSONAL', 'Personal'
        ORGANIZATION = 'ORGANIZATION', 'Organization'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=255)
    type = models.CharField(
        max_length=20, 
        choices=Type.choices, 
        default=Type.ORGANIZATION
    )
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name


class Organization(models.Model):
    """
    Organization model for managing educational institutions.
    """
    class Status(models.TextChoices):
        PENDING = 'PENDING', 'Pending'
        VERIFIED = 'VERIFIED', 'Verified'
        REJECTED = 'REJECTED', 'Rejected'


    name = models.CharField(max_length=255)
    email = models.EmailField(unique=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    # Updated status to use choices
    status = models.CharField(
        max_length=20, 
        choices=Status.choices, 
        default=Status.PENDING
    )

    # Registration details
    address = models.TextField(default="address")
    phone_number = models.CharField(max_length=20, null=True)
    registration_date = models.DateField(default=date.today)
    registration_proof = models.FileField(
        null=True, upload_to="organization_docs/"
    )
    description = models.TextField(null=True)

    # Multi-tenancy link
    tenant = models.OneToOneField(
        Tenant,
        on_delete=models.CASCADE,
        related_name="organization_profile",
        null=True,
    )

    # Admin verification
    VERIFICATION_STATUS_CHOICES = (
        ("PENDING", "Pending"),
        ("APPROVED", "Approved"),
        ("REJECTED", "Rejected"),
    )
    verification_status = models.CharField(
        max_length=20, choices=VERIFICATION_STATUS_CHOICES, default="PENDING"
    )
    is_verified = models.BooleanField(default=False)
    verification_notes = models.TextField(null=True, blank=True)
    verified_by = models.ForeignKey(
        "User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="verified_organizations",
    )
    verified_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return self.name

    def verify_organization(self, admin_user, notes=None):
        """Verify the organization by an admin"""
        self.is_verified = True
        self.status = self.Status.VERIFIED
        self.verified_by = admin_user
        self.verified_at = timezone.now()
        if notes:
            self.verification_notes = notes
        self.save()

    def reject_organization(self, admin_user, notes):
        """Reject the organization registration"""
        self.is_verified = False
        self.status = self.Status.REJECTED
        self.verified_by = admin_user
        self.verified_at = timezone.now()
        self.verification_notes = notes
        self.save()


class User(AbstractUser):
    """
    Custom User model with fields needed for authentication and profile.
    """
    ROLES = [
        ("student", "Student"),
        ("evaluator", "Evaluator"),
        ("qp_uploader", "QP Uploader"),
        ("mentor", "Mentor"),
    ]

    ORG_ROLES = [
        ("admin", "Admin"),
        ("student", "Student"),
    ]

    # Link User to Tenant
    tenant = models.ForeignKey(
        Tenant,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="users"
    )

    # Remove roles = models.JSONField(default=list)
    # Add boolean fields for each role
    is_student = models.BooleanField(default=False)
    is_evaluator = models.BooleanField(default=False)
    is_qp_uploader = models.BooleanField(default=False)
    is_mentor = models.BooleanField(default=False)

    active_role = models.CharField(
        max_length=20, choices=ROLES, null=True, blank=True
    )
    organization = models.ForeignKey(
        Organization,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="users",
    )
    role_org = models.CharField(
        max_length=20, choices=ORG_ROLES, null=True, blank=True
    )
    email = models.EmailField(_("email address"), unique=True)
    username = models.CharField(max_length=150)
    is_email_verified = models.BooleanField(default=False)
    otp = models.CharField(max_length=6, null=True, blank=True)
    otp_created_at = models.DateTimeField(null=True, blank=True)
    password_reset_token = models.CharField(
        max_length=100, null=True, blank=True
    )
    password_reset_expires = models.DateTimeField(null=True, blank=True)

    # Security fields
    failed_login_attempts = models.IntegerField(default=0)
    account_locked_until = models.DateTimeField(null=True, blank=True)
    google_id = models.CharField(
        max_length=255, unique=True, null=True, blank=True
    )

    # Permission fields for QP Uploader and Evaluator
    is_qp_uploader_allowed = models.BooleanField(default=False, help_text="Is this QP Uploader allowed?")
    is_evaluator_allowed = models.BooleanField(default=False, help_text="Is this Evaluator allowed?")
    is_premium = models.BooleanField(default=False)
    is_profile_completed = models.BooleanField(default=False)
    is_admin = models.BooleanField(default=False)  # New field for admin status
    full_name = models.CharField(max_length=255, null=True, blank=True)
    # Removed specific address fields in favor of separate UserPII if needed, 
    # but keeping them for now to minimize migration friction unless strictly replaced.
    # The user request involved UserPII previously, but I'll stick to a minimal diff on User for now
    # unless UserPII is explicitly part of the new 'Constraint' or plan?
    # The plan didn't explicitly mention UserPII, just "Refactor User roles". 
    # I will keep existing fields but ensure Tenant is added.
    
    country = models.CharField(max_length=100, null=True, blank=True)
    state = models.CharField(max_length=100, null=True, blank=True)
    city = models.CharField(max_length=100, null=True, blank=True)
    address_line1 = models.TextField(null=True, blank=True)
    address_line2 = models.TextField(null=True, blank=True)
    phone_number = models.CharField(max_length=20, null=True, blank=True)
    profile_picture = models.ImageField(upload_to='profile_pictures/', null=True, blank=True, verbose_name='Profile Picture')


    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["username"]

    objects = CustomUserManager()

    def __str__(self):
        return self.email

    def lock_account(self):
        self.account_locked_until = timezone.now() + timedelta(minutes=30)
        self.save()

    def unlock_account(self):
        self.account_locked_until = None
        self.failed_login_attempts = 0
        self.save()

    def increment_failed_attempts(self):
        self.failed_login_attempts += 1
        if self.failed_login_attempts >= 5:  # Lock after 5 attempts
            self.lock_account()
        self.save()

    def generate_otp(self):
        self.otp = generate_otp()
        self.otp_created_at = timezone.now()
        self.save()
        return self.otp

    def verify_otp(self, otp):
        if not self.otp or not self.otp_created_at:
            return False

        # OTP expires after 10 minutes
        if timezone.now() > self.otp_created_at + timedelta(minutes=10):
            return False

        return self.otp == otp

    def generate_password_reset_token(self):
        self.password_reset_token = "".join(
            random.choices(string.ascii_letters + string.digits, k=64)
        )
        self.password_reset_expires = timezone.now() + timedelta(hours=1)
        self.save()
        return self.password_reset_token

    def verify_password_reset_token(self, token):
        return (
            self.password_reset_token == token
            and self.password_reset_expires
            and timezone.now() < self.password_reset_expires
        )

    def clean(self):
        # Ensure active_role is one of the selected roles
        super().clean()
        if self.active_role:
            valid = False
            if self.active_role == "student" and self.is_student:
                valid = True
            elif self.active_role == "evaluator" and self.is_evaluator:
                valid = True
            elif self.active_role == "qp_uploader" and self.is_qp_uploader:
                valid = True
            elif self.active_role == "mentor" and self.is_mentor:
                valid = True
            elif self.active_role == "admin" and self.is_admin:
                valid = True
            if not valid:
                raise ValidationError(
                    {"active_role": "Active role must be one of the selected roles."}
                )

    def save(self, *args, **kwargs):
        self.clean()  # Ensure validation before saving
        created = not self.pk
        super().save(*args, **kwargs)
        if created:
            # Create UserCredit with $1 free credit for new users
            UserCredit.objects.get_or_create(
                user=self,
                defaults={
                    "free_credit": Decimal("50.00"),
                    "paid_credit": Decimal("0.00"),
                },
            )

    def has_role(self, role_name):
        # Check using boolean fields
        if role_name == "student":
            return self.is_student
        if role_name == "evaluator":
            return self.is_evaluator
        if role_name == "qp_uploader":
            return self.is_qp_uploader
        if role_name == "mentor":
            return self.is_mentor
        if role_name == "admin":
            return self.is_admin
        return False


class UserPII(models.Model):
    """
    User Personally Identifiable Information (Digital Vault).
    
    Stores sensitive personal data separately for GDPR compliance
    and security. OneToOne relationship with User model.
    """
    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        primary_key=True,
        related_name='pii'
    )
    
    # Contact Information
    phone_number = models.CharField(max_length=20, null=True, blank=True)
    
    # Personal Details
    dob = models.DateField(null=True, blank=True, verbose_name="Date of Birth")
    
    # Address Information
    address_line1 = models.CharField(max_length=255, null=True, blank=True)
    address_line2 = models.CharField(max_length=255, null=True, blank=True)
    city = models.CharField(max_length=100, null=True, blank=True)
    state = models.CharField(max_length=100, null=True, blank=True)
    country = models.CharField(max_length=100, null=True, blank=True)
    pincode = models.CharField(max_length=20, null=True, blank=True)
    
    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name = "User PII"
        verbose_name_plural = "User PII Records"

    def __str__(self):
        return f"PII for {self.user.email}"


class OrganizationMember(models.Model):
    """
    Link between a User and an Organization (Multitenant membership).
    """
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="memberships")
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name="members")
    joined_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('user', 'organization')

    def __str__(self):
        return f"{self.user.username} in {self.organization.name}"


class Role(models.Model):
    """
    RBAC Role definition.
    """
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="roles")
    name = models.CharField(max_length=100)
    description = models.TextField(null=True, blank=True)

    def __str__(self):
        return f"{self.name} ({self.tenant.name})"


class Permission(models.Model):
    """
    Granular permissions.
    """
    code = models.CharField(max_length=100, unique=True) # e.g. TEST_CREATE
    description = models.TextField(null=True, blank=True)

    def __str__(self):
        return self.code


class UserRoleAssignment(models.Model):
    """
    Assigns a Role to a User, optionally scoped to a specific entity.
    """
    SCOPE_CHOICES = [
        ('GLOBAL', 'Global'),
        ('TENANT', 'Tenant'),
        ('ORG_UNIT', 'Organization Unit'),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="role_assignments")
    role = models.ForeignKey(Role, on_delete=models.CASCADE, related_name="users")
    scope_type = models.CharField(max_length=20, choices=SCOPE_CHOICES, default='TENANT')
    scope_id = models.CharField(max_length=100, null=True, blank=True)

    def __str__(self):
        return f"{self.user.username} - {self.role.name} ({self.scope_type})"





class PaymentTransaction(models.Model):
    STATUS_CHOICES = [
        ("created", "Created"),
        ("pending", "Pending"),
        ("completed", "Completed"),
        ("failed", "Failed"),
        ("refunded", "Refunded"),
    ]

    user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="transactions"
    )
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    currency = models.CharField(max_length=3, default="USD")
    razorpay_payment_id = models.CharField(
        max_length=100, null=True, blank=True
    )
    razorpay_order_id = models.CharField(max_length=100)
    razorpay_signature = models.CharField(
        max_length=100, null=True, blank=True
    )
    razorpay_invoice_id = models.CharField(
        max_length=100, null=True, blank=True
    )
    status = models.CharField(
        max_length=20, choices=STATUS_CHOICES, default="created"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Payment Transaction"
        verbose_name_plural = "Payment Transactions"

    def __str__(self):
        return f"{self.user.email} - {self.amount} {self.currency} ({self.status})"


class UserCredit(models.Model):
    user = models.OneToOneField(
        User, on_delete=models.CASCADE, related_name="credit", primary_key=True
    )
    free_credit = models.DecimalField(
        max_digits=10, decimal_places=7, default=Decimal("50.00")
    )
    paid_credit = models.DecimalField(
        max_digits=10, decimal_places=7, default=Decimal("0.00")
    )
    last_updated = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "User Credit"
        verbose_name_plural = "User Credits"

    @property
    def total_credit(self):
        return self.free_credit + self.paid_credit

    def __str__(self):
        return f"{self.user.email} - {self.total_credit} USD"


class UsageHistory(models.Model):
    user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="usage_history"
    )
    service_type = models.CharField(max_length=50)
    input_length = models.IntegerField()
    cost = models.DecimalField(max_digits=10, decimal_places=7)
    timestamp = models.DateTimeField(auto_now_add=True)
    # reference_id = models.CharField(max_length=100, null=True, blank=True)

    class Meta:
        verbose_name = "Usage History"
        verbose_name_plural = "Usage History"
        ordering = ["-timestamp"]
        indexes = [
            models.Index(fields=["user", "timestamp"]),
            models.Index(fields=["service_type"]),
        ]

    def __str__(self):
        return f"{self.user.email} - {self.service_type} - {self.cost} USD"



def validate_pdf_size(value):
    """Validate PDF file size (max 100MB)"""
    max_size = 100 * 1024 * 1024  # 100MB
    if value.size > max_size:
        raise ValidationError(f'File size cannot exceed {max_size / (1024*1024)}MB')


class Product(models.Model):
    """Model for products/books that can be purchased"""
    title = models.CharField(max_length=255)
    description = models.TextField()
    price = models.DecimalField(max_digits=10, decimal_places=2)
    pdf_file = models.FileField(
        upload_to="products/books/",
        validators=[validate_pdf_size]
    )
    cover_image = models.ImageField(
        upload_to="products/covers/", 
        blank=True, 
        null=True
    )
    total_chapters = models.PositiveIntegerField(
        default=1, 
        help_text="Number of chapters in the book"
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Product"
        verbose_name_plural = "Products"

    def __str__(self):
        return self.title
    
    def get_file_size_mb(self):
        """Get file size in MB"""
        if self.pdf_file:
            return round(self.pdf_file.size / (1024 * 1024), 2)
        return 0


class UserPurchase(models.Model):
    """Track which users have purchased which products"""
    user = models.ForeignKey(
        User, 
        on_delete=models.CASCADE, 
        related_name="purchases"
    )
    product = models.ForeignKey(
        Product, 
        on_delete=models.CASCADE, 
        related_name="purchases"
    )
    transaction = models.ForeignKey(
        PaymentTransaction, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True,
        related_name="product_purchases"
    )
    purchased_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ["user", "product"]
        ordering = ["-purchased_at"]
        verbose_name = "User Purchase"
        verbose_name_plural = "User Purchases"

    def __str__(self):
        return f"{self.user.email} - {self.product.title}"


class UserInvitation(models.Model):
    """
    Invitation for a Lysa user to join an organization with specific roles.
    
    HODs can search the platform for users and invite them to join
    their organization with role assignments (student, evaluator, mentor, etc.).
    """
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('accepted', 'Accepted'),
        ('declined', 'Declined'),
        ('cancelled', 'Cancelled'),
        ('expired', 'Expired'),
    ]
    
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='organization_invitations'
    )
    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name='sent_invitations'
    )
    invited_by = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='invitations_sent'
    )
    
    # Roles to assign upon acceptance (e.g., ["evaluator", "mentor"])
    roles = models.JSONField(default=list)
    
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='pending'
    )
    invitation_token = models.CharField(max_length=100, unique=True)
    message = models.TextField(blank=True, default='')
    
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    accepted_at = models.DateTimeField(null=True, blank=True)
    declined_at = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['invitation_token']),
            models.Index(fields=['status', 'expires_at']),
        ]
    
    def __str__(self):
        return f"Invitation for {self.user.email} to {self.organization.name} ({self.status})"
    
    def is_expired(self):
        """Check if invitation has expired"""
        from django.utils import timezone
        return timezone.now() > self.expires_at
    
    def can_be_accepted(self):
        """Check if invitation can still be accepted"""
        return self.status == 'pending' and not self.is_expired()


class AuditLog(models.Model):
    """
    Security and Compliance Audit Trail.
    
    Tracks all significant actions in the system for security monitoring,
    compliance, and debugging purposes.
    """
    ACTION_CHOICES = [
        ('USER_LOGIN', 'User Login'),
        ('USER_LOGOUT', 'User Logout'),
        ('USER_REGISTER', 'User Registration'),
        ('USER_UPDATE', 'User Profile Update'),
        ('TEST_CREATE', 'Test Created'),
        ('TEST_UPDATE', 'Test Updated'),
        ('TEST_DELETE', 'Test Deleted'),
        ('TEST_ASSIGN', 'Test Assigned to Student'),
        ('TEST_SUBMIT', 'Test Submitted'),
        ('TEST_GRADE', 'Test Graded'),
        ('TEST_HACK_ATTEMPT', 'Test Hacking Attempt Detected'),
        ('DELEGATION_CREATE', 'Delegation Created'),
        ('DELEGATION_COMPLETE', 'Delegation Completed'),
        ('ORGANIZATION_CREATE', 'Organization Created'),
        ('ORGANIZATION_VERIFY', 'Organization Verified'),
        ('ROLE_ASSIGN', 'Role Assigned'),
        ('PERMISSION_GRANT', 'Permission Granted'),
        ('DATA_EXPORT', 'Data Export'),
        ('DATA_DELETE', 'Data Deletion'),
        ('OTHER', 'Other Action'),
    ]
    
    # Who performed the action
    actor = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='audit_actions'
    )
    
    # What action was performed
    action = models.CharField(max_length=50, choices=ACTION_CHOICES)
    
    # What was affected
    target_model = models.CharField(max_length=100, null=True, blank=True)
    target_object_id = models.CharField(max_length=100, null=True, blank=True)
    
    # Where it happened from
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(null=True, blank=True)
    
    # Additional context
    details = models.JSONField(default=dict, blank=True)
    
    # When it happened
    timestamp = models.DateTimeField(auto_now_add=True, db_index=True)
    
    class Meta:
        ordering = ['-timestamp']
        indexes = [
            models.Index(fields=['actor', 'timestamp']),
            models.Index(fields=['action', 'timestamp']),
            models.Index(fields=['target_model', 'target_object_id']),
        ]
        verbose_name = "Audit Log"
        verbose_name_plural = "Audit Logs"
    
    def __str__(self):
        actor_name = self.actor.email if self.actor else "System"
        return f"{actor_name} - {self.action} at {self.timestamp}"
    
    @classmethod
    def log_action(cls, actor, action, target_model=None, target_object_id=None, 
                   ip_address=None, user_agent=None, details=None):
        """
        Helper method to create audit log entries.
        
        Usage:
            AuditLog.log_action(
                actor=request.user,
                action='TEST_CREATE',
                target_model='Test',
                target_object_id=str(test.id),
                ip_address=get_client_ip(request),
                details={'test_name': test.title}
            )
        """
        return cls.objects.create(
            actor=actor,
            action=action,
            target_model=target_model,
            target_object_id=target_object_id,
            ip_address=ip_address,
            user_agent=user_agent,
            details=details or {}
        )

