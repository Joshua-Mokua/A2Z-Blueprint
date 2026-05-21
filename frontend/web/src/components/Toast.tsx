// v10.496 — Toast primitive + ToastProvider.
//
// User feedback notifications. "Saved successfully.", "Login failed.",
// "Cache cleared." Auto-dismiss after 4s by default. Stack vertically
// in the top-right corner.
//
// Provider pattern: ToastProvider holds the toast queue in state and
// renders the visible toasts. useToast() hook is what page code uses.
// Example usage from any component:
//
//   const { toast } = useToast();
//   ...
//   toast({ tone: 'success', message: 'Targets saved' });
//   toast({ tone: 'danger',  message: 'Network error',
//           duration: 6000 });
//
// Add <ToastProvider> high in the tree (App.tsx wraps it inside
// BrandingProvider in v10.496).

import {
  createContext, useCallback, useContext, useMemo, useState,
  type ReactNode,
} from 'react';
import { cn } from '@/lib/cn';

export type ToastTone = 'success' | 'warning' | 'danger' | 'info';

interface ToastInput {
  message: ReactNode;
  tone?: ToastTone;
  duration?: number;  // ms; 0 = sticky until dismissed
}

interface Toast extends Required<Omit<ToastInput, 'message'>> {
  id: number;
  message: ReactNode;
}

interface ToastContextValue {
  toast: (input: ToastInput) => void;
  dismiss: (id: number) => void;
}

const ToastContext = createContext<ToastContextValue | null>(null);

let _toastIdCounter = 0;

const TONE_CLASSES: Record<ToastTone, string> = {
  success: 'bg-green-50 border-green-300 text-green-800',
  warning: 'bg-amber-50 border-amber-300 text-amber-800',
  danger:  'bg-red-50 border-red-300 text-red-800',
  info:    'bg-blue-50 border-blue-300 text-blue-800',
};

const TONE_ICONS: Record<ToastTone, string> = {
  success: '✓',
  warning: '⚠',
  danger:  '✕',
  info:    'ℹ',
};

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([]);

  const dismiss = useCallback((id: number) => {
    setToasts((prev) => prev.filter((t) => t.id !== id));
  }, []);

  const toast = useCallback((input: ToastInput) => {
    const id = ++_toastIdCounter;
    const next: Toast = {
      id,
      message: input.message,
      tone: input.tone ?? 'info',
      duration: input.duration ?? 4000,
    };
    setToasts((prev) => [...prev, next]);
    if (next.duration > 0) {
      window.setTimeout(() => dismiss(id), next.duration);
    }
  }, [dismiss]);

  const value = useMemo(() => ({ toast, dismiss }),
                         [toast, dismiss]);

  return (
    <ToastContext.Provider value={value}>
      {children}
      <div
        aria-live="polite"
        aria-atomic="true"
        className="pointer-events-none fixed top-4 right-4 z-50
                   flex flex-col gap-2 max-w-sm"
      >
        {toasts.map((t) => (
          <div
            key={t.id}
            role="status"
            className={cn(
              'pointer-events-auto flex items-start gap-3 rounded-md ' +
                'border px-4 py-3 shadow-md animate-in fade-in',
              TONE_CLASSES[t.tone],
            )}
          >
            <span aria-hidden="true" className="text-lg leading-none">
              {TONE_ICONS[t.tone]}
            </span>
            <div className="flex-1 text-sm">{t.message}</div>
            <button
              type="button"
              onClick={() => dismiss(t.id)}
              aria-label="Dismiss notification"
              className="text-current opacity-60 hover:opacity-100"
            >
              ×
            </button>
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  );
}

export function useToast(): ToastContextValue {
  const ctx = useContext(ToastContext);
  if (!ctx) {
    throw new Error('useToast must be used inside ToastProvider');
  }
  return ctx;
}
