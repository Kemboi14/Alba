"""
Core models for Alba Capital ERP System
Custom User model with Role-Based Access Control (RBAC)
"""

from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.db import models
from django.utils import timezone


class UserManager(BaseUserManager):
    """Custom user manager for email-based authentication"""
    
    def create_user(self, email, password=None, **extra_fields):
        """Create and return a regular user"""
        if not email:
            raise ValueError('Users must have an email address')
        
        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user
    
    def create_superuser(self, email, password=None, **extra_fields):
        """Create and return a superuser"""
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        extra_fields.setdefault('role', User.ADMIN)
        
        if extra_fields.get('is_staff') is not True:
            raise ValueError('Superuser must have is_staff=True')
        if extra_fields.get('is_superuser') is not True:
            raise ValueError('Superuser must have is_superuser=True')
        
        return self.create_user(email, password, **extra_fields)


class User(AbstractBaseUser, PermissionsMixin):
    """
    Custom User model with Role-Based Access Control
    Based on SRS Section 2.2 - User Classes and Characteristics
    """
    
    # Role Choices as per SRS
    ADMIN = 'ADMIN'
    CREDIT_OFFICER = 'CREDIT_OFFICER'
    FINANCE_OFFICER = 'FINANCE_OFFICER'
    HR_OFFICER = 'HR_OFFICER'
    MANAGEMENT = 'MANAGEMENT'
    INVESTOR = 'INVESTOR'
    CUSTOMER = 'CUSTOMER'
    
    ROLE_CHOICES = [
        (ADMIN, 'System Administrator'),
        (CREDIT_OFFICER, 'Credit Officer'),
        (FINANCE_OFFICER, 'Finance Officer'),
        (HR_OFFICER, 'HR Officer'),
        (MANAGEMENT, 'Management'),
        (INVESTOR, 'Investor'),
        (CUSTOMER, 'Customer'),
    ]
    
    # User fields
    email = models.EmailField('Email Address', unique=True)
    first_name = models.CharField('First Name', max_length=150)
    last_name = models.CharField('Last Name', max_length=150)
    phone = models.CharField('Phone Number', max_length=15, blank=True)
    
    # Role and Permissions
    role = models.CharField(
        'User Role',
        max_length=20,
        choices=ROLE_CHOICES,
        default=CUSTOMER,
        help_text='User role determines access permissions'
    )
    
    # Status fields
    is_active = models.BooleanField('Active', default=True)
    is_staff = models.BooleanField('Staff Status', default=False)
    is_approved = models.BooleanField('Approved', default=False, help_text='Account approved by administrator')
    
    # Timestamps
    date_joined = models.DateTimeField('Date Joined', default=timezone.now)
    last_login = models.DateTimeField('Last Login', null=True, blank=True)
    
    objects = UserManager()
    
    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['first_name', 'last_name']
    
    class Meta:
        db_table = 'users'
        verbose_name = 'User'
        verbose_name_plural = 'Users'
        ordering = ['-date_joined']
    
    def __str__(self):
        return f"{self.get_full_name()} ({self.get_role_display()})"
    
    def get_full_name(self):
        """Return the user's full name"""
        return f"{self.first_name} {self.last_name}".strip()
    
    def get_short_name(self):
        """Return the user's first name"""
        return self.first_name
    
    def has_permission(self, module, permission_type='view'):
        """
        Check if user has permission for a specific module
        
        Args:
            module: Module name (e.g., 'loans', 'accounting', 'hr')
            permission_type: Type of permission ('view', 'create', 'edit', 'delete', 'approve')
        
        Returns:
            bool: True if user has permission, False otherwise
        """
        # Admins have all permissions
        if self.role == self.ADMIN or self.is_superuser:
            return True
        
        # Role-based permission matrix (SRS Section 4.1 - Security & RBAC)
        permission_matrix = {
            self.CREDIT_OFFICER: {
                'loans': ['view', 'create', 'edit', 'approve'],
                'customers': ['view', 'create', 'edit'],
                'crm': ['view', 'create', 'edit'],
                'reports': ['view'],
            },
            self.FINANCE_OFFICER: {
                'accounting': ['view', 'create', 'edit', 'approve'],
                'loans': ['view'],
                'budgeting': ['view', 'create', 'edit'],
                'investors': ['view', 'create', 'edit'],
                'reports': ['view'],
            },
            self.HR_OFFICER: {
                'hr': ['view', 'create', 'edit'],
                'payroll': ['view', 'create', 'edit', 'approve'],
                'employees': ['view', 'create', 'edit'],
                'reports': ['view'],
            },
            self.MANAGEMENT: {
                'dashboard': ['view'],
                'reports': ['view'],
                'loans': ['view'],
                'accounting': ['view'],
                'hr': ['view'],
                'investors': ['view'],
                'analytics': ['view'],
            },
            self.INVESTOR: {
                'investor_portal': ['view'],
                'investor_reports': ['view'],
                'statements': ['view'],
            },
            self.CUSTOMER: {
                'customer_portal': ['view'],
                'loan_applications': ['view', 'create'],
                'documents': ['view', 'create'],
                'statements': ['view'],
            },
        }
        
        # Get role permissions
        role_permissions = permission_matrix.get(self.role, {})
        module_permissions = role_permissions.get(module, [])
        
        return permission_type in module_permissions
    
    def is_staff_user(self):
        """Check if user is a staff member (not customer or investor)"""
        return self.role in [
            self.ADMIN,
            self.CREDIT_OFFICER,
            self.FINANCE_OFFICER,
            self.HR_OFFICER,
            self.MANAGEMENT
        ]


class AuditLog(models.Model):
    """
    Audit trail for all system actions
    SRS Section 4.1 - Immutable, timestamped logs
    """
    
    ACTION_CHOICES = [
        ('CREATE', 'Create'),
        ('UPDATE', 'Update'),
        ('DELETE', 'Delete'),
        ('LOGIN', 'Login'),
        ('LOGOUT', 'Logout'),
        ('APPROVE', 'Approve'),
        ('REJECT', 'Reject'),
        ('VIEW', 'View'),
    ]
    
    user = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        related_name='audit_logs'
    )
    action = models.CharField('Action', max_length=20, choices=ACTION_CHOICES)
    model_name = models.CharField('Model', max_length=100)
    object_id = models.CharField('Object ID', max_length=100, blank=True)
    description = models.TextField('Description')
    ip_address = models.GenericIPAddressField('IP Address', null=True, blank=True)
    user_agent = models.TextField('User Agent', blank=True)
    timestamp = models.DateTimeField('Timestamp', default=timezone.now, db_index=True)
    
    class Meta:
        db_table = 'audit_logs'
        verbose_name = 'Audit Log'
        verbose_name_plural = 'Audit Logs'
        ordering = ['-timestamp']
        indexes = [
            models.Index(fields=['-timestamp']),
            models.Index(fields=['user', '-timestamp']),
            models.Index(fields=['model_name', '-timestamp']),
        ]
    
    def __str__(self):
        user_email = self.user.email if self.user else 'System'
        return f"{user_email} - {self.action} - {self.model_name} - {self.timestamp}"


class OdooConfig(models.Model):
    """
    Odoo API configuration stored in database.
    Allows admin panel management of Odoo integration settings.
    Falls back to environment variables if not configured.
    """

    url = models.URLField(
        'Odoo URL',
        help_text='Base URL of the Odoo instance, e.g., https://odoo.albacapital.co.ke'
    )
    api_key = models.CharField(
        'API Key',
        max_length=255,
        help_text='X-Alba-API-Key for authenticating with Odoo'
    )
    database = models.CharField(
        'Database',
        max_length=100,
        blank=True,
        help_text='Odoo database name (optional)'
    )
    webhook_secret = models.CharField(
        'Webhook Secret',
        max_length=255,
        blank=True,
        help_text='Secret for verifying webhook signatures'
    )
    webhook_url = models.URLField(
        'Outbound Webhook URL',
        blank=True,
        help_text='URL where Odoo sends webhooks (e.g., https://yourdomain.com/api/v1/webhooks/odoo/)'
    )
    is_active = models.BooleanField('Active', default=True)
    connection_status = models.CharField(
        'Connection Status',
        max_length=20,
        default='unknown',
        choices=[
            ('unknown', 'Unknown'),
            ('connected', 'Connected'),
            ('error', 'Error'),
        ]
    )
    last_sync = models.DateTimeField('Last Sync', null=True, blank=True)
    last_error = models.TextField('Last Error', blank=True)
    created_at = models.DateTimeField('Created At', auto_now_add=True)
    updated_at = models.DateTimeField('Updated At', auto_now=True)
    updated_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='odoo_config_updates'
    )

    class Meta:
        db_table = 'odoo_config'
        verbose_name = 'Odoo Configuration'
        verbose_name_plural = 'Odoo Configuration'

    def __str__(self):
        return f"Odoo Config ({self.url}) - {'Active' if self.is_active else 'Inactive'}"

    @classmethod
    def get_active(cls):
        """Get the active configuration or None."""
        return cls.objects.filter(is_active=True).first()

    def mask_secret(self, secret):
        """Mask a secret for display - show only last 4 chars."""
        if not secret or len(secret) <= 4:
            return '****'
        return '*' * (len(secret) - 4) + secret[-4:]

    @property
    def masked_api_key(self):
        return self.mask_secret(self.api_key)

    @property
    def masked_webhook_secret(self):
        return self.mask_secret(self.webhook_secret)
