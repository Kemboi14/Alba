"""
Loan Management Models for Alba Capital ERP
SRS Section 3.1 - Loan Management System

Models include:
- LoanProduct: Configurable loan products (SRS 3.1.1)
- Sector: Business sector classification (CBK compliance)
- Subsector: Business subsector classification (CBK compliance)
- Customer: Customer profile linked to User
- LoanApplication: Loan application workflow (SRS 3.1.2)
- Loan: Active loans
- LoanRepayment: Repayment tracking
- CreditScore: Credit evaluation (SRS 3.1.3)
- EmployerVerification: Employer verification (SRS 3.1.4)
- GuarantorVerification: Guarantor verification (SRS 3.1.4)
- LoanDocument: Document management
"""

import secrets
import string
from decimal import Decimal

from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models, transaction
from django.utils import timezone

from core.models import User


class LoanProduct(models.Model):
    """
    Loan Product Configuration Model - SRS 3.1.1
    Supports: Salary Advances, Business Loans, Asset Financing, Bonds, IPF, Staff Loans
    NOTE: Investor Loans are managed in Odoo only, not in Django client portal
    """

    # Product Categories as per Requirements Questionnaire
    # NOTE: Investor Loans are managed in Odoo only, not in Django client portal
    SALARY_ADVANCE = "salary_advance"
    BUSINESS_LOAN = "business_loan"
    PERSONAL_LOAN = "personal_loan"
    IPF_LOAN = "ipf_loan"
    BID_BOND = "bid_bond"
    PERFORMANCE_BOND = "performance_bond"
    STAFF_LOAN = "staff_loan"
    ASSET_FINANCING = "asset_financing"

    PRODUCT_CATEGORY_CHOICES = [
        (SALARY_ADVANCE, "Salary Advance"),
        (BUSINESS_LOAN, "Business Loan"),
        (PERSONAL_LOAN, "Personal Loan"),
        (IPF_LOAN, "IPF Loan"),
        (BID_BOND, "Bid Bond"),
        (PERFORMANCE_BOND, "Performance Bond"),
        (STAFF_LOAN, "Staff Loan"),
        (ASSET_FINANCING, "Asset Financing"),
    ]

    # Interest Rate Methodology
    FLAT_RATE = "FLAT_RATE"
    REDUCING_BALANCE = "REDUCING_BALANCE"

    INTEREST_METHOD_CHOICES = [
        (FLAT_RATE, "Flat Rate"),
        (REDUCING_BALANCE, "Reducing Balance"),
    ]

    # Repayment Frequency
    WEEKLY = "WEEKLY"
    FORTNIGHTLY = "FORTNIGHTLY"
    MONTHLY = "MONTHLY"

    FREQUENCY_CHOICES = [
        (WEEKLY, "Weekly"),
        (FORTNIGHTLY, "Fortnightly"),
        (MONTHLY, "Monthly"),
    ]

    # Basic Fields
    name = models.CharField("Product Name", max_length=100, unique=True)
    code = models.CharField("Product Code", max_length=20, unique=True)
    category = models.CharField(
        "Category", max_length=30, choices=PRODUCT_CATEGORY_CHOICES
    )
    description = models.TextField("Description", blank=True)

    # Fee-based products (Bid/Performance Bonds) - no interest
    is_fee_based = models.BooleanField(
        "Is Fee-based Product",
        default=False,
        help_text="Bid bonds and performance bonds are fee-based, not interest-bearing",
    )

    # Loan Amount Limits
    min_amount = models.DecimalField(
        "Minimum Loan Amount",
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.01"))],
    )
    max_amount = models.DecimalField(
        "Maximum Loan Amount",
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.01"))],
    )

    # Interest Configuration
    interest_rate = models.DecimalField(
        "Interest Rate (%)",
        max_digits=5,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0")), MaxValueValidator(Decimal("100"))],
    )
    interest_method = models.CharField(
        "Interest Calculation Method",
        max_length=20,
        choices=INTEREST_METHOD_CHOICES,
        default=REDUCING_BALANCE,
    )

    # Fees Configuration
    origination_fee_percentage = models.DecimalField(
        "Origination Fee (%)",
        max_digits=5,
        decimal_places=2,
        default=Decimal("0"),
        validators=[MinValueValidator(Decimal("0")), MaxValueValidator(Decimal("100"))],
    )
    origination_fee_fixed = models.DecimalField(
        "Origination Fee (Fixed Amount)",
        max_digits=12,
        decimal_places=2,
        default=Decimal("0"),
        validators=[MinValueValidator(Decimal("0"))],
    )
    processing_fee = models.DecimalField(
        "Processing Fee",
        max_digits=12,
        decimal_places=2,
        default=Decimal("0"),
        validators=[MinValueValidator(Decimal("0"))],
    )

    # Penalty Configuration
    penalty_rate = models.DecimalField(
        "Penalty Rate (% per month on overdue amount)",
        max_digits=5,
        decimal_places=2,
        default=Decimal("2"),
        validators=[MinValueValidator(Decimal("0")), MaxValueValidator(Decimal("50"))],
    )
    grace_period_days = models.PositiveIntegerField(
        "Grace Period (Days)",
        default=0,
        help_text="Days before penalties start accruing",
    )

    # Repayment Terms
    min_tenure_months = models.PositiveIntegerField(
        "Minimum Tenure (Months)", default=1
    )
    max_tenure_months = models.PositiveIntegerField(
        "Maximum Tenure (Months)", default=12
    )
    default_repayment_frequency = models.CharField(
        "Default Repayment Frequency",
        max_length=15,
        choices=FREQUENCY_CHOICES,
        default=MONTHLY,
    )

    # Status and Tracking
    is_active = models.BooleanField("Active", default=True)
    color = models.PositiveIntegerField(
        "Color Index",
        default=0,
        help_text="Color used in Kanban and Tree views"
    )
    requires_guarantor = models.BooleanField("Requires Guarantor", default=False)
    requires_employer_verification = models.BooleanField(
        "Requires Employer Verification", default=False
    )
    min_credit_score = models.PositiveIntegerField(
        "Minimum Credit Score",
        default=0,
        validators=[MaxValueValidator(100)],
        help_text="Minimum credit score required (0-100)",
    )
    
    # Product Requirements (Odoo Alignment)
    requires_employer = models.BooleanField(
        "Requires Employer Details",
        default=False,
        help_text="Show employer, job title, and payslip fields on the application"
    )
    min_guarantors = models.PositiveIntegerField(
        "Minimum Guarantors",
        default=0,
        help_text="Minimum number of confirmed guarantors required before disbursement"
    )
    requires_collateral = models.BooleanField(
        "Requires Collateral",
        default=False,
        help_text="Show collateral tab and enforce collateral pledge before disbursement"
    )
    requires_business_info = models.BooleanField(
        "Requires Business Information",
        default=False,
        help_text="Show business name, registration, type, and revenue fields"
    )
    requires_payslip = models.BooleanField(
        "Requires Payslip / Proof of Income",
        default=False,
        help_text="Enforce payslip document upload before submission"
    )
    requires_business_reg = models.BooleanField(
        "Requires Business Registration Docs",
        default=False,
        help_text="Enforce business registration certificate upload"
    )
    
    # Automation (Odoo Alignment)
    auto_approve_score_threshold = models.PositiveIntegerField(
        "Auto-Approve Score Threshold",
        default=85,
        help_text="Applications with a credit score above this threshold can be auto-approved"
    )
    auto_disburse = models.BooleanField(
        "Auto-Disburse via M-Pesa B2C",
        default=False,
        help_text="If ticked, approved applications will automatically trigger a B2C API call to disburse funds instantly"
    )
    
    # Provisioning (Odoo Alignment)
    provision_rate = models.DecimalField(
        "Default Provisioning Rate (%)",
        max_digits=5,
        decimal_places=2,
        default=Decimal("1.0"),
        help_text="Base provisioning rate for Normal loans. Substandard/Doubtful/Loss rates are fixed by company policy"
    )

    # Timestamps
    created_at = models.DateTimeField("Created At", auto_now_add=True)
    updated_at = models.DateTimeField("Updated At", auto_now=True)

    # Odoo Integration
    odoo_product_id = models.PositiveIntegerField(
        "Odoo Product ID",
        null=True,
        blank=True,
        unique=True,
        help_text="ID of the corresponding alba.loan.product record in Odoo",
    )

    created_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, related_name="created_loan_products"
    )

    class Meta:
        db_table = "loan_products"
        verbose_name = "Loan Product"
        verbose_name_plural = "Loan Products"
        ordering = ["category", "name"]
        indexes = [
            models.Index(fields=["category", "is_active"]),
            models.Index(fields=["code"]),
        ]

    def __str__(self):
        return f"{self.name} ({self.get_category_display()})"

    def calculate_total_fees(self, loan_amount):
        """
        Calculate total fees based on fee templates (Odoo Alignment)
        
        Args:
            loan_amount: The loan amount to calculate fees for
            
        Returns:
            Decimal: Total fees (fixed amounts + percentage-based fees)
        """
        # Start with legacy fee calculation for backward compatibility
        loan_amount = Decimal(str(loan_amount))
        origination_fee_percentage = Decimal(str(self.origination_fee_percentage))
        percentage_fee = (loan_amount * origination_fee_percentage) / Decimal("100")
        total_fees = percentage_fee + self.origination_fee_fixed + self.processing_fee
        
        # Add fee template fees (Odoo Alignment)
        for template in self.fee_templates.filter(is_active=True):
            if template.fee_type == FeeTemplate.FEE_TYPE_FIXED:
                total_fees += template.amount
            elif template.fee_type == FeeTemplate.FEE_TYPE_PERCENTAGE:
                total_fees += loan_amount * (template.amount / Decimal("100"))
        
        return total_fees

    def calculate_total_interest(self, principal, tenure_months):
        """Calculate total interest based on method"""
        from decimal import Decimal

        # Ensure all values are Decimal
        principal = Decimal(str(principal))
        tenure_months = Decimal(str(tenure_months))
        rate = Decimal(str(self.interest_rate)) / Decimal("100")

        if self.interest_method == self.FLAT_RATE:
            # Flat rate: simple interest on principal
            total_interest = principal * rate * tenure_months
        else:
            # Reducing balance: proper calculation using monthly compounding
            # Formula: Total Interest = Principal * Monthly Rate * Tenure * (Tenure + 1) / (2 * 12)
            # This is an approximation for equal monthly installments
            if tenure_months <= 0:
                total_interest = Decimal("0")
            else:
                monthly_rate = rate / Decimal("12")
                # More accurate reducing balance calculation
                total_interest = (
                    principal
                    * monthly_rate
                    * tenure_months
                    * (tenure_months + Decimal("1"))
                    / (Decimal("2") * Decimal("12"))
                )

        return total_interest.quantize(Decimal("0.01"))
    
    def check_auto_approval_eligibility(self, credit_score):
        """
        Check if application is eligible for auto-approval based on credit score
        (Odoo Alignment)
        
        Args:
            credit_score: Customer's credit score (0-100)
            
        Returns:
            bool: True if eligible for auto-approval
        """
        return credit_score >= self.auto_approve_score_threshold


class Sector(models.Model):
    """
    Business Sector/Industry Classification
    CBK compliance requirement for customer segmentation
    """
    
    name = models.CharField("Sector Name", max_length=200, unique=True)
    code = models.CharField("Sector Code", max_length=50, unique=True)
    description = models.TextField("Description", blank=True)
    is_active = models.BooleanField("Active", default=True)
    
    created_at = models.DateTimeField("Created At", auto_now_add=True)
    updated_at = models.DateTimeField("Updated At", auto_now=True)
    
    class Meta:
        db_table = "sectors"
        verbose_name = "Sector"
        verbose_name_plural = "Sectors"
        ordering = ["name"]
        indexes = [
            models.Index(fields=["code"]),
            models.Index(fields=["is_active"]),
        ]
    
    def __str__(self):
        return self.name


class Subsector(models.Model):
    """
    Business Subsector/Industry Specialization
    Child of Sector with dynamic filtering
    CBK compliance requirement
    """
    
    sector = models.ForeignKey(
        Sector,
        on_delete=models.CASCADE,
        related_name="subsectors"
    )
    name = models.CharField("Subsector Name", max_length=200)
    code = models.CharField("Subsector Code", max_length=50)
    description = models.TextField("Description", blank=True)
    is_active = models.BooleanField("Active", default=True)
    
    created_at = models.DateTimeField("Created At", auto_now_add=True)
    updated_at = models.DateTimeField("Updated At", auto_now=True)
    
    class Meta:
        db_table = "subsectors"
        verbose_name = "Subsector"
        verbose_name_plural = "Subsectors"
        ordering = ["sector", "name"]
        unique_together = [["sector", "code"]]
        indexes = [
            models.Index(fields=["sector", "is_active"]),
            models.Index(fields=["code"]),
        ]
    
    def __str__(self):
        return f"{self.sector.name} > {self.name}"


# =============================================================================
# Location Models (Hierarchical - Odoo Alignment)
# =============================================================================

class County(models.Model):
    """
    County Model - Top-level administrative division
    Odoo Alignment: alba.county
    """
    
    name = models.CharField("County Name", max_length=100, unique=True)
    code = models.CharField("County Code", max_length=10, unique=True)
    description = models.TextField("Description", blank=True)
    is_active = models.BooleanField("Active", default=True)
    
    created_at = models.DateTimeField("Created At", auto_now_add=True)
    updated_at = models.DateTimeField("Updated At", auto_now=True)
    
    class Meta:
        db_table = "counties"
        verbose_name = "County"
        verbose_name_plural = "Counties"
        ordering = ["name"]
        indexes = [
            models.Index(fields=["code"]),
            models.Index(fields=["is_active"]),
        ]
    
    def __str__(self):
        return self.name


class SubCounty(models.Model):
    """
    Sub-County Model - Second-level administrative division
    Odoo Alignment: alba.sub.county
    """
    
    county = models.ForeignKey(
        County,
        on_delete=models.CASCADE,
        related_name="sub_counties"
    )
    name = models.CharField("Sub-County Name", max_length=100)
    code = models.CharField("Sub-County Code", max_length=10)
    description = models.TextField("Description", blank=True)
    is_active = models.BooleanField("Active", default=True)
    
    created_at = models.DateTimeField("Created At", auto_now_add=True)
    updated_at = models.DateTimeField("Updated At", auto_now=True)
    
    class Meta:
        db_table = "sub_counties"
        verbose_name = "Sub-County"
        verbose_name_plural = "Sub-Counties"
        ordering = ["county", "name"]
        unique_together = [["county", "code"]]
        indexes = [
            models.Index(fields=["county", "is_active"]),
            models.Index(fields=["code"]),
        ]
    
    def __str__(self):
        return f"{self.county.name} > {self.name}"


class Ward(models.Model):
    """
    Ward Model - Third-level administrative division
    Odoo Alignment: alba.ward
    """
    
    sub_county = models.ForeignKey(
        SubCounty,
        on_delete=models.CASCADE,
        related_name="wards"
    )
    name = models.CharField("Ward Name", max_length=100)
    code = models.CharField("Ward Code", max_length=10)
    description = models.TextField("Description", blank=True)
    is_active = models.BooleanField("Active", default=True)
    
    created_at = models.DateTimeField("Created At", auto_now_add=True)
    updated_at = models.DateTimeField("Updated At", auto_now=True)
    
    class Meta:
        db_table = "wards"
        verbose_name = "Ward"
        verbose_name_plural = "Wards"
        ordering = ["sub_county", "name"]
        unique_together = [["sub_county", "code"]]
        indexes = [
            models.Index(fields=["sub_county", "is_active"]),
            models.Index(fields=["code"]),
        ]
    
    def __str__(self):
        return f"{self.sub_county.county.name} > {self.sub_county.name} > {self.name}"


# =============================================================================
# Employer Model (Odoo Alignment)
# =============================================================================

class Employer(models.Model):
    """
    Employer Model - For employer verification and customer employment tracking
    Odoo Alignment: alba.employer
    """
    
    name = models.CharField("Employer Name", max_length=200, unique=True)
    phone = models.CharField("Phone Number", max_length=15, blank=True)
    email = models.EmailField("Email Address", blank=True)
    address = models.TextField("Physical Address", blank=True)
    company_registration_number = models.CharField(
        "Company Registration Number",
        max_length=100,
        blank=True,
        help_text="Business registration number for the employer"
    )
    tax_pin = models.CharField(
        "Tax PIN",
        max_length=20,
        blank=True,
        help_text="Kenya Revenue Authority PIN"
    )
    industry = models.CharField("Industry/Sector", max_length=100, blank=True)
    is_active = models.BooleanField("Active", default=True)
    
    created_at = models.DateTimeField("Created At", auto_now_add=True)
    updated_at = models.DateTimeField("Updated At", auto_now=True)
    
    class Meta:
        db_table = "employers"
        verbose_name = "Employer"
        verbose_name_plural = "Employers"
        ordering = ["name"]
        indexes = [
            models.Index(fields=["name"]),
            models.Index(fields=["is_active"]),
        ]
    
    def __str__(self):
        return self.name


# =============================================================================
# Loan Status Reason Model (Odoo Alignment)
# =============================================================================

class LoanStatusReason(models.Model):
    """
    Loan Status Reason Model - For deferral/decline reasons
    Odoo Alignment: alba.loan.status.reason
    """
    
    CATEGORY_DEFERRED = "DEFERRED"
    CATEGORY_DECLINED = "DECLINED"
    
    CATEGORY_CHOICES = [
        (CATEGORY_DEFERRED, "Deferred"),
        (CATEGORY_DECLINED, "Declined"),
    ]
    
    category = models.CharField(
        "Category",
        max_length=20,
        choices=CATEGORY_CHOICES,
        help_text="Status reason category (deferred or declined)"
    )
    reason = models.CharField("Reason", max_length=200)
    description = models.TextField("Description", blank=True)
    is_active = models.BooleanField("Active", default=True)
    
    created_at = models.DateTimeField("Created At", auto_now_add=True)
    updated_at = models.DateTimeField("Updated At", auto_now=True)
    
    class Meta:
        db_table = "loan_status_reasons"
        verbose_name = "Loan Status Reason"
        verbose_name_plural = "Loan Status Reasons"
        ordering = ["category", "reason"]
        indexes = [
            models.Index(fields=["category", "is_active"]),
            models.Index(fields=["is_active"]),
        ]
    
    def __str__(self):
        return f"{self.category}: {self.reason}"


# =============================================================================
# Customer Tag Model (Odoo Alignment)
# =============================================================================

class CustomerTag(models.Model):
    """
    Customer Tag Model - For customer segmentation and categorization
    Odoo Alignment: alba.customer.tag
    """
    
    name = models.CharField("Tag Name", max_length=50, unique=True)
    color = models.PositiveIntegerField(
        "Color Index",
        default=0,
        help_text="Color used in Kanban and Tree views"
    )
    description = models.TextField("Description", blank=True)
    is_active = models.BooleanField("Active", default=True)
    
    created_at = models.DateTimeField("Created At", auto_now_add=True)
    updated_at = models.DateTimeField("Updated At", auto_now=True)
    
    class Meta:
        db_table = "customer_tags"
        verbose_name = "Customer Tag"
        verbose_name_plural = "Customer Tags"
        ordering = ["name"]
        indexes = [
            models.Index(fields=["name"]),
            models.Index(fields=["is_active"]),
        ]
    
    def __str__(self):
        return self.name


# =============================================================================
# Fee Template Model (Odoo Alignment)
# =============================================================================

class FeeTemplate(models.Model):
    """
    Fee Template Model - For product-based fee configuration
    Odoo Alignment: alba.loan.fee.template
    """
    
    FEE_TYPE_FIXED = "FIXED"
    FEE_TYPE_PERCENTAGE = "PERCENTAGE"
    
    FEE_TYPE_CHOICES = [
        (FEE_TYPE_FIXED, "Fixed Amount"),
        (FEE_TYPE_PERCENTAGE, "Percentage of Loan Amount"),
    ]
    
    loan_product = models.ForeignKey(
        LoanProduct,
        on_delete=models.CASCADE,
        related_name="fee_templates",
        verbose_name="Loan Product"
    )
    fee_name = models.CharField("Fee Name", max_length=100)
    fee_type = models.CharField(
        "Fee Type",
        max_length=20,
        choices=FEE_TYPE_CHOICES,
        default=FEE_TYPE_FIXED
    )
    amount = models.DecimalField(
        "Amount",
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0"))],
        help_text="Fixed amount or percentage (0-100)"
    )
    is_mandatory = models.BooleanField(
        "Mandatory",
        default=True,
        help_text="Whether this fee is mandatory for all applications"
    )
    description = models.TextField("Description", blank=True)
    is_active = models.BooleanField("Active", default=True)
    
    created_at = models.DateTimeField("Created At", auto_now_add=True)
    updated_at = models.DateTimeField("Updated At", auto_now=True)
    
    class Meta:
        db_table = "fee_templates"
        verbose_name = "Fee Template"
        verbose_name_plural = "Fee Templates"
        ordering = ["loan_product", "fee_name"]
        indexes = [
            models.Index(fields=["loan_product", "is_active"]),
            models.Index(fields=["fee_type"]),
        ]
    
    def __str__(self):
        return f"{self.fee_name} ({self.get_fee_type_display()})"


# =============================================================================
# Fee Line Model (Odoo Alignment)
# =============================================================================

class FeeLine(models.Model):
    """
    Fee Line Model - For application-specific fee configuration
    Odoo Alignment: alba.loan.fee.line
    """
    
    loan_application = models.ForeignKey(
        "LoanApplication",
        on_delete=models.CASCADE,
        related_name="fee_lines",
        verbose_name="Loan Application"
    )
    fee_template = models.ForeignKey(
        FeeTemplate,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="fee_lines",
        verbose_name="Fee Template"
    )
    fee_name = models.CharField("Fee Name", max_length=100)
    fee_type = models.CharField(
        "Fee Type",
        max_length=20,
        choices=FeeTemplate.FEE_TYPE_CHOICES
    )
    amount = models.DecimalField(
        "Amount",
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0"))]
    )
    is_paid = models.BooleanField("Paid", default=False)
    paid_at = models.DateTimeField("Paid At", null=True, blank=True)
    
    created_at = models.DateTimeField("Created At", auto_now_add=True)
    updated_at = models.DateTimeField("Updated At", auto_now=True)
    
    class Meta:
        db_table = "fee_lines"
        verbose_name = "Fee Line"
        verbose_name_plural = "Fee Lines"
        ordering = ["loan_application", "fee_name"]
        indexes = [
            models.Index(fields=["loan_application"]),
            models.Index(fields=["is_paid"]),
        ]
    
    def __str__(self):
        return f"{self.fee_name} - {self.loan_application.application_number}"


# =============================================================================
# Guarantor Model (Odoo Alignment)
# =============================================================================

class Guarantor(models.Model):
    """
    Guarantor Model - For guarantor management and verification
    Odoo Alignment: alba.loan.guarantor
    """
    
    GUARANTOR_STATUS_PENDING = "PENDING"
    GUARANTOR_STATUS_CONFIRMED = "CONFIRMED"
    GUARANTOR_STATUS_REJECTED = "REJECTED"
    
    GUARANTOR_STATUS_CHOICES = [
        (GUARANTOR_STATUS_PENDING, "Pending"),
        (GUARANTOR_STATUS_CONFIRMED, "Confirmed"),
        (GUARANTOR_STATUS_REJECTED, "Rejected"),
    ]
    
    loan_application = models.ForeignKey(
        "LoanApplication",
        on_delete=models.CASCADE,
        related_name="guarantors",
        verbose_name="Loan Application"
    )
    full_name = models.CharField("Full Name", max_length=200)
    id_number = models.CharField("ID/Passport Number", max_length=50)
    phone = models.CharField("Phone Number", max_length=15)
    email = models.EmailField("Email Address", blank=True)
    relationship = models.CharField(
        "Relationship to Borrower",
        max_length=50,
        help_text="e.g., Spouse, Parent, Sibling, Friend"
    )
    employer = models.CharField("Employer", max_length=200, blank=True)
    monthly_income = models.DecimalField(
        "Monthly Income",
        max_digits=12,
        decimal_places=2,
        blank=True,
        null=True,
        validators=[MinValueValidator(Decimal("0"))]
    )
    address = models.TextField("Physical Address", blank=True)
    
    # Verification
    confirmation_code = models.CharField(
        "Confirmation Code",
        max_length=50,
        blank=True,
        unique=True,
        help_text="Unique code sent to guarantor for confirmation"
    )
    status = models.CharField(
        "Status",
        max_length=20,
        choices=GUARANTOR_STATUS_CHOICES,
        default=GUARANTOR_STATUS_PENDING
    )
    confirmed_at = models.DateTimeField("Confirmed At", null=True, blank=True)
    confirmed_via = models.CharField(
        "Confirmed Via",
        max_length=20,
        blank=True,
        help_text="Method of confirmation (SMS, Email, In-Person)"
    )
    rejection_reason = models.TextField("Rejection Reason", blank=True)
    
    # Documents
    id_document_file = models.FileField(
        "ID Document",
        upload_to="guarantor_documents/id/%Y/%m/%d/",
        blank=True
    )
    payslip_file = models.FileField(
        "Payslip",
        upload_to="guarantor_documents/payslips/%Y/%m/%d/",
        blank=True
    )
    
    created_at = models.DateTimeField("Created At", auto_now_add=True)
    updated_at = models.DateTimeField("Updated At", auto_now=True)
    
    class Meta:
        db_table = "guarantors"
        verbose_name = "Guarantor"
        verbose_name_plural = "Guarantors"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["loan_application", "status"]),
            models.Index(fields=["status"]),
            models.Index(fields=["id_number"]),
        ]
    
    def __str__(self):
        return f"{self.full_name} - {self.get_status_display()}"


# =============================================================================
# Collateral Model (Odoo Alignment)
# =============================================================================

class Collateral(models.Model):
    """
    Collateral Model - For collateral management and pledge tracking
    Odoo Alignment: alba.collateral
    """
    
    COLLATERAL_TYPE_LAND = "LAND"
    COLLATERAL_TYPE_BUILDING = "BUILDING"
    COLLATERAL_TYPE_VEHICLE = "VEHICLE"
    COLLATERAL_TYPE_EQUIPMENT = "EQUIPMENT"
    COLLATERAL_TYPE_INVENTORY = "INVENTORY"
    COLLATERAL_TYPE_RECEIVABLES = "RECEIVABLES"
    COLLATERAL_TYPE_OTHER = "OTHER"
    
    COLLATERAL_TYPE_CHOICES = [
        (COLLATERAL_TYPE_LAND, "Land"),
        (COLLATERAL_TYPE_BUILDING, "Building"),
        (COLLATERAL_TYPE_VEHICLE, "Vehicle"),
        (COLLATERAL_TYPE_EQUIPMENT, "Equipment"),
        (COLLATERAL_TYPE_INVENTORY, "Inventory"),
        (COLLATERAL_TYPE_RECEIVABLES, "Receivables"),
        (COLLATERAL_TYPE_OTHER, "Other"),
    ]
    
    COLLATERAL_STATUS_PENDING = "PENDING"
    COLLATERAL_STATUS_VERIFIED = "VERIFIED"
    COLLATERAL_STATUS_PLEDGED = "PLEDGED"
    COLLATERAL_STATUS_RELEASED = "RELEASED"
    COLLATERAL_STATUS_REJECTED = "REJECTED"
    
    COLLATERAL_STATUS_CHOICES = [
        (COLLATERAL_STATUS_PENDING, "Pending"),
        (COLLATERAL_STATUS_VERIFIED, "Verified"),
        (COLLATERAL_STATUS_PLEDGED, "Pledged"),
        (COLLATERAL_STATUS_RELEASED, "Released"),
        (COLLATERAL_STATUS_REJECTED, "Rejected"),
    ]
    
    loan_application = models.ForeignKey(
        "LoanApplication",
        on_delete=models.CASCADE,
        related_name="collaterals",
        verbose_name="Loan Application"
    )
    collateral_type = models.CharField(
        "Collateral Type",
        max_length=30,
        choices=COLLATERAL_TYPE_CHOICES
    )
    description = models.TextField("Description")
    estimated_value = models.DecimalField(
        "Estimated Value",
        max_digits=15,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0"))]
    )
    valuation_date = models.DateField("Valuation Date", null=True, blank=True)
    location = models.CharField("Physical Location", max_length=200, blank=True)
    
    # Verification
    status = models.CharField(
        "Status",
        max_length=20,
        choices=COLLATERAL_STATUS_CHOICES,
        default=COLLATERAL_STATUS_PENDING
    )
    verified_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="verified_collaterals"
    )
    verified_at = models.DateTimeField("Verified At", null=True, blank=True)
    verification_notes = models.TextField("Verification Notes", blank=True)
    
    # Documents
    title_deed_file = models.FileField(
        "Title Deed",
        upload_to="collateral_documents/title_deeds/%Y/%m/%d/",
        blank=True
    )
    insurance_certificate_file = models.FileField(
        "Insurance Certificate",
        upload_to="collateral_documents/insurance/%Y/%m/%d/",
        blank=True
    )
    valuation_report_file = models.FileField(
        "Valuation Report",
        upload_to="collateral_documents/valuations/%Y/%m/%d/",
        blank=True
    )
    
    pledged_at = models.DateTimeField("Pledged At", auto_now_add=True)
    released_at = models.DateTimeField("Released At", null=True, blank=True)
    
    created_at = models.DateTimeField("Created At", auto_now_add=True)
    updated_at = models.DateTimeField("Updated At", auto_now=True)
    
    class Meta:
        db_table = "collaterals"
        verbose_name = "Collateral"
        verbose_name_plural = "Collaterals"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["loan_application", "status"]),
            models.Index(fields=["status"]),
            models.Index(fields=["collateral_type"]),
        ]
    
    def __str__(self):
        return f"{self.get_collateral_type_display()} - {self.estimated_value:,.2f}"


# =============================================================================
# KYC Provider Model (Odoo Alignment)
# =============================================================================

class KYCProvider(models.Model):
    """
    KYC Provider Model - For automated KYC verification integration
    Odoo Alignment: alba.kyc.provider
    """
    
    name = models.CharField("Provider Name", max_length=100, unique=True)
    is_active = models.BooleanField("Active", default=True)
    api_endpoint = models.URLField("API Endpoint", blank=True)
    api_key = models.CharField("API Key", max_length=100, blank=True)
    api_secret = models.CharField("API Secret", max_length=100, blank=True)
    provider_type = models.CharField(
        "Provider Type",
        max_length=50,
        blank=True,
        help_text="e.g., IDValidate, CRB, CreditInfo"
    )
    confidence_threshold = models.PositiveIntegerField(
        "Confidence Threshold (%)",
        default=80,
        validators=[MaxValueValidator(100)],
        help_text="Minimum confidence score to accept verification"
    )
    description = models.TextField("Description", blank=True)
    
    created_at = models.DateTimeField("Created At", auto_now_add=True)
    updated_at = models.DateTimeField("Updated At", auto_now=True)
    
    class Meta:
        db_table = "kyc_providers"
        verbose_name = "KYC Provider"
        verbose_name_plural = "KYC Providers"
        ordering = ["name"]
        indexes = [
            models.Index(fields=["is_active"]),
        ]
    
    def __str__(self):
        return self.name
    
    def verify_identity(self, id_number, first_name, last_name=None):
        """
        Perform automated KYC verification via external provider
        
        Args:
            id_number: Customer's ID number
            first_name: Customer's first name
            last_name: Customer's last name (optional)
            
        Returns:
            dict: Verification result with status, confidence_score, notes, provider_reference
        """
        import requests
        import logging
        
        logger = logging.getLogger(__name__)
        
        if not self.is_active:
            return {
                'status': 'error',
                'confidence_score': 0,
                'notes': 'KYC provider is not active',
                'provider_reference': None
            }
        
        try:
            # Placeholder for actual API integration
            # This would be customized based on the specific KYC provider's API
            response = requests.post(
                self.api_endpoint,
                json={
                    'id_number': id_number,
                    'first_name': first_name,
                    'last_name': last_name,
                    'api_key': self.api_key,
                },
                timeout=30
            )
            
            if response.status_code == 200:
                data = response.json()
                return {
                    'status': data.get('status', 'pending'),
                    'confidence_score': data.get('confidence_score', 0),
                    'notes': data.get('notes', ''),
                    'provider_reference': data.get('reference', '')
                }
            else:
                return {
                    'status': 'error',
                    'confidence_score': 0,
                    'notes': f"API error: {response.status_code}",
                    'provider_reference': None
                }
                
        except Exception as e:
            logger.error(f"KYC verification error: {e}")
            return {
                'status': 'error',
                'confidence_score': 0,
                'notes': f"Verification failed: {str(e)}",
                'provider_reference': None
            }


class Customer(models.Model):
    """
    Customer Profile Model
    Extends User model with customer-specific information
    """

    # Employment Status (Odoo Alignment)
    EMPLOYED = "EMPLOYED"
    SELF_EMPLOYED = "SELF_EMPLOYED"
    BUSINESS_OWNER = "BUSINESS_OWNER"
    UNEMPLOYED = "UNEMPLOYED"
    RETIRED = "RETIRED"

    EMPLOYMENT_STATUS_CHOICES = [
        (EMPLOYED, "Employed"),
        (SELF_EMPLOYED, "Self Employed"),
        (BUSINESS_OWNER, "Business Owner"),
        (UNEMPLOYED, "Unemployed"),
        (RETIRED, "Retired"),
    ]

    # Link to User
    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name="customer_profile",
        primary_key=True,
    )

    # Personal Information
    date_of_birth = models.DateField("Date of Birth", null=True, blank=True)
    id_number = models.CharField(
        "ID/Passport Number",
        max_length=50,
        unique=True,
        null=True,
        blank=True,
        db_index=True,  # Add index for frequent lookups
    )
    
    # Identity Fields (Odoo Alignment)
    ID_TYPE_NATIONAL = "NATIONAL"
    ID_TYPE_PASSPORT = "PASSPORT"
    ID_TYPE_MILITARY = "MILITARY"
    ID_TYPE_OTHER = "OTHER"
    
    ID_TYPE_CHOICES = [
        (ID_TYPE_NATIONAL, "National ID"),
        (ID_TYPE_PASSPORT, "Passport"),
        (ID_TYPE_MILITARY, "Military ID"),
        (ID_TYPE_OTHER, "Other"),
    ]
    
    id_type = models.CharField(
        "ID Type",
        max_length=20,
        choices=ID_TYPE_CHOICES,
        blank=True,
        help_text="Type of identification document"
    )
    
    GENDER_MALE = "MALE"
    GENDER_FEMALE = "FEMALE"
    GENDER_OTHER = "OTHER"
    
    GENDER_CHOICES = [
        (GENDER_MALE, "Male"),
        (GENDER_FEMALE, "Female"),
        (GENDER_OTHER, "Other"),
    ]
    
    gender = models.CharField(
        "Gender",
        max_length=10,
        choices=GENDER_CHOICES,
        blank=True,
    )
    
    MARITAL_STATUS_SINGLE = "SINGLE"
    MARITAL_STATUS_MARRIED = "MARRIED"
    MARITAL_STATUS_DIVORCED = "DIVORCED"
    MARITAL_STATUS_WIDOWED = "WIDOWED"
    
    MARITAL_STATUS_CHOICES = [
        (MARITAL_STATUS_SINGLE, "Single"),
        (MARITAL_STATUS_MARRIED, "Married"),
        (MARITAL_STATUS_DIVORCED, "Divorced"),
        (MARITAL_STATUS_WIDOWED, "Widowed"),
    ]
    
    marital_status = models.CharField(
        "Marital Status",
        max_length=20,
        choices=MARITAL_STATUS_CHOICES,
        blank=True,
    )
    
    nationality = models.CharField(
        "Nationality",
        max_length=50,
        default="Kenyan",
    )
    
    address = models.TextField("Physical Address", blank=True)
    
    # Location (Hierarchical - Odoo Alignment)
    county_id = models.ForeignKey(
        County,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="customers",
        help_text="County selection (hierarchical)"
    )
    sub_county_id = models.ForeignKey(
        SubCounty,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="customers",
        help_text="Sub-County selection (hierarchical)"
    )
    ward_id = models.ForeignKey(
        Ward,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="customers",
        help_text="Ward selection (hierarchical)"
    )
    
    # Legacy county field for backward compatibility (text-based)
    county = models.CharField("County (Legacy)", max_length=100, blank=True)
    city = models.CharField("City/Town", max_length=100, blank=True)

    # Employment Information
    employment_status = models.CharField(
        "Employment Status (Odoo Alignment)",
        max_length=20,
        choices=EMPLOYMENT_STATUS_CHOICES,
        default=EMPLOYED,
    )
    employer_name = models.CharField("Employer Name", max_length=200, blank=True)
    employer_contact = models.CharField("Employer Contact", max_length=15, blank=True)
    employer_email = models.EmailField("Employer Email", blank=True)
    job_title = models.CharField("Job Title", max_length=100, blank=True)
    
    # Employer (Odoo Alignment)
    employer_id = models.ForeignKey(
        Employer,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="employees",
        verbose_name="Employer"
    )
    months_employed = models.PositiveIntegerField(
        "Months in Current Employment",
        blank=True,
        null=True,
        help_text="Number of months in current employment"
    )
    monthly_income = models.DecimalField(
        "Monthly Income",
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal("0"))],
    )
    other_income = models.DecimalField(
        "Other Monthly Income",
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal("0"))],
        help_text="Additional monthly income from other sources"
    )
    employment_date = models.DateField("Date of Employment", null=True, blank=True)

    # Business Information (SRS 3.1.2 - Business Loans - Odoo Alignment)
    is_business_entity = models.BooleanField("Is Business Entity", default=False)
    business_name = models.CharField("Business Name", max_length=200, blank=True)
    business_registration_number = models.CharField(
        "Business Registration Number", max_length=100, blank=True
    )
    business_location = models.CharField("Business Location", max_length=200, blank=True)
    business_industry = models.CharField("Industry/Sector", max_length=100, blank=True)
    
    # Business Type (Odoo Alignment)
    BUSINESS_TYPE_SOLE_PROPRIETOR = "SOLE_PROPRIETOR"
    BUSINESS_TYPE_PARTNERSHIP = "PARTNERSHIP"
    BUSINESS_TYPE_LIMITED_COMPANY = "LIMITED_COMPANY"
    BUSINESS_TYPE_OTHER = "OTHER"
    
    BUSINESS_TYPE_CHOICES = [
        (BUSINESS_TYPE_SOLE_PROPRIETOR, "Sole Proprietor"),
        (BUSINESS_TYPE_PARTNERSHIP, "Partnership"),
        (BUSINESS_TYPE_LIMITED_COMPANY, "Limited Company"),
        (BUSINESS_TYPE_OTHER, "Other"),
    ]
    
    business_type = models.CharField(
        "Business Type",
        max_length=30,
        choices=BUSINESS_TYPE_CHOICES,
        blank=True,
    )
    
    years_in_business = models.PositiveIntegerField(
        "Years in Business",
        blank=True,
        null=True,
        help_text="Number of years the business has been operating"
    )
    
    monthly_business_turnover = models.DecimalField(
        "Monthly Business Turnover",
        max_digits=15,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal("0"))],
        help_text="Average monthly revenue from business operations"
    )
    
    # CBK Compliance - Sector & Subsector Classification (Req #5)
    sector = models.ForeignKey(
        Sector,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="customers"
    )
    subsector = models.ForeignKey(
        Subsector,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="customers"
    )
    
    annual_turnover = models.DecimalField(
        "Annual Turnover",
        max_digits=15,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal("0"))],
    )

    # Next of Kin (Odoo Alignment)
    next_of_kin_name = models.CharField("Next of Kin Name", max_length=200, blank=True)
    next_of_kin_phone = models.CharField("Next of Kin Phone", max_length=15, blank=True)
    next_of_kin_relationship = models.CharField(
        "Next of Kin Relationship",
        max_length=50,
        blank=True,
        help_text="Relationship to the customer (e.g., Spouse, Parent, Sibling)"
    )

    # Customer Referral Source (Req #3)
    REFERRAL_AGENT = "AGENT"
    REFERRAL_STAFF = "STAFF"
    REFERRAL_DIRECTOR = "DIRECTOR"
    
    REFERRAL_SOURCE_CHOICES = [
        (REFERRAL_AGENT, "Agent"),
        (REFERRAL_STAFF, "Staff"),
        (REFERRAL_DIRECTOR, "Director"),
    ]
    
    referral_source = models.CharField(
        "Referral Source",
        max_length=20,
        choices=REFERRAL_SOURCE_CHOICES,
        null=True,
        blank=True,
        help_text="How the customer was referred to Alba Capital"
    )
    
    referral_name = models.CharField(
        "Referred By",
        max_length=200,
        blank=True,
        help_text="Name of the person who referred this customer"
    )


    # Financial Information
    existing_loans = models.DecimalField(
        "Existing Loan Obligations",
        max_digits=12,
        decimal_places=2,
        default=Decimal("0"),
        validators=[MinValueValidator(Decimal("0"))],
    )
    bank_name = models.CharField("Bank Name", max_length=100, blank=True)
    bank_account = models.CharField("Bank Account Number", max_length=50, blank=True)
    
    # M-Pesa Number (Odoo Alignment)
    mpesa_number = models.CharField(
        "M-Pesa Number",
        max_length=15,
        blank=True,
        help_text="Must start with 254 e.g. 254712345678"
    )

    # KYC Status (Enhanced - Odoo Alignment)
    KYC_STATUS_PENDING = "PENDING"
    KYC_STATUS_PARTIAL = "PARTIAL"
    KYC_STATUS_COMPLETE = "COMPLETE"
    KYC_STATUS_VERIFIED = "VERIFIED"
    KYC_STATUS_REJECTED = "REJECTED"
    
    KYC_STATUS_CHOICES = [
        (KYC_STATUS_PENDING, "Pending"),
        (KYC_STATUS_PARTIAL, "Partially Complete"),
        (KYC_STATUS_COMPLETE, "Complete — Awaiting Verification"),
        (KYC_STATUS_VERIFIED, "Verified"),
        (KYC_STATUS_REJECTED, "Rejected"),
    ]
    
    kyc_status = models.CharField(
        "KYC Status",
        max_length=20,
        choices=KYC_STATUS_CHOICES,
        default=KYC_STATUS_PENDING,
        db_index=True,
        help_text="Enhanced KYC status matching Odoo's 5-state system"
    )
    
    # Legacy field for backward compatibility
    kyc_verified = models.BooleanField(
        "KYC Verified (Legacy)",
        default=False,
        help_text="Legacy boolean field - use kyc_status for new implementations"
    )
    kyc_verified_at = models.DateTimeField("KYC Verified At", null=True, blank=True)
    kyc_verified_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="verified_customers",
    )
    
    # Credit Score & Risk Rating (Odoo Alignment)
    credit_score = models.PositiveIntegerField(
        "Internal Credit Score",
        default=0,
        validators=[MaxValueValidator(100)],
        help_text="0-100 internal credit score assigned by the credit team"
    )
    
    RISK_RATING_LOW = "LOW"
    RISK_RATING_MEDIUM = "MEDIUM"
    RISK_RATING_HIGH = "HIGH"
    RISK_RATING_VERY_HIGH = "VERY_HIGH"
    
    RISK_RATING_CHOICES = [
        (RISK_RATING_LOW, "Low Risk"),
        (RISK_RATING_MEDIUM, "Medium Risk"),
        (RISK_RATING_HIGH, "High Risk"),
        (RISK_RATING_VERY_HIGH, "Very High Risk"),
    ]
    
    risk_rating = models.CharField(
        "Risk Rating",
        max_length=20,
        choices=RISK_RATING_CHOICES,
        blank=True,
        help_text="Customer risk assessment category"
    )

    # KYC Documents
    national_id_file = models.FileField(
        "National ID Document",
        upload_to="kyc_documents/national_id/%Y/%m/%d/",
        null=True,
        blank=True,
    )
    bank_statement_file = models.FileField(
        "Bank Statement",
        upload_to="kyc_documents/bank_statements/%Y/%m/%d/",
        null=True,
        blank=True,
    )
    face_recognition_photo = models.FileField(
        "Face Recognition Photo",
        upload_to="kyc_documents/face_photos/%Y/%m/%d/",
        null=True,
        blank=True,
    )

    # Document Verification Status
    national_id_verified = models.BooleanField("National ID Verified", default=False)
    bank_statement_verified = models.BooleanField(
        "Bank Statement Verified", default=False
    )
    face_recognition_verified = models.BooleanField(
        "Face Recognition Verified", default=False
    )

    # Face Recognition Data
    face_encoding_data = models.TextField("Face Encoding Data", null=True, blank=True)
    face_scan_date = models.DateTimeField("Face Scan Date", null=True, blank=True)

    # ID back photo (verification wizard sends front and back separately)
    id_back_file = models.FileField(
        "National ID Back",
        upload_to="kyc_documents/national_id_back/%Y/%m/%d/",
        null=True,
        blank=True,
    )

    # Additional payslips (JSON list of file paths)
    additional_payslip_files = models.TextField(
        "Additional Payslip File Paths",
        blank=True,
        default="[]",
        help_text="JSON list of uploaded payslip file paths",
    )

    # Odoo customer ID (used by OdooSyncService)
    odoo_customer_id = models.IntegerField(
        "Odoo Customer ID",
        null=True,
        blank=True,
        unique=True,
        help_text="ID of the corresponding alba.customer record in Odoo",
    )

    # Sync status tracking
    ODOO_SYNC_PENDING = "PENDING"
    ODOO_SYNC_SUCCESS = "SUCCESS"
    ODOO_SYNC_FAILED = "FAILED"
    ODOO_SYNC_RETRY = "RETRY"

    ODOO_SYNC_STATUS_CHOICES = [
        (ODOO_SYNC_PENDING, "Pending"),
        (ODOO_SYNC_SUCCESS, "Success"),
        (ODOO_SYNC_FAILED, "Failed"),
        (ODOO_SYNC_RETRY, "Retry"),
    ]

    odoo_sync_status = models.CharField(
        "Odoo Sync Status",
        max_length=20,
        choices=ODOO_SYNC_STATUS_CHOICES,
        default=ODOO_SYNC_PENDING,
        help_text="Status of customer sync to Odoo",
    )
    odoo_sync_error = models.TextField(
        "Odoo Sync Error",
        blank=True,
        help_text="Error message if sync to Odoo failed",
    )
    odoo_sync_attempts = models.IntegerField(
        "Odoo Sync Attempts",
        default=0,
        help_text="Number of sync attempts made to Odoo",
    )
    odoo_last_sync_at = models.DateTimeField(
        "Last Odoo Sync Attempt",
        null=True,
        blank=True,
        help_text="Timestamp of the last sync attempt to Odoo",
    )

    # Verification status from the React wizard
    VERIFICATION_STATUS_CHOICES = [
        ("pending", "Pending"),
        ("in_progress", "In Progress"),
        ("verified", "Verified"),
        ("rejected", "Rejected"),
    ]
    verification_status = models.CharField(
        "Verification Status",
        max_length=20,
        choices=VERIFICATION_STATUS_CHOICES,
        default="pending",
        db_index=True,
    )

    # Raw JSON output from the React verification wizard
    verification_results = models.TextField(
        "Verification Results (JSON)",
        blank=True,
        default="{}",
        help_text="Raw JSON output from the document verification wizard",
    )

    # Overall confidence score from the wizard (0-100)
    verification_confidence = models.IntegerField(
        "Verification Confidence Score",
        default=0,
        help_text="0-100 confidence score from the document verification wizard",
    )

    # Status (Odoo Alignment)
    is_blacklisted = models.BooleanField("Blacklisted", default=False)
    blacklist_reason = models.TextField("Blacklist Reason", blank=True)
    active = models.BooleanField("Active", default=True, help_text="Customer account status")
    
    # Internal Notes (Odoo Alignment)
    notes = models.TextField("Internal Notes", blank=True, help_text="Internal notes about the customer")
    
    # Tags (Odoo Alignment)
    tag_ids = models.ManyToManyField(
        CustomerTag,
        blank=True,
        related_name="customers",
        verbose_name="Tags"
    )

    # Timestamps
    created_at = models.DateTimeField("Created At", auto_now_add=True)
    updated_at = models.DateTimeField("Updated At", auto_now=True)

    class Meta:
        db_table = "customers"
        verbose_name = "Customer"
        verbose_name_plural = "Customers"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["kyc_status", "-created_at"]),
            models.Index(fields=["kyc_verified", "-created_at"]),
            models.Index(fields=["is_blacklisted"]),
            models.Index(fields=["id_number"]),
            models.Index(fields=["active"]),
            models.Index(fields=["credit_score"]),
            models.Index(fields=["risk_rating"]),
            models.Index(fields=["county_id"]),
            models.Index(fields=["sub_county_id"]),
            models.Index(fields=["ward_id"]),
            models.Index(
                fields=[
                    "national_id_verified",
                    "bank_statement_verified",
                    "face_recognition_verified",
                ]
            ),
        ]

    def __str__(self):
        return f"{self.user.get_full_name()} - {self.id_number or 'No ID'}"

    @property
    def total_applications(self):
        """Calculate total number of loan applications for this customer"""
        return self.loan_applications.count()

    @property
    def last_application_date(self):
        """Get the date of the last loan application"""
        last_app = self.loan_applications.order_by("-created_at").first()
        return last_app.created_at if last_app else None

    @property
    def active_loans_count(self):
        """Get count of active loans"""
        return self.loans.filter(status="ACTIVE").count()

    @property
    def is_fully_verified(self):
        """Return True when KYC is verified AND the document wizard passed."""
        return self.kyc_verified and self.verification_status == "verified"

    @property
    def total_loans_borrowed(self):
        """Get total amount borrowed across all loans"""
        from django.db.models import Sum

        total = self.loans.aggregate(total=Sum("principal_amount"))["total"]
        return total or Decimal("0")

    def get_age(self):
        """Calculate customer age"""
        if self.date_of_birth:
            today = timezone.now().date()
            return (
                today.year
                - self.date_of_birth.year
                - (
                    (today.month, today.day)
                    < (self.date_of_birth.month, self.date_of_birth.day)
                )
            )
        return None

    def get_total_active_loans(self):
        """Get total outstanding balance on active loans"""
        from django.db.models import Sum

        total = self.loans.filter(status="ACTIVE").aggregate(
            total=Sum("outstanding_balance")
        )["total"]
        return total or Decimal("0")

    def get_kyc_completion_percentage(self):
        """Calculate KYC completion percentage.

        Profile fields and document fields count as filled when they have
        been provided (uploaded). Verification status is tracked separately.
        """
        fields = [
            bool(self.id_number),
            bool(self.date_of_birth),
            bool(self.address),
            bool(self.monthly_income),
            bool(self.employer_name),
            bool(self.national_id_file),  # Count if uploaded, regardless of verification
            bool(self.bank_statement_file),
            bool(self.face_recognition_photo),
        ]
        completed = sum(fields)
        total = len(fields)
        return round((completed / total) * 100) if total > 0 else 0

    def is_kyc_fully_uploaded(self):
        """Check if all KYC documents are uploaded"""
        return all(
            [
                self.national_id_file,
                self.bank_statement_file,
                self.face_recognition_photo,
            ]
        )

    def is_kyc_fully_verified(self):
        """Check if all KYC documents are verified"""
        return all(
            [
                self.national_id_verified,
                self.bank_statement_verified,
                self.face_recognition_verified,
            ]
        )
    
    def update_kyc_status(self):
        """
        Update KYC status based on document verification and wizard status
        (Odoo Alignment - 5-state system)
        """
        if self.kyc_status == Customer.KYC_STATUS_REJECTED:
            # Once rejected, cannot auto-update
            return
        
        if self.is_kyc_fully_verified() and self.verification_status == "verified":
            self.kyc_status = Customer.KYC_STATUS_VERIFIED
            self.kyc_verified = True
            self.kyc_verified_at = timezone.now()
        elif self.is_kyc_fully_uploaded():
            self.kyc_status = Customer.KYC_STATUS_COMPLETE
        elif self.national_id_file or self.bank_statement_file or self.face_recognition_photo:
            self.kyc_status = Customer.KYC_STATUS_PARTIAL
        else:
            self.kyc_status = Customer.KYC_STATUS_PENDING
        
        self.save(update_fields=['kyc_status', 'kyc_verified', 'kyc_verified_at'])
    
    def calculate_risk_score(self):
        """
        Calculate risk score based on customer's credit score, employment status,
        existing loans, and other factors (Odoo Alignment)
        
        Returns:
            float: Risk score (0.0 to 1.0, where 0.0 is lowest risk)
        """
        risk_score = 0.0
        
        # Credit score component (inverse relationship)
        if self.credit_score > 0:
            credit_risk = (100 - self.credit_score) / 100
            risk_score += credit_risk * 0.4  # 40% weight
        
        # Employment status component
        if self.employment_status == Customer.EMPLOYED:
            employment_risk = 0.1
        elif self.employment_status == Customer.SELF_EMPLOYED:
            employment_risk = 0.2
        elif self.employment_status == Customer.BUSINESS_OWNER:
            employment_risk = 0.15
        else:
            employment_risk = 0.5
        risk_score += employment_risk * 0.2  # 20% weight
        
        # Existing loans component
        active_loans = self.active_loans_count
        if active_loans == 0:
            loans_risk = 0.0
        elif active_loans == 1:
            loans_risk = 0.2
        elif active_loans == 2:
            loans_risk = 0.4
        else:
            loans_risk = 0.6
        risk_score += loans_risk * 0.2  # 20% weight
        
        # Outstanding balance component
        total_outstanding = self.get_total_active_loans()
        if total_outstanding == 0:
            balance_risk = 0.0
        elif total_outstanding < 100000:
            balance_risk = 0.1
        elif total_outstanding < 500000:
            balance_risk = 0.3
        else:
            balance_risk = 0.5
        risk_score += balance_risk * 0.1  # 10% weight
        
        # KYC status component
        if self.kyc_status == Customer.KYC_STATUS_VERIFIED:
            kyc_risk = 0.0
        elif self.kyc_status == Customer.KYC_STATUS_COMPLETE:
            kyc_risk = 0.1
        elif self.kyc_status == Customer.KYC_STATUS_PARTIAL:
            kyc_risk = 0.3
        else:
            kyc_risk = 0.5
        risk_score += kyc_risk * 0.1  # 10% weight
        
        # Cap at 1.0
        return min(risk_score, 1.0)
    
    def update_risk_rating(self):
        """
        Update risk rating based on calculated risk score (Odoo Alignment)
        """
        risk_score = self.calculate_risk_score()
        
        if risk_score < 0.25:
            self.risk_rating = Customer.RISK_RATING_LOW
        elif risk_score < 0.5:
            self.risk_rating = Customer.RISK_RATING_MEDIUM
        elif risk_score < 0.75:
            self.risk_rating = Customer.RISK_RATING_HIGH
        else:
            self.risk_rating = Customer.RISK_RATING_VERY_HIGH
        
        self.save(update_fields=['risk_rating'])
    
    def perform_automated_kyc_verification(self, provider_id=None):
        """
        Perform automated KYC verification using configured KYC provider
        (Odoo Alignment)
        
        Args:
            provider_id: Optional KYC provider ID to use. If None, uses active provider.
            
        Returns:
            dict: Verification result with status, confidence_score, notes, provider_reference
        """
        try:
            # Get KYC provider
            if provider_id:
                provider = KYCProvider.objects.get(id=provider_id, is_active=True)
            else:
                provider = KYCProvider.objects.filter(is_active=True).first()
            
            if not provider:
                return {
                    'status': 'error',
                    'confidence_score': 0,
                    'notes': 'No active KYC provider configured',
                    'provider_reference': None
                }
            
            # Perform verification
            result = provider.verify_identity(
                id_number=self.id_number,
                first_name=self.user.first_name,
                last_name=self.user.last_name
            )
            
            # Update customer based on result
            if result['status'] == 'verified' and result['confidence_score'] >= provider.confidence_threshold:
                self.kyc_status = Customer.KYC_STATUS_VERIFIED
                self.kyc_verified = True
                self.kyc_verified_at = timezone.now()
                self.credit_score = result['confidence_score']
            elif result['status'] == 'rejected':
                self.kyc_status = Customer.KYC_STATUS_REJECTED
            elif result['status'] == 'partial':
                self.kyc_status = Customer.KYC_STATUS_PARTIAL
            
            self.save(update_fields=['kyc_status', 'kyc_verified', 'kyc_verified_at', 'credit_score'])
            
            return result
            
        except KYCProvider.DoesNotExist:
            return {
                'status': 'error',
                'confidence_score': 0,
                'notes': 'KYC provider not found',
                'provider_reference': None
            }
        except Exception as e:
            return {
                'status': 'error',
                'confidence_score': 0,
                'notes': f'Verification failed: {str(e)}',
                'provider_reference': None
            }


class CreditScore(models.Model):
    """
    Credit Score Model - SRS 3.1.3
    Automated credit evaluation engine
    """

    # Score Categories
    APPROVED = "APPROVED"
    CONDITIONAL = "CONDITIONAL"
    REJECTED = "REJECTED"

    RECOMMENDATION_CHOICES = [
        (APPROVED, "Approved"),
        (CONDITIONAL, "Conditional Approval"),
        (REJECTED, "Rejected"),
    ]

    customer = models.ForeignKey(
        Customer, on_delete=models.CASCADE, related_name="credit_scores"
    )
    loan_application = models.OneToOneField(
        "LoanApplication",
        on_delete=models.CASCADE,
        related_name="credit_score",
        null=True,
        blank=True,
    )

    # Scoring Parameters (each out of specific points)
    income_score = models.DecimalField(
        "Income Score", max_digits=5, decimal_places=2, default=0
    )
    employment_score = models.DecimalField(
        "Employment Score", max_digits=5, decimal_places=2, default=0
    )
    credit_history_score = models.DecimalField(
        "Credit History Score", max_digits=5, decimal_places=2, default=0
    )
    existing_obligations_score = models.DecimalField(
        "Existing Obligations Score", max_digits=5, decimal_places=2, default=0
    )
    age_score = models.DecimalField(
        "Age Score", max_digits=5, decimal_places=2, default=0
    )

    # Total Score (0-100)
    total_score = models.DecimalField(
        "Total Score",
        max_digits=5,
        decimal_places=2,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
    )

    # Recommendation
    recommendation = models.CharField(
        "Recommendation", max_length=15, choices=RECOMMENDATION_CHOICES
    )

    # Override Capability (SRS requirement)
    is_overridden = models.BooleanField("Score Overridden", default=False)
    override_reason = models.TextField("Override Justification", blank=True)
    overridden_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="score_overrides",
    )
    overridden_at = models.DateTimeField("Overridden At", null=True, blank=True)

    # Calculation Details
    calculation_details = models.JSONField(
        "Calculation Details", default=dict, blank=True
    )

    # Timestamps
    created_at = models.DateTimeField("Created At", auto_now_add=True)

    class Meta:
        db_table = "credit_scores"
        verbose_name = "Credit Score"
        verbose_name_plural = "Credit Scores"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["customer", "-created_at"]),
            models.Index(fields=["recommendation"]),
            models.Index(fields=["is_overridden"]),
        ]

    def __str__(self):
        return f"{self.customer} - Score: {self.total_score} ({self.recommendation})"


class LoanApplication(models.Model):
    """
    Loan Application Model - SRS 3.1.2
    Manages 9-stage loan application workflow
    """

    # Application Status - 12 Stages (Odoo Alignment)
    DRAFT = "DRAFT"
    SUBMITTED = "SUBMITTED"
    UNDER_REVIEW = "UNDER_REVIEW"
    CREDIT_ANALYSIS = "CREDIT_ANALYSIS"
    PENDING_APPROVAL = "PENDING_APPROVAL"
    APPROVED = "APPROVED"
    DEFERRED = "DEFERRED"
    EMPLOYER_VERIFICATION = "EMPLOYER_VERIFICATION"
    GUARANTOR_CONFIRMATION = "GUARANTOR_CONFIRMATION"
    DISBURSED = "DISBURSED"
    DECLINED = "DECLINED"
    REJECTED = "REJECTED"
    CANCELLED = "CANCELLED"

    APPLICATION_STATUS_CHOICES = [
        (DRAFT, "Draft"),
        (SUBMITTED, "Submitted"),
        (UNDER_REVIEW, "Under Review"),
        (CREDIT_ANALYSIS, "Credit Analysis"),
        (PENDING_APPROVAL, "Pending Approval"),
        (APPROVED, "Approved"),
        (DEFERRED, "Deferred"),
        (EMPLOYER_VERIFICATION, "Employer Verification"),
        (GUARANTOR_CONFIRMATION, "Guarantor Confirmation"),
        (DISBURSED, "Disbursed"),
        (DECLINED, "Declined"),
        (REJECTED, "Rejected"),
        (CANCELLED, "Cancelled"),
    ]

    # Basic Information
    application_number = models.CharField(
        "Application Number", max_length=50, unique=True, editable=False
    )
    customer = models.ForeignKey(
        Customer, on_delete=models.CASCADE, related_name="loan_applications"
    )
    loan_product = models.ForeignKey(
        LoanProduct, on_delete=models.PROTECT, related_name="applications"
    )

    # Loan Details
    requested_amount = models.DecimalField(
        "Requested Amount",
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.01"))],
    )
    approved_amount = models.DecimalField(
        "Approved Amount",
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal("0.01"))],
    )
    tenure_months = models.PositiveIntegerField("Loan Tenure (Months)")
    repayment_frequency = models.CharField(
        "Repayment Frequency", max_length=15, choices=LoanProduct.FREQUENCY_CHOICES
    )
    purpose = models.TextField("Loan Purpose")

    # Business Specific Data (Captured at time of application)
    business_name = models.CharField("Business Name", max_length=200, blank=True)
    business_registration_number = models.CharField(
        "Business Registration Number", max_length=100, blank=True
    )
    business_location = models.CharField("Business Location", max_length=200, blank=True)
    annual_turnover = models.DecimalField(
        "Annual Turnover",
        max_digits=15,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal("0"))],
    )

    # Status and Workflow
    status = models.CharField(
        "Application Status",
        max_length=25,
        choices=APPLICATION_STATUS_CHOICES,
        default=DRAFT,
    )

    # Dates (Odoo Alignment - Additional Stage Timestamps)
    submitted_at = models.DateTimeField("Submitted At", null=True, blank=True)
    reviewed_at = models.DateTimeField("Reviewed At", null=True, blank=True)
    credit_analysis_date = models.DateTimeField("Credit Analysis At", null=True, blank=True)
    pending_approval_date = models.DateTimeField("Pending Approval At", null=True, blank=True)
    approved_at = models.DateTimeField("Approved At", null=True, blank=True)
    employer_verification_date = models.DateTimeField("Employer Verification At", null=True, blank=True)
    guarantor_confirmation_date = models.DateTimeField("Guarantor Confirmation At", null=True, blank=True)
    disbursed_at = models.DateTimeField("Disbursed At", null=True, blank=True)
    rejected_at = models.DateTimeField("Rejected At", null=True, blank=True)
    deferred_date = models.DateTimeField("Deferred At", null=True, blank=True)
    declined_date = models.DateTimeField("Declined At", null=True, blank=True)
    cancelled_date = models.DateTimeField("Cancelled At", null=True, blank=True)

    # Approval/Rejection
    reviewed_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="reviewed_applications",
    )
    approved_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="approved_applications",
    )
    rejection_reason = models.TextField("Rejection Reason", blank=True)
    cancellation_reason = models.TextField("Cancellation Reason", blank=True)
    conditions_of_approval = models.TextField(
        "Conditions of Approval",
        blank=True,
        help_text="Any special conditions that must be met before disbursement"
    )

    # Notes
    internal_notes = models.TextField("Internal Notes", blank=True)
    
    # Employment Details (Pre-captured from customer - Odoo Alignment)
    employer_name = models.CharField("Employer Name", max_length=200, blank=True)
    monthly_income = models.DecimalField(
        "Monthly Income",
        max_digits=12,
        decimal_places=2,
        blank=True,
        null=True,
        validators=[MinValueValidator(Decimal("0"))],
    )
    job_title = models.CharField("Job Title", max_length=100, blank=True)
    
    # Employer (Odoo Alignment)
    employer_id = models.ForeignKey(
        Employer,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="loan_applications",
        verbose_name="Employer"
    )
    
    # Status Reason (Odoo Alignment)
    status_reason_id = models.ForeignKey(
        LoanStatusReason,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="loan_applications",
        verbose_name="Status Reason"
    )
    status_reason = models.CharField(
        "Status Reason (Legacy)",
        max_length=200,
        blank=True,
        help_text="Reason for deferral or decline (legacy - use status_reason_id)"
    )
    
    # Computed Totals (Odoo Alignment)
    estimated_total_interest = models.DecimalField(
        "Estimated Total Interest",
        max_digits=12,
        decimal_places=2,
        blank=True,
        null=True,
        help_text="Calculated total interest over loan tenure"
    )
    estimated_total_fees = models.DecimalField(
        "Estimated Total Fees",
        max_digits=12,
        decimal_places=2,
        blank=True,
        null=True,
        help_text="Calculated total fees (processing, insurance, etc.)"
    )
    estimated_total_repayable = models.DecimalField(
        "Estimated Total Repayable",
        max_digits=12,
        decimal_places=2,
        blank=True,
        null=True,
        help_text="Principal + Interest + Fees"
    )
    net_disbursement_amount = models.DecimalField(
        "Net Disbursement",
        max_digits=12,
        decimal_places=2,
        blank=True,
        null=True,
        help_text="Amount to be paid to customer after deducting fees"
    )
    
    # UX Helpers (Odoo Alignment)
    application_progress = models.PositiveIntegerField(
        "Application Progress",
        default=0,
        help_text="Progress percentage through application stages"
    )
    has_guarantor_block = models.BooleanField(
        "Guarantor Block",
        default=False,
        help_text="Application blocked due to missing guarantor requirements"
    )
    has_collateral_block = models.BooleanField(
        "Collateral Block",
        default=False,
        help_text="Application blocked due to missing collateral requirements"
    )
    risk_score = models.FloatField(
        "Credit Risk Score",
        default=0.0,
        help_text="Computed risk score based on customer assessment"
    )

    # Odoo Integration
    odoo_application_id = models.PositiveIntegerField(
        "Odoo Application ID", null=True, blank=True
    )
    odoo_loan_id = models.PositiveIntegerField(
        "Odoo Loan ID",
        null=True,
        blank=True,
        help_text="Odoo alba.loan ID assigned when this application is disbursed",
    )
    odoo_loan_number = models.CharField(
        "Odoo Loan Number",
        max_length=50,
        blank=True,
        help_text="Odoo loan reference number (e.g. LN-20240601-0001)",
    )

    # Sync status tracking
    ODOO_SYNC_PENDING = "PENDING"
    ODOO_SYNC_SUCCESS = "SUCCESS"
    ODOO_SYNC_FAILED = "FAILED"
    ODOO_SYNC_RETRY = "RETRY"

    ODOO_SYNC_STATUS_CHOICES = [
        (ODOO_SYNC_PENDING, "Pending"),
        (ODOO_SYNC_SUCCESS, "Success"),
        (ODOO_SYNC_FAILED, "Failed"),
        (ODOO_SYNC_RETRY, "Retry"),
    ]

    odoo_sync_status = models.CharField(
        "Odoo Sync Status",
        max_length=20,
        choices=ODOO_SYNC_STATUS_CHOICES,
        default=ODOO_SYNC_PENDING,
        help_text="Status of application sync to Odoo",
    )
    odoo_sync_error = models.TextField(
        "Odoo Sync Error",
        blank=True,
        help_text="Error message if sync to Odoo failed",
    )
    odoo_sync_attempts = models.IntegerField(
        "Odoo Sync Attempts",
        default=0,
        help_text="Number of sync attempts made to Odoo",
    )
    odoo_last_sync_at = models.DateTimeField(
        "Last Odoo Sync Attempt",
        null=True,
        blank=True,
        help_text="Timestamp of the last sync attempt to Odoo",
    )

    # Timestamps
    created_at = models.DateTimeField("Created At", auto_now_add=True)
    updated_at = models.DateTimeField("Updated At", auto_now=True)

    class Meta:
        db_table = "loan_applications"
        verbose_name = "Loan Application"
        verbose_name_plural = "Loan Applications"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["customer", "-created_at"]),
            models.Index(fields=["status", "-created_at"]),
            models.Index(fields=["application_number"]),
            models.Index(fields=["loan_product", "status"]),
        ]

    def __str__(self):
        return f"{self.application_number} - {self.customer.user.get_full_name()}"

    def save(self, *args, **kwargs):
        """Generate application number on creation with improved atomic lock to prevent race conditions"""
        if not self.application_number:
            from django.db import connection, transaction

            date_str = timezone.now().strftime("%Y%m%d")
            prefix = f"LA-{date_str}-"

            # Use database-level advisory lock with retry mechanism
            max_retries = 3
            for attempt in range(max_retries):
                try:
                    with transaction.atomic():
                        # Acquire exclusive lock for this date's sequence with retry
                        lock_id = int(date_str) + (attempt * 1000)  # Add attempt offset
                        with connection.cursor() as cursor:
                            cursor.execute(
                                "SELECT pg_advisory_xact_lock(%s)", [lock_id]
                            )

                        # Get the last number with lock held
                        last_app = (
                            LoanApplication.objects.filter(
                                application_number__startswith=prefix
                            )
                            .order_by("-application_number")
                            .select_for_update()
                            .first()
                        )

                        if last_app:
                            try:
                                last_number = int(
                                    last_app.application_number.split("-")[-1]
                                )
                                new_number = last_number + 1
                            except (ValueError, IndexError):
                                new_number = 1
                        else:
                            new_number = 1

                        # Validate number is within reasonable bounds
                        if new_number > 9999:
                            raise ValueError(
                                "Application number sequence exhausted for today"
                            )

                        self.application_number = f"{prefix}{new_number:04d}"
                        break  # Success, exit retry loop

                except Exception as e:
                    if attempt == max_retries - 1:
                        raise ValueError(
                            f"Failed to generate application number after {max_retries} attempts: {e}"
                        )
                    continue

        super().save(*args, **kwargs)

    def can_transition_to(self, new_status):
        """Validate status transitions (Odoo Alignment - includes DEFERRED and DECLINED)"""
        valid_transitions = {
            self.DRAFT: [self.SUBMITTED, self.CANCELLED],
            self.SUBMITTED: [self.UNDER_REVIEW, self.CANCELLED],
            self.UNDER_REVIEW: [self.CREDIT_ANALYSIS, self.DEFERRED, self.REJECTED],
            self.CREDIT_ANALYSIS: [self.PENDING_APPROVAL, self.DEFERRED, self.REJECTED],
            self.PENDING_APPROVAL: [self.APPROVED, self.DECLINED, self.REJECTED],
            self.APPROVED: [self.EMPLOYER_VERIFICATION, self.DISBURSED],
            self.DEFERRED: [self.UNDER_REVIEW, self.REJECTED, self.CANCELLED],
            self.DECLINED: [self.UNDER_REVIEW, self.REJECTED, self.CANCELLED],
            self.EMPLOYER_VERIFICATION: [
                self.GUARANTOR_CONFIRMATION,
                self.DISBURSED,
                self.REJECTED,
            ],
            self.GUARANTOR_CONFIRMATION: [self.DISBURSED, self.REJECTED],
        }

        return new_status in valid_transitions.get(self.status, [])
    
    def calculate_estimated_totals(self):
        """
        Calculate estimated totals for the loan application (Odoo Alignment)
        Updates: estimated_total_interest, estimated_total_fees, estimated_total_repayable, net_disbursement_amount
        """
        principal = self.requested_amount
        tenure = self.tenure_months
        
        # Calculate total interest
        self.estimated_total_interest = self.loan_product.calculate_total_interest(principal, tenure)
        
        # Calculate total fees
        self.estimated_total_fees = self.loan_product.calculate_total_fees(principal)
        
        # Calculate total repayable
        self.estimated_total_repayable = principal + self.estimated_total_interest + self.estimated_total_fees
        
        # Calculate net disbursement
        self.net_disbursement_amount = principal - self.estimated_total_fees
        
        self.save(update_fields=[
            'estimated_total_interest',
            'estimated_total_fees',
            'estimated_total_repayable',
            'net_disbursement_amount'
        ])
    
    def update_application_progress(self):
        """
        Update application progress percentage based on current status (Odoo Alignment)
        """
        status_progress = {
            self.DRAFT: 10,
            self.SUBMITTED: 20,
            self.UNDER_REVIEW: 30,
            self.CREDIT_ANALYSIS: 40,
            self.PENDING_APPROVAL: 50,
            self.APPROVED: 60,
            self.DEFERRED: 45,
            self.DECLINED: 45,
            self.EMPLOYER_VERIFICATION: 70,
            self.GUARANTOR_CONFIRMATION: 80,
            self.DISBURSED: 100,
            self.REJECTED: 0,
            self.CANCELLED: 0,
        }
        
        self.application_progress = status_progress.get(self.status, 0)
        self.save(update_fields=['application_progress'])
    
    def check_guarantor_requirement(self):
        """
        Check if guarantor requirement is met (Odoo Alignment)
        Updates: has_guarantor_block
        
        Returns:
            bool: True if requirement is met
        """
        if not self.loan_product.requires_guarantor:
            self.has_guarantor_block = False
            self.save(update_fields=['has_guarantor_block'])
            return True
        
        confirmed_count = self.guarantors.filter(status=Guarantor.GUARANTOR_STATUS_CONFIRMED).count()
        required_count = self.loan_product.min_guarantors
        
        if confirmed_count >= required_count:
            self.has_guarantor_block = False
        else:
            self.has_guarantor_block = True
        
        self.save(update_fields=['has_guarantor_block'])
        return not self.has_guarantor_block
    
    def check_collateral_requirement(self):
        """
        Check if collateral requirement is met (Odoo Alignment)
        Updates: has_collateral_block
        
        Returns:
            bool: True if requirement is met
        """
        if not self.loan_product.requires_collateral:
            self.has_collateral_block = False
            self.save(update_fields=['has_collateral_block'])
            return True
        
        # Check if at least one collateral is verified or pledged
        verified_collateral = self.collaterals.filter(
            status__in=[Collateral.COLLATERAL_STATUS_VERIFIED, Collateral.COLLATERAL_STATUS_PLEDGED]
        ).exists()
        
        if verified_collateral:
            self.has_collateral_block = False
        else:
            self.has_collateral_block = True
        
        self.save(update_fields=['has_collateral_block'])
        return not self.has_collateral_block
    
    def calculate_risk_score(self):
        """
        Calculate risk score for the loan application (Odoo Alignment)
        Updates: risk_score
        
        Returns:
            float: Risk score (0.0 to 1.0)
        """
        # Get customer's risk score
        customer_risk = self.customer.calculate_risk_score()
        
        # Adjust based on loan amount
        loan_amount = float(self.requested_amount)
        if loan_amount < 50000:
            amount_risk = 0.0
        elif loan_amount < 200000:
            amount_risk = 0.1
        elif loan_amount < 500000:
            amount_risk = 0.2
        else:
            amount_risk = 0.3
        
        # Adjust based on loan tenure
        tenure = self.tenure_months
        if tenure <= 6:
            tenure_risk = 0.0
        elif tenure <= 12:
            tenure_risk = 0.1
        elif tenure <= 24:
            tenure_risk = 0.2
        else:
            tenure_risk = 0.3
        
        # Calculate combined risk score
        combined_risk = (customer_risk * 0.6) + (amount_risk * 0.2) + (tenure_risk * 0.2)
        
        self.risk_score = combined_risk
        self.save(update_fields=['risk_score'])
        
        return combined_risk
    
    def can_auto_approve(self):
        """
        Check if application is eligible for auto-approval (Odoo Alignment)
        
        Returns:
            bool: True if eligible for auto-approval
        """
        # Check if product has auto-approval enabled
        if not self.loan_product.auto_approve_score_threshold:
            return False
        
        # Check credit score
        if self.customer.credit_score < self.loan_product.auto_approve_score_threshold:
            return False
        
        # Check if requirements are met
        if self.loan_product.requires_guarantor and not self.check_guarantor_requirement():
            return False
        
        if self.loan_product.requires_collateral and not self.check_collateral_requirement():
            return False
        
        # Check KYC status
        if self.customer.kyc_status != Customer.KYC_STATUS_VERIFIED:
            return False
        
        # Check if customer is blacklisted
        if self.customer.is_blacklisted:
            return False
        
        return True
    
    def generate_fee_lines(self):
        """
        Generate fee lines from fee templates (Odoo Alignment)
        Creates FeeLine records based on the loan product's fee templates
        """
        # Delete existing fee lines
        self.fee_lines.all().delete()
        
        # Create new fee lines from templates
        for template in self.loan_product.fee_templates.filter(is_active=True):
            fee_amount = template.amount
            if template.fee_type == FeeTemplate.FEE_TYPE_PERCENTAGE:
                fee_amount = self.requested_amount * (template.amount / Decimal("100"))
            
            FeeLine.objects.create(
                loan_application=self,
                fee_template=template,
                fee_name=template.fee_name,
                fee_type=template.fee_type,
                amount=fee_amount
            )


class Loan(models.Model):
    """
    Active Loan Model
    Created when loan application is disbursed
    """

    # Loan Status
    ACTIVE = "ACTIVE"
    PAID = "PAID"
    OVERDUE = "OVERDUE"
    DEFAULTED = "DEFAULTED"
    WRITTEN_OFF = "WRITTEN_OFF"
    RESTRUCTURED = "RESTRUCTURED"

    LOAN_STATUS_CHOICES = [
        (ACTIVE, "Active"),
        (PAID, "Fully Paid"),
        (OVERDUE, "Overdue"),
        (DEFAULTED, "Defaulted"),
        (WRITTEN_OFF, "Written Off"),
        (RESTRUCTURED, "Restructured"),
    ]

    # Basic Information
    loan_number = models.CharField(
        "Loan Number", max_length=50, unique=True, editable=False
    )
    application = models.OneToOneField(
        LoanApplication, on_delete=models.PROTECT, related_name="disbursed_loan"
    )
    customer = models.ForeignKey(
        Customer, on_delete=models.CASCADE, related_name="loans"
    )
    loan_product = models.ForeignKey(
        LoanProduct, on_delete=models.PROTECT, related_name="active_loans"
    )

    # Loan Amount Breakdown
    principal_amount = models.DecimalField(
        "Principal Amount",
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.01"))],
    )
    interest_amount = models.DecimalField(
        "Total Interest",
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0"))],
    )
    fees = models.DecimalField(
        "Total Fees",
        max_digits=12,
        decimal_places=2,
        default=Decimal("0"),
        validators=[MinValueValidator(Decimal("0"))],
    )
    total_amount = models.DecimalField(
        "Total Amount Payable",
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.01"))],
    )
    outstanding_balance = models.DecimalField(
        "Outstanding Balance",
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0"))],
    )

    # Repayment Details
    installment_amount = models.DecimalField(
        "Installment Amount",
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.01"))],
    )
    repayment_frequency = models.CharField(
        "Repayment Frequency", max_length=15, choices=LoanProduct.FREQUENCY_CHOICES
    )
    tenure_months = models.PositiveIntegerField("Tenure (Months)")

    # Dates
    disbursement_date = models.DateField("Disbursement Date")
    first_payment_date = models.DateField("First Payment Date")
    maturity_date = models.DateField("Maturity Date")
    next_payment_date = models.DateField("Next Payment Date", null=True, blank=True)
    last_payment_date = models.DateField("Last Payment Date", null=True, blank=True)

    # Status
    status = models.CharField(
        "Loan Status", max_length=15, choices=LOAN_STATUS_CHOICES, default=ACTIVE
    )
    days_overdue = models.PositiveIntegerField("Days Overdue", default=0)

    # Penalties
    penalty_charged = models.DecimalField(
        "Total Penalties Charged",
        max_digits=12,
        decimal_places=2,
        default=Decimal("0"),
        validators=[MinValueValidator(Decimal("0"))],
    )

    # Disbursement Details
    disbursed_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, related_name="disbursed_loans"
    )
    disbursement_method = models.CharField(
        "Disbursement Method",
        max_length=50,
        blank=True,
        help_text="e.g., Bank Transfer, M-Pesa, Cheque",
    )
    disbursement_reference = models.CharField(
        "Disbursement Reference", max_length=100, blank=True
    )

    # Odoo Integration
    odoo_loan_id = models.PositiveIntegerField(
        "Odoo Loan ID",
        null=True,
        blank=True,
        unique=True,
        db_index=True,
        help_text="ID of the corresponding alba.loan record in Odoo",
    )

    # Timestamps
    created_at = models.DateTimeField("Created At", auto_now_add=True)
    updated_at = models.DateTimeField("Updated At", auto_now=True)

    class Meta:
        db_table = "loans"
        verbose_name = "Loan"
        verbose_name_plural = "Loans"
        ordering = ["-disbursement_date"]
        indexes = [
            models.Index(fields=["customer", "status"]),
            models.Index(fields=["status", "-disbursement_date"]),
            models.Index(fields=["loan_number"]),
            models.Index(fields=["next_payment_date"]),
        ]

    def __str__(self):
        return f"{self.loan_number} - {self.customer.user.get_full_name()}"

    def save(self, *args, **kwargs):
        """Generate loan number on creation with improved atomic lock to prevent race conditions"""
        if not self.loan_number:
            from django.db import connection, transaction

            date_str = timezone.now().strftime("%Y%m%d")
            prefix = f"LN-{date_str}-"

            # Use database-level advisory lock with retry mechanism
            max_retries = 3
            for attempt in range(max_retries):
                try:
                    with transaction.atomic():
                        # Acquire exclusive lock for this date's sequence with retry
                        lock_id = (
                            int(date_str) + 1000000 + (attempt * 1000)
                        )  # Offset to avoid collision with application locks
                        with connection.cursor() as cursor:
                            cursor.execute(
                                "SELECT pg_advisory_xact_lock(%s)", [lock_id]
                            )

                        last_loan = (
                            Loan.objects.filter(loan_number__startswith=prefix)
                            .order_by("-loan_number")
                            .select_for_update()
                            .first()
                        )

                        if last_loan:
                            try:
                                last_number = int(last_loan.loan_number.split("-")[-1])
                                new_number = last_number + 1
                            except (ValueError, IndexError):
                                new_number = 1
                        else:
                            new_number = 1

                        # Validate number is within reasonable bounds
                        if new_number > 9999:
                            raise ValueError("Loan number sequence exhausted for today")

                        self.loan_number = f"{prefix}{new_number:04d}"
                        break  # Success, exit retry loop

                except Exception as e:
                    if attempt == max_retries - 1:
                        raise ValueError(
                            f"Failed to generate loan number after {max_retries} attempts: {e}"
                        )
                    continue

        super().save(*args, **kwargs)

    def get_payment_progress_percentage(self):
        """Calculate payment progress"""
        if self.total_amount > 0:
            paid = self.total_amount - self.outstanding_balance
            return (paid / self.total_amount) * 100
        return 0


class LoanRepayment(models.Model):
    """
    Loan Repayment Tracking Model
    Records all payments made against loans
    """

    # Payment Type
    REGULAR_PAYMENT = "REGULAR_PAYMENT"
    PARTIAL_PAYMENT = "PARTIAL_PAYMENT"
    FULL_SETTLEMENT = "FULL_SETTLEMENT"
    PENALTY_PAYMENT = "PENALTY_PAYMENT"

    PAYMENT_TYPE_CHOICES = [
        (REGULAR_PAYMENT, "Regular Payment"),
        (PARTIAL_PAYMENT, "Partial Payment"),
        (FULL_SETTLEMENT, "Full Settlement"),
        (PENALTY_PAYMENT, "Penalty Payment"),
    ]

    # Payment Method
    BANK_TRANSFER = "BANK_TRANSFER"
    M_PESA = "M_PESA"
    CASH = "CASH"
    CHEQUE = "CHEQUE"
    DIRECT_DEBIT = "DIRECT_DEBIT"

    PAYMENT_METHOD_CHOICES = [
        (BANK_TRANSFER, "Bank Transfer"),
        (M_PESA, "M-Pesa"),
        (CASH, "Cash"),
        (CHEQUE, "Cheque"),
        (DIRECT_DEBIT, "Direct Debit"),
    ]

    # Basic Information
    receipt_number = models.CharField(
        "Receipt Number", max_length=50, unique=True, editable=False
    )
    loan = models.ForeignKey(Loan, on_delete=models.CASCADE, related_name="repayments")

    # Payment Details
    payment_date = models.DateField("Payment Date")
    amount = models.DecimalField(
        "Amount Paid",
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.01"))],
    )
    payment_type = models.CharField(
        "Payment Type",
        max_length=20,
        choices=PAYMENT_TYPE_CHOICES,
        default=REGULAR_PAYMENT,
    )
    payment_method = models.CharField(
        "Payment Method", max_length=20, choices=PAYMENT_METHOD_CHOICES
    )
    reference_number = models.CharField(
        "Reference Number",
        max_length=100,
        blank=True,
        help_text="Transaction reference from payment provider",
    )

    # Allocation Breakdown
    principal_paid = models.DecimalField(
        "Principal Paid",
        max_digits=12,
        decimal_places=2,
        default=Decimal("0"),
        validators=[MinValueValidator(Decimal("0"))],
    )
    interest_paid = models.DecimalField(
        "Interest Paid",
        max_digits=12,
        decimal_places=2,
        default=Decimal("0"),
        validators=[MinValueValidator(Decimal("0"))],
    )
    penalty_paid = models.DecimalField(
        "Penalty Paid",
        max_digits=12,
        decimal_places=2,
        default=Decimal("0"),
        validators=[MinValueValidator(Decimal("0"))],
    )

    # Processing
    processed_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, related_name="processed_repayments"
    )
    notes = models.TextField("Notes", blank=True)

    # Odoo Integration
    odoo_repayment_id = models.PositiveIntegerField(
        "Odoo Repayment ID",
        null=True,
        blank=True,
        help_text="ID of the posted repayment record in Odoo",
    )
    sync_status = models.CharField(
        "Sync Status",
        max_length=20,
        choices=[
            ("pending", "Pending Sync"),
            ("posted", "Posted in Odoo"),
            ("failed", "Sync Failed"),
        ],
        default="pending",
        db_index=True,
        help_text="Whether this repayment has been posted/reconciled in Odoo",
    )
    principal_applied = models.DecimalField(
        "Principal Applied",
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Principal allocation confirmed by Odoo after posting",
    )
    interest_applied = models.DecimalField(
        "Interest Applied",
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Interest allocation confirmed by Odoo after posting",
    )

    # Timestamps
    created_at = models.DateTimeField("Created At", auto_now_add=True)

    class Meta:
        db_table = "loan_repayments"
        verbose_name = "Loan Repayment"
        verbose_name_plural = "Loan Repayments"
        ordering = ["-payment_date", "-created_at"]
        indexes = [
            models.Index(fields=["loan", "-payment_date"]),
            models.Index(fields=["receipt_number"]),
            models.Index(fields=["payment_date"]),
        ]

    def __str__(self):
        return f"{self.receipt_number} - {self.loan.loan_number} - KES {self.amount}"

    def save(self, *args, **kwargs):
        """Generate receipt number on creation with atomic lock to prevent race conditions"""
        if not self.receipt_number:
            from django.db import connection

            date_str = timezone.now().strftime("%Y%m%d")
            prefix = f"RCP-{date_str}-"

            with transaction.atomic():
                # Acquire exclusive lock for this date's sequence
                lock_id = (
                    int(date_str) + 2000000
                )  # Offset to avoid collision with other locks
                with connection.cursor() as cursor:
                    cursor.execute("SELECT pg_advisory_xact_lock(%s)", [lock_id])

                last_receipt = (
                    LoanRepayment.objects.filter(receipt_number__startswith=prefix)
                    .order_by("-receipt_number")
                    .select_for_update()
                    .first()
                )

                if last_receipt:
                    try:
                        last_number = int(last_receipt.receipt_number.split("-")[-1])
                        new_number = last_number + 1
                    except (ValueError, IndexError):
                        new_number = 1
                else:
                    new_number = 1

                self.receipt_number = f"{prefix}{new_number:04d}"

        super().save(*args, **kwargs)


class EmployerVerification(models.Model):
    """
    Employer Verification Model - SRS 3.1.4
    Third-party validation of employment details
    """

    # Verification Status
    PENDING = "PENDING"
    VERIFIED = "VERIFIED"
    FAILED = "FAILED"
    WAIVED = "WAIVED"

    STATUS_CHOICES = [
        (PENDING, "Pending"),
        (VERIFIED, "Verified"),
        (FAILED, "Failed"),
        (WAIVED, "Waived"),
    ]

    application = models.OneToOneField(
        LoanApplication, on_delete=models.CASCADE, related_name="employer_verification"
    )

    # Employer Details
    employer_name = models.CharField("Employer Name", max_length=200)
    contact_person = models.CharField("Contact Person", max_length=100, blank=True)
    contact_email = models.EmailField("Contact Email", blank=True)
    contact_phone = models.CharField("Contact Phone", max_length=15, blank=True)

    # Verification Details
    employment_confirmed = models.BooleanField("Employment Confirmed", default=False)
    income_confirmed = models.BooleanField("Stated Income Confirmed", default=False)
    verified_income = models.DecimalField(
        "Verified Income",
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal("0"))],
    )

    # Status
    status = models.CharField(
        "Verification Status", max_length=10, choices=STATUS_CHOICES, default=PENDING
    )

    # Verification Process
    sent_at = models.DateTimeField(
        "Verification Request Sent At", null=True, blank=True
    )
    verified_at = models.DateTimeField("Verified At", null=True, blank=True)
    verified_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="employer_verifications",
    )

    # Notes
    verification_notes = models.TextField("Verification Notes", blank=True)

    # Timestamps
    created_at = models.DateTimeField("Created At", auto_now_add=True)
    updated_at = models.DateTimeField("Updated At", auto_now=True)

    class Meta:
        db_table = "employer_verifications"
        verbose_name = "Employer Verification"
        verbose_name_plural = "Employer Verifications"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["status", "-created_at"]),
            models.Index(fields=["application"]),
        ]

    def __str__(self):
        return f"Employer Verification - {self.application.application_number} - {self.status}"


class GuarantorVerification(models.Model):
    """
    Guarantor Verification Model - SRS 3.1.4
    Third-party guarantor confirmation
    """

    # Verification Status
    PENDING = "PENDING"
    CONFIRMED = "CONFIRMED"
    DECLINED = "DECLINED"
    WAIVED = "WAIVED"

    STATUS_CHOICES = [
        (PENDING, "Pending"),
        (CONFIRMED, "Confirmed"),
        (DECLINED, "Declined"),
        (WAIVED, "Waived"),
    ]

    application = models.ForeignKey(
        LoanApplication, on_delete=models.CASCADE, related_name="guarantor_verifications"
    )

    # Guarantor Details
    full_name = models.CharField("Full Name", max_length=200)
    id_number = models.CharField("ID/Passport Number", max_length=50)
    phone = models.CharField("Phone Number", max_length=15)
    email = models.EmailField("Email", blank=True)
    relationship = models.CharField(
        "Relationship to Applicant",
        max_length=100,
        help_text="e.g., Friend, Colleague, Relative",
    )

    # Financial Information
    employer = models.CharField("Employer", max_length=200, blank=True)
    monthly_income = models.DecimalField(
        "Monthly Income",
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal("0"))],
    )

    # Verification
    status = models.CharField(
        "Status", max_length=10, choices=STATUS_CHOICES, default=PENDING
    )
    confirmation_code = models.CharField(
        "Confirmation Code", max_length=10, unique=True, editable=False, blank=True
    )
    sent_at = models.DateTimeField(
        "Confirmation Request Sent At", null=True, blank=True
    )
    confirmed_at = models.DateTimeField("Confirmed At", null=True, blank=True)

    # Notes
    guarantor_notes = models.TextField("Guarantor Notes", blank=True)
    internal_notes = models.TextField("Internal Notes", blank=True)

    # Timestamps
    created_at = models.DateTimeField("Created At", auto_now_add=True)
    updated_at = models.DateTimeField("Updated At", auto_now=True)

    class Meta:
        db_table = "guarantor_verifications"
        verbose_name = "Guarantor Verification"
        verbose_name_plural = "Guarantor Verifications"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["application", "status"]),
            models.Index(fields=["confirmation_code"]),
            models.Index(fields=["status", "-created_at"]),
        ]

    def __str__(self):
        return f"Guarantor: {self.full_name} for {self.application.application_number}"

    def save(self, *args, **kwargs):
        """Generate confirmation code on creation using cryptographically secure random"""
        if not self.confirmation_code:
            # Use secrets for cryptographically secure random generation
            self.confirmation_code = "".join(
                secrets.choice(string.ascii_uppercase + string.digits) for _ in range(8)
            )
        super().save(*args, **kwargs)


class RepaymentSchedule(models.Model):
    """
    Repayment Schedule Model
    Generated at disbursement; each row is one expected installment.
    Odoo will update is_paid / paid_date when payments are recorded.
    """

    loan = models.ForeignKey("Loan", on_delete=models.CASCADE, related_name="schedule")
    installment_number = models.PositiveIntegerField("Installment #")
    due_date = models.DateField("Due Date")

    # Amounts expected for this installment
    principal_due = models.DecimalField(
        "Principal Due",
        max_digits=12,
        decimal_places=2,
        default=Decimal("0"),
        validators=[MinValueValidator(Decimal("0"))],
    )
    interest_due = models.DecimalField(
        "Interest Due",
        max_digits=12,
        decimal_places=2,
        default=Decimal("0"),
        validators=[MinValueValidator(Decimal("0"))],
    )
    fees_due = models.DecimalField(
        "Fees Due",
        max_digits=12,
        decimal_places=2,
        default=Decimal("0"),
        validators=[MinValueValidator(Decimal("0"))],
    )
    penalty_due = models.DecimalField(
        "Penalty Due",
        max_digits=12,
        decimal_places=2,
        default=Decimal("0"),
        validators=[MinValueValidator(Decimal("0"))],
    )
    total_due = models.DecimalField(
        "Total Due",
        max_digits=12,
        decimal_places=2,
        default=Decimal("0"),
        validators=[MinValueValidator(Decimal("0"))],
    )

    # Payment state
    amount_paid = models.DecimalField(
        "Amount Paid",
        max_digits=12,
        decimal_places=2,
        default=Decimal("0"),
        validators=[MinValueValidator(Decimal("0"))],
    )
    is_paid = models.BooleanField("Paid", default=False)
    paid_date = models.DateField("Date Paid", null=True, blank=True)

    # Outstanding on this row
    balance = models.DecimalField(
        "Balance", max_digits=12, decimal_places=2, default=Decimal("0")
    )

    # Odoo sync
    odoo_id = models.CharField(
        "Odoo Record ID",
        max_length=50,
        blank=True,
        help_text="ID of the corresponding record in Odoo",
    )

    created_at = models.DateTimeField("Created At", auto_now_add=True)
    updated_at = models.DateTimeField("Updated At", auto_now=True)

    class Meta:
        db_table = "repayment_schedule"
        verbose_name = "Repayment Schedule"
        verbose_name_plural = "Repayment Schedules"
        ordering = ["loan", "installment_number"]
        unique_together = [["loan", "installment_number"]]
        indexes = [
            models.Index(fields=["loan", "due_date"]),
            models.Index(fields=["is_paid", "due_date"]),
        ]

    def __str__(self):
        return (
            f"{self.loan.loan_number} — Installment {self.installment_number} "
            f"(Due: {self.due_date})"
        )

    def save(self, *args, **kwargs):
        """Keep balance in sync"""
        self.balance = self.total_due - self.amount_paid
        if self.balance < Decimal("0"):
            self.balance = Decimal("0")
        super().save(*args, **kwargs)


class Notification(models.Model):
    """
    In-portal notification model — SRS Section 3.5 (push notifications & in-portal alerts)
    Notifications are created by the system or pushed from Odoo via webhook.
    """

    # Notification Types
    APPLICATION_SUBMITTED = "APPLICATION_SUBMITTED"
    APPLICATION_UNDER_REVIEW = "APPLICATION_UNDER_REVIEW"
    APPLICATION_APPROVED = "APPLICATION_APPROVED"
    APPLICATION_REJECTED = "APPLICATION_REJECTED"
    LOAN_DISBURSED = "LOAN_DISBURSED"
    PAYMENT_DUE = "PAYMENT_DUE"
    PAYMENT_OVERDUE = "PAYMENT_OVERDUE"
    PAYMENT_RECEIVED = "PAYMENT_RECEIVED"
    KYC_VERIFIED = "KYC_VERIFIED"
    KYC_REJECTED = "KYC_REJECTED"
    ACCOUNT_APPROVED = "ACCOUNT_APPROVED"
    GENERAL = "GENERAL"

    NOTIFICATION_TYPE_CHOICES = [
        (APPLICATION_SUBMITTED, "Application Submitted"),
        (APPLICATION_UNDER_REVIEW, "Application Under Review"),
        (APPLICATION_APPROVED, "Application Approved"),
        (APPLICATION_REJECTED, "Application Rejected"),
        (LOAN_DISBURSED, "Loan Disbursed"),
        (PAYMENT_DUE, "Payment Due"),
        (PAYMENT_OVERDUE, "Payment Overdue"),
        (PAYMENT_RECEIVED, "Payment Received"),
        (KYC_VERIFIED, "KYC Verified"),
        (KYC_REJECTED, "KYC Rejected"),
        (ACCOUNT_APPROVED, "Account Approved"),
        (GENERAL, "General"),
    ]

    # Priority
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"

    PRIORITY_CHOICES = [
        (LOW, "Low"),
        (MEDIUM, "Medium"),
        (HIGH, "High"),
        (CRITICAL, "Critical"),
    ]

    user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="notifications"
    )
    notification_type = models.CharField(
        "Type", max_length=30, choices=NOTIFICATION_TYPE_CHOICES, default=GENERAL
    )
    priority = models.CharField(
        "Priority", max_length=10, choices=PRIORITY_CHOICES, default=MEDIUM
    )
    title = models.CharField("Title", max_length=200)
    message = models.TextField("Message")

    # Optional links to related objects
    loan_application = models.ForeignKey(
        "LoanApplication",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="notifications",
    )
    loan = models.ForeignKey(
        "Loan",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="notifications",
    )

    # State
    is_read = models.BooleanField("Read", default=False)
    read_at = models.DateTimeField("Read At", null=True, blank=True)

    # Source — helpful for Odoo-pushed notifications
    source = models.CharField(
        "Source",
        max_length=20,
        choices=[("SYSTEM", "System"), ("ODOO", "Odoo")],
        default="SYSTEM",
    )

    created_at = models.DateTimeField("Created At", auto_now_add=True)

    class Meta:
        db_table = "notifications"
        verbose_name = "Notification"
        verbose_name_plural = "Notifications"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["user", "is_read", "-created_at"]),
            models.Index(fields=["user", "notification_type"]),
        ]

    def __str__(self):
        return (
            f"{self.user.email} — {self.title} ({'Read' if self.is_read else 'Unread'})"
        )

    def mark_read(self):
        """Mark notification as read"""
        if not self.is_read:
            self.is_read = True
            self.read_at = timezone.now()
            self.save(update_fields=["is_read", "read_at"])

    @classmethod
    def create_for_user(
        cls,
        user,
        notification_type,
        title,
        message,
        priority=None,
        loan_application=None,
        loan=None,
        source="SYSTEM",
    ):
        """Convenience factory used across the codebase"""
        return cls.objects.create(
            user=user,
            notification_type=notification_type,
            title=title,
            message=message,
            priority=priority or cls.MEDIUM,
            loan_application=loan_application,
            loan=loan,
            source=source,
        )


class LoanDocument(models.Model):
    """
    Loan Document Model
    Manages uploaded documents for loan applications
    """

    # Document Types
    ID_CARD = "ID_CARD"
    PAYSLIP = "PAYSLIP"
    BANK_STATEMENT = "BANK_STATEMENT"
    EMPLOYMENT_LETTER = "EMPLOYMENT_LETTER"
    GUARANTOR_ID = "GUARANTOR_ID"
    OTHER = "OTHER"

    DOCUMENT_TYPE_CHOICES = [
        (ID_CARD, "ID Card/Passport"),
        (PAYSLIP, "Payslip"),
        (BANK_STATEMENT, "Bank Statement"),
        (EMPLOYMENT_LETTER, "Employment Letter"),
        (GUARANTOR_ID, "Guarantor ID"),
        (OTHER, "Other"),
    ]

    application = models.ForeignKey(
        LoanApplication, on_delete=models.CASCADE, related_name="documents"
    )
    document_type = models.CharField(
        "Document Type", max_length=20, choices=DOCUMENT_TYPE_CHOICES
    )
    document_file = models.FileField(
        "Document File", upload_to="loan_documents/%Y/%m/%d/"
    )
    description = models.CharField("Description", max_length=200, blank=True)

    # Validation
    is_validated = models.BooleanField("Validated", default=False)
    validated_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="validated_documents",
    )
    validated_at = models.DateTimeField("Validated At", null=True, blank=True)

    # Upload Details
    uploaded_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, related_name="uploaded_documents"
    )

    # Odoo Sync Status (Odoo Alignment)
    odoo_document_id = models.PositiveIntegerField(
        "Odoo Document ID",
        null=True,
        blank=True,
        help_text="ID of the corresponding alba.loan.document record in Odoo"
    )
    ODOO_SYNC_PENDING = "PENDING"
    ODOO_SYNC_SUCCESS = "SUCCESS"
    ODOO_SYNC_FAILED = "FAILED"
    
    ODOO_SYNC_STATUS_CHOICES = [
        (ODOO_SYNC_PENDING, "Pending"),
        (ODOO_SYNC_SUCCESS, "Success"),
        (ODOO_SYNC_FAILED, "Failed"),
    ]
    
    odoo_sync_status = models.CharField(
        "Odoo Sync Status",
        max_length=20,
        choices=ODOO_SYNC_STATUS_CHOICES,
        default=ODOO_SYNC_PENDING,
        help_text="Status of document sync to Odoo"
    )
    odoo_sync_error = models.TextField(
        "Odoo Sync Error",
        blank=True,
        help_text="Error message if sync to Odoo failed"
    )
    odoo_last_sync_at = models.DateTimeField(
        "Last Odoo Sync At",
        null=True,
        blank=True,
        help_text="Timestamp of last sync attempt to Odoo"
    )

    # Timestamps
    created_at = models.DateTimeField("Created At", auto_now_add=True)

    class Meta:
        db_table = "loan_documents"
        verbose_name = "Loan Document"
        verbose_name_plural = "Loan Documents"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["application", "document_type"]),
            models.Index(fields=["is_validated"]),
        ]

    def __str__(self):
        return f"{self.get_document_type_display()} - {self.application.application_number}"


class WebhookDelivery(models.Model):
    """
    Audit record for every inbound Odoo webhook delivery.
    Used for idempotency (duplicate detection) and operational monitoring.
    """

    STATUS_CHOICES = [
        ("processing", "Processing"),
        ("success", "Success"),
        ("error", "Error"),
        ("unhandled", "Unhandled Event"),
    ]

    delivery_id = models.CharField(
        "Delivery ID",
        max_length=128,
        unique=True,
        db_index=True,
        help_text="X-Alba-Delivery UUID sent by Odoo in the webhook envelope",
    )
    event_type = models.CharField("Event Type", max_length=128)
    status = models.CharField(
        "Processing Status",
        max_length=20,
        choices=STATUS_CHOICES,
        default="processing",
        db_index=True,
    )
    processing_detail = models.TextField("Processing Detail", blank=True)
    raw_body = models.TextField("Raw Request Body", blank=True)
    remote_ip = models.CharField("Remote IP", max_length=64, blank=True)
    odoo_timestamp = models.DateTimeField("Odoo Event Timestamp", null=True, blank=True)
    received_at = models.DateTimeField("Received At", auto_now_add=True, db_index=True)

    class Meta:
        db_table = "webhook_deliveries"
        verbose_name = "Webhook Delivery"
        verbose_name_plural = "Webhook Deliveries"
        ordering = ["-received_at"]
        indexes = [
            models.Index(fields=["event_type", "-received_at"]),
            models.Index(fields=["status", "-received_at"]),
        ]

    def __str__(self):
        return f"{self.event_type} [{self.delivery_id[:8]}…] — {self.status}"
