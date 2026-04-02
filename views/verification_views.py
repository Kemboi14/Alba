"""
Views for document verification integration with Django
"""
from django.shortcuts import render, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_http_methods
from django.http import JsonResponse
from django.views import View
from django.utils.decorators import method_decorator
import json


@login_required
def client_profile_verification(request):
    """
    Render the client profile page with embedded document verification
    
    This view serves the React verification feature embedded in Django
    on the same port 8000 - no separate frontend server needed.
    """
    context = {
        'client': request.user.client if hasattr(request.user, 'client') else None,
        'debug': request.GET.get('debug', False),  # Enable debug mode for Vite HMR
    }
    return render(request, 'client_profile_verification.html', context)


@method_decorator(login_required, name='dispatch')
class DocumentUploadView(View):
    """
    Handle document uploads from the verification wizard
    """
    def post(self, request):
        from django.core.files.storage import default_storage
        from django.core.files.base import ContentFile
        
        client = request.user.client if hasattr(request.user, 'client') else None
        if not client:
            return JsonResponse({'error': 'Client not found'}, status=400)
        
        uploaded_files = {}
        
        # Handle ID front
        if 'id_front' in request.FILES:
            file = request.FILES['id_front']
            path = default_storage.save(
                f'clients/{client.id}/documents/id_front_{file.name}',
                ContentFile(file.read())
            )
            client.id_front_url = default_storage.url(path)
            uploaded_files['id_front'] = client.id_front_url
        
        # Handle ID back
        if 'id_back' in request.FILES:
            file = request.FILES['id_back']
            path = default_storage.save(
                f'clients/{client.id}/documents/id_back_{file.name}',
                ContentFile(file.read())
            )
            client.id_back_url = default_storage.url(path)
            uploaded_files['id_back'] = client.id_back_url
        
        # Handle payslips
        payslip_urls = []
        for key in request.FILES:
            if key.startswith('payslip_'):
                file = request.FILES[key]
                path = default_storage.save(
                    f'clients/{client.id}/documents/payslips/{file.name}',
                    ContentFile(file.read())
                )
                payslip_urls.append(default_storage.url(path))
        
        if payslip_urls:
            client.payslip_urls = json.dumps(payslip_urls)
            uploaded_files['payslips'] = payslip_urls
        
        # Handle selfie
        if 'selfie' in request.FILES:
            file = request.FILES['selfie']
            path = default_storage.save(
                f'clients/{client.id}/documents/selfie_{file.name}',
                ContentFile(file.read())
            )
            client.selfie_url = default_storage.url(path)
            uploaded_files['selfie'] = client.selfie_url
        
        client.save()
        
        return JsonResponse({
            'status': 'success',
            'files': uploaded_files
        })


@method_decorator(login_required, name='dispatch')
class ProfileUpdateView(View):
    """
    Update client profile with extracted verification data
    """
    def post(self, request):
        client = request.user.client if hasattr(request.user, 'client') else None
        if not client:
            return JsonResponse({'error': 'Client not found'}, status=400)
        
        try:
            data = json.loads(request.body)
            extracted_data = data.get('extracted_data', {})
            
            # Update personal info from ID extraction
            personal = extracted_data.get('personalInfo', {})
            if personal.get('idNumber'):
                client.id_number = personal['idNumber']
            if personal.get('dateOfBirth'):
                client.date_of_birth = personal['dateOfBirth']
            if personal.get('gender'):
                client.gender = personal['gender']
            if personal.get('firstName') or personal.get('lastName'):
                client.full_name = f"{personal.get('firstName', '')} {personal.get('lastName', '')}".strip()
            
            # Update employment info from payslip extraction
            employment = extracted_data.get('employmentInfo', {})
            if employment.get('employer'):
                client.employer = employment['employer']
            if employment.get('monthlyIncome'):
                client.monthly_income = employment['monthlyIncome']
            
            # Store verification results
            client.verification_status = 'verified'
            client.verification_results = json.dumps(data.get('verification_results', {}))
            client.save()
            
            return JsonResponse({
                'status': 'success',
                'client_id': client.id
            })
            
        except json.JSONDecodeError:
            return JsonResponse({'error': 'Invalid JSON'}, status=400)


@login_required
@require_http_methods(["GET"])
def get_client_verification_status(request):
    """
    Get current verification status for the client
    """
    client = request.user.client if hasattr(request.user, 'client') else None
    if not client:
        return JsonResponse({'error': 'Client not found'}, status=400)
    
    return JsonResponse({
        'status': client.verification_status or 'pending',
        'id_front_url': client.id_front_url,
        'id_back_url': client.id_back_url,
        'payslip_urls': json.loads(client.payslip_urls or '[]'),
        'selfie_url': client.selfie_url,
        'id_number': client.id_number,
        'monthly_income': client.monthly_income,
        'employer': client.employer,
    })
