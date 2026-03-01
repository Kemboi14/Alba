"""
Loans Admin Configuration
"""
from django.contrib import admin
from .models import (
    LoanProduct, Customer, LoanApplication, Loan,
    RepaymentSchedule, Payment, CreditScore
)


@admin.register(LoanProduct)
class LoanProductAdmin(admin.ModelAdmin):
    list_display = ['name', 'code', 'interest_rate', 'interest_method', 'minimum_amount', 'maximum_amount', 'is_active']
    list_filter = ['is_active', 'interest_method']
    search_fields = ['name', 'code']


@admin.register(Customer)
class CustomerAdmin(admin.ModelAdmin):
    list_display = ['customer_number', 'get_full_name', 'phone_number', 'email', 'kyc_status', 'is_active', 'is_blacklisted', 'created_at']
    list_filter = ['kyc_status', 'is_active', 'is_blacklisted', 'employment_status', 'email_verified', 'created_at']
    search_fields = ['customer_number', 'first_name', 'last_name', 'national_id', 'email']
    readonly_fields = ['kyc_verified_by', 'kyc_verified_at', 'email_verified_at', 'created_at', 'updated_at']
    actions = ['approve_kyc', 'reject_kyc']
    date_hierarchy = 'created_at'
    
    def get_queryset(self, request):
        """Order by newest first, show pending approvals at top"""
        qs = super().get_queryset(request)
        # Sort: inactive first (is_active=False), then by newest
        return qs.order_by('is_active', '-created_at')
    
    def approve_kyc(self, request, queryset):
        """Approve KYC verification for selected customers"""
        from django.utils import timezone
        count = 0
        for customer in queryset:
            if customer.kyc_status != 'VERIFIED':
                customer.kyc_status = 'VERIFIED'
                customer.kyc_verified_by = request.user
                customer.kyc_verified_at = timezone.now()
                customer.is_active = True
                customer.user.is_active = True
                customer.user.save()
                customer.save()
                
                # Send notification to customer
                from apps.loans.notifications import NotificationService
                notification_service = NotificationService()
                notification_service.send_sms_notification(
                    customer.phone_number,
                    f"✅ Your Alba Capital account has been verified! You can now login and apply for loans. Visit http://127.0.0.1:3000/portal/login"[:160]
                )
                count += 1
        
        self.message_user(request, f'Successfully approved KYC for {count} customer(s).')
    approve_kyc.short_description = "✅ Approve KYC Verification"
    
    def reject_kyc(self, request, queryset):
        """Reject KYC verification for selected customers"""
        count = queryset.update(kyc_status='REJECTED')
        self.message_user(request, f'Rejected KYC for {count} customer(s).')
    reject_kyc.short_description = "❌ Reject KYC Verification"


@admin.register(LoanApplication)
class LoanApplicationAdmin(admin.ModelAdmin):
    list_display = ['application_number', 'customer', 'loan_product', 'requested_amount', 'status', 'created_at']
    list_filter = ['status', 'loan_product', 'created_at']
    search_fields = ['application_number', 'customer__customer_number', 'customer__first_name']


@admin.register(Loan)
class LoanAdmin(admin.ModelAdmin):
    list_display = ['loan_number', 'customer', 'principal_amount', 'status', 'disbursement_date', 'days_overdue']
    list_filter = ['status', 'loan_product', 'disbursement_date']
    search_fields = ['loan_number', 'customer__customer_number']


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ['payment_number', 'loan', 'amount', 'payment_date', 'payment_method', 'is_reconciled']
    list_filter = ['payment_method', 'is_reconciled', 'payment_date']
    search_fields = ['payment_number', 'reference_number']
