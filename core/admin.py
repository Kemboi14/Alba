"""
Django admin configuration for Core models
"""

from django.contrib import admin
from django.contrib.auth.models import Group
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin, GroupAdmin as BaseGroupAdmin
from django.utils.html import format_html
from .models import User, AuditLog, OdooConfig


class FixedModelAdmin(admin.ModelAdmin):
    """Base admin class with __copy__ method to fix Django template context issue"""
    
    def __copy__(self):
        """Fix Django template context copying issue"""
        cls = self.__class__
        result = cls.__new__(cls)
        result.__dict__.update(self.__dict__)
        return result


class FixedUserAdmin(BaseUserAdmin):
    """Fixed UserAdmin with __copy__ method"""
    
    def __copy__(self):
        """Fix Django template context copying issue"""
        cls = self.__class__
        result = cls.__new__(cls)
        result.__dict__.update(self.__dict__)
        return result


class FixedGroupAdmin(BaseGroupAdmin):
    """Fixed GroupAdmin with __copy__ method"""
    
    def __copy__(self):
        """Fix Django template context copying issue"""
        cls = self.__class__
        result = cls.__new__(cls)
        result.__dict__.update(self.__dict__)
        return result


# Unregister default Django admin classes and register fixed versions
admin.site.unregister(Group)
@admin.register(Group)
class GroupAdmin(FixedGroupAdmin):
    """Fixed GroupAdmin with __copy__ method"""
    
    def __copy__(self):
        """Fix Django template context copying issue"""
        cls = self.__class__
        result = cls.__new__(cls)
        result.__dict__.update(self.__dict__)
        return result


@admin.register(User)
class UserAdmin(FixedUserAdmin):
    """Admin interface for Custom User model"""
    
    list_display = ['email', 'get_full_name', 'role', 'is_active', 'is_staff', 'date_joined']
    list_filter = ['role', 'is_active', 'is_staff', 'date_joined']
    search_fields = ['email', 'first_name', 'last_name', 'phone']
    ordering = ['-date_joined']
    actions = ['approve_users', 'reject_users']
    
    fieldsets = (
        (None, {'fields': ('email', 'password')}),
        ('Personal Info', {'fields': ('first_name', 'last_name', 'phone')}),
        ('Permissions', {'fields': ('role', 'is_active', 'is_staff', 'is_superuser')}),
        ('Important dates', {'fields': ('last_login', 'date_joined')}),
    )
    
    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': ('email', 'first_name', 'last_name', 'password1', 'password2', 'role', 'is_staff'),
        }),
    )
    
    readonly_fields = ['date_joined', 'last_login']
    
    def __copy__(self):
        """Fix Django template context copying issue"""
        cls = self.__class__
        result = cls.__new__(cls)
        result.__dict__.update(self.__dict__)
        return result
    
    @admin.action(description='Approve selected users')
    def approve_users(self, request, queryset):
        """Approve pending user registrations"""
        updated = queryset.filter(is_active=False).update(is_active=True)
        self.message_user(
            request,
            f'{updated} user(s) have been approved and can now login.',
            level='success'
        )
    
    @admin.action(description='Reject/Deactivate selected users')
    def reject_users(self, request, queryset):
        """Reject/deactivate user accounts"""
        updated = queryset.filter(is_active=True).update(is_active=False)
        self.message_user(
            request,
            f'{updated} user(s) have been deactivated and cannot login.',
            level='warning'
        )


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    """Admin interface for Audit Logs - Read-only"""
    
    list_display = ['timestamp', 'user', 'action', 'model_name', 'object_id', 'ip_address']
    list_filter = ['action', 'model_name', 'timestamp']
    search_fields = ['user__email', 'model_name', 'object_id', 'description']
    ordering = ['-timestamp']
    date_hierarchy = 'timestamp'
    
    # Make audit logs read-only
    def has_add_permission(self, request):
        return False
    
    def has_change_permission(self, request, obj=None):
        return False
    
    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(OdooConfig)
class OdooConfigAdmin(FixedModelAdmin):
    """
    Admin interface for Odoo API configuration.
    Allows superusers to manage Odoo integration settings from Django admin.
    """
    list_display = ['url', 'database', 'is_active', 'connection_status', 'updated_at']
    list_filter = ['is_active', 'connection_status', 'created_at']
    readonly_fields = ['created_at', 'updated_at', 'last_sync', 'connection_status', 'last_error']
    search_fields = ['url', 'database']
    
    fieldsets = (
        ('Connection Settings', {
            'fields': ('url', 'api_key', 'database')
        }),
        ('Webhook Settings', {
            'fields': ('webhook_secret', 'webhook_url'),
            'description': 'Configuration for receiving webhooks from Odoo'
        }),
        ('Status', {
            'fields': ('is_active', 'connection_status', 'last_sync', 'last_error')
        }),
        ('Audit', {
            'fields': ('created_at', 'updated_at', 'updated_by'),
            'classes': ('collapse',)
        }),
    )
    
    def save_model(self, request, obj, form, change):
        """Set updated_by to current user on save."""
        obj.updated_by = request.user
        super().save_model(request, obj, form, change)
