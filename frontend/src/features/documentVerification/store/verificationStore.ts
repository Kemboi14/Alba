import { create } from 'zustand';
import { devtools, persist } from 'zustand/middleware';

export interface VerificationResult {
  isValid: boolean;
  confidence: number;
  extractedData: Record<string, any>;
  errors: string[];
  warnings: string[];
}

export interface DocumentFile {
  file: File;
  preview: string;
  verification: VerificationResult | null;
  status: 'pending' | 'verifying' | 'verified' | 'error';
}

export interface IDCardState {
  front: DocumentFile | null;
  back: DocumentFile | null;
  extractedData: {
    idNumber?: string;
    fullName?: string;
    dateOfBirth?: string;
    gender?: string;
  } | null;
}

export interface PayslipState {
  files: DocumentFile[];
  extractedData: {
    monthlyIncome?: number;
    employer?: string;
    grossPay?: number;
    netPay?: number;
    payPeriods?: string[];
  } | null;
}

export interface FaceState {
  image: DocumentFile | null;
  faceDetected: boolean;
  quality: 'good' | 'poor' | 'multiple' | null;
}

export interface ExtractedClientData {
  fullName: string;
  idNumber: string;
  dateOfBirth: string;
  monthlyIncome: number;
  employer: string;
  gender: string;
}

interface VerificationState {
  // Document states
  idCard: IDCardState;
  payslips: PayslipState;
  faceImage: FaceState;
  
  // Overall status
  currentStep: number;
  overallStatus: 'incomplete' | 'verifying' | 'ready' | 'error';
  extractedClientData: ExtractedClientData;
  
  // Actions
  setIDFront: (file: DocumentFile | null) => void;
  setIDBack: (file: DocumentFile | null) => void;
  setIDVerification: (side: 'front' | 'back', result: VerificationResult) => void;
  setIDExtractedData: (data: IDCardState['extractedData']) => void;
  
  addPayslip: (file: DocumentFile) => void;
  removePayslip: (index: number) => void;
  setPayslipVerification: (index: number, result: VerificationResult) => void;
  setPayslipExtractedData: (data: PayslipState['extractedData']) => void;
  
  setFaceImage: (file: DocumentFile | null) => void;
  setFaceDetection: (detected: boolean, quality: FaceState['quality']) => void;
  
  setCurrentStep: (step: number) => void;
  updateClientData: (data: Partial<ExtractedClientData>) => void;
  resetVerification: () => void;
  
  // Getters
  canProceedToStep: (step: number) => boolean;
  getVerificationOutput: () => VerificationOutput;
}

export interface VerificationOutput {
  verification: {
    idCard: {
      verified: boolean;
      confidence: number;
      timestamp: string;
      extractedData: IDCardState['extractedData'];
      warnings: string[];
    };
    payslips: {
      verified: boolean;
      count: number;
      confidence: number;
      extractedData: PayslipState['extractedData'];
    };
    faceImage: {
      verified: boolean;
      faceDetected: boolean;
      quality: FaceState['quality'];
    };
  };
  clientData: ExtractedClientData & {
    documents: {
      idFront?: { file: File; verified: boolean };
      idBack?: { file: File; verified: boolean };
      payslips: File[];
      selfie?: File;
    };
  };
  summary: {
    totalDocuments: number;
    verifiedDocuments: number;
    needsReview: boolean;
    confidenceScore: number;
    canSubmit: boolean;
  };
}

const initialState = {
  idCard: {
    front: null,
    back: null,
    extractedData: null,
  },
  payslips: {
    files: [],
    extractedData: null,
  },
  faceImage: {
    image: null,
    faceDetected: false,
    quality: null,
  },
  currentStep: 0,
  overallStatus: 'incomplete' as const,
  extractedClientData: {
    fullName: '',
    idNumber: '',
    dateOfBirth: '',
    monthlyIncome: 0,
    employer: '',
    gender: '',
  },
};

export const useVerificationStore = create<VerificationState>()(
  devtools(
    persist(
      (set, get) => ({
        ...initialState,

        setIDFront: (file) =>
          set((state) => ({
            idCard: { ...state.idCard, front: file },
          })),

        setIDBack: (file) =>
          set((state) => ({
            idCard: { ...state.idCard, back: file },
          })),

        setIDVerification: (side, result) =>
          set((state) => ({
            idCard: {
              ...state.idCard,
              [side]: state.idCard[side]
                ? { ...state.idCard[side], verification: result, status: result.isValid ? 'verified' : 'error' }
                : null,
            },
          })),

        setIDExtractedData: (data) =>
          set((state) => ({
            idCard: { ...state.idCard, extractedData: data },
            extractedClientData: {
              ...state.extractedClientData,
              ...data,
            },
          })),

        addPayslip: (file) =>
          set((state) => ({
            payslips: {
              ...state.payslips,
              files: [...state.payslips.files, file],
            },
          })),

        removePayslip: (index) =>
          set((state) => ({
            payslips: {
              ...state.payslips,
              files: state.payslips.files.filter((_, i) => i !== index),
            },
          })),

        setPayslipVerification: (index, result) =>
          set((state) => ({
            payslips: {
              ...state.payslips,
              files: state.payslips.files.map((f, i) =>
                i === index
                  ? { ...f, verification: result, status: result.isValid ? 'verified' : 'error' }
                  : f
              ),
            },
          })),

        setPayslipExtractedData: (data) =>
          set((state) => ({
            payslips: { ...state.payslips, extractedData: data },
            extractedClientData: {
              ...state.extractedClientData,
              monthlyIncome: data?.monthlyIncome || state.extractedClientData.monthlyIncome,
              employer: data?.employer || state.extractedClientData.employer,
            },
          })),

        setFaceImage: (file) =>
          set((state) => ({
            faceImage: { ...state.faceImage, image: file },
          })),

        setFaceDetection: (detected, quality) =>
          set((state) => ({
            faceImage: {
              ...state.faceImage,
              faceDetected: detected,
              quality,
            },
          })),

        setCurrentStep: (step) => set({ currentStep: step }),

        updateClientData: (data) =>
          set((state) => ({
            extractedClientData: { ...state.extractedClientData, ...data },
          })),

        resetVerification: () => set(initialState),

        canProceedToStep: (step) => {
          const state = get();
          switch (step) {
            case 0:
              return true;
            case 1:
              return !!state.idCard.front && !!state.idCard.back;
            case 2:
              return state.payslips.files.length > 0;
            case 3:
              return !!state.faceImage.image && state.faceImage.faceDetected;
            default:
              return false;
          }
        },

        getVerificationOutput: () => {
          const state = get();
          
          const idVerified = state.idCard.front?.verification?.isValid && state.idCard.back?.verification?.isValid;
          const idConfidence = Math.min(
            state.idCard.front?.verification?.confidence || 0,
            state.idCard.back?.verification?.confidence || 0
          );
          
          const payslipVerified = state.payslips.files.every(f => f.verification?.isValid);
          const payslipConfidence = state.payslips.files.length > 0
            ? state.payslips.files.reduce((acc, f) => acc + (f.verification?.confidence || 0), 0) / state.payslips.files.length
            : 0;
          
          const totalVerified = (idVerified ? 2 : 0) + state.payslips.files.filter(f => f.verification?.isValid).length + (state.faceImage.faceDetected ? 1 : 0);
          const totalDocs = 2 + state.payslips.files.length + 1;
          
          return {
            verification: {
              idCard: {
                verified: !!idVerified,
                confidence: idConfidence,
                timestamp: new Date().toISOString(),
                extractedData: state.idCard.extractedData,
                warnings: [
                  ...(state.idCard.front?.verification?.warnings || []),
                  ...(state.idCard.back?.verification?.warnings || []),
                ],
              },
              payslips: {
                verified: payslipVerified,
                count: state.payslips.files.length,
                confidence: payslipConfidence,
                extractedData: state.payslips.extractedData,
              },
              faceImage: {
                verified: state.faceImage.faceDetected,
                faceDetected: state.faceImage.faceDetected,
                quality: state.faceImage.quality,
              },
            },
            clientData: {
              ...state.extractedClientData,
              documents: {
                idFront: state.idCard.front?.file ? { file: state.idCard.front.file, verified: !!state.idCard.front.verification?.isValid } : undefined,
                idBack: state.idCard.back?.file ? { file: state.idCard.back.file, verified: !!state.idCard.back.verification?.isValid } : undefined,
                payslips: state.payslips.files.map(f => f.file),
                selfie: state.faceImage.image?.file,
              },
            },
            summary: {
              totalDocuments: totalDocs,
              verifiedDocuments: totalVerified,
              needsReview: !idVerified || !payslipVerified || state.faceImage.quality === 'poor',
              confidenceScore: Math.round((idConfidence + payslipConfidence) / 2),
              canSubmit: idVerified && state.payslips.files.length > 0 && state.faceImage.faceDetected,
            },
          };
        },
      }),
      {
        name: 'verification-storage',
        partialize: (state) => ({
          idCard: state.idCard,
          payslips: state.payslips,
          faceImage: state.faceImage,
          extractedClientData: state.extractedClientData,
        }),
      }
    )
  )
);
