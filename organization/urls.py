from django.urls import path
from . import views
from .views import OrganizationProfileView

"""
URL configuration for the organization app.
Defines API endpoints for student management, test management, organization hierarchy, and profile.
"""
app_name = "organization"

urlpatterns = [
    # Student Management URLs
    # List and invite students
    path(
        "api/organization/students/",
        views.StudentManagementViewSet.as_view(
            {"get": "list", "post": "create"}
        ),
        name="student-list",
    ),
    # Remove a student
    path(
        "api/organization/students/<int:pk>/remove/",
        views.StudentManagementViewSet.as_view({"post": "remove"}),
        name="student-remove",
    ),
    # List pending invitations
    path(
        "api/organization/students/pending_invitations/",
        views.StudentManagementViewSet.as_view({"get": "pending_invitations"}),
        name="student-pending-invitations",
    ),
    # Cancel a student invitation
    path(
        "api/organization/students/<int:pk>/cancel_invitation/",
        views.StudentManagementViewSet.as_view({"post": "cancel_invitation"}),
        name="student-cancel-invitation",
    ),
    # Accept a student invitation
    path(
        "api/organization/students/accept_invitation/<str:token>/",
        views.StudentManagementViewSet.as_view({"post": "accept_invitation"}),
        name="student-accept-invitation",
    ),
    # Upload students via CSV
    path(
        "api/organization/students/upload_csv/",
        views.StudentManagementViewSet.as_view({"post": "upload_csv"}),
        name="student-upload-csv",
    ),
    # Assignment Management URLs
    # List and create assignments (for admins)
    path(
        "api/organization/assignments/",
        views.AssignmentManagementViewSet.as_view(
            {"get": "list", "post": "create"}
        ),
        name="assignment-list-create",
    ),
    # Retrieve, update, or delete a specific assignment (for admins)
    path(
        "api/organization/assignments/<int:pk>/",
        views.AssignmentManagementViewSet.as_view(
            {
                "get": "retrieve",
                "put": "update",
                "patch": "partial_update",
                "delete": "destroy",
            }
        ),
        name="assignment-detail",
    ),
    # Get assignments for the currently logged-in student
    path(
        "api/organization/assignments/my_assignments/",
        views.AssignmentManagementViewSet.as_view({"get": "my_assignments"}),
        name="assignment-my-assignments",
    ),
    # Submit files for an assignment (for students)
    path(
        "api/organization/assignments/<int:pk>/submit/",
        views.AssignmentManagementViewSet.as_view({"post": "submit"}),
        name="assignment-submit",
    ),
    # Get the gradebook/submission status for an assignment (for admins)
    path(
        "api/organization/assignments/<int:pk>/gradebook/",
        views.AssignmentManagementViewSet.as_view({"get": "gradebook"}),
        name="assignment-gradebook",
    ),
    # Grade a specific submission (for admins)
    path(
        "api/organization/assignments/submissions/<int:submission_pk>/grade/",
        views.AssignmentManagementViewSet.as_view({"post": "grade_submission"}),
        name="assignment-grade-submission",
    ),
    # Test Management URLs
    # List and create tests
    path(
        "api/organization/tests/",
        views.TestManagementViewSet.as_view({"get": "list", "post": "create"}),
        name="test-list",
    ),
    # Retrieve, update, or delete a test
    path(
        "api/organization/tests/<int:pk>/",
        views.TestManagementViewSet.as_view(
            {
                "get": "retrieve",
                "put": "update",
                "patch": "partial_update",
                "delete": "destroy",
            }
        ),
        name="test-detail",
    ),
    # Upload a question paper for a test
    path(
        "api/organization/tests/<int:pk>/upload_question_paper/",
        views.TestManagementViewSet.as_view({"post": "upload_question_paper"}),
        name="test-upload-question-paper",
    ),
    # Assign students to a test
    path(
        "api/organization/tests/<int:pk>/assign_students/",
        views.TestManagementViewSet.as_view({"post": "assign_students"}),
        name="test-assign-students",
    ),
    # List students assigned to a test
    path(
        "api/organization/tests/<int:pk>/assigned_students/",
        views.TestManagementViewSet.as_view({"get": "assigned_students"}),
        name="test-assigned-students",
    ),
    # List tests assigned to the current student
    path(
        "api/organization/tests/assigned_tests/",
        views.TestManagementViewSet.as_view({"get": "assigned_tests"}),
        name="test-assigned-tests",
    ),
    # Get results for a test
    path(
        "api/organization/tests/<int:pk>/results/",
        views.TestManagementViewSet.as_view({"get": "results"}),
        name="test-results",
    ),
    # Trigger AI grading for a test
    path(
        "api/organization/tests/<int:pk>/grade_with_ai/",
        views.TestManagementViewSet.as_view({"post": "grade_with_ai"}),
        name="test-grade-with-ai",
    ),
    # List questions for a test
    path(
        "api/organization/tests/<int:pk>/questions/",
        views.TestManagementViewSet.as_view({"get": "questions"}),
        name="test-questions",
    ),
    # Submit answers for a test
    path(
        "api/organization/tests/<int:pk>/submit/",
        views.TestManagementViewSet.as_view({"post": "submit_answers"}),
        name="test-submit-answers",
    ),
    # Check submission status for a test
    path(
        "api/organization/tests/<int:pk>/check_submission/",
        views.TestManagementViewSet.as_view({"get": "check_submission"}),
        name="test-check-submission",
    ),
    # Get progress summary for the organization
    path(
        "api/organization/progress_summary/",
        views.TestManagementViewSet.as_view({"get": "progress_summary"}),
        name="progress-summary",
    ),
    # Organization Hierarchy URLs
    # List and create hierarchy levels
    path(
        "api/organization/hierarchy-levels/",
        views.OrganizationHierarchyViewSet.as_view(
            {"get": "list", "post": "create"}
        ),
        name="hierarchy-level-list",
    ),
    # Retrieve, update, or delete a hierarchy level
    path(
        "api/organization/hierarchy-levels/<int:pk>/",
        views.OrganizationHierarchyViewSet.as_view(
            {
                "get": "retrieve",
                "put": "update",
                "patch": "partial_update",
                "delete": "destroy",
            }
        ),
        name="hierarchy-level-detail",
    ),
    # List values for a hierarchy level
    path(
        "api/organization/hierarchy-levels/<int:pk>/values/",
        views.OrganizationHierarchyViewSet.as_view({"get": "values"}),
        name="hierarchy-level-values",
    ),
    # Add a value to a hierarchy level
    path(
        "api/organization/hierarchy-levels/<int:pk>/add_value/",
        views.OrganizationHierarchyViewSet.as_view({"post": "add_value"}),
        name="hierarchy-level-add-value",
    ),
    # Get the hierarchy tree
    path(
        "api/organization/hierarchy-levels/tree/",
        views.OrganizationHierarchyViewSet.as_view({"get": "tree"}),
        name="hierarchy-level-tree",
    ),
    # Hierarchy Values URLs
    # List and create hierarchy values
    path(
        "api/organization/hierarchy-values/",
        views.HierarchyValueViewSet.as_view({"get": "list", "post": "create"}),
        name="hierarchy-value-list",
    ),
    # Retrieve, update, or delete a hierarchy value
    path(
        "api/organization/hierarchy-values/<int:pk>/",
        views.HierarchyValueViewSet.as_view(
            {
                "get": "retrieve",
                "put": "update",
                "patch": "partial_update",
                "delete": "destroy",
            }
        ),
        name="hierarchy-value-detail",
    ),
    # User Hierarchy Membership URLs
    # List and create user hierarchies
    path(
        "api/organization/user-hierarchies/",
        views.UserHierarchyMembershipViewSet.as_view(
            {"get": "list", "post": "create"}
        ),
        name="user-hierarchy-list",
    ),
    # Retrieve, update, or delete a user hierarchy
    path(
        "api/organization/user-hierarchies/<int:pk>/",
        views.UserHierarchyMembershipViewSet.as_view(
            {
                "get": "retrieve",
                "put": "update",
                "patch": "partial_update",
                "delete": "destroy",
            }
        ),
        name="user-hierarchy-detail",
    ),
    # List hierarchy values for a user
    path(
        "api/organization/user-hierarchies/user_hierarchies/",
        views.UserHierarchyMembershipViewSet.as_view({"get": "user_hierarchies"}),
        name="user-hierarchy-values",
    ),
    # Bulk assign hierarchy values to users
    path(
        "api/organization/user-hierarchies/bulk_assign/",
        views.UserHierarchyMembershipViewSet.as_view({"post": "bulk_assign"}),
        name="user-hierarchy-bulk-assign",
    ),
    # Organization profile endpoint
    path(
        "api/organization/profile/",
        OrganizationProfileView.as_view(),
        name="organization-profile",
    ),
    # Delegation Management URLs
    # Delegate a test to evaluators
    path(
        "api/organization/delegations/delegate-test/",
        views.DelegationViewSet.as_view({"post": "delegate_test"}),
        name="delegation-delegate-test",
    ),
    # List delegations created by user
    path(
        "api/organization/delegations/my-delegations/",
        views.DelegationViewSet.as_view({"get": "my_delegations"}),
        name="delegation-my-delegations",
    ),
    # List evaluations assigned to current user
    path(
        "api/organization/delegations/assigned-to-me/",
        views.DelegationViewSet.as_view({"get": "assigned_to_me"}),
        name="delegation-assigned-to-me",
    ),
    # Update evaluation assignment status
    path(
        "api/organization/delegations/<int:pk>/update-status/",
        views.DelegationViewSet.as_view({"put": "update_status"}),
        name="delegation-update-status",
    ),
    # Get delegation statistics
    path(
        "api/organization/delegations/stats/",
        views.DelegationViewSet.as_view({"get": "stats"}),
        name="delegation-stats",
    ),
    # Get available evaluators
    path(
        "api/organization/delegations/available-evaluators/",
        views.DelegationViewSet.as_view({"get": "available_evaluators"}),
        name="delegation-available-evaluators",
    ),
]
