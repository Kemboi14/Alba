"""
Celery configuration for Alba Capital ERP System.
Used for asynchronous task processing (emails, SMS, reports, etc.)
"""
import os
from celery import Celery
from celery.schedules import crontab

# Set the default Django settings module for the 'celery' program.
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

app = Celery('alba_erp')

# Using a string here means the worker doesn't have to serialize
# the configuration object to child processes.
app.config_from_object('django.conf:settings', namespace='CELERY')

# Load task modules from all registered Django apps.
app.autodiscover_tasks()

# Periodic Tasks Configuration
app.conf.beat_schedule = {
    # Daily interest accrual for loans
    'accrue-loan-interest-daily': {
        'task': 'apps.loans.tasks.accrue_daily_interest',
        'schedule': crontab(hour=0, minute=5),  # Run at 00:05 every day
    },
    
    # Monthly investor interest calculation
    'calculate-investor-interest-monthly': {
        'task': 'apps.investors.tasks.calculate_monthly_interest',
        'schedule': crontab(day_of_month=1, hour=0, minute=30),  # First day of month
    },
    
    # Send payment reminders
    'send-payment-reminders': {
        'task': 'apps.loans.tasks.send_payment_reminders',
        'schedule': crontab(hour=9, minute=0),  # 9 AM daily
    },
    
    # Send overdue alerts
    'send-overdue-alerts': {
        'task': 'apps.loans.tasks.send_overdue_alerts',
        'schedule': crontab(hour=10, minute=0),  # 10 AM daily
    },
    
    # Monthly depreciation calculation
    'calculate-monthly-depreciation': {
        'task': 'apps.assets.tasks.calculate_monthly_depreciation',
        'schedule': crontab(day_of_month=1, hour=1, minute=0),  # First day of month
    },
    
    # Generate monthly investor statements
    'generate-investor-statements': {
        'task': 'apps.investors.tasks.generate_monthly_statements',
        'schedule': crontab(day_of_month=1, hour=2, minute=0),  # First day of month
    },
}


@app.task(bind=True, ignore_result=True)
def debug_task(self):
    """Debug task for testing Celery configuration"""
    print(f'Request: {self.request!r}')
