"""
Django Admin Configuration for Loan Management
Professional admin interfaces for all loan models
"""

from django.contrib import admin
from django.utils.html import format_html
from django.urls import reverse
from django.utils import timezone
from .models import (
    LoanProduct,
    Customer,
    CreditScore,
    LoanApplication,
    Loan,
    LoanRepayment,
    EmployerVerification,
    GuarantorVerification,
    LoanDocument,
    WebhookDelivery,
)


@admin.register(LoanProduct)
class LoanProductAdmin(admin.ModelAdmin):
    list_display = [
        'name',
        'code',
        'category',
        'min_amount',
        'max_amount',
        'interest_rate',
        'interest_method',
        'odoo_sync_status',
        'is_active',
        'created_at',
    ]
    list_filter = ['category', 'is_active', 'interest_method', 'odoo_product_id']
    search_fields = ['name', 'code', 'description']
    readonly_fields = ['created_at', 'updated_at']
    actions = ['sync_products_to_odoo', 'sync_missing_products']

    fieldsets = (
        ('Basic Information', {
            'fields': ('name', 'code', 'category', 'description', 'is_active')
        }),
        ('Loan Limits', {
            'fields': ('min_amount', 'max_amount', 'min_tenure_months', 'max_tenure_months')
        }),
        ('Interest Configuration', {
            'fields': ('interest_rate', 'interest_method')
        }),
        ('Fees', {
            'fields': ('origination_fee_percentage', 'origination_fee_fixed', 'processing_fee')
        }),
        ('Penalties', {
            'fields': ('penalty_rate', 'grace_period_days')
        }),
        ('Requirements', {
            'fields': (
                'requires_guarantor',
                'requires_employer_verification',
                'min_credit_score',
                'default_repayment_frequency',
            )
        }),
        ('Odoo Integration', {
            'fields': ('odoo_product_id',),
            'classes': ('collapse',)
        }),
        ('Tracking', {
            'fields': ('created_by', 'created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )

    def odoo_sync_status(self, obj):
        if obj.odoo_product_id:
            return format_html(
                '<span style="color: green;">✓ Synced (ID: {})</span>',
                obj.odoo_product_id
            )
        else:
            return format_html(
                '<span style="color: red;">✗ Not Synced</span>'
            )
    odoo_sync_status.short_description = 'Odoo Sync'

    def sync_products_to_odoo(self, request, queryset):
        """Admin action to sync selected loan products to Odoo"""
        from core.services.odoo_sync import OdooSyncService
        
        synced = 0
        failed = 0
        errors = []
        
        try:
            service = OdooSyncService()
            if service.is_reachable():
                for product in queryset:
                    try:
                        odoo_id = service.sync_loan_product_to_odoo(product)
                        if odoo_id:
                            product.odoo_product_id = odoo_id
                            product.save(update_fields=['odoo_product_id'])
                            synced += 1
                        else:
                            failed += 1
                            errors.append(f"Product {product.code}: No matching product in Odoo")
                    except Exception as e:
                        failed += 1
                        errors.append(f"Product {product.code}: {str(e)[:100]}")
            else:
                self.message_user(request, "Odoo is unreachable. Cannot sync products.", level='ERROR')
                return
        except Exception as e:
            self.message_user(request, f"Sync failed: {str(e)}", level='ERROR')
            return
        
        self.message_user(request, f"Synced {synced} products to Odoo successfully. {failed} failed.")
        if errors:
            self.message_user(request, f"Errors: {'; '.join(errors[:3])}", level='ERROR')
    sync_products_to_odoo.short_description = 'Sync selected products to Odoo'

    def sync_missing_products(self, request, queryset):
        """Admin action to sync all products missing Odoo IDs"""
        missing_products = queryset.filter(odoo_product_id__isnull=True)
        count = missing_products.count()
        
        if count == 0:
            self.message_user(request, "No products missing Odoo sync.")
            return
        
        return self.sync_products_to_odoo(request, missing_products)
    sync_missing_products.short_description = 'Sync products missing Odoo ID'

    def __copy__(self):
        """Fix Django template context copying issue"""
        cls = self.__class__
        result = cls.__new__(cls)
        result.__dict__.update(self.__dict__)
        return result


@admin.register(Customer)
class CustomerAdmin(admin.ModelAdmin):
    list_display = [
        'get_full_name',
        'id_number',
        'employment_status',
        'monthly_income',
        'kyc_verified',
        'get_kyc_completion',
        'odoo_sync_status_badge',
        'is_blacklisted',
        'created_at',
    ]
    list_filter = ['kyc_verified', 'is_blacklisted', 'employment_status', 'odoo_sync_status']
    search_fields = ['user__first_name', 'user__last_name', 'user__email', 'id_number']
    readonly_fields = ['created_at', 'updated_at', 'kyc_verified_at', 'get_age', 'odoo_last_sync_at']
    actions = ['sync_to_odoo', 'retry_failed_syncs']

    fieldsets = (
        ('User Information', {
            'fields': ('user',)
        }),
        ('Personal Information', {
            'fields': ('date_of_birth', 'get_age', 'id_number', 'address', 'county', 'city')
        }),
        ('Employment Information', {
            'fields': (
                'employment_status',
                'employer_name',
                'employer_contact',
                'employer_email',
                'monthly_income',
                'employment_date',
            )
        }),
        ('Business Information', {
            'fields': (
                'is_business_entity',
                'business_name',
                'business_registration_number',
                'business_location',
                'business_industry',
                'annual_turnover',
            ),
            'classes': ('collapse',)
        }),
        ('Financial Information', {
            'fields': ('existing_loans', 'bank_name', 'bank_account')
        }),
        ('KYC Documents', {
            'fields': (
                'national_id_file',
                'national_id_verified',
                'bank_statement_file',
                'bank_statement_verified',
                'face_recognition_photo',
                'face_recognition_verified',
            )
        }),
        ('KYC Status', {
            'fields': ('kyc_verified', 'kyc_verified_at', 'kyc_verified_by')
        }),
        ('Odoo Integration', {
            'fields': (
                'odoo_customer_id',
                'odoo_sync_status',
                'odoo_sync_error',
                'odoo_sync_attempts',
                'odoo_last_sync_at',
            ),
            'classes': ('collapse',)
        }),
        ('Status', {
            'fields': ('is_blacklisted', 'blacklist_reason')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )

    def __copy__(self):
        """Fix Django template context copying issue"""
        cls = self.__class__
        result = cls.__new__(cls)
        result.__dict__.update(self.__dict__)
        return result

    def get_full_name(self, obj):
        return obj.user.get_full_name()
    get_full_name.short_description = 'Customer Name'

    def get_kyc_completion(self, obj):
        completion = obj.get_kyc_completion_percentage()
        if completion == 100:
            color = 'green'
            status = 'Complete'
        elif completion >= 66:
            color = 'yellow'
            status = 'Good'
        elif completion >= 33:
            color = 'orange'
            status = 'Partial'
        else:
            color = 'red'
            status = 'Low'

        return format_html(
            '<span style="color: {};">{}%</span>',
            color,
            completion
        )
    get_kyc_completion.short_description = 'KYC %'

    def odoo_sync_status_badge(self, obj):
        colors = {
            'PENDING': '#ffc107',
            'SUCCESS': '#20c997',
            'FAILED': '#dc3545',
            'RETRY': '#fd7e14',
        }
        color = colors.get(obj.odoo_sync_status, '#6c757d')
        return format_html(
            '<span style="background-color: {}; color: white; padding: 3px 10px; border-radius: 3px; font-weight: bold; font-size: 11px;">{}</span>',
            color,
            obj.odoo_sync_status
        )
    odoo_sync_status_badge.short_description = 'Odoo Sync'

    def sync_to_odoo(self, request, queryset):
        """Admin action to sync selected customers to Odoo"""
        from core.services.odoo_sync import OdooSyncService
        
        synced = 0
        failed = 0
        errors = []
        
        for customer in queryset:
            try:
                service = OdooSyncService()
                if service.is_reachable():
                    result = service.create_or_update_customer(customer.user)
                    if result and result.get('odoo_customer_id'):
                        customer.odoo_customer_id = result.get('odoo_customer_id')
                        customer.odoo_sync_status = 'SUCCESS'
                        customer.odoo_sync_error = ''
                        customer.odoo_last_sync_at = timezone.now()
                        customer.save(update_fields=['odoo_customer_id', 'odoo_sync_status', 'odoo_sync_error', 'odoo_last_sync_at'])
                        synced += 1
                    else:
                        failed += 1
                        errors.append(f"Customer {customer.id}: Invalid response from Odoo")
                else:
                    failed += 1
                    errors.append(f"Customer {customer.id}: Odoo unreachable")
            except Exception as e:
                failed += 1
                errors.append(f"Customer {customer.id}: {str(e)[:100]}")
        
        self.message_user(request, f"Synced {synced} customers to Odoo successfully. {failed} failed.")
        if errors:
            self.message_user(request, f"Errors: {'; '.join(errors[:3])}", level='ERROR')
    sync_to_odoo.short_description = 'Sync selected customers to Odoo'

    def retry_failed_syncs(self, request, queryset):
        """Admin action to retry sync for customers with failed status"""
        failed_customers = queryset.filter(odoo_sync_status='FAILED')
        count = failed_customers.count()
        
        if count == 0:
            self.message_user(request, "No customers with failed sync status selected.")
            return
        
        return self.sync_to_odoo(request, failed_customers)
    retry_failed_syncs.short_description = 'Retry failed syncs to Odoo'


@admin.register(CreditScore)
class CreditScoreAdmin(admin.ModelAdmin):
    list_display = [
        'customer',
        'loan_application',
        'total_score',
        'recommendation',
        'is_overridden',
        'created_at',
    ]
    list_filter = ['recommendation', 'is_overridden', 'created_at']
    search_fields = ['customer__user__first_name', 'customer__user__last_name']
    readonly_fields = ['created_at', 'calculation_details']

    fieldsets = (
        ('Score Details', {
            'fields': (
                'customer',
                'loan_application',
                'income_score',
                'employment_score',
                'credit_history_score',
                'existing_obligations_score',
                'age_score',
                'total_score',
                'recommendation',
            )
        }),
        ('Override', {
            'fields': ('is_overridden', 'override_reason', 'overridden_by', 'overridden_at'),
            'classes': ('collapse',)
        }),
        ('Calculation', {
            'fields': ('calculation_details', 'created_at'),
            'classes': ('collapse',)
        }),
    )

    def __copy__(self):
        """Fix Django template context copying issue"""
        cls = self.__class__
        result = cls.__new__(cls)
        result.__dict__.update(self.__dict__)
        return result


@admin.register(LoanApplication)
class LoanApplicationAdmin(admin.ModelAdmin):
    list_display = [
        'application_number',
        'customer_name',
        'loan_product',
        'requested_amount',
        'tenure_months',
        'status_badge',
        'odoo_sync_status_badge',
        'submitted_at',
        'created_at',
    ]
    list_filter = ['status', 'loan_product', 'submitted_at', 'created_at', 'odoo_sync_status']
    search_fields = [
        'application_number',
        'customer__user__first_name',
        'customer__user__last_name',
        'customer__user__email',
        'odoo_application_id',
    ]
    readonly_fields = [
        'application_number',
        'created_at',
        'updated_at',
        'submitted_at',
        'reviewed_at',
        'approved_at',
        'disbursed_at',
        'rejected_at',
        'odoo_last_sync_at',
    ]
    actions = ['sync_to_odoo', 'retry_failed_syncs', 'sync_all_pending']

    fieldsets = (
        ('Application Details', {
            'fields': (
                'application_number',
                'customer',
                'loan_product',
                'requested_amount',
                'tenure_months',
                'repayment_frequency',
                'purpose',
            )
        }),
        ('Business Details', {
            'fields': (
                'business_name',
                'business_registration_number',
                'business_location',
                'annual_turnover',
            ),
            'classes': ('collapse',)
        }),
        ('Status & Workflow', {
            'fields': (
                'status',
                'approved_amount',
                'submitted_at',
                'reviewed_at',
                'approved_at',
                'disbursed_at',
                'rejected_at',
            )
        }),
        ('Odoo Integration', {
            'fields': (
                'odoo_application_id',
                'odoo_loan_id',
                'odoo_loan_number',
                'odoo_sync_status',
                'odoo_sync_error',
                'odoo_sync_attempts',
                'odoo_last_sync_at',
            ),
            'classes': ('collapse',)
        }),
        ('Approval/Rejection', {
            'fields': ('reviewed_by', 'approved_by', 'rejection_reason')
        }),
        ('Notes', {
            'fields': ('internal_notes',),
            'classes': ('collapse',)
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    def __copy__(self):
        """Fix Django template context copying issue"""
        cls = self.__class__
        result = cls.__new__(cls)
        result.__dict__.update(self.__dict__)
        return result
    
    def customer_name(self, obj):
        return obj.customer.user.get_full_name()
    customer_name.short_description = 'Customer'
    
    def status_badge(self, obj):
        colors = {
            'DRAFT': '#6c757d',
            'SUBMITTED': '#0dcaf0',
            'UNDER_REVIEW': '#0d6efd',
            'CREDIT_ANALYSIS': '#6610f2',
            'PENDING_APPROVAL': '#fd7e14',
            'APPROVED': '#20c997',
            'EMPLOYER_VERIFICATION': '#17a2b8',
            'GUARANTOR_CONFIRMATION': '#ffc107',
            'DISBURSED': '#198754',
            'REJECTED': '#dc3545',
            'CANCELLED': '#6c757d',
        }
        color = colors.get(obj.status, '#6c757d')
        return format_html(
            '<span style="background-color: {}; color: white; padding: 3px 10px; border-radius: 3px; font-weight: bold;">{}</span>',
            color,
            obj.get_status_display()
        )
    status_badge.short_description = 'Status'

    def odoo_sync_status_badge(self, obj):
        colors = {
            'PENDING': '#ffc107',
            'SUCCESS': '#20c997',
            'FAILED': '#dc3545',
            'RETRY': '#fd7e14',
        }
        color = colors.get(obj.odoo_sync_status, '#6c757d')
        return format_html(
            '<span style="background-color: {}; color: white; padding: 3px 10px; border-radius: 3px; font-weight: bold; font-size: 11px;">{}</span>',
            color,
            obj.odoo_sync_status
        )
    odoo_sync_status_badge.short_description = 'Odoo Sync'

    def sync_to_odoo(self, request, queryset):
        """Admin action to sync selected loan applications to Odoo"""
        from core.services.odoo_sync import OdooSyncService
        
        synced = 0
        failed = 0
        errors = []
        
        for application in queryset:
            try:
                service = OdooSyncService()
                if service.is_reachable():
                    result = service.create_loan_application(application)
                    if result and result.get('odoo_application_id'):
                        application.odoo_application_id = result.get('odoo_application_id')
                        application.odoo_sync_status = 'SUCCESS'
                        application.odoo_sync_error = ''
                        application.odoo_last_sync_at = timezone.now()
                        application.save(update_fields=['odoo_application_id', 'odoo_sync_status', 'odoo_sync_error', 'odoo_last_sync_at'])
                        synced += 1
                    else:
                        failed += 1
                        errors.append(f"Application {application.application_number}: Invalid response from Odoo")
                else:
                    failed += 1
                    errors.append(f"Application {application.application_number}: Odoo unreachable")
            except Exception as e:
                failed += 1
                errors.append(f"Application {application.application_number}: {str(e)[:100]}")
        
        self.message_user(request, f"Synced {synced} applications to Odoo successfully. {failed} failed.")
        if errors:
            self.message_user(request, f"Errors: {'; '.join(errors[:3])}", level='ERROR')
    sync_to_odoo.short_description = 'Sync selected applications to Odoo'

    def retry_failed_syncs(self, request, queryset):
        """Admin action to retry sync for applications with failed status"""
        failed_apps = queryset.filter(odoo_sync_status='FAILED')
        count = failed_apps.count()
        
        if count == 0:
            self.message_user(request, "No applications with failed sync status selected.")
            return
        
        return self.sync_to_odoo(request, failed_apps)
    retry_failed_syncs.short_description = 'Retry failed syncs to Odoo'

    def sync_all_pending(self, request, queryset):
        """Admin action to sync all applications with pending status"""
        pending_apps = queryset.filter(odoo_sync_status='PENDING')
        count = pending_apps.count()
        
        if count == 0:
            self.message_user(request, "No applications with pending sync status.")
            return
        
        return self.sync_to_odoo(request, pending_apps)
    sync_all_pending.short_description = 'Sync pending applications to Odoo'


@admin.register(Loan)
class LoanAdmin(admin.ModelAdmin):
    list_display = [
        'loan_number',
        'customer_name',
        'loan_product',
        'principal_amount',
        'outstanding_balance',
        'status_badge',
        'disbursement_date',
        'next_payment_date',
    ]
    list_filter = ['status', 'loan_product', 'disbursement_date']
    search_fields = [
        'loan_number',
        'customer__user__first_name',
        'customer__user__last_name',
    ]
    readonly_fields = [
        'loan_number',
        'application',
        'created_at',
        'updated_at',
        'get_payment_progress_percentage',
    ]
    
    fieldsets = (
        ('Loan Details', {
            'fields': (
                'loan_number',
                'application',
                'customer',
                'loan_product',
                'status',
            )
        }),
        ('Amount Breakdown', {
            'fields': (
                'principal_amount',
                'interest_amount',
                'fees',
                'total_amount',
                'outstanding_balance',
                'get_payment_progress_percentage',
            )
        }),
        ('Repayment Details', {
            'fields': (
                'installment_amount',
                'repayment_frequency',
                'tenure_months',
            )
        }),
        ('Dates', {
            'fields': (
                'disbursement_date',
                'first_payment_date',
                'maturity_date',
                'next_payment_date',
                'last_payment_date',
            )
        }),
        ('Status & Penalties', {
            'fields': ('days_overdue', 'penalty_charged')
        }),
        ('Disbursement', {
            'fields': (
                'disbursed_by',
                'disbursement_method',
                'disbursement_reference',
            ),
            'classes': ('collapse',)
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    def __copy__(self):
        """Fix Django template context copying issue"""
        cls = self.__class__
        result = cls.__new__(cls)
        result.__dict__.update(self.__dict__)
        return result
    
    def customer_name(self, obj):
        return obj.customer.user.get_full_name()
    customer_name.short_description = 'Customer'
    
    def status_badge(self, obj):
        colors = {
            'ACTIVE': '#198754',
            'PAID': '#0d6efd',
            'OVERDUE': '#ffc107',
            'DEFAULTED': '#dc3545',
            'WRITTEN_OFF': '#6c757d',
            'RESTRUCTURED': '#0dcaf0',
        }
        color = colors.get(obj.status, '#6c757d')
        return format_html(
            '<span style="background-color: {}; color: white; padding: 3px 10px; border-radius: 3px; font-weight: bold;">{}</span>',
            color,
            obj.get_status_display()
        )
    status_badge.short_description = 'Status'


@admin.register(LoanRepayment)
class LoanRepaymentAdmin(admin.ModelAdmin):
    list_display = [
        'receipt_number',
        'loan_link',
        'payment_date',
        'amount',
        'payment_method',
        'payment_type',
        'created_at',
    ]
    list_filter = ['payment_method', 'payment_type', 'payment_date']
    search_fields = ['receipt_number', 'loan__loan_number', 'reference_number']
    readonly_fields = ['receipt_number', 'created_at']
    
    fieldsets = (
        ('Payment Details', {
            'fields': (
                'receipt_number',
                'loan',
                'payment_date',
                'amount',
                'payment_type',
                'payment_method',
                'reference_number',
            )
        }),
        ('Allocation', {
            'fields': ('principal_paid', 'interest_paid', 'penalty_paid')
        }),
        ('Processing', {
            'fields': ('processed_by', 'notes'),
            'classes': ('collapse',)
        }),
        ('Timestamp', {
            'fields': ('created_at',),
            'classes': ('collapse',)
        }),
    )
    
    def loan_link(self, obj):
        url = reverse('admin:loans_loan_change', args=[obj.loan.pk])
        return format_html('<a href="{}">{}</a>', url, obj.loan.loan_number)
    loan_link.short_description = 'Loan'


@admin.register(EmployerVerification)
class EmployerVerificationAdmin(admin.ModelAdmin):
    list_display = [
        'application_link',
        'employer_name',
        'employment_confirmed',
        'income_confirmed',
        'status',
        'verified_at',
    ]
    list_filter = ['status', 'employment_confirmed', 'income_confirmed']
    search_fields = ['application__application_number', 'employer_name']
    readonly_fields = ['created_at', 'updated_at', 'sent_at', 'verified_at']

    fieldsets = (
        ('Application', {
            'fields': ('application',)
        }),
        ('Employer Details', {
            'fields': (
                'employer_name',
                'contact_person',
                'contact_email',
                'contact_phone',
            )
        }),
        ('Verification', {
            'fields': (
                'employment_confirmed',
                'income_confirmed',
                'verified_income',
                'status',
            )
        }),
        ('Process', {
            'fields': ('sent_at', 'verified_at', 'verified_by', 'verification_notes')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )

    def __copy__(self):
        """Fix Django template context copying issue"""
        cls = self.__class__
        result = cls.__new__(cls)
        result.__dict__.update(self.__dict__)
        return result
    
    def application_link(self, obj):
        url = reverse('admin:loans_loanapplication_change', args=[obj.application.pk])
        return format_html('<a href="{}">{}</a>', url, obj.application.application_number)
    application_link.short_description = 'Application'


@admin.register(GuarantorVerification)
class GuarantorVerificationAdmin(admin.ModelAdmin):
    list_display = [
        'full_name',
        'application_link',
        'phone',
        'relationship',
        'liability_amount',  # Odoo Alignment
        'status',
        'confirmed_at',
    ]
    list_filter = ['status', 'created_at']
    search_fields = [
        'full_name',
        'id_number',
        'phone',
        'email',
        'application__application_number',
    ]
    readonly_fields = ['confirmation_code', 'created_at', 'updated_at', 'sent_at', 'confirmed_at']

    fieldsets = (
        ('Application', {
            'fields': ('application',)
        }),
        ('Guarantor Details', {
            'fields': (
                'full_name',
                'id_number',
                'phone',
                'email',
                'relationship',
                'address',  # Odoo Alignment
            )
        }),
        ('Financial Information', {
            'fields': ('employer', 'monthly_income', 'liability_amount')  # Odoo Alignment
        }),
        ('Verification', {
            'fields': (
                'status',
                'confirmation_code',
                'sent_at',
                'confirmed_at',
            )
        }),
        ('Notes', {
            'fields': ('guarantor_notes', 'internal_notes'),
            'classes': ('collapse',)
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )

    def __copy__(self):
        """Fix Django template context copying issue"""
        cls = self.__class__
        result = cls.__new__(cls)
        result.__dict__.update(self.__dict__)
        return result
    
    def application_link(self, obj):
        url = reverse('admin:loans_loanapplication_change', args=[obj.application.pk])
        return format_html('<a href="{}">{}</a>', url, obj.application.application_number)
    application_link.short_description = 'Application'


@admin.register(LoanDocument)
class LoanDocumentAdmin(admin.ModelAdmin):
    list_display = [
        'application_link',
        'document_type',
        'description',
        'is_validated',
        'validated_by',
        'created_at',
    ]
    list_filter = ['document_type', 'is_validated', 'created_at']
    search_fields = ['application__application_number', 'description']
    readonly_fields = ['created_at', 'validated_at']
    
    def __copy__(self):
        """Fix Django template context copying issue"""
        cls = self.__class__
        result = cls.__new__(cls)
        result.__dict__.update(self.__dict__)
        return result
    
    fieldsets = (
        ('Document Details', {
            'fields': (
                'application',
                'document_type',
                'document_file',
                'description',
            )
        }),
        ('Validation', {
            'fields': ('is_validated', 'validated_by', 'validated_at')
        }),
        ('Upload Info', {
            'fields': ('uploaded_by', 'created_at'),
            'classes': ('collapse',)
        }),
    )
    
    def application_link(self, obj):
        url = reverse('admin:loans_loanapplication_change', args=[obj.application.pk])
        return format_html('<a href="{}">{}</a>', url, obj.application.application_number)
    application_link.short_description = 'Application'


@admin.register(WebhookDelivery)
class WebhookDeliveryAdmin(admin.ModelAdmin):
    list_display = [
        'event_type',
        'delivery_id_short',
        'status_badge',
        'remote_ip',
        'received_at',
        'odoo_timestamp',
    ]
    list_filter = ['status', 'event_type', 'received_at']
    search_fields = ['delivery_id', 'event_type', 'processing_detail']
    readonly_fields = [
        'delivery_id',
        'event_type',
        'received_at',
        'raw_body',
        'remote_ip',
        'odoo_timestamp',
    ]
    actions = ['retry_failed_webhooks', 'cleanup_old_webhooks']

    fieldsets = (
        ('Webhook Details', {
            'fields': (
                'delivery_id',
                'event_type',
                'status',
                'processing_detail',
            )
        }),
        ('Technical Details', {
            'fields': (
                'remote_ip',
                'odoo_timestamp',
                'received_at',
            ),
            'classes': ('collapse',)
        }),
        ('Payload', {
            'fields': ('raw_body',),
            'classes': ('collapse',)
        }),
    )

    def __copy__(self):
        """Fix Django template context copying issue"""
        cls = self.__class__
        result = cls.__new__(cls)
        result.__dict__.update(self.__dict__)
        return result

    def delivery_id_short(self, obj):
        return obj.delivery_id[:20] + '...' if len(obj.delivery_id) > 20 else obj.delivery_id
    delivery_id_short.short_description = 'Delivery ID'

    def status_badge(self, obj):
        colors = {
            'processing': '#ffc107',
            'success': '#20c997',
            'error': '#dc3545',
            'unhandled': '#6c757d',
        }
        color = colors.get(obj.status, '#6c757d')
        return format_html(
            '<span style="background-color: {}; color: white; padding: 3px 10px; border-radius: 3px; font-weight: bold; font-size: 11px;">{}</span>',
            color,
            obj.status
        )
    status_badge.short_description = 'Status'

    def retry_failed_webhooks(self, request, queryset):
        """Admin action to retry failed webhook deliveries - placeholder for future implementation"""
        failed_webhooks = queryset.filter(status='error')
        count = failed_webhooks.count()
        
        if count == 0:
            self.message_user(request, "No failed webhook deliveries selected.")
            return
        
        # This would need to be implemented with actual retry logic
        self.message_user(request, f"Found {count} failed webhook deliveries. Retry functionality to be implemented.")
    retry_failed_webhooks.short_description = 'Retry failed webhooks'

    def cleanup_old_webhooks(self, request, queryset):
        """Admin action to clean up old successful webhook deliveries"""
        from datetime import timedelta
        from django.utils import timezone
        
        cutoff_date = timezone.now() - timedelta(days=30)
        old_webhooks = queryset.filter(status='success', received_at__lt=cutoff_date)
        count = old_webhooks.count()
        
        if count == 0:
            self.message_user(request, "No old successful webhook deliveries found (older than 30 days).")
            return
        
        deleted_count, _ = old_webhooks.delete()
        self.message_user(request, f"Deleted {deleted_count} old webhook deliveries.")
    cleanup_old_webhooks.short_description = 'Clean up old successful webhooks (30+ days)'

