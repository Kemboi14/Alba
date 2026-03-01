"""
Comprehensive Test Suite for Double-Entry Accounting System

Tests all accounting models and services to ensure:
- Data integrity (debits = credits)
- Transaction safety (atomic operations)
- Business rule compliance
- Validation logic
"""
from decimal import Decimal
from datetime import date, timedelta
from django.test import TestCase
from django.core.exceptions import ValidationError
from django.db import transaction
from django.contrib.auth import get_user_model

from apps.accounting.models import (
    FiscalYear,
    AccountType,
    Account,
    JournalEntry,
    JournalEntryLine,
)
from apps.accounting.services import AccountingService

User = get_user_model()


class FiscalYearModelTest(TestCase):
    """Test FiscalYear model"""
    
    def setUp(self):
        self.user = User.objects.create_user(
            email='test@example.com',
            password='testpass123',
            first_name='Test',
            last_name='User',
        )
    
    def test_create_fiscal_year(self):
        """Test creating a fiscal year"""
        fy = FiscalYear.objects.create(
            name="FY 2026",
            start_date=date(2026, 1, 1),
            end_date=date(2026, 12, 31),
            is_active=True,
            created_by=self.user,
        )
        self.assertEqual(fy.name, "FY 2026")
        self.assertTrue(fy.is_active)
        self.assertFalse(fy.is_closed)
    
    def test_fiscal_year_unique_name(self):
        """Test fiscal year name uniqueness"""
        FiscalYear.objects.create(
            name="FY 2026",
            start_date=date(2026, 1, 1),
            end_date=date(2026, 12, 31),
            created_by=self.user,
        )
        
        with self.assertRaises(Exception):
            FiscalYear.objects.create(
                name="FY 2026",
                start_date=date(2026, 1, 1),
                end_date=date(2026, 12, 31),
                created_by=self.user,
            )


class AccountTypeModelTest(TestCase):
    """Test AccountType model with validation"""
    
    def test_create_account_types(self):
        """Test creating all account types"""
        asset = AccountType.objects.create(
            name=AccountType.ASSET,
            normal_balance='DEBIT'
        )
        self.assertEqual(asset.name, AccountType.ASSET)
        self.assertEqual(asset.normal_balance, 'DEBIT')
    
    def test_asset_must_have_debit_normal_balance(self):
        """Test Asset accounts must have DEBIT normal balance"""
        account_type = AccountType(
            name=AccountType.ASSET,
            normal_balance='CREDIT'  # Wrong!
        )
        
        with self.assertRaises(ValidationError):
            account_type.clean()
    
    def test_liability_must_have_credit_normal_balance(self):
        """Test Liability accounts must have CREDIT normal balance"""
        account_type = AccountType(
            name=AccountType.LIABILITY,
            normal_balance='DEBIT'  # Wrong!
        )
        
        with self.assertRaises(ValidationError):
            account_type.clean()
    
    def test_expense_must_have_debit_normal_balance(self):
        """Test Expense accounts must have DEBIT normal balance"""
        account_type = AccountType(
            name=AccountType.EXPENSE,
            normal_balance='CREDIT'  # Wrong!
        )
        
        with self.assertRaises(ValidationError):
            account_type.clean()
    
    def test_income_must_have_credit_normal_balance(self):
        """Test Income accounts must have CREDIT normal balance"""
        account_type = AccountType(
            name=AccountType.INCOME,
            normal_balance='DEBIT'  # Wrong!
        )
        
        with self.assertRaises(ValidationError):
            account_type.clean()


class AccountModelTest(TestCase):
    """Test Account model with hierarchical structure"""
    
    def setUp(self):
        self.user = User.objects.create_user(
            email='test@example.com',
            password='testpass123',
            first_name='Test',
            last_name='User',
        )
        
        self.asset_type = AccountType.objects.create(
            name=AccountType.ASSET,
            normal_balance='DEBIT'
        )
        
        self.expense_type = AccountType.objects.create(
            name=AccountType.EXPENSE,
            normal_balance='DEBIT'
        )
    
    def test_create_account(self):
        """Test creating an account"""
        account = Account.objects.create(
            code="1000",
            name="Cash",
            account_type=self.asset_type,
            created_by=self.user,
        )
        self.assertEqual(account.code, "1000")
        self.assertEqual(account.name, "Cash")
        self.assertTrue(account.is_active)
    
    def test_account_code_uniqueness(self):
        """Test account codes must be unique"""
        Account.objects.create(
            code="1000",
            name="Cash",
            account_type=self.asset_type,
            created_by=self.user,
        )
        
        with self.assertRaises(Exception):
            Account.objects.create(
                code="1000",  # Duplicate!
                name="Another Account",
                account_type=self.asset_type,
                created_by=self.user,
            )
    
    def test_hierarchical_accounts(self):
        """Test parent-child account relationships"""
        parent = Account.objects.create(
            code="1000",
            name="Assets",
            account_type=self.asset_type,
            created_by=self.user,
        )
        
        child = Account.objects.create(
            code="1100",
            name="Current Assets",
            account_type=self.asset_type,
            parent_account=parent,
            created_by=self.user,
        )
        
        self.assertEqual(child.parent_account, parent)
        self.assertIn(child, parent.sub_accounts.all())
    
    def test_parent_account_type_must_match(self):
        """Test parent account must be same type as child"""
        asset_parent = Account.objects.create(
            code="1000",
            name="Assets",
            account_type=self.asset_type,
            created_by=self.user,
        )
        
        # Try to create expense account with asset parent
        expense_child = Account(
            code="5000",
            name="Expenses",
            account_type=self.expense_type,
            parent_account=asset_parent,
            created_by=self.user,
        )
        
        with self.assertRaises(ValidationError):
            expense_child.clean()
    
    def test_get_full_path(self):
        """Test account full path generation"""
        parent = Account.objects.create(
            code="1000",
            name="Assets",
            account_type=self.asset_type,
            created_by=self.user,
        )
        
        child = Account.objects.create(
            code="1100",
            name="Current Assets",
            account_type=self.asset_type,
            parent_account=parent,
            created_by=self.user,
        )
        
        grandchild = Account.objects.create(
            code="1110",
            name="Cash",
            account_type=self.asset_type,
            parent_account=child,
            created_by=self.user,
        )
        
        self.assertEqual(grandchild.get_full_path(), "Assets > Current Assets > Cash")


class JournalEntryModelTest(TestCase):
    """Test JournalEntry model with posting and reversal"""
    
    def setUp(self):
        self.user = User.objects.create_user(
            email='test@example.com',
            password='testpass123',
            first_name='Test',
            last_name='User',
        )
        
        self.fiscal_year = FiscalYear.objects.create(
            name="FY 2026",
            start_date=date(2026, 1, 1),
            end_date=date(2026, 12, 31),
            is_active=True,
            created_by=self.user,
        )
        
        asset_type = AccountType.objects.create(
            name=AccountType.ASSET,
            normal_balance='DEBIT'
        )
        
        income_type = AccountType.objects.create(
            name=AccountType.INCOME,
            normal_balance='CREDIT'
        )
        
        self.cash = Account.objects.create(
            code="1000",
            name="Cash",
            account_type=asset_type,
            created_by=self.user,
        )
        
        self.revenue = Account.objects.create(
            code="4000",
            name="Sales Revenue",
            account_type=income_type,
            created_by=self.user,
        )
    
    def test_create_journal_entry(self):
        """Test creating a journal entry"""
        entry = JournalEntry.objects.create(
            entry_number="JE-2026-00001",
            date=date(2026, 6, 1),
            fiscal_year=self.fiscal_year,
            description="Test entry",
            created_by=self.user,
        )
        
        self.assertEqual(entry.entry_number, "JE-2026-00001")
        self.assertEqual(entry.status, 'DRAFT')
    
    def test_is_balanced_true(self):
        """Test balanced entry returns True"""
        entry = JournalEntry.objects.create(
            entry_number="JE-2026-00001",
            date=date(2026, 6, 1),
            fiscal_year=self.fiscal_year,
            description="Balanced entry",
            created_by=self.user,
        )
        
        # Add balanced lines
        JournalEntryLine.objects.create(
            journal_entry=entry,
            account=self.cash,
            description="Cash debit",
            debit_amount=Decimal('1000.00'),
            credit_amount=Decimal('0.00'),
        )
        
        JournalEntryLine.objects.create(
            journal_entry=entry,
            account=self.revenue,
            description="Revenue credit",
            debit_amount=Decimal('0.00'),
            credit_amount=Decimal('1000.00'),
        )
        
        self.assertTrue(entry.is_balanced())
    
    def test_is_balanced_false(self):
        """Test unbalanced entry returns False"""
        entry = JournalEntry.objects.create(
            entry_number="JE-2026-00001",
            date=date(2026, 6, 1),
            fiscal_year=self.fiscal_year,
            description="Unbalanced entry",
            created_by=self.user,
        )
        
        # Add unbalanced lines
        JournalEntryLine.objects.create(
            journal_entry=entry,
            account=self.cash,
            description="Cash debit",
            debit_amount=Decimal('1000.00'),
            credit_amount=Decimal('0.00'),
        )
        
        JournalEntryLine.objects.create(
            journal_entry=entry,
            account=self.revenue,
            description="Revenue credit",
            debit_amount=Decimal('0.00'),
            credit_amount=Decimal('500.00'),  # Only $500, not $1000!
        )
        
        self.assertFalse(entry.is_balanced())
    
    def test_cannot_post_unbalanced_entry(self):
        """Test posting unbalanced entry raises error"""
        entry = JournalEntry.objects.create(
            entry_number="JE-2026-00001",
            date=date(2026, 6, 1),
            fiscal_year=self.fiscal_year,
            description="Unbalanced entry",
            created_by=self.user,
        )
        
        JournalEntryLine.objects.create(
            journal_entry=entry,
            account=self.cash,
            description="Cash debit",
            debit_amount=Decimal('1000.00'),
            credit_amount=Decimal('0.00'),
        )
        
        JournalEntryLine.objects.create(
            journal_entry=entry,
            account=self.revenue,
            description="Revenue credit",
            debit_amount=Decimal('0.00'),
            credit_amount=Decimal('500.00'),
        )
        
        with self.assertRaises(ValidationError) as cm:
            entry.post(self.user)
        
        self.assertIn('unbalanced', str(cm.exception).lower())
    
    def test_post_balanced_entry(self):
        """Test posting a balanced entry"""
        entry = JournalEntry.objects.create(
            entry_number="JE-2026-00001",
            date=date(2026, 6, 1),
            fiscal_year=self.fiscal_year,
            description="Balanced entry",
            created_by=self.user,
        )
        
        JournalEntryLine.objects.create(
            journal_entry=entry,
            account=self.cash,
            description="Cash debit",
            debit_amount=Decimal('1000.00'),
            credit_amount=Decimal('0.00'),
        )
        
        JournalEntryLine.objects.create(
            journal_entry=entry,
            account=self.revenue,
            description="Revenue credit",
            debit_amount=Decimal('0.00'),
            credit_amount=Decimal('1000.00'),
        )
        
        entry.post(self.user)
        
        entry.refresh_from_db()
        self.assertEqual(entry.status, 'POSTED')
        self.assertIsNotNone(entry.posted_at)
        self.assertEqual(entry.posted_by, self.user)
    
    def test_cannot_post_already_posted_entry(self):
        """Test cannot post an already posted entry"""
        entry = JournalEntry.objects.create(
            entry_number="JE-2026-00001",
            date=date(2026, 6, 1),
            fiscal_year=self.fiscal_year,
            description="Balanced entry",
            created_by=self.user,
        )
        
        JournalEntryLine.objects.create(
            journal_entry=entry,
            account=self.cash,
            description="Cash debit",
            debit_amount=Decimal('1000.00'),
            credit_amount=Decimal('0.00'),
        )
        
        JournalEntryLine.objects.create(
            journal_entry=entry,
            account=self.revenue,
            description="Revenue credit",
            debit_amount=Decimal('0.00'),
            credit_amount=Decimal('1000.00'),
        )
        
        entry.post(self.user)
        
        with self.assertRaises(ValidationError) as cm:
            entry.post(self.user)
        
        self.assertIn('already posted', str(cm.exception).lower())
    
    def test_reverse_posted_entry(self):
        """Test reversing a posted entry"""
        entry = JournalEntry.objects.create(
            entry_number="JE-2026-00001",
            date=date(2026, 6, 1),
            fiscal_year=self.fiscal_year,
            description="Entry to reverse",
            created_by=self.user,
        )
        
        JournalEntryLine.objects.create(
            journal_entry=entry,
            account=self.cash,
            description="Cash debit",
            debit_amount=Decimal('1000.00'),
            credit_amount=Decimal('0.00'),
        )
        
        JournalEntryLine.objects.create(
            journal_entry=entry,
            account=self.revenue,
            description="Revenue credit",
            debit_amount=Decimal('0.00'),
            credit_amount=Decimal('1000.00'),
        )
        
        entry.post(self.user)
        
        # Reverse the entry
        reversing_entry = entry.reverse(self.user, "Test reversal")
        
        entry.refresh_from_db()
        self.assertEqual(entry.status, 'REVERSED')
        self.assertEqual(reversing_entry.status, 'POSTED')
        self.assertEqual(reversing_entry.reversed_entry, entry)
        
        # Check lines are swapped
        original_lines = list(entry.lines.all())
        reversing_lines = list(reversing_entry.lines.all())
        
        self.assertEqual(original_lines[0].debit_amount, reversing_lines[0].credit_amount)
        self.assertEqual(original_lines[0].credit_amount, reversing_lines[0].debit_amount)
    
    def test_cannot_reverse_draft_entry(self):
        """Test cannot reverse a draft entry"""
        entry = JournalEntry.objects.create(
            entry_number="JE-2026-00001",
            date=date(2026, 6, 1),
            fiscal_year=self.fiscal_year,
            description="Draft entry",
            created_by=self.user,
        )
        
        with self.assertRaises(ValidationError) as cm:
            entry.reverse(self.user, "Cannot reverse draft")
        
        self.assertIn('only posted', str(cm.exception).lower())
    
    def test_get_total_debit(self):
        """Test getting total debit amount"""
        entry = JournalEntry.objects.create(
            entry_number="JE-2026-00001",
            date=date(2026, 6, 1),
            fiscal_year=self.fiscal_year,
            description="Test entry",
            created_by=self.user,
        )
        
        JournalEntryLine.objects.create(
            journal_entry=entry,
            account=self.cash,
            description="Line 1",
            debit_amount=Decimal('500.00'),
            credit_amount=Decimal('0.00'),
        )
        
        JournalEntryLine.objects.create(
            journal_entry=entry,
            account=self.cash,
            description="Line 2",
            debit_amount=Decimal('300.00'),
            credit_amount=Decimal('0.00'),
        )
        
        self.assertEqual(entry.get_total_debit(), Decimal('800.00'))
    
    def test_get_total_credit(self):
        """Test getting total credit amount"""
        entry = JournalEntry.objects.create(
            entry_number="JE-2026-00001",
            date=date(2026, 6, 1),
            fiscal_year=self.fiscal_year,
            description="Test entry",
            created_by=self.user,
        )
        
        JournalEntryLine.objects.create(
            journal_entry=entry,
            account=self.revenue,
            description="Line 1",
            debit_amount=Decimal('0.00'),
            credit_amount=Decimal('600.00'),
        )
        
        JournalEntryLine.objects.create(
            journal_entry=entry,
            account=self.revenue,
            description="Line 2",
            debit_amount=Decimal('0.00'),
            credit_amount=Decimal('200.00'),
        )
        
        self.assertEqual(entry.get_total_credit(), Decimal('800.00'))


class JournalEntryLineModelTest(TestCase):
    """Test JournalEntryLine model validation"""
    
    def setUp(self):
        self.user = User.objects.create_user(
            email='test@example.com',
            password='testpass123',
            first_name='Test',
            last_name='User',
        )
        
        self.fiscal_year = FiscalYear.objects.create(
            name="FY 2026",
            start_date=date(2026, 1, 1),
            end_date=date(2026, 12, 31),
            is_active=True,
            created_by=self.user,
        )
        
        asset_type = AccountType.objects.create(
            name=AccountType.ASSET,
            normal_balance='DEBIT'
        )
        
        self.cash = Account.objects.create(
            code="1000",
            name="Cash",
            account_type=asset_type,
            created_by=self.user,
        )
        
        self.entry = JournalEntry.objects.create(
            entry_number="JE-2026-00001",
            date=date(2026, 6, 1),
            fiscal_year=self.fiscal_year,
            description="Test entry",
            created_by=self.user,
        )
    
    def test_create_debit_line(self):
        """Test creating a debit line"""
        line = JournalEntryLine.objects.create(
            journal_entry=self.entry,
            account=self.cash,
            description="Cash debit",
            debit_amount=Decimal('1000.00'),
            credit_amount=Decimal('0.00'),
        )
        
        self.assertEqual(line.debit_amount, Decimal('1000.00'))
        self.assertEqual(line.credit_amount, Decimal('0.00'))
    
    def test_create_credit_line(self):
        """Test creating a credit line"""
        line = JournalEntryLine.objects.create(
            journal_entry=self.entry,
            account=self.cash,
            description="Cash credit",
            debit_amount=Decimal('0.00'),
            credit_amount=Decimal('500.00'),
        )
        
        self.assertEqual(line.debit_amount, Decimal('0.00'))
        self.assertEqual(line.credit_amount, Decimal('500.00'))
    
    def test_cannot_have_both_debit_and_credit(self):
        """Test line cannot have both debit and credit amounts"""
        line = JournalEntryLine(
            journal_entry=self.entry,
            account=self.cash,
            description="Invalid line",
            debit_amount=Decimal('100.00'),
            credit_amount=Decimal('100.00'),  # Both set!
        )
        
        with self.assertRaises(ValidationError) as cm:
            line.clean()
        
        self.assertIn('both debit and credit', str(cm.exception).lower())
    
    def test_must_have_at_least_one_amount(self):
        """Test line must have at least one non-zero amount"""
        line = JournalEntryLine(
            journal_entry=self.entry,
            account=self.cash,
            description="Invalid line",
            debit_amount=Decimal('0.00'),
            credit_amount=Decimal('0.00'),  # Both zero!
        )
        
        with self.assertRaises(ValidationError) as cm:
            line.clean()
        
        self.assertIn('greater than zero', str(cm.exception).lower())
    
    def test_get_amount(self):
        """Test getting non-zero amount"""
        debit_line = JournalEntryLine.objects.create(
            journal_entry=self.entry,
            account=self.cash,
            description="Debit line",
            debit_amount=Decimal('150.00'),
            credit_amount=Decimal('0.00'),
        )
        
        credit_line = JournalEntryLine.objects.create(
            journal_entry=self.entry,
            account=self.cash,
            description="Credit line",
            debit_amount=Decimal('0.00'),
            credit_amount=Decimal('250.00'),
        )
        
        self.assertEqual(debit_line.get_amount(), Decimal('150.00'))
        self.assertEqual(credit_line.get_amount(), Decimal('250.00'))
    
    def test_get_side(self):
        """Test getting debit/credit side"""
        debit_line = JournalEntryLine.objects.create(
            journal_entry=self.entry,
            account=self.cash,
            description="Debit line",
            debit_amount=Decimal('150.00'),
            credit_amount=Decimal('0.00'),
        )
        
        credit_line = JournalEntryLine.objects.create(
            journal_entry=self.entry,
            account=self.cash,
            description="Credit line",
            debit_amount=Decimal('0.00'),
            credit_amount=Decimal('250.00'),
        )
        
        self.assertEqual(debit_line.get_side(), 'DEBIT')
        self.assertEqual(credit_line.get_side(), 'CREDIT')


class AccountBalanceTest(TestCase):
    """Test account balance calculations"""
    
    def setUp(self):
        self.user = User.objects.create_user(
            email='test@example.com',
            password='testpass123',
            first_name='Test',
            last_name='User',
        )
        
        self.fiscal_year = FiscalYear.objects.create(
            name="FY 2026",
            start_date=date(2026, 1, 1),
            end_date=date(2026, 12, 31),
            is_active=True,
            created_by=self.user,
        )
        
        asset_type = AccountType.objects.create(
            name=AccountType.ASSET,
            normal_balance='DEBIT'
        )
        
        income_type = AccountType.objects.create(
            name=AccountType.INCOME,
            normal_balance='CREDIT'
        )
        
        self.cash = Account.objects.create(
            code="1000",
            name="Cash",
            account_type=asset_type,
            created_by=self.user,
        )
        
        self.revenue = Account.objects.create(
            code="4000",
            name="Sales Revenue",
            account_type=income_type,
            created_by=self.user,
        )
    
    def test_asset_account_balance(self):
        """Test asset account balance calculation (debit increases)"""
        # Create and post entry
        entry = JournalEntry.objects.create(
            entry_number="JE-2026-00001",
            date=date(2026, 6, 1),
            fiscal_year=self.fiscal_year,
            description="Cash sale",
            created_by=self.user,
        )
        
        JournalEntryLine.objects.create(
            journal_entry=entry,
            account=self.cash,
            description="Cash received",
            debit_amount=Decimal('1000.00'),
            credit_amount=Decimal('0.00'),
        )
        
        JournalEntryLine.objects.create(
            journal_entry=entry,
            account=self.revenue,
            description="Revenue",
            debit_amount=Decimal('0.00'),
            credit_amount=Decimal('1000.00'),
        )
        
        entry.post(self.user)
        
        # Check balances
        self.assertEqual(self.cash.get_balance(), Decimal('1000.00'))
    
    def test_revenue_account_balance(self):
        """Test revenue account balance calculation (credit increases)"""
        entry = JournalEntry.objects.create(
            entry_number="JE-2026-00001",
            date=date(2026, 6, 1),
            fiscal_year=self.fiscal_year,
            description="Sale",
            created_by=self.user,
        )
        
        JournalEntryLine.objects.create(
            journal_entry=entry,
            account=self.cash,
            description="Cash",
            debit_amount=Decimal('500.00'),
            credit_amount=Decimal('0.00'),
        )
        
        JournalEntryLine.objects.create(
            journal_entry=entry,
            account=self.revenue,
            description="Revenue",
            debit_amount=Decimal('0.00'),
            credit_amount=Decimal('500.00'),
        )
        
        entry.post(self.user)
        
        self.assertEqual(self.revenue.get_balance(), Decimal('500.00'))
    
    def test_multiple_transactions_balance(self):
        """Test balance with multiple transactions"""
        # Transaction 1: Cash debit $1000
        entry1 = JournalEntry.objects.create(
            entry_number="JE-2026-00001",
            date=date(2026, 6, 1),
            fiscal_year=self.fiscal_year,
            description="Sale 1",
            created_by=self.user,
        )
        
        JournalEntryLine.objects.create(
            journal_entry=entry1,
            account=self.cash,
            description="Cash",
            debit_amount=Decimal('1000.00'),
            credit_amount=Decimal('0.00'),
        )
        
        JournalEntryLine.objects.create(
            journal_entry=entry1,
            account=self.revenue,
            description="Revenue",
            debit_amount=Decimal('0.00'),
            credit_amount=Decimal('1000.00'),
        )
        
        entry1.post(self.user)
        
        # Transaction 2: Cash credit $300
        entry2 = JournalEntry.objects.create(
            entry_number="JE-2026-00002",
            date=date(2026, 6, 2),
            fiscal_year=self.fiscal_year,
            description="Payment",
            created_by=self.user,
        )
        
        expense_type = AccountType.objects.create(
            name=AccountType.EXPENSE,
            normal_balance='DEBIT'
        )
        
        expense = Account.objects.create(
            code="5000",
            name="Expense",
            account_type=expense_type,
            created_by=self.user,
        )
        
        JournalEntryLine.objects.create(
            journal_entry=entry2,
            account=expense,
            description="Expense",
            debit_amount=Decimal('300.00'),
            credit_amount=Decimal('0.00'),
        )
        
        JournalEntryLine.objects.create(
            journal_entry=entry2,
            account=self.cash,
            description="Cash payment",
            debit_amount=Decimal('0.00'),
            credit_amount=Decimal('300.00'),
        )
        
        entry2.post(self.user)
        
        # Cash balance should be $1000 - $300 = $700
        self.assertEqual(self.cash.get_balance(), Decimal('700.00'))


class AccountingServiceTest(TestCase):
    """Test AccountingService class"""
    
    def setUp(self):
        self.user = User.objects.create_user(
            email='test@example.com',
            password='testpass123',
            first_name='Test',
            last_name='User',
        )
        
        self.fiscal_year = FiscalYear.objects.create(
            name="FY 2026",
            start_date=date(2026, 1, 1),
            end_date=date(2026, 12, 31),
            is_active=True,
            created_by=self.user,
        )
        
        asset_type = AccountType.objects.create(
            name=AccountType.ASSET,
            normal_balance='DEBIT'
        )
        
        income_type = AccountType.objects.create(
            name=AccountType.INCOME,
            normal_balance='CREDIT'
        )
        
        self.cash = Account.objects.create(
            code="1000",
            name="Cash",
            account_type=asset_type,
            created_by=self.user,
        )
        
        self.revenue = Account.objects.create(
            code="4000",
            name="Sales Revenue",
            account_type=income_type,
            created_by=self.user,
        )
    
    def test_generate_entry_number(self):
        """Test entry number generation"""
        entry_number = AccountingService.generate_entry_number()
        self.assertIn("JE-", entry_number)
        self.assertIn("2026", entry_number)  # Current year
    
    def test_create_simple_entry(self):
        """Test creating simple two-line entry"""
        entry = AccountingService.create_simple_entry(
            date=date.today(),
            fiscal_year=self.fiscal_year,
            description="Test sale",
            debit_account=self.cash,
            credit_account=self.revenue,
            amount=Decimal('1000.00'),
            created_by=self.user,
        )
        
        self.assertEqual(entry.lines.count(), 2)
        self.assertTrue(entry.is_balanced())
        self.assertEqual(entry.status, 'DRAFT')
    
    def test_create_simple_entry_with_auto_post(self):
        """Test creating and auto-posting entry"""
        entry = AccountingService.create_simple_entry(
            date=date.today(),
            fiscal_year=self.fiscal_year,
            description="Test sale",
            debit_account=self.cash,
            credit_account=self.revenue,
            amount=Decimal('500.00'),
            created_by=self.user,
            auto_post=True,
        )
        
        self.assertEqual(entry.status, 'POSTED')
        self.assertIsNotNone(entry.posted_at)
    
    def test_create_journal_entry_with_multiple_lines(self):
        """Test creating entry with multiple lines"""
        expense_type = AccountType.objects.create(
            name=AccountType.EXPENSE,
            normal_balance='DEBIT'
        )
        
        expense1 = Account.objects.create(
            code="5000",
            name="Expense 1",
            account_type=expense_type,
            created_by=self.user,
        )
        
        expense2 = Account.objects.create(
            code="5100",
            name="Expense 2",
            account_type=expense_type,
            created_by=self.user,
        )
        
        entry = AccountingService.create_journal_entry(
            date=date.today(),
            fiscal_year=self.fiscal_year,
            description="Multiple expenses",
            lines=[
                {
                    'account': expense1,
                    'description': "Expense 1",
                    'debit_amount': Decimal('300.00'),
                    'credit_amount': Decimal('0.00'),
                },
                {
                    'account': expense2,
                    'description': "Expense 2",
                    'debit_amount': Decimal('200.00'),
                    'credit_amount': Decimal('0.00'),
                },
                {
                    'account': self.cash,
                    'description': "Cash payment",
                    'debit_amount': Decimal('0.00'),
                    'credit_amount': Decimal('500.00'),
                },
            ],
            created_by=self.user,
        )
        
        self.assertEqual(entry.lines.count(), 3)
        self.assertTrue(entry.is_balanced())
        self.assertEqual(entry.get_total_debit(), Decimal('500.00'))
        self.assertEqual(entry.get_total_credit(), Decimal('500.00'))
    
    def test_cannot_create_unbalanced_entry(self):
        """Test service rejects unbalanced entry"""
        with self.assertRaises(ValidationError) as cm:
            AccountingService.create_journal_entry(
                date=date.today(),
                fiscal_year=self.fiscal_year,
                description="Unbalanced entry",
                lines=[
                    {
                        'account': self.cash,
                        'description': "Cash",
                        'debit_amount': Decimal('1000.00'),
                        'credit_amount': Decimal('0.00'),
                    },
                    {
                        'account': self.revenue,
                        'description': "Revenue",
                        'debit_amount': Decimal('0.00'),
                        'credit_amount': Decimal('500.00'),  # Unbalanced!
                    },
                ],
                created_by=self.user,
            )
        
        self.assertIn('unbalanced', str(cm.exception).lower())
    
    def test_post_journal_entry_service(self):
        """Test posting entry through service"""
        entry = AccountingService.create_simple_entry(
            date=date.today(),
            fiscal_year=self.fiscal_year,
            description="Test",
            debit_account=self.cash,
            credit_account=self.revenue,
            amount=Decimal('100.00'),
            created_by=self.user,
            auto_post=False,
        )
        
        self.assertEqual(entry.status, 'DRAFT')
        
        posted_entry = AccountingService.post_journal_entry(
            entry_id=entry.id,
            user=self.user,
        )
        
        self.assertEqual(posted_entry.status, 'POSTED')
    
    def test_reverse_journal_entry_service(self):
        """Test reversing entry through service"""
        entry = AccountingService.create_simple_entry(
            date=date.today(),
            fiscal_year=self.fiscal_year,
            description="To be reversed",
            debit_account=self.cash,
            credit_account=self.revenue,
            amount=Decimal('250.00'),
            created_by=self.user,
            auto_post=True,
        )
        
        reversing_entry = AccountingService.reverse_journal_entry(
            entry_id=entry.id,
            user=self.user,
            reason="Test reversal",
        )
        
        entry.refresh_from_db()
        self.assertEqual(entry.status, 'REVERSED')
        self.assertEqual(reversing_entry.status, 'POSTED')
        self.assertEqual(reversing_entry.reversed_entry, entry)
    
    def test_validate_account_balance(self):
        """Test account balance validation"""
        AccountingService.create_simple_entry(
            date=date.today(),
            fiscal_year=self.fiscal_year,
            description="Test",
            debit_account=self.cash,
            credit_account=self.revenue,
            amount=Decimal('1000.00'),
            created_by=self.user,
            auto_post=True,
        )
        
        self.assertTrue(
            AccountingService.validate_account_balance(
                self.cash,
                Decimal('1000.00')
            )
        )
        
        self.assertFalse(
            AccountingService.validate_account_balance(
                self.cash,
                Decimal('500.00')
            )
        )
    
    def test_get_trial_balance(self):
        """Test trial balance generation"""
        # Create some transactions
        AccountingService.create_simple_entry(
            date=date.today(),
            fiscal_year=self.fiscal_year,
            description="Sale",
            debit_account=self.cash,
            credit_account=self.revenue,
            amount=Decimal('1000.00'),
            created_by=self.user,
            auto_post=True,
        )
        
        trial_balance = AccountingService.get_trial_balance(self.fiscal_year)
        
        self.assertIn('accounts', trial_balance)
        self.assertIn('total_debits', trial_balance)
        self.assertIn('total_credits', trial_balance)
        self.assertIn('is_balanced', trial_balance)
        self.assertTrue(trial_balance['is_balanced'])
        self.assertEqual(trial_balance['total_debits'], trial_balance['total_credits'])


class TransactionAtomicityTest(TestCase):
    """Test database transaction safety"""
    
    def setUp(self):
        self.user = User.objects.create_user(
            email='test@example.com',
            password='testpass123',
            first_name='Test',
            last_name='User',
        )
        
        self.fiscal_year = FiscalYear.objects.create(
            name="FY 2026",
            start_date=date(2026, 1, 1),
            end_date=date(2026, 12, 31),
            is_active=True,
            created_by=self.user,
        )
        
        asset_type = AccountType.objects.create(
            name=AccountType.ASSET,
            normal_balance='DEBIT'
        )
        
        self.cash = Account.objects.create(
            code="1000",
            name="Cash",
            account_type=asset_type,
            created_by=self.user,
        )
    
    def test_transaction_rollback_on_error(self):
        """Test transaction is rolled back on error"""
        initial_count = JournalEntry.objects.count()
        
        # Try to create unbalanced entry (should fail and rollback)
        try:
            with transaction.atomic():
                entry = JournalEntry.objects.create(
                    entry_number="JE-TEST",
                    date=date.today(),
                    fiscal_year=self.fiscal_year,
                    description="Test",
                    created_by=self.user,
                )
                
                # Add only debit line (unbalanced)
                JournalEntryLine.objects.create(
                    journal_entry=entry,
                    account=self.cash,
                    description="Test",
                    debit_amount=Decimal('100.00'),
                    credit_amount=Decimal('0.00'),
                )
                
                # Try to post (should fail)
                entry.post(self.user)
        except ValidationError:
            pass
        
        # Entry should not exist (rolled back)
        final_count = JournalEntry.objects.count()
        self.assertEqual(initial_count, final_count)


# Run tests with: python manage.py test tests.test_accounting_double_entry
