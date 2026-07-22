// Blocking modal — prompts for staff_code when it's missing on the signed-in
// user's record. AD-authenticated users arrive with no staff_code (AD
// doesn't carry one), and staff_code drives rm_code ("KE" + staff_code)
// portfolio lookups against cbs_accounts, so it must be captured once,
// up front, before those features can work.
//
// Deliberately a modal overlay rendered inside AppShell rather than a
// ProtectedRoute redirect (contrast with ChangePassword/must_rotate): the
// user is already fully authenticated and authorized, so the rest of the
// app stays mounted underneath — this only blocks interaction, not access.
// No close/dismiss affordance — it clears itself only on successful submit.

import { useState, type KeyboardEvent } from 'react';
import { useAuth } from '@/hooks/useAuth';
import { Input } from '@/components/Input';
import { Button } from '@/components/Button';

export function StaffIdModal() {
  const { mustSetStaffId, setStaffId, error } = useAuth();
  const [staffCode, setStaffCode]   = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [localError, setLocalError] = useState<string | null>(null);

  if (!mustSetStaffId) return null;

  async function handleSubmit() {
    if (submitting) return;
    const code = staffCode.trim();
    if (!code) {
      setLocalError('Enter your staff ID.');
      return;
    }
    setLocalError(null);
    setSubmitting(true);
    try {
      await setStaffId(code);
    } catch {
      // AuthProvider populated context.error with the user-friendly message.
    } finally {
      setSubmitting(false);
    }
  }

  function handleKeyDown(e: KeyboardEvent<HTMLInputElement>) {
    if (e.key === 'Enter') {
      e.preventDefault();
      handleSubmit();
    }
  }

  const displayedError = error || localError;

  return (
    <div
      className="fixed inset-0 z-[100] flex items-center justify-center
                 bg-black/50 px-4"
      role="dialog"
      aria-modal="true"
      aria-labelledby="staff-id-modal-title"
    >
      <div className="w-full max-w-sm bg-white rounded-lg shadow-xl
                      border border-gray-200 p-8">
        <h2 id="staff-id-modal-title" className="text-lg font-semibold text-gray-900 mb-1">
          Staff ID required
        </h2>
        <p className="text-sm text-gray-500 mb-6">
          We couldn't find a staff ID on your account. Enter it to continue —
          it's used to pull your portfolio and reporting line.
        </p>

        <div className="flex flex-col gap-4">
          <Input
            label="Staff ID"
            placeholder="e.g. 1293"
            autoFocus
            value={staffCode}
            onChange={(e) => setStaffCode(e.target.value)}
            onKeyDown={handleKeyDown}
            disabled={submitting}
            error={displayedError || undefined}
          />
          <Button
            variant="primary"
            size="md"
            fullWidth
            loading={submitting}
            onClick={handleSubmit}
          >
            {submitting ? 'Saving…' : 'Save and continue'}
          </Button>
        </div>
      </div>
    </div>
  );
}
