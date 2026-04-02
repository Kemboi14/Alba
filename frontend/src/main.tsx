import React from 'react';
import ReactDOM from 'react-dom/client';
import { VerificationWizard } from './features/documentVerification';
import './index.css';  // Tailwind styles

/**
 * Main entry point for document verification embedded in Django
 * 
 * This mounts the verification wizard into a div with id="verification-root"
 * that should be present in the Django template.
 */

// Get context passed from Django template
const context = (window as any).VERIFICATION_CONTEXT || {
  clientId: null,
  csrfToken: '',
  apiBaseUrl: '/api',
};

// Find the root element (injected by Django template)
const rootElement = document.getElementById('verification-root');

if (rootElement) {
  ReactDOM.createRoot(rootElement).render(
    <React.StrictMode>
      <VerificationWizard
        onComplete={(output) => {
          // Auto-fill Django form fields with extracted data
          autoFillDjangoForm(output);
          
          // Dispatch custom event that Django can listen to
          window.dispatchEvent(new CustomEvent('verificationComplete', { 
            detail: output 
          }));
        }}
        onCancel={() => {
          window.dispatchEvent(new CustomEvent('verificationCancelled'));
        }}
      />
    </React.StrictMode>
  );
} else {
  console.error('Verification root element not found');
}

/**
 * Auto-fill Django form fields with extracted verification data
 */
function autoFillDjangoForm(output: any) {
  const { clientData } = output;
  
  // Map extracted data to Django form field IDs
  const fieldMappings: Record<string, string> = {
    'id_id_number': clientData.idNumber,
    'id_full_name': clientData.fullName,
    'id_date_of_birth': clientData.dateOfBirth,
    'id_gender': clientData.gender?.toLowerCase(),
    'id_employer': clientData.employer,
    'id_monthly_income': clientData.monthlyIncome?.toString(),
  };
  
  // Fill each field if it exists
  Object.entries(fieldMappings).forEach(([fieldId, value]) => {
    const field = document.getElementById(fieldId) as HTMLInputElement | null;
    if (field && value) {
      field.value = value;
      // Trigger change event for any Django JS handlers
      field.dispatchEvent(new Event('change', { bubbles: true }));
    }
  });
  
  // Store documents for form submission
  (window as any).VERIFIED_DOCUMENTS = clientData.documents;
  
  // Show success message
  showVerificationSuccess();
}

/**
 * Show success message after verification
 */
function showVerificationSuccess() {
  const successDiv = document.createElement('div');
  successDiv.className = 'verification-success-banner';
  successDiv.innerHTML = `
    <div style="
      background: #dcfce7;
      border: 1px solid #86efac;
      color: #166534;
      padding: 12px 16px;
      border-radius: 8px;
      margin-bottom: 16px;
      display: flex;
      align-items: center;
      gap: 8px;
    ">
      <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
        <path d="M20 6L9 17l-5-5"/>
      </svg>
      <span>Documents verified successfully! Form fields auto-filled.</span>
    </div>
  `;
  
  // Insert at top of form
  const form = document.querySelector('form') || document.getElementById('verification-root');
  if (form && form.parentNode) {
    form.parentNode.insertBefore(successDiv, form);
  }
}
