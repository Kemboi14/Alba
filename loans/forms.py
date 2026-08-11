"""
Loan Application Forms — Customer Portal
Handles: customer profile/KYC, loan application, guarantors, document uploads.
Staff-side forms (review, credit score override, disbursement) are handled in Odoo.
"""

from django import forms
from django.core.exceptions import ValidationError

from .models import (
    Collateral,
    Customer,
    CustomerTag,
    Employer,
    GuarantorVerification,
    LoanApplication,
    LoanDocument,
    LoanProduct,
    LoanStatusReason,
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
            # Status reason (Odoo Alignment)
            "status_reason_id",
        ]
        widgets = {
            "loan_product": forms.Select(
                attrs={
                    "class": (
                        "mt-1 block w-full rounded-lg border-gray-300 shadow-sm "
                        "focus:border-alba-orange focus:ring-alba-orange "
                        "text-base px-4 py-3"
                    ),
                    "onchange": "updateLoanCalculator()",
                    "required": True,
                }
            ),
            "requested_amount": forms.NumberInput(
                attrs={
                    "class": (
                        "mt-1 block w-full rounded-lg border-gray-300 shadow-sm "
                        "focus:border-alba-orange focus:ring-alba-orange "
                        "text-base px-4 py-3 pl-12"
                    ),
                    "placeholder": "e.g. 50,000",
                    "step": "0.01",
                    "onchange": "updateLoanCalculator()",
                }
            ),
            "tenure_months": forms.NumberInput(
                attrs={
                    "class": (
                        "mt-1 block w-full rounded-lg border-gray-300 shadow-sm "
                        "focus:border-alba-orange focus:ring-alba-orange "
                        "text-base px-4 py-3 pl-14"
                    ),
                    "placeholder": "e.g. 12",
                    "onchange": "updateLoanCalculator()",
                }
            ),
            "repayment_frequency": forms.Select(
                attrs={
                    "class": (
                        "mt-1 block w-full rounded-lg border-gray-300 shadow-sm "
                        "focus:border-alba-orange focus:ring-alba-orange "
                        "text-base px-4 py-3"
                    ),
                }
            ),
            "purpose": forms.Textarea(
                attrs={
                    "rows": 5,
                    "class": (
                        "mt-1 block w-full rounded-lg border-gray-300 shadow-sm "
                        "focus:border-alba-orange focus:ring-alba-orange "
                        "text-base px-4 py-3"
                    ),
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
            "status_reason_id": forms.Select(
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
        # Build descriptive labels for each active product
        choices = [("", "---------")]
        for product in LoanProduct.objects.filter(is_active=True):
            label = (
                f"{product.name} — {product.get_category_display()} "
                f"| KES {product.min_amount:,.0f}–{product.max_amount:,.0f} "
                f"| {product.interest_rate}% p.a."
            )
            choices.append((product.pk, label))
        self.fields["loan_product"].choices = choices
        
        # Populate employer choices (Odoo Alignment)
        employer_choices = [("", "Select Employer (optional)")]
        for employer in Employer.objects.filter(is_active=True):
            employer_choices.append((employer.pk, employer.name))
        self.fields["employer_id"].choices = employer_choices
        
        # Populate status reason choices (Odoo Alignment)
        status_reason_choices = [("", "Select Reason (if applicable)")]
        for reason in LoanStatusReason.objects.filter(is_active=True):
            status_reason_choices.append((reason.pk, f"{reason.category}: {reason.reason}"))
        self.fields["status_reason_id"].choices = status_reason_choices

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

        if product and tenure:
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
