"""
Loans Models: Products, Applications, Disbursements, Repayments, Credit Scoring
Comprehensive loan lifecycle management with automated accounting integration
"""
from decimal import Decimal
from django.db import models
from django.core.validators import MinValueValidator, MaxValueValidator
from django.core.exceptions import ValidationError
from django.utils import timezone
from dateutil.relativedelta import relativedelta
from phonenumber_field.modelfields import PhoneNumberField
from apps.core.models import User


class LoanProduct(models.Model):
    """
    Loan Product Configuration
    
    Defines different types of loans offered (Salary Advance, Business Loan, Asset Financing)
    with comprehensive configuration for interest calculation, fees, penalties, and requirements.
    
    Field Mapping (API-friendly names):
    - interest_method → interest_type (flat, reducing_balance)
    - processing_fee_percentage → processing_fee_percent
    - late_payment_penalty_percentage → penalty_rate
    - default_repayment_frequency → repayment_frequency (weekly, monthly, etc.)
    
    Examples:
        # Salary Advance Product
        product = LoanProduct.objects.create(
            name="Salary Advance",
            code="SAL-ADV",
            interest_rate=Decimal('12.00'),
            interest_method='FLAT',
            processing_fee_percentage=Decimal('2.00'),
            created_by=user,
        )
    """
    # Interest calculation methods
    INTEREST_METHOD_CHOICES = [
        ('FLAT', 'Flat Rate'),  # Interest on original principal
        ('REDUCING_BALANCE', 'Reducing Balance'),  # Interest on outstanding balance
    ]
    
    # Repayment schedule frequencies
    REPAYMENT_FREQUENCY_CHOICES = [
        ('WEEKLY', 'Weekly'),
        ('FORTNIGHTLY', 'Fortnightly'),
        ('MONTHLY', 'Monthly'),
        ('QUARTERLY', 'Quarterly'),
    ]
    
    # Basic Information
    name = models.CharField(
        max_length=200,
        db_index=True,
        help_text="Product name (e.g., 'Salary Advance', 'Business Loan')"
    )
    code = models.CharField(
        max_length=20,
        unique=True,
        db_index=True,
        help_text="Unique product code (e.g., 'SAL-ADV', 'BUS-001')"
    )
    description = models.TextField(
        help_text="Detailed product description"
    )
    
    # Interest Configuration
    interest_rate = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.00')), MaxValueValidator(Decimal('100.00'))],
        db_index=True,
        help_text='Annual interest rate percentage (0.00 - 100.00)'
    )
    interest_method = models.CharField(
        max_length=20,
        choices=INTEREST_METHOD_CHOICES,
        default='REDUCING_BALANCE',
        db_index=True,
        help_text='Interest calculation method (FLAT or REDUCING_BALANCE)'
    )
    
    # Loan Amount Limits
    minimum_amount = models.DecimalField(
        max_digits=20,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.00'))],
        help_text='Minimum loan amount allowed'
    )
    maximum_amount = models.DecimalField(
        max_digits=20,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.00'))],
        help_text='Maximum loan amount allowed'
    )
    
    # Loan Term Limits (in months)
    minimum_term_months = models.IntegerField(
        validators=[MinValueValidator(1)],
        help_text='Minimum loan term in months'
    )
    maximum_term_months = models.IntegerField(
        validators=[MinValueValidator(1)],
        help_text='Maximum loan term in months'
    )
    
    # Processing Fees
    processing_fee_percentage = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal('0.00'),
        validators=[MinValueValidator(Decimal('0.00')), MaxValueValidator(Decimal('100.00'))],
        help_text='Processing fee as percentage of loan amount'
    )
    processing_fee_fixed = models.DecimalField(
        max_digits=20,
        decimal_places=2,
        default=Decimal('0.00'),
        validators=[MinValueValidator(Decimal('0.00'))],
        help_text='Fixed processing fee amount'
    )
    
    # Penalty Configuration
    late_payment_penalty_percentage = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal('5.00'),
        validators=[MinValueValidator(Decimal('0.00')), MaxValueValidator(Decimal('100.00'))],
        help_text='Late payment penalty as percentage'
    )
    grace_period_days = models.IntegerField(
        default=3,
        validators=[MinValueValidator(0)],
        help_text='Number of days grace period before penalty applies'
    )
    
    # Repayment Settings
    default_repayment_frequency = models.CharField(
        max_length=20,
        choices=REPAYMENT_FREQUENCY_CHOICES,
        default='MONTHLY',
        db_index=True,
        help_text='Default repayment frequency (WEEKLY, MONTHLY, etc.)'
    )
    
    # Requirements
    requires_guarantor = models.BooleanField(
        default=False,
        help_text='Whether this product requires a guarantor'
    )
    requires_collateral = models.BooleanField(
        default=False,
        help_text='Whether this product requires collateral'
    )
    requires_employer_verification = models.BooleanField(
        default=False,
        help_text='Whether employment verification is required'
    )
    minimum_guarantors = models.IntegerField(
        default=0,
        validators=[MinValueValidator(0)],
        help_text='Minimum number of guarantors required (if applicable)'
    )
    
    # GL Account Mapping (for automatic journal entries)
    loan_receivable_account = models.ForeignKey(
        'accounting.Account',
        on_delete=models.PROTECT,
        related_name='loan_products_receivable',
        help_text='GL Account for loan receivables (Asset account)',
        null=True,
        blank=True,
    )
    interest_income_account = models.ForeignKey(
        'accounting.Account',
        on_delete=models.PROTECT,
        related_name='loan_products_interest',
        help_text='GL Account for interest income (Income account)',
        null=True,
        blank=True,
    )
    fee_income_account = models.ForeignKey(
        'accounting.Account',
        on_delete=models.PROTECT,
        related_name='loan_products_fees',
        help_text='GL Account for fee income (Income account)',
        null=True,
        blank=True,
    )
    penalty_income_account = models.ForeignKey(
        'accounting.Account',
        on_delete=models.PROTECT,
        related_name='loan_products_penalties',
        help_text='GL Account for penalty income (Income account)',
        null=True,
        blank=True,
    )
    
    # Status and Audit
    is_active = models.BooleanField(
        default=True,
        db_index=True,
        help_text='Whether this product is currently active for new loans'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(
        User,
        on_delete=models.PROTECT,
        related_name='created_loan_products'
    )
    
    class Meta:
        db_table = 'loans_products'
        verbose_name = 'Loan Product'
        verbose_name_plural = 'Loan Products'
        ordering = ['name']
        indexes = [
            models.Index(fields=['name']),
            models.Index(fields=['code']),
            models.Index(fields=['is_active']),
            models.Index(fields=['interest_method', 'is_active']),
            models.Index(fields=['default_repayment_frequency']),
            models.Index(fields=['-created_at']),
        ]
    
    def __str__(self):
        return f"{self.name} ({self.code})"
    
    def clean(self):
        """Validate loan product configuration"""
        super().clean()
        
        # Validate minimum is less than maximum amount
        if self.minimum_amount and self.maximum_amount:
            if self.minimum_amount > self.maximum_amount:
                raise ValidationError({
                    'minimum_amount': 'Minimum amount cannot be greater than maximum amount'
                })
        
        # Validate minimum is less than maximum term
        if self.minimum_term_months and self.maximum_term_months:
            if self.minimum_term_months > self.maximum_term_months:
                raise ValidationError({
                    'minimum_term_months': 'Minimum term cannot be greater than maximum term'
                })
        
        # Validate interest rate is reasonable
        if self.interest_rate > Decimal('50.00'):
            raise ValidationError({
                'interest_rate': 'Interest rate seems unusually high (> 50%). Please verify.'
            })
        
        # Validate processing fee total doesn't exceed 100%
        if self.processing_fee_percentage > Decimal('20.00'):
            raise ValidationError({
                'processing_fee_percentage': 'Processing fee percentage seems unusually high (> 20%). Please verify.'
            })
        
        # Validate penalty rate is reasonable
        if self.late_payment_penalty_percentage > Decimal('20.00'):
            raise ValidationError({
                'late_payment_penalty_percentage': 'Penalty rate seems unusually high (> 20%). Please verify.'
            })
        
        # Validate guarantor requirements
        if self.requires_guarantor and self.minimum_guarantors < 1:
            raise ValidationError({
                'minimum_guarantors': 'Minimum guarantors must be at least 1 when guarantor is required'
            })
        
        # Validate GL account mapping if provided
        if self.loan_receivable_account:
            if self.loan_receivable_account.account_type.name != 'ASSET':
                raise ValidationError({
                    'loan_receivable_account': 'Loan receivable account must be an ASSET account'
                })
        
        if self.interest_income_account:
            if self.interest_income_account.account_type.name != 'INCOME':
                raise ValidationError({
                    'interest_income_account': 'Interest income account must be an INCOME account'
                })
        
        if self.fee_income_account:
            if self.fee_income_account.account_type.name != 'INCOME':
                raise ValidationError({
                    'fee_income_account': 'Fee income account must be an INCOME account'
                })
        
        if self.penalty_income_account:
            if self.penalty_income_account.account_type.name != 'INCOME':
                raise ValidationError({
                    'penalty_income_account': 'Penalty income account must be an INCOME account'
                })
    
    def save(self, *args, **kwargs):
        """Override save to run validation"""
        self.full_clean()
        super().save(*args, **kwargs)
    
    # Property aliases for API/external use (matches user's requested field names)
    @property
    def interest_type(self):
        """Alias for interest_method (API-friendly name)"""
        return self.interest_method.lower() if self.interest_method else None
    
    @property
    def processing_fee_percent(self):
        """Alias for processing_fee_percentage (API-friendly name)"""
        return self.processing_fee_percentage
    
    @property
    def penalty_rate(self):
        """Alias for late_payment_penalty_percentage (API-friendly name)"""
        return self.late_payment_penalty_percentage
    
    @property
    def repayment_frequency(self):
        """Alias for default_repayment_frequency (API-friendly name)"""
        return self.default_repayment_frequency.lower() if self.default_repayment_frequency else None
    
    def calculate_processing_fee(self, loan_amount):
        """
        Calculate total processing fee for a given loan amount
        
        Args:
            loan_amount: Decimal - Principal loan amount
            
        Returns:
            Decimal - Total processing fee (percentage + fixed)
        """
        if loan_amount < 0:
            raise ValueError("Loan amount cannot be negative")
        
        percentage_fee = loan_amount * (self.processing_fee_percentage / Decimal('100'))
        return percentage_fee + self.processing_fee_fixed
    
    def calculate_flat_interest(self, loan_amount, term_months):
        """
        Calculate total interest using flat rate method
        
        Args:
            loan_amount: Decimal - Principal amount
            term_months: int - Loan term in months
            
        Returns:
            Decimal - Total interest for entire loan term
        """
        annual_interest = loan_amount * (self.interest_rate / Decimal('100'))
        total_interest = annual_interest * (Decimal(term_months) / Decimal('12'))
        return total_interest
    
    def calculate_monthly_payment(self, loan_amount, term_months):
        """
        Calculate monthly payment amount
        
        Args:
            loan_amount: Decimal - Principal amount
            term_months: int - Loan term in months
            
        Returns:
            Decimal - Monthly payment amount
        """
        if self.interest_method == 'FLAT':
            total_interest = self.calculate_flat_interest(loan_amount, term_months)
            total_repayment = loan_amount + total_interest
            return total_repayment / Decimal(term_months)
        else:
            # Reducing balance (EMI formula)
            if self.interest_rate == 0:
                return loan_amount / Decimal(term_months)
            
            monthly_rate = (self.interest_rate / Decimal('100')) / Decimal('12')
            numerator = loan_amount * monthly_rate * ((1 + monthly_rate) ** term_months)
            denominator = ((1 + monthly_rate) ** term_months) - 1
            
            return numerator / denominator if denominator != 0 else loan_amount / Decimal(term_months)
    
    def is_amount_valid(self, amount):
        """Check if loan amount is within product limits"""
        return self.minimum_amount <= amount <= self.maximum_amount
    
    def is_term_valid(self, term_months):
        """Check if loan term is within product limits"""
        return self.minimum_term_months <= term_months <= self.maximum_term_months
    
    def get_active_loans_count(self):
        """Get count of active loans using this product"""
        return self.loans.filter(status__in=['PENDING', 'APPROVED', 'DISBURSED', 'ACTIVE']).count()
    
    def can_be_deactivated(self):
        """Check if product can be safely deactivated"""
        active_count = self.get_active_loans_count()
        return active_count == 0


class Customer(models.Model):
    """
    Customer/Borrower Information
    """
    GENDER_CHOICES = [
        ('MALE', 'Male'),
        ('FEMALE', 'Female'),
        ('OTHER', 'Other'),
    ]
    
    MARITAL_STATUS_CHOICES = [
        ('SINGLE', 'Single'),
        ('MARRIED', 'Married'),
        ('DIVORCED', 'Divorced'),
        ('WIDOWED', 'Widowed'),
    ]
    
    # Personal Information
    customer_number = models.CharField(max_length=20, unique=True, db_index=True)
    first_name = models.CharField(max_length=100)
    last_name = models.CharField(max_length=100)
    other_names = models.CharField(max_length=100, blank=True)
    date_of_birth = models.DateField()
    gender = models.CharField(max_length=10, choices=GENDER_CHOICES)
    marital_status = models.CharField(max_length=20, choices=MARITAL_STATUS_CHOICES)
    
    # Identification
    national_id = models.CharField(max_length=20, unique=True)
    passport_number = models.CharField(max_length=20, blank=True)
    kra_pin = models.CharField(max_length=20, blank=True, verbose_name='KRA PIN')
    
    # Contact Information
    phone_number = PhoneNumberField()
    alternate_phone = PhoneNumberField(blank=True)
    email = models.EmailField()
    
    # Address
    physical_address = models.TextField()
    postal_address = models.CharField(max_length=200, blank=True)
    city = models.CharField(max_length=100)
    county = models.CharField(max_length=100)
    
    # Employment/Business Information
    employment_status = models.CharField(
        max_length=20,
        choices=[
            ('EMPLOYED', 'Employed'),
            ('SELF_EMPLOYED', 'Self Employed'),
            ('BUSINESS', 'Business Owner'),
            ('UNEMPLOYED', 'Unemployed'),
        ]
    )
    employer_name = models.CharField(max_length=200, blank=True)
    employer_phone = PhoneNumberField(blank=True)
    employer_address = models.TextField(blank=True)
    occupation = models.CharField(max_length=100, blank=True)
    monthly_income = models.DecimalField(
        max_digits=20,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.00'))]
    )
    
    # KYC Documents
    id_document = models.FileField(upload_to='kyc/ids/', blank=True)
    proof_of_residence = models.FileField(upload_to='kyc/residence/', blank=True)
    payslip = models.FileField(upload_to='kyc/payslips/', blank=True)
    bank_statement = models.FileField(upload_to='kyc/statements/', blank=True)
    
    # Customer Status & KYC Verification (Bank Security)
    kyc_status = models.CharField(
        max_length=20,
        choices=[
            ('PENDING', 'Pending Verification'),
            ('UNDER_REVIEW', 'Under Review'),
            ('VERIFIED', 'Verified'),
            ('REJECTED', 'Rejected'),
        ],
        default='PENDING',
        db_index=True
    )
    kyc_verified_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='verified_customers'
    )
    kyc_verified_at = models.DateTimeField(null=True, blank=True)
    kyc_notes = models.TextField(blank=True, help_text='KYC verification notes')
    
    email_verified = models.BooleanField(default=False)
    email_verified_at = models.DateTimeField(null=True, blank=True)
    
    is_active = models.BooleanField(default=True)
    is_blacklisted = models.BooleanField(default=False)
    blacklist_reason = models.TextField(blank=True)
    
    # Linked User Account (for portal access)
    user = models.OneToOneField(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='customer_profile')
    
    # Audit
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(User, on_delete=models.PROTECT, related_name='created_customers')
    
    class Meta:
        db_table = 'loans_customers'
        verbose_name = 'Customer'
        verbose_name_plural = 'Customers'
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.customer_number} - {self.first_name} {self.last_name}"
    
    def get_full_name(self):
        return f"{self.first_name} {self.other_names} {self.last_name}".strip()
    
    def get_age(self):
        today = timezone.now().date()
        return today.year - self.date_of_birth.year - ((today.month, today.day) < (self.date_of_birth.month, self.date_of_birth.day))


class LoanApplication(models.Model):
    """
    Loan Application with Workflow Management
    """
    STATUS_CHOICES = [
        ('DRAFT', 'Draft'),
        ('SUBMITTED', 'Submitted'),
        ('UNDER_REVIEW', 'Under Review'),
        ('CREDIT_SCORING', 'Credit Scoring'),
        ('PENDING_VERIFICATION', 'Pending Verification'),
        ('PENDING_APPROVAL', 'Pending Approval'),
        ('APPROVED', 'Approved'),
        ('REJECTED', 'Rejected'),
        ('DISBURSED', 'Disbursed'),
        ('CANCELLED', 'Cancelled'),
    ]
    
    application_number = models.CharField(max_length=50, unique=True, db_index=True)
    customer = models.ForeignKey(Customer, on_delete=models.PROTECT, related_name='loan_applications')
    loan_product = models.ForeignKey(LoanProduct, on_delete=models.PROTECT, related_name='applications')
    
    # Loan Details
    requested_amount = models.DecimalField(max_digits=20, decimal_places=2, validators=[MinValueValidator(Decimal('0.01'))])
    approved_amount = models.DecimalField(max_digits=20, decimal_places=2, null=True, blank=True)
    loan_term_months = models.IntegerField(validators=[MinValueValidator(1)])
    repayment_frequency = models.CharField(max_length=20, choices=LoanProduct.REPAYMENT_FREQUENCY_CHOICES)
    purpose = models.TextField()
    
    # Status and Workflow
    status = models.CharField(max_length=30, choices=STATUS_CHOICES, default='DRAFT', db_index=True)
    current_stage = models.CharField(max_length=50, blank=True)
    
    # Credit Scoring
    credit_score = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    credit_score_date = models.DateTimeField(null=True, blank=True)
    credit_assessment = models.TextField(blank=True)
    
    # Guarantor Information (if required)
    guarantor_name = models.CharField(max_length=200, blank=True)
    guarantor_phone = PhoneNumberField(blank=True)
    guarantor_email = models.EmailField(blank=True)
    guarantor_id_number = models.CharField(max_length=20, blank=True)
    guarantor_verified = models.BooleanField(default=False)
    guarantor_verified_at = models.DateTimeField(null=True, blank=True)
    
    # Employer Verification (if required)
    employer_verified = models.BooleanField(default=False)
    employer_verification_date = models.DateTimeField(null=True, blank=True)
    employer_verification_notes = models.TextField(blank=True)
    
    # Approval/Rejection
    reviewed_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='reviewed_applications')
    reviewed_at = models.DateTimeField(null=True, blank=True)
    review_notes = models.TextField(blank=True)
    
    approved_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='approved_applications')
    approved_at = models.DateTimeField(null=True, blank=True)
    approval_notes = models.TextField(blank=True)
    
    rejection_reason = models.TextField(blank=True)
    rejected_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='rejected_applications')
    rejected_at = models.DateTimeField(null=True, blank=True)
    
    # Audit
    submitted_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(User, on_delete=models.PROTECT, related_name='created_applications')
    
    class Meta:
        db_table = 'loans_applications'
        verbose_name = 'Loan Application'
        verbose_name_plural = 'Loan Applications'
        ordering = ['-created_at']
        permissions = [
            ('can_approve_loans', 'Can approve loan applications'),
            ('can_reject_loans', 'Can reject loan applications'),
        ]
    
    def __str__(self):
        return f"{self.application_number} - {self.customer.get_full_name()}"
    
    def clean(self):
        """Validate application"""
        if self.requested_amount < self.loan_product.minimum_amount:
            raise ValidationError(f'Requested amount below minimum: {self.loan_product.minimum_amount}')
        
        if self.requested_amount > self.loan_product.maximum_amount:
            raise ValidationError(f'Requested amount exceeds maximum: {self.loan_product.maximum_amount}')


class Loan(models.Model):
    """
    Active Loan Account
    Created after approval and disbursement
    """
    STATUS_CHOICES = [
        ('PENDING_DISBURSEMENT', 'Pending Disbursement'),
        ('ACTIVE', 'Active'),
        ('OVERDUE', 'Overdue'),
        ('NPL', 'Non-Performing Loan'),
        ('CLOSED', 'Closed'),
        ('WRITTEN_OFF', 'Written Off'),
    ]
    
    loan_number = models.CharField(max_length=50, unique=True, db_index=True)
    application = models.OneToOneField(LoanApplication, on_delete=models.PROTECT, related_name='loan')
    customer = models.ForeignKey(Customer, on_delete=models.PROTECT, related_name='loans')
    loan_product = models.ForeignKey(LoanProduct, on_delete=models.PROTECT, related_name='loans')
    
    # Loan Terms
    principal_amount = models.DecimalField(max_digits=20, decimal_places=2, validators=[MinValueValidator(Decimal('0.01'))])
    interest_rate = models.DecimalField(max_digits=5, decimal_places=2)
    interest_method = models.CharField(max_length=20, choices=LoanProduct.INTEREST_METHOD_CHOICES)
    loan_term_months = models.IntegerField()
    repayment_frequency = models.CharField(max_length=20)
    
    # Fees
    processing_fee = models.DecimalField(max_digits=20, decimal_places=2, default=Decimal('0.00'))
    
    # Calculated Fields
    total_interest = models.DecimalField(max_digits=20, decimal_places=2, default=Decimal('0.00'))
    total_amount = models.DecimalField(max_digits=20, decimal_places=2)  # Principal + Interest + Fees
    monthly_installment = models.DecimalField(max_digits=20, decimal_places=2)
    
    # Disbursement
    disbursed_amount = models.DecimalField(max_digits=20, decimal_places=2, null=True, blank=True)
    disbursement_date = models.DateField(null=True, blank=True)
    disbursed_by = models.ForeignKey(
        User,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='disbursed_loans'
    )
    disbursement_method = models.CharField(
        max_length=20,
        choices=[
            ('BANK_TRANSFER', 'Bank Transfer'),
            ('MPESA', 'M-Pesa'),
            ('CASH', 'Cash'),
            ('CHEQUE', 'Cheque'),
        ],
        blank=True
    )
    disbursement_reference = models.CharField(max_length=100, blank=True)
    
    # Repayment Schedule
    first_repayment_date = models.DateField(null=True, blank=True)
    last_repayment_date = models.DateField(null=True, blank=True)
    
    # Balance Tracking
    outstanding_principal = models.DecimalField(max_digits=20, decimal_places=2)
    outstanding_interest = models.DecimalField(max_digits=20, decimal_places=2, default=Decimal('0.00'))
    outstanding_fees = models.DecimalField(max_digits=20, decimal_places=2, default=Decimal('0.00'))
    outstanding_penalties = models.DecimalField(max_digits=20, decimal_places=2, default=Decimal('0.00'))
    total_outstanding = models.DecimalField(max_digits=20, decimal_places=2)
    
    total_paid = models.DecimalField(max_digits=20, decimal_places=2, default=Decimal('0.00'))
    
    # Loan Status
    status = models.CharField(max_length=30, choices=STATUS_CHOICES, default='PENDING_DISBURSEMENT', db_index=True)
    days_overdue = models.IntegerField(default=0)
    
    # Closure
    closed_at = models.DateTimeField(null=True, blank=True)
    closed_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='closed_loans'
    )
    closure_notes = models.TextField(blank=True)
    
    # Assigned Officer
    loan_officer = models.ForeignKey(
        User,
        on_delete=models.PROTECT,
        related_name='managed_loans'
    )
    
    # Audit
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'loans'
        verbose_name = 'Loan'
        verbose_name_plural = 'Loans'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['status', '-created_at']),
            models.Index(fields=['customer', 'status']),
        ]
    
    def __str__(self):
        return f"{self.loan_number} - {self.customer.get_full_name()}"
    
    def update_outstanding_balance(self):
        """Recalculate outstanding balances"""
        self.total_outstanding = (
            self.outstanding_principal +
            self.outstanding_interest +
            self.outstanding_fees +
            self.outstanding_penalties
        )
        self.save()
    
    def is_overdue(self):
        """Check if loan has overdue payments"""
        return self.days_overdue > self.loan_product.grace_period_days
    
    def is_npl(self):
        """Check if loan qualifies as NPL"""
        from django.conf import settings
        return self.days_overdue >= settings.LOAN_NPL_THRESHOLD_DAYS


class RepaymentSchedule(models.Model):
    """
    Loan Repayment Schedule
    Generated at loan disbursement
    """
    loan = models.ForeignKey(Loan, on_delete=models.CASCADE, related_name='repayment_schedule')
    installment_number = models.IntegerField()
    due_date = models.DateField(db_index=True)
    
    # Amounts Due
    principal_due = models.DecimalField(max_digits=20, decimal_places=2)
    interest_due = models.DecimalField(max_digits=20, decimal_places=2)
    total_due = models.DecimalField(max_digits=20, decimal_places=2)
    
    # Amounts Paid
    principal_paid = models.DecimalField(max_digits=20, decimal_places=2, default=Decimal('0.00'))
    interest_paid = models.DecimalField(max_digits=20, decimal_places=2, default=Decimal('0.00'))
    penalty_paid = models.DecimalField(max_digits=20, decimal_places=2, default=Decimal('0.00'))
    total_paid = models.DecimalField(max_digits=20, decimal_places=2, default=Decimal('0.00'))
    
    # Status
    is_paid = models.BooleanField(default=False)
    paid_date = models.DateField(null=True, blank=True)
    days_overdue = models.IntegerField(default=0)
    
    class Meta:
        db_table = 'loans_repayment_schedule'
        verbose_name = 'Repayment Schedule'
        verbose_name_plural = 'Repayment Schedules'
        ordering = ['loan', 'installment_number']
        unique_together = ['loan', 'installment_number']
    
    def __str__(self):
        return f"{self.loan.loan_number} - Installment {self.installment_number}"


class Payment(models.Model):
    """
    Customer Payments
    Records all payments received from customers
    """
    PAYMENT_METHOD_CHOICES = [
        ('MPESA', 'M-Pesa'),
        ('BANK_TRANSFER', 'Bank Transfer'),
        ('CASH', 'Cash'),
        ('CHEQUE', 'Cheque'),
        ('STANDING_ORDER', 'Standing Order'),
    ]
    
    payment_number = models.CharField(max_length=50, unique=True, db_index=True)
    loan = models.ForeignKey(Loan, on_delete=models.PROTECT, related_name='payments')
    customer = models.ForeignKey(Customer, on_delete=models.PROTECT, related_name='payments')
    
    # Payment Details
    payment_date = models.DateField(db_index=True)
    amount = models.DecimalField(max_digits=20, decimal_places=2, validators=[MinValueValidator(Decimal('0.01'))])
    payment_method = models.CharField(max_length=20, choices=PAYMENT_METHOD_CHOICES)
    reference_number = models.CharField(max_length=100, blank=True)
    
    # Allocation
    principal_paid = models.DecimalField(max_digits=20, decimal_places=2, default=Decimal('0.00'))
    interest_paid = models.DecimalField(max_digits=20, decimal_places=2, default=Decimal('0.00'))
    fees_paid = models.DecimalField(max_digits=20, decimal_places=2, default=Decimal('0.00'))
    penalty_paid = models.DecimalField(max_digits=20, decimal_places=2, default=Decimal('0.00'))
    
    # Status
    is_reconciled = models.BooleanField(default=False)
    reconciled_at = models.DateTimeField(null=True, blank=True)
    reconciled_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='reconciled_payments'
    )
    
    notes = models.TextField(blank=True)
    
    # Audit
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(User, on_delete=models.PROTECT, related_name='recorded_payments')
    
    class Meta:
        db_table = 'loans_payments'
        verbose_name = 'Payment'
        verbose_name_plural = 'Payments'
        ordering = ['-payment_date']
    
    def __str__(self):
        return f"{self.payment_number} - {self.amount}"


class CreditScore(models.Model):
    """
    Credit Scoring Results
    """
    application = models.OneToOneField(LoanApplication, on_delete=models.CASCADE, related_name='credit_score_detail')
    score = models.DecimalField(max_digits=5, decimal_places=2)
    
    # Scoring Components
    income_score = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal('0.00'))
    employment_score = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal('0.00'))
    credit_history_score = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal('0.00'))
    existing_obligations_score = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal('0.00'))
    
    # Recommendation
    recommendation = models.CharField(
        max_length=20,
        choices=[
            ('APPROVE', 'Approve'),
            ('CONDITIONAL', 'Conditional Approval'),
            ('REJECT', 'Reject'),
        ]
    )
    notes = models.TextField(blank=True)
    
    scored_at = models.DateTimeField(auto_now_add=True)
    scored_by = models.ForeignKey(User, on_delete=models.PROTECT, related_name='credit_scores')
    
    class Meta:
        db_table = 'loans_credit_scores'
        verbose_name = 'Credit Score'
        verbose_name_plural = 'Credit Scores'
    
    def __str__(self):
        return f"{self.application.application_number} - Score: {self.score}"


# =============================================================================
# ENHANCED LOAN MODELS (Production-Ready, Simplified Structure)
# =============================================================================
# These models provide a streamlined loan management system with comprehensive
# validation, proper indexing, and reducing balance schedule generation.
# They reference User directly for simplified workflows.
# =============================================================================


class DirectLoan(models.Model):
    """
    Direct Loan Model (Simplified, Production-Ready)
    
    Streamlined loan account that references User directly without intermediary
    Customer or LoanApplication models. Suitable for simpler loan workflows.
    
    Features:
    - Direct User foreign key relationship
    - Simple status workflow (pending → approved → disbursed → closed/defaulted)
    - Comprehensive validation with clean() method
    - Proper database indexing for performance
    - Decimal precision for all monetary amounts
    - Outstanding principal tracking
    - Integration-ready with LoanProduct and repayment schedules
    
    Status Workflow:
        PENDING → APPROVED → DISBURSED → CLOSED
                                      ↓
                                  DEFAULTED
    
    Example:
        loan = DirectLoan.objects.create(
            customer=user,
            loan_product=product,
            principal_amount=Decimal('50000.00'),
            interest_rate=Decimal('12.00'),
            term_months=12,
            disbursement_date=timezone.now().date(),
            status='DISBURSED'
        )
    """
    STATUS_CHOICES = [
        ('PENDING', 'Pending'),
        ('APPROVED', 'Approved'),
        ('DISBURSED', 'Disbursed'),
        ('CLOSED', 'Closed'),
        ('DEFAULTED', 'Defaulted'),
    ]
    
    # Relationships
    customer = models.ForeignKey(
        User,
        on_delete=models.PROTECT,
        related_name='direct_loans',
        db_index=True,
        help_text='Borrower (User account)'
    )
    loan_product = models.ForeignKey(
        LoanProduct,
        on_delete=models.PROTECT,
        related_name='direct_loans',
        db_index=True,
        help_text='Associated loan product configuration'
    )
    
    # Loan Terms
    principal_amount = models.DecimalField(
        max_digits=20,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.01'))],
        help_text='Principal loan amount'
    )
    interest_rate = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.00')), MaxValueValidator(Decimal('100.00'))],
        help_text='Annual interest rate percentage (0.00 - 100.00)'
    )
    term_months = models.PositiveIntegerField(
        validators=[MinValueValidator(1)],
        help_text='Loan term in months'
    )
    
    # Disbursement
    disbursement_date = models.DateField(
        null=True,
        blank=True,
        db_index=True,
        help_text='Date when loan was disbursed'
    )
    
    # Status and Balance
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='PENDING',
        db_index=True,
        help_text='Current loan status'
    )
    outstanding_principal = models.DecimalField(
        max_digits=20,
        decimal_places=2,
        default=Decimal('0.00'),
        validators=[MinValueValidator(Decimal('0.00'))],
        help_text='Remaining principal balance'
    )
    
    # Audit Fields
    created_at = models.DateTimeField(
        auto_now_add=True,
        db_index=True,
        help_text='Timestamp when loan was created'
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        help_text='Timestamp of last update'
    )
    created_by = models.ForeignKey(
        User,
        on_delete=models.PROTECT,
        related_name='created_direct_loans',
        null=True,
        blank=True,
        help_text='User who created this loan'
    )
    
    class Meta:
        db_table = 'direct_loans'
        verbose_name = 'Direct Loan'
        verbose_name_plural = 'Direct Loans'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['customer', 'status']),
            models.Index(fields=['status', '-disbursement_date']),
            models.Index(fields=['loan_product', 'status']),
            models.Index(fields=['-created_at']),
        ]
    
    def __str__(self):
        return f"Loan #{self.pk} - {self.customer.get_full_name()} - {self.principal_amount}"
    
    def clean(self):
        """Comprehensive validation"""
        super().clean()
        errors = {}
        
        # Validate principal amount against product limits
        if self.loan_product_id:
            if self.principal_amount < self.loan_product.minimum_amount:
                errors['principal_amount'] = f'Amount below product minimum: {self.loan_product.minimum_amount}'
            
            if self.principal_amount > self.loan_product.maximum_amount:
                errors['principal_amount'] = f'Amount exceeds product maximum: {self.loan_product.maximum_amount}'
            
            # Validate term against product limits
            if self.term_months < self.loan_product.minimum_term_months:
                errors['term_months'] = f'Term below product minimum: {self.loan_product.minimum_term_months} months'
            
            if self.term_months > self.loan_product.maximum_term_months:
                errors['term_months'] = f'Term exceeds product maximum: {self.loan_product.maximum_term_months} months'
            
            # Warn if interest rate differs significantly from product rate
            if abs(self.interest_rate - self.loan_product.interest_rate) > Decimal('5.00'):
                errors['interest_rate'] = f'Interest rate differs significantly from product rate ({self.loan_product.interest_rate}%)'
        
        # Validate status transitions
        if self.pk:
            old_instance = DirectLoan.objects.filter(pk=self.pk).first()
            if old_instance:
                # Cannot change from CLOSED or DEFAULTED
                if old_instance.status in ['CLOSED', 'DEFAULTED'] and self.status != old_instance.status:
                    errors['status'] = f'Cannot change status from {old_instance.status}'
                
                # Cannot skip statuses (except for DEFAULTED from any status)
                if self.status != 'DEFAULTED':
                    valid_transitions = {
                        'PENDING': ['APPROVED', 'DEFAULTED'],
                        'APPROVED': ['DISBURSED', 'PENDING', 'DEFAULTED'],
                        'DISBURSED': ['CLOSED', 'DEFAULTED'],
                    }
                    if old_instance.status in valid_transitions:
                        if self.status not in valid_transitions[old_instance.status]:
                            errors['status'] = f'Invalid status transition from {old_instance.status} to {self.status}'
        
        # Disbursement date required for DISBURSED status
        if self.status in ['DISBURSED', 'CLOSED'] and not self.disbursement_date:
            errors['disbursement_date'] = 'Disbursement date required for disbursed/closed loans'
        
        # Outstanding principal should be initialized when disbursed
        if self.status == 'DISBURSED' and self.outstanding_principal == 0:
            # Auto-set if not manually set
            self.outstanding_principal = self.principal_amount
        
        # Outstanding principal should be zero when closed
        if self.status == 'CLOSED' and self.outstanding_principal > 0:
            errors['outstanding_principal'] = 'Outstanding principal must be zero for closed loans'
        
        if errors:
            raise ValidationError(errors)
    
    def save(self, *args, **kwargs):
        """Override save to ensure validation"""
        self.full_clean()
        super().save(*args, **kwargs)
    
    def get_total_interest(self):
        """Calculate total interest based on loan product method"""
        if self.loan_product.interest_method == 'FLAT':
            return self.loan_product.calculate_flat_interest(
                self.principal_amount,
                self.term_months
            )
        else:
            # For reducing balance, calculate from schedule
            return self.repayment_schedules.aggregate(
                total=models.Sum('interest_due')
            )['total'] or Decimal('0.00')
    
    def get_monthly_payment(self):
        """Calculate monthly payment amount"""
        return self.loan_product.calculate_monthly_payment(
            self.principal_amount,
            self.term_months
        )
    
    def get_total_repayment(self):
        """Calculate total amount to be repaid"""
        return self.principal_amount + self.get_total_interest()
    
    def get_total_paid(self):
        """Calculate total amount paid so far"""
        return self.repayment_schedules.aggregate(
            total=models.Sum('paid_amount')
        )['total'] or Decimal('0.00')
    
    def is_fully_paid(self):
        """Check if loan is fully paid"""
        return self.outstanding_principal == 0 and self.status in ['CLOSED', 'DISBURSED']
    
    def get_next_payment_due(self):
        """Get next unpaid installment"""
        return self.repayment_schedules.filter(
            is_paid=False
        ).order_by('due_date').first()


class DirectLoanRepaymentSchedule(models.Model):
    """
    Loan Repayment Schedule (Production-Ready)
    
    Individual installments for loan repayment with comprehensive tracking
    of principal, interest, penalties, and payment status.
    
    Features:
    - Decimal precision for all amounts
    - Separate tracking of principal_due, interest_due, penalty_due
    - Paid amount tracking with is_paid flag
    - Database indexes for performance
    - Validation to prevent negative amounts
    - Integration with DirectLoan model
    
    Example:
        schedule = DirectLoanRepaymentSchedule.objects.create(
            loan=loan,
            due_date=date(2024, 3, 15),
            principal_due=Decimal('4166.67'),
            interest_due=Decimal('500.00'),
            penalty_due=Decimal('0.00'),
            paid_amount=Decimal('0.00'),
            is_paid=False
        )
    """
    # Relationships
    loan = models.ForeignKey(
        DirectLoan,
        on_delete=models.CASCADE,
        related_name='repayment_schedules',
        db_index=True,
        help_text='Associated loan'
    )
    
    # Schedule Details
    installment_number = models.PositiveIntegerField(
        help_text='Installment sequence number (1, 2, 3, ...)'
    )
    due_date = models.DateField(
        db_index=True,
        help_text='Date when payment is due'
    )
    
    # Amounts Due
    principal_due = models.DecimalField(
        max_digits=20,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.00'))],
        help_text='Principal amount due for this installment'
    )
    interest_due = models.DecimalField(
        max_digits=20,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.00'))],
        help_text='Interest amount due for this installment'
    )
    penalty_due = models.DecimalField(
        max_digits=20,
        decimal_places=2,
        default=Decimal('0.00'),
        validators=[MinValueValidator(Decimal('0.00'))],
        help_text='Penalty amount due (for late payment)'
    )
    
    # Payment Tracking
    paid_amount = models.DecimalField(
        max_digits=20,
        decimal_places=2,
        default=Decimal('0.00'),
        validators=[MinValueValidator(Decimal('0.00'))],
        help_text='Total amount paid for this installment'
    )
    is_paid = models.BooleanField(
        default=False,
        db_index=True,
        help_text='Whether installment is fully paid'
    )
    paid_date = models.DateField(
        null=True,
        blank=True,
        help_text='Date when installment was fully paid'
    )
    
    # Audit Fields
    created_at = models.DateTimeField(
        auto_now_add=True,
        help_text='Timestamp when schedule was created'
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        help_text='Timestamp of last update'
    )
    
    class Meta:
        db_table = 'direct_loan_repayment_schedules'
        verbose_name = 'Direct Loan Repayment Schedule'
        verbose_name_plural = 'Direct Loan Repayment Schedules'
        ordering = ['loan', 'installment_number']
        unique_together = [['loan', 'installment_number']]
        indexes = [
            models.Index(fields=['loan', 'due_date']),
            models.Index(fields=['loan', 'is_paid']),
            models.Index(fields=['due_date', 'is_paid']),
            models.Index(fields=['-due_date']),
        ]
    
    def __str__(self):
        return f"Loan #{self.loan.pk} - Installment {self.installment_number} - Due: {self.due_date}"
    
    def clean(self):
        """Comprehensive validation"""
        super().clean()
        errors = {}
        
        # Validate paid amount doesn't exceed total due
        total_due = self.get_total_due()
        if self.paid_amount > total_due:
            errors['paid_amount'] = f'Paid amount ({self.paid_amount}) exceeds total due ({total_due})'
        
        # Validate is_paid flag consistency
        if self.is_paid and self.paid_amount < total_due:
            errors['is_paid'] = f'Cannot mark as paid when paid amount ({self.paid_amount}) is less than total due ({total_due})'
        
        # Validate paid_date consistency
        if self.is_paid and not self.paid_date:
            errors['paid_date'] = 'Paid date required when installment is marked as paid'
        
        if not self.is_paid and self.paid_date:
            errors['paid_date'] = 'Cannot set paid date when installment is not fully paid'
        
        # Validate due date is after loan disbursement
        if self.loan_id and self.loan.disbursement_date:
            if self.due_date < self.loan.disbursement_date:
                errors['due_date'] = f'Due date cannot be before loan disbursement ({self.loan.disbursement_date})'
        
        if errors:
            raise ValidationError(errors)
    
    def save(self, *args, **kwargs):
        """Override save to ensure validation"""
        self.full_clean()
        super().save(*args, **kwargs)
    
    def get_total_due(self):
        """Calculate total amount due (principal + interest + penalty)"""
        return self.principal_due + self.interest_due + self.penalty_due
    
    def get_outstanding_amount(self):
        """Calculate remaining amount to be paid"""
        return self.get_total_due() - self.paid_amount
    
    def is_overdue(self):
        """Check if installment is overdue"""
        if self.is_paid:
            return False
        return timezone.now().date() > self.due_date
    
    def get_days_overdue(self):
        """Calculate days overdue"""
        if not self.is_overdue():
            return 0
        return (timezone.now().date() - self.due_date).days
    
    def record_payment(self, amount, payment_date=None):
        """
        Record a payment against this installment
        
        Args:
            amount: Decimal - Amount being paid
            payment_date: date - Date of payment (defaults to today)
        
        Returns:
            Decimal - Any excess amount if payment exceeds total due
        """
        if payment_date is None:
            payment_date = timezone.now().date()
        
        total_due = self.get_total_due()
        
        if amount <= 0:
            raise ValidationError('Payment amount must be positive')
        
        # Calculate new paid amount
        new_paid_amount = self.paid_amount + amount
        excess = Decimal('0.00')
        
        if new_paid_amount >= total_due:
            # Fully paid
            self.paid_amount = total_due
            self.is_paid = True
            self.paid_date = payment_date
            excess = new_paid_amount - total_due
        else:
            # Partial payment
            self.paid_amount = new_paid_amount
            self.is_paid = False
            self.paid_date = None
        
        self.save()
        return excess


# =============================================================================
# INVESTOR ACCOUNT MODELS
# =============================================================================


class InvestorAccount(models.Model):
    """
    Investor Account Model (Production-Ready)
    
    Represents an investor's account with principal balance and interest rate.
    Tracks investor deposits, withdrawals, and interest accruals.
    
    Features:
    - Decimal precision for all monetary amounts
    - Monthly interest rate tracking
    - Last interest calculation date
    - Comprehensive validation with clean() method
    - Database indexes for performance
    - Helper methods for balance calculations
    
    Example:
        account = InvestorAccount.objects.create(
            investor=user,
            principal_balance=Decimal('100000.00'),
            monthly_interest_rate=Decimal('1.50'),
            last_interest_date=date.today()
        )
    """
    # Relationships
    investor = models.ForeignKey(
        User,
        on_delete=models.PROTECT,
        related_name='investor_accounts',
        db_index=True,
        help_text='Investor (User account)'
    )
    
    # Balance and Rates
    principal_balance = models.DecimalField(
        max_digits=20,
        decimal_places=2,
        default=Decimal('0.00'),
        validators=[MinValueValidator(Decimal('0.00'))],
        help_text='Current principal balance'
    )
    monthly_interest_rate = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.00')), MaxValueValidator(Decimal('100.00'))],
        help_text='Monthly interest rate percentage (0.00 - 100.00)'
    )
    
    # Interest Tracking
    last_interest_date = models.DateField(
        null=True,
        blank=True,
        db_index=True,
        help_text='Date when interest was last calculated and credited'
    )
    
    # Audit Fields
    created_at = models.DateTimeField(
        auto_now_add=True,
        db_index=True,
        help_text='Timestamp when account was created'
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        help_text='Timestamp of last update'
    )
    
    class Meta:
        db_table = 'investor_accounts'
        verbose_name = 'Investor Account'
        verbose_name_plural = 'Investor Accounts'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['investor', '-created_at']),
            models.Index(fields=['-principal_balance']),
            models.Index(fields=['last_interest_date']),
        ]
    
    def __str__(self):
        return f"Investor Account - {self.investor.get_full_name()} - Balance: {self.principal_balance}"
    
    def clean(self):
        """Comprehensive validation"""
        super().clean()
        errors = {}
        
        # Validate principal balance is non-negative
        if self.principal_balance < 0:
            errors['principal_balance'] = 'Principal balance cannot be negative'
        
        # Validate monthly interest rate is within reasonable range
        if self.monthly_interest_rate < 0:
            errors['monthly_interest_rate'] = 'Interest rate cannot be negative'
        
        if self.monthly_interest_rate > Decimal('50.00'):
            errors['monthly_interest_rate'] = 'Monthly interest rate seems unreasonably high (>50%)'
        
        # Validate last_interest_date is not in the future
        if self.last_interest_date and self.last_interest_date > timezone.now().date():
            errors['last_interest_date'] = 'Last interest date cannot be in the future'
        
        if errors:
            raise ValidationError(errors)
    
    def save(self, *args, **kwargs):
        """Override save to ensure validation"""
        self.full_clean()
        super().save(*args, **kwargs)
    
    def get_total_deposits(self):
        """Calculate total deposits made to this account"""
        return self.transactions.filter(
            transaction_type='DEPOSIT'
        ).aggregate(
            total=models.Sum('amount')
        )['total'] or Decimal('0.00')
    
    def get_total_withdrawals(self):
        """Calculate total withdrawals from this account"""
        return self.transactions.filter(
            transaction_type='WITHDRAWAL'
        ).aggregate(
            total=models.Sum('amount')
        )['total'] or Decimal('0.00')
    
    def get_total_interest_earned(self):
        """Calculate total interest earned on this account"""
        return self.transactions.filter(
            transaction_type='INTEREST'
        ).aggregate(
            total=models.Sum('amount')
        )['total'] or Decimal('0.00')
    
    def calculate_pending_interest(self, as_of_date=None):
        """
        Calculate interest accrued since last_interest_date
        
        Args:
            as_of_date: date - Calculate interest up to this date (default: today)
        
        Returns:
            Decimal - Interest amount accrued
        """
        if as_of_date is None:
            as_of_date = timezone.now().date()
        
        # If no last_interest_date, no pending interest
        if not self.last_interest_date:
            return Decimal('0.00')
        
        # If as_of_date is before or same as last_interest_date, no pending interest
        if as_of_date <= self.last_interest_date:
            return Decimal('0.00')
        
        # Calculate number of days
        days = (as_of_date - self.last_interest_date).days
        
        # Calculate interest (simple interest for pending days)
        # Interest = Principal × (Rate/100) × (Days/30)
        monthly_rate = self.monthly_interest_rate / Decimal('100')
        interest = self.principal_balance * monthly_rate * (Decimal(days) / Decimal('30'))
        
        return interest.quantize(Decimal('0.01'), ROUND_HALF_UP)
    
    def get_account_summary(self):
        """
        Get comprehensive account summary
        
        Returns:
            dict - Account summary with all key metrics
        """
        return {
            'investor': self.investor.get_full_name(),
            'principal_balance': self.principal_balance,
            'monthly_interest_rate': self.monthly_interest_rate,
            'annual_interest_rate': self.monthly_interest_rate * Decimal('12'),
            'last_interest_date': self.last_interest_date,
            'total_deposits': self.get_total_deposits(),
            'total_withdrawals': self.get_total_withdrawals(),
            'total_interest_earned': self.get_total_interest_earned(),
            'pending_interest': self.calculate_pending_interest(),
            'account_age_days': (timezone.now().date() - self.created_at.date()).days,
            'created_at': self.created_at
        }
    
    def can_withdraw(self, amount):
        """
        Check if withdrawal amount can be processed
        
        Args:
            amount: Decimal - Withdrawal amount
        
        Returns:
            bool - True if withdrawal is allowed
        """
        return amount <= self.principal_balance and amount > 0


class InvestorTransaction(models.Model):
    """
    Investor Transaction Model (Production-Ready)
    
    Records all transactions on investor accounts including deposits,
    withdrawals, and interest accruals.
    
    Features:
    - Decimal precision for all amounts
    - Transaction type tracking (DEPOSIT, WITHDRAWAL, INTEREST)
    - Comprehensive validation with clean() method
    - Database indexes for performance
    - Audit trail with timestamps
    
    Transaction Types:
    - DEPOSIT: Investor adds funds to account
    - WITHDRAWAL: Investor removes funds from account
    - INTEREST: Interest credited to account
    
    Example:
        transaction = InvestorTransaction.objects.create(
            investor_account=account,
            transaction_type='DEPOSIT',
            amount=Decimal('50000.00'),
            transaction_date=date.today(),
            description='Initial deposit'
        )
    """
    TRANSACTION_TYPE_CHOICES = [
        ('DEPOSIT', 'Deposit'),
        ('WITHDRAWAL', 'Withdrawal'),
        ('INTEREST', 'Interest'),
    ]
    
    # Relationships
    investor_account = models.ForeignKey(
        InvestorAccount,
        on_delete=models.PROTECT,
        related_name='transactions',
        db_index=True,
        help_text='Associated investor account'
    )
    
    # Transaction Details
    transaction_type = models.CharField(
        max_length=20,
        choices=TRANSACTION_TYPE_CHOICES,
        db_index=True,
        help_text='Type of transaction'
    )
    amount = models.DecimalField(
        max_digits=20,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.01'))],
        help_text='Transaction amount (must be positive)'
    )
    transaction_date = models.DateField(
        db_index=True,
        help_text='Date when transaction occurred'
    )
    description = models.TextField(
        blank=True,
        help_text='Optional transaction description'
    )
    reference = models.CharField(
        max_length=100,
        blank=True,
        help_text='External reference (e.g., receipt number, transaction ID)'
    )
    
    # Audit Fields
    created_at = models.DateTimeField(
        auto_now_add=True,
        help_text='Timestamp when transaction was recorded'
    )
    created_by = models.ForeignKey(
        User,
        on_delete=models.PROTECT,
        related_name='created_investor_transactions',
        null=True,
        blank=True,
        help_text='User who created this transaction'
    )
    
    class Meta:
        db_table = 'investor_transactions'
        verbose_name = 'Investor Transaction'
        verbose_name_plural = 'Investor Transactions'
        ordering = ['-transaction_date', '-created_at']
        indexes = [
            models.Index(fields=['investor_account', '-transaction_date']),
            models.Index(fields=['transaction_type', '-transaction_date']),
            models.Index(fields=['-transaction_date']),
            models.Index(fields=['investor_account', 'transaction_type']),
        ]
    
    def __str__(self):
        return f"{self.get_transaction_type_display()} - {self.amount} - {self.transaction_date}"
    
    def clean(self):
        """Comprehensive validation"""
        super().clean()
        errors = {}
        
        # Validate amount is positive
        if self.amount <= 0:
            errors['amount'] = 'Transaction amount must be positive'
        
        # Validate transaction date is not in the future
        if self.transaction_date > timezone.now().date():
            errors['transaction_date'] = 'Transaction date cannot be in the future'
        
        # Validate withdrawal amount doesn't exceed balance
        if self.transaction_type == 'WITHDRAWAL' and self.investor_account_id:
            # Check if withdrawal exceeds current balance
            # Note: This is a basic check. In production, you'd want to check
            # the balance at the time of the withdrawal, considering pending transactions
            if self.amount > self.investor_account.principal_balance:
                errors['amount'] = f'Withdrawal amount ({self.amount}) exceeds account balance ({self.investor_account.principal_balance})'
        
        # Validate transaction date is not before account creation
        if self.investor_account_id:
            account_created = self.investor_account.created_at.date()
            if self.transaction_date < account_created:
                errors['transaction_date'] = f'Transaction date cannot be before account creation ({account_created})'
        
        if errors:
            raise ValidationError(errors)
    
    def save(self, *args, **kwargs):
        """Override save to ensure validation"""
        self.full_clean()
        super().save(*args, **kwargs)
    
    def get_balance_impact(self):
        """
        Get the impact of this transaction on account balance
        
        Returns:
            Decimal - Positive for deposits/interest, negative for withdrawals
        """
        if self.transaction_type in ['DEPOSIT', 'INTEREST']:
            return self.amount
        elif self.transaction_type == 'WITHDRAWAL':
            return -self.amount
        return Decimal('0.00')
    
    def is_deposit(self):
        """Check if transaction is a deposit"""
        return self.transaction_type == 'DEPOSIT'
    
    def is_withdrawal(self):
        """Check if transaction is a withdrawal"""
        return self.transaction_type == 'WITHDRAWAL'
    
    def is_interest(self):
        """Check if transaction is an interest credit"""
        return self.transaction_type == 'INTEREST'
