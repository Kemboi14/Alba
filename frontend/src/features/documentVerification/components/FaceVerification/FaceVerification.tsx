import React, { useState, useRef, useCallback, useEffect } from 'react';
import Webcam from 'react-webcam';
import { VerificationBadge } from '../VerificationBadge';
import { detectFace, detectFaceFromVideo, getFaceGuidance, checkCameraSupport, FaceDetectionResult } from '../../utils/faceDetector';
import { useVerificationStore } from '../../store/verificationStore';
import { Camera, Upload, RefreshCw, AlertCircle, CheckCircle, User } from 'lucide-react';
import { cn } from '../DocumentUploadCard';

export interface FaceVerificationProps {
  onComplete?: () => void;
  onValidationChange?: (isValid: boolean) => void;
}

export const FaceVerification: React.FC<FaceVerificationProps> = ({
  onComplete,
  onValidationChange,
}) => {
  const { faceImage, setFaceImage, setFaceDetection } = useVerificationStore();
  
  const webcamRef = useRef<Webcam>(null);
  const [isCapturing, setIsCapturing] = useState(false);
  const [cameraError, setCameraError] = useState<string | null>(null);
  const [liveDetection, setLiveDetection] = useState<FaceDetectionResult | null>(null);
  const [isModelsLoading, setIsModelsLoading] = useState(true);

  // Check camera support on mount
  useEffect(() => {
    const checkSupport = async () => {
      const { supported, error } = await checkCameraSupport();
      if (!supported) {
        setCameraError(error || 'Camera not available');
      }
      setIsModelsLoading(false);
    };
    checkSupport();
  }, []);

  // Live face detection loop
  useEffect(() => {
    if (!isCapturing || !webcamRef.current?.video) return;

    let animationId: number;
    const detect = async () => {
      if (webcamRef.current?.video) {
        const result = await detectFaceFromVideo(webcamRef.current.video);
        setLiveDetection(result);
      }
      animationId = requestAnimationFrame(detect);
    };

    detect();
    return () => cancelAnimationFrame(animationId);
  }, [isCapturing]);

  const isComplete = faceImage.faceDetected && faceImage.quality === 'good';

  useEffect(() => {
    onValidationChange?.(isComplete);
  }, [isComplete, onValidationChange]);

  const handleCapture = useCallback(async () => {
    if (!webcamRef.current) return;

    const screenshot = webcamRef.current.getScreenshot();
    if (!screenshot) return;

    // Convert base64 to file
    const byteString = atob(screenshot.split(',')[1]);
    const mimeString = screenshot.split(',')[0].split(':')[1].split(';')[0];
    const arrayBuffer = new ArrayBuffer(byteString.length);
    const intArray = new Uint8Array(arrayBuffer);
    
    for (let i = 0; i < byteString.length; i++) {
      intArray[i] = byteString.charCodeAt(i);
    }
    
    const blob = new Blob([arrayBuffer], { type: mimeString });
    const file = new File([blob], 'face-capture.jpg', { type: 'image/jpeg' });

    // Stop capturing
    setIsCapturing(false);

    // Run face detection
    const result = await detectFace(file);
    
    setFaceImage({
      file,
      preview: screenshot,
      verification: result.faceDetected ? {
        isValid: true,
        confidence: result.confidence,
      } : null,
      status: result.faceDetected ? 'verified' : 'error',
    });
    
    setFaceDetection(result.faceDetected, result.quality);
  }, [setFaceImage, setFaceDetection]);

  const handleFileUpload = useCallback(async (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (!file) return;

    const preview = await new Promise<string>((resolve) => {
      const reader = new FileReader();
      reader.onload = () => resolve(reader.result as string);
      reader.readAsDataURL(file);
    });

    setFaceImage({
      file,
      preview,
      verification: null,
      status: 'pending',
    });

    // Run face detection
    const result = await detectFace(file);
    
    setFaceImage({
      file,
      preview,
      verification: result.faceDetected ? {
        isValid: true,
        confidence: result.confidence,
      } : null,
      status: result.faceDetected ? 'verified' : 'error',
    });
    
    setFaceDetection(result.faceDetected, result.quality);
  }, [setFaceImage, setFaceDetection]);

  const handleRetake = useCallback(() => {
    setFaceImage({
      image: null,
      faceDetected: false,
      quality: null,
    });
    setLiveDetection(null);
    setIsCapturing(true);
  }, [setFaceImage]);

  const getOverallStatus = () => {
    if (isModelsLoading) return 'pending';
    if (faceImage.quality === 'multiple') return 'warning';
    if (isComplete) return 'verified';
    if (faceImage.quality === 'poor') return 'warning';
    if (faceImage.faceDetected) return 'pending';
    return 'pending';
  };

  const getStatusMessage = () => {
    if (isModelsLoading) return 'Loading face detection...';
    if (isComplete) return 'Face verified';
    if (faceImage.quality === 'multiple') return 'Multiple faces detected';
    if (faceImage.quality === 'poor') return 'Image quality low';
    if (faceImage.faceDetected) return 'Face detected';
    return 'Capture or upload selfie';
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-xl font-bold text-gray-900">Face Verification</h2>
          <p className="text-sm text-gray-500">
            Take a clear selfie or upload a photo of your face
          </p>
        </div>
        <VerificationBadge
          status={getOverallStatus()}
          message={getStatusMessage()}
        />
      </div>

      {/* Camera Error */}
      {cameraError && (
        <div className="p-4 bg-amber-50 border border-amber-200 rounded-lg flex items-start gap-3">
          <AlertCircle className="w-5 h-5 text-amber-600 mt-0.5" />
          <div>
            <p className="text-sm font-medium text-amber-800">Camera Issue</p>
            <p className="text-sm text-amber-700">{cameraError}</p>
            <p className="text-xs text-amber-600 mt-1">
              You can still upload a photo from your device.
            </p>
          </div>
        </div>
      )}

      {/* Main Content */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        {/* Camera / Preview */}
        <div className="bg-gray-900 rounded-lg overflow-hidden aspect-[4/3] relative">
          {!faceImage.image ? (
            // Camera view
            <>
              {!cameraError && (
                <Webcam
                  ref={webcamRef}
                  audio={false}
                  screenshotFormat="image/jpeg"
                  screenshotQuality={0.95}
                  videoConstraints={{
                    facingMode: 'user',
                    width: 1280,
                    height: 720,
                  }}
                  className="w-full h-full object-cover"
                  onUserMedia={() => setIsCapturing(true)}
                  onUserMediaError={() => setCameraError('Could not access camera')}
                />
              )}
              
              {/* Face guidance overlay */}
              {liveDetection && isCapturing && (
                <div className="absolute inset-0 pointer-events-none">
                  {/* Face oval guide */}
                  <div className="absolute inset-0 flex items-center justify-center">
                    <div 
                      className={cn(
                        'w-48 h-64 border-4 rounded-full transition-colors',
                        liveDetection.faceDetected 
                          ? liveDetection.quality === 'good' 
                            ? 'border-green-500 bg-green-500/10'
                            : 'border-yellow-500 bg-yellow-500/10'
                          : 'border-white/50'
                      )}
                    />
                  </div>
                  
                  {/* Guidance text */}
                  <div className="absolute bottom-4 left-0 right-0 text-center">
                    <p className={cn(
                      'text-sm font-medium px-4 py-2 rounded-full inline-block',
                      liveDetection.faceDetected 
                        ? liveDetection.quality === 'good'
                          ? 'bg-green-500 text-white'
                          : 'bg-yellow-500 text-white'
                        : 'bg-black/70 text-white'
                    )}>
                      {getFaceGuidance(liveDetection)}
                    </p>
                  </div>

                  {/* Confidence indicator */}
                  {liveDetection.faceDetected && (
                    <div className="absolute top-4 right-4">
                      <div className="bg-black/70 text-white px-3 py-1 rounded-full text-sm">
                        {liveDetection.confidence}%
                      </div>
                    </div>
                  )}
                </div>
              )}

              {/* Upload fallback */}
              {cameraError && (
                <div className="absolute inset-0 flex flex-col items-center justify-center p-6 text-white">
                  <Upload className="w-12 h-12 mb-4 opacity-50" />
                  <p className="text-center mb-4">Camera not available</p>
                  <label className="cursor-pointer">
                    <input
                      type="file"
                      accept="image/*"
                      onChange={handleFileUpload}
                      className="hidden"
                    />
                    <span className="px-4 py-2 bg-white text-gray-900 rounded-lg hover:bg-gray-100 transition-colors">
                      Upload Photo
                    </span>
                  </label>
                </div>
              )}
            </>
          ) : (
            // Preview mode
            <>
              <img
                src={faceImage.image.preview}
                alt="Captured face"
                className="w-full h-full object-cover"
              />
              
              {/* Verification overlay */}
              <div className="absolute inset-0 bg-black/50 flex items-center justify-center">
                <div className="text-center text-white p-6">
                  {faceImage.faceDetected ? (
                    <>
                      <CheckCircle className="w-16 h-16 mx-auto mb-4 text-green-500" />
                      <p className="text-xl font-semibold">Face Detected</p>
                      <p className="text-sm opacity-75 mt-1">
                        Quality: {faceImage.quality}
                      </p>
                    </>
                  ) : (
                    <>
                      <AlertCircle className="w-16 h-16 mx-auto mb-4 text-red-500" />
                      <p className="text-xl font-semibold">No Face Detected</p>
                      <p className="text-sm opacity-75 mt-1">
                        Please retake with better lighting
                      </p>
                    </>
                  )}
                </div>
              </div>
            </>
          )}
        </div>

        {/* Controls & Info */}
        <div className="space-y-4">
          {/* Capture Button */}
          {!faceImage.image && !cameraError && (
            <button
              onClick={handleCapture}
              disabled={!liveDetection?.faceDetected || liveDetection.quality !== 'good'}
              className={cn(
                'w-full py-4 rounded-lg font-semibold text-lg transition-all flex items-center justify-center gap-2',
                liveDetection?.faceDetected && liveDetection.quality === 'good'
                  ? 'bg-blue-600 text-white hover:bg-blue-700'
                  : 'bg-gray-200 text-gray-400 cursor-not-allowed'
              )}
            >
              <Camera className="w-6 h-6" />
              {liveDetection?.faceDetected && liveDetection.quality === 'good'
                ? 'Capture Photo'
                : 'Position your face'}
            </button>
          )}

          {/* Retake Button */}
          {faceImage.image && (
            <button
              onClick={handleRetake}
              className="w-full py-4 bg-gray-100 text-gray-700 rounded-lg font-semibold hover:bg-gray-200 transition-colors flex items-center justify-center gap-2"
            >
              <RefreshCw className="w-5 h-5" />
              Retake Photo
            </button>
          )}

          {/* Upload Alternative */}
          {!faceImage.image && !cameraError && (
            <div className="text-center">
              <span className="text-gray-400">or</span>
              <label className="block mt-2 cursor-pointer">
                <input
                  type="file"
                  accept="image/*"
                  onChange={handleFileUpload}
                  className="hidden"
                />
                <span className="text-blue-600 hover:text-blue-700 font-medium">
                  Upload from device
                </span>
              </label>
            </div>
          )}

          {/* Tips */}
          <div className="bg-blue-50 rounded-lg p-4">
            <h4 className="font-medium text-blue-900 mb-2 flex items-center gap-2">
              <User className="w-4 h-4" />
              Tips for best results
            </h4>
            <ul className="text-sm text-blue-700 space-y-1">
              <li>• Face the camera directly</li>
              <li>• Ensure good lighting on your face</li>
              <li>• Remove glasses or hats</li>
              <li>• Keep a neutral expression</li>
              <li>• Frame your face within the oval guide</li>
            </ul>
          </div>

          {/* Quality Issues */}
          {faceImage.quality === 'poor' && faceImage.faceDetected && (
            <div className="bg-yellow-50 border border-yellow-200 rounded-lg p-4">
              <div className="flex items-start gap-2">
                <AlertCircle className="w-5 h-5 text-yellow-600 mt-0.5" />
                <div>
                  <p className="font-medium text-yellow-800">Image Quality Low</p>
                  <p className="text-sm text-yellow-700">
                    Consider retaking for better verification accuracy.
                  </p>
                </div>
              </div>
            </div>
          )}

          {/* Multiple Faces Warning */}
          {faceImage.quality === 'multiple' && (
            <div className="bg-red-50 border border-red-200 rounded-lg p-4">
              <div className="flex items-start gap-2">
                <AlertCircle className="w-5 h-5 text-red-600 mt-0.5" />
                <div>
                  <p className="font-medium text-red-800">Multiple Faces Detected</p>
                  <p className="text-sm text-red-700">
                    Please ensure only your face is visible in the photo.
                  </p>
                </div>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

export default FaceVerification;
