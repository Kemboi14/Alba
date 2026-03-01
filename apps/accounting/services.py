"""
Accounting Services: Business logic for double-entry accounting operations

This service layer provides safe, transaction-protected methods for creating
and managing journal entries, ensuring data integrity and business rule compliance.
"""
from decimal import Decimal
from typing import List, Dict, Optional
from django.db import transaction
from django.core.exceptions import ValidationError
from django.utils import timezone
from .models import (
    FiscalYear,
    AccountType,
    Account,
    JournalEntry,
    JournalEntryLine,
)


class AccountingService:
    """
    Service class for accounting operations
    
    Provides transaction-safe methods for:
    - Creating journal entries
    - Posting journal entries
    - Reversing journal entries
    - Validating account balances
    
    All methods use database transactions to ensure data integrity.
    """
    
    @staticmethod
    def generate_entry_number(prefix: str = "JE") -> str:
        """
        Generate unique journal entry number
        
        Args:
            prefix: Prefix for entry number (default: "JE")
            
        Returns:
            str: Unique entry number (e.g., "JE-2026-00001")
        """
        from django.db.models import Max
        
        year = timezone.now().year
        prefix_with_year = f"{prefix}-{year}"
        
        # Get the highest entry number for this year
        last_entry = JournalEntry.objects.filter(
            entry_number__startswith=prefix_with_year
        ).aggregate(Max('entry_number'))['entry_number__max']
        
        if last_entry:
            # Extract the numeric part and increment
            last_number = int(last_entry.split('-')[-1])
            new_number = last_number + 1
        else:
            new_number = 1
        
        return f"{prefix_with_year}-{new_number:05d}"
    
    @staticmethod
    @transaction.atomic
    def create_journal_entry(
        date,
        fiscal_year,
        description: str,
        lines: List[Dict],
        created_by,
        entry_number: Optional[str] = None,
        reference: str = "",
        source_module: str = "",
        source_document: str = "",
        auto_post: bool = False,
    ) -> JournalEntry:
        """
        Create a journal entry with lines
        
        Args:
            date: Transaction date
            fiscal_year: FiscalYear instance
            description: Entry description
            lines: List of dicts with keys:
                - account: Account instance or code
                - description: Line description
                - debit_amount: Decimal (optional, default 0)
                - credit_amount: Decimal (optional, default 0)
                - cost_center: str (optional)
                - department: str (optional)
            created_by: User instance
            entry_number: Optional entry number (generated if not provided)
            reference: External reference
            source_module: Source module name
            source_document: Source document reference
            auto_post: Whether to post immediately after creation
            
        Returns:
            JournalEntry: Created journal entry
            
        Raises:
            ValidationError: If entry is unbalanced or validation fails
            
        Example:
            entry = AccountingService.create_journal_entry(
                date=date.today(),
                fiscal_year=fy,
                description="Cash sale",
                lines=[
                    {'account': cash_account, 'debit_amount': Decimal('1000.00'), 'description': 'Cash received'},
                    {'account': revenue_account, 'credit_amount': Decimal('1000.00'), 'description': 'Sale revenue'},
                ],
                created_by=user,
            )
        """
        # Generate entry number if not provided
        if not entry_number:
            entry_number = AccountingService.generate_entry_number()
        
        # Validate lines exist
        if not lines:
            raise ValidationError("Journal entry must have at least one line")
        
        # Validate balanced before creating
        total_debits = Decimal('0.00')
        total_credits = Decimal('0.00')
        
        for line in lines:
            debit = line.get('debit_amount', Decimal('0.00'))
            credit = line.get('credit_amount', Decimal('0.00'))
            
            if isinstance(debit, (int, float, str)):
                debit = Decimal(str(debit))
            if isinstance(credit, (int, float, str)):
                credit = Decimal(str(credit))
            
            total_debits += debit
            total_credits += credit
        
        if total_debits != total_credits:
            raise ValidationError(
                f"Journal entry is unbalanced. "
                f"Debits: {total_debits}, Credits: {total_credits}, "
                f"Difference: {total_debits - total_credits}"
            )
        
        # Create journal entry
        entry = JournalEntry.objects.create(
            entry_number=entry_number,
            date=date,
            fiscal_year=fiscal_year,
            description=description,
            reference=reference,
            source_module=source_module,
            source_document=source_document,
            created_by=created_by,
            status='DRAFT',
        )
        
        # Create lines
        for line_data in lines:
            # Get account instance
            account = line_data['account']
            if isinstance(account, str):
                # Assume it's an account code
                account = Account.objects.get(code=account)
            
            # Convert amounts to Decimal
            debit = line_data.get('debit_amount', Decimal('0.00'))
            credit = line_data.get('credit_amount', Decimal('0.00'))
            
            if isinstance(debit, (int, float, str)):
                debit = Decimal(str(debit))
            if isinstance(credit, (int, float, str)):
                credit = Decimal(str(credit))
            
            JournalEntryLine.objects.create(
                journal_entry=entry,
                account=account,
                description=line_data['description'],
                debit_amount=debit,
                credit_amount=credit,
                cost_center=line_data.get('cost_center', ''),
                department=line_data.get('department', ''),
            )
        
        # Auto-post if requested
        if auto_post:
            entry.post(created_by)
        
        return entry
    
    @staticmethod
    @transaction.atomic
    def post_journal_entry(entry_id: int, user) -> JournalEntry:
        """
        Post a draft journal entry
        
        Args:
            entry_id: Journal entry ID
            user: User posting the entry
            
        Returns:
            JournalEntry: Posted entry
            
        Raises:
            ValidationError: If entry cannot be posted
        """
        entry = JournalEntry.objects.select_for_update().get(id=entry_id)
        entry.post(user)
        return entry
    
    @staticmethod
    @transaction.atomic
    def reverse_journal_entry(
        entry_id: int,
        user,
        reason: str
    ) -> JournalEntry:
        """
        Reverse a posted journal entry
        
        Args:
            entry_id: Journal entry ID to reverse
            user: User reversing the entry
            reason: Reason for reversal
            
        Returns:
            JournalEntry: Reversing entry
            
        Raises:
            ValidationError: If entry cannot be reversed
        """
        entry = JournalEntry.objects.select_for_update().get(id=entry_id)
        reversing_entry = entry.reverse(user, reason)
        return reversing_entry
    
    @staticmethod
    def validate_account_balance(account, expected_balance: Decimal, as_of_date=None) -> bool:
        """
        Validate account balance matches expected amount
        
        Args:
            account: Account instance
            expected_balance: Expected balance
            as_of_date: Date to check balance as of (default: now)
            
        Returns:
            bool: Whether balance matches
        """
        actual_balance = account.get_balance(as_of_date)
        return actual_balance == expected_balance
    
    @staticmethod
    def get_trial_balance(fiscal_year, as_of_date=None) -> Dict:
        """
        Generate trial balance for a fiscal year
        
        Args:
            fiscal_year: FiscalYear instance
            as_of_date: Date to calculate balance as of (default: fiscal year end)
            
        Returns:
            dict: Trial balance with accounts, debits, credits
        """
        if not as_of_date:
            as_of_date = fiscal_year.end_date
        
        accounts = Account.objects.filter(is_active=True).order_by('code')
        
        trial_balance = {
            'accounts': [],
            'total_debits': Decimal('0.00'),
            'total_credits': Decimal('0.00'),
            'is_balanced': True,
        }
        
        for account in accounts:
            balance = account.get_balance(as_of_date)
            
            if balance != 0:
                # Determine debit or credit side
                if account.account_type.normal_balance == 'DEBIT':
                    debit_balance = balance if balance > 0 else Decimal('0.00')
                    credit_balance = abs(balance) if balance < 0 else Decimal('0.00')
                else:
                    credit_balance = balance if balance > 0 else Decimal('0.00')
                    debit_balance = abs(balance) if balance < 0 else Decimal('0.00')
                
                trial_balance['accounts'].append({
                    'code': account.code,
                    'name': account.name,
                    'type': account.account_type.get_name_display(),
                    'debit_balance': debit_balance,
                    'credit_balance': credit_balance,
                })
                
                trial_balance['total_debits'] += debit_balance
                trial_balance['total_credits'] += credit_balance
        
        trial_balance['is_balanced'] = (
            trial_balance['total_debits'] == trial_balance['total_credits']
        )
        
        return trial_balance
    
    @staticmethod
    @transaction.atomic
    def create_simple_entry(
        date,
        fiscal_year,
        description: str,
        debit_account,
        credit_account,
        amount: Decimal,
        created_by,
        reference: str = "",
        auto_post: bool = False,
    ) -> JournalEntry:
        """
        Create a simple two-line journal entry (debit/credit)
        
        This is a convenience method for common single debit/credit entries.
        
        Args:
            date: Transaction date
            fiscal_year: FiscalYear instance
            description: Entry description
            debit_account: Account to debit (instance or code)
            credit_account: Account to credit (instance or code)
            amount: Transaction amount
            created_by: User instance
            reference: External reference
            auto_post: Whether to post immediately
            
        Returns:
            JournalEntry: Created entry
            
        Example:
            entry = AccountingService.create_simple_entry(
                date=date.today(),
                fiscal_year=fy,
                description="Cash payment for supplies",
                debit_account="5100",  # Supplies Expense
                credit_account="1000",  # Cash
                amount=Decimal('500.00'),
                created_by=user,
                auto_post=True,
            )
        """
        lines = [
            {
                'account': debit_account,
                'description': description,
                'debit_amount': amount,
                'credit_amount': Decimal('0.00'),
            },
            {
                'account': credit_account,
                'description': description,
                'debit_amount': Decimal('0.00'),
                'credit_amount': amount,
            },
        ]
        
        return AccountingService.create_journal_entry(
            date=date,
            fiscal_year=fiscal_year,
            description=description,
            lines=lines,
            created_by=created_by,
            reference=reference,
            auto_post=auto_post,
        )
