import React, { useCallback, useState } from 'react';
import { useDropzone } from 'react-dropzone';
import { Upload, X, AlertCircle, CheckCircle, RefreshCw, FileImage } from 'lucide-react';
import { clsx, type ClassValue } from 'clsx';
import { twMerge } from 'tailwind-merge';

// Utility for tailwind class merging
export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export interface DocumentUploadCardProps {
  title: string;
  description: string;
  accept?: string;
  maxFiles?: number;
  onUpload: (files: File[]) => void;
  uploadedFiles?: Array<{
    file: File;
    preview?: string;
    status?: 'pending' | 'verifying' | 'verified' | 'error';
    verification?: {
      isValid: boolean;
      confidence: number;
      errors?: string[];
      warnings?: string[];
    };
  }>;
  onRemove?: (index: number) => void;
  showPreview?: boolean;
  disabled?: boolean;
}

export const DocumentUploadCard: React.FC<DocumentUploadCardProps> = ({
  title,
  description,
  accept = 'image/*,.pdf',
  maxFiles = 1,
  onUpload,
  uploadedFiles = [],
  onRemove,
  showPreview = true,
  disabled = false,
}) => {
  const [isDragActive, setIsDragActive] = useState(false);

  const onDrop = useCallback((acceptedFiles: File[]) => {
    if (acceptedFiles.length > 0) {
      onUpload(acceptedFiles);
    }
  }, [onUpload]);

  const { getRootProps, getInputProps, isDragReject } = useDropzone({
    onDrop,
    accept: accept.split(',').reduce((acc, type) => {
      if (type.includes('image')) {
        acc['image/*'] = [];
      } else if (type.includes('pdf')) {
        acc['application/pdf'] = [];
      }
      return acc;
    }, {} as Record<string, string[]>),
    maxFiles,
    disabled: disabled || uploadedFiles.length >= maxFiles,
    onDragEnter: () => setIsDragActive(true),
    onDragLeave: () => setIsDragActive(false),
  });

  const getStatusIcon = (status?: string) => {
    switch (status) {
      case 'verified':
        return <CheckCircle className="w-5 h-5 text-green-500" />;
      case 'error':
        return <AlertCircle className="w-5 h-5 text-red-500" />;
      case 'verifying':
        return <RefreshCw className="w-5 h-5 text-blue-500 animate-spin" />;
      default:
        return <FileImage className="w-5 h-5 text-gray-400" />;
    }
  };

  const getStatusBadge = (file: typeof uploadedFiles[0]) => {
    if (!file.status || file.status === 'pending') return null;

    const statusConfig = {
      verifying: { bg: 'bg-blue-100', text: 'text-blue-700', label: 'Verifying...' },
      verified: { bg: 'bg-green-100', text: 'text-green-700', label: file.verification?.confidence ? `${file.verification.confidence}% Match` : 'Verified' },
      error: { bg: 'bg-red-100', text: 'text-red-700', label: 'Failed' },
    };

    const config = statusConfig[file.status];
    if (!config) return null;

    return (
      <span className={cn('px-2 py-0.5 text-xs font-medium rounded-full', config.bg, config.text)}>
        {config.label}
      </span>
    );
  };

  return (
    <div className="w-full">
      <div className="mb-2">
        <h3 className="text-lg font-semibold text-gray-900">{title}</h3>
        <p className="text-sm text-gray-500">{description}</p>
      </div>

      {/* Upload Zone */}
      {uploadedFiles.length < maxFiles && (
        <div
          {...getRootProps()}
          className={cn(
            'border-2 border-dashed rounded-lg p-6 cursor-pointer transition-colors',
            'hover:border-blue-400 hover:bg-blue-50/50',
            isDragActive && 'border-blue-500 bg-blue-50',
            isDragReject && 'border-red-400 bg-red-50',
            disabled && 'opacity-50 cursor-not-allowed',
            'flex flex-col items-center justify-center gap-2'
          )}
        >
          <input {...getInputProps()} />
          <Upload className={cn('w-8 h-8', isDragActive ? 'text-blue-500' : 'text-gray-400')} />
          <div className="text-center">
            <p className="text-sm font-medium text-gray-700">
              {isDragActive ? 'Drop files here' : 'Drag & drop files here'}
            </p>
            <p className="text-xs text-gray-500 mt-1">
              or click to browse (max {maxFiles} file{maxFiles > 1 ? 's' : ''})
            </p>
          </div>
          <p className="text-xs text-gray-400">
            Supported: Images (JPG, PNG), PDF
          </p>
        </div>
      )}

      {/* File List */}
      {uploadedFiles.length > 0 && (
        <div className="mt-4 space-y-2">
          {uploadedFiles.map((file, index) => (
            <div
              key={index}
              className={cn(
                'flex items-center gap-3 p-3 rounded-lg border',
                file.status === 'verified' && 'bg-green-50 border-green-200',
                file.status === 'error' && 'bg-red-50 border-red-200',
                file.status === 'verifying' && 'bg-blue-50 border-blue-200',
                (!file.status || file.status === 'pending') && 'bg-gray-50 border-gray-200'
              )}
            >
              {/* Preview */}
              {showPreview && file.preview && file.file.type.startsWith('image/') && (
                <img
                  src={file.preview}
                  alt="Preview"
                  className="w-12 h-12 object-cover rounded border"
                />
              )}
              {!file.preview && (
                <div className="w-12 h-12 bg-gray-100 rounded border flex items-center justify-center">
                  {getStatusIcon(file.status)}
                </div>
              )}

              {/* File Info */}
              <div className="flex-1 min-w-0">
                <p className="text-sm font-medium text-gray-900 truncate">
                  {file.file.name}
                </p>
                <p className="text-xs text-gray-500">
                  {(file.file.size / 1024 / 1024).toFixed(2)} MB
                </p>
                
                {/* Verification Details */}
                {file.verification && (
                  <div className="mt-1">
                    {file.verification.errors && file.verification.errors.length > 0 && (
                      <p className="text-xs text-red-600">
                        {file.verification.errors[0]}
                      </p>
                    )}
                    {file.verification.warnings && file.verification.warnings.length > 0 && 
                     file.verification.errors?.length === 0 && (
                      <p className="text-xs text-amber-600">
                        {file.verification.warnings[0]}
                      </p>
                    )}
                  </div>
                )}
              </div>

              {/* Status Badge */}
              {getStatusBadge(file)}

              {/* Remove Button */}
              {onRemove && (
                <button
                  onClick={() => onRemove(index)}
                  className="p-1 hover:bg-gray-200 rounded transition-colors"
                  type="button"
                >
                  <X className="w-4 h-4 text-gray-500" />
                </button>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
};

export default DocumentUploadCard;
