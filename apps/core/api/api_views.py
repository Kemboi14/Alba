"""
Core API Views
"""
from rest_framework import generics
from rest_framework.permissions import IsAuthenticated
from apps.core.models import User, Notification
from .serializers import UserSerializer, NotificationSerializer


class UserListAPIView(generics.ListAPIView):
    """API endpoint for listing users"""
    queryset = User.objects.all()
    serializer_class = UserSerializer
    permission_classes = [IsAuthenticated]


class NotificationListAPIView(generics.ListAPIView):
    """API endpoint for listing notifications"""
    queryset = Notification.objects.all()
    serializer_class = NotificationSerializer
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        """Filter notifications for current user"""
        return self.queryset.filter(user=self.request.user)
