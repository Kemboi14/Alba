"""
Core URL Configuration
"""
from django.urls import path
from . import views
from . import mfa_views

app_name = 'core'

urlpatterns = [
    # Authentication
    path('', views.DashboardView.as_view(), name='dashboard'),
    path('login/', views.LoginView.as_view(), name='login'),
    path('logout/', views.LogoutView.as_view(), name='logout'),
    path('profile/', views.ProfileView.as_view(), name='profile'),
    path('change-password/', views.ChangePasswordView.as_view(), name='change_password'),
    
    # Multi-Factor Authentication
    path('mfa/setup/', mfa_views.MFASetupView.as_view(), name='mfa_setup'),
    path('mfa/verify/', mfa_views.MFAVerificationView.as_view(), name='mfa_verify'),
    path('mfa/disable/', mfa_views.MFADisableView.as_view(), name='mfa_disable'),
    
    # User Management
    path('users/', views.UserListView.as_view(), name='user_list'),
    path('users/create/', views.UserCreateView.as_view(), name='user_create'),
    path('users/<int:pk>/', views.UserDetailView.as_view(), name='user_detail'),
    path('users/<int:pk>/edit/', views.UserUpdateView.as_view(), name='user_edit'),
    
    # Role Management
    path('roles/', views.RoleListView.as_view(), name='role_list'),
    path('roles/<int:pk>/', views.RoleDetailView.as_view(), name='role_detail'),
    
    # Audit Logs
    path('audit-logs/', views.AuditLogListView.as_view(), name='audit_logs'),
    
    # Notifications
    path('notifications/', views.NotificationListView.as_view(), name='notifications'),
    path('notifications/<int:pk>/mark-read/', views.mark_notification_read, name='notification_mark_read'),
]
