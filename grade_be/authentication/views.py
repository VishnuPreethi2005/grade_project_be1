from .models import PaymentTransaction, UserCredit, UsageHistory, Product, UserPurchase
from rest_framework.views import APIView
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.response import Response
from rest_framework import status
from rest_framework_simplejwt.tokens import RefreshToken
from django.contrib.auth import authenticate
from .serializers import (
    RegisterSerializer,
    LoginSerializer,
    GoogleLoginSerializer,
    VerifyOTPSerializer,
    ResendOTPSerializer,
    ForgotPasswordSerializer,
    ResetPasswordSerializer,
    OrganizationRegistrationSerializer,
    OrganizationVerificationSerializer,
    OrganizationListSerializer,
    OrganizationRejectionSerializer,
    UserCreditSerializer,
    CreateRazorpayOrderSerializer,
    VerifyPaymentSerializer,
    ProductSerializer,
    CreateBookOrderSerializer,
)
from .utils import log_audit
from .models import User, Organization, Tenant
from django.db import transaction
import logging
from google.oauth2 import id_token
from google.auth.transport import requests
from django.conf import settings
from django.utils import timezone
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.utils.html import strip_tags
import razorpay
from decimal import Decimal, ROUND_DOWN
from rest_framework.views import APIView
from .authentication import CsrfExemptSessionAuthentication
from rest_framework import viewsets, permissions
from rest_framework.decorators import action
from django.http import FileResponse
import os
from django.contrib.auth import get_user_model
from django.core.files.storage import default_storage
from django.conf import settings
import os
import mimetypes


logger = logging.getLogger(__name__)


class VerifyOTPView(APIView):
    authentication_classes = (CsrfExemptSessionAuthentication,)
    permission_classes = [AllowAny]

    def post(self, request):
        try:
            serializer = VerifyOTPSerializer(data=request.data)
            serializer.is_valid(raise_exception=True)

            email = serializer.validated_data["email"].lower()
            otp = serializer.validated_data["otp"]

            user = User.objects.filter(email=email).first()
            if not user:
                return Response(
                    {"detail": "User not found", "code": "user_not_found"},
                    status=status.HTTP_404_NOT_FOUND,
                )

            if user.is_email_verified:
                return Response(
                    {
                        "detail": "Email already verified",
                        "code": "already_verified",
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

            if not user.verify_otp(otp):
                return Response(
                    {
                        "detail": "Invalid or expired OTP",
                        "code": "invalid_otp",
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

            user.is_email_verified = True
            user.otp = None
            user.otp_created_at = None
            user.save()

            refresh = RefreshToken.for_user(user)

            response_data = {
                "user": {
                    "id": user.id,
                    "email": user.email,
                    "username": user.username,
                    "is_email_verified": user.is_email_verified,
                },
                "tokens": {
                    "access": str(refresh.access_token),
                    "refresh": str(refresh),
                },
            }

            return Response(response_data)

        except Exception as e:
            logger.error(f"OTP verification error: {str(e)}")
            return Response(
                {"detail": str(e), "code": "otp_verification_failed"},
                status=status.HTTP_400_BAD_REQUEST,
            )


class ResendOTPView(APIView):
    authentication_classes = (CsrfExemptSessionAuthentication,)
    permission_classes = [AllowAny]

    def post(self, request):
        try:
            serializer = ResendOTPSerializer(data=request.data)
            serializer.is_valid(raise_exception=True)

            email = serializer.validated_data["email"].lower()

            user = User.objects.filter(email=email).first()
            if not user:
                return Response(
                    {"detail": "User not found", "code": "user_not_found"},
                    status=status.HTTP_404_NOT_FOUND,
                )

            if user.is_email_verified:
                return Response(
                    {
                        "detail": "Email already verified",
                        "code": "already_verified",
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

            user.generate_otp()

            # Send OTP email
            RegisterView().send_otp_email(user)

            return Response({"message": "New OTP sent to your email"})

        except Exception as e:
            logger.error(f"Resend OTP error: {str(e)}")
            return Response(
                {"detail": str(e), "code": "resend_otp_failed"},
                status=status.HTTP_400_BAD_REQUEST,
            )


class LoginView(APIView):
    authentication_classes = (CsrfExemptSessionAuthentication,)
    permission_classes = [AllowAny]

    def post(self, request):
        try:
            # Check for Google login first
            if "id_token" in request.data:
                google_serializer = GoogleLoginSerializer(data=request.data)
                google_serializer.is_valid(raise_exception=True)
                id_token_str = google_serializer.validated_data["id_token"]
                selected_role = google_serializer.validated_data.get("role", "")

                try:
                    # Verify Google token
                    idinfo = id_token.verify_oauth2_token(
                        id_token_str,
                        requests.Request(),
                        settings.GOOGLE_CLIENT_ID,
                    )

                    if idinfo["aud"] != settings.GOOGLE_CLIENT_ID:
                        return Response(
                            {
                                "detail": "Invalid audience in Google token",
                                "code": "invalid_google_token",
                            },
                            status=status.HTTP_401_UNAUTHORIZED,
                        )

                    # Get or create user
                    email = idinfo["email"].lower()

                    # Check if this is an admin email
                    is_admin = email in settings.ADMIN_EMAILS
                    user, created = User.objects.get_or_create(
                        email=email,
                        defaults={
                            "username": idinfo.get("name", email.split("@")[0]),
                            "google_id": idinfo["sub"],
                            "is_active": True,
                            "is_email_verified": True,  # Google verified emails don't need OTP
                            "is_admin": is_admin,
                        },
                    )

                    if created:
                        user.set_unusable_password()
                        user.save()
                    else:
                        # Update admin status for existing users
                        if is_admin and not user.is_admin:
                            user.is_admin = True
                            user.active_role = "admin"
                            user.save()
                        elif selected_role:
                            user.active_role = selected_role
                            user.save()
                        elif not selected_role:
                            user.active_role = ""
                            user.save()

                    # Ensure user has a tenant (Migration/Self-healing for legacy users)
                    if not user.tenant:
                        if not user.organization:
                            # Create a new Personal Tenant
                            tenant = Tenant.objects.create(
                                name=f"{user.username}'s Personal Tenant",
                                type=Tenant.Type.PERSONAL
                            )
                            user.tenant = tenant
                            user.save()
                        else:
                            # Fallback: if they belong to an org but somehow have no tenant (hybrid state), use org's tenant
                            try:
                                if user.organization.tenant:
                                    user.tenant = user.organization.tenant
                                    user.save()
                            except Exception:
                                pass

                    refresh = RefreshToken.for_user(user)

                    # Get profile picture URL
                    profile_picture_url = None
                    if user.profile_picture:
                        profile_picture_url = request.build_absolute_uri(user.profile_picture.url)

                    response_data = {
                        "user": {
                            "id": user.id,
                            "email": user.email,
                            "username": user.username,
                            "is_active": user.is_active,
                            "is_student": user.is_student,
                            "is_evaluator": user.is_evaluator,
                            "is_qp_uploader": user.is_qp_uploader,
                            "is_mentor": user.is_mentor,
                            "active_role": user.active_role,
                            "is_qp_uploader_allowed": user.is_qp_uploader_allowed,
                            "is_evaluator_allowed": user.is_evaluator_allowed,
                            "is_premium": user.is_premium,
                            "is_profile_completed": user.is_profile_completed,
                            "is_admin": user.is_admin,
                            "organization": (
                                user.organization.id if user.organization else None
                            ),
                            "organization_name": (
                                user.organization.name if user.organization else None
                            ),
                            "tenant_id": user.tenant.id if user.tenant else None,
                            "role_org": user.role_org,
                            "profile_picture_url": profile_picture_url,
                            # Add new fields
                            "is_qp_uploader_allowed": user.is_qp_uploader_allowed,
                            "is_evaluator_allowed": user.is_evaluator_allowed,
                        },
                        "tokens": {
                            "access": str(refresh.access_token),
                            "refresh": str(refresh),
                        },
                    }

                    return Response(response_data)

                except ValueError as e:
                    return Response(
                        {
                            "detail": f"Invalid Google token: {str(e)}",
                            "code": "invalid_google_token",
                        },
                        status=status.HTTP_401_UNAUTHORIZED,
                    )

            # Traditional email/password login
            serializer = LoginSerializer(data=request.data)
            serializer.is_valid(raise_exception=True)

            email = serializer.validated_data["email"].lower()
            password = serializer.validated_data["password"]
            requested_role = serializer.validated_data.get("role")

            # Check if this is an admin email
            is_admin = email in settings.ADMIN_EMAILS
            logger.info(f"Login attempt for email: {email}, is_admin: {is_admin}")

            user = authenticate(request, email=email, password=password)
            logger.info(f"Authenticated user: {user}")

            if not user:
                user = User.objects.filter(email=email).first()
                if user:
                    user.increment_failed_attempts()
                return Response(
                    {
                        "detail": "Invalid credentials",
                        "code": "invalid_credentials",
                    },
                    status=status.HTTP_401_UNAUTHORIZED,
                )

            # Update admin status if needed
            if is_admin and not user.is_admin:
                user.is_admin = True
                user.active_role = "admin"
                logger.info(f"Promoting user {user.active_role} to admin")
                user.save()

            # Set active role if provided
            if requested_role:
                user.active_role = requested_role
                logger.info(f"Setting active role for user {user.id} to {requested_role}")
                user.save()

            if (
                user.account_locked_until
                and user.account_locked_until > timezone.now()
            ):
                return Response(
                    {
                        "detail": f"Account locked until {user.account_locked_until}",
                        "code": "account_locked",
                    },
                    status=status.HTTP_403_FORBIDDEN,
                )

            if not user.is_email_verified:
                # Generate and send OTP
                user.generate_otp()
                RegisterView().send_otp_email(user)
                return Response(
                    {
                        "detail": "Email not verified. OTP sent to your email.",
                        "code": "email_not_verified",
                        "email": user.email,
                    },
                    status=status.HTTP_403_FORBIDDEN,
                )

            user.unlock_account()

            # Ensure user has a tenant (Migration/Self-healing for legacy users)
            if not user.tenant:
                if not user.organization:
                    # Create a new Personal Tenant
                    tenant = Tenant.objects.create(
                        name=f"{user.username}'s Personal Tenant",
                        type=Tenant.Type.PERSONAL
                    )
                    user.tenant = tenant
                    user.save()
                else:
                    # Fallback: key off organization
                    try:
                        if user.organization.tenant:
                            user.tenant = user.organization.tenant
                            user.save()
                    except Exception:
                        pass
                        
            refresh = RefreshToken.for_user(user)

            # Build roles array from boolean fields and admin/org
            roles = get_user_roles(user)
            logger.info(f"Roles for user {user.id}: {roles}")

            # Get profile picture URL
            profile_picture_url = None
            if user.profile_picture:
                profile_picture_url = request.build_absolute_uri(user.profile_picture.url)

            response_data = {
                "user": {
                    "id": user.id,
                    "email": user.email,
                    "username": user.username,
                    "is_active": user.is_active,
                    "is_student": user.is_student,
                    "is_evaluator": user.is_evaluator,
                    "is_qp_uploader": user.is_qp_uploader,
                    "is_mentor": user.is_mentor,
                    "active_role": user.active_role,
                    "is_premium": user.is_premium,
                    "is_profile_completed": user.is_profile_completed,
                    "is_admin": user.is_admin,
                    "organization": (
                        user.organization.id if user.organization else None
                    ),
                    "organization_name": (
                        user.organization.name if user.organization else None
                    ),
                    "tenant_id": user.tenant.id if user.tenant else None,  # [NEW] Return Tenant ID
                    "role_org": user.role_org,
                    "profile_picture_url": profile_picture_url,
                    "is_qp_uploader_allowed": user.is_qp_uploader_allowed,
                    "is_evaluator_allowed": user.is_evaluator_allowed,
                    "roles": roles,
                    "active_role": user.active_role,
                },
                "tokens": {
                    "access": str(refresh.access_token),
                    "refresh": str(refresh),
                },
            }

            return Response(response_data)

        except Exception as e:
            logger.error(f"Login error: {str(e)}")
            return Response(
                {"detail": str(e), "code": "login_failed"},
                status=status.HTTP_400_BAD_REQUEST,
            )


class RegisterView(APIView):
    authentication_classes = (CsrfExemptSessionAuthentication,)
    permission_classes = [AllowAny]

    def post(self, request):
        try:
            request_data = request.data.copy()
            account_type = request_data.get("account_type", "PERSONAL")
            org_name = request_data.get("organization_name", "")
            
            # Default roles if not provided
            if "roles" not in request_data:
                request_data["roles"] = {
                    "student": False,
                    "evaluator": False,
                    "qp_uploader": False,
                    "mentor": False,
                }

            serializer = RegisterSerializer(data=request_data)
            serializer.is_valid(raise_exception=True)

            with transaction.atomic():
                # 1. Create Tenant
                from .models import Tenant, Organization, OrganizationMember, UserPII
                
                tenant_type = Tenant.Type.ORGANIZATION if account_type == "ORGANIZATION" else Tenant.Type.PERSONAL
                tenant_name = org_name if account_type == "ORGANIZATION" else serializer.validated_data["email"]
                
                tenant = Tenant.objects.create(
                    name=tenant_name or "Default Tenant",
                    type=tenant_type
                )

                # 2. Create User linked to Tenant
                user = serializer.save()
                user.tenant = tenant
                user.save()

                # 3. Handle Organization Logic
                if account_type == "ORGANIZATION":
                    if not org_name:
                         raise ValueError("Organization name is required for Organization accounts.")
                    
                    organization = Organization.objects.create(
                        name=org_name,
                        email=user.email, # Default to admin email
                        tenant=tenant,
                        status='PENDING' # Requires Admin Approval
                    )
                    
                    # Link User to Organization as Admin/Member
                    OrganizationMember.objects.create(
                        user=user,
                        organization=organization,
                        role='ADMIN'
                    )
                    
                    # Also set the legacy organization field for backward compatibility
                    user.organization = organization
                    user.save()

                # 4. Create PII Vault
                # UserPII is created automatically via signals.py post_save handler
                # UserPII.objects.create(user=user)

                # 5. Handle Roles
                roles_dict = request_data.get("roles", {})
                if not any(roles_dict.values()):  
                    user.roles = []
                    user.active_role = ""
                    user.save()

                # Send OTP email
                self.send_otp_email(user)

                response_data = {
                    "email": user.email,
                    "tenant_id": tenant.id,
                    "message": "OTP sent to your email. Please verify to complete registration.",
                }

                return Response(response_data, status=status.HTTP_201_CREATED)

        except Exception as e:
            logger.error(f"Registration error: {str(e)}")
            return Response(
                {"detail": str(e), "code": "registration_failed"},
                status=status.HTTP_400_BAD_REQUEST,
            )

    def send_otp_email(self, user):
        subject = "Verify Your Email Address"
        html_message = render_to_string(
            "emails/otp_email.html", {"user": user, "otp": user.otp}
        )
        plain_message = strip_tags(html_message)
        from_email = settings.DEFAULT_FROM_EMAIL
        to_email = user.email

        send_mail(
            subject,
            plain_message,
            from_email,
            [to_email],
            html_message=html_message,
            fail_silently=False,
        )


class ForgotPasswordView(APIView):
    authentication_classes = (CsrfExemptSessionAuthentication,)
    permission_classes = [AllowAny]

    def post(self, request):
        try:
            serializer = ForgotPasswordSerializer(data=request.data)
            serializer.is_valid(raise_exception=True)

            email = serializer.validated_data["email"].lower()

            user = User.objects.filter(email=email).first()
            if not user:
                return Response(
                    {
                        "detail": "If this email exists, a password reset link has been sent",
                        "code": "email_not_found",
                    },
                    status=status.HTTP_200_OK,
                )  # Don't reveal if user exists

            token = user.generate_password_reset_token()

            # Send password reset email
            self.send_password_reset_email(user, token)

            return Response(
                {
                    "message": "If this email exists, a password reset link has been sent"
                }
            )

        except Exception as e:
            logger.error(f"Forgot password error: {str(e)}")
            return Response(
                {"detail": str(e), "code": "forgot_password_failed"},
                status=status.HTTP_400_BAD_REQUEST,
            )

    def send_password_reset_email(self, user, token):
        subject = "Password Reset Request"
        reset_url = f"{settings.FRONTEND_URL}/reset-password?token={token}"
        html_message = render_to_string(
            "emails/password_reset.html",
            {"user": user, "reset_url": reset_url},
        )
        plain_message = strip_tags(html_message)
        from_email = settings.DEFAULT_FROM_EMAIL
        to_email = user.email

        send_mail(
            subject,
            plain_message,
            from_email,
            [to_email],
            html_message=html_message,
            fail_silently=False,
        )


class ResetPasswordView(APIView):
    authentication_classes = (CsrfExemptSessionAuthentication,)
    permission_classes = [AllowAny]

    def post(self, request):
        try:
            serializer = ResetPasswordSerializer(data=request.data)
            serializer.is_valid(raise_exception=True)

            token = serializer.validated_data["token"]
            password = serializer.validated_data["password"]

            user = User.objects.filter(password_reset_token=token).first()
            if not user or not user.verify_password_reset_token(token):
                return Response(
                    {
                        "detail": "Invalid or expired token",
                        "code": "invalid_token",
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

            user.set_password(password)
            user.password_reset_token = None
            user.password_reset_expires = None
            user.save()

            return Response({"message": "Password reset successfully"})

        except Exception as e:
            logger.error(f"Reset password error: {str(e)}")
            return Response(
                {"detail": str(e), "code": "reset_password_failed"},
                status=status.HTTP_400_BAD_REQUEST,
            )


client = razorpay.Client(
    auth=(settings.RAZORPAY_KEY, settings.RAZORPAY_KEY_SECRET)
)


class UpdateUserRolesView(APIView):
    def post(self, request):
        try:
            logger.info("Updating user roles with data: %s", request.data)
            user_id = request.data.get("user_id")
            if not user_id:
                return Response(
                    {
                        "detail": "User ID is required",
                        "code": "user_id_required",
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

            try:
                logger.info("Fetching user with ID: %s", user_id)
                user = User.objects.get(id=user_id)
            except User.DoesNotExist:
                return Response(
                    {"detail": "User not found", "code": "user_not_found"},
                    status=status.HTTP_404_NOT_FOUND,
                )

            roles = request.data.get("roles", [])
            active_role = request.data.get("active_role", "")
            logger.info("Received roles: %s, active_role: %s", roles, active_role)

            # Validate roles
            valid_roles = ["student", "mentor", "qp_uploader", "evaluator", "admin"]
            if not all(role in valid_roles for role in roles):
                return Response(
                    {
                        "detail": "Invalid role provided",
                        "code": "invalid_role",
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

            # Validate active_role is in selected roles
            if active_role and active_role not in roles:
                return Response(
                    {
                        "detail": "Active role must be one of the selected roles",
                        "code": "invalid_active_role",
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

            # Update user boolean role fields based on roles array
            user.is_student = "student" in roles
            user.is_mentor = "mentor" in roles
            user.is_qp_uploader = "qp_uploader" in roles
            user.is_evaluator = "evaluator" in roles
            user.is_admin = "admin" in roles
            # For organization, you may need to assign an organization instance
            if "organization" in roles and not user.organization:
                # Assign to a default org or handle as needed
                org = Organization.objects.first()
                if org:
                    user.organization = org
            elif "organization" not in roles:
                user.organization = None
            user.active_role = active_role
            logger.info("Active role set to: %s", user.active_role)
            user.save()

            roles = get_user_roles(user)
            logger.info("Updated roles for user %s: %s", user_id, roles)

            # Get profile picture URL
            profile_picture_url = None
            if user.profile_picture:
                profile_picture_url = request.build_absolute_uri(user.profile_picture.url)

            response_data = {
                "message": "Roles updated successfully",
                "user": {
                    "id": user.id,
                    "email": user.email,
                    "username": user.username,
                    "is_active": user.is_active,
                    "roles": roles,
                    "active_role": user.active_role,
                    "is_premium": user.is_premium,
                    "is_profile_completed": user.is_profile_completed,
                    "is_student": user.is_student,
                    "is_mentor": user.is_mentor,
                    "is_qp_uploader": user.is_qp_uploader,
                    "is_evaluator": user.is_evaluator,
                    "is_admin": user.is_admin,
                    "organization": user.organization.id if user.organization else None,
                    "profile_picture_url": profile_picture_url,
                },
            }

            return Response(response_data, status=status.HTTP_200_OK)

        except Exception as e:
            return Response(
                {"detail": str(e), "code": "update_failed"},
                status=status.HTTP_400_BAD_REQUEST,
            )


class UpdateActiveRoleView(APIView):
    def post(self, request):
        try:
            user_id = request.data.get("user_id")
            if not user_id:
                return Response(
                    {
                        "detail": "User ID is required",
                        "code": "user_id_required",
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

            try:
                user = User.objects.get(id=user_id)
            except User.DoesNotExist:
                return Response(
                    {"detail": "User not found", "code": "user_not_found"},
                    status=status.HTTP_404_NOT_FOUND,
                )

            active_role = request.data.get("active_role", "")

            # Validate that user has this role
            roles = get_user_roles(user)
            if active_role and active_role not in roles:
                return Response(
                    {
                        "detail": f"You don't have {active_role} role assigned",
                        "code": "invalid_role",
                    },
                    status=status.HTTP_403_FORBIDDEN,
                )

            # Update active role and ensure boolean is set
            set_user_role(user, active_role, organization=user.organization)
            logger.info(f"Updating active role for user {user_id} to {active_role}")

            roles = get_user_roles(user)

            response_data = {
                "message": "Active role updated successfully",
                "user": {
                    "id": user.id,
                    "email": user.email,
                    "username": user.username,
                    "is_active": user.is_active,
                    "roles": roles,
                    "active_role": user.active_role,
                    "is_premium": user.is_premium,
                    "is_profile_completed": user.is_profile_completed,
                    "is_student": user.is_student,
                    "is_mentor": user.is_mentor,
                    "is_qp_uploader": user.is_qp_uploader,
                    "is_evaluator": user.is_evaluator,
                    "is_admin": user.is_admin,
                    "organization": user.organization.id if user.organization else None,
                },
            }

            return Response(response_data, status=status.HTTP_200_OK)

        except Exception as e:
            return Response(
                {"detail": str(e), "code": "update_failed"},
                status=status.HTTP_400_BAD_REQUEST,
            )


class UserCreditView(APIView):
    def get(self, request):
        user_credit, _ = UserCredit.objects.get_or_create(user=request.user)
        serializer = UserCreditSerializer(user_credit)
        return Response(serializer.data)


# views.py - Update the CreateRazorpayOrderView and VerifyPaymentView


class CreateRazorpayOrderView(APIView):
    def post(self, request):
        serializer = CreateRazorpayOrderSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        amount = Decimal(str(serializer.validated_data["amount"]))
        currency = "INR"  # Force INR currency

        # Convert to smallest currency unit (paise for INR)
        amount_in_subunit = int(amount * 100)

        try:
            order_data = {
                "amount": amount_in_subunit,
                "currency": currency,
                "receipt": f"order_{request.user.id}_{timezone.now().timestamp()}",
                "notes": {
                    "user_id": request.user.id,
                    "purpose": "credit_topup",
                },
                "payment_capture": "1",
            }

            razorpay_order = client.order.create(data=order_data)

            PaymentTransaction.objects.create(
                user=request.user,
                amount=amount,
                currency=currency,
                razorpay_order_id=razorpay_order["id"],
                status="created",
            )

            return Response(
                {
                    "order_id": razorpay_order["id"],
                    "amount": amount_in_subunit,
                    "currency": currency,
                }
            )

        except Exception as e:
            logger.error(f"Razorpay order creation failed: {str(e)}")
            return Response(
                {"error": "Payment gateway error"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class VerifyPaymentView(APIView):
    def post(self, request):
        serializer = VerifyPaymentSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        data = serializer.validated_data

        try:
            # Verify payment signature
            params_dict = {
                "razorpay_order_id": data["razorpay_order_id"],
                "razorpay_payment_id": data["razorpay_payment_id"],
                "razorpay_signature": data["razorpay_signature"],
            }

            client.utility.verify_payment_signature(params_dict)

            # Get transaction record
            transaction = PaymentTransaction.objects.get(
                razorpay_order_id=data["razorpay_order_id"], user=request.user
            )

            if transaction.status == "completed":
                return Response({"status": "already_processed"})

            # Convert INR to USD (using approximate rate)
            inr_amount = Decimal(str(data["amount"]))
            # Update this with current rate
            usd_amount = inr_amount * Decimal("0.012")

            # Update user credits
            user_credit, _ = UserCredit.objects.get_or_create(
                user=request.user
            )
            user_credit.paid_credit += usd_amount
            user_credit.save()

            # Update user's premium status
            request.user.is_premium = True
            request.user.save()

            # Update transaction
            transaction.razorpay_payment_id = data["razorpay_payment_id"]
            transaction.razorpay_signature = data["razorpay_signature"]
            transaction.status = "completed"
            transaction.save()

            return Response(
                {
                    "status": "success",
                    "paid_credit": float(usd_amount),
                    "new_balance": float(user_credit.total_credit),
                    "is_premium": request.user.is_premium,
                }
            )

        except Exception as e:
            logger.error(f"Payment verification failed: {str(e)}")
            return Response(
                {"error": "Payment verification failed"},
                status=status.HTTP_400_BAD_REQUEST,
            )


User = get_user_model()

@api_view(['POST'])
def update_profile(request):
    try:
        user_id = request.data.get("user_id")

        if not user_id:
            return Response(
                {"error": "User ID is required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            user = User.objects.get(id=user_id)
        except User.DoesNotExist:
            return Response(
                {"error": "User not found"}, status=status.HTTP_404_NOT_FOUND
            )

        # Update profile fields
        user.full_name = request.data.get("full_name")
        user.country = request.data.get("country")
        user.state = request.data.get("state")
        user.city = request.data.get("city")
        user.address_line1 = request.data.get("address_line1")
        user.address_line2 = request.data.get("address_line2")
        user.phone_number = request.data.get("phone_number")
        user.is_profile_completed = True
        user.save()
            
        # Log user profile update
        log_audit(
            request,
            'USER_UPDATE',
            target_model='User',
            target_id=user.id,
            user_email=user.email
        )

        return Response(
            {
                "message": "Profile updated successfully",
                "user_id": user.id,
                "is_profile_completed": user.is_profile_completed,
            },
            status=status.HTTP_200_OK,
        )

    except Exception as e:
        return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def update_profile_pic(request):
    """Update user profile including profile picture"""
    try:
        user = request.user
        
        # Handle profile picture upload
        if 'profile_picture' in request.FILES:
            profile_picture = request.FILES['profile_picture']
            
            # Validate file type
            allowed_types = ['image/jpeg', 'image/jpg', 'image/png', 'image/gif']
            if profile_picture.content_type not in allowed_types:
                return Response(
                    {'error': 'Invalid file type. Please upload a valid image.'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # Validate file size (5MB max)
            if profile_picture.size > 5 * 1024 * 1024:
                return Response(
                    {'error': 'File size too large. Maximum size is 5MB.'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # Delete old profile picture if exists
            if user.profile_picture:
                try:
                    default_storage.delete(user.profile_picture.name)
                except:
                    pass  # Ignore if file doesn't exist
            
            # Save new profile picture
            user.profile_picture = profile_picture
            user.save()
            
            # Return the full URL
            profile_picture_url = request.build_absolute_uri(user.profile_picture.url)
            
            return Response({
                'message': 'Profile picture updated successfully',
                'profile_picture_url': profile_picture_url
            }, status=status.HTTP_200_OK)
        
        # Handle other profile fields
        data = request.data
        updatable_fields = ['full_name', 'country', 'state', 'city', 'address_line1', 'address_line2', 'phone_number']
        
        for field in updatable_fields:
            if field in data:
                setattr(user, field, data[field])
        
        user.save()
        
        return Response({
            'message': 'Profile updated successfully'
        }, status=status.HTTP_200_OK)
        
    except Exception as e:
        return Response(
            {'error': str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['DELETE'])
@permission_classes([IsAuthenticated])
def delete_profile_picture(request):
    """Delete user's profile picture"""
    try:
        user = request.user
        
        # Check if user has a profile picture
        if not user.profile_picture:
            return Response(
                {'error': 'No profile picture to delete'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Delete the file from storage
        try:
            default_storage.delete(user.profile_picture.name)
        except Exception as e:
            logger.warning(f"Failed to delete profile picture file: {e}")
            # Continue even if file deletion fails
        
        # Remove profile picture reference from user
        user.profile_picture = None
        user.save()
        
        return Response({
            'message': 'Profile picture deleted successfully'
        }, status=status.HTTP_200_OK)
        
    except Exception as e:
        logger.error(f"Error deleting profile picture: {e}")
        return Response(
            {'error': str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(["POST"])
def add_role(request):
    """
    Add a new role (string) to the user's JSONField roles list.
    """
    try:
        user_id = request.data.get("user_id")
        new_role = request.data.get("new_role")  
 
        if not user_id or not new_role:
            return Response(
                {"error": "User ID and role are required."},
                status=status.HTTP_400_BAD_REQUEST,
            )
 
        user = User.objects.get(id=user_id)
        role_map = {
            "student": lambda user: user.is_student,
            "mentor": lambda user: user.is_mentor,
            "qp_uploader": lambda user: user.is_qp_uploader and user.is_qp_uploader_allowed,
            "evaluator": lambda user: user.is_evaluator and user.is_evaluator_allowed,
        }
 
        assign_map = {
            "student": lambda user: setattr(user, "is_student", True),
            "mentor": lambda user: setattr(user, "is_mentor", True),
            "qp_uploader": lambda user: setattr(user, "is_qp_uploader", True),
            "evaluator": lambda user: setattr(user, "is_evaluator", True),
        }
 
        if new_role in role_map:
            if role_map[new_role](user):
                return Response(
                    {"message": "User already has this role."},
                    status=status.HTTP_400_BAD_REQUEST
                )
            assign_map[new_role](user)
        user.save()
        
        # Log password reset
        log_audit(
            request,
            'USER_UPDATE',
            target_model='User',
            target_id=user.id,
            action_detail='password_reset'
        )

        return Response(
            {"detail": "Password reset successful. You can now log in with your new password."},
            status=status.HTTP_200_OK,
        )
 
        return Response(
            {"message": "Role added successfully."}, status=status.HTTP_200_OK
        )
 
    except User.DoesNotExist:
        return Response(
            {"error": "User not found."}, status=status.HTTP_404_NOT_FOUND
        )
    except Exception as e:
        return Response(
            {"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


class BillingInfoView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        try:
            # Get user's credit information
            user_credit = UserCredit.objects.get(user=request.user)

            # Get all payment transactions for the user
            transactions = PaymentTransaction.objects.filter(
                user=request.user, status="completed"
            ).order_by("-created_at")

            # Get usage history grouped by service type
            usage_history = UsageHistory.objects.filter(
                user=request.user
            ).order_by("-timestamp")

            # Group usage by service type
            service_usage = {}
            total_usage_cost = Decimal("0.00")

            # Define service types and their display names
            service_types = {
                "entity": "Entity Recognition",
                "translation": "Translation",
                "emailwriter": "Email Writer",
                "summarization": "Text Summarization",
                "grading": "Answer Grading",
                "evaluation": "Evaluation",
            }

            for usage in usage_history:
                service_type = usage.service_type
                if service_type not in service_usage:
                    service_usage[service_type] = {
                        "total_cost": Decimal("0.00"),
                        "total_input_length": 0,
                        "usage_count": 0,
                        "last_used": None,
                        "history": [],
                    }

                service_usage[service_type]["total_cost"] += usage.cost
                service_usage[service_type][
                    "total_input_length"
                ] += usage.input_length
                service_usage[service_type]["usage_count"] += 1
                service_usage[service_type]["last_used"] = usage.timestamp
                service_usage[service_type]["history"].append(
                    {
                        "timestamp": usage.timestamp,
                        "input_length": usage.input_length,
                        "cost": float(usage.cost),
                        # 'reference_id': usage.reference_id
                    }
                )
                total_usage_cost += usage.cost

            # Format transactions for response
            transaction_history = []
            for transaction in transactions:
                transaction_history.append(
                    {
                        "id": transaction.id,
                        "date": transaction.created_at,
                        "amount": float(transaction.amount),
                        "currency": transaction.currency,
                        "status": transaction.status,
                        "invoice_id": transaction.razorpay_invoice_id,
                        "order_id": transaction.razorpay_order_id,
                    }
                )

            # Calculate total paid amount
            total_paid = sum(
                Decimal(str(t["amount"]))
                for t in transaction_history
                if t["currency"] == "USD"
            )

            # Format service usage with display names
            formatted_service_usage = {}
            for service_type, data in service_usage.items():
                display_name = service_types.get(
                    service_type, service_type.title()
                )
                formatted_service_usage[display_name] = {
                    "total_cost": float(data["total_cost"]),
                    "total_input_length": data["total_input_length"],
                    "usage_count": data["usage_count"],
                    "last_used": data["last_used"],
                    # Last 5 usage records
                    "recent_history": data["history"][:5],
                }

            # Prepare response data
            response_data = {
                "credits": {
                    "total_available": float(user_credit.total_credit),
                    "free_credits": float(user_credit.free_credit),
                    "paid_credits": float(user_credit.paid_credit),
                    "last_updated": user_credit.last_updated,
                },
                "usage_summary": {
                    "total_usage_cost": float(total_usage_cost),
                    "total_paid_amount": float(total_paid),
                    "services": formatted_service_usage,
                },
                "payment_history": transaction_history,
            }

            return Response(response_data)

        except UserCredit.DoesNotExist:
            # Create UserCredit if it doesn't exist
            user_credit = UserCredit.objects.create(user=request.user)
            return Response(
                {
                    "credits": {
                        "total_available": float(user_credit.total_credit),
                        "free_credits": float(user_credit.free_credit),
                        "paid_credits": float(user_credit.paid_credit),
                        "last_updated": user_credit.last_updated,
                    },
                    "usage_summary": {
                        "total_usage_cost": 0.0,
                        "total_paid_amount": 0.0,
                        "services": {},
                    },
                    "payment_history": [],
                }
            )
        except Exception as e:
            logger.error(f"Error fetching billing info: {str(e)}")
            return Response(
                {"error": "Failed to fetch billing information"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class IsAdminUser(permissions.BasePermission):
    def has_permission(self, request, view):
        return bool(request.user and request.user.is_admin)


class OrganizationRegistrationViewSet(viewsets.ModelViewSet):
    queryset = Organization.objects.all()
    serializer_class = OrganizationRegistrationSerializer
    permission_classes = [permissions.AllowAny]  # Allow anyone to register

    def get_serializer_class(self):
        if self.action == "verify":
            return OrganizationVerificationSerializer
        elif self.action == "reject":
            return OrganizationRejectionSerializer
        elif self.action == "list":
            return OrganizationListSerializer
        return self.serializer_class

    def get_permissions(self):
        if self.action in ["verify", "reject", "list"]:
            return [IsAdminUser()]
        return super().get_permissions()

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        organization = serializer.save()

        return Response(
            {
                "status": "success",
                "message": "Organization registered successfully. Waiting for admin verification.",
                "data": {
                    "id": organization.id,
                    "name": organization.name,
                    "email": organization.email,
                },
            },
            status=status.HTTP_201_CREATED,
        )

    @action(detail=True, methods=["post"])
    def verify(self, request, pk=None):
        try:
            organization = self.get_object()
            serializer = self.get_serializer(data=request.data)
            serializer.is_valid(raise_exception=True)

            # Verify the organization
            organization.verify_organization(
                admin_user=request.user,
                notes=serializer.validated_data.get("verification_notes"),
            )

            # Find and update the user with the organization's email
            try:
                user = User.objects.get(email=organization.email)
                user.organization = organization
                user.role_org = "admin"
                user.save()
            except User.DoesNotExist:
                return Response(
                    {
                        "status": "error",
                        "message": "No user found with the organization email",
                    },
                    status=status.HTTP_404_NOT_FOUND,
                )

            return Response(
                {
                    "status": "success",
                    "message": "Organization verified successfully and user updated",
                    "data": OrganizationListSerializer(organization).data,
                }
            )
        except Exception as e:
            return Response(
                {"status": "error", "message": str(e)},
                status=status.HTTP_400_BAD_REQUEST,
            )

    @action(detail=True, methods=["post"])
    def reject(self, request, pk=None):
        try:
            organization = self.get_object()
            serializer = self.get_serializer(data=request.data)
            serializer.is_valid(raise_exception=True)

            # Store the organization data before deletion for the response
            org_data = OrganizationListSerializer(organization).data

            # Delete the organization
            organization.delete()

            return Response(
                {
                    "status": "success",
                    "message": "Organization registration rejected and removed",
                    "data": org_data,
                }
            )
        except Exception as e:
            return Response(
                {"status": "error", "message": str(e)},
                status=status.HTTP_400_BAD_REQUEST,
            )

    def list(self, request, *args, **kwargs):
        # Get all organizations
        queryset = self.get_queryset()

        # Filter out organizations that already have an admin user
        filtered_queryset = []
        for org in queryset:
            # Check if any user has this organization and role_org as admin
            has_admin = User.objects.filter(
                organization=org, role_org="admin"
            ).exists()

            if not has_admin:
                filtered_queryset.append(org)

        serializer = self.get_serializer(filtered_queryset, many=True)
        return Response({"status": "success", "data": serializer.data})

    @action(detail=True, methods=["get"])
    def view_document(self, request, pk=None):
        try:
            organization = self.get_object()
            if not organization.registration_proof:
                return Response(
                    {
                        "status": "error",
                        "message": "No registration document found",
                    },
                    status=status.HTTP_404_NOT_FOUND,
                )

            file_path = os.path.join(
                settings.MEDIA_ROOT, str(organization.registration_proof)
            )
            if not os.path.exists(file_path):
                return Response(
                    {"status": "error", "message": "Document file not found"},
                    status=status.HTTP_404_NOT_FOUND,
                )

            return FileResponse(open(file_path, "rb"), as_attachment=False)
        except Exception as e:
            return Response(
                {"status": "error", "message": str(e)},
                status=status.HTTP_400_BAD_REQUEST,
            )


@api_view(["POST"])
def check_user_exists(request):
    """
    Check if a user with the given email exists
    """
    email = request.data.get("email")
    if not email:
        return Response(
            {"detail": "Email is required"}, status=status.HTTP_400_BAD_REQUEST
        )

    exists = User.objects.filter(email=email).exists()
    return Response({"exists": exists})


@api_view(["GET"])
def user_count(request):
    User = get_user_model()
    return Response({"count": User.objects.count()})


@api_view(["GET"])
def user_role_counts(request):
    User = get_user_model()
    users = User.objects.all()
    student_count = 0
    evaluator_count = 0
    qp_uploader_count = 0
    mentor_count = 0
    organization_count = 0
    for user in users:
        if getattr(user, 'is_student', False):
            student_count += 1
        if getattr(user, 'is_evaluator', False):
            evaluator_count += 1
        if getattr(user, 'is_qp_uploader', False):
            qp_uploader_count += 1
        if getattr(user, 'is_mentor', False):
            mentor_count += 1
        if getattr(user, 'organization', None):
            organization_count += 1
    return Response(
        {
            "student": student_count,
            "evaluator": evaluator_count,
            "qp_uploader": qp_uploader_count,
            "mentor": mentor_count,
            "organization": organization_count,
        }
    )


def get_user_roles(user):
    roles = []
    if getattr(user, 'is_student', False):
        roles.append("student")
    if getattr(user, 'is_mentor', False):
        roles.append("mentor")
    if getattr(user, 'is_evaluator', False):
        roles.append("evaluator")
    if getattr(user, 'is_qp_uploader', False):
        roles.append("qp_uploader")
    if getattr(user, 'is_admin', False):
        roles.append("admin")
    if getattr(user, 'organization', None):
        roles.append("organization")
    
    # [NEW] Add Dynamic RBAC Roles
    try:
        from .models import UserRoleAssignment
        rbac_assignments = UserRoleAssignment.objects.filter(user=user)
        for assignment in rbac_assignments:
            role_name = assignment.role.name
            if role_name not in roles:
                roles.append(role_name)
    except Exception:
        pass # Handle migration/import issues gracefully
        
    return roles


def set_user_role(user, role, organization=None):
    if role == "student":
        user.is_student = True
    elif role == "mentor":
        user.is_mentor = True
    elif role == "evaluator":
        user.is_evaluator = True
    elif role == "qp_uploader":
        user.is_qp_uploader = True
    elif role == "admin":
        user.is_admin = True
    elif role == "organization" and organization:
        user.organization = organization
    user.active_role = role
    user.save()


class ProductListView(APIView):
    """List all active products/books"""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        products = Product.objects.filter(is_active=True)
        serializer = ProductSerializer(
            products, 
            many=True, 
            context={"request": request}
        )
        return Response(serializer.data)


class CreateBookOrderView(APIView):
    """Create a Razorpay order for a book purchase"""
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = CreateBookOrderSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        product_id = serializer.validated_data["product_id"]
        
        try:
            product = Product.objects.get(id=product_id, is_active=True)
        except Product.DoesNotExist:
            return Response(
                {"error": "Product not found"},
                status=status.HTTP_404_NOT_FOUND
            )
        
        # Check if user already purchased this product
        if UserPurchase.objects.filter(user=request.user, product=product).exists():
            return Response(
                {"error": "You have already purchased this product"},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Validate and convert price to Decimal (same pattern as credit upgrade)
        if product.price is None:
            return Response(
                {"error": "Product price is not set"},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            # product.price is a DecimalField, which is already a Decimal in Django
            # Use it directly or convert safely
            if isinstance(product.price, Decimal):
                amount = product.price
            elif hasattr(product.price, '__float__'):
                # Convert through float to avoid InvalidOperation
                amount = Decimal(str(float(product.price)))
            else:
                # Fallback: convert to string then to Decimal
                amount = Decimal(str(product.price))
        except (ValueError, TypeError, Exception) as e:
            logger.error(f"Invalid product price conversion: {product.price}, type: {type(product.price)}, error: {str(e)}", exc_info=True)
            return Response(
                {"error": "Invalid product price"},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        currency = "INR"
        amount_in_subunit = int(amount * 100)
        
        try:
            order_data = {
                "amount": amount_in_subunit,
                "currency": currency,
                "receipt": f"book_{product.id}_{request.user.id}_{timezone.now().timestamp()}",
                "notes": {
                    "user_id": request.user.id,
                    "product_id": product.id,
                    "purpose": "book_purchase",
                },
                "payment_capture": "1",
            }
            
            razorpay_order = client.order.create(data=order_data)
            
            # PaymentTransaction.amount now has max_digits=12, decimal_places=2
            # This allows amounts up to 9999999999.99 (sufficient for book prices)
            # Ensure amount is a valid Decimal (same pattern as credit upgrade)
            if not isinstance(amount, Decimal):
                amount = Decimal(str(amount))
            
            PaymentTransaction.objects.create(
                user=request.user,
                amount=amount,
                currency=currency,
                razorpay_order_id=razorpay_order["id"],
                status="created",
            )
            
            return Response(
                {
                    "order_id": razorpay_order["id"],
                    "amount": amount_in_subunit,
                    "currency": currency,
                    "product": ProductSerializer(product, context={"request": request}).data,
                }
            )
        except Exception as e:
            logger.error(f"Razorpay order creation failed: {str(e)}", exc_info=True)
            return Response(
                {"error": f"Payment gateway error: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class VerifyBookPaymentView(APIView):
    """Verify payment for book purchase and grant access"""
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = VerifyPaymentSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        data = serializer.validated_data
        
        try:
            # Verify payment signature
            params_dict = {
                "razorpay_order_id": data["razorpay_order_id"],
                "razorpay_payment_id": data["razorpay_payment_id"],
                "razorpay_signature": data["razorpay_signature"],
            }
            
            client.utility.verify_payment_signature(params_dict)
            
            # Get transaction record
            transaction = PaymentTransaction.objects.get(
                razorpay_order_id=data["razorpay_order_id"],
                user=request.user
            )
            
            if transaction.status == "completed":
                return Response({"status": "already_processed"})
            
            # Get product from request
            product_id = request.data.get("product_id")
            if not product_id:
                return Response(
                    {"error": "Product ID is required"},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            try:
                product = Product.objects.get(id=product_id, is_active=True)
            except Product.DoesNotExist:
                return Response(
                    {"error": "Product not found"},
                    status=status.HTTP_404_NOT_FOUND
                )
            
            # Create purchase record
            purchase, created = UserPurchase.objects.get_or_create(
                user=request.user,
                product=product,
                defaults={"transaction": transaction}
            )
            
            if not created:
                return Response({"status": "already_purchased"})
            
            # Update transaction
            transaction.razorpay_payment_id = data["razorpay_payment_id"]
            transaction.razorpay_signature = data["razorpay_signature"]
            transaction.status = "completed"
            transaction.save()
            
            return Response(
                {
                    "status": "success",
                    "message": "Book purchased successfully",
                    "product": ProductSerializer(product, context={"request": request}).data,
                }
            )
        except Exception as e:
            logger.error(f"Payment verification failed: {str(e)}")
            return Response(
                {"error": "Payment verification failed"},
                status=status.HTTP_400_BAD_REQUEST,
            )


class UserPurchasesView(APIView):
    """Get all books purchased by the user"""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        purchases = UserPurchase.objects.filter(
            user=request.user
        ).select_related("product")
        products = [purchase.product for purchase in purchases]
        serializer = ProductSerializer(
            products, 
            many=True, 
            context={"request": request}
        )
        return Response(serializer.data)


class BookPDFAccessView(APIView):
    """
    SECURE PDF ACCESS ENDPOINT
    Serves PDF files with authentication and purchase verification.
    Prevents direct download by using 'inline' content disposition.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request, product_id):
        try:
            product = Product.objects.get(id=product_id, is_active=True)
        except Product.DoesNotExist:
            return Response(
                {"error": "Book not found"},
                status=status.HTTP_404_NOT_FOUND
            )
        
        # SECURITY CHECK: Verify user has purchased this book
        if not UserPurchase.objects.filter(user=request.user, product=product).exists():
            return Response(
                {"error": "You need to purchase this book to access it"},
                status=status.HTTP_403_FORBIDDEN
            )
        
        # Get the PDF file path
        pdf_path = product.pdf_file.path
        
        if not os.path.exists(pdf_path):
            return Response(
                {"error": "PDF file not found on server"},
                status=status.HTTP_404_NOT_FOUND
            )
        
        # SECURE STREAMING: Open and stream the PDF file
        try:
            pdf_file = open(pdf_path, 'rb')
            
            # Determine content type
            content_type = mimetypes.guess_type(pdf_path)[0] or 'application/pdf'
            
            # Create response with inline disposition (view, not download)
            response = FileResponse(
                pdf_file,
                content_type=content_type,
                as_attachment=False  # KEY: This prevents download
            )
            
            # SECURITY HEADERS: Prevent download and caching
            response['Content-Disposition'] = 'inline; filename="book.pdf"'  # inline = view in browser
            response['X-Content-Type-Options'] = 'nosniff'
            response['Content-Security-Policy'] = "default-src 'self'"
            
            # Cache control to prevent unauthorized caching
            response['Cache-Control'] = 'private, no-cache, no-store, must-revalidate'
            response['Pragma'] = 'no-cache'
            response['Expires'] = '0'
            
            return response
            
        except Exception as e:
            logger.error(f"Error serving PDF: {str(e)}")
            return Response(
                {"error": "Error accessing PDF file"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
