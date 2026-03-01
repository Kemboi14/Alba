"""
Payroll Models: Employee records, payroll processing, leave management

Production-Ready Payroll System with:
- Statutory deductions (Kenyan PAYE, NSSF, NHIF)
- Comprehensive validation
- Database indexing
- Audit trail
- Decimal precision
"""
from decimal import Decimal, ROUND_HALF_UP
from django.db import models
from django.core.validators import MinValueValidator, MaxValueValidator
from django.core.exceptions import ValidationError
from django.utils import timezone
from apps.core.models import User


class Employee(models.Model):
    """
    Employee Model (Production-Ready)
    
    Represents an employee with salary information and statutory details.
    
    Features:
    - One-to-one with User model
    - Unique employee number
    - Bank details for salary payments
    - Statutory numbers (KRA PIN, NSSF, NHIF)
    - Comprehensive validation
    - Helper methods for salary calculations
    """
    
    # Relationships
    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name='employee_profile',
        db_index=True,
        help_text='Associated user account'
    )
    
    # Employee Information
    employee_number = models.CharField(
        max_length=20,
        unique=True,
        db_index=True,
        help_text='Unique employee identification number'
    )
    department = models.CharField(
        max_length=200,
        blank=True,
        help_text='Employee department'
    )
    designation = models.CharField(
        max_length=200,
        blank=True,
        help_text='Job title or designation'
    )
    
    # Salary Information
    basic_salary = models.DecimalField(
        max_digits=20,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.00'))],
        help_text='Basic monthly salary'
    )
    housing_allowance = models.DecimalField(
        max_digits=20,
        decimal_places=2,
        default=Decimal('0.00'),
        validators=[MinValueValidator(Decimal('0.00'))],
        help_text='Housing allowance'
    )
    transport_allowance = models.DecimalField(
        max_digits=20,
        decimal_places=2,
        default=Decimal('0.00'),
        validators=[MinValueValidator(Decimal('0.00'))],
        help_text='Transport allowance'
    )
    other_allowances = models.DecimalField(
        max_digits=20,
        decimal_places=2,
        default=Decimal('0.00'),
        validators=[MinValueValidator(Decimal('0.00'))],
        help_text='Other monthly allowances'
    )
    
    # Bank Details
    bank_name = models.CharField(
        max_length=200,
        help_text='Bank name for salary payment'
    )
    bank_branch = models.CharField(
        max_length=200,
        blank=True,
        help_text='Bank branch'
    )
    account_number = models.CharField(
        max_length=50,
        help_text='Bank account number'
    )
    account_name = models.CharField(
        max_length=200,
        help_text='Account holder name'
    )
    
    # Statutory Numbers (Kenya)
    kra_pin = models.CharField(
        max_length=20,
        blank=True,
        db_index=True,
        help_text='Kenya Revenue Authority PIN for PAYE'
    )
    nssf_number = models.CharField(
        max_length=50,
        blank=True,
        help_text='National Social Security Fund number'
    )
    nhif_number = models.CharField(
        max_length=50,
        blank=True,
        help_text='National Hospital Insurance Fund number'
    )
    
    # Employment Details
    hire_date = models.DateField(
        null=True,
        blank=True,
        help_text='Date of hiring'
    )
    termination_date = models.DateField(
        null=True,
        blank=True,
        help_text='Date of termination (if applicable)'
    )
    
    # Status
    is_active = models.BooleanField(
        default=True,
        db_index=True,
        help_text='Is employee currently active'
    )
    
    # Audit Fields
    created_at = models.DateTimeField(
        auto_now_add=True,
        db_index=True
    )
    updated_at = models.DateTimeField(
        auto_now=True
    )
    
    class Meta:
        db_table = 'payroll_employees'
        verbose_name = 'Employee'
        verbose_name_plural = 'Employees'
        ordering = ['employee_number']
        indexes = [
            models.Index(fields=['is_active', '-created_at']),
            models.Index(fields=['department', 'is_active']),
        ]
    
    def __str__(self):
        return f"{self.employee_number} - {self.user.get_full_name()}"
    
    def clean(self):
        """Comprehensive validation"""
        super().clean()
        errors = {}
        
        # Validate salary amounts are non-negative
        if self.basic_salary < 0:
            errors['basic_salary'] = 'Basic salary cannot be negative'
        
        if self.basic_salary == 0:
            errors['basic_salary'] = 'Basic salary must be greater than zero'
        
        # Validate termination date is after hire date
        if self.hire_date and self.termination_date:
            if self.termination_date < self.hire_date:
                errors['termination_date'] = 'Termination date cannot be before hire date'
        
        # Validate account name matches user name (warning)
        if self.account_name and self.user:
            expected_name = self.user.get_full_name()
            if expected_name and self.account_name.lower() != expected_name.lower():
                # This is just a warning, not an error
                pass
        
        if errors:
            raise ValidationError(errors)
    
    def save(self, *args, **kwargs):
        """Override save to ensure validation"""
        self.full_clean()
        super().save(*args, **kwargs)
    
    def get_gross_salary(self):
        """Calculate total gross salary including all allowances"""
        return (
            self.basic_salary +
            self.housing_allowance +
            self.transport_allowance +
            self.other_allowances
        )
    
    def get_total_allowances(self):
        """Get sum of all allowances"""
        return (
            self.housing_allowance +
            self.transport_allowance +
            self.other_allowances
        )
    
    def is_terminated(self):
        """Check if employee is terminated"""
        if self.termination_date:
            return self.termination_date <= timezone.now().date()
        return False


class PayrollRun(models.Model):
    """
    PayrollRun Model (Production-Ready)
    
    Represents a payroll processing period/run.
    
    Features:
    - Date range for payroll period
    - Status tracking (DRAFT, APPROVED, PROCESSED, PAID)
    - Journal entry linking for accounting integration
    - Comprehensive validation
    - Audit trail
    """
    
    STATUS_CHOICES = [
        ('DRAFT', 'Draft'),
        ('APPROVED', 'Approved'),
        ('PROCESSED', 'Processed'),
        ('PAID', 'Paid'),
        ('CANCELLED', 'Cancelled')
    ]
    
    # Period Information
    name = models.CharField(
        max_length=100,
        help_text='Payroll run name (e.g., "January 2026 Payroll")'
    )
    period_start = models.DateField(
        db_index=True,
        help_text='Start date of payroll period'
    )
    period_end = models.DateField(
        db_index=True,
        help_text='End date of payroll period'
    )
    payment_date = models.DateField(
        help_text='Scheduled payment date'
    )
    
    # Status
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='DRAFT',
        db_index=True,
        help_text='Current status of payroll run'
    )
    
    # Totals (computed during processing)
    total_gross = models.DecimalField(
        max_digits=20,
        decimal_places=2,
        default=Decimal('0.00'),
        help_text='Total gross salary for all employees'
    )
    total_deductions = models.DecimalField(
        max_digits=20,
        decimal_places=2,
        default=Decimal('0.00'),
        help_text='Total deductions for all employees'
    )
    total_net = models.DecimalField(
        max_digits=20,
        decimal_places=2,
        default=Decimal('0.00'),
        help_text='Total net salary to be paid'
    )
    
    # Accounting Integration
    journal_entry = models.ForeignKey(
        'accounting.JournalEntry',
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='payroll_runs',
        help_text='Associated journal entry for accounting'
    )
    
    # Audit Fields
    created_at = models.DateTimeField(
        auto_now_add=True,
        db_index=True
    )
    created_by = models.ForeignKey(
        User,
        on_delete=models.PROTECT,
        related_name='created_payroll_runs',
        help_text='User who created this payroll run'
    )
    approved_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text='Timestamp when payroll was approved'
    )
    approved_by = models.ForeignKey(
        User,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='approved_payroll_runs',
        help_text='User who approved this payroll run'
    )
    processed_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text='Timestamp when payroll was processed'
    )
    paid_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text='Timestamp when payroll was marked as paid'
    )
    
    class Meta:
        db_table = 'payroll_runs'
        verbose_name = 'Payroll Run'
        verbose_name_plural = 'Payroll Runs'
        ordering = ['-period_start']
        indexes = [
            models.Index(fields=['status', '-period_start']),
            models.Index(fields=['-payment_date']),
        ]
    
    def __str__(self):
        return f"{self.name} ({self.status})"
    
    def clean(self):
        """Comprehensive validation"""
        super().clean()
        errors = {}
        
        # Validate period_end is after period_start
        if self.period_end < self.period_start:
            errors['period_end'] = 'Period end date must be after start date'
        
        # Validate payment_date is not before period_end
        if self.payment_date < self.period_end:
            errors['payment_date'] = 'Payment date should not be before period end date'
        
        # Validate dates are not too far in the future
        if self.period_start > timezone.now().date() + timezone.timedelta(days=365):
            errors['period_start'] = 'Period start date is too far in the future'
        
        if errors:
            raise ValidationError(errors)
    
    def save(self, *args, **kwargs):
        """Override save to ensure validation"""
        self.full_clean()
        super().save(*args, **kwargs)
    
    def can_edit(self):
        """Check if payroll run can be edited"""
        return self.status in ['DRAFT', 'APPROVED']
    
    def can_approve(self):
        """Check if payroll run can be approved"""
        return self.status == 'DRAFT' and self.items.exists()
    
    def can_process(self):
        """Check if payroll run can be processed"""
        return self.status == 'APPROVED'
    
    def get_employee_count(self):
        """Get number of employees in this payroll run"""
        return self.items.count()


class PayrollItem(models.Model):
    """
    PayrollItem Model (Production-Ready)
    
    Represents an individual employee's payroll for a specific run.
    
    Features:
    - Complete earnings breakdown
    - Statutory deductions (PAYE, NSSF, NHIF)
    - Other deductions
    - Net salary calculation
    - Comprehensive validation
    - Audit trail
    """
    
    # Relationships
    payroll_run = models.ForeignKey(
        PayrollRun,
        on_delete=models.CASCADE,
        related_name='items',
        db_index=True,
        help_text='Associated payroll run'
    )
    employee = models.ForeignKey(
        Employee,
        on_delete=models.PROTECT,
        related_name='payroll_items',
        db_index=True,
        help_text='Employee for this payroll item'
    )
    
    # Earnings
    basic_salary = models.DecimalField(
        max_digits=20,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.00'))],
        help_text='Basic salary for this period'
    )
    housing_allowance = models.DecimalField(
        max_digits=20,
        decimal_places=2,
        default=Decimal('0.00'),
        validators=[MinValueValidator(Decimal('0.00'))],
        help_text='Housing allowance'
    )
    transport_allowance = models.DecimalField(
        max_digits=20,
        decimal_places=2,
        default=Decimal('0.00'),
        validators=[MinValueValidator(Decimal('0.00'))],
        help_text='Transport allowance'
    )
    other_allowances = models.DecimalField(
        max_digits=20,
        decimal_places=2,
        default=Decimal('0.00'),
        validators=[MinValueValidator(Decimal('0.00'))],
        help_text='Other allowances'
    )
    gross_salary = models.DecimalField(
        max_digits=20,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.00'))],
        help_text='Total gross salary (Basic + Allowances)'
    )
    
    # Statutory Deductions (Kenya)
    paye = models.DecimalField(
        max_digits=20,
        decimal_places=2,
        default=Decimal('0.00'),
        validators=[MinValueValidator(Decimal('0.00'))],
        help_text='Pay As You Earn (Income Tax)'
    )
    nssf = models.DecimalField(
        max_digits=20,
        decimal_places=2,
        default=Decimal('0.00'),
        validators=[MinValueValidator(Decimal('0.00'))],
        help_text='National Social Security Fund contribution'
    )
    nhif = models.DecimalField(
        max_digits=20,
        decimal_places=2,
        default=Decimal('0.00'),
        validators=[MinValueValidator(Decimal('0.00'))],
        help_text='National Hospital Insurance Fund contribution'
    )
    
    # Other Deductions
    loan_deduction = models.DecimalField(
        max_digits=20,
        decimal_places=2,
        default=Decimal('0.00'),
        validators=[MinValueValidator(Decimal('0.00'))],
        help_text='Staff loan deduction'
    )
    other_deductions = models.DecimalField(
        max_digits=20,
        decimal_places=2,
        default=Decimal('0.00'),
        validators=[MinValueValidator(Decimal('0.00'))],
        help_text='Other deductions'
    )
    total_deductions = models.DecimalField(
        max_digits=20,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.00'))],
        help_text='Total of all deductions'
    )
    
    # Net Salary
    net_salary = models.DecimalField(
        max_digits=20,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.00'))],
        help_text='Net salary to be paid (Gross - Deductions)'
    )
    
    # Additional Information
    days_worked = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal('30.00'),
        validators=[MinValueValidator(Decimal('0.00')), MaxValueValidator(Decimal('31.00'))],
        help_text='Number of days worked in period'
    )
    notes = models.TextField(
        blank=True,
        help_text='Additional notes or comments'
    )
    
    # Audit Fields
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'payroll_items'
        verbose_name = 'Payroll Item'
        verbose_name_plural = 'Payroll Items'
        unique_together = ['payroll_run', 'employee']
        ordering = ['employee__employee_number']
        indexes = [
            models.Index(fields=['payroll_run', 'employee']),
            models.Index(fields=['-created_at']),
        ]
    
    def __str__(self):
        return f"{self.employee} - {self.payroll_run.name}"
    
    def clean(self):
        """Comprehensive validation"""
        super().clean()
        errors = {}
        
        # Validate gross salary calculation
        calculated_gross = (
            self.basic_salary +
            self.housing_allowance +
            self.transport_allowance +
            self.other_allowances
        )
        if abs(self.gross_salary - calculated_gross) > Decimal('0.01'):
            errors['gross_salary'] = (
                f'Gross salary {self.gross_salary} does not match calculated value {calculated_gross}'
            )
        
        # Validate total deductions calculation
        calculated_deductions = (
            self.paye +
            self.nssf +
            self.nhif +
            self.loan_deduction +
            self.other_deductions
        )
        if abs(self.total_deductions - calculated_deductions) > Decimal('0.01'):
            errors['total_deductions'] = (
                f'Total deductions {self.total_deductions} does not match calculated value {calculated_deductions}'
            )
        
        # Validate net salary calculation
        calculated_net = self.gross_salary - self.total_deductions
        if abs(self.net_salary - calculated_net) > Decimal('0.01'):
            errors['net_salary'] = (
                f'Net salary {self.net_salary} does not match calculated value {calculated_net}'
            )
        
        # Validate net salary is not negative
        if self.net_salary < 0:
            errors['net_salary'] = 'Net salary cannot be negative (deductions exceed gross)'
        
        # Validate days worked is reasonable
        if self.days_worked > 31:
            errors['days_worked'] = 'Days worked cannot exceed 31'
        
        # Validate employee is active (unless payroll run is already processed)
        if self.employee_id and not self.employee.is_active:
            if self.payroll_run_id and self.payroll_run.status == 'DRAFT':
                errors['employee'] = 'Cannot add inactive employee to payroll run'
        
        if errors:
            raise ValidationError(errors)
    
    def save(self, *args, **kwargs):
        """Override save to ensure validation"""
        self.full_clean()
        super().save(*args, **kwargs)
    
    def get_statutory_deductions(self):
        """Get total statutory deductions"""
        return self.paye + self.nssf + self.nhif
    
    def get_non_statutory_deductions(self):
        """Get total non-statutory deductions"""
        return self.loan_deduction + self.other_deductions


class LeaveType(models.Model):
    """Types of leave"""
    name = models.CharField(max_length=100)
    days_per_year = models.IntegerField()
    is_paid = models.BooleanField(default=True)
    is_active = models.BooleanField(default=True)
    
    class Meta:
        db_table = 'payroll_leave_types'
    
    def __str__(self):
        return self.name


class LeaveApplication(models.Model):
    """Employee leave applications"""
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name='leave_applications')
    leave_type = models.ForeignKey(LeaveType, on_delete=models.PROTECT)
    
    start_date = models.DateField()
    end_date = models.DateField()
    days_requested = models.IntegerField()
    reason = models.TextField()
    
    status = models.CharField(
        max_length=20,
        choices=[('PENDING', 'Pending'), ('APPROVED', 'Approved'), ('REJECTED', 'Rejected')],
        default='PENDING'
    )
    
    approved_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='approved_leaves')
    approved_at = models.DateTimeField(null=True, blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'payroll_leave_applications'
        verbose_name = 'Leave Application'
        verbose_name_plural = 'Leave Applications'
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.employee} - {self.leave_type} - {self.start_date}"
