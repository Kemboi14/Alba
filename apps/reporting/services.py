"""
Financial and Loan Reporting Services

This module provides high-performance reporting services for:
- Accounting Reports: Trial Balance, Profit & Loss, Balance Sheet
- Loan Reports: Aged Receivables, NPL Analysis, Portfolio at Risk (PAR)

All services use:
- Decimal precision for financial accuracy
- Efficient PostgreSQL queries with annotate/aggregate
- Production-ready error handling and logging

Usage:
    from apps.reporting.services import FinancialReportingService, LoanReportingService
    
    # Generate Trial Balance
    trial_balance = FinancialReportingService.generate_trial_balance(
        fiscal_year=fiscal_year,
        as_of_date=date(2024, 12, 31)
    )
    
    # Calculate Portfolio at Risk
    par_report = LoanReportingService.calculate_par(
        as_of_date=date.today(),
        days=[1, 7, 30, 90]
    )
"""

import logging
from datetime import date, timedelta
from decimal import Decimal
from typing import Dict, List, Optional, Tuple

from django.db import transaction
from django.db.models import (
    Case,
    Count,
    DecimalField,
    F,
    OuterRef,
    Q,
    Subquery,
    Sum,
    When,
    Value,
)
from django.db.models.functions import Coalesce, TruncDate
from django.utils import timezone

from apps.accounting.models import Account, AccountType, JournalEntry, JournalEntryLine, FiscalYear
from apps.loans.models import Loan, Payment, RepaymentSchedule

logger = logging.getLogger(__name__)


class FinancialReportingService:
    """
    Financial Reporting Service for Accounting Reports
    
    Provides methods to generate standard financial reports:
    - Trial Balance: Verify accounting equation
    - Profit & Loss (Income Statement): Revenue and expenses
    - Balance Sheet: Assets, Liabilities, and Equity
    
    All reports use posted journal entries only (status='POSTED').
    """
    
    @staticmethod
    def generate_trial_balance(
        fiscal_year: FiscalYear,
        as_of_date: Optional[date] = None,
        include_inactive: bool = False
    ) -> Dict:
        """
        Generate Trial Balance Report
        
        Lists all accounts with their debit and credit balances, verifying
        that total debits equal total credits (fundamental accounting equation).
        
        Args:
            fiscal_year: FiscalYear to report on
            as_of_date: Calculate balances as of this date (defaults to fiscal year end)
            include_inactive: Include inactive accounts in the report
            
        Returns:
            Dict containing:
                - accounts: List of accounts with balances
                - totals: Total debits and credits
                - is_balanced: Whether debits equal credits
                - metadata: Report parameters
                
        Example:
            {
                'accounts': [
                    {
                        'code': '1000',
                        'name': 'Cash',
                        'account_type': 'Asset',
                        'debit_balance': Decimal('50000.00'),
                        'credit_balance': Decimal('0.00'),
                        'net_balance': Decimal('50000.00')
                    },
                    ...
                ],
                'totals': {
                    'total_debit': Decimal('150000.00'),
                    'total_credit': Decimal('150000.00'),
                    'difference': Decimal('0.00')
                },
                'is_balanced': True,
                'metadata': {
                    'fiscal_year': '2024',
                    'as_of_date': '2024-12-31',
                    'generated_at': '2024-01-15 10:30:00'
                }
            }
        """
        try:
            logger.info(f"Generating Trial Balance for {fiscal_year.name} as of {as_of_date}")
            
            # Default to fiscal year end date
            if as_of_date is None:
                as_of_date = fiscal_year.end_date
            
            # Validate date is within fiscal year
            if not (fiscal_year.start_date <= as_of_date <= fiscal_year.end_date):
                raise ValueError(
                    f"as_of_date must be within fiscal year "
                    f"({fiscal_year.start_date} to {fiscal_year.end_date})"
                )
            
            # Get all journal entry lines for posted entries up to the date
            lines_query = JournalEntryLine.objects.filter(
                journal_entry__fiscal_year=fiscal_year,
                journal_entry__date__lte=as_of_date,
                journal_entry__status='POSTED'
            )
            
            # Aggregate by account
            account_balances = lines_query.values(
                'account',
                'account__code',
                'account__name',
                'account__account_type__name',
                'account__account_type__normal_balance',
                'account__is_active'
            ).annotate(
                total_debit=Coalesce(Sum('debit_amount'), Decimal('0.00')),
                total_credit=Coalesce(Sum('credit_amount'), Decimal('0.00'))
            ).order_by('account__code')
            
            # Filter inactive accounts if requested
            if not include_inactive:
                account_balances = account_balances.filter(account__is_active=True)
            
            # Process accounts and calculate net balances
            accounts = []
            total_debit = Decimal('0.00')
            total_credit = Decimal('0.00')
            
            for acc in account_balances:
                debit_balance = acc['total_debit']
                credit_balance = acc['total_credit']
                
                # Calculate net balance based on normal balance type
                if acc['account__account_type__normal_balance'] == 'DEBIT':
                    net_balance = debit_balance - credit_balance
                    display_debit = net_balance if net_balance > 0 else Decimal('0.00')
                    display_credit = abs(net_balance) if net_balance < 0 else Decimal('0.00')
                else:
                    net_balance = credit_balance - debit_balance
                    display_credit = net_balance if net_balance > 0 else Decimal('0.00')
                    display_debit = abs(net_balance) if net_balance < 0 else Decimal('0.00')
                
                # Add to running totals
                total_debit += display_debit
                total_credit += display_credit
                
                # Only include accounts with non-zero balances
                if net_balance != Decimal('0.00'):
                    accounts.append({
                        'account_id': acc['account'],
                        'code': acc['account__code'],
                        'name': acc['account__name'],
                        'account_type': acc['account__account_type__name'],
                        'debit_balance': display_debit,
                        'credit_balance': display_credit,
                        'net_balance': net_balance,
                        'is_active': acc['account__is_active']
                    })
            
            # Calculate totals and check if balanced
            difference = total_debit - total_credit
            is_balanced = difference == Decimal('0.00')
            
            result = {
                'accounts': accounts,
                'totals': {
                    'total_debit': total_debit,
                    'total_credit': total_credit,
                    'difference': difference
                },
                'is_balanced': is_balanced,
                'metadata': {
                    'fiscal_year': fiscal_year.name,
                    'as_of_date': as_of_date.isoformat(),
                    'generated_at': timezone.now().isoformat(),
                    'include_inactive': include_inactive
                }
            }
            
            logger.info(
                f"Trial Balance generated: {len(accounts)} accounts, "
                f"Balanced: {is_balanced}, Difference: {difference}"
            )
            
            return result
            
        except Exception as e:
            logger.error(f"Error generating Trial Balance: {str(e)}", exc_info=True)
            raise
    
    @staticmethod
    def generate_profit_loss(
        fiscal_year: FiscalYear,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        group_by_account_type: bool = True
    ) -> Dict:
        """
        Generate Profit & Loss (Income Statement) Report
        
        Calculates revenue and expenses for a period to determine net income.
        Formula: Net Income = Total Revenue - Total Expenses
        
        Args:
            fiscal_year: FiscalYear to report on
            start_date: Start of reporting period (defaults to fiscal year start)
            end_date: End of reporting period (defaults to fiscal year end)
            group_by_account_type: Group accounts by type for summary
            
        Returns:
            Dict containing:
                - revenue: List of income accounts and totals
                - expenses: List of expense accounts and totals
                - net_income: Calculated profit or loss
                - metadata: Report parameters
                
        Example:
            {
                'revenue': {
                    'accounts': [
                        {
                            'code': '4000',
                            'name': 'Interest Income',
                            'amount': Decimal('45000.00')
                        },
                        ...
                    ],
                    'total': Decimal('120000.00')
                },
                'expenses': {
                    'accounts': [
                        {
                            'code': '5000',
                            'name': 'Salaries',
                            'amount': Decimal('35000.00')
                        },
                        ...
                    ],
                    'total': Decimal('80000.00')
                },
                'net_income': Decimal('40000.00'),
                'metadata': {...}
            }
        """
        try:
            logger.info(f"Generating P&L for {fiscal_year.name}")
            
            # Default to fiscal year dates
            if start_date is None:
                start_date = fiscal_year.start_date
            if end_date is None:
                end_date = fiscal_year.end_date
            
            # Validate dates
            if start_date > end_date:
                raise ValueError("start_date cannot be after end_date")
            
            if not (fiscal_year.start_date <= start_date <= fiscal_year.end_date):
                raise ValueError("start_date must be within fiscal year")
            
            if not (fiscal_year.start_date <= end_date <= fiscal_year.end_date):
                raise ValueError("end_date must be within fiscal year")
            
            # Get income and expense account types
            income_type = AccountType.objects.get(name='INCOME')
            expense_type = AccountType.objects.get(name='EXPENSE')
            
            # Query for income accounts
            income_accounts = JournalEntryLine.objects.filter(
                journal_entry__fiscal_year=fiscal_year,
                journal_entry__date__gte=start_date,
                journal_entry__date__lte=end_date,
                journal_entry__status='POSTED',
                account__account_type=income_type,
                account__is_active=True
            ).values(
                'account__code',
                'account__name'
            ).annotate(
                total_debit=Coalesce(Sum('debit_amount'), Decimal('0.00')),
                total_credit=Coalesce(Sum('credit_amount'), Decimal('0.00'))
            ).order_by('account__code')
            
            # Query for expense accounts
            expense_accounts = JournalEntryLine.objects.filter(
                journal_entry__fiscal_year=fiscal_year,
                journal_entry__date__gte=start_date,
                journal_entry__date__lte=end_date,
                journal_entry__status='POSTED',
                account__account_type=expense_type,
                account__is_active=True
            ).values(
                'account__code',
                'account__name'
            ).annotate(
                total_debit=Coalesce(Sum('debit_amount'), Decimal('0.00')),
                total_credit=Coalesce(Sum('credit_amount'), Decimal('0.00'))
            ).order_by('account__code')
            
            # Process income accounts (credit increases, debit decreases)
            revenue_accounts = []
            total_revenue = Decimal('0.00')
            
            for acc in income_accounts:
                # For income accounts, credit increases balance
                net_amount = acc['total_credit'] - acc['total_debit']
                if net_amount > 0:
                    revenue_accounts.append({
                        'code': acc['account__code'],
                        'name': acc['account__name'],
                        'amount': net_amount
                    })
                    total_revenue += net_amount
            
            # Process expense accounts (debit increases, credit decreases)
            expense_account_list = []
            total_expenses = Decimal('0.00')
            
            for acc in expense_accounts:
                # For expense accounts, debit increases balance
                net_amount = acc['total_debit'] - acc['total_credit']
                if net_amount > 0:
                    expense_account_list.append({
                        'code': acc['account__code'],
                        'name': acc['account__name'],
                        'amount': net_amount
                    })
                    total_expenses += net_amount
            
            # Calculate net income
            net_income = total_revenue - total_expenses
            
            result = {
                'revenue': {
                    'accounts': revenue_accounts,
                    'total': total_revenue
                },
                'expenses': {
                    'accounts': expense_account_list,
                    'total': total_expenses
                },
                'gross_profit': total_revenue,  # For simplicity, treating all revenue as gross
                'operating_expenses': total_expenses,
                'net_income': net_income,
                'net_income_percentage': (net_income / total_revenue * 100) if total_revenue > 0 else Decimal('0.00'),
                'metadata': {
                    'fiscal_year': fiscal_year.name,
                    'start_date': start_date.isoformat(),
                    'end_date': end_date.isoformat(),
                    'generated_at': timezone.now().isoformat(),
                    'period_days': (end_date - start_date).days + 1
                }
            }
            
            logger.info(
                f"P&L generated: Revenue {total_revenue}, "
                f"Expenses {total_expenses}, Net Income {net_income}"
            )
            
            return result
            
        except Exception as e:
            logger.error(f"Error generating P&L: {str(e)}", exc_info=True)
            raise
    
    @staticmethod
    def generate_balance_sheet(
        fiscal_year: FiscalYear,
        as_of_date: Optional[date] = None
    ) -> Dict:
        """
        Generate Balance Sheet Report
        
        Shows financial position at a specific point in time.
        Formula: Assets = Liabilities + Equity
        
        Args:
            fiscal_year: FiscalYear to report on
            as_of_date: Date for balance sheet (defaults to fiscal year end)
            
        Returns:
            Dict containing:
                - assets: Asset accounts and totals
                - liabilities: Liability accounts and totals
                - equity: Equity accounts and totals
                - is_balanced: Whether accounting equation holds
                - metadata: Report parameters
                
        Example:
            {
                'assets': {
                    'current_assets': [...],
                    'non_current_assets': [...],
                    'total': Decimal('500000.00')
                },
                'liabilities': {
                    'current_liabilities': [...],
                    'non_current_liabilities': [...],
                    'total': Decimal('300000.00')
                },
                'equity': {
                    'accounts': [...],
                    'total': Decimal('200000.00')
                },
                'is_balanced': True,
                'metadata': {...}
            }
        """
        try:
            logger.info(f"Generating Balance Sheet for {fiscal_year.name} as of {as_of_date}")
            
            # Default to fiscal year end date
            if as_of_date is None:
                as_of_date = fiscal_year.end_date
            
            # Validate date
            if not (fiscal_year.start_date <= as_of_date <= fiscal_year.end_date):
                raise ValueError(
                    f"as_of_date must be within fiscal year "
                    f"({fiscal_year.start_date} to {fiscal_year.end_date})"
                )
            
            # Get account types
            asset_type = AccountType.objects.get(name='ASSET')
            liability_type = AccountType.objects.get(name='LIABILITY')
            equity_type = AccountType.objects.get(name='EQUITY')
            
            # Helper function to get account balances by type
            def get_balances_by_type(account_type):
                return JournalEntryLine.objects.filter(
                    journal_entry__fiscal_year=fiscal_year,
                    journal_entry__date__lte=as_of_date,
                    journal_entry__status='POSTED',
                    account__account_type=account_type,
                    account__is_active=True
                ).values(
                    'account__code',
                    'account__name',
                    'account__account_type__normal_balance'
                ).annotate(
                    total_debit=Coalesce(Sum('debit_amount'), Decimal('0.00')),
                    total_credit=Coalesce(Sum('credit_amount'), Decimal('0.00'))
                ).order_by('account__code')
            
            # Get assets (debit balance)
            asset_accounts = []
            total_assets = Decimal('0.00')
            
            for acc in get_balances_by_type(asset_type):
                net_amount = acc['total_debit'] - acc['total_credit']
                if net_amount > 0:
                    asset_accounts.append({
                        'code': acc['account__code'],
                        'name': acc['account__name'],
                        'amount': net_amount
                    })
                    total_assets += net_amount
            
            # Get liabilities (credit balance)
            liability_accounts = []
            total_liabilities = Decimal('0.00')
            
            for acc in get_balances_by_type(liability_type):
                net_amount = acc['total_credit'] - acc['total_debit']
                if net_amount > 0:
                    liability_accounts.append({
                        'code': acc['account__code'],
                        'name': acc['account__name'],
                        'amount': net_amount
                    })
                    total_liabilities += net_amount
            
            # Get equity (credit balance)
            equity_accounts = []
            total_equity = Decimal('0.00')
            
            for acc in get_balances_by_type(equity_type):
                net_amount = acc['total_credit'] - acc['total_debit']
                if net_amount > 0:
                    equity_accounts.append({
                        'code': acc['account__code'],
                        'name': acc['account__name'],
                        'amount': net_amount
                    })
                    total_equity += net_amount
            
            # Check accounting equation: Assets = Liabilities + Equity
            liabilities_plus_equity = total_liabilities + total_equity
            difference = total_assets - liabilities_plus_equity
            is_balanced = abs(difference) < Decimal('0.01')  # Allow tiny rounding differences
            
            result = {
                'assets': {
                    'current_assets': asset_accounts,  # TODO: Separate current vs non-current
                    'non_current_assets': [],
                    'total': total_assets
                },
                'liabilities': {
                    'current_liabilities': liability_accounts,  # TODO: Separate current vs non-current
                    'non_current_liabilities': [],
                    'total': total_liabilities
                },
                'equity': {
                    'accounts': equity_accounts,
                    'total': total_equity
                },
                'total_liabilities_and_equity': liabilities_plus_equity,
                'is_balanced': is_balanced,
                'difference': difference,
                'metadata': {
                    'fiscal_year': fiscal_year.name,
                    'as_of_date': as_of_date.isoformat(),
                    'generated_at': timezone.now().isoformat()
                }
            }
            
            logger.info(
                f"Balance Sheet generated: Assets {total_assets}, "
                f"Liabilities {total_liabilities}, Equity {total_equity}, "
                f"Balanced: {is_balanced}"
            )
            
            return result
            
        except Exception as e:
            logger.error(f"Error generating Balance Sheet: {str(e)}", exc_info=True)
            raise


class LoanReportingService:
    """
    Loan Portfolio Reporting Service
    
    Provides methods to analyze loan portfolio health:
    - Aged Receivables: Loans categorized by overdue period
    - NPL Report: Non-Performing Loan analysis
    - Portfolio at Risk (PAR): Loans at risk of default
    
    All calculations use efficient PostgreSQL queries with aggregations.
    """
    
    @staticmethod
    def generate_aged_receivables(
        as_of_date: Optional[date] = None,
        aging_buckets: Optional[List[Tuple[int, int]]] = None
    ) -> Dict:
        """
        Generate Aged Receivables Report
        
        Categorizes outstanding loans by how long they are overdue.
        Helps identify collection issues and prioritize follow-ups.
        
        Args:
            as_of_date: Date for aging analysis (defaults to today)
            aging_buckets: Custom aging periods as (min_days, max_days) tuples
                          Defaults to: Current, 1-30, 31-60, 61-90, 90+
            
        Returns:
            Dict containing:
                - aging_summary: Count and amount by aging bucket
                - loans_by_aging: Detailed loan list by bucket
                - totals: Overall portfolio statistics
                - metadata: Report parameters
                
        Example:
            {
                'aging_summary': [
                    {
                        'bucket': 'Current',
                        'min_days': 0,
                        'max_days': 0,
                        'loan_count': 150,
                        'principal_outstanding': Decimal('450000.00'),
                        'total_outstanding': Decimal('520000.00')
                    },
                    {
                        'bucket': '1-30 Days',
                        'min_days': 1,
                        'max_days': 30,
                        'loan_count': 25,
                        'principal_outstanding': Decimal('75000.00'),
                        'total_outstanding': Decimal('85000.00')
                    },
                    ...
                ],
                'totals': {
                    'total_loans': 200,
                    'total_principal': Decimal('600000.00'),
                    'total_outstanding': Decimal('720000.00')
                },
                'metadata': {...}
            }
        """
        try:
            logger.info(f"Generating Aged Receivables as of {as_of_date}")
            
            # Default to today
            if as_of_date is None:
                as_of_date = date.today()
            
            # Default aging buckets: Current, 1-30, 31-60, 61-90, 90+
            if aging_buckets is None:
                aging_buckets = [
                    (0, 0, 'Current'),
                    (1, 30, '1-30 Days'),
                    (31, 60, '31-60 Days'),
                    (61, 90, '61-90 Days'),
                    (91, 999999, '90+ Days'),
                ]
            
            # Get all active loans with balances
            loans = Loan.objects.filter(
                status__in=['ACTIVE', 'OVERDUE', 'NPL']
            ).select_related(
                'customer',
                'loan_product',
                'loan_officer'
            ).annotate(
                customer_name=F('customer__first_name')  # + ' ' + F('customer__last_name')
            )
            
            # Categorize loans by aging bucket
            aging_summary = []
            loans_by_aging = {}
            
            total_loans = 0
            total_principal = Decimal('0.00')
            total_outstanding = Decimal('0.00')
            
            for min_days, max_days, bucket_name in aging_buckets:
                # Filter loans in this aging bucket
                if max_days == 999999:
                    bucket_loans = loans.filter(days_overdue__gte=min_days)
                else:
                    bucket_loans = loans.filter(
                        days_overdue__gte=min_days,
                        days_overdue__lte=max_days
                    )
                
                # Calculate aggregates
                bucket_stats = bucket_loans.aggregate(
                    count=Count('id'),
                    principal=Coalesce(Sum('outstanding_principal'), Decimal('0.00')),
                    outstanding=Coalesce(Sum('total_outstanding'), Decimal('0.00'))
                )
                
                loan_count = bucket_stats['count']
                principal_sum = bucket_stats['principal']
                outstanding_sum = bucket_stats['outstanding']
                
                # Add to summary
                aging_summary.append({
                    'bucket': bucket_name,
                    'min_days': min_days,
                    'max_days': max_days if max_days < 999999 else None,
                    'loan_count': loan_count,
                    'principal_outstanding': principal_sum,
                    'total_outstanding': outstanding_sum,
                    'percentage_of_portfolio': Decimal('0.00')  # Calculate after totals
                })
                
                # Get detailed loan list for this bucket (limit to 100 per bucket for performance)
                loans_by_aging[bucket_name] = list(
                    bucket_loans.values(
                        'loan_number',
                        'customer__first_name',
                        'customer__last_name',
                        'principal_amount',
                        'outstanding_principal',
                        'total_outstanding',
                        'days_overdue',
                        'disbursement_date',
                        'loan_officer__email'
                    )[:100]
                )
                
                # Add to totals
                total_loans += loan_count
                total_principal += principal_sum
                total_outstanding += outstanding_sum
            
            # Calculate percentages
            for bucket in aging_summary:
                if total_outstanding > 0:
                    bucket['percentage_of_portfolio'] = (
                        bucket['total_outstanding'] / total_outstanding * 100
                    ).quantize(Decimal('0.01'))
            
            result = {
                'aging_summary': aging_summary,
                'loans_by_aging': loans_by_aging,
                'totals': {
                    'total_loans': total_loans,
                    'total_principal': total_principal,
                    'total_outstanding': total_outstanding
                },
                'metadata': {
                    'as_of_date': as_of_date.isoformat(),
                    'generated_at': timezone.now().isoformat(),
                    'aging_buckets_count': len(aging_buckets)
                }
            }
            
            logger.info(
                f"Aged Receivables generated: {total_loans} loans, "
                f"Outstanding: {total_outstanding}"
            )
            
            return result
            
        except Exception as e:
            logger.error(f"Error generating Aged Receivables: {str(e)}", exc_info=True)
            raise
    
    @staticmethod
    def generate_npl_report(
        as_of_date: Optional[date] = None,
        threshold_days: int = 90
    ) -> Dict:
        """
        Generate Non-Performing Loans (NPL) Report
        
        Identifies loans that have been in default for an extended period.
        NPL is typically defined as loans overdue > 90 days.
        
        Args:
            as_of_date: Date for analysis (defaults to today)
            threshold_days: Days overdue to classify as NPL (default: 90)
            
        Returns:
            Dict containing:
                - npl_loans: List of non-performing loans
                - npl_summary: NPL statistics
                - portfolio_summary: Overall portfolio statistics
                - npl_ratio: NPL Amount / Total Portfolio
                - metadata: Report parameters
                
        Example:
            {
                'npl_loans': [
                    {
                        'loan_number': 'LOAN-001',
                        'customer_name': 'John Doe',
                        'principal_amount': Decimal('50000.00'),
                        'outstanding_balance': Decimal('35000.00'),
                        'days_overdue': 120,
                        'loan_officer': 'officer1'
                    },
                    ...
                ],
                'npl_summary': {
                    'npl_count': 12,
                    'npl_principal': Decimal('450000.00'),
                    'npl_outstanding': Decimal('380000.00')
                },
                'portfolio_summary': {
                    'total_loans': 200,
                    'total_principal': Decimal('5000000.00'),
                    'total_outstanding': Decimal('4200000.00')
                },
                'npl_ratio': Decimal('9.05'),  # percentage
                'metadata': {...}
            }
        """
        try:
            logger.info(f"Generating NPL Report as of {as_of_date}, threshold: {threshold_days} days")
            
            # Default to today
            if as_of_date is None:
                as_of_date = date.today()
            
            # Get all active loans (not closed or written off)
            active_loans = Loan.objects.filter(
                status__in=['ACTIVE', 'OVERDUE', 'NPL', 'PENDING_DISBURSEMENT']
            )
            
            # Identify NPL loans (overdue > threshold OR status = NPL)
            npl_loans = active_loans.filter(
                Q(days_overdue__gte=threshold_days) | Q(status='NPL')
            ).select_related(
                'customer',
                'loan_product',
                'loan_officer'
            ).values(
                'loan_number',
                'customer__first_name',
                'customer__last_name',
                'customer__phone_number',
                'principal_amount',
                'outstanding_principal',
                'outstanding_interest',
                'outstanding_fees',
                'outstanding_penalties',
                'total_outstanding',
                'days_overdue',
                'disbursement_date',
                'loan_officer__email',
                'loan_product__name'
            )
            
            # Calculate NPL statistics
            npl_stats = active_loans.filter(
                Q(days_overdue__gte=threshold_days) | Q(status='NPL')
            ).aggregate(
                count=Count('id'),
                principal=Coalesce(Sum('outstanding_principal'), Decimal('0.00')),
                outstanding=Coalesce(Sum('total_outstanding'), Decimal('0.00'))
            )
            
            # Calculate portfolio statistics
            portfolio_stats = active_loans.aggregate(
                count=Count('id'),
                principal=Coalesce(Sum('outstanding_principal'), Decimal('0.00')),
                outstanding=Coalesce(Sum('total_outstanding'), Decimal('0.00'))
            )
            
            # Calculate NPL ratio
            npl_outstanding = npl_stats['outstanding']
            portfolio_outstanding = portfolio_stats['outstanding']
            
            npl_ratio = (
                (npl_outstanding / portfolio_outstanding * 100)
                if portfolio_outstanding > 0
                else Decimal('0.00')
            ).quantize(Decimal('0.01'))
            
            result = {
                'npl_loans': list(npl_loans),
                'npl_summary': {
                    'npl_count': npl_stats['count'],
                    'npl_principal': npl_stats['principal'],
                    'npl_outstanding': npl_outstanding
                },
                'portfolio_summary': {
                    'total_loans': portfolio_stats['count'],
                    'total_principal': portfolio_stats['principal'],
                    'total_outstanding': portfolio_outstanding
                },
                'npl_ratio': npl_ratio,
                'metadata': {
                    'as_of_date': as_of_date.isoformat(),
                    'threshold_days': threshold_days,
                    'generated_at': timezone.now().isoformat()
                }
            }
            
            logger.info(
                f"NPL Report generated: {npl_stats['count']} NPL loans "
                f"({npl_outstanding} outstanding), NPL Ratio: {npl_ratio}%"
            )
            
            return result
            
        except Exception as e:
            logger.error(f"Error generating NPL Report: {str(e)}", exc_info=True)
            raise
    
    @staticmethod
    def calculate_par(
        as_of_date: Optional[date] = None,
        days: Optional[List[int]] = None
    ) -> Dict:
        """
        Calculate Portfolio at Risk (PAR)
        
        PAR measures the portion of the portfolio that is at risk due to late payments.
        PAR is calculated for different overdue thresholds (e.g., PAR 1, PAR 7, PAR 30, PAR 90).
        
        Formula:
            PAR X = (Outstanding Balance of Loans > X days overdue) / (Total Outstanding Portfolio)
        
        Args:
            as_of_date: Date for calculation (defaults to today)
            days: List of day thresholds (default: [1, 7, 30, 90])
            
        Returns:
            Dict containing PAR calculations for each threshold:
                - par_X_amount: Total outstanding for loans overdue > X days
                - par_X_ratio: Percentage of portfolio at risk
                - par_X_loan_count: Number of loans overdue > X days
                
        Example:
            {
                'par_calculations': [
                    {
                        'days': 1,
                        'par_name': 'PAR 1',
                        'amount': Decimal('150000.00'),
                        'ratio': Decimal('3.57'),  # percentage
                        'loan_count': 30
                    },
                    {
                        'days': 30,
                        'par_name': 'PAR 30',
                        'amount': Decimal('75000.00'),
                        'ratio': Decimal('1.79'),
                        'loan_count': 12
                    },
                    ...
                ],
                'portfolio_total': Decimal('4200000.00'),
                'active_loan_count': 200,
                'metadata': {...}
            }
        """
        try:
            logger.info(f"Calculating PAR as of {as_of_date}")
            
            # Default to today
            if as_of_date is None:
                as_of_date = date.today()
            
            # Default PAR thresholds: 1, 7, 30, 90 days
            if days is None:
                days = [1, 7, 30, 90]
            
            # Get active portfolio statistics
            active_loans = Loan.objects.filter(
                status__in=['ACTIVE', 'OVERDUE', 'NPL']
            )
            
            portfolio_stats = active_loans.aggregate(
                total_outstanding=Coalesce(Sum('total_outstanding'), Decimal('0.00')),
                loan_count=Count('id')
            )
            
            portfolio_total = portfolio_stats['total_outstanding']
            total_loans = portfolio_stats['loan_count']
            
            # Calculate PAR for each threshold
            par_calculations = []
            
            for day_threshold in days:
                # Get loans overdue > threshold
                overdue_loans = active_loans.filter(
                    days_overdue__gt=day_threshold
                )
                
                par_stats = overdue_loans.aggregate(
                    amount=Coalesce(Sum('total_outstanding'), Decimal('0.00')),
                    count=Count('id')
                )
                
                par_amount = par_stats['amount']
                par_count = par_stats['count']
                
                # Calculate PAR ratio
                par_ratio = (
                    (par_amount / portfolio_total * 100)
                    if portfolio_total > 0
                    else Decimal('0.00')
                ).quantize(Decimal('0.01'))
                
                par_calculations.append({
                    'days': day_threshold,
                    'par_name': f'PAR {day_threshold}',
                    'amount': par_amount,
                    'ratio': par_ratio,
                    'loan_count': par_count,
                    'loan_percentage': (
                        (Decimal(par_count) / Decimal(total_loans) * 100)
                        if total_loans > 0
                        else Decimal('0.00')
                    ).quantize(Decimal('0.01'))
                })
            
            result = {
                'par_calculations': par_calculations,
                'portfolio_total': portfolio_total,
                'active_loan_count': total_loans,
                'metadata': {
                    'as_of_date': as_of_date.isoformat(),
                    'generated_at': timezone.now().isoformat(),
                    'thresholds': days
                }
            }
            
            logger.info(
                f"PAR calculated: Portfolio {portfolio_total}, "
                f"Thresholds: {days}"
            )
            
            return result
            
        except Exception as e:
            logger.error(f"Error calculating PAR: {str(e)}", exc_info=True)
            raise
    
    @staticmethod
    def generate_loan_portfolio_summary(
        as_of_date: Optional[date] = None,
        group_by_product: bool = False,
        group_by_officer: bool = False
    ) -> Dict:
        """
        Generate Comprehensive Loan Portfolio Summary
        
        Provides an overview of the entire loan portfolio with key metrics.
        
        Args:
            as_of_date: Date for analysis (defaults to today)
            group_by_product: Include breakdown by loan product
            group_by_officer: Include breakdown by loan officer
            
        Returns:
            Dict containing:
                - portfolio_overview: Overall portfolio statistics
                - by_status: Breakdown by loan status
                - by_product: Breakdown by product (if requested)
                - by_officer: Breakdown by officer (if requested)
                - metadata: Report parameters
        """
        try:
            logger.info(f"Generating Portfolio Summary as of {as_of_date}")
            
            if as_of_date is None:
                as_of_date = date.today()
            
            # Overall portfolio statistics
            all_loans = Loan.objects.all()
            
            portfolio_overview = all_loans.aggregate(
                total_loans=Count('id'),
                total_principal_disbursed=Coalesce(Sum('principal_amount'), Decimal('0.00')),
                total_outstanding=Coalesce(Sum('total_outstanding'), Decimal('0.00')),
                total_paid=Coalesce(Sum('total_paid'), Decimal('0.00'))
            )
            
            # Breakdown by status
            by_status = list(
                all_loans.values('status').annotate(
                    loan_count=Count('id'),
                    principal=Coalesce(Sum('principal_amount'), Decimal('0.00')),
                    outstanding=Coalesce(Sum('total_outstanding'), Decimal('0.00'))
                ).order_by('-outstanding')
            )
            
            result = {
                'portfolio_overview': portfolio_overview,
                'by_status': by_status,
                'metadata': {
                    'as_of_date': as_of_date.isoformat(),
                    'generated_at': timezone.now().isoformat()
                }
            }
            
            # Optional groupings
            if group_by_product:
                result['by_product'] = list(
                    all_loans.values(
                        'loan_product__name',
                        'loan_product__code'
                    ).annotate(
                        loan_count=Count('id'),
                        principal=Coalesce(Sum('principal_amount'), Decimal('0.00')),
                        outstanding=Coalesce(Sum('total_outstanding'), Decimal('0.00'))
                    ).order_by('-outstanding')
                )
            
            if group_by_officer:
                result['by_officer'] = list(
                    all_loans.values(
                        'loan_officer__email',
                        'loan_officer__first_name',
                        'loan_officer__last_name'
                    ).annotate(
                        loan_count=Count('id'),
                        principal=Coalesce(Sum('principal_amount'), Decimal('0.00')),
                        outstanding=Coalesce(Sum('total_outstanding'), Decimal('0.00'))
                    ).order_by('-outstanding')
                )
            
            logger.info(
                f"Portfolio Summary generated: {portfolio_overview['total_loans']} loans, "
                f"Outstanding: {portfolio_overview['total_outstanding']}"
            )
            
            return result
            
        except Exception as e:
            logger.error(f"Error generating Portfolio Summary: {str(e)}", exc_info=True)
            raise
