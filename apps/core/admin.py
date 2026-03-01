"""
Core Admin Configuration
"""
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.utils.html import format_html
from .models import User, Role, Permission, AuditLog, SystemSetting, Notification


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    """Custom User Admin"""
    list_display = ['email', 'get_full_name', 'role', 'department', 'is_active', 'date_joined']
    list_filter = ['role', 'department', 'is_active', 'employment_status']
    search_fields = ['email', 'first_name', 'last_name', 'employee_id', 'national_id']
    ordering = ['-date_joined']
    
    fieldsets = (
        (None, {'fields': ('email', 'password')}),
        ('Personal Info', {
            'fields': ('first_name', 'last_name', 'phone_number', 'national_id',
                      'date_of_birth', 'address', 'profile_picture')
        }),
        ('Employment', {
            'fields': ('employee_id', 'role', 'department', 'branch',
                      'date_joined_company', 'employment_status')
        }),
        ('Permissions', {
            'fields': ('is_active', 'is_staff', 'is_superuser', 'groups', 'user_permissions')
        }),
        ('Security', {
            'fields': ('force_password_change', 'last_login', 'last_login_ip',
                      'failed_login_attempts', 'account_locked_until')
        }),
    )
    
    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': ('email', 'first_name', 'last_name', 'role', 'password1', 'password2'),
        }),
    )


@admin.register(Role)
class RoleAdmin(admin.ModelAdmin):
    """Role Admin"""
    list_display = ['name', 'description', 'is_active', 'user_count', 'created_at']
    list_filter = ['is_active']
    search_fields = ['name', 'description']
    
    def user_count(self, obj):
        return obj.users.count()
    user_count.short_description = 'Users'


@admin.register(Permission)
class PermissionAdmin(admin.ModelAdmin):
    """Permission Admin"""
    list_display = ['role', 'module', 'can_view', 'can_create', 'can_edit',
                   'can_delete', 'can_approve', 'can_export']
    list_filter = ['role', 'module']
    search_fields = ['role__name', 'module']


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    """
    Audit Log Admin - Read-Only and Tamper-Resistant
    
    Features:
    - Completely read-only (no add/edit/delete)
    - Comprehensive field display
    - Advanced filtering and search
    - Export functionality
    - Integrity verification
    """
    list_display = [
        'timestamp',
        'user',
        'action_type',
        'model_name',
        'object_id',
        'module',
        'ip_address',
        'get_description_preview',
    ]
    list_filter = [
        'action_type',
        'module',
        'model_name',
        ('timestamp', admin.DateFieldListFilter),
    ]
    search_fields = [
        'user__email',
        'user__first_name',
        'user__last_name',
        'description',
        'model_name',
        'object_id',
        'ip_address',
    ]
    readonly_fields = [
        'user',
        'action_type',
        'model_name',
        'object_id',
        'description',
        'module',
        'old_value_display',
        'new_value_display',
        'changed_fields_display',
        'ip_address',
        'user_agent',
        'request_method',
        'request_path',
        'session_key',
        'timestamp',
        'checksum',
        'verify_integrity_status',
    ]
    ordering = ['-timestamp']
    date_hierarchy = 'timestamp'
    list_per_page = 50
    
    # Display all fields in detail view
    fieldsets = (
        ('Action Information', {
            'fields': (
                'timestamp',
                'user',
                'action_type',
                'description',
            )
        }),
        ('Object Information', {
            'fields': (
                'module',
                'model_name',
                'object_id',
            )
        }),
        ('Change Tracking', {
            'fields': (
                'changed_fields_display',
                'old_value_display',
                'new_value_display',
            ),
            'classes': ('collapse',),
        }),
        ('Request Metadata', {
            'fields': (
                'ip_address',
                'user_agent',
                'request_method',
                'request_path',
                'session_key',
            ),
            'classes': ('collapse',),
        }),
        ('Security', {
            'fields': (
                'checksum',
                'verify_integrity_status',
            ),
            'classes': ('collapse',),
        }),
    )
    
    def get_description_preview(self, obj):
        """Show preview of description in list view"""
        if len(obj.description) > 100:
            return obj.description[:100] + '...'
        return obj.description
    get_description_preview.short_description = 'Description'
    
    def old_value_display(self, obj):
        """Format old value for display"""
        if obj.old_value:
            import json
            return json.dumps(obj.old_value, indent=2)
        return '-'
    old_value_display.short_description = 'Old Value (JSON)'
    
    def new_value_display(self, obj):
        """Format new value for display"""
        if obj.new_value:
            import json
            return json.dumps(obj.new_value, indent=2)
        return '-'
    new_value_display.short_description = 'New Value (JSON)'
    
    def changed_fields_display(self, obj):
        """Format changed fields for display"""
        if obj.changed_fields:
            return ', '.join(obj.changed_fields)
        return '-'
    changed_fields_display.short_description = 'Changed Fields'
    
    def verify_integrity_status(self, obj):
        """Verify and display integrity status"""
        from django.utils.html import format_html
        
        if obj.verify_integrity():
            return format_html(
                '<span style="color: green; font-weight: bold;">✓ Valid</span>'
            )
        else:
            return format_html(
                '<span style="color: red; font-weight: bold;">✗ Tampered</span>'
            )
    verify_integrity_status.short_description = 'Integrity Check'
    
    def has_add_permission(self, request):
        """Prevent manual creation of audit logs"""
        return False
    
    def has_change_permission(self, request, obj=None):
        """Prevent editing of audit logs"""
        return False
    
    def has_delete_permission(self, request, obj=None):
        """Prevent deletion of audit logs"""
        return False
    
    def get_actions(self, request):
        """Remove bulk delete action"""
        actions = super().get_actions(request)
        if 'delete_selected' in actions:
            del actions['delete_selected']
        return actions


@admin.register(SystemSetting)
class SystemSettingAdmin(admin.ModelAdmin):
    """System Setting Admin"""
    list_display = ['key', 'get_value_display', 'data_type', 'updated_at', 'updated_by']
    list_filter = ['data_type', 'is_sensitive']
    search_fields = ['key', 'description']
    readonly_fields = ['updated_at', 'updated_by']
    
    def get_value_display(self, obj):
        if obj.is_sensitive:
            return '********'
        return obj.value[:50] + '...' if len(obj.value) > 50 else obj.value
    get_value_display.short_description = 'Value'
    
    def save_model(self, request, obj, form, change):
        obj.updated_by = request.user
        super().save_model(request, obj, form, change)


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    """Notification Admin"""
    list_display = ['user', 'title', 'notification_type', 'is_read', 'created_at']
    list_filter = ['notification_type', 'is_read', 'created_at']
    search_fields = ['user__email', 'title', 'message']
    readonly_fields = ['created_at', 'read_at']
