// Main exports for the Document Verification feature
export { VerificationWizard } from './components/VerificationWizard';
export { IDVerification } from './components/IDVerification/IDVerification';
export { PayslipVerification } from './components/PayslipVerification/PayslipVerification';
export { FaceVerification } from './components/FaceVerification/FaceVerification';
export { VerificationBadge } from './components/VerificationBadge';
export { DocumentUploadCard } from './components/DocumentUploadCard';
export { VerificationSummary } from './components/VerificationSummary';

// Store
export { 
  useVerificationStore, 
  type VerificationOutput,
  type VerificationResult,
  type DocumentFile,
  type IDCardState,
  type PayslipState,
  type FaceState,
  type ExtractedClientData,
} from './store/verificationStore';

// Utilities
export { verifyKenyanID, validateIDNumber, calculateAge, isEligibleAge, fileToBase64 } from './utils/idVerifier';
export { verifyPayslip, calculateAverageIncome, validateMinimumIncome, estimateLoanEligibility } from './utils/payslipVerifier';
export { 
  detectFace, 
  detectFaceFromVideo, 
  loadFaceDetectionModels,
  compareFaces,
  getFaceGuidance,
  checkCameraSupport,
  drawFaceOverlay,
  type FaceDetectionResult,
} from './utils/faceDetector';
