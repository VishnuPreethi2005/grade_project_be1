import pytest
from rest_framework import serializers
from django.core.files.uploadedfile import SimpleUploadedFile
from authentication.models import User, Organization
from organization.models import (
    OrganizationHierarchyLevel,
    HierarchyValue,
    UserHierarchyMembership,
)
from organization.serializers import (
    AddStudentSerializer,
    BulkAddStudentSerializer,
    CSVUploadSerializer,
    UserHierarchyMembershipDetailSerializer,
)

@pytest.fixture
def org(db):
    """Fixture for a test Organization."""
    return Organization.objects.create(name="Test University", email="contact@testuni.edu")

@pytest.fixture
def user_no_org(db):
    """Fixture for a user not associated with any organization."""
    return User.objects.create_user(username="new_student", email="new@student.com", password="password")

@pytest.fixture
def user_with_org(db, org):
    """Fixture for a user already associated with an organization."""
    return User.objects.create_user(
        username="existing_student",
        email="existing@student.com",
        password="password",
        organization=org,
    )

@pytest.fixture
def hierarchy_level(db, org):
    """Fixture for an OrganizationHierarchyLevel."""
    return OrganizationHierarchyLevel.objects.create(organization=org, name="Department", order=1)

@pytest.fixture
def hierarchy_value(db, hierarchy_level):
    """Fixture for a HierarchyValue."""
    return HierarchyValue.objects.create(hierarchy_level=hierarchy_level, value="Computer Science")

def test_add_student_serializer_valid(user_no_org):
    """Test AddStudentSerializer with a valid, unaffiliated user."""
    serializer = AddStudentSerializer(data={'email': user_no_org.email})
    assert serializer.is_valid(raise_exception=True)
    assert serializer.validated_data['email'] == user_no_org.email

def test_add_student_serializer_user_in_org(user_with_org):
    """Test that the serializer fails if the user is already in an organization."""
    serializer = AddStudentSerializer(data={'email': user_with_org.email})
    with pytest.raises(serializers.ValidationError) as excinfo:
        serializer.is_valid(raise_exception=True)
    assert "already associated" in str(excinfo.value)

def test_add_student_serializer_user_not_found(db):
    """Test that the serializer fails if the user does not exist."""
    serializer = AddStudentSerializer(data={'email': 'nonexistent@email.com'})
    with pytest.raises(serializers.ValidationError) as excinfo:
        serializer.is_valid(raise_exception=True)
    assert "No user found" in str(excinfo.value)

def test_bulk_add_student_serializer_valid():
    """Test BulkAddStudentSerializer with a valid list of emails."""
    emails = ["student1@test.com", "student2@test.com"]
    serializer = BulkAddStudentSerializer(data={'emails': emails})
    assert serializer.is_valid(raise_exception=True)
    assert serializer.validated_data['emails'] == emails

def test_csv_upload_serializer_valid():
    """Test CSVUploadSerializer with a valid file upload."""
    csv_file = SimpleUploadedFile("students.csv", b"email\nstudent@test.com")
    serializer = CSVUploadSerializer(data={'file': csv_file})
    assert serializer.is_valid(raise_exception=True)

def test_user_hierarchy_membership_detail_serializer(user_with_org, hierarchy_value):
    """Test the detail serializer for user hierarchy membership."""
    user_hierarchy = UserHierarchyMembership.objects.create(
        user=user_with_org, hierarchy_value=hierarchy_value
    )
    serializer = UserHierarchyMembershipDetailSerializer(instance=user_hierarchy)
    data = serializer.data

    assert data['id'] == user_hierarchy.id
    assert data['hierarchy_level']['id'] == hierarchy_value.hierarchy_level.id
    assert data['hierarchy_level']['name'] == "Department"
    assert data['value'] == "Computer Science"