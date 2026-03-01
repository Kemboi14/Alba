"""
Enterprise-Grade Audit Logging Signals
=======================================

Django signals to automatically log model changes (Create/Update/Delete)

Features:
- Automatic logging via post_save and post_delete signals
- Tracks field-level changes for UPDATE operations
- Extracts old and new values
- Thread-safe with middleware integration
- Excludes audit logs from being audited (prevents recursion)
- Handles system actions (no user)
- Login/Logout tracking

Usage:
    This module is automatically loaded when Django starts.
    Signals are connected in apps.py
"""

import json
from django.db.models.signals import post_save, post_delete, pre_save
from django.dispatch import receiver, Signal
from django.contrib.contenttypes.models import ContentType
from django.core.serializers.json import DjangoJSONEncoder
from django.contrib.auth.signals import user_logged_in, user_logged_out
from apps.core.models import AuditLog
from apps.core.middleware import get_current_user, get_current_request


# Store original values before save (for tracking changes)
_original_values = {}


def should_audit_model(instance):
    """
    Determine if a model instance should be audited
    
    Args:
        instance: Model instance
    
    Returns:
        bool: True if should be audited, False otherwise
    """
    # Don't audit the AuditLog model itself (prevents recursion)
    if isinstance(instance, AuditLog):
        return False
    
    # Don't audit Django's internal models
    excluded_apps = ['contenttypes', 'sessions', 'admin', 'auth']
    if instance._meta.app_label in excluded_apps:
        return False
    
    # Don't audit migration history
    if instance._meta.model_name == 'migration':
        return False
    
    return True


def get_model_fields(instance):
    """
    Get all relevant fields from a model instance
    
    Args:
        instance: Model instance
    
    Returns:
        dict: Field name -> value mapping
    """
    fields = {}
    
    for field in instance._meta.fields:
        field_name = field.name
        
        # Skip sensitive fields
        if field.name in ['password', 'checksum']:
            continue
        
        try:
            value = getattr(instance, field_name)
            
            # Convert to JSON-serializable format
            if hasattr(value, 'pk'):
                # Foreign key - store ID and string representation
                fields[field_name] = {
                    'id': value.pk,
                    'display': str(value)
                }
            elif isinstance(value, (list, dict)):
                fields[field_name] = value
            else:
                fields[field_name] = str(value) if value is not None else None
                
        except Exception:
            # Skip fields that can't be accessed
            continue
    
    return fields


def get_changed_fields(old_values, new_values):
    """
    Compare old and new values to find changed fields
    
    Args:
        old_values: Dict of old field values
        new_values: Dict of new field values
    
    Returns:
        list: Names of fields that changed
    """
    changed = []
    
    for field_name in new_values.keys():
        old_val = old_values.get(field_name)
        new_val = new_values.get(field_name)
        
        # Handle dict comparison (for ForeignKey fields)
        if isinstance(old_val, dict) and isinstance(new_val, dict):
            if old_val.get('id') != new_val.get('id'):
                changed.append(field_name)
        elif old_val != new_val:
            changed.append(field_name)
    
    return changed


@receiver(pre_save)
def store_original_values(sender, instance, **kwargs):
    """
    Store original values before save (for UPDATE operations)
    
    Args:
        sender: Model class
        instance: Model instance being saved
    """
    if not should_audit_model(instance):
        return
    
    # Only store if updating (has pk)
    if instance.pk:
        try:
            original = sender.objects.get(pk=instance.pk)
            key = f"{sender._meta.model_name}_{instance.pk}"
            _original_values[key] = get_model_fields(original)
        except sender.DoesNotExist:
            # New instance (shouldn't happen in pre_save, but handle it)
            pass


@receiver(post_save)
def log_model_save(sender, instance, created, **kwargs):
    """
    Automatically log model creation and updates
    
    Args:
        sender: Model class
        instance: Model instance that was saved
        created: Boolean indicating if this is a new instance
    """
    if not should_audit_model(instance):
        return
    
    # Get current user and request
    user = get_current_user()
    request = get_current_request()
    
    # Determine action type
    action_type = AuditLog.CREATE if created else AuditLog.UPDATE
    
    # Get model information
    model_name = sender._meta.model_name.capitalize()
    object_id = str(instance.pk)
    module = sender._meta.app_label
    
    # Get new values
    new_values = get_model_fields(instance)
    
    # For updates, get old values and changed fields
    old_values = None
    changed_fields = None
    
    if not created:
        key = f"{sender._meta.model_name}_{instance.pk}"
        old_values = _original_values.get(key)
        
        if old_values:
            changed_fields = get_changed_fields(old_values, new_values)
            # Clean up stored values
            del _original_values[key]
    
    # Build description
    if created:
        description = f"Created {model_name} '{instance}'"
    else:
        if changed_fields:
            fields_str = ', '.join(changed_fields)
            description = f"Updated {model_name} '{instance}' - Changed fields: {fields_str}"
        else:
            description = f"Updated {model_name} '{instance}'"
    
    # Get request metadata
    ip_address = None
    user_agent = None
    request_method = None
    request_path = None
    session_key = None
    
    if request:
        ip_address = getattr(request, 'audit_ip', None)
        user_agent = getattr(request, 'audit_user_agent', '')[:500]
        request_method = request.method
        request_path = request.path[:500]
        session_key = request.session.session_key if hasattr(request, 'session') else None
    
    # Create audit log
    try:
        AuditLog.log_action(
            user=user,
            action_type=action_type,
            model_name=model_name,
            object_id=object_id,
            description=description,
            module=module,
            old_value=old_values,
            new_value=new_values,
            changed_fields=changed_fields,
            ip_address=ip_address,
            user_agent=user_agent,
            request_method=request_method,
            request_path=request_path,
            session_key=session_key,
        )
    except Exception as e:
        # Log error but don't break the save operation
        import logging
        logger = logging.getLogger('audit')
        logger.error(f"Failed to create audit log for {model_name}: {e}")


@receiver(post_delete)
def log_model_delete(sender, instance, **kwargs):
    """
    Automatically log model deletions
    
    Args:
        sender: Model class
        instance: Model instance that was deleted
    """
    if not should_audit_model(instance):
        return
    
    # Get current user and request
    user = get_current_user()
    request = get_current_request()
    
    # Get model information
    model_name = sender._meta.model_name.capitalize()
    object_id = str(instance.pk)
    module = sender._meta.app_label
    
    # Get values before deletion
    old_values = get_model_fields(instance)
    
    # Build description
    description = f"Deleted {model_name} '{instance}'"
    
    # Get request metadata
    ip_address = None
    user_agent = None
    request_method = None
    request_path = None
    session_key = None
    
    if request:
        ip_address = getattr(request, 'audit_ip', None)
        user_agent = getattr(request, 'audit_user_agent', '')[:500]
        request_method = request.method
        request_path = request.path[:500]
        session_key = request.session.session_key if hasattr(request, 'session') else None
    
    # Create audit log
    try:
        AuditLog.log_action(
            user=user,
            action_type=AuditLog.DELETE,
            model_name=model_name,
            object_id=object_id,
            description=description,
            module=module,
            old_value=old_values,
            new_value=None,
            ip_address=ip_address,
            user_agent=user_agent,
            request_method=request_method,
            request_path=request_path,
            session_key=session_key,
        )
    except Exception as e:
        # Log error but don't break the delete operation
        import logging
        logger = logging.getLogger('audit')
        logger.error(f"Failed to create audit log for {model_name}: {e}")


@receiver(user_logged_in)
def log_user_login(sender, request, user, **kwargs):
    """
    Log user login events
    
    Args:
        sender: Signal sender
        request: HttpRequest object
        user: User instance that logged in
    """
    from apps.core.middleware import get_client_ip
    
    ip_address = get_client_ip(request)
    user_agent = request.META.get('HTTP_USER_AGENT', '')[:500]
    
    try:
        AuditLog.log_action(
            user=user,
            action_type=AuditLog.LOGIN,
            model_name='User',
            object_id=str(user.pk),
            description=f"User {user.email} logged in successfully",
            module='core',
            ip_address=ip_address,
            user_agent=user_agent,
            request_method=request.method,
            request_path=request.path[:500],
            session_key=request.session.session_key if hasattr(request, 'session') else None,
        )
    except Exception as e:
        import logging
        logger = logging.getLogger('audit')
        logger.error(f"Failed to log login for {user.email}: {e}")


@receiver(user_logged_out)
def log_user_logout(sender, request, user, **kwargs):
    """
    Log user logout events
    
    Args:
        sender: Signal sender
        request: HttpRequest object
        user: User instance that logged out (may be None)
    """
    if user is None:
        return
    
    from apps.core.middleware import get_client_ip
    
    ip_address = get_client_ip(request)
    user_agent = request.META.get('HTTP_USER_AGENT', '')[:500]
    
    try:
        AuditLog.log_action(
            user=user,
            action_type=AuditLog.LOGOUT,
            model_name='User',
            object_id=str(user.pk),
            description=f"User {user.email} logged out",
            module='core',
            ip_address=ip_address,
            user_agent=user_agent,
            request_method=request.method if request else None,
            request_path=request.path[:500] if request else None,
        )
    except Exception as e:
        import logging
        logger = logging.getLogger('audit')
        logger.error(f"Failed to log logout for {user.email}: {e}")


# Custom signal for special actions (approve, reject, export, etc.)
audit_log_signal = Signal()


@receiver(audit_log_signal)
def handle_custom_audit_log(sender, **kwargs):
    """
    Handle custom audit log events
    
    Usage:
        from apps.core.signals import audit_log_signal
        from apps.core.models import AuditLog
        
        audit_log_signal.send(
            sender=None,
            user=request.user,
            action_type=AuditLog.APPROVE,
            model_name='Loan',
            object_id=loan.pk,
            description='Loan approved',
            module='loans'
        )
    """
    try:
        AuditLog.log_action(**kwargs)
    except Exception as e:
        import logging
        logger = logging.getLogger('audit')
        logger.error(f"Failed to create custom audit log: {e}")


# Export public API
__all__ = [
    'audit_log_signal',
    'log_model_save',
    'log_model_delete',
    'log_user_login',
    'log_user_logout',
]
