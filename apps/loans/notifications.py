"""
Notification Service
Automated Email and SMS notifications for Alba Capital ERP
Implements SRS Section 3.10: Communication & Notifications
"""
from typing import Dict, List, Optional, Any
from decimal import Decimal
from datetime import datetime, date
from django.core.mail import send_mail, EmailMultiAlternatives
from django.template.loader import render_to_string
from django.conf import settings
from django.utils import timezone
from django.db import transaction
import logging

# SMS Integration
try:
    import africastalking
    AFRICASTALKING_AVAILABLE = True
except ImportError:
    AFRICASTALKING_AVAILABLE = False
    logging.warning("africastalking not installed. SMS notifications disabled.")

logger = logging.getLogger(__name__)


class NotificationService:
    """
    Centralized notification service for email and SMS
    
    Features:
    - Email notifications with HTML templates
    - SMS notifications via Africa's Talking
    - Automatic logging of all communications
    - Retry logic for failed deliveries
    - Template-based messages for consistency
    """
    
    def __init__(self):
        """Initialize Africa's Talking SMS client"""
        self.sms_enabled = AFRICASTALKING_AVAILABLE and hasattr(settings, 'SMS_API_KEY')
        
        if self.sms_enabled:
            try:
                africastalking.initialize(
                    username=settings.SMS_USERNAME,
                    api_key=settings.SMS_API_KEY
                )
                self.sms = africastalking.SMS
                logger.info("SMS service initialized successfully")
            except Exception as e:
                logger.error(f"SMS service initialization failed: {str(e)}")
                self.sms_enabled = False
        else:
            logger.warning("SMS service not configured")
    
    # ========================================================================
    # EMAIL NOTIFICATIONS
    # ========================================================================
    
    def send_email_notification(
        self,
        recipient_email: str,
        subject: str,
        template_name: str,
        context: Dict[str, Any],
        cc: Optional[List[str]] = None,
        attachments: Optional[List[tuple]] = None
    ) -> bool:
        """
        Send email notification using HTML template
        
        Args:
            recipient_email: Recipient email address
            subject: Email subject
            template_name: Path to HTML template (e.g., 'emails/loan_approved.html')
            context: Template context variables
            cc: CC recipients (optional)
            attachments: List of (filename, content, mimetype) tuples
            
        Returns:
            bool: Success status
        """
        try:
            # Render email template
            html_content = render_to_string(template_name, context)
            text_content = f"{subject}\n\n{context.get('message', '')}"
            
            # Create email
            email = EmailMultiAlternatives(
                subject=subject,
                body=text_content,
                from_email=settings.DEFAULT_FROM_EMAIL,
                to=[recipient_email],
                cc=cc or []
            )
            email.attach_alternative(html_content, "text/html")
            
            # Add attachments if provided
            if attachments:
                for filename, content, mimetype in attachments:
                    email.attach(filename, content, mimetype)
            
            # Send email
            email.send()
            
            # Log success
            self._log_notification(
                recipient=recipient_email,
                notification_type='EMAIL',
                subject=subject,
                status='SENT',
                details={'template': template_name}
            )
            
            logger.info(f"Email sent to {recipient_email}: {subject}")
            return True
            
        except Exception as e:
            logger.error(f"Email sending failed to {recipient_email}: {str(e)}")
            self._log_notification(
                recipient=recipient_email,
                notification_type='EMAIL',
                subject=subject,
                status='FAILED',
                details={'error': str(e)}
            )
            return False
    
    # ========================================================================
    # SMS NOTIFICATIONS
    # ========================================================================
    
    def send_sms_notification(
        self,
        recipient_phone: str,
        message: str,
        sender_id: Optional[str] = None
    ) -> bool:
        """
        Send SMS notification via Africa's Talking
        
        Args:
            recipient_phone: Phone number in format +254712345678
            message: SMS message (max 160 chars for single SMS)
            sender_id: Optional custom sender ID
            
        Returns:
            bool: Success status
        """
        if not self.sms_enabled:
            logger.warning(f"SMS sending skipped (not configured): {recipient_phone}")
            return False
        
        try:
            # Ensure phone number has country code
            if not recipient_phone.startswith('+'):
                if recipient_phone.startswith('0'):
                    recipient_phone = '+254' + recipient_phone[1:]
                elif recipient_phone.startswith('254'):
                    recipient_phone = '+' + recipient_phone
            
            # Use custom sender ID or default
            sender = sender_id or getattr(settings, 'SMS_SENDER_ID', 'ALBACAPITAL')
            
            # Send SMS
            response = self.sms.send(message, [recipient_phone], sender)
            
            # Check response
            if response['SMSMessageData']['Recipients']:
                recipient_data = response['SMSMessageData']['Recipients'][0]
                status = recipient_data.get('status', 'Unknown')
                
                if status == 'Success':
                    self._log_notification(
                        recipient=recipient_phone,
                        notification_type='SMS',
                        subject=message[:50],
                        status='SENT',
                        details={'response': str(response)}
                    )
                    logger.info(f"SMS sent to {recipient_phone}")
                    return True
                else:
                    logger.warning(f"SMS delivery uncertain to {recipient_phone}: {status}")
                    return False
            
            return False
            
        except Exception as e:
            logger.error(f"SMS sending failed to {recipient_phone}: {str(e)}")
            self._log_notification(
                recipient=recipient_phone,
                notification_type='SMS',
                subject=message[:50],
                status='FAILED',
                details={'error': str(e)}
            )
            return False
    
    # ========================================================================
    # LOAN LIFECYCLE NOTIFICATIONS
    # ========================================================================
    
    def notify_application_received(self, application: 'LoanApplication') -> bool:
        """Notify customer that application was received"""
        try:
            customer = application.customer
            
            # Email notification
            email_sent = self.send_email_notification(
                recipient_email=customer.email,
                subject=f'Loan Application Received - {application.application_number}',
                template_name='emails/application_received.html',
                context={
                    'customer_name': customer.get_full_name(),
                    'application_number': application.application_number,
                    'product_name': application.loan_product.name,
                    'amount': application.requested_amount,
                    'application_date': application.created_at.date(),
                }
            )
            
            # SMS notification
            sms_message = (
                f"Dear {customer.first_name}, your loan application "
                f"#{application.application_number} for KES {application.requested_amount:,.0f} "
                f"has been received. We will review and respond within 48 hours. - Alba Capital"
            )
            sms_sent = self.send_sms_notification(
                recipient_phone=str(customer.phone_number),
                message=sms_message
            )
            
            return email_sent or sms_sent
            
        except Exception as e:
            logger.error(f"Application notification failed: {str(e)}")
            return False
    
    def notify_application_approved(self, application: 'LoanApplication') -> bool:
        """Notify customer of loan approval"""
        try:
            customer = application.customer
            
            # Email notification
            email_sent = self.send_email_notification(
                recipient_email=customer.email,
                subject=f'Loan Application Approved - {application.application_number}',
                template_name='emails/application_approved.html',
                context={
                    'customer_name': customer.get_full_name(),
                    'application_number': application.application_number,
                    'product_name': application.loan_product.name,
                    'approved_amount': application.approved_amount,
                    'approval_date': timezone.now().date(),
                }
            )
            
            # SMS notification
            sms_message = (
                f"Congratulations {customer.first_name}! Your loan application "
                f"#{application.application_number} for KES {application.approved_amount:,.0f} "
                f"has been APPROVED. Disbursement in progress. - Alba Capital"
            )
            sms_sent = self.send_sms_notification(
                recipient_phone=str(customer.phone_number),
                message=sms_message
            )
            
            return email_sent or sms_sent
            
        except Exception as e:
            logger.error(f"Approval notification failed: {str(e)}")
            return False
    
    def notify_application_rejected(self, application: 'LoanApplication', reason: str = '') -> bool:
        """Notify customer of loan rejection"""
        try:
            customer = application.customer
            
            # Email notification
            email_sent = self.send_email_notification(
                recipient_email=customer.email,
                subject=f'Loan Application Update - {application.application_number}',
                template_name='emails/application_rejected.html',
                context={
                    'customer_name': customer.get_full_name(),
                    'application_number': application.application_number,
                    'product_name': application.loan_product.name,
                    'reason': reason or 'Did not meet our current lending criteria',
                }
            )
            
            # SMS notification
            sms_message = (
                f"Dear {customer.first_name}, we regret that your loan application "
                f"#{application.application_number} was not successful at this time. "
                f"You may reapply after 30 days. - Alba Capital"
            )
            sms_sent = self.send_sms_notification(
                recipient_phone=str(customer.phone_number),
                message=sms_message
            )
            
            return email_sent or sms_sent
            
        except Exception as e:
            logger.error(f"Rejection notification failed: {str(e)}")
            return False
    
    def notify_loan_disbursed(self, loan: 'Loan') -> bool:
        """Notify customer that loan has been disbursed"""
        try:
            customer = loan.customer
            
            # Email notification
            email_sent = self.send_email_notification(
                recipient_email=customer.email,
                subject=f'Loan Disbursed - {loan.loan_number}',
                template_name='emails/loan_disbursed.html',
                context={
                    'customer_name': customer.get_full_name(),
                    'loan_number': loan.loan_number,
                    'product_name': loan.product.name,
                    'principal_amount': loan.principal_amount,
                    'disbursement_date': loan.disbursement_date,
                    'first_payment_date': loan.repayment_schedules.order_by('due_date').first().due_date if loan.repayment_schedules.exists() else None,
                }
            )
            
            # SMS notification
            sms_message = (
                f"Dear {customer.first_name}, your loan KES {loan.principal_amount:,.0f} "
                f"has been disbursed to your account. Loan No: {loan.loan_number}. "
                f"Thank you for choosing Alba Capital."
            )
            sms_sent = self.send_sms_notification(
                recipient_phone=str(customer.phone_number),
                message=sms_message
            )
            
            return email_sent or sms_sent
            
        except Exception as e:
            logger.error(f"Disbursement notification failed: {str(e)}")
            return False
    
    def notify_payment_received(self, payment: 'Payment') -> bool:
        """Notify customer that payment was received"""
        try:
            loan = payment.loan
            customer = loan.customer
            
            # Email notification
            email_sent = self.send_email_notification(
                recipient_email=customer.email,
                subject=f'Payment Received - {loan.loan_number}',
                template_name='emails/payment_received.html',
                context={
                    'customer_name': customer.get_full_name(),
                    'loan_number': loan.loan_number,
                    'payment_amount': payment.amount,
                    'payment_date': payment.payment_date,
                    'outstanding_balance': loan.total_outstanding,
                    'payment_reference': payment.reference_number,
                }
            )
            
            # SMS notification
            sms_message = (
                f"Payment received: KES {payment.amount:,.0f} for loan {loan.loan_number}. "
                f"Balance: KES {loan.total_outstanding:,.0f}. Ref: {payment.reference_number}. "
                f"Thank you! - Alba Capital"
            )
            sms_sent = self.send_sms_notification(
                recipient_phone=str(customer.phone_number),
                message=sms_message
            )
            
            return email_sent or sms_sent
            
        except Exception as e:
            logger.error(f"Payment notification failed: {str(e)}")
            return False
    
    def notify_payment_reminder(self, loan: 'Loan', days_until_due: int) -> bool:
        """
        Send payment reminder before due date
        Implements SRS Section 3.10: Payment reminders
        """
        try:
            customer = loan.customer
            
            # Get next payment due
            next_schedule = loan.repayment_schedules.filter(
                status='PENDING',
                due_date__gte=timezone.now().date()
            ).order_by('due_date').first()
            
            if not next_schedule:
                return False
            
            # Email reminder
            email_sent = self.send_email_notification(
                recipient_email=customer.email,
                subject=f'Payment Reminder - Loan {loan.loan_number}',
                template_name='emails/payment_reminder.html',
                context={
                    'customer_name': customer.get_full_name(),
                    'loan_number': loan.loan_number,
                    'amount_due': next_schedule.amount_due,
                    'due_date': next_schedule.due_date,
                    'days_until_due': days_until_due,
                    'payment_instructions': 'Pay via M-Pesa Paybill or bank transfer',
                }
            )
            
            # SMS reminder
            sms_message = (
                f"Reminder: Loan payment of KES {next_schedule.amount_due:,.0f} "
                f"is due on {next_schedule.due_date:%d-%b-%Y} ({days_until_due} days). "
                f"Loan: {loan.loan_number}. Pay via Paybill. - Alba Capital"
            )
            sms_sent = self.send_sms_notification(
                recipient_phone=str(customer.phone_number),
                message=sms_message
            )
            
            logger.info(f"Payment reminder sent for loan {loan.loan_number}, due in {days_until_due} days")
            return email_sent or sms_sent
            
        except Exception as e:
            logger.error(f"Payment reminder failed: {str(e)}")
            return False
    
    def notify_payment_overdue(self, loan: 'Loan') -> bool:
        """
        Send overdue payment alert
        Implements SRS Section 3.10: Overdue alerts
        """
        try:
            customer = loan.customer
            
            # Email alert
            email_sent = self.send_email_notification(
                recipient_email=customer.email,
                subject=f'URGENT: Overdue Payment - Loan {loan.loan_number}',
                template_name='emails/payment_overdue.html',
                context={
                    'customer_name': customer.get_full_name(),
                    'loan_number': loan.loan_number,
                    'days_overdue': loan.days_overdue,
                    'overdue_amount': loan.total_outstanding,  # Using total outstanding
                    'total_outstanding': loan.total_outstanding,
                    'penalty_accruing': loan.outstanding_penalties > 0,
                }
            )
            
            # SMS alert
            sms_message = (
                f"URGENT: Your loan {loan.loan_number} is {loan.days_overdue} days overdue. "
                f"Outstanding: KES {loan.total_outstanding:,.0f}. Please pay immediately to avoid penalties. "
                f"Contact us: {settings.COMPANY_PHONE}. - Alba Capital"
            )
            sms_sent = self.send_sms_notification(
                recipient_phone=str(customer.phone_number),
                message=sms_message
            )
            
            logger.warning(f"Overdue alert sent for loan {loan.loan_number}, {loan.days_in_arrears} days overdue")
            return email_sent or sms_sent
            
        except Exception as e:
            logger.error(f"Overdue notification failed: {str(e)}")
            return False
    
    # ========================================================================
    # WORKFLOW NOTIFICATIONS
    # ========================================================================
    
    def notify_credit_officer_new_application(self, application: 'LoanApplication') -> bool:
        """Notify assigned credit officer of new application"""
        try:
            if not application.assigned_to:
                # TODO: Auto-assign based on workload
                return False
            
            officer = application.assigned_to
            
            # Email notification
            email_sent = self.send_email_notification(
                recipient_email=officer.email,
                subject=f'New Loan Application Assigned - {application.application_number}',
                template_name='emails/officer_new_application.html',
                context={
                    'officer_name': officer.get_full_name(),
                    'application_number': application.application_number,
                    'customer_name': application.customer.get_full_name(),
                    'product_name': application.loan_product.name,
                    'requested_amount': application.requested_amount,
                    'credit_score': application.credit_score,
                    'credit_grade': application.credit_grade,
                    'auto_decision': application.auto_decision,
                    'application_url': f'/loans/applications/{application.id}/',
                }
            )
            
            logger.info(f"Credit officer notified: {officer.email} for application {application.id}")
            return email_sent
            
        except Exception as e:
            logger.error(f"Officer notification failed: {str(e)}")
            return False
    
    def notify_employer_verification_request(
        self,
        application: 'LoanApplication',
        employer_email: str,
        employer_contact_person: str = 'HR Department'
    ) -> bool:
        """
        Send employer verification request
        Implements SRS Section 3.1.4: Employer Verification
        """
        try:
            customer = application.customer
            
            # Email to employer
            email_sent = self.send_email_notification(
                recipient_email=employer_email,
                subject=f'Employment Verification Request - {customer.get_full_name()}',
                template_name='emails/employer_verification.html',
                context={
                    'employer_contact': employer_contact_person,
                    'employee_name': customer.get_full_name(),
                    'employee_id_number': customer.national_id,
                    'application_number': application.application_number,
                    'verification_url': f'{settings.BASE_URL}/verify/employer/{application.id}/',
                    'company_name': settings.COMPANY_NAME,
                }
            )
            
            logger.info(f"Employer verification request sent for application {application.id}")
            return email_sent
            
        except Exception as e:
            logger.error(f"Employer verification request failed: {str(e)}")
            return False
    
    def notify_guarantor_consent_request(
        self,
        guarantor: 'Guarantor',
        application: 'LoanApplication'
    ) -> bool:
        """
        Send guarantor consent request
        Implements SRS Section 3.1.4: Guarantor Verification
        """
        try:
            customer = application.customer
            
            # Email to guarantor
            email_sent = self.send_email_notification(
                recipient_email=guarantor.email,
                subject=f'Guarantor Consent Request - {customer.get_full_name()}',
                template_name='emails/guarantor_consent.html',
                context={
                    'guarantor_name': guarantor.get_full_name(),
                    'customer_name': customer.get_full_name(),
                    'loan_amount': application.requested_amount,
                    'product_name': application.loan_product.name,
                    'consent_url': f'{settings.BASE_URL}/verify/guarantor/{guarantor.id}/',
                    'company_name': settings.COMPANY_NAME,
                }
            )
            
            # SMS to guarantor
            sms_message = (
                f"Dear {guarantor.first_name}, {customer.first_name} {customer.last_name} "
                f"has listed you as guarantor for a loan of KES {application.requested_amount:,.0f}. "
                f"Check your email for details. - Alba Capital"
            )
            sms_sent = self.send_sms_notification(
                recipient_phone=str(guarantor.phone_number),
                message=sms_message
            )
            
            logger.info(f"Guarantor consent request sent for application {application.id}, guarantor: {guarantor.email}")
            return email_sent or sms_sent
            
        except Exception as e:
            logger.error(f"Guarantor consent request failed: {str(e)}")
            return False
    
    # ========================================================================
    # BULK NOTIFICATIONS
    # ========================================================================
    
    def send_bulk_payment_reminders(self, days_before_due: int = 3) -> Dict[str, int]:
        """
        Send payment reminders for loans due in X days
        Scheduled via Celery for daily execution
        
        Args:
            days_before_due: Days before due date to send reminder
            
        Returns:
            Dict with success/failure counts
        """
        from apps.loans.models import Loan, RepaymentSchedule
        
        try:
            # Get upcoming payments
            target_date = timezone.now().date() + timedelta(days=days_before_due)
            
            upcoming_payments = RepaymentSchedule.objects.filter(
                due_date=target_date,
                status='PENDING',
                loan__status='ACTIVE'
            ).select_related('loan', 'loan__customer')
            
            success_count = 0
            failure_count = 0
            
            for schedule in upcoming_payments:
                if self.notify_payment_reminder(schedule.loan, days_before_due):
                    success_count += 1
                else:
                    failure_count += 1
            
            logger.info(
                f"Bulk payment reminders sent: {success_count} successful, "
                f"{failure_count} failed for date {target_date}"
            )
            
            return {
                'success': success_count,
                'failed': failure_count,
                'total': upcoming_payments.count()
            }
            
        except Exception as e:
            logger.error(f"Bulk payment reminders failed: {str(e)}")
            return {'success': 0, 'failed': 0, 'total': 0, 'error': str(e)}
    
    def send_bulk_overdue_alerts(self) -> Dict[str, int]:
        """
        Send overdue alerts for all loans in arrears
        Scheduled via Celery for daily execution
        
        Returns:
            Dict with success/failure counts
        """
        from apps.loans.models import Loan
        
        try:
            # Get overdue loans
            overdue_loans = Loan.objects.filter(
                status='ACTIVE',
                days_in_arrears__gt=0
            ).select_related('customer')
            
            success_count = 0
            failure_count = 0
            
            for loan in overdue_loans:
                if self.notify_payment_overdue(loan):
                    success_count += 1
                else:
                    failure_count += 1
            
            logger.info(
                f"Bulk overdue alerts sent: {success_count} successful, "
                f"{failure_count} failed, {overdue_loans.count()} total"
            )
            
            return {
                'success': success_count,
                'failed': failure_count,
                'total': overdue_loans.count()
            }
            
        except Exception as e:
            logger.error(f"Bulk overdue alerts failed: {str(e)}")
            return {'success': 0, 'failed': 0, 'total': 0, 'error': str(e)}
    
    def notify_new_customer_registration(self, customer):
        """
        Notify admin team about new customer registration requiring approval
        
        Args:
            customer: Customer object pending verification
        """
        try:
            # Get admin users for notifications
            from apps.core.models import User
            admin_users = User.objects.filter(
                role__in=['ADMIN', 'SUPERUSER', 'LOAN_OFFICER'],
                is_active=True
            )
            
            success_count = 0
            for admin in admin_users:
                try:
                    subject = f'New Customer Registration - Action Required'
                    message = (
                        f"New customer {customer.get_full_name()} ({customer.customer_number}) "
                        f"registered and requires KYC verification. "
                        f"Email: {customer.email}, Phone: {customer.phone_number}, "
                        f"National ID: {customer.national_id}. "
                        f"Please review and approve in admin panel."
                    )
                    
                    # Send SMS to admin (if configured)
                    self.send_sms_notification(
                        recipient_phone=str(admin.phone_number) if hasattr(admin, 'phone_number') else None,
                        message=message[:160]  # SMS limit
                    )
                    success_count += 1
                    
                except Exception as e:
                    logger.error(f"Admin notification failed for {admin.email}: {str(e)}")
            
            logger.info(f"New registration notifications sent to {success_count} admins")
            return True
            
        except Exception as e:
            logger.error(f"New registration notification failed: {str(e)}")
            return False
    
    # ========================================================================
    # UTILITY METHODS
    # ========================================================================
    
    def _log_notification(
        self,
        recipient: str,
        notification_type: str,
        subject: str,
        status: str,
        details: Optional[Dict] = None
    ):
        """Log notification attempt in database"""
        try:
            from apps.core.models import Notification
            
            Notification.objects.create(
                recipient=recipient,
                notification_type=notification_type,
                subject=subject,
                status=status,
                sent_at=timezone.now() if status == 'SENT' else None,
                details=details or {}
            )
        except Exception as e:
            logger.error(f"Notification logging failed: {str(e)}")


# Global notification service instance
notification_service = NotificationService()
