from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from apps.accounting.models import AccountType, Account, FiscalYear
from datetime import date
from decimal import Decimal

User = get_user_model()

class Command(BaseCommand):
    help = 'Create initial test data for Alba Capital ERP'

    def handle(self, *args, **options):
        self.stdout.write('')
        self.stdout.write('='*70)
        self.stdout.write('  CREATING TEST DATA FOR ALBA CAPITAL ERP')
        self.stdout.write('='*70)
        self.stdout.write('')
        
        # Get or create user
        user = User.objects.filter(is_superuser=True).first()
        if not user:
            self.stdout.write(self.style.ERROR('❌ No superuser found!'))
            return
        
        # Create account types
        account_types = [
            ('ASSET', 'DEBIT', 'Assets - Economic resources'),
            ('LIABILITY', 'CREDIT', 'Liabilities - Obligations'),
            ('EQUITY', 'CREDIT', 'Equity - Ownership interest'),
            ('INCOME', 'CREDIT', 'Revenue - Income from operations'),
            ('EXPENSE', 'DEBIT', 'Expenses - Costs of operations'),
        ]
        
        self.stdout.write('Creating Account Types...')
        for name, normal_balance, desc in account_types:
            obj, created = AccountType.objects.get_or_create(
                name=name,
                defaults={'normal_balance': normal_balance, 'description': desc}
            )
            if created:
                self.stdout.write(self.style.SUCCESS(f'  ✅ Created: {name}'))
            else:
                self.stdout.write(f'  ℹ️  Exists: {name}')
        
        # Get fiscal year
        fiscal_year = FiscalYear.objects.filter(is_active=True).first()
        if not fiscal_year:
            self.stdout.write(self.style.WARNING('⚠️  No active fiscal year, skipping accounts'))
            return
        
        # Create sample accounts
        self.stdout.write('')
        self.stdout.write('Creating Sample Accounts...')
        
        asset_type = AccountType.objects.get(name='ASSET')
        liability_type = AccountType.objects.get(name='LIABILITY')
        equity_type = AccountType.objects.get(name='EQUITY')
        income_type = AccountType.objects.get(name='INCOME')
        expense_type = AccountType.objects.get(name='EXPENSE')
        
        accounts = [
            ('1000', 'Cash at Bank', asset_type),
            ('1100', 'Accounts Receivable', asset_type),
            ('1200', 'Loan Portfolio', asset_type),
            ('2000', 'Accounts Payable', liability_type),
            ('2100', 'Deposits from Investors', liability_type),
            ('3000', 'Share Capital', equity_type),
            ('3100', 'Retained Earnings', equity_type),
            ('4000', 'Interest Income - Loans', income_type),
            ('4100', 'Service Fees Income', income_type),
            ('5000', 'Operating Expenses', expense_type),
            ('5100', 'Staff Salaries', expense_type),
            ('5200', 'Loan Loss Provision', expense_type),
        ]
        
        for code, name, acc_type in accounts:
            obj, created = Account.objects.get_or_create(
                code=code,
                defaults={
                    'name': name,
                    'account_type': acc_type,
                    'created_by': user,
                    'is_active': True
                }
            )
            if created:
                self.stdout.write(self.style.SUCCESS(f'  ✅ Created: {code} - {name}'))
            else:
                self.stdout.write(f'  ℹ️  Exists: {code} - {name}')
        
        self.stdout.write('')
        self.stdout.write('='*70)
        self.stdout.write(self.style.SUCCESS('  ✅ TEST DATA CREATED SUCCESSFULLY!'))
        self.stdout.write('='*70)
        self.stdout.write('')
        
        # Show summary
        self.stdout.write('DATABASE SUMMARY:')
        self.stdout.write(f'  Users: {User.objects.count()}')
        self.stdout.write(f'  Fiscal Years: {FiscalYear.objects.count()}')
        self.stdout.write(f'  Account Types: {AccountType.objects.count()}')
        self.stdout.write(f'  Accounts: {Account.objects.count()}')
        self.stdout.write('')
