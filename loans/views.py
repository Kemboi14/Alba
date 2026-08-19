"""
Loan Management Views — Customer Portal
Handles: customer dashboard, profile, loan application, documents, guarantors,
         repayment schedule, in-portal notifications, PDF statement download.
Staff/admin processing is handled in Odoo.
"""

import json
import logging
import base64
from decimal import Decimal, InvalidOperation
from io import BytesIO

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import F
from django.db.models.functions import Greatest
from django.http import Http404, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from core.views import create_audit_log  # noqa: PLC0415

logger = logging.getLogger(__name__)

from .forms import (
    CollateralForm,
    CustomerProfileForm,
    GuarantorForm,
    LoanApplicationForm,
    LoanDocumentForm,
)
from .models import (
    Collateral,
    Customer,
    GuarantorVerification,
    Loan,
    LoanApplication,
    LoanDocument,
    LoanProduct,
    LoanRepayment,
    Notification,
    RepaymentSchedule,
)

from core.services.odoo_sync import OdooSyncService, OdooSyncError
from core.services.mpesa import (
    MpesaService,
    MpesaError,
    MpesaAuthError,
    MpesaValidationError,
    MpesaAPIError,
    MpesaTimeoutError,
    MpesaConnectionError,
)

# ---------------------------------------------------------------------------
# Customer dashboard
# ---------------------------------------------------------------------------


@login_required
def customer_loan_dashboard(request):
    """Main customer loan dashboard"""
    customer, _ = Customer.objects.get_or_create(user=request.user)

    applications = LoanApplication.objects.filter(customer=customer)
    active_loans = Loan.objects.filter(customer=customer, status="ACTIVE")

    from django.db.models import Sum

    total_borrowed = active_loans.aggregate(total=Sum("principal_amount"))[
        "total"
    ] or Decimal("0")
    total_outstanding = active_loans.aggregate(total=Sum("outstanding_balance"))[
        "total"
    ] or Decimal("0")

    context = {
        "customer": customer,
        "applications_count": applications.count(),
        "active_loans_count": active_loans.count(),
        "total_borrowed": total_borrowed,
        "total_outstanding": total_outstanding,
        "recent_applications": applications.order_by("-created_at")[:5],
        "my_loans": active_loans.order_by("-disbursement_date")[:5],
        "kyc_complete": customer.kyc_verified,
        "kyc_status": customer.kyc_status,  # Odoo Alignment - KYC status
    }

    create_audit_log(
        request.user, "VIEW", "LoanDashboard", None, "Viewed customer loan dashboard"
    )
    return render(request, "loans/customer/dashboard.html", context)


# ---------------------------------------------------------------------------
# Customer profile / KYC
# ---------------------------------------------------------------------------


@login_required
def customer_profile(request):
    """View and update customer profile / KYC documents"""
    customer, _ = Customer.objects.get_or_create(user=request.user)

    if request.method == "POST":
        was_fully_uploaded = customer.is_kyc_fully_uploaded()
        form = CustomerProfileForm(request.POST, request.FILES, instance=customer)
        if form.is_valid():
            customer = form.save(commit=False)
            if customer.is_kyc_fully_uploaded():
                if customer.verification_status in ["pending", "rejected"]:
                    customer.verification_status = "in_progress"
            customer.save()
            if customer.is_kyc_fully_uploaded() and not customer.kyc_verified:
                messages.info(
                    request,
                    "Documents uploaded successfully. Awaiting KYC review.",
                )
            messages.success(request, "Profile updated successfully.")
            create_audit_log(
                request.user,
                "UPDATE",
                "Customer",
                customer.pk,
                "Updated customer profile",
            )

            # Notify Odoo that documents are ready for KYC review, the
            # moment all three become present. Best-effort — the sync
            # status/error is recorded so a failure here is picked up by
            # the existing `sync_odoo customers` retry path, and this only
            # fires on the pending->uploaded transition, not on every
            # subsequent unrelated profile edit.
            if customer.is_kyc_fully_uploaded() and not was_fully_uploaded:
                customer.odoo_sync_status = Customer.ODOO_SYNC_PENDING
                customer.odoo_sync_attempts += 1
                customer.odoo_last_sync_at = timezone.now()
                customer.save(update_fields=["odoo_sync_status", "odoo_sync_attempts", "odoo_last_sync_at"])
                try:
                    svc = OdooSyncService()
                    if not svc.is_reachable():
                        raise OdooSyncError("Odoo instance unreachable")
                    odoo_id = customer.odoo_customer_id
                    if not odoo_id:
                        result = svc.create_or_update_customer(request.user)
                        odoo_id = result.get("odoo_customer_id")
                        if odoo_id:
                            customer.odoo_customer_id = odoo_id
                    if not odoo_id:
                        raise OdooSyncError("Failed to sync customer to Odoo — no Odoo ID returned")
                    svc.update_kyc_status(
                        odoo_customer_id=odoo_id,
                        kyc_status="submitted",
                        notes="Documents uploaded via portal. Awaiting manual KYC review.",
                        document_type="national_id",
                        document_number=customer.id_number or "",
                    )
                    customer.odoo_sync_status = Customer.ODOO_SYNC_SUCCESS
                    customer.odoo_sync_error = ""
                    customer.save(update_fields=["odoo_customer_id", "odoo_sync_status", "odoo_sync_error"])
                except Exception as exc:
                    logger.warning(
                        "Failed to notify Odoo of KYC document submission: customer_id=%s error=%s",
                        customer.pk, exc,
                    )
                    customer.odoo_sync_status = Customer.ODOO_SYNC_FAILED
                    customer.odoo_sync_error = str(exc)[:500]
                    customer.save(update_fields=["odoo_sync_status", "odoo_sync_error"])

            return redirect("loans:customer_dashboard")
        else:
            logger.warning(
                "customer_profile: form invalid for customer_id=%s errors=%s",
                customer.pk, form.errors.as_json(),
            )
    else:
        form = CustomerProfileForm(instance=customer)

    # ── Fetch real-time KYC status from Odoo (best-effort) ──────────────────
    odoo_kyc = None
    if customer.odoo_customer_id:
        try:
            svc = OdooSyncService()
            if svc.is_reachable():
                odoo_kyc = svc.get_kyc_status(customer.odoo_customer_id)
                # Sync Odoo's authoritative status back to Django
                odoo_status = (odoo_kyc.get("kyc_status") or "").strip()
                if odoo_status == "verified" and not customer.kyc_verified:
                    customer.kyc_verified = True
                    customer.national_id_verified = True
                    customer.bank_statement_verified = True
                    customer.face_recognition_verified = True
                    customer.verification_status = "verified"
                    customer.save(update_fields=[
                        "kyc_verified",
                        "national_id_verified",
                        "bank_statement_verified",
                        "face_recognition_verified",
                        "verification_status",
                    ])
                elif odoo_status == "rejected" and customer.kyc_verified:
                    customer.kyc_verified = False
                    customer.verification_status = "rejected"
                    customer.save(update_fields=[
                        "kyc_verified", "verification_status",
                    ])
        except Exception as exc:
            logger.debug("Could not fetch Odoo KYC status: %s", exc)

    # Parse verification results for display
    verification_details = {}
    try:
        verification_details = json.loads(customer.verification_results or "{}")
    except (json.JSONDecodeError, ValueError):
        verification_details = {}

    # Re-calculate after possible Odoo sync update
    kyc_completion = int(customer.get_kyc_completion_percentage())

    return render(
        request,
        "loans/customer/profile.html",
        {
            "form": form,
            "customer": customer,
            "kyc_completion": kyc_completion,
            "kyc_verified": customer.kyc_verified,
            "verification_status": customer.verification_status,
            "verification_confidence": customer.verification_confidence,
            "verification_details": verification_details,
            "odoo_kyc": odoo_kyc,
            "debug": request.GET.get("debug", "false").lower() == "true",
        },
    )


# ---------------------------------------------------------------------------
# Loan application
# ---------------------------------------------------------------------------


@login_required
def apply_for_loan(request):
    """Customer loan application form with enhanced pre-sync validation for Odoo 19 integration."""
    customer, _ = Customer.objects.get_or_create(user=request.user)

    # Require minimal profile before applying - check all KYC fields
    required_fields = [
        customer.id_number,
        customer.date_of_birth,
        customer.address,
        customer.monthly_income,
        customer.employment_status,
        customer.employer_name,
    ]
    if not all(required_fields):
        missing = []
        if not customer.id_number:
            missing.append("ID Number")
        if not customer.date_of_birth:
            missing.append("Date of Birth")
        if not customer.address:
            missing.append("Address")
        if not customer.monthly_income:
            missing.append("Monthly Income")
        if not customer.employment_status:
            missing.append("Employment Status")
        if not customer.employer_name:
            missing.append("Employer Name")
        messages.warning(
            request,
            f"Please complete your profile before applying for a loan. Missing: {', '.join(missing)}",
        )
        return redirect("loans:customer_profile")

    # Try to sync real products from Odoo first; only fall back to the local
    # fixture products if Odoo is unusable. Fixture codes (QSAL001, BIZ001,
    # ASSET001) don't exist in Odoo's catalog, so an application against one
    # of them can never be submitted — sync_loan_product_to_odoo() can only
    # find a matching product that already exists there, not create one —
    # and picking a fixture product fails at submission with "Product sync
    # returned zero ID" no matter how correct the rest of the application is.
    if not LoanProduct.objects.filter(is_active=True).exists():
        try:
            from core.services.odoo_sync import OdooSyncService as _OdooSyncServiceForSeed

            seed_odoo_service = _OdooSyncServiceForSeed()
            if seed_odoo_service.is_configured() and seed_odoo_service.is_reachable():
                seed_odoo_service.sync_loan_products_from_odoo()
        except Exception as seed_sync_exc:
            logger.warning("Pre-apply product sync from Odoo failed: %s", seed_sync_exc)
        if not LoanProduct.objects.filter(is_active=True).exists():
            _seed_loan_products()

    # Pre-sync validation: Ensure customer is synced to Odoo
    odoo_sync_ready = True
    sync_message = ""
    
    try:
        from core.services.odoo_sync import OdooSyncService
        
        odoo_service = OdooSyncService()
        
        # Check if Odoo service is properly configured
        if not odoo_service.is_configured():
            logger.warning("Odoo service not configured - pre-sync validation skipped")
            odoo_sync_ready = False
            sync_message = "Odoo integration not configured - application will be synced when configured"
        # Check if customer needs syncing
        elif not customer.odoo_customer_id:
            if odoo_service.is_reachable():
                try:
                    logger.info(
                        "Pre-sync validation: Customer not synced to Odoo, syncing now: customer_id=%s",
                        customer.pk
                    )
                    result = odoo_service.create_or_update_customer(customer.user)
                    if result and result.get("odoo_customer_id"):
                        customer.odoo_customer_id = result.get("odoo_customer_id")
                        customer.odoo_sync_status = "SUCCESS"
                        customer.odoo_sync_error = ""
                        customer.odoo_last_sync_at = timezone.now()
                        customer.save(update_fields=["odoo_customer_id", "odoo_sync_status", "odoo_sync_error", "odoo_last_sync_at"])
                        logger.info(
                            "Pre-sync validation: Customer synced successfully: django_id=%s odoo_id=%s",
                            customer.pk,
                            customer.odoo_customer_id
                        )
                    else:
                        odoo_sync_ready = False
                        sync_message = "Customer sync returned invalid response"
                        logger.warning(
                            "Pre-sync validation: Customer sync failed - invalid response: customer_id=%s",
                            customer.pk
                        )
                except Exception as sync_exc:
                    odoo_sync_ready = False
                    sync_message = f"Customer sync failed: {str(sync_exc)}"
                    logger.warning(
                        "Pre-sync validation: Customer sync failed: customer_id=%s error=%s",
                        customer.pk,
                        sync_exc
                    )
            else:
                # Odoo not reachable, but allow application to proceed
                logger.warning(
                    "Pre-sync validation: Odoo unreachable, will sync later: customer_id=%s",
                    customer.pk
                )
                sync_message = "Odoo unreachable - will sync during submission"
        else:
            logger.info(
                "Pre-sync validation: Customer already synced to Odoo: django_id=%s odoo_id=%s",
                customer.pk,
                customer.odoo_customer_id
            )

        # Sync loan products if needed
        products_needing_sync = LoanProduct.objects.filter(
            is_active=True,
            odoo_product_id__isnull=True
        )
        
        if products_needing_sync.exists() and odoo_service.is_configured() and odoo_service.is_reachable():
            try:
                logger.info(
                    "Pre-sync validation: Syncing %d loan products to Odoo",
                    products_needing_sync.count()
                )
                sync_result = odoo_service.sync_loan_products_from_odoo()
                logger.info(
                    "Pre-sync validation: Loan products sync completed: %s",
                    sync_result
                )
            except Exception as sync_exc:
                logger.warning(
                    "Pre-sync validation: Loan products sync failed: error=%s",
                    sync_exc
                )
                # Don't block application if product sync fails
        elif products_needing_sync.exists() and not odoo_service.is_configured():
            logger.warning(
                "Pre-sync validation: Odoo not configured, skipping loan product sync"
            )
        
        # Show sync status to user
        if sync_message:
            if odoo_sync_ready:
                messages.info(request, sync_message)
            else:
                messages.warning(request, sync_message)

    except Exception as exc:
        logger.exception(
            "Pre-sync validation error: customer_id=%s error=%s",
            customer.pk,
            exc
        )
        # Don't block application on pre-sync errors

    if request.method == "POST":
        form = LoanApplicationForm(request.POST)
        if form.is_valid():
            application = form.save(commit=False)
            application.customer = customer

            # Capture business fields from form if they exist
            for field in [
                "business_name",
                "business_registration_number",
                "business_location",
                "annual_turnover",
            ]:
                if field in form.cleaned_data:
                    setattr(application, field, form.cleaned_data[field])

            # Save as DRAFT — customer must upload supporting documents
            # (payslip / employment letter) before final submission.
            application.status = LoanApplication.DRAFT
            application.save()

            messages.success(
                request,
                (
                    f"Application {application.application_number} saved. "
                    "Please upload your supporting documents (payslip, employment letter, etc.) "
                    "then click Submit."
                ),
            )
            create_audit_log(
                request.user,
                "CREATE",
                "LoanApplication",
                application.pk,
                f"Created draft loan application {application.application_number}",
            )
            return redirect("loans:application_detail", pk=application.pk)
    else:
        # Get default Salary Advance product for initial form data
        default_product = LoanProduct.objects.filter(
            category=LoanProduct.SALARY_ADVANCE, is_active=True
        ).first()
        
        initial_data = {}
        if default_product:
            initial_data = {
                "loan_product": default_product.id,
                "requested_amount": 30000,  # Mid-range default for salary advance
                "tenure_months": 3,  # Common default tenure
                "repayment_frequency": LoanProduct.MONTHLY,
            }
        
        form = LoanApplicationForm(initial=initial_data)

    # Get default product for template calculator initialization
    default_product = LoanProduct.objects.filter(
        category=LoanProduct.SALARY_ADVANCE, is_active=True
    ).first()

    return render(
        request,
        "loans/customer/apply.html",
        {
            "form": form,
            "products": LoanProduct.objects.filter(is_active=True),
            "customer": customer,
            "default_product": default_product,
            "default_product_id": default_product.id if default_product else None,
            "odoo_sync_ready": odoo_sync_ready,
        },
    )


@login_required
def application_detail(request, pk):
    """Detail view for a single loan application (customer)"""
    customer, _ = Customer.objects.get_or_create(user=request.user)
    application = get_object_or_404(LoanApplication, pk=pk, customer=customer)

    documents = LoanDocument.objects.filter(application=application)
    guarantors = GuarantorVerification.objects.filter(application=application)
    collaterals = Collateral.objects.filter(loan_application=application)

    return render(
        request,
        "loans/application_detail.html",
        {
            "application": application,
            "documents": documents,
            "guarantors": guarantors,
            "collaterals": collaterals,
        },
    )


@login_required
def my_applications(request):
    """List all of the customer's loan applications"""
    customer, _ = Customer.objects.get_or_create(user=request.user)
    applications = LoanApplication.objects.filter(customer=customer).order_by(
        "-created_at"
    )
    return render(
        request,
        "loans/customer/my_applications.html",
        {"applications": applications},
    )


@login_required
def submit_application(request, pk):
    """Final submission of a draft application — requires at least one supporting document.
    
    Documents must be uploaded before submission, but verification happens asynchronously in Odoo.
    The Django portal displays the verification progress as it updates from Odoo.
    Enhanced with robust error handling, pre-sync validation, and comprehensive logging
    to ensure seamless integration with Odoo 19 Alba loan module.
    """
    from .models import LoanDocument  # Ensure local import

    if request.method != "POST":
        return redirect("loans:application_detail", pk=pk)

    customer, _ = Customer.objects.get_or_create(user=request.user)
    application = get_object_or_404(LoanApplication, pk=pk, customer=customer)

    if application.status != LoanApplication.DRAFT:
        messages.info(request, "This application has already been submitted.")
        return redirect("loans:application_detail", pk=pk)

    # Enforce document requirement: customer must upload at least one supporting document
    # (payslip, employment letter, bank statement, etc.) before submission.
    has_documents = (
        LoanDocument.objects.filter(application=application).exists()
        or bool(customer.national_id_file or customer.bank_statement_file or customer.face_recognition_photo)
    )
    if not has_documents:
        messages.warning(
            request,
            "Please upload at least one supporting document (e.g. payslip or employment "
            "letter) before submitting your application.",
        )
        return redirect("loans:upload_document", application_pk=pk)

    with transaction.atomic():
        application = LoanApplication.objects.select_for_update().get(pk=application.pk)
        if application.status != LoanApplication.DRAFT:
            messages.info(request, "This application has already been submitted.")
            return redirect("loans:application_detail", pk=pk)
        application.status = LoanApplication.SUBMITTED
        application.save(update_fields=["status"])

    # Enhanced sync to Odoo with comprehensive error handling before locking Django status
    sync_success = False
    sync_error_message = ""
    is_transient_error = False
    
    try:
        from core.services.odoo_sync import OdooSyncService, OdooSyncError, OdooConnectionError, OdooTimeoutError
        from django.utils import timezone

        odoo_service = OdooSyncService()
        
        # Check if Odoo service is properly configured
        if not odoo_service.is_configured():
            logger.error("Odoo service not configured - missing API credentials")
            raise OdooSyncError(
                "Odoo integration not configured. Please contact administrator.",
                detail="API credentials are not configured in the admin panel."
            )
        
        # Check Odoo connectivity before attempting sync
        if not odoo_service.is_reachable():
            raise OdooConnectionError("Odoo instance unreachable - please check network connectivity")
        
        # Explicitly sync customer to Odoo first before creating application
        logger.info("Syncing customer to Odoo before application creation: customer_id=%s", customer.pk)
        try:
            customer_result = odoo_service.create_or_update_customer(request.user)
            customer_odoo_id = customer_result.get("odoo_customer_id")
            if customer_odoo_id:
                customer.odoo_customer_id = customer_odoo_id
                customer.save(update_fields=["odoo_customer_id"])
                logger.info("Customer synced successfully: django_id=%s odoo_id=%s", customer.pk, customer_odoo_id)
            else:
                raise OdooSyncError("Failed to sync customer - no Odoo ID returned")
        except OdooSyncError:
            # Preserve the original error's type (auth/validation/connection/
            # timeout) and detail. Re-wrapping it here would replace the real
            # cause with a generic message and would erase the type, which
            # the (OdooConnectionError, OdooTimeoutError) handler below
            # relies on to tell a transient network blip apart from a
            # permanent data/validation problem.
            raise
        except Exception as customer_sync_error:
            logger.error("Failed to sync customer to Odoo: customer_id=%s error=%s", customer.pk, customer_sync_error)
            raise OdooSyncError(
                f"Failed to sync customer to Odoo: {customer_sync_error}",
                detail=f"Customer sync is required before application creation: {customer_sync_error}"
            ) from customer_sync_error
        
        # Sync application to Odoo with automatic prerequisite sync
        result = odoo_service.create_loan_application(application)
        
        # Validate response
        if not result or not result.get("odoo_application_id"):
            raise OdooSyncError(
                "Invalid response from Odoo - missing odoo_application_id",
                detail="Odoo returned an invalid response structure"
            )

        # Sync was fully successful: Lock application status to SUBMITTED
        application.status = LoanApplication.SUBMITTED
        application.submitted_at = timezone.now()
        application.odoo_application_id = result.get("odoo_application_id")
        application.odoo_sync_status = LoanApplication.ODOO_SYNC_SUCCESS
        application.odoo_sync_error = ""
        application.save()

        logger.info(
            "Application synced to Odoo successfully: django_id=%s odoo_id=%s app_number=%s",
            application.pk,
            application.odoo_application_id,
            application.application_number
        )

        # Trigger Odoo workflow transition: draft → submitted.
        # This is a non-fatal step — if the network fails here the application
        # has already been created in Odoo and can be submitted manually.
        try:
            submit_result = odoo_service.submit_loan_application(application.odoo_application_id)
            logger.info(
                "Application submitted to Odoo workflow: django_id=%s odoo_id=%s new_state=%s",
                application.pk,
                application.odoo_application_id,
                submit_result.get("new_state", "unknown"),
            )
        except Exception as submit_exc:
            logger.warning(
                "Odoo workflow submit failed (non-fatal): django_id=%s odoo_id=%s error=%s",
                application.pk,
                application.odoo_application_id,
                submit_exc,
            )

        sync_success = True
        messages.success(request, "Application submitted successfully. Verification progress will be updated from Odoo.")

        # Sync customer profile KYC documents to Odoo with error handling
        customer = getattr(application, "customer", None)
        if customer:
            kyc_docs = [
                (customer.national_id_file, "national_id", "National ID Document"),
                (customer.bank_statement_file, "bank_statement", "Bank Statement"),
                (customer.face_recognition_photo, "other", "Face Recognition Photo"),
            ]
            
            synced_docs = []
            failed_docs = []
            
            for file_field, doc_type, doc_name in kyc_docs:
                if file_field:
                    try:
                        odoo_service.sync_kyc_file(
                            odoo_application_id=application.odoo_application_id,
                            file_field=file_field,
                            document_type=doc_type,
                            name=doc_name
                        )
                        synced_docs.append(doc_name)
                    except Exception as doc_exc:
                        failed_docs.append(doc_name)
                        logger.warning(
                            "KYC document sync to Odoo failed: type=%s error=%s app_id=%s",
                            doc_type,
                            doc_exc,
                            application.pk
                        )
            
            # Sync all pre-uploaded LoanDocument records that haven't been synced successfully yet
            from loans.models import LoanDocument
            pre_uploaded_docs = application.documents.exclude(odoo_sync_status=LoanDocument.ODOO_SYNC_SUCCESS)
            for doc in pre_uploaded_docs:
                try:
                    doc.odoo_sync_status = LoanDocument.ODOO_SYNC_PENDING
                    doc.odoo_last_sync_at = timezone.now()
                    doc.save(update_fields=["odoo_sync_status", "odoo_last_sync_at"])
                    
                    result_doc = odoo_service.sync_document(application.odoo_application_id, doc)
                    if result_doc and result_doc.get("odoo_document_id"):
                        doc.odoo_document_id = result_doc.get("odoo_document_id")
                        doc.odoo_sync_status = LoanDocument.ODOO_SYNC_SUCCESS
                        doc.odoo_sync_error = ""
                        doc.odoo_last_sync_at = timezone.now()
                        doc.save(update_fields=["odoo_document_id", "odoo_sync_status", "odoo_sync_error", "odoo_last_sync_at"])
                        synced_docs.append(doc.get_document_type_display())
                    else:
                        raise Exception("Invalid response from Odoo")
                except Exception as doc_exc:
                    failed_docs.append(doc.get_document_type_display())
                    doc.odoo_sync_status = LoanDocument.ODOO_SYNC_FAILED
                    doc.odoo_sync_error = str(doc_exc)[:500]
                    doc.odoo_last_sync_at = timezone.now()
                    doc.save(update_fields=["odoo_sync_status", "odoo_sync_error", "odoo_last_sync_at"])
            
            if synced_docs:
                messages.info(
                    request,
                    f"Documents synced: {', '.join(synced_docs)}"
                )
            if failed_docs:
                messages.warning(
                    request,
                    f"Some documents could not be synced: {', '.join(failed_docs)}. "
                    "They will be retried automatically."
                )

    except (OdooConnectionError, OdooTimeoutError) as conn_exc:
        # Transient connection/network error: lock application as SUBMITTED but mark sync as FAILED so user can retry manually
        is_transient_error = True
        sync_error_message = f"Connection error: {str(conn_exc)}"
        logger.error("Odoo transient sync error: app_id=%s error=%s", application.pk, conn_exc)
        
        application.status = LoanApplication.SUBMITTED
        application.submitted_at = timezone.now()
        application.odoo_sync_status = LoanApplication.ODOO_SYNC_FAILED
        application.odoo_sync_error = sync_error_message[:500]
        application.odoo_last_sync_at = timezone.now()
        application.save()
        
        messages.warning(
            request,
            "Your application has been submitted successfully, but we could not synchronize it with the Odoo backend due to a temporary network issue. "
            "Our team will retry this automatically, or you can retry manually using the 'Retry Sync' button."
        )

    except Exception as general_exc:
        # Non-transient / Validation / API payload error: Keep status as DRAFT so they can edit profile and fix data
        sync_error_message = f"Validation or setup error: {str(general_exc)}"
        logger.exception("Odoo validation/API sync error: app_id=%s error=%s", application.pk, general_exc)

        application.status = LoanApplication.DRAFT
        application.odoo_sync_status = LoanApplication.ODOO_SYNC_FAILED
        application.odoo_sync_error = sync_error_message[:500]
        application.odoo_last_sync_at = timezone.now()
        application.save()
        
        messages.error(
            request,
            f"Failed to submit application: {general_exc}. "
            "Please review your customer profile and application details, update any incorrect fields, and try again."
        )
        return redirect("loans:application_detail", pk=pk)

    create_audit_log(
        request.user,
        "UPDATE",
        "LoanApplication",
        application.pk,
        f"Submitted application {application.application_number} - Odoo sync: {'Success' if sync_success else 'Failed (Transient)' if is_transient_error else 'Failed (Validation)'}",
    )
    
    return redirect("loans:application_detail", pk=pk)


@login_required
def retry_application_sync(request, pk):
    """Manually retry Odoo sync for a submitted application that failed to sync."""
    if request.method != "POST":
        return redirect("loans:application_detail", pk=pk)

    customer, _ = Customer.objects.get_or_create(user=request.user)
    application = get_object_or_404(LoanApplication, pk=pk, customer=customer)

    if application.odoo_sync_status == LoanApplication.ODOO_SYNC_SUCCESS:
        messages.info(request, "This application has already been successfully synced to Odoo.")
        return redirect("loans:application_detail", pk=pk)

    from core.services.odoo_sync import OdooSyncService, OdooSyncError, OdooConnectionError, OdooTimeoutError
    from django.utils import timezone
    from loans.models import LoanDocument

    odoo_service = OdooSyncService()
    sync_success = False
    sync_error_message = ""

    try:
        if not odoo_service.is_reachable():
            raise OdooConnectionError("Odoo instance unreachable - please check network connectivity")

        # Update application sync status to in-progress
        application.odoo_sync_status = LoanApplication.ODOO_SYNC_PENDING
        application.odoo_sync_attempts += 1
        application.odoo_last_sync_at = timezone.now()
        application.save(update_fields=["odoo_sync_status", "odoo_sync_attempts", "odoo_last_sync_at"])

        result = odoo_service.create_loan_application(application)
        if not result or not result.get("odoo_application_id"):
            raise OdooSyncError("Invalid response from Odoo - missing odoo_application_id")

        application.odoo_application_id = result.get("odoo_application_id")
        application.odoo_sync_status = LoanApplication.ODOO_SYNC_SUCCESS
        application.odoo_sync_error = ""
        application.save(update_fields=["odoo_application_id", "odoo_sync_status", "odoo_sync_error"])

        # Trigger Odoo workflow transition: draft → submitted (non-fatal).
        try:
            submit_result = odoo_service.submit_loan_application(application.odoo_application_id)
            logger.info(
                "Application submitted to Odoo workflow on retry: django_id=%s odoo_id=%s new_state=%s",
                application.pk,
                application.odoo_application_id,
                submit_result.get("new_state", "unknown"),
            )
        except Exception as submit_exc:
            logger.warning(
                "Odoo workflow submit failed during retry (non-fatal): django_id=%s odoo_id=%s error=%s",
                application.pk,
                application.odoo_application_id,
                submit_exc,
            )

        # Also sync documents
        pre_uploaded_docs = application.documents.exclude(odoo_sync_status=LoanDocument.ODOO_SYNC_SUCCESS)
        synced_count = 0
        for doc in pre_uploaded_docs:
            try:
                doc.odoo_sync_status = LoanDocument.ODOO_SYNC_PENDING
                doc.odoo_last_sync_at = timezone.now()
                doc.save(update_fields=["odoo_sync_status", "odoo_last_sync_at"])
                
                result_doc = odoo_service.sync_document(application.odoo_application_id, doc)
                if result_doc and result_doc.get("odoo_document_id"):
                    doc.odoo_document_id = result_doc.get("odoo_document_id")
                    doc.odoo_sync_status = LoanDocument.ODOO_SYNC_SUCCESS
                    doc.odoo_sync_error = ""
                    doc.odoo_last_sync_at = timezone.now()
                    doc.save(update_fields=["odoo_document_id", "odoo_sync_status", "odoo_sync_error", "odoo_last_sync_at"])
                    synced_count += 1
            except Exception as e:
                logger.error("Failed to sync document during retry: doc_id=%d err=%s", doc.id, e)

        messages.success(
            request, 
            f"Application successfully synced to Odoo! {synced_count} documents synced."
        )
        sync_success = True
    except Exception as exc:
        sync_error_message = str(exc)
        application.odoo_sync_status = LoanApplication.ODOO_SYNC_FAILED
        application.odoo_sync_error = sync_error_message[:500]
        application.odoo_last_sync_at = timezone.now()
        application.save(update_fields=["odoo_sync_status", "odoo_sync_error", "odoo_last_sync_at"])
        messages.error(request, f"Odoo sync failed: {sync_error_message}")

    create_audit_log(
        request.user,
        "UPDATE",
        "LoanApplication",
        application.pk,
        f"Manually retried sync for application {application.application_number} - Odoo sync: {'Success' if sync_success else 'Failed'}",
    )
    return redirect("loans:application_detail", pk=pk)


# ---------------------------------------------------------------------------
# Active loans
# ---------------------------------------------------------------------------


@login_required
def my_loans(request):
    """List all active/past loans for the customer"""
    customer, _ = Customer.objects.get_or_create(user=request.user)
    loans = Loan.objects.filter(customer=customer).order_by("-disbursement_date")
    return render(request, "loans/customer/my_loans.html", {"loans": loans})


@login_required
def loan_detail(request, pk):
    """Detail view for a single active loan"""
    customer, _ = Customer.objects.get_or_create(user=request.user)
    loan = get_object_or_404(Loan, pk=pk, customer=customer)
    repayments = loan.repayments.order_by("-payment_date")
    return render(
        request,
        "loans/loan_detail.html",
        {"loan": loan, "repayments": repayments},
    )


# ---------------------------------------------------------------------------
# Repayment (M-Pesa STK Push) — AJAX
# ---------------------------------------------------------------------------

@login_required
def initiate_repayment(request, loan_pk):
    """
    AJAX endpoint — trigger a live M-Pesa STK Push for a repayment.

    Does not create a LoanRepayment yet: only once the customer actually
    confirms the payment on their phone (checked via check_repayment_status)
    is anything persisted, so a cancelled/ignored prompt leaves no trace.
    """
    if request.method != "POST":
        return JsonResponse({"error": "POST required"}, status=405)

    customer, _ = Customer.objects.get_or_create(user=request.user)
    loan = get_object_or_404(Loan, pk=loan_pk, customer=customer)

    if not loan.is_payable:
        return JsonResponse(
            {"error": f"This loan is {loan.get_status_display()} and cannot take a repayment."},
            status=400,
        )

    try:
        amount = Decimal(str(request.POST.get("amount", "0")))
    except (InvalidOperation, ValueError, TypeError):
        return JsonResponse({"error": "Invalid amount."}, status=400)

    if amount <= 0:
        return JsonResponse({"error": "Amount must be greater than zero."}, status=400)
    if amount > loan.outstanding_balance:
        return JsonResponse(
            {
                "error": (
                    f"Amount cannot exceed the outstanding balance of "
                    f"KES {loan.outstanding_balance:,.2f}."
                )
            },
            status=400,
        )

    phone = (customer.mpesa_number or customer.user.phone or "").strip()
    if not phone:
        return JsonResponse(
            {"error": "Please add an M-Pesa number to your profile before paying."},
            status=400,
        )

    try:
        result = MpesaService().stk_push(
            phone_number=phone,
            amount=float(amount),
            account_reference=loan.loan_number,
            transaction_desc="Loan Repayment",
            odoo_loan_id=loan.odoo_loan_id or 0,
        )
    except MpesaValidationError as exc:
        return JsonResponse({"error": str(exc)}, status=400)
    except MpesaAuthError as exc:
        logger.error("initiate_repayment: M-Pesa auth error: %s", exc)
        return JsonResponse({"error": "Payment service is temporarily unavailable. Please try again shortly."}, status=502)
    except MpesaAPIError as exc:
        return JsonResponse({"error": str(exc) or "M-Pesa declined the request."}, status=400)
    except MpesaTimeoutError:
        return JsonResponse({"error": "The payment request timed out. Please try again."}, status=504)
    except MpesaConnectionError as exc:
        logger.error("initiate_repayment: cannot reach M-Pesa/Odoo: %s", exc)
        return JsonResponse({"error": "Payment service is temporarily unavailable. Please try again shortly."}, status=502)
    except MpesaError as exc:
        logger.exception("initiate_repayment: unexpected M-Pesa error")
        return JsonResponse({"error": str(exc) or "Could not initiate payment."}, status=500)

    checkout_request_id = result.get("checkout_request_id") or result.get("CheckoutRequestID")
    if not checkout_request_id:
        return JsonResponse({"error": "M-Pesa did not return a request reference. Please try again."}, status=502)

    return JsonResponse(
        {
            "checkout_request_id": checkout_request_id,
            "message": "Check your phone and enter your M-Pesa PIN to complete the payment.",
        }
    )


@login_required
def check_repayment_status(request, loan_pk):
    """
    AJAX endpoint — polled by the frontend after initiate_repayment.

    Once the STK Push is confirmed by Safaricom (status == "completed"),
    creates the local LoanRepayment and posts it to Odoo synchronously via
    OdooSyncService.record_payment() — the same, already-working, immediately-
    posting endpoint used everywhere else in this codebase for payments.
    """
    if request.method != "GET":
        return JsonResponse({"error": "GET required"}, status=405)

    customer, _ = Customer.objects.get_or_create(user=request.user)
    loan = get_object_or_404(Loan, pk=loan_pk, customer=customer)

    checkout_request_id = (request.GET.get("checkout_request_id") or "").strip()
    if not checkout_request_id:
        return JsonResponse({"error": "checkout_request_id is required."}, status=400)

    try:
        result = MpesaService().query_stk_status(checkout_request_id)
    except MpesaConnectionError as exc:
        logger.error("check_repayment_status: cannot reach M-Pesa/Odoo: %s", exc)
        return JsonResponse({"error": "Payment service is temporarily unavailable."}, status=502)
    except MpesaTimeoutError:
        return JsonResponse({"error": "Status check timed out."}, status=504)
    except MpesaError as exc:
        logger.exception("check_repayment_status: unexpected M-Pesa error")
        return JsonResponse({"error": str(exc) or "Could not check payment status."}, status=500)

    status = result.get("status", "pending")

    if status == "pending":
        return JsonResponse({"status": "pending"})

    if status in ("failed", "cancelled"):
        return JsonResponse(
            {
                "status": "failed",
                "message": result.get("result_desc") or "The payment was not completed.",
            }
        )

    # status == "completed"
    mpesa_code = (result.get("mpesa_code") or "").strip()
    amount = Decimal(str(result.get("amount") or "0"))
    if amount <= 0:
        # Fall back to whatever the customer originally requested rather
        # than persist a zero-amount repayment.
        amount = loan.outstanding_balance

    repayment, created = LoanRepayment.objects.get_or_create(
        reference_number=mpesa_code or f"STK-{checkout_request_id}",
        defaults={
            "loan": loan,
            "payment_date": timezone.now().date(),
            "amount": amount,
            "payment_type": LoanRepayment.REGULAR_PAYMENT,
            "payment_method": LoanRepayment.M_PESA,
            "sync_status": "pending",
        },
    )

    if not created and repayment.sync_status == "posted":
        # Already fully processed by an earlier poll — nothing left to do.
        return JsonResponse(
            {
                "status": "completed",
                "receipt_number": repayment.receipt_number,
                "amount": str(repayment.amount),
            }
        )

    try:
        odoo_result = OdooSyncService().record_payment(
            loan_number=loan.loan_number,
            amount_paid=float(repayment.amount),
            payment_date=str(repayment.payment_date),
            payment_method="mpesa",
            mpesa_transaction_id=mpesa_code,
            payment_reference=mpesa_code,
            django_payment_id=repayment.pk,
            django_customer_id=customer.user_id,
        )
    except OdooSyncError as exc:
        logger.error(
            "check_repayment_status: Odoo posting failed for repayment %d — %s",
            repayment.pk,
            exc,
        )
        repayment.sync_status = "failed"
        repayment.notes = f"Odoo posting failed: {exc}"
        repayment.save(update_fields=["sync_status", "notes"])
        # The M-Pesa payment itself succeeded — only the ledger posting is
        # delayed. Tell the customer the truth: paid, processing.
        return JsonResponse(
            {
                "status": "completed",
                "pending_sync": True,
                "receipt_number": repayment.receipt_number,
                "amount": str(repayment.amount),
                "message": "Payment received and is being processed. It will reflect on your account shortly.",
            }
        )

    repayment.sync_status = "posted"
    repayment.odoo_repayment_id = odoo_result.get("odoo_repayment_id") or None
    repayment.principal_applied = odoo_result.get("principal_applied")
    repayment.interest_applied = odoo_result.get("interest_applied")
    repayment.save(
        update_fields=[
            "sync_status",
            "odoo_repayment_id",
            "principal_applied",
            "interest_applied",
        ]
    )

    # Atomic decrement — avoids a lost update if a concurrent request (e.g.
    # the payment.matched webhook, or a duplicate poll) writes the balance
    # around the same time. The webhook still overwrites this afterward with
    # Odoo's authoritative absolute value; this is only for instant UI
    # feedback before that webhook lands.
    Loan.objects.filter(pk=loan.pk).update(
        outstanding_balance=Greatest(F("outstanding_balance") - amount, Decimal("0"))
    )

    create_audit_log(
        request.user,
        "CREATE",
        "LoanRepayment",
        repayment.pk,
        f"M-Pesa repayment of KES {repayment.amount} posted for loan {loan.loan_number}",
    )

    return JsonResponse(
        {
            "status": "completed",
            "receipt_number": repayment.receipt_number,
            "amount": str(repayment.amount),
        }
    )


# ---------------------------------------------------------------------------
# Documents & guarantors
# ---------------------------------------------------------------------------


@login_required
def upload_document(request, application_pk):
    """Upload a supporting document for an application"""
    customer, _ = Customer.objects.get_or_create(user=request.user)
    application = get_object_or_404(
        LoanApplication, pk=application_pk, customer=customer
    )

    if application.status != LoanApplication.DRAFT:
        messages.error(request, "This application can no longer be modified.")
        return redirect("loans:application_detail", pk=application_pk)

    if request.method == "POST":
        files = request.FILES.getlist("document_files") or request.FILES.getlist("document_file")
        if not files:
            form = LoanDocumentForm(request.POST, request.FILES)
            if not form.is_valid():
                return render(
                    request,
                    "loans/customer/upload_document.html",
                    {"form": form, "application": application},
                )
        
        success = False
        sync_success_count = 0
        for file in files:
            data = request.POST.copy()
            form = LoanDocumentForm(data, {"document_file": file})
            if form.is_valid():
                doc = form.save(commit=False)
                doc.application = application
                doc.uploaded_by = request.user
                doc.save()
                success = True
                create_audit_log(
                    request.user,
                    "CREATE",
                    "LoanDocument",
                    doc.pk,
                    f"Uploaded document for application {application.application_number}",
                )
                
                # Sync to Odoo with improved status tracking
                if application.odoo_application_id:
                    try:
                        from core.services.odoo_sync import OdooSyncService
                        from django.utils import timezone

                        sync = OdooSyncService()
                        
                        # Update sync status to in-progress
                        doc.odoo_sync_status = LoanDocument.ODOO_SYNC_PENDING
                        doc.odoo_last_sync_at = timezone.now()
                        doc.save(update_fields=["odoo_sync_status", "odoo_last_sync_at"])
                        
                        if sync.is_reachable():
                            result = sync.sync_document(application.odoo_application_id, doc)
                            
                            # Update sync status on success
                            if result and result.get("odoo_document_id"):
                                doc.odoo_document_id = result.get("odoo_document_id")
                                doc.odoo_sync_status = LoanDocument.ODOO_SYNC_SUCCESS
                                doc.odoo_sync_error = ""
                                doc.odoo_last_sync_at = timezone.now()
                                doc.save(update_fields=["odoo_document_id", "odoo_sync_status", "odoo_sync_error", "odoo_last_sync_at"])
                                sync_success_count += 1
                                logger.info(
                                    "Document synced to Odoo successfully: doc_id=%s odoo_id=%s",
                                    doc.pk,
                                    doc.odoo_document_id
                                )
                            else:
                                raise Exception("Invalid response from Odoo - missing odoo_document_id")
                        else:
                            # Odoo unreachable - mark as failed but don't block
                            doc.odoo_sync_status = LoanDocument.ODOO_SYNC_FAILED
                            doc.odoo_sync_error = "Odoo instance unreachable - will retry automatically"
                            doc.odoo_last_sync_at = timezone.now()
                            doc.save(update_fields=["odoo_sync_status", "odoo_sync_error", "odoo_last_sync_at"])
                            logger.warning(
                                "Odoo unreachable during document sync: doc_id=%s",
                                doc.pk
                            )
                    except Exception as exc:  # noqa: BLE001
                        logger.error(
                            "Document sync to Odoo failed: doc_id=%s err=%s",
                            doc.pk,
                            exc,
                        )
                        # Update sync status to failed
                        doc.odoo_sync_status = LoanDocument.ODOO_SYNC_FAILED
                        doc.odoo_sync_error = str(exc)[:500]
                        doc.odoo_last_sync_at = timezone.now()
                        doc.save(update_fields=["odoo_sync_status", "odoo_sync_error", "odoo_last_sync_at"])
        if success:
            if sync_success_count > 0:
                messages.success(
                    request, 
                    f"Documents uploaded successfully. {sync_success_count} document(s) synced to Odoo for verification."
                )
            else:
                messages.success(
                    request,
                    "Documents uploaded successfully. They will be synced to Odoo for verification shortly."
                )
            return redirect("loans:application_detail", pk=application_pk)
    else:
        form = LoanDocumentForm()

    return render(
        request,
        "loans/customer/upload_document.html",
        {"form": form, "application": application},
    )


@login_required
def add_guarantor(request, application_pk):
    """Add a guarantor to a loan application"""
    customer, _ = Customer.objects.get_or_create(user=request.user)
    application = get_object_or_404(
        LoanApplication, pk=application_pk, customer=customer
    )

    if application.status != LoanApplication.DRAFT:
        messages.error(request, "This application can no longer be modified.")
        return redirect("loans:application_detail", pk=application_pk)

    if request.method == "POST":
        form = GuarantorForm(request.POST, customer=customer)
        if form.is_valid():
            guarantor = form.save(commit=False)
            guarantor.application = application
            guarantor.save()
            messages.success(request, "Guarantor added successfully.")
            create_audit_log(
                request.user,
                "CREATE",
                "GuarantorVerification",
                guarantor.pk,
                f"Added guarantor for application {application.application_number}",
            )

            # Sync to Odoo opportunistically — the guarantor record already
            # exists locally regardless of sync outcome, matching upload_document's
            # "save locally first, sync best-effort" pattern.
            if application.odoo_application_id:
                from core.services.odoo_sync import OdooSyncService
                from django.utils import timezone

                guarantor.odoo_sync_status = GuarantorVerification.ODOO_SYNC_PENDING
                guarantor.odoo_sync_attempts += 1
                guarantor.odoo_last_sync_at = timezone.now()
                guarantor.save(update_fields=["odoo_sync_status", "odoo_sync_attempts", "odoo_last_sync_at"])
                try:
                    sync = OdooSyncService()
                    result = sync.sync_guarantor(application, guarantor)
                    guarantor.odoo_loan_guarantor_id = result.get("odoo_loan_guarantor_id")
                    guarantor.odoo_guarantor_id = result.get("odoo_guarantor_id")
                    guarantor.odoo_sync_status = GuarantorVerification.ODOO_SYNC_SUCCESS
                    guarantor.odoo_sync_error = ""
                    guarantor.save(update_fields=[
                        "odoo_loan_guarantor_id", "odoo_guarantor_id",
                        "odoo_sync_status", "odoo_sync_error",
                    ])
                except Exception as exc:
                    logger.warning(
                        "Guarantor sync to Odoo failed: guarantor_id=%s app_id=%s error=%s",
                        guarantor.pk, application.pk, exc,
                    )
                    guarantor.odoo_sync_status = GuarantorVerification.ODOO_SYNC_FAILED
                    guarantor.odoo_sync_error = str(exc)[:500]
                    guarantor.save(update_fields=["odoo_sync_status", "odoo_sync_error"])
                    messages.warning(
                        request,
                        "Guarantor was saved but could not be synced to Odoo yet. It will be retried automatically.",
                    )
            else:
                guarantor.odoo_sync_status = GuarantorVerification.ODOO_SYNC_PENDING
                guarantor.odoo_sync_error = "Application not yet synced to Odoo."
                guarantor.save(update_fields=["odoo_sync_status", "odoo_sync_error"])

            return redirect("loans:application_detail", pk=application_pk)
    else:
        form = GuarantorForm(customer=customer)

    return render(
        request,
        "loans/customer/add_guarantor.html",
        {"form": form, "application": application},
    )


@login_required
def add_collateral(request, application_pk):
    """Pledge collateral to a loan application (only for products that require it)."""
    customer, _ = Customer.objects.get_or_create(user=request.user)
    application = get_object_or_404(
        LoanApplication, pk=application_pk, customer=customer
    )

    if application.status != LoanApplication.DRAFT:
        messages.error(request, "This application can no longer be modified.")
        return redirect("loans:application_detail", pk=application_pk)

    if not application.loan_product.requires_collateral:
        messages.info(request, "This loan product does not require collateral.")
        return redirect("loans:application_detail", pk=application_pk)

    if request.method == "POST":
        form = CollateralForm(request.POST, request.FILES)
        if form.is_valid():
            collateral = form.save(commit=False)
            collateral.loan_application = application
            collateral.save()
            messages.success(request, "Collateral added successfully.")
            create_audit_log(
                request.user,
                "CREATE",
                "Collateral",
                collateral.pk,
                f"Added collateral for application {application.application_number}",
            )

            # Sync to Odoo opportunistically — same "save locally first,
            # sync best-effort" pattern as add_guarantor/upload_document.
            if application.odoo_application_id:
                from core.services.odoo_sync import OdooSyncService
                from django.utils import timezone

                collateral.odoo_sync_status = Collateral.ODOO_SYNC_PENDING
                collateral.odoo_sync_attempts += 1
                collateral.odoo_last_sync_at = timezone.now()
                collateral.save(update_fields=["odoo_sync_status", "odoo_sync_attempts", "odoo_last_sync_at"])
                try:
                    sync = OdooSyncService()
                    result = sync.sync_collateral(application, collateral)
                    collateral.odoo_collateral_id = result.get("odoo_collateral_id")
                    collateral.odoo_sync_status = Collateral.ODOO_SYNC_SUCCESS
                    collateral.odoo_sync_error = ""
                    collateral.save(update_fields=["odoo_collateral_id", "odoo_sync_status", "odoo_sync_error"])

                    for file_field, doc_type, doc_name in (
                        (collateral.title_deed_file, "title_deed", "Title Deed"),
                        (collateral.insurance_certificate_file, "insurance", "Insurance Certificate"),
                        (collateral.valuation_report_file, "valuation", "Valuation Report"),
                    ):
                        if file_field:
                            try:
                                sync.sync_collateral_document(
                                    collateral.odoo_collateral_id, file_field, doc_type, doc_name
                                )
                            except Exception as doc_exc:
                                logger.warning(
                                    "Collateral document sync failed: collateral_id=%s type=%s error=%s",
                                    collateral.pk, doc_type, doc_exc,
                                )
                except Exception as exc:
                    logger.warning(
                        "Collateral sync to Odoo failed: collateral_id=%s app_id=%s error=%s",
                        collateral.pk, application.pk, exc,
                    )
                    collateral.odoo_sync_status = Collateral.ODOO_SYNC_FAILED
                    collateral.odoo_sync_error = str(exc)[:500]
                    collateral.save(update_fields=["odoo_sync_status", "odoo_sync_error"])
                    messages.warning(
                        request,
                        "Collateral was saved but could not be synced to Odoo yet. It will be retried automatically.",
                    )
            else:
                collateral.odoo_sync_status = Collateral.ODOO_SYNC_PENDING
                collateral.odoo_sync_error = "Application not yet synced to Odoo."
                collateral.save(update_fields=["odoo_sync_status", "odoo_sync_error"])

            return redirect("loans:application_detail", pk=application_pk)
    else:
        form = CollateralForm()

    return render(
        request,
        "loans/customer/add_collateral.html",
        {"form": form, "application": application},
    )


# ---------------------------------------------------------------------------
# AJAX
# ---------------------------------------------------------------------------


@login_required
def calculate_loan(request):
    """AJAX endpoint — returns loan cost breakdown for the calculator widget

    Requires authentication to prevent abuse.
    """
    if request.method != "GET":
        return JsonResponse({"error": "GET required"}, status=405)

    # Validate inputs
    product_id = request.GET.get("product_id")
    amount_str = request.GET.get("amount", "0")
    tenure_str = request.GET.get("tenure", "12")

    if not product_id:
        return JsonResponse({"error": "product_id is required"}, status=400)

    # Validate amount is a positive decimal
    try:
        amount = Decimal(amount_str)
        if amount <= 0:
            return JsonResponse({"error": "Amount must be positive"}, status=400)
    except (ValueError, TypeError, InvalidOperation):
        return JsonResponse({"error": "Invalid amount format"}, status=400)

    # Validate tenure is a positive integer
    try:
        tenure = int(tenure_str)
        if tenure <= 0:
            return JsonResponse({"error": "Tenure must be positive"}, status=400)
    except (ValueError, TypeError):
        return JsonResponse({"error": "Invalid tenure format"}, status=400)

    try:
        product = LoanProduct.objects.get(pk=product_id, is_active=True)

        interest = product.calculate_total_interest(amount, tenure)
        fees = product.calculate_total_fees(amount)
        total = amount + interest + fees
        installment = total / Decimal(str(tenure)) if tenure > 0 else Decimal("0")

        return JsonResponse(
            {
                "principal": str(amount),
                "interest": str(interest),
                "fees": str(fees),
                "total": str(total),
                "installment": str(installment),
            }
        )
    except LoanProduct.DoesNotExist:
        return JsonResponse({"error": "Loan product not found"}, status=404)
    except (ValidationError, ValueError) as e:
        return JsonResponse({"error": f"Invalid input: {str(e)}"}, status=400)
    except Exception:
        # Log the full error for debugging but return generic message
        logging.getLogger(__name__).exception("Error in calculate_loan")
        return JsonResponse({"error": "An internal error occurred"}, status=500)


# ---------------------------------------------------------------------------
# Repayment schedule
# ---------------------------------------------------------------------------


@login_required
def repayment_schedule(request, loan_pk):
    """Full repayment schedule for a single active loan"""
    customer, _ = Customer.objects.get_or_create(user=request.user)
    loan = get_object_or_404(Loan, pk=loan_pk, customer=customer)
    schedule = RepaymentSchedule.objects.filter(loan=loan).order_by(
        "installment_number"
    )

    # If no schedule rows exist yet, generate a projected one on the fly
    if not schedule.exists():
        schedule = _build_projected_schedule(loan)
        persisted = False
    else:
        persisted = True

    return render(
        request,
        "loans/customer/repayment_schedule.html",
        {
            "loan": loan,
            "schedule": schedule,
            "persisted": persisted,
        },
    )


# ---------------------------------------------------------------------------
# Notifications
# ---------------------------------------------------------------------------


@login_required
def notifications_list(request):
    """List all in-portal notifications for the logged-in user"""
    notifications = Notification.objects.filter(user=request.user).order_by(
        "-created_at"
    )
    unread_count = notifications.filter(is_read=False).count()
    return render(
        request,
        "loans/customer/notifications.html",
        {
            "notifications": notifications,
            "unread_count": unread_count,
        },
    )


@login_required
def mark_notification_read(request, pk):
    """Mark a single notification as read (POST only)"""
    if request.method != "POST":
        return JsonResponse({"error": "POST method required"}, status=405)
    notification = get_object_or_404(Notification, pk=pk, user=request.user)
    notification.mark_read()
    return JsonResponse({"status": "ok"})


@login_required
def mark_all_notifications_read(request):
    """Mark every unread notification as read for the current user (POST only)"""
    if request.method != "POST":
        return JsonResponse({"error": "POST method required"}, status=405)

    Notification.objects.filter(user=request.user, is_read=False).update(
        is_read=True, read_at=timezone.now()
    )
    return redirect("loans:notifications")


# ---------------------------------------------------------------------------
# PDF Statement
# ---------------------------------------------------------------------------


@login_required
def download_statement(request, loan_pk):
    """
    Generate and stream a PDF loan statement — SRS Section 3.5

    Layout mirrors the "Loan Statement" QWeb report in the Odoo backend
    (odoo_addons/alba_loans/report/loan_statement_template.xml) so a
    customer's portal statement and a loan officer's Odoo-printed
    statement show the same sections, columns, and status colors.
    Built with ReportLab (no per-installment opening/closing balance or
    fee-per-repayment fields exist in the Django schema, so those are
    computed here rather than stored).
    """
    customer, _ = Customer.objects.get_or_create(user=request.user)
    loan = get_object_or_404(
        Loan.objects.select_related("customer__user", "loan_product"),
        pk=loan_pk,
        customer=customer,
    )
    repayments = loan.repayments.order_by("payment_date")
    schedule = RepaymentSchedule.objects.filter(loan=loan).order_by(
        "installment_number"
    )

    try:
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
        from reportlab.lib.units import mm
        from reportlab.platypus import (
            Image,
            Paragraph,
            SimpleDocTemplate,
            Spacer,
            Table,
            TableStyle,
        )
    except ImportError:
        return HttpResponse(
            "ReportLab is not installed. Run: pip install reportlab",
            status=500,
        )

    from django.conf import settings as dj_settings

    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=15 * mm,
        leftMargin=15 * mm,
        topMargin=15 * mm,
        bottomMargin=15 * mm,
    )

    styles = getSampleStyleSheet()
    PRIMARY = colors.HexColor("#0d6efd")
    MUTED = colors.HexColor("#6b7280")
    BORDER = colors.HexColor("#dee2e6")
    # Exact colors Odoo's QWeb template hardcodes for status badges/tints,
    # kept literal here for the same reason: they aren't theme-dependent.
    STATUS_COLOR = {
        "paid": colors.HexColor("#28a745"),
        "overdue": colors.HexColor("#dc3545"),
        "partial": colors.HexColor("#ffc107"),
        "pending": colors.HexColor("#17a2b8"),
    }
    ROW_TINT = {
        "overdue": colors.HexColor("#ffe6e6"),
        "paid": colors.HexColor("#e6ffe6"),
        "partial": colors.HexColor("#fffbe6"),
        "pending": colors.white,
    }
    SYNC_BADGE = {
        "posted": (colors.HexColor("#28a745"), "POSTED"),
        "pending": (colors.HexColor("#ffc107"), "PENDING SYNC"),
        "failed": (colors.HexColor("#dc3545"), "SYNC FAILED"),
    }
    TABLE_PRIMARY_HEAD = colors.HexColor("#b8daff")
    TABLE_SUCCESS_HEAD = colors.HexColor("#c3e6cb")
    TABLE_SECONDARY = colors.HexColor("#d6d8db")
    TABLE_LIGHT = colors.HexColor("#fdfdfe")

    title_style = ParagraphStyle(
        "Title", parent=styles["Heading1"], textColor=PRIMARY, fontSize=16, spaceAfter=2,
    )
    subtitle_style = ParagraphStyle(
        "Subtitle", parent=styles["Normal"], fontSize=12, spaceAfter=2,
    )
    company_style = ParagraphStyle(
        "Company", parent=styles["Normal"], fontSize=9, alignment=2, leading=12,
    )
    section_style = ParagraphStyle(
        "Section", parent=styles["Heading2"], fontSize=11, spaceBefore=6, spaceAfter=4,
    )
    normal = ParagraphStyle("NormalSm", parent=styles["Normal"], fontSize=8)
    footer_style = ParagraphStyle(
        "Footer", parent=normal, textColor=MUTED, fontSize=7,
    )

    def kv_table(rows, col_widths):
        """Borderless label/value table, matching Odoo's table-borderless blocks."""
        t = Table(rows, colWidths=col_widths)
        t.setStyle(TableStyle([
            ("FONTSIZE", (0, 0), (-1, -1), 8),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ("TOPPADDING", (0, 0), (-1, -1), 3),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ]))
        return t

    elements = []

    # ── Header — logo + title on the left, company block on the right ───────
    logo_path = dj_settings.BASE_DIR / "static" / "logo.png"
    logo_cell = [Image(str(logo_path), width=28 * mm, height=14 * mm, kind="proportional")] if logo_path.exists() else []
    left_cell = [
        *logo_cell,
        Paragraph("<b>LOAN STATEMENT</b>", title_style),
        Paragraph(loan.loan_number, subtitle_style),
    ]
    right_cell = [
        Paragraph(
            "<b>Alba Capital Limited</b><br/>Nairobi, Kenya<br/>info@albacapital.co.ke<br/>"
            f"<i>Statement Generated: {timezone.now().strftime('%d %B %Y %H:%M')}</i>",
            company_style,
        )
    ]
    header_table = Table([[left_cell, right_cell]], colWidths=[90 * mm, 90 * mm])
    header_table.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP")]))
    elements.append(header_table)
    elements.append(Spacer(1, 2 * mm))
    hr = Table([[""]], colWidths=[180 * mm])
    hr.setStyle(TableStyle([("LINEBELOW", (0, 0), (-1, 0), 0.75, colors.black)]))
    elements.append(hr)
    elements.append(Spacer(1, 4 * mm))

    # ── Customer Information + Loan Details (side by side) ───────────────────
    user = loan.customer.user
    customer_rows = [
        [Paragraph("<b>Name</b>", normal), Paragraph(user.get_full_name() or "—", normal)],
        [Paragraph("<b>ID Number</b>", normal), Paragraph(loan.customer.id_number or "—", normal)],
        [Paragraph("<b>Phone</b>", normal), Paragraph(user.phone or "—", normal)],
        [Paragraph("<b>Email</b>", normal), Paragraph(user.email or "—", normal)],
    ]
    loan_details_rows = [
        [Paragraph("<b>Loan Number</b>", normal), Paragraph(loan.loan_number, normal)],
        [Paragraph("<b>Product</b>", normal), Paragraph(loan.loan_product.name, normal)],
        [Paragraph("<b>Principal</b>", normal), Paragraph(f"KES {loan.principal_amount:,.2f}", normal)],
        [Paragraph("<b>Interest Rate</b>", normal), Paragraph(f"{loan.loan_product.interest_rate:.2f}% p.m.", normal)],
        [Paragraph("<b>Interest Method</b>", normal), Paragraph(loan.loan_product.get_interest_method_display(), normal)],
        [Paragraph("<b>Tenure</b>", normal), Paragraph(f"{loan.tenure_months} months", normal)],
        [Paragraph("<b>Disbursement Date</b>", normal), Paragraph(loan.disbursement_date.strftime("%d %B %Y"), normal)],
        [Paragraph("<b>Maturity Date</b>", normal), Paragraph(loan.maturity_date.strftime("%d %B %Y"), normal)],
        [Paragraph("<b>Status</b>", normal), Paragraph(loan.get_odoo_status_label(), normal)],
    ]
    elements.append(Paragraph("Customer Information", section_style))
    two_col = Table(
        [[
            kv_table(customer_rows, [30 * mm, 55 * mm]),
            kv_table(loan_details_rows, [38 * mm, 47 * mm]),
        ]],
        colWidths=[90 * mm, 90 * mm],
    )
    two_col.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP")]))
    elements.append(two_col)
    elements.append(Spacer(1, 4 * mm))

    # ── Account Summary ───────────────────────────────────────────────────────
    today = timezone.now().date()
    total_paid = loan.total_amount - loan.outstanding_balance
    arrears_amount = sum(
        (s.balance for s in schedule if s.due_date < today and s.balance > 0),
        Decimal("0"),
    )
    elements.append(Paragraph("Account Summary", section_style))
    summary_rows = [
        [
            Paragraph("<b>Total Repayable</b>", normal),
            Paragraph(f"KES {loan.total_amount:,.2f}", normal),
            Paragraph("<b>Total Paid to Date</b>", normal),
            Paragraph(f"KES {total_paid:,.2f}", normal),
        ],
        [
            Paragraph("<b>Outstanding Balance</b>", normal),
            Paragraph(f"<b>KES {loan.outstanding_balance:,.2f}</b>", normal),
            Paragraph("<b>Arrears Amount</b>", normal),
            Paragraph(
                f"KES {arrears_amount:,.2f}",
                ParagraphStyle("Arrears", parent=normal, textColor=colors.red if arrears_amount > 0 else colors.black),
            ),
        ],
    ]
    summary_style = [
        ("BACKGROUND", (0, 0), (-1, -1), TABLE_LIGHT),
        ("GRID", (0, 0), (-1, -1), 0.5, BORDER),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("PADDING", (0, 0), (-1, -1), 4),
    ]
    if loan.days_overdue > 0:
        summary_rows.append([
            Paragraph("<b>Days in Arrears</b>", normal), "",
            Paragraph(f"<b>{loan.days_overdue} days</b>", normal), "",
        ])
        last_row = len(summary_rows) - 1
        summary_style += [
            ("SPAN", (0, last_row), (1, last_row)),
            ("SPAN", (2, last_row), (3, last_row)),
            ("BACKGROUND", (0, last_row), (-1, last_row), colors.HexColor("#f5c6cb")),
        ]
    summary_table = Table(summary_rows, colWidths=[42 * mm, 48 * mm, 42 * mm, 48 * mm])
    summary_table.setStyle(TableStyle(summary_style))
    elements.append(summary_table)
    elements.append(Spacer(1, 5 * mm))

    # ── Repayment Schedule ─────────────────────────────────────────────────
    if schedule.exists():
        elements.append(Paragraph("Repayment Schedule", section_style))
        sched_headers = [
            "#", "Due Date", "Opening Bal.", "Principal", "Interest",
            "Total Due", "Total Paid", "Balance Due", "Closing Bal.", "Status",
        ]
        sched_rows = [sched_headers]
        row_styles = [
            ("BACKGROUND", (0, 0), (-1, 0), TABLE_PRIMARY_HEAD),
            ("FONTSIZE", (0, 0), (-1, -1), 6.5),
            ("PADDING", (0, 0), (-1, -1), 2.5),
            ("GRID", (0, 0), (-1, -1), 0.3, BORDER),
            ("ALIGN", (2, 0), (-1, -2), "RIGHT"),
            ("ALIGN", (0, 0), (0, -1), "CENTER"),
            ("ALIGN", (-1, 0), (-1, -1), "CENTER"),
        ]
        running_balance = loan.principal_amount
        for i, row in enumerate(schedule, start=1):
            opening_balance = running_balance
            closing_balance = opening_balance - row.principal_due
            running_balance = closing_balance
            if row.is_paid or row.amount_paid >= row.total_due:
                status = "paid"
            elif row.amount_paid > 0:
                status = "partial"
            elif row.due_date < today:
                status = "overdue"
            else:
                status = "pending"
            sched_rows.append([
                str(row.installment_number),
                row.due_date.strftime("%d/%m/%Y"),
                f"{opening_balance:,.2f}",
                f"{row.principal_due:,.2f}",
                f"{row.interest_due:,.2f}",
                f"{row.total_due:,.2f}",
                f"{row.amount_paid:,.2f}",
                f"{row.balance:,.2f}",
                f"{closing_balance:,.2f}",
                status.upper(),
            ])
            row_styles.append(("BACKGROUND", (0, i), (-2, i), ROW_TINT[status]))
            row_styles.append(("BACKGROUND", (-1, i), (-1, i), STATUS_COLOR[status]))
            row_styles.append(("TEXTCOLOR", (-1, i), (-1, i), colors.white))
            if status == "overdue" and row.balance > 0:
                row_styles.append(("TEXTCOLOR", (-2, i), (-2, i), colors.red))
        totals_row = len(sched_rows)
        sched_rows.append([
            "Totals", "", "",
            f"{sum(s.principal_due for s in schedule):,.2f}",
            f"{sum(s.interest_due for s in schedule):,.2f}",
            f"{sum(s.total_due for s in schedule):,.2f}",
            f"{sum(s.amount_paid for s in schedule):,.2f}",
            f"{sum(s.balance for s in schedule):,.2f}",
            "", "",
        ])
        row_styles += [
            ("SPAN", (0, totals_row), (2, totals_row)),
            ("SPAN", (8, totals_row), (9, totals_row)),
            ("BACKGROUND", (0, totals_row), (-1, totals_row), TABLE_SECONDARY),
            ("FONTNAME", (0, totals_row), (-1, totals_row), "Helvetica-Bold"),
        ]
        sched_table = Table(
            sched_rows,
            colWidths=[9 * mm, 18 * mm, 19 * mm, 18 * mm, 17 * mm, 19 * mm, 19 * mm, 19 * mm, 19 * mm, 23 * mm],
            repeatRows=1,
        )
        sched_table.setStyle(TableStyle(row_styles))
        elements.append(sched_table)
        elements.append(Spacer(1, 5 * mm))

    # ── Payment History ────────────────────────────────────────────────────
    elements.append(Paragraph("Payment History", section_style))
    if repayments.exists():
        pay_headers = [
            "Reference", "Date", "Method", "Amount Paid", "Principal", "Interest", "TXN ID", "Status",
        ]
        pay_rows = [pay_headers]
        pay_styles = [
            ("BACKGROUND", (0, 0), (-1, 0), TABLE_SUCCESS_HEAD),
            ("FONTSIZE", (0, 0), (-1, -1), 7),
            ("PADDING", (0, 0), (-1, -1), 3),
            ("GRID", (0, 0), (-1, -1), 0.3, BORDER),
            ("ALIGN", (3, 0), (5, -1), "RIGHT"),
            ("ALIGN", (-1, 0), (-1, -1), "CENTER"),
        ]
        for i, p in enumerate(repayments, start=1):
            pay_rows.append([
                p.receipt_number,
                p.payment_date.strftime("%d/%m/%Y"),
                p.get_payment_method_display(),
                f"{p.amount:,.2f}",
                f"{p.principal_paid:,.2f}",
                f"{p.interest_paid:,.2f}",
                p.reference_number or "—",
                (SYNC_BADGE.get(p.sync_status) or (MUTED, p.sync_status.upper()))[1],
            ])
            badge_color = (SYNC_BADGE.get(p.sync_status) or (MUTED, ""))[0]
            pay_styles.append(("BACKGROUND", (-1, i), (-1, i), badge_color))
            pay_styles.append(("TEXTCOLOR", (-1, i), (-1, i), colors.white))
        totals_row = len(pay_rows)
        pay_rows.append([
            "Total Paid", "", "",
            f"{sum(p.amount for p in repayments):,.2f}",
            f"{sum(p.principal_paid for p in repayments):,.2f}",
            f"{sum(p.interest_paid for p in repayments):,.2f}",
            "", "",
        ])
        pay_styles += [
            ("SPAN", (0, totals_row), (2, totals_row)),
            ("SPAN", (6, totals_row), (7, totals_row)),
            ("BACKGROUND", (0, totals_row), (-1, totals_row), TABLE_SECONDARY),
            ("FONTNAME", (0, totals_row), (-1, totals_row), "Helvetica-Bold"),
        ]
        pay_table = Table(
            pay_rows,
            colWidths=[24 * mm, 20 * mm, 20 * mm, 24 * mm, 20 * mm, 20 * mm, 28 * mm, 24 * mm],
            repeatRows=1,
        )
        pay_table.setStyle(TableStyle(pay_styles))
        elements.append(pay_table)
    else:
        elements.append(Paragraph("No payments recorded yet.", normal))

    # ── Footer ─────────────────────────────────────────────────────────────
    elements.append(Spacer(1, 6 * mm))
    footer_hr = Table([[""]], colWidths=[180 * mm])
    footer_hr.setStyle(TableStyle([("LINEBELOW", (0, 0), (-1, 0), 0.75, colors.black)]))
    elements.append(footer_hr)
    elements.append(Spacer(1, 2 * mm))
    elements.append(
        Paragraph(
            "This statement is generated automatically by Alba Capital's loan management system "
            "and is valid as of the date of generation. For queries, contact your loan officer "
            "or email <i>info@albacapital.co.ke</i>. "
            "Alba Capital Limited is regulated by the Central Bank of Kenya.",
            footer_style,
        )
    )

    doc.build(elements)
    buffer.seek(0)

    filename = f"loan_statement_{loan.loan_number}_{timezone.now().strftime('%Y%m%d')}.pdf"
    response = HttpResponse(buffer, content_type="application/pdf")
    response["Content-Disposition"] = f'attachment; filename="{filename}"'

    create_audit_log(
        request.user,
        "VIEW",
        "Loan",
        loan.pk,
        f"Downloaded PDF statement for loan {loan.loan_number}",
    )
    return response


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


@login_required
def download_official_report(request, report_type, res_id):
    """
    Proxy view to download Odoo-generated reports via the Django portal.
    Supported report_types: 'application', 'guarantor', 'statement'
    """
    # Permission mapping
    report_map = {
        "application": "alba_loans.loan_application_report",
        "guarantor": "alba_loans.guarantor_agreement_report",
        "statement": "alba_investors.investment_statement_report",
    }

    xml_id = report_map.get(report_type)
    if not xml_id:
        return redirect("dashboard")

    # Access control — verify the requesting customer owns the record before
    # forwarding any request to Odoo, and resolve the Odoo-side id to use
    # (Django pk and Odoo record id are different id spaces).
    customer, _ = Customer.objects.get_or_create(user=request.user)

    if report_type == "application":
        application = get_object_or_404(LoanApplication, pk=res_id, customer=customer)
        odoo_res_id = application.odoo_application_id
    elif report_type == "guarantor":
        guarantor = get_object_or_404(
            GuarantorVerification, pk=res_id, application__customer=customer
        )
        odoo_res_id = guarantor.odoo_loan_guarantor_id
    else:  # "statement" — no Django model here to verify ownership against, fail closed
        raise Http404()

    if not odoo_res_id:
        messages.error(
            request, "Official document is not yet available for this record."
        )
        return redirect("dashboard")

    sync = OdooSyncService()
    try:
        pdf_base64 = sync.download_report(xml_id, odoo_res_id)
        if not pdf_base64:
            messages.error(
                request, "Official document is not yet available for this record."
            )
            return redirect("dashboard")

        pdf_content = base64.b64decode(pdf_base64)
        response = HttpResponse(pdf_content, content_type="application/pdf")
        filename = f"{report_type}_{res_id}.pdf"
        response["Content-Disposition"] = f'attachment; filename="{filename}"'
        return response
    except OdooSyncError as e:
        messages.error(request, f"Odoo Sync Error: {str(e)}")
    except Exception as e:
        logger.error(f"Failed to download report {xml_id}/{res_id}: {str(e)}")
        messages.error(request, "An error occurred while generating your document.")

    return redirect("dashboard")


def _build_projected_schedule(loan):
    """
    Build a projected repayment schedule list (not saved to DB) for display
    when Odoo has not yet pushed the confirmed schedule rows.
    Returns a list of dict-like objects that the template can iterate over.
    """
    from dateutil.relativedelta import relativedelta

    schedule = []
    principal = loan.principal_amount
    total_interest = loan.interest_amount
    tenure = loan.tenure_months

    if tenure <= 0:
        return schedule

    installment = loan.installment_amount
    principal_per_installment = (principal / Decimal(tenure)).quantize(Decimal("0.01"))
    interest_per_installment = (total_interest / Decimal(tenure)).quantize(
        Decimal("0.01")
    )

    running_balance = loan.total_amount
    due_date = loan.first_payment_date

    today = timezone.now().date()

    for i in range(1, tenure + 1):
        running_balance -= installment
        if running_balance < Decimal("0"):
            running_balance = Decimal("0")

        schedule.append(
            {
                "installment_number": i,
                "due_date": due_date,
                "principal_due": principal_per_installment,
                "interest_due": interest_per_installment,
                "fees_due": Decimal("0"),
                "penalty_due": Decimal("0"),
                "total_due": installment,
                "amount_paid": Decimal("0"),
                "balance": running_balance,
                "is_paid": False,
                "paid_date": None,
                # helper flags for template
                "is_overdue": due_date < today,
            }
        )
        due_date = due_date + relativedelta(months=1)

    return schedule


def _seed_loan_products():
    """Create default loan products if the table is empty"""
    from django.db import transaction

    products = [
        {
            "code": "QSAL001",
            "name": "Quick Salary Advance",
            "category": "salary_advance",
            "description": "Fast salary advance for employed individuals.",
            "min_amount": Decimal("10000"),
            "max_amount": Decimal("50000"),
            "interest_rate": 15.0,
            "interest_method": "REDUCING_BALANCE",
            "min_tenure_months": 1,
            "max_tenure_months": 6,
            "origination_fee_percentage": 5.0,
            "processing_fee": Decimal("500"),
            "is_active": True,
        },
        {
            "code": "BIZ001",
            "name": "Business Expansion Loan",
            "category": "business_loan",
            "description": "Flexible financing for business growth.",
            "min_amount": Decimal("50000"),
            "max_amount": Decimal("500000"),
            "interest_rate": 18.0,
            "interest_method": "REDUCING_BALANCE",
            "min_tenure_months": 6,
            "max_tenure_months": 36,
            "origination_fee_percentage": 3.0,
            "processing_fee": Decimal("1500"),
            "is_active": True,
        },
        {
            "code": "ASSET001",
            "name": "Asset Finance — Vehicle",
            "category": "asset_financing",
            "description": "Financing for new and used vehicle purchases.",
            "min_amount": Decimal("100000"),
            "max_amount": Decimal("1000000"),
            "interest_rate": 12.0,
            "interest_method": "REDUCING_BALANCE",
            "min_tenure_months": 12,
            "max_tenure_months": 48,
            "origination_fee_percentage": 2.0,
            "processing_fee": Decimal("2000"),
            "is_active": True,
        },
    ]

    with transaction.atomic():
        for data in products:
            LoanProduct.objects.update_or_create(code=data["code"], defaults=data)
