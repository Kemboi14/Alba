"""
M-Pesa Payment Integration
Safaricom M-Pesa API integration for loan disbursements and collections
Implements SRS Section 3.4: Payment Platform Integration
"""
from typing import Dict, Optional, Any
from decimal import Decimal
from datetime import datetime, date
from django.conf import settings
from django.utils import timezone
from django.db import transaction
import requests
import base64
import json
import logging

from apps.loans.models import Loan, Payment, Customer
from apps.core.models import User

logger = logging.getLogger(__name__)


class MPesaService:
    """
    M-Pesa Daraja API integration for payments
    
    Features:
    - B2C (Business to Customer) for loan disbursements
    - C2B (Customer to Business) for loan repayments
    - Transaction status queries
    - Automatic reconciliation
    - Full audit trail
    
    API Documentation: https://developer.safaricom.co.ke/docs
    """
    
    def __init__(self):
        """Initialize M-Pesa credentials from settings"""
        self.consumer_key = getattr(settings, 'MPESA_CONSUMER_KEY', '')
        self.consumer_secret = getattr(settings, 'MPESA_CONSUMER_SECRET', '')
        self.shortcode = getattr(settings, 'MPESA_SHORTCODE', '')
        self.passkey = getattr(settings, 'MPESA_PASSKEY', '')
        self.environment = getattr(settings, 'MPESA_ENVIRONMENT', 'sandbox')
        
        # API URLs
        if self.environment == 'production':
            self.base_url = 'https://api.safaricom.co.ke'
        else:
            self.base_url = 'https://sandbox.safaricom.co.ke'
        
        self.auth_url = f'{self.base_url}/oauth/v1/generate?grant_type=client_credentials'
        self.b2c_url = f'{self.base_url}/mpesa/b2c/v1/paymentrequest'
        self.c2b_register_url = f'{self.base_url}/mpesa/c2b/v1/registerurl'
        self.c2b_simulate_url = f'{self.base_url}/mpesa/c2b/v1/simulate'
        self.status_url = f'{self.base_url}/mpesa/transactionstatus/v1/query'
        
        self.enabled = bool(self.consumer_key and self.consumer_secret)
        
        if not self.enabled:
            logger.warning("M-Pesa credentials not configured. Payment integration disabled.")
    
    def _get_access_token(self) -> Optional[str]:
        """
        Get OAuth access token from M-Pesa API
        
        Returns:
            str: Access token or None if failed
        """
        try:
            # Create basic auth header
            auth_string = f"{self.consumer_key}:{self.consumer_secret}"
            auth_bytes = auth_string.encode('ascii')
            auth_base64 = base64.b64encode(auth_bytes).decode('ascii')
            
            headers = {
                'Authorization': f'Basic {auth_base64}',
                'Content-Type': 'application/json'
            }
            
            response = requests.get(self.auth_url, headers=headers, timeout=30)
            response.raise_for_status()
            
            data = response.json()
            access_token = data.get('access_token')
            
            logger.info("M-Pesa access token obtained successfully")
            return access_token
            
        except Exception as e:
            logger.error(f"M-Pesa authentication failed: {str(e)}")
            return None
    
    def disburse_loan(
        self,
        loan: Loan,
        phone_number: str,
        amount: Decimal,
        remarks: str = 'Loan Disbursement'
    ) -> Dict[str, Any]:
        """
        Disburse loan to customer via M-Pesa B2C
        
        Args:
            loan: Loan object being disbursed
            phone_number: Customer's M-Pesa phone number (+254...)
            amount: Amount to disburse
            remarks: Transaction remarks
            
        Returns:
            Dict with transaction details and status
        """
        if not self.enabled:
            return {
                'success': False,
                'error': 'M-Pesa not configured',
                'transaction_id': None
            }
        
        try:
            access_token = self._get_access_token()
            if not access_token:
                return {
                    'success': False,
                    'error': 'Authentication failed',
                    'transaction_id': None
                }
            
            # Format phone number
            if phone_number.startswith('+'):
                phone_number = phone_number[1:]
            if phone_number.startswith('0'):
                phone_number = '254' + phone_number[1:]
            
            # Prepare B2C request
            headers = {
                'Authorization': f'Bearer {access_token}',
                'Content-Type': 'application/json'
            }
            
            payload = {
                'InitiatorName': 'AlbaCapital',  # API initiator name from portal
                'SecurityCredential': self._get_security_credential(),
                'CommandID': 'BusinessPayment',
                'Amount': str(int(amount)),
                'PartyA': self.shortcode,
                'PartyB': phone_number,
                'Remarks': remarks,
                'QueueTimeOutURL': f'{settings.BASE_URL}/api/mpesa/timeout/',
                'ResultURL': f'{settings.BASE_URL}/api/mpesa/b2c/result/',
                'Occasion': f'Loan {loan.loan_number} disbursement'
            }
            
            response = requests.post(
                self.b2c_url,
                json=payload,
                headers=headers,
                timeout=30
            )
            response.raise_for_status()
            
            data = response.json()
            
            if data.get('ResponseCode') == '0':
                # Success - payment initiated
                conversation_id = data.get('ConversationID')
                originator_conversation_id = data.get('OriginatorConversationID')
                
                logger.info(
                    f"M-Pesa disbursement initiated for loan {loan.loan_number}: "
                    f"Amount {amount}, ConversationID: {conversation_id}"
                )
                
                # Update loan status
                loan.disbursement_method = 'MPESA'
                loan.disbursement_reference = conversation_id
                loan.save()
                
                return {
                    'success': True,
                    'transaction_id': conversation_id,
                    'originator_conversation_id': originator_conversation_id,
                    'response_description': data.get('ResponseDescription'),
                    'phone_number': phone_number,
                    'amount': amount
                }
            else:
                logger.error(f"M-Pesa disbursement failed: {data}")
                return {
                    'success': False,
                    'error': data.get('ResponseDescription', 'Unknown error'),
                    'transaction_id': None
                }
        
        except Exception as e:
            logger.error(f"M-Pesa disbursement exception: {str(e)}")
            return {
                'success': False,
                'error': str(e),
                'transaction_id': None
            }
    
    def process_c2b_payment(
        self,
        callback_data: Dict[str, Any]
    ) -> bool:
        """
        Process incoming C2B payment callback from M-Pesa
        Automatically allocates payment to correct loan account
        
        Args:
            callback_data: M-Pesa callback JSON data
            
        Returns:
            bool: Success status
        """
        try:
            # Extract callback parameters
            transaction_type = callback_data.get('TransactionType')
            trans_id = callback_data.get('TransID')
            trans_time = callback_data.get('TransTime')
            trans_amount = Decimal(callback_data.get('TransAmount', '0'))
            business_short_code = callback_data.get('BusinessShortCode')
            bill_ref_number = callback_data.get('BillRefNumber', '')
            msisdn = callback_data.get('MSISDN')
            first_name = callback_data.get('FirstName', '')
            last_name = callback_data.get('LastName', '')
            
            logger.info(
                f"Processing M-Pesa C2B payment: TransID={trans_id}, "
                f"Amount={trans_amount}, BillRef={bill_ref_number}"
            )
            
            # Try to find loan by bill reference number (loan number)
            loan = None
            if bill_ref_number:
                try:
                    loan = Loan.objects.get(loan_number=bill_ref_number.strip())
                except Loan.DoesNotExist:
                    logger.warning(f"Loan not found for bill reference: {bill_ref_number}")
            
            # If no loan found, try to find by phone number
            if not loan and msisdn:
                try:
                    # Format phone number
                    phone = msisdn if msisdn.startswith('+') else f'+{msisdn}'
                    customer = Customer.objects.filter(phone_number=phone).first()
                    
                    if customer:
                        # Get customer's most recent active loan
                        loan = Loan.objects.filter(
                            customer=customer,
                            status='ACTIVE'
                        ).order_by('-disbursement_date').first()
                except Exception as e:
                    logger.warning(f"Customer lookup failed: {str(e)}")
            
            # Create payment record
            with transaction.atomic():
                # Get system user for created_by
                system_user = User.objects.filter(is_superuser=True).first()
                if not system_user:
                    system_user = User.objects.filter(is_staff=True).first()
                
                payment = Payment.objects.create(
                    loan=loan,
                    customer=loan.customer if loan else None,
                    payment_date=datetime.strptime(trans_time, '%Y%m%d%H%M%S').date(),
                    amount=trans_amount,
                    payment_method='MPESA',
                    reference_number=trans_id,
                    notes=f"M-Pesa C2B: {first_name} {last_name}, BillRef: {bill_ref_number}, MSISDN: {msisdn}",
                    created_by=system_user
                )
                
                if loan:
                    # Allocate payment to loan (principal, interest, fees, penalties)
                    self._allocate_payment(loan, payment)
                    
                    logger.info(
                        f"Payment allocated successfully: {trans_id} -> Loan {loan.loan_number}, "
                        f"Amount: {trans_amount}"
                    )
                    
                    # Send payment confirmation to customer
                    from apps.loans.notifications import notification_service
                    notification_service.notify_payment_received(payment)
                else:
                    logger.warning(
                        f"Payment received but not allocated: {trans_id}, "
                        f"Amount: {trans_amount}, BillRef: {bill_ref_number}"
                    )
            
            return True
            
        except Exception as e:
            logger.error(f"C2B payment processing failed: {str(e)}")
            return False
    
    def _allocate_payment(self, loan: Loan, payment: Payment):
        """
        Allocate payment to loan in order: Penalties → Interest → Fees → Principal
        
        Args:
            loan: Loan receiving payment
            payment: Payment to allocate
        """
        remaining_amount = payment.amount
        
        # Allocation order as per standard practice
        allocations = {}
        
        # 1. Penalties first
        if loan.outstanding_penalties > 0 and remaining_amount > 0:
            penalty_payment = min(remaining_amount, loan.outstanding_penalties)
            allocations['penalty'] = penalty_payment
            remaining_amount -= penalty_payment
            loan.outstanding_penalties -= penalty_payment
        
        # 2. Interest second
        if loan.outstanding_interest > 0 and remaining_amount > 0:
            interest_payment = min(remaining_amount, loan.outstanding_interest)
            allocations['interest'] = interest_payment
            remaining_amount -= interest_payment
            loan.outstanding_interest -= interest_payment
        
        # 3. Fees third
        if loan.outstanding_fees > 0 and remaining_amount > 0:
            fee_payment = min(remaining_amount, loan.outstanding_fees)
            allocations['fees'] = fee_payment
            remaining_amount -= fee_payment
            loan.outstanding_fees -= fee_payment
        
        # 4. Principal last
        if remaining_amount > 0:
            principal_payment = min(remaining_amount, loan.outstanding_principal)
            allocations['principal'] = principal_payment
            loan.outstanding_principal -= principal_payment
        
        # Update loan total outstanding
        loan.total_outstanding = (
            loan.outstanding_principal + loan.outstanding_interest + 
            loan.outstanding_fees + loan.outstanding_penalties
        )
        loan.total_paid += payment.amount
        
        # Update payment allocation
        payment.principal_paid = allocations.get('principal', Decimal('0'))
        payment.interest_paid = allocations.get('interest', Decimal('0'))
        payment.fees_paid = allocations.get('fees', Decimal('0'))
        payment.penalty_paid = allocations.get('penalty', Decimal('0'))
        payment.is_reconciled = True
        payment.save()
        
        # Check if loan is fully paid
        if loan.total_outstanding <= Decimal('0.01'):  # Allow for rounding
            loan.status = 'CLOSED'
            loan.closed_at = timezone.now()
        
        loan.save()
        
        logger.info(
            f"Payment allocated for loan {loan.loan_number}: "
            f"Principal={allocations.get('principal', 0)}, "
            f"Interest={allocations.get('interest', 0)}, "
            f"Fees={allocations.get('fees', 0)}, "
            f"Penalties={allocations.get('penalty', 0)}"
        )
    
    def register_c2b_urls(self) -> bool:
        """
        Register C2B validation and confirmation URLs with M-Pesa
        Should be called once during system setup
        
        Returns:
            bool: Success status
        """
        if not self.enabled:
            logger.warning("M-Pesa not configured. C2B URL registration skipped.")
            return False
        
        try:
            access_token = self._get_access_token()
            if not access_token:
                return False
            
            headers = {
                'Authorization': f'Bearer {access_token}',
                'Content-Type': 'application/json'
            }
            
            payload = {
                'ShortCode': self.shortcode,
                'ResponseType': 'Completed',  # or 'Cancelled'
                'ConfirmationURL': f'{settings.BASE_URL}/api/mpesa/c2b/confirmation/',
                'ValidationURL': f'{settings.BASE_URL}/api/mpesa/c2b/validation/',
            }
            
            response = requests.post(
                self.c2b_register_url,
                json=payload,
                headers=headers,
                timeout=30
            )
            response.raise_for_status()
            
            data = response.json()
            
            if data.get('ResponseCode') == '0':
                logger.info("M-Pesa C2B URLs registered successfully")
                return True
            else:
                logger.error(f"C2B URL registration failed: {data}")
                return False
        
        except Exception as e:
            logger.error(f"C2B URL registration exception: {str(e)}")
            return False
    
    def query_transaction_status(self, transaction_id: str) -> Dict[str, Any]:
        """
        Query status of M-Pesa transaction
        
        Args:
            transaction_id: M-Pesa transaction ID
            
        Returns:
            Dict with transaction status details
        """
        if not self.enabled:
            return {'success': False, 'error': 'M-Pesa not configured'}
        
        try:
            access_token = self._get_access_token()
            if not access_token:
                return {'success': False, 'error': 'Authentication failed'}
            
            headers = {
                'Authorization': f'Bearer {access_token}',
                'Content-Type': 'application/json'
            }
            
            payload = {
                'Initiator': 'AlbaCapital',
                'SecurityCredential': self._get_security_credential(),
                'CommandID': 'TransactionStatusQuery',
                'TransactionID': transaction_id,
                'PartyA': self.shortcode,
                'IdentifierType': '4',  # Shortcode identifier
                'ResultURL': f'{settings.BASE_URL}/api/mpesa/status/result/',
                'QueueTimeOutURL': f'{settings.BASE_URL}/api/mpesa/timeout/',
                'Remarks': 'Transaction status query',
                'Occasion': 'Status check'
            }
            
            response = requests.post(
                self.status_url,
                json=payload,
                headers=headers,
                timeout=30
            )
            response.raise_for_status()
            
            data = response.json()
            logger.info(f"Transaction status queried: {transaction_id}")
            
            return {
                'success': True,
                'data': data
            }
            
        except Exception as e:
            logger.error(f"Transaction status query failed: {str(e)}")
            return {'success': False, 'error': str(e)}
    
    def _get_security_credential(self) -> str:
        """
        Generate security credential for M-Pesa API
        Encrypts initiator password with M-Pesa public key
        
        Returns:
            str: Base64 encoded security credential
        """
        # TODO: Implement proper RSA encryption with M-Pesa public certificate
        # For now, return placeholder
        # In production, encrypt initiator password with Safaricom's public key
        return "placeholder_security_credential"
    
    def simulate_c2b_payment(
        self,
        phone_number: str,
        amount: Decimal,
        bill_ref_number: str
    ) -> Dict[str, Any]:
        """
        Simulate C2B payment (sandbox only)
        Used for testing payment integration
        
        Args:
            phone_number: Customer phone number
            amount: Payment amount
            bill_ref_number: Loan number or reference
            
        Returns:
            Dict with simulation result
        """
        if not self.enabled or self.environment != 'sandbox':
            return {
                'success': False,
                'error': 'C2B simulation only available in sandbox mode'
            }
        
        try:
            access_token = self._get_access_token()
            if not access_token:
                return {'success': False, 'error': 'Authentication failed'}
            
            # Format phone number
            if phone_number.startswith('+'):
                phone_number = phone_number[1:]
            if phone_number.startswith('0'):
                phone_number = '254' + phone_number[1:]
            
            headers = {
                'Authorization': f'Bearer {access_token}',
                'Content-Type': 'application/json'
            }
            
            payload = {
                'ShortCode': self.shortcode,
                'CommandID': 'CustomerPayBillOnline',
                'Amount': str(int(amount)),
                'Msisdn': phone_number,
                'BillRefNumber': bill_ref_number
            }
            
            response = requests.post(
                self.c2b_simulate_url,
                json=payload,
                headers=headers,
                timeout=30
            )
            response.raise_for_status()
            
            data = response.json()
            logger.info(f"C2B payment simulated: {data}")
            
            return {
                'success': True,
                'data': data
            }
            
        except Exception as e:
            logger.error(f"C2B simulation failed: {str(e)}")
            return {'success': False, 'error': str(e)}


class PaymentReconciliationService:
    """
    Automatic payment reconciliation service
    Matches incoming M-Pesa payments with loan accounts
    """
    
    @staticmethod
    def reconcile_unallocated_payments() -> Dict[str, int]:
        """
        Reconcile unallocated payments
        Attempts to match payments without loan references
        
        Returns:
            Dict with reconciliation statistics
        """
        try:
            # Get unallocated payments
            unallocated = Payment.objects.filter(
                status='UNALLOCATED',
                loan__isnull=True
            )
            
            reconciled_count = 0
            mpesa_service = MPesaService()
            
            for payment in unallocated:
                # Try to match by phone number
                if payment.payer_phone:
                    phone = payment.payer_phone
                    if not phone.startswith('+'):
                        phone = f'+{phone}'
                    
                    customer = Customer.objects.filter(phone_number=phone).first()
                    
                    if customer:
                        # Get customer's active loan
                        loan = Loan.objects.filter(
                            customer=customer,
                            status='ACTIVE'
                        ).order_by('-disbursement_date').first()
                        
                        if loan:
                            payment.loan = loan
                            payment.status = 'PENDING_ALLOCATION'
                            payment.save()
                            
                            # Allocate payment
                            mpesa_service._allocate_payment(loan, payment)
                            reconciled_count += 1
                            
                            logger.info(
                                f"Payment reconciled: {payment.payment_reference} -> "
                                f"Loan {loan.loan_number}"
                            )
            
            return {
                'total_unallocated': unallocated.count(),
                'reconciled': reconciled_count,
                'remaining': unallocated.count() - reconciled_count
            }
            
        except Exception as e:
            logger.error(f"Payment reconciliation failed: {str(e)}")
            return {'total_unallocated': 0, 'reconciled': 0, 'remaining': 0, 'error': str(e)}
    
    @staticmethod
    def generate_reconciliation_report(start_date: date, end_date: date) -> Dict[str, Any]:
        """
        Generate payment reconciliation report
        
        Args:
            start_date: Report start date
            end_date: Report end date
            
        Returns:
            Dict with reconciliation statistics
        """
        try:
            payments = Payment.objects.filter(
                payment_date__range=[start_date, end_date]
            )
            
            total_payments = payments.count()
            total_amount = sum(p.amount for p in payments)
            
            allocated = payments.filter(status='CLEARED', loan__isnull=False).count()
            unallocated = payments.filter(status='UNALLOCATED').count()
            
            mpesa_payments = payments.filter(payment_method='MPESA').count()
            bank_payments = payments.filter(payment_method='BANK_TRANSFER').count()
            cash_payments = payments.filter(payment_method='CASH').count()
            
            return {
                'period': {
                    'start_date': start_date,
                    'end_date': end_date
                },
                'summary': {
                    'total_payments': total_payments,
                    'total_amount': total_amount,
                    'allocated_count': allocated,
                    'unallocated_count': unallocated,
                    'allocation_rate': (allocated / total_payments * 100) if total_payments > 0 else 0
                },
                'by_method': {
                    'mpesa': mpesa_payments,
                    'bank': bank_payments,
                    'cash': cash_payments
                }
            }
            
        except Exception as e:
            logger.error(f"Reconciliation report generation failed: {str(e)}")
            return {}


# Global M-Pesa service instance
mpesa_service = MPesaService()
