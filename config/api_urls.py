"""
API URL Configuration
Centralized API endpoint routing for all modules
"""
from django.urls import path, include

urlpatterns = [
    path('core/', include('apps.core.api.urls')),
    path('accounting/', include('apps.accounting.api.urls')),
    path('loans/', include('apps.loans.api.urls')),
    path('investors/', include('apps.investors.api.urls')),
    path('payroll/', include('apps.payroll.api.urls')),
    path('crm/', include('apps.crm.api.urls')),
    path('assets/', include('apps.assets.api.urls')),
    path('reporting/', include('apps.reporting.api.urls')),
]
