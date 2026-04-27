"""
URL configuration for core app
"""

from django.contrib.auth import views as auth_views
from django.urls import path

from . import views
from .admin_views import (
    admin_dashboard,
    user_management,
    user_detail,
    loan_management,
    loan_detail,
    product_management,
    audit_logs,
    system_settings,
    api_status,
    test_odoo_connection,
)

urlpatterns = [
    # Landing page
    path("", views.landing_page, name="landing"),
    # Authentication
    path("login/", views.LoginView.as_view(), name="login"),
    path("register/", views.RegisterView.as_view(), name="register"),
    path("logout/", views.logout_view, name="logout"),
    # Google OAuth shortcut (redirects to allauth's Google login)
    path("auth/google/", views.google_login, name="google_login"),
    # Password reset flow
    path(
        "password-reset/",
        auth_views.PasswordResetView.as_view(
            template_name="core/password_reset.html",
            email_template_name="core/email/password_reset_email.html",
            subject_template_name="core/email/password_reset_subject.txt",
            success_url="/password-reset/done/",
        ),
        name="password_reset",
    ),
    path(
        "password-reset/done/",
        auth_views.PasswordResetDoneView.as_view(
            template_name="core/password_reset_done.html",
        ),
        name="password_reset_done",
    ),
    path(
        "password-reset-confirm/<uidb64>/<token>/",
        auth_views.PasswordResetConfirmView.as_view(
            template_name="core/password_reset_confirm.html",
            success_url="/password-reset-complete/",
        ),
        name="password_reset_confirm",
    ),
    path(
        "password-reset-complete/",
        auth_views.PasswordResetCompleteView.as_view(
            template_name="core/password_reset_complete.html",
        ),
        name="password_reset_complete",
    ),
    # Dashboards
    path("dashboard/", views.DashboardView.as_view(), name="dashboard"),
    path(
        "customer/dashboard/",
        views.CustomerDashboardView.as_view(),
        name="customer_dashboard",
    ),
    # ── Admin Panel ─────────────────────────────────────────────────────────
    path("admin-panel/", admin_dashboard, name="admin_dashboard"),
    path("admin-panel/users/", user_management, name="admin_user_management"),
    path("admin-panel/users/<int:user_id>/", user_detail, name="admin_user_detail"),
    path("admin-panel/loans/", loan_management, name="admin_loan_management"),
    path("admin-panel/loans/<int:application_id>/", loan_detail, name="admin_loan_detail"),
    path("admin-panel/products/", product_management, name="admin_product_management"),
    path("admin-panel/audit-logs/", audit_logs, name="admin_audit_logs"),
    path("admin-panel/settings/", system_settings, name="admin_settings"),
    path("admin-panel/api/status/", api_status, name="admin_api_status"),
    path("admin-panel/api/test-odoo/", test_odoo_connection, name="admin_test_odoo"),
    # ── Odoo Webhook Receiver ────────────────────────────────────────────────
    path("api/v1/webhooks/odoo/", views.odoo_webhook, name="odoo_webhook"),
]
