// v10.496 — Input primitive.
// v10.510 β1 type fix — Omit native 'prefix' from extended InputHTMLAttributes.
//   The bespoke ReactNode prefix conflicted with the native string prefix
//   (the HTML <input> prefix attribute, used for some legacy doc contexts).
//   Same pattern as the pre-existing Omit on 'size'.
//
// Text input with label, optional helper text, optional error state,
// optional prefix/suffix icons or text. Three sizes matching Button.
//
// Forwards refs so it works with React Hook Form (added in v10.497).
//
// API:
//   <Input label="Username" placeholder="Enter username" />
//   <Input label="Email" type="email" error="Invalid email" />
//   <Input label="Amount" prefix="KES" suffix=".00" />
//   <Input label="Search" size="sm" />

import { forwardRef, useId } from 'react';
import type { InputHTMLAttributes, ReactNode } from 'react';
import { cn } from '@/lib/cn';
import type { Size } from '@/lib/tokens';

export interface InputProps
  extends Omit<InputHTMLAttributes<HTMLInputElement>, 'size' | 'prefix'> {
  label?: ReactNode;
  helper?: ReactNode;
  error?: ReactNode;
  prefix?: ReactNode;
  suffix?: ReactNode;
  size?: Size;
  containerClassName?: string;
}

const SIZE_CLASSES: Record<Size, string> = {
  sm: 'h-8 text-sm',
  md: 'h-10 text-base',
  lg: 'h-12 text-lg',
};

export const Input = forwardRef<HTMLInputElement, InputProps>(
function Input(
  {
    label, helper, error, prefix, suffix, size = 'md',
    containerClassName, className, id,
    ...rest
  },
  ref,
) {
  // useId() gives a stable unique id even when SSR-rendered, so the
  // <label htmlFor=...> hookup works even without a user-supplied id.
  const reactId = useId();
  const inputId = id || `input-${reactId}`;
  const helperId = helper ? `${inputId}-helper` : undefined;
  const errorId  = error  ? `${inputId}-error`  : undefined;
  const ariaDescribedBy = [helperId, errorId].filter(Boolean).join(' ')
    || undefined;

  return (
    <div className={cn('flex flex-col gap-1', containerClassName)}>
      {label && (
        <label
          htmlFor={inputId}
          className="text-sm font-medium text-gray-700"
        >
          {label}
        </label>
      )}
      <div className={cn(
        'flex items-stretch w-full rounded-md border bg-white',
        'transition-colors duration-150',
        error
          ? 'border-red-500 focus-within:ring-2 focus-within:ring-red-200'
          : 'border-gray-300 focus-within:border-brand-primary ' +
            'focus-within:ring-2 focus-within:ring-brand-primary/20',
      )}>
        {prefix !== undefined && (
          <span className={cn(
            'flex items-center px-3 text-gray-500 ' +
            'border-r border-gray-300 bg-gray-50',
            SIZE_CLASSES[size],
          )}>
            {prefix}
          </span>
        )}
        <input
          ref={ref}
          id={inputId}
          aria-invalid={!!error}
          aria-describedby={ariaDescribedBy}
          className={cn(
            'flex-1 min-w-0 bg-transparent px-3 outline-none',
            'placeholder:text-gray-400',
            SIZE_CLASSES[size],
            className,
          )}
          {...rest}
        />
        {suffix !== undefined && (
          <span className={cn(
            'flex items-center px-3 text-gray-500 ' +
            'border-l border-gray-300 bg-gray-50',
            SIZE_CLASSES[size],
          )}>
            {suffix}
          </span>
        )}
      </div>
      {helper && !error && (
        <p id={helperId} className="text-xs text-gray-500">
          {helper}
        </p>
      )}
      {error && (
        <p id={errorId} className="text-xs text-red-600">
          {error}
        </p>
      )}
    </div>
  );
});
