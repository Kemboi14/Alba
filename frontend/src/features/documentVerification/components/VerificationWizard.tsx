import React, { useState, useCallback } from 'react';
import { IDVerification } from './IDVerification/IDVerification';
import { PayslipVerification } from './PayslipVerification/PayslipVerification';
import { FaceVerification } from './FaceVerification/FaceVerification';
import { VerificationSummary } from './VerificationSummary';
import { useVerificationStore, VerificationOutput } from '../store/verificationStore';
import { ChevronRight, ChevronLeft, CheckCircle, Shield, FileText, User, Camera, Send } from 'lucide-react';
import { cn } from './DocumentUploadCard';

export interface VerificationWizardProps {
  onComplete?: (output: VerificationOutput) => void;
  onCancel?: () => void;
  initialStep?: number;
}

const steps = [
  {
    id: 'id',
    title: 'ID Verification',
    description: 'Upload your National ID',
    icon: FileText,
  },
  {
    id: 'payslip',
    title: 'Income Verification',
    description: 'Upload payslips',
    icon: User,
  },
  {
    id: 'face',
    title: 'Face Verification',
    description: 'Take a selfie',
    icon: Camera,
  },
  {
    id: 'review',
    title: 'Review & Submit',
    description: 'Confirm details',
    icon: CheckCircle,
  },
];

export const VerificationWizard: React.FC<VerificationWizardProps> = ({
  onComplete,
  onCancel,
  initialStep = 0,
}) => {
  const { currentStep, setCurrentStep, getVerificationOutput, canProceedToStep } = useVerificationStore();
  const [isStepValid, setIsStepValid] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);

  // Use external step control if provided
  const activeStep = initialStep !== 0 ? initialStep : currentStep;

  const handleStepValidation = useCallback((isValid: boolean) => {
    setIsStepValid(isValid);
  }, []);

  const handleNext = useCallback(() => {
    if (activeStep < steps.length - 1) {
      setCurrentStep(activeStep + 1);
      setIsStepValid(false);
    }
  }, [activeStep, setCurrentStep]);

  const handleBack = useCallback(() => {
    if (activeStep > 0) {
      setCurrentStep(activeStep - 1);
      setIsStepValid(false);
    }
  }, [activeStep, setCurrentStep]);

  const handleSubmit = useCallback(async () => {
    setIsSubmitting(true);
    
    try {
      const output = getVerificationOutput();
      onComplete?.(output);
    } catch (error) {
      console.error('Verification submission error:', error);
    } finally {
      setIsSubmitting(false);
    }
  }, [getVerificationOutput, onComplete]);

  const renderStepContent = () => {
    switch (activeStep) {
      case 0:
        return (
          <IDVerification
            onValidationChange={handleStepValidation}
          />
        );
      case 1:
        return (
          <PayslipVerification
            onValidationChange={handleStepValidation}
          />
        );
      case 2:
        return (
          <FaceVerification
            onValidationChange={handleStepValidation}
          />
        );
      case 3:
        return (
          <VerificationSummary
            onConfirm={handleSubmit}
            isSubmitting={isSubmitting}
            onValidationChange={handleStepValidation}
          />
        );
      default:
        return null;
    }
  };

  const CurrentIcon = steps[activeStep].icon;

  return (
    <div className="w-full max-w-4xl mx-auto bg-white rounded-xl shadow-lg overflow-hidden">
      {/* Header */}
      <div className="bg-gradient-to-r from-blue-600 to-blue-700 px-6 py-4">
        <div className="flex items-center gap-3">
          <Shield className="w-8 h-8 text-white" />
          <div>
            <h1 className="text-xl font-bold text-white">Document Verification</h1>
            <p className="text-blue-100 text-sm">
              Verify your identity and income securely
            </p>
          </div>
        </div>
      </div>

      {/* Stepper */}
      <div className="px-6 py-4 border-b bg-gray-50">
        <div className="flex items-center justify-between">
          {steps.map((step, index) => {
            const StepIcon = step.icon;
            const isActive = index === activeStep;
            const isCompleted = index < activeStep;
            const isClickable = index <= activeStep || canProceedToStep(index);

            return (
              <React.Fragment key={step.id}>
                <button
                  onClick={() => isClickable && setCurrentStep(index)}
                  disabled={!isClickable}
                  className={cn(
                    'flex flex-col items-center gap-2 transition-colors',
                    isClickable ? 'cursor-pointer' : 'cursor-default'
                  )}
                >
                  <div
                    className={cn(
                      'w-10 h-10 rounded-full flex items-center justify-center transition-colors',
                      isActive && 'bg-blue-600 text-white ring-4 ring-blue-100',
                      isCompleted && 'bg-green-500 text-white',
                      !isActive && !isCompleted && isClickable && 'bg-white text-gray-600 border-2 border-gray-300',
                      !isClickable && 'bg-gray-200 text-gray-400'
                    )}
                  >
                    {isCompleted ? (
                      <CheckCircle className="w-5 h-5" />
                    ) : (
                      <StepIcon className="w-5 h-5" />
                    )}
                  </div>
                  <div className="text-center hidden sm:block">
                    <p
                      className={cn(
                        'text-xs font-medium',
                        isActive && 'text-blue-600',
                        isCompleted && 'text-green-600',
                        !isActive && !isCompleted && 'text-gray-500'
                      )}
                    >
                      {step.title}
                    </p>
                  </div>
                </button>

                {index < steps.length - 1 && (
                  <div
                    className={cn(
                      'flex-1 h-0.5 mx-2 sm:mx-4',
                      isCompleted ? 'bg-green-500' : 'bg-gray-300'
                    )}
                  />
                )}
              </React.Fragment>
            );
          })}
        </div>
      </div>

      {/* Content */}
      <div className="p-6 min-h-[500px]">
        {/* Step Title */}
        <div className="flex items-center gap-3 mb-6">
          <div className="p-2 bg-blue-100 rounded-lg">
            <CurrentIcon className="w-6 h-6 text-blue-600" />
          </div>
          <div>
            <h2 className="text-lg font-semibold text-gray-900">
              {steps[activeStep].title}
            </h2>
            <p className="text-sm text-gray-500">
              {steps[activeStep].description}
            </p>
          </div>
        </div>

        {/* Step Component */}
        <div className="animate-in fade-in slide-in-from-bottom-4 duration-300">
          {renderStepContent()}
        </div>
      </div>

      {/* Footer */}
      <div className="px-6 py-4 border-t bg-gray-50 flex items-center justify-between">
        <button
          onClick={onCancel}
          className="text-gray-600 hover:text-gray-800 font-medium"
        >
          Cancel
        </button>

        <div className="flex items-center gap-3">
          {activeStep > 0 && activeStep < steps.length - 1 && (
            <button
              onClick={handleBack}
              className="flex items-center gap-2 px-4 py-2 text-gray-700 hover:bg-gray-200 rounded-lg transition-colors"
            >
              <ChevronLeft className="w-4 h-4" />
              Back
            </button>
          )}

          {activeStep < steps.length - 1 ? (
            <button
              onClick={handleNext}
              disabled={!isStepValid}
              className={cn(
                'flex items-center gap-2 px-6 py-2 rounded-lg font-medium transition-colors',
                isStepValid
                  ? 'bg-blue-600 text-white hover:bg-blue-700'
                  : 'bg-gray-300 text-gray-500 cursor-not-allowed'
              )}
            >
              Next
              <ChevronRight className="w-4 h-4" />
            </button>
          ) : (
            <button
              onClick={handleSubmit}
              disabled={isSubmitting || !isStepValid}
              className={cn(
                'flex items-center gap-2 px-6 py-2 rounded-lg font-medium transition-colors',
                isSubmitting || !isStepValid
                  ? 'bg-gray-400 cursor-not-allowed'
                  : 'bg-green-600 text-white hover:bg-green-700'
              )}
            >
              {isSubmitting ? (
                <>
                  <div className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin" />
                  Submitting...
                </>
              ) : (
                <>
                  <Send className="w-4 h-4" />
                  Submit Verification
                </>
              )}
            </button>
          )}
        </div>
      </div>
    </div>
  );
};

export default VerificationWizard;
