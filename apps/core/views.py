"""
Core Views - Authentication, Dashboard, User Management
"""
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import login, logout, authenticate
from django.contrib.auth.mixins import LoginRequiredMixin, PermissionRequiredMixin
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.views.generic import TemplateView, ListView, DetailView, CreateView, UpdateView
from django.urls import reverse_lazy
from django.utils import timezone
from django.http import JsonResponse
from .models import User, Role, AuditLog, Notification
from .forms import LoginForm, UserForm, ChangePasswordForm


class LoginView(TemplateView):
    """User login view"""
    template_name = 'core/login.html'
    
    def get(self, request, *args, **kwargs):
        if request.user.is_authenticated:
            # Redirect based on user type
            if request.user.role == 'CUSTOMER' and not request.user.is_staff:
                return redirect('portal:dashboard')
            return redirect('core:dashboard')
        return super().get(request, *args, **kwargs)
    
    def post(self, request):
        form = LoginForm(request.POST)
        if form.is_valid():
            email = form.cleaned_data['email']
            password = form.cleaned_data['password']
            user = authenticate(request, username=email, password=password)
            
            if user is not None:
                if user.is_account_locked():
                    messages.error(request, 'Your account is locked. Please contact administrator.')
                    return redirect('core:login')
                
                # Check if MFA is enabled for this user
                if user.mfa_enabled:
                    # Redirect to MFA verification
                    request.session['mfa_user_id'] = user.id
                    logger.info(f"MFA verification required for {user.email}")
                    return redirect('core:mfa_verify')
                
                # No MFA required - complete login
                login(request, user)
                user.failed_login_attempts = 0
                user.last_login_ip = self.get_client_ip(request)
                user.save()
                
                # Log the login
                AuditLog.objects.create(
                    user=user,
                    action_type='LOGIN',
                    model_name='User',
                    object_id=str(user.id),
                    module='core',
                    description=f'User logged in successfully',
                    ip_address=self.get_client_ip(request),
                    user_agent=request.META.get('HTTP_USER_AGENT', '')
                )
                
                # Redirect based on user type
                if user.role == 'CUSTOMER' and not user.is_staff:
                    return redirect('portal:dashboard')
                return redirect('core:dashboard')
            else:
                messages.error(request, 'Invalid email or password.')
        
        return render(request, self.template_name, {'form': form})
    
    def get_client_ip(self, request):
        """Get client IP address"""
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip = x_forwarded_for.split(',')[0]
        else:
            ip = request.META.get('REMOTE_ADDR')
        return ip


class LogoutView(LoginRequiredMixin, TemplateView):
    """User logout view"""
    
    def get(self, request):
        # Log the logout
        AuditLog.objects.create(
            user=request.user,
            action_type='LOGOUT',
            model_name='User',
            object_id=str(request.user.id),
            module='core',
            description='User logged out',
            ip_address=self.get_client_ip(request),
            user_agent=request.META.get('HTTP_USER_AGENT', '')
        )
        logout(request)
        messages.success(request, 'You have been logged out successfully.')
        return redirect('core:login')
    
    def get_client_ip(self, request):
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip = x_forwarded_for.split(',')[0]
        else:
            ip = request.META.get('REMOTE_ADDR')
        return ip


class DashboardView(LoginRequiredMixin, TemplateView):
    """Main dashboard view"""
    template_name = 'core/dashboard.html'
    
    def dispatch(self, request, *args, **kwargs):
        """Redirect customers to their portal dashboard"""
        if request.user.is_authenticated and request.user.role == 'CUSTOMER' and not request.user.is_staff:
            return redirect('portal:dashboard')
        return super().dispatch(request, *args, **kwargs)
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user
        
        # Add dashboard statistics here
        context['unread_notifications'] = user.notifications.filter(is_read=False).count()
        
        # For admins/credit officers, show pending approvals and statistics
        if user.is_staff or user.role in ['ADMINISTRATOR', 'CREDIT_OFFICER']:
            from apps.loans.models import Customer, LoanApplication, Loan, Payment
            from django.db.models import Sum, Count, Q
            from datetime import date
            
            # Pending customer approvals (inactive accounts)
            context['pending_customers'] = Customer.objects.filter(
                is_active=False, 
                kyc_status='PENDING'
            ).order_by('-created_at')[:5]
            
            context['pending_customers_count'] = Customer.objects.filter(
                is_active=False,
                kyc_status='PENDING'
            ).count()
            
            # Pending loan applications
            context['pending_loan_applications'] = LoanApplication.objects.filter(
                status__in=['SUBMITTED', 'UNDER_REVIEW', 'PENDING_APPROVAL']
            ).select_related('customer', 'loan_product').order_by('-created_at')[:5]
            
            context['pending_loan_applications_count'] = LoanApplication.objects.filter(
                status__in=['SUBMITTED', 'UNDER_REVIEW', 'PENDING_APPROVAL']
            ).count()
            
            # Dashboard statistics
            # Total active loans
            context['total_loans'] = Loan.objects.filter(
                status__in=['ACTIVE', 'OVERDUE', 'NPL', 'PENDING_DISBURSEMENT']
            ).count()
            
            # Outstanding balance (sum of all outstanding amounts)
            outstanding = Loan.objects.filter(
                status__in=['ACTIVE', 'OVERDUE', 'NPL']
            ).aggregate(total=Sum('total_outstanding'))
            context['outstanding_balance'] = outstanding['total'] or 0
            
            # Pending applications (already have count above)
            context['pending_applications'] = context['pending_loan_applications_count']
            
            # Collections today
            today = date.today()
            collections = Payment.objects.filter(
                payment_date=today
            ).aggregate(total=Sum('amount'))
            context['collections_today'] = collections['total'] or 0
            
            # Recent applications (last 10 regardless of status)
            context['recent_applications'] = LoanApplication.objects.select_related(
                'customer', 'loan_product'
            ).order_by('-created_at')[:10]
        
        return context


class ProfileView(LoginRequiredMixin, TemplateView):
    """User profile view"""
    template_name = 'core/profile.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['user'] = self.request.user
        return context


class ChangePasswordView(LoginRequiredMixin, TemplateView):
    """Change password view"""
    template_name = 'core/change_password.html'
    
    def post(self, request):
        form = ChangePasswordForm(request.user, request.POST)
        if form.is_valid():
            user = form.save()
            messages.success(request, 'Your password has been changed successfully.')
            return redirect('core:profile')
        return render(request, self.template_name, {'form': form})


class UserListView(LoginRequiredMixin, PermissionRequiredMixin, ListView):
    """List all users"""
    model = User
    template_name = 'core/user_list.html'
    context_object_name = 'users'
    paginate_by = 25
    permission_required = 'core.can_manage_users'


class UserDetailView(LoginRequiredMixin, PermissionRequiredMixin, DetailView):
    """User detail view"""
    model = User
    template_name = 'core/user_detail.html'
    context_object_name = 'user_detail'
    permission_required = 'core.can_manage_users'


class UserCreateView(LoginRequiredMixin, PermissionRequiredMixin, CreateView):
    """Create new user"""
    model = User
    form_class = UserForm
    template_name = 'core/user_form.html'
    success_url = reverse_lazy('core:user_list')
    permission_required = 'core.can_manage_users'
    
    def form_valid(self, form):
        form.instance.created_by = self.request.user
        messages.success(self.request, 'User created successfully.')
        return super().form_valid(form)


class UserUpdateView(LoginRequiredMixin, PermissionRequiredMixin, UpdateView):
    """Update user"""
    model = User
    form_class = UserForm
    template_name = 'core/user_form.html'
    success_url = reverse_lazy('core:user_list')
    permission_required = 'core.can_manage_users'


class RoleListView(LoginRequiredMixin, PermissionRequiredMixin, ListView):
    """List all roles"""
    model = Role
    template_name = 'core/role_list.html'
    context_object_name = 'roles'
    permission_required = 'core.can_manage_roles'


class RoleDetailView(LoginRequiredMixin, PermissionRequiredMixin, DetailView):
    """Role detail view"""
    model = Role
    template_name = 'core/role_detail.html'
    context_object_name = 'role'
    permission_required = 'core.can_manage_roles'


class AuditLogListView(LoginRequiredMixin, PermissionRequiredMixin, ListView):
    """List audit logs"""
    model = AuditLog
    template_name = 'core/audit_log_list.html'
    context_object_name = 'logs'
    paginate_by = 50
    permission_required = 'core.can_view_audit_logs'
    
    def get_queryset(self):
        queryset = super().get_queryset()
        # Add filters here based on request parameters
        return queryset


class NotificationListView(LoginRequiredMixin, ListView):
    """List user notifications"""
    model = Notification
    template_name = 'core/notification_list.html'
    context_object_name = 'notifications'
    paginate_by = 20
    
    def get_queryset(self):
        return self.request.user.notifications.all()


@login_required
def mark_notification_read(request, pk):
    """Mark notification as read"""
    notification = get_object_or_404(Notification, pk=pk, user=request.user)
    notification.mark_as_read()
    return JsonResponse({'status': 'success'})
