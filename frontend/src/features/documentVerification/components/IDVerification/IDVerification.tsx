import React, { useState, useCallback } from "react";
import { DocumentUploadCard } from "../DocumentUploadCard";
import { VerificationBadge } from "../VerificationBadge";
import {
  verifyKenyanID,
  verifyKenyanIDBack,
  fileToBase64,
  validateIDNumber,
} from "../../utils/idVerifier";
import { useVerificationStore } from "../../store/verificationStore";
import {
  AlertCircle,
  CheckCircle,
  Edit2,
  User,
  Calendar,
  CreditCard,
} from "lucide-react";
import { cn } from "../DocumentUploadCard";

export interface IDVerificationProps {
  onComplete?: () => void;
  onValidationChange?: (isValid: boolean) => void;
}

export const IDVerification: React.FC<IDVerificationProps> = ({
  onValidationChange,
}) => {
  const {
    idCard,
    setIDFront,
    setIDBack,
    setIDExtractedData,
    updateClientData,
  } = useVerificationStore();

  const [isVerifyingFront, setIsVerifyingFront] = useState(false);
  const [isVerifyingBack, setIsVerifyingBack] = useState(false);
  const [manualEdit, setManualEdit] = useState(false);
  const [editedData, setEditedData] = useState({
    fullName: idCard.extractedData?.fullName || "",
    idNumber: idCard.extractedData?.idNumber || "",
    dateOfBirth: idCard.extractedData?.dateOfBirth || "",
    gender: idCard.extractedData?.gender || "",
  });

  // Validate if ID is complete
  const isComplete = !!(
    idCard.front?.verification?.isValid &&
    idCard.back?.verification?.isValid &&
    (idCard.extractedData?.idNumber || editedData.idNumber)
  );

  React.useEffect(() => {
    onValidationChange?.(isComplete);
  }, [isComplete, onValidationChange]);

  const handleFrontUpload = useCallback(
    async (files: File[]) => {
      if (files.length === 0) return;

      const file = files[0];
      const preview = await fileToBase64(file);

      setIDFront({
        file,
        preview,
        verification: null,
        status: "pending",
      });

      setIsVerifyingFront(true);

      try {
        const result = await verifyKenyanID(file);

        setIDFront({
          file,
          preview,
          verification: result,
          status: result.isValid ? "verified" : "error",
        });

        if (result.isValid && result.extractedData) {
          setIDExtractedData(result.extractedData);
          setEditedData((prev) => ({
            ...prev,
            ...result.extractedData,
          }));
          updateClientData(result.extractedData);
        }
      } catch (error) {
        console.error("Front verification error:", error);
      } finally {
        setIsVerifyingFront(false);
      }
    },
    [setIDFront, setIDExtractedData, updateClientData],
  );

  const handleBackUpload = useCallback(
    async (files: File[]) => {
      if (files.length === 0) return;

      const file = files[0];
      const preview = await fileToBase64(file);

      setIDBack({
        file,
        preview,
        verification: null,
        status: "pending",
      });

      setIsVerifyingBack(true);

      try {
        // For the back of ID, use dedicated back-side verifier
        const result = await verifyKenyanIDBack(file);

        setIDBack({
          file,
          preview,
          verification: result,
          status: result.isValid ? "verified" : "error",
        });

        // Merge any additional data from back
        if (result.extractedData) {
          const mergedData = {
            ...idCard.extractedData,
            ...result.extractedData,
          };
          setIDExtractedData(mergedData);
          updateClientData(mergedData);
        }
      } catch (error) {
        console.error("Back verification error:", error);
      } finally {
        setIsVerifyingBack(false);
      }
    },
    [setIDBack, setIDExtractedData, updateClientData, idCard.extractedData],
  );

  const handleRemoveFront = useCallback(() => {
    setIDFront(null);
  }, [setIDFront]);

  const handleRemoveBack = useCallback(() => {
    setIDBack(null);
  }, [setIDBack]);

  const handleSaveManualEdit = useCallback(() => {
    const data = {
      fullName: editedData.fullName,
      idNumber: editedData.idNumber,
      dateOfBirth: editedData.dateOfBirth,
      gender: editedData.gender,
    };
    setIDExtractedData(data);
    updateClientData(data);
    setManualEdit(false);
  }, [editedData, setIDExtractedData, updateClientData]);

  const getOverallStatus = () => {
    if (isVerifyingFront || isVerifyingBack) return "verifying";
    if (isComplete) return "verified";
    if (idCard.front?.status === "error" || idCard.back?.status === "error")
      return "error";
    if (idCard.front || idCard.back) return "pending";
    return "pending";
  };

  const getStatusMessage = () => {
    if (isVerifyingFront || isVerifyingBack) return "Verifying your ID...";
    if (isComplete) return "ID verified successfully";
    if (!idCard.front) return "Upload front of ID to begin";
    if (!idCard.back) return "Now upload the back of your ID";
    if (idCard.front?.status === "error") return "Front verification failed";
    if (idCard.back?.status === "error") return "Back verification failed";
    return "Complete both uploads";
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-xl font-bold text-gray-900">ID Verification</h2>
          <p className="text-sm text-gray-500">
            Upload your Kenyan National ID for verification
          </p>
        </div>
        <VerificationBadge
          status={getOverallStatus()}
          message={getStatusMessage()}
        />
      </div>

      {/* Upload Cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        {/* Front Upload */}
        <DocumentUploadCard
          title="ID Front Side"
          description="Upload the front of your National ID (photo side)"
          accept="image/*"
          maxFiles={1}
          onUpload={handleFrontUpload}
          uploadedFiles={
            idCard.front
              ? [
                  {
                    ...idCard.front,
                    verification: idCard.front.verification ?? undefined,
                  },
                ]
              : []
          }
          onRemove={handleRemoveFront}
          disabled={isVerifyingFront}
        />

        {/* Back Upload */}
        <DocumentUploadCard
          title="ID Back Side"
          description="Upload the back of your National ID"
          accept="image/*"
          maxFiles={1}
          onUpload={handleBackUpload}
          uploadedFiles={
            idCard.back
              ? [
                  {
                    ...idCard.back,
                    verification: idCard.back.verification ?? undefined,
                  },
                ]
              : []
          }
          onRemove={handleRemoveBack}
          disabled={isVerifyingBack || !idCard.front}
        />
      </div>

      {/* Extracted Data Display */}
      {(idCard.extractedData || (idCard.front && idCard.back)) && (
        <div className="bg-white border rounded-lg p-6">
          <div className="flex items-center justify-between mb-4">
            <h3 className="text-lg font-semibold text-gray-900">
              Extracted Information
            </h3>
            <button
              onClick={() => setManualEdit(!manualEdit)}
              className="flex items-center gap-1 text-sm text-blue-600 hover:text-blue-700"
            >
              <Edit2 className="w-4 h-4" />
              {manualEdit ? "Cancel" : "Edit"}
            </button>
          </div>

          {manualEdit ? (
            <div className="space-y-4">
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">
                    Full Name
                  </label>
                  <input
                    type="text"
                    value={editedData.fullName}
                    onChange={(e) =>
                      setEditedData((prev) => ({
                        ...prev,
                        fullName: e.target.value,
                      }))
                    }
                    className="w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                    placeholder="Enter full name"
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">
                    ID Number
                  </label>
                  <input
                    type="text"
                    value={editedData.idNumber}
                    onChange={(e) => {
                      const value = e.target.value
                        .replace(/\D/g, "")
                        .slice(0, 8);
                      setEditedData((prev) => ({ ...prev, idNumber: value }));
                    }}
                    className={cn(
                      "w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500",
                      editedData.idNumber &&
                        !validateIDNumber(editedData.idNumber) &&
                        "border-red-300",
                    )}
                    placeholder="8-digit ID number"
                    maxLength={8}
                  />
                  {editedData.idNumber &&
                    !validateIDNumber(editedData.idNumber) && (
                      <p className="text-xs text-red-600 mt-1">
                        ID must be exactly 8 digits
                      </p>
                    )}
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">
                    Date of Birth
                  </label>
                  <input
                    type="date"
                    value={editedData.dateOfBirth}
                    onChange={(e) =>
                      setEditedData((prev) => ({
                        ...prev,
                        dateOfBirth: e.target.value,
                      }))
                    }
                    className="w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">
                    Gender
                  </label>
                  <select
                    value={editedData.gender}
                    onChange={(e) =>
                      setEditedData((prev) => ({
                        ...prev,
                        gender: e.target.value,
                      }))
                    }
                    className="w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                  >
                    <option value="">Select gender</option>
                    <option value="Male">Male</option>
                    <option value="Female">Female</option>
                  </select>
                </div>
              </div>
              <button
                onClick={handleSaveManualEdit}
                disabled={
                  !editedData.idNumber || !validateIDNumber(editedData.idNumber)
                }
                className="w-full py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:bg-gray-300 disabled:cursor-not-allowed"
              >
                Save Changes
              </button>
            </div>
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div className="flex items-center gap-3 p-3 bg-gray-50 rounded-lg">
                <User className="w-5 h-5 text-gray-400" />
                <div>
                  <p className="text-xs text-gray-500">Full Name</p>
                  <p className="text-sm font-medium text-gray-900">
                    {idCard.extractedData?.fullName ||
                      editedData.fullName ||
                      "Not detected"}
                  </p>
                </div>
              </div>
              <div className="flex items-center gap-3 p-3 bg-gray-50 rounded-lg">
                <CreditCard className="w-5 h-5 text-gray-400" />
                <div>
                  <p className="text-xs text-gray-500">ID Number</p>
                  <p className="text-sm font-medium text-gray-900">
                    {idCard.extractedData?.idNumber ||
                      editedData.idNumber ||
                      "Not detected"}
                  </p>
                </div>
              </div>
              <div className="flex items-center gap-3 p-3 bg-gray-50 rounded-lg">
                <Calendar className="w-5 h-5 text-gray-400" />
                <div>
                  <p className="text-xs text-gray-500">Date of Birth</p>
                  <p className="text-sm font-medium text-gray-900">
                    {idCard.extractedData?.dateOfBirth ||
                      editedData.dateOfBirth ||
                      "Not detected"}
                  </p>
                </div>
              </div>
              <div className="flex items-center gap-3 p-3 bg-gray-50 rounded-lg">
                <User className="w-5 h-5 text-gray-400" />
                <div>
                  <p className="text-xs text-gray-500">Gender</p>
                  <p className="text-sm font-medium text-gray-900">
                    {idCard.extractedData?.gender ||
                      editedData.gender ||
                      "Not detected"}
                  </p>
                </div>
              </div>
            </div>
          )}

          {/* Verification Confidence */}
          {idCard.front?.verification && (
            <div className="mt-4 pt-4 border-t">
              <div className="flex items-center gap-2 text-sm">
                {idCard.front.verification.isValid ? (
                  <CheckCircle className="w-4 h-4 text-green-500" />
                ) : (
                  <AlertCircle className="w-4 h-4 text-amber-500" />
                )}
                <span
                  className={
                    idCard.front.verification.isValid
                      ? "text-green-700"
                      : "text-amber-700"
                  }
                >
                  Front verification: {idCard.front.verification.confidence}%
                  confidence
                </span>
              </div>
              {idCard.front.verification.warnings.length > 0 && (
                <div className="mt-2 text-xs text-amber-600">
                  {idCard.front.verification.warnings.map((w, i) => (
                    <p key={i}>• {w}</p>
                  ))}
                </div>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
};

export default IDVerification;
