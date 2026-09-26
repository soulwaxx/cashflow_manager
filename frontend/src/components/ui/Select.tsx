import React, { useId } from 'react';

interface SelectProps extends React.SelectHTMLAttributes<HTMLSelectElement>, React.RefAttributes<HTMLSelectElement> {
  label: string;
  hint?: string;
  error?: string;
  options: Array<{ value: string; label: string }>;
}

export function Select({ label, hint, error, id, options, required, ref, ...props }: SelectProps) {
  const generatedId = useId();
  const selectId = id ?? generatedId;
  return (
    <div className="flex min-w-0 flex-col gap-1">
      <label htmlFor={selectId} className="text-sm font-medium text-secondary">{label}{required && <span className="text-red-500 ml-0.5">*</span>}</label>
      <select
        id={selectId}
        ref={ref}
        required={required}
        className={`min-w-0 w-full min-h-11 border rounded-lg px-3 py-2 text-base sm:text-sm bg-elevated text-primary focus-visible:outline focus-visible:outline-2 focus-visible:outline-blue-600 ${error ? 'border-red-500' : 'border-line-strong'}`}
        {...props}
      >
        <option value="">— select —</option>
        {options.map((o) => (
          <option key={o.value} value={o.value}>{o.label}</option>
        ))}
      </select>
      {hint && <p className="text-xs text-faint">{hint}</p>}
      {error && <p className="text-xs text-red-600">{error}</p>}
    </div>
  );
}
Select.displayName = 'Select';
