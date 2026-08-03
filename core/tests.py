from unittest import mock

from django.test import TestCase

from core.services.odoo_sync import (
    OdooConnectionError,
    OdooSyncError,
    OdooSyncService,
    OdooValidationError,
    _build_customer_payload,
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


class _FakeProfile:
    """
    Stand-in for loans.models.Customer carrying the UPPER_SNAKE_CASE choice
    values the real model stores (e.g. Customer.EMPLOYED == "EMPLOYED").
    """

    def __init__(self, **overrides):
        defaults = dict(
            id_number="12345678",
            id_type="NATIONAL",
            date_of_birth=None,
            gender="MALE",
            marital_status="MARRIED",
            nationality="Kenyan",
            address="123 Test Street",
            city="Nairobi",
            county=None,
            county_id=None,
            sub_county_id=None,
            ward_id=None,
            employment_status="EMPLOYED",
            employer_name="Acme Ltd",
            employer_contact=None,
            employer_email=None,
            job_title=None,
            months_employed=None,
            other_income=None,
            monthly_income=85000,
            employment_date=None,
            business_name=None,
            business_registration_number=None,
            business_location=None,
            business_industry=None,
            business_type="SOLE_PROPRIETOR",
            years_in_business=None,
            monthly_business_turnover=None,
            sector_id=None,
            subsector_id=None,
            annual_turnover=None,
            next_of_kin_name=None,
            next_of_kin_phone=None,
            next_of_kin_relationship=None,
            referral_source="AGENT",
            referral_name=None,
            bank_name=None,
            bank_account=None,
            mpesa_number=None,
            kyc_status="PENDING",
            kyc_verified=False,
            credit_score=None,
            risk_rating="LOW",
            notes=None,
            odoo_customer_id=None,
        )
        defaults.update(overrides)
        for key, value in defaults.items():
            setattr(self, key, value)


class BuildCustomerPayloadChoiceMappingTests(TestCase):
    """
    Regression tests for a bug where every Selection-type profile field
    (employment_status, gender, marital_status, id_type, business_type,
    referral_source, kyc_status, risk_rating) was forwarded to Odoo using
    Django's UPPER_SNAKE_CASE value verbatim (e.g. "EMPLOYED"), while every
    corresponding Odoo field uses lower_snake_case (e.g. "employed"). Odoo
    rejects the *entire* customer record the moment any one of these is
    set ("Wrong value for alba.customer.employment_status: 'EMPLOYED'"),
    which effectively broke customer sync for any real customer who filled
    in their profile. Found by running the actual portal locally against a
    real local Odoo instance and watching create_or_update_customer fail.
    """

    def _payload_for(self, **profile_overrides):
        user = mock.Mock(pk=1, email="jane@example.com", first_name="Jane", last_name="Doe", phone="+254700000000")
        user.customer_profile = _FakeProfile(**profile_overrides)
        return _build_customer_payload(user)

    def test_employment_status_is_lowercased_for_odoo(self):
        payload = self._payload_for(employment_status="EMPLOYED")
        self.assertEqual(payload["employment_status"], "employed")

    def test_gender_is_lowercased_for_odoo(self):
        payload = self._payload_for(gender="FEMALE")
        self.assertEqual(payload["gender"], "female")

    def test_marital_status_is_lowercased_for_odoo(self):
        payload = self._payload_for(marital_status="DIVORCED")
        self.assertEqual(payload["marital_status"], "divorced")

    def test_id_type_is_translated_to_odoo_values(self):
        self.assertEqual(self._payload_for(id_type="NATIONAL")["id_type"], "national_id")
        self.assertEqual(self._payload_for(id_type="PASSPORT")["id_type"], "passport")

    def test_business_type_is_lowercased_for_odoo(self):
        payload = self._payload_for(business_type="LIMITED_COMPANY")
        self.assertEqual(payload["business_type"], "limited_company")

    def test_referral_source_is_lowercased_for_odoo(self):
        payload = self._payload_for(referral_source="STAFF")
        self.assertEqual(payload["referral_source"], "staff")

    def test_kyc_status_is_lowercased_for_odoo(self):
        payload = self._payload_for(kyc_status="VERIFIED")
        self.assertEqual(payload["kyc_status"], "verified")

    def test_risk_rating_is_lowercased_for_odoo(self):
        payload = self._payload_for(risk_rating="VERY_HIGH")
        self.assertEqual(payload["risk_rating"], "very_high")

    def test_unmappable_choice_is_omitted_not_forwarded_raw(self):
        # A value with no known mapping must be dropped rather than sent
        # raw, since sending it would abort the whole customer sync.
        payload = self._payload_for(employment_status="SOME_FUTURE_VALUE")
        self.assertNotIn("employment_status", payload)


class CreateLoanApplicationCustomerPkTests(TestCase):
    """
    Regression test for a bug where OdooSyncService.create_loan_application()
    built its idempotency key with ``customer.id``. loans.models.Customer
    sets its ``user`` OneToOneField as the primary key (``primary_key=True``),
    so Django never creates an implicit ``id`` column/attribute on it —
    accessing ``customer.id`` raised
    ``AttributeError: 'Customer' object has no attribute 'id'`` for every
    application, right after a (now-fixed) successful customer sync. Only
    surfaced by actually running the app against a real Odoo instance and
    submitting a real application all the way through.
    """

    def test_application_creation_does_not_touch_customer_id_attribute(self):
        customer = _FakeCustomer(odoo_customer_id=42)  # already synced
        loan_product = _FakeLoanProduct(odoo_product_id=7)  # already synced
        application = _FakeApplication(customer, loan_product)

        service = OdooSyncService()
        service.base_url = "https://odoo.example.com"
        service.api_key = "test-key"

        with mock.patch.object(
            service,
            "_post_with_idempotency",
            return_value={
                "odoo_application_id": 99,
                "application_number": "APP-TEST-0001",
                "status": "created",
            },
        ):
            result = service.create_loan_application(application)

        self.assertEqual(result["odoo_application_id"], 99)
