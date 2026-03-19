"""
This module handles Django administration settings and authentication-related imports.
"""

from django.contrib import admin
from django.contrib.auth import admin as auth_admin
from django.contrib.auth import get_user_model
from django.utils.translation import gettext_lazy as _
from .models import PaymentTransaction, UserCredit, UsageHistory, Organization, Product, UserPurchase, Tenant, UserPII, OrganizationMember, AuditLog
from django.contrib.auth.admin import UserAdmin

User = get_user_model()


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ("actor", "action", "ip_address", "timestamp")
    list_filter = ("action", "timestamp")
    search_fields = ("actor__email", "action", "ip_address")
    readonly_fields = ("timestamp",)





@admin.register(Tenant)
class TenantAdmin(admin.ModelAdmin):
    list_display = ("name", "type", "created_at")
    list_filter = ("type", "created_at")
    search_fields = ("name", "id")
    readonly_fields = ("created_at",)


@admin.register(Organization)
class OrganizationAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "tenant",
        "email",
        "status",
        "is_verified",
        "created_at",
        "verified_at",
    )
    list_filter = ("status", "is_verified", "created_at", "verified_at", "tenant")
    search_fields = ("name", "email", "address", "phone_number")
    readonly_fields = ("created_at", "updated_at", "verified_at")
    fieldsets = (
        ("Basic Information", {"fields": ("tenant", "name", "email", "password")}),
        (
            "Contact Details",
            {"fields": ("address", "phone_number", "description")},
        ),
        (
            "Registration Details",
            {"fields": ("registration_date", "registration_proof")},
        ),
        (
            "Verification Status",
            {
                "fields": (
                    "status",
                    "is_verified",
                    "verification_notes",
                    "verified_by",
                    "verified_at",
                )
            },
        ),
        (
            "Timestamps",
            {"fields": ("created_at", "updated_at"), "classes": ("collapse",)},
        ),
    )

    def save_model(self, request, obj, form, change):
        if not change:  # Only hash password on creation
            obj.password = (
                obj.password
            )  # Password will be hashed in model's save method
        super().save_model(request, obj, form, change)


class UserCreditInline(admin.StackedInline):
    model = UserCredit
    can_delete = False
    verbose_name_plural = "User Credit"
    fields = ("free_credit", "paid_credit", "total_credit", "last_updated")
    readonly_fields = ("total_credit", "last_updated")


class PaymentTransactionInline(admin.TabularInline):
    model = PaymentTransaction
    extra = 0
    readonly_fields = ("created_at", "updated_at")
    fields = (
        "amount",
        "currency",
        "status",
        "created_at",
        "razorpay_order_id",
    )
    ordering = ("-created_at",)


@admin.register(UserPII)
class UserPIIAdmin(admin.ModelAdmin):
    list_display = ("user", "phone_number", "city", "country", "created_at")
    search_fields = ("user__email", "phone_number")
    list_filter = ("country", "city")

class UserPIIInline(admin.StackedInline):
    model = UserPII
    can_delete = False
    verbose_name_plural = "User PII"


class OrganizationMemberInline(admin.TabularInline):
    model = OrganizationMember
    extra = 0
    can_delete = True


@admin.register(User)
class UserAdmin(auth_admin.UserAdmin):
    """
    Custom User admin configuration.
    """

    inlines = (UserCreditInline, PaymentTransactionInline, UserPIIInline, OrganizationMemberInline)

    fieldsets = (
        (None, {"fields": ("username", "password")}),
        (
            _("Personal info"),
            {"fields": ("email", "full_name")},
        ),
        (
            _("Tenancy & Organization"),
            {
                "fields": (
                    "tenant",
                    "organization",
                    "role_org",
                ),
            },
        ),
        (
            _("Address information"),
            {
                "fields": (
                    # "country",
                    # "state",
                    # "city",
                    # "address_line1",
                    # "address_line2",
                ),
                "classes": ("collapse",), # Hide by default or just show empty group
                "description": "Moved to UserPII inline below",
            },
        ),
        (
            _("Security Information"),
            {
                "fields": (
                    "otp",
                    "otp_created_at",
                    "password_reset_token",
                    "password_reset_expires",
                    "failed_login_attempts",
                    "account_locked_until",
                ),
            },
        ),
        (
            _("Permissions and Status"),
            {
                "fields": (
                    "is_active",
                    "is_staff",
                    "is_superuser",
                    "is_qp_uploader_allowed",
                    "is_evaluator_allowed",
                    "is_premium",
                    "is_profile_completed",
                    "is_email_verified",
                    "groups",
                    "user_permissions",
                ),
            },
        ),
        (_("Important dates"), {"fields": ("last_login", "date_joined")}),
    )

    list_display = [
        "id",
        "email",
        "username",
        "full_name",
        "tenant",
        "organization",
        "role_org",
        # "country",
        # "state",
        # "city",
        # "address_line1",
        # "address_line2",
        # "phone_number",
        "is_student",
        "is_evaluator",
        "is_qp_uploader",
        "is_admin",
        "is_mentor",
        "active_role",
        "is_premium",
        "is_qp_uploader_allowed",
        "is_evaluator_allowed",
        "is_profile_completed",
        "is_email_verified",
        "is_staff",
        "last_login",
    ]

    list_filter = [
        "is_premium",
        "is_qp_uploader_allowed",
        "is_evaluator_allowed",
        "is_profile_completed",
        "is_staff",
        "is_superuser",
        "is_email_verified",
        # "country",
        # "city",
        "organization",
        "role_org",
    ]

    search_fields = [
        "username",
        "email",
        "id",
        "full_name",
        # "phone_number",
        # "organization__name",
    ]

    readonly_fields = [
        "otp_created_at",
        "password_reset_expires",
        "account_locked_until",
        "last_login",
        "date_joined",
    ]

    raw_id_fields = ["organization"]

    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": ("email", "username", "password1", "password2"),
            },
        ),
    )


@admin.register(PaymentTransaction)
class PaymentTransactionAdmin(admin.ModelAdmin):
    list_display = ("user", "amount", "currency", "status", "created_at")
    list_filter = ("status", "created_at", "currency")
    search_fields = ("user__email", "razorpay_payment_id", "razorpay_order_id")
    readonly_fields = ("created_at", "updated_at")
    fieldsets = (
        (
            "Transaction Details",
            {"fields": ("user", "amount", "currency", "status")},
        ),
        (
            "Razorpay Details",
            {
                "fields": (
                    "razorpay_payment_id",
                    "razorpay_order_id",
                    "razorpay_signature",
                    "razorpay_invoice_id",
                )
            },
        ),
        (
            "Timestamps",
            {"fields": ("created_at", "updated_at"), "classes": ("collapse",)},
        ),
    )


@admin.register(UserCredit)
class UserCreditAdmin(admin.ModelAdmin):
    list_display = (
        "user",
        "free_credit",
        "paid_credit",
        "total_credit",
        "last_updated",
    )
    list_filter = ("last_updated",)
    search_fields = ("user__email",)
    readonly_fields = ("last_updated",)


@admin.register(UsageHistory)
class UsageHistoryAdmin(admin.ModelAdmin):
    list_display = (
        "user",
        "service_type",
        "input_length",
        "cost",
        "timestamp",
    )
    list_filter = ("service_type", "timestamp")
    search_fields = ("user__email", "service_type")
    readonly_fields = ("timestamp",)
    fieldsets = (
        (
            "Usage Details",
            {"fields": ("user", "service_type", "input_length", "cost")},
        ),
        ("Timestamps", {"fields": ("timestamp",), "classes": ("collapse",)}),
    )


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ['title', 'price', 'total_chapters', 'get_file_size_mb', 'is_active', 'created_at']
    list_filter = ['is_active', 'created_at']
    search_fields = ['title', 'description']
    readonly_fields = ['created_at', 'updated_at', 'get_file_size_mb']
    
    fieldsets = (
        ('Basic Information', {
            'fields': ('title', 'description', 'price', 'total_chapters')
        }),
        ('Media Files', {
            'fields': ('cover_image', 'pdf_file', 'get_file_size_mb')
        }),
        ('Status', {
            'fields': ('is_active',)
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    def get_file_size_mb(self, obj):
        return f"{obj.get_file_size_mb()} MB"
    get_file_size_mb.short_description = 'File Size'


@admin.register(UserPurchase)
class UserPurchaseAdmin(admin.ModelAdmin):
    list_display = ['user', 'product', 'purchased_at']
    list_filter = ['purchased_at']
    search_fields = ['user__email', 'product__title']
    readonly_fields = ['purchased_at']
