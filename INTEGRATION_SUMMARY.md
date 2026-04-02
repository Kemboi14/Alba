# Complete Integration Summary

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         CLIENT BROWSER                                    │
│  ┌─────────────────────────────────────────────────────────────────┐     │
│  │  URL: https://yourdomain.com/client/profile/                   │     │
│  │                                                                 │     │
│  │  ┌─────────────────────────────────────────────────────────┐   │     │
│  │  │  Django Template (client_profile_verification.html)     │   │     │
│  │  │                                                         │   │     │
│  │  │  ┌─────────────────────────────────────────────────┐   │   │     │
│  │  │  │  Django Form Fields (Traditional)               │   │   │     │
│  │  │  │  - id_full_name                                 │   │   │     │
│  │  │  │  - id_id_number                                 │   │   │     │
│  │  │  │  - id_date_of_birth                             │   │   │     │
│  │  │  │  - id_gender                                    │   │   │     │
│  │  │  │  - id_employer                                  │   │   │     │
│  │  │  │  - id_monthly_income                            │   │   │     │
│  │  │  └─────────────────────────────────────────────────┘   │   │     │
│  │  │                                                         │   │     │
│  │  │  ┌─────────────────────────────────────────────────┐   │   │     │
│  │  │  │  <div id="verification-root">                 │   │   │     │
│  │  │  │                                                 │   │   │     │
│  │  │  │  REACT VERIFICATION WIZARD MOUNTS HERE        │   │   │     │
│  │  │  │                                                 │   │   │     │
│  │  │  │  • ID Verification (OCR)                      │   │   │     │
│  │  │  │  • Payslip Verification (PDF/Image + OCR)       │   │   │     │
│  │  │  │  • Face Verification (Camera + Detection)      │   │   │     │
│  │  │  │  • Review & Submit                            │   │   │     │
│  │  │  │                                                 │   │   │     │
│  │  │  └─────────────────────────────────────────────────┘   │   │     │
│  │  │                                                         │   │     │
│  │  │  ┌─────────────────────────────────────────────────┐   │   │     │
│  │  │  │  Submit Button (Django Form Submit)           │   │   │     │
│  │  │  └─────────────────────────────────────────────────┘   │   │     │
│  │  │                                                         │   │     │
│  │  └─────────────────────────────────────────────────────────┘   │     │
│  │                                                                 │     │
│  └─────────────────────────────────────────────────────────────────┘     │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    │ HTTPS (Port 443)
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                         NGINX (Reverse Proxy)                           │
│  • Serves static files (/static/verification/*)                         │
│  • Proxies to Gunicorn for dynamic content                              │
│  • SSL/TLS termination                                                  │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    │
                    ┌───────────────┴───────────────┐
                    │                               │
                    ▼                               ▼
        ┌───────────────────┐           ┌───────────────────┐
        │  STATIC FILES     │           │   GUNICORN        │
        │  (React Build)    │           │   (Django App)    │
        │                   │           │                   │
        │  /static/         │           │  /client/profile/ │
        │    verification/  │           │                   │
        │      js/          │           │  API Endpoints:   │
        │      css/         │           │  • /api/client/   │
        │      assets/      │           │    /documents/    │
        └───────────────────┘           │    /upload/         │
                                        │  • /api/client/   │
                                        │    /profile/      │
                                        │    /update/       │
                                        │  • /api/client/   │
                                        │    /verification- │
                                        │    status/        │
                                        └─────────┬─────────┘
                                                  │
                                                  │
                    ┌───────────────────────────────┼───────────────────┐
                    │                               │                   │
                    ▼                               ▼                   ▼
        ┌───────────────────┐           ┌───────────────────┐   ┌──────────────┐
        │  MEDIA STORAGE  │           │   DATABASE        │   │    ODOO    │
        │  (File Uploads) │           │   (PostgreSQL)    │   │   SERVER   │
        │                   │           │                   │   │            │
        │  media/clients/ │           │  • Client model │   │  • Partner │
        │    {id}/         │           │  • Documents      │   │  • Documents│
        │      documents/  │           │  • Verification   │   │            │
        │        id_front  │           │    results        │   │            │
        │        id_back   │           │                   │   │            │
        │        payslips/ │           │                   │   │            │
        │        selfie    │           │                   │   │            │
        └───────────────────┘           └───────────────────┘   └────────────┘
```

## Data Flow Sequence

### 1. Page Load
```
1. Client visits /client/profile/
2. Django renders template with:
   - CSRF token in meta tag
   - VERIFICATION_CONTEXT JavaScript object
   - All form fields
   - <div id="verification-root">
3. Browser loads React bundle from /static/verification/
4. React mounts into verification-root div
```

### 2. Document Upload & Verification
```
1. User uploads ID front image
2. React uses Tesseract.js (browser-side OCR)
3. ID number, name, DOB extracted locally
4. Result displayed in UI with confidence score
5. User uploads ID back (same process)
6. User uploads payslips (PDF or images)
7. React uses PDF.js or Tesseract.js for extraction
8. Income, employer data extracted
9. User takes selfie with camera
10. React uses face-api.js for detection
11. Face quality assessed
```

### 3. Form Auto-Fill
```
1. User clicks "Submit" in React wizard
2. React auto-fills Django form fields:
   - id_id_number ← extracted ID
   - id_full_name ← extracted name
   - id_date_of_birth ← extracted DOB
   - id_gender ← extracted gender
   - id_employer ← extracted employer
   - id_monthly_income ← extracted income
3. React dispatches 'verificationComplete' event
4. Django form now has all data filled
```

### 4. Django Form Submission
```
1. User reviews auto-filled data
2. User clicks Django "Save Profile" button
3. Browser submits traditional form POST
4. Django view receives:
   - Form data (auto-filled)
   - CSRF token
   - Any manually corrected fields
5. Django validates and saves to database
6. Django syncs with Odoo via your integration
```

### 5. File Upload (Async)
```
1. When React wizard submits:
   - Files uploaded via AJAX to /api/client/documents/upload/
   - Multipart/form-data with CSRF token
   - Files saved to media/clients/{id}/documents/
2. Django returns file URLs
3. React continues with profile update
```

### 6. Profile Update (Async)
```
1. React sends extracted data via AJAX
   POST /api/client/profile/update/
   {
     "extracted_data": {
       "personalInfo": {...},
       "employmentInfo": {...}
     },
     "verification_results": {...}
   }
2. Django updates Client model:
   - id_number
   - date_of_birth
   - gender
   - employer
   - monthly_income
   - verification_status = "verified"
   - verification_results (JSON)
3. Django returns success response
```

### 7. Odoo Sync
```
1. Django calls existing Odoo integration
2. POST /api/odoo/client/sync/
   {
     "client_data": {
       "name": "...",
       "id_number": "...",
       ...
     },
     "documents": {...}
   }
3. Odoo integration creates/updates partner
4. Documents attached to Odoo partner
5. Returns Odoo partner ID
```

## File Locations Reference

### Django/Backend Files
| File | Purpose |
|------|---------|
| `loan_system/templates/client_profile_verification.html` | Django template with embedded React |
| `loan_system/views/verification_views.py` | API endpoints for upload/update |
| `loan_system/models.py` | Client model fields |
| `loan_system/urls.py` | URL routing |
| `loan_system/settings.py` | Static/media config |

### Frontend/Build Files
| File | Purpose |
|------|---------|
| `frontend/src/main.tsx` | React entry point |
| `frontend/vite.config.ts` | Build config for Django static |
| `frontend/src/features/documentVerification/` | All verification components |
| `frontend/package.json` | Dependencies |

### Generated Static Files (After Build)
| File | Purpose |
|------|---------|
| `loan_system/static/verification/js/main-*.js` | React app bundle |
| `loan_system/static/verification/css/main-*.css` | Styles |
| `loan_system/static/verification/manifest.json` | Asset manifest |

### Uploaded Media Files (Runtime)
| File | Purpose |
|------|---------|
| `media/clients/{id}/documents/id_front_*.jpg` | ID front |
| `media/clients/{id}/documents/id_back_*.jpg` | ID back |
| `media/clients/{id}/documents/payslips/*.pdf` | Payslips |
| `media/clients/{id}/documents/selfie_*.jpg` | Selfie |

## API Endpoints Summary

### GET /client/profile/
- **Purpose:** Render profile page with React
- **Returns:** HTML with embedded verification wizard

### POST /api/client/documents/upload/
- **Purpose:** Upload document files
- **Request:** Multipart form data
- **Files:** id_front, id_back, payslip_0, payslip_1, payslip_2, selfie
- **Returns:** `{ "files": { "id_front": "/media/...", ... } }`

### POST /api/client/profile/update/
- **Purpose:** Save extracted data
- **Request:** JSON
- **Body:** `{ "extracted_data": {...}, "verification_results": {...} }`
- **Returns:** `{ "status": "success", "client_id": 123 }`

### GET /api/client/verification-status/
- **Purpose:** Get current verification status
- **Returns:** `{ "status": "verified", "id_front_url": "...", ... }`

## Environment Variables

### Development (.env)
```
DEBUG=True
DJANGO_SETTINGS_MODULE=loan_system.settings
SECRET_KEY=dev-secret-key
```

### Production (.env.production)
```
DEBUG=False
DJANGO_SETTINGS_MODULE=loan_system.settings_production
SECRET_KEY=production-secret-key
ALLOWED_HOSTS=yourdomain.com,www.yourdomain.com
DB_PASSWORD=secure-db-password
ODOO_API_KEY=your-odoo-api-key
ODOO_WEBHOOK_SECRET=your-webhook-secret
```

## Testing Commands

```bash
# Run integration tests
cd /home/nick/ACCT.f
python loan_system/tests/test_verification_integration.py

# Test specific URL
python -c "
import requests
response = requests.get('http://localhost:8000/client/profile/')
print(f'Status: {response.status_code}')
print(f'Has React root: {\"verification-root\" in response.text}')
"

# Check static files
python manage.py findstatic verification/js/main.js
```

## Troubleshooting Common Issues

### Issue: React not loading
**Check:**
1. `npm run build` completed successfully
2. `python manage.py collectstatic` run
3. Static files exist in `loan_system/static/verification/`
4. Nginx serving static files correctly

### Issue: CORS errors
**Check:**
1. `CORS_ALLOWED_ORIGINS` includes your domain
2. `CORS_ALLOW_CREDENTIALS = True`
3. CSRF token in request headers

### Issue: Files not uploading
**Check:**
1. `MEDIA_ROOT` and `MEDIA_URL` configured
2. Directory permissions (www-data:www-data)
3. `client_max_body_size` in Nginx (50M)
4. `DATA_UPLOAD_MAX_MEMORY_SIZE` in Django (50M)

### Issue: Form not auto-filling
**Check:**
1. Form field IDs match in template and React
2. `autoFillDjangoForm()` function in main.tsx
3. `change` event dispatched after setting value

## Performance Optimizations

1. **Static Files:**
   - Nginx serves with `expires 1y` cache headers
   - Gzip compression enabled
   - ManifestStaticFilesStorage for hashed filenames

2. **File Uploads:**
   - Client-side image compression before upload
   - Max 2MB per image, 5MB per PDF
   - Async uploads don't block UI

3. **OCR Processing:**
   - Browser-side using Tesseract.js
   - No server CPU load
   - Web Workers for non-blocking processing

## Security Considerations

1. **CSRF Protection:**
   - All state-changing endpoints require CSRF token
   - Token passed in header from Django template

2. **File Uploads:**
   - File type validation (image/*, application/pdf)
   - File size limits enforced
   - Stored outside web root (media/)

3. **Data Privacy:**
   - ID numbers encrypted at rest
   - HTTPS only in production
   - Secure session cookies

4. **Access Control:**
   - All endpoints require authentication
   - Users can only access own documents
   - Staff can access all (if needed)

## Complete File Tree

```
/home/nick/ACCT.f/
├── frontend/
│   ├── package.json
│   ├── vite.config.ts
│   ├── src/
│   │   ├── main.tsx                    ← Entry point
│   │   ├── index.css                   ← Tailwind styles
│   │   └── features/
│   │       └── documentVerification/
│   │           ├── index.ts            ← Exports
│   │           ├── store/
│   │           │   └── verificationStore.ts
│   │           ├── components/
│   │           │   ├── VerificationWizard.tsx
│   │           │   ├── VerificationSummary.tsx
│   │           │   ├── VerificationBadge.tsx
│   │           │   ├── DocumentUploadCard.tsx
│   │           │   ├── IDVerification/
│   │           │   │   └── IDVerification.tsx
│   │           │   ├── PayslipVerification/
│   │           │   │   └── PayslipVerification.tsx
│   │           │   └── FaceVerification/
│   │           │       └── FaceVerification.tsx
│   │           └── utils/
│   │               ├── idVerifier.ts
│   │               ├── payslipVerifier.ts
│   │               └── faceDetector.ts
│   └── node_modules/                   ← After npm install
│
├── loan_system/
│   ├── templates/
│   │   └── client_profile_verification.html
│   ├── views/
│   │   └── verification_views.py
│   ├── models.py                       ← Client model
│   ├── urls.py                         ← URL routing
│   └── static/
│       └── verification/               ← After npm run build
│           ├── js/main-*.js
│           ├── css/main-*.css
│           └── manifest.json
│
├── media/
│   └── clients/                        ← Uploaded files
│       └── {client_id}/
│           └── documents/
│
├── DEPLOYMENT_PRODUCTION.md
├── DJANGO_INTEGRATION_GUIDE.md
├── INTEGRATION_CHECKLIST.md
└── INTEGRATION_SUMMARY.md              ← This file
```

---

**Status:** ✅ All components integrated and documented
**Last Updated:** April 1, 2026
