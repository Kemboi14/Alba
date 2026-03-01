"""
Core API Serializers
"""
from rest_framework import serializers
from ..models import User, Role, Notification


class RoleSerializer(serializers.ModelSerializer):
    """Role serializer"""
    
    class Meta:
        model = Role
        fields = ['id', 'name', 'description']


class UserSerializer(serializers.ModelSerializer):
    """User serializer"""
    role = RoleSerializer(read_only=True)
    full_name = serializers.CharField(source='get_full_name', read_only=True)
    
    class Meta:
        model = User
        fields = ['id', 'email', 'first_name', 'last_name', 'full_name',
                 'phone_number', 'role', 'department', 'branch', 'is_active']


class NotificationSerializer(serializers.ModelSerializer):
    """Notification serializer"""
    
    class Meta:
        model = Notification
        fields = ['id', 'title', 'message', 'notification_type', 'is_read',
                 'link', 'created_at']
