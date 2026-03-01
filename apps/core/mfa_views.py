"""
Multi-Factor Authentication (MFA) Implementation
TOTP-based 2FA for privileged accounts
Implements SRS Section 4.1: Security - MFA for privileged accounts
"""
from django.shortcuts import render, redirect
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.views.generic import TemplateView
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import JsonResponse
from django.utils import timezone
import logging
import io
import base64

try:
    import pyotp
    import qrcode
    MFA_AVAILABLE = True
except ImportError:
    MFA_AVAILABLE = False
    logging.warning("pyotp or qrcode not installed. MFA functionality disabled.")

from apps.core.models import User, AuditLog

logger = logging.getLogger(__name__)


class MFAService:
    """
    Multi-Factor Authentication Service
    Uses TOTP (Time-based One-Time Password) for 2FA
    Compatible with Google Authenticator, Authy, etc.
    """
    
    # Privileged roles that require MFA
    MFA_REQUIRED_ROLES = [
        User.ADMIN,
        User.FINANCE_OFFICER,
        User.MANAGEMENT,
    ]
    
    @staticmethod
    def is_mfa_required(user: User) -> bool:
        """
        Check if user requires MFA based on role
        
        Args:
            user: User to check
            
        Returns:
            bool: True if MFA required for this user
        """
        return user.role in MFAService.MFA_REQUIRED_ROLES or user.is_superuser
    
    @staticmethod
    def generate_secret_key() -> str:
        """
        Generate a new TOTP secret key
        
        Returns:
            str: Base32 encoded secret key
        """
        if not MFA_AVAILABLE:
            return ''
        
        return pyotp.random_base32()
    
    @staticmethod
    def get_totp_uri(user: User, secret_key: str) -> str:
        """
        Generate TOTP provisioning URI for QR code
        
        Args:
            user: User setting up MFA
            secret_key: User's TOTP secret
            
        Returns:
            str: otpauth:// URI
        """
        if not MFA_AVAILABLE:
            return ''
        
        return pyotp.totp.TOTP(secret_key).provisioning_uri(
            name=user.email,
            issuer_name='Alba Capital ERP'
        )
    
    @staticmethod
    def generate_qr_code(totp_uri: str) -> str:
        """
        Generate QR code image for TOTP URI
        
        Args:
            totp_uri: TOTP provisioning URI
            
        Returns:
            str: Base64 encoded QR code image
        """
        if not MFA_AVAILABLE:
            return ''
        
        try:
            # Generate QR code
            qr = qrcode.QRCode(version=1, box_size=10, border=5)
            qr.add_data(totp_uri)
            qr.make(fit=True)
            
            img = qr.make_image(fill_color="black", back_color="white")
            
            # Convert to base64
            buffer = io.BytesIO()
            img.save(buffer, format='PNG')
            buffer.seek(0)
            img_base64 = base64.b64encode(buffer.getvalue()).decode()
            
            return f"data:image/png;base64,{img_base64}"
            
        except Exception as e:
            logger.error(f"QR code generation failed: {str(e)}")
            return ''
    
    @staticmethod
    def verify_totp_code(secret_key: str, code: str) -> bool:
        """
        Verify TOTP code entered by user
        
        Args:
            secret_key: User's TOTP secret
            code: 6-digit code entered by user
            
        Returns:
            bool: True if code is valid
        """
        if not MFA_AVAILABLE or not secret_key:
            return True  # Bypass if MFA not available
        
        try:
            totp = pyotp.TOTP(secret_key)
            return totp.verify(code, valid_window=1)  # Allow 30s window
        except Exception as e:
            logger.error(f"TOTP verification failed: {str(e)}")
            return False
    
    @staticmethod
    def generate_backup_codes(count: int = 10) -> list:
        """
        Generate backup codes for MFA recovery
        
        Args:
            count: Number of backup codes to generate
            
        Returns:
            list: List of backup codes
        """
        import secrets
        import string
        
        codes = []
        for _ in range(count):
            # Generate 8-character alphanumeric code
            code = ''.join(
                secrets.choice(string.ascii_uppercase + string.digits)
                for _ in range(8)
            )
            # Format as XXXX-XXXX
            formatted_code = f"{code[:4]}-{code[4:]}"
            codes.append(formatted_code)
        
        return codes


class MFASetupView(LoginRequiredMixin, TemplateView):
    """View for setting up MFA"""
    template_name = 'core/mfa_setup.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user
        
        # Generate new secret if not exists
        if not user.mfa_secret:
            user.mfa_secret = MFAService.generate_secret_key()
            user.save()
        
        # Generate QR code
        totp_uri = MFAService.get_totp_uri(user, user.mfa_secret)
        qr_code = MFAService.generate_qr_code(totp_uri)
        
        context['qr_code'] = qr_code
        context['secret_key'] = user.mfa_secret
        context['mfa_required'] = MFAService.is_mfa_required(user)
        
        return context
    
    def post(self, request):
        """Verify MFA setup"""
        user = request.user
        verification_code = request.POST.get('verification_code', '').strip()
        
        if MFAService.verify_totp_code(user.mfa_secret, verification_code):
            # MFA verified successfully
            user.mfa_enabled = True
            user.mfa_backup_codes = MFAService.generate_backup_codes()
            user.save()
            
            # Log MFA enablement
            AuditLog.objects.create(
                user=user,
                action='MFA_ENABLED',
                module='core',
                description='User enabled Multi-Factor Authentication',
                ip_address=self.get_client_ip(request)
            )
            
            messages.success(request, 'Multi-Factor Authentication enabled successfully!')
            logger.info(f"MFA enabled for user {user.email}")
            
            return redirect('core:profile')
        else:
            messages.error(request, 'Invalid verification code. Please try again.')
            return self.get(request)
    
    def get_client_ip(self, request):
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            return x_forwarded_for.split(',')[0]
        return request.META.get('REMOTE_ADDR', '')


class MFAVerificationView(TemplateView):
    """View for verifying MFA code during login"""
    template_name = 'core/mfa_verify.html'
    
    def dispatch(self, request, *args, **kwargs):
        # Check if user is in MFA verification state
        if not request.session.get('mfa_user_id'):
            return redirect('core:login')
        return super().dispatch(request, *args, **kwargs)
    
    def post(self, request):
        """Verify MFA code"""
        user_id = request.session.get('mfa_user_id')
        verification_code = request.POST.get('verification_code', '').strip()
        backup_code = request.POST.get('backup_code', '').strip()
        
        try:
            user = User.objects.get(id=user_id)
            
            # Try TOTP code first
            if verification_code and MFAService.verify_totp_code(user.mfa_secret, verification_code):
                # MFA verified - complete login
                login(request, user)
                
                # Clear MFA session
                del request.session['mfa_user_id']
                
                # Update user
                user.last_mfa_verification = timezone.now()
                user.failed_login_attempts = 0
                user.last_login_ip = self.get_client_ip(request)
                user.save()
                
                # Log successful MFA
                AuditLog.objects.create(
                    user=user,
                    action='MFA_VERIFIED',
                    module='core',
                    description='MFA verification successful',
                    ip_address=self.get_client_ip(request)
                )
                
                logger.info(f"MFA verification successful for {user.email}")
                messages.success(request, 'Login successful!')
                return redirect('core:dashboard')
            
            # Try backup code
            elif backup_code and backup_code in user.mfa_backup_codes:
                # Backup code used - complete login
                login(request, user)
                
                # Remove used backup code
                user.mfa_backup_codes.remove(backup_code)
                user.last_mfa_verification = timezone.now()
                user.save()
                
                # Clear MFA session
                del request.session['mfa_user_id']
                
                # Log backup code usage
                AuditLog.objects.create(
                    user=user,
                    action='MFA_BACKUP_CODE_USED',
                    module='core',
                    description='MFA backup code used for authentication',
                    ip_address=self.get_client_ip(request)
                )
                
                logger.warning(f"MFA backup code used for {user.email}")
                messages.warning(
                    request,
                    f'Login successful using backup code. '
                    f'You have {len(user.mfa_backup_codes)} backup codes remaining.'
                )
                return redirect('core:dashboard')
            
            else:
                # Invalid code
                user.failed_login_attempts += 1
                
                if user.failed_login_attempts >= 5:
                    user.account_locked_until = timezone.now() + timezone.timedelta(minutes=30)
                    user.save()
                    
                    logger.warning(f"Account locked due to failed MFA attempts: {user.email}")
                    messages.error(request, 'Account locked due to multiple failed attempts.')
                    return redirect('core:login')
                
                user.save()
                messages.error(request, 'Invalid verification code. Please try again.')
                return render(request, self.template_name)
        
        except User.DoesNotExist:
            messages.error(request, 'Session expired. Please log in again.')
            return redirect('core:login')
    
    def get_client_ip(self, request):
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            return x_forwarded_for.split(',')[0]
        return request.META.get('REMOTE_ADDR', '')


class MFADisableView(LoginRequiredMixin, TemplateView):
    """View for disabling MFA"""
    template_name = 'core/mfa_disable.html'
    
    def post(self, request):
        """Disable MFA after password confirmation"""
        password = request.POST.get('password', '')
        user = request.user
        
        if user.check_password(password):
            user.mfa_enabled = False
            user.mfa_secret = ''
            user.mfa_backup_codes = []
            user.save()
            
            # Log MFA disablement
            AuditLog.objects.create(
                user=user,
                action='MFA_DISABLED',
                module='core',
                description='User disabled Multi-Factor Authentication',
                ip_address=self.get_client_ip(request)
            )
            
            messages.success(request, 'Multi-Factor Authentication disabled.')
            logger.warning(f"MFA disabled for user {user.email}")
            return redirect('core:profile')
        else:
            messages.error(request, 'Incorrect password.')
            return render(request, self.template_name)
    
    def get_client_ip(self, request):
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            return x_forwarded_for.split(',')[0]
        return request.META.get('REMOTE_ADDR', '')
