"""
Payroll Service - Production-Ready

Handles payroll processing with:
- Statutory deduction calculations (Kenyan PAYE, NSSF, NHIF)
- Automatic journal entry posting
- Transaction safety
- Full audit trail

All operations are atomic and production-safe.
"""

from decimal import Decimal, ROUND_HALF_UP
from datetime import date
from django.db import transaction
from django.core.exceptions import ValidationError
from django.utils import timezone
from apps.payroll.models import Employee, PayrollRun, PayrollItem
from apps.accounting.services import AccountingService
from apps.accounting.models import Account


class StatutoryCalculator:
    """
    Statutory Deduction Calculator for Kenya
    
    Calculates PAYE (Income Tax), NSSF, and NHIF based on Kenyan tax laws.
    Rates are as of 2026 (adjust as needed for actual rates).
    """
    
    # NSSF Rates (2026) - Tier system
    NSSF_TIER_1_LIMIT = Decimal('7000.00')
    NSSF_TIER_2_LIMIT = Decimal('36000.00')
    NSSF_RATE = Decimal('0.06')  # 6% employee contribution
    
    # NHIF Rates (2026) - Based on gross salary bands
    NHIF_RATES = [
        (Decimal('0.00'), Decimal('5999.99'), Decimal('150.00')),
        (Decimal('6000.00'), Decimal('7999.99'), Decimal('300.00')),
        (Decimal('8000.00'), Decimal('11999.99'), Decimal('400.00')),
        (Decimal('12000.00'), Decimal('14999.99'), Decimal('500.00')),
        (Decimal('15000.00'), Decimal('19999.99'), Decimal('600.00')),
        (Decimal('20000.00'), Decimal('24999.99'), Decimal('750.00')),
        (Decimal('25000.00'), Decimal('29999.99'), Decimal('850.00')),
        (Decimal('30000.00'), Decimal('34999.99'), Decimal('900.00')),
        (Decimal('35000.00'), Decimal('39999.99'), Decimal('950.00')),
        (Decimal('40000.00'), Decimal('44999.99'), Decimal('1000.00')),
        (Decimal('45000.00'), Decimal('49999.99'), Decimal('1100.00')),
        (Decimal('50000.00'), Decimal('59999.99'), Decimal('1200.00')),
        (Decimal('60000.00'), Decimal('69999.99'), Decimal('1300.00')),
        (Decimal('70000.00'), Decimal('79999.99'), Decimal('1400.00')),
        (Decimal('80000.00'), Decimal('89999.99'), Decimal('1500.00')),
        (Decimal('90000.00'), Decimal('99999.99'), Decimal('1600.00')),
        (Decimal('100000.00'), Decimal('999999999.99'), Decimal('1700.00')),
    ]
    
    # PAYE Tax Bands (2026) - Progressive tax rates
    PAYE_BANDS = [
        (Decimal('0.00'), Decimal('24000.00'), Decimal('0.10')),      # 10% on first 24,000
        (Decimal('24001.00'), Decimal('32333.00'), Decimal('0.25')),  # 25% on next 8,333
        (Decimal('32334.00'), Decimal('999999999.99'), Decimal('0.30')),  # 30% on amount above
    ]
    
    # Personal Relief (monthly)
    PERSONAL_RELIEF = Decimal('2400.00')  # KES 2,400 per month
    
    @staticmethod
    def calculate_nssf(gross_salary: Decimal) -> Decimal:
        """
        Calculate NSSF contribution (employee portion)
        
        NSSF is calculated on pensionable pay with tier limits:
        - Tier 1: Up to KES 7,000 at 6%
        - Tier 2: KES 7,001 to 36,000 at 6%
        
        Args:
            gross_salary: Decimal - Gross monthly salary
        
        Returns:
            Decimal - NSSF contribution amount
        """
        if gross_salary <= 0:
            return Decimal('0.00')
        
        # Tier 1 contribution
        tier1_pensionable = min(gross_salary, StatutoryCalculator.NSSF_TIER_1_LIMIT)
        tier1_contribution = tier1_pensionable * StatutoryCalculator.NSSF_RATE
        
        # Tier 2 contribution (if salary exceeds tier 1 limit)
        tier2_contribution = Decimal('0.00')
        if gross_salary > StatutoryCalculator.NSSF_TIER_1_LIMIT:
            tier2_pensionable = min(
                gross_salary - StatutoryCalculator.NSSF_TIER_1_LIMIT,
                StatutoryCalculator.NSSF_TIER_2_LIMIT - StatutoryCalculator.NSSF_TIER_1_LIMIT
            )
            tier2_contribution = tier2_pensionable * StatutoryCalculator.NSSF_RATE
        
        total_nssf = tier1_contribution + tier2_contribution
        return total_nssf.quantize(Decimal('0.01'), ROUND_HALF_UP)
    
    @staticmethod
    def calculate_nhif(gross_salary: Decimal) -> Decimal:
        """
        Calculate NHIF contribution based on salary bands
        
        Args:
            gross_salary: Decimal - Gross monthly salary
        
        Returns:
            Decimal - NHIF contribution amount
        """
        if gross_salary <= 0:
            return Decimal('0.00')
        
        # Find applicable rate band
        for min_salary, max_salary, contribution in StatutoryCalculator.NHIF_RATES:
            if min_salary <= gross_salary <= max_salary:
                return contribution
        
        # Default to highest band if not found
        return StatutoryCalculator.NHIF_RATES[-1][2]
    
    @staticmethod
    def calculate_paye(gross_salary: Decimal, nssf: Decimal) -> Decimal:
        """
        Calculate PAYE (Income Tax) using progressive tax bands
        
        Taxable income = Gross salary - NSSF
        Tax is calculated progressively on bands, then personal relief is deducted.
        
        Args:
            gross_salary: Decimal - Gross monthly salary
            nssf: Decimal - NSSF contribution (tax-deductible)
        
        Returns:
            Decimal - PAYE tax amount
        """
        # Calculate taxable income (gross minus NSSF)
        taxable_income = gross_salary - nssf
        
        if taxable_income <= 0:
            return Decimal('0.00')
        
        # Calculate tax progressively through bands
        tax = Decimal('0.00')
        remaining_income = taxable_income
        
        for i, (band_start, band_end, rate) in enumerate(StatutoryCalculator.PAYE_BANDS):
            if remaining_income <= 0:
                break
            
            # Determine income in this band
            if i == 0:
                # First band starts at 0
                band_income = min(remaining_income, band_end - band_start + Decimal('1.00'))
            else:
                # For subsequent bands
                prev_band_end = StatutoryCalculator.PAYE_BANDS[i-1][1]
                band_size = band_end - band_start + Decimal('1.00')
                
                if taxable_income <= prev_band_end:
                    band_income = Decimal('0.00')
                else:
                    income_above_prev = taxable_income - prev_band_end
                    band_income = min(income_above_prev, band_size)
            
            # Calculate tax for this band
            band_tax = band_income * rate
            tax += band_tax
            remaining_income -= band_income
        
        # Apply personal relief
        tax_after_relief = tax - StatutoryCalculator.PERSONAL_RELIEF
        
        # PAYE cannot be negative
        final_paye = max(tax_after_relief, Decimal('0.00'))
        
        return final_paye.quantize(Decimal('0.01'), ROUND_HALF_UP)


class PayrollService:
    """
    Payroll Service - Production-Ready
    
    Handles complete payroll processing including:
    - Payroll run creation
    - Statutory deduction calculation
    - Net salary computation
    - Automatic journal entry posting
    - Transaction safety
    """
    
    @staticmethod
    @transaction.atomic()
    def create_payroll_run(
        name: str,
        period_start: date,
        period_end: date,
        payment_date: date,
        created_by
    ) -> PayrollRun:
        """
        Create a new payroll run
        
        Args:
            name: str - Payroll run name
            period_start: date - Start of payroll period
            period_end: date - End of payroll period
            payment_date: date - Scheduled payment date
            created_by: User - User creating the payroll run
        
        Returns:
            PayrollRun - Created payroll run
        
        Raises:
            ValidationError: If validation fails
        """
        payroll_run = PayrollRun.objects.create(
            name=name,
            period_start=period_start,
            period_end=period_end,
            payment_date=payment_date,
            status='DRAFT',
            created_by=created_by
        )
        
        return payroll_run
    
    @staticmethod
    @transaction.atomic()
    def add_employee_to_payroll(
        payroll_run_id: int,
        employee_id: int,
        days_worked: Decimal = Decimal('30.00')
    ) -> PayrollItem:
        """
        Add an employee to a payroll run with calculated deductions
        
        This method:
        1. Gets employee salary information
        2. Calculates statutory deductions (NSSF, NHIF, PAYE)
        3. Calculates net salary
        4. Creates PayrollItem record
        
        Args:
            payroll_run_id: int - ID of payroll run
            employee_id: int - ID of employee
            days_worked: Decimal - Number of days worked (default: 30)
        
        Returns:
            PayrollItem - Created payroll item
        
        Raises:
            ValidationError: If validation fails
        """
        # Get payroll run and employee with locks
        try:
            payroll_run = PayrollRun.objects.select_for_update().get(id=payroll_run_id)
        except PayrollRun.DoesNotExist:
            raise ValidationError(f"Payroll run with ID {payroll_run_id} does not exist")
        
        try:
            employee = Employee.objects.select_for_update().get(id=employee_id)
        except Employee.DoesNotExist:
            raise ValidationError(f"Employee with ID {employee_id} does not exist")
        
        # Validate payroll run can be edited
        if not payroll_run.can_edit():
            raise ValidationError(f"Cannot add employees to payroll run with status {payroll_run.status}")
        
        # Validate employee is active
        if not employee.is_active:
            raise ValidationError(f"Cannot add inactive employee {employee.employee_number} to payroll")
        
        # Check if employee already in this payroll run
        if PayrollItem.objects.filter(payroll_run=payroll_run, employee=employee).exists():
            raise ValidationError(f"Employee {employee.employee_number} already exists in this payroll run")
        
        # Calculate salary components
        basic_salary = employee.basic_salary
        housing_allowance = employee.housing_allowance
        transport_allowance = employee.transport_allowance
        other_allowances = employee.other_allowances
        gross_salary = employee.get_gross_salary()
        
        # Calculate statutory deductions
        nssf = StatutoryCalculator.calculate_nssf(gross_salary)
        nhif = StatutoryCalculator.calculate_nhif(gross_salary)
        paye = StatutoryCalculator.calculate_paye(gross_salary, nssf)
        
        # Get other deductions (e.g., loan deductions)
        loan_deduction = Decimal('0.00')  # TODO: Implement loan deduction lookup
        other_deductions = Decimal('0.00')
        
        # Calculate totals
        total_deductions = paye + nssf + nhif + loan_deduction + other_deductions
        net_salary = gross_salary - total_deductions
        
        # Create payroll item
        payroll_item = PayrollItem.objects.create(
            payroll_run=payroll_run,
            employee=employee,
            basic_salary=basic_salary,
            housing_allowance=housing_allowance,
            transport_allowance=transport_allowance,
            other_allowances=other_allowances,
            gross_salary=gross_salary,
            paye=paye,
            nssf=nssf,
            nhif=nhif,
            loan_deduction=loan_deduction,
            other_deductions=other_deductions,
            total_deductions=total_deductions,
            net_salary=net_salary,
            days_worked=days_worked
        )
        
        return payroll_item
    
    @staticmethod
    @transaction.atomic()
    def add_all_active_employees(payroll_run_id: int) -> dict:
        """
        Add all active employees to a payroll run
        
        Args:
            payroll_run_id: int - ID of payroll run
        
        Returns:
            dict with results summary
        """
        results = {
            'total_employees': 0,
            'added': 0,
            'skipped': 0,
            'failed': 0,
            'details': []
        }
        
        active_employees = Employee.objects.filter(is_active=True)
        results['total_employees'] = active_employees.count()
        
        for employee in active_employees:
            try:
                payroll_item = PayrollService.add_employee_to_payroll(
                    payroll_run_id=payroll_run_id,
                    employee_id=employee.id
                )
                results['added'] += 1
                results['details'].append({
                    'employee_number': employee.employee_number,
                    'name': employee.user.get_full_name(),
                    'status': 'added',
                    'net_salary': payroll_item.net_salary
                })
            except ValidationError as e:
                if 'already exists' in str(e):
                    results['skipped'] += 1
                    results['details'].append({
                        'employee_number': employee.employee_number,
                        'name': employee.user.get_full_name(),
                        'status': 'skipped',
                        'reason': 'Already in payroll run'
                    })
                else:
                    results['failed'] += 1
                    results['details'].append({
                        'employee_number': employee.employee_number,
                        'name': employee.user.get_full_name(),
                        'status': 'failed',
                        'error': str(e)
                    })
        
        return results
    
    @staticmethod
    @transaction.atomic()
    def process_payroll_with_accounting(
        payroll_run_id: int,
        fiscal_year_id: int,
        description: str = None
    ) -> dict:
        """
        Process payroll and post accounting journal entry
        
        This method:
        1. Validates payroll run can be processed
        2. Calculates totals
        3. Creates multi-line journal entry:
           - Debit: Salary Expense (gross)
           - Credit: PAYE Payable
           - Credit: NSSF Payable
           - Credit: NHIF Payable
           - Credit: Net Salary Payable
        4. Updates payroll run status
        
        Args:
            payroll_run_id: int - ID of payroll run
            fiscal_year_id: int - ID of fiscal year for accounting
            description: str - Optional description
        
        Returns:
            dict with processing results
        
        Raises:
            ValidationError: If validation fails
        """
        # Get payroll run with lock
        try:
            payroll_run = PayrollRun.objects.select_for_update().get(id=payroll_run_id)
        except PayrollRun.DoesNotExist:
            raise ValidationError(f"Payroll run with ID {payroll_run_id} does not exist")
        
        # Validate can process
        if payroll_run.status != 'APPROVED':
            raise ValidationError(f"Payroll run must be APPROVED to process. Current status: {payroll_run.status}")
        
        # Validate has items
        if not payroll_run.items.exists():
            raise ValidationError("Payroll run has no employee items")
        
        # Calculate totals
        total_gross = Decimal('0.00')
        total_paye = Decimal('0.00')
        total_nssf = Decimal('0.00')
        total_nhif = Decimal('0.00')
        total_other_deductions = Decimal('0.00')
        total_net = Decimal('0.00')
        
        for item in payroll_run.items.all():
            total_gross += item.gross_salary
            total_paye += item.paye
            total_nssf += item.nssf
            total_nhif += item.nhif
            total_other_deductions += item.loan_deduction + item.other_deductions
            total_net += item.net_salary
        
        total_deductions = total_paye + total_nssf + total_nhif + total_other_deductions
        
        # Get accounting service
        accounting_service = AccountingService()
        
        # Get required accounts
        try:
            salary_expense_account = Account.objects.get(
                code='5100',  # Salary Expense
                account_type='EXPENSE'
            )
        except Account.DoesNotExist:
            raise ValidationError("Salary Expense account (5100) not found. Please create it first.")
        
        try:
            paye_payable_account = Account.objects.get(
                code='2100',  # PAYE Payable
                account_type='LIABILITY'
            )
        except Account.DoesNotExist:
            raise ValidationError("PAYE Payable account (2100) not found. Please create it first.")
        
        try:
            nssf_payable_account = Account.objects.get(
                code='2110',  # NSSF Payable
                account_type='LIABILITY'
            )
        except Account.DoesNotExist:
            raise ValidationError("NSSF Payable account (2110) not found. Please create it first.")
        
        try:
            nhif_payable_account = Account.objects.get(
                code='2120',  # NHIF Payable
                account_type='LIABILITY'
            )
        except Account.DoesNotExist:
            raise ValidationError("NHIF Payable account (2120) not found. Please create it first.")
        
        try:
            salary_payable_account = Account.objects.get(
                code='2200',  # Salary Payable
                account_type='LIABILITY'
            )
        except Account.DoesNotExist:
            raise ValidationError("Salary Payable account (2200) not found. Please create it first.")
        
        # Prepare journal entry lines
        journal_lines = [
            {
                'account': salary_expense_account,
                'debit': total_gross,
                'credit': Decimal('0.00'),
                'description': f'Salary expense for {payroll_run.name}'
            },
            {
                'account': paye_payable_account,
                'debit': Decimal('0.00'),
                'credit': total_paye,
                'description': f'PAYE deductions for {payroll_run.name}'
            },
            {
                'account': nssf_payable_account,
                'debit': Decimal('0.00'),
                'credit': total_nssf,
                'description': f'NSSF deductions for {payroll_run.name}'
            },
            {
                'account': nhif_payable_account,
                'debit': Decimal('0.00'),
                'credit': total_nhif,
                'description': f'NHIF deductions for {payroll_run.name}'
            },
            {
                'account': salary_payable_account,
                'debit': Decimal('0.00'),
                'credit': total_net,
                'description': f'Net salary payable for {payroll_run.name}'
            }
        ]
        
        # Create journal entry
        entry_description = description or f'Payroll processing for {payroll_run.name}'
        
        journal_entry = accounting_service.create_journal_entry(
            fiscal_year_id=fiscal_year_id,
            entry_date=payroll_run.payment_date,
            description=entry_description,
            reference=f'PAYROLL-{payroll_run.id}',
            lines=journal_lines
        )
        
        # Update payroll run
        payroll_run.total_gross = total_gross
        payroll_run.total_deductions = total_deductions
        payroll_run.total_net = total_net
        payroll_run.journal_entry = journal_entry
        payroll_run.status = 'PROCESSED'
        payroll_run.processed_at = timezone.now()
        payroll_run.save(update_fields=[
            'total_gross', 'total_deductions', 'total_net',
            'journal_entry', 'status', 'processed_at'
        ])
        
        return {
            'success': True,
            'payroll_run_id': payroll_run.id,
            'payroll_run_name': payroll_run.name,
            'employee_count': payroll_run.items.count(),
            'total_gross': total_gross,
            'total_paye': total_paye,
            'total_nssf': total_nssf,
            'total_nhif': total_nhif,
            'total_other_deductions': total_other_deductions,
            'total_deductions': total_deductions,
            'total_net': total_net,
            'journal_entry_id': journal_entry.id,
            'message': f'Payroll processed successfully with journal entry {journal_entry.entry_number}'
        }
    
    @staticmethod
    @transaction.atomic()
    def approve_payroll_run(
        payroll_run_id: int,
        approved_by
    ) -> PayrollRun:
        """
        Approve a payroll run (changes status from DRAFT to APPROVED)
        
        Args:
            payroll_run_id: int - ID of payroll run
            approved_by: User - User approving the payroll
        
        Returns:
            PayrollRun - Updated payroll run
        
        Raises:
            ValidationError: If validation fails
        """
        try:
            payroll_run = PayrollRun.objects.select_for_update().get(id=payroll_run_id)
        except PayrollRun.DoesNotExist:
            raise ValidationError(f"Payroll run with ID {payroll_run_id} does not exist")
        
        if not payroll_run.can_approve():
            raise ValidationError(f"Cannot approve payroll run with status {payroll_run.status}")
        
        payroll_run.status = 'APPROVED'
        payroll_run.approved_by = approved_by
        payroll_run.approved_at = timezone.now()
        payroll_run.save(update_fields=['status', 'approved_by', 'approved_at'])
        
        return payroll_run
    
    @staticmethod
    def get_payroll_summary(payroll_run_id: int) -> dict:
        """
        Get comprehensive summary of a payroll run
        
        Args:
            payroll_run_id: int - ID of payroll run
        
        Returns:
            dict with summary information
        """
        try:
            payroll_run = PayrollRun.objects.get(id=payroll_run_id)
        except PayrollRun.DoesNotExist:
            raise ValidationError(f"Payroll run with ID {payroll_run_id} does not exist")
        
        items = payroll_run.items.all()
        
        # Calculate totals
        total_gross = sum(item.gross_salary for item in items)
        total_paye = sum(item.paye for item in items)
        total_nssf = sum(item.nssf for item in items)
        total_nhif = sum(item.nhif for item in items)
        total_other = sum(item.loan_deduction + item.other_deductions for item in items)
        total_deductions = sum(item.total_deductions for item in items)
        total_net = sum(item.net_salary for item in items)
        
        return {
            'payroll_run': {
                'id': payroll_run.id,
                'name': payroll_run.name,
                'status': payroll_run.status,
                'period_start': payroll_run.period_start,
                'period_end': payroll_run.period_end,
                'payment_date': payroll_run.payment_date
            },
            'summary': {
                'employee_count': items.count(),
                'total_gross': total_gross,
                'total_paye': total_paye,
                'total_nssf': total_nssf,
                'total_nhif': total_nhif,
                'total_statutory': total_paye + total_nssf + total_nhif,
                'total_other_deductions': total_other,
                'total_deductions': total_deductions,
                'total_net': total_net
            },
            'items': [
                {
                    'employee_number': item.employee.employee_number,
                    'employee_name': item.employee.user.get_full_name(),
                    'gross_salary': item.gross_salary,
                    'paye': item.paye,
                    'nssf': item.nssf,
                    'nhif': item.nhif,
                    'total_deductions': item.total_deductions,
                    'net_salary': item.net_salary
                }
                for item in items
            ]
        }
