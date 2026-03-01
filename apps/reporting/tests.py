"""
Tests for Financial and Loan Reporting Services

Run with:
    python manage.py test apps.reporting.tests
    
Or specific test:
    python manage.py test apps.reporting.tests.TestFinancialReportingService.test_trial_balance
"""

from datetime import date, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from apps.accounting.models import Account, AccountType, FiscalYear, JournalEntry, JournalEntryLine
from apps.loans.models import Customer, Loan, LoanProduct, Payment
from apps.reporting.services import FinancialReportingService, LoanReportingService

User = get_user_model()


class TestFinancialReportingService(TestCase):
    """Tests for FinancialReportingService"""
    
    @classmethod
    def setUpTestData(cls):
        """Set up test data for all test methods"""
        # Create test user
        cls.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )
        
        # Create fiscal year
        cls.fiscal_year = FiscalYear.objects.create(
            name='2024',
            start_date=date(2024, 1, 1),
            end_date=date(2024, 12, 31),
            is_active=True,
            created_by=cls.user
        )
        
        # Create account types
        cls.asset_type = AccountType.objects.create(
            name='ASSET',
            normal_balance='DEBIT'
        )
        cls.liability_type = AccountType.objects.create(
            name='LIABILITY',
            normal_balance='CREDIT'
        )
        cls.equity_type = AccountType.objects.create(
            name='EQUITY',
            normal_balance='CREDIT'
        )
        cls.income_type = AccountType.objects.create(
            name='INCOME',
            normal_balance='CREDIT'
        )
        cls.expense_type = AccountType.objects.create(
            name='EXPENSE',
            normal_balance='DEBIT'
        )
        
        # Create accounts
        cls.cash_account = Account.objects.create(
            code='1000',
            name='Cash',
            account_type=cls.asset_type,
            created_by=cls.user
        )
        cls.loans_receivable = Account.objects.create(
            code='1200',
            name='Loans Receivable',
            account_type=cls.asset_type,
            created_by=cls.user
        )
        cls.bank_loan = Account.objects.create(
            code='2000',
            name='Bank Loan',
            account_type=cls.liability_type,
            created_by=cls.user
        )
        cls.capital = Account.objects.create(
            code='3000',
            name='Capital',
            account_type=cls.equity_type,
            created_by=cls.user
        )
        cls.interest_income = Account.objects.create(
            code='4000',
            name='Interest Income',
            account_type=cls.income_type,
            created_by=cls.user
        )
        cls.salary_expense = Account.objects.create(
            code='5000',
            name='Salary Expense',
            account_type=cls.expense_type,
            created_by=cls.user
        )
    
    def test_trial_balance_basic(self):
        """Test basic trial balance generation"""
        # Create simple journal entry: Dr Cash 10000, Cr Capital 10000
        je = JournalEntry.objects.create(
            entry_number='JE-001',
            date=date(2024, 1, 15),
            fiscal_year=self.fiscal_year,
            description='Initial capital',
            status='POSTED',
            created_by=self.user,
            posted_by=self.user,
            posted_at=timezone.now()
        )
        
        JournalEntryLine.objects.create(
            journal_entry=je,
            account=self.cash_account,
            description='Cash received',
            debit_amount=Decimal('10000.00'),
            credit_amount=Decimal('0.00')
        )
        
        JournalEntryLine.objects.create(
            journal_entry=je,
            account=self.capital,
            description='Capital contribution',
            debit_amount=Decimal('0.00'),
            credit_amount=Decimal('10000.00')
        )
        
        # Generate trial balance
        result = FinancialReportingService.generate_trial_balance(
            fiscal_year=self.fiscal_year,
            as_of_date=date(2024, 1, 31)
        )
        
        # Assertions
        self.assertTrue(result['is_balanced'])
        self.assertEqual(result['totals']['total_debit'], Decimal('10000.00'))
        self.assertEqual(result['totals']['total_credit'], Decimal('10000.00'))
        self.assertEqual(result['totals']['difference'], Decimal('0.00'))
        self.assertEqual(len(result['accounts']), 2)
    
    def test_trial_balance_multiple_entries(self):
        """Test trial balance with multiple entries"""
        # Entry 1: Dr Cash 50000, Cr Capital 50000
        je1 = JournalEntry.objects.create(
            entry_number='JE-001',
            date=date(2024, 1, 1),
            fiscal_year=self.fiscal_year,
            description='Initial capital',
            status='POSTED',
            created_by=self.user,
            posted_by=self.user,
            posted_at=timezone.now()
        )
        JournalEntryLine.objects.create(
            journal_entry=je1,
            account=self.cash_account,
            debit_amount=Decimal('50000.00'),
            credit_amount=Decimal('0.00'),
            description='Cash'
        )
        JournalEntryLine.objects.create(
            journal_entry=je1,
            account=self.capital,
            debit_amount=Decimal('0.00'),
            credit_amount=Decimal('50000.00'),
            description='Capital'
        )
        
        # Entry 2: Dr Loans Receivable 20000, Cr Cash 20000
        je2 = JournalEntry.objects.create(
            entry_number='JE-002',
            date=date(2024, 1, 15),
            fiscal_year=self.fiscal_year,
            description='Loan disbursement',
            status='POSTED',
            created_by=self.user,
            posted_by=self.user,
            posted_at=timezone.now()
        )
        JournalEntryLine.objects.create(
            journal_entry=je2,
            account=self.loans_receivable,
            debit_amount=Decimal('20000.00'),
            credit_amount=Decimal('0.00'),
            description='Loan'
        )
        JournalEntryLine.objects.create(
            journal_entry=je2,
            account=self.cash_account,
            debit_amount=Decimal('0.00'),
            credit_amount=Decimal('20000.00'),
            description='Cash'
        )
        
        # Generate trial balance
        result = FinancialReportingService.generate_trial_balance(
            fiscal_year=self.fiscal_year,
            as_of_date=date(2024, 1, 31)
        )
        
        # Cash should have net debit of 30000 (50000 Dr - 20000 Cr)
        cash_balance = next(
            (acc for acc in result['accounts'] if acc['code'] == '1000'),
            None
        )
        self.assertIsNotNone(cash_balance)
        self.assertEqual(cash_balance['net_balance'], Decimal('30000.00'))
        
        # Loans Receivable should have debit of 20000
        loan_balance = next(
            (acc for acc in result['accounts'] if acc['code'] == '1200'),
            None
        )
        self.assertIsNotNone(loan_balance)
        self.assertEqual(loan_balance['net_balance'], Decimal('20000.00'))
        
        # Should be balanced
        self.assertTrue(result['is_balanced'])
    
    def test_profit_loss_basic(self):
        """Test basic P&L generation"""
        # Create income: Cr Interest Income 5000, Dr Cash 5000
        je1 = JournalEntry.objects.create(
            entry_number='JE-001',
            date=date(2024, 1, 15),
            fiscal_year=self.fiscal_year,
            description='Interest received',
            status='POSTED',
            created_by=self.user,
            posted_by=self.user,
            posted_at=timezone.now()
        )
        JournalEntryLine.objects.create(
            journal_entry=je1,
            account=self.cash_account,
            debit_amount=Decimal('5000.00'),
            credit_amount=Decimal('0.00'),
            description='Cash'
        )
        JournalEntryLine.objects.create(
            journal_entry=je1,
            account=self.interest_income,
            debit_amount=Decimal('0.00'),
            credit_amount=Decimal('5000.00'),
            description='Interest'
        )
        
        # Create expense: Dr Salary Expense 3000, Cr Cash 3000
        je2 = JournalEntry.objects.create(
            entry_number='JE-002',
            date=date(2024, 1, 20),
            fiscal_year=self.fiscal_year,
            description='Salary payment',
            status='POSTED',
            created_by=self.user,
            posted_by=self.user,
            posted_at=timezone.now()
        )
        JournalEntryLine.objects.create(
            journal_entry=je2,
            account=self.salary_expense,
            debit_amount=Decimal('3000.00'),
            credit_amount=Decimal('0.00'),
            description='Salary'
        )
        JournalEntryLine.objects.create(
            journal_entry=je2,
            account=self.cash_account,
            debit_amount=Decimal('0.00'),
            credit_amount=Decimal('3000.00'),
            description='Cash'
        )
        
        # Generate P&L
        result = FinancialReportingService.generate_profit_loss(
            fiscal_year=self.fiscal_year,
            start_date=date(2024, 1, 1),
            end_date=date(2024, 1, 31)
        )
        
        # Assertions
        self.assertEqual(result['revenue']['total'], Decimal('5000.00'))
        self.assertEqual(result['expenses']['total'], Decimal('3000.00'))
        self.assertEqual(result['net_income'], Decimal('2000.00'))
    
    def test_balance_sheet_basic(self):
        """Test basic balance sheet generation"""
        # Create initial capital: Dr Cash 100000, Cr Capital 100000
        je1 = JournalEntry.objects.create(
            entry_number='JE-001',
            date=date(2024, 1, 1),
            fiscal_year=self.fiscal_year,
            description='Initial capital',
            status='POSTED',
            created_by=self.user,
            posted_by=self.user,
            posted_at=timezone.now()
        )
        JournalEntryLine.objects.create(
            journal_entry=je1,
            account=self.cash_account,
            debit_amount=Decimal('100000.00'),
            credit_amount=Decimal('0.00'),
            description='Cash'
        )
        JournalEntryLine.objects.create(
            journal_entry=je1,
            account=self.capital,
            debit_amount=Decimal('0.00'),
            credit_amount=Decimal('100000.00'),
            description='Capital'
        )
        
        # Create liability: Dr Cash 50000, Cr Bank Loan 50000
        je2 = JournalEntry.objects.create(
            entry_number='JE-002',
            date=date(2024, 1, 15),
            fiscal_year=self.fiscal_year,
            description='Bank loan',
            status='POSTED',
            created_by=self.user,
            posted_by=self.user,
            posted_at=timezone.now()
        )
        JournalEntryLine.objects.create(
            journal_entry=je2,
            account=self.cash_account,
            debit_amount=Decimal('50000.00'),
            credit_amount=Decimal('0.00'),
            description='Cash'
        )
        JournalEntryLine.objects.create(
            journal_entry=je2,
            account=self.bank_loan,
            debit_amount=Decimal('0.00'),
            credit_amount=Decimal('50000.00'),
            description='Loan'
        )
        
        # Generate Balance Sheet
        result = FinancialReportingService.generate_balance_sheet(
            fiscal_year=self.fiscal_year,
            as_of_date=date(2024, 1, 31)
        )
        
        # Assertions: Assets = Liabilities + Equity
        # Assets: Cash 150000
        # Liabilities: Bank Loan 50000
        # Equity: Capital 100000
        self.assertEqual(result['assets']['total'], Decimal('150000.00'))
        self.assertEqual(result['liabilities']['total'], Decimal('50000.00'))
        self.assertEqual(result['equity']['total'], Decimal('100000.00'))
        self.assertTrue(result['is_balanced'])


class TestLoanReportingService(TestCase):
    """Tests for LoanReportingService"""
    
    @classmethod
    def setUpTestData(cls):
        """Set up test data for all test methods"""
        # Create test user
        cls.user = User.objects.create_user(
            username='officer1',
            email='officer@example.com',
            password='testpass123'
        )
        
        # Create loan product
        cls.loan_product = LoanProduct.objects.create(
            name='Standard Loan',
            code='STD',
            description='Standard loan product',
            interest_rate=Decimal('12.00'),
            interest_method='REDUCING_BALANCE',
            default_repayment_frequency='MONTHLY',
            minimum_amount=Decimal('10000.00'),
            maximum_amount=Decimal('500000.00'),
            minimum_term_months=6,
            maximum_term_months=24,
            created_by=cls.user
        )
        
        # Create customers
        cls.customer1 = Customer.objects.create(
            first_name='John',
            last_name='Doe',
            id_number='12345678',
            phone_number='+254700000001',
            email='john@example.com'
        )
        
        cls.customer2 = Customer.objects.create(
            first_name='Jane',
            last_name='Smith',
            id_number='87654321',
            phone_number='+254700000002',
            email='jane@example.com'
        )
    
    def test_aged_receivables(self):
        """Test aged receivables report generation"""
        # Create loans with different overdue days
        # Current loan (0 days overdue)
        Loan.objects.create(
            loan_number='LOAN-001',
            customer=self.customer1,
            loan_product=self.loan_product,
            principal_amount=Decimal('100000.00'),
            interest_rate=Decimal('12.00'),
            interest_method='REDUCING_BALANCE',
            loan_term_months=12,
            repayment_frequency='MONTHLY',
            total_amount=Decimal('112000.00'),
            monthly_installment=Decimal('9333.33'),
            outstanding_principal=Decimal('90000.00'),
            outstanding_interest=Decimal('9000.00'),
            total_outstanding=Decimal('99000.00'),
            days_overdue=0,
            status='ACTIVE',
            loan_officer=self.user,
            disbursement_date=date.today() - timedelta(days=60)
        )
        
        # Overdue loan (45 days)
        Loan.objects.create(
            loan_number='LOAN-002',
            customer=self.customer2,
            loan_product=self.loan_product,
            principal_amount=Decimal('50000.00'),
            interest_rate=Decimal('12.00'),
            interest_method='REDUCING_BALANCE',
            loan_term_months=12,
            repayment_frequency='MONTHLY',
            total_amount=Decimal('56000.00'),
            monthly_installment=Decimal('4666.67'),
            outstanding_principal=Decimal('40000.00'),
            outstanding_interest=Decimal('4000.00'),
            total_outstanding=Decimal('44000.00'),
            days_overdue=45,
            status='OVERDUE',
            loan_officer=self.user,
            disbursement_date=date.today() - timedelta(days=105)
        )
        
        # NPL loan (120 days)
        Loan.objects.create(
            loan_number='LOAN-003',
            customer=self.customer1,
            loan_product=self.loan_product,
            principal_amount=Decimal('30000.00'),
            interest_rate=Decimal('12.00'),
            interest_method='REDUCING_BALANCE',
            loan_term_months=12,
            repayment_frequency='MONTHLY',
            total_amount=Decimal('33600.00'),
            monthly_installment=Decimal('2800.00'),
            outstanding_principal=Decimal('25000.00'),
            outstanding_interest=Decimal('2500.00'),
            total_outstanding=Decimal('27500.00'),
            days_overdue=120,
            status='NPL',
            loan_officer=self.user,
            disbursement_date=date.today() - timedelta(days=180)
        )
        
        # Generate aged receivables
        result = LoanReportingService.generate_aged_receivables()
        
        # Assertions
        self.assertEqual(result['totals']['total_loans'], 3)
        self.assertEqual(
            result['totals']['total_outstanding'],
            Decimal('170500.00')  # 99000 + 44000 + 27500
        )
        
        # Check aging buckets
        aging_summary = result['aging_summary']
        
        # Current bucket (0 days)
        current = next(b for b in aging_summary if b['bucket'] == 'Current')
        self.assertEqual(current['loan_count'], 1)
        self.assertEqual(current['total_outstanding'], Decimal('99000.00'))
        
        # 31-60 days bucket
        bucket_31_60 = next(b for b in aging_summary if b['bucket'] == '31-60 Days')
        self.assertEqual(bucket_31_60['loan_count'], 1)
        self.assertEqual(bucket_31_60['total_outstanding'], Decimal('44000.00'))
        
        # 90+ days bucket
        bucket_90_plus = next(b for b in aging_summary if b['bucket'] == '90+ Days')
        self.assertEqual(bucket_90_plus['loan_count'], 1)
        self.assertEqual(bucket_90_plus['total_outstanding'], Decimal('27500.00'))
    
    def test_npl_report(self):
        """Test NPL report generation"""
        # Create active loan (not NPL)
        Loan.objects.create(
            loan_number='LOAN-001',
            customer=self.customer1,
            loan_product=self.loan_product,
            principal_amount=Decimal('100000.00'),
            interest_rate=Decimal('12.00'),
            interest_method='REDUCING_BALANCE',
            loan_term_months=12,
            repayment_frequency='MONTHLY',
            total_amount=Decimal('112000.00'),
            monthly_installment=Decimal('9333.33'),
            outstanding_principal=Decimal('90000.00'),
            total_outstanding=Decimal('99000.00'),
            days_overdue=0,
            status='ACTIVE',
            loan_officer=self.user,
            disbursement_date=date.today() - timedelta(days=60)
        )
        
        # Create NPL loan (120 days overdue)
        Loan.objects.create(
            loan_number='LOAN-002',
            customer=self.customer2,
            loan_product=self.loan_product,
            principal_amount=Decimal('50000.00'),
            interest_rate=Decimal('12.00'),
            interest_method='REDUCING_BALANCE',
            loan_term_months=12,
            repayment_frequency='MONTHLY',
            total_amount=Decimal('56000.00'),
            monthly_installment=Decimal('4666.67'),
            outstanding_principal=Decimal('40000.00'),
            total_outstanding=Decimal('44000.00'),
            days_overdue=120,
            status='NPL',
            loan_officer=self.user,
            disbursement_date=date.today() - timedelta(days=180)
        )
        
        # Generate NPL report
        result = LoanReportingService.generate_npl_report(threshold_days=90)
        
        # Assertions
        self.assertEqual(result['npl_summary']['npl_count'], 1)
        self.assertEqual(result['npl_summary']['npl_outstanding'], Decimal('44000.00'))
        self.assertEqual(result['portfolio_summary']['total_loans'], 2)
        self.assertEqual(
            result['portfolio_summary']['total_outstanding'],
            Decimal('143000.00')  # 99000 + 44000
        )
        
        # NPL Ratio = 44000 / 143000 * 100 = 30.77%
        expected_ratio = Decimal('30.77')
        self.assertAlmostEqual(
            float(result['npl_ratio']),
            float(expected_ratio),
            places=1
        )
    
    def test_par_calculation(self):
        """Test PAR calculation"""
        # Create loans with different overdue days
        # Current loan
        Loan.objects.create(
            loan_number='LOAN-001',
            customer=self.customer1,
            loan_product=self.loan_product,
            principal_amount=Decimal('100000.00'),
            interest_rate=Decimal('12.00'),
            interest_method='REDUCING_BALANCE',
            loan_term_months=12,
            repayment_frequency='MONTHLY',
            total_amount=Decimal('112000.00'),
            monthly_installment=Decimal('9333.33'),
            outstanding_principal=Decimal('100000.00'),
            total_outstanding=Decimal('112000.00'),
            days_overdue=0,
            status='ACTIVE',
            loan_officer=self.user
        )
        
        # 5 days overdue
        Loan.objects.create(
            loan_number='LOAN-002',
            customer=self.customer2,
            loan_product=self.loan_product,
            principal_amount=Decimal('50000.00'),
            interest_rate=Decimal('12.00'),
            interest_method='REDUCING_BALANCE',
            loan_term_months=12,
            repayment_frequency='MONTHLY',
            total_amount=Decimal('56000.00'),
            monthly_installment=Decimal('4666.67'),
            outstanding_principal=Decimal('50000.00'),
            total_outstanding=Decimal('56000.00'),
            days_overdue=5,
            status='OVERDUE',
            loan_officer=self.user
        )
        
        # 45 days overdue
        Loan.objects.create(
            loan_number='LOAN-003',
            customer=self.customer1,
            loan_product=self.loan_product,
            principal_amount=Decimal('30000.00'),
            interest_rate=Decimal('12.00'),
            interest_method='REDUCING_BALANCE',
            loan_term_months=12,
            repayment_frequency='MONTHLY',
            total_amount=Decimal('33600.00'),
            monthly_installment=Decimal('2800.00'),
            outstanding_principal=Decimal('30000.00'),
            total_outstanding=Decimal('33600.00'),
            days_overdue=45,
            status='OVERDUE',
            loan_officer=self.user
        )
        
        # Generate PAR
        result = LoanReportingService.calculate_par(days=[1, 7, 30, 90])
        
        # Total portfolio
        total_portfolio = Decimal('201600.00')  # 112000 + 56000 + 33600
        self.assertEqual(result['portfolio_total'], total_portfolio)
        
        # PAR 1: Loans with > 1 day overdue = LOAN-002 + LOAN-003
        par_1 = next(p for p in result['par_calculations'] if p['days'] == 1)
        self.assertEqual(par_1['loan_count'], 2)
        self.assertEqual(par_1['amount'], Decimal('89600.00'))  # 56000 + 33600
        
        # PAR 1 Ratio = 89600 / 201600 * 100 = 44.44%
        expected_par_1_ratio = Decimal('44.44')
        self.assertAlmostEqual(
            float(par_1['ratio']),
            float(expected_par_1_ratio),
            places=1
        )
        
        # PAR 30: Loans with > 30 days overdue = LOAN-003 only
        par_30 = next(p for p in result['par_calculations'] if p['days'] == 30)
        self.assertEqual(par_30['loan_count'], 1)
        self.assertEqual(par_30['amount'], Decimal('33600.00'))
    
    def test_portfolio_summary(self):
        """Test portfolio summary generation"""
        # Create various loans
        Loan.objects.create(
            loan_number='LOAN-001',
            customer=self.customer1,
            loan_product=self.loan_product,
            principal_amount=Decimal('100000.00'),
            interest_rate=Decimal('12.00'),
            interest_method='REDUCING_BALANCE',
            loan_term_months=12,
            repayment_frequency='MONTHLY',
            total_amount=Decimal('112000.00'),
            monthly_installment=Decimal('9333.33'),
            outstanding_principal=Decimal('90000.00'),
            total_outstanding=Decimal('99000.00'),
            total_paid=Decimal('13000.00'),
            status='ACTIVE',
            loan_officer=self.user
        )
        
        Loan.objects.create(
            loan_number='LOAN-002',
            customer=self.customer2,
            loan_product=self.loan_product,
            principal_amount=Decimal('50000.00'),
            interest_rate=Decimal('12.00'),
            interest_method='REDUCING_BALANCE',
            loan_term_months=12,
            repayment_frequency='MONTHLY',
            total_amount=Decimal('56000.00'),
            monthly_installment=Decimal('4666.67'),
            outstanding_principal=Decimal('0.00'),
            total_outstanding=Decimal('0.00'),
            total_paid=Decimal('56000.00'),
            status='CLOSED',
            loan_officer=self.user
        )
        
        # Generate summary
        result = LoanReportingService.generate_loan_portfolio_summary()
        
        # Assertions
        self.assertEqual(result['portfolio_overview']['total_loans'], 2)
        self.assertEqual(
            result['portfolio_overview']['total_principal_disbursed'],
            Decimal('150000.00')
        )
        self.assertEqual(
            result['portfolio_overview']['total_outstanding'],
            Decimal('99000.00')
        )
        self.assertEqual(
            result['portfolio_overview']['total_paid'],
            Decimal('69000.00')
        )
        
        # Check by status
        by_status = result['by_status']
        active_status = next(s for s in by_status if s['status'] == 'ACTIVE')
        self.assertEqual(active_status['loan_count'], 1)
        self.assertEqual(active_status['outstanding'], Decimal('99000.00'))
