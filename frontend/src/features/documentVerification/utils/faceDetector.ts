import * as faceapi from "@vladmandic/face-api";

// Model loading state
let modelsLoaded = false;
let modelLoadPromise: Promise<void> | null = null;

// Model URLs - using CDN for lightweight models
const MODEL_URL =
  "https://cdn.jsdelivr.net/npm/@vladmandic/face-api@1.7.12/model";

export interface FaceDetectionResult {
  faceDetected: boolean;
  faceCount: number;
  quality: "good" | "poor" | "multiple" | "none";
  boundingBox: {
    x: number;
    y: number;
    width: number;
    height: number;
  } | null;
  confidence: number;
  warnings: string[];
  landmarks?: faceapi.FaceLandmarks68;
  descriptor?: Float32Array;
}

/**
 * Load face detection models
 */
export async function loadFaceDetectionModels(): Promise<void> {
  if (modelsLoaded) return;

  if (modelLoadPromise) {
    return modelLoadPromise;
  }

  modelLoadPromise = (async () => {
    try {
      await Promise.all([
        faceapi.nets.tinyFaceDetector.loadFromUri(MODEL_URL),
        faceapi.nets.faceLandmark68Net.loadFromUri(MODEL_URL),
        faceapi.nets.faceRecognitionNet.loadFromUri(MODEL_URL),
      ]);
      modelsLoaded = true;
      console.log("Face detection models loaded successfully");
    } catch (error) {
      console.error("Failed to load face detection models:", error);
      throw error;
    }
  })();

  return modelLoadPromise;
}

/**
 * Detect face in image file
 */
export async function detectFace(
  imageFile: File,
): Promise<FaceDetectionResult> {
  const warnings: string[] = [];

  try {
    // Ensure models are loaded
    await loadFaceDetectionModels();

    // Create image element from file
    const image = await fileToImageElement(imageFile);

    // Detect faces with landmarks using proper face-api.js API
    const detections: any = await (faceapi as any)
      .detectAllFaces(
        image,
        new faceapi.TinyFaceDetectorOptions({
          inputSize: 512,
          scoreThreshold: 0.5,
        }),
      )
      .withFaceLandmarks();

    // No faces detected
    if (detections.length === 0) {
      return {
        faceDetected: false,
        faceCount: 0,
        quality: "none",
        boundingBox: null,
        confidence: 0,
        warnings: [
          "No face detected. Please ensure your face is clearly visible.",
        ],
      };
    }

    // Multiple faces detected
    if (detections.length > 1) {
      warnings.push(
        "Multiple faces detected. Please ensure only your face is in the frame.",
      );

      // Return the detection with highest confidence
      const bestDetection = detections.reduce((best: any, current: any) => {
        return current.detection.score > best.detection.score ? current : best;
      });

      const box = bestDetection.detection.box;

      return {
        faceDetected: true,
        faceCount: detections.length,
        quality: "multiple",
        boundingBox: {
          x: Math.round(box.x),
          y: Math.round(box.y),
          width: Math.round(box.width),
          height: Math.round(box.height),
        },
        confidence: Math.round(bestDetection.detection.score * 100),
        warnings,
        landmarks: bestDetection.landmarks,
      };
    }

    // Single face detected - analyze quality
    const detection = detections[0] as any;
    const box = detection.detection.box;

    // Check face size (should be at least 20% of image)
    const faceArea = box.width * box.height;
    const imageArea = image.width * image.height;
    const faceRatio = faceArea / imageArea;

    if (faceRatio < 0.1) {
      warnings.push(
        "Face appears too small in the image. Please move closer to the camera.",
      );
    }

    if (faceRatio > 0.8) {
      warnings.push(
        "Face appears too large or too close. Please move back slightly.",
      );
    }

    // Check face position (should be centered)
    const faceCenterX = box.x + box.width / 2;
    const faceCenterY = box.y + box.height / 2;
    const imageCenterX = image.width / 2;
    const imageCenterY = image.height / 2;

    const offsetX = Math.abs(faceCenterX - imageCenterX) / image.width;
    const offsetY = Math.abs(faceCenterY - imageCenterY) / image.height;

    if (offsetX > 0.3 || offsetY > 0.3) {
      warnings.push(
        "Face is not centered. Please position your face in the center of the frame.",
      );
    }

    // Check detection confidence
    const confidence = Math.round(detection.detection?.score * 100 || 0);
    if (confidence < 70) {
      warnings.push(
        "Face detection confidence is low. Please ensure good lighting and clear view.",
      );
    }

    // Determine quality
    let quality: FaceDetectionResult["quality"] = "good";
    if (warnings.length > 0) {
      quality = "poor";
    }

    return {
      faceDetected: true,
      faceCount: 1,
      quality,
      boundingBox: {
        x: Math.round(box.x),
        y: Math.round(box.y),
        width: Math.round(box.width),
        height: Math.round(box.height),
      },
      confidence,
      warnings,
      landmarks: detection.landmarks,
      descriptor: detection.descriptor,
    };
  } catch (error) {
    console.error("Face Detection Error:", error);
    return {
      faceDetected: false,
      faceCount: 0,
      quality: "none",
      boundingBox: null,
      confidence: 0,
      warnings: [
        "Failed to process image. Please try again with a clearer photo.",
      ],
    };
  }
}

/**
 * Detect face from webcam/video stream
 */
export async function detectFaceFromVideo(
  videoElement: HTMLVideoElement,
): Promise<FaceDetectionResult> {
  try {
    await loadFaceDetectionModels();

    const detections: any = await (faceapi as any)
      .detectAllFaces(
        videoElement,
        new faceapi.TinyFaceDetectorOptions({
          inputSize: 512,
          scoreThreshold: 0.5,
        }),
      )
      .withFaceLandmarks();

    if (detections.length === 0) {
      return {
        faceDetected: false,
        faceCount: 0,
        quality: "none",
        boundingBox: null,
        confidence: 0,
        warnings: [],
      };
    }

    const detection = detections[0] as any; // Take first face
    const box = detection.detection.box;

    return {
      faceDetected: true,
      faceCount: detections.length,
      quality: detections.length > 1 ? "multiple" : "good",
      boundingBox: {
        x: Math.round(box.x),
        y: Math.round(box.y),
        width: Math.round(box.width),
        height: Math.round(box.height),
      },
      confidence: Math.round(detection.detection?.score * 100 || 0),
      warnings: detections.length > 1 ? ["Multiple faces detected"] : [],
      landmarks: detection.landmarks,
    };
  } catch (error) {
    console.error("Video Face Detection Error:", error);
    return {
      faceDetected: false,
      faceCount: 0,
      quality: "none",
      boundingBox: null,
      confidence: 0,
      warnings: ["Detection failed"],
    };
  }
}

/**
 * Compare two faces for similarity (for ID vs Selfie verification)
 */
export async function compareFaces(
  faceDescriptor1: Float32Array,
  faceDescriptor2: Float32Array,
): Promise<{
  isMatch: boolean;
  similarity: number;
  threshold: number;
}> {
  const distance = faceapi.euclideanDistance(faceDescriptor1, faceDescriptor2);
  const similarity = Math.max(0, 1 - distance);
  const threshold = 0.6; // Standard threshold for face matching

  return {
    isMatch: distance < threshold,
    similarity: Math.round(similarity * 100),
    threshold: Math.round(threshold * 100),
  };
}

/**
 * Get guidance message based on detection state
 */
export function getFaceGuidance(result: FaceDetectionResult): string {
  if (!result.faceDetected) {
    return "Position your face in the center of the frame";
  }

  if (result.faceCount > 1) {
    return "Multiple faces detected. Ensure only your face is visible";
  }

  if (result.quality === "poor") {
    const warning =
      result.warnings[0] || "Adjust your position for better detection";
    return warning;
  }

  if (result.confidence < 80) {
    return "Hold still... Improving detection";
  }

  return "Perfect! Hold still to capture";
}

/**
 * Convert File to HTMLImageElement
 */
function fileToImageElement(file: File): Promise<HTMLImageElement> {
  return new Promise((resolve, reject) => {
    const img = new Image();
    const url = URL.createObjectURL(file);

    img.onload = () => {
      URL.revokeObjectURL(url);
      resolve(img);
    };

    img.onerror = () => {
      URL.revokeObjectURL(url);
      reject(new Error("Failed to load image"));
    };

    img.src = url;
  });
}

/**
 * Draw face detection overlay on canvas
 */
export function drawFaceOverlay(
  canvas: HTMLCanvasElement,
  video: HTMLVideoElement,
  detection: FaceDetectionResult,
): void {
  const ctx = canvas.getContext("2d");
  if (!ctx) return;

  // Clear canvas
  ctx.clearRect(0, 0, canvas.width, canvas.height);

  // Draw video frame
  ctx.drawImage(video, 0, 0, canvas.width, canvas.height);

  if (detection.boundingBox && detection.faceDetected) {
    const { x, y, width, height } = detection.boundingBox;

    // Draw bounding box
    ctx.strokeStyle = detection.quality === "good" ? "#22c55e" : "#f59e0b";
    ctx.lineWidth = 3;
    ctx.strokeRect(x, y, width, height);

    // Draw confidence label
    ctx.fillStyle = detection.quality === "good" ? "#22c55e" : "#f59e0b";
    ctx.font = "bold 16px sans-serif";
    ctx.fillText(`${detection.confidence}%`, x, y - 5);

    // Draw landmarks if available
    if (detection.landmarks) {
      ctx.fillStyle = "#3b82f6";
      const landmarks = detection.landmarks.positions;
      for (const point of landmarks) {
        ctx.beginPath();
        ctx.arc(point.x, point.y, 2, 0, 2 * Math.PI);
        ctx.fill();
      }
    }
  }
}

/**
 * Check if environment supports camera
 */
export async function checkCameraSupport(): Promise<{
  supported: boolean;
  error?: string;
}> {
  try {
    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
      return {
        supported: false,
        error: "Camera API not supported in this browser",
      };
    }

    // Try to access camera
    const stream = await navigator.mediaDevices.getUserMedia({ video: true });
    stream.getTracks().forEach((track) => track.stop());

    return { supported: true };
  } catch (error: any) {
    let errorMessage = "Camera access failed";

    if (error.name === "NotAllowedError") {
      errorMessage = "Camera permission denied. Please allow camera access.";
    } else if (error.name === "NotFoundError") {
      errorMessage = "No camera found. Please connect a camera device.";
    } else if (error.name === "NotReadableError") {
      errorMessage = "Camera is already in use by another application.";
    }

    return { supported: false, error: errorMessage };
  }
}
