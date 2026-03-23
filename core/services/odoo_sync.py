# -*- coding: utf-8 -*-
"""
core.services.odoo_sync
========================
Bidirectional synchronisation service between the Django portal and the
Odoo backend via the Alba REST API.

All outbound calls (Django → Odoo) go through OdooSyncService.  The
methods map 1-to-1 with the REST endpoints exposed by alba_integration:

  POST  /alba/api/v1/customers
  POST  /alba/api/v1/customers/<id>/kyc
  POST  /alba/api/v1/applications
  PATCH /alba/api/v1/applications/<id>/status
  POST  /alba/api/v1/payments
  GET   /alba/api/v1/loan-products
  GET   /alba/api/v1/health

Configuration (Django settings / .env)
---------------------------------------
  ODOO_URL               Base URL of the Odoo instance, e.g.
                         https://odoo.albacapital.co.ke
  ODOO_API_KEY           Value for the X-Alba-API-Key header.
  ODOO_WEBHOOK_SECRET    Shared secret for verifying inbound webhooks
                         (used by the webhook receiver, not here).
  ODOO_TIMEOUT           HTTP timeout in seconds (default: 30).
  ODOO_MAX_RETRIES       Max retry attempts on transient errors (default: 3).
  ODOO_RETRY_BACKOFF     Base back-off in seconds between retries (default: 2).

Error handling
--------------
  OdooSyncError          Base exception raised on unrecoverable API errors.
  OdooAuthError          Authentication failure (HTTP 403).
  OdooNotFoundError      Resource not found (HTTP 404).
  OdooValidationError    Payload rejected by Odoo (HTTP 400 / 422).
  OdooServerError        Odoo-side server error (HTTP 5xx).
  OdooTimeoutError       Request timed out.
  OdooConnectionError    Could not reach the Odoo instance.

All exceptions carry a ``status_code`` attribute (int) and a ``detail``
attribute (str) with the parsed error message from the Odoo response body.

Thread safety
-------------
OdooSyncService is stateless — a new requests.Session is created per
instance.  It is safe to use from multiple Django views / celery workers
simultaneously.  For high-throughput deployments consider instantiating
one service instance per thread and reusing the session.
"""

import json
import logging
import time
from typing import Any

import requests
from django.conf import settings

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Custom exceptions
# ---------------------------------------------------------------------------


class OdooSyncError(Exception):
    """Base exception for all Odoo sync failures."""

    def __init__(self, message: str, status_code: int = 0, detail: str = ""):
        super().__init__(message)
        self.status_code = status_code
        self.detail = detail or message

    def __str__(self):
        if self.status_code:
            return f"[HTTP {self.status_code}] {self.detail}"
        return self.detail


class OdooAuthError(OdooSyncError):
    """Raised when the API key is missing, invalid, or inactive."""

    pass


class OdooNotFoundError(OdooSyncError):
    """Raised when the requested Odoo resource does not exist."""

    pass


class OdooValidationError(OdooSyncError):
    """Raised when Odoo rejects the payload due to validation errors."""

    pass


class OdooServerError(OdooSyncError):
    """Raised on Odoo-side 5xx errors."""

    pass


class OdooTimeoutError(OdooSyncError):
    """Raised when the HTTP request times out."""

    pass


class OdooConnectionError(OdooSyncError):
    """Raised when the Django portal cannot reach the Odoo instance."""

    pass


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------


class OdooSyncService:
    """
    Django-side REST client for the Alba Capital Odoo integration API.

    Instantiate once per request (or per Celery task) and call the
    appropriate method.  All methods are synchronous.

    Example::

        from core.services.odoo_sync import OdooSyncService, OdooSyncError

        service = OdooSyncService()
        try:
            result = service.create_or_update_customer(user)
            user.odoo_customer_id = result["odoo_customer_id"]
            user.save(update_fields=["odoo_customer_id"])
        except OdooSyncError as exc:
            logger.error("Odoo sync failed: %s", exc)
    """

    # Default configuration fallbacks
    _DEFAULT_TIMEOUT = 30
    _DEFAULT_MAX_RETRIES = 3
    _DEFAULT_RETRY_BACKOFF = 2  # seconds
    _RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}

    def __init__(self):
        self.base_url = (getattr(settings, "ODOO_URL", "") or "").rstrip("/")
        self.api_key = getattr(settings, "ODOO_API_KEY", "") or ""
        self.timeout = int(getattr(settings, "ODOO_TIMEOUT", self._DEFAULT_TIMEOUT))
        self.max_retries = int(
            getattr(settings, "ODOO_MAX_RETRIES", self._DEFAULT_MAX_RETRIES)
        )
        self.retry_backoff = float(
            getattr(settings, "ODOO_RETRY_BACKOFF", self._DEFAULT_RETRY_BACKOFF)
        )

        self._session = requests.Session()
        self._session.headers.update(
            {
                "X-Alba-API-Key": self.api_key,
                "Content-Type": "application/json",
                "Accept": "application/json",
                "User-Agent": "AlbaDjangoPortal/1.0",
            }
        )

    # =========================================================================
    # Public API methods
    # =========================================================================

    def health_check(self) -> dict:
        """
        Call the Odoo health endpoint to verify connectivity.

        Returns:
            dict: Response body, e.g. ``{"status": "ok", "version": "1.0"}``.

        Raises:
            OdooConnectionError: When the instance is unreachable.
        """
        return self._get("/alba/api/v1/health")

    def get_loan_products(self) -> list[dict]:
        """
        Fetch the list of active loan products from Odoo.

        Returns:
            list[dict]: Each dict contains at minimum:
                ``id``, ``name``, ``code``, ``category``,
                ``min_amount``, ``max_amount``, ``tenure_months_min``,
                ``tenure_months_max``, ``interest_rate``, ``interest_method``.

        Raises:
            OdooSyncError: On any API failure.
        """
        response = self._get("/alba/api/v1/loan-products")
        return response.get("products", [])

    def create_or_update_customer(self, user) -> dict:
        """
        Push a Django User record to Odoo as an ``alba.customer``.

        If the user already has an ``odoo_customer_id``, Odoo will look up
        the existing record and update it.  Otherwise a new customer is
        created and the response will contain the new Odoo ID.

        Args:
            user: Django User model instance.  Expected fields:
                  ``id``, ``first_name``, ``last_name``, ``email``,
                  ``phone``, optionally ``id_number``, ``id_type``,
                  ``date_of_birth``, ``address``, ``city``, ``country``.

        Returns:
            dict: Response body containing at minimum:
                ``odoo_customer_id`` (int),
                ``customer_number`` (str),
                ``status`` ("created" | "updated").

        Raises:
            OdooSyncError: On any API failure.
        """
        payload = _build_customer_payload(user)
        logger.info(
            "Syncing customer to Odoo: user_id=%s email=%s",
            user.pk,
            user.email,
        )
        result = self._post("/alba/api/v1/customers", payload)
        logger.info(
            "Customer synced: user_id=%s odoo_id=%s status=%s",
            user.pk,
            result.get("odoo_customer_id"),
            result.get("status"),
        )
        return result

    def update_kyc_status(
        self,
        odoo_customer_id: int,
        kyc_status: str,
        notes: str = "",
        document_type: str = "",
        document_number: str = "",
    ) -> dict:
        """
        Update the KYC status of a customer in Odoo.

        Args:
            odoo_customer_id:  Odoo ID of the ``alba.customer`` record.
            kyc_status:        One of: ``pending``, ``submitted``,
                               ``verified``, ``rejected``.
            notes:             Optional remarks for the KYC update.
            document_type:     Optional document type string.
            document_number:   Optional document number.

        Returns:
            dict: Response body.

        Raises:
            OdooNotFoundError: When the customer ID is not found in Odoo.
            OdooSyncError: On any other API failure.
        """
        payload: dict[str, Any] = {"kyc_status": kyc_status}
        if notes:
            payload["notes"] = notes
        if document_type:
            payload["document_type"] = document_type
        if document_number:
            payload["document_number"] = document_number

        logger.info(
            "Updating KYC: odoo_customer_id=%d kyc_status=%s",
            odoo_customer_id,
            kyc_status,
        )
        return self._post(
            f"/alba/api/v1/customers/{odoo_customer_id}/kyc",
            payload,
        )

    def create_loan_application(self, application) -> dict:
        """
        Submit a Django LoanApplication record to Odoo.

        Args:
            application: Django LoanApplication model instance.  Expected
                         fields: ``id``, ``customer`` (FK to User),
                         ``loan_product_odoo_id``, ``requested_amount``,
                         ``tenure_months``, ``repayment_frequency``,
                         ``purpose``, optionally ``approved_amount``,
                         ``odoo_customer_id``.

        Returns:
            dict: Response body containing at minimum:
                ``odoo_application_id`` (int),
                ``application_number`` (str),
                ``status`` ("created").

        Raises:
            OdooSyncError: On any API failure.
        """
        payload = _build_application_payload(application)
        logger.info(
            "Creating Odoo loan application: django_app_id=%s customer=%s",
            application.pk,
            application.customer_id if hasattr(application, "customer_id") else "—",
        )
        result = self._post("/alba/api/v1/applications", payload)
        logger.info(
            "Application created in Odoo: django_app_id=%s odoo_id=%s number=%s",
            application.pk,
            result.get("odoo_application_id"),
            result.get("application_number"),
        )
        return result

    def update_application_status(
        self,
        odoo_application_id: int,
        new_status: str,
        rejection_reason: str = "",
        cancellation_reason: str = "",
        approved_amount: float = 0.0,
        conditions: str = "",
    ) -> dict:
        """
        Transition a loan application to a new status stage in Odoo.

        Args:
            odoo_application_id: Odoo ID of the ``alba.loan.application``.
            new_status:          Target status string, one of:
                                 ``submitted``, ``under_review``,
                                 ``credit_analysis``, ``pending_approval``,
                                 ``approved``, ``employer_verification``,
                                 ``guarantor_confirmation``, ``disbursed``,
                                 ``rejected``, ``cancelled``.
            rejection_reason:    Required when new_status is ``rejected``.
            cancellation_reason: Required when new_status is ``cancelled``.
            approved_amount:     Set when new_status is ``approved``.
            conditions:          Conditions of approval text.

        Returns:
            dict: Response body.

        Raises:
            OdooNotFoundError:   When the application ID is not found.
            OdooValidationError: When the transition is not allowed.
            OdooSyncError:       On any other failure.
        """
        payload: dict[str, Any] = {"status": new_status}
        if rejection_reason:
            payload["rejection_reason"] = rejection_reason
        if cancellation_reason:
            payload["cancellation_reason"] = cancellation_reason
        if approved_amount:
            payload["approved_amount"] = approved_amount
        if conditions:
            payload["conditions_of_approval"] = conditions

        logger.info(
            "Updating application status: odoo_id=%d → %s",
            odoo_application_id,
            new_status,
        )
        return self._patch(
            f"/alba/api/v1/applications/{odoo_application_id}/status",
            payload,
        )

    def record_payment(
        self,
        odoo_loan_id: int,
        amount: float,
        payment_date: str,
        payment_method: str = "mpesa",
        mpesa_transaction_id: str = "",
        payment_reference: str = "",
        django_payment_id: int = 0,
        notes: str = "",
    ) -> dict:
        """
        Record a repayment in Odoo against a loan.

        Args:
            odoo_loan_id:          Odoo ID of the ``alba.loan`` record.
            amount:                Payment amount (KES).
            payment_date:          ISO-8601 date string, e.g. ``"2024-06-15"``.
            payment_method:        One of: ``mpesa``, ``bank_transfer``,
                                   ``cash``, ``cheque``, ``rtgs``.
            mpesa_transaction_id:  M-Pesa receipt code (for mpesa payments).
            payment_reference:     Generic payment reference / bank ref.
            django_payment_id:     Primary key of the Django repayment record.
            notes:                 Optional remarks.

        Returns:
            dict: Response body containing:
                ``odoo_repayment_id`` (int),
                ``status`` ("posted"),
                ``principal_applied`` (float),
                ``interest_applied`` (float).

        Raises:
            OdooNotFoundError:   When the loan ID is not found.
            OdooValidationError: When the payment cannot be posted.
            OdooSyncError:       On any other failure.
        """
        payload: dict[str, Any] = {
            "odoo_loan_id": odoo_loan_id,
            "amount": amount,
            "payment_date": payment_date,
            "payment_method": payment_method,
        }
        if mpesa_transaction_id:
            payload["mpesa_transaction_id"] = mpesa_transaction_id
        if payment_reference:
            payload["payment_reference"] = payment_reference
        if django_payment_id:
            payload["django_payment_id"] = django_payment_id
        if notes:
            payload["notes"] = notes

        logger.info(
            "Recording payment in Odoo: loan_id=%d amount=%.2f method=%s",
            odoo_loan_id,
            amount,
            payment_method,
        )
        result = self._post("/alba/api/v1/payments", payload)
        logger.info(
            "Payment recorded: odoo_repayment_id=%s principal=%.2f interest=%.2f",
            result.get("odoo_repayment_id"),
            result.get("principal_applied", 0),
            result.get("interest_applied", 0),
        )
        return result

    # =========================================================================
    # Convenience wrappers
    # =========================================================================

    def sync_user_to_odoo(self, user) -> tuple[int, str]:
        """
        High-level convenience: sync a user to Odoo and return
        ``(odoo_customer_id, status)``.  Persists the odoo_customer_id on
        the user model if the field exists.

        Args:
            user: Django User instance.

        Returns:
            tuple[int, str]: ``(odoo_customer_id, "created" | "updated")``
        """
        result = self.create_or_update_customer(user)
        odoo_id = int(result.get("odoo_customer_id", 0))
        status = result.get("status", "")

        # Persist back if the field exists on the model
        if odoo_id and hasattr(user, "odoo_customer_id"):
            user.odoo_customer_id = odoo_id
            user.save(update_fields=["odoo_customer_id"])

        return odoo_id, status

    def is_reachable(self) -> bool:
        """
        Return ``True`` when the Odoo instance is reachable and the API key
        is valid.  Swallows all exceptions — never raises.
        """
        if not self.base_url or not self.api_key:
            return False
        try:
            resp = self.health_check()
            return resp.get("status") == "ok"
        except Exception:
            return False

    # =========================================================================
    # Low-level HTTP helpers
    # =========================================================================

    def _get(self, path: str, params: dict = None) -> dict:
        """Execute a GET request and return the parsed JSON body."""
        return self._request("GET", path, params=params)

    def _post(self, path: str, payload: dict) -> dict:
        """Execute a POST request and return the parsed JSON body."""
        return self._request("POST", path, json_body=payload)

    def _patch(self, path: str, payload: dict) -> dict:
        """Execute a PATCH request and return the parsed JSON body."""
        return self._request("PATCH", path, json_body=payload)

    def _request(
        self,
        method: str,
        path: str,
        json_body: dict = None,
        params: dict = None,
    ) -> dict:
        """
        Execute an authenticated HTTP request against the Odoo API with
        automatic retries on transient failures.

        Args:
            method:    HTTP method string (GET, POST, PATCH, …).
            path:      URL path relative to ``self.base_url``.
            json_body: Optional request body (serialised to JSON).
            params:    Optional query parameters dict.

        Returns:
            dict: Parsed JSON response body.

        Raises:
            OdooAuthError:        HTTP 401 / 403.
            OdooNotFoundError:    HTTP 404.
            OdooValidationError:  HTTP 400 / 422.
            OdooServerError:      HTTP 5xx after all retries exhausted.
            OdooTimeoutError:     Timeout on all attempts.
            OdooConnectionError:  Connection error on all attempts.
            OdooSyncError:        Any other unexpected failure.
        """
        if not self.base_url:
            raise OdooConnectionError(
                "ODOO_URL is not configured.  Please set it in your .env file.",
                detail="ODOO_URL missing from Django settings.",
            )
        if not self.api_key:
            raise OdooAuthError(
                "ODOO_API_KEY is not configured.  Please set it in your .env file.",
                status_code=401,
                detail="ODOO_API_KEY missing from Django settings.",
            )

        url = self.base_url.rstrip("/") + path
        last_exc: Exception | None = None

        for attempt in range(1, self.max_retries + 1):
            try:
                logger.debug(
                    "Odoo API %s %s (attempt %d/%d)",
                    method,
                    path,
                    attempt,
                    self.max_retries,
                )
                start = time.monotonic()
                response = self._session.request(
                    method=method,
                    url=url,
                    json=json_body,
                    params=params,
                    timeout=self.timeout,
                )
                elapsed_ms = int((time.monotonic() - start) * 1000)
                logger.debug(
                    "Odoo API %s %s → HTTP %d (%dms)",
                    method,
                    path,
                    response.status_code,
                    elapsed_ms,
                )

                # ── Parse response ─────────────────────────────────────────
                return _parse_response(response, path)

            except requests.exceptions.Timeout as exc:
                last_exc = OdooTimeoutError(
                    f"Request to Odoo timed out after {self.timeout}s "
                    f"(attempt {attempt}/{self.max_retries}).",
                    detail=str(exc),
                )
                logger.warning(
                    "Odoo API timeout on %s %s (attempt %d): %s",
                    method,
                    path,
                    attempt,
                    exc,
                )

            except requests.exceptions.ConnectionError as exc:
                last_exc = OdooConnectionError(
                    f"Cannot connect to Odoo at {self.base_url} "
                    f"(attempt {attempt}/{self.max_retries}).",
                    detail=str(exc),
                )
                logger.warning(
                    "Odoo API connection error on %s %s (attempt %d): %s",
                    method,
                    path,
                    attempt,
                    exc,
                )

            except (OdooAuthError, OdooNotFoundError, OdooValidationError):
                # Non-retryable — re-raise immediately
                raise

            except OdooServerError as exc:
                last_exc = exc
                logger.warning(
                    "Odoo API server error on %s %s (attempt %d): %s",
                    method,
                    path,
                    attempt,
                    exc,
                )

            except OdooSyncError:
                raise

            except Exception as exc:
                raise OdooSyncError(
                    f"Unexpected error calling Odoo API: {exc}",
                    detail=str(exc),
                ) from exc

            # Back off before retrying
            if attempt < self.max_retries:
                backoff = self.retry_backoff * (2 ** (attempt - 1))
                logger.debug("Retrying in %.1fs…", backoff)
                time.sleep(backoff)

        # All retries exhausted
        raise last_exc or OdooSyncError(
            f"All {self.max_retries} attempts to {method} {path} failed."
        )


# ---------------------------------------------------------------------------
# Response parser
# ---------------------------------------------------------------------------


def _parse_response(response: requests.Response, path: str) -> dict:
    """
    Parse an HTTP response from the Odoo API.

    Attempts to decode the body as JSON.  Raises the appropriate
    OdooSyncError subclass based on the HTTP status code.

    Args:
        response: The requests.Response object.
        path:     URL path (used in error messages).

    Returns:
        dict: Parsed JSON body on success (2xx).

    Raises:
        OdooAuthError:        403.
        OdooNotFoundError:    404.
        OdooValidationError:  400 / 422.
        OdooServerError:      5xx.
        OdooSyncError:        Other non-2xx.
    """
    # Try to extract a detail message from the body regardless of status
    detail = ""
    body: dict = {}
    try:
        body = response.json()
        detail = body.get("error") or body.get("detail") or body.get("message") or ""
        if isinstance(detail, dict):
            detail = json.dumps(detail)
        detail = str(detail)
    except (ValueError, TypeError):
        detail = response.text[:500]

    status = response.status_code

    if 200 <= status < 300:
        return body

    if status == 400:
        raise OdooValidationError(
            f"Odoo rejected the request to {path}: {detail}",
            status_code=status,
            detail=detail,
        )
    if status in (401, 403):
        raise OdooAuthError(
            f"Odoo authentication failed for {path}: {detail}",
            status_code=status,
            detail=detail or "Invalid or inactive API key.",
        )
    if status == 404:
        raise OdooNotFoundError(
            f"Odoo resource not found at {path}: {detail}",
            status_code=status,
            detail=detail or f"Resource not found: {path}",
        )
    if status == 422:
        raise OdooValidationError(
            f"Odoo validation error for {path}: {detail}",
            status_code=status,
            detail=detail,
        )
    if status == 429:
        raise OdooServerError(
            f"Odoo rate limit exceeded for {path}.",
            status_code=status,
            detail="Too many requests — please retry after a short delay.",
        )
    if 500 <= status < 600:
        raise OdooServerError(
            f"Odoo server error (HTTP {status}) for {path}: {detail}",
            status_code=status,
            detail=detail or f"Server error HTTP {status}.",
        )

    raise OdooSyncError(
        f"Unexpected HTTP {status} from Odoo for {path}: {detail}",
        status_code=status,
        detail=detail,
    )


# ---------------------------------------------------------------------------
# Payload builders
# ---------------------------------------------------------------------------


def _build_customer_payload(user) -> dict:
    """
    Build the JSON payload for POST /alba/api/v1/customers from a Django
    User instance.

    Maps Django User fields → Odoo customer fields.  Falls back gracefully
    when optional fields are absent on the User model.
    """
    payload: dict[str, Any] = {
        "django_customer_id": user.pk,
        "email": user.email or "",
        "first_name": getattr(user, "first_name", "") or "",
        "last_name": getattr(user, "last_name", "") or "",
        "phone": getattr(user, "phone", "") or "",
    }

    # Optional KYC / identity fields
    for field in (
        "id_number",
        "id_type",
        "nationality",
        "gender",
        "date_of_birth",
        "address",
        "city",
        "country",
        "employer_name",
        "employer_address",
        "monthly_income",
        "kyc_status",
    ):
        value = getattr(user, field, None)
        if value is not None:
            # Convert date objects to ISO strings
            if hasattr(value, "isoformat"):
                payload[field] = value.isoformat()
            else:
                payload[field] = value

    # If the user already has an Odoo customer ID include it so Odoo
    # can find and update the existing record instead of creating a duplicate.
    odoo_id = getattr(user, "odoo_customer_id", None)
    if odoo_id:
        payload["odoo_customer_id"] = odoo_id

    return payload


def _build_application_payload(application) -> dict:
    """
    Build the JSON payload for POST /alba/api/v1/applications from a
    Django LoanApplication instance.
    """
    # Resolve customer Odoo ID
    customer = getattr(application, "customer", None) or getattr(
        application, "user", None
    )
    odoo_customer_id = 0
    if customer:
        odoo_customer_id = int(getattr(customer, "odoo_customer_id", 0) or 0)

    payload: dict[str, Any] = {
        "django_application_id": application.pk,
        "odoo_customer_id": odoo_customer_id,
        "odoo_loan_product_id": int(
            getattr(application, "loan_product_odoo_id", 0)
            or getattr(application, "odoo_product_id", 0)
            or 0
        ),
        "requested_amount": float(getattr(application, "requested_amount", 0) or 0),
        "tenure_months": int(getattr(application, "tenure_months", 0) or 0),
        "repayment_frequency": getattr(application, "repayment_frequency", "monthly")
        or "monthly",
        "purpose": getattr(application, "purpose", "") or "",
    }

    # Optional fields
    for field in ("approved_amount", "conditions_of_approval", "internal_notes"):
        value = getattr(application, field, None)
        if value is not None:
            payload[field] = value

    return payload
