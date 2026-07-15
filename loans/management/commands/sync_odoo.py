# -*- coding: utf-8 -*-
"""
Management command to sync data with Odoo

This command provides utilities for:
1. Syncing loan products from Odoo to Django
2. Syncing customers to Odoo
3. Syncing failed applications to Odoo
4. Checking sync status

Usage:
    python manage.py sync_odoo products     # Sync loan products from Odoo
    python manage.py sync_odoo customers    # Sync all customers to Odoo
    python manage.py sync_odoo applications # Sync failed applications
    python manage.py sync_odoo status       # Check sync status
"""

from django.core.management.base import BaseCommand
from django.utils import timezone
from loans.models import Customer, LoanApplication, LoanProduct


class Command(BaseCommand):
    help = 'Sync data with Odoo ERP system'

    def add_arguments(self, parser):
        parser.add_argument(
            'action',
            type=str,
            choices=['products', 'customers', 'applications', 'status'],
            help='Action to perform: products, customers, applications, or status'
        )
        parser.add_argument(
            '--force',
            action='store_true',
            help='Force sync even if already synced'
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be synced without actually syncing'
        )

    def handle(self, *args, **options):
        action = options['action']
        force = options['force']
        dry_run = options['dry_run']

        if action == 'products':
            self.sync_products(force, dry_run)
        elif action == 'customers':
            self.sync_customers(force, dry_run)
        elif action == 'applications':
            self.sync_applications(force, dry_run)
        elif action == 'status':
            self.show_status()

    def sync_products(self, force, dry_run):
        """Sync loan products from Odoo to Django"""
        self.stdout.write(self.style.SUCCESS('Syncing loan products from Odoo...'))
        
        try:
            from core.services.odoo_sync import OdooSyncService
            
            service = OdooSyncService()
            if not service.is_reachable():
                self.stdout.write(self.style.ERROR('Odoo is not reachable. Check configuration.'))
                return
            
            if dry_run:
                self.stdout.write('Dry run mode - would sync products from Odoo')
                products = service.get_loan_products()
                self.stdout.write(f'Found {len(products)} products in Odoo')
                for product in products:
                    self.stdout.write(f"  - {product.get('code')}: {product.get('name')}")
                return
            
            summary = service.sync_loan_products_from_odoo()
            
            self.stdout.write(self.style.SUCCESS(
                f'Product sync completed: {summary["total_products"]} total, '
                f'{summary["created"]} created, {summary["updated"]} updated, '
                f'{summary["failed"]} failed'
            ))
            
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'Product sync failed: {str(e)}'))

    def sync_customers(self, force, dry_run):
        """Sync customers to Odoo"""
        self.stdout.write(self.style.SUCCESS('Syncing customers to Odoo...'))
        
        try:
            from core.services.odoo_sync import OdooSyncService
            
            service = OdooSyncService()
            if not service.is_reachable():
                self.stdout.write(self.style.ERROR('Odoo is not reachable. Check configuration.'))
                return
            
            # Get customers that need syncing
            if force:
                customers = Customer.objects.all()
            else:
                customers = Customer.objects.filter(
                    odoo_customer_id__isnull=True
                ) | Customer.objects.filter(
                    odoo_sync_status__in=[Customer.ODOO_SYNC_FAILED, Customer.ODOO_SYNC_RETRY]
                )
            
            self.stdout.write(f'Found {customers.count()} customers to sync')
            
            if dry_run:
                self.stdout.write('Dry run mode - would sync customers to Odoo')
                for customer in customers:
                    self.stdout.write(f"  - {customer.user.email} (ID: {customer.pk})")
                return
            
            synced = 0
            failed = 0
            
            for customer in customers:
                try:
                    odoo_id, status = service.sync_user_to_odoo(customer.user)
                    synced += 1
                    self.stdout.write(f"  ✓ Synced {customer.user.email} (status: {status})")
                except Exception as e:
                    failed += 1
                    try:
                        customer.odoo_sync_status = Customer.ODOO_SYNC_FAILED
                        customer.odoo_sync_error = str(e)[:500]
                        customer.odoo_last_sync_at = timezone.now()
                        customer.save(update_fields=['odoo_sync_status', 'odoo_sync_error', 'odoo_last_sync_at'])
                    except Exception:
                        pass  # Avoid cascading errors
                    self.stdout.write(self.style.ERROR(f"  ✗ Failed {customer.user.email}: {str(e)}"))
            
            self.stdout.write(self.style.SUCCESS(
                f'Customer sync completed: {synced} synced, {failed} failed'
            ))
            
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'Customer sync failed: {str(e)}'))

    def sync_applications(self, force, dry_run):
        """Sync failed applications to Odoo"""
        self.stdout.write(self.style.SUCCESS('Syncing failed applications to Odoo...'))
        
        try:
            from core.services.odoo_sync import OdooSyncService
            
            service = OdooSyncService()
            if not service.is_reachable():
                self.stdout.write(self.style.ERROR('Odoo is not reachable. Check configuration.'))
                return
            
            # Get applications that need syncing
            if force:
                applications = LoanApplication.objects.filter(status=LoanApplication.SUBMITTED)
            else:
                applications = LoanApplication.objects.filter(
                    odoo_application_id__isnull=True,
                    status=LoanApplication.SUBMITTED
                ) | LoanApplication.objects.filter(
                    odoo_sync_status__in=[LoanApplication.ODOO_SYNC_FAILED, LoanApplication.ODOO_SYNC_RETRY]
                )
            
            self.stdout.write(f'Found {applications.count()} applications to sync')
            
            if dry_run:
                self.stdout.write('Dry run mode - would sync applications to Odoo')
                for app in applications:
                    self.stdout.write(f"  - {app.application_number} (ID: {app.pk})")
                return
            
            synced = 0
            failed = 0
            
            for application in applications:
                try:
                    result = service.create_loan_application(application)
                    application.odoo_application_id = result.get("odoo_application_id")
                    application.odoo_sync_status = LoanApplication.ODOO_SYNC_SUCCESS
                    application.odoo_sync_error = ""
                    application.odoo_last_sync_at = timezone.now()
                    application.save(update_fields=['odoo_application_id', 'odoo_sync_status', 'odoo_sync_error', 'odoo_last_sync_at'])
                    synced += 1
                    self.stdout.write(f"  ✓ Synced {application.application_number}")
                except Exception as e:
                    failed += 1
                    application.odoo_sync_status = LoanApplication.ODOO_SYNC_FAILED
                    application.odoo_sync_error = str(e)[:500]
                    application.odoo_last_sync_at = timezone.now()
                    application.save(update_fields=['odoo_sync_status', 'odoo_sync_error', 'odoo_last_sync_at'])
                    self.stdout.write(self.style.ERROR(f"  ✗ Failed {application.application_number}: {str(e)}"))
            
            self.stdout.write(self.style.SUCCESS(
                f'Application sync completed: {synced} synced, {failed} failed'
            ))
            
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'Application sync failed: {str(e)}'))

    def show_status(self):
        """Show sync status summary"""
        self.stdout.write(self.style.SUCCESS('Odoo Sync Status'))
        self.stdout.write('=' * 50)
        
        # Customer status
        total_customers = Customer.objects.count()
        synced_customers = Customer.objects.filter(odoo_customer_id__isnull=False).count()
        failed_customers = Customer.objects.filter(odoo_sync_status='FAILED').count()
        
        self.stdout.write(f'\nCustomers:')
        self.stdout.write(f'  Total: {total_customers}')
        self.stdout.write(f'  Synced: {synced_customers} ({synced_customers/total_customers*100 if total_customers else 0:.1f}%)')
        self.stdout.write(f'  Failed: {failed_customers}')
        
        # Product status
        total_products = LoanProduct.objects.count()
        synced_products = LoanProduct.objects.filter(odoo_product_id__isnull=False).count()
        
        self.stdout.write(f'\nLoan Products:')
        self.stdout.write(f'  Total: {total_products}')
        self.stdout.write(f'  Synced: {synced_products} ({synced_products/total_products*100 if total_products else 0:.1f}%)')
        
        # Application status
        total_applications = LoanApplication.objects.count()
        synced_applications = LoanApplication.objects.filter(odoo_application_id__isnull=False).count()
        failed_applications = LoanApplication.objects.filter(odoo_sync_status='FAILED').count()
        
        self.stdout.write(f'\nApplications:')
        self.stdout.write(f'  Total: {total_applications}')
        self.stdout.write(f'  Synced: {synced_applications} ({synced_applications/total_applications*100 if total_applications else 0:.1f}%)')
        self.stdout.write(f'  Failed: {failed_applications}')
        
        # Test Odoo connectivity
        try:
            from core.services.odoo_sync import OdooSyncService
            service = OdooSyncService()
            if service.is_reachable():
                self.stdout.write(self.style.SUCCESS('\n✓ Odoo is reachable'))
            else:
                self.stdout.write(self.style.ERROR('\n✗ Odoo is not reachable'))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'\n✗ Odoo connectivity check failed: {str(e)}'))