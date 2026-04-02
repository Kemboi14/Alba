import Tesseract from 'tesseract.js';
import * as pdfjsLib from 'pdfjs-dist';

// Set up PDF.js worker
pdfjsLib.GlobalWorkerOptions.workerSrc = `https://cdnjs.cloudflare.com/ajax/libs/pdf.js/${pdfjsLib.version}/pdf.worker.min.js`;

export interface PayslipVerificationResult {
  isValid: boolean;
  confidence: number;
  extractedData: {
    grossPay?: number;
    netPay?: number;
    employer?: string;
    payPeriod?: string;
    monthlyIncome?: number;
    payDate?: string;
    employeeName?: string;
  };
  errors: string[];
  warnings: string[];
  rawText: string;
}

const FINANCIAL_PATTERNS = {
  grossPay: /(?:gross\s*(?:pay|salary)|total\s*earnings)[:\s]*[KShs]*[\s,]*([\d,]+\.?\d*)/i,
  netPay: /(?:net\s*(?:pay|salary)|take\s*home)[:\s]*[KShs]*[\s,]*([\d,]+\.?\d*)/i,
  basicSalary: /(?:basic\s*salary)[:\s]*[KShs]*[\s,]*([\d,]+\.?\d*)/i,
  employer: /(?:employer|company|organization)[:\s]+([A-Za-z0-9\s&.,]+)(?=\n|$)/i,
  payPeriod: /(?:pay\s*period|period|month)[:\s]+([A-Za-z0-9\s\-/.,]+)(?=\n|$)/i,
  payDate: /(?:pay\s*date|date\s*paid)[:\s]+(\d{1,2}[\/\-\.]\d{1,2}[\/\-\.]\d{2,4})/i,
  employeeName: /(?:employee\s*name|name)[:\s]+([A-Za-z\s]+)(?=\n|$)/i,
};

const INCOME_KEYWORDS = [
  'salary', 'gross', 'net', 'earnings', 'basic', 'pay', 'income',
  'allowance', 'benefit', 'deduction', 'tax', 'nhif', 'nssf'
];

/**
 * Verify payslip from file (PDF or image)
 */
export async function verifyPayslip(file: File): Promise<PayslipVerificationResult> {
  const errors: string[] = [];
  const warnings: string[] = [];
  let rawText = '';

  try {
    // Determine file type and extract text
    if (file.type === 'application/pdf') {
      rawText = await extractTextFromPDF(file);
    } else if (file.type.startsWith('image/')) {
      rawText = await extractTextFromImage(file);
    } else {
      return {
        isValid: false,
        confidence: 0,
        extractedData: {},
        errors: ['Unsupported file type. Please upload PDF or image (JPEG, PNG).'],
        warnings: [],
        rawText: '',
      };
    }

    // Check if document looks like a payslip
    const isPayslipLike = INCOME_KEYWORDS.some(keyword => 
      rawText.toLowerCase().includes(keyword)
    );

    if (!isPayslipLike) {
      warnings.push('Document may not be a payslip. Please verify the uploaded file.');
    }

    // Extract financial data
    const extractedData: PayslipVerificationResult['extractedData'] = {};

    // Extract Gross Pay
    const grossMatch = rawText.match(FINANCIAL_PATTERNS.grossPay);
    if (grossMatch) {
      extractedData.grossPay = parseAmount(grossMatch[1]);
    }

    // Extract Net Pay
    const netMatch = rawText.match(FINANCIAL_PATTERNS.netPay);
    if (netMatch) {
      extractedData.netPay = parseAmount(netMatch[1]);
    }

    // Extract Basic Salary (use as fallback for gross)
    const basicMatch = rawText.match(FINANCIAL_PATTERNS.basicSalary);
    if (basicMatch && !extractedData.grossPay) {
      extractedData.grossPay = parseAmount(basicMatch[1]);
    }

    // Extract Employer
    const employerMatch = rawText.match(FINANCIAL_PATTERNS.employer);
    if (employerMatch) {
      extractedData.employer = cleanEmployerName(employerMatch[1]);
    }

    // Extract Pay Period
    const periodMatch = rawText.match(FINANCIAL_PATTERNS.payPeriod);
    if (periodMatch) {
      extractedData.payPeriod = periodMatch[1].trim();
    }

    // Extract Pay Date
    const dateMatch = rawText.match(FINANCIAL_PATTERNS.payDate);
    if (dateMatch) {
      extractedData.payDate = normalizeDate(dateMatch[1]);
    }

    // Extract Employee Name
    const nameMatch = rawText.match(FINANCIAL_PATTERNS.employeeName);
    if (nameMatch) {
      extractedData.employeeName = nameMatch[1].trim();
    }

    // Calculate monthly income (use net pay as primary indicator of disposable income)
    if (extractedData.netPay) {
      extractedData.monthlyIncome = extractedData.netPay;
    } else if (extractedData.grossPay) {
      extractedData.monthlyIncome = extractedData.grossPay * 0.7; // Estimate net as 70% of gross
      warnings.push('Net pay not found. Monthly income estimated from gross pay.');
    }

    // Calculate confidence score
    let confidence = 0;
    let validFields = 0;

    if (extractedData.grossPay && extractedData.grossPay > 0) {
      confidence += 30;
      validFields++;
    }

    if (extractedData.netPay && extractedData.netPay > 0) {
      confidence += 35;
      validFields++;
    }

    if (extractedData.employer) {
      confidence += 20;
      validFields++;
    }

    if (extractedData.payPeriod || extractedData.payDate) {
      confidence += 15;
      validFields++;
    }

    // Validation checks
    if (!extractedData.grossPay && !extractedData.netPay) {
      errors.push('Could not detect income amount. Please ensure payslip is clearly visible.');
    }

    if (extractedData.grossPay && extractedData.grossPay < 1000) {
      warnings.push('Gross pay amount seems unusually low. Please verify.');
    }

    if (extractedData.grossPay && extractedData.netPay && extractedData.netPay > extractedData.grossPay) {
      warnings.push('Net pay appears higher than gross pay. Please verify the document.');
    }

    // Check if document is recent (within last 3 months)
    if (extractedData.payDate) {
      const payDate = new Date(extractedData.payDate);
      const threeMonthsAgo = new Date();
      threeMonthsAgo.setMonth(threeMonthsAgo.getMonth() - 3);
      
      if (payDate < threeMonthsAgo) {
        warnings.push('Payslip is older than 3 months. Consider uploading a more recent document.');
      }
    }

    return {
      isValid: validFields >= 2 && errors.length === 0,
      confidence: Math.min(confidence, 100),
      extractedData,
      errors,
      warnings,
      rawText,
    };

  } catch (error) {
    console.error('Payslip Verification Error:', error);
    return {
      isValid: false,
      confidence: 0,
      extractedData: {},
      errors: ['Failed to process payslip. Please try again with a clearer document.'],
      warnings: [],
      rawText: '',
    };
  }
}

/**
 * Extract text from PDF file
 */
async function extractTextFromPDF(file: File): Promise<string> {
  const arrayBuffer = await file.arrayBuffer();
  const pdf = await pdfjsLib.getDocument({ data: arrayBuffer }).promise;
  
  let fullText = '';
  
  for (let i = 1; i <= pdf.numPages; i++) {
    const page = await pdf.getPage(i);
    const textContent = await page.getTextContent();
    const pageText = textContent.items.map((item: any) => item.str).join(' ');
    fullText += pageText + '\n';
  }
  
  return fullText;
}

/**
 * Extract text from image using OCR
 */
async function extractTextFromImage(file: File): Promise<string> {
  const result = await Tesseract.recognize(file, 'eng', {
    logger: () => {}, // Silent logging
  });
  
  return result.data.text;
}

/**
 * Parse amount string to number
 */
function parseAmount(amountStr: string): number {
  // Remove commas and spaces, keep decimal point
  const clean = amountStr.replace(/[,\s]/g, '');
  const num = parseFloat(clean);
  return isNaN(num) ? 0 : num;
}

/**
 * Clean employer name
 */
function cleanEmployerName(name: string): string {
  return name
    .replace(/\s+/g, ' ')
    .trim()
    .replace(/\b(LTD|LIMITED|INC|LLC|PLC)\b/gi, (match) => match.toUpperCase());
}

/**
 * Normalize date format
 */
function normalizeDate(dateStr: string): string | null {
  try {
    const parts = dateStr.split(/[/.\-]/);
    if (parts.length === 3) {
      let [day, month, year] = parts;
      if (year.length === 2) {
        year = '20' + year;
      }
      return `${year}-${month.padStart(2, '0')}-${day.padStart(2, '0')}`;
    }
    return null;
  } catch {
    return null;
  }
}

/**
 * Calculate average monthly income from multiple payslips
 */
export function calculateAverageIncome(payslips: PayslipVerificationResult[]): {
  averageGross: number;
  averageNet: number;
  averageMonthly: number;
  employer: string;
  confidence: number;
} {
  if (payslips.length === 0) {
    return {
      averageGross: 0,
      averageNet: 0,
      averageMonthly: 0,
      employer: '',
      confidence: 0,
    };
  }

  const validPayslips = payslips.filter(p => p.isValid);
  
  if (validPayslips.length === 0) {
    return {
      averageGross: 0,
      averageNet: 0,
      averageMonthly: 0,
      employer: payslips[0]?.extractedData.employer || '',
      confidence: 0,
    };
  }

  const totalGross = validPayslips.reduce((sum, p) => sum + (p.extractedData.grossPay || 0), 0);
  const totalNet = validPayslips.reduce((sum, p) => sum + (p.extractedData.netPay || 0), 0);
  const totalMonthly = validPayslips.reduce((sum, p) => sum + (p.extractedData.monthlyIncome || 0), 0);

  // Find most common employer
  const employers = validPayslips.map(p => p.extractedData.employer).filter(Boolean);
  const employer = employers[0] || '';

  // Calculate average confidence
  const avgConfidence = validPayslips.reduce((sum, p) => sum + p.confidence, 0) / validPayslips.length;

  return {
    averageGross: Math.round(totalGross / validPayslips.length),
    averageNet: Math.round(totalNet / validPayslips.length),
    averageMonthly: Math.round(totalMonthly / validPayslips.length),
    employer,
    confidence: Math.round(avgConfidence),
  };
}

/**
 * Validate if income meets minimum requirement
 */
export function validateMinimumIncome(monthlyIncome: number, minimumRequired: number = 15000): {
  meetsRequirement: boolean;
  shortfall: number;
  message: string;
} {
  const meetsRequirement = monthlyIncome >= minimumRequired;
  const shortfall = meetsRequirement ? 0 : minimumRequired - monthlyIncome;
  
  return {
    meetsRequirement,
    shortfall,
    message: meetsRequirement 
      ? `Income meets minimum requirement of KSh ${minimumRequired.toLocaleString()}`
      : `Income is KSh ${shortfall.toLocaleString()} below minimum requirement of KSh ${minimumRequired.toLocaleString()}`,
  };
}

/**
 * Estimate loan eligibility based on income
 */
export function estimateLoanEligibility(
  monthlyIncome: number, 
  existingObligations: number = 0
): {
  maxMonthlyPayment: number;
  maxLoanAmount: number;
  recommendedLoanAmount: number;
  debtToIncomeRatio: number;
} {
  // Use net income for calculations
  const disposableIncome = monthlyIncome - existingObligations;
  
  // Standard rule: max 40% of gross income for debt payments
  const maxMonthlyPayment = monthlyIncome * 0.4 - existingObligations;
  
  // Estimate max loan (assuming 12-month term at ~15% interest)
  const maxLoanAmount = maxMonthlyPayment * 12 * 0.9;
  
  // Recommended is 70% of max for safety
  const recommendedLoanAmount = maxLoanAmount * 0.7;
  
  // Debt-to-income ratio
  const debtToIncomeRatio = existingObligations / monthlyIncome;

  return {
    maxMonthlyPayment: Math.max(0, Math.round(maxMonthlyPayment)),
    maxLoanAmount: Math.round(maxLoanAmount),
    recommendedLoanAmount: Math.round(recommendedLoanAmount),
    debtToIncomeRatio: Math.round(debtToIncomeRatio * 100) / 100,
  };
}
