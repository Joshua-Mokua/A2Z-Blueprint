// v10.543 Phase P Batch P3a — ConfirmDialog primitive.
//
// The standardized confirmation modal for consequential banking actions
// (Disburse, Cancel deal, Record decision, Approve cancellation). Until
// now there was NO modal primitive — destructive actions either fired
// immediately or used bespoke inline panels. This gives them one calm,
// accessible confirm surface.
//
// API:
//   const [open, setOpen] = useState(false);
//   <ConfirmDialog
//     open={open}
//     title="Clear case for disbursement?"
//     message="This marks CALMS00042 ready for the finance system."
//     confirmLabel="Disburse"
//     tone="danger"               // danger | primary  (default primary)
//     loading={mutating}          // disables buttons + shows spinner
//     onConfirm={() => doDisburse()}
//     onCancel={() => setOpen(false)}
//   />
//
// ─── React concepts used here (reference for future work) ─────────────
//  • createPortal: renders the overlay at document.body so it escapes
//    any parent `overflow:hidden`/`z-index` stacking context. The modal
//    is logically a child of the page but physically a child of <body>.
//  • useEffect cleanup: the function returned from useEffect runs on
//    unmount / before re-run — we use it to remove the Escape listener
//    and restore body scroll. Forgetting cleanup is the #1 modal bug.
//  • We render nothing (return null) when closed, so there's no hidden
//    DOM and no stray listeners while inactive.

import { useEffect } from 'react';
import { createPortal } from 'react-dom';
import { Button } from '@/components/Button';
import { cn } from '@/lib/cn';

export interface ConfirmDialogProps {
  open: boolean;
  title: React.ReactNode;
  message?: React.ReactNode;
  confirmLabel?: string;
  cancelLabel?: string;
  tone?: 'primary' | 'danger';
  loading?: boolean;
  onConfirm: () => void;
  onCancel: () => void;
}

export function ConfirmDialog({
  open,
  title,
  message,
  confirmLabel = 'Confirm',
  cancelLabel = 'Cancel',
  tone = 'primary',
  loading = false,
  onConfirm,
  onCancel,
}: ConfirmDialogProps) {
  // Escape-to-cancel + lock background scroll while the modal is open.
  // Both are torn down in the cleanup so they never leak between opens.
  useEffect(() => {
    if (!open) return;

    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && !loading) onCancel();
    };
    document.addEventListener('keydown', onKey);

    const prevOverflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';

    return () => {
      document.removeEventListener('keydown', onKey);
      document.body.style.overflow = prevOverflow;
    };
  }, [open, loading, onCancel]);

  if (!open) return null;

  return createPortal(
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4"
      role="dialog"
      aria-modal="true"
    >
      {/* Backdrop — click to cancel (unless a mutation is in flight). */}
      <div
        className="absolute inset-0 bg-black/40"
        onClick={() => { if (!loading) onCancel(); }}
        aria-hidden="true"
      />

      {/* Dialog card */}
      <div
        className={cn(
          'relative w-full max-w-md rounded-lg bg-white shadow-xl',
          'border border-gray-200',
        )}
      >
        <div className="px-6 pt-5 pb-4">
          <h2 className="text-base font-semibold text-gray-900">{title}</h2>
          {message && (
            <p className="mt-2 text-sm text-gray-500">{message}</p>
          )}
        </div>

        <div className="flex items-center justify-end gap-2 border-t border-gray-200 px-6 py-3">
          <Button variant="ghost" size="sm" onClick={onCancel} disabled={loading}>
            {cancelLabel}
          </Button>
          <Button
            variant={tone === 'danger' ? 'danger' : 'primary'}
            size="sm"
            onClick={onConfirm}
            loading={loading}
          >
            {confirmLabel}
          </Button>
        </div>
      </div>
    </div>,
    document.body,
  );
}
