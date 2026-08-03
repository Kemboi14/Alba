from unittest import mock

from django.test import TestCase

from core.services.odoo_sync import (
    OdooConnectionError,
    OdooSyncError,
    OdooSyncService,
    OdooValidationError,
)


class _FakeCustomer:
    """Minimal stand-in for loans.models.Customer used by create_loan_application."""

    def __init__(self, pk=1, odoo_customer_id=None):
        self.pk = pk
        self.odoo_customer_id = odoo_customer_id
        self.user = mock.Mock(pk=pk)

    def save(self, update_fields=None):
        pass


class _FakeLoanProduct:
    """Minimal stand-in for loans.models.LoanProduct used by create_loan_application."""

    def __init__(self, pk=1, code="BL-1", odoo_product_id=None):
        self.pk = pk
        self.code = code
        self.name = "Business Loan"
        self.odoo_product_id = odoo_product_id

    def save(self, update_fields=None):
        pass


class _FakeApplication:
    """Minimal stand-in for loans.models.LoanApplication used by create_loan_application."""

    def __init__(self, customer, loan_product):
        self.pk = 1
        self.customer = customer
        self.customer_id = customer.pk
        self.loan_product = loan_product
        self.odoo_application_id = None
        self.application_number = "LA-TEST-0001"
        self.requested_amount = 1000
        self.tenure_months = 3
        self.repayment_frequency = "MONTHLY"
        self.purpose = "test"


class CreateLoanApplicationErrorPropagationTests(TestCase):
    """
    Regression tests for a bug where OdooSyncService.create_loan_application()
    masked the real cause of a customer/product sync failure behind the
    generic "... sync is required before application creation" message, and
    erased the exception TYPE in the process (e.g. turning a transient
    OdooConnectionError into a plain OdooSyncError).

    Both defects hid the actual diagnosis from the admin panel and from the
    error shown to the customer ("Validation or setup error: Customer sync
    is required before application creation" told nobody anything useful),
    and broke the transient-vs-permanent retry classification relied on by
    loans/views.py's ``except (OdooConnectionError, OdooTimeoutError)``
    handler.
    """

    def _service(self):
        service = OdooSyncService()
        # Force is_configured() to True regardless of local env/.env state,
        # so these tests never depend on real Odoo credentials.
        service.base_url = "https://odoo.example.com"
        service.api_key = "test-key"
        return service

    def test_validation_error_from_customer_sync_is_not_masked(self):
        customer = _FakeCustomer()
        loan_product = _FakeLoanProduct(odoo_product_id=5)
        application = _FakeApplication(customer, loan_product)

        service = self._service()
        real_detail = "Invalid email format."
        with mock.patch.object(
            service,
            "create_or_update_customer",
            side_effect=OdooValidationError(
                f"Odoo rejected the request: {real_detail}",
                status_code=400,
                detail=real_detail,
            ),
        ):
            with self.assertRaises(OdooValidationError) as ctx:
                service.create_loan_application(application)

        # The real, diagnosable cause must survive unchanged.
        self.assertIn(real_detail, str(ctx.exception))
        self.assertNotEqual(
            str(ctx.exception),
            "Customer sync is required before application creation",
        )

    def test_connection_error_from_customer_sync_keeps_transient_type(self):
        customer = _FakeCustomer()
        loan_product = _FakeLoanProduct(odoo_product_id=5)
        application = _FakeApplication(customer, loan_product)

        service = self._service()
        with mock.patch.object(
            service,
            "create_or_update_customer",
            side_effect=OdooConnectionError(
                "Cannot reach Odoo at https://odoo.example.com"
            ),
        ):
            # Must still be an OdooConnectionError (transient) — not a plain
            # OdooSyncError — so callers correctly treat it as retryable
            # instead of a permanent validation problem.
            with self.assertRaises(OdooConnectionError):
                service.create_loan_application(application)

    def test_non_odoo_exception_from_customer_sync_is_wrapped_with_real_cause(self):
        customer = _FakeCustomer()
        loan_product = _FakeLoanProduct(odoo_product_id=5)
        application = _FakeApplication(customer, loan_product)

        service = self._service()
        with mock.patch.object(
            service,
            "create_or_update_customer",
            side_effect=KeyError("email"),
        ):
            with self.assertRaises(OdooSyncError) as ctx:
                service.create_loan_application(application)

        # A truly generic (non-Odoo) exception is still wrapped in an
        # OdooSyncError, but its message must remain visible in the detail.
        self.assertIn("email", str(ctx.exception))

    def test_validation_error_from_loan_product_sync_is_not_masked(self):
        customer = _FakeCustomer(odoo_customer_id=42)  # already synced
        loan_product = _FakeLoanProduct(odoo_product_id=None)
        application = _FakeApplication(customer, loan_product)

        service = self._service()
        real_detail = "No matching loan product found in Odoo for code=BL-1."
        with mock.patch.object(
            service,
            "sync_loan_product_to_odoo",
            side_effect=OdooValidationError(
                real_detail, status_code=400, detail=real_detail
            ),
        ):
            with self.assertRaises(OdooValidationError) as ctx:
                service.create_loan_application(application)

        self.assertIn(real_detail, str(ctx.exception))
        self.assertNotEqual(
            str(ctx.exception),
            "Product sync is required before application creation",
        )
