declare module 'face-api.js' {
  export interface FaceDetection {
    score: number;
    box: {
      x: number;
      y: number;
      width: number;
      height: number;
    };
  }

  export interface FaceLandmarks68 {
    positions: Array<{ x: number; y: number }>;
  }

  export interface WithFaceDescriptor {
    descriptor: Float32Array;
  }

  export interface FaceDetectionWithLandmarks {
    detection: FaceDetection;
    landmarks: FaceLandmarks68;
    descriptor?: Float32Array;
  }

  export class TinyFaceDetectorOptions {
    constructor(options?: { inputSize?: number; scoreThreshold?: number });
  }

  export const nets: {
    tinyFaceDetector: {
      loadFromUri(uri: string): Promise<void>;
    };
    faceLandmark68Net: {
      loadFromUri(uri: string): Promise<void>;
    };
    faceRecognitionNet: {
      loadFromUri(uri: string): Promise<void>;
    };
  };

  export function detectAllFaces(
    input: HTMLImageElement | HTMLVideoElement | HTMLCanvasElement,
    options?: TinyFaceDetectorOptions
  ): Promise<FaceDetection[]>;

  export function euclideanDistance(descriptor1: Float32Array, descriptor2: Float32Array): number;

  // Extend withFaceLandmarks
  interface FaceDetectionWithLandmarksArray extends Array<FaceDetectionWithLandmarks> {}
}

declare module 'tesseract.js';
declare module 'pdfjs-dist';
declare module 'browser-image-compression';
