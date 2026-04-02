# Alba Document Verification Feature

A comprehensive frontend document verification system for the Alba loan management platform. This feature enables client-side verification of Kenyan National IDs, payslips, and face detection before submitting to the Odoo backend.

## Features

- **Kenyan National ID Verification**: OCR-based extraction of ID number, full name, date of birth, and gender
- **Payslip Verification**: PDF and image parsing for income extraction with loan eligibility calculation
- **Face Verification**: Real-time face detection with live camera capture and quality assessment
- **Step-by-Step Wizard**: Guided 4-step verification process with progress tracking
- **Real-time Validation**: Instant feedback on document quality and extracted data
- **Manual Override**: Edit extracted data when OCR confidence is low
- **Mobile Responsive**: Optimized for both desktop and mobile devices

## Installation

```bash
cd frontend
npm install
```

## Usage

### Basic Implementation

```tsx
import { VerificationWizard } from './features/documentVerification';

function LoanApplicationPage() {
  const handleVerificationComplete = (output) => {
    // Send to your Odoo integration
    console.log('Verification complete:', output);
    
    // Example: Send to your API
    fetch('/api/verify-documents', {
      method: 'POST',
      body: JSON.stringify(output),
    });
  };

  return (
    <div className="container mx-auto py-8">
      <VerificationWizard 
        onComplete={handleVerificationComplete}
        onCancel={() => console.log('Cancelled')}
      />
    </div>
  );
}
```

### Individual Components

```tsx
import { 
  IDVerification, 
  PayslipVerification, 
  FaceVerification 
} from './features/documentVerification';

// Use individual components for custom flows
function CustomVerification() {
  return (
    <div>
      <IDVerification 
        onValidationChange={(isValid) => console.log('ID valid:', isValid)}
      />
      <PayslipVerification />
      <FaceVerification />
    </div>
  );
}
```

### Using the Store Directly

```tsx
import { useVerificationStore } from './features/documentVerification';

function MyComponent() {
  const { 
    idCard, 
    payslips, 
    faceImage,
    extractedClientData,
    getVerificationOutput 
  } = useVerificationStore();

  const handleSubmit = () => {
    const output = getVerificationOutput();
    // Process the verification output
  };

  return <button onClick={handleSubmit}>Submit</button>;
}
```

## Output Format

The verification output follows this structure:

```typescript
{
  verification: {
    idCard: {
      verified: boolean,
      confidence: number, // 0-100
      timestamp: string, // ISO date
      extractedData: {
        idNumber: string,
        fullName: string,
        dateOfBirth: string,
        gender: string
      },
      warnings: string[]
    },
    payslips: {
      verified: boolean,
      count: number,
      confidence: number,
      extractedData: {
        monthlyIncome: number,
        employer: string,
        grossPay: number,
        netPay: number
      }
    },
    faceImage: {
      verified: boolean,
      faceDetected: boolean,
      quality: 'good' | 'poor' | 'multiple' | null
    }
  },
  clientData: {
    fullName: string,
    idNumber: string,
    dateOfBirth: string,
    monthlyIncome: number,
    employer: string,
    gender: string,
    documents: {
      idFront: { file: File, verified: boolean },
      idBack: { file: File, verified: boolean },
      payslips: File[],
      selfie: File
    }
  },
  summary: {
    totalDocuments: number,
    verifiedDocuments: number,
    needsReview: boolean,
    confidenceScore: number,
    canSubmit: boolean
  }
}
```

## Configuration

### Tailwind CSS

Add to your `tailwind.config.js`:

```javascript
module.exports = {
  content: [
    './src/**/*.{js,ts,jsx,tsx}',
    './src/features/documentVerification/**/*.{js,ts,jsx,tsx}',
  ],
  // ... rest of config
}
```

### Vite Config

For handling large ML models, add to `vite.config.ts`:

```typescript
export default defineConfig({
  optimizeDeps: {
    exclude: ['tesseract.js', 'face-api.js'],
  },
  build: {
    commonjsOptions: {
      transformMixedEsModules: true,
    },
  },
});
```

## Browser Support

- Chrome/Edge 90+
- Firefox 88+
- Safari 14+
- Mobile Safari (iOS 14+)
- Chrome for Android

## Dependencies

Key libraries used:
- `tesseract.js` - OCR for document text extraction
- `face-api.js` - Face detection and recognition
- `pdfjs-dist` - PDF text extraction
- `react-webcam` - Camera capture
- `react-dropzone` - File upload handling
- `zustand` - State management
- `browser-image-compression` - Image optimization

## API Integration

Connect to your existing Odoo integration:

```typescript
const sendToOdoo = async (verificationOutput) => {
  const response = await fetch('/api/odoo/verify-documents', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      client_data: verificationOutput.clientData,
      verification_results: verificationOutput.verification,
      documents: await Promise.all([
        uploadFile(verificationOutput.clientData.documents.idFront.file),
        uploadFile(verificationOutput.clientData.documents.idBack.file),
        ...verificationOutput.clientData.documents.payslips.map(uploadFile),
        uploadFile(verificationOutput.clientData.documents.selfie),
      ]),
    }),
  });
  
  return response.json();
};
```

## Customization

### Styling

The components use Tailwind CSS classes. Override by:

1. Passing custom classNames (where supported)
2. Using CSS modules
3. Modifying the component source

### Minimum Income Threshold

Change in `payslipVerifier.ts`:

```typescript
const validation = validateMinimumIncome(monthlyIncome, 20000); // Change from 15000
```

### ID Patterns

Modify regex patterns in `idVerifier.ts` for different ID formats.

## Troubleshooting

### Face Detection Not Working

1. Ensure camera permissions are granted
2. Check that models are loading (check browser console)
3. Verify good lighting conditions

### OCR Accuracy Issues

1. Ensure documents are well-lit
2. Use higher resolution images (min 1024px width)
3. Avoid glare and shadows

### PDF Not Processing

1. Ensure PDF is text-based (not scanned image)
2. Check PDF.js worker is loaded correctly

## License

Internal use for Alba Capital loan management system.
