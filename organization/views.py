from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action
from rest_framework.response import Response
from .delegation_views import DelegationViewSet  # Import delegation views
from rest_framework.views import APIView
from rest_framework.exceptions import AuthenticationFailed
from authentication.models import User, Organization
from .serializers import (
    StudentSerializer,
    AddStudentSerializer,
    TestSerializer,
    QuestionPaperSerializer,
    TestAssignmentSerializer,
    BulkAddStudentSerializer,
    OrganizationHierarchyLevelSerializer,
    HierarchyValueSerializer,
    UserHierarchyMembershipSerializer,
    UserHierarchyMembershipDetailSerializer,
    AssignmentDetailSerializer,
    AssignmentCreateSerializer,
    SubmissionSerializer,
    GradeSubmissionSerializer,
    AssignmentDetailSerializer,
)
from .models import (
    Test,
    QuestionPaper,
    TestAssignment,
    StudentInvitation,
    TestQuestion,
    StudentAnswer,
    OrganizationHierarchyLevel,
    HierarchyValue,
    UserHierarchyMembership,
    Assignment,
    Submission,
    SubmissionFile,
    AssignmentAttachment
)
from .grading_service import OrganizationGradingService
from django.utils import timezone
from django.db import transaction
from django.core.mail import send_mail
from django.conf import settings
from django.template.loader import render_to_string
from django.utils.html import strip_tags
from grade.models import Notification, AnswerUpload, GradingResult
from django.db.models import Prefetch
import csv
import io
from rest_framework import serializers
from django.utils import timezone
import datetime
import json
from django.db import IntegrityError
from .serializers import SubmissionFileSerializer
from authentication.serializers import OrganizationListSerializer
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from typing import Any
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
import logging


logger = logging.getLogger(__name__)

class IsOrgAdmin(permissions.BasePermission):
    """
    Custom permission to only allow organization admins.
    """
    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.role_org == 'admin'


class StudentManagementViewSet(viewsets.ViewSet):
    """Manages students in an organization.

    This ViewSet handles listing, inviting, removing, and handling student
    invitations.
    """
    permission_classes = [permissions.IsAuthenticated]

    def get_permissions(self) -> list:
        """Gets the permissions for the current action.

        Returns:
            A list of permission classes for the action.
        """
        if self.action == "accept_invitation":
            return [permissions.AllowAny()]
        return [permissions.IsAuthenticated()]

    def list(self, request: Request) -> Response:
        """Lists all students in the organization.

        Args:
            request: The HTTP request object.

        Returns:
            A Response object containing the list of students or an error message.
        """
        logger.info(
            f"Listing students for organization '{request.user.organization.name if request.user.organization else 'N/A'}'"
        )
        try:
            if not request.user.is_authenticated:
                raise AuthenticationFailed(
                    "Authentication credentials were not provided."
                )

            if not request.user.organization:
                return Response(
                    {
                        "status": "error",
                        "code": status.HTTP_400_BAD_REQUEST,
                        "message": "You are not associated with any organization",
                        "data": None,
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

            students = User.objects.filter(
                organization=request.user.organization, role_org="student"
            )
            serializer = StudentSerializer(students, many=True)
            return Response(
                {
                    "status": "success",
                    "code": status.HTTP_200_OK,
                    "message": "Students retrieved successfully",
                    "data": serializer.data,
                },
                status=status.HTTP_200_OK,
            )

        except AuthenticationFailed as e:
            logger.error(f"Error listing students: {e}", exc_info=True)
            return Response(
                {
                    "status": "error",
                    "code": status.HTTP_401_UNAUTHORIZED,
                    "message": str(e),
                    "data": None,
                },
                status=status.HTTP_401_UNAUTHORIZED,
            )
        except Exception as e:
            logger.error(f"Error listing students: {e}", exc_info=True)
            return Response(
                {
                    "status": "error",
                    "code": status.HTTP_500_INTERNAL_SERVER_ERROR,
                    "message": str(e),
                    "data": None,
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    def create(self, request: Request) -> Response:
        """Sends invitation(s) to student(s).

        Args:
            request: The HTTP request object.

        Returns:
            A Response object indicating the result of the invitation(s).
        """
        logger.info(
            f"Create student/invitation request received for organization '{request.user.organization.name if request.user.organization else 'N/A'}'"
        )
        try:
            if not request.user.is_authenticated:
                raise AuthenticationFailed(
                    "Authentication credentials were not provided."
                )

            if not request.user.organization:
                return Response(
                    {
                        "status": "error",
                        "code": status.HTTP_400_BAD_REQUEST,
                        "message": "You are not associated with any organization",
                        "data": None,
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

            if not request.user.role_org == "admin":
                return Response(
                    {
                        "status": "error",
                        "code": status.HTTP_403_FORBIDDEN,
                        "message": "Only organization admins can invite students",
                        "data": None,
                    },
                    status=status.HTTP_403_FORBIDDEN,
                )

            # Check if this is a bulk invitation request
            if "emails" in request.data:
                return self._handle_bulk_invitation(request)
            else:
                return self._handle_single_invitation(request)

        except AuthenticationFailed as e:
            logger.error(f"Error creating invitation: {e}", exc_info=True)
            return Response(
                {
                    "status": "error",
                    "code": status.HTTP_401_UNAUTHORIZED,
                    "message": str(e),
                    "data": None,
                },
                status=status.HTTP_401_UNAUTHORIZED,
            )
        except Exception as e:
            logger.error(f"Error creating invitation: {e}", exc_info=True)
            return Response(
                {
                    "status": "error",
                    "code": status.HTTP_500_INTERNAL_SERVER_ERROR,
                    "message": str(e),
                    "data": None,
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    def _handle_single_invitation(self, request: Request) -> Response:
        """Handles a single student invitation.

        Args:
            request: The HTTP request object.

        Returns:
            A Response object indicating the result of the invitation.
        """
        logger.info(f"Handling single invitation for email: {request.data.get('email')}")
        try:
            serializer = AddStudentSerializer(data=request.data)
            if serializer.is_valid():
                email = serializer.validated_data["email"]
                try:
                    # Check if user already exists in the organization
                    if User.objects.filter(
                        email=email, organization=request.user.organization
                    ).exists():
                        return Response(
                            {
                                "status": "error",
                                "code": status.HTTP_400_BAD_REQUEST,
                                "message": "This user is already a member of your organization",
                                "data": None,
                            },
                            status=status.HTTP_400_BAD_REQUEST,
                        )

                    # Check if there's already a pending invitation
                    if StudentInvitation.objects.filter(
                        email=email,
                        organization=request.user.organization,
                        status="pending",
                    ).exists():
                        return Response(
                            {
                                "status": "error",
                                "code": status.HTTP_400_BAD_REQUEST,
                                "message": "An invitation has already been sent to this email",
                                "data": None,
                            },
                            status=status.HTTP_400_BAD_REQUEST,
                        )

                    # Create invitation
                    invitation = StudentInvitation.objects.create(
                        email=email, organization=request.user.organization
                    )

                    # Send invitation email
                    self._send_invitation_email(
                        request.user.organization, email, invitation
                    )

                    return Response(
                        {
                            "status": "success",
                            "code": status.HTTP_200_OK,
                            "message": "Invitation sent successfully",
                            "data": {
                                "email": email,
                                "expires_at": invitation.expires_at,
                            },
                        },
                        status=status.HTTP_200_OK,
                    )
                except Exception as e:
                    logger.error(f"Error in _handle_single_invitation: {str(e)}", exc_info=True)
                    return Response(
                        {
                            "status": "error",
                            "code": status.HTTP_500_INTERNAL_SERVER_ERROR,
                            "message": f"Internal server error: {str(e)}",
                            "data": None,
                        },
                        status=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    )
            return Response(
                {
                    "status": "error",
                    "code": status.HTTP_400_BAD_REQUEST,
                    "message": "Invalid data provided",
                    "data": serializer.errors,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        except Exception as e:
            logger.error(f"Unexpected error in _handle_single_invitation: {str(e)}", exc_info=True)
            return Response(
                {
                    "status": "error",
                    "code": status.HTTP_500_INTERNAL_SERVER_ERROR,
                    "message": f"Internal server error: {str(e)}",
                    "data": None,
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    def _handle_bulk_invitation(self, request: Request) -> Response:
        """Handles bulk student invitations.

        Args:
            request: The HTTP request object.

        Returns:
            A Response object with the results of the bulk invitation.
        """
        logger.info("Handling bulk invitation.")
        serializer = BulkAddStudentSerializer(data=request.data)
        if not serializer.is_valid():
            logger.warning(f"Bulk invitation validation failed: {serializer.errors}")
            return Response(
                {
                    "status": "error",
                    "code": status.HTTP_400_BAD_REQUEST,
                    "message": "Invalid data provided",
                    "data": serializer.errors,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        emails = serializer.validated_data["emails"]
        results = {
            "success": [],
            "already_member": [],
            "already_invited": [],
            "invalid": [],
        }

        with transaction.atomic():
            for email in emails:
                try:
                    # Check if user already exists in the organization
                    if User.objects.filter(
                        email=email, organization=request.user.organization
                    ).exists():
                        results["already_member"].append(email)
                        continue

                    # Check if there's already a pending invitation
                    if StudentInvitation.objects.filter(
                        email=email,
                        organization=request.user.organization,
                        status="pending",
                    ).exists():
                        results["already_invited"].append(email)
                        continue

                    # Create invitation
                    invitation = StudentInvitation.objects.create(
                        email=email, organization=request.user.organization
                    )

                    # Send invitation email
                    self._send_invitation_email(
                        request.user.organization, email, invitation
                    )
                    results["success"].append(email)

                except Exception as e:
                    logger.error(f"Error processing email {email} in bulk invitation: {e}", exc_info=True)
                    results["invalid"].append(email)
                    continue

        return Response(
            {
                "status": "success",
                "code": status.HTTP_200_OK,
                "message": "Bulk invitation process completed",
                "data": {
                    "success_count": len(results["success"]),
                    "already_member_count": len(results["already_member"]),
                    "already_invited_count": len(results["already_invited"]),
                    "invalid_count": len(results["invalid"]),
                    "details": results,
                },
            },
            status=status.HTTP_200_OK,
        )

    def _send_invitation_email(self, organization, email: str, invitation) -> None:
        """Sends an invitation email to a student.

        Args:
            organization: The organization sending the invitation.
            email: The email address of the student.
            invitation: The StudentInvitation object.
        """
        logger.info(f"Sending invitation email to {email} for organization {organization.name}")
        context = {
            "organization_name": organization.name,
            "invitation_link": f"{settings.FRONTEND_URL}/accept-invitation/{invitation.token}",
            "expires_at": invitation.expires_at,
        }

        html_message = render_to_string(
            "email/student_invitation.html", context
        )
        plain_message = strip_tags(html_message)

        send_mail(
            f"Invitation to join {organization.name}",
            plain_message,
            settings.DEFAULT_FROM_EMAIL,
            [email],
            html_message=html_message,
            fail_silently=False,
        )

    @action(detail=False, methods=["get"])
    def pending_invitations(self, request: Request) -> Response:
        """Lists all pending invitations for the organization.

        Args:
            request: The HTTP request object.

        Returns:
            A Response object containing a list of pending invitations.
        """
        logger.info("Fetching pending invitations.")
        try:
            if (
                not request.user.is_authenticated
                or not request.user.role_org == "admin"
            ):
                raise AuthenticationFailed(
                    "Authentication credentials were not provided."
                )

            invitations = StudentInvitation.objects.filter(
                organization=request.user.organization, status="pending"
            ).order_by("-created_at")

            data = [
                {
                    "id": inv.id,
                    "email": inv.email,
                    "created_at": inv.created_at,
                    "expires_at": inv.expires_at,
                    "status": inv.status,
                }
                for inv in invitations
            ]

            return Response(
                {
                    "status": "success",
                    "code": status.HTTP_200_OK,
                    "message": "Pending invitations retrieved successfully",
                    "data": data,
                },
                status=status.HTTP_200_OK,
            )

        except Exception as e:
            logger.error(f"Error fetching pending invitations: {e}", exc_info=True)
            return Response(
                {
                    "status": "error",
                    "code": status.HTTP_500_INTERNAL_SERVER_ERROR,
                    "message": str(e),
                    "data": None,
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @action(detail=True, methods=["post"])
    def cancel_invitation(self, request: Request, pk: int = None) -> Response:
        """Cancels a pending invitation.

        Args:
            request: The HTTP request object.
            pk: The primary key of the invitation to cancel.

        Returns:
            A Response object indicating the result of the cancellation.
        """
        logger.info(f"Canceling invitation with pk={pk}")
        try:
            if (
                not request.user.is_authenticated
                or not request.user.role_org == "admin"
            ):
                raise AuthenticationFailed(
                    "Authentication credentials were not provided."
                )
            try:
                invitation = StudentInvitation.objects.get(
                    pk=pk, organization=request.user.organization, status="pending"
                )
                invitation.status = "rejected"
                invitation.save()
                return Response(
                    {
                        "status": "success",
                        "code": status.HTTP_200_OK,
                        "message": "Invitation cancelled successfully",
                        "data": None,
                    },
                    status=status.HTTP_200_OK,
                )
            except StudentInvitation.DoesNotExist:
                return Response(
                    {
                        "status": "error",
                        "code": status.HTTP_404_NOT_FOUND,
                        "message": "Invitation not found",
                        "data": None,
                    },
                    status=status.HTTP_404_NOT_FOUND,
                )
            except Exception as e:
                logger.error(f"Error in cancel_invitation: {str(e)}", exc_info=True)
                return Response(
                    {
                        "status": "error",
                        "code": status.HTTP_500_INTERNAL_SERVER_ERROR,
                        "message": f"Internal server error: {str(e)}",
                        "data": None,
                    },
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR,
                )
        except AuthenticationFailed as e:
            logger.error(f"Authentication failed in cancel_invitation: {e}", exc_info=True)
            return Response(
                {
                    "status": "error",
                    "code": status.HTTP_401_UNAUTHORIZED,
                    "message": str(e),
                    "data": None,
                },
                status=status.HTTP_401_UNAUTHORIZED,
            )
        except Exception as e:
            logger.error(f"Unexpected error in cancel_invitation: {str(e)}", exc_info=True)
            return Response(
                {
                    "status": "error",
                    "code": status.HTTP_500_INTERNAL_SERVER_ERROR,
                    "message": f"Internal server error: {str(e)}",
                    "data": None,
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @action(detail=True, methods=["post"])
    def remove(self, request: Request, pk: int = None) -> Response:
        """Removes a student from the organization.

        Args:
            request: The HTTP request object.
            pk: The primary key of the student to remove.

        Returns:
            A Response object indicating the result of the removal.
        """
        logger.info(f"Removing student with pk={pk}")
        try:
            if not request.user.is_authenticated:
                raise AuthenticationFailed(
                    "Authentication credentials were not provided."
                )
            if not request.user.organization:
                return Response(
                    {
                        "status": "error",
                        "code": status.HTTP_400_BAD_REQUEST,
                        "message": "You are not associated with any organization",
                        "data": None,
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )
            if not request.user.role_org == "admin":
                return Response(
                    {
                        "status": "error",
                        "code": status.HTTP_403_FORBIDDEN,
                        "message": "Only organization admins can remove students",
                        "data": None,
                    },
                    status=status.HTTP_403_FORBIDDEN,
                )
            try:
                student = User.objects.get(
                    pk=pk,
                    organization=request.user.organization,
                    role_org="student",
                )
                student.organization = None
                student.role_org = None
                student.save()
                return Response(
                    {
                        "status": "success",
                        "code": status.HTTP_200_OK,
                        "message": "Student removed from organization successfully",
                        "data": None,
                    },
                    status=status.HTTP_200_OK,
                )
            except User.DoesNotExist:
                return Response(
                    {
                        "status": "error",
                        "code": status.HTTP_404_NOT_FOUND,
                        "message": "Student not found in your organization",
                        "data": None,
                    },
                    status=status.HTTP_404_NOT_FOUND,
                )
            except Exception as e:
                logger.error(f"Error in remove: {str(e)}", exc_info=True)
                return Response(
                    {
                        "status": "error",
                        "code": status.HTTP_500_INTERNAL_SERVER_ERROR,
                        "message": f"Internal server error: {str(e)}",
                        "data": None,
                    },
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR,
                )
        except AuthenticationFailed as e:
            logger.error(f"Authentication failed in remove: {e}", exc_info=True)
            return Response(
                {
                    "status": "error",
                    "code": status.HTTP_401_UNAUTHORIZED,
                    "message": str(e),
                    "data": None,
                },
                status=status.HTTP_401_UNAUTHORIZED,
            )
        except Exception as e:
            logger.error(f"Unexpected error in remove: {str(e)}", exc_info=True)
            return Response(
                {
                    "status": "error",
                    "code": status.HTTP_500_INTERNAL_SERVER_ERROR,
                    "message": f"Internal server error: {str(e)}",
                    "data": None,
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @action(
        detail=False,
        methods=["post"],
        url_path="accept_invitation/(?P<token>[^/.]+)",
    )
    def accept_invitation(self, request: Request, token: str = None) -> Response:
        """Accepts a student invitation.

        Args:
            request: The HTTP request object.
            token: The invitation token.

        Returns:
            A Response object indicating the result of accepting the invitation.
        """
        logger.info(f"Accepting invitation with token: {token}")
        try:
            try:
                invitation = StudentInvitation.objects.get(
                    token=token, status="pending"
                )
            except StudentInvitation.DoesNotExist:
                return Response(
                    {
                        "status": "error",
                        "code": status.HTTP_404_NOT_FOUND,
                        "message": "Invitation not found or already used/expired",
                        "data": None,
                    },
                    status=status.HTTP_404_NOT_FOUND,
                )

            if invitation.is_expired():
                invitation.status = "expired"
                invitation.save()
                return Response(
                    {
                        "status": "error",
                        "code": status.HTTP_400_BAD_REQUEST,
                        "message": "This invitation has expired",
                        "data": None,
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

            # Get or create user
            user, created = User.objects.get_or_create(
                email=invitation.email,
                defaults={
                    "username": invitation.email.split("@")[0],
                    "is_active": True,
                },
            )

            # Update user's organization and role
            user.organization = invitation.organization
            user.role_org = "student"
            user.save()

            # Update invitation status
            invitation.status = "accepted"
            invitation.accepted_at = timezone.now()
            invitation.save()

            return Response(
                {
                    "status": "success",
                    "code": status.HTTP_200_OK,
                    "message": "Invitation accepted successfully",
                    "data": {
                        "email": user.email,
                        "organization": invitation.organization.name,
                    },
                },
                status=status.HTTP_200_OK,
            )
        except Exception as e:
            logger.error(f"Unexpected error in accept_invitation: {str(e)}", exc_info=True)
            return Response(
                {
                    "status": "error",
                    "code": status.HTTP_500_INTERNAL_SERVER_ERROR,
                    "message": f"Internal server error: {str(e)}",
                    "data": None,
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @action(detail=False, methods=["post"])
    def upload_csv(self, request: Request) -> Response:
        """Handles CSV file upload for bulk student invitations.

        Args:
            request: The HTTP request object containing the CSV file.

        Returns:
            A Response object with the results of the bulk invitation from the CSV.
        """
        logger.info("CSV upload request received.")
        try:
            if not request.user.is_authenticated:
                raise AuthenticationFailed(
                    "Authentication credentials were not provided."
                )

            if not request.user.organization:
                return Response(
                    {
                        "status": "error",
                        "code": status.HTTP_400_BAD_REQUEST,
                        "message": "You are not associated with any organization",
                        "data": None,
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

            if not request.user.role_org == "admin":
                return Response(
                    {
                        "status": "error",
                        "code": status.HTTP_403_FORBIDDEN,
                        "message": "Only organization admins can invite students",
                        "data": None,
                    },
                    status=status.HTTP_403_FORBIDDEN,
                )

            if "file" not in request.FILES:
                return Response(
                    {
                        "status": "error",
                        "code": status.HTTP_400_BAD_REQUEST,
                        "message": "No file provided",
                        "data": None,
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

            csv_file = request.FILES["file"]
            if not csv_file.name.endswith(".csv"):
                return Response(
                    {
                        "status": "error",
                        "code": status.HTTP_400_BAD_REQUEST,
                        "message": "Only CSV files are allowed",
                        "data": None,
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

            # Read and parse CSV file
            try:
                decoded_file = csv_file.read().decode("utf-8")
                csv_reader = csv.DictReader(io.StringIO(decoded_file))

                # Validate CSV structure
                if "email" not in csv_reader.fieldnames:
                    return Response(
                        {
                            "status": "error",
                            "code": status.HTTP_400_BAD_REQUEST,
                            "message": "CSV file must contain an 'email' column",
                            "data": None,
                        },
                        status=status.HTTP_400_BAD_REQUEST,
                    )

                # Extract emails
                emails = []
                for row in csv_reader:
                    if row["email"].strip():  # Skip empty rows
                        emails.append(row["email"].strip())
                
                if not emails:
                    return Response(
                        {
                            "status": "error",
                            "code": status.HTTP_400_BAD_REQUEST,
                            "message": "No valid email addresses found in the CSV file",
                            "data": None,
                        },
                        status=status.HTTP_400_BAD_REQUEST,
                    )

                if len(emails) > 200:  # Limit to prevent abuse
                    return Response(
                        {
                            "status": "error",
                            "code": status.HTTP_400_BAD_REQUEST,
                            "message": "CSV file contains too many email addresses. Maximum allowed is 200.",
                            "data": None,
                        },
                        status=status.HTTP_400_BAD_REQUEST,
                    )

                # Process the emails using existing bulk invitation logic
                results = {
                    "success": [],
                    "already_member": [],
                    "already_invited": [],
                    "invalid": [],
                }

                with transaction.atomic():
                    for email in emails:
                        try:
                            # Check if user already exists in the organization
                            if User.objects.filter(
                                email=email,
                                organization=request.user.organization,
                            ).exists():
                                results["already_member"].append(email)
                                continue

                            # Check if there's already a pending invitation
                            if StudentInvitation.objects.filter(
                                email=email,
                                organization=request.user.organization,
                                status="pending",
                            ).exists():
                                results["already_invited"].append(email)
                                continue

                            # Create invitation
                            invitation = StudentInvitation.objects.create(
                                email=email,
                                organization=request.user.organization,
                            )

                            # Send invitation email
                            self._send_invitation_email(
                                request.user.organization, email, invitation
                            )
                            results["success"].append(email)

                        except Exception as e:
                            logger.error(f"Error processing email {email} in bulk invitation: {e}", exc_info=True)
                            results["invalid"].append(email)
                            continue

                return Response(
                    {
                        "status": "success",
                        "code": status.HTTP_200_OK,
                        "message": "Bulk invitation process completed",
                        "data": {
                            "success_count": len(results["success"]),
                            "already_member_count": len(
                                results["already_member"]
                            ),
                            "already_invited_count": len(
                                results["already_invited"]
                            ),
                            "invalid_count": len(results["invalid"]),
                            "details": results,
                        },
                    },
                    status=status.HTTP_200_OK,
                )

            except csv.Error as e:
                logger.error(f"Invalid CSV file format: {e}", exc_info=True)
                return Response(
                    {
                        "status": "error",
                        "code": status.HTTP_400_BAD_REQUEST,
                        "message": "Invalid CSV file format",
                        "data": None,
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )
            except UnicodeDecodeError as e:
                logger.error(f"Invalid file encoding: {e}", exc_info=True)
                return Response(
                    {
                        "status": "error",
                        "code": status.HTTP_400_BAD_REQUEST,
                        "message": "Invalid file encoding. Please use UTF-8 encoding.",
                        "data": None,
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

        except AuthenticationFailed as e:
            logger.error(f"Authentication failed in upload_csv: {e}", exc_info=True)
            return Response(
                {
                    "status": "error",
                    "code": status.HTTP_401_UNAUTHORIZED,
                    "message": str(e),
                    "data": None,
                },
                status=status.HTTP_401_UNAUTHORIZED,
            )
        except Exception as e:
            logger.error(f"Unexpected error in upload_csv: {e}", exc_info=True)
            return Response(
                {
                    "status": "error",
                    "code": status.HTTP_500_INTERNAL_SERVER_ERROR,
                    "message": str(e),
                    "data": None,
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class TestManagementViewSet(viewsets.ModelViewSet):
    """Manages tests, questions, assignments, and results.

    This ViewSet handles test creation, question paper management, student
    assignments, and viewing results within an organization.
    """
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = TestSerializer

    def get_queryset(self) -> Any:
        """Gets the queryset of tests for the user's organization.

        Returns:
            A queryset of tests or an empty queryset if no organization is
            associated.
        """
        logger.info(f"Fetching tests for organization '{self.request.user.organization.name if self.request.user.organization else 'N/A'}'")
        if not self.request.user.organization:
            return Test.objects.none()
        return Test.objects.filter(organization=self.request.user.organization)

    def perform_create(self, serializer) -> None:
        """Creates a new test for the user's organization.

        Args:
            serializer: The serializer instance for the new test.

        Raises:
            permissions.PermissionDenied: If the user is not an admin.
        """
        logger.info(f"Creating test for organization '{self.request.user.organization.name if self.request.user.organization else 'N/A'}'")
        if not self.request.user.role_org == "admin":
            raise permissions.PermissionDenied(
                "Only organization admins can create tests"
            )
        
        # [NEW] Handle Scoping
        scope_type = self.request.data.get('scope_type', 'ORGANIZATION')
        scope_id = self.request.data.get('scope_id')
        
        serializer.save(
            organization=self.request.user.organization,
            scope_type=scope_type,
            scope_id=scope_id
        )

    @action(detail=True, methods=["get"])
    def question_paper(self, request: Request, pk: int = None) -> Response:
        """Gets the question paper for a test.

        Args:
            request: The HTTP request object.
            pk: The primary key of the test.

        Returns:
            A Response object containing the question paper's PDF URL.
        """
        logger.info(f"Fetching question paper for test pk={pk}")
        try:
            test = self.get_object()

            # Check if user is assigned to this test
            if request.user.role_org == "student":
                if not TestAssignment.objects.filter(
                    test=test, student=request.user
                ).exists():
                    return Response(
                        {
                            "status": "error",
                            "message": "You are not assigned to this test",
                        },
                        status=status.HTTP_403_FORBIDDEN,
                    )

            # Get the question paper
            try:
                question_paper = test.question_paper
            except QuestionPaper.DoesNotExist:
                return Response(
                    {
                        "status": "error",
                        "message": "Question paper not found for this test",
                    },
                    status=status.HTTP_404_NOT_FOUND,
                )

            return Response(
                {
                    "status": "success",
                    "data": {
                        "pdf_url": request.build_absolute_uri(
                            question_paper.pdf_file.url
                        )
                    },
                },
                status=status.HTTP_200_OK,
            )

        except Exception as e:
            logger.error(f"Error fetching question paper for test pk={pk}: {e}", exc_info=True)
            return Response(
                {"status": "error", "message": str(e)},
                status=status.HTTP_400_BAD_REQUEST,
            )

    @action(detail=False, methods=["get"])
    def assigned_tests(self, request: Request) -> Response:
        """Gets all tests assigned to the current student.

        Args:
            request: The HTTP request object.

        Returns:
            A Response object containing a list of assigned tests.
        """
        logger.info(f"Fetching assigned tests for user: {request.user.email}")
        try:
            if not request.user.role_org == "student":
                return Response(
                    {
                        "status": "error",
                        "message": "Only students can view their assigned tests",
                    },
                    status=status.HTTP_403_FORBIDDEN,
                )

            assignments = TestAssignment.objects.filter(
                student=request.user,
                test__organization=request.user.organization,
            ).select_related("test")

            tests = [assignment.test for assignment in assignments]

            return Response(
                {
                    "status": "success",
                    "data": TestSerializer(tests, many=True).data,
                },
                status=status.HTTP_200_OK,
            )

        except Exception as e:
            logger.error(f"Error fetching assigned tests for user {request.user.email}: {e}", exc_info=True)
            return Response(
                {"status": "error", "message": str(e)},
                status=status.HTTP_400_BAD_REQUEST,
            )

    @action(detail=True, methods=["post"])
    def upload_question_paper(self, request: Request, pk: int = None) -> Response:
        """Uploads a question paper for a test.

        This can be either a PDF file or a JSON structure of questions.

        Args:
            request: The HTTP request object.
            pk: The primary key of the test.

        Returns:
            A Response object indicating success or failure.
        """
        logger.info(f"Uploading question paper for test pk={pk}")
        try:
            test = self.get_object()

            # DEBUG LOGGING
            logger.info(f"Method: {request.method}")
            logger.info(f"Content-Type: {request.content_type}")
            logger.info(f"Request Data Keys: {list(request.data.keys())}")
            logger.info(f"Request Files Keys: {list(request.FILES.keys())}")
            if 'questions' in request.data:
                logger.info(f"Questions Data Type: {type(request.data['questions'])}")
                logger.info(f"Questions Data Preview: {str(request.data['questions'])[:200]}")

            # Check if either pdf_file or questions are provided
            pdf_file = request.FILES.get("pdf_file")
            questions_data = request.data.get("questions")

            if not pdf_file and not questions_data:
                logger.error("Validation Error: Neither pdf_file nor questions provided")
                return Response(
                    {
                        "status": "error",
                        "message": "Either a question paper (PDF) or questions data must be provided",
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

            # Create question paper
            question_paper = QuestionPaper.objects.create(
                test=test,
                pdf_file=pdf_file,
                answer_key=request.FILES.get("answer_key"),
            )

            # Create test questions if provided
            if questions_data:
                try:
                    # Parse the JSON string if it's a string
                    if isinstance(questions_data, str):
                        questions_data = json.loads(questions_data)

                    for index, question_data in enumerate(questions_data):
                        question = TestQuestion.objects.create(
                            question_paper=question_paper,
                            question_text=question_data["text"],
                            question_type=question_data["type"],
                            marks=question_data["marks"],
                            order=index + 1,
                        )

                        # Handle different question types
                        if question_data["type"] == "mcq":
                            question.options = question_data.get("options", [])
                            question.correct_answer = question_data.get(
                                "correctAnswer", ""
                            )
                        elif question_data["type"] == "programming":
                            question.programming_language = question_data.get(
                                "programmingLanguage", ""
                            )
                            question.test_cases = question_data.get(
                                "testCases", []
                            )
                            question.time_limit = question_data.get(
                                "timeLimit", 5
                            )
                            question.memory_limit = question_data.get(
                                "memoryLimit", 512
                            )
                        elif question_data["type"] == "matching":
                            matching_pairs = question_data.get(
                                "matchingPairs", []
                            )
                            if not isinstance(matching_pairs, list):
                                raise ValueError(
                                    "Matching pairs must be a list"
                                )
                            if len(matching_pairs) < 2:
                                raise ValueError(
                                    "Matching questions must have at least two pairs"
                                )
                            question.options = matching_pairs
                            question.correct_answer = json.dumps(
                                matching_pairs
                            )
                        elif question_data["type"] in [
                            "descriptive",
                            "short_answer",
                            "long_answer",
                        ]:
                            question.model_answer = question_data.get(
                                "modelAnswer", ""
                            )
                            question.keywords = question_data.get(
                                "keywords", []
                            )
                        else:
                            question.correct_answer = question_data.get(
                                "correctAnswer", ""
                            )

                        question.save()
                except json.JSONDecodeError as e:
                    logger.error(f"JSON Decode Error: {str(e)}")
                    return Response(
                        {
                            "status": "error",
                            "message": "Invalid questions data format",
                        },
                        status=status.HTTP_400_BAD_REQUEST,
                    )
                except KeyError as e:
                    logger.error(f"Missing Key in Question Data: {str(e)}")
                    return Response(
                        {
                            "status": "error",
                            "message": f"Missing required field in question data: {str(e)}",
                        },
                        status=status.HTTP_400_BAD_REQUEST,
                    )

            return Response(
                {
                    "status": "success",
                    "message": "Question paper uploaded successfully",
                    "data": QuestionPaperSerializer(question_paper).data,
                },
                status=status.HTTP_201_CREATED,
            )

        except Exception as e:
            logger.error(f"Error uploading question paper for test pk={pk}: {e}", exc_info=True)
            return Response(
                {"status": "error", "message": str(e)},
                status=status.HTTP_400_BAD_REQUEST,
            )

    @action(detail=True, methods=["post"])
    def assign_students(self, request: Request, pk: int = None) -> Response:
        """Assigns a test to multiple students.

        Args:
            request: The HTTP request containing a list of student IDs.
            pk: The primary key of the test.

        Returns:
            A Response object indicating the result of the assignment.
        """
        logger.info(f"Assigning students to test pk={pk}")
        try:
            test = self.get_object()
            student_ids = request.data.get("student_ids", [])

            if not student_ids:
                return Response(
                    {
                        "status": "error",
                        "message": "No students selected for assignment",
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

            # Verify all students belong to the organization
            students = User.objects.filter(
                id__in=student_ids,
                organization=request.user.organization,
                role_org="student",
            )

            if len(students) != len(student_ids):
                return Response(
                    {
                        "status": "error",
                        "message": "Some selected students are not valid",
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

            # Create assignments and notifications
            assignments = []
            for student in students:
                assignment, created = TestAssignment.objects.get_or_create(
                    test=test, student=student
                )
                assignments.append(assignment)

                # Create notification for the student
                Notification.objects.create(
                    sender=request.user,
                    recipient=student,
                    sender_role="admin",
                    recipient_role="student",
                    message=f"You have been assigned a new test: {test.title}. The test starts at {test.start_time.strftime('%Y-%m-%d %H:%M')} and duration is {test.duration_minutes} minutes.",
                )

            return Response(
                {
                    "status": "success",
                    "message": f"Test assigned to {len(assignments)} students",
                    "data": TestAssignmentSerializer(
                        assignments, many=True
                    ).data,
                },
                status=status.HTTP_200_OK,
            )

        except Exception as e:
            logger.error(f"Error assigning students to test pk={pk}: {e}", exc_info=True)
            return Response(
                {"status": "error", "message": str(e)},
                status=status.HTTP_400_BAD_REQUEST,
            )

    @action(detail=True, methods=["get"])
    def assigned_students(self, request: Request, pk: int = None) -> Response:
        """Gets all students assigned to a specific test.

        Args:
            request: The HTTP request object.
            pk: The primary key of the test.

        Returns:
            A Response object containing a list of assigned students.
        """
        logger.info(f"Fetching assigned students for test pk={pk}")
        try:
            test = self.get_object()
            assignments = TestAssignment.objects.filter(test=test)
            return Response(
                {
                    "status": "success",
                    "data": TestAssignmentSerializer(
                        assignments, many=True
                    ).data,
                },
                status=status.HTTP_200_OK,
            )
        except Exception as e:
            logger.error(f"Error fetching assigned students for test pk={pk}: {e}", exc_info=True)
            return Response(
                {"status": "error", "message": str(e)},
                status=status.HTTP_400_BAD_REQUEST,
            )

    @action(detail=True, methods=["get"])
    def results(self, request: Request, pk: int = None) -> Response:
        """Gets the results for all students who have submitted answers for a test.

        Args:
            request: The HTTP request object.
            pk: The primary key of the test.

        Returns:
            A Response object containing the test results.
        """
        logger.info(f"Fetching results for test pk={pk}")
        try:
            test = self.get_object()
            results = []

            # First get all students who have submitted answers
            submitted_students = set()

            # Check for PDF submissions
            pdf_submissions = AnswerUpload.objects.filter(
                organization_test=test
            ).values_list("user_id", flat=True)
            submitted_students.update(pdf_submissions)

            # Check for text-based submissions
            text_submissions = StudentAnswer.objects.filter(
                test=test
            ).values_list("student_id", flat=True)
            submitted_students.update(text_submissions)

            # Now get assignments only for students who submitted
            assignments = TestAssignment.objects.filter(
                test=test, student_id__in=submitted_students
            )

            for assignment in assignments:
                student = assignment.student
                result = {
                    "student_name": student.username,
                    "student_email": student.email,
                    "submission_time": assignment.assigned_at,
                    "score": assignment.score,
                    "grading_complete": False,
                    "answer_file": None,
                    "answer_id": None,
                    "answer_text": None,
                    "max_score": None,
                }

                # Check if there's a question paper with PDF
                try:
                    question_paper = QuestionPaper.objects.get(test=test)
                    if question_paper.pdf_file:
                        # Get the answer upload for PDF-based answers
                        answer_upload = AnswerUpload.objects.filter(
                            organization_test=test, user_id=student.id
                        ).first()

                        if answer_upload:
                            result["answer_file"] = answer_upload.file.url
                            result["answer_id"] = answer_upload.id

                            # Check if grading is complete
                            grading_result = GradingResult.objects.filter(
                                answer_upload=answer_upload
                            ).first()

                            if grading_result:
                                result["grading_complete"] = True
                                # For PDF, this is the actual score
                                result["max_score"] = (
                                    grading_result.total_score
                                )
                                # Update score to match max_score for PDF
                                result["score"] = grading_result.total_score
                    else:
                        # Get text-based answers from StudentAnswer model
                        student_answers = StudentAnswer.objects.filter(
                            test=test, student=student
                        )

                        if student_answers.exists():
                            result["answer_text"] = {
                                answer.question.id: {
                                    "question_text": answer.question.question_text,
                                    "answer_text": answer.answer_text,
                                    "score": answer.score,
                                    "is_evaluated": answer.is_evaluated,
                                    "question_type": answer.question.question_type,
                                }
                                for answer in student_answers
                            }
                            result["grading_complete"] = all(
                                answer.is_evaluated
                                for answer in student_answers
                            )
                            # For text answers, max_score is the total possible
                            # score
                            result["max_score"] = sum(
                                answer.question.marks
                                for answer in student_answers
                            )
                except QuestionPaper.DoesNotExist:
                    # If no question paper exists, get text-based answers
                    student_answers = StudentAnswer.objects.filter(
                        test=test, student=student
                    )

                    if student_answers.exists():
                        result["answer_text"] = {
                            answer.question.id: {
                                "question_text": answer.question.question_text,
                                "answer_text": answer.answer_text,
                                "score": answer.score,
                                "is_evaluated": answer.is_evaluated,
                                "question_type": answer.question.question_type,
                            }
                            for answer in student_answers
                        }
                        result["grading_complete"] = all(
                            answer.is_evaluated for answer in student_answers
                        )
                        # For text answers, max_score is the total possible
                        # score
                        result["max_score"] = sum(
                            answer.question.marks for answer in student_answers
                        )

                results.append(result)

            return Response(
                {
                    "status": "success",
                    "code": status.HTTP_200_OK,
                    "message": "Test results retrieved successfully",
                    "data": results,
                },
                status=status.HTTP_200_OK,
            )

        except Exception as e:
            logger.error(f"Error fetching results for test pk={pk}: {e}", exc_info=True)
            return Response(
                {
                    "status": "error",
                    "code": status.HTTP_500_INTERNAL_SERVER_ERROR,
                    "message": str(e),
                    "data": None,
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @action(detail=False, methods=["get"])
    def progress_summary(self, request: Request) -> Response:
        """Gets a progress summary for the organization.

        This includes overall stats, student progress, and test performance.

        Args:
            request: The HTTP request object.

        Returns:
            A Response object containing the progress summary.
        """
        logger.info(f"Fetching progress summary for organization '{self.request.user.organization.name if self.request.user.organization else 'N/A'}'")
        try:
            logger.debug(
                f"[progress_summary] User authenticated: {request.user.is_authenticated}"
            )
            logger.debug(f"[progress_summary] User: {request.user}")
            logger.debug(
                f"[progress_summary] User organization: {request.user.organization}"
            )

            if (
                not request.user.is_authenticated
                or not request.user.organization
            ):
                logger.warning(
                    f"[progress_summary] Authentication failed - is_authenticated: {request.user.is_authenticated}, has_organization: {bool(request.user.organization)}"
                )
                return Response(
                    {
                        "status": "error",
                        "message": "Authentication required or user not associated with an organization",
                    },
                    status=status.HTTP_401_UNAUTHORIZED,
                )

            try:
                organization = request.user.organization
                logger.debug(
                    f"[progress_summary] Getting students for organization: {organization}"
                )
                students = User.objects.filter(
                    organization=organization, role_org="student"
                )
                logger.debug(f"[progress_summary] Found {students.count()} students")

                # Log student details
                for student in students:
                    logger.debug(
                        f"[progress_summary] Student: {student.email}, role: {student.role_org}"
                    )

                logger.debug(
                    f"[progress_summary] Getting tests for organization: {organization}"
                )
                tests = Test.objects.filter(organization=organization)
                logger.debug(f"[progress_summary] Found {tests.count()} tests")

                # Overall Stats
                logger.debug("[progress_summary] Calculating overall stats")
                total_students = students.count()
                total_completed_tests = TestAssignment.objects.filter(
                    test__organization=organization, is_completed=True
                ).count()
                total_assigned_tests = TestAssignment.objects.filter(
                    test__organization=organization
                ).count()

                logger.debug(f"[progress_summary] Total students: {total_students}")
                logger.debug(
                    f"[progress_summary] Total completed tests: {total_completed_tests}"
                )
                logger.debug(
                    f"[progress_summary] Total assigned tests: {total_assigned_tests}"
                )

                overall_completion_rate = (
                    (total_completed_tests / total_assigned_tests * 100)
                    if total_assigned_tests > 0
                    else 0
                )
                logger.debug(
                    f"[progress_summary] Overall completion rate: {overall_completion_rate}"
                )

                # Calculate average score
                logger.debug("[progress_summary] Calculating average scores")
                all_scores = [
                    gr.total_score
                    for gr in GradingResult.objects.filter(
                        answer_upload__organization_test__organization=organization,
                        total_score__isnull=False,
                    )
                ]
                logger.debug(f"[progress_summary] Found {len(all_scores)} scores")
                average_overall_score = (
                    sum(all_scores) / len(all_scores) if all_scores else 0
                )
                logger.debug(
                    f"[progress_summary] Average overall score: {average_overall_score}"
                )

                # Active tests
                logger.debug("[progress_summary] Calculating active tests")
                now = timezone.now()
                active_tests_count = 0
                for test in tests:
                    try:
                        test_end_time = test.start_time + datetime.timedelta(
                            minutes=test.duration_minutes
                        )
                        if test.start_time <= now <= test_end_time:
                            active_tests_count += 1
                    except Exception as e:
                        logger.error(
                            f"[progress_summary] Error calculating test end time for test {test.id}: {str(e)}", exc_info=True
                        )
                logger.debug(
                    f"[progress_summary] Active tests count: {active_tests_count}"
                )

                # Student Progress
                logger.debug("[progress_summary] Calculating student progress")
                student_progress_data = []
                for student in students:
                    try:
                        logger.debug(
                            f"[progress_summary] Processing student: {student.email}"
                        )
                        student_assignments = TestAssignment.objects.filter(
                            student=student
                        )
                        logger.debug(
                            f"[progress_summary] Found {student_assignments.count()} assignments for student {student.email}"
                        )

                        student_completed_tests = student_assignments.filter(
                            is_completed=True
                        ).count()
                        student_total_assignments = student_assignments.count()
                        logger.debug(
                            f"[progress_summary] Student {student.email} - Completed: {student_completed_tests}, Total: {student_total_assignments}"
                        )

                        student_scores = [
                            gr.total_score
                            for gr in GradingResult.objects.filter(
                                answer_upload__user_id=student.id,
                                answer_upload__organization_test__organization=organization,
                                total_score__isnull=False,
                            )
                        ]
                        logger.debug(
                            f"[progress_summary] Found {len(student_scores)} scores for student {student.email}"
                        )
                        student_average_score = (
                            sum(student_scores) / len(student_scores)
                            if student_scores
                            else 0
                        )
                        logger.debug(
                            f"[progress_summary] Student {student.email} average score: {student_average_score}"
                        )

                        recent_grading_results = GradingResult.objects.filter(
                            answer_upload__user_id=student.id,
                            answer_upload__organization_test__organization=organization,
                            total_score__isnull=False,
                        ).order_by("-id")[:5]
                        recent_scores = [
                            gr.total_score for gr in recent_grading_results
                        ]
                        logger.debug(
                            f"[progress_summary] Student {student.email} recent scores: {recent_scores}"
                        )

                        last_assignment = student_assignments.order_by(
                            "-assigned_at"
                        ).first()
                        last_test_date = None
                        if last_assignment and last_assignment.assigned_at:
                            last_test_date = last_assignment.assigned_at.date()
                            logger.debug(
                                f"[progress_summary] Student {student.email} last test date: {last_test_date}"
                            )

                        student_progress_data.append(
                            {
                                "id": student.id,
                                "name": student.get_full_name()
                                or student.username
                                or student.email,
                                "completedTests": student_completed_tests,
                                "totalTests": student_total_assignments,
                                "averageScore": round(
                                    student_average_score, 2
                                ),
                                "lastTestDate": last_test_date,
                                "recentScores": recent_scores,
                            }
                        )
                        logger.debug(
                            f"[progress_summary] Added progress data for student {student.email}"
                        )
                    except Exception as e:
                        logger.error(
                            f"[progress_summary] Error processing student {student.id}: {str(e)}", exc_info=True
                        )
                        continue

                logger.debug(
                    f"[progress_summary] Processed {len(student_progress_data)} students"
                )

                # Test Performance
                logger.debug("[progress_summary] Calculating test performance")
                test_performance_data = []
                for test in tests:
                    try:
                        test_assignments = TestAssignment.objects.filter(
                            test=test
                        )
                        test_total_students = test_assignments.count()
                        test_completed_students = test_assignments.filter(
                            status__in=['SUBMITTED', 'EVALUATED']
                        ).count()

                        test_completion_rate = (
                            (
                                test_completed_students
                                / test_total_students
                                * 100
                            )
                            if test_total_students > 0
                            else 0
                        )

                        test_scores = [
                            gr.total_score
                            for gr in GradingResult.objects.filter(
                                answer_upload__organization_test=test,
                                total_score__isnull=False,
                            )
                        ]
                        test_average_score = (
                            sum(test_scores) / len(test_scores)
                            if test_scores
                            else 0
                        )

                        test_performance_data.append(
                            {
                                "id": test.id,
                                "title": test.title,
                                "averageScore": round(test_average_score, 2),
                                "completionRate": round(
                                    test_completion_rate, 2
                                ),
                                "totalStudents": test_total_students,
                                "date": test.start_time.date(),
                            }
                        )
                    except Exception as e:
                        logger.error(
                            f"[progress_summary] Error processing test {test.id}: {str(e)}", exc_info=True
                        )
                        continue

                logger.debug(
                    f"[progress_summary] Processed {len(test_performance_data)} tests"
                )

                return Response(
                    {
                        "status": "success",
                        "data": {
                            "overallStats": {
                                "totalStudents": total_students,
                                "averageScore": round(
                                    average_overall_score, 2
                                ),
                                "completionRate": round(
                                    overall_completion_rate, 2
                                ),
                                "activeTests": active_tests_count,
                            },
                            "studentProgress": student_progress_data,
                            "testPerformance": test_performance_data,
                        },
                    },
                    status=status.HTTP_200_OK,
                )

            except Exception as e:
                logger.error(f"[progress_summary] Error in data processing: {str(e)}", exc_info=True)
                raise

        except Exception as e:
            logger.error(f"[progress_summary] Top-level error: {str(e)}", exc_info=True)
            return Response(
                {"status": "error", "message": str(e)},
                status=status.HTTP_400_BAD_REQUEST,
            )

    @action(detail=True, methods=["get"])
    def questions(self, request: Request, pk: int = None) -> Response:
        """Gets all questions for a specific test.

        Args:
            request: The HTTP request object.
            pk: The primary key of the test.

        Returns:
            A Response object containing the list of questions.
        """
        logger.info(f"Fetching questions for test pk={pk}")
        try:
            test = self.get_object()

            # Check if user is assigned to this test
            if request.user.role_org == "student":
                if not TestAssignment.objects.filter(
                    test=test, student=request.user
                ).exists():
                    return Response(
                        {
                            "status": "error",
                            "message": "You are not assigned to this test",
                        },
                        status=status.HTTP_403_FORBIDDEN,
                    )

            # Get the question paper and its questions
            try:
                question_paper = test.question_paper
                questions = question_paper.test_questions.all().order_by(
                    "order"
                )

                # Format questions data
                questions_data = []
                for question in questions:
                    question_data = {
                        "id": question.id,
                        "text": question.question_text,
                        "type": question.question_type,
                        "marks": question.marks,
                        "order": question.order,
                    }

                    # Add type-specific fields
                    if question.question_type == "mcq":
                        question_data["options"] = question.options
                        question_data["correctAnswer"] = (
                            question.correct_answer
                        )
                    elif question.question_type == "programming":
                        question_data["programmingLanguage"] = (
                            question.programming_language
                        )
                        question_data["testCases"] = question.test_cases
                        question_data["timeLimit"] = question.time_limit
                        question_data["memoryLimit"] = question.memory_limit
                    elif question.question_type == "matching":
                        question_data["matchingPairs"] = (
                            question.options if question.options else []
                        )
                    elif question.question_type in [
                        "descriptive",
                        "short_answer",
                        "long_answer",
                    ]:
                        question_data["modelAnswer"] = question.model_answer
                        question_data["keywords"] = question.keywords
                    else:
                        question_data["correctAnswer"] = (
                            question.correct_answer
                        )

                    questions_data.append(question_data)

                return Response(
                    {"status": "success", "data": questions_data},
                    status=status.HTTP_200_OK,
                )

            except QuestionPaper.DoesNotExist:
                return Response(
                    {
                        "status": "error",
                        "message": "Question paper not found for this test",
                    },
                    status=status.HTTP_404_NOT_FOUND,
                )

        except Exception as e:
            logger.error(f"Error fetching questions for test pk={pk}: {e}", exc_info=True)
            return Response(
                {"status": "error", "message": str(e)},
                status=status.HTTP_400_BAD_REQUEST,
            )

    @action(detail=True, methods=["post"])
    def start_test(self, request: Request, pk: int = None) -> Response:
        """Starts a test for a student."""
        test = self.get_object()
        try:
            assignment = TestAssignment.objects.get(test=test, student=request.user)
            if assignment.status == 'ASSIGNED': # Only start if not already started/completed
                assignment.status = 'STARTED'
                assignment.started_at = timezone.now()
                assignment.save()
            return Response({"status": "success", "message": "Test started", "started_at": assignment.started_at})
        except TestAssignment.DoesNotExist:
             return Response({"status": "error", "message": "Assignment not found"}, status=status.HTTP_404_NOT_FOUND)

    @action(detail=True, methods=["post"])
    def submit_answers(self, request: Request, pk: int = None) -> Response:
        """Submits student answers for a test.

        Args:
            request: The HTTP request object containing the answers.
            pk: The primary key of the test.

        Returns:
            A Response object indicating the result of the submission.
        """
        logger.info(f"Submitting answers for test pk={pk} by user {request.user.email}")
        try:
            if not request.user.is_authenticated:
                raise AuthenticationFailed(
                    "Authentication credentials were not provided."
                )

            test = self.get_object()  # This gets the Test instance based on pk
            student = request.user

            if not student.role_org == "student":
                return Response(
                    {
                        "status": "error",
                        "code": status.HTTP_403_FORBIDDEN,
                        "message": "Only students can submit test answers.",
                    },
                    status=status.HTTP_403_FORBIDDEN,
                )

            answers_data = request.data.get("answers", [])
            if not isinstance(answers_data, list):
                return Response(
                    {
                        "status": "error",
                        "code": status.HTTP_400_BAD_REQUEST,
                        "message": "'answers' must be a list of answer objects.",
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

            with transaction.atomic():
                for answer_data in answers_data:
                    question_id = answer_data.get("question_id")
                    # This might be a string or a dict for programming
                    answer_text = answer_data.get("answer")

                    if not question_id:
                        continue  # Skip if question_id is missing

                    try:
                        question = TestQuestion.objects.get(
                            id=question_id, question_paper__test=test
                        )
                    except TestQuestion.DoesNotExist:
                        # Optionally log this or return an error if a question
                        # doesn't exist
                        continue

                    # Handle different answer types
                    final_answer_text = ""
                    if isinstance(answer_text, dict) and "code" in answer_text:
                        # Store programming answers as JSON string
                        final_answer_text = json.dumps(answer_text)
                    elif (
                        isinstance(answer_text, list)
                        and question.question_type == "matching"
                    ):
                        # Ensure matching answers are properly formatted JSON
                        final_answer_text = json.dumps(answer_text)
                    elif answer_text is not None:
                        final_answer_text = str(answer_text)

                    # Update or create the student's answer
                    student_answer, created = (
                        StudentAnswer.objects.update_or_create(
                            test=test,
                            student=student,
                            question=question,
                            defaults={"answer_text": final_answer_text},
                        )
                    )

            # Mark test assignment as completed
            test_assignment = TestAssignment.objects.filter(
                test=test, student=student
            ).first()
            if test_assignment:
                test_assignment.status = 'SUBMITTED'
                test_assignment.completed_at = timezone.now()
                test_assignment.save()

            return Response(
                {
                    "status": "success",
                    "code": status.HTTP_200_OK,
                    "message": "Answers submitted successfully.",
                },
                status=status.HTTP_200_OK,
            )

        except AuthenticationFailed as e:
            logger.error(f"Authentication failed in submit_answers: {e}", exc_info=True)
            return Response(
                {
                    "status": "error",
                    "code": status.HTTP_401_UNAUTHORIZED,
                    "message": str(e),
                },
                status=status.HTTP_401_UNAUTHORIZED,
            )
        except Exception as e:
            logger.error(f"Error submitting answers for test pk={pk}: {e}", exc_info=True)
            return Response(
                {
                    "status": "error",
                    "code": status.HTTP_500_INTERNAL_SERVER_ERROR,
                    "message": f"An error occurred: {str(e)}",
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @action(detail=True, methods=["get"])
    def check_submission(self, request: Request, pk: int = None) -> Response:
        """Checks if a student has submitted answers for this test.

        Args:
            request: The HTTP request object.
            pk: The primary key of the test.

        Returns:
            A Response object indicating whether the test has been submitted.
        """
        logger.info(f"Checking submission status for test pk={pk} by user {request.user.email}")
        try:
            test = self.get_object()
            student = request.user

            # Check for PDF submissions
            pdf_submitted = AnswerUpload.objects.filter(
                organization_test=test, user_id=student.id
            ).exists()

            # Check for manual question submissions
            manual_submitted = StudentAnswer.objects.filter(
                test=test, student=student
            ).exists()

            # Check if test assignment is marked as completed
            assignment_completed = TestAssignment.objects.filter(
                test=test, student=student, status__in=['SUBMITTED', 'EVALUATED']
            ).exists()

            return Response(
                {
                    "status": "success",
                    "submitted": pdf_submitted
                    or manual_submitted
                    or assignment_completed,
                },
                status=status.HTTP_200_OK,
            )

        except Exception as e:
            logger.error(f"Error checking submission status for test pk={pk}: {e}", exc_info=True)
            return Response(
                {"status": "error", "message": str(e)},
                status=status.HTTP_400_BAD_REQUEST,
            )


    @action(detail=True, methods=["post"])
    def grade_with_ai(self, request: Request, pk: int = None) -> Response:
        """Triggers AI grading for a test.

        Args:
            request: The HTTP request object.
            pk: The primary key of the test.

        Returns:
            A Response object with the grading summary.
        """
        logger.info(f"Triggering AI grading for test pk={pk}")
        try:
            test = self.get_object()
            
            # Permission check: Only admins can trigger grading
            if not request.user.role_org == "admin":
                 return Response(
                    {"status": "error", "message": "Only admins can trigger AI grading"},
                    status=status.HTTP_403_FORBIDDEN
                )

            # Initialize Service
            service = OrganizationGradingService(test_id=test.id)
            
            # Execute Grading
            summary = service.grade_test()
            
            return Response(
                {
                    "status": "success",
                    "message": "AI grading completed",
                    "data": summary
                },
                status=status.HTTP_200_OK
            )
            
        except ValueError as e:
            logger.warning(f"Grading validation failed: {e}")
            return Response(
                {"status": "error", "message": str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )
        except Exception as e:
            logger.error(f"Error during AI grading for test pk={pk}: {e}", exc_info=True)
            return Response(
                {"status": "error", "message": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

class OrganizationHierarchyViewSet(viewsets.ModelViewSet):
    """Manages organization hierarchy levels."""

    permission_classes = [permissions.IsAuthenticated]
    serializer_class = OrganizationHierarchyLevelSerializer

    def get_queryset(self) -> Any:
        """Returns a queryset of hierarchy levels for the user's organization.

        Returns:
            A queryset of OrganizationHierarchyLevel objects.
        """
        logger.info(f"Fetching hierarchy levels for organization '{self.request.user.organization.name if self.request.user.organization else 'N/A'}'")
        if not self.request.user.organization:
            return OrganizationHierarchyLevel.objects.none()
        return OrganizationHierarchyLevel.objects.filter(
            organization=self.request.user.organization
        ).order_by("order")

    def perform_create(self, serializer) -> None:
        """Creates a new hierarchy level for the user's organization.

        The `order` of the new level is automatically set.

        Args:
            serializer: The serializer instance for the new level.
        """
        logger.info(f"Creating hierarchy level for organization '{self.request.user.organization.name if self.request.user.organization else 'N/A'}'")
        # Get the highest order number for the organization
        highest_order = (
            OrganizationHierarchyLevel.objects.filter(
                organization=self.request.user.organization
            )
            .order_by("-order")
            .first()
        )

        # Set the new order to be one more than the highest
        new_order = (highest_order.order + 1) if highest_order else 1

        # If order is provided in the request, use it
        if "order" in self.request.data:
            new_order = self.request.data["order"]

        serializer.save(
            organization=self.request.user.organization, order=new_order
        )

    def perform_update(self, serializer) -> None:
        """Updates an existing hierarchy level.

        Ensures the organization is not changed.

        Args:
            serializer: The serializer instance for the updated level.
        """
        logger.info(f"Updating hierarchy level pk={serializer.instance.pk}")
        # Ensure the organization field is preserved during updates
        serializer.save(organization=self.request.user.organization)

    @action(detail=True, methods=["get"])
    def values(self, request: Request, pk: int = None) -> Response:
        """Gets all values for a specific hierarchy level.

        Args:
            request: The HTTP request object.
            pk: The primary key of the hierarchy level.

        Returns:
            A Response object containing the hierarchy values.
        """
        hierarchy_level = self.get_object()
        logger.info(f"Fetching values for hierarchy level pk={pk}")
        values = HierarchyValue.objects.filter(
            hierarchy_level=hierarchy_level, is_active=True
        )
        serializer = HierarchyValueSerializer(values, many=True)
        return Response(
            {
                "status": "success",
                "code": status.HTTP_200_OK,
                "message": "Hierarchy values retrieved successfully",
                "data": serializer.data,
            }
        )

    @action(detail=True, methods=["post"])
    def add_value(self, request: Request, pk: int = None) -> Response:
        """Adds a new value to a hierarchy level.

        Args:
            request: The HTTP request object with the new value data.
            pk: The primary key of the hierarchy level.

        Returns:
            A Response object with the created hierarchy value.
        """
        hierarchy_level = self.get_object()
        logger.info(f"Adding value to hierarchy level pk={pk}")
        data = request.data.copy()
        # Add hierarchy_level to the data
        data["hierarchy_level"] = hierarchy_level.id
        serializer = HierarchyValueSerializer(data=data)

        if serializer.is_valid():
            try:
                value = serializer.save(hierarchy_level=hierarchy_level)
                return Response(
                    {
                        "status": "success",
                        "code": status.HTTP_201_CREATED,
                        "message": "Hierarchy value added successfully",
                        "data": serializer.data,
                    },
                    status=status.HTTP_201_CREATED,
                )
            except IntegrityError:
                return Response(
                    {
                        "status": "error",
                        "code": status.HTTP_400_BAD_REQUEST,
                        "message": f"A value '{request.data.get('value')}' already exists in this hierarchy level",
                        "data": None,
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )
        return Response(
            {
                "status": "error",
                "code": status.HTTP_400_BAD_REQUEST,
                "message": "Invalid data provided",
                "data": serializer.errors,
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    @action(detail=False, methods=["get"])
    def tree(self, request: Request) -> Response:
        """Returns the hierarchy as a tree structure.

        Args:
            request: The HTTP request object.

        Returns:
            A Response object containing the hierarchy tree.
        """
        organization = request.user.organization
        logger.info(f"Fetching hierarchy tree for organization '{organization.name if organization else 'N/A'}'")
        if not organization:
            return Response(
                {"status": "error", "message": "No organization found."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        levels = OrganizationHierarchyLevel.objects.filter(
            organization=organization, is_active=True
        )
        values = HierarchyValue.objects.filter(
            hierarchy_level__organization=organization, is_active=True
        )
        level_dict = {level.id: level for level in levels}
        value_dict = {}
        for value in values:
            value_dict.setdefault(value.hierarchy_level_id, []).append(
                {
                    "id": value.id,
                    "value": value.value,
                    "description": value.description,
                    "is_active": value.is_active,
                }
            )

        def build_tree(parent_id: int = None) -> Any:
            nodes = []
            for level in levels:
                if level.parent_id == parent_id:
                    node = {
                        "id": level.id,
                        "name": level.name,
                        "description": level.description,
                        "order": level.order,
                        "is_active": level.is_active,
                        "parent": level.parent_id,
                        "children": build_tree(level.id),
                        "values": value_dict.get(level.id, []),
                    }
                    nodes.append(node)
            nodes.sort(key=lambda x: x["order"])
            return nodes

        tree = build_tree(None)
        return Response({"status": "success", "data": tree})


class UserHierarchyMembershipViewSet(viewsets.ModelViewSet):
    """Manages user hierarchy memberships."""

    permission_classes = [permissions.IsAuthenticated]
    serializer_class = UserHierarchyMembershipSerializer

    def get_queryset(self) -> Any:
        """Returns a queryset of user hierarchy memberships.

        The queryset is for the user's organization.

        Returns:
            A queryset of UserHierarchyMembership objects.
        """
        logger.info(f"Fetching user hierarchy queryset for organization '{self.request.user.organization.name if self.request.user.organization else 'N/A'}'")
        if not self.request.user.organization:
            return UserHierarchyMembership.objects.none()
        
        # Determine if we should filter by organization via the hierarchy level
        return UserHierarchyMembership.objects.filter(
            hierarchy_value__hierarchy_level__organization=self.request.user.organization
        )

    @action(detail=False, methods=["get"])
    def user_hierarchies(self, request: Request) -> Response:
        """Gets all hierarchy values for a specific user.

        Args:
            request: The HTTP request object. Expects a `user_id` query param.

        Returns:
            A Response object with the user's hierarchy memberships.
        """
        user_id = request.query_params.get("user_id")
        logger.info(f"Fetching hierarchies for user_id={user_id}")
        if not user_id:
            return Response(
                {
                    "status": "error",
                    "code": status.HTTP_400_BAD_REQUEST,
                    "message": "User ID is required",
                    "data": None,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        memberships = UserHierarchyMembership.objects.filter(
            user_id=user_id,
        )
        # Note: Removing student__organization filter temporarily as user might not have org link via legacy field anymore
        # Ideally we check against tenant or organization membership.

        serializer = UserHierarchyMembershipDetailSerializer(memberships, many=True)
        return Response(
            {
                "status": "success",
                "code": status.HTTP_200_OK,
                "message": "User hierarchies retrieved successfully",
                "data": serializer.data,
            }
        )

    @action(detail=False, methods=["post"])
    def bulk_assign(self, request: Request) -> Response:
        """Bulk assigns hierarchy values to a user.

        Args:
            request: The HTTP request object containing `user_id` and
                `hierarchy_values`.

        Returns:
            A Response object with the created memberships.
        """
        user_id = request.data.get("user_id")
        hierarchy_values = request.data.get("hierarchy_values", [])
        logger.info(f"Bulk assigning hierarchy values for user_id={user_id}")

        if not user_id or not hierarchy_values:
            return Response(
                {
                    "status": "error",
                    "code": status.HTTP_400_BAD_REQUEST,
                    "message": "User ID and hierarchy values are required",
                    "data": None,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            user = User.objects.get(
                id=user_id, organization=self.request.user.organization
            )
        except User.DoesNotExist:
            return Response(
                {
                    "status": "error",
                    "code": status.HTTP_404_NOT_FOUND,
                    "message": "User not found",
                    "data": None,
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        # Remove existing memberships
        UserHierarchyMembership.objects.filter(user=user).delete()

        # Create new memberships
        memberships = []
        for value_id in hierarchy_values:
            try:
                hierarchy_value = HierarchyValue.objects.get(
                    id=value_id,
                    hierarchy_level__organization=self.request.user.organization,
                )
                membership = UserHierarchyMembership.objects.create(
                    user=user, hierarchy_value=hierarchy_value
                )
                memberships.append(membership)
            except HierarchyValue.DoesNotExist:
                logger.warning(f"HierarchyValue with id={value_id} does not exist. Skipping.")
                continue

        serializer = UserHierarchyMembershipSerializer(memberships, many=True)
        return Response(
            {
                "status": "success",
                "code": status.HTTP_201_CREATED,
                "message": "Hierarchy values assigned successfully",
                "data": serializer.data,
            }
        )


class HierarchyValueViewSet(viewsets.ModelViewSet):
    """Manages hierarchy values."""

    permission_classes = [permissions.IsAuthenticated]
    serializer_class = HierarchyValueSerializer

    def get_queryset(self) -> Any:
        """Returns a queryset of hierarchy values for the user's organization.

        Returns:
            A queryset of HierarchyValue objects.
        """
        logger.info(f"Fetching hierarchy value queryset for organization '{self.request.user.organization.name if self.request.user.organization else 'N/A'}'")
        if not self.request.user.organization:
            return HierarchyValue.objects.none()
        return HierarchyValue.objects.filter(
            hierarchy_level__organization=self.request.user.organization
        )

    def perform_create(self, serializer) -> None:
        """Creates a new hierarchy value.

        Ensures the value is associated with a hierarchy level within the
        user's organization.

        Args:
            serializer: The serializer instance for the new value.

        Raises:
            serializers.ValidationError: If the hierarchy level is invalid.
        """
        logger.info(f"Creating hierarchy value for level_id={self.request.data.get('hierarchy_level')}")
        # Ensure the hierarchy level belongs to the user's organization
        hierarchy_level_id = self.request.data.get("hierarchy_level")
        try:
            hierarchy_level = OrganizationHierarchyLevel.objects.get(
                id=hierarchy_level_id,
                organization=self.request.user.organization,
            )
            serializer.save(hierarchy_level=hierarchy_level)
        except OrganizationHierarchyLevel.DoesNotExist:
            raise serializers.ValidationError("Invalid hierarchy level")

    def perform_update(self, serializer) -> None:
        """Updates an existing hierarchy value.

        Ensures that if the hierarchy level is changed, it remains within the
        user's organization.

        Args:
            serializer: The serializer instance for the updated value.

        Raises:
            serializers.ValidationError: If the hierarchy level is invalid.
        """
        # Ensure the hierarchy level belongs to the user's organization
        hierarchy_level_id = self.request.data.get("hierarchy_level")
        logger.info(f"Updating hierarchy value pk={serializer.instance.pk} with level_id={hierarchy_level_id}")
        if hierarchy_level_id:
            try:
                hierarchy_level = OrganizationHierarchyLevel.objects.get(
                    id=hierarchy_level_id,
                    organization=self.request.user.organization,
                )
                serializer.save(hierarchy_level=hierarchy_level)
            except OrganizationHierarchyLevel.DoesNotExist:
                raise serializers.ValidationError("Invalid hierarchy level")
        else:
            serializer.save()


class OrganizationProfileView(APIView):
    """Retrieves and updates the user's organization profile."""
    permission_classes = [IsAuthenticated]

    def get(self, request: Request) -> Response:
        """Retrieves the profile of the user's organization.

        Args:
            request: The HTTP request object.

        Returns:
            A Response object containing the organization's data or an error.
        """
        logger.info(f"Fetching organization profile for user: {request.user.email}")
        org = request.user.organization
        if not org:
            return Response(
                {"detail": "No organization found for user."},
                status=status.HTTP_404_NOT_FOUND,
            )
        serializer = OrganizationListSerializer(org)
        return Response(serializer.data)

    def put(self, request: Request) -> Response:
        """Updates the profile of the user's organization.

        Args:
            request: The HTTP request object with updated data.

        Returns:
            A Response object containing the updated organization's data or an
            error.
        """
        logger.info(f"Updating organization profile for user: {request.user.email}")
        org = request.user.organization
        if not org:
            return Response(
                {"detail": "No organization found for user."},
                status=status.HTTP_404_NOT_FOUND,
            )
        serializer = OrganizationListSerializer(
            org, data=request.data, partial=True
        )
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
# In organization/views.py

class AssignmentManagementViewSet(viewsets.ModelViewSet):
    """
    Manages Assignments, Submissions, and Grading within an organization.
    """
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def get_serializer_class(self):
        if self.action in ['create', 'update', 'partial_update']:
            return AssignmentCreateSerializer
        return AssignmentDetailSerializer

    def get_permissions(self):
        if self.action in ['my_assignments', 'submit', 'retrieve']:
            self.permission_classes = [IsAuthenticated]
        else:
            self.permission_classes = [IsAuthenticated, IsOrgAdmin]
        return super().get_permissions()

    def get_queryset(self):
        user = self.request.user
        if not hasattr(user, 'organization') or not user.organization:
            return Assignment.objects.none()
        assigned_to_prefetch = Prefetch('assigned_to', queryset=HierarchyValue.objects.select_related('hierarchy_level'))
        if user.role_org == 'admin':
            admin_submission_prefetch = Prefetch('submissions', queryset=Submission.objects.prefetch_related('files'))
            return Assignment.objects.filter(organization=user.organization).select_related('creator').prefetch_related('attachments', assigned_to_prefetch, admin_submission_prefetch)
        if user.role_org == 'student':
            student_hierarchy_values = StudentHierarchy.objects.filter(student=user).values_list('hierarchy_value_id', flat=True)
            student_submission_prefetch = Prefetch('submissions', queryset=Submission.objects.filter(student=user).prefetch_related('files'), to_attr='student_submission')
            return Assignment.objects.filter(organization=user.organization, assigned_to__id__in=student_hierarchy_values).select_related('creator').prefetch_related('attachments', assigned_to_prefetch, student_submission_prefetch).distinct()
        return Assignment.objects.none()

    def perform_create(self, serializer):
        assignment_instance = serializer.save(
            creator=self.request.user,
            organization=self.request.user.organization
        )
        # --- LOGGING MOVED HERE ---
        logger.info(
            f"Admin '{self.request.user.email}' (ID: {self.request.user.id}) created Assignment (ID: {assignment_instance.id})."
        )
        uploaded_files = self.request.FILES.getlist('attachments')
        for file in uploaded_files:
            AssignmentAttachment.objects.create(assignment=assignment_instance, file=file)
    
    @action(detail=False, methods=['get'])
    def my_assignments(self, request):
        queryset = self.get_queryset()
        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=['post'], parser_classes=[MultiPartParser, FormParser])
    def submit(self, request, pk=None):
        try:
            assignment = self.get_object()
            student = request.user
            submission, created = Submission.objects.get_or_create(assignment=assignment, student=student)
            if submission.status == 'GRADED':
                return Response({'error': 'Cannot submit to a graded assignment.'}, status=status.HTTP_400_BAD_REQUEST)
            submission.files.all().delete()
            uploaded_files = request.FILES.getlist('files')
            for f in uploaded_files:
                SubmissionFile.objects.create(submission=submission, file=f)
            submission.submitted_at = timezone.now()
            submission.save()
            # --- LOGGING MOVED HERE ---
            logger.info(
                f"Student '{student.email}' (ID: {student.id}) submitted/updated Assignment (ID: {pk}). Submission ID: {submission.id}."
            )
            updated_assignment = self.get_queryset().get(pk=pk)
            serializer = self.get_serializer(updated_assignment)
            return Response(serializer.data, status=status.HTTP_200_OK)
        except Exception:
            logger.exception(f"An unexpected error occurred during submission for Assignment (ID: {pk}) by User (ID: {request.user.id}).")
            return Response({"error": "An internal error occurred."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @action(detail=True, methods=['get'])
    def gradebook(self, request, pk=None):
        assignment = self.get_object()
        assigned_hierarchy_ids = assignment.assigned_to.values_list('id', flat=True)
        students = User.objects.filter(hierarchy_values__hierarchy_value_id__in=assigned_hierarchy_ids, role_org='student').distinct()
        submissions_by_student = {sub.student.id: sub for sub in assignment.submissions.all()}
        gradebook_data = []
        for student in students:
            submission = submissions_by_student.get(student.id)
            files_data = []
            if submission and submission.files.exists():
                files_data = SubmissionFileSerializer(submission.files.all(), many=True, context={'request': request}).data
            gradebook_data.append({
                'student_id': student.id,
                'student_name': student.full_name or student.username,
                'student_email': student.email,
                'status': submission.status if submission else 'PENDING',
                'grade': submission.grade if submission else None,
                'submitted_at': submission.submitted_at if submission else None,
                'submission_id': submission.id if submission else None,
                'files': files_data
            })
        return Response(gradebook_data)

    @action(detail=False, methods=['post'], url_path='submissions/(?P<submission_pk>[^/.]+)/grade')
    def grade_submission(self, request, submission_pk=None):
        try:
            submission = Submission.objects.get(pk=submission_pk, assignment__organization=request.user.organization)
        except Submission.DoesNotExist:
            # --- LOGGING ADDED HERE ---
            logger.warning(
                f"Admin '{request.user.email}' failed to find Submission (ID: {submission_pk}) for grading."
            )
            return Response({'error': 'Submission not found.'}, status=status.HTTP_404_NOT_FOUND)
        serializer = GradeSubmissionSerializer(instance=submission, data=request.data)
        serializer.is_valid(raise_exception=True)
        updated_submission = serializer.save()
        # --- LOGGING MOVED HERE ---
        logger.info(
            f"Admin '{request.user.email}' (ID: {request.user.id}) graded Submission (ID: {updated_submission.id}). "
            f"Grade: {updated_submission.grade}."
        )
        return Response(SubmissionSerializer(updated_submission).data, status=status.HTTP_200_OK)