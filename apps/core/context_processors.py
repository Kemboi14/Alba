"""
Core Context Processors
Adds common variables to all templates
"""
from django.conf import settings
from .models import Notification


def company_settings(request):
    """Add company settings to context"""
    return {
        'COMPANY_NAME': settings.COMPANY_NAME,
        'COMPANY_EMAIL': settings.COMPANY_EMAIL,
        'COMPANY_PHONE': settings.COMPANY_PHONE,
        'BASE_CURRENCY': settings.BASE_CURRENCY,
    }
