"""
Accounting App Configuration
"""
from django.apps import AppConfig


class AccountingConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.accounting'
    verbose_name = 'Accounting'
    
    def ready(self):
        """Import signals when app is ready"""
        import apps.accounting.signals
