"""
Super Admin Panel Views for Alba Capital
Provides comprehensive admin dashboard for system management
"""

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import Count, Sum, Q
from django.utils import timezone
from django.http import JsonResponse
from django.core.paginator import Paginator
from django.contrib.auth import get_user_model
from django.conf import settings
from functools import wraps

from .models import User, AuditLog, OdooConfig
from loans.models import LoanProduct, LoanApplication, Customer, Loan
from .services.odoo_sync import (
    OdooSyncService, OdooSyncError, OdooAuthError,
    OdooConnectionError, OdooNotFoundError, OdooValidationError,
    OdooServerError, OdooTimeoutError
)


User = get_user_model()


def admin_required(view_func):
    """
    Decorator to restrict views to admin users only.
    Requires user to be logged in and have ADMIN role or be superuser.
    """
    @wraps(view_func)
    @login_required
    def wrapper(request, *args, **kwargs):
        if not (request.user.role == User.ADMIN or request.user.is_superuser):
            messages.error(request, "Access denied. Admin privileges required.")
            return redirect('dashboard')
        return view_func(request, *args, **kwargs)
    return wrapper


@admin_required
def admin_dashboard(request):
    """
    Admin Dashboard - System overview with key metrics
    """
    # Calculate metrics
    today = timezone.now().date()
    
    # User statistics
    total_users = User.objects.count()
    active_users = User.objects.filter(is_active=True).count()
    new_users_today = User.objects.filter(date_joined__date=today).count()
    pending_kyc = Customer.objects.filter(kyc_verified=False).count()
    
    # Loan statistics
    total_applications = LoanApplication.objects.count()
    pending_applications = LoanApplication.objects.filter(
        status__in=[LoanApplication.SUBMITTED, LoanApplication.UNDER_REVIEW]
    ).count()
    approved_loans = LoanApplication.objects.filter(status=LoanApplication.APPROVED).count()
    disbursed_loans = Loan.objects.count()
    
    # Financial metrics
    total_disbursed = Loan.objects.filter(status=Loan.ACTIVE).aggregate(
        total=Sum('principal_amount')
    )['total'] or 0
    
    # Recent activity
    recent_audit_logs = AuditLog.objects.select_related('user').order_by('-timestamp')[:10]
    
    # Recent applications
    recent_applications = LoanApplication.objects.select_related(
        'customer', 'loan_product'
    ).order_by('-created_at')[:5]
    
    # Charts data (last 30 days)
    thirty_days_ago = timezone.now() - timezone.timedelta(days=30)
    
    # Applications by status
    applications_by_status = LoanApplication.objects.values('status').annotate(
        count=Count('id')
    ).order_by('status')
    
    # Users by role
    users_by_role = User.objects.values('role').annotate(
        count=Count('id')
    ).order_by('role')
    
    context = {
        'page_title': 'Admin Dashboard',
        'metrics': {
            'total_users': total_users,
            'active_users': active_users,
            'new_users_today': new_users_today,
            'pending_kyc': pending_kyc,
            'total_applications': total_applications,
            'pending_applications': pending_applications,
            'approved_loans': approved_loans,
            'disbursed_loans': disbursed_loans,
            'total_disbursed': total_disbursed,
        },
        'recent_audit_logs': recent_audit_logs,
        'recent_applications': recent_applications,
        'applications_by_status': list(applications_by_status),
        'users_by_role': list(users_by_role),
    }
    
    return render(request, 'admin/dashboard.html', context)


@admin_required
def user_management(request):
    """
    User Management - List all users with filtering and search
    """
    # Get filter parameters
    role_filter = request.GET.get('role', '')
    status_filter = request.GET.get('status', '')
    search_query = request.GET.get('q', '')
    
    # Base queryset
    users = User.objects.select_related().order_by('-date_joined')
    
    # Apply filters
    if role_filter:
        users = users.filter(role=role_filter)
    
    if status_filter == 'active':
        users = users.filter(is_active=True)
    elif status_filter == 'inactive':
        users = users.filter(is_active=False)
    elif status_filter == 'pending':
        users = users.filter(is_active=False, is_approved=False)
    
    if search_query:
        users = users.filter(
            Q(email__icontains=search_query) |
            Q(first_name__icontains=search_query) |
            Q(last_name__icontains=search_query) |
            Q(phone__icontains=search_query)
        )
    
    # Pagination
    paginator = Paginator(users, 25)
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)
    
    # Statistics
    total_users = User.objects.count()
    active_users = User.objects.filter(is_active=True).count()
    pending_users = User.objects.filter(is_active=False, is_approved=False).count()
    staff_users = User.objects.filter(is_staff=True).count()
    
    context = {
        'page_title': 'User Management',
        'users': page_obj,
        'role_choices': User.ROLE_CHOICES,
        'role_filter': role_filter,
        'status_filter': status_filter,
        'search_query': search_query,
        'stats': {
            'total': total_users,
            'active': active_users,
            'pending': pending_users,
            'staff': staff_users,
        }
    }
    
    return render(request, 'admin/user_management.html', context)


@admin_required
def user_detail(request, user_id):
    """
    User Detail - View and manage individual user
    """
    user = get_object_or_404(User, id=user_id)
    
    # Get related data
    customer_profile = None
    loan_applications = []
    audit_logs = []
    
    try:
        customer_profile = Customer.objects.get(user=user)
        loan_applications = LoanApplication.objects.filter(
            customer=customer_profile
        ).order_by('-created_at')
    except Customer.DoesNotExist:
        pass
    
    # Get audit logs for this user
    audit_logs = AuditLog.objects.filter(user=user).order_by('-timestamp')[:20]
    
    if request.method == 'POST':
        action = request.POST.get('action')
        
        if action == 'activate':
            user.is_active = True
            user.save()
            messages.success(request, f'User {user.email} has been activated.')
            
        elif action == 'deactivate':
            user.is_active = False
            user.save()
            messages.warning(request, f'User {user.email} has been deactivated.')
            
        elif action == 'change_role':
            new_role = request.POST.get('new_role')
            if new_role in [choice[0] for choice in User.ROLE_CHOICES]:
                old_role = user.get_role_display()
                user.role = new_role
                user.save()
                messages.success(
                    request, 
                    f'User role changed from {old_role} to {user.get_role_display()}.'
                )
                
        elif action == 'approve_kyc':
            if customer_profile:
                customer_profile.kyc_verified = True
                customer_profile.kyc_verified_at = timezone.now()
                customer_profile.kyc_verified_by = request.user
                customer_profile.save()
                messages.success(request, f'KYC approved for {user.get_full_name()}.')
        
        return redirect('admin_user_detail', user_id=user.id)
    
    context = {
        'page_title': f'User: {user.get_full_name()}',
        'user_obj': user,
        'customer_profile': customer_profile,
        'loan_applications': loan_applications,
        'audit_logs': audit_logs,
        'role_choices': User.ROLE_CHOICES,
    }
    
    return render(request, 'admin/user_detail.html', context)


@admin_required
def loan_management(request):
    """
    Loan Management - Overview of all loan applications
    """
    # Get filter parameters
    status_filter = request.GET.get('status', '')
    product_filter = request.GET.get('product', '')
    search_query = request.GET.get('q', '')
    
    # Base queryset
    applications = LoanApplication.objects.select_related(
        'customer', 'customer__user', 'loan_product'
    ).order_by('-created_at')
    
    # Apply filters
    if status_filter:
        applications = applications.filter(status=status_filter)
    
    if product_filter:
        applications = applications.filter(loan_product_id=product_filter)
    
    if search_query:
        applications = applications.filter(
            Q(application_number__icontains=search_query) |
            Q(customer__user__first_name__icontains=search_query) |
            Q(customer__user__last_name__icontains=search_query) |
            Q(customer__user__email__icontains=search_query)
        )
    
    # Pagination
    paginator = Paginator(applications, 25)
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)
    
    # Statistics
    total_apps = LoanApplication.objects.count()
    pending_apps = LoanApplication.objects.filter(
        status__in=[LoanApplication.SUBMITTED, LoanApplication.UNDER_REVIEW]
    ).count()
    approved_apps = LoanApplication.objects.filter(status=LoanApplication.APPROVED).count()
    disbursed_count = Loan.objects.count()
    
    context = {
        'page_title': 'Loan Management',
        'applications': page_obj,
        'products': LoanProduct.objects.filter(is_active=True),
        'status_choices': LoanApplication.APPLICATION_STATUS_CHOICES,
        'status_filter': status_filter,
        'product_filter': product_filter,
        'search_query': search_query,
        'stats': {
            'total': total_apps,
            'pending': pending_apps,
            'approved': approved_apps,
            'disbursed': disbursed_count,
        }
    }
    
    return render(request, 'admin/loan_management.html', context)


@admin_required
def loan_detail(request, application_id):
    """
    Loan Application Detail - View full application details
    """
    application = get_object_or_404(
        LoanApplication.objects.select_related('customer', 'customer__user', 'loan_product'),
        id=application_id
    )
    
    # Get related documents
    documents = application.documents.all() if hasattr(application, 'documents') else []
    
    # Get audit logs for this application
    audit_logs = AuditLog.objects.filter(
        model_name='LoanApplication',
        object_id=str(application.id)
    ).order_by('-timestamp')[:10]
    
    context = {
        'page_title': f'Application {application.application_number}',
        'application': application,
        'documents': documents,
        'audit_logs': audit_logs,
        'status_choices': LoanApplication.APPLICATION_STATUS_CHOICES,
    }
    
    return render(request, 'admin/loan_detail.html', context)


@admin_required
def product_management(request):
    """
    Loan Product Management - CRUD for loan products
    """
    products = LoanProduct.objects.all().order_by('-is_active', 'name')
    
    context = {
        'page_title': 'Loan Products',
        'products': products,
    }
    
    return render(request, 'admin/product_management.html', context)


@admin_required
def audit_logs(request):
    """
    Audit Logs - View system activity logs
    """
    # Get filter parameters
    action_filter = request.GET.get('action', '')
    model_filter = request.GET.get('model', '')
    search_query = request.GET.get('q', '')
    
    # Base queryset
    logs = AuditLog.objects.select_related('user').order_by('-timestamp')
    
    # Apply filters
    if action_filter:
        logs = logs.filter(action=action_filter)
    
    if model_filter:
        logs = logs.filter(model_name=model_filter)
    
    if search_query:
        logs = logs.filter(
            Q(user__email__icontains=search_query) |
            Q(model_name__icontains=search_query) |
            Q(description__icontains=search_query)
        )
    
    # Pagination
    paginator = Paginator(logs, 50)
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)
    
    # Get unique actions and models for filters
    actions = AuditLog.objects.values_list('action', flat=True).distinct().order_by('action')
    models = AuditLog.objects.values_list('model_name', flat=True).distinct().order_by('model_name')
    
    context = {
        'page_title': 'Audit Logs',
        'logs': page_obj,
        'actions': actions,
        'models': models,
        'action_filter': action_filter,
        'model_filter': model_filter,
        'search_query': search_query,
    }
    
    return render(request, 'admin/audit_logs.html', context)


@admin_required
def system_settings(request):
    """
    System Settings - Global system configuration including Odoo API
    """
    config = OdooConfig.get_active()

    if request.method == 'POST':
        action = request.POST.get('action', 'save')

        if action == 'save':
            # Get or create config
            if not config:
                config = OdooConfig()

            config.url = request.POST.get('odoo_url', '').strip()
            config.database = request.POST.get('odoo_database', '').strip()

            # Only update secrets if provided (not masked)
            api_key = request.POST.get('odoo_api_key', '').strip()
            if api_key and not api_key.startswith('****'):
                config.api_key = api_key

            webhook_secret = request.POST.get('odoo_webhook_secret', '').strip()
            if webhook_secret and not webhook_secret.startswith('****'):
                config.webhook_secret = webhook_secret

            config.webhook_url = request.POST.get('odoo_webhook_url', '').strip()

            config.is_active = request.POST.get('is_active') == 'on'
            config.updated_by = request.user
            config.save()

            messages.success(request, 'Odoo configuration saved successfully.')
            return redirect('admin_settings')

    # Prepare context
    context = {
        'page_title': 'System Settings',
        'config': config,
        'env_config': {
            'url': getattr(settings, 'ODOO_URL', ''),
            'database': getattr(settings, 'ODOO_DB', ''),
        }
    }

    return render(request, 'admin/system_settings.html', context)


@admin_required
def test_odoo_connection(request):
    """
    Test Odoo connection and return status as JSON.
    """
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)

    try:
        import json
        body = json.loads(request.body)
        use_test_values = body.get('use_test_values', False)

        if use_test_values:
            # Test with provided values without saving
            test_url = body.get('url', '').strip()
            test_api_key = body.get('api_key', '').strip()
            test_database = body.get('database', '').strip()
        else:
            # Test with saved configuration
            config = OdooConfig.get_active()
            if not config:
                return JsonResponse({
                    'status': 'error',
                    'message': 'No Odoo configuration found. Please save configuration first.'
                }, status=400)
            test_url = config.url
            test_api_key = config.api_key
            test_database = config.database

        if not test_url or not test_api_key:
            return JsonResponse({
                'status': 'error',
                'message': 'Odoo URL and API Key are required.'
            }, status=400)

        # Create temporary service to test connection
        from django.conf import settings
        original_url = getattr(settings, 'ODOO_URL', None)
        original_key = getattr(settings, 'ODOO_API_KEY', None)

        try:
            # Temporarily override settings for testing
            settings.ODOO_URL = test_url
            settings.ODOO_API_KEY = test_api_key
            if test_database:
                settings.ODOO_DB = test_database

            service = OdooSyncService()
            result = service.health_check()

            # Update config status if using saved config
            if not use_test_values:
                config.connection_status = 'connected'
                config.last_sync = timezone.now()
                config.last_error = ''
                config.save()

            return JsonResponse({
                'status': 'success',
                'message': 'Connection successful!',
                'version': result.get('version', 'unknown'),
                'details': result
            })

        except OdooAuthError as e:
            error_msg = f'Authentication failed: {str(e)}'
            if not use_test_values:
                config.connection_status = 'error'
                config.last_error = error_msg
                config.save()
            return JsonResponse({
                'status': 'error',
                'message': error_msg
            }, status=401)

        except OdooConnectionError as e:
            error_msg = f'Connection failed: {str(e)}'
            if not use_test_values:
                config.connection_status = 'error'
                config.last_error = error_msg
                config.save()
            return JsonResponse({
                'status': 'error',
                'message': error_msg
            }, status=503)

        except OdooSyncError as e:
            error_msg = f'Odoo error: {str(e)}'
            if not use_test_values:
                config.connection_status = 'error'
                config.last_error = error_msg
                config.save()
            return JsonResponse({
                'status': 'error',
                'message': error_msg
            }, status=500)

        finally:
            # Restore original settings
            if original_url:
                settings.ODOO_URL = original_url
            if original_key:
                settings.ODOO_API_KEY = original_key

    except json.JSONDecodeError:
        return JsonResponse({
            'status': 'error',
            'message': 'Invalid JSON in request body.'
        }, status=400)

    except Exception as e:
        return JsonResponse({
            'status': 'error',
            'message': f'Unexpected error: {str(e)}'
        }, status=500)


@admin_required
def api_status(request):
    """
    API Status - Check system health and integrations
    """
    # Check Odoo integration status
    config = OdooConfig.get_active()
    if config:
        odoo_status = config.connection_status
    else:
        odoo_status = 'not_configured'

    # Check various system components
    status = {
        'database': 'OK',
        'odoo_integration': odoo_status,
        'sms_service': 'Unknown',
        'email_service': 'Unknown',
    }

    return JsonResponse(status)
