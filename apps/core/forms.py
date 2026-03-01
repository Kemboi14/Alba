"""
Core Forms
"""
from django import forms
from django.contrib.auth.forms import UserCreationForm, PasswordChangeForm
from .models import User, Role


class LoginForm(forms.Form):
    """Login form"""
    email = forms.EmailField(
        widget=forms.EmailInput(attrs={
            'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500',
            'placeholder': 'Email address'
        })
    )
    password = forms.CharField(
        widget=forms.PasswordInput(attrs={
            'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500',
            'placeholder': 'Password'
        })
    )


class UserForm(UserCreationForm):
    """User creation/update form"""
    
    class Meta:
        model = User
        fields = ['email', 'first_name', 'last_name', 'phone_number', 'role',
                 'department', 'branch', 'employee_id', 'national_id',
                 'date_of_birth', 'address', 'is_active']
        widgets = {
            'date_of_birth': forms.DateInput(attrs={'type': 'date'}),
            'address': forms.Textarea(attrs={'rows': 3}),
        }


class ChangePasswordForm(PasswordChangeForm):
    """Password change form"""
    pass
