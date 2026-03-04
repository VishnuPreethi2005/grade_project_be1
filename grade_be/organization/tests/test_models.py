import pytest
from django.utils import timezone
from datetime import timedelta
from authentication.models import User, Organization
from organization.models import StudentInvitation, Test, TestAssignment

@pytest.fixture
def org(db):
    """Fixture for a test Organization."""
    return Organization.objects.create(name="Test University", email="contact@testuni.edu")

@pytest.fixture
def student(db, org):
    """Fixture for a test student associated with an organization."""
    return User.objects.create_user(
        username="test_student",
        email="student@testuni.edu",
        password="password",
        organization=org,
    )

@pytest.fixture
def test_instance(db, org):
    """Fixture for a Test instance."""
    return Test.objects.create(
        title="Mid-term Exam",
        description="A test for the mid-term.",
        start_time=timezone.now(),
        duration_minutes=60,
        organization=org,
    )

def test_student_invitation_creation_and_defaults(org):
    """
    Test that a StudentInvitation is created with correct defaults.
    """
    invitation = StudentInvitation.objects.create(
        email="invitee@example.com",
        organization=org,
    )
    # Test default status
    assert invitation.status == "pending"
    # Test that expires_at is set automatically
    assert invitation.expires_at is not None
    assert invitation.expires_at > timezone.now()

def test_student_invitation_is_expired_method(org):
    """
    Test the is_expired() method on the StudentInvitation model.
    """
    # Test a valid, non-expired invitation
    valid_invitation = StudentInvitation.objects.create(
        email="valid@example.com",
        organization=org,
        expires_at=timezone.now() + timedelta(days=1),
    )
    assert not valid_invitation.is_expired()

    # Test an expired invitation
    expired_invitation = StudentInvitation.objects.create(
        email="expired@example.com",
        organization=org,
        expires_at=timezone.now() - timedelta(days=1),
    )
    assert expired_invitation.is_expired()

def test_test_assignment_unique_together_constraint(student, test_instance):
    """
    Test the unique_together constraint on the TestAssignment model.
    """
    # Create the first assignment, which should succeed
    TestAssignment.objects.create(test=test_instance, student=student)

    # Attempt to create a duplicate assignment, which should fail
    with pytest.raises(Exception) as excinfo:
        TestAssignment.objects.create(test=test_instance, student=student)
    
    # Check that we have a database integrity error
    assert 'UNIQUE constraint failed' in str(excinfo.value) or 'Duplicate entry' in str(excinfo.value)

def test_model_str_representations(org, student, test_instance):
    """
    Test the __str__ methods of the models.
    """
    assert str(test_instance) == "Mid-term Exam"
    
    assignment = TestAssignment.objects.create(test=test_instance, student=student)
    assert str(assignment) == "student@testuni.edu - Mid-term Exam"
    
    invitation = StudentInvitation.objects.create(email="invitee@example.com", organization=org)
    assert str(invitation) == "Invitation for invitee@example.com to Test University"

