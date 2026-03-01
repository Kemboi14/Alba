"""
Accounting Integration Tests for Payroll System

Tests the integration between payroll and accounting modules:
- Journal entry creation
- Account posting
- Balanced entries
- Multiple employee scenarios
"""

from decimal import Decimal
from datetime import date
from django.test import TestCase
from django.core.exceptions import ValidationError
from apps.core.models import User
from apps.payroll.models import Employee, PayrollRun, PayrollItem
from apps.payroll.payroll_service import PayrollService
from apps.accounting.models import (
    FiscalYear, AccountType, Account, JournalEntry, JournalEntryLine
)


class PayrollAccountingIntegrationTests(TestCase):
    """Tests for payroll-accounting integration"""
    
    def setUp(self):
        """Set up test data"""
        self.user = User.objects.create_user(
            username='admin',
            email='admin@test.com',
            password='testpass123'
        )
        
        # Create fiscal year
        self.fiscal_year = FiscalYear.objects.create(
            name='FY 2026',
            start_date=date(2026, 1, 1),
            end_date=date(2026, 12, 31),
            is_active=True
        )
        
        # Create account types
        self.expense_type = AccountType.objects.create(
            name='Expenses',
            code='5000',
            nature='DEBIT'
        )
        
        self.liability_type = AccountType.objects.create(
            name='Current Liabilities',
            code='2000',
            nature='CREDIT'
        )
        
        # Create accounts for payroll
        self.salary_expense = Account.objects.create(
            name='Salary Expense',
            code='5100',
            account_type=self.expense_type,
            is_active=True
        )
        
        self.paye_payable = Account.objects.create(
            name='PAYE Payable',
            code='2100',
            account_type=self.liability_type,
            is_active=True
        )
        
        self.nssf_payable = Account.objects.create(
            name='NSSF Payable',
            code='2110',
            account_type=self.liability_type,
            is_active=True
        )
        
        self.nhif_payable = Account.objects.create(
            name='NHIF Payable',
            code='2120',
            account_type=self.liability_type,
            is_active=True
        )
        
        self.salary_payable = Account.objects.create(
            name='Salary Payable',
            code='2200',
            account_type=self.liability_type,
            is_active=True
        )
        
        # Create employee
        self.emp_user = User.objects.create_user(
            username='emp001',
            email='employee@test.com',
            password='testpass123',
            first_name='John',
            last_name='Employee'
        )
        
        self.employee = Employee.objects.create(
            user=self.emp_user,
            employee_number='EMP001',
            basic_salary=Decimal('50000.00'),
            housing_allowance=Decimal('15000.00'),
            transport_allowance=Decimal('5000.00'),
            bank_name='Test Bank',
            account_number='1234567890',
            account_name='John Employee',
            kra_pin='A123456789X'
        )
    
    def test_process_payroll_creates_journal_entry(self):
        """Test that processing payroll creates a journal entry"""
        # Create and approve payroll
        payroll_run = PayrollService.create_payroll_run(
            name='January 2026',
            period_start=date(2026, 1, 1),
            period_end=date(2026, 1, 31),
            payment_date=date(2026, 2, 5),
            created_by=self.user
        )
        
        PayrollService.add_employee_to_payroll(
            payroll_run_id=payroll_run.id,
            employee_id=self.employee.id
        )
        
        PayrollService.approve_payroll_run(
            payroll_run_id=payroll_run.id,
            approved_by=self.user
        )
        
        # Process with accounting
        processed_run = PayrollService.process_payroll_with_accounting(
            payroll_run_id=payroll_run.id,
            fiscal_year=self.fiscal_year,
            salary_expense_account=self.salary_expense,
            paye_payable_account=self.paye_payable,
            nssf_payable_account=self.nssf_payable,
            nhif_payable_account=self.nhif_payable,
            salary_payable_account=self.salary_payable
        )
        
        # Verify journal entry was created
        self.assertIsNotNone(processed_run.journal_entry)
        self.assertEqual(processed_run.status, 'PROCESSED')
    
    def test_journal_entry_is_balanced(self):
        """Test that journal entry debits equal credits"""
        payroll_run = PayrollService.create_payroll_run(
            name='January 2026',
            period_start=date(2026, 1, 1),
            period_end=date(2026, 1, 31),
            payment_date=date(2026, 2, 5),
            created_by=self.user
        )
        
        PayrollService.add_employee_to_payroll(
            payroll_run_id=payroll_run.id,
            employee_id=self.employee.id
        )
        
        PayrollService.approve_payroll_run(
            payroll_run_id=payroll_run.id,
            approved_by=self.user
        )
        
        processed_run = PayrollService.process_payroll_with_accounting(
            payroll_run_id=payroll_run.id,
            fiscal_year=self.fiscal_year,
            salary_expense_account=self.salary_expense,
            paye_payable_account=self.paye_payable,
            nssf_payable_account=self.nssf_payable,
            nhif_payable_account=self.nhif_payable,
            salary_payable_account=self.salary_payable
        )
        
        # Get journal entry
        journal_entry = processed_run.journal_entry
        
        # Calculate totals
        debit_total = sum(
            line.debit for line in journal_entry.lines.all()
        )
        credit_total = sum(
            line.credit for line in journal_entry.lines.all()
        )
        
        # Verify balanced
        self.assertEqual(debit_total, credit_total)
    
    def test_journal_entry_has_correct_accounts(self):
        """Test that journal entry uses correct accounts"""
        payroll_run = PayrollService.create_payroll_run(
            name='January 2026',
            period_start=date(2026, 1, 1),
            period_end=date(2026, 1, 31),
            payment_date=date(2026, 2, 5),
            created_by=self.user
        )
        
        PayrollService.add_employee_to_payroll(
            payroll_run_id=payroll_run.id,
            employee_id=self.employee.id
        )
        
        PayrollService.approve_payroll_run(
            payroll_run_id=payroll_run.id,
            approved_by=self.user
        )
        
        processed_run = PayrollService.process_payroll_with_accounting(
            payroll_run_id=payroll_run.id,
            fiscal_year=self.fiscal_year,
            salary_expense_account=self.salary_expense,
            paye_payable_account=self.paye_payable,
            nssf_payable_account=self.nssf_payable,
            nhif_payable_account=self.nhif_payable,
            salary_payable_account=self.salary_payable
        )
        
        journal_entry = processed_run.journal_entry
        lines = list(journal_entry.lines.all())
        
        # Get accounts used
        accounts = [line.account for line in lines]
        
        # Verify all required accounts are present
        self.assertIn(self.salary_expense, accounts)
        self.assertIn(self.paye_payable, accounts)
        self.assertIn(self.nssf_payable, accounts)
        self.assertIn(self.nhif_payable, accounts)
        self.assertIn(self.salary_payable, accounts)
    
    def test_journal_entry_amounts_match_payroll(self):
        """Test that journal entry amounts match payroll totals"""
        payroll_run = PayrollService.create_payroll_run(
            name='January 2026',
            period_start=date(2026, 1, 1),
            period_end=date(2026, 1, 31),
            payment_date=date(2026, 2, 5),
            created_by=self.user
        )
        
        item = PayrollService.add_employee_to_payroll(
            payroll_run_id=payroll_run.id,
            employee_id=self.employee.id
        )
        
        PayrollService.approve_payroll_run(
            payroll_run_id=payroll_run.id,
            approved_by=self.user
        )
        
        processed_run = PayrollService.process_payroll_with_accounting(
            payroll_run_id=payroll_run.id,
            fiscal_year=self.fiscal_year,
            salary_expense_account=self.salary_expense,
            paye_payable_account=self.paye_payable,
            nssf_payable_account=self.nssf_payable,
            nhif_payable_account=self.nhif_payable,
            salary_payable_account=self.salary_payable
        )
        
        journal_entry = processed_run.journal_entry
        lines = {line.account: line for line in journal_entry.lines.all()}
        
        # Verify amounts
        salary_expense_line = lines[self.salary_expense]
        self.assertEqual(salary_expense_line.debit, item.gross_salary)
        
        paye_line = lines[self.paye_payable]
        self.assertEqual(paye_line.credit, item.paye)
        
        nssf_line = lines[self.nssf_payable]
        self.assertEqual(nssf_line.credit, item.nssf)
        
        nhif_line = lines[self.nhif_payable]
        self.assertEqual(nhif_line.credit, item.nhif)
        
        salary_payable_line = lines[self.salary_payable]
        self.assertEqual(salary_payable_line.credit, item.net_salary)
    
    def test_multiple_employees_journal_entry(self):
        """Test journal entry for multiple employees"""
        # Create additional employees
        employees = []
        for i in range(3):
            user = User.objects.create_user(
                username=f'emp00{i+2}',
                email=f'emp{i+2}@test.com',
                password='testpass123'
            )
            emp = Employee.objects.create(
                user=user,
                employee_number=f'EMP00{i+2}',
                basic_salary=Decimal('40000.00'),
                housing_allowance=Decimal('10000.00'),
                bank_name='Test Bank',
                account_number=f'123456789{i}',
                account_name=f'Employee {i+2}',
                kra_pin=f'B12345678{i}X'
            )
            employees.append(emp)
        
        # Create payroll
        payroll_run = PayrollService.create_payroll_run(
            name='January 2026',
            period_start=date(2026, 1, 1),
            period_end=date(2026, 1, 31),
            payment_date=date(2026, 2, 5),
            created_by=self.user
        )
        
        # Add all employees
        items = []
        items.append(PayrollService.add_employee_to_payroll(
            payroll_run_id=payroll_run.id,
            employee_id=self.employee.id
        ))
        
        for emp in employees:
            items.append(PayrollService.add_employee_to_payroll(
                payroll_run_id=payroll_run.id,
                employee_id=emp.id
            ))
        
        # Approve and process
        PayrollService.approve_payroll_run(
            payroll_run_id=payroll_run.id,
            approved_by=self.user
        )
        
        processed_run = PayrollService.process_payroll_with_accounting(
            payroll_run_id=payroll_run.id,
            fiscal_year=self.fiscal_year,
            salary_expense_account=self.salary_expense,
            paye_payable_account=self.paye_payable,
            nssf_payable_account=self.nssf_payable,
            nhif_payable_account=self.nhif_payable,
            salary_payable_account=self.salary_payable
        )
        
        # Calculate expected totals
        total_gross = sum(item.gross_salary for item in items)
        total_paye = sum(item.paye for item in items)
        total_nssf = sum(item.nssf for item in items)
        total_nhif = sum(item.nhif for item in items)
        total_net = sum(item.net_salary for item in items)
        
        # Get journal entry
        journal_entry = processed_run.journal_entry
        lines = {line.account: line for line in journal_entry.lines.all()}
        
        # Verify totals match
        self.assertEqual(lines[self.salary_expense].debit, total_gross)
        self.assertEqual(lines[self.paye_payable].credit, total_paye)
        self.assertEqual(lines[self.nssf_payable].credit, total_nssf)
        self.assertEqual(lines[self.nhif_payable].credit, total_nhif)
        self.assertEqual(lines[self.salary_payable].credit, total_net)
    
    def test_cannot_process_unapproved_payroll(self):
        """Test that unapproved payroll cannot be processed"""
        payroll_run = PayrollService.create_payroll_run(
            name='January 2026',
            period_start=date(2026, 1, 1),
            period_end=date(2026, 1, 31),
            payment_date=date(2026, 2, 5),
            created_by=self.user
        )
        
        PayrollService.add_employee_to_payroll(
            payroll_run_id=payroll_run.id,
            employee_id=self.employee.id
        )
        
        # Don't approve, try to process directly
        with self.assertRaises(ValidationError) as context:
            PayrollService.process_payroll_with_accounting(
                payroll_run_id=payroll_run.id,
                fiscal_year=self.fiscal_year,
                salary_expense_account=self.salary_expense,
                paye_payable_account=self.paye_payable,
                nssf_payable_account=self.nssf_payable,
                nhif_payable_account=self.nhif_payable,
                salary_payable_account=self.salary_payable
            )
        
        self.assertIn('must be approved', str(context.exception).lower())
    
    def test_cannot_process_empty_payroll(self):
        """Test that empty payroll cannot be processed"""
        payroll_run = PayrollService.create_payroll_run(
            name='January 2026',
            period_start=date(2026, 1, 1),
            period_end=date(2026, 1, 31),
            payment_date=date(2026, 2, 5),
            created_by=self.user
        )
        
        # Approve without adding employees
        PayrollService.approve_payroll_run(
            payroll_run_id=payroll_run.id,
            approved_by=self.user
        )
        
        with self.assertRaises(ValidationError) as context:
            PayrollService.process_payroll_with_accounting(
                payroll_run_id=payroll_run.id,
                fiscal_year=self.fiscal_year,
                salary_expense_account=self.salary_expense,
                paye_payable_account=self.paye_payable,
                nssf_payable_account=self.nssf_payable,
                nhif_payable_account=self.nhif_payable,
                salary_payable_account=self.salary_payable
            )
        
        self.assertIn('no payroll items', str(context.exception).lower())
    
    def test_journal_entry_reference(self):
        """Test journal entry has proper reference"""
        payroll_run = PayrollService.create_payroll_run(
            name='January 2026 Payroll',
            period_start=date(2026, 1, 1),
            period_end=date(2026, 1, 31),
            payment_date=date(2026, 2, 5),
            created_by=self.user
        )
        
        PayrollService.add_employee_to_payroll(
            payroll_run_id=payroll_run.id,
            employee_id=self.employee.id
        )
        
        PayrollService.approve_payroll_run(
            payroll_run_id=payroll_run.id,
            approved_by=self.user
        )
        
        processed_run = PayrollService.process_payroll_with_accounting(
            payroll_run_id=payroll_run.id,
            fiscal_year=self.fiscal_year,
            salary_expense_account=self.salary_expense,
            paye_payable_account=self.paye_payable,
            nssf_payable_account=self.nssf_payable,
            nhif_payable_account=self.nhif_payable,
            salary_payable_account=self.salary_payable
        )
        
        journal_entry = processed_run.journal_entry
        
        # Verify reference contains payroll name
        self.assertIn('January 2026 Payroll', journal_entry.reference)
        self.assertIn('Payroll', journal_entry.description)
