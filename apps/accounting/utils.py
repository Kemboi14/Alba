"""
Accounting Utility Functions
Helper functions for double-entry bookkeeping and financial calculations
"""
from decimal import Decimal
from django.utils import timezone
from .models import JournalEntry, JournalEntryLine, Account, FiscalYear


def create_journal_entry(
    date,
    description,
    lines,
    created_by,
    reference='',
    source_module='',
    source_document='',
    auto_post=True
):
    """
    Create a balanced journal entry with multiple lines
    
    Args:
        date: Transaction date
        description: Entry description
        lines: List of tuples (account_code, description, debit, credit)
        created_by: User creating the entry
        reference: Optional reference number
        source_module: Source module name
        source_document: Source document identifier
        auto_post: Automatically post if balanced
    
    Returns:
        JournalEntry object
    
    Example:
        lines = [
            ('1000', 'Cash received', Decimal('1000.00'), Decimal('0.00')),
            ('4000', 'Revenue earned', Decimal('0.00'), Decimal('1000.00')),
        ]
        entry = create_journal_entry(date.today(), 'Revenue receipt', lines, user)
    """
    # Get active fiscal year
    fiscal_year = FiscalYear.objects.filter(
        is_active=True,
        start_date__lte=date,
        end_date__gte=date
    ).first()
    
    if not fiscal_year:
        raise ValueError('No active fiscal year found for this date')
    
    # Generate entry number
    entry_number = generate_journal_entry_number(date)
    
    # Create journal entry
    entry = JournalEntry.objects.create(
        entry_number=entry_number,
        date=date,
        fiscal_year=fiscal_year,
        description=description,
        reference=reference,
        source_module=source_module,
        source_document=source_document,
        is_auto_generated=True,
        created_by=created_by
    )
    
    # Create lines
    for account_code, line_desc, debit, credit in lines:
        account = Account.objects.get(code=account_code)
        JournalEntryLine.objects.create(
            journal_entry=entry,
            account=account,
            description=line_desc,
            debit_amount=debit,
            credit_amount=credit
        )
    
    # Auto-post if requested and balanced
    if auto_post and entry.is_balanced():
        entry.post(created_by)
    
    return entry


def generate_journal_entry_number(date):
    """Generate unique journal entry number"""
    prefix = f"JE{date.year}{date.month:02d}"
    last_entry = JournalEntry.objects.filter(
        entry_number__startswith=prefix
    ).order_by('-entry_number').first()
    
    if last_entry:
        last_num = int(last_entry.entry_number[-4:])
        new_num = last_num + 1
    else:
        new_num = 1
    
    return f"{prefix}{new_num:04d}"


def get_account_balance(account_code, as_of_date=None):
    """Get balance of an account"""
    try:
        account = Account.objects.get(code=account_code)
        return account.get_balance(as_of_date)
    except Account.DoesNotExist:
        return Decimal('0.00')
