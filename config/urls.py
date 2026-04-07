"""
URL configuration for Alba Capital ERP System
"""

from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path

from core.services.webhooks import odoo_webhook_receiver
from core.verification_views import (
    DocumentUploadView,
    ProfileUpdateView,
    VerificationSubmitView,
    client_profile_verification,
    verification_status,
)

urlpatterns = [
    # Admin
    path("admin/", admin.site.urls),
    # Allauth (Google OAuth callbacks)
    path("accounts/", include("allauth.urls")),
    # Core app (authentication, landing page, dashboards)
    path("", include("core.urls")),
    # Loans app (customer-facing loan portal)
    path("loans/", include("loans.urls")),
    # ── Document Verification Wizard ─────────────────────────────────────────
    path(
        "verify/profile/",
        client_profile_verification,
        name="client_profile_verification",
    ),
    path(
        "api/verify/documents/upload/",
        DocumentUploadView.as_view(),
        name="document_upload",
    ),
    path(
        "api/verify/profile/update/", ProfileUpdateView.as_view(), name="profile_update"
    ),
    path(
        "api/verify/submit/",
        VerificationSubmitView.as_view(),
        name="verification_submit",
    ),
    path("api/verify/status/", verification_status, name="verification_status"),
    # ── Odoo Integration Webhooks ────────────────────────────────────────────
    # Receives HMAC-SHA256-signed event notifications from Odoo.
    # Odoo fires POST requests here whenever application statuses change,
    # loans are disbursed, payments are matched, KYC is verified, etc.
    # The URL must match the webhook_path configured on the Odoo API key record
    # (Settings: Alba Integration → API Keys → Webhook Path).
    path("api/v1/webhooks/odoo/", odoo_webhook_receiver, name="odoo_webhook_receiver"),
]

# Serve media and static files in development
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)

# Custom error handlers
handler404 = "core.views.page_not_found"
handler500 = "core.views.server_error"

# Customize admin site
admin.site.site_header = "Alba Capital Administration"
admin.site.site_title = "Alba Capital"
admin.site.index_title = "System Administration"
