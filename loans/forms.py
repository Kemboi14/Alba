"""
Loan Application Forms — Customer Portal
Handles: customer profile/KYC, loan application, guarantors, document uploads.
Staff-side forms (review, credit score override, disbursement) are handled in Odoo.
"""

import os

from django import forms
from django.core.exceptions import ValidationError
from django.core.validators import RegexValidator

from .models import (
    Collateral,
    Customer,
    CustomerTag,
    Employer,
    GuarantorVerification,
    LoanApplication,
    LoanDocument,
    LoanProduct,
)

ALLOWED_DOCUMENT_EXTENSIONS = {".pdf", ".jpg", ".jpeg", ".png"}
ALLOWED_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png"}
MAX_UPLOAD_SIZE_BYTES = 10 * 1024 * 1024  # 10 MB


def validate_uploaded_document(uploaded_file, allowed_extensions=ALLOWED_DOCUMENT_EXTENSIONS):
    if uploaded_file is None:
        return
    ext = os.path.splitext(uploaded_file.name)[1].lower()
    if ext not in allowed_extensions:
        raise ValidationError(
            f"Unsupported file type '{ext}'. Allowed: {', '.join(sorted(allowed_extensions))}."
        )
    if uploaded_file.size > MAX_UPLOAD_SIZE_BYTES:
        raise ValidationError("File is too large. Maximum size is 10MB.")


kenyan_phone_validator = RegexValidator(
    regex=r"^254[17]\d{8}$",
    message="Enter a valid phone number starting with 254 (e.g. 254712345678).",
)

# For contact-only phone numbers (not used for M-Pesa API calls), accept the
# local 0-prefixed format too — several of these fields' own widgets show a
# "0712345678"-style placeholder, so requiring the 254-prefixed form here
# would reject exactly what the form tells the user to type.
kenyan_contact_phone_validator = RegexValidator(
    regex=r"^(?:0[17]\d{8}|254[17]\d{8})$",
    message="Enter a valid Kenyan phone number (e.g. 0712345678 or 254712345678).",
)

# employer_contact can legitimately be a landline, an international number,
# or include an extension — unlike a personal mobile number there's no single
# format to enforce, so this only rejects obvious garbage rather than
# requiring a specific Kenyan mobile shape.
general_phone_validator = RegexValidator(
    regex=r"^\+?[\d\s\-()]{7,20}$",
    message="Enter a valid phone number.",
)


class CustomerProfileForm(forms.ModelForm):
    """
    Form for updating customer KYC profile.
    Must be completed before a loan application can be submitted.
    """

    class Meta:
        model = Customer
        # Enhanced with Phase 1 Odoo Alignment fields
        fields = [
            # Identity fields
            "date_of_birth",
            "id_number",
            "id_type",
            "gender",
            "marital_status",
            "nationality",
            # Address
            "address",
            "county",  # Legacy text field
            "county_id",  # Hierarchical FK
            "sub_county_id",
            "ward_id",
            "city",
            # Employment (Odoo Alignment)
            "employment_status",
            "employer_id",  # FK to Employer model
            "employer_name",  # Fallback text field
            "employer_contact",
            "employer_email",
            "job_title",
            "months_employed",
            "other_income",
            "monthly_income",
            "employment_date",
            # Business
            "is_business_entity",
            "business_name",
            "business_registration_number",
            "business_location",
            "business_industry",
            "business_type",
            "years_in_business",
            "monthly_business_turnover",
            "sector",
            "subsector",
            "annual_turnover",
            # Next of Kin
            "next_of_kin_name",
            "next_of_kin_phone",
            "next_of_kin_relationship",
            # Referral
            "referral_source",
            "referral_name",
            # Financial
            "existing_loans",
            "bank_name",
            "bank_account",
            "mpesa_number",
            # KYC Documents
            "national_id_file",
            "bank_statement_file",
            "face_recognition_photo",
            # Customer Tags (Odoo Alignment)
            "tag_ids",
        ]
        widgets = {
            "date_of_birth": forms.DateInput(
                attrs={
                    "type": "date",
                    "class": (
                        "mt-1 block w-full rounded-md border-gray-300 shadow-sm "
                        "focus:border-alba-orange focus:ring-alba-orange sm:text-sm"
                    ),
                }
            ),
            "id_number": forms.TextInput(
                attrs={
                    "class": (
                        "mt-1 block w-full rounded-md border-gray-300 shadow-sm "
                        "focus:border-alba-orange focus:ring-alba-orange sm:text-sm"
                    ),
                    "placeholder": "ID or Passport Number",
                }
            ),
            "address": forms.Textarea(
                attrs={
                    "rows": 2,
                    "class": (
                        "mt-1 block w-full rounded-md border-gray-300 shadow-sm "
                        "focus:border-alba-orange focus:ring-alba-orange sm:text-sm"
                    ),
                    "placeholder": "Physical address",
                }
            ),
            "county": forms.TextInput(
                attrs={
                    "class": (
                        "mt-1 block w-full rounded-md border-gray-300 shadow-sm "
                        "focus:border-alba-orange focus:ring-alba-orange sm:text-sm"
                    ),
                }
            ),
            "city": forms.TextInput(
                attrs={
                    "class": (
                        "mt-1 block w-full rounded-md border-gray-300 shadow-sm "
                        "focus:border-alba-orange focus:ring-alba-orange sm:text-sm"
                    ),
                }
            ),
            "employment_status": forms.Select(
                attrs={
                    "class": (
                        "mt-1 block w-full rounded-md border-gray-300 shadow-sm "
                        "focus:border-alba-orange focus:ring-alba-orange sm:text-sm"
                    ),
                }
            ),
            "employer_name": forms.TextInput(
                attrs={
                    "class": (
                        "mt-1 block w-full rounded-md border-gray-300 shadow-sm "
                        "focus:border-alba-orange focus:ring-alba-orange sm:text-sm"
                    ),
                    "placeholder": "Employer name (if not in list)",
                }
            ),
            "employer_id": forms.Select(
                attrs={
                    "class": (
                        "mt-1 block w-full rounded-md border-gray-300 shadow-sm "
                        "focus:border-alba-orange focus:ring-alba-orange sm:text-sm"
                    ),
                }
            ),
            "employer_contact": forms.TextInput(
                attrs={
                    "class": (
                        "mt-1 block w-full rounded-md border-gray-300 shadow-sm "
                        "focus:border-alba-orange focus:ring-alba-orange sm:text-sm"
                    ),
                    "placeholder": "0712345678",
                }
            ),
            "employer_email": forms.EmailInput(
                attrs={
                    "class": (
                        "mt-1 block w-full rounded-md border-gray-300 shadow-sm "
                        "focus:border-alba-orange focus:ring-alba-orange sm:text-sm"
                    ),
                }
            ),
            "monthly_income": forms.NumberInput(
                attrs={
                    "class": (
                        "mt-1 block w-full rounded-md border-gray-300 shadow-sm "
                        "focus:border-alba-orange focus:ring-alba-orange sm:text-sm"
                    ),
                    "placeholder": "50000.00",
                    "step": "0.01",
                }
            ),
            "employment_date": forms.DateInput(
                attrs={
                    "type": "date",
                    "class": (
                        "mt-1 block w-full rounded-md border-gray-300 shadow-sm "
                        "focus:border-alba-orange focus:ring-alba-orange sm:text-sm"
                    ),
                }
            ),
            # New Phase 1 fields widgets
            "id_type": forms.Select(
                attrs={
                    "class": (
                        "mt-1 block w-full rounded-md border-gray-300 shadow-sm "
                        "focus:border-alba-orange focus:ring-alba-orange sm:text-sm"
                    ),
                }
            ),
            "gender": forms.Select(
                attrs={
                    "class": (
                        "mt-1 block w-full rounded-md border-gray-300 shadow-sm "
                        "focus:border-alba-orange focus:ring-alba-orange sm:text-sm"
                    ),
                }
            ),
            "marital_status": forms.Select(
                attrs={
                    "class": (
                        "mt-1 block w-full rounded-md border-gray-300 shadow-sm "
                        "focus:border-alba-orange focus:ring-alba-orange sm:text-sm"
                    ),
                }
            ),
            "nationality": forms.TextInput(
                attrs={
                    "class": (
                        "mt-1 block w-full rounded-md border-gray-300 shadow-sm "
                        "focus:border-alba-orange focus:ring-alba-orange sm:text-sm"
                    ),
                }
            ),
            "county_id": forms.Select(
                attrs={
                    "class": (
                        "mt-1 block w-full rounded-md border-gray-300 shadow-sm "
                        "focus:border-alba-orange focus:ring-alba-orange sm:text-sm"
                    ),
                }
            ),
            "sub_county_id": forms.Select(
                attrs={
                    "class": (
                        "mt-1 block w-full rounded-md border-gray-300 shadow-sm "
                        "focus:border-alba-orange focus:ring-alba-orange sm:text-sm"
                    ),
                }
            ),
            "ward_id": forms.Select(
                attrs={
                    "class": (
                        "mt-1 block w-full rounded-md border-gray-300 shadow-sm "
                        "focus:border-alba-orange focus:ring-alba-orange sm:text-sm"
                    ),
                }
            ),
            "job_title": forms.TextInput(
                attrs={
                    "class": (
                        "mt-1 block w-full rounded-md border-gray-300 shadow-sm "
                        "focus:border-alba-orange focus:ring-alba-orange sm:text-sm"
                    ),
                }
            ),
            "months_employed": forms.NumberInput(
                attrs={
                    "class": (
                        "mt-1 block w-full rounded-md border-gray-300 shadow-sm "
                        "focus:border-alba-orange focus:ring-alba-orange sm:text-sm"
                    ),
                }
            ),
            "other_income": forms.NumberInput(
                attrs={
                    "class": (
                        "mt-1 block w-full rounded-md border-gray-300 shadow-sm "
                        "focus:border-alba-orange focus:ring-alba-orange sm:text-sm"
                    ),
                    "step": "0.01",
                }
            ),
            "business_type": forms.Select(
                attrs={
                    "class": (
                        "mt-1 block w-full rounded-md border-gray-300 shadow-sm "
                        "focus:border-alba-orange focus:ring-alba-orange sm:text-sm"
                    ),
                }
            ),
            "years_in_business": forms.NumberInput(
                attrs={
                    "class": (
                        "mt-1 block w-full rounded-md border-gray-300 shadow-sm "
                        "focus:border-alba-orange focus:ring-alba-orange sm:text-sm"
                    ),
                }
            ),
            "monthly_business_turnover": forms.NumberInput(
                attrs={
                    "class": (
                        "mt-1 block w-full rounded-md border-gray-300 shadow-sm "
                        "focus:border-alba-orange focus:ring-alba-orange sm:text-sm"
                    ),
                    "step": "0.01",
                }
            ),
            "next_of_kin_name": forms.TextInput(
                attrs={
                    "class": (
                        "mt-1 block w-full rounded-md border-gray-300 shadow-sm "
                        "focus:border-alba-orange focus:ring-alba-orange sm:text-sm"
                    ),
                }
            ),
            "next_of_kin_phone": forms.TextInput(
                attrs={
                    "class": (
                        "mt-1 block w-full rounded-md border-gray-300 shadow-sm "
                        "focus:border-alba-orange focus:ring-alba-orange sm:text-sm"
                    ),
                }
            ),
            "next_of_kin_relationship": forms.TextInput(
                attrs={
                    "class": (
                        "mt-1 block w-full rounded-md border-gray-300 shadow-sm "
                        "focus:border-alba-orange focus:ring-alba-orange sm:text-sm"
                    ),
                }
            ),
            "referral_source": forms.Select(
                attrs={
                    "class": (
                        "mt-1 block w-full rounded-md border-gray-300 shadow-sm "
                        "focus:border-alba-orange focus:ring-alba-orange sm:text-sm"
                    ),
                }
            ),
            "referral_name": forms.TextInput(
                attrs={
                    "class": (
                        "mt-1 block w-full rounded-md border-gray-300 shadow-sm "
                        "focus:border-alba-orange focus:ring-alba-orange sm:text-sm"
                    ),
                }
            ),
            "mpesa_number": forms.TextInput(
                attrs={
                    "class": (
                        "mt-1 block w-full rounded-md border-gray-300 shadow-sm "
                        "focus:border-alba-orange focus:ring-alba-orange sm:text-sm"
                    ),
                    "placeholder": "254712345678",
                }
            ),
            "existing_loans": forms.NumberInput(
                attrs={
                    "class": (
                        "mt-1 block w-full rounded-md border-gray-300 shadow-sm "
                        "focus:border-alba-orange focus:ring-alba-orange sm:text-sm"
                    ),
                    "placeholder": "0.00",
                    "step": "0.01",
                }
            ),
            "bank_name": forms.TextInput(
                attrs={
                    "class": (
                        "mt-1 block w-full rounded-md border-gray-300 shadow-sm "
                        "focus:border-alba-orange focus:ring-alba-orange sm:text-sm"
                    ),
                }
            ),
            "bank_account": forms.TextInput(
                attrs={
                    "class": (
                        "mt-1 block w-full rounded-md border-gray-300 shadow-sm "
                        "focus:border-alba-orange focus:ring-alba-orange sm:text-sm"
                    ),
                }
            ),
            "tag_ids": forms.SelectMultiple(
                attrs={
                    "class": (
                        "mt-1 block w-full rounded-md border-gray-300 shadow-sm "
                        "focus:border-alba-orange focus:ring-alba-orange sm:text-sm"
                    ),
                }
            ),
            "national_id_file": forms.FileInput(
                attrs={
                    "class": (
                        "mt-1 block w-full text-sm text-gray-500 "
                        "file:mr-4 file:py-2 file:px-4 file:rounded-full file:border-0 "
                        "file:text-sm file:font-semibold file:bg-alba-orange file:text-white "
                        "hover:file:bg-alba-navy"
                    ),
                    "accept": "image/*,.pdf",
                }
            ),
            "bank_statement_file": forms.FileInput(
                attrs={
                    "class": (
                        "mt-1 block w-full text-sm text-gray-500 "
                        "file:mr-4 file:py-2 file:px-4 file:rounded-full file:border-0 "
                        "file:text-sm file:font-semibold file:bg-alba-orange file:text-white "
                        "hover:file:bg-alba-navy"
                    ),
                    "accept": "image/*,.pdf",
                }
            ),
            "face_recognition_photo": forms.FileInput(
                attrs={
                    "class": (
                        "mt-1 block w-full text-sm text-gray-500 "
                        "file:mr-4 file:py-2 file:px-4 file:rounded-full file:border-0 "
                        "file:text-sm file:font-semibold file:bg-alba-orange file:text-white "
                        "hover:file:bg-alba-navy"
                    ),
                    "accept": "image/*",
                    "capture": "camera",
                }
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Populate employer choices (Odoo Alignment)
        employer_choices = [("", "Select Employer (optional)")]
        for employer in Employer.objects.filter(is_active=True):
            employer_choices.append((employer.pk, employer.name))
        self.fields["employer_id"].choices = employer_choices
        
        # Populate customer tag choices (Odoo Alignment)
        tag_choices = [(tag.pk, tag.name) for tag in CustomerTag.objects.filter(is_active=True)]
        self.fields["tag_ids"].choices = tag_choices

    def clean_national_id_file(self):
        f = self.cleaned_data.get("national_id_file")
        validate_uploaded_document(f)
        return f

    def clean_bank_statement_file(self):
        f = self.cleaned_data.get("bank_statement_file")
        validate_uploaded_document(f)
        return f

    def clean_face_recognition_photo(self):
        f = self.cleaned_data.get("face_recognition_photo")
        validate_uploaded_document(f, allowed_extensions=ALLOWED_IMAGE_EXTENSIONS)
        return f

    def clean_employer_contact(self):
        value = self.cleaned_data.get("employer_contact")
        if value:
            general_phone_validator(value)
        return value

    def clean_next_of_kin_phone(self):
        value = self.cleaned_data.get("next_of_kin_phone")
        if value:
            kenyan_contact_phone_validator(value)
        return value

    def clean_mpesa_number(self):
        value = self.cleaned_data.get("mpesa_number")
        if value:
            kenyan_phone_validator(value)
        return value


class LoanApplicationForm(forms.ModelForm):
    """
    Form for a customer to apply for a loan product.
    Validates amount and tenure against the selected product's limits.
    """

    class Meta:
        model = LoanApplication
        # Enhanced with Phase 1 Odoo Alignment fields
        fields = [
            "loan_product",
            "requested_amount",
            "tenure_months",
            "repayment_frequency",
            "purpose",
            # Business fields
            "business_name",
            "business_registration_number",
            "business_location",
            "annual_turnover",
            # Employment details (Phase 1)
            "employer_name",
            "employer_id",
            "monthly_income",
            "job_title",
        ]
        widgets = {
            "loan_product": forms.Select(
                attrs={"class": "form-input", "id": "id_loan_product", "required": True}
            ),
            "requested_amount": forms.NumberInput(
                attrs={
                    "class": "form-input no-spin",
                    "id": "id_requested_amount",
                    "placeholder": "e.g. 50,000",
                    "step": "0.01",
                }
            ),
            "tenure_months": forms.NumberInput(
                attrs={
                    "class": "form-input no-spin",
                    "id": "id_tenure_months",
                    "placeholder": "e.g. 12",
                }
            ),
            "repayment_frequency": forms.Select(attrs={"class": "form-input"}),
            "purpose": forms.Textarea(
                attrs={
                    "rows": 4,
                    "class": "form-input",
                    "placeholder": "Briefly describe the purpose of this loan",
                }
            ),
            "employer_name": forms.TextInput(
                attrs={
                    "class": (
                        "mt-1 block w-full rounded-lg border-gray-300 shadow-sm "
                        "focus:border-alba-orange focus:ring-alba-orange "
                        "text-base px-4 py-3"
                    ),
                    "placeholder": "Employer name (if not in list)",
                }
            ),
            "employer_id": forms.Select(
                attrs={
                    "class": (
                        "mt-1 block w-full rounded-lg border-gray-300 shadow-sm "
                        "focus:border-alba-orange focus:ring-alba-orange "
                        "text-base px-4 py-3"
                    ),
                }
            ),
            "job_title": forms.TextInput(
                attrs={
                    "class": (
                        "mt-1 block w-full rounded-lg border-gray-300 shadow-sm "
                        "focus:border-alba-orange focus:ring-alba-orange "
                        "text-base px-4 py-3"
                    ),
                }
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Short, scannable labels — full details (amount range, tenure) are
        # shown in the info strip that appears once a product is picked, so
        # the dropdown itself doesn't need to repeat them.
        choices = [("", "Select a loan product…")]
        for product in LoanProduct.objects.filter(is_active=True):
            choices.append((product.pk, f"{product.name} — {product.interest_rate}% p.m."))
        self.fields["loan_product"].choices = choices
        
        # Populate employer choices (Odoo Alignment)
        employer_choices = [("", "Select Employer (optional)")]
        for employer in Employer.objects.filter(is_active=True):
            employer_choices.append((employer.pk, employer.name))
        self.fields["employer_id"].choices = employer_choices

    def clean(self):
        cleaned_data = super().clean()
        product = cleaned_data.get("loan_product")
        amount = cleaned_data.get("requested_amount")
        tenure = cleaned_data.get("tenure_months")

        if product and amount:
            if amount < product.min_amount:
                raise ValidationError(
                    {
                        "requested_amount": (
                            f"Minimum loan amount for {product.name} is "
                            f"KES {product.min_amount:,.2f}."
                        )
                    }
                )
            if amount > product.max_amount:
                raise ValidationError(
                    {
                        "requested_amount": (
                            f"Maximum loan amount for {product.name} is "
                            f"KES {product.max_amount:,.2f}."
                        )
                    }
                )

        if product and tenure is not None:
            if tenure < product.min_tenure_months:
                raise ValidationError(
                    {
                        "tenure_months": (
                            f"Minimum tenure for {product.name} is "
                            f"{product.min_tenure_months} months."
                        )
                    }
                )
            if tenure > product.max_tenure_months:
                raise ValidationError(
                    {
                        "tenure_months": (
                            f"Maximum tenure for {product.name} is "
                            f"{product.max_tenure_months} months."
                        )
                    }
                )

        return cleaned_data


class GuarantorForm(forms.ModelForm):
    """Form for adding a guarantor to a loan application (Odoo Alignment)."""

    class Meta:
        model = GuarantorVerification
        fields = [
            "full_name",
            "id_number",
            "phone",
            "email",
            "relationship",
            "employer",
            "monthly_income",
            "address",
            "liability_amount",  # Odoo Alignment: guaranteed amount
        ]
        widgets = {
            "full_name": forms.TextInput(
                attrs={
                    "class": (
                        "mt-1 block w-full rounded-md border-gray-300 shadow-sm "
                        "focus:border-alba-orange focus:ring-alba-orange sm:text-sm"
                    ),
                    "placeholder": "Full Name",
                }
            ),
            "id_number": forms.TextInput(
                attrs={
                    "class": (
                        "mt-1 block w-full rounded-md border-gray-300 shadow-sm "
                        "focus:border-alba-orange focus:ring-alba-orange sm:text-sm"
                    ),
                    "placeholder": "ID Number",
                }
            ),
            "phone": forms.TextInput(
                attrs={
                    "class": (
                        "mt-1 block w-full rounded-md border-gray-300 shadow-sm "
                        "focus:border-alba-orange focus:ring-alba-orange sm:text-sm"
                    ),
                    "placeholder": "0712345678",
                }
            ),
            "email": forms.EmailInput(
                attrs={
                    "class": (
                        "mt-1 block w-full rounded-md border-gray-300 shadow-sm "
                        "focus:border-alba-orange focus:ring-alba-orange sm:text-sm"
                    ),
                    "placeholder": "guarantor@example.com",
                }
            ),
            "relationship": forms.TextInput(
                attrs={
                    "class": (
                        "mt-1 block w-full rounded-md border-gray-300 shadow-sm "
                        "focus:border-alba-orange focus:ring-alba-orange sm:text-sm"
                    ),
                    "placeholder": "e.g. Friend, Colleague, Relative",
                }
            ),
            "employer": forms.TextInput(
                attrs={
                    "class": (
                        "mt-1 block w-full rounded-md border-gray-300 shadow-sm "
                        "focus:border-alba-orange focus:ring-alba-orange sm:text-sm"
                    ),
                    "placeholder": "Employer Name",
                }
            ),
            "monthly_income": forms.NumberInput(
                attrs={
                    "class": (
                        "mt-1 block w-full rounded-md border-gray-300 shadow-sm "
                        "focus:border-alba-orange focus:ring-alba-orange sm:text-sm"
                    ),
                    "placeholder": "50000.00",
                    "step": "0.01",
                }
            ),
            "address": forms.Textarea(
                attrs={
                    "rows": 2,
                    "class": (
                        "mt-1 block w-full rounded-md border-gray-300 shadow-sm "
                        "focus:border-alba-orange focus:ring-alba-orange sm:text-sm"
                    ),
                    "placeholder": "Physical address",
                }
            ),
            "liability_amount": forms.NumberInput(
                attrs={
                    "class": (
                        "mt-1 block w-full rounded-md border-gray-300 shadow-sm "
                        "focus:border-alba-orange focus:ring-alba-orange sm:text-sm"
                    ),
                    "placeholder": "Maximum guaranteed amount",
                    "step": "0.01",
                }
            ),
        }

    def __init__(self, *args, customer=None, **kwargs):
        super().__init__(*args, **kwargs)
        self._customer = customer

    def clean_phone(self):
        value = self.cleaned_data.get("phone")
        if value:
            kenyan_contact_phone_validator(value)
        return value

    def clean(self):
        cleaned_data = super().clean()
        if self._customer is not None:
            id_number = cleaned_data.get("id_number")
            phone = cleaned_data.get("phone")
            if id_number and self._customer.id_number and id_number == self._customer.id_number:
                raise ValidationError(
                    {"id_number": "You cannot name yourself as your own guarantor."}
                )
            if phone and self._customer.mpesa_number and phone == self._customer.mpesa_number:
                raise ValidationError(
                    {"phone": "You cannot name yourself as your own guarantor."}
                )
        return cleaned_data


class CollateralForm(forms.ModelForm):
    """Form for pledging collateral to a loan application (Odoo Alignment)."""

    class Meta:
        model = Collateral
        fields = [
            "collateral_type",
            "description",
            "estimated_value",
            "valuation_date",
            "location",
            "title_deed_file",
            "insurance_certificate_file",
            "valuation_report_file",
        ]
        widgets = {
            "collateral_type": forms.Select(
                attrs={
                    "class": (
                        "mt-1 block w-full rounded-md border-gray-300 shadow-sm "
                        "focus:border-alba-orange focus:ring-alba-orange sm:text-sm"
                    ),
                }
            ),
            "description": forms.Textarea(
                attrs={
                    "rows": 3,
                    "class": (
                        "mt-1 block w-full rounded-md border-gray-300 shadow-sm "
                        "focus:border-alba-orange focus:ring-alba-orange sm:text-sm"
                    ),
                    "placeholder": "Describe the collateral (e.g. Toyota Probox KDA 123X, or Title No. Nairobi/Block 1/234)",
                }
            ),
            "estimated_value": forms.NumberInput(
                attrs={
                    "class": (
                        "mt-1 block w-full rounded-md border-gray-300 shadow-sm "
                        "focus:border-alba-orange focus:ring-alba-orange sm:text-sm"
                    ),
                    "placeholder": "Market value",
                    "step": "0.01",
                }
            ),
            "valuation_date": forms.DateInput(
                attrs={
                    "type": "date",
                    "class": (
                        "mt-1 block w-full rounded-md border-gray-300 shadow-sm "
                        "focus:border-alba-orange focus:ring-alba-orange sm:text-sm"
                    ),
                }
            ),
            "location": forms.TextInput(
                attrs={
                    "class": (
                        "mt-1 block w-full rounded-md border-gray-300 shadow-sm "
                        "focus:border-alba-orange focus:ring-alba-orange sm:text-sm"
                    ),
                    "placeholder": "Physical location",
                }
            ),
            "title_deed_file": forms.FileInput(
                attrs={
                    "class": (
                        "mt-1 block w-full text-sm text-gray-500 "
                        "file:mr-4 file:py-2 file:px-4 file:rounded-md file:border-0 "
                        "file:text-sm file:font-semibold file:bg-alba-orange file:text-white "
                        "hover:file:bg-opacity-90"
                    ),
                    "accept": ".pdf,.jpg,.jpeg,.png",
                }
            ),
            "insurance_certificate_file": forms.FileInput(
                attrs={
                    "class": (
                        "mt-1 block w-full text-sm text-gray-500 "
                        "file:mr-4 file:py-2 file:px-4 file:rounded-md file:border-0 "
                        "file:text-sm file:font-semibold file:bg-alba-orange file:text-white "
                        "hover:file:bg-opacity-90"
                    ),
                    "accept": ".pdf,.jpg,.jpeg,.png",
                }
            ),
            "valuation_report_file": forms.FileInput(
                attrs={
                    "class": (
                        "mt-1 block w-full text-sm text-gray-500 "
                        "file:mr-4 file:py-2 file:px-4 file:rounded-md file:border-0 "
                        "file:text-sm file:font-semibold file:bg-alba-orange file:text-white "
                        "hover:file:bg-opacity-90"
                    ),
                    "accept": ".pdf,.jpg,.jpeg,.png",
                }
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["valuation_date"].required = True

    def clean_estimated_value(self):
        value = self.cleaned_data.get("estimated_value")
        if value is not None and value <= 0:
            raise ValidationError("Estimated value must be greater than 0.")
        return value

    def clean_title_deed_file(self):
        f = self.cleaned_data.get("title_deed_file")
        validate_uploaded_document(f)
        return f

    def clean_insurance_certificate_file(self):
        f = self.cleaned_data.get("insurance_certificate_file")
        validate_uploaded_document(f)
        return f

    def clean_valuation_report_file(self):
        f = self.cleaned_data.get("valuation_report_file")
        validate_uploaded_document(f)
        return f


class LoanDocumentForm(forms.ModelForm):
    """Form for uploading a supporting document to a loan application (Odoo Alignment)."""

    class Meta:
        model = LoanDocument
        fields = ["document_type", "document_file", "description"]
        widgets = {
            "document_type": forms.Select(
                attrs={
                    "class": (
                        "mt-1 block w-full rounded-md border-gray-300 shadow-sm "
                        "focus:border-alba-orange focus:ring-alba-orange sm:text-sm"
                    ),
                }
            ),
            "document_file": forms.FileInput(
                attrs={
                    "class": (
                        "mt-1 block w-full text-sm text-gray-500 "
                        "file:mr-4 file:py-2 file:px-4 file:rounded-md file:border-0 "
                        "file:text-sm file:font-semibold file:bg-alba-orange file:text-white "
                        "hover:file:bg-opacity-90"
                    ),
                    "accept": ".pdf,.jpg,.jpeg,.png",
                }
            ),
            "description": forms.TextInput(
                attrs={
                    "class": (
                        "mt-1 block w-full rounded-md border-gray-300 shadow-sm "
                        "focus:border-alba-orange focus:ring-alba-orange sm:text-sm"
                    ),
                    "placeholder": "Brief description (optional)",
                }
            ),
        }

    def clean_document_file(self):
        f = self.cleaned_data.get("document_file")
        validate_uploaded_document(f)
        return f
