# -*- coding: utf-8 -*-
"""
core.verification_views
========================
Django views that back the React document-verification wizard embedded in the
customer portal.

URL map (registered in config/urls.py)
---------------------------------------
GET  /verify/profile/                   Render the wizard HTML shell
POST /api/verify/documents/upload/      Save uploaded files to media storage
POST /api/verify/profile/update/        Write extracted OCR data to Customer record
POST /api/verify/submit/                Mark Customer verified + trigger Odoo KYC sync
GET  /api/verify/status/                Return current verification status
"""

import json
import logging
import os

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.http import require_GET

from core.forms import VerificationProfileForm

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_ALLOWED_IMAGE_TYPES = {
    "image/jpeg",
    "image/png",
    "image/webp",
    "image/heic",
    "image/heif",
}
_ALLOWED_DOC_TYPES = _ALLOWED_IMAGE_TYPES | {"application/pdf"}
_MAX_FILE_BYTES = 5 * 1024 * 1024  # 5 MB


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _get_customer(user):
    """Return Customer profile linked to user, or None."""
    return getattr(user, "customer_profile", None)


def _json_error(message: str, status: int = 400) -> JsonResponse:
    return JsonResponse({"status": "error", "error": message}, status=status)


def _validate_file(f, allowed_types: set, label: str):
    """Return (ok: bool, error_message: str)."""
    if f.content_type not in allowed_types:
        return (
            False,
            f"{label}: unsupported type '{f.content_type}'. Allowed: {', '.join(sorted(allowed_types))}",
        )
    if f.size > _MAX_FILE_BYTES:
        return False, f"{label}: file too large ({f.size // 1024} KB). Max 5 MB."
    return True, ""


def _safe_url(field) -> str:
    """Return URL string for a FileField value, or empty string."""
    try:
        return field.url if field else ""
    except Exception:
        return ""


# ---------------------------------------------------------------------------
# Page view
# ---------------------------------------------------------------------------


@login_required
def client_profile_verification(request):
    """Render the HTML page that loads the React verification wizard.

    GET  – display the form pre-filled from the Customer record.
    POST – validate and save profile fields, then redirect back.
    """
    customer = _get_customer(request.user)

    if request.method == "POST":
        form = VerificationProfileForm(request.POST, instance=customer)
        if form.is_valid():
            form.save()
            messages.success(request, "Profile saved successfully.")
            return redirect("client_profile_verification")
        else:
            messages.error(request, "Please correct the errors below.")
    else:
        form = VerificationProfileForm(instance=customer)

    # Build existing-document URLs for React context
    payslip_urls = []
    if customer:
        try:
            payslip_urls = json.loads(customer.additional_payslip_files or "[]")
        except (json.JSONDecodeError, ValueError):
            payslip_urls = []

    context = {
        "form": form,
        "customer": customer,
        # 'client' alias so the template works unchanged
        "client": customer,
        "verification_status": getattr(customer, "verification_status", "pending"),
        "debug": request.GET.get("debug", "false").lower() == "true",
        # Pre-built JSON for the VERIFICATION_CONTEXT window variable
        "verification_context_json": json.dumps(
            {
                "csrfToken": request.META.get("CSRF_COOKIE", ""),
                "apiBaseUrl": "/api/verify",
                "existingDocuments": {
                    "idFront": _safe_url(getattr(customer, "national_id_file", None)),
                    "idBack": _safe_url(getattr(customer, "id_back_file", None)),
                    "payslips": payslip_urls,
                    "selfie": _safe_url(
                        getattr(customer, "face_recognition_photo", None)
                    ),
                },
                "verificationStatus": getattr(
                    customer, "verification_status", "pending"
                ),
                "confidence": getattr(customer, "verification_confidence", 0),
            }
        ),
    }
    return render(request, "client_profile_verification.html", context)


# ---------------------------------------------------------------------------
# File upload
# ---------------------------------------------------------------------------


@method_decorator(login_required, name="dispatch")
class DocumentUploadView(View):
    """
    Accept multipart/form-data file uploads from the verification wizard.

    Expected fields:
        id_front      image
        id_back       image
        payslip_<n>   image or PDF  (one per payslip, e.g. payslip_0, payslip_1)
        selfie        image
    """

    def post(self, request):
        customer = _get_customer(request.user)
        if not customer:
            return _json_error("Customer profile not found.", 404)

        uploaded = {}
        errors = []

        # ── ID front ──────────────────────────────────────────────────────────
        if "id_front" in request.FILES:
            f = request.FILES["id_front"]
            ok, err = _validate_file(f, _ALLOWED_IMAGE_TYPES, "ID front")
            if not ok:
                errors.append(err)
            else:
                ext = os.path.splitext(f.name)[1] or ".jpg"
                path = default_storage.save(
                    f"kyc/{customer.pk}/id_front{ext}", ContentFile(f.read())
                )
                customer.national_id_file = path
                uploaded["id_front"] = default_storage.url(path)

        # ── ID back ───────────────────────────────────────────────────────────
        if "id_back" in request.FILES:
            f = request.FILES["id_back"]
            ok, err = _validate_file(f, _ALLOWED_IMAGE_TYPES, "ID back")
            if not ok:
                errors.append(err)
            else:
                ext = os.path.splitext(f.name)[1] or ".jpg"
                path = default_storage.save(
                    f"kyc/{customer.pk}/id_back{ext}", ContentFile(f.read())
                )
                customer.id_back_file = path
                uploaded["id_back"] = default_storage.url(path)

        # ── Payslips ──────────────────────────────────────────────────────────
        try:
            payslip_paths = json.loads(customer.additional_payslip_files or "[]")
        except (json.JSONDecodeError, ValueError):
            payslip_paths = []

        payslip_urls = []
        for key in sorted(request.FILES):
            if not key.startswith("payslip_"):
                continue
            f = request.FILES[key]
            ok, err = _validate_file(f, _ALLOWED_DOC_TYPES, f"Payslip ({key})")
            if not ok:
                errors.append(err)
                continue
            path = default_storage.save(
                f"kyc/{customer.pk}/payslips/{f.name}", ContentFile(f.read())
            )
            url = default_storage.url(path)
            payslip_paths.append(path)
            payslip_urls.append(url)
            # Keep first payslip in legacy bank_statement_file field
            if not customer.bank_statement_file:
                customer.bank_statement_file = path

        if payslip_urls:
            customer.additional_payslip_files = json.dumps(payslip_paths)
            uploaded["payslips"] = payslip_urls

        # ── Selfie ────────────────────────────────────────────────────────────
        if "selfie" in request.FILES:
            f = request.FILES["selfie"]
            ok, err = _validate_file(f, _ALLOWED_IMAGE_TYPES, "Selfie")
            if not ok:
                errors.append(err)
            else:
                ext = os.path.splitext(f.name)[1] or ".jpg"
                path = default_storage.save(
                    f"kyc/{customer.pk}/selfie{ext}", ContentFile(f.read())
                )
                customer.face_recognition_photo = path
                uploaded["selfie"] = default_storage.url(path)

        if errors:
            return _json_error("; ".join(errors), 422)

        customer.verification_status = "in_progress"
        customer.save()
        logger.info(
            "Documents uploaded for customer pk=%s: %s",
            customer.pk,
            list(uploaded.keys()),
        )
        return JsonResponse({"status": "success", "uploaded": uploaded})


# ---------------------------------------------------------------------------
# Profile update with OCR-extracted data
# ---------------------------------------------------------------------------


@method_decorator(login_required, name="dispatch")
class ProfileUpdateView(View):
    """
    Write OCR-extracted data from the React wizard back to the Customer record.

    Expected JSON body:
    {
        "extracted_data": {
            "personalInfo":   { "idNumber", "dateOfBirth", "gender", "fullName" },
            "employmentInfo": { "employer", "monthlyIncome" }
        },
        "verification_results": { ...full wizard output... },
        "confidence_score": 85
    }
    """

    def post(self, request):
        customer = _get_customer(request.user)
        if not customer:
            return _json_error("Customer profile not found.", 404)

        try:
            body = json.loads(request.body)
        except (json.JSONDecodeError, ValueError):
            return _json_error("Invalid JSON body.")

        extracted = body.get("extracted_data", {})
        personal = extracted.get("personalInfo", {})
        employment = extracted.get("employmentInfo", {})

        # Personal info — only fill blanks, never overwrite manually entered data
        if personal.get("idNumber") and not customer.id_number:
            customer.id_number = str(personal["idNumber"])[:50]

        if personal.get("dateOfBirth") and not customer.date_of_birth:
            try:
                from datetime import date as date_type

                parts = str(personal["dateOfBirth"]).split("-")
                customer.date_of_birth = date_type(
                    int(parts[0]), int(parts[1]), int(parts[2])
                )
            except Exception:
                pass

        # Employment info — only fill blanks
        if employment.get("employer") and not customer.employer_name:
            customer.employer_name = str(employment["employer"])[:200]

        if employment.get("monthlyIncome") and not customer.monthly_income:
            try:
                customer.monthly_income = float(employment["monthlyIncome"])
            except (TypeError, ValueError):
                pass

        # Store wizard output
        customer.verification_results = json.dumps(
            body.get("verification_results", {}), default=str
        )[:10_000]
        customer.verification_confidence = min(
            int(body.get("confidence_score", 0)), 100
        )
        customer.save()

        logger.info(
            "Profile updated from wizard: customer pk=%s confidence=%s",
            customer.pk,
            customer.verification_confidence,
        )
        return JsonResponse(
            {
                "status": "success",
                "customer_id": customer.pk,
                "confidence": customer.verification_confidence,
            }
        )


# ---------------------------------------------------------------------------
# Final submission
# ---------------------------------------------------------------------------


@method_decorator(login_required, name="dispatch")
class VerificationSubmitView(View):
    """
    Called when the customer clicks "Submit Verification" in the wizard.
    Marks Customer as verified and triggers Odoo KYC sync (best-effort).
    """

    def post(self, request):
        customer = _get_customer(request.user)
        if not customer:
            return _json_error("Customer profile not found.", 404)

        try:
            body = json.loads(request.body)
        except (json.JSONDecodeError, ValueError):
            body = {}

        confidence = min(
            int(body.get("confidence_score", customer.verification_confidence)), 100
        )

        if confidence < 40:
            return _json_error(
                "Verification confidence too low. Please re-upload clearer documents.",
                422,
            )

        customer.verification_status = "verified"
        customer.verification_confidence = confidence
        customer.kyc_verified = True
        customer.save()

        # Best-effort Odoo KYC sync — never block the response on failure
        odoo_synced = False
        try:
            from core.services.odoo_sync import OdooSyncService

            svc = OdooSyncService()
            if svc.is_reachable():
                odoo_id = customer.odoo_customer_id
                if not odoo_id:
                    new_id, _ = svc.sync_user_to_odoo(request.user)
                    if new_id:
                        customer.odoo_customer_id = new_id
                        customer.save(update_fields=["odoo_customer_id"])
                        odoo_id = new_id
                if odoo_id:
                    svc.update_kyc_status(
                        odoo_customer_id=odoo_id,
                        kyc_status="verified",
                        notes=f"Verified via document wizard (confidence {confidence}%)",
                    )
                    odoo_synced = True
        except Exception as exc:
            logger.warning(
                "Odoo KYC sync failed for customer pk=%s: %s", customer.pk, exc
            )

        logger.info(
            "Verification submitted: pk=%s confidence=%s odoo_synced=%s",
            customer.pk,
            confidence,
            odoo_synced,
        )
        return JsonResponse(
            {
                "status": "success",
                "verification_status": "verified",
                "confidence": confidence,
                "odoo_synced": odoo_synced,
            }
        )


# ---------------------------------------------------------------------------
# Status endpoint
# ---------------------------------------------------------------------------


@login_required
@require_GET
def verification_status(request):
    """Return current verification status for the logged-in customer."""
    customer = _get_customer(request.user)
    if not customer:
        return _json_error("Customer profile not found.", 404)

    payslip_urls = []
    try:
        paths = json.loads(customer.additional_payslip_files or "[]")
        payslip_urls = [default_storage.url(p) for p in paths if p]
    except Exception:
        pass

    return JsonResponse(
        {
            "status": "success",
            "verification_status": customer.verification_status,
            "verification_confidence": customer.verification_confidence,
            "kyc_verified": customer.kyc_verified,
            "has_id_front": bool(customer.national_id_file),
            "has_id_back": bool(customer.id_back_file),
            "payslip_count": len(payslip_urls),
            "has_selfie": bool(customer.face_recognition_photo),
            "id_number": customer.id_number or "",
            "monthly_income": float(customer.monthly_income or 0),
            "employer": customer.employer_name or "",
        }
    )
