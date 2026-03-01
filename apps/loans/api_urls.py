"""
URL Configuration for M-Pesa API Callbacks
"""
from django.urls import path
from apps.loans import api_views

app_name = 'api'

urlpatterns = [
    # M-Pesa C2B callbacks
    path('mpesa/c2b/confirmation/', api_views.mpesa_c2b_confirmation, name='mpesa_c2b_confirmation'),
    path('mpesa/c2b/validation/', api_views.mpesa_c2b_validation, name='mpesa_c2b_validation'),
    
    # M-Pesa B2C callbacks
    path('mpesa/b2c/result/', api_views.mpesa_b2c_result, name='mpesa_b2c_result'),
    path('mpesa/b2c/timeout/', api_views.mpesa_timeout, name='mpesa_b2c_timeout'),
    
    # M-Pesa transaction status
    path('mpesa/status/result/', api_views.mpesa_status_result, name='mpesa_status_result'),
]
