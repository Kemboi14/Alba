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
  POST  /alba/api/v1/applications/<id>/submit
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
from datetime import date
from typing import Any

import requests
from django.conf import settings
from django.db import models

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
        # Try to get configuration from database first (admin panel config)
        # Fall back to environment variables if database config is not available
        try:
            from core.models import OdooConfig
            
            db_config = OdooConfig.get_active()
            if db_config and db_config.is_active:
                logger.info("Using Odoo configuration from database (admin panel)")
                self.base_url = (db_config.url or "").rstrip("/")
                self.api_key = db_config.api_key or ""
                self.db_name = (db_config.database or "").strip()
                self.webhook_secret = db_config.webhook_secret or ""
                self.webhook_url = db_config.webhook_url or ""
            else:
                logger.info("No active database config, falling back to environment variables")
                self.base_url = (getattr(settings, "ODOO_URL", "") or "").rstrip("/")
                self.api_key = getattr(settings, "ODOO_API_KEY", "") or ""
                self.db_name = (getattr(settings, "ODOO_DB", "") or "").strip()
                self.webhook_secret = getattr(settings, "ODOO_WEBHOOK_SECRET", "") or ""
                self.webhook_url = getattr(settings, "WEBHOOK_URL", "") or ""
        except Exception as exc:
            logger.warning("Failed to load database config, using environment variables: %s", exc)
            self.base_url = (getattr(settings, "ODOO_URL", "") or "").rstrip("/")
            self.api_key = getattr(settings, "ODOO_API_KEY", "") or ""
            self.db_name = (getattr(settings, "ODOO_DB", "") or "").strip()
            self.webhook_secret = getattr(settings, "ODOO_WEBHOOK_SECRET", "") or ""
            self.webhook_url = getattr(settings, "WEBHOOK_URL", "") or ""

        self.timeout = int(getattr(settings, "ODOO_TIMEOUT", self._DEFAULT_TIMEOUT))
        self.max_retries = int(
            getattr(settings, "ODOO_MAX_RETRIES", self._DEFAULT_MAX_RETRIES)
        )
        self.retry_backoff = float(
            getattr(settings, "ODOO_RETRY_BACKOFF", self._DEFAULT_RETRY_BACKOFF)
        )

        self._session = requests.Session()
        headers = {
            "X-Alba-API-Key": self.api_key,
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "AlbaDjangoPortal/1.0",
        }
        if self.db_name:
            headers["X-Odoo-Database"] = self.db_name
        self._session.headers.update(headers)

    # =========================================================================
    # Public API methods
    # =========================================================================

    def is_configured(self) -> bool:
        """
        Check if the service is properly configured with required credentials.
        
        Returns:
            bool: True if base_url and api_key are configured, False otherwise.
        """
        return bool(self.base_url and self.api_key)

    def health_check(self) -> dict:
        """
        Call the Odoo health endpoint to verify connectivity.

        Returns:
            dict: Response body, e.g. ``{"status": "ok", "version": "1.0"}``.

        Raises:
            OdooConnectionError: When the instance is unreachable.
        """
        return self._get("/alba/api/v1/health")

    def download_report(self, report_xml_id: str, res_id: int) -> str:
        """
        Fetch a PDF report from Odoo for a specific record.

        Args:
            report_xml_id: The full XML ID of the report, e.g. 'alba_loans.loan_application_report'
            res_id: The ID of the record to generate the report for.

        Returns:
            str: Base64 encoded PDF content.

        Raises:
            OdooSyncError: On any API failure.
        """
        endpoint = f"/alba/api/v1/reports/{report_xml_id}/{res_id}"
        result = self._get(endpoint)
        return result.get("pdf_content", "")

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

    def sync_loan_products_from_odoo(self) -> dict:
        """
        Sync all loan products from Odoo to Django and establish ID mappings.

        This method fetches all active loan products from Odoo and creates/updates
        corresponding LoanProduct records in Django, storing the Odoo product ID
        for future reference.

        Returns:
            dict: Summary of sync operation with keys:
                ``total_products`` (int),
                ``created`` (int),
                ``updated`` (int),
                ``failed`` (int).

        Raises:
            OdooSyncError: On any API failure.
        """
        from loans.models import LoanProduct

        odoo_products = self.get_loan_products()
        summary = {
            "total_products": len(odoo_products),
            "created": 0,
            "updated": 0,
            "failed": 0,
        }

        category_map = {
            "salary_advance": LoanProduct.SALARY_ADVANCE,
            "business_loan": LoanProduct.BUSINESS_LOAN,
            "personal_loan": LoanProduct.PERSONAL_LOAN,
            "ipf_loan": LoanProduct.IPF_LOAN,
            "bid_bond": LoanProduct.BID_BOND,
            "performance_bond": LoanProduct.PERFORMANCE_BOND,
            "staff_loan": LoanProduct.STAFF_LOAN,
            "asset_financing": LoanProduct.ASSET_FINANCING,
        }
        interest_method_map = {
            "flat_rate": LoanProduct.FLAT_RATE,
            "reducing_balance": LoanProduct.REDUCING_BALANCE,
        }
        frequency_map = {
            "weekly": LoanProduct.WEEKLY,
            "fortnightly": LoanProduct.FORTNIGHTLY,
            "monthly": LoanProduct.MONTHLY,
        }

        for product_data in odoo_products:
            try:
                odoo_id = product_data.get("id")
                code = product_data.get("code", "")
                name = product_data.get("name", "")

                if not odoo_id or not code:
                    logger.warning("Skipping product with missing id or code: %s", product_data)
                    summary["failed"] += 1
                    continue

                # Investor loans are managed in Odoo only — never mirrored
                # into the Django client portal's LoanProduct table.
                if product_data.get("category") == "investor_loan":
                    logger.info("Skipping investor-only product: code=%s odoo_id=%s", code, odoo_id)
                    continue

                # Try to find existing product by Odoo ID or code
                existing = LoanProduct.objects.filter(
                    models.Q(odoo_product_id=odoo_id) | models.Q(code=code)
                ).first()

                if existing:
                    # Update existing product
                    existing.odoo_product_id = odoo_id
                    existing.name = name or existing.name
                    existing.code = code
                    raw_category = product_data.get("category")
                    if raw_category is not None:
                        existing.category = category_map.get(raw_category, existing.category)
                    existing.min_amount = product_data.get("min_amount", existing.min_amount)
                    existing.max_amount = product_data.get("max_amount", existing.max_amount)
                    existing.interest_rate = product_data.get("interest_rate", existing.interest_rate)
                    raw_interest_method = product_data.get("interest_method")
                    if raw_interest_method is not None:
                        existing.interest_method = interest_method_map.get(
                            raw_interest_method, existing.interest_method
                        )
                    existing.min_tenure_months = product_data.get("min_tenure_months", existing.min_tenure_months)
                    existing.max_tenure_months = product_data.get("max_tenure_months", existing.max_tenure_months)
                    raw_frequency = product_data.get("repayment_frequency")
                    if raw_frequency is not None:
                        existing.default_repayment_frequency = frequency_map.get(
                            raw_frequency, existing.default_repayment_frequency
                        )
                    existing.origination_fee_percentage = product_data.get("origination_fee_percentage", existing.origination_fee_percentage)
                    existing.save()
                    summary["updated"] += 1
                    logger.info("Updated loan product: code=%s odoo_id=%s", code, odoo_id)
                else:
                    # Create new product
                    category = category_map.get(product_data.get("category"), LoanProduct.BUSINESS_LOAN)
                    interest_method = interest_method_map.get(
                        product_data.get("interest_method"), LoanProduct.REDUCING_BALANCE
                    )
                    repayment_frequency = frequency_map.get(
                        product_data.get("repayment_frequency"), LoanProduct.MONTHLY
                    )

                    LoanProduct.objects.create(
                        name=name,
                        code=code,
                        category=category,
                        description=product_data.get("description", ""),
                        min_amount=product_data.get("min_amount", 0),
                        max_amount=product_data.get("max_amount", 0),
                        interest_rate=product_data.get("interest_rate", 0),
                        interest_method=interest_method,
                        min_tenure_months=product_data.get("min_tenure_months", 1),
                        max_tenure_months=product_data.get("max_tenure_months", 12),
                        default_repayment_frequency=repayment_frequency,
                        origination_fee_percentage=product_data.get("origination_fee_percentage", 0),
                        odoo_product_id=odoo_id,
                        is_active=True,
                    )
                    summary["created"] += 1
                    logger.info("Created loan product: code=%s odoo_id=%s", code, odoo_id)

            except Exception as exc:
                logger.error("Failed to sync loan product: %s error=%s", product_data, exc)
                summary["failed"] += 1

        logger.info("Loan product sync completed: %s", summary)
        return summary

    def sync_loan_product_to_odoo(self, loan_product) -> int:
        """
        Sync a single Django LoanProduct to Odoo.

        This method attempts to find a matching product in Odoo by code and
        returns the Odoo product ID. If no match is found, it logs an error
        since Odoo doesn't provide a product creation endpoint in the current API.

        Args:
            loan_product: Django LoanProduct model instance.

        Returns:
            int: Odoo product ID, or 0 if sync failed.

        Raises:
            OdooSyncError: On API failure.
        """
        products = self.get_loan_products()
        
        # Try to find matching product by code
        for product in products:
            if product.get("code") == loan_product.code:
                odoo_id = product.get("id")
                logger.info(
                    "Found matching loan product in Odoo: code=%s odoo_id=%s",
                    loan_product.code,
                    odoo_id,
                )
                return odoo_id
        
        # No matching product found
        logger.error(
            "No matching loan product found in Odoo: code=%s name=%s",
            loan_product.code,
            loan_product.name,
        )
        return 0

    def create_or_update_customer(self, user) -> dict:
        """
        Push a Django User record to Odoo as an ``alba.customer`` with idempotency guards.

        If the user already has an ``odoo_customer_id``, Odoo will look up
        the existing record and update it.  Otherwise a new customer is
        created and the response will contain the new Odoo ID.

        Enhanced with idempotency guards to prevent duplicate customer creation
        and ensure consistent behavior across retry scenarios.

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
        # Idempotency check: if user already has odoo_customer_id, verify it exists in Odoo
        from loans.models import Customer

        customer_exists_in_odoo = False
        try:
            customer = Customer.objects.get(user=user)
            if customer.odoo_customer_id:
                logger.info(
                    "Idempotency check: Customer already has odoo_customer_id: user_id=%s odoo_id=%s",
                    user.pk,
                    customer.odoo_customer_id
                )
                # Verify the customer still exists in Odoo by attempting to fetch KYC status
                try:
                    kyc_status = self.get_kyc_status(customer.odoo_customer_id)
                    logger.info(
                        "Idempotency check: Verified customer exists in Odoo: user_id=%s odoo_id=%s",
                        user.pk,
                        customer.odoo_customer_id
                    )
                    customer_exists_in_odoo = True
                except OdooNotFoundError:
                    # Customer doesn't exist in Odoo despite having ID, clear and proceed
                    logger.warning(
                        "Idempotency check: Customer odoo_customer_id %s not found in Odoo, clearing: user_id=%s",
                        customer.odoo_customer_id,
                        user.pk
                    )
                    customer.odoo_customer_id = None
                    customer.odoo_sync_status = "PENDING"
                    customer.save(update_fields=["odoo_customer_id", "odoo_sync_status"])
                except Exception as e:
                    # Other errors, proceed with sync attempt
                    logger.warning(
                        "Idempotency check: Error verifying customer in Odoo: user_id=%s error=%s",
                        user.pk,
                        e
                    )
        except Customer.DoesNotExist:
            # No customer record exists, will create one
            logger.info("Idempotency check: No Customer record exists for user_id=%s", user.pk)

        payload = _build_customer_payload(user)
        logger.info(
            "Syncing customer to Odoo: user_id=%s email=%s",
            user.pk,
            user.email,
        )

        if customer_exists_in_odoo:
            # Updating an existing record: no idempotency key needed since
            # this isn't a creation prone to duplication.
            result = self._post("/alba/api/v1/customers", payload)
        else:
            # Add idempotency key based on user ID and email
            idempotency_key = f"customer_{user.id}_{user.email}"
            result = self._post_with_idempotency(
                "/alba/api/v1/customers",
                payload,
                idempotency_key
            )

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

    def get_kyc_status(self, odoo_customer_id: int) -> dict:
        """
        Fetch the real-time KYC verification status from Odoo.

        Args:
            odoo_customer_id: Odoo ID of the ``alba.customer`` record.

        Returns:
            dict: Response body containing:
                ``odoo_customer_id`` (int),
                ``kyc_status`` (str) — pending / partial / complete / verified / rejected,
                ``kyc_verified_by`` (str),
                ``kyc_verified_date`` (str),
                ``kyc_notes`` (str).

        Raises:
            OdooNotFoundError: When the customer ID is not found in Odoo.
            OdooSyncError: On any other API failure.
        """
        logger.info("Fetching KYC status from Odoo: odoo_customer_id=%d", odoo_customer_id)
        return self._get(f"/alba/api/v1/customers/{odoo_customer_id}/kyc")

    def _post_with_idempotency(self, endpoint: str, payload: dict, idempotency_key: str) -> dict:
        """
        Perform POST request with idempotency key to prevent duplicate operations.
        
        This method adds an X-Idempotency-Key header to the request and handles
        idempotency conflicts gracefully.
        
        Args:
            endpoint: API endpoint path
            payload: Request payload
            idempotency_key: Unique key for this operation
            
        Returns:
            dict: Response body
            
        Raises:
            OdooSyncError: On API failure
        """
        headers = self._session.headers.copy()
        headers["X-Idempotency-Key"] = idempotency_key
        
        try:
            response = self._session.post(
                f"{self.base_url}{endpoint}",
                json=payload,
                headers=headers,
                timeout=self.timeout
            )
            
            # Handle idempotency conflict (HTTP 409)
            if response.status_code == 409:
                logger.info(
                    "Idempotency conflict detected for key=%s, fetching existing resource",
                    idempotency_key
                )
                # Try to extract the existing resource from the response
                try:
                    error_data = response.json()
                    if "existing_id" in error_data:
                        logger.info(
                            "Recovered from idempotency conflict: existing_id=%s",
                            error_data["existing_id"]
                        )
                        error_data["status"] = "exists"
                        if "/customers" in endpoint:
                            error_data["odoo_customer_id"] = error_data.get("existing_id")
                        elif "/applications" in endpoint:
                            error_data["odoo_application_id"] = error_data.get("existing_id")
                        return error_data
                except Exception:
                    pass
                
                # If we can't recover, raise the error
                raise OdooSyncError(
                    "Idempotency conflict - operation already performed",
                    detail=f"Key: {idempotency_key}",
                    status_code=409
                )
            
            return self._handle_response(response)
            
        except requests.exceptions.Timeout:
            raise OdooTimeoutError(
                f"Request to {endpoint} timed out after {self.timeout}s"
            )
        except requests.exceptions.ConnectionError as e:
            raise OdooConnectionError(f"Cannot reach Odoo instance: {e}")
        except requests.exceptions.HTTPError as e:
            raise OdooSyncError(f"HTTP error: {e}", status_code=e.response.status_code if e.response else 0)

    def create_loan_application(self, application) -> dict:
        """
        Submit a Django LoanApplication record to Odoo with automatic prerequisite sync and idempotency.

        This method now automatically ensures that:
        1. The customer is synced to Odoo (with retry logic)
        2. The loan product is synced to Odoo (with retry logic)
        3. The application payload includes valid Odoo IDs
        4. Idempotency guards prevent duplicate applications

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
        # Idempotency check: if application already has odoo_application_id, verify it exists
        if application.odoo_application_id:
            logger.info(
                "Idempotency check: Application already has odoo_application_id: django_id=%s odoo_id=%s",
                application.pk,
                application.odoo_application_id
            )
            # Verify the application still exists in Odoo by checking the status
            try:
                # We can't directly check application status without an endpoint, 
                # but we can return the existing ID
                logger.info(
                    "Idempotency check: Returning existing odoo_application_id: django_id=%s odoo_id=%s",
                    application.pk,
                    application.odoo_application_id
                )
                return {
                    "odoo_application_id": application.odoo_application_id,
                    "application_number": application.application_number,
                    "status": "exists"
                }
            except Exception as e:
                logger.warning(
                    "Idempotency check: Error verifying application in Odoo: django_id=%s error=%s",
                    application.pk,
                    e
                )
        # Step 1: Ensure customer is synced to Odoo
        customer = getattr(application, "customer", None)
        if customer:
            # Check if service is configured before attempting sync
            if not self.is_configured():
                raise OdooSyncError(
                    "Odoo integration not configured. Please contact administrator.",
                    detail="API credentials are not configured in the admin panel."
                )
            
            odoo_customer_id = getattr(customer, "odoo_customer_id", None)
            if not odoo_customer_id:
                logger.info(
                    "Customer not synced to Odoo yet, syncing now: customer_id=%s",
                    customer.pk,
                )
                try:
                    result = self.create_or_update_customer(customer.user)
                    odoo_id = result.get("odoo_customer_id")
                    status = result.get("status", "unknown")
                    if odoo_id:
                        customer.odoo_customer_id = odoo_id
                        customer.save(update_fields=["odoo_customer_id"])
                        logger.info(
                            "Customer synced successfully: django_id=%s odoo_id=%s status=%s",
                            customer.pk,
                            odoo_id,
                            status,
                        )
                    else:
                        raise OdooSyncError(
                            "Failed to sync customer to Odoo - no ID returned",
                            detail="Customer sync returned zero ID",
                        )
                except OdooSyncError:
                    # Already a specific, correctly-typed sync error (auth,
                    # validation, connection, timeout, ...) carrying its real
                    # cause in .detail — propagate unchanged. Re-wrapping it
                    # here would both erase the actual cause (replaced by a
                    # generic message) and erase the type, which breaks the
                    # transient-vs-permanent classification callers rely on
                    # (e.g. a network timeout would look like a validation
                    # failure and stop being auto-retried).
                    raise
                except Exception as exc:
                    logger.error(
                        "Failed to sync customer to Odoo: customer_id=%s error=%s",
                        customer.pk,
                        exc,
                    )
                    raise OdooSyncError(
                        f"Failed to sync customer to Odoo: {exc}",
                        detail=f"Customer sync is required before application creation: {exc}",
                    ) from exc

        # Step 2: Ensure loan product is synced to Odoo
        loan_product = getattr(application, "loan_product", None)
        if loan_product:
            odoo_product_id = getattr(loan_product, "odoo_product_id", None)
            if not odoo_product_id:
                logger.info(
                    "Loan product not synced to Odoo yet, syncing now: product_id=%s",
                    loan_product.pk,
                )
                try:
                    odoo_id = self.sync_loan_product_to_odoo(loan_product)
                    if odoo_id:
                        loan_product.odoo_product_id = odoo_id
                        loan_product.save(update_fields=["odoo_product_id"])
                        logger.info(
                            "Loan product synced successfully: django_id=%s odoo_id=%s",
                            loan_product.pk,
                            odoo_id,
                        )
                    else:
                        raise OdooSyncError(
                            "Failed to sync loan product to Odoo - no ID returned",
                            detail="Product sync returned zero ID",
                        )
                except OdooSyncError:
                    # See comment in the customer-sync block above: preserve
                    # the original error type and detail instead of masking
                    # the real cause with a generic message.
                    raise
                except Exception as exc:
                    logger.error(
                        "Failed to sync loan product to Odoo: product_id=%s error=%s",
                        loan_product.pk,
                        exc,
                    )
                    raise OdooSyncError(
                        f"Failed to sync loan product to Odoo: {exc}",
                        detail=f"Product sync is required before application creation: {exc}",
                    ) from exc

        # Step 3: Build and send application payload with idempotency
        payload = _build_application_payload(application)
        logger.info(
            "Creating Odoo loan application: django_app_id=%s customer=%s",
            application.pk,
            application.customer_id if hasattr(application, "customer_id") else "—",
        )
        
        # Generate idempotency key based on application ID and customer ID.
        # Use .pk, not .id: loans.models.Customer sets its `user` FK as the
        # primary key, so it has no implicit `id` attribute at all.
        idempotency_key = f"application_{application.pk}_{customer.pk if customer else 'unknown'}"
        
        result = self._post_with_idempotency(
            "/alba/api/v1/applications",
            payload,
            idempotency_key
        )

        logger.info(
            "Application created in Odoo: django_app_id=%s odoo_id=%s number=%s",
            application.pk,
            result.get("odoo_application_id"),
            result.get("application_number"),
        )
        return result

    def submit_loan_application(self, odoo_application_id: int) -> dict:
        """
        Trigger the Odoo workflow transition from ``draft`` → ``submitted``
        by calling the dedicated submit endpoint.

        This must be called *after* :meth:`create_loan_application` has
        returned a valid ``odoo_application_id``.  Calling the submit
        endpoint causes Odoo to run ``action_submit()`` on the
        ``alba.loan.application`` record, which starts KYC verification,
        credit scoring, and the auto-decisioning pipeline.

        Args:
            odoo_application_id: Odoo database ID of the loan application.

        Returns:
            dict: Response body containing ``status``, ``previous_state``,
                  ``new_state``, and ``application_number``.

        Raises:
            OdooNotFoundError:   When the application ID does not exist.
            OdooValidationError: When the application is not in draft state.
            OdooSyncError:       On any other API failure.
        """
        logger.info(
            "Submitting loan application to Odoo workflow: odoo_id=%d",
            odoo_application_id,
        )
        return self._post(
            f"/alba/api/v1/applications/{odoo_application_id}/submit",
            {},
        )

    def sync_document(self, odoo_application_id: int, doc) -> dict:
        """
        Sync a Django LoanDocument to Odoo as an alba.loan.document record with retry logic.

        This method now includes retry logic and better error handling for failed syncs.

        Args:
            odoo_application_id: Odoo ID of the ``alba.loan.application``.
            doc: Django LoanDocument model instance with ``document_file``,
                 ``document_type``, and ``description`` fields.

        Returns:
            dict: Response body containing ``odoo_document_id`` and
                  ``status`` ("created").

        Raises:
            OdooSyncError: On any API failure after retries.
        """
        import base64 as _b64

        if not odoo_application_id:
            logger.error(
                "Cannot sync document: no odoo_application_id provided. doc_id=%s",
                doc.pk if hasattr(doc, 'pk') else 'unknown'
            )
            raise OdooSyncError(
                "Cannot sync document: no odoo_application_id",
                detail="Document sync requires a valid Odoo application ID",
            )

        # Read and encode the file
        doc.document_file.open("rb")
        try:
            file_bytes = doc.document_file.read()
        finally:
            doc.document_file.close()

        file_content_b64 = _b64.b64encode(file_bytes).decode("utf-8")
        file_name = doc.document_file.name.split("/")[-1]
        doc_type_display = dict(getattr(doc, "DOCUMENT_TYPE_CHOICES", [])).get(
            doc.document_type, doc.document_type
        )

        payload: dict = {
            "name": doc_type_display or file_name,
            "document_type": doc.document_type,
            "file_content": file_content_b64,
            "file_name": file_name,
            "description": getattr(doc, "description", "") or "",
        }

        logger.info(
            "Syncing document to Odoo: app_id=%d type=%s file=%s",
            odoo_application_id,
            doc.document_type,
            file_name,
        )
        try:
            result = self._post(
                f"/alba/api/v1/applications/{odoo_application_id}/documents",
                payload,
                retry=False,
            )
            logger.info(
                "Document synced to Odoo: odoo_doc_id=%s",
                result.get("odoo_document_id"),
            )
            return result
        except OdooSyncError as exc:
            logger.error(
                "Document sync failed: doc_id=%s error=%s",
                doc.pk if hasattr(doc, 'pk') else 'unknown',
                exc,
            )
            raise

    def sync_kyc_file(
        self,
        odoo_application_id: int,
        file_field,
        document_type: str,
        name: str,
    ) -> dict:
        """
        Sync a raw Django FileField/FieldFile (e.g. customer's national_id_file)
        to Odoo under a loan application with retry logic.

        Args:
            odoo_application_id: Odoo ID of the ``alba.loan.application``.
            file_field: Django FileField/FieldFile instance.
            document_type: The document type string (e.g., "national_id", "bank_statement", "other").
            name: The document display name.

        Returns:
            dict: Response body from Odoo, or empty dict if file_field is empty.
        """
        import base64 as _b64

        if not file_field:
            logger.debug("Skipping KYC file sync: no file provided for %s", name)
            return {}

        if not odoo_application_id:
            logger.error(
                "Cannot sync KYC file: no odoo_application_id provided. type=%s name=%s",
                document_type,
                name,
            )
            return {}

        file_field.open("rb")
        try:
            file_bytes = file_field.read()
        finally:
            file_field.close()

        file_content_b64 = _b64.b64encode(file_bytes).decode("utf-8")
        file_name = file_field.name.split("/")[-1]

        payload: dict = {
            "name": name,
            "document_type": document_type,
            "file_content": file_content_b64,
            "file_name": file_name,
            "description": f"Customer KYC - {name}",
        }

        logger.info(
            "Syncing KYC file to Odoo: app_id=%d type=%s file=%s",
            odoo_application_id,
            document_type,
            file_name,
        )
        try:
            result = self._post(
                f"/alba/api/v1/applications/{odoo_application_id}/documents",
                payload,
                retry=False,
            )
            logger.info(
                "KYC file synced to Odoo: odoo_doc_id=%s",
                result.get("odoo_document_id"),
            )
            return result
        except OdooSyncError as exc:
            logger.error(
                "KYC file sync failed: type=%s name=%s error=%s",
                document_type,
                name,
                exc,
            )
            # Return empty dict instead of raising to avoid blocking the main flow
            return {}

    def sync_guarantor(self, application, guarantor_verification) -> dict:
        """
        Create a guarantor assignment in Odoo from a Django GuarantorVerification.

        The guarantor confirmation SMS/email is NOT sent as a side effect —
        the assignment is created in Odoo's default ``pending`` status;
        sending the confirmation stays a manual Odoo back-office action.

        Args:
            application: Django LoanApplication instance. Must already have
                         a valid ``odoo_application_id``.
            guarantor_verification: Django GuarantorVerification instance.

        Returns:
            dict: Response body containing ``odoo_guarantor_id``,
                  ``odoo_loan_guarantor_id``, and ``status``.

        Raises:
            OdooSyncError: If the application has no odoo_application_id yet,
                           or on any API failure.
        """
        odoo_application_id = getattr(application, "odoo_application_id", None)
        if not odoo_application_id:
            raise OdooSyncError(
                "Cannot sync guarantor: application has no odoo_application_id",
                detail="The loan application must be synced to Odoo before its guarantors.",
            )

        payload = _build_guarantor_payload(guarantor_verification)
        logger.info(
            "Syncing guarantor to Odoo: django_guarantor_id=%s app_odoo_id=%d",
            guarantor_verification.pk,
            odoo_application_id,
        )
        return self._post(
            f"/alba/api/v1/applications/{odoo_application_id}/guarantors",
            payload,
            retry=False,
        )

    def get_guarantor_status(self, odoo_loan_guarantor_id: int) -> dict:
        """
        Poll the current status of a guarantor assignment from Odoo — a
        fallback for when a ``guarantor.status_changed`` webhook hasn't
        landed yet.

        Args:
            odoo_loan_guarantor_id: Odoo ID of the ``alba.loan.guarantor`` record.

        Returns:
            dict: Response body containing ``status``, ``confirmed_date``,
                  ``confirmed_method``, ``rejection_reason``.
        """
        logger.info(
            "Fetching guarantor status from Odoo: odoo_loan_guarantor_id=%d",
            odoo_loan_guarantor_id,
        )
        return self._get(f"/alba/api/v1/loan-guarantors/{odoo_loan_guarantor_id}/status")

    def sync_guarantor_document(
        self,
        odoo_loan_guarantor_id: int,
        file_field,
        document_type: str,
        name: str,
    ) -> dict:
        """
        Sync a guarantor's document (ID, payslip, etc.) to Odoo as an
        ``alba.guarantor.document`` record.

        Args:
            odoo_loan_guarantor_id: Odoo ID of the ``alba.loan.guarantor`` record.
            file_field: Django FileField/FieldFile instance.
            document_type: Document type string (id_front/id_back/photo/
                           payslip/bank_statement/employment_letter/
                           utility_bill/other).
            name: The document display name.

        Returns:
            dict: Response body containing ``odoo_guarantor_document_id``
                  and ``status``, or empty dict if file_field is empty.
        """
        import base64 as _b64

        if not file_field:
            logger.debug("Skipping guarantor document sync: no file provided for %s", name)
            return {}

        file_field.open("rb")
        try:
            file_bytes = file_field.read()
        finally:
            file_field.close()

        payload: dict = {
            "name": name,
            "document_type": document_type,
            "file_content": _b64.b64encode(file_bytes).decode("utf-8"),
            "file_name": file_field.name.split("/")[-1],
        }
        return self._post(
            f"/alba/api/v1/loan-guarantors/{odoo_loan_guarantor_id}/documents",
            payload,
            retry=False,
        )

    def sync_collateral(self, application, collateral) -> dict:
        """
        Create a collateral asset record in Odoo from a Django Collateral.

        This creates the asset-registry record only (``alba.collateral``) —
        it does not pledge it to a loan, since the pledge junction
        (``alba.loan.collateral``) requires a disbursed ``alba.loan``, which
        doesn't exist yet at application time. Pledging remains a manual
        Odoo back-office step at disbursement.

        Args:
            application: Django LoanApplication instance. Must already have
                         a valid ``odoo_application_id``.
            collateral: Django Collateral instance.

        Returns:
            dict: Response body containing ``odoo_collateral_id`` and ``status``.

        Raises:
            OdooSyncError: If the application has no odoo_application_id yet,
                           or on any API failure.
        """
        odoo_application_id = getattr(application, "odoo_application_id", None)
        if not odoo_application_id:
            raise OdooSyncError(
                "Cannot sync collateral: application has no odoo_application_id",
                detail="The loan application must be synced to Odoo before its collateral.",
            )

        payload = _build_collateral_payload(collateral)
        logger.info(
            "Syncing collateral to Odoo: django_collateral_id=%s app_odoo_id=%d",
            collateral.pk,
            odoo_application_id,
        )
        return self._post(
            f"/alba/api/v1/applications/{odoo_application_id}/collateral",
            payload,
            retry=False,
        )

    def sync_collateral_document(
        self,
        odoo_collateral_id: int,
        file_field,
        document_type: str,
        name: str,
    ) -> dict:
        """
        Sync a collateral document (title deed, insurance, valuation report)
        to Odoo as an ``alba.collateral.document`` record.

        Args:
            odoo_collateral_id: Odoo ID of the ``alba.collateral`` record.
            file_field: Django FileField/FieldFile instance.
            document_type: Document type string (title_deed/logbook/
                           valuation/insurance/photo/survey/id/
                           power_attorney/other).
            name: The document display name.

        Returns:
            dict: Response body containing ``odoo_collateral_document_id``
                  and ``status``, or empty dict if file_field is empty.
        """
        import base64 as _b64

        if not file_field:
            logger.debug("Skipping collateral document sync: no file provided for %s", name)
            return {}

        file_field.open("rb")
        try:
            file_bytes = file_field.read()
        finally:
            file_field.close()

        payload: dict = {
            "name": name,
            "document_type": document_type,
            "file_content": _b64.b64encode(file_bytes).decode("utf-8"),
            "file_name": file_field.name.split("/")[-1],
        }
        return self._post(
            f"/alba/api/v1/collateral/{odoo_collateral_id}/documents",
            payload,
            retry=False,
        )

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
        result = self._post("/alba/api/v1/payments", payload, retry=False)
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
        the user model if the field exists. Updates sync status tracking.

        Args:
            user: Django User instance.

        Returns:
            tuple[int, str]: ``(odoo_customer_id, "created" | "updated")``
        """
        from loans.models import Customer

        # Get customer profile if it exists
        customer = None
        try:
            customer = user.customer_profile
        except Exception:
            pass

        result = self.create_or_update_customer(user)
        odoo_id = int(result.get("odoo_customer_id", 0))
        status = result.get("status", "")

        # Persist back if the field exists on the model
        if odoo_id and hasattr(user, "odoo_customer_id"):
            user.odoo_customer_id = odoo_id
            user.save(update_fields=["odoo_customer_id"])

        # Update customer sync status if customer profile exists
        if customer:
            from django.utils import timezone
            customer.odoo_customer_id = odoo_id
            customer.odoo_sync_status = "SUCCESS"
            customer.odoo_sync_error = ""
            customer.odoo_sync_attempts += 1
            customer.odoo_last_sync_at = timezone.now()
            customer.save(
                update_fields=[
                    "odoo_customer_id",
                    "odoo_sync_status",
                    "odoo_sync_error",
                    "odoo_sync_attempts",
                    "odoo_last_sync_at",
                ]
            )

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

    def _post(self, path: str, payload: dict, retry: bool = True) -> dict:
        """Execute a POST request and return the parsed JSON body."""
        return self._request("POST", path, json_body=payload, retry=retry)

    def _handle_response(self, response) -> dict:
        """
        Handle HTTP response with proper error handling and parsing.
        
        This method is used by idempotency requests that need direct response handling.
        
        Args:
            response: requests.Response object
            
        Returns:
            dict: Parsed JSON response body
            
        Raises:
            OdooSyncError: On API failure
        """
        return _parse_response(response, "")

    def _patch(self, path: str, payload: dict) -> dict:
        """Execute a PATCH request and return the parsed JSON body."""
        return self._request("PATCH", path, json_body=payload)

    def _request(
        self,
        method: str,
        path: str,
        json_body: dict = None,
        params: dict = None,
        retry: bool = True,
    ) -> dict:
        """
        Execute an authenticated HTTP request against the Odoo API with
        automatic retries on transient failures.

        Args:
            method:    HTTP method string (GET, POST, PATCH, …).
            path:      URL path relative to ``self.base_url``.
            json_body: Optional request body (serialised to JSON).
            params:    Optional query parameters dict.
            retry:     Whether to auto-retry on timeout/connection/server
                       errors. Must be ``False`` for non-idempotent
                       record-creating calls, where a retry after a timeout
                       could double-post the record.

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
        max_attempts = self.max_retries if retry else 1

        for attempt in range(1, max_attempts + 1):
            try:
                logger.debug(
                    "Odoo API %s %s (attempt %d/%d)",
                    method,
                    path,
                    attempt,
                    max_attempts,
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
                    f"(attempt {attempt}/{max_attempts}).",
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
                    f"(attempt {attempt}/{max_attempts}).",
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
            if attempt < max_attempts:
                backoff = self.retry_backoff * (2 ** (attempt - 1))
                logger.debug("Retrying in %.1fs…", backoff)
                time.sleep(backoff)

        # All retries exhausted
        raise last_exc or OdooSyncError(
            f"All {max_attempts} attempts to {method} {path} failed."
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

# Django's Customer model stores choice fields as UPPER_SNAKE_CASE (e.g.
# "EMPLOYED"), while the corresponding Odoo alba.customer/res.partner
# Selection fields use lower_snake_case (e.g. "employed"). Sending the raw
# Django value makes Odoo reject the *entire* customer record with
# "Wrong value for alba.customer.<field>: '<value>'" the moment any one of
# these optional fields is populated — which is effectively guaranteed for
# any customer who has filled in their profile.
_ID_TYPE_MAP = {
    "NATIONAL": "national_id",
    "PASSPORT": "passport",
    "MILITARY": "alien_id",
    "OTHER": "alien_id",
}
_GENDER_MAP = {"MALE": "male", "FEMALE": "female", "OTHER": "other"}
_MARITAL_STATUS_MAP = {
    "SINGLE": "single",
    "MARRIED": "married",
    "DIVORCED": "divorced",
    "WIDOWED": "widowed",
}
_EMPLOYMENT_STATUS_MAP = {
    "EMPLOYED": "employed",
    "SELF_EMPLOYED": "self_employed",
    "BUSINESS_OWNER": "business_owner",
    "UNEMPLOYED": "unemployed",
    "RETIRED": "retired",
}
_BUSINESS_TYPE_MAP = {
    "SOLE_PROPRIETOR": "sole_proprietor",
    "PARTNERSHIP": "partnership",
    "LIMITED_COMPANY": "limited_company",
    "OTHER": "other",
}
_REFERRAL_SOURCE_MAP = {"AGENT": "agent", "STAFF": "staff", "DIRECTOR": "director"}
_KYC_STATUS_MAP = {
    "PENDING": "pending",
    "PARTIAL": "partial",
    "COMPLETE": "complete",
    "VERIFIED": "verified",
    "REJECTED": "rejected",
}
_RISK_RATING_MAP = {
    "LOW": "low",
    "MEDIUM": "medium",
    "HIGH": "high",
    "VERY_HIGH": "very_high",
}


def _map_choice(value, mapping: dict, field_name: str):
    """
    Translate a Django UPPER_SNAKE_CASE choice value to the lower_snake_case
    value Odoo's Selection field expects.

    Returns None (dropping the field from the payload) when the value can't
    be mapped, rather than forwarding a raw value that would make Odoo
    reject the whole customer record.
    """
    if value is None or value == "":
        return None
    key = str(value).strip().upper()
    mapped = mapping.get(key)
    if mapped is None:
        logger.warning(
            "_build_customer_payload: unmappable %s value %r — omitting from Odoo payload",
            field_name,
            value,
        )
    return mapped


def _build_customer_payload(user) -> dict:
    """
    Build the JSON payload for POST /alba/api/v1/customers from a Django
    User instance.

    Core identity fields come from the User model.  KYC/profile fields are
    read from the related Customer profile (``user.customer_profile``) when
    it exists.
    """
    payload: dict[str, Any] = {
        "django_customer_id": user.pk,
        "email": user.email or "",
        "first_name": getattr(user, "first_name", "") or "",
        "last_name": getattr(user, "last_name", "") or "",
        "phone": getattr(user, "phone", "") or "",
    }

    # Try to pull KYC data from the Customer profile (OneToOne reverse FK)
    profile = None
    try:
        profile = user.customer_profile  # raises RelatedObjectDoesNotExist if absent
    except Exception:
        pass

    if profile is not None:
        # Enhanced with Phase 1 Odoo Alignment fields
        profile_fields = {
            # Identity fields
            "id_number": getattr(profile, "id_number", None),
            "id_type": _map_choice(getattr(profile, "id_type", None), _ID_TYPE_MAP, "id_type"),
            "date_of_birth": getattr(profile, "date_of_birth", None),
            "gender": _map_choice(getattr(profile, "gender", None), _GENDER_MAP, "gender"),
            "marital_status": _map_choice(
                getattr(profile, "marital_status", None), _MARITAL_STATUS_MAP, "marital_status"
            ),
            "nationality": getattr(profile, "nationality", None),
            # Address
            "address": getattr(profile, "address", None),
            "city": getattr(profile, "city", None),
            "county": getattr(profile, "county", None),  # Legacy text field
            # Hierarchical FK fields are themselves named *_id (see loans.models.Customer),
            # so Django's raw-int accessor is the double-suffixed *_id_id attribute --
            # plain getattr(profile, "county_id") returns the related County instance,
            # which is not JSON serializable.
            "county_id": getattr(profile, "county_id_id", None),
            "sub_county_id": getattr(profile, "sub_county_id_id", None),
            "ward_id": getattr(profile, "ward_id_id", None),
            # Employment
            "employment_status": _map_choice(
                getattr(profile, "employment_status", None),
                _EMPLOYMENT_STATUS_MAP,
                "employment_status",
            ),
            "employer_name": getattr(profile, "employer_name", None),
            "employer_contact": getattr(profile, "employer_contact", None),
            "employer_email": getattr(profile, "employer_email", None),
            "job_title": getattr(profile, "job_title", None),
            "months_employed": getattr(profile, "months_employed", None),
            "other_income": getattr(profile, "other_income", None),
            "monthly_income": getattr(profile, "monthly_income", None),
            "employment_date": getattr(profile, "employment_date", None),
            # Business
            "business_name": getattr(profile, "business_name", None),
            "business_registration_number": getattr(profile, "business_registration_number", None),
            "business_location": getattr(profile, "business_location", None),
            "business_industry": getattr(profile, "business_industry", None),
            "business_type": _map_choice(
                getattr(profile, "business_type", None), _BUSINESS_TYPE_MAP, "business_type"
            ),
            "years_in_business": getattr(profile, "years_in_business", None),
            "monthly_business_turnover": getattr(profile, "monthly_business_turnover", None),
            "sector_id": getattr(profile, "sector_id", None),
            "subsector_id": getattr(profile, "subsector_id", None),
            "annual_turnover": getattr(profile, "annual_turnover", None),
            # Next of Kin
            "next_of_kin_name": getattr(profile, "next_of_kin_name", None),
            "next_of_kin_phone": getattr(profile, "next_of_kin_phone", None),
            "next_of_kin_relationship": getattr(profile, "next_of_kin_relationship", None),
            # Referral
            "referral_source": _map_choice(
                getattr(profile, "referral_source", None), _REFERRAL_SOURCE_MAP, "referral_source"
            ),
            "referral_name": getattr(profile, "referral_name", None),
            # Banking
            "bank_name": getattr(profile, "bank_name", None),
            "bank_account": getattr(profile, "bank_account", None),
            "mpesa_number": getattr(profile, "mpesa_number", None),
            # KYC
            "kyc_status": _map_choice(getattr(profile, "kyc_status", None), _KYC_STATUS_MAP, "kyc_status"),
            "kyc_verified": getattr(profile, "kyc_verified", None),
            "credit_score": getattr(profile, "credit_score", None),
            "risk_rating": _map_choice(
                getattr(profile, "risk_rating", None), _RISK_RATING_MAP, "risk_rating"
            ),
            # Status
            "notes": getattr(profile, "notes", None),
        }
        for field, value in profile_fields.items():
            if value is not None:
                if hasattr(value, "isoformat"):
                    payload[field] = value.isoformat()
                elif hasattr(value, "__class__") and value.__class__.__name__ == "Decimal":
                    payload[field] = float(value)
                else:
                    payload[field] = value

        # Odoo customer ID is stored on the Customer profile
        odoo_id = getattr(profile, "odoo_customer_id", None)
        if odoo_id:
            payload["odoo_customer_id"] = odoo_id
    else:
        # Fallback: check the user object itself (for custom user models)
        odoo_id = getattr(user, "odoo_customer_id", None)
        if odoo_id:
            payload["odoo_customer_id"] = odoo_id

    return payload


def _build_application_payload(application) -> dict:
    """
    Build the JSON payload for POST /alba/api/v1/applications from a
    Django LoanApplication instance.

    Field resolution priority:
    - Odoo IDs are pulled from related objects (customer.odoo_customer_id, etc.)
    - employer_name: resolved from the employer_id FK first, then falls back
      to the plain employer_name text field on the application.
    - business_type / years_in_business / monthly_business_turnover: sourced
      from the Customer profile when not overridden on the application.
    """
    # Resolve the Odoo customer ID from the Customer profile
    customer = getattr(application, "customer", None)
    odoo_customer_id = 0
    if customer is not None:
        odoo_customer_id = int(getattr(customer, "odoo_customer_id", 0) or 0)

    # Resolve the Odoo product ID from the LoanProduct
    loan_product = getattr(application, "loan_product", None)
    odoo_loan_product_id = 0
    if loan_product is not None:
        odoo_loan_product_id = int(getattr(loan_product, "odoo_product_id", 0) or 0)

    payload: dict[str, Any] = {
        "django_application_id": application.pk,
        "odoo_customer_id": odoo_customer_id,
        "odoo_loan_product_id": odoo_loan_product_id,
        "requested_amount": float(getattr(application, "requested_amount", 0) or 0),
        "tenure_months": int(getattr(application, "tenure_months", 0) or 0),
        "repayment_frequency": getattr(application, "repayment_frequency", "MONTHLY")
        or "MONTHLY",
        "purpose": getattr(application, "purpose", "") or "",
    }

    # Loan product name/code for Odoo display (fallback when odoo_loan_product_id is 0)
    if loan_product is not None:
        payload["loan_product_name"] = getattr(loan_product, "name", "") or ""
        payload["loan_product_code"] = getattr(loan_product, "code", "") or ""

    # --- Employer name resolution -------------------------------------------------
    # Prefer the structured employer FK (employer_id → Employer.name), then fall
    # back to the free-text employer_name field stored directly on the application.
    employer_fk = getattr(application, "employer_id", None)
    if employer_fk is not None:
        resolved_employer_name = getattr(employer_fk, "name", "") or ""
    else:
        resolved_employer_name = getattr(application, "employer_name", "") or ""
    if resolved_employer_name:
        payload["employer_name"] = resolved_employer_name

    # Optional application-level fields (Odoo Alignment)
    for field in (
        "approved_amount",
        "conditions_of_approval",
        "internal_notes",
        "business_name",
        "business_registration_number",
        "business_location",
        "annual_turnover",
        "monthly_income",
        "job_title",
    ):
        value = getattr(application, field, None)
        if value is not None:
            if hasattr(value, "__class__") and value.__class__.__name__ == "Decimal":
                payload[field] = float(value)
            else:
                payload[field] = value

    # --- Customer-level business fields ------------------------------------------
    # These live on the Customer profile rather than the application, so we read
    # them from there when they are not already present on the application itself.
    if customer is not None:
        for cust_field in ("business_type", "years_in_business", "monthly_business_turnover"):
            # Only add if not already set from application-level data
            if cust_field not in payload:
                value = getattr(customer, cust_field, None)
                if value is not None:
                    if hasattr(value, "__class__") and value.__class__.__name__ == "Decimal":
                        payload[cust_field] = float(value)
                    else:
                        payload[cust_field] = value

    return payload


def _build_guarantor_payload(guarantor_verification) -> dict:
    """
    Build the JSON payload for POST
    /alba/api/v1/applications/<id>/guarantors from a Django
    GuarantorVerification instance.
    """
    payload: dict[str, Any] = {
        "django_guarantor_id": guarantor_verification.pk,
        "full_name": guarantor_verification.full_name,
        "id_number": guarantor_verification.id_number,
        "phone": guarantor_verification.phone,
        "relationship": (guarantor_verification.relationship or "").strip().lower(),
        "guarantee_amount": float(guarantor_verification.liability_amount or 0),
    }
    if guarantor_verification.email:
        payload["email"] = guarantor_verification.email
    if guarantor_verification.address:
        payload["address"] = guarantor_verification.address
    if guarantor_verification.employer:
        payload["employer_name"] = guarantor_verification.employer
    if guarantor_verification.monthly_income is not None:
        payload["monthly_income"] = float(guarantor_verification.monthly_income)
    return payload


# Django Collateral.collateral_type choices -> Odoo alba.collateral.collateral_type
# selection values. Django's set (LAND/BUILDING/VEHICLE/EQUIPMENT/INVENTORY/
# RECEIVABLES/OTHER) doesn't line up 1:1 with Odoo's (land/vehicle/equipment/
# shares/deposit/guarantee/other) — BUILDING maps to land (the closest Odoo
# concept for real-property collateral), INVENTORY/RECEIVABLES have no close
# Odoo analog and map to "other".
_COLLATERAL_TYPE_MAP = {
    "LAND": "land",
    "BUILDING": "land",
    "VEHICLE": "vehicle",
    "EQUIPMENT": "equipment",
    "INVENTORY": "other",
    "RECEIVABLES": "other",
    "OTHER": "other",
}


def _build_collateral_payload(collateral) -> dict:
    """
    Build the JSON payload for POST /alba/api/v1/applications/<id>/collateral
    from a Django Collateral instance.
    """
    payload: dict[str, Any] = {
        "django_collateral_id": collateral.pk,
        "name": collateral.description[:200] if collateral.description else "Collateral",
        "collateral_type": _COLLATERAL_TYPE_MAP.get(collateral.collateral_type, "other"),
        "valuation_amount": float(collateral.estimated_value or 0),
        "valuation_date": (
            collateral.valuation_date.isoformat() if collateral.valuation_date else date.today().isoformat()
        ),
    }
    if collateral.location:
        payload["location_description"] = collateral.location
    return payload
