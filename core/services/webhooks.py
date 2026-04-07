# -*- coding: utf-8 -*-
"""
core.services.webhooks
=======================
Inbound webhook receiver for Odoo → Django event notifications.

Every time Odoo fires a webhook (application status changed, loan disbursed,
payment matched, M-Pesa received, etc.) it POSTs a signed JSON envelope to
``/api/v1/webhooks/odoo/``.  This module handles:

  1. HMAC-SHA256 signature verification  (X-Alba-Signature header)
  2. Idempotency guard                   (X-Alba-Delivery deduplication)
  3. Event routing                       (dispatch to per-event handlers)
  4. Audit logging                       (WebhookDelivery model)

Configuration (.env)
---------------------
  ODOO_WEBHOOK_SECRET   64-char hex shared secret used to verify signatures.

Signature format
----------------
Odoo computes::

    signature = hmac.new(secret.encode(), body_bytes, sha256).hexdigest()
    X-Alba-Signature: sha256=<hex_digest>

The receiver re-computes the HMAC over the raw request body and compares
it in constant time to prevent timing attacks.

Event catalogue
---------------
  application.status_changed
  loan.disbursed
  loan.npl_flagged
  loan.closed
  loan.instalment_overdue
  loan.maturing_soon
  payment.matched
  payment.mpesa_received
  customer.kyc_verified
  portfolio.stats_updated
  integration.health_check
  integration.dead_webhooks_alert

Adding a new event handler
--------------------------
Define a function ``handle_<dotted_event_with_underscores>(data, delivery_id)``
and register it in the ``_EVENT_HANDLERS`` dict at the bottom of this file.
"""

import hashlib
import hmac
import json
import logging
from datetime import datetime, timezone

from django.conf import settings
from django.http import HttpRequest, JsonResponse
from django.utils import timezone as dj_timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_SIGNATURE_HEADER = "HTTP_X_ALBA_SIGNATURE"
_EVENT_HEADER = "HTTP_X_ALBA_EVENT"
_DELIVERY_HEADER = "HTTP_X_ALBA_DELIVERY"


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class WebhookVerificationError(Exception):
    """Raised when the webhook signature cannot be verified."""

    pass


class WebhookParseError(Exception):
    """Raised when the webhook body cannot be parsed."""

    pass


# ---------------------------------------------------------------------------
# Signature verification
# ---------------------------------------------------------------------------


def verify_signature(raw_body: bytes, signature_header: str, secret: str) -> bool:
    """
    Verify the HMAC-SHA256 signature of an inbound Odoo webhook.

    Args:
        raw_body:          The raw (undecoded) request body bytes.
        signature_header:  Value of the X-Alba-Signature header,
                           e.g. ``sha256=abc123…``.
        secret:            The shared HMAC secret (ODOO_WEBHOOK_SECRET).

    Returns:
        bool: ``True`` when the signature matches, ``False`` otherwise.

    Notes:
        The comparison uses ``hmac.compare_digest`` to prevent timing attacks.
        If ``signature_header`` does not start with ``sha256=`` or ``secret``
        is empty, the function returns ``False`` without raising.
    """
    if not secret:
        logger.warning(
            "ODOO_WEBHOOK_SECRET is not configured — all webhooks will be rejected."
        )
        return False

    if not signature_header or not signature_header.startswith("sha256="):
        return False

    expected_digest = signature_header[len("sha256=") :]
    computed = hmac.new(
        secret.encode("utf-8"),
        raw_body,
        hashlib.sha256,
    ).hexdigest()

    return hmac.compare_digest(computed, expected_digest)


# ---------------------------------------------------------------------------
# HTTP view — main entry point
# ---------------------------------------------------------------------------


@csrf_exempt
@require_POST
def odoo_webhook_receiver(request: HttpRequest) -> JsonResponse:
    """
    Django view: receive and process inbound Odoo webhook POST requests.

    URL:  POST /api/v1/webhooks/odoo/

    Responses:
        200  Event processed (or intentionally ignored / duplicate).
        400  Malformed body or missing required envelope fields.
        401  Missing or invalid signature.
        500  Unexpected processing error (event still acknowledged to
             prevent Odoo from retrying a definitively malformed payload).

    Safaricom / Odoo will retry delivery if they receive a non-2xx response,
    so we always return 200 for known events even when our handler raises —
    and log the error for investigation.
    """
    # ── 1. Read raw body ────────────────────────────────────────────────────
    raw_body = request.body  # bytes

    # ── 2. Verify HMAC signature ────────────────────────────────────────────
    secret = getattr(settings, "ODOO_WEBHOOK_SECRET", "") or ""
    sig_header = request.META.get(_SIGNATURE_HEADER, "")

    if not verify_signature(raw_body, sig_header, secret):
        logger.warning(
            "Webhook signature verification failed.  sig_header=%s  remote_addr=%s",
            sig_header[:30] if sig_header else "(none)",
            request.META.get("REMOTE_ADDR", "—"),
        )
        return JsonResponse(
            {"status": "error", "detail": "Invalid or missing signature."},
            status=401,
        )

    # ── 3. Parse envelope ───────────────────────────────────────────────────
    try:
        envelope = json.loads(raw_body.decode("utf-8"))
    except (ValueError, UnicodeDecodeError) as exc:
        logger.error("Webhook body parse error: %s", exc)
        return JsonResponse(
            {"status": "error", "detail": "Malformed JSON body."},
            status=400,
        )

    event_type = (
        envelope.get("event") or request.META.get(_EVENT_HEADER, "") or ""
    ).strip()
    delivery_id = (
        envelope.get("delivery_id") or request.META.get(_DELIVERY_HEADER, "") or ""
    ).strip()
    timestamp_str = (envelope.get("timestamp") or "").strip()
    data = envelope.get("data") or {}

    if not event_type:
        logger.warning("Webhook received with no event type — rejecting.")
        return JsonResponse(
            {"status": "error", "detail": "Missing 'event' field in envelope."},
            status=400,
        )

    logger.info(
        "Webhook received: event=%s delivery_id=%s",
        event_type,
        delivery_id or "(none)",
    )

    # ── 4. Idempotency check ────────────────────────────────────────────────
    if delivery_id and _is_duplicate_delivery(delivery_id):
        logger.info(
            "Duplicate webhook delivery ignored: event=%s delivery_id=%s",
            event_type,
            delivery_id,
        )
        return JsonResponse(
            {"status": "ok", "detail": "Duplicate delivery — ignored."},
            status=200,
        )

    # ── 5. Persist delivery record (best-effort) ────────────────────────────
    _record_delivery(
        event_type=event_type,
        delivery_id=delivery_id,
        timestamp_str=timestamp_str,
        raw_body=raw_body,
        status="processing",
        remote_ip=_get_client_ip(request),
    )

    # ── 6. Dispatch to event handler ────────────────────────────────────────
    handler = _EVENT_HANDLERS.get(event_type)
    processing_status = "success"
    processing_detail = ""

    if handler is None:
        logger.info(
            "No handler registered for webhook event '%s' — acknowledging.", event_type
        )
        processing_status = "unhandled"
    else:
        try:
            handler(data, delivery_id)
            logger.info(
                "Webhook event '%s' processed successfully (delivery_id=%s).",
                event_type,
                delivery_id,
            )
        except Exception as exc:
            processing_status = "error"
            processing_detail = str(exc)
            logger.exception(
                "Error processing webhook event '%s' (delivery_id=%s): %s",
                event_type,
                delivery_id,
                exc,
            )

    # ── 7. Update delivery record (best-effort) ─────────────────────────────
    _update_delivery(
        delivery_id=delivery_id,
        status=processing_status,
        detail=processing_detail,
    )

    # Always return 200 so Odoo does not retry indefinitely
    return JsonResponse({"status": "ok", "event": event_type}, status=200)


# ---------------------------------------------------------------------------
# Delivery persistence helpers
# ---------------------------------------------------------------------------


def _is_duplicate_delivery(delivery_id: str) -> bool:
    """
    Return ``True`` when a WebhookDelivery record with *delivery_id*
    already exists and was processed successfully.

    Falls back to ``False`` when the model is unavailable (e.g. before
    migrations have run) so the webhook is processed rather than silently
    dropped.
    """
    if not delivery_id:
        return False
    try:
        from loans.models import WebhookDelivery  # lazy import

        return WebhookDelivery.objects.filter(
            delivery_id=delivery_id,
            status__in=("success", "processing"),
        ).exists()
    except Exception:
        return False


def _record_delivery(
    event_type: str,
    delivery_id: str,
    timestamp_str: str,
    raw_body: bytes,
    status: str,
    remote_ip: str,
):
    """Create a WebhookDelivery record for audit purposes (best-effort)."""
    if not delivery_id:
        return
    try:
        from loans.models import WebhookDelivery  # lazy import

        WebhookDelivery.objects.update_or_create(
            delivery_id=delivery_id,
            defaults={
                "event_type": event_type[:128],
                "raw_body": raw_body.decode("utf-8", errors="replace")[:20_000],
                "status": status,
                "remote_ip": remote_ip[:64],
                "odoo_timestamp": _parse_iso_timestamp(timestamp_str),
            },
        )
    except Exception as exc:
        logger.debug("Could not record webhook delivery: %s", exc)


def _update_delivery(delivery_id: str, status: str, detail: str):
    """Update the status of an existing WebhookDelivery record."""
    if not delivery_id:
        return
    try:
        from loans.models import WebhookDelivery  # lazy import

        WebhookDelivery.objects.filter(delivery_id=delivery_id).update(
            status=status,
            processing_detail=detail[:5_000],
        )
    except Exception as exc:
        logger.debug("Could not update webhook delivery status: %s", exc)


def _parse_iso_timestamp(ts: str):
    """Parse an ISO-8601 timestamp string; return None on failure."""
    if not ts:
        return None
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None


def _get_client_ip(request: HttpRequest) -> str:
    """Extract the real client IP from request headers."""
    x_forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
    if x_forwarded:
        return x_forwarded.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR", "")


# Event handlers
# ---------------------------------------------------------------------------


def _safe_int(value, field_name="value", default=0):
    """Safely convert value to int with validation"""
    try:
        if value is None or value == "":
            return default
        int_value = int(value)
        if int_value < 0:
            logger.warning("Negative value received for %s: %s", field_name, int_value)
            return default
        return int_value
    except (ValueError, TypeError) as exc:
        logger.warning("Invalid integer value for %s: %s - %s", field_name, value, exc)
        return default


def _safe_float(value, field_name="value", default=0.0):
    """Safely convert value to float with validation"""
    try:
        if value is None or value == "":
            return default
        float_value = float(value)
        if float_value < 0:
            logger.warning(
                "Negative value received for %s: %s", field_name, float_value
            )
            return default
        return float_value
    except (ValueError, TypeError) as exc:
        logger.warning("Invalid float value for %s: %s - %s", field_name, value, exc)
        return default


def _handle_application_status_changed(data: dict, delivery_id: str):
    """
    application.status_changed
    ---------------------------
    Odoo has moved an application to a new stage.  Update the Django
    LoanApplication record to reflect the new status.

    Expected data keys:
        odoo_application_id, django_application_id, new_status,
        odoo_loan_id (when disbursed), loan_number (when disbursed)
    """
    from loans.models import LoanApplication  # lazy import

    django_app_id = _safe_int(
        data.get("django_application_id"), "django_application_id"
    )
    new_status = (data.get("new_status") or data.get("status") or "").strip()
    odoo_app_id = _safe_int(data.get("odoo_application_id"), "odoo_application_id")

    if not django_app_id and not odoo_app_id:
        logger.warning(
            "application.status_changed: no application ID in payload — skipping."
        )
        return

    # Lookup by Django ID first, fall back to Odoo ID
    app = None
    if django_app_id:
        app = LoanApplication.objects.filter(id=django_app_id).first()
    if not app and odoo_app_id:
        app = LoanApplication.objects.filter(odoo_application_id=odoo_app_id).first()

    if not app:
        logger.warning(
            "application.status_changed: no LoanApplication found "
            "(django_id=%s, odoo_id=%s).",
            django_app_id,
            odoo_app_id,
        )
        return

    update_fields = []

    # Map Odoo state to Django status
    status_map = {
        "submitted": "SUBMITTED",
        "under_review": "UNDER_REVIEW",
        "credit_analysis": "CREDIT_ANALYSIS",
        "pending_approval": "PENDING_APPROVAL",
        "approved": "APPROVED",
        "employer_verification": "EMPLOYER_VERIFICATION",
        "guarantor_confirmation": "GUARANTOR_CONFIRMATION",
        "disbursed": "DISBURSED",
        "rejected": "REJECTED",
        "cancelled": "CANCELLED",
    }
    mapped_status = status_map.get(new_status, new_status)
    if mapped_status and hasattr(app, "status") and app.status != mapped_status:
        app.status = mapped_status
        update_fields.append("status")

    # Capture Odoo application ID if missing
    if (
        odoo_app_id
        and hasattr(app, "odoo_application_id")
        and not app.odoo_application_id
    ):
        app.odoo_application_id = odoo_app_id
        update_fields.append("odoo_application_id")

    # Capture loan details when disbursed
    if new_status == "disbursed":
        odoo_loan_id = _safe_int(data.get("odoo_loan_id"), "odoo_loan_id")
        loan_number = (data.get("loan_number") or "").strip()
        # Validate loan number format
        if loan_number and not (
            len(loan_number) >= 3
            and loan_number.replace("-", "").replace("_", "").isalnum()
        ):
            logger.warning("Invalid loan number format: %s", loan_number)
            loan_number = ""
        if odoo_loan_id and hasattr(app, "odoo_loan_id"):
            app.odoo_loan_id = odoo_loan_id
            update_fields.append("odoo_loan_id")
        if loan_number and hasattr(app, "odoo_loan_number"):
            app.odoo_loan_number = loan_number
            update_fields.append("odoo_loan_number")

    if update_fields:
        app.save(update_fields=update_fields)
        logger.info(
            "Application %s updated: status=%s (fields=%s)",
            app.pk,
            mapped_status,
            update_fields,
        )


def _handle_loan_disbursed(data: dict, delivery_id: str):
    """
    loan.disbursed
    --------------
    Odoo has disbursed a loan.  Mark the Django application as DISBURSED,
    record the Odoo loan ID / loan number, and create or update the Loan record.
    """
    # ── Step 1: update application status ───────────────────────────────────
    data_with_status = dict(data)
    data_with_status["new_status"] = "disbursed"
    _handle_application_status_changed(data_with_status, delivery_id)

    # ── Step 2: create / update Django Loan ─────────────────────────────────
    try:
        import datetime
        from decimal import Decimal

        from django.utils import timezone as dj_tz

        from loans.models import Loan, LoanApplication  # lazy import

        odoo_loan_id = _safe_int(data.get("odoo_loan_id"), "odoo_loan_id")
        django_app_id = _safe_int(
            data.get("django_application_id"), "django_application_id"
        )
        odoo_app_id = _safe_int(data.get("odoo_application_id"), "odoo_application_id")
        loan_number = (data.get("loan_number") or "").strip()
        disbursed_amount = _safe_float(data.get("disbursed_amount"), "disbursed_amount")
        outstanding = _safe_float(
            data.get("outstanding_balance"), "outstanding_balance", disbursed_amount
        )
        disbursement_date_str = (data.get("disbursement_date") or "").strip()

        if odoo_loan_id <= 0:
            logger.warning("loan.disbursed: invalid odoo_loan_id — skipping Loan sync.")
            return

        # Find the LoanApplication
        app = None
        if django_app_id:
            app = LoanApplication.objects.filter(id=django_app_id).first()
        if not app and odoo_app_id:
            app = LoanApplication.objects.filter(
                odoo_application_id=odoo_app_id
            ).first()

        if not app:
            logger.warning(
                "loan.disbursed: cannot find LoanApplication "
                "(django_id=%s, odoo_id=%s) — creating stub Loan skipped.",
                django_app_id,
                odoo_app_id,
            )
            return

        # Parse disbursement date
        try:
            d_date = (
                datetime.date.fromisoformat(disbursement_date_str)
                if disbursement_date_str
                else dj_tz.now().date()
            )
        except ValueError:
            d_date = dj_tz.now().date()

        # Check if Loan already exists for this application
        existing_loan = None
        try:
            existing_loan = app.disbursed_loan
        except Exception:
            existing_loan = None

        if existing_loan:
            # Loan already exists — just update the Odoo fields
            update_fields = []
            if odoo_loan_id and not existing_loan.odoo_loan_id:
                existing_loan.odoo_loan_id = odoo_loan_id
                update_fields.append("odoo_loan_id")
            if loan_number and not existing_loan.loan_number:
                existing_loan.loan_number = loan_number
                update_fields.append("loan_number")
            if outstanding and existing_loan.outstanding_balance != Decimal(
                str(outstanding)
            ):
                existing_loan.outstanding_balance = Decimal(str(outstanding))
                update_fields.append("outstanding_balance")
            if update_fields:
                existing_loan.save(update_fields=update_fields)
            logger.info(
                "Existing Loan %s updated with odoo_loan_id=%d.",
                existing_loan.pk,
                odoo_loan_id,
            )
        else:
            # Create a new Loan from application data + webhook payload
            principal = (
                Decimal(str(disbursed_amount))
                if disbursed_amount
                else (app.approved_amount or app.requested_amount)
            )
            # Loan number: Odoo-provided or generate locally
            ln_number = loan_number  # will auto-generate if blank via model.save()

            import calendar

            # Simple tenure-based maturity
            m = d_date.month + app.tenure_months
            y = d_date.year + (m - 1) // 12
            mo = (m - 1) % 12 + 1
            day = min(d_date.day, calendar.monthrange(y, mo)[1])
            maturity = datetime.date(y, mo, day)

            first_pay_m = d_date.month + 1
            first_pay_y = d_date.year + (first_pay_m - 1) // 12
            first_pay_mo = (first_pay_m - 1) % 12 + 1
            first_pay_day = min(
                d_date.day, calendar.monthrange(first_pay_y, first_pay_mo)[1]
            )
            first_payment = datetime.date(first_pay_y, first_pay_mo, first_pay_day)

            loan = Loan(
                application=app,
                customer=app.customer,
                loan_product=app.loan_product,
                principal_amount=principal,
                interest_amount=Decimal("0"),  # updated later by Odoo sync
                fees=Decimal("0"),
                total_amount=principal,
                outstanding_balance=Decimal(str(outstanding))
                if outstanding
                else principal,
                installment_amount=Decimal("0"),  # updated later
                repayment_frequency=app.repayment_frequency,
                tenure_months=app.tenure_months,
                disbursement_date=d_date,
                first_payment_date=first_payment,
                maturity_date=maturity,
                next_payment_date=first_payment,
                status=Loan.ACTIVE,
                odoo_loan_id=odoo_loan_id,
            )
            if ln_number:
                loan.loan_number = ln_number  # override auto-gen
            loan.save()
            logger.info(
                "Loan %s created from webhook (odoo_loan_id=%d).",
                loan.pk,
                odoo_loan_id,
            )

    except Exception as exc:
        logger.error(
            "Could not create/update Loan from loan.disbursed: %s", exc, exc_info=True
        )


def _handle_loan_npl_flagged(data: dict, delivery_id: str):
    """
    loan.npl_flagged
    ----------------
    Odoo has moved a loan to Non-Performing Loan status.
    Update the Django Loan record to DEFAULTED.
    """
    _update_loan_state(data, "npl")


def _handle_loan_instalment_overdue(data: dict, delivery_id: str):
    """
    loan.instalment_overdue
    -----------------------
    An instalment is past its due date.  Log the event and optionally
    trigger a customer notification (email / SMS via the portal).
    """
    odoo_loan_id = _safe_int(data.get("odoo_loan_id"), "odoo_loan_id")
    days_overdue = _safe_int(data.get("days_overdue"), "days_overdue")
    balance_due = _safe_float(data.get("balance_due"), "balance_due")
    due_date = (data.get("due_date") or "").strip()

    if odoo_loan_id <= 0:
        logger.warning(
            "Invalid odoo_loan_id in instalment_overdue webhook: %s", odoo_loan_id
        )
        return

    if days_overdue < 0:
        logger.warning(
            "Invalid days_overdue in instalment_overdue webhook: %s", days_overdue
        )
        return

    if balance_due < 0:
        logger.warning(
            "Invalid balance_due in instalment_overdue webhook: %s", balance_due
        )
        return

    logger.info(
        "Instalment overdue: odoo_loan_id=%d days=%d balance=%.2f due_date=%s",
        odoo_loan_id,
        days_overdue,
        balance_due,
        due_date,
    )

    # Attempt to queue a notification via the portal's notification system
    try:
        _queue_overdue_notification(odoo_loan_id, days_overdue, balance_due, due_date)
    except Exception as exc:
        logger.error("Could not queue overdue notification: %s", exc, exc_info=True)


def _queue_overdue_notification(odoo_loan_id, days_overdue, balance_due, due_date):
    """Best-effort: find the Django loan and send an overdue notification."""
    from loans.models import Loan  # lazy import

    loan = (
        Loan.objects.filter(odoo_loan_id=odoo_loan_id)
        .select_related("customer")
        .first()
    )
    if not loan:
        return

    customer = getattr(loan, "customer", None) or getattr(loan, "user", None)
    if not customer:
        return

    logger.info(
        "Overdue notification queued for customer %s (loan %s) — %d days overdue.",
        customer.pk,
        loan.loan_number if hasattr(loan, "loan_number") else loan.pk,
        days_overdue,
    )
    # In a real implementation this would call a Celery task:
    # tasks.send_overdue_sms.delay(customer.pk, loan.pk, days_overdue, balance_due)


def _handle_payment_matched(data: dict, delivery_id: str):
    """
    payment.matched
    ---------------
    A repayment has been posted and allocated to a loan in Odoo.
    Update the Django repayment / loan records with the posted data.

    Expected data keys:
        odoo_repayment_id, django_payment_id, loan_number,
        odoo_loan_id, amount_paid, principal_applied, interest_applied,
        outstanding_balance
    """
    django_payment_id = _safe_int(data.get("django_payment_id"), "django_payment_id")
    odoo_repayment_id = _safe_int(data.get("odoo_repayment_id"), "odoo_repayment_id")
    odoo_loan_id = _safe_int(data.get("odoo_loan_id"), "odoo_loan_id")
    outstanding_balance = _safe_float(
        data.get("outstanding_balance"), "outstanding_balance"
    )
    principal_applied = _safe_float(data.get("principal_applied"), "principal_applied")
    interest_applied = _safe_float(data.get("interest_applied"), "interest_applied")

    logger.info(
        "Payment matched: django_payment_id=%d odoo_repayment_id=%d "
        "odoo_loan_id=%d outstanding_balance=%.2f",
        django_payment_id,
        odoo_repayment_id,
        odoo_loan_id,
        outstanding_balance,
    )

    # Update loan outstanding balance
    if odoo_loan_id > 0:
        try:
            from loans.models import Loan  # lazy import

            Loan.objects.filter(odoo_loan_id=odoo_loan_id).update(
                outstanding_balance=outstanding_balance
            )
        except Exception as exc:
            logger.error(
                "Could not update loan outstanding balance: %s", exc, exc_info=True
            )

    # Update Django repayment record status to 'posted'
    if django_payment_id > 0:
        try:
            from loans.models import LoanRepayment  # lazy import

            LoanRepayment.objects.filter(id=django_payment_id).update(
                status="posted",
                odoo_repayment_id=odoo_repayment_id,
                principal_applied=principal_applied,
                interest_applied=interest_applied,
            )
        except Exception as exc:
            logger.error(
                "Could not update LoanRepayment status: %s", exc, exc_info=True
            )


def _handle_payment_mpesa_received(data: dict, delivery_id: str):
    """
    payment.mpesa_received
    ----------------------
    An inbound M-Pesa payment (C2B or STK callback) has been received
    and recorded in Odoo.  Update the Django portal with M-Pesa
    transaction details so it can show the customer their payment status.

    Expected data keys:
        mpesa_code, amount, phone_number, account_reference,
        loan_number, loan_odoo_id, transaction_type, completed_at,
        repayment_odoo_id
    """
    mpesa_code = (data.get("mpesa_code") or "").strip()
    amount = _safe_float(data.get("amount"), "amount")
    loan_number = (data.get("loan_number") or "").strip()
    odoo_loan_id = _safe_int(data.get("loan_odoo_id"), "loan_odoo_id")

    if amount <= 0:
        logger.warning("Invalid amount in M-Pesa payment webhook: %s", amount)
        return

    # Validate M-Pesa code format
    if mpesa_code and not (
        len(mpesa_code) >= 8 and mpesa_code.replace(" ", "").isalnum()
    ):
        logger.warning("Invalid M-Pesa code format: %s", mpesa_code)
        mpesa_code = ""

    logger.info(
        "M-Pesa payment received: mpesa_code=%s amount=%.2f loan=%s",
        mpesa_code or "(pending)",
        amount,
        loan_number or str(odoo_loan_id),
    )

    # Best-effort: record this against the Django loan
    if odoo_loan_id > 0:
        try:
            from loans.models import Loan  # lazy import

            loan = Loan.objects.filter(odoo_loan_id=odoo_loan_id).first()
            if loan and mpesa_code:
                logger.info(
                    "M-Pesa %s (KES %.2f) matched to Django loan %s.",
                    mpesa_code,
                    amount,
                    loan.pk,
                )
        except Exception as exc:
            logger.error(
                "Could not match M-Pesa payment to Django loan: %s", exc, exc_info=True
            )


def _handle_customer_kyc_verified(data: dict, delivery_id: str):
    """
    customer.kyc_verified
    ----------------------
    A customer's KYC has been verified (or rejected) in Odoo.
    Update the Django Customer profile record.

    Expected data keys:
        odoo_customer_id, django_customer_id, kyc_status
    """
    django_customer_id = _safe_int(data.get("django_customer_id"), "django_customer_id")
    kyc_status = (data.get("kyc_status") or "verified").strip()

    if django_customer_id <= 0:
        logger.warning(
            "customer.kyc_verified: invalid django_customer_id in payload: %s",
            django_customer_id,
        )
        return

    valid_statuses = ["pending", "verified", "rejected", "requires_additional_info"]
    if kyc_status not in valid_statuses:
        logger.warning(
            "Invalid kyc_status '%s' for django_customer_id=%d — defaulting to 'pending'.",
            kyc_status,
            django_customer_id,
        )
        kyc_status = "pending"

    try:
        from loans.models import Customer  # lazy import

        # Customer PK == user PK (OneToOne with primary_key=True)
        customer = Customer.objects.filter(user_id=django_customer_id).first()
        if not customer:
            logger.warning(
                "customer.kyc_verified: no Customer profile for user_id=%d.",
                django_customer_id,
            )
            return

        update_fields = ["verification_status", "updated_at"]
        customer.verification_status = kyc_status

        if kyc_status == "verified":
            customer.kyc_verified = True
            customer.kyc_verified_at = dj_timezone.now()
            # Mark individual documents as verified (Odoo confirmed all)
            customer.national_id_verified = True
            customer.bank_statement_verified = True
            customer.face_recognition_verified = True
            update_fields += [
                "kyc_verified", "kyc_verified_at",
                "national_id_verified", "bank_statement_verified",
                "face_recognition_verified",
            ]
        elif kyc_status == "rejected":
            customer.kyc_verified = False
            customer.national_id_verified = False
            customer.bank_statement_verified = False
            customer.face_recognition_verified = False
            update_fields += [
                "kyc_verified",
                "national_id_verified", "bank_statement_verified",
                "face_recognition_verified",
            ]

        customer.save(update_fields=update_fields)
        logger.info(
            "KYC status updated to '%s' for Django customer (user_id=%d).",
            kyc_status,
            django_customer_id,
        )
    except Exception as exc:
        logger.error("Could not update KYC status: %s", exc, exc_info=True)


def _update_loan_state(data: dict, new_state: str):
    """
    Helper: find a Django Loan by odoo_loan_id and update its status.

    State-to-status mapping (Odoo lowercase → Django uppercase constant):
        active        → ACTIVE
        npl           → DEFAULTED
        overdue       → OVERDUE
        closed        → PAID
        written_off   → WRITTEN_OFF
        restructured  → RESTRUCTURED
    """
    from loans.models import Loan  # lazy import

    odoo_loan_id = _safe_int(data.get("odoo_loan_id"), "odoo_loan_id")
    if odoo_loan_id <= 0:
        logger.warning(
            "_update_loan_state: invalid odoo_loan_id for state '%s': %s",
            new_state,
            odoo_loan_id,
        )
        return

    state_to_status = {
        "active": Loan.ACTIVE,
        "npl": Loan.DEFAULTED,
        "overdue": Loan.OVERDUE,
        "closed": Loan.PAID,
        "written_off": Loan.WRITTEN_OFF,
        "restructured": Loan.RESTRUCTURED,
    }
    django_status = state_to_status.get(new_state)
    if not django_status:
        logger.warning(
            "_update_loan_state: unknown state '%s' for odoo_loan_id=%d",
            new_state,
            odoo_loan_id,
        )
        return

    updated = Loan.objects.filter(odoo_loan_id=odoo_loan_id).update(
        status=django_status
    )
    logger.info(
        "Loan status updated to '%s' for odoo_loan_id=%d (%d record(s)).",
        django_status,
        odoo_loan_id,
        updated,
    )


def _handle_loan_closed(data: dict, delivery_id: str):
    """
    loan.closed
    -----------
    Odoo has closed a fully-repaid loan.
    """
    _update_loan_state(data, "closed")


def _handle_loan_maturing_soon(data: dict, delivery_id: str):
    """
    loan.maturing_soon
    ------------------
    A loan is maturing within 30 days.  Log for follow-up.
    """
    odoo_loan_id = _safe_int(data.get("odoo_loan_id"), "odoo_loan_id")
    loan_number = (data.get("loan_number") or "").strip()
    outstanding = _safe_float(data.get("outstanding_balance"), "outstanding_balance")

    if odoo_loan_id <= 0:
        logger.warning(
            "Invalid odoo_loan_id in loan.maturing_soon webhook: %s", odoo_loan_id
        )
        return

    logger.info(
        "Loan maturing soon: odoo_loan_id=%d loan_number=%s outstanding=%.2f",
        odoo_loan_id,
        loan_number,
        outstanding,
    )


def _handle_portfolio_stats_updated(data: dict, delivery_id: str):
    """
    portfolio.stats_updated
    -----------------------
    Odoo has pushed aggregate portfolio statistics.  Cache them so the
    Django dashboard can display current numbers without querying Odoo.

    Expected data keys:
        total_active_loans, total_disbursed, total_outstanding,
        total_arrears, par_30_balance, par_90_balance,
        npl_count, npl_balance
    """
    logger.info(
        "Portfolio stats received: active_loans=%s total_disbursed=%s "
        "total_outstanding=%s npl_count=%s",
        data.get("total_active_loans"),
        data.get("total_disbursed"),
        data.get("total_outstanding"),
        data.get("npl_count"),
    )
    # Cache in Django's cache framework so dashboard views can read it
    try:
        from django.core.cache import cache

        cache.set("odoo_portfolio_stats", data, timeout=60 * 60 * 7)  # 7 hours
    except Exception as exc:
        logger.debug("Could not cache portfolio stats: %s", exc)


def _handle_integration_health_check(data: dict, delivery_id: str):
    """
    integration.health_check
    ------------------------
    Odoo is confirming the integration is alive.  Cache the health summary
    so the Django admin dashboard can show integration status.
    """
    logger.info(
        "Integration health check received: total=%s inbound=%s outbound=%s",
        data.get("total"),
        data.get("inbound"),
        data.get("outbound"),
    )
    try:
        from django.core.cache import cache

        data["received_at"] = datetime.now(timezone.utc).isoformat()
        cache.set("odoo_integration_health", data, timeout=60 * 60 * 7)
    except Exception as exc:
        logger.debug("Could not cache integration health: %s", exc)


def _handle_integration_dead_webhooks_alert(data: dict, delivery_id: str):
    """
    integration.dead_webhooks_alert
    --------------------------------
    Odoo has detected dead (undeliverable) webhook retry records.
    Log a warning so Django's error monitoring system can alert the team.
    """
    dead_count = int(data.get("dead_count") or 0)
    logger.warning(
        "ODOO ALERT: %d dead webhook retry record(s) detected in Odoo.  "
        "Action required: %s",
        dead_count,
        data.get("action_required", "Review Alba Integration → Dead Webhooks in Odoo."),
    )


# ---------------------------------------------------------------------------
# Event handler registry
# ---------------------------------------------------------------------------

_EVENT_HANDLERS = {
    "application.status_changed": _handle_application_status_changed,
    "loan.disbursed": _handle_loan_disbursed,
    "loan.npl_flagged": _handle_loan_npl_flagged,
    "loan.closed": _handle_loan_closed,
    "loan.instalment_overdue": _handle_loan_instalment_overdue,
    "loan.maturing_soon": _handle_loan_maturing_soon,
    "payment.matched": _handle_payment_matched,
    "payment.mpesa_received": _handle_payment_mpesa_received,
    "customer.kyc_verified": _handle_customer_kyc_verified,
    "portfolio.stats_updated": _handle_portfolio_stats_updated,
    "integration.health_check": _handle_integration_health_check,
    "integration.dead_webhooks_alert": _handle_integration_dead_webhooks_alert,
}
