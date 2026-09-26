import React, { useId } from 'react';

interface InputProps extends React.InputHTMLAttributes<HTMLInputElement>, React.RefAttributes<HTMLInputElement> {
  label: string;
  hint?: string;
  error?: string;
}

export function Input({ label, hint, error, id, className = '', required, ref, ...props }: InputProps) {
  const generatedId = useId();
  const inputId = id ?? generatedId;
  return (
    <div className="flex min-w-0 flex-col gap-1">
      <label htmlFor={inputId} className="text-sm font-medium text-secondary">
        {label}{required && <span className="text-red-500 ml-0.5">*</span>}
      </label>
      <input
        id={inputId}
        ref={ref}
        required={required}
        className={`min-w-0 w-full min-h-11 border rounded-lg px-3 py-2 text-base sm:text-sm bg-elevated text-primary placeholder-faint focus-visible:outline focus-visible:outline-2 focus-visible:outline-blue-600 ${
          error ? 'border-red-500' : 'border-line-strong'
        } ${className}`}
        {...props}
      />
      {hint && <p className="text-xs text-faint">{hint}</p>}
      {error && <p className="text-xs text-red-600">{error}</p>}
    </div>
  );
}
Input.displayName = 'Input';
