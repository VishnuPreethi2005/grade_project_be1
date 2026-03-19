from django.urls import path
from .views import (
    RegisterView,
    LoginView,
    VerifyOTPView,
    ResendOTPView,
    ForgotPasswordView,
    ResetPasswordView,
    UpdateUserRolesView,
    UpdateActiveRoleView,
    BillingInfoView,
    UserCreditView,
    CreateRazorpayOrderView,
    VerifyPaymentView,
    update_profile,
    update_profile_pic,
    delete_profile_picture,
    add_role,
    OrganizationRegistrationViewSet,
    check_user_exists,
    user_count,
    user_role_counts,
    ProductListView,
    CreateBookOrderView,
    VerifyBookPaymentView,
    UserPurchasesView,
    BookPDFAccessView,
)
from . import user_invitation_views

# from .views import TokenRefreshView
from rest_framework_simplejwt.views import TokenRefreshView  # Add this import


urlpatterns = [
    # User authentication URLs
    path("api/signup/", RegisterView.as_view(), name="register"),
    path("api/verify-otp/", VerifyOTPView.as_view(), name="verify_otp"),
    path("api/resend-otp/", ResendOTPView.as_view(), name="resend_otp"),
    path("api/login/", LoginView.as_view(), name="login"),
    path(
        "api/forgot-password/",
        ForgotPasswordView.as_view(),
        name="forgot_password",
    ),
    path(
        "api/reset-password/",
        ResetPasswordView.as_view(),
        name="reset_password",
    ),
    # Organization authentication URLs
    path("api/user/credits/", UserCreditView.as_view(), name="user-credits"),
    path(
        "api/payments/create-order/",
        CreateRazorpayOrderView.as_view(),
        name="create-order",
    ),
    path(
        "api/payments/verify/",
        VerifyPaymentView.as_view(),
        name="verify-payment",
    ),
    path(
        "api/token/refresh/", TokenRefreshView.as_view(), name="token_refresh"
    ),
    path("api/update-profile/", update_profile, name="update_profile"),
    path("api/update-profile-pic/", update_profile_pic, name="update_profile_pic"),
    path("api/delete-profile-picture/", delete_profile_picture, name="delete_profile_picture"),
    path(
        "api/update-user-roles/",
        UpdateUserRolesView.as_view(),
        name="update-user-roles",
    ),
    path(
        "api/update-active-role/",
        UpdateActiveRoleView.as_view(),
        name="update-active-role",
    ),
    path("api/add_role/", add_role, name="add_role"),
    path("api/billing/", BillingInfoView.as_view(), name="billing-info"),
    # Organization registration and verification
    path(
        "api/organization/register/",
        OrganizationRegistrationViewSet.as_view({"post": "create"}),
        name="organization-register",
    ),
    path(
        "api/organization/verify/<int:pk>/",
        OrganizationRegistrationViewSet.as_view({"post": "verify"}),
        name="organization-verify",
    ),
    path(
        "api/organization/reject/<int:pk>/",
        OrganizationRegistrationViewSet.as_view({"post": "reject"}),
        name="organization-reject",
    ),
    path(
        "api/organization/list/",
        OrganizationRegistrationViewSet.as_view({"get": "list"}),
        name="organization-list",
    ),
    path(
        "api/organization/<int:pk>/view_document/",
        OrganizationRegistrationViewSet.as_view({"get": "view_document"}),
        name="organization-view-document",
    ),
    # New organization management endpoints
    path("api/auth/check-user/", check_user_exists, name="check-user"),
    path("api/user-count/", user_count, name="user-count"),
    path("api/user-role-counts/", user_role_counts, name="user-role-counts"),
    # Book/Product purchase URLs
    path("api/products/", ProductListView.as_view(), name="product-list"),
    path("api/products/create-order/", CreateBookOrderView.as_view(), name="create-book-order"),
    path("api/products/verify-payment/", VerifyBookPaymentView.as_view(), name="verify-book-payment"),
    path("api/products/my-purchases/", UserPurchasesView.as_view(), name="user-purchases"),
    path("api/products/<int:product_id>/pdf/", BookPDFAccessView.as_view(), name="book-pdf-access"),
    
    # User Invitation URLs
    path('api/auth/invitations/search/', user_invitation_views.UserInvitationViewSet.as_view({'get': 'search_users'}), name='invitation-search'),
    path('api/auth/invitations/invite/', user_invitation_views.UserInvitationViewSet.as_view({'post': 'invite_user'}), name='invitation-invite'),
    path('api/auth/invitations/pending/', user_invitation_views.UserInvitationViewSet.as_view({'get': 'pending_invitations'}), name='invitation-pending'),
    path('api/auth/invitations/accept/', user_invitation_views.UserInvitationViewSet.as_view({'post': 'accept_invitation'}), name='invitation-accept'),
    path('api/auth/invitations/<int:pk>/resend/', user_invitation_views.UserInvitationViewSet.as_view({'post': 'resend_invitation'}), name='invitation-resend'),
    path('api/auth/invitations/<int:pk>/cancel/', user_invitation_views.UserInvitationViewSet.as_view({'post': 'cancel_invitation'}), name='invitation-cancel'),
]
