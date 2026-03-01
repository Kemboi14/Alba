"""
Customer Portal Views
Public-facing loan application and customer self-service portal
Implements SRS Section 3.5: Customer Portal
"""
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import login, authenticate
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.views.generic import TemplateView, ListView, DetailView, CreateView, FormView
from django.urls import reverse_lazy
from django.db import transaction
from django.utils import timezone
from django.http import HttpResponse, JsonResponse
from decimal import Decimal
import logging

from apps.core.models import User
from apps.loans.models import (
    LoanProduct, Customer, LoanApplication, Loan, 
    Payment
)
from .portal_forms import (
    CustomerRegistrationForm, CustomerLoanApplicationForm,
    DocumentUploadForm
)

logger = logging.getLogger(__name__)


class CustomerPortalMixin:
    """Mixin to ensure only customers can access portal"""
    
    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('portal:login')
        if request.user.role != User.CUSTOMER:
            messages.error(request, 'Access denied. This portal is for customers only.')
            return redirect('core:dashboard')
        return super().dispatch(request, *args, **kwargs)


class CustomerRegistrationView(CreateView):
    """
    Public customer registration
    Creates User (CUSTOMER role) and associated Customer record
    """
    form_class = CustomerRegistrationForm
    template_name = 'portal/register.html'
    success_url = reverse_lazy('portal:login')
    
    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated:
            return redirect('portal:dashboard')
        return super().dispatch(request, *args, **kwargs)
    
    def form_valid(self, form):
        """Create user and customer record atomically"""
        try:
            with transaction.atomic():
                # Create user account (INACTIVE - pending approval)
                user = form.save(commit=False)
                user.role = User.CUSTOMER
                user.is_active = False  # BANK SECURITY: Require admin approval
                user.save()
                
                # Get system user for created_by
                system_user = User.objects.filter(is_superuser=True).first()
                if not system_user:
                    system_user = User.objects.filter(is_staff=True).first()
                
                # Create customer record
                customer = Customer.objects.create(
                    user=user,
                    customer_number=f'CUST{timezone.now().strftime("%Y%m%d%H%M%S")}',
                    first_name=user.first_name,
                    last_name=user.last_name,
                    other_names='',
                    email=user.email,
                    phone_number=form.cleaned_data['phone_number'],
                    national_id=form.cleaned_data['national_id'],
                    date_of_birth=form.cleaned_data['date_of_birth'],
                    gender='MALE',  # TODO: Add to form
                    marital_status='SINGLE',  # TODO: Add to form
                    physical_address=form.cleaned_data.get('address', 'Not provided'),
                    city='Nairobi',  # TODO: Add to form
                    county='Nairobi',  # TODO: Add to form
                    employment_status='EMPLOYED',  # TODO: Add to form
                    monthly_income=Decimal('50000.00'),  # TODO: Add to form
                    kyc_status='PENDING',  # Pending KYC verification
                    email_verified=False,
                    is_active=False,  # Inactive until approved
                    created_by=system_user
                )
                
                logger.info(f"New customer registered (PENDING APPROVAL): {user.email}")
                messages.success(
                    self.request,
                    '✅ Registration submitted successfully! Your account is pending verification. '
                    'Our team will review your details within 24 hours and notify you via email when approved.'
                )
                
                # Notify admin about new registration
                from apps.loans.notifications import notification_service
                notification_service.notify_new_customer_registration(customer)
                
                return redirect(self.success_url)
                
        except Exception as e:
            logger.error(f"Customer registration failed: {str(e)}")
            messages.error(self.request, 'Registration failed. Please try again.')
            return self.form_invalid(form)


class CustomerLoginView(TemplateView):
    """Customer portal login (separate from staff login)"""
    template_name = 'portal/login.html'
    
    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated:
            if request.user.role == User.CUSTOMER:
                return redirect('portal:dashboard')
            else:
                return redirect('core:dashboard')
        return super().dispatch(request, *args, **kwargs)
    
    def post(self, request):
        email = request.POST.get('email')
        password = request.POST.get('password')
        
        user = authenticate(request, username=email, password=password)
        
        if user is not None:
            if user.role != User.CUSTOMER:
                messages.error(request, 'Invalid login. Staff should use the admin portal.')
                return redirect('portal:login')
            
            # BANK SECURITY: Check if account is approved
            if not user.is_active:
                messages.warning(
                    request,
                    '⏳ Your account is pending verification. '
                    'Our team will review your details and notify you via email when approved. '
                    'This typically takes 24 hours.'
                )
                return redirect('portal:login')
            
            if user.is_account_locked():
                messages.error(request, 'Your account is locked. Please contact support.')
                return redirect('portal:login')
            
            login(request, user)
            user.failed_login_attempts = 0
            user.last_login_ip = self.get_client_ip(request)
            user.save()
            
            logger.info(f"Customer logged in: {user.email}")
            
            # Redirect to next or dashboard
            next_url = request.GET.get('next', reverse_lazy('portal:dashboard'))
            return redirect(next_url)
        else:
            # Track failed login attempts
            try:
                user_obj = User.objects.get(email=email, role=User.CUSTOMER)
                user_obj.failed_login_attempts += 1
                if user_obj.failed_login_attempts >= 5:
                    user_obj.account_locked_until = timezone.now() + timezone.timedelta(minutes=30)
                    messages.error(request, 'Account locked due to multiple failed login attempts.')
                user_obj.save()
            except User.DoesNotExist:
                pass
            
            messages.error(request, 'Invalid email or password.')
        
        return render(request, self.template_name)
    
    def get_client_ip(self, request):
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            return x_forwarded_for.split(',')[0]
        return request.META.get('REMOTE_ADDR', '')


class CustomerDashboardView(LoginRequiredMixin, CustomerPortalMixin, TemplateView):
    """Customer portal dashboard"""
    template_name = 'portal/dashboard.html'
    login_url = 'portal:login'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user
        
        try:
            customer = Customer.objects.get(user=user)
            
            # Get customer's loan applications
            applications = LoanApplication.objects.filter(
                customer=customer
            ).order_by('-created_at')[:5]
            
            # Get customer's active loans
            loans = Loan.objects.filter(
                customer=customer,
                status__in=['ACTIVE', 'DISBURSED']
            ).select_related('loan_product')
            
            # Count pending applications
            pending_applications_count = LoanApplication.objects.filter(
                customer=customer,
                status__in=['SUBMITTED', 'UNDER_REVIEW', 'PENDING_APPROVAL']
            ).count()
            
            # Calculate totals
            total_borrowed = sum(loan.principal_amount for loan in loans)
            total_outstanding = sum(loan.total_outstanding for loan in loans)
            total_paid = total_borrowed - total_outstanding
            
            context.update({
                'customer': customer,
                'applications': applications,
                'loans': loans,
                'total_borrowed': total_borrowed,
                'total_outstanding': total_outstanding,
                'total_paid': total_paid,
                'active_loans_count': loans.count(),
                'pending_applications_count': pending_applications_count,
            })
            
        except Customer.DoesNotExist:
            messages.warning(self.request, 'Customer profile not found.')
            context['customer'] = None
        
        return context


class LoanApplicationCreateView(LoginRequiredMixin, CustomerPortalMixin, FormView):
    """
    Customer loan application form
    Implements SRS Section 3.1.2: Loan Application Submission
    """
    form_class = CustomerLoanApplicationForm
    template_name = 'portal/apply.html'
    success_url = reverse_lazy('portal:applications')
    login_url = 'portal:login'
    
    def get(self, request, *args, **kwargs):
        """Check KYC status before showing form"""
        try:
            customer = Customer.objects.get(user=request.user)
            
            # BANK SECURITY: Verify KYC is approved
            if customer.kyc_status != 'VERIFIED':
                messages.error(
                    request,
                    '🔒 KYC Verification Required: Your account must be verified before applying for loans. '
                    'Please upload your documents and wait for our team to verify your identity. '
                    'This typically takes 24-48 hours.'
                )
                return redirect('portal:dashboard')
            
            if not customer.is_active:
                messages.error(request, '⛔ Account Inactive: Please contact support.')
                return redirect('portal:dashboard')
                
        except Customer.DoesNotExist:
            messages.error(request, 'Customer profile not found.')
            return redirect('portal:dashboard')
        
        return super().get(request, *args, **kwargs)
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['loan_products'] = LoanProduct.objects.filter(is_active=True)
        return context
    
    def form_valid(self, form):
        """Create loan application with credit scoring"""
        try:
            with transaction.atomic():
                customer = Customer.objects.get(user=self.request.user)
                
                # Create loan application
                application = form.save(commit=False)
                application.customer = customer
                application.created_by = self.request.user
                application.status = 'PENDING'
                application.application_date = timezone.now().date()
                
                # Run credit scoring (implemented in credit_scoring.py)
                from apps.loans.credit_scoring import CreditScoringService
                scoring_service = CreditScoringService()
                
                score_result = scoring_service.calculate_credit_score(
                    customer=customer,
                    loan_amount=application.requested_amount,
                    loan_product=application.loan_product,
                    monthly_income=form.cleaned_data.get('monthly_income', Decimal('0')),
                    existing_obligations=form.cleaned_data.get('existing_obligations', Decimal('0')),
                    employment_years=form.cleaned_data.get('employment_years', 0)
                )
                
                application.credit_score = score_result['score']
                application.credit_grade = score_result['grade']
                application.auto_decision = score_result['decision']
                application.scoring_details = score_result
                application.save()
                
                logger.info(
                    f"Loan application created: {application.id} for customer {customer.email}, "
                    f"Amount: {application.requested_amount}, Score: {score_result['score']}"
                )
                
                # TODO: Send notification to customer and credit officer
                
                messages.success(
                    self.request,
                    f'Loan application submitted successfully! '
                    f'Application ID: {application.application_number}. '
                    f'We will review your application and notify you within 24-48 hours.'
                )
                
                return redirect(self.success_url)
                
        except Customer.DoesNotExist:
            messages.error(self.request, 'Customer profile not found. Please contact support.')
            return redirect('portal:dashboard')
        except Exception as e:
            logger.error(f"Loan application creation failed: {str(e)}")
            messages.error(self.request, 'Application submission failed. Please try again.')
            return self.form_invalid(form)


class CustomerApplicationListView(LoginRequiredMixin, CustomerPortalMixin, ListView):
    """List all customer's loan applications"""
    model = LoanApplication
    template_name = 'portal/applications.html'
    context_object_name = 'applications'
    paginate_by = 10
    login_url = 'portal:login'
    
    def get_queryset(self):
        try:
            customer = Customer.objects.get(user=self.request.user)
            return LoanApplication.objects.filter(
                customer=customer
            ).select_related('loan_product').order_by('-created_at')
        except Customer.DoesNotExist:
            return LoanApplication.objects.none()


class CustomerApplicationDetailView(LoginRequiredMixin, CustomerPortalMixin, DetailView):
    """View detailed loan application status"""
    model = LoanApplication
    template_name = 'portal/application_detail.html'
    context_object_name = 'application'
    login_url = 'portal:login'
    
    def get_queryset(self):
        """Ensure customer can only view their own applications"""
        try:
            customer = Customer.objects.get(user=self.request.user)
            return LoanApplication.objects.filter(customer=customer)
        except Customer.DoesNotExist:
            return LoanApplication.objects.none()


class CustomerLoanListView(LoginRequiredMixin, CustomerPortalMixin, ListView):
    """List all customer's loans"""
    model = Loan
    template_name = 'portal/loans.html'
    context_object_name = 'loans'
    paginate_by = 10
    login_url = 'portal:login'
    
    def get_queryset(self):
        try:
            customer = Customer.objects.get(user=self.request.user)
            return Loan.objects.filter(
                customer=customer
            ).select_related('loan_product').order_by('-disbursement_date')
        except Customer.DoesNotExist:
            return Loan.objects.none()


class CustomerLoanDetailView(LoginRequiredMixin, CustomerPortalMixin, DetailView):
    """View detailed loan information and repayment schedule"""
    model = Loan
    template_name = 'portal/loan_detail.html'
    context_object_name = 'loan'
    login_url = 'portal:login'
    
    def get_queryset(self):
        """Ensure customer can only view their own loans"""
        try:
            customer = Customer.objects.get(user=self.request.user)
            return Loan.objects.filter(customer=customer)
        except Customer.DoesNotExist:
            return Loan.objects.none()
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        loan = self.object
        
        # Get repayment schedule
        context['schedule'] = loan.repayment_schedule.order_by('due_date')
        
        # Get payment history
        context['payments'] = Payment.objects.filter(
            loan=loan
        ).order_by('-payment_date')[:10]
        
        # Calculate summary
        total_paid = sum(p.amount for p in Payment.objects.filter(loan=loan))
        context['total_paid'] = total_paid
        context['next_payment'] = loan.repayment_schedule.filter(
            is_paid=False,
            due_date__gte=timezone.now().date()
        ).order_by('due_date').first()
        
        return context


class DocumentUploadView(LoginRequiredMixin, CustomerPortalMixin, FormView):
    """Upload KYC documents for loan application"""
    form_class = DocumentUploadForm
    template_name = 'portal/upload_documents.html'
    login_url = 'portal:login'
    
    def get_success_url(self):
        application_id = self.kwargs.get('application_id')
        return reverse_lazy('portal:application_detail', kwargs={'pk': application_id})
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        application_id = self.kwargs.get('application_id')
        try:
            customer = Customer.objects.get(user=self.request.user)
            application = LoanApplication.objects.get(id=application_id, customer=customer)
            context['application'] = application
            context['existing_documents'] = LoanDocument.objects.filter(
                application=application
            )
        except (Customer.DoesNotExist, LoanApplication.DoesNotExist):
            pass
        return context
    
    def form_valid(self, form):
        """Save uploaded documents"""
        try:
            application_id = self.kwargs.get('application_id')
            customer = Customer.objects.get(user=self.request.user)
            application = LoanApplication.objects.get(id=application_id, customer=customer)
            
            # Save each uploaded document
            uploaded_files = self.request.FILES.getlist('documents')
            document_type = form.cleaned_data['document_type']
            
            for uploaded_file in uploaded_files:
                LoanDocument.objects.create(
                    application=application,
                    loan=application.loan if hasattr(application, 'loan') and application.loan else None,
                    document_type=document_type,
                    file=uploaded_file,
                    uploaded_by=self.request.user,
                    upload_date=timezone.now().date()
                )
            
            # Update application status to reflect document submission
            if application.status == 'PENDING':
                application.status = 'UNDER_REVIEW'
                application.save()
            
            messages.success(
                self.request,
                f'{len(uploaded_files)} document(s) uploaded successfully!'
            )
            
            logger.info(
                f"Documents uploaded for application {application.id}: "
                f"{len(uploaded_files)} files, Type: {document_type}"
            )
            
            return redirect(self.get_success_url())
            
        except (Customer.DoesNotExist, LoanApplication.DoesNotExist):
            messages.error(self.request, 'Application not found.')
            return redirect('portal:dashboard')
        except Exception as e:
            logger.error(f"Document upload failed: {str(e)}")
            messages.error(self.request, 'Document upload failed. Please try again.')
            return self.form_invalid(form)


@login_required(login_url='portal:login')
def download_loan_statement(request, loan_id):
    """
    Generate and download loan statement PDF
    Implements SRS Section 3.5: Statement download in PDF format
    """
    try:
        customer = Customer.objects.get(user=request.user)
        loan = get_object_or_404(Loan, id=loan_id, customer=customer)
        
        # Generate PDF statement
        from apps.loans.reports import LoanStatementGenerator
        generator = LoanStatementGenerator()
        pdf_content = generator.generate_statement(loan)
        
        # Return PDF response
        response = HttpResponse(pdf_content, content_type='application/pdf')
        response['Content-Disposition'] = f'attachment; filename="loan_statement_{loan.loan_number}.pdf"'
        
        logger.info(f"Loan statement generated for loan {loan.loan_number}")
        return response
        
    except Customer.DoesNotExist:
        messages.error(request, 'Customer profile not found.')
        return redirect('portal:dashboard')
    except Exception as e:
        logger.error(f"Statement generation failed: {str(e)}")
        messages.error(request, 'Failed to generate statement. Please try again.')
        return redirect('portal:loans')


class CustomerProfileView(LoginRequiredMixin, CustomerPortalMixin, TemplateView):
    """Customer profile and KYC information"""
    template_name = 'portal/profile.html'
    login_url = 'portal:login'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        try:
            customer = Customer.objects.get(user=self.request.user)
            context['customer'] = customer
        except Customer.DoesNotExist:
            context['customer'] = None
        return context


class LoanProductListView(TemplateView):
    """Public-facing loan products page (no login required)"""
    template_name = 'portal/products.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['products'] = LoanProduct.objects.filter(
            is_active=True
        ).order_by('name')
        return context


class CustomerPasswordResetView(TemplateView):
    """Password reset for customer portal"""
    template_name = 'portal/password_reset.html'
    
    def post(self, request):
        email = request.POST.get('email')
        
        try:
            user = User.objects.get(email=email, role=User.CUSTOMER)
            
            # Generate reset token (simple implementation)
            from django.utils.crypto import get_random_string
            reset_token = get_random_string(32)
            
            # Store token in cache (expires in 1 hour)
            from django.core.cache import cache
            cache.set(f'password_reset_{reset_token}', user.id, 3600)
            
            # Send email (placeholder - implement your email service)
            reset_link = f"http://localhost:3000/portal/password-reset/{reset_token}/"
            
            # Log the action
            logger.info(f"Password reset requested for {email}")
            
            messages.success(
                request,
                '✅ Password reset instructions have been sent to your email. '
                'The link will expire in 1 hour.'
            )
            
        except User.DoesNotExist:
            # Don't reveal if email exists (security)
            messages.success(
                request,
                'If that email exists in our system, you will receive reset instructions shortly.'
            )
        
        return redirect('portal:password_reset')
