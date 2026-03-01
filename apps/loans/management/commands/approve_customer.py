"""
Management command to approve customer KYC verification
Usage: python manage.py approve_customer <email_or_customer_number>
"""
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone
from apps.loans.models import Customer
from apps.loans.notifications import NotificationService


class Command(BaseCommand):
    help = 'Approve customer KYC verification and activate account'

    def add_arguments(self, parser):
        parser.add_argument(
            'identifier',
            type=str,
            help='Customer email or customer number'
        )
        parser.add_argument(
            '--notes',
            type=str,
            default='Approved via management command',
            help='Verification notes'
        )

    def handle(self, *args, **options):
        identifier = options['identifier']
        notes = options['notes']
        
        # Try to find customer by email or customer number
        try:
            customer = Customer.objects.get(email=identifier)
        except Customer.DoesNotExist:
            try:
                customer = Customer.objects.get(customer_number=identifier)
            except Customer.DoesNotExist:
                raise CommandError(f'Customer not found: {identifier}')
        
        if customer.kyc_status == 'VERIFIED':
            self.stdout.write(
                self.style.WARNING(
                    f'Customer {customer.get_full_name()} ({customer.customer_number}) is already verified'
                )
            )
            return
        
        # Approve KYC
        customer.kyc_status = 'VERIFIED'
        customer.kyc_verified_at = timezone.now()
        customer.kyc_notes = notes
        customer.is_active = True
        customer.user.is_active = True
        customer.user.save()
        customer.save()
        
        # Send notification
        notification_service = NotificationService()
        notification_service.send_sms_notification(
            customer.phone_number,
            f"✅ Your Alba Capital account has been verified! You can now login and apply for loans. Visit http://127.0.0.1:3000/portal/login"[:160]
        )
        
        self.stdout.write(
            self.style.SUCCESS(
                f'✅ Successfully approved KYC for {customer.get_full_name()} ({customer.customer_number})'
            )
        )
        self.stdout.write(
            f'   Email: {customer.email}'
        )
        self.stdout.write(
            f'   Phone: {customer.phone_number}'
        )
        self.stdout.write(
            f'   Status: {customer.kyc_status}'
        )
