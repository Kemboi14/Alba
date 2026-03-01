"""
CRM Models: Lead tracking, customer interactions, sales pipeline
"""
from django.db import models
from phonenumber_field.modelfields import PhoneNumberField
from apps.core.models import User


class Lead(models.Model):
    """Sales leads and prospects"""
    STATUS_CHOICES = [
        ('NEW', 'New'),
        ('CONTACTED', 'Contacted'),
        ('QUALIFIED', 'Qualified'),
        ('PROPOSAL', 'Proposal Sent'),
        ('NEGOTIATION', 'Negotiation'),
        ('WON', 'Won'),
        ('LOST', 'Lost'),
    ]
    
    SOURCE_CHOICES = [
        ('WEBSITE', 'Website'),
        ('REFERRAL', 'Referral'),
        ('WALK_IN', 'Walk-in'),
        ('PHONE', 'Phone Call'),
        ('SOCIAL_MEDIA', 'Social Media'),
        ('OTHER', 'Other'),
    ]
    
    lead_number = models.CharField(max_length=20, unique=True)
    first_name = models.CharField(max_length=100)
    last_name = models.CharField(max_length=100)
    email = models.EmailField()
    phone_number = PhoneNumberField()
    
    company = models.CharField(max_length=200, blank=True)
    job_title = models.CharField(max_length=100, blank=True)
    
    source = models.CharField(max_length=20, choices=SOURCE_CHOICES)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='NEW')
    
    assigned_to = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='assigned_leads')
    
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'crm_leads'
        verbose_name = 'Lead'
        verbose_name_plural = 'Leads'
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.lead_number} - {self.first_name} {self.last_name}"


class Interaction(models.Model):
    """Customer/Lead interactions"""
    INTERACTION_TYPE_CHOICES = [
        ('CALL', 'Phone Call'),
        ('EMAIL', 'Email'),
        ('MEETING', 'Meeting'),
        ('VISIT', 'Office Visit'),
        ('OTHER', 'Other'),
    ]
    
    lead = models.ForeignKey(Lead, on_delete=models.CASCADE, null=True, blank=True, related_name='interactions')
    interaction_type = models.CharField(max_length=20, choices=INTERACTION_TYPE_CHOICES)
    subject = models.CharField(max_length=200)
    notes = models.TextField()
    
    interaction_date = models.DateTimeField()
    user = models.ForeignKey(User, on_delete=models.PROTECT, related_name='interactions')
    
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'crm_interactions'
        verbose_name = 'Interaction'
        verbose_name_plural = 'Interactions'
        ordering = ['-interaction_date']
    
    def __str__(self):
        return f"{self.interaction_type} - {self.subject}"
