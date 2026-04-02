import React from 'react';
import { CheckCircle, AlertCircle, XCircle, Loader2, Info } from 'lucide-react';
import { cn } from './DocumentUploadCard';

export interface VerificationBadgeProps {
  status: 'verified' | 'warning' | 'error' | 'pending' | 'verifying';
  confidence?: number;
  message?: string;
  size?: 'sm' | 'md' | 'lg';
  showIcon?: boolean;
}

export const VerificationBadge: React.FC<VerificationBadgeProps> = ({
  status,
  confidence,
  message,
  size = 'md',
  showIcon = true,
}) => {
  const statusConfig = {
    verified: {
      bg: 'bg-green-100',
      border: 'border-green-200',
      text: 'text-green-800',
      icon: CheckCircle,
      label: 'Verified',
      iconColor: 'text-green-600',
    },
    warning: {
      bg: 'bg-amber-100',
      border: 'border-amber-200',
      text: 'text-amber-800',
      icon: AlertCircle,
      label: 'Warning',
      iconColor: 'text-amber-600',
    },
    error: {
      bg: 'bg-red-100',
      border: 'border-red-200',
      text: 'text-red-800',
      icon: XCircle,
      label: 'Error',
      iconColor: 'text-red-600',
    },
    pending: {
      bg: 'bg-gray-100',
      border: 'border-gray-200',
      text: 'text-gray-800',
      icon: Info,
      label: 'Pending',
      iconColor: 'text-gray-500',
    },
    verifying: {
      bg: 'bg-blue-100',
      border: 'border-blue-200',
      text: 'text-blue-800',
      icon: Loader2,
      label: 'Verifying...',
      iconColor: 'text-blue-600',
    },
  };

  const config = statusConfig[status];
  const Icon = config.icon;

  const sizeClasses = {
    sm: 'px-2 py-0.5 text-xs',
    md: 'px-3 py-1 text-sm',
    lg: 'px-4 py-2 text-base',
  };

  const iconSizes = {
    sm: 'w-3 h-3',
    md: 'w-4 h-4',
    lg: 'w-5 h-5',
  };

  return (
    <div
      className={cn(
        'inline-flex items-center gap-1.5 rounded-full border font-medium',
        config.bg,
        config.border,
        config.text,
        sizeClasses[size]
      )}
    >
      {showIcon && (
        <Icon
          className={cn(
            iconSizes[size],
            config.iconColor,
            status === 'verifying' && 'animate-spin'
          )}
        />
      )}
      <span>{message || config.label}</span>
      {confidence !== undefined && status !== 'pending' && status !== 'verifying' && (
        <span className="opacity-75">({confidence}%)</span>
      )}
    </div>
  );
};

export default VerificationBadge;
