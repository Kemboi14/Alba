"""
URL Configuration for Customer Portal
"""
from django.urls import path
from django.views.generic import TemplateView
from apps.loans import portal_views

app_name = 'portal'

urlpatterns = [
    # Public pages
    path('', TemplateView.as_view(template_name='portal/index.html'), name='index'),
    path('products/', portal_views.LoanProductListView.as_view(), name='products'),
    path('calculator/', TemplateView.as_view(template_name='portal/loan_calculator.html'), name='calculator'),
    path('register/', portal_views.CustomerRegistrationView.as_view(), name='register'),
    path('login/', portal_views.CustomerLoginView.as_view(), name='login'),
    path('password-reset/', portal_views.CustomerPasswordResetView.as_view(), name='password_reset'),
    
    # Customer dashboard
    path('dashboard/', portal_views.CustomerDashboardView.as_view(), name='dashboard'),
    path('profile/', portal_views.CustomerProfileView.as_view(), name='profile'),
    
    # Loan applications
    path('apply/', portal_views.LoanApplicationCreateView.as_view(), name='apply'),
    path('applications/', portal_views.CustomerApplicationListView.as_view(), name='applications'),
    path('applications/<int:pk>/', portal_views.CustomerApplicationDetailView.as_view(), name='application_detail'),
    
    # Loans
    path('loans/', portal_views.CustomerLoanListView.as_view(), name='loans'),
    path('loans/<int:pk>/', portal_views.CustomerLoanDetailView.as_view(), name='loan_detail'),
    path('loans/<int:loan_id>/statement/', portal_views.download_loan_statement, name='loan_statement'),
    
    # Documents
    path('documents/upload/', portal_views.DocumentUploadView.as_view(), name='upload_documents'),
]
