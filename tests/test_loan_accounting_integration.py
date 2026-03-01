"""
Comprehensive Test Suite for Loan-Accounting Integration
Tests automatic journal entry posting for disbursements and repayments
"""
from decimal import Decimal
from datetime import date
from django.test import TestCase
from django.core.exceptions import ValidationError
from django.contrib.auth import get_user_model
from apps.loans.models import LoanProduct, DirectLoan
from apps.loans.services import LoanService
from apps.accounting.models import (
    FiscalYear,
    AccountType,
    Account,
    JournalEntry
)

User = get_user_model()


class LoanAccountingIntegrationTest(TestCase):
    """Test loan-accounting integration"""
    
    def setUp(self):
        """Set up test data"""
        # Create users
        self.customer = User.objects.create_user(
            username='customer1',
            email='customer@example.com',
            password='testpass123',
            first_name='John',
            last_name='Doe'
        )
        
        self.admin = User.objects.create_user(
            username='admin1',
            email='admin@example.com',
            password='testpass123',
            role='ADMIN'
        )
        
        # Create fiscal year
        self.fiscal_year = FiscalYear.objects.create(
            name='FY 2026',
            start_date=date(2026, 1, 1),
            end_date=date(2026, 12, 31),
            is_active=True
        )
        
        # Create account types
        self.asset_type = AccountType.objects.create(
            name='ASSET',
            description='Asset accounts',
            normal_balance='DEBIT'
        )
        
        self.income_type = AccountType.objects.create(
            name='INCOME',
            description='Income accounts',
            normal_balance='CREDIT'
        )
        
        # Create GL accounts
        self.bank_account = Account.objects.create(
            code='1010',
            name='Bank Account',
            account_type=self.asset_type,
            is_active=True
        )
        
        self.loan_receivable = Account.objects.create(
            code='1300',
            name='Loan Receivable',
            account_type=self.asset_type,
            is_active=True
        )
        
        self.interest_income = Account.objects.create(
            code='4100',
            name='Interest Income',
            account_type=self.income_type,
            is_active=True
        )
        
        self.penalty_income = Account.objects.create(
            code='4200',
            name='Penalty Income',
            account_type=self.income_type,
            is_active=True
        )
        
        # Create loan product with GL account mappings
        self.product = LoanProduct.objects.create(
            name='Personal Loan',
            code='PL-001',
            description='Personal loan product',
            interest_rate=Decimal('12.00'),
            interest_method='REDUCING_BALANCE',
            minimum_amount=Decimal('10000.00'),
            maximum_amount=Decimal('500000.00'),
            minimum_term_months=6,
            maximum_term_months=60,
            processing_fee_percentage=Decimal('2.00'),
            late_payment_penalty_percentage=Decimal('1.50'),
            grace_period_days=3,
            default_repayment_frequency='MONTHLY',
            loan_receivable_account=self.loan_receivable,
            interest_income_account=self.interest_income,
            penalty_income_account=self.penalty_income,
            created_by=self.admin
        )
    
    def test_disburse_loan_with_accounting(self):
        """Test loan disbursement creates proper accounting entry"""
        # Create loan
        loan = DirectLoan.objects.create(
            customer=self.customer,
            loan_product=self.product,
            principal_amount=Decimal('100000.00'),
            interest_rate=Decimal('12.00'),
            term_months=12,
            status='APPROVED'
        )
        
        # Disburse with accounting
        result = LoanService.disburse_loan_with_accounting(
            loan=loan,
            bank_account=self.bank_account,
            disbursement_date=date(2026, 3, 1),
            disbursed_by=self.admin,
            fiscal_year=self.fiscal_year,
            reference='DISB-001'
        )
        
        # Verify loan status
        loan.refresh_from_db()
        self.assertEqual(loan.status, 'DISBURSED')
        self.assertEqual(loan.outstanding_principal, Decimal('100000.00'))
        self.assertEqual(loan.disbursement_date, date(2026, 3, 1))
        
        # Verify journal entry was created
        journal_entry = result['journal_entry']
        self.assertIsNotNone(journal_entry)
        self.assertTrue(journal_entry.is_posted)
        
        # Verify journal entry lines
        lines = journal_entry.lines.all()
        self.assertEqual(lines.count(), 2)
        
        # Find debit and credit lines
        debit_line = lines.get(debit_amount__gt=0)
        credit_line = lines.get(credit_amount__gt=0)
        
        # Verify debit to Loan Receivable
        self.assertEqual(debit_line.account, self.loan_receivable)
        self.assertEqual(debit_line.debit_amount, Decimal('100000.00'))
        
        # Verify credit to Bank
        self.assertEqual(credit_line.account, self.bank_account)
        self.assertEqual(credit_line.credit_amount, Decimal('100000.00'))
        
        # Verify entry is balanced
        self.assertTrue(journal_entry.is_balanced())
    
    def test_disburse_loan_without_fiscal_year_fails(self):
        """Test disbursement fails without fiscal year"""
        loan = DirectLoan.objects.create(
            customer=self.customer,
            loan_product=self.product,
            principal_amount=Decimal('100000.00'),
            interest_rate=Decimal('12.00'),
            term_months=12,
            status='APPROVED'
        )
        
        with self.assertRaises(ValidationError) as context:
            LoanService.disburse_loan_with_accounting(
                loan=loan,
                bank_account=self.bank_account,
                fiscal_year=None  # Missing!
            )
        
        self.assertIn('Fiscal year is required', str(context.exception))
    
    def test_disburse_loan_without_receivable_account_fails(self):
        """Test disbursement fails if product has no receivable account"""
        # Create product without GL accounts
        product_no_gl = LoanProduct.objects.create(
            name='Product No GL',
            code='NO-GL',
            description='Product without GL',
            interest_rate=Decimal('12.00'),
            interest_method='FLAT',
            minimum_amount=Decimal('10000.00'),
            maximum_amount=Decimal('500000.00'),
            minimum_term_months=6,
            maximum_term_months=60,
            processing_fee_percentage=Decimal('2.00'),
            late_payment_penalty_percentage=Decimal('1.50'),
            grace_period_days=3,
            default_repayment_frequency='MONTHLY',
            created_by=self.admin
        )
        
        loan = DirectLoan.objects.create(
            customer=self.customer,
            loan_product=product_no_gl,
            principal_amount=Decimal('50000.00'),
            interest_rate=Decimal('12.00'),
            term_months=12,
            status='APPROVED'
        )
        
        with self.assertRaises(ValidationError) as context:
            LoanService.disburse_loan_with_accounting(
                loan=loan,
                bank_account=self.bank_account,
                fiscal_year=self.fiscal_year
            )
        
        self.assertIn('does not have loan_receivable_account', str(context.exception))
    
    def test_disburse_already_disbursed_loan_fails(self):
        """Test cannot disburse already disbursed loan"""
        loan = DirectLoan.objects.create(
            customer=self.customer,
            loan_product=self.product,
            principal_amount=Decimal('50000.00'),
            interest_rate=Decimal('12.00'),
            term_months=12,
            status='DISBURSED',
            disbursement_date=date(2026, 2, 1),
            outstanding_principal=Decimal('50000.00')
        )
        
        with self.assertRaises(ValidationError) as context:
            LoanService.disburse_loan_with_accounting(
                loan=loan,
                bank_account=self.bank_account,
                fiscal_year=self.fiscal_year
            )
        
        self.assertIn('cannot be disbursed', str(context.exception))
    
    def test_record_payment_with_accounting_principal_only(self):
        """Test payment recording with accounting for principal-only payment"""
        # Create and disburse loan
        loan = LoanService.create_loan_with_schedule(
            customer=self.customer,
            loan_product=self.product,
            principal_amount=Decimal('120000.00'),
            term_months=12,
            disbursement_date=date(2026, 3, 1),
            status='DISBURSED'
        )
        
        # Get first installment total
        first_schedule = loan.repayment_schedules.first()
        payment_amount = first_schedule.get_total_due()
        
        # Record payment with accounting
        result = LoanService.record_payment_with_accounting(
            loan=loan,
            amount=payment_amount,
            bank_account=self.bank_account,
            payment_date=date(2026, 4, 1),
            received_by=self.admin,
            fiscal_year=self.fiscal_year,
            reference='RCPT-001'
        )
        
        # Verify payment was recorded
        first_schedule.refresh_from_db()
        self.assertTrue(first_schedule.is_paid)
        
        # Verify journal entry
        journal_entry = result['journal_entry']
        self.assertIsNotNone(journal_entry)
        self.assertTrue(journal_entry.is_posted)
        
        # Verify entry is balanced
        self.assertTrue(journal_entry.is_balanced())
        
        # Verify allocation
        allocation = result['allocation']
        self.assertGreater(allocation['principal_paid'], Decimal('0.00'))
        self.assertGreater(allocation['interest_paid'], Decimal('0.00'))
        self.assertEqual(allocation['penalty_paid'], Decimal('0.00'))
    
    def test_record_payment_allocation_order(self):
        """Test payment allocation follows order: Penalty → Interest → Principal"""
        # Create loan
        loan = LoanService.create_loan_with_schedule(
            customer=self.customer,
            loan_product=self.product,
            principal_amount=Decimal('100000.00'),
            term_months=12,
            disbursement_date=date(2026, 3, 1),
            status='DISBURSED'
        )
        
        # Add penalty to first installment
        first_schedule = loan.repayment_schedules.first()
        first_schedule.penalty_due = Decimal('500.00')
        first_schedule.save()
        
        # Make partial payment (less than total)
        partial_amount = Decimal('1000.00')
        
        result = LoanService.record_payment_with_accounting(
            loan=loan,
            amount=partial_amount,
            bank_account=self.bank_account,
            payment_date=date(2026, 4, 1),
            received_by=self.admin,
            fiscal_year=self.fiscal_year,
            reference='RCPT-002'
        )
        
        # Verify allocation order: Penalty first
        allocation = result['allocation']
        self.assertEqual(allocation['penalty_paid'], Decimal('500.00'))
        
        # Remaining 500 should go to interest
        self.assertGreater(allocation['interest_paid'], Decimal('0.00'))
        self.assertLessEqual(allocation['interest_paid'], Decimal('500.00'))
    
    def test_record_full_loan_payment_closes_loan(self):
        """Test paying full loan amount closes the loan"""
        # Create loan
        loan = LoanService.create_loan_with_schedule(
            customer=self.customer,
            loan_product=self.product,
            principal_amount=Decimal('100000.00'),
            term_months=12,
            disbursement_date=date(2026, 3, 1),
            status='DISBURSED'
        )
        
        # Calculate total repayment
        summary = LoanService.calculate_loan_summary(loan)
        total_due = summary['total_amount_due']
        
        # Pay full amount
        result = LoanService.record_payment_with_accounting(
            loan=loan,
            amount=total_due,
            bank_account=self.bank_account,
            payment_date=date(2026, 4, 1),
            received_by=self.admin,
            fiscal_year=self.fiscal_year,
            reference='FULL-PAY'
        )
        
        # Verify loan is closed
        loan.refresh_from_db()
        self.assertEqual(loan.status, 'CLOSED')
        self.assertEqual(loan.outstanding_principal, Decimal('0.00'))
        
        # Verify all installments are paid
        self.assertEqual(
            loan.repayment_schedules.filter(is_paid=False).count(),
            0
        )
    
    def test_payment_without_fiscal_year_fails(self):
        """Test payment fails without fiscal year"""
        loan = LoanService.create_loan_with_schedule(
            customer=self.customer,
            loan_product=self.product,
            principal_amount=Decimal('100000.00'),
            term_months=12,
            disbursement_date=date(2026, 3, 1),
            status='DISBURSED'
        )
        
        with self.assertRaises(ValidationError) as context:
            LoanService.record_payment_with_accounting(
                loan=loan,
                amount=Decimal('5000.00'),
                bank_account=self.bank_account,
                fiscal_year=None  # Missing!
            )
        
        self.assertIn('Fiscal year is required', str(context.exception))
    
    def test_payment_with_penalty_requires_penalty_account(self):
        """Test payment with penalty requires penalty income account"""
        # Create product without penalty account
        product_no_penalty = LoanProduct.objects.create(
            name='No Penalty Account',
            code='NO-PEN',
            description='Product without penalty account',
            interest_rate=Decimal('12.00'),
            interest_method='REDUCING_BALANCE',
            minimum_amount=Decimal('10000.00'),
            maximum_amount=Decimal('500000.00'),
            minimum_term_months=6,
            maximum_term_months=60,
            processing_fee_percentage=Decimal('2.00'),
            late_payment_penalty_percentage=Decimal('1.50'),
            grace_period_days=3,
            default_repayment_frequency='MONTHLY',
            loan_receivable_account=self.loan_receivable,
            interest_income_account=self.interest_income,
            # penalty_income_account NOT SET
            created_by=self.admin
        )
        
        loan = LoanService.create_loan_with_schedule(
            customer=self.customer,
            loan_product=product_no_penalty,
            principal_amount=Decimal('50000.00'),
            term_months=12,
            disbursement_date=date(2026, 3, 1),
            status='DISBURSED'
        )
        
        # Add penalty
        first_schedule = loan.repayment_schedules.first()
        first_schedule.penalty_due = Decimal('500.00')
        first_schedule.save()
        
        # Try to pay with penalty
        with self.assertRaises(ValidationError) as context:
            LoanService.record_payment_with_accounting(
                loan=loan,
                amount=first_schedule.get_total_due(),
                bank_account=self.bank_account,
                fiscal_year=self.fiscal_year
            )
        
        self.assertIn('penalty_income_account', str(context.exception))
    
    def test_transaction_atomicity_on_error(self):
        """Test that transaction rolls back on error"""
        # Create loan
        loan = DirectLoan.objects.create(
            customer=self.customer,
            loan_product=self.product,
            principal_amount=Decimal('100000.00'),
            interest_rate=Decimal('12.00'),
            term_months=12,
            status='APPROVED'
        )
        
        initial_journal_count = JournalEntry.objects.count()
        
        # Try to disburse with invalid bank account type
        # First create an income account (wrong type)
        wrong_account = Account.objects.create(
            code='5000',
            name='Wrong Account',
            account_type=self.income_type,  # Wrong type!
            is_active=True
        )
        
        # This should fail and rollback
        with self.assertRaises(ValidationError):
            LoanService.disburse_loan_with_accounting(
                loan=loan,
                bank_account=wrong_account,
                fiscal_year=self.fiscal_year
            )
        
        # Verify loan was not disbursed
        loan.refresh_from_db()
        self.assertEqual(loan.status, 'APPROVED')  # Still approved
        
        # Verify no journal entry was created
        self.assertEqual(JournalEntry.objects.count(), initial_journal_count)
    
    def test_multiple_payments_cumulative_allocation(self):
        """Test multiple payments accumulate correctly"""
        loan = LoanService.create_loan_with_schedule(
            customer=self.customer,
            loan_product=self.product,
            principal_amount=Decimal('100000.00'),
            term_months=12,
            disbursement_date=date(2026, 3, 1),
            status='DISBURSED'
        )
        
        # Make 3 payments
        for i in range(3):
            result = LoanService.record_payment_with_accounting(
                loan=loan,
                amount=Decimal('10000.00'),
                bank_account=self.bank_account,
                payment_date=date(2026, 4, 1 + i),
                received_by=self.admin,
                fiscal_year=self.fiscal_year,
                reference=f'RCPT-00{i+1}'
            )
            
            # Verify journal entry created
            self.assertIsNotNone(result['journal_entry'])
            self.assertTrue(result['journal_entry'].is_posted)
        
        # Verify multiple installments are paid
        paid_count = loan.repayment_schedules.filter(is_paid=True).count()
        self.assertGreater(paid_count, 0)
        
        # Verify outstanding principal decreased
        self.assertLess(loan.outstanding_principal, Decimal('100000.00'))


class LoanAccountingEdgeCasesTest(TestCase):
    """Test edge cases and error handling"""
    
    def setUp(self):
        """Set up test data"""
        self.customer = User.objects.create_user(
            username='customer2',
            email='customer2@example.com',
            password='testpass123'
        )
        
        self.admin = User.objects.create_user(
            username='admin2',
            email='admin2@example.com',
            password='testpass123'
        )
        
        self.fiscal_year = FiscalYear.objects.create(
            name='FY 2026',
            start_date=date(2026, 1, 1),
            end_date=date(2026, 12, 31),
            is_active=True
        )
        
        asset_type = AccountType.objects.create(
            name='ASSET',
            description='Asset accounts',
            normal_balance='DEBIT'
        )
        
        income_type = AccountType.objects.create(
            name='INCOME',
            description='Income accounts',
            normal_balance='CREDIT'
        )
        
        self.bank_account = Account.objects.create(
            code='1010',
            name='Bank',
            account_type=asset_type,
            is_active=True
        )
        
        self.loan_receivable = Account.objects.create(
            code='1300',
            name='Loan Receivable',
            account_type=asset_type,
            is_active=True
        )
        
        self.interest_income = Account.objects.create(
            code='4100',
            name='Interest Income',
            account_type=income_type,
            is_active=True
        )
        
        self.product = LoanProduct.objects.create(
            name='Test Product',
            code='TEST-001',
            description='Test product',
            interest_rate=Decimal('12.00'),
            interest_method='FLAT',
            minimum_amount=Decimal('10000.00'),
            maximum_amount=Decimal('500000.00'),
            minimum_term_months=6,
            maximum_term_months=60,
            processing_fee_percentage=Decimal('2.00'),
            late_payment_penalty_percentage=Decimal('1.50'),
            grace_period_days=3,
            default_repayment_frequency='MONTHLY',
            loan_receivable_account=self.loan_receivable,
            interest_income_account=self.interest_income,
            created_by=self.admin
        )
    
    def test_zero_amount_payment_fails(self):
        """Test zero or negative payment fails"""
        loan = LoanService.create_loan_with_schedule(
            customer=self.customer,
            loan_product=self.product,
            principal_amount=Decimal('50000.00'),
            term_months=12,
            disbursement_date=date(2026, 3, 1),
            status='DISBURSED'
        )
        
        with self.assertRaises(ValidationError) as context:
            LoanService.record_payment_with_accounting(
                loan=loan,
                amount=Decimal('0.00'),
                bank_account=self.bank_account,
                fiscal_year=self.fiscal_year
            )
        
        self.assertIn('must be positive', str(context.exception))
    
    def test_overpayment_returns_excess(self):
        """Test overpayment returns excess amount"""
        loan = LoanService.create_loan_with_schedule(
            customer=self.customer,
            loan_product=self.product,
            principal_amount=Decimal('50000.00'),
            term_months=12,
            disbursement_date=date(2026, 3, 1),
            status='DISBURSED'
        )
        
        # Get total due
        summary = LoanService.calculate_loan_summary(loan)
        total_due = summary['total_amount_due']
        
        # Pay more than total
        overpayment = total_due + Decimal('5000.00')
        
        result = LoanService.record_payment_with_accounting(
            loan=loan,
            amount=overpayment,
            bank_account=self.bank_account,
            fiscal_year=self.fiscal_year
        )
        
        # Should have excess
        self.assertEqual(result['excess_amount'], Decimal('5000.00'))
        
        # Loan should be closed
        loan.refresh_from_db()
        self.assertEqual(loan.status, 'CLOSED')
