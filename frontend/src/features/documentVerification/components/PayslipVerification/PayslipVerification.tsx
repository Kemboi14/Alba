import React, { useState, useCallback, useMemo } from 'react';
import { DocumentUploadCard } from '../DocumentUploadCard';
import { VerificationBadge } from '../VerificationBadge';
import { verifyPayslip, calculateAverageIncome, validateMinimumIncome, estimateLoanEligibility } from '../../utils/payslipVerifier';
import { useVerificationStore } from '../../store/verificationStore';
import { AlertCircle, CheckCircle, Building2, DollarSign, Calendar, TrendingUp, Edit2, Calculator } from 'lucide-react';
import { cn } from '../DocumentUploadCard';

export interface PayslipVerificationProps {
  onComplete?: () => void;
  onValidationChange?: (isValid: boolean) => void;
}

export const PayslipVerification: React.FC<PayslipVerificationProps> = ({
  onComplete: _onComplete,
  onValidationChange,
}) => {
  const {
    payslips,
    extractedClientData,
    addPayslip,
    removePayslip,
    setPayslipVerification,
    setPayslipExtractedData,
    updateClientData,
  } = useVerificationStore();

  const [verifyingIndex, setVerifyingIndex] = useState<number | null>(null);
  const [manualEdit, setManualEdit] = useState(false);
  const [editedData, setEditedData] = useState({
    monthlyIncome: extractedClientData.monthlyIncome || 0,
    employer: extractedClientData.employer || '',
  });

  const MAX_PAYSLIPS = 3;

  // Calculate summary statistics
  const summary = useMemo(() => {
    const verifiedPayslips = payslips.files.filter(p => p.verification?.isValid);
    const results = verifiedPayslips.map(p => p.verification).filter(Boolean) as NonNullable<typeof payslips.files[0]['verification']>[];
    
    return calculateAverageIncome(results);
  }, [payslips.files]);

  const incomeValidation = useMemo(() => {
    return validateMinimumIncome(summary.averageMonthly, 15000);
  }, [summary.averageMonthly]);

  const loanEstimate = useMemo(() => {
    return estimateLoanEligibility(summary.averageMonthly);
  }, [summary.averageMonthly]);

  // Check if complete
  const isComplete = payslips.files.length > 0 && payslips.files.every(p => p.status === 'verified');

  React.useEffect(() => {
    onValidationChange?.(isComplete);
  }, [isComplete, onValidationChange]);

  const handleUpload = useCallback(async (files: File[]) => {
    if (payslips.files.length + files.length > MAX_PAYSLIPS) {
      return; // Would exceed max
    }

    for (const file of files) {
      // Create preview for images
      let preview: string | undefined;
      if (file.type.startsWith('image/')) {
        preview = await new Promise<string>((resolve) => {
          const reader = new FileReader();
          reader.onload = () => resolve(reader.result as string);
          reader.readAsDataURL(file);
        });
      }

      const index = payslips.files.length;
      
      addPayslip({
        file,
        preview,
        verification: null,
        status: 'pending',
      });

      setVerifyingIndex(index);

      try {
        const result = await verifyPayslip(file);

        setPayslipVerification(index, result);

        // Update summary if this is the first successful verification
        if (result.isValid && result.extractedData) {
          const newData = {
            monthlyIncome: result.extractedData.monthlyIncome || summary.averageMonthly,
            employer: result.extractedData.employer || summary.employer,
          };
          
          if (!payslips.extractedData) {
            setPayslipExtractedData(newData);
            setEditedData(newData);
            updateClientData(newData);
          }
        }
      } catch (error) {
        console.error('Payslip verification error:', error);
      } finally {
        setVerifyingIndex(null);
      }
    }
  }, [payslips.files.length, payslips.extractedData, summary.averageMonthly, summary.employer, addPayslip, setPayslipVerification, setPayslipExtractedData, updateClientData]);

  const handleRemove = useCallback((index: number) => {
    removePayslip(index);
  }, [removePayslip]);

  const handleSaveManualEdit = useCallback(() => {
    const data = {
      monthlyIncome: editedData.monthlyIncome,
      employer: editedData.employer,
    };
    setPayslipExtractedData(data);
    updateClientData(data);
    setManualEdit(false);
  }, [editedData, setPayslipExtractedData, updateClientData]);

  const getOverallStatus = () => {
    if (verifyingIndex !== null) return 'verifying';
    if (isComplete) return 'verified';
    if (payslips.files.some(p => p.status === 'error')) return 'warning';
    if (payslips.files.length > 0) return 'pending';
    return 'pending';
  };

  const getStatusMessage = () => {
    if (verifyingIndex !== null) return 'Analyzing payslip...';
    if (isComplete) return 'Income verified';
    if (payslips.files.length === 0) return 'Upload at least 1 payslip';
    if (payslips.files.some(p => p.status === 'error')) return 'Some verifications failed';
    return 'Verifying...';
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-xl font-bold text-gray-900">Income Verification</h2>
          <p className="text-sm text-gray-500">
            Upload your payslips to verify income (max {MAX_PAYSLIPS} files)
          </p>
        </div>
        <VerificationBadge
          status={getOverallStatus()}
          message={getStatusMessage()}
        />
      </div>

      {/* Upload Section */}
      <DocumentUploadCard
        title="Payslip Documents"
        description="Upload recent payslips (PDF or images). Last 3 months preferred."
        accept="image/*,.pdf"
        maxFiles={MAX_PAYSLIPS}
        onUpload={handleUpload}
        uploadedFiles={payslips.files.map((f, i) => ({
          file: f.file,
          preview: f.preview,
          status: i === verifyingIndex ? 'verifying' : f.status,
          verification: f.verification || undefined,
        }))}
        onRemove={handleRemove}
        disabled={verifyingIndex !== null}
      />

      {/* Income Summary */}
      {summary.averageMonthly > 0 && (
        <div className="bg-white border rounded-lg p-6">
          <div className="flex items-center justify-between mb-4">
            <h3 className="text-lg font-semibold text-gray-900">
              Income Summary
            </h3>
            <button
              onClick={() => setManualEdit(!manualEdit)}
              className="flex items-center gap-1 text-sm text-blue-600 hover:text-blue-700"
            >
              <Edit2 className="w-4 h-4" />
              {manualEdit ? 'Cancel' : 'Edit'}
            </button>
          </div>

          {manualEdit ? (
            <div className="space-y-4">
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">
                    Monthly Income (KSh)
                  </label>
                  <input
                    type="number"
                    value={editedData.monthlyIncome}
                    onChange={(e) => setEditedData(prev => ({ ...prev, monthlyIncome: Number(e.target.value) }))}
                    className="w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                    placeholder="Enter monthly income"
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">
                    Employer Name
                  </label>
                  <input
                    type="text"
                    value={editedData.employer}
                    onChange={(e) => setEditedData(prev => ({ ...prev, employer: e.target.value }))}
                    className="w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                    placeholder="Enter employer name"
                  />
                </div>
              </div>
              <button
                onClick={handleSaveManualEdit}
                className="w-full py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700"
              >
                Save Changes
              </button>
            </div>
          ) : (
            <div className="space-y-4">
              {/* Key Stats */}
              <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                <div className="p-4 bg-blue-50 rounded-lg">
                  <div className="flex items-center gap-2 text-blue-600 mb-1">
                    <DollarSign className="w-4 h-4" />
                    <span className="text-xs font-medium">Monthly Income</span>
                  </div>
                  <p className="text-xl font-bold text-blue-900">
                    KSh {summary.averageMonthly.toLocaleString()}
                  </p>
                  <p className="text-xs text-blue-600 mt-1">
                    from {payslips.files.filter(p => p.verification?.isValid).length} payslip(s)
                  </p>
                </div>

                <div className="p-4 bg-gray-50 rounded-lg">
                  <div className="flex items-center gap-2 text-gray-600 mb-1">
                    <Building2 className="w-4 h-4" />
                    <span className="text-xs font-medium">Employer</span>
                  </div>
                  <p className="text-lg font-semibold text-gray-900 truncate">
                    {summary.employer || 'Not detected'}
                  </p>
                </div>

                <div className="p-4 bg-gray-50 rounded-lg">
                  <div className="flex items-center gap-2 text-gray-600 mb-1">
                    <Calendar className="w-4 h-4" />
                    <span className="text-xs font-medium">Avg Gross Pay</span>
                  </div>
                  <p className="text-lg font-semibold text-gray-900">
                    KSh {summary.averageGross.toLocaleString()}
                  </p>
                </div>

                <div className="p-4 bg-gray-50 rounded-lg">
                  <div className="flex items-center gap-2 text-gray-600 mb-1">
                    <Calculator className="w-4 h-4" />
                    <span className="text-xs font-medium">Avg Net Pay</span>
                  </div>
                  <p className="text-lg font-semibold text-gray-900">
                    KSh {summary.averageNet.toLocaleString()}
                  </p>
                </div>
              </div>

              {/* Income Validation */}
              <div className={cn(
                'p-4 rounded-lg border',
                incomeValidation.meetsRequirement
                  ? 'bg-green-50 border-green-200'
                  : 'bg-amber-50 border-amber-200'
              )}>
                <div className="flex items-start gap-3">
                  {incomeValidation.meetsRequirement ? (
                    <CheckCircle className="w-5 h-5 text-green-600 mt-0.5" />
                  ) : (
                    <AlertCircle className="w-5 h-5 text-amber-600 mt-0.5" />
                  )}
                  <div>
                    <p className={cn(
                      'font-medium',
                      incomeValidation.meetsRequirement ? 'text-green-800' : 'text-amber-800'
                    )}>
                      {incomeValidation.message}
                    </p>
                    {!incomeValidation.meetsRequirement && (
                      <p className="text-sm text-amber-700 mt-1">
                        Consider uploading additional income documents or contact support.
                      </p>
                    )}
                  </div>
                </div>
              </div>

              {/* Loan Estimate */}
              <div className="p-4 bg-purple-50 rounded-lg border border-purple-200">
                <div className="flex items-center gap-2 text-purple-600 mb-3">
                  <TrendingUp className="w-5 h-5" />
                  <span className="font-medium">Estimated Loan Eligibility</span>
                </div>
                <div className="grid grid-cols-3 gap-4 text-center">
                  <div>
                    <p className="text-2xl font-bold text-purple-900">
                      KSh {loanEstimate.maxLoanAmount.toLocaleString()}
                    </p>
                    <p className="text-xs text-purple-600">Maximum Loan</p>
                  </div>
                  <div>
                    <p className="text-2xl font-bold text-purple-900">
                      KSh {loanEstimate.recommendedLoanAmount.toLocaleString()}
                    </p>
                    <p className="text-xs text-purple-600">Recommended</p>
                  </div>
                  <div>
                    <p className="text-2xl font-bold text-purple-900">
                      KSh {loanEstimate.maxMonthlyPayment.toLocaleString()}
                    </p>
                    <p className="text-xs text-purple-600">Max Monthly Payment</p>
                  </div>
                </div>
                <p className="text-xs text-purple-600 mt-3 text-center">
                  Based on {summary.averageMonthly > 0 ? `verified income of KSh ${summary.averageMonthly.toLocaleString()}` : 'provided income'} per month
                </p>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
};

export default PayslipVerification;
