import React, { useState } from 'react';
import { VerificationWizard, useVerificationStore, type VerificationOutput } from '../features/documentVerification';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Upload, FileCheck, AlertCircle } from 'lucide-react';

/**
 * ClientProfileWithVerification Component
 * 
 * This component integrates the document verification feature into the 
 * Django client profile creation flow. It should be used when clients
 * are filling out their profile and uploading documents.
 */

export interface ClientProfileWithVerificationProps {
  clientId?: string;
  onProfileComplete?: (data: ProfileData) => void;
  existingDocuments?: {
    idFront?: string;
    idBack?: string;
    payslips?: string[];
    selfie?: string;
  };
}

export interface ProfileData {
  // Personal Info (from Django form + extracted from ID)
  personalInfo: {
    firstName: string;
    lastName: string;
    email: string;
    phone: string;
    idNumber: string;
    dateOfBirth: string;
    gender: string;
  };
  
  // Employment Info (from Django form + extracted from payslips)
  employmentInfo: {
    employer: string;
    jobTitle: string;
    employmentType: 'permanent' | 'contract' | 'self-employed';
    monthlyIncome: number;
    employmentDate: string;
  };
  
  // Address Info (from Django form)
  addressInfo: {
    street: string;
    city: string;
    county: string;
    postalCode: string;
  };
  
  // Documents with verification data
  documents: VerificationOutput;
}

export const ClientProfileWithVerification: React.FC<ClientProfileWithVerificationProps> = ({
  clientId,
  onProfileComplete,
  existingDocuments,
}) => {
  const [showVerificationWizard, setShowVerificationWizard] = useState(false);
  const [verificationComplete, setVerificationComplete] = useState(false);
  const [uploadStatus, setUploadStatus] = useState<'idle' | 'uploading' | 'success' | 'error'>('idle');
  
  const { getVerificationOutput, resetVerification } = useVerificationStore();

  /**
   * Handle verification completion
   * This sends the verified data to Django/Odoo
   */
  const handleVerificationComplete = async (output: VerificationOutput) => {
    setUploadStatus('uploading');
    
    try {
      // 1. Upload document files to Django storage
      const uploadedDocs = await uploadDocumentsToDjango(output);
      
      // 2. Send extracted data to Django profile API
      const profileData = await syncWithDjangoProfile(output, uploadedDocs);
      
      // 3. Sync with Odoo via your existing integration
      await syncWithOdoo(profileData);
      
      setVerificationComplete(true);
      setUploadStatus('success');
      setShowVerificationWizard(false);
      
      // Notify parent component
      onProfileComplete?.(profileData);
      
    } catch (error) {
      console.error('Profile sync error:', error);
      setUploadStatus('error');
    }
  };

  /**
   * Upload document files to Django backend
   */
  const uploadDocumentsToDjango = async (output: VerificationOutput) => {
    const formData = new FormData();
    
    // Append ID documents
    if (output.clientData.documents.idFront?.file) {
      formData.append('id_front', output.clientData.documents.idFront.file);
    }
    if (output.clientData.documents.idBack?.file) {
      formData.append('id_back', output.clientData.documents.idBack.file);
    }
    
    // Append payslips
    output.clientData.documents.payslips.forEach((file, index) => {
      formData.append(`payslip_${index}`, file);
    });
    
    // Append selfie
    if (output.clientData.documents.selfie) {
      formData.append('selfie', output.clientData.documents.selfie);
    }

    const response = await fetch('/api/client/documents/upload/', {
      method: 'POST',
      body: formData,
      headers: {
        'X-CSRFToken': getCSRFToken(), // Django CSRF protection
      },
    });

    if (!response.ok) {
      throw new Error('Failed to upload documents');
    }

    return await response.json(); // Returns document URLs/paths
  };

  /**
   * Sync extracted data with Django client profile
   */
  const syncWithDjangoProfile = async (
    output: VerificationOutput, 
    uploadedDocs: any
  ): Promise<ProfileData> => {
    const profileData: ProfileData = {
      personalInfo: {
        firstName: extractFirstName(output.clientData.fullName),
        lastName: extractLastName(output.clientData.fullName),
        email: '', // From Django form
        phone: '', // From Django form
        idNumber: output.clientData.idNumber,
        dateOfBirth: output.clientData.dateOfBirth,
        gender: output.clientData.gender.toLowerCase(),
      },
      employmentInfo: {
        employer: output.clientData.employer,
        jobTitle: '', // From Django form
        employmentType: 'permanent', // From Django form
        monthlyIncome: output.clientData.monthlyIncome,
        employmentDate: '', // From Django form
      },
      addressInfo: {
        street: '', // From Django form
        city: '', // From Django form
        county: '', // From Django form
        postalCode: '', // From Django form
      },
      documents: output,
    };

    // Send to Django profile API
    const response = await fetch('/api/client/profile/update/', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-CSRFToken': getCSRFToken(),
      },
      body: JSON.stringify({
        client_id: clientId,
        extracted_data: profileData,
        document_urls: uploadedDocs,
        verification_results: output.verification,
      }),
    });

    if (!response.ok) {
      throw new Error('Failed to update profile');
    }

    return profileData;
  };

  /**
   * Sync with Odoo via existing integration
   */
  const syncWithOdoo = async (profileData: ProfileData) => {
    // This connects to your existing Odoo integration module
    const response = await fetch('/api/odoo/client/sync/', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-CSRFToken': getCSRFToken(),
      },
      body: JSON.stringify({
        client_data: {
          name: `${profileData.personalInfo.firstName} ${profileData.personalInfo.lastName}`,
          id_number: profileData.personalInfo.idNumber,
          date_of_birth: profileData.personalInfo.dateOfBirth,
          gender: profileData.personalInfo.gender,
          email: profileData.personalInfo.email,
          phone: profileData.personalInfo.phone,
          monthly_income: profileData.employmentInfo.monthlyIncome,
          employer: profileData.employmentInfo.employer,
        },
        documents: profileData.documents,
      }),
    });

    if (!response.ok) {
      throw new Error('Failed to sync with Odoo');
    }

    return await response.json();
  };

  /**
   * Get Django CSRF token from cookies
   */
  const getCSRFToken = (): string => {
    const name = 'csrftoken';
    const cookies = document.cookie.split(';');
    for (let cookie of cookies) {
      const [cookieName, cookieValue] = cookie.trim().split('=');
      if (cookieName === name) {
        return decodeURIComponent(cookieValue);
      }
    }
    return '';
  };

  /**
   * Helper to extract first name from full name
   */
  const extractFirstName = (fullName: string): string => {
    const parts = fullName.split(' ');
    return parts[0] || '';
  };

  /**
   * Helper to extract last name from full name
   */
  const extractLastName = (fullName: string): string => {
    const parts = fullName.split(' ');
    return parts.slice(1).join(' ') || '';
  };

  return (
    <div className="space-y-6">
      {/* Profile Form Section */}
      <div className="bg-white rounded-lg shadow p-6">
        <h2 className="text-xl font-bold mb-4">Personal Information</h2>
        {/* Your existing Django form fields would go here */}
        <p className="text-gray-500 text-sm">
          Fill in your personal details below. Document verification will auto-fill some fields.
        </p>
      </div>

      {/* Document Verification Section */}
      <div className="bg-white rounded-lg shadow p-6">
        <div className="flex items-center justify-between mb-4">
          <div>
            <h2 className="text-xl font-bold">Document Verification</h2>
            <p className="text-gray-500 text-sm">
              Upload your ID, payslips, and take a selfie for verification
            </p>
          </div>
          
          {verificationComplete ? (
            <div className="flex items-center gap-2 text-green-600">
              <FileCheck className="w-5 h-5" />
              <span className="font-medium">Verified</span>
            </div>
          ) : (
            <Button 
              onClick={() => setShowVerificationWizard(true)}
              className="flex items-center gap-2"
            >
              <Upload className="w-4 h-4" />
              Verify Documents
            </Button>
          )}
        </div>

        {/* Status Messages */}
        {uploadStatus === 'uploading' && (
          <div className="bg-blue-50 border border-blue-200 rounded-lg p-4 flex items-center gap-3">
            <div className="w-5 h-5 border-2 border-blue-600 border-t-transparent rounded-full animate-spin" />
            <p className="text-blue-700">Uploading and verifying documents...</p>
          </div>
        )}

        {uploadStatus === 'error' && (
          <div className="bg-red-50 border border-red-200 rounded-lg p-4 flex items-center gap-3">
            <AlertCircle className="w-5 h-5 text-red-600" />
            <div>
              <p className="text-red-700 font-medium">Upload failed</p>
              <p className="text-red-600 text-sm">
                Please try again or contact support if the issue persists.
              </p>
              <Button 
                variant="outline" 
                size="sm" 
                onClick={() => setShowVerificationWizard(true)}
                className="mt-2"
              >
                Retry Verification
              </Button>
            </div>
          </div>
        )}

        {verificationComplete && (
          <div className="bg-green-50 border border-green-200 rounded-lg p-4">
            <p className="text-green-700">
              Documents verified and synced with your profile successfully!
            </p>
          </div>
        )}
      </div>

      {/* Verification Wizard Modal */}
      <Dialog open={showVerificationWizard} onOpenChange={setShowVerificationWizard}>
        <DialogContent className="max-w-4xl max-h-[90vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>Document Verification</DialogTitle>
          </DialogHeader>
          <VerificationWizard
            onComplete={handleVerificationComplete}
            onCancel={() => {
              setShowVerificationWizard(false);
              resetVerification();
            }}
          />
        </DialogContent>
      </Dialog>
    </div>
  );
};

export default ClientProfileWithVerification;
