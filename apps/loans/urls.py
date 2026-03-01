"""
Loans URL Configuration
"""
from django.urls import path
from . import views

app_name = 'loans'

urlpatterns = [
    path('', views.LoanDashboardView.as_view(), name='dashboard'),
    path('applications/', views.LoanApplicationListView.as_view(), name='application_list'),
    path('applications/<int:pk>/', views.LoanApplicationDetailView.as_view(), name='application_detail'),
    path('loans/', views.LoanListView.as_view(), name='loan_list'),
    path('loans/<int:pk>/', views.LoanDetailView.as_view(), name='loan_detail'),
    path('customers/', views.CustomerListView.as_view(), name='customer_list'),
    path('customers/<int:pk>/', views.CustomerDetailView.as_view(), name='customer_detail'),
]
