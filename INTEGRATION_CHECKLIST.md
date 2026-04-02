# Integration Checklist

Verify all components are correctly integrated before deploying.

## Backend Integration ✅

### Django Settings
- [ ] `REST_FRAMEWORK` added to `INSTALLED_APPS`
- [ ] `CORS_ALLOWED_ORIGINS` configured for production domain
- [ ] `STATICFILES_DIRS` includes `loan_system/static`
- [ ] `MEDIA_URL` and `MEDIA_ROOT` configured
- [ ] `DATA_UPLOAD_MAX_MEMORY_SIZE` set to at least 50MB
- [ ] `FILE_UPLOAD_MAX_MEMORY_SIZE` set to at least 50MB

### URL Configuration
- [ ] `/client/profile/` → `client_profile_verification` view
- [ ] `/api/client/documents/upload/` → `DocumentUploadView`
- [ ] `/api/client/profile/update/` → `ProfileUpdateView`
- [ ] `/api/client/verification-status/` → `get_client_verification_status`

### Views
- [ ] `client_profile_verification` renders template with context
- [ ] `DocumentUploadView` handles multipart file uploads
- [ ] `ProfileUpdateView` processes JSON with extracted data
- [ ] CSRF token properly handled in all API endpoints

### Models
- [ ] `Client.id_number` field exists
- [ ] `Client.id_front_url` field exists
- [ ] `Client.id_back_url` field exists
- [ ] `Client.payslip_urls` field exists (JSON/text)
- [ ] `Client.selfie_url` field exists
- [ ] `Client.verification_status` field exists
- [ ] `Client.verification_results` field exists (JSON)
- [ ] `Client.monthly_income` field exists
- [ ] `Client.employer` field exists

### Templates
- [ ] `client_profile_verification.html` exists
- [ ] Template includes `verification-root` div
- [ ] Template passes `VERIFICATION_CONTEXT` to JavaScript
- [ ] Template includes CSRF token meta tag
- [ ] Template loads static files correctly

## Frontend Integration ✅

### Build Configuration
- [ ] `vite.config.ts` builds to `loan_system/static/verification/`
- [ ] `npm run build` completes without errors
- [ ] Static files generated in correct location:
  - `loan_system/static/verification/js/main-*.js`
  - `loan_system/static/verification/css/main-*.css`
  - `loan_system/static/verification/manifest.json`

### Dependencies
- [ ] `tesseract.js` installed
- [ ] `face-api.js` installed
- [ ] `pdfjs-dist` installed
- [ ] `react-dropzone` installed
- [ ] `react-webcam` installed
- [ ] `zustand` installed
- [ ] All dependencies in `package.json`

### Components
- [ ] `VerificationWizard` exports correctly
- [ ] `IDVerification` component works
- [ ] `PayslipVerification` component works
- [ ] `FaceVerification` component works
- [ ] `DocumentUploadCard` component works
- [ ] `VerificationBadge` component works

### Main Entry Point
- [ ] `main.tsx` exists and exports
- [ ] `main.tsx` reads `window.VERIFICATION_CONTEXT`
- [ ] `main.tsx` auto-fills Django form fields
- [ ] `main.tsx` dispatches `verificationComplete` event

## Static Files Integration ✅

### Development Mode
- [ ] Template checks `{% if debug %}` condition
- [ ] Development loads from `http://localhost:5173`
- [ ] Vite dev server starts without errors

### Production Mode
- [ ] `collectstatic` finds verification files
- [ ] Static files served from `/static/verification/`
- [ ] No 404 errors for JS/CSS files in browser console
- [ ] Manifest file generated and used

## API Integration ✅

### File Upload
- [ ] ID front upload works
- [ ] ID back upload works
- [ ] Multiple payslips upload works (max 3)
- [ ] Selfie upload works
- [ ] Files saved to correct location: `media/clients/{id}/documents/`

### Data Sync
- [ ] Extracted ID data populates Django form
- [ ] Extracted payslip data populates Django form
- [ ] Verification results saved to database
- [ ] CSRF protection working (no 403 errors)

## Django-Odoo Integration ✅

### Data Flow
- [ ] Django receives extracted data from React
- [ ] Django saves documents and data
- [ ] Django syncs with Odoo via existing integration
- [ ] Odoo partner created/updated with correct data
- [ ] Documents attached to Odoo partner

### Required Data Fields
- [ ] `name` → Odoo partner name
- [ ] `id_number` → Odoo partner ID number
- [ ] `date_of_birth` → Odoo partner DOB
- [ ] `gender` → Odoo partner gender
- [ ] `email` → Odoo partner email
- [ ] `phone` → Odoo partner phone
- [ ] `monthly_income` → Odoo partner income
- [ ] `employer` → Odoo partner employer

## Testing ✅

### Manual Testing Steps
1. [ ] Navigate to `/client/profile/`
2. [ ] Upload ID front image
3. [ ] Verify OCR extracts ID number
4. [ ] Upload ID back image
5. [ ] Upload 2-3 payslips
6. [ ] Verify income extraction
7. [ ] Take selfie with camera
8. [ ] Verify face detection works
9. [ ] Click "Submit" button
10. [ ] Verify Django form auto-filled
11. [ ] Submit Django form
12. [ ] Verify data saved in admin
13. [ ] Verify Odoo partner created

### Browser Console Checks
- [ ] No JavaScript errors
- [ ] No CORS errors
- [ ] No 404 errors for assets
- [ ] Console shows "Verification complete" event

### Network Tab Checks
- [ ] `/api/client/documents/upload/` returns 200
- [ ] `/api/client/profile/update/` returns 200
- [ ] Files uploaded with correct multipart format
- [ ] JSON data sent with correct Content-Type

## Production Readiness ✅

### Security
- [ ] `DEBUG = False` in production
- [ ] `SECRET_KEY` set and secure
- [ ] `ALLOWED_HOSTS` configured
- [ ] HTTPS enabled
- [ ] CSRF_COOKIE_SECURE = True
- [ ] SESSION_COOKIE_SECURE = True

### Performance
- [ ] Static files gzipped by Nginx
- [ ] Static files have cache headers
- [ ] Media files served efficiently
- [ ] Database queries optimized

### Monitoring
- [ ] Health check endpoint configured
- [ ] Error logging configured
- [ ] File upload size limits set
- [ ] Rate limiting on API endpoints

## Sign-off

- [ ] All backend tests pass
- [ ] All frontend tests pass
- [ ] Integration tests pass
- [ ] Manual testing complete
- [ ] Production deployment successful
- [ ] Client can upload and verify documents
- [ ] Data correctly syncs to Odoo

---

**Integration Status:** ⬜ In Progress / ⬜ Testing / ⬜ Complete

**Last Verified By:** _______________

**Date:** _______________
