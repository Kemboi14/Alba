# Django Portal Integration Guide

This guide explains how to integrate the Document Verification feature with your Django client portal and existing Odoo integration.

## Architecture Flow

```
┌─────────────────────────────────────────────────────────────────┐
│                    CLIENT BROWSER                               │
│  ┌─────────────────┐    ┌─────────────────┐                    │
│  │ Profile Form    │───▶│ Doc Verification │                   │
│  │ (Django Rendered)│    │ (React Component) │                   │
│  └─────────────────┘    └────────┬────────┘                    │
│                                  │                              │
│                         OCR/Face Detection                      │
│                         (Browser-side)                          │
│                                  │                              │
└──────────────────────────────────┼──────────────────────────────┘
                                   │
                                   ▼
┌─────────────────────────────────────────────────────────────────┐
│                      DJANGO BACKEND                             │
│  ┌─────────────────┐    ┌─────────────────┐    ┌──────────────┐ │
│  │ Document API    │◀───│ Extracted Data  │───▶│ Profile Model│ │
│  │ /api/client/... │    │ Verification    │    │ (Client)     │ │
│  └────────┬────────┘    └─────────────────┘    └──────────────┘ │
│           │                                                      │
│           │    ┌─────────────────┐                              │
│           └───▶│ Odoo Integration│◀──────────────────────────────┤
│                │ Module (Existing)│                              │
│                └─────────────────┘                              │
└─────────────────────────────────────────────────────────────────┘
```

## Integration Steps

### 1. Django Backend Endpoints

Add these API endpoints to your Django `urls.py`:

```python
# urls.py
from django.urls import path
from . import views

urlpatterns = [
    # Document upload endpoint
    path('api/client/documents/upload/', views.DocumentUploadView.as_view(), name='document_upload'),
    
    # Profile update with extracted data
    path('api/client/profile/update/', views.ProfileUpdateView.as_view(), name='profile_update'),
    
    # Odoo sync endpoint
    path('api/odoo/client/sync/', views.OdooSyncView.as_view(), name='odoo_sync'),
]
```

### 2. Django Views

```python
# views.py
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.parsers import MultiPartParser, FormParser
from django.core.files.storage import default_storage
from django.core.files.base import ContentFile
import json

class DocumentUploadView(APIView):
    parser_classes = (MultiPartParser, FormParser)
    
    def post(self, request):
        """Handle document uploads from verification wizard"""
        client_id = request.session.get('client_id')
        
        uploaded_files = {}
        
        # Save ID documents
        if 'id_front' in request.FILES:
            path = default_storage.save(
                f'clients/{client_id}/id_front.jpg',
                ContentFile(request.FILES['id_front'].read())
            )
            uploaded_files['id_front_url'] = default_storage.url(path)
            
        if 'id_back' in request.FILES:
            path = default_storage.save(
                f'clients/{client_id}/id_back.jpg',
                ContentFile(request.FILES['id_back'].read())
            )
            uploaded_files['id_back_url'] = default_storage.url(path)
        
        # Save payslips
        payslip_urls = []
        for key in request.FILES:
            if key.startswith('payslip_'):
                path = default_storage.save(
                    f'clients/{client_id}/payslips/{key}.pdf',
                    ContentFile(request.FILES[key].read())
                )
                payslip_urls.append(default_storage.url(path))
        
        uploaded_files['payslip_urls'] = payslip_urls
        
        # Save selfie
        if 'selfie' in request.FILES:
            path = default_storage.save(
                f'clients/{client_id}/selfie.jpg',
                ContentFile(request.FILES['selfie'].read())
            )
            uploaded_files['selfie_url'] = default_storage.url(path)
        
        return Response({
            'status': 'success',
            'files': uploaded_files
        })


class ProfileUpdateView(APIView):
    def post(self, request):
        """Update client profile with extracted verification data"""
        client_id = request.data.get('client_id')
        extracted_data = request.data.get('extracted_data')
        
        # Get or create client
        client = Client.objects.get(id=client_id)
        
        # Update personal info from ID extraction
        client.id_number = extracted_data['personalInfo']['idNumber']
        client.date_of_birth = extracted_data['personalInfo']['dateOfBirth']
        client.gender = extracted_data['personalInfo']['gender']
        
        # Update employment info from payslip extraction
        client.employer = extracted_data['employmentInfo']['employer']
        client.monthly_income = extracted_data['employmentInfo']['monthlyIncome']
        
        # Save verification metadata
        client.verification_results = json.dumps(request.data.get('verification_results'))
        client.verification_status = 'verified'
        client.save()
        
        return Response({
            'status': 'success',
            'client_id': client.id,
            'verification_status': 'verified'
        })


class OdooSyncView(APIView):
    def post(self, request):
        """Sync verified client data with Odoo via existing integration"""
        from .odoo_integration import OdooIntegration
        
        client_data = request.data.get('client_data')
        documents = request.data.get('documents')
        
        # Use your existing Odoo integration
        odoo = OdooIntegration()
        
        # Create or update partner in Odoo
        partner_id = odoo.create_or_update_partner({
            'name': client_data['name'],
            'id_number': client_data['id_number'],
            'date_of_birth': client_data['date_of_birth'],
            'gender': client_data['gender'],
            'email': client_data['email'],
            'phone': client_data['phone'],
            'monthly_income': client_data['monthly_income'],
            'employer': client_data['employer'],
        })
        
        # Attach documents to Odoo partner
        odoo.attach_documents(partner_id, documents)
        
        return Response({
            'status': 'success',
            'odoo_partner_id': partner_id
        })
```

### 3. Django Template Integration

In your Django client profile template:

```html
<!-- client_profile.html -->
{% extends 'base.html' %}
{% load static %}

{% block content %}
<div id="profile-root"></div>

<script>
  // Pass Django context to React
  window.DJANGO_CONTEXT = {
    clientId: '{{ client.id }}',
    csrfToken: '{{ csrf_token }}',
    apiBaseUrl: '/api',
    existingDocuments: {
      idFront: '{{ client.id_front_url|default:"" }}',
      idBack: '{{ client.id_back_url|default:"" }}',
      payslips: {{ client.payslip_urls|safe|default:"[]" }},
      selfie: '{{ client.selfie_url|default:"" }}'
    }
  };
</script>

<!-- Load your React bundle -->
<script src="{% static 'js/profile-bundle.js' %}"></script>
{% endblock %}
```

### 4. React Entry Point

```tsx
// profile-entry.tsx
import React from 'react';
import ReactDOM from 'react-dom/client';
import { ClientProfileWithVerification } from './components/ClientProfileWithVerification';
import { VerificationWizard } from './features/documentVerification';

// Get Django context
const djangoContext = (window as any).DJANGO_CONTEXT;

const root = ReactDOM.createRoot(document.getElementById('profile-root')!);

root.render(
  <React.StrictMode>
    <ClientProfileWithVerification
      clientId={djangoContext?.clientId}
      existingDocuments={djangoContext?.existingDocuments}
      onProfileComplete={(data) => {
        console.log('Profile complete:', data);
        // Redirect to success page or next step
        window.location.href = '/client/loan-application/';
      }}
    />
  </React.StrictMode>
);
```

### 5. Minimal Integration (Just the Wizard)

If you just want to add the verification wizard to an existing form:

```html
<!-- In your Django template -->
<div id="document-verification"></div>

<script>
  // Render just the verification wizard
  const container = document.getElementById('document-verification');
  
  // When wizard completes, populate your form fields
  window.onVerificationComplete = (output) => {
    // Auto-fill Django form fields
    document.getElementById('id_id_number').value = output.clientData.idNumber;
    document.getElementById('id_full_name').value = output.clientData.fullName;
    document.getElementById('id_date_of_birth').value = output.clientData.dateOfBirth;
    document.getElementById('id_employer').value = output.clientData.employer;
    document.getElementById('id_monthly_income').value = output.clientData.monthlyIncome;
    
    // Store documents for form submission
    window.verifiedDocuments = output.clientData.documents;
  };
</script>
```

## Data Flow Summary

1. **Client uploads documents** → React verification wizard
2. **Browser-side OCR/Detection** → Extracts data using Tesseract.js/Face-API
3. **Verification complete** → User clicks "Submit"
4. **Files uploaded** → Django `/api/client/documents/upload/`
5. **Extracted data synced** → Django `/api/client/profile/update/`
6. **Odoo sync triggered** → Django `/api/odoo/client/sync/`
7. **Partner created/updated** → Odoo `res.partner` with documents attached

## Required Django Settings

```python
# settings.py

# Media files for document storage
MEDIA_URL = '/media/'
MEDIA_ROOT = os.path.join(BASE_DIR, 'media')

# REST Framework
INSTALLED_APPS += ['rest_framework']

REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'rest_framework.authentication.SessionAuthentication',
    ],
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.IsAuthenticated',
    ],
}

# CORS for frontend (if separate domain)
CORS_ALLOWED_ORIGINS = [
    "http://localhost:5173",  # Vite dev server
    "https://yourdomain.com",
]
```

## Testing the Integration

1. **Start Django**: `python manage.py runserver`
2. **Start React dev server**: `cd frontend && npm run dev`
3. **Navigate to profile page**: `http://localhost:8000/client/profile/`
4. **Upload test documents**:
   - Kenyan ID (front/back)
   - 2-3 payslips
   - Take selfie
5. **Verify data auto-populates** Django form fields
6. **Check Odoo** - new partner should be created with documents

## Troubleshooting

### CORS Errors
Add to `settings.py`:
```python
CORS_ALLOW_CREDENTIALS = True
CORS_ALLOW_HEADERS = [
    'content-type',
    'x-csrftoken',
    'authorization',
]
```

### CSRF Token Issues
Ensure the CSRF token is passed in headers:
```javascript
headers: {
  'X-CSRFToken': getCSRFToken(),
}
```

### Large File Uploads
Increase Django's max upload size:
```python
# settings.py
DATA_UPLOAD_MAX_MEMORY_SIZE = 5242880  # 5MB
FILE_UPLOAD_MAX_MEMORY_SIZE = 5242880  # 5MB
```
