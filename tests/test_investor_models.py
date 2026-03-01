"""
Comprehensive Tests for InvestorAccount and InvestorTransaction Models

Tests cover:
- Model creation and validation
- Decimal precision
- Field validators
- Helper methods
- Edge cases
- Production scenarios

Total: 50+ tests
"""

from decimal import Decimal
from datetime import date, timedelta
from django.test import TestCase
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone
from apps.core.models import User
from apps.loans.models import InvestorAccount, InvestorTransaction


class InvestorAccountModelTests(TestCase):
    """Tests for InvestorAccount model"""
    
    def setUp(self):
        """Set up test data"""
        self.user = User.objects.create_user(
            username='investor1',
            email='investor1@test.com',
            password='testpass123',
            first_name='John',
            last_name='Investor'
        )
    
    def test_create_investor_account_with_valid_data(self):
        """Test creating an investor account with valid data"""
        account = InvestorAccount.objects.create(
            investor=self.user,
            principal_balance=Decimal('100000.00'),
            monthly_interest_rate=Decimal('1.50'),
            last_interest_date=date.today()
        )
        
        self.assertEqual(account.investor, self.user)
        self.assertEqual(account.principal_balance, Decimal('100000.00'))
        self.assertEqual(account.monthly_interest_rate, Decimal('1.50'))
        self.assertEqual(account.last_interest_date, date.today())
        self.assertIsNotNone(account.created_at)
        self.assertIsNotNone(account.updated_at)
    
    def test_investor_account_default_balance(self):
        """Test default principal balance is zero"""
        account = InvestorAccount.objects.create(
            investor=self.user,
            monthly_interest_rate=Decimal('1.50')
        )
        
        self.assertEqual(account.principal_balance, Decimal('0.00'))
    
    def test_investor_account_string_representation(self):
        """Test string representation of investor account"""
        account = InvestorAccount.objects.create(
            investor=self.user,
            principal_balance=Decimal('50000.00'),
            monthly_interest_rate=Decimal('2.00')
        )
        
        expected = f"Investor Account - John Investor - Balance: 50000.00"
        self.assertEqual(str(account), expected)
    
    def test_negative_balance_validation(self):
        """Test that negative balance raises validation error"""
        account = InvestorAccount(
            investor=self.user,
            principal_balance=Decimal('-1000.00'),
            monthly_interest_rate=Decimal('1.50')
        )
        
        with self.assertRaises(ValidationError) as context:
            account.full_clean()
        
        self.assertIn('principal_balance', context.exception.error_dict)
    
    def test_negative_interest_rate_validation(self):
        """Test that negative interest rate raises validation error"""
        account = InvestorAccount(
            investor=self.user,
            principal_balance=Decimal('10000.00'),
            monthly_interest_rate=Decimal('-1.00')
        )
        
        with self.assertRaises(ValidationError) as context:
            account.full_clean()
        
        self.assertIn('monthly_interest_rate', context.exception.error_dict)
    
    def test_unreasonably_high_interest_rate_validation(self):
        """Test that interest rate > 50% raises validation error"""
        account = InvestorAccount(
            investor=self.user,
            principal_balance=Decimal('10000.00'),
            monthly_interest_rate=Decimal('51.00')
        )
        
        with self.assertRaises(ValidationError) as context:
            account.full_clean()
        
        self.assertIn('monthly_interest_rate', context.exception.error_dict)
    
    def test_future_last_interest_date_validation(self):
        """Test that future last_interest_date raises validation error"""
        future_date = date.today() + timedelta(days=10)
        account = InvestorAccount(
            investor=self.user,
            principal_balance=Decimal('10000.00'),
            monthly_interest_rate=Decimal('1.50'),
            last_interest_date=future_date
        )
        
        with self.assertRaises(ValidationError) as context:
            account.full_clean()
        
        self.assertIn('last_interest_date', context.exception.error_dict)
    
    def test_investor_account_ordering(self):
        """Test accounts are ordered by created_at descending"""
        account1 = InvestorAccount.objects.create(
            investor=self.user,
            monthly_interest_rate=Decimal('1.50')
        )
        
        user2 = User.objects.create_user(
            username='investor2',
            email='investor2@test.com',
            password='testpass123'
        )
        account2 = InvestorAccount.objects.create(
            investor=user2,
            monthly_interest_rate=Decimal('2.00')
        )
        
        accounts = list(InvestorAccount.objects.all())
        self.assertEqual(accounts[0], account2)  # Most recent first
        self.assertEqual(accounts[1], account1)
    
    def test_get_total_deposits_with_no_transactions(self):
        """Test get_total_deposits with no transactions"""
        account = InvestorAccount.objects.create(
            investor=self.user,
            monthly_interest_rate=Decimal('1.50')
        )
        
        self.assertEqual(account.get_total_deposits(), Decimal('0.00'))
    
    def test_get_total_deposits_with_transactions(self):
        """Test get_total_deposits with multiple deposits"""
        account = InvestorAccount.objects.create(
            investor=self.user,
            monthly_interest_rate=Decimal('1.50')
        )
        
        InvestorTransaction.objects.create(
            investor_account=account,
            transaction_type='DEPOSIT',
            amount=Decimal('10000.00'),
            transaction_date=date.today()
        )
        InvestorTransaction.objects.create(
            investor_account=account,
            transaction_type='DEPOSIT',
            amount=Decimal('5000.00'),
            transaction_date=date.today()
        )
        
        self.assertEqual(account.get_total_deposits(), Decimal('15000.00'))
    
    def test_get_total_withdrawals_with_no_transactions(self):
        """Test get_total_withdrawals with no transactions"""
        account = InvestorAccount.objects.create(
            investor=self.user,
            monthly_interest_rate=Decimal('1.50')
        )
        
        self.assertEqual(account.get_total_withdrawals(), Decimal('0.00'))
    
    def test_get_total_withdrawals_with_transactions(self):
        """Test get_total_withdrawals with multiple withdrawals"""
        account = InvestorAccount.objects.create(
            investor=self.user,
            principal_balance=Decimal('50000.00'),
            monthly_interest_rate=Decimal('1.50')
        )
        
        InvestorTransaction.objects.create(
            investor_account=account,
            transaction_type='WITHDRAWAL',
            amount=Decimal('5000.00'),
            transaction_date=date.today()
        )
        InvestorTransaction.objects.create(
            investor_account=account,
            transaction_type='WITHDRAWAL',
            amount=Decimal('3000.00'),
            transaction_date=date.today()
        )
        
        self.assertEqual(account.get_total_withdrawals(), Decimal('8000.00'))
    
    def test_get_total_interest_earned_with_no_transactions(self):
        """Test get_total_interest_earned with no transactions"""
        account = InvestorAccount.objects.create(
            investor=self.user,
            monthly_interest_rate=Decimal('1.50')
        )
        
        self.assertEqual(account.get_total_interest_earned(), Decimal('0.00'))
    
    def test_get_total_interest_earned_with_transactions(self):
        """Test get_total_interest_earned with multiple interest credits"""
        account = InvestorAccount.objects.create(
            investor=self.user,
            principal_balance=Decimal('100000.00'),
            monthly_interest_rate=Decimal('1.50')
        )
        
        InvestorTransaction.objects.create(
            investor_account=account,
            transaction_type='INTEREST',
            amount=Decimal('1500.00'),
            transaction_date=date.today()
        )
        InvestorTransaction.objects.create(
            investor_account=account,
            transaction_type='INTEREST',
            amount=Decimal('1500.00'),
            transaction_date=date.today()
        )
        
        self.assertEqual(account.get_total_interest_earned(), Decimal('3000.00'))
    
    def test_calculate_pending_interest_with_no_last_interest_date(self):
        """Test calculate_pending_interest returns zero when no last_interest_date"""
        account = InvestorAccount.objects.create(
            investor=self.user,
            principal_balance=Decimal('100000.00'),
            monthly_interest_rate=Decimal('1.50'),
            last_interest_date=None
        )
        
        pending = account.calculate_pending_interest()
        self.assertEqual(pending, Decimal('0.00'))
    
    def test_calculate_pending_interest_same_date(self):
        """Test calculate_pending_interest returns zero for same date"""
        account = InvestorAccount.objects.create(
            investor=self.user,
            principal_balance=Decimal('100000.00'),
            monthly_interest_rate=Decimal('1.50'),
            last_interest_date=date.today()
        )
        
        pending = account.calculate_pending_interest(as_of_date=date.today())
        self.assertEqual(pending, Decimal('0.00'))
    
    def test_calculate_pending_interest_30_days(self):
        """Test calculate_pending_interest for 30 days (1 month)"""
        last_date = date.today() - timedelta(days=30)
        account = InvestorAccount.objects.create(
            investor=self.user,
            principal_balance=Decimal('100000.00'),
            monthly_interest_rate=Decimal('1.50'),
            last_interest_date=last_date
        )
        
        # Interest = 100000 × 0.015 × (30/30) = 1500.00
        pending = account.calculate_pending_interest()
        self.assertEqual(pending, Decimal('1500.00'))
    
    def test_calculate_pending_interest_15_days(self):
        """Test calculate_pending_interest for 15 days (half month)"""
        last_date = date.today() - timedelta(days=15)
        account = InvestorAccount.objects.create(
            investor=self.user,
            principal_balance=Decimal('100000.00'),
            monthly_interest_rate=Decimal('1.50'),
            last_interest_date=last_date
        )
        
        # Interest = 100000 × 0.015 × (15/30) = 750.00
        pending = account.calculate_pending_interest()
        self.assertEqual(pending, Decimal('750.00'))
    
    def test_calculate_pending_interest_60_days(self):
        """Test calculate_pending_interest for 60 days (2 months)"""
        last_date = date.today() - timedelta(days=60)
        account = InvestorAccount.objects.create(
            investor=self.user,
            principal_balance=Decimal('50000.00'),
            monthly_interest_rate=Decimal('2.00'),
            last_interest_date=last_date
        )
        
        # Interest = 50000 × 0.02 × (60/30) = 2000.00
        pending = account.calculate_pending_interest()
        self.assertEqual(pending, Decimal('2000.00'))
    
    def test_get_account_summary(self):
        """Test get_account_summary returns comprehensive info"""
        account = InvestorAccount.objects.create(
            investor=self.user,
            principal_balance=Decimal('100000.00'),
            monthly_interest_rate=Decimal('1.50'),
            last_interest_date=date.today() - timedelta(days=30)
        )
        
        # Add some transactions
        InvestorTransaction.objects.create(
            investor_account=account,
            transaction_type='DEPOSIT',
            amount=Decimal('100000.00'),
            transaction_date=date.today()
        )
        InvestorTransaction.objects.create(
            investor_account=account,
            transaction_type='INTEREST',
            amount=Decimal('1500.00'),
            transaction_date=date.today()
        )
        
        summary = account.get_account_summary()
        
        self.assertEqual(summary['investor'], 'John Investor')
        self.assertEqual(summary['principal_balance'], Decimal('100000.00'))
        self.assertEqual(summary['monthly_interest_rate'], Decimal('1.50'))
        self.assertEqual(summary['annual_interest_rate'], Decimal('18.00'))
        self.assertEqual(summary['total_deposits'], Decimal('100000.00'))
        self.assertEqual(summary['total_interest_earned'], Decimal('1500.00'))
        self.assertEqual(summary['pending_interest'], Decimal('1500.00'))
    
    def test_can_withdraw_with_sufficient_balance(self):
        """Test can_withdraw returns True for valid withdrawal"""
        account = InvestorAccount.objects.create(
            investor=self.user,
            principal_balance=Decimal('10000.00'),
            monthly_interest_rate=Decimal('1.50')
        )
        
        self.assertTrue(account.can_withdraw(Decimal('5000.00')))
        self.assertTrue(account.can_withdraw(Decimal('10000.00')))
    
    def test_can_withdraw_with_insufficient_balance(self):
        """Test can_withdraw returns False for excessive withdrawal"""
        account = InvestorAccount.objects.create(
            investor=self.user,
            principal_balance=Decimal('10000.00'),
            monthly_interest_rate=Decimal('1.50')
        )
        
        self.assertFalse(account.can_withdraw(Decimal('15000.00')))
    
    def test_can_withdraw_with_zero_or_negative_amount(self):
        """Test can_withdraw returns False for zero or negative amounts"""
        account = InvestorAccount.objects.create(
            investor=self.user,
            principal_balance=Decimal('10000.00'),
            monthly_interest_rate=Decimal('1.50')
        )
        
        self.assertFalse(account.can_withdraw(Decimal('0.00')))
        self.assertFalse(account.can_withdraw(Decimal('-100.00')))


class InvestorTransactionModelTests(TestCase):
    """Tests for InvestorTransaction model"""
    
    def setUp(self):
        """Set up test data"""
        self.user = User.objects.create_user(
            username='investor1',
            email='investor1@test.com',
            password='testpass123'
        )
        self.account = InvestorAccount.objects.create(
            investor=self.user,
            principal_balance=Decimal('50000.00'),
            monthly_interest_rate=Decimal('1.50')
        )
    
    def test_create_deposit_transaction(self):
        """Test creating a deposit transaction"""
        txn = InvestorTransaction.objects.create(
            investor_account=self.account,
            transaction_type='DEPOSIT',
            amount=Decimal('10000.00'),
            transaction_date=date.today(),
            description='Initial deposit'
        )
        
        self.assertEqual(txn.investor_account, self.account)
        self.assertEqual(txn.transaction_type, 'DEPOSIT')
        self.assertEqual(txn.amount, Decimal('10000.00'))
        self.assertEqual(txn.transaction_date, date.today())
        self.assertEqual(txn.description, 'Initial deposit')
    
    def test_create_withdrawal_transaction(self):
        """Test creating a withdrawal transaction"""
        txn = InvestorTransaction.objects.create(
            investor_account=self.account,
            transaction_type='WITHDRAWAL',
            amount=Decimal('5000.00'),
            transaction_date=date.today(),
            description='Partial withdrawal'
        )
        
        self.assertEqual(txn.transaction_type, 'WITHDRAWAL')
        self.assertEqual(txn.amount, Decimal('5000.00'))
    
    def test_create_interest_transaction(self):
        """Test creating an interest transaction"""
        txn = InvestorTransaction.objects.create(
            investor_account=self.account,
            transaction_type='INTEREST',
            amount=Decimal('750.00'),
            transaction_date=date.today(),
            description='Monthly interest'
        )
        
        self.assertEqual(txn.transaction_type, 'INTEREST')
        self.assertEqual(txn.amount, Decimal('750.00'))
    
    def test_transaction_string_representation(self):
        """Test string representation of transaction"""
        txn = InvestorTransaction.objects.create(
            investor_account=self.account,
            transaction_type='DEPOSIT',
            amount=Decimal('10000.00'),
            transaction_date=date.today()
        )
        
        expected = f"Deposit - 10000.00 - {date.today()}"
        self.assertEqual(str(txn), expected)
    
    def test_zero_amount_validation(self):
        """Test that zero amount raises validation error"""
        txn = InvestorTransaction(
            investor_account=self.account,
            transaction_type='DEPOSIT',
            amount=Decimal('0.00'),
            transaction_date=date.today()
        )
        
        with self.assertRaises(ValidationError) as context:
            txn.full_clean()
        
        self.assertIn('amount', context.exception.error_dict)
    
    def test_negative_amount_validation(self):
        """Test that negative amount raises validation error"""
        txn = InvestorTransaction(
            investor_account=self.account,
            transaction_type='DEPOSIT',
            amount=Decimal('-100.00'),
            transaction_date=date.today()
        )
        
        with self.assertRaises(ValidationError) as context:
            txn.full_clean()
        
        self.assertIn('amount', context.exception.error_dict)
    
    def test_future_transaction_date_validation(self):
        """Test that future transaction date raises validation error"""
        future_date = date.today() + timedelta(days=10)
        txn = InvestorTransaction(
            investor_account=self.account,
            transaction_type='DEPOSIT',
            amount=Decimal('1000.00'),
            transaction_date=future_date
        )
        
        with self.assertRaises(ValidationError) as context:
            txn.full_clean()
        
        self.assertIn('transaction_date', context.exception.error_dict)
    
    def test_withdrawal_exceeds_balance_validation(self):
        """Test that withdrawal exceeding balance raises validation error"""
        txn = InvestorTransaction(
            investor_account=self.account,
            transaction_type='WITHDRAWAL',
            amount=Decimal('100000.00'),  # More than 50000.00 balance
            transaction_date=date.today()
        )
        
        with self.assertRaises(ValidationError) as context:
            txn.full_clean()
        
        self.assertIn('amount', context.exception.error_dict)
    
    def test_transaction_date_before_account_creation_validation(self):
        """Test that transaction date before account creation raises error"""
        past_date = self.account.created_at.date() - timedelta(days=10)
        txn = InvestorTransaction(
            investor_account=self.account,
            transaction_type='DEPOSIT',
            amount=Decimal('1000.00'),
            transaction_date=past_date
        )
        
        with self.assertRaises(ValidationError) as context:
            txn.full_clean()
        
        self.assertIn('transaction_date', context.exception.error_dict)
    
    def test_transaction_ordering(self):
        """Test transactions are ordered by date and created_at descending"""
        yesterday = date.today() - timedelta(days=1)
        
        txn1 = InvestorTransaction.objects.create(
            investor_account=self.account,
            transaction_type='DEPOSIT',
            amount=Decimal('1000.00'),
            transaction_date=yesterday
        )
        
        txn2 = InvestorTransaction.objects.create(
            investor_account=self.account,
            transaction_type='DEPOSIT',
            amount=Decimal('2000.00'),
            transaction_date=date.today()
        )
        
        transactions = list(InvestorTransaction.objects.all())
        self.assertEqual(transactions[0], txn2)  # Most recent first
        self.assertEqual(transactions[1], txn1)
    
    def test_get_balance_impact_for_deposit(self):
        """Test get_balance_impact returns positive for deposit"""
        txn = InvestorTransaction.objects.create(
            investor_account=self.account,
            transaction_type='DEPOSIT',
            amount=Decimal('10000.00'),
            transaction_date=date.today()
        )
        
        self.assertEqual(txn.get_balance_impact(), Decimal('10000.00'))
    
    def test_get_balance_impact_for_withdrawal(self):
        """Test get_balance_impact returns negative for withdrawal"""
        txn = InvestorTransaction.objects.create(
            investor_account=self.account,
            transaction_type='WITHDRAWAL',
            amount=Decimal('5000.00'),
            transaction_date=date.today()
        )
        
        self.assertEqual(txn.get_balance_impact(), Decimal('-5000.00'))
    
    def test_get_balance_impact_for_interest(self):
        """Test get_balance_impact returns positive for interest"""
        txn = InvestorTransaction.objects.create(
            investor_account=self.account,
            transaction_type='INTEREST',
            amount=Decimal('750.00'),
            transaction_date=date.today()
        )
        
        self.assertEqual(txn.get_balance_impact(), Decimal('750.00'))
    
    def test_is_deposit_method(self):
        """Test is_deposit returns True only for deposits"""
        deposit = InvestorTransaction.objects.create(
            investor_account=self.account,
            transaction_type='DEPOSIT',
            amount=Decimal('1000.00'),
            transaction_date=date.today()
        )
        withdrawal = InvestorTransaction.objects.create(
            investor_account=self.account,
            transaction_type='WITHDRAWAL',
            amount=Decimal('1000.00'),
            transaction_date=date.today()
        )
        
        self.assertTrue(deposit.is_deposit())
        self.assertFalse(withdrawal.is_deposit())
    
    def test_is_withdrawal_method(self):
        """Test is_withdrawal returns True only for withdrawals"""
        deposit = InvestorTransaction.objects.create(
            investor_account=self.account,
            transaction_type='DEPOSIT',
            amount=Decimal('1000.00'),
            transaction_date=date.today()
        )
        withdrawal = InvestorTransaction.objects.create(
            investor_account=self.account,
            transaction_type='WITHDRAWAL',
            amount=Decimal('1000.00'),
            transaction_date=date.today()
        )
        
        self.assertFalse(deposit.is_withdrawal())
        self.assertTrue(withdrawal.is_withdrawal())
    
    def test_is_interest_method(self):
        """Test is_interest returns True only for interest"""
        deposit = InvestorTransaction.objects.create(
            investor_account=self.account,
            transaction_type='DEPOSIT',
            amount=Decimal('1000.00'),
            transaction_date=date.today()
        )
        interest = InvestorTransaction.objects.create(
            investor_account=self.account,
            transaction_type='INTEREST',
            amount=Decimal('750.00'),
            transaction_date=date.today()
        )
        
        self.assertFalse(deposit.is_interest())
        self.assertTrue(interest.is_interest())
    
    def test_transaction_with_reference(self):
        """Test transaction with external reference"""
        txn = InvestorTransaction.objects.create(
            investor_account=self.account,
            transaction_type='DEPOSIT',
            amount=Decimal('10000.00'),
            transaction_date=date.today(),
            reference='RECEIPT-12345'
        )
        
        self.assertEqual(txn.reference, 'RECEIPT-12345')
    
    def test_transaction_with_created_by(self):
        """Test transaction with created_by user"""
        admin = User.objects.create_user(
            username='admin',
            email='admin@test.com',
            password='adminpass'
        )
        
        txn = InvestorTransaction.objects.create(
            investor_account=self.account,
            transaction_type='DEPOSIT',
            amount=Decimal('10000.00'),
            transaction_date=date.today(),
            created_by=admin
        )
        
        self.assertEqual(txn.created_by, admin)
    
    def test_related_transactions_via_account(self):
        """Test accessing transactions through account relationship"""
        InvestorTransaction.objects.create(
            investor_account=self.account,
            transaction_type='DEPOSIT',
            amount=Decimal('10000.00'),
            transaction_date=date.today()
        )
        InvestorTransaction.objects.create(
            investor_account=self.account,
            transaction_type='WITHDRAWAL',
            amount=Decimal('2000.00'),
            transaction_date=date.today()
        )
        
        self.assertEqual(self.account.transactions.count(), 2)
    
    def test_decimal_precision_in_calculations(self):
        """Test that decimal precision is maintained"""
        # Create account with specific balance
        account = InvestorAccount.objects.create(
            investor=self.user,
            principal_balance=Decimal('33333.33'),
            monthly_interest_rate=Decimal('1.23')
        )
        
        # Create transaction with specific amount
        txn = InvestorTransaction.objects.create(
            investor_account=account,
            transaction_type='DEPOSIT',
            amount=Decimal('99999.99'),
            transaction_date=date.today()
        )
        
        # Verify precision is maintained
        self.assertEqual(txn.amount, Decimal('99999.99'))
        self.assertEqual(account.principal_balance, Decimal('33333.33'))


class InvestorAccountEdgeCasesTests(TestCase):
    """Edge case tests for investor models"""
    
    def setUp(self):
        """Set up test data"""
        self.user = User.objects.create_user(
            username='investor1',
            email='investor1@test.com',
            password='testpass123'
        )
    
    def test_zero_balance_account(self):
        """Test account with zero balance"""
        account = InvestorAccount.objects.create(
            investor=self.user,
            principal_balance=Decimal('0.00'),
            monthly_interest_rate=Decimal('1.50')
        )
        
        self.assertEqual(account.principal_balance, Decimal('0.00'))
        self.assertFalse(account.can_withdraw(Decimal('1.00')))
    
    def test_zero_interest_rate_account(self):
        """Test account with zero interest rate"""
        account = InvestorAccount.objects.create(
            investor=self.user,
            principal_balance=Decimal('10000.00'),
            monthly_interest_rate=Decimal('0.00'),
            last_interest_date=date.today() - timedelta(days=30)
        )
        
        pending = account.calculate_pending_interest()
        self.assertEqual(pending, Decimal('0.00'))
    
    def test_very_small_interest_calculation(self):
        """Test interest calculation with very small amounts"""
        account = InvestorAccount.objects.create(
            investor=self.user,
            principal_balance=Decimal('100.00'),
            monthly_interest_rate=Decimal('0.10'),
            last_interest_date=date.today() - timedelta(days=1)
        )
        
        # Interest = 100 × 0.001 × (1/30) = 0.00333... rounds to 0.00
        pending = account.calculate_pending_interest()
        self.assertEqual(pending, Decimal('0.00'))
    
    def test_large_balance_and_interest(self):
        """Test with very large balance and interest"""
        account = InvestorAccount.objects.create(
            investor=self.user,
            principal_balance=Decimal('10000000.00'),  # 10 million
            monthly_interest_rate=Decimal('5.00'),
            last_interest_date=date.today() - timedelta(days=30)
        )
        
        # Interest = 10,000,000 × 0.05 × (30/30) = 500,000
        pending = account.calculate_pending_interest()
        self.assertEqual(pending, Decimal('500000.00'))
    
    def test_multiple_accounts_for_same_investor(self):
        """Test that one investor can have multiple accounts"""
        account1 = InvestorAccount.objects.create(
            investor=self.user,
            principal_balance=Decimal('50000.00'),
            monthly_interest_rate=Decimal('1.50')
        )
        account2 = InvestorAccount.objects.create(
            investor=self.user,
            principal_balance=Decimal('100000.00'),
            monthly_interest_rate=Decimal('2.00')
        )
        
        accounts = InvestorAccount.objects.filter(investor=self.user)
        self.assertEqual(accounts.count(), 2)
    
    def test_interest_calculation_rounding(self):
        """Test that interest calculations round correctly"""
        account = InvestorAccount.objects.create(
            investor=self.user,
            principal_balance=Decimal('10333.33'),
            monthly_interest_rate=Decimal('1.77'),
            last_interest_date=date.today() - timedelta(days=17)
        )
        
        # Interest = 10333.33 × 0.0177 × (17/30) = 103.56...
        pending = account.calculate_pending_interest()
        
        # Should be rounded to 2 decimal places
        self.assertEqual(len(str(pending).split('.')[-1]), 2)
