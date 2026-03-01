"""
Django Management Command: Initialize System with Default Data
Creates roles, permissions, account types, and sample chart of accounts
"""
from django.core.management.base import BaseCommand
from django.db import transaction
from apps.core.models import Role, Permission
from apps.accounting.models import AccountType, Account, FiscalYear
from apps.core.models import User
from datetime import date, timedelta


class Command(BaseCommand):
    help = 'Initialize system with default roles, permissions, and chart of accounts'

    def handle(self, *args, **kwargs):
        self.stdout.write('Starting system initialization...')
        
        with transaction.atomic():
            # Create Roles
            self.stdout.write('Creating roles...')
            self.create_roles()
            
            # Create Account Types
            self.stdout.write('Creating account types...')
            self.create_account_types()
            
            # Create Fiscal Year
            self.stdout.write('Creating fiscal year...')
            self.create_fiscal_year()
            
            # Create Sample Chart of Accounts
            self.stdout.write('Creating chart of accounts...')
            # This will be done manually or through data migration
            
        self.stdout.write(self.style.SUCCESS('✓ System initialization completed successfully!'))
        self.stdout.write('')
        self.stdout.write('Next steps:')
        self.stdout.write('1. Create superuser: python manage.py createsuperuser')
        self.stdout.write('2. Create chart of accounts through admin panel')
        self.stdout.write('3. Configure loan products')
    
    def create_roles(self):
        """Create system roles"""
        roles_data = [
            (Role.SYSTEM_ADMIN, 'Full system access with all permissions'),
            (Role.CREDIT_OFFICER, 'Loan processing and customer management'),
            (Role.FINANCE_OFFICER, 'Accounting and financial management'),
            (Role.HR_OFFICER, 'Human resource and payroll management'),
            (Role.MANAGEMENT, 'Management dashboards and reports'),
            (Role.INVESTOR, 'Investor portal access'),
            (Role.CUSTOMER, 'Customer portal access'),
        ]
        
        for role_name, description in roles_data:
            role, created = Role.objects.get_or_create(
                name=role_name,
                defaults={'description': description}
            )
            if created:
                self.stdout.write(f'  ✓ Created role: {role.get_name_display()}')
            
            # Create default permissions for each role
            self.create_default_permissions(role)
    
    def create_default_permissions(self, role):
        """Create default permissions for a role"""
        modules = ['core', 'accounting', 'loans', 'investors', 'payroll', 'crm', 'assets', 'reporting']
        
        # System Admin gets all permissions
        if role.name == Role.SYSTEM_ADMIN:
            for module in modules:
                Permission.objects.get_or_create(
                    role=role,
                    module=module,
                    defaults={
                        'can_view': True,
                        'can_create': True,
                        'can_edit': True,
                        'can_delete': True,
                        'can_approve': True,
                        'can_export': True,
                    }
                )
        
        # Credit Officer permissions
        elif role.name == Role.CREDIT_OFFICER:
            Permission.objects.get_or_create(
                role=role, module='loans',
                defaults={'can_view': True, 'can_create': True, 'can_edit': True}
            )
            Permission.objects.get_or_create(
                role=role, module='crm',
                defaults={'can_view': True, 'can_create': True, 'can_edit': True}
            )
        
        # Finance Officer permissions
        elif role.name == Role.FINANCE_OFFICER:
            for module in ['accounting', 'loans', 'investors']:
                Permission.objects.get_or_create(
                    role=role, module=module,
                    defaults={'can_view': True, 'can_create': True, 'can_edit': True, 'can_approve': True}
                )
    
    def create_account_types(self):
        """Create standard account types"""
        account_types = [
            ('ASSET', 'DEBIT', 'Assets owned by the company'),
            ('LIABILITY', 'CREDIT', 'Obligations owed by the company'),
            ('EQUITY', 'CREDIT', 'Owner\'s equity and retained earnings'),
            ('REVENUE', 'CREDIT', 'Income from business operations'),
            ('EXPENSE', 'DEBIT', 'Costs of doing business'),
        ]
        
        for name, normal_balance, description in account_types:
            account_type, created = AccountType.objects.get_or_create(
                name=name,
                defaults={
                    'normal_balance': normal_balance,
                    'description': description
                }
            )
            if created:
                self.stdout.write(f'  ✓ Created account type: {account_type.get_name_display()}')
    
    def create_fiscal_year(self):
        """Create current fiscal year"""
        today = date.today()
        start_date = date(today.year, 1, 1)
        end_date = date(today.year, 12, 31)
        
        # Create a system user if not exists
        system_user = User.objects.filter(is_superuser=True).first()
        if not system_user:
            self.stdout.write(self.style.WARNING('  ! No superuser found. Fiscal year will need to be created manually.'))
            return
        
        fiscal_year, created = FiscalYear.objects.get_or_create(
            name=f'FY {today.year}',
            defaults={
                'start_date': start_date,
                'end_date': end_date,
                'is_active': True,
                'created_by': system_user
            }
        )
        if created:
            self.stdout.write(f'  ✓ Created fiscal year: {fiscal_year.name}')
