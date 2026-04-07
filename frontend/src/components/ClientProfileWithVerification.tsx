import React from "react";
import { VerificationWizard } from "../features/documentVerification";
import type { VerificationOutput } from "../features/documentVerification";

interface ClientProfileWithVerificationProps {
  clientId?: string | null;
  existingDocuments?: {
    idFront?: string;
    idBack?: string;
    payslips?: string[];
    selfie?: string;
  };
  onProfileComplete?: (data: VerificationOutput) => void;
}

export const ClientProfileWithVerification: React.FC<
  ClientProfileWithVerificationProps
> = ({
  onProfileComplete,
  onCancel,
}: ClientProfileWithVerificationProps & { onCancel?: () => void }) => {
  return (
    <VerificationWizard onComplete={onProfileComplete} onCancel={onCancel} />
  );
};

export default ClientProfileWithVerification;
