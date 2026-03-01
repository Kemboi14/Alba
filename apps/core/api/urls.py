"""
Core API URLs
"""
from django.urls import path
from . import api_views

urlpatterns = [
    # Add API endpoints here
    path('users/', api_views.UserListAPIView.as_view(), name='user-list-api'),
    path('notifications/', api_views.NotificationListAPIView.as_view(), name='notification-list-api'),
]
