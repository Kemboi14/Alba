"""
Core Models: User, Role, Permission, AuditLog
Implements RBAC (Role-Based Access Control) and comprehensive audit trail
"""
from decimal import Decimal
from django.db import models
from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.utils.translation import gettext_lazy as _
from django.utils import timezone
from phonenumber_field.modelfields import PhoneNumberField


class UserManager(BaseUserManager):
    """
    Custom user manager for email-based authentication
    Production-ready manager with comprehensive validation
    """
    
    def create_user(self, email, password=None, **extra_fields):
        """
        Create and save a regular user with email authentication
        
        Args:
            email: User email address (required)
            password: User password (required)
            **extra_fields: Additional user fields
            
        Returns:
            User: Created user instance
            
        Raises:
            ValueError: If email is not provided
        """
        if not email:
            raise ValueError(_('The Email field must be set'))
        
        email = self.normalize_email(email)
        extra_fields.setdefault('is_active', True)
        
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user
    
    def create_superuser(self, email, password=None, **extra_fields):
        """
        Create and save a superuser with full system access
        
        Args:
            email: Superuser email address (required)
            password: Superuser password (required)
            **extra_fields: Additional user fields
            
        Returns:
            User: Created superuser instance
            
        Raises:
            ValueError: If required superuser fields are not True
        """
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        extra_fields.setdefault('is_active', True)
        extra_fields.setdefault('role', 'ADMIN')
        extra_fields.setdefault('is_verified', True)
        
        if extra_fields.get('is_staff') is not True:
            raise ValueError(_('Superuser must have is_staff=True.'))
        if extra_fields.get('is_superuser') is not True:
            raise ValueError(_('Superuser must have is_superuser=True.'))
        
        return self.create_user(email, password, **extra_fields)


class Role(models.Model):
    """
    Role model for RBAC implementation
    Defines system roles with specific permissions
    """
    SYSTEM_ADMIN = 'SYSTEM_ADMIN'
    CREDIT_OFFICER = 'CREDIT_OFFICER'
    FINANCE_OFFICER = 'FINANCE_OFFICER'
    HR_OFFICER = 'HR_OFFICER'
    MANAGEMENT = 'MANAGEMENT'
    INVESTOR = 'INVESTOR'
    CUSTOMER = 'CUSTOMER'
    
    ROLE_CHOICES = [
        (SYSTEM_ADMIN, 'System Administrator'),
        (CREDIT_OFFICER, 'Credit Officer'),
        (FINANCE_OFFICER, 'Finance Officer'),
        (HR_OFFICER, 'HR Officer'),
        (MANAGEMENT, 'Management'),
        (INVESTOR, 'Investor'),
        (CUSTOMER, 'Customer'),
    ]
    
    name = models.CharField(max_length=50, unique=True, choices=ROLE_CHOICES)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'core_roles'
        verbose_name = 'Role'
        verbose_name_plural = 'Roles'
        ordering = ['name']
    
    def __str__(self):
        return self.get_name_display()


class Permission(models.Model):
    """
    Granular permission model for fine-grained access control
    """
    role = models.ForeignKey(Role, on_delete=models.CASCADE, related_name='permissions')
    module = models.CharField(max_length=50)  # e.g., 'loans', 'accounting'
    can_view = models.BooleanField(default=False)
    can_create = models.BooleanField(default=False)
    can_edit = models.BooleanField(default=False)
    can_delete = models.BooleanField(default=False)
    can_approve = models.BooleanField(default=False)
    can_export = models.BooleanField(default=False)
    
    class Meta:
        db_table = 'core_permissions'
        verbose_name = 'Permission'
        verbose_name_plural = 'Permissions'
        unique_together = ['role', 'module']
    
    def __str__(self):
        return f"{self.role.name} - {self.module}"


class User(AbstractUser):
    """
    Custom User model extending Django's AbstractUser
    Production-ready user model with role-based access control
    """
    # Role choices as requested
    ADMIN = 'ADMIN'
    CREDIT_OFFICER = 'CREDIT_OFFICER'
    FINANCE_OFFICER = 'FINANCE_OFFICER'
    HR_OFFICER = 'HR_OFFICER'
    MANAGEMENT = 'MANAGEMENT'
    INVESTOR = 'INVESTOR'
    CUSTOMER = 'CUSTOMER'
    
    ROLE_CHOICES = [
        (ADMIN, 'Administrator'),
        (CREDIT_OFFICER, 'Credit Officer'),
        (FINANCE_OFFICER, 'Finance Officer'),
        (HR_OFFICER, 'HR Officer'),
        (MANAGEMENT, 'Management'),
        (INVESTOR, 'Investor'),
        (CUSTOMER, 'Customer'),
    ]
    
    username = None  # Remove username field
    email = models.EmailField(_('email address'), unique=True, db_index=True)
    phone_number = PhoneNumberField(blank=True, null=True)
    
    # Role and Status Fields
    role = models.CharField(
        max_length=20,
        choices=ROLE_CHOICES,
        default=CUSTOMER,
        db_index=True,
        help_text='User role for access control'
    )
    is_verified = models.BooleanField(
        default=False,
        db_index=True,
        help_text='Email/phone verification status'
    )
    # is_active inherited from AbstractUser with db_index
    
    # Profile Information
    employee_id = models.CharField(max_length=20, blank=True, null=True, unique=True, db_index=True)
    department = models.CharField(max_length=100, blank=True, db_index=True)
    branch = models.CharField(max_length=100, blank=True, default='Head Office')
    
    # Additional Fields
    national_id = models.CharField(max_length=20, blank=True, null=True, unique=True, db_index=True)
    date_of_birth = models.DateField(blank=True, null=True)
    address = models.TextField(blank=True)
    profile_picture = models.ImageField(upload_to='profile_pictures/', blank=True, null=True)
    
    # Employment Details
    date_joined_company = models.DateField(blank=True, null=True)
    employment_status = models.CharField(
        max_length=20,
        choices=[
            ('ACTIVE', 'Active'),
            ('ON_LEAVE', 'On Leave'),
            ('SUSPENDED', 'Suspended'),
            ('TERMINATED', 'Terminated'),
        ],
        default='ACTIVE',
        db_index=True
    )
    
    # Security
    force_password_change = models.BooleanField(default=False)
    last_login_ip = models.GenericIPAddressField(blank=True, null=True)
    failed_login_attempts = models.IntegerField(default=0)
    account_locked_until = models.DateTimeField(blank=True, null=True)
    
    # Multi-Factor Authentication (MFA)
    mfa_enabled = models.BooleanField(default=False, help_text='MFA enabled for this user')
    mfa_secret = models.CharField(max_length=32, blank=True, default='', help_text='TOTP secret key')
    mfa_backup_codes = models.JSONField(default=list, blank=True, help_text='Backup codes for MFA recovery')
    last_mfa_verification = models.DateTimeField(blank=True, null=True, help_text='Last successful MFA verification')
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(
        'self',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='created_users'
    )
    
    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['first_name', 'last_name']
    
    objects = UserManager()
    
    class Meta:
        db_table = 'core_users'
        verbose_name = 'User'
        verbose_name_plural = 'Users'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['email']),
            models.Index(fields=['role', 'is_active']),
            models.Index(fields=['is_verified', 'is_active']),
            models.Index(fields=['employee_id']),
            models.Index(fields=['national_id']),
            models.Index(fields=['-created_at']),
            models.Index(fields=['department', 'is_active']),
            models.Index(fields=['employment_status']),
        ]
        permissions = [
            ('can_manage_users', 'Can manage users'),
            ('can_manage_roles', 'Can manage roles'),
            ('can_view_audit_logs', 'Can view audit logs'),
        ]
    
    def __str__(self):
        return f"{self.get_full_name()} ({self.email})"
    
    def get_full_name(self):
        """Return the full name of the user"""
        return f"{self.first_name} {self.last_name}".strip() or self.email
    
    def has_permission(self, module, permission_type):
        """
        Check if user has specific permission for a module
        Uses role-based permissions from the Permission model
        """
        if self.is_superuser or self.role == self.ADMIN:
            return True
        
        if not self.role:
            return False
        
        try:
            # Try to get permission from the legacy Role model if it exists
            role_obj = Role.objects.filter(name=self.role).first()
            if role_obj:
                permission = role_obj.permissions.get(module=module)
                return getattr(permission, f'can_{permission_type}', False)
        except Permission.DoesNotExist:
            pass
        
        # Default role-based permissions
        admin_roles = [self.ADMIN]
        finance_roles = [self.ADMIN, self.FINANCE_OFFICER, self.MANAGEMENT]
        credit_roles = [self.ADMIN, self.CREDIT_OFFICER, self.FINANCE_OFFICER]
        
        # Module-specific permissions
        if module == 'accounting' and self.role in finance_roles:
            return True
        if module == 'loans' and self.role in credit_roles:
            return True
        if module == 'investors' and self.role in finance_roles:
            return True
        
        return False
    
    def is_account_locked(self):
        """Check if account is currently locked"""
        if self.account_locked_until:
            return self.account_locked_until > timezone.now()
        return False
    
    def is_admin(self):
        """Check if user is an administrator"""
        return self.role == self.ADMIN or self.is_superuser
    
    def can_approve_loans(self):
        """Check if user can approve loans"""
        return self.role in [self.ADMIN, self.CREDIT_OFFICER, self.MANAGEMENT]
    
    def can_manage_finances(self):
        """Check if user can manage financial operations"""
        return self.role in [self.ADMIN, self.FINANCE_OFFICER]


class AuditLog(models.Model):
    """
    Enterprise-Grade Tamper-Resistant Audit Logging System
    
    Features:
    - Immutable records (cannot be edited or deleted)
    - Comprehensive field tracking
    - IP address and user agent logging
    - Optimized indexes for fast queries
    - Change tracking with old/new values
    - Automatic timestamp generation
    
    Security:
    - Write-once model (no updates allowed)
    - Protected from deletion
    - Hash verification for integrity
    - Isolated database table
    """
    
    # Action type choices
    CREATE = 'CREATE'
    UPDATE = 'UPDATE'
    DELETE = 'DELETE'
    VIEW = 'VIEW'
    LOGIN = 'LOGIN'
    LOGOUT = 'LOGOUT'
    APPROVE = 'APPROVE'
    REJECT = 'REJECT'
    EXPORT = 'EXPORT'
    IMPORT = 'IMPORT'
    PAYMENT = 'PAYMENT'
    DISBURSEMENT = 'DISBURSEMENT'
    CONFIGURE = 'CONFIGURE'
    BACKUP = 'BACKUP'
    RESTORE = 'RESTORE'
    
    ACTION_TYPES = [
        (CREATE, 'Create'),
        (UPDATE, 'Update'),
        (DELETE, 'Delete'),
        (VIEW, 'View'),
        (LOGIN, 'Login'),
        (LOGOUT, 'Logout'),
        (APPROVE, 'Approve'),
        (REJECT, 'Reject'),
        (EXPORT, 'Export'),
        (IMPORT, 'Import'),
        (PAYMENT, 'Payment'),
        (DISBURSEMENT, 'Disbursement'),
        (CONFIGURE, 'Configure'),
        (BACKUP, 'Backup'),
        (RESTORE, 'Restore'),
    ]
    
    # Core audit fields
    user = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='audit_logs',
        db_index=True,
        help_text='User who performed the action'
    )
    action_type = models.CharField(
        max_length=20,
        choices=ACTION_TYPES,
        db_index=True,
        help_text='Type of action performed'
    )
    model_name = models.CharField(
        max_length=100,
        db_index=True,
        help_text='Django model name (e.g., Loan, User)'
    )
    object_id = models.CharField(
        max_length=100,
        db_index=True,
        help_text='Primary key of the affected object'
    )
    description = models.TextField(
        help_text='Human-readable description of the action'
    )
    
    # Module tracking
    module = models.CharField(
        max_length=50,
        db_index=True,
        help_text='Application module (e.g., loans, accounting)'
    )
    
    # Change tracking (for UPDATE actions)
    old_value = models.JSONField(
        blank=True,
        null=True,
        help_text='Previous state of the object (JSON)'
    )
    new_value = models.JSONField(
        blank=True,
        null=True,
        help_text='New state of the object (JSON)'
    )
    changed_fields = models.JSONField(
        blank=True,
        null=True,
        help_text='List of fields that were changed'
    )
    
    # Request metadata
    ip_address = models.GenericIPAddressField(
        blank=True,
        null=True,
        db_index=True,
        help_text='IP address of the request'
    )
    user_agent = models.TextField(
        blank=True,
        null=True,
        help_text='Browser user agent string'
    )
    request_method = models.CharField(
        max_length=10,
        blank=True,
        null=True,
        help_text='HTTP method (GET, POST, PUT, DELETE)'
    )
    request_path = models.CharField(
        max_length=500,
        blank=True,
        null=True,
        help_text='URL path of the request'
    )
    
    # Timestamp (immutable)
    timestamp = models.DateTimeField(
        auto_now_add=True,
        db_index=True,
        editable=False,
        help_text='When the action occurred (cannot be changed)'
    )
    
    # Integrity verification
    checksum = models.CharField(
        max_length=64,
        blank=True,
        editable=False,
        help_text='SHA-256 hash for integrity verification'
    )
    
    # Session tracking
    session_key = models.CharField(
        max_length=40,
        blank=True,
        null=True,
        db_index=True,
        help_text='Django session key'
    )
    
    class Meta:
        db_table = 'core_audit_logs'
        verbose_name = 'Audit Log'
        verbose_name_plural = 'Audit Logs'
        ordering = ['-timestamp']
        get_latest_by = 'timestamp'
        
        # Comprehensive indexing for performance
        indexes = [
            # Primary query patterns
            models.Index(fields=['-timestamp'], name='idx_audit_timestamp'),
            models.Index(fields=['user', '-timestamp'], name='idx_audit_user_time'),
            models.Index(fields=['action_type', '-timestamp'], name='idx_audit_action_time'),
            models.Index(fields=['model_name', 'object_id'], name='idx_audit_object'),
            models.Index(fields=['module', 'action_type'], name='idx_audit_module'),
            models.Index(fields=['ip_address', '-timestamp'], name='idx_audit_ip'),
            models.Index(fields=['session_key'], name='idx_audit_session'),
            
            # Compound indexes for common queries
            models.Index(fields=['user', 'action_type', '-timestamp'], name='idx_audit_user_action'),
            models.Index(fields=['model_name', 'action_type', '-timestamp'], name='idx_audit_model_action'),
        ]
        
        # Permissions
        permissions = [
            ('view_audit_log', 'Can view audit logs'),
            ('export_audit_log', 'Can export audit logs'),
        ]
    
    def save(self, *args, **kwargs):
        """
        Override save to enforce immutability and generate checksum
        
        Raises:
            ValueError: If attempting to update an existing record
        """
        # Prevent updates (only allow creation)
        if self.pk is not None:
            raise ValueError(
                "Audit logs are immutable and cannot be modified. "
                "Create a new log entry instead."
            )
        
        # Generate checksum before saving
        if not self.checksum:
            import hashlib
            import json
            
            # Create a deterministic string representation
            data = {
                'user_id': self.user_id,
                'action_type': self.action_type,
                'model_name': self.model_name,
                'object_id': self.object_id,
                'description': self.description,
                'module': self.module,
                'ip_address': self.ip_address,
            }
            
            data_str = json.dumps(data, sort_keys=True)
            self.checksum = hashlib.sha256(data_str.encode()).hexdigest()
        
        super().save(*args, **kwargs)
    
    def delete(self, *args, **kwargs):
        """
        Override delete to prevent deletion of audit logs
        
        Raises:
            ValueError: Always - audit logs cannot be deleted
        """
        raise ValueError(
            "Audit logs cannot be deleted. "
            "They are permanent records required for compliance."
        )
    
    def __str__(self):
        user_display = self.user.email if self.user else 'System'
        return f"{user_display} - {self.action_type} - {self.model_name} - {self.timestamp}"
    
    def verify_integrity(self):
        """
        Verify the integrity of this audit log using checksum
        
        Returns:
            bool: True if checksum is valid, False otherwise
        """
        import hashlib
        import json
        
        data = {
            'user_id': self.user_id,
            'action_type': self.action_type,
            'model_name': self.model_name,
            'object_id': self.object_id,
            'description': self.description,
            'module': self.module,
            'ip_address': self.ip_address,
        }
        
        data_str = json.dumps(data, sort_keys=True)
        calculated_checksum = hashlib.sha256(data_str.encode()).hexdigest()
        
        return calculated_checksum == self.checksum
    
    @classmethod
    def log_action(cls, user, action_type, model_name, object_id, description, 
                   module=None, old_value=None, new_value=None, changed_fields=None,
                   ip_address=None, user_agent=None, request_method=None, 
                   request_path=None, session_key=None):
        """
        Convenience method to create an audit log entry
        
        Args:
            user: User instance or None for system actions
            action_type: One of the ACTION_TYPES constants
            model_name: Name of the model being audited
            object_id: Primary key of the object
            description: Human-readable description
            module: Application module (optional, inferred from model_name)
            old_value: Previous state (for UPDATE)
            new_value: New state (for UPDATE)
            changed_fields: List of changed field names
            ip_address: Request IP address
            user_agent: Browser user agent
            request_method: HTTP method
            request_path: URL path
            session_key: Django session key
        
        Returns:
            AuditLog: Created audit log instance
        """
        # Infer module from model_name if not provided
        if module is None:
            module = model_name.lower().split('.')[0] if '.' in model_name else 'core'
        
        return cls.objects.create(
            user=user,
            action_type=action_type,
            model_name=model_name,
            object_id=str(object_id),
            description=description,
            module=module,
            old_value=old_value,
            new_value=new_value,
            changed_fields=changed_fields,
            ip_address=ip_address,
            user_agent=user_agent,
            request_method=request_method,
            request_path=request_path,
            session_key=session_key,
        )


class SystemSetting(models.Model):
    """
    System-wide configuration settings
    Stores key-value pairs for system configuration
    """
    key = models.CharField(max_length=100, unique=True)
    value = models.TextField()
    description = models.TextField(blank=True)
    data_type = models.CharField(
        max_length=20,
        choices=[
            ('STRING', 'String'),
            ('INTEGER', 'Integer'),
            ('DECIMAL', 'Decimal'),
            ('BOOLEAN', 'Boolean'),
            ('JSON', 'JSON'),
        ],
        default='STRING'
    )
    is_sensitive = models.BooleanField(default=False)  # For passwords, API keys
    updated_at = models.DateTimeField(auto_now=True)
    updated_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        related_name='updated_settings'
    )
    
    class Meta:
        db_table = 'core_system_settings'
        verbose_name = 'System Setting'
        verbose_name_plural = 'System Settings'
        ordering = ['key']
    
    def __str__(self):
        return self.key
    
    def get_value(self):
        """Return the value cast to appropriate type"""
        if self.data_type == 'INTEGER':
            return int(self.value)
        elif self.data_type == 'DECIMAL':
            return Decimal(self.value)
        elif self.data_type == 'BOOLEAN':
            return self.value.lower() in ('true', '1', 'yes')
        elif self.data_type == 'JSON':
            import json
            return json.loads(self.value)
        return self.value


class Notification(models.Model):
    """
    In-app notification system
    """
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='notifications')
    title = models.CharField(max_length=200)
    message = models.TextField()
    notification_type = models.CharField(
        max_length=20,
        choices=[
            ('INFO', 'Information'),
            ('SUCCESS', 'Success'),
            ('WARNING', 'Warning'),
            ('ERROR', 'Error'),
        ],
        default='INFO'
    )
    is_read = models.BooleanField(default=False)
    link = models.CharField(max_length=255, blank=True)  # URL to related object
    created_at = models.DateTimeField(auto_now_add=True)
    read_at = models.DateTimeField(blank=True, null=True)
    
    class Meta:
        db_table = 'core_notifications'
        verbose_name = 'Notification'
        verbose_name_plural = 'Notifications'
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.user} - {self.title}"
    
    def mark_as_read(self):
        """Mark notification as read"""
        if not self.is_read:
            self.is_read = True
            self.read_at = timezone.now()
            self.save()
