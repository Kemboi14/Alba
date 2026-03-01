"""
Loan Services: Business Logic for Loan Management with Accounting Integration
Provides transaction-safe operations for loan creation, disbursement, and schedule generation
Automatically posts journal entries for disbursements and repayments
"""
from decimal import Decimal, ROUND_HALF_UP
from datetime import date
from dateutil.relativedelta import relativedelta
from django.db import transaction
from django.core.exceptions import ValidationError
from django.utils import timezone
from apps.loans.models import DirectLoan, DirectLoanRepaymentSchedule, LoanProduct
from apps.core.models import User
from apps.accounting.models import Account, FiscalYear
from apps.accounting.services import AccountingService


class LoanService:
    """
    Loan Service Class (Production-Ready)
    
    Provides transaction-safe business logic for:
    - Creating loans with validation
    - Generating repayment schedules (FLAT and REDUCING_BALANCE methods)
    - Disbursing loans
    - Recording payments
    - Calculating balances
    
    All methods use Decimal for precise financial calculations.
    All database operations are wrapped in @transaction.atomic for data integrity.
    
    Example Usage:
        # Create loan with schedule
        loan = LoanService.create_loan_with_schedule(
            customer=user,
            loan_product=product,
            principal_amount=Decimal('50000.00'),
            term_months=12,
            disbursement_date=date.today()
        )
        
        # Generate schedule separately
        schedules = LoanService.generate_repayment_schedule(
            loan=loan,
            start_date=date.today()
        )
    """
    
    @staticmethod
    @transaction.atomic
    def create_loan(
        customer: User,
        loan_product: LoanProduct,
        principal_amount: Decimal,
        term_months: int,
        interest_rate: Decimal = None,
        disbursement_date: date = None,
        status: str = 'PENDING',
        created_by: User = None
    ) -> DirectLoan:
        """
        Create a new loan with validation
        
        Args:
            customer: User - The borrower
            loan_product: LoanProduct - Product configuration
            principal_amount: Decimal - Loan principal
            term_months: int - Loan term in months
            interest_rate: Decimal - Override interest rate (defaults to product rate)
            disbursement_date: date - Disbursement date (optional)
            status: str - Initial status (default: PENDING)
            created_by: User - User creating the loan (optional)
        
        Returns:
            DirectLoan - Created loan instance
        
        Raises:
            ValidationError: If validation fails
        
        Example:
            loan = LoanService.create_loan(
                customer=user,
                loan_product=product,
                principal_amount=Decimal('100000.00'),
                term_months=24,
                status='APPROVED',
                created_by=admin_user
            )
        """
        # Use product interest rate if not specified
        if interest_rate is None:
            interest_rate = loan_product.interest_rate
        
        # Convert to Decimal if needed
        principal_amount = Decimal(str(principal_amount))
        interest_rate = Decimal(str(interest_rate))
        
        # Validate against product limits
        if not loan_product.is_amount_valid(principal_amount):
            raise ValidationError(
                f'Principal amount {principal_amount} is outside product limits '
                f'({loan_product.minimum_amount} - {loan_product.maximum_amount})'
            )
        
        if not loan_product.is_term_valid(term_months):
            raise ValidationError(
                f'Term {term_months} months is outside product limits '
                f'({loan_product.minimum_term_months} - {loan_product.maximum_term_months})'
            )
        
        # Create loan
        loan = DirectLoan.objects.create(
            customer=customer,
            loan_product=loan_product,
            principal_amount=principal_amount,
            interest_rate=interest_rate,
            term_months=term_months,
            disbursement_date=disbursement_date,
            status=status,
            outstanding_principal=principal_amount if status == 'DISBURSED' else Decimal('0.00'),
            created_by=created_by
        )
        
        return loan
    
    @staticmethod
    @transaction.atomic
    def generate_repayment_schedule(
        loan: DirectLoan,
        start_date: date = None,
        frequency: str = 'MONTHLY'
    ) -> list:
        """
        Generate repayment schedule for a loan
        
        Supports both FLAT and REDUCING_BALANCE interest methods.
        Uses precise Decimal arithmetic throughout.
        
        Args:
            loan: DirectLoan - The loan to generate schedule for
            start_date: date - First payment date (defaults to disbursement date or today)
            frequency: str - Payment frequency (MONTHLY, WEEKLY, FORTNIGHTLY, QUARTERLY)
        
        Returns:
            list - List of created DirectLoanRepaymentSchedule instances
        
        Raises:
            ValidationError: If schedule cannot be generated
        
        Example:
            schedules = LoanService.generate_repayment_schedule(
                loan=loan,
                start_date=date(2024, 4, 1),
                frequency='MONTHLY'
            )
        """
        # Determine start date
        if start_date is None:
            start_date = loan.disbursement_date or timezone.now().date()
        
        # Delete existing schedule if any
        loan.repayment_schedules.all().delete()
        
        # Generate schedule based on interest method
        if loan.loan_product.interest_method == 'FLAT':
            schedules = LoanService._generate_flat_schedule(
                loan, start_date, frequency
            )
        else:  # REDUCING_BALANCE
            schedules = LoanService._generate_reducing_balance_schedule(
                loan, start_date, frequency
            )
        
        return schedules
    
    @staticmethod
    def _generate_flat_schedule(
        loan: DirectLoan,
        start_date: date,
        frequency: str
    ) -> list:
        """
        Generate FLAT interest repayment schedule
        
        For FLAT interest:
        - Interest is calculated on original principal for entire term
        - Same payment amount each period
        - Interest distributed evenly across installments
        
        Formula:
            Total Interest = Principal × (Rate/100) × (Months/12)
            Monthly Payment = (Principal + Total Interest) / Number of Months
        
        Args:
            loan: DirectLoan - The loan
            start_date: date - First payment date
            frequency: str - Payment frequency
        
        Returns:
            list - List of created schedule instances
        """
        # Calculate total interest
        total_interest = loan.loan_product.calculate_flat_interest(
            loan.principal_amount,
            loan.term_months
        )
        
        # Calculate monthly payment
        monthly_payment = loan.get_monthly_payment()
        
        # Calculate portions
        interest_per_month = total_interest / Decimal(loan.term_months)
        principal_per_month = loan.principal_amount / Decimal(loan.term_months)
        
        # Round to 2 decimal places
        interest_per_month = interest_per_month.quantize(Decimal('0.01'), ROUND_HALF_UP)
        principal_per_month = principal_per_month.quantize(Decimal('0.01'), ROUND_HALF_UP)
        
        schedules = []
        current_date = start_date
        remaining_principal = loan.principal_amount
        remaining_interest = total_interest
        
        for i in range(1, loan.term_months + 1):
            # For last installment, use remaining amounts to avoid rounding errors
            if i == loan.term_months:
                principal_due = remaining_principal
                interest_due = remaining_interest
            else:
                principal_due = principal_per_month
                interest_due = interest_per_month
            
            # Create schedule entry
            schedule = DirectLoanRepaymentSchedule.objects.create(
                loan=loan,
                installment_number=i,
                due_date=current_date,
                principal_due=principal_due,
                interest_due=interest_due,
                penalty_due=Decimal('0.00'),
                paid_amount=Decimal('0.00'),
                is_paid=False
            )
            schedules.append(schedule)
            
            # Update remaining amounts
            remaining_principal -= principal_due
            remaining_interest -= interest_due
            
            # Calculate next due date based on frequency
            current_date = LoanService._get_next_due_date(current_date, frequency)
        
        return schedules
    
    @staticmethod
    def _generate_reducing_balance_schedule(
        loan: DirectLoan,
        start_date: date,
        frequency: str
    ) -> list:
        """
        Generate REDUCING BALANCE (EMI) repayment schedule
        
        For REDUCING BALANCE:
        - Interest calculated on outstanding balance each period
        - Fixed installment amount (EMI)
        - Interest portion decreases over time
        - Principal portion increases over time
        
        EMI Formula:
            EMI = P × r × (1 + r)^n / ((1 + r)^n - 1)
            where:
                P = Principal loan amount
                r = Monthly interest rate (annual rate / 12 / 100)
                n = Number of months
        
        Args:
            loan: DirectLoan - The loan
            start_date: date - First payment date
            frequency: str - Payment frequency
        
        Returns:
            list - List of created schedule instances
        """
        # Get monthly payment (EMI)
        monthly_payment = loan.get_monthly_payment()
        
        # Calculate monthly interest rate
        monthly_rate = (loan.interest_rate / Decimal('100')) / Decimal('12')
        
        schedules = []
        current_date = start_date
        outstanding_balance = loan.principal_amount
        
        for i in range(1, loan.term_months + 1):
            # Calculate interest on outstanding balance
            interest_due = (outstanding_balance * monthly_rate).quantize(
                Decimal('0.01'), ROUND_HALF_UP
            )
            
            # Calculate principal portion
            principal_due = monthly_payment - interest_due
            
            # For last installment, adjust to close the loan exactly
            if i == loan.term_months:
                principal_due = outstanding_balance
                # Recalculate interest for final payment if needed
                interest_due = (monthly_payment - principal_due).quantize(
                    Decimal('0.01'), ROUND_HALF_UP
                )
                # Ensure non-negative
                if interest_due < 0:
                    interest_due = Decimal('0.00')
            
            # Ensure principal due doesn't exceed outstanding balance
            if principal_due > outstanding_balance:
                principal_due = outstanding_balance
            
            # Create schedule entry
            schedule = DirectLoanRepaymentSchedule.objects.create(
                loan=loan,
                installment_number=i,
                due_date=current_date,
                principal_due=principal_due,
                interest_due=interest_due,
                penalty_due=Decimal('0.00'),
                paid_amount=Decimal('0.00'),
                is_paid=False
            )
            schedules.append(schedule)
            
            # Update outstanding balance
            outstanding_balance -= principal_due
            
            # Calculate next due date
            current_date = LoanService._get_next_due_date(current_date, frequency)
        
        return schedules
    
    @staticmethod
    def _get_next_due_date(current_date: date, frequency: str) -> date:
        """
        Calculate next due date based on frequency
        
        Args:
            current_date: date - Current due date
            frequency: str - Payment frequency
        
        Returns:
            date - Next due date
        """
        if frequency == 'WEEKLY':
            return current_date + relativedelta(weeks=1)
        elif frequency == 'FORTNIGHTLY':
            return current_date + relativedelta(weeks=2)
        elif frequency == 'MONTHLY':
            return current_date + relativedelta(months=1)
        elif frequency == 'QUARTERLY':
            return current_date + relativedelta(months=3)
        else:
            # Default to monthly
            return current_date + relativedelta(months=1)
    
    @staticmethod
    @transaction.atomic
    def create_loan_with_schedule(
        customer: User,
        loan_product: LoanProduct,
        principal_amount: Decimal,
        term_months: int,
        disbursement_date: date = None,
        interest_rate: Decimal = None,
        frequency: str = 'MONTHLY',
        status: str = 'PENDING',
        created_by: User = None
    ) -> DirectLoan:
        """
        Create loan and generate repayment schedule in one transaction
        
        This is the recommended method for creating new loans as it ensures
        the loan and its schedule are created atomically.
        
        Args:
            customer: User - The borrower
            loan_product: LoanProduct - Product configuration
            principal_amount: Decimal - Loan principal
            term_months: int - Loan term in months
            disbursement_date: date - Disbursement date (optional, defaults to today)
            interest_rate: Decimal - Override interest rate (optional)
            frequency: str - Payment frequency (default: MONTHLY)
            status: str - Initial status (default: PENDING)
            created_by: User - User creating the loan (optional)
        
        Returns:
            DirectLoan - Created loan with repayment schedule
        
        Raises:
            ValidationError: If validation fails
        
        Example:
            loan = LoanService.create_loan_with_schedule(
                customer=user,
                loan_product=product,
                principal_amount=Decimal('50000.00'),
                term_months=12,
                disbursement_date=date.today(),
                status='DISBURSED',
                created_by=admin_user
            )
            # Loan and repayment schedule created atomically
            print(f"Created loan with {loan.repayment_schedules.count()} installments")
        """
        # Set disbursement date if not provided
        if disbursement_date is None:
            disbursement_date = timezone.now().date()
        
        # Create loan
        loan = LoanService.create_loan(
            customer=customer,
            loan_product=loan_product,
            principal_amount=principal_amount,
            term_months=term_months,
            interest_rate=interest_rate,
            disbursement_date=disbursement_date,
            status=status,
            created_by=created_by
        )
        
        # Generate repayment schedule
        LoanService.generate_repayment_schedule(
            loan=loan,
            start_date=disbursement_date,
            frequency=frequency
        )
        
        return loan
    
    @staticmethod
    @transaction.atomic
    def disburse_loan(
        loan: DirectLoan,
        disbursement_date: date = None,
        disbursed_by: User = None
    ) -> DirectLoan:
        """
        Mark loan as disbursed and set outstanding principal
        
        Args:
            loan: DirectLoan - The loan to disburse
            disbursement_date: date - Date of disbursement (defaults to today)
            disbursed_by: User - User disbursing the loan (optional)
        
        Returns:
            DirectLoan - Updated loan instance
        
        Raises:
            ValidationError: If loan cannot be disbursed
        
        Example:
            loan = LoanService.disburse_loan(
                loan=loan,
                disbursement_date=date.today(),
                disbursed_by=admin_user
            )
        """
        if loan.status not in ['PENDING', 'APPROVED']:
            raise ValidationError(
                f'Loan cannot be disbursed from status: {loan.status}. '
                'Must be PENDING or APPROVED.'
            )
        
        if disbursement_date is None:
            disbursement_date = timezone.now().date()
        
        # Update loan
        loan.status = 'DISBURSED'
        loan.disbursement_date = disbursement_date
        loan.outstanding_principal = loan.principal_amount
        
        if disbursed_by:
            loan.created_by = disbursed_by
        
        loan.save()
        
        # Generate schedule if not exists
        if loan.repayment_schedules.count() == 0:
            LoanService.generate_repayment_schedule(
                loan=loan,
                start_date=disbursement_date
            )
        
        return loan
    
    @staticmethod
    @transaction.atomic
    def record_payment(
        loan: DirectLoan,
        amount: Decimal,
        payment_date: date = None,
        apply_to_oldest: bool = True
    ) -> dict:
        """
        Record a payment against loan and allocate to installments
        
        Args:
            loan: DirectLoan - The loan receiving payment
            amount: Decimal - Payment amount
            payment_date: date - Date of payment (defaults to today)
            apply_to_oldest: bool - Apply to oldest unpaid installment first (default: True)
        
        Returns:
            dict - Summary of payment allocation
        
        Raises:
            ValidationError: If payment cannot be recorded
        
        Example:
            result = LoanService.record_payment(
                loan=loan,
                amount=Decimal('5000.00'),
                payment_date=date.today()
            )
            print(f"Applied to {result['installments_paid']} installments")
        """
        if amount <= 0:
            raise ValidationError('Payment amount must be positive')
        
        if payment_date is None:
            payment_date = timezone.now().date()
        
        amount = Decimal(str(amount))
        remaining_amount = amount
        installments_updated = []
        
        # Get unpaid installments in order
        if apply_to_oldest:
            schedules = loan.repayment_schedules.filter(
                is_paid=False
            ).order_by('due_date', 'installment_number')
        else:
            schedules = loan.repayment_schedules.filter(
                is_paid=False
            ).order_by('-due_date', '-installment_number')
        
        # Apply payment to installments
        for schedule in schedules:
            if remaining_amount <= 0:
                break
            
            # Record payment and get excess
            excess = schedule.record_payment(remaining_amount, payment_date)
            installments_updated.append(schedule.installment_number)
            remaining_amount = excess
        
        # Update loan outstanding principal
        total_principal_paid = loan.repayment_schedules.filter(
            is_paid=True
        ).aggregate(
            total=models.Sum('principal_due')
        )['total'] or Decimal('0.00')
        
        loan.outstanding_principal = loan.principal_amount - total_principal_paid
        
        # Check if loan is fully paid
        if loan.outstanding_principal == 0:
            loan.status = 'CLOSED'
        
        loan.save()
        
        return {
            'amount_paid': amount,
            'amount_applied': amount - remaining_amount,
            'excess_amount': remaining_amount,
            'installments_paid': len(installments_updated),
            'installment_numbers': installments_updated,
            'loan_outstanding': loan.outstanding_principal,
            'loan_status': loan.status
        }
    
    @staticmethod
    def calculate_loan_summary(loan: DirectLoan) -> dict:
        """
        Calculate comprehensive loan summary with all balances
        
        Args:
            loan: DirectLoan - The loan to summarize
        
        Returns:
            dict - Comprehensive loan summary
        
        Example:
            summary = LoanService.calculate_loan_summary(loan)
            print(f"Outstanding: {summary['outstanding_principal']}")
            print(f"Total paid: {summary['total_paid']}")
            print(f"Progress: {summary['payment_progress']}%")
        """
        from django.db.models import Sum, Count, Q
        
        # Get schedule aggregates
        schedule_stats = loan.repayment_schedules.aggregate(
            total_principal=Sum('principal_due'),
            total_interest=Sum('interest_due'),
            total_penalties=Sum('penalty_due'),
            total_paid=Sum('paid_amount'),
            paid_count=Count('id', filter=Q(is_paid=True)),
            total_count=Count('id')
        )
        
        total_principal = schedule_stats['total_principal'] or Decimal('0.00')
        total_interest = schedule_stats['total_interest'] or Decimal('0.00')
        total_penalties = schedule_stats['total_penalties'] or Decimal('0.00')
        total_paid = schedule_stats['total_paid'] or Decimal('0.00')
        paid_count = schedule_stats['paid_count'] or 0
        total_count = schedule_stats['total_count'] or 0
        
        total_due = total_principal + total_interest + total_penalties
        outstanding = total_due - total_paid
        
        # Calculate progress percentage
        payment_progress = Decimal('0.00')
        if total_due > 0:
            payment_progress = (total_paid / total_due * Decimal('100')).quantize(
                Decimal('0.01'), ROUND_HALF_UP
            )
        
        return {
            'principal_amount': loan.principal_amount,
            'interest_rate': loan.interest_rate,
            'term_months': loan.term_months,
            'disbursement_date': loan.disbursement_date,
            'status': loan.status,
            'outstanding_principal': loan.outstanding_principal,
            'total_principal_due': total_principal,
            'total_interest_due': total_interest,
            'total_penalties_due': total_penalties,
            'total_amount_due': total_due,
            'total_paid': total_paid,
            'total_outstanding': outstanding,
            'installments_total': total_count,
            'installments_paid': paid_count,
            'installments_pending': total_count - paid_count,
            'payment_progress': payment_progress,
            'next_payment': loan.get_next_payment_due()
        }
    
    @staticmethod
    @transaction.atomic
    def disburse_loan_with_accounting(
        loan: DirectLoan,
        bank_account: Account,
        disbursement_date: date = None,
        disbursed_by: User = None,
        fiscal_year: FiscalYear = None,
        reference: str = ""
    ) -> dict:
        """
        Disburse loan and automatically post accounting entry
        
        Creates journal entry:
        - Debit: Loan Receivable (from loan product configuration)
        - Credit: Bank Account (provided)
        
        All operations wrapped in transaction.atomic() to prevent partial corruption.
        If any step fails, entire transaction rolls back.
        
        Args:
            loan: DirectLoan - The loan to disburse
            bank_account: Account - Bank account to credit
            disbursement_date: date - Date of disbursement (defaults to today)
            disbursed_by: User - User disbursing the loan
            fiscal_year: FiscalYear - Fiscal year for journal entry (required)
            reference: str - External reference (e.g., bank transaction ID)
        
        Returns:
            dict - Summary with loan and journal entry details
        
        Raises:
            ValidationError: If loan cannot be disbursed or accounting entry fails
        
        Example:
            result = LoanService.disburse_loan_with_accounting(
                loan=loan,
                bank_account=bank_account,
                disbursement_date=date.today(),
                disbursed_by=admin_user,
                fiscal_year=current_fiscal_year,
                reference="TXN-12345"
            )
            print(f"Loan disbursed: {result['loan'].pk}")
            print(f"Journal entry: {result['journal_entry'].entry_number}")
        """
        # Validate loan can be disbursed
        if loan.status not in ['PENDING', 'APPROVED']:
            raise ValidationError(
                f'Loan cannot be disbursed from status: {loan.status}. '
                'Must be PENDING or APPROVED.'
            )
        
        # Validate fiscal year is provided
        if not fiscal_year:
            raise ValidationError('Fiscal year is required for accounting entry')
        
        # Validate loan product has loan receivable account configured
        if not loan.loan_product.loan_receivable_account:
            raise ValidationError(
                f'Loan product "{loan.loan_product.name}" does not have '
                'loan_receivable_account configured. Please configure GL accounts.'
            )
        
        # Validate bank account is an ASSET account
        if bank_account.account_type.name != 'ASSET':
            raise ValidationError(
                f'Bank account must be an ASSET account. '
                f'"{bank_account.name}" is {bank_account.account_type.name}'
            )
        
        # Set defaults
        if disbursement_date is None:
            disbursement_date = timezone.now().date()
        
        # Get loan receivable account from product
        loan_receivable = loan.loan_product.loan_receivable_account
        
        # Validate loan receivable is ASSET account
        if loan_receivable.account_type.name != 'ASSET':
            raise ValidationError(
                f'Loan receivable account must be ASSET. '
                f'"{loan_receivable.name}" is {loan_receivable.account_type.name}'
            )
        
        # Update loan status
        loan.status = 'DISBURSED'
        loan.disbursement_date = disbursement_date
        loan.outstanding_principal = loan.principal_amount
        
        if disbursed_by:
            loan.created_by = disbursed_by
        
        loan.save()
        
        # Generate schedule if not exists
        if loan.repayment_schedules.count() == 0:
            LoanService.generate_repayment_schedule(
                loan=loan,
                start_date=disbursement_date
            )
        
        # Create accounting entry: Debit Loan Receivable, Credit Bank
        journal_entry = AccountingService.create_simple_entry(
            date=disbursement_date,
            fiscal_year=fiscal_year,
            description=f'Loan disbursement - {loan.customer.get_full_name()} - Loan #{loan.pk}',
            debit_account=loan_receivable,
            credit_account=bank_account,
            amount=loan.principal_amount,
            created_by=disbursed_by,
            reference=reference,
            auto_post=True  # Post immediately
        )
        
        return {
            'loan': loan,
            'journal_entry': journal_entry,
            'disbursement_date': disbursement_date,
            'amount_disbursed': loan.principal_amount,
            'loan_receivable_account': loan_receivable.code,
            'bank_account': bank_account.code,
            'entry_number': journal_entry.entry_number,
            'status': loan.status
        }
    
    @staticmethod
    @transaction.atomic
    def record_payment_with_accounting(
        loan: DirectLoan,
        amount: Decimal,
        bank_account: Account,
        payment_date: date = None,
        received_by: User = None,
        fiscal_year: FiscalYear = None,
        reference: str = "",
        apply_to_oldest: bool = True
    ) -> dict:
        """
        Record loan payment with automatic accounting entry
        
        Payment allocation order (as per requirement):
        1. Penalty
        2. Interest
        3. Principal
        
        Creates journal entry:
        - Debit: Bank Account (cash received)
        - Credit: Loan Receivable (principal portion)
        - Credit: Interest Income (interest portion)
        - Credit: Penalty Income (penalty portion, if any)
        
        All operations wrapped in transaction.atomic() to prevent partial corruption.
        If any step fails, entire transaction rolls back.
        
        Args:
            loan: DirectLoan - The loan receiving payment
            amount: Decimal - Payment amount
            bank_account: Account - Bank account receiving payment
            payment_date: date - Date of payment (defaults to today)
            received_by: User - User recording the payment
            fiscal_year: FiscalYear - Fiscal year for journal entry (required)
            reference: str - External reference (e.g., receipt number, transaction ID)
            apply_to_oldest: bool - Apply to oldest unpaid installment first (default: True)
        
        Returns:
            dict - Summary with payment allocation and journal entry details
        
        Raises:
            ValidationError: If payment cannot be recorded or accounting entry fails
        
        Example:
            result = LoanService.record_payment_with_accounting(
                loan=loan,
                amount=Decimal('5000.00'),
                bank_account=bank_account,
                payment_date=date.today(),
                received_by=cashier_user,
                fiscal_year=current_fiscal_year,
                reference="RCPT-12345"
            )
            print(f"Payment allocation: {result['allocation']}")
            print(f"Journal entry: {result['journal_entry'].entry_number}")
        """
        # Validate inputs
        if amount <= 0:
            raise ValidationError('Payment amount must be positive')
        
        if not fiscal_year:
            raise ValidationError('Fiscal year is required for accounting entry')
        
        # Validate loan product has required GL accounts
        if not loan.loan_product.loan_receivable_account:
            raise ValidationError(
                f'Loan product "{loan.loan_product.name}" does not have '
                'loan_receivable_account configured'
            )
        
        if not loan.loan_product.interest_income_account:
            raise ValidationError(
                f'Loan product "{loan.loan_product.name}" does not have '
                'interest_income_account configured'
            )
        
        # Validate bank account is ASSET
        if bank_account.account_type.name != 'ASSET':
            raise ValidationError(
                f'Bank account must be an ASSET account. '
                f'"{bank_account.name}" is {bank_account.account_type.name}'
            )
        
        # Set defaults
        if payment_date is None:
            payment_date = timezone.now().date()
        
        amount = Decimal(str(amount))
        remaining_amount = amount
        
        # Track allocation breakdown
        allocation = {
            'penalty_paid': Decimal('0.00'),
            'interest_paid': Decimal('0.00'),
            'principal_paid': Decimal('0.00'),
            'installments_updated': [],
            'installments_fully_paid': []
        }
        
        # Get unpaid installments in order
        if apply_to_oldest:
            schedules = loan.repayment_schedules.filter(
                is_paid=False
            ).order_by('due_date', 'installment_number')
        else:
            schedules = loan.repayment_schedules.filter(
                is_paid=False
            ).order_by('-due_date', '-installment_number')
        
        # Apply payment to installments with proper allocation order
        for schedule in schedules:
            if remaining_amount <= 0:
                break
            
            # Calculate what's due for this installment
            penalty_due = schedule.penalty_due
            interest_due = schedule.interest_due
            principal_due = schedule.principal_due
            
            # Calculate what's already been paid
            paid = schedule.paid_amount
            
            # We need to track how much of each component has been paid
            # For simplicity, we'll assume payment allocation follows the order:
            # penalty → interest → principal
            
            # Calculate remaining amounts due in order
            penalty_remaining = max(Decimal('0.00'), penalty_due - min(paid, penalty_due))
            
            interest_start = penalty_due
            interest_already_paid = max(Decimal('0.00'), min(paid, interest_start + interest_due) - interest_start)
            interest_remaining = interest_due - interest_already_paid
            
            principal_start = penalty_due + interest_due
            principal_already_paid = max(Decimal('0.00'), paid - principal_start)
            principal_remaining = principal_due - principal_already_paid
            
            # Allocate payment in order: Penalty → Interest → Principal
            installment_payment = Decimal('0.00')
            
            # 1. Pay penalty first
            penalty_payment = min(remaining_amount, penalty_remaining)
            if penalty_payment > 0:
                allocation['penalty_paid'] += penalty_payment
                remaining_amount -= penalty_payment
                installment_payment += penalty_payment
            
            # 2. Pay interest second
            interest_payment = min(remaining_amount, interest_remaining)
            if interest_payment > 0:
                allocation['interest_paid'] += interest_payment
                remaining_amount -= interest_payment
                installment_payment += interest_payment
            
            # 3. Pay principal last
            principal_payment = min(remaining_amount, principal_remaining)
            if principal_payment > 0:
                allocation['principal_paid'] += principal_payment
                remaining_amount -= principal_payment
                installment_payment += principal_payment
            
            # Record payment on schedule if any amount was allocated
            if installment_payment > 0:
                schedule.paid_amount += installment_payment
                
                # Check if fully paid
                total_due = schedule.get_total_due()
                if schedule.paid_amount >= total_due:
                    schedule.is_paid = True
                    schedule.paid_date = payment_date
                    allocation['installments_fully_paid'].append(schedule.installment_number)
                
                schedule.save()
                allocation['installments_updated'].append(schedule.installment_number)
        
        # Update loan outstanding principal
        total_principal_paid = loan.repayment_schedules.filter(
            is_paid=True
        ).aggregate(
            total=models.Sum('principal_due')
        )['total'] or Decimal('0.00')
        
        loan.outstanding_principal = loan.principal_amount - total_principal_paid
        
        # Check if loan is fully paid
        if loan.outstanding_principal == 0 and loan.repayment_schedules.filter(is_paid=False).count() == 0:
            loan.status = 'CLOSED'
        
        loan.save()
        
        # Create accounting entry
        # We need to create a multi-line entry with proper allocation
        journal_lines = []
        
        # Debit: Bank Account (total amount received)
        journal_lines.append({
            'account': bank_account,
            'description': f'Payment received - Loan #{loan.pk}',
            'debit_amount': amount,
            'credit_amount': Decimal('0.00')
        })
        
        # Credit: Loan Receivable (principal portion)
        if allocation['principal_paid'] > 0:
            journal_lines.append({
                'account': loan.loan_product.loan_receivable_account,
                'description': 'Principal payment',
                'debit_amount': Decimal('0.00'),
                'credit_amount': allocation['principal_paid']
            })
        
        # Credit: Interest Income (interest portion)
        if allocation['interest_paid'] > 0:
            journal_lines.append({
                'account': loan.loan_product.interest_income_account,
                'description': 'Interest payment',
                'debit_amount': Decimal('0.00'),
                'credit_amount': allocation['interest_paid']
            })
        
        # Credit: Penalty Income (penalty portion, if any)
        if allocation['penalty_paid'] > 0:
            # Check if penalty income account is configured
            if not loan.loan_product.penalty_income_account:
                raise ValidationError(
                    f'Loan product "{loan.loan_product.name}" does not have '
                    'penalty_income_account configured, but payment includes penalty'
                )
            
            journal_lines.append({
                'account': loan.loan_product.penalty_income_account,
                'description': 'Penalty payment',
                'debit_amount': Decimal('0.00'),
                'credit_amount': allocation['penalty_paid']
            })
        
        # Create journal entry
        journal_entry = AccountingService.create_journal_entry(
            date=payment_date,
            fiscal_year=fiscal_year,
            description=f'Loan repayment - {loan.customer.get_full_name()} - Loan #{loan.pk}',
            lines=journal_lines,
            created_by=received_by,
            reference=reference,
            auto_post=True  # Post immediately
        )
        
        return {
            'loan': loan,
            'journal_entry': journal_entry,
            'payment_date': payment_date,
            'amount_paid': amount,
            'amount_applied': amount - remaining_amount,
            'excess_amount': remaining_amount,
            'allocation': allocation,
            'loan_outstanding': loan.outstanding_principal,
            'loan_status': loan.status,
            'entry_number': journal_entry.entry_number,
            'installments_updated': len(allocation['installments_updated']),
            'installments_fully_paid': len(allocation['installments_fully_paid'])
        }


# Import models at the end to avoid circular imports
from django.db import models
