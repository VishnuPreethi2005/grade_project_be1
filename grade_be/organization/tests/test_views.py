import pytest
from rest_framework.test import APIClient
from rest_framework import status
from django.urls import reverse
from unittest.mock import patch
from authentication.models import User, Organization
from organization.models import StudentInvitation
from django.core.files.uploadedfile import SimpleUploadedFile

@pytest.fixture
def api_client():
    """Provide an APIClient instance for making test requests.

    Returns:
        APIClient: An instance of the REST Framework APIClient.
    """
    return APIClient()

@pytest.fixture
def org(db):
    """Provide a sample Organization for testing.

    Args:
        db: The pytest-django database fixture.

    Returns:
        Organization: A sample `Organization` instance.
    """
    return Organization.objects.create(name="Test University", email="contact@testuni.edu")

@pytest.fixture
def org_admin(db, org):
    """Provide an admin user for the test organization.

    Args:
        db: The pytest-django database fixture.
        org: The `Organization` instance to which the admin belongs.

    Returns:
        User: An admin `User` instance for the organization.
    """
    return User.objects.create_user(
        username="org_admin",
        email="admin@testuni.edu",
        password="password",
        organization=org,
        role_org="admin",
    )

@pytest.fixture
def student_in_org(db, org):
    """Provide a student user within the test organization.

    Args:
        db: The pytest-django database fixture.
        org: The `Organization` instance to which the student belongs.

    Returns:
        User: A student `User` instance for the organization.
    """
    return User.objects.create_user(
        username="student_member",
        email="student@testuni.edu",
        password="password",
        organization=org,
        role_org="student",
    )

@pytest.fixture
def unaffiliated_user(db):
    """Provide a user that is not part of any organization.

    Args:
        db: The pytest-django database fixture.

    Returns:
        User: A `User` instance without an organization.
    """
    return User.objects.create_user(
        username="new_user",
        email="new@example.com",
        password="password",
    )

@pytest.fixture
def pending_invitation(db, org, unaffiliated_user):
    """Provide a pending `StudentInvitation`.

    Args:
        db: The pytest-django database fixture.
        org: The `Organization` sending the invitation.
        unaffiliated_user: The `User` being invited.

    Returns:
        StudentInvitation: A `StudentInvitation` instance with 'pending' status.
    """
    return StudentInvitation.objects.create(
        email=unaffiliated_user.email,
        organization=org,
    )

# --- Tests for StudentManagementViewSet ---

def test_list_students_as_admin(api_client, org_admin, student_in_org):
    """Verify an organization admin can list students in their organization."""
    api_client.force_authenticate(user=org_admin)
    url = reverse("organization:student-list")
    response = api_client.get(url)

    assert response.status_code == status.HTTP_200_OK
    assert len(response.data['data']) == 1
    assert response.data['data'][0]['email'] == student_in_org.email

def test_list_students_unauthenticated(api_client):
    """Verify unauthenticated users cannot list students."""
    url = reverse("organization:student-list")
    response = api_client.get(url)
    assert response.status_code == status.HTTP_401_UNAUTHORIZED

@patch('organization.views.StudentManagementViewSet._send_invitation_email')
def test_invite_student_as_admin_success(mock_send_email, api_client, org_admin, unaffiliated_user):
    """Verify an admin can successfully invite a new student."""
    api_client.force_authenticate(user=org_admin)
    url = reverse("organization:student-list")
    data = {'email': unaffiliated_user.email}
    response = api_client.post(url, data)

    assert response.status_code == status.HTTP_200_OK
    mock_send_email.assert_called_once()

def test_invite_student_as_student_forbidden(api_client, student_in_org, unaffiliated_user):
    """Verify a non-admin student cannot invite users."""
    api_client.force_authenticate(user=student_in_org)
    url = reverse("organization:student-list")
    data = {'email': unaffiliated_user.email}
    response = api_client.post(url, data)
    assert response.status_code == status.HTTP_403_FORBIDDEN

def test_invite_student_already_in_org_fails(api_client, org_admin, student_in_org):
    """Verify inviting a student already in the organization fails."""
    api_client.force_authenticate(user=org_admin)
    url = reverse("organization:student-list")
    data = {'email': student_in_org.email}
    response = api_client.post(url, data)
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "Invalid data provided" in response.data['message']

def test_pending_invitations_as_admin(api_client, org_admin, pending_invitation):
    """Verify an admin can list pending invitations."""
    api_client.force_authenticate(user=org_admin)
    url = reverse("organization:student-pending-invitations")
    response = api_client.get(url)

    assert response.status_code == status.HTTP_200_OK
    assert len(response.data['data']) == 1
    assert response.data['data'][0]['email'] == pending_invitation.email

def test_cancel_invitation_as_admin(api_client, org_admin, pending_invitation):
    """Verify an admin can cancel a pending invitation."""
    api_client.force_authenticate(user=org_admin)
    url = reverse("organization:student-cancel-invitation", kwargs={'pk': pending_invitation.id})
    response = api_client.post(url)
    pending_invitation.refresh_from_db()

    assert response.status_code == status.HTTP_200_OK
    assert pending_invitation.status == 'rejected'

def test_remove_student_as_admin(api_client, org_admin, student_in_org):
    """Verify an admin can remove a student from the organization."""
    api_client.force_authenticate(user=org_admin)
    url = reverse("organization:student-remove", kwargs={'pk': student_in_org.id})
    response = api_client.post(url)
    student_in_org.refresh_from_db()

    assert response.status_code == status.HTTP_200_OK
    assert student_in_org.organization is None

def test_accept_valid_invitation(api_client, unaffiliated_user, pending_invitation):
    """Verify a user can accept a valid invitation token."""
    api_client.force_authenticate(user=unaffiliated_user)
    url = reverse("organization:student-accept-invitation", kwargs={'token': str(pending_invitation.token)})
    response = api_client.post(url)
    unaffiliated_user.refresh_from_db()

    assert response.status_code == status.HTTP_200_OK
    assert unaffiliated_user.organization == pending_invitation.organization

@patch('organization.views.StudentManagementViewSet._send_invitation_email')
def test_upload_csv_as_admin(mock_send_email, api_client, org_admin):
    """Verify an admin can invite students via CSV upload."""
    csv_content = "email\ncsv.user@example.com\n"
    csv_file = SimpleUploadedFile("students.csv", csv_content.encode('utf-8'), "text/csv")
    
    api_client.force_authenticate(user=org_admin)
    url = reverse("organization:student-upload-csv")
    response = api_client.post(url, {'file': csv_file}, format='multipart')

    assert response.status_code == status.HTTP_200_OK
    assert StudentInvitation.objects.filter(email="csv.user@example.com", organization=org_admin.organization).exists()
    assert mock_send_email.call_count == 1 