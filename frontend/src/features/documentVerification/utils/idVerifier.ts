import Tesseract from "tesseract.js";
import imageCompression from "browser-image-compression";

export interface IDVerificationResult {
  isValid: boolean;
  confidence: number;
  extractedData: {
    idNumber?: string;
    fullName?: string;
    dateOfBirth?: string;
    gender?: string;
    serialNumber?: string;
  };
  errors: string[];
  warnings: string[];
  rawText: string;
}

const KENYAN_ID_PATTERNS = {
  idNumber: /\b\d{8}\b/g,
  serialNumber: /[A-Z]{2}\d{6,8}/g,
  dateOfBirth:
    /(\d{2}\/\d{2}\/\d{4})|(\d{2}\.\d{2}\.\d{4})|(\d{2}-\d{2}-\d{4})/g,
  gender: /\b(MALE|FEMALE|M|F)\b/gi,
};

// Keywords that should appear on a genuine Kenyan National ID
const ID_KEYWORDS_FRONT = [
  "republic",
  "kenya",
  "national",
  "identity",
  "jamhuri",
  "kitambulisho",
  "full name",
  "date of birth",
  "sex",
  "district",
  "place of issue",
  "holder",
];

const ID_KEYWORDS_BACK = [
  "republic",
  "kenya",
  "national",
  "identity",
  "jamhuri",
  "kitambulisho",
  "principal registrar",
  "address",
  "district",
  "division",
  "location",
  "serial",
];

/**
 * Check if OCR text contains enough ID keywords to be a genuine ID
 */
function hasIDKeywords(text: string, keywords: string[], minMatches: number): { matches: number; matched: string[] } {
  const lowerText = text.toLowerCase();
  const matched = keywords.filter((kw) => lowerText.includes(kw));
  return { matches: matched.length, matched };
}

/**
 * Compress image before OCR processing
 */
export async function compressImageForOCR(file: File): Promise<File> {
  const options = {
    maxSizeMB: 2,
    maxWidthOrHeight: 1920,
    useWebWorker: true,
    fileType: "image/jpeg",
  };

  try {
    return await imageCompression(file, options);
  } catch (error) {
    console.warn("Image compression failed, using original:", error);
    return file;
  }
}

/**
 * Convert file to base64 for preview
 */
export function fileToBase64(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(reader.result as string);
    reader.onerror = reject;
    reader.readAsDataURL(file);
  });
}

/**
 * Verify Kenyan National ID using OCR
 */
export async function verifyKenyanID(
  imageFile: File,
): Promise<IDVerificationResult> {
  const errors: string[] = [];
  const warnings: string[] = [];

  try {
    // Compress image for faster processing
    const compressedFile = await compressImageForOCR(imageFile);

    // Perform OCR
    const result = await Tesseract.recognize(compressedFile, "eng", {
      logger: (m: { status: string; progress: number }) => {
        if (m.status === "recognizing text") {
          console.log(`OCR Progress: ${(m.progress * 100).toFixed(0)}%`);
        }
      },
    });

    const rawText = result.data.text;
    const extractedData: IDVerificationResult["extractedData"] = {};

    // Check if document looks like a Kenyan ID (keyword check)
    const keywordCheck = hasIDKeywords(rawText, ID_KEYWORDS_FRONT, 2);
    if (keywordCheck.matches < 2) {
      return {
        isValid: false,
        confidence: 0,
        extractedData: {},
        errors: [
          "This does not appear to be a Kenyan National ID. Please upload a clear photo of the front of your National ID card.",
        ],
        warnings: [],
        rawText,
      };
    }

    // Extract ID Number (8 digits)
    const idNumbers = rawText.match(KENYAN_ID_PATTERNS.idNumber);
    if (idNumbers && idNumbers.length > 0) {
      // Take the first valid 8-digit number that looks like an ID
      const validId = idNumbers.find((n: string) => {
        const num = parseInt(n, 10);
        return num > 10000000 && num < 99999999;
      });
      if (validId) {
        extractedData.idNumber = validId;
      }
    }

    // Extract Serial Number (format: XX12345678)
    const serialNumbers = rawText.match(KENYAN_ID_PATTERNS.serialNumber);
    if (serialNumbers && serialNumbers.length > 0) {
      extractedData.serialNumber = serialNumbers[0];
    }

    // Extract Date of Birth
    const dobMatches = rawText.match(KENYAN_ID_PATTERNS.dateOfBirth);
    if (dobMatches && dobMatches.length > 0) {
      extractedData.dateOfBirth = normalizeDate(dobMatches[0]) ?? undefined;
    }

    // Extract Gender
    const genderMatches = rawText.match(KENYAN_ID_PATTERNS.gender);
    if (genderMatches && genderMatches.length > 0) {
      const gender = genderMatches[0].toUpperCase();
      extractedData.gender = gender.startsWith("M") ? "Male" : "Female";
    }

    // Extract Full Name - look for patterns like "FULL NAME", "NAME", or capitalized words
    const fullName = extractFullName(rawText);
    if (fullName) {
      extractedData.fullName = fullName;
    }

    // Calculate confidence score
    let confidence = 0;
    let validFields = 0;

    if (extractedData.idNumber) {
      confidence += 40;
      validFields++;
    } else {
      errors.push("ID number not detected. Ensure the ID is clearly visible.");
    }

    if (extractedData.fullName) {
      confidence += 25;
      validFields++;
    } else {
      warnings.push(
        "Full name not clearly detected. You may need to enter it manually.",
      );
    }

    if (extractedData.dateOfBirth) {
      confidence += 20;
      validFields++;
    } else {
      warnings.push("Date of birth not detected.");
    }

    if (extractedData.gender) {
      confidence += 15;
      validFields++;
    }

    // Additional validation
    if (validFields < 2) {
      warnings.push(
        "Low detection confidence. Please ensure good lighting and clear image.",
      );
    }

    if (result.data.confidence < 60) {
      warnings.push("Image quality is low. Consider retaking the photo.");
    }

    return {
      isValid: !!extractedData.idNumber && validFields >= 2,
      confidence: Math.min(confidence, 100),
      extractedData,
      errors,
      warnings,
      rawText,
    };
  } catch (error) {
    console.error("ID Verification Error:", error);
    return {
      isValid: false,
      confidence: 0,
      extractedData: {},
      errors: [
        "Failed to process image. Please try again with a clearer photo.",
      ],
      warnings: [],
      rawText: "",
    };
  }
}

/**
 * Verify back side of Kenyan National ID using OCR
 * Less strict than front — checks for document keywords and serial number
 */
export async function verifyKenyanIDBack(
  imageFile: File,
): Promise<IDVerificationResult> {
  const errors: string[] = [];
  const warnings: string[] = [];

  try {
    const compressedFile = await compressImageForOCR(imageFile);

    const result = await Tesseract.recognize(compressedFile, "eng", {
      logger: (m: { status: string; progress: number }) => {
        if (m.status === "recognizing text") {
          console.log(`OCR Progress (back): ${(m.progress * 100).toFixed(0)}%`);
        }
      },
    });

    const rawText = result.data.text;
    const extractedData: IDVerificationResult["extractedData"] = {};

    // Check if document looks like the back of a Kenyan ID
    const keywordCheck = hasIDKeywords(rawText, ID_KEYWORDS_BACK, 2);
    if (keywordCheck.matches < 2) {
      return {
        isValid: false,
        confidence: 0,
        extractedData: {},
        errors: [
          "This does not appear to be the back of a Kenyan National ID. Please upload a clear photo of the back of your ID card.",
        ],
        warnings: [],
        rawText,
      };
    }

    let confidence = 0;
    let validFields = 0;

    // Keywords matched — that's a strong signal
    confidence += 30;
    validFields++;

    // Extract Serial Number
    const serialNumbers = rawText.match(KENYAN_ID_PATTERNS.serialNumber);
    if (serialNumbers && serialNumbers.length > 0) {
      extractedData.serialNumber = serialNumbers[0];
      confidence += 30;
      validFields++;
    } else {
      warnings.push("Serial number not clearly detected on back side.");
    }

    // Check for address/district text (common on back)
    const addressPattern = /(?:address|district|division|location|province)[:\s]+([A-Za-z\s]+)/i;
    const addressMatch = rawText.match(addressPattern);
    if (addressMatch) {
      confidence += 20;
      validFields++;
    }

    // Check for ID number on back too (sometimes visible)
    const idNumbers = rawText.match(KENYAN_ID_PATTERNS.idNumber);
    if (idNumbers && idNumbers.length > 0) {
      const validId = idNumbers.find((n: string) => {
        const num = parseInt(n, 10);
        return num > 10000000 && num < 99999999;
      });
      if (validId) {
        extractedData.idNumber = validId;
        confidence += 20;
        validFields++;
      }
    }

    if (result.data.confidence < 50) {
      warnings.push("Image quality is low. Consider retaking the photo.");
    }

    return {
      isValid: validFields >= 2,
      confidence: Math.min(confidence, 100),
      extractedData,
      errors,
      warnings,
      rawText,
    };
  } catch (error) {
    console.error("ID Back Verification Error:", error);
    return {
      isValid: false,
      confidence: 0,
      extractedData: {},
      errors: [
        "Failed to process image. Please try again with a clearer photo.",
      ],
      warnings: [],
      rawText: "",
    };
  }
}

/**
 * Extract full name from ID text
 */
function extractFullName(text: string): string | null {
  // Look for patterns like "FULL NAME" or "NAME" followed by capitalized words
  const namePatterns = [
    /FULL\s*NAME[:\s]+([A-Z\s]+)(?=\n|$)/i,
    /NAME[:\s]+([A-Z\s]+)(?=\n|$)/i,
    /SURNAME[:\s]+([A-Z\s]+)(?=\n|$)/i,
  ];

  for (const pattern of namePatterns) {
    const match = text.match(pattern);
    if (match && match[1]) {
      const name = match[1].trim();
      if (name.length > 3 && name.includes(" ")) {
        return toTitleCase(name);
      }
    }
  }

  // Fallback: look for consecutive capitalized words (2-4 words)
  const capitalizedWords = text.match(/\b[A-Z][A-Z\s]+[A-Z]\b/g);
  if (capitalizedWords) {
    for (const wordGroup of capitalizedWords) {
      const words = wordGroup.trim().split(/\s+/);
      if (words.length >= 2 && words.length <= 4 && wordGroup.length > 5) {
        // Filter out common false positives
        const lower = wordGroup.toLowerCase();
        if (
          !lower.includes("republic") &&
          !lower.includes("kenya") &&
          !lower.includes("national") &&
          !lower.includes("identity") &&
          !lower.includes("card")
        ) {
          return toTitleCase(wordGroup);
        }
      }
    }
  }

  return null;
}

/**
 * Normalize date format to YYYY-MM-DD
 */
function normalizeDate(dateStr: string): string | null {
  try {
    // Remove any non-numeric characters except separators
    const clean = dateStr.replace(/[^\d/\-.]/g, "");

    // Try to parse DD/MM/YYYY or DD.MM.YYYY or DD-MM-YYYY
    const parts = clean.split(/[/.\-]/);
    if (parts.length === 3) {
      const day = parts[0].padStart(2, "0");
      const month = parts[1].padStart(2, "0");
      const year = parts[2].length === 2 ? "19" + parts[2] : parts[2];

      // Validate date
      const date = new Date(`${year}-${month}-${day}`);
      if (!isNaN(date.getTime())) {
        return `${year}-${month}-${day}`;
      }
    }
    return null;
  } catch {
    return null;
  }
}

/**
 * Convert string to Title Case
 */
function toTitleCase(str: string): string {
  return str
    .toLowerCase()
    .split(" ")
    .map((word) => word.charAt(0).toUpperCase() + word.slice(1))
    .join(" ");
}

/**
 * Validate ID number format
 */
export function validateIDNumber(idNumber: string): boolean {
  // Kenyan ID numbers are 8 digits
  return /^\d{8}$/.test(idNumber);
}

/**
 * Calculate age from date of birth
 */
export function calculateAge(dateOfBirth: string): number {
  try {
    const dob = new Date(dateOfBirth);
    const today = new Date();
    let age = today.getFullYear() - dob.getFullYear();
    const monthDiff = today.getMonth() - dob.getMonth();

    if (monthDiff < 0 || (monthDiff === 0 && today.getDate() < dob.getDate())) {
      age--;
    }

    return age;
  } catch {
    return 0;
  }
}

/**
 * Check if person is eligible (18+ years)
 */
export function isEligibleAge(dateOfBirth: string): boolean {
  const age = calculateAge(dateOfBirth);
  return age >= 18;
}
