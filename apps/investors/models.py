"""
Investors Models: Portfolio management with compound interest
"""
from decimal import Decimal
from django.db import models
from django.core.validators import MinValueValidator, MaxValueValidator
from django.utils import timezone
from apps.core.models import User


class Investor(models.Model):
    """
    Investor Information
    """
    investor_number = models.CharField(max_length=20, unique=True, db_index=True)
    name = models.CharField(max_length=200)
    email = models.EmailField()
    phone_number = models.CharField(max_length=20)
    address = models.TextField(blank=True)
    
    # KYC
    id_number = models.CharField(max_length=50, unique=True)
    kra_pin = models.CharField(max_length=20, blank=True)
    
    # Bank Details
    bank_name = models.CharField(max_length=200, blank=True)
    bank_account_number = models.CharField(max_length=50, blank=True)
    bank_branch = models.CharField(max_length=100, blank=True)
    
    # Portal Access
    user = models.OneToOneField(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='investor_profile')
    
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(User, on_delete=models.PROTECT, related_name='created_investors')
    
    class Meta:
        db_table = 'investors'
        verbose_name = 'Investor'
        verbose_name_plural = 'Investors'
    
    def __str__(self):
        return f"{self.investor_number} - {self.name}"


class InvestmentAccount(models.Model):
    """
    Investor Account with compound interest calculation
    """
    account_number = models.CharField(max_length=50, unique=True, db_index=True)
    investor = models.ForeignKey(Investor, on_delete=models.PROTECT, related_name='accounts')
    
    # Investment Terms
    monthly_interest_rate = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.00')), MaxValueValidator(Decimal('100.00'))],
        help_text='Monthly interest rate percentage (e.g., 2.00 for 2%)'
    )
    
    # Balances
    opening_balance = models.DecimalField(max_digits=20, decimal_places=2, default=Decimal('0.00'))
    current_balance = models.DecimalField(max_digits=20, decimal_places=2, default=Decimal('0.00'))
    total_interest_earned = models.DecimalField(max_digits=20, decimal_places=2, default=Decimal('0.00'))
    
    # Account Status
    is_active = models.BooleanField(default=True)
    opened_date = models.DateField()
    closed_date = models.DateField(null=True, blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'investors_accounts'
        verbose_name = 'Investment Account'
        verbose_name_plural = 'Investment Accounts'
    
    def __str__(self):
        return f"{self.account_number} - {self.investor.name}"


class InvestmentTransaction(models.Model):
    """
    Investment Transactions: Deposits, Withdrawals, Interest
    """
    TRANSACTION_TYPE_CHOICES = [
        ('DEPOSIT', 'Deposit'),
        ('WITHDRAWAL', 'Withdrawal'),
        ('INTEREST', 'Interest Accrual'),
    ]
    
    account = models.ForeignKey(InvestmentAccount, on_delete=models.PROTECT, related_name='transactions')
    transaction_number = models.CharField(max_length=50, unique=True)
    transaction_type = models.CharField(max_length=20, choices=TRANSACTION_TYPE_CHOICES)
    
    amount = models.DecimalField(max_digits=20, decimal_places=2, validators=[MinValueValidator(Decimal('0.01'))])
    balance_after = models.DecimalField(max_digits=20, decimal_places=2)
    
    transaction_date = models.DateField(db_index=True)
    description = models.TextField()
    reference = models.CharField(max_length=100, blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(User, on_delete=models.PROTECT, related_name='investor_transactions')
    
    class Meta:
        db_table = 'investors_transactions'
        verbose_name = 'Investment Transaction'
        verbose_name_plural = 'Investment Transactions'
        ordering = ['-transaction_date', '-created_at']
    
    def __str__(self):
        return f"{self.transaction_number} - {self.transaction_type}"


class MonthlyInterestCalculation(models.Model):
    """
    Monthly Interest Calculation Log
    Tracks interest accrual with withdrawal penalties
    """
    account = models.ForeignKey(InvestmentAccount, on_delete=models.CASCADE, related_name='monthly_calculations')
    month = models.DateField(help_text='First day of the month')
    
    opening_balance = models.DecimalField(max_digits=20, decimal_places=2)
    had_withdrawal = models.BooleanField(default=False)
    interest_rate = models.DecimalField(max_digits=5, decimal_places=2)
    interest_earned = models.DecimalField(max_digits=20, decimal_places=2)
    closing_balance = models.DecimalField(max_digits=20, decimal_places=2)
    
    notes = models.TextField(blank=True)
    calculated_at = models.DateTimeField(auto_now_add=True)
    calculated_by = models.ForeignKey(User, on_delete=models.PROTECT)
    
    class Meta:
        db_table = 'investors_monthly_calculations'
        verbose_name = 'Monthly Interest Calculation'
        verbose_name_plural = 'Monthly Interest Calculations'
        unique_together = ['account', 'month']
        ordering = ['-month']
    
    def __str__(self):
        return f"{self.account.account_number} - {self.month.strftime('%B %Y')}"


class InvestorStatement(models.Model):
    """
    Monthly Investor Statements
    """
    account = models.ForeignKey(InvestmentAccount, on_delete=models.CASCADE, related_name='statements')
    statement_number = models.CharField(max_length=50, unique=True)
    period_start = models.DateField()
    period_end = models.DateField()
    
    opening_balance = models.DecimalField(max_digits=20, decimal_places=2)
    closing_balance = models.DecimalField(max_digits=20, decimal_places=2)
    total_deposits = models.DecimalField(max_digits=20, decimal_places=2, default=Decimal('0.00'))
    total_withdrawals = models.DecimalField(max_digits=20, decimal_places=2, default=Decimal('0.00'))
    interest_earned = models.DecimalField(max_digits=20, decimal_places=2, default=Decimal('0.00'))
    
    pdf_file = models.FileField(upload_to='investor_statements/', blank=True)
    generated_at = models.DateTimeField(auto_now_add=True)
    sent_at = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        db_table = 'investors_statements'
        verbose_name = 'Investor Statement'
        verbose_name_plural = 'Investor Statements'
        ordering = ['-period_end']
    
    def __str__(self):
        return f"{self.statement_number} - {self.account.investor.name}"
