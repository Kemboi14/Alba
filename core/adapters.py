"""
Custom allauth adapters for Alba Capital's User model.

Handles Google OAuth signup so new users are assigned the CUSTOMER role
and redirected to the correct dashboard.
"""

from allauth.account.adapter import DefaultAccountAdapter
from allauth.socialaccount.adapter import DefaultSocialAccountAdapter

from .models import User


class AccountAdapter(DefaultAccountAdapter):
    """Route allauth redirects through our own login/dashboard URLs."""

    def get_login_redirect_url(self, request):
        return "/dashboard/"

    def get_logout_redirect_url(self, request):
        return "/"


class SocialAccountAdapter(DefaultSocialAccountAdapter):
    """Populate custom User fields when signing up via Google."""

    def populate_user(self, request, sociallogin, data):
        user = super().populate_user(request, sociallogin, data)
        user.role = User.CUSTOMER
        user.is_approved = True
        return user

    def save_user(self, request, sociallogin, form=None):
        user = super().save_user(request, sociallogin, form)
        if not user.role:
            user.role = User.CUSTOMER
        if not user.is_approved:
            user.is_approved = True
            user.save(update_fields=["role", "is_approved"])
        return user
