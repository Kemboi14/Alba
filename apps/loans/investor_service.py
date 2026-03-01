"""
Investor Service - Production-Ready

Handles investor account operations including monthly compound interest calculation.

Key Business Rule:
- If ANY withdrawal occurs within a calendar month, NO interest is accrued for that entire month.
- Otherwise, interest is calculated and compounded monthly.

All operations are atomic and fully auditable.
"""

from decimal import Decimal, ROUND_HALF_UP
from datetime import date, timedelta
from django.db import transaction
from django.core.exceptions import ValidationError
from django.utils import timezone
from apps.loans.models import InvestorAccount, InvestorTransaction


class InvestorService:
    """
    Service class for investor account operations
    
    Features:
    - Monthly compound interest calculation
    - Withdrawal penalty rule enforcement
    - Atomic transactions
    - Full audit trail
    - Decimal precision
    - Production-safe error handling
    """
    
    @staticmethod
    @transaction.atomic()
    def apply_monthly_interest(
        investor_account_id: int,
        calculation_date: date = None,
        created_by=None
    ) -> dict:
        """
        Apply monthly compound interest to an investor account
        
        Business Rules:
        1. If ANY withdrawal occurred in the calendar month, NO interest is accrued
        2. Interest can only be applied once per calendar month
        3. Interest is calculated as: principal_balance * (monthly_rate / 100)
        4. Interest is added to principal_balance (compounding)
        5. last_interest_date is updated to calculation_date
        
        Args:
            investor_account_id: int - ID of the investor account
            calculation_date: date - Date to calculate interest for (default: today)
            created_by: User - User performing the operation (for audit trail)
        
        Returns:
            dict with keys:
                - success: bool
                - interest_amount: Decimal
                - new_balance: Decimal
                - message: str
                - transaction_id: int (if interest was applied)
                - withdrawal_penalty: bool (if interest was blocked due to withdrawal)
        
        Raises:
            ValidationError: If account doesn't exist or validation fails
        
        Example:
            result = InvestorService.apply_monthly_interest(
                investor_account_id=1,
                calculation_date=date(2026, 2, 28),
                created_by=user
            )
            if result['success']:
                print(f"Interest applied: {result['interest_amount']}")
        """
        # Default to today if no date provided
        if calculation_date is None:
            calculation_date = timezone.now().date()
        
        # Validate calculation_date is not in the future
        if calculation_date > timezone.now().date():
            raise ValidationError("Cannot calculate interest for a future date")
        
        # Get investor account with select_for_update to prevent concurrent modifications
        try:
            account = InvestorAccount.objects.select_for_update().get(id=investor_account_id)
        except InvestorAccount.DoesNotExist:
            raise ValidationError(f"Investor account with ID {investor_account_id} does not exist")
        
        # Get the calendar month for calculation
        month_start = date(calculation_date.year, calculation_date.month, 1)
        
        # Calculate next month start for range check
        if calculation_date.month == 12:
            month_end = date(calculation_date.year + 1, 1, 1) - timedelta(days=1)
        else:
            month_end = date(calculation_date.year, calculation_date.month + 1, 1) - timedelta(days=1)
        
        # Check if interest has already been applied for this month
        if account.last_interest_date:
            last_interest_month = date(account.last_interest_date.year, account.last_interest_date.month, 1)
            if last_interest_month >= month_start:
                return {
                    'success': False,
                    'interest_amount': Decimal('0.00'),
                    'new_balance': account.principal_balance,
                    'message': f'Interest already applied for {calculation_date.strftime("%B %Y")}',
                    'withdrawal_penalty': False
                }
        
        # CRITICAL BUSINESS RULE: Check for ANY withdrawals in the calendar month
        withdrawals_in_month = InvestorTransaction.objects.filter(
            investor_account=account,
            transaction_type='WITHDRAWAL',
            transaction_date__gte=month_start,
            transaction_date__lte=month_end
        )
        
        if withdrawals_in_month.exists():
            # Withdrawal penalty: NO interest for this month
            withdrawal_count = withdrawals_in_month.count()
            total_withdrawn = withdrawals_in_month.aggregate(
                total=transaction.Sum('amount')
            )['total'] or Decimal('0.00')
            
            # Update last_interest_date to mark that we've processed this month (with zero interest)
            account.last_interest_date = calculation_date
            account.save(update_fields=['last_interest_date', 'updated_at'])
            
            return {
                'success': False,
                'interest_amount': Decimal('0.00'),
                'new_balance': account.principal_balance,
                'message': (
                    f'No interest accrued for {calculation_date.strftime("%B %Y")} due to '
                    f'{withdrawal_count} withdrawal(s) totaling {total_withdrawn}. '
                    'Business rule: Any withdrawal in a calendar month forfeits that month\'s interest.'
                ),
                'withdrawal_penalty': True,
                'withdrawal_count': withdrawal_count,
                'total_withdrawn': total_withdrawn
            }
        
        # Calculate interest
        # Interest = Principal × (Monthly Rate / 100)
        monthly_rate_decimal = account.monthly_interest_rate / Decimal('100')
        interest_amount = account.principal_balance * monthly_rate_decimal
        
        # Round to 2 decimal places (standard currency precision)
        interest_amount = interest_amount.quantize(Decimal('0.01'), ROUND_HALF_UP)
        
        # Check if interest amount is zero (e.g., zero balance or zero rate)
        if interest_amount == Decimal('0.00'):
            return {
                'success': False,
                'interest_amount': Decimal('0.00'),
                'new_balance': account.principal_balance,
                'message': 'No interest to apply (zero balance or zero rate)',
                'withdrawal_penalty': False
            }
        
        # Compound the interest: Add to principal balance
        new_balance = account.principal_balance + interest_amount
        
        # Create interest transaction record (for audit trail)
        interest_transaction = InvestorTransaction.objects.create(
            investor_account=account,
            transaction_type='INTEREST',
            amount=interest_amount,
            transaction_date=calculation_date,
            description=(
                f'Monthly compound interest for {calculation_date.strftime("%B %Y")} - '
                f'{account.monthly_interest_rate}% on principal balance {account.principal_balance}'
            ),
            reference=f'INT-{calculation_date.strftime("%Y%m")}-{account.id}',
            created_by=created_by
        )
        
        # Update account balance and last interest date
        account.principal_balance = new_balance
        account.last_interest_date = calculation_date
        account.save(update_fields=['principal_balance', 'last_interest_date', 'updated_at'])
        
        return {
            'success': True,
            'interest_amount': interest_amount,
            'previous_balance': account.principal_balance - interest_amount,
            'new_balance': new_balance,
            'message': (
                f'Interest of {interest_amount} applied for {calculation_date.strftime("%B %Y")}. '
                f'Balance increased from {account.principal_balance - interest_amount} to {new_balance}.'
            ),
            'transaction_id': interest_transaction.id,
            'withdrawal_penalty': False,
            'calculation_date': calculation_date,
            'month_processed': calculation_date.strftime("%B %Y")
        }
    
    @staticmethod
    @transaction.atomic()
    def record_deposit(
        investor_account_id: int,
        amount: Decimal,
        transaction_date: date,
        description: str = '',
        reference: str = '',
        created_by=None
    ) -> dict:
        """
        Record a deposit to an investor account
        
        Args:
            investor_account_id: int - ID of the investor account
            amount: Decimal - Deposit amount (must be positive)
            transaction_date: date - Date of the deposit
            description: str - Optional description
            reference: str - Optional external reference
            created_by: User - User recording the deposit
        
        Returns:
            dict with success status and transaction details
        
        Raises:
            ValidationError: If validation fails
        """
        if amount <= 0:
            raise ValidationError("Deposit amount must be positive")
        
        if transaction_date > timezone.now().date():
            raise ValidationError("Transaction date cannot be in the future")
        
        # Get account with lock
        try:
            account = InvestorAccount.objects.select_for_update().get(id=investor_account_id)
        except InvestorAccount.DoesNotExist:
            raise ValidationError(f"Investor account with ID {investor_account_id} does not exist")
        
        # Create deposit transaction
        deposit_transaction = InvestorTransaction.objects.create(
            investor_account=account,
            transaction_type='DEPOSIT',
            amount=amount,
            transaction_date=transaction_date,
            description=description or f'Deposit to account {account.id}',
            reference=reference,
            created_by=created_by
        )
        
        # Update account balance
        old_balance = account.principal_balance
        account.principal_balance += amount
        account.save(update_fields=['principal_balance', 'updated_at'])
        
        return {
            'success': True,
            'transaction_id': deposit_transaction.id,
            'amount': amount,
            'previous_balance': old_balance,
            'new_balance': account.principal_balance,
            'message': f'Deposit of {amount} recorded successfully'
        }
    
    @staticmethod
    @transaction.atomic()
    def record_withdrawal(
        investor_account_id: int,
        amount: Decimal,
        transaction_date: date,
        description: str = '',
        reference: str = '',
        created_by=None
    ) -> dict:
        """
        Record a withdrawal from an investor account
        
        IMPORTANT: Any withdrawal in a calendar month will forfeit that month's interest
        
        Args:
            investor_account_id: int - ID of the investor account
            amount: Decimal - Withdrawal amount (must be positive)
            transaction_date: date - Date of the withdrawal
            description: str - Optional description
            reference: str - Optional external reference
            created_by: User - User recording the withdrawal
        
        Returns:
            dict with success status, transaction details, and interest warning
        
        Raises:
            ValidationError: If validation fails or insufficient balance
        """
        if amount <= 0:
            raise ValidationError("Withdrawal amount must be positive")
        
        if transaction_date > timezone.now().date():
            raise ValidationError("Transaction date cannot be in the future")
        
        # Get account with lock
        try:
            account = InvestorAccount.objects.select_for_update().get(id=investor_account_id)
        except InvestorAccount.DoesNotExist:
            raise ValidationError(f"Investor account with ID {investor_account_id} does not exist")
        
        # Check sufficient balance
        if amount > account.principal_balance:
            raise ValidationError(
                f"Insufficient balance. Withdrawal amount {amount} exceeds "
                f"available balance {account.principal_balance}"
            )
        
        # Create withdrawal transaction
        withdrawal_transaction = InvestorTransaction.objects.create(
            investor_account=account,
            transaction_type='WITHDRAWAL',
            amount=amount,
            transaction_date=transaction_date,
            description=description or f'Withdrawal from account {account.id}',
            reference=reference,
            created_by=created_by
        )
        
        # Update account balance
        old_balance = account.principal_balance
        account.principal_balance -= amount
        account.save(update_fields=['principal_balance', 'updated_at'])
        
        # Warning about interest forfeiture
        month_name = transaction_date.strftime("%B %Y")
        interest_warning = (
            f"WARNING: This withdrawal in {month_name} will forfeit interest for the entire month. "
            "Business rule: Any withdrawal in a calendar month results in zero interest for that month."
        )
        
        return {
            'success': True,
            'transaction_id': withdrawal_transaction.id,
            'amount': amount,
            'previous_balance': old_balance,
            'new_balance': account.principal_balance,
            'message': f'Withdrawal of {amount} recorded successfully',
            'interest_warning': interest_warning,
            'affected_month': month_name
        }
    
    @staticmethod
    def get_interest_preview(
        investor_account_id: int,
        calculation_date: date = None
    ) -> dict:
        """
        Preview interest calculation without applying it (read-only)
        
        Args:
            investor_account_id: int - ID of the investor account
            calculation_date: date - Date to calculate for (default: today)
        
        Returns:
            dict with preview information
        """
        if calculation_date is None:
            calculation_date = timezone.now().date()
        
        try:
            account = InvestorAccount.objects.get(id=investor_account_id)
        except InvestorAccount.DoesNotExist:
            raise ValidationError(f"Investor account with ID {investor_account_id} does not exist")
        
        # Get the calendar month
        month_start = date(calculation_date.year, calculation_date.month, 1)
        if calculation_date.month == 12:
            month_end = date(calculation_date.year + 1, 1, 1) - timedelta(days=1)
        else:
            month_end = date(calculation_date.year, calculation_date.month + 1, 1) - timedelta(days=1)
        
        # Check for withdrawals
        withdrawals_in_month = InvestorTransaction.objects.filter(
            investor_account=account,
            transaction_type='WITHDRAWAL',
            transaction_date__gte=month_start,
            transaction_date__lte=month_end
        )
        
        has_withdrawal = withdrawals_in_month.exists()
        
        # Calculate potential interest
        monthly_rate_decimal = account.monthly_interest_rate / Decimal('100')
        potential_interest = (account.principal_balance * monthly_rate_decimal).quantize(
            Decimal('0.01'), ROUND_HALF_UP
        )
        
        # Check if already applied
        already_applied = False
        if account.last_interest_date:
            last_interest_month = date(account.last_interest_date.year, account.last_interest_date.month, 1)
            already_applied = last_interest_month >= month_start
        
        return {
            'account_id': account.id,
            'investor_name': account.investor.get_full_name(),
            'current_balance': account.principal_balance,
            'monthly_interest_rate': account.monthly_interest_rate,
            'calculation_date': calculation_date,
            'month': calculation_date.strftime("%B %Y"),
            'potential_interest': potential_interest if not has_withdrawal else Decimal('0.00'),
            'projected_balance': account.principal_balance + potential_interest if not has_withdrawal else account.principal_balance,
            'has_withdrawal_penalty': has_withdrawal,
            'withdrawal_count': withdrawals_in_month.count() if has_withdrawal else 0,
            'already_applied': already_applied,
            'can_apply': not has_withdrawal and not already_applied,
            'message': self._get_preview_message(has_withdrawal, already_applied, potential_interest)
        }
    
    @staticmethod
    def _get_preview_message(has_withdrawal: bool, already_applied: bool, potential_interest: Decimal) -> str:
        """Helper to generate preview message"""
        if already_applied:
            return "Interest has already been applied for this month"
        elif has_withdrawal:
            return "No interest will be accrued due to withdrawal(s) in this month"
        elif potential_interest == Decimal('0.00'):
            return "No interest to apply (zero balance or zero rate)"
        else:
            return f"Interest of {potential_interest} can be applied"
    
    @staticmethod
    @transaction.atomic()
    def apply_interest_to_multiple_accounts(
        calculation_date: date = None,
        created_by=None
    ) -> dict:
        """
        Apply monthly interest to all active investor accounts
        
        Use Case: End-of-month batch processing
        
        Args:
            calculation_date: date - Date to calculate for (default: today)
            created_by: User - User running the batch process
        
        Returns:
            dict with summary of all accounts processed
        """
        if calculation_date is None:
            calculation_date = timezone.now().date()
        
        accounts = InvestorAccount.objects.all()
        results = {
            'total_accounts': accounts.count(),
            'successful': 0,
            'failed': 0,
            'withdrawal_penalty': 0,
            'already_applied': 0,
            'total_interest_applied': Decimal('0.00'),
            'details': []
        }
        
        for account in accounts:
            try:
                result = InvestorService.apply_monthly_interest(
                    investor_account_id=account.id,
                    calculation_date=calculation_date,
                    created_by=created_by
                )
                
                if result['success']:
                    results['successful'] += 1
                    results['total_interest_applied'] += result['interest_amount']
                else:
                    results['failed'] += 1
                    if result.get('withdrawal_penalty'):
                        results['withdrawal_penalty'] += 1
                    elif 'already applied' in result['message'].lower():
                        results['already_applied'] += 1
                
                results['details'].append({
                    'account_id': account.id,
                    'investor': account.investor.get_full_name(),
                    'result': result
                })
            
            except Exception as e:
                results['failed'] += 1
                results['details'].append({
                    'account_id': account.id,
                    'investor': account.investor.get_full_name(),
                    'error': str(e)
                })
        
        return results
