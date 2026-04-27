"""
Core views for Alba Capital ERP System
Handles: landing page, authentication, customer dashboard
"""

import logging

from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import redirect, render
from django.views.generic import TemplateView
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from .forms import LoginForm, UserRegistrationForm
from .models import AuditLog, User

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def get_client_ip(request):
    """Extract client IP from request headers"""
    x_forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
    if x_forwarded_for:
        return x_forwarded_for.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR")


def create_audit_log(user, action, model_name, object_id, description, request=None):
    """Create an immutable audit log entry"""
    AuditLog.objects.create(
        user=user,
        action=action,
        model_name=model_name,
        object_id=str(object_id) if object_id else "",
        description=description,
        ip_address=get_client_ip(request) if request else None,
        user_agent=request.META.get("HTTP_USER_AGENT", "") if request else "",
    )


# ---------------------------------------------------------------------------
# Public pages
# ---------------------------------------------------------------------------


def landing_page(request):
    """Public landing / marketing page — always shown, even when logged in."""
    return render(request, "landing.html")


def google_login(request):
    """Redirect to allauth's Google OAuth2 login endpoint."""
    return redirect("/accounts/google/login/")


def csrf_failure(request, reason=""):
    """Custom CSRF failure page"""
    return render(
        request,
        "core/login.html",
        {
            "error": "Security token expired. Please try again.",
        },
        status=403,
    )


# ---------------------------------------------------------------------------
# Authentication
# ---------------------------------------------------------------------------


class LoginView(TemplateView):
    template_name = "core/login.html"

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated:
            return redirect("dashboard")
        return super().dispatch(request, *args, **kwargs)

    def get(self, request, *args, **kwargs):
        form = LoginForm()
        return render(request, self.template_name, {"form": form})

    def post(self, request, *args, **kwargs):
        form = LoginForm(data=request.POST)
        if form.is_valid():
            email = form.cleaned_data["username"]  # AuthenticationForm uses 'username'
            password = form.cleaned_data["password"]
            user = authenticate(request, username=email, password=password)

            if user is not None:
                if not user.is_active:
                    messages.error(
                        request,
                        "Your account has been deactivated. Please contact support.",
                    )
                    return render(request, self.template_name, {"form": form})

                login(request, user)

                if not form.cleaned_data.get("remember_me"):
                    request.session.set_expiry(0)

                create_audit_log(
                    user,
                    "LOGIN",
                    "User",
                    user.pk,
                    f"User {user.email} logged in",
                    request,
                )
                messages.success(request, f"Welcome back, {user.get_short_name()}!")
                
                # Redirect admins/superusers to admin panel, others to dashboard
                if user.is_superuser or getattr(user, 'role', '') == 'ADMIN':
                    return redirect("admin_dashboard")
                return redirect("dashboard")
            else:
                messages.error(request, "Invalid email or password.")
        else:
            messages.error(request, "Please correct the errors below.")

        return render(request, self.template_name, {"form": form})


class RegisterView(TemplateView):
    template_name = "core/register.html"

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated:
            # Redirect admins to admin panel, others to dashboard
            if request.user.is_superuser or getattr(request.user, 'role', '') == 'ADMIN':
                return redirect("admin_dashboard")
            return redirect("dashboard")
        return super().dispatch(request, *args, **kwargs)

    def get(self, request, *args, **kwargs):
        form = UserRegistrationForm()
        return render(request, self.template_name, {"form": form})

    def post(self, request, *args, **kwargs):
        form = UserRegistrationForm(request.POST)
        if form.is_valid():
            user = form.save(commit=False)
            user.role = User.CUSTOMER
            user.is_approved = True
            user.save()
            create_audit_log(
                user,
                "CREATE",
                "User",
                user.pk,
                f"New customer registered: {user.email}",
                request,
            )
            messages.success(
                request,
                (
                    "Registration successful! Welcome to Alba Capital. "
                    "You can now log in to access your account."
                ),
            )
            return redirect("login")
        return render(request, self.template_name, {"form": form})


def logout_view(request):
    """Log the user out and redirect to landing page."""
    if request.user.is_authenticated:
        create_audit_log(
            request.user,
            "LOGOUT",
            "User",
            request.user.pk,
            f"User {request.user.email} logged out",
            request,
        )
    logout(request)
    messages.info(request, "You have been logged out successfully.")
    return redirect("landing")


# ---------------------------------------------------------------------------
# Dashboards
# ---------------------------------------------------------------------------


class DashboardView(LoginRequiredMixin, TemplateView):
    """Entry-point dashboard - routes customers to customer portal, allows admin to Django panel"""

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect("login")

        user = request.user

        if user.role == User.CUSTOMER:
            return redirect("customer_dashboard")

        # Admin role gets access to Django admin panel
        if user.role == User.ADMIN or user.is_superuser:
            return redirect("admin_dashboard")

        # Other staff roles (CREDIT_OFFICER, FINANCE_OFFICER, etc.) should use Odoo
        messages.warning(
            request,
            "Staff access is through Odoo. Please use the Odoo portal for administrative functions.",
        )
        logout(request)
        return redirect("login")

    def get(self, request, *args, **kwargs):
        return redirect("login")


class CustomerDashboardView(LoginRequiredMixin, TemplateView):
    """Customer portal dashboard"""

    template_name = "core/customer_dashboard.html"

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated and request.user.role != User.CUSTOMER:
            messages.warning(request, "Access denied. This is the customer portal.")
            return redirect("dashboard")
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user

        context["user_name"] = user.get_full_name()
        context["user_email"] = user.email
        context["member_since"] = user.date_joined

        # --- Loan / customer profile data ---
        try:
            from loans.models import (  # noqa: PLC0415
                Customer,
                Loan,
                LoanApplication,
                LoanProduct,
            )

            customer_profile, _ = Customer.objects.get_or_create(user=user)
            context["customer_profile"] = customer_profile
            context["kyc_verified"] = customer_profile.kyc_verified
            context["monthly_income"] = customer_profile.monthly_income or 0
            context["employment_status"] = (
                customer_profile.get_employment_status_display()
            )
            context["employer_name"] = customer_profile.employer_name or ""
            context["has_national_id"] = bool(customer_profile.national_id_file)
            context["has_bank_statement"] = bool(customer_profile.bank_statement_file)
            context["has_face_photo"] = bool(customer_profile.face_recognition_photo)

            # Use the model's method for consistent calculation
            context["kyc_completion"] = customer_profile.get_kyc_completion_percentage()

            applications = LoanApplication.objects.filter(  # type: ignore[attr-defined]
                customer=customer_profile
            ).order_by("-created_at")
            context["applications_count"] = applications.count()
            context["recent_applications"] = applications[:5]

            active_loans = Loan.objects.filter(  # type: ignore[attr-defined]
                customer=customer_profile, status="ACTIVE"
            )
            context["active_loans_count"] = active_loans.count()
            context["recent_loans"] = active_loans.order_by("-disbursement_date")[:5]
            from django.db.models import Sum

            context["total_borrowed"] = (
                active_loans.aggregate(total=Sum("principal_amount"))["total"] or 0
            )

            context["available_products"] = LoanProduct.objects.filter(  # type: ignore[attr-defined]
                is_active=True
            )[:3]

        except ImportError as exc:
            logger.error("Failed to import loan models: %s", exc, exc_info=True)
            # Set default values when models are not available
            context.update(
                {
                    "customer_profile": None,
                    "kyc_verified": False,
                    "kyc_completion": 0,
                    "monthly_income": 0,
                    "employment_status": "Not Set",
                    "employer_name": "",
                    "has_national_id": False,
                    "has_bank_statement": False,
                    "has_face_photo": False,
                    "applications_count": 0,
                    "recent_applications": [],
                    "active_loans_count": 0,
                    "recent_loans": [],
                    "total_borrowed": 0,
                    "available_products": [],
                }
            )
        except Exception as exc:
            logger.error(
                "Error loading loan data for dashboard: %s", exc, exc_info=True
            )
            # Set safe default values
            context.update(
                {
                    "customer_profile": None,
                    "kyc_verified": False,
                    "kyc_completion": 0,
                    "monthly_income": 0,
                    "employment_status": "Not Set",
                    "employer_name": "",
                    "has_national_id": False,
                    "has_bank_statement": False,
                    "has_face_photo": False,
                    "applications_count": 0,
                    "recent_applications": [],
                    "active_loans_count": 0,
                    "recent_loans": [],
                    "total_borrowed": 0,
                    "available_products": [],
                }
            )

        return context


# ---------------------------------------------------------------------------
# Odoo Webhook Receiver
# ---------------------------------------------------------------------------


@csrf_exempt
@require_http_methods(["POST"])
def odoo_webhook(request):
    """
    Receive webhook events from Odoo.
    Verifies HMAC signature using configured webhook secret.
    
    Expected headers:
        X-Alba-Signature: sha256=<hex_digest>
    
    Expected payload (JSON):
        {
            "event": "loan.status_changed",
            "timestamp": "2024-01-15T10:30:00Z",
            "payload": { ...event specific data... }
        }
    """
    import hashlib
    import hmac
    import json
    from .models import OdooConfig, AuditLog
    
    # Get active configuration
    config = OdooConfig.get_active()
    if not config or not config.webhook_secret:
        logger.warning("Odoo webhook received but no configuration or secret found")
        return JsonResponse(
            {"error": "Webhook not configured"}, 
            status=503
        )
    
    # Verify signature
    signature_header = request.headers.get('X-Alba-Signature', '')
    if not signature_header.startswith('sha256='):
        logger.warning("Odoo webhook: invalid signature format")
        return JsonResponse(
            {"error": "Invalid signature format"}, 
            status=401
        )
    
    expected_signature = signature_header[7:]  # Remove 'sha256=' prefix
    
    # Calculate expected signature
    payload_bytes = request.body
    calculated_signature = hmac.new(
        config.webhook_secret.encode('utf-8'),
        payload_bytes,
        hashlib.sha256
    ).hexdigest()
    
    if not hmac.compare_digest(expected_signature, calculated_signature):
        logger.warning("Odoo webhook: signature verification failed")
        return JsonResponse(
            {"error": "Signature verification failed"}, 
            status=401
        )
    
    # Parse payload
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        logger.error("Odoo webhook: invalid JSON payload")
        return JsonResponse(
            {"error": "Invalid JSON payload"}, 
            status=400
        )
    
    event_type = data.get('event', 'unknown')
    event_payload = data.get('payload', {})
    
    logger.info(f"Odoo webhook received: {event_type}")
    
    # Process different event types
    try:
        if event_type == 'loan.status_changed':
            _handle_loan_status_change(event_payload)
        elif event_type == 'payment.received':
            _handle_payment_received(event_payload)
        elif event_type == 'customer.updated':
            _handle_customer_updated(event_payload)
        else:
            logger.info(f"Odoo webhook: unhandled event type {event_type}")
        
        # Log the webhook receipt
        AuditLog.objects.create(
            action='WEBHOOK_RECEIVED',
            model_name='OdooWebhook',
            description=f"Received {event_type} webhook from Odoo",
            user=None  # System action
        )
        
        return JsonResponse({
            "status": "success",
            "event": event_type,
            "processed": True
        })
        
    except Exception as e:
        logger.error(f"Odoo webhook processing error: {e}")
        return JsonResponse(
            {"error": "Processing failed", "details": str(e)}, 
            status=500
        )


def _handle_loan_status_change(payload):
    """Handle loan status change events from Odoo."""
    from loans.models import LoanApplication
    
    odoo_loan_id = payload.get('loan_id')
    new_status = payload.get('status')
    
    if not odoo_loan_id:
        return
    
    # Find and update local loan application
    try:
        loan = LoanApplication.objects.filter(odoo_loan_id=odoo_loan_id).first()
        if loan and new_status:
            loan.status = new_status
            loan.save(update_fields=['status', 'updated_at'])
            logger.info(f"Updated loan {loan.id} status to {new_status}")
    except Exception as e:
        logger.error(f"Failed to update loan status: {e}")


def _handle_payment_received(payload):
    """Handle payment received events from Odoo."""
    from loans.models import LoanApplication
    
    odoo_loan_id = payload.get('loan_id')
    amount = payload.get('amount')
    
    logger.info(f"Payment received for loan {odoo_loan_id}: KES {amount}")
    # Additional payment processing logic here


def _handle_customer_updated(payload):
    """Handle customer updated events from Odoo."""
    logger.info(f"Customer update event received: {payload.get('customer_id')}")
    # Sync customer data from Odoo if needed


# Error handlers
# ---------------------------------------------------------------------------


def page_not_found(request, exception=None):
    return render(request, "404.html", status=404)


def server_error(request):
    return render(request, "500.html", status=500)
