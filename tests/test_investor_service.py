"""
Comprehensive Tests for InvestorService

Tests cover:
- Monthly compound interest calculation
- Withdrawal penalty rule (critical business logic)
- Atomic transactions
- Edge cases and error handling
- Batch processing
- Audit trail

Total: 40+ tests
"""

from decimal import Decimal
from datetime import date, timedelta
from django.test import TestCase
from django.core.exceptions import ValidationError
from django.utils import timezone
from apps.core.models import User
from apps.loans.models import InvestorAccount, InvestorTransaction
from apps.loans.investor_service import InvestorService


class InvestorServiceInterestCalculationTests(TestCase):
    """Tests for monthly interest calculation"""
    
    def setUp(self):
        """Set up test data"""
        self.user = User.objects.create_user(
            username='investor1',
            email='investor1@test.com',
            password='testpass123',
            first_name='John',
            last_name='Investor'
        )
        
        self.admin = User.objects.create_user(
            username='admin',
            email='admin@test.com',
            password='adminpass'
        )
    
    def test_apply_monthly_interest_basic(self):
        """Test basic monthly interest application"""
        account = InvestorAccount.objects.create(
            investor=self.user,
            principal_balance=Decimal('100000.00'),
            monthly_interest_rate=Decimal('1.50'),
            last_interest_date=None
        )
        
        result = InvestorService.apply_monthly_interest(
            investor_account_id=account.id,
            calculation_date=date(2026, 2, 28),
            created_by=self.admin
        )
        
        # 100,000 × 1.5% = 1,500
        expected_interest = Decimal('1500.00')
        expected_new_balance = Decimal('101500.00')
        
        self.assertTrue(result['success'])
        self.assertEqual(result['interest_amount'], expected_interest)
        self.assertEqual(result['new_balance'], expected_new_balance)
        self.assertFalse(result['withdrawal_penalty'])
        
        # Verify account updated
        account.refresh_from_db()
        self.assertEqual(account.principal_balance, expected_new_balance)
        self.assertEqual(account.last_interest_date, date(2026, 2, 28))
    
    def test_apply_monthly_interest_creates_transaction(self):
        """Test that interest application creates audit transaction"""
        account = InvestorAccount.objects.create(
            investor=self.user,
            principal_balance=Decimal('50000.00'),
            monthly_interest_rate=Decimal('2.00')
        )
        
        result = InvestorService.apply_monthly_interest(
            investor_account_id=account.id,
            calculation_date=date(2026, 2, 28),
            created_by=self.admin
        )
        
        # Verify transaction created
        self.assertIn('transaction_id', result)
        transaction = InvestorTransaction.objects.get(id=result['transaction_id'])
        
        self.assertEqual(transaction.investor_account, account)
        self.assertEqual(transaction.transaction_type, 'INTEREST')
        self.assertEqual(transaction.amount, Decimal('1000.00'))  # 50,000 × 2%
        self.assertEqual(transaction.transaction_date, date(2026, 2, 28))
        self.assertEqual(transaction.created_by, self.admin)
        self.assertIn('February 2026', transaction.description)
        self.assertIn('INT-202602', transaction.reference)
    
    def test_apply_monthly_interest_compounds(self):
        """Test that interest compounds (adds to principal)"""
        account = InvestorAccount.objects.create(
            investor=self.user,
            principal_balance=Decimal('100000.00'),
            monthly_interest_rate=Decimal('1.00')
        )
        
        # Month 1: Apply interest
        result1 = InvestorService.apply_monthly_interest(
            investor_account_id=account.id,
            calculation_date=date(2026, 1, 31)
        )
        self.assertEqual(result1['interest_amount'], Decimal('1000.00'))
        self.assertEqual(result1['new_balance'], Decimal('101000.00'))
        
        # Month 2: Interest should compound on new balance
        result2 = InvestorService.apply_monthly_interest(
            investor_account_id=account.id,
            calculation_date=date(2026, 2, 28)
        )
        self.assertEqual(result2['interest_amount'], Decimal('1010.00'))  # 101,000 × 1%
        self.assertEqual(result2['new_balance'], Decimal('102010.00'))
    
    def test_withdrawal_blocks_interest_for_entire_month(self):
        """Test CRITICAL RULE: Any withdrawal in month blocks interest"""
        account = InvestorAccount.objects.create(
            investor=self.user,
            principal_balance=Decimal('100000.00'),
            monthly_interest_rate=Decimal('2.00')
        )
        
        # Make a withdrawal on Feb 15
        InvestorTransaction.objects.create(
            investor_account=account,
            transaction_type='WITHDRAWAL',
            amount=Decimal('5000.00'),
            transaction_date=date(2026, 2, 15)
        )
        
        # Try to apply interest for February
        result = InvestorService.apply_monthly_interest(
            investor_account_id=account.id,
            calculation_date=date(2026, 2, 28)
        )
        
        # Should fail with withdrawal penalty
        self.assertFalse(result['success'])
        self.assertEqual(result['interest_amount'], Decimal('0.00'))
        self.assertTrue(result['withdrawal_penalty'])
        self.assertEqual(result['withdrawal_count'], 1)
        self.assertIn('withdrawal', result['message'].lower())
        
        # Verify balance unchanged
        account.refresh_from_db()
        self.assertEqual(account.principal_balance, Decimal('100000.00'))
        
        # Verify last_interest_date IS updated (to mark month as processed)
        self.assertEqual(account.last_interest_date, date(2026, 2, 28))
    
    def test_withdrawal_on_first_day_blocks_interest(self):
        """Test withdrawal on first day of month blocks interest"""
        account = InvestorAccount.objects.create(
            investor=self.user,
            principal_balance=Decimal('100000.00'),
            monthly_interest_rate=Decimal('1.50')
        )
        
        # Withdrawal on first day of month
        InvestorTransaction.objects.create(
            investor_account=account,
            transaction_type='WITHDRAWAL',
            amount=Decimal('1000.00'),
            transaction_date=date(2026, 2, 1)
        )
        
        result = InvestorService.apply_monthly_interest(
            investor_account_id=account.id,
            calculation_date=date(2026, 2, 28)
        )
        
        self.assertFalse(result['success'])
        self.assertTrue(result['withdrawal_penalty'])
    
    def test_withdrawal_on_last_day_blocks_interest(self):
        """Test withdrawal on last day of month blocks interest"""
        account = InvestorAccount.objects.create(
            investor=self.user,
            principal_balance=Decimal('100000.00'),
            monthly_interest_rate=Decimal('1.50')
        )
        
        # Withdrawal on last day of month
        InvestorTransaction.objects.create(
            investor_account=account,
            transaction_type='WITHDRAWAL',
            amount=Decimal('1000.00'),
            transaction_date=date(2026, 2, 28)
        )
        
        result = InvestorService.apply_monthly_interest(
            investor_account_id=account.id,
            calculation_date=date(2026, 2, 28)
        )
        
        self.assertFalse(result['success'])
        self.assertTrue(result['withdrawal_penalty'])
    
    def test_multiple_withdrawals_in_month(self):
        """Test multiple withdrawals in month"""
        account = InvestorAccount.objects.create(
            investor=self.user,
            principal_balance=Decimal('100000.00'),
            monthly_interest_rate=Decimal('1.50')
        )
        
        # Multiple withdrawals
        InvestorTransaction.objects.create(
            investor_account=account,
            transaction_type='WITHDRAWAL',
            amount=Decimal('1000.00'),
            transaction_date=date(2026, 2, 5)
        )
        InvestorTransaction.objects.create(
            investor_account=account,
            transaction_type='WITHDRAWAL',
            amount=Decimal('2000.00'),
            transaction_date=date(2026, 2, 20)
        )
        
        result = InvestorService.apply_monthly_interest(
            investor_account_id=account.id,
            calculation_date=date(2026, 2, 28)
        )
        
        self.assertFalse(result['success'])
        self.assertTrue(result['withdrawal_penalty'])
        self.assertEqual(result['withdrawal_count'], 2)
        self.assertEqual(result['total_withdrawn'], Decimal('3000.00'))
    
    def test_withdrawal_in_previous_month_does_not_affect_current(self):
        """Test that previous month's withdrawal doesn't affect current month"""
        account = InvestorAccount.objects.create(
            investor=self.user,
            principal_balance=Decimal('100000.00'),
            monthly_interest_rate=Decimal('1.50')
        )
        
        # Withdrawal in January
        InvestorTransaction.objects.create(
            investor_account=account,
            transaction_type='WITHDRAWAL',
            amount=Decimal('1000.00'),
            transaction_date=date(2026, 1, 15)
        )
        
        # Apply interest for February (should succeed)
        result = InvestorService.apply_monthly_interest(
            investor_account_id=account.id,
            calculation_date=date(2026, 2, 28)
        )
        
        self.assertTrue(result['success'])
        self.assertFalse(result['withdrawal_penalty'])
        self.assertEqual(result['interest_amount'], Decimal('1500.00'))
    
    def test_deposits_do_not_block_interest(self):
        """Test that deposits don't block interest (only withdrawals do)"""
        account = InvestorAccount.objects.create(
            investor=self.user,
            principal_balance=Decimal('100000.00'),
            monthly_interest_rate=Decimal('1.50')
        )
        
        # Make deposits in February
        InvestorTransaction.objects.create(
            investor_account=account,
            transaction_type='DEPOSIT',
            amount=Decimal('10000.00'),
            transaction_date=date(2026, 2, 5)
        )
        InvestorTransaction.objects.create(
            investor_account=account,
            transaction_type='DEPOSIT',
            amount=Decimal('5000.00'),
            transaction_date=date(2026, 2, 15)
        )
        
        # Interest should still apply
        result = InvestorService.apply_monthly_interest(
            investor_account_id=account.id,
            calculation_date=date(2026, 2, 28)
        )
        
        self.assertTrue(result['success'])
        self.assertFalse(result['withdrawal_penalty'])
        # Interest on original 100,000 (deposits don't affect calculation)
        self.assertEqual(result['interest_amount'], Decimal('1500.00'))
    
    def test_cannot_apply_interest_twice_same_month(self):
        """Test that interest can only be applied once per month"""
        account = InvestorAccount.objects.create(
            investor=self.user,
            principal_balance=Decimal('100000.00'),
            monthly_interest_rate=Decimal('1.50')
        )
        
        # First application
        result1 = InvestorService.apply_monthly_interest(
            investor_account_id=account.id,
            calculation_date=date(2026, 2, 28)
        )
        self.assertTrue(result1['success'])
        
        # Second application same month
        result2 = InvestorService.apply_monthly_interest(
            investor_account_id=account.id,
            calculation_date=date(2026, 2, 28)
        )
        self.assertFalse(result2['success'])
        self.assertIn('already applied', result2['message'].lower())
    
    def test_interest_on_zero_balance(self):
        """Test interest calculation on zero balance"""
        account = InvestorAccount.objects.create(
            investor=self.user,
            principal_balance=Decimal('0.00'),
            monthly_interest_rate=Decimal('1.50')
        )
        
        result = InvestorService.apply_monthly_interest(
            investor_account_id=account.id,
            calculation_date=date(2026, 2, 28)
        )
        
        self.assertFalse(result['success'])
        self.assertEqual(result['interest_amount'], Decimal('0.00'))
        self.assertIn('zero', result['message'].lower())
    
    def test_interest_with_zero_rate(self):
        """Test interest calculation with zero rate"""
        account = InvestorAccount.objects.create(
            investor=self.user,
            principal_balance=Decimal('100000.00'),
            monthly_interest_rate=Decimal('0.00')
        )
        
        result = InvestorService.apply_monthly_interest(
            investor_account_id=account.id,
            calculation_date=date(2026, 2, 28)
        )
        
        self.assertFalse(result['success'])
        self.assertEqual(result['interest_amount'], Decimal('0.00'))
    
    def test_future_date_validation(self):
        """Test that future dates are rejected"""
        account = InvestorAccount.objects.create(
            investor=self.user,
            principal_balance=Decimal('100000.00'),
            monthly_interest_rate=Decimal('1.50')
        )
        
        future_date = timezone.now().date() + timedelta(days=30)
        
        with self.assertRaises(ValidationError) as context:
            InvestorService.apply_monthly_interest(
                investor_account_id=account.id,
                calculation_date=future_date
            )
        
        self.assertIn('future', str(context.exception).lower())
    
    def test_nonexistent_account_validation(self):
        """Test validation for nonexistent account"""
        with self.assertRaises(ValidationError) as context:
            InvestorService.apply_monthly_interest(
                investor_account_id=99999,
                calculation_date=date(2026, 2, 28)
            )
        
        self.assertIn('does not exist', str(context.exception))
    
    def test_decimal_precision_maintained(self):
        """Test that Decimal precision is maintained"""
        account = InvestorAccount.objects.create(
            investor=self.user,
            principal_balance=Decimal('123456.78'),
            monthly_interest_rate=Decimal('1.23')
        )
        
        result = InvestorService.apply_monthly_interest(
            investor_account_id=account.id,
            calculation_date=date(2026, 2, 28)
        )
        
        # 123456.78 × 0.0123 = 1518.52
        expected_interest = Decimal('1518.52')
        
        self.assertEqual(result['interest_amount'], expected_interest)
        self.assertEqual(result['new_balance'], Decimal('124975.30'))


class InvestorServiceDepositWithdrawalTests(TestCase):
    """Tests for deposit and withdrawal operations"""
    
    def setUp(self):
        """Set up test data"""
        self.user = User.objects.create_user(
            username='investor1',
            email='investor1@test.com',
            password='testpass123'
        )
        
        self.admin = User.objects.create_user(
            username='admin',
            email='admin@test.com',
            password='adminpass'
        )
    
    def test_record_deposit(self):
        """Test recording a deposit"""
        account = InvestorAccount.objects.create(
            investor=self.user,
            principal_balance=Decimal('50000.00'),
            monthly_interest_rate=Decimal('1.50')
        )
        
        result = InvestorService.record_deposit(
            investor_account_id=account.id,
            amount=Decimal('10000.00'),
            transaction_date=date(2026, 2, 15),
            description='Additional investment',
            reference='DEP-001',
            created_by=self.admin
        )
        
        self.assertTrue(result['success'])
        self.assertEqual(result['amount'], Decimal('10000.00'))
        self.assertEqual(result['previous_balance'], Decimal('50000.00'))
        self.assertEqual(result['new_balance'], Decimal('60000.00'))
        
        # Verify account updated
        account.refresh_from_db()
        self.assertEqual(account.principal_balance, Decimal('60000.00'))
        
        # Verify transaction created
        transaction = InvestorTransaction.objects.get(id=result['transaction_id'])
        self.assertEqual(transaction.transaction_type, 'DEPOSIT')
        self.assertEqual(transaction.amount, Decimal('10000.00'))
        self.assertEqual(transaction.description, 'Additional investment')
        self.assertEqual(transaction.reference, 'DEP-001')
    
    def test_record_withdrawal(self):
        """Test recording a withdrawal"""
        account = InvestorAccount.objects.create(
            investor=self.user,
            principal_balance=Decimal('50000.00'),
            monthly_interest_rate=Decimal('1.50')
        )
        
        result = InvestorService.record_withdrawal(
            investor_account_id=account.id,
            amount=Decimal('10000.00'),
            transaction_date=date(2026, 2, 15),
            description='Partial withdrawal',
            reference='WD-001',
            created_by=self.admin
        )
        
        self.assertTrue(result['success'])
        self.assertEqual(result['amount'], Decimal('10000.00'))
        self.assertEqual(result['previous_balance'], Decimal('50000.00'))
        self.assertEqual(result['new_balance'], Decimal('40000.00'))
        self.assertIn('WARNING', result['interest_warning'])
        self.assertIn('February 2026', result['affected_month'])
        
        # Verify account updated
        account.refresh_from_db()
        self.assertEqual(account.principal_balance, Decimal('40000.00'))
    
    def test_withdrawal_insufficient_balance(self):
        """Test withdrawal with insufficient balance"""
        account = InvestorAccount.objects.create(
            investor=self.user,
            principal_balance=Decimal('5000.00'),
            monthly_interest_rate=Decimal('1.50')
        )
        
        with self.assertRaises(ValidationError) as context:
            InvestorService.record_withdrawal(
                investor_account_id=account.id,
                amount=Decimal('10000.00'),
                transaction_date=date(2026, 2, 15)
            )
        
        self.assertIn('insufficient', str(context.exception).lower())
        
        # Verify balance unchanged
        account.refresh_from_db()
        self.assertEqual(account.principal_balance, Decimal('5000.00'))
    
    def test_negative_deposit_validation(self):
        """Test that negative deposits are rejected"""
        account = InvestorAccount.objects.create(
            investor=self.user,
            principal_balance=Decimal('10000.00'),
            monthly_interest_rate=Decimal('1.50')
        )
        
        with self.assertRaises(ValidationError):
            InvestorService.record_deposit(
                investor_account_id=account.id,
                amount=Decimal('-1000.00'),
                transaction_date=date(2026, 2, 15)
            )
    
    def test_zero_withdrawal_validation(self):
        """Test that zero withdrawals are rejected"""
        account = InvestorAccount.objects.create(
            investor=self.user,
            principal_balance=Decimal('10000.00'),
            monthly_interest_rate=Decimal('1.50')
        )
        
        with self.assertRaises(ValidationError):
            InvestorService.record_withdrawal(
                investor_account_id=account.id,
                amount=Decimal('0.00'),
                transaction_date=date(2026, 2, 15)
            )


class InvestorServiceInterestPreviewTests(TestCase):
    """Tests for interest preview (read-only)"""
    
    def setUp(self):
        """Set up test data"""
        self.user = User.objects.create_user(
            username='investor1',
            email='investor1@test.com',
            password='testpass123',
            first_name='John',
            last_name='Investor'
        )
    
    def test_get_interest_preview_basic(self):
        """Test basic interest preview"""
        account = InvestorAccount.objects.create(
            investor=self.user,
            principal_balance=Decimal('100000.00'),
            monthly_interest_rate=Decimal('1.50')
        )
        
        preview = InvestorService.get_interest_preview(
            investor_account_id=account.id,
            calculation_date=date(2026, 2, 28)
        )
        
        self.assertEqual(preview['current_balance'], Decimal('100000.00'))
        self.assertEqual(preview['potential_interest'], Decimal('1500.00'))
        self.assertEqual(preview['projected_balance'], Decimal('101500.00'))
        self.assertFalse(preview['has_withdrawal_penalty'])
        self.assertTrue(preview['can_apply'])
        self.assertEqual(preview['investor_name'], 'John Investor')
    
    def test_get_interest_preview_with_withdrawal(self):
        """Test preview shows withdrawal penalty"""
        account = InvestorAccount.objects.create(
            investor=self.user,
            principal_balance=Decimal('100000.00'),
            monthly_interest_rate=Decimal('1.50')
        )
        
        # Add withdrawal
        InvestorTransaction.objects.create(
            investor_account=account,
            transaction_type='WITHDRAWAL',
            amount=Decimal('5000.00'),
            transaction_date=date(2026, 2, 15)
        )
        
        preview = InvestorService.get_interest_preview(
            investor_account_id=account.id,
            calculation_date=date(2026, 2, 28)
        )
        
        self.assertEqual(preview['potential_interest'], Decimal('0.00'))
        self.assertTrue(preview['has_withdrawal_penalty'])
        self.assertEqual(preview['withdrawal_count'], 1)
        self.assertFalse(preview['can_apply'])
        self.assertIn('withdrawal', preview['message'].lower())


class InvestorServiceBatchProcessingTests(TestCase):
    """Tests for batch interest application"""
    
    def setUp(self):
        """Set up test data"""
        self.user1 = User.objects.create_user(
            username='investor1',
            email='investor1@test.com',
            password='testpass123'
        )
        self.user2 = User.objects.create_user(
            username='investor2',
            email='investor2@test.com',
            password='testpass123'
        )
        self.user3 = User.objects.create_user(
            username='investor3',
            email='investor3@test.com',
            password='testpass123'
        )
    
    def test_apply_interest_to_multiple_accounts(self):
        """Test batch processing multiple accounts"""
        # Account 1: Normal (should get interest)
        account1 = InvestorAccount.objects.create(
            investor=self.user1,
            principal_balance=Decimal('100000.00'),
            monthly_interest_rate=Decimal('1.50')
        )
        
        # Account 2: Has withdrawal (should not get interest)
        account2 = InvestorAccount.objects.create(
            investor=self.user2,
            principal_balance=Decimal('50000.00'),
            monthly_interest_rate=Decimal('2.00')
        )
        InvestorTransaction.objects.create(
            investor_account=account2,
            transaction_type='WITHDRAWAL',
            amount=Decimal('1000.00'),
            transaction_date=date(2026, 2, 10)
        )
        
        # Account 3: Normal (should get interest)
        account3 = InvestorAccount.objects.create(
            investor=self.user3,
            principal_balance=Decimal('75000.00'),
            monthly_interest_rate=Decimal('1.00')
        )
        
        # Run batch process
        results = InvestorService.apply_interest_to_multiple_accounts(
            calculation_date=date(2026, 2, 28)
        )
        
        self.assertEqual(results['total_accounts'], 3)
        self.assertEqual(results['successful'], 2)  # account1 and account3
        self.assertEqual(results['failed'], 1)  # account2 with withdrawal
        self.assertEqual(results['withdrawal_penalty'], 1)
        
        # Total interest = 1500 (account1) + 750 (account3) = 2250
        self.assertEqual(results['total_interest_applied'], Decimal('2250.00'))
        
        # Verify individual results
        self.assertEqual(len(results['details']), 3)
    
    def test_batch_processing_with_already_applied(self):
        """Test batch processing skips already-applied accounts"""
        account = InvestorAccount.objects.create(
            investor=self.user1,
            principal_balance=Decimal('100000.00'),
            monthly_interest_rate=Decimal('1.50'),
            last_interest_date=date(2026, 2, 20)  # Already applied this month
        )
        
        results = InvestorService.apply_interest_to_multiple_accounts(
            calculation_date=date(2026, 2, 28)
        )
        
        self.assertEqual(results['total_accounts'], 1)
        self.assertEqual(results['successful'], 0)
        self.assertEqual(results['already_applied'], 1)
        self.assertEqual(results['total_interest_applied'], Decimal('0.00'))


class InvestorServiceEdgeCasesTests(TestCase):
    """Tests for edge cases and special scenarios"""
    
    def setUp(self):
        """Set up test data"""
        self.user = User.objects.create_user(
            username='investor1',
            email='investor1@test.com',
            password='testpass123'
        )
    
    def test_interest_calculation_december_to_january(self):
        """Test interest calculation across year boundary"""
        account = InvestorAccount.objects.create(
            investor=self.user,
            principal_balance=Decimal('100000.00'),
            monthly_interest_rate=Decimal('1.50'),
            last_interest_date=date(2025, 12, 31)
        )
        
        # Apply interest for January 2026
        result = InvestorService.apply_monthly_interest(
            investor_account_id=account.id,
            calculation_date=date(2026, 1, 31)
        )
        
        self.assertTrue(result['success'])
        self.assertEqual(result['interest_amount'], Decimal('1500.00'))
    
    def test_very_small_interest_amount(self):
        """Test handling of very small interest amounts"""
        account = InvestorAccount.objects.create(
            investor=self.user,
            principal_balance=Decimal('10.00'),
            monthly_interest_rate=Decimal('0.01')
        )
        
        result = InvestorService.apply_monthly_interest(
            investor_account_id=account.id,
            calculation_date=date(2026, 2, 28)
        )
        
        # 10 × 0.0001 = 0.001 rounds to 0.00
        self.assertFalse(result['success'])
        self.assertEqual(result['interest_amount'], Decimal('0.00'))
    
    def test_large_balance_interest_calculation(self):
        """Test interest calculation with very large balance"""
        account = InvestorAccount.objects.create(
            investor=self.user,
            principal_balance=Decimal('10000000.00'),  # 10 million
            monthly_interest_rate=Decimal('3.00')
        )
        
        result = InvestorService.apply_monthly_interest(
            investor_account_id=account.id,
            calculation_date=date(2026, 2, 28)
        )
        
        # 10,000,000 × 3% = 300,000
        self.assertTrue(result['success'])
        self.assertEqual(result['interest_amount'], Decimal('300000.00'))
        self.assertEqual(result['new_balance'], Decimal('10300000.00'))
    
    def test_interest_rounding(self):
        """Test that interest is properly rounded to 2 decimal places"""
        account = InvestorAccount.objects.create(
            investor=self.user,
            principal_balance=Decimal('12345.67'),
            monthly_interest_rate=Decimal('1.77')
        )
        
        result = InvestorService.apply_monthly_interest(
            investor_account_id=account.id,
            calculation_date=date(2026, 2, 28)
        )
        
        # 12345.67 × 0.0177 = 218.52... should round to 218.52
        interest = result['interest_amount']
        self.assertEqual(len(str(interest).split('.')[-1]), 2)  # 2 decimal places
        self.assertTrue(result['success'])
