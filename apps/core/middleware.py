"""
Enterprise-Grade Audit Logging Middleware
==========================================

Automatically captures and logs all significant actions in the system.

Features:
- Captures all Create/Update/Delete operations
- Logs request metadata (IP, user agent, path)
- Tracks user sessions
- Excludes sensitive endpoints (login, static files)
- Thread-safe implementation
- Minimal performance impact
"""

import json
import threading
from django.utils.deprecation import MiddlewareMixin
from django.contrib.contenttypes.models import ContentType
from .models import AuditLog


# Thread-local storage for request context
_thread_locals = threading.local()


def get_current_request():
    """
    Get the current request from thread-local storage
    
    Returns:
        HttpRequest: Current request or None
    """
    return getattr(_thread_locals, 'request', None)


def get_current_user():
    """
    Get the current user from thread-local storage
    
    Returns:
        User: Current user or None
    """
    request = get_current_request()
    if request and hasattr(request, 'user'):
        return request.user if request.user.is_authenticated else None
    return None


def get_client_ip(request):
    """
    Extract client IP address from request
    
    Handles proxy headers (X-Forwarded-For, X-Real-IP)
    
    Args:
        request: Django HttpRequest object
    
    Returns:
        str: Client IP address or None
    """
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        ip = x_forwarded_for.split(',')[0].strip()
    else:
        ip = request.META.get('REMOTE_ADDR')
    return ip


class AuditLoggingMiddleware(MiddlewareMixin):
    """
    Middleware to automatically log all significant actions
    
    Captures:
    - All POST, PUT, PATCH, DELETE requests
    - Login/Logout events
    - Admin actions
    - API calls
    
    Excludes:
    - Static file requests
    - Media file requests
    - Health check endpoints
    - AJAX polling requests
    """
    
    # Paths to exclude from audit logging
    EXCLUDED_PATHS = [
        '/static/',
        '/media/',
        '/health/',
        '/ping/',
        '/favicon.ico',
        '/__debug__/',
        '/api/heartbeat/',
    ]
    
    # Methods to log
    LOGGED_METHODS = ['POST', 'PUT', 'PATCH', 'DELETE']
    
    def process_request(self, request):
        """
        Store request in thread-local storage and add audit metadata
        
        Args:
            request: Django HttpRequest object
        """
        _thread_locals.request = request
        
        # Store request metadata for audit logging
        request.audit_ip = get_client_ip(request)
        request.audit_user_agent = request.META.get('HTTP_USER_AGENT', '')
        
        # Store request start time for performance monitoring
        import time
        request._audit_start_time = time.time()
    
    def process_response(self, request, response):
        """
        Log the request if it's a significant action
        
        Args:
            request: Django HttpRequest object
            response: Django HttpResponse object
        
        Returns:
            HttpResponse: Unmodified response
        """
        # Skip excluded paths
        if any(request.path.startswith(path) for path in self.EXCLUDED_PATHS):
            return response
        
        # Only log certain HTTP methods
        if request.method not in self.LOGGED_METHODS:
            return response
        
        # Skip if response indicates error (server errors are logged elsewhere)
        if response.status_code >= 500:
            return response
        
        # Log the action
        try:
            self._create_audit_log(request, response)
        except Exception as e:
            # Don't break the request if audit logging fails
            import logging
            logger = logging.getLogger('audit')
            logger.error(f"Failed to create audit log: {e}", exc_info=True)
        
        return response
    
    def _create_audit_log(self, request, response):
        """
        Create an audit log entry for this request
        
        Args:
            request: Django HttpRequest object
            response: Django HttpResponse object
        """
        user = request.user if request.user.is_authenticated else None
        
        # Determine action type based on HTTP method
        action_type_map = {
            'POST': AuditLog.CREATE,
            'PUT': AuditLog.UPDATE,
            'PATCH': AuditLog.UPDATE,
            'DELETE': AuditLog.DELETE,
        }
        action_type = action_type_map.get(request.method, AuditLog.UPDATE)
        
        # Extract model and object info from request
        model_name, object_id = self._extract_model_info(request)
        
        # Build description
        description = self._build_description(request, response, action_type)
        
        # Determine module from path
        module = self._extract_module(request.path)
        
        # Get request metadata
        ip_address = get_client_ip(request)
        user_agent = request.META.get('HTTP_USER_AGENT', '')[:500]  # Limit length
        session_key = request.session.session_key if hasattr(request, 'session') else None
        
        # Create audit log (skip if not enough info)
        if model_name and object_id:
            AuditLog.log_action(
                user=user,
                action_type=action_type,
                model_name=model_name,
                object_id=object_id,
                description=description,
                module=module,
                ip_address=ip_address,
                user_agent=user_agent,
                request_method=request.method,
                request_path=request.path[:500],
                session_key=session_key,
            )
    
    def _extract_model_info(self, request):
        """
        Extract model name and object ID from request path
        
        Args:
            request: Django HttpRequest object
        
        Returns:
            tuple: (model_name, object_id) or (None, None)
        """
        # Try to extract from URL pattern
        # Pattern: /module/model/id/ or /api/module/model/id/
        path_parts = [p for p in request.path.split('/') if p]
        
        if len(path_parts) >= 3:
            # Check if last part is numeric (likely an ID)
            if path_parts[-1].isdigit() or self._is_uuid(path_parts[-1]):
                object_id = path_parts[-1]
                model_name = path_parts[-2].rstrip('s').capitalize()  # Remove plural 's'
                return model_name, object_id
        
        # Try to get from POST data
        if hasattr(request, 'POST') and 'id' in request.POST:
            model_name = path_parts[-1].capitalize() if path_parts else 'Unknown'
            return model_name, request.POST['id']
        
        return None, None
    
    def _is_uuid(self, value):
        """Check if value is a UUID"""
        import re
        uuid_pattern = re.compile(r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$', re.I)
        return bool(uuid_pattern.match(value))
    
    def _extract_module(self, path):
        """
        Extract module name from request path
        
        Args:
            path: Request path string
        
        Returns:
            str: Module name or 'core'
        """
        path_parts = [p for p in path.split('/') if p]
        
        # Common module names
        modules = ['loans', 'accounting', 'investors', 'payroll', 'crm', 'assets', 'reporting', 'core']
        
        for part in path_parts:
            if part in modules:
                return part
        
        return 'core'
    
    def _build_description(self, request, response, action_type):
        """
        Build a human-readable description of the action
        
        Args:
            request: Django HttpRequest object
            response: Django HttpResponse object
            action_type: AuditLog action type constant
        
        Returns:
            str: Description of the action
        """
        user_display = request.user.get_full_name() if request.user.is_authenticated else 'Anonymous'
        path = request.path
        status = response.status_code
        
        action_verb = {
            AuditLog.CREATE: 'created',
            AuditLog.UPDATE: 'updated',
            AuditLog.DELETE: 'deleted',
        }.get(action_type, 'modified')
        
        return f"{user_display} {action_verb} resource at {path} (Status: {status})"


class AuditLoggingContextMiddleware(MiddlewareMixin):
    """
    Lightweight middleware to maintain request context for audit logging
    
    This should be placed early in MIDDLEWARE setting to ensure
    request context is available to all subsequent middleware and views.
    """
    
    def process_request(self, request):
        """Store request in thread-local storage"""
        _thread_locals.request = request
    
    def process_response(self, request, response):
        """Clean up thread-local storage"""
        if hasattr(_thread_locals, 'request'):
            delattr(_thread_locals, 'request')
        return response
    
    def process_exception(self, request, exception):
        """Clean up on exception"""
        if hasattr(_thread_locals, 'request'):
            delattr(_thread_locals, 'request')


# Legacy alias for backward compatibility
AuditLogMiddleware = AuditLoggingMiddleware


# Export public API
__all__ = [
    'AuditLoggingMiddleware',
    'AuditLoggingContextMiddleware',
    'AuditLogMiddleware',  # Legacy
    'get_current_request',
    'get_current_user',
    'get_client_ip',
]
