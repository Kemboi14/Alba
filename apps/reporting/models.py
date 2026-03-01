"""
Reporting Models: Saved reports, schedules
"""
from django.db import models
from apps.core.models import User


class SavedReport(models.Model):
    """User-saved reports"""
    REPORT_TYPE_CHOICES = [
        ('TRIAL_BALANCE', 'Trial Balance'),
        ('BALANCE_SHEET', 'Balance Sheet'),
        ('INCOME_STATEMENT', 'Income Statement'),
        ('LOAN_PORTFOLIO', 'Loan Portfolio'),
        ('NPL_REPORT', 'NPL Report'),
        ('INVESTOR_SUMMARY', 'Investor Summary'),
        ('CUSTOM', 'Custom Report'),
    ]
    
    name = models.CharField(max_length=200)
    report_type = models.CharField(max_length=50, choices=REPORT_TYPE_CHOICES)
    parameters = models.JSONField(default=dict)
    
    created_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name='saved_reports')
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'reporting_saved_reports'
        verbose_name = 'Saved Report'
        verbose_name_plural = 'Saved Reports'
    
    def __str__(self):
        return self.name


class ReportSchedule(models.Model):
    """Scheduled automatic reports"""
    report = models.ForeignKey(SavedReport, on_delete=models.CASCADE, related_name='schedules')
    frequency = models.CharField(
        max_length=20,
        choices=[
            ('DAILY', 'Daily'),
            ('WEEKLY', 'Weekly'),
            ('MONTHLY', 'Monthly'),
        ]
    )
    recipients = models.JSONField(default=list, help_text='List of email addresses')
    is_active = models.BooleanField(default=True)
    
    last_run = models.DateTimeField(null=True, blank=True)
    next_run = models.DateTimeField()
    
    class Meta:
        db_table = 'reporting_schedules'
    
    def __str__(self):
        return f"{self.report.name} - {self.frequency}"
