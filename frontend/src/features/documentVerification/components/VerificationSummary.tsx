import React from 'react';
import { useVerificationStore } from '../store/verificationStore';
import { VerificationBadge } from './VerificationBadge';
import { 
  User, 
  Building2, 
  CreditCard, 
  Calendar, 
  Camera, 
  FileText, 
  AlertCircle,
  CheckCircle,
  TrendingUp,
  Shield
} from 'lucide-react';
import { cn } from './DocumentUploadCard';

export interface VerificationSummaryProps {
  onConfirm: () => void;
  isSubmitting: boolean;
  onValidationChange?: (isValid: boolean) => void;
}

export const VerificationSummary: React.FC<VerificationSummaryProps> = ({
  onConfirm,
  isSubmitting,
  onValidationChange,
}) => {
  const { 
    idCard, 
    payslips, 
    faceImage, 
    extractedClientData,
    getVerificationOutput 
  } = useVerificationStore();

  const output = getVerificationOutput();
  const { verification, summary } = output;

  // Report validation status to parent
  React.useEffect(() => {
    onValidationChange?.(summary.canSubmit);
  }, [summary.canSubmit, onValidationChange]);

  const formatCurrency = (amount: number) => {
    return `KSh ${amount.toLocaleString()}`;
  };

  return (
    <div className="space-y-6">
      {/* Overall Status */}
      <div className={cn(
        'p-4 rounded-lg border flex items-start gap-3',
        summary.canSubmit 
          ? 'bg-green-50 border-green-200' 
          : 'bg-amber-50 border-amber-200'
      )}>
        {summary.canSubmit ? (
          <CheckCircle className="w-6 h-6 text-green-600 mt-0.5" />
        ) : (
          <AlertCircle className="w-6 h-6 text-amber-600 mt-0.5" />
        )}
        <div>
          <h3 className={cn(
            'font-semibold',
            summary.canSubmit ? 'text-green-800' : 'text-amber-800'
          )}>
            {summary.canSubmit 
              ? 'Ready to Submit' 
              : 'Additional Information Required'}
          </h3>
          <p className={cn(
            'text-sm mt-1',
            summary.canSubmit ? 'text-green-700' : 'text-amber-700'
          )}>
            {summary.canSubmit
              ? `All documents verified with ${summary.confidenceScore}% confidence. You can now submit your application.`
              : 'Some documents need attention before submission. Please review the sections below.'}
          </p>
        </div>
      </div>

      {/* Verification Summary Cards */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        {/* ID Card Status */}
        <div className={cn(
          'p-4 rounded-lg border',
          verification.idCard.verified 
            ? 'bg-green-50 border-green-200' 
            : 'bg-red-50 border-red-200'
        )}>
          <div className="flex items-center gap-2 mb-3">
            <FileText className={cn(
              'w-5 h-5',
              verification.idCard.verified ? 'text-green-600' : 'text-red-600'
            )} />
            <h4 className="font-semibold text-gray-900">ID Card</h4>
          </div>
          <VerificationBadge 
            status={verification.idCard.verified ? 'verified' : 'error'}
            confidence={verification.idCard.confidence}
            size="sm"
          />
          {verification.idCard.warnings.length > 0 && (
            <p className="text-xs text-amber-600 mt-2">
              {verification.idCard.warnings[0]}
            </p>
          )}
        </div>

        {/* Payslips Status */}
        <div className={cn(
          'p-4 rounded-lg border',
          verification.payslips.verified 
            ? 'bg-green-50 border-green-200' 
            : 'bg-red-50 border-red-200'
        )}>
          <div className="flex items-center gap-2 mb-3">
            <CreditCard className={cn(
              'w-5 h-5',
              verification.payslips.verified ? 'text-green-600' : 'text-red-600'
            )} />
            <h4 className="font-semibold text-gray-900">Payslips</h4>
          </div>
          <VerificationBadge 
            status={verification.payslips.verified ? 'verified' : 'error'}
            confidence={verification.payslips.confidence}
            size="sm"
          />
          <p className="text-xs text-gray-600 mt-2">
            {verification.payslips.count} document{verification.payslips.count !== 1 ? 's' : ''} uploaded
          </p>
        </div>

        {/* Face Verification Status */}
        <div className={cn(
          'p-4 rounded-lg border',
          verification.faceImage.verified 
            ? 'bg-green-50 border-green-200' 
            : 'bg-red-50 border-red-200'
        )}>
          <div className="flex items-center gap-2 mb-3">
            <Camera className={cn(
              'w-5 h-5',
              verification.faceImage.verified ? 'text-green-600' : 'text-red-600'
            )} />
            <h4 className="font-semibold text-gray-900">Face Verification</h4>
          </div>
          <VerificationBadge 
            status={verification.faceImage.verified ? 'verified' : 'error'}
            size="sm"
          />
          <p className="text-xs text-gray-600 mt-2 capitalize">
            Quality: {verification.faceImage.quality || 'N/A'}
          </p>
        </div>
      </div>

      {/* Extracted Data Summary */}
      <div className="bg-white border rounded-lg overflow-hidden">
        <div className="px-4 py-3 bg-gray-50 border-b">
          <h3 className="font-semibold text-gray-900 flex items-center gap-2">
            <Shield className="w-5 h-5 text-blue-600" />
            Extracted Client Information
          </h3>
        </div>
        
        <div className="p-4 grid grid-cols-1 md:grid-cols-2 gap-4">
          {/* Personal Info */}
          <div className="space-y-3">
            <h4 className="text-sm font-medium text-gray-500 uppercase tracking-wide">
              Personal Details
            </h4>
            
            <div className="flex items-center gap-3 p-3 bg-gray-50 rounded-lg">
              <User className="w-5 h-5 text-gray-400" />
              <div>
                <p className="text-xs text-gray-500">Full Name</p>
                <p className="font-medium text-gray-900">
                  {extractedClientData.fullName || 'Not extracted'}
                </p>
              </div>
            </div>

            <div className="flex items-center gap-3 p-3 bg-gray-50 rounded-lg">
              <CreditCard className="w-5 h-5 text-gray-400" />
              <div>
                <p className="text-xs text-gray-500">ID Number</p>
                <p className="font-medium text-gray-900">
                  {extractedClientData.idNumber || 'Not extracted'}
                </p>
              </div>
            </div>

            <div className="flex items-center gap-3 p-3 bg-gray-50 rounded-lg">
              <Calendar className="w-5 h-5 text-gray-400" />
              <div>
                <p className="text-xs text-gray-500">Date of Birth</p>
                <p className="font-medium text-gray-900">
                  {extractedClientData.dateOfBirth || 'Not extracted'}
                </p>
              </div>
            </div>
          </div>

          {/* Income Info */}
          <div className="space-y-3">
            <h4 className="text-sm font-medium text-gray-500 uppercase tracking-wide">
              Income Details
            </h4>
            
            <div className="flex items-center gap-3 p-3 bg-blue-50 rounded-lg">
              <TrendingUp className="w-5 h-5 text-blue-500" />
              <div>
                <p className="text-xs text-blue-600">Monthly Income</p>
                <p className="font-semibold text-blue-900 text-lg">
                  {formatCurrency(extractedClientData.monthlyIncome)}
                </p>
              </div>
            </div>

            <div className="flex items-center gap-3 p-3 bg-gray-50 rounded-lg">
              <Building2 className="w-5 h-5 text-gray-400" />
              <div>
                <p className="text-xs text-gray-500">Employer</p>
                <p className="font-medium text-gray-900">
                  {extractedClientData.employer || 'Not extracted'}
                </p>
              </div>
            </div>

            <div className="flex items-center gap-3 p-3 bg-gray-50 rounded-lg">
              <User className="w-5 h-5 text-gray-400" />
              <div>
                <p className="text-xs text-gray-500">Gender</p>
                <p className="font-medium text-gray-900">
                  {extractedClientData.gender || 'Not detected'}
                </p>
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Documents Preview */}
      <div className="bg-white border rounded-lg overflow-hidden">
        <div className="px-4 py-3 bg-gray-50 border-b">
          <h3 className="font-semibold text-gray-900">Uploaded Documents</h3>
        </div>
        
        <div className="p-4">
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            {/* ID Front */}
            {idCard.front?.preview && (
              <div className="space-y-2">
                <p className="text-xs text-gray-500">ID Front</p>
                <div className="relative aspect-[3/2] rounded-lg overflow-hidden border">
                  <img 
                    src={idCard.front.preview} 
                    alt="ID Front" 
                    className="w-full h-full object-cover"
                  />
                  {idCard.front.verification?.isValid && (
                    <div className="absolute top-1 right-1">
                      <CheckCircle className="w-5 h-5 text-green-500 bg-white rounded-full" />
                    </div>
                  )}
                </div>
              </div>
            )}

            {/* ID Back */}
            {idCard.back?.preview && (
              <div className="space-y-2">
                <p className="text-xs text-gray-500">ID Back</p>
                <div className="relative aspect-[3/2] rounded-lg overflow-hidden border">
                  <img 
                    src={idCard.back.preview} 
                    alt="ID Back" 
                    className="w-full h-full object-cover"
                  />
                  {idCard.back.verification?.isValid && (
                    <div className="absolute top-1 right-1">
                      <CheckCircle className="w-5 h-5 text-green-500 bg-white rounded-full" />
                    </div>
                  )}
                </div>
              </div>
            )}

            {/* Payslips */}
            {payslips.files.map((file, index) => (
              file.preview && (
                <div key={index} className="space-y-2">
                  <p className="text-xs text-gray-500">Payslip {index + 1}</p>
                  <div className="relative aspect-[3/2] rounded-lg overflow-hidden border">
                    <img 
                      src={file.preview} 
                      alt={`Payslip ${index + 1}`} 
                      className="w-full h-full object-cover"
                    />
                    {file.verification?.isValid && (
                      <div className="absolute top-1 right-1">
                        <CheckCircle className="w-5 h-5 text-green-500 bg-white rounded-full" />
                      </div>
                    )}
                  </div>
                </div>
              )
            ))}

            {/* Face Image */}
            {faceImage.image?.preview && (
              <div className="space-y-2">
                <p className="text-xs text-gray-500">Face Photo</p>
                <div className="relative aspect-[3/2] rounded-lg overflow-hidden border">
                  <img 
                    src={faceImage.image.preview} 
                    alt="Face" 
                    className="w-full h-full object-cover"
                  />
                  {faceImage.faceDetected && (
                    <div className="absolute top-1 right-1">
                      <CheckCircle className="w-5 h-5 text-green-500 bg-white rounded-full" />
                    </div>
                  )}
                </div>
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Confidence Score */}
      <div className="bg-gradient-to-r from-blue-50 to-indigo-50 rounded-lg p-4 border border-blue-200">
        <div className="flex items-center justify-between">
          <div>
            <p className="text-sm font-medium text-blue-900">Overall Confidence Score</p>
            <p className="text-xs text-blue-700 mt-1">
              Based on document quality and data extraction accuracy
            </p>
          </div>
          <div className="text-right">
            <p className="text-3xl font-bold text-blue-600">{summary.confidenceScore}%</p>
            <p className="text-xs text-blue-500">
              {summary.verifiedDocuments}/{summary.totalDocuments} documents verified
            </p>
          </div>
        </div>
        
        {/* Progress Bar */}
        <div className="mt-3 h-2 bg-blue-200 rounded-full overflow-hidden">
          <div 
            className="h-full bg-blue-600 transition-all duration-500"
            style={{ width: `${summary.confidenceScore}%` }}
          />
        </div>
      </div>

      {/* Submit Button Area */}
      <div className="flex items-center justify-between pt-4 border-t">
        <div className="text-sm text-gray-500">
          {summary.needsReview ? (
            <span className="flex items-center gap-1 text-amber-600">
              <AlertCircle className="w-4 h-4" />
              Some items need review
            </span>
          ) : (
            <span className="flex items-center gap-1 text-green-600">
              <CheckCircle className="w-4 h-4" />
              All checks passed
            </span>
          )}
        </div>

        <button
          onClick={onConfirm}
          disabled={isSubmitting || !summary.canSubmit}
          className={cn(
            'px-8 py-3 rounded-lg font-semibold transition-colors flex items-center gap-2',
            !summary.canSubmit
              ? 'bg-gray-300 text-gray-500 cursor-not-allowed'
              : isSubmitting
                ? 'bg-blue-400 text-white cursor-wait'
                : 'bg-blue-600 text-white hover:bg-blue-700'
          )}
        >
          {isSubmitting ? (
            <>
              <div className="w-5 h-5 border-2 border-white border-t-transparent rounded-full animate-spin" />
              Processing...
            </>
          ) : (
            <>
              Submit for Approval
              <CheckCircle className="w-5 h-5" />
            </>
          )}
        </button>
      </div>
    </div>
  );
};

export default VerificationSummary;
