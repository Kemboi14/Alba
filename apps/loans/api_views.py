"""
M-Pesa API Callback Views
Handles M-Pesa payment callbacks and webhooks
"""
from django.http import JsonResponse, HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.utils import timezone
import json
import logging

from apps.loans.mpesa_integration import mpesa_service
from apps.loans.models import Payment

logger = logging.getLogger(__name__)


@csrf_exempt
@require_http_methods(["POST"])
def mpesa_c2b_confirmation(request):
    """
    M-Pesa C2B payment confirmation callback
    Called by Safaricom when customer makes payment via Paybill
    """
    try:
        # Parse callback data
        callback_data = json.loads(request.body.decode('utf-8'))
        
        logger.info(f"M-Pesa C2B confirmation received: {callback_data}")
        
        # Process payment
        success = mpesa_service.process_c2b_payment(callback_data)
        
        if success:
            return JsonResponse({
                'ResultCode': 0,
                'ResultDesc': 'Accepted'
            })
        else:
            return JsonResponse({
                'ResultCode': 1,
                'ResultDesc': 'Processing failed'
            })
    
    except Exception as e:
        logger.error(f"M-Pesa C2B confirmation error: {str(e)}")
        return JsonResponse({
            'ResultCode': 1,
            'ResultDesc': 'Error processing payment'
        }, status=500)


@csrf_exempt
@require_http_methods(["POST"])
def mpesa_c2b_validation(request):
    """
    M-Pesa C2B payment validation callback
    Called before payment is completed - can accept or reject
    """
    try:
        callback_data = json.loads(request.body.decode('utf-8'))
        
        # Validate payment (e.g., check if paybill is correct)
        business_short_code = callback_data.get('BusinessShortCode')
        trans_amount = float(callback_data.get('TransAmount', 0))
        
        # Basic validation
        if trans_amount < 1:
            return JsonResponse({
                'ResultCode': 1,
                'ResultDesc': 'Invalid amount'
            })
        
        # Accept payment
        return JsonResponse({
            'ResultCode': 0,
            'ResultDesc': 'Accepted'
        })
    
    except Exception as e:
        logger.error(f"M-Pesa C2B validation error: {str(e)}")
        return JsonResponse({
            'ResultCode': 1,
            'ResultDesc': 'Validation failed'
        }, status=500)


@csrf_exempt
@require_http_methods(["POST"])
def mpesa_b2c_result(request):
    """
    M-Pesa B2C payment result callback
    Called after disbursement is completed or fails
    """
    try:
        callback_data = json.loads(request.body.decode('utf-8'))
        
        logger.info(f"M-Pesa B2C result received: {callback_data}")
        
        # Extract result parameters
        result = callback_data.get('Result', {})
        result_code = result.get('ResultCode')
        conversation_id = result.get('ConversationID')
        
        # Update loan disbursement status based on result
        # TODO: Implement proper status update logic
        
        return JsonResponse({
            'ResultCode': 0,
            'ResultDesc': 'Accepted'
        })
    
    except Exception as e:
        logger.error(f"M-Pesa B2C result error: {str(e)}")
        return JsonResponse({
            'ResultCode': 1,
            'ResultDesc': 'Error processing result'
        }, status=500)


@csrf_exempt
@require_http_methods(["POST"])
def mpesa_timeout(request):
    """
    M-Pesa timeout callback
    Called when M-Pesa request times out
    """
    try:
        callback_data = json.loads(request.body.decode('utf-8'))
        logger.warning(f"M-Pesa timeout: {callback_data}")
        
        return JsonResponse({
            'ResultCode': 0,
            'ResultDesc': 'Timeout acknowledged'
        })
    
    except Exception as e:
        logger.error(f"M-Pesa timeout error: {str(e)}")
        return JsonResponse({
            'ResultCode': 1,
            'ResultDesc': 'Error'
        }, status=500)


@csrf_exempt
@require_http_methods(["POST"])
def mpesa_status_result(request):
    """
    M-Pesa transaction status query result callback
    """
    try:
        callback_data = json.loads(request.body.decode('utf-8'))
        logger.info(f"M-Pesa status result: {callback_data}")
        
        return JsonResponse({
            'ResultCode': 0,
            'ResultDesc': 'Accepted'
        })
    
    except Exception as e:
        logger.error(f"M-Pesa status result error: {str(e)}")
        return JsonResponse({
            'ResultCode': 1,
            'ResultDesc': 'Error'
        }, status=500)
