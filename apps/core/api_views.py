"""
Core API Views
REST API endpoints for core functionality
"""
from rest_framework import generics, permissions
from rest_framework.response import Response
from ..models import User, Notification
from .serializers import UserSerializer, NotificationSerializer


class UserListAPIView(generics.ListAPIView):
    """List all users"""
    queryset = User.objects.all()
    serializer_class = UserSerializer
    permission_classes = [permissions.IsAuthenticated]


class NotificationListAPIView(generics.ListAPIView):
    """List user notifications"""
    serializer_class = NotificationSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        return self.request.user.notifications.filter(is_read=False)
