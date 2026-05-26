// v10.500 Phase 1 Batch 3b — ChangePassword page.
//
// Forced-rotation surface for users whose users.json record has
// must_change_password=true. Reachable as /change-password. Composes
// the same Input + Button + useBranding primitives the Login page uses
// so the visual language stays consistent.
//
// Doctrine context (REVIVAL_LEDGER batch 3b):
//   - Page is reachable when auth.status === 'must_rotate' (the user
//     just logged in with a must_rotate-scope token) OR
//     auth.status === 'authenticated' (future voluntary rotation flow
//     — not exposed in this batch but the page handles it correctly).
//   - ProtectedRoute confines must_rotate users HERE; bouncing every
//     other route to /change-password. This page is their only legit
//     destination until rotation completes.
//   - The page does NOT display the username. RoleProvider does not
//     hydrate identity during must_rotate (whoami-detailed would 403
//     a must_rotate token), so we have no name to display. Generic
//     "Set a new password to continue" keeps separation-of-concerns
//     clean: AuthProvider owns the token, RoleProvider owns identity,
//     neither bleeds into the other.
//
// Validation policy (matches utils/api.py /api/auth/change-password):
//   - new_password length ≥ 8
//   - new_password ≠ current_password
//   - confirmation matches new_password
//
// On success the AuthProvider state flips to 'authenticated' and the
// useEffect navigates the user to '/'. RoleProvider's auth-status
// effect then fires whoami-detailed + registry, identity hydrates,
// Dashboard renders.

import { useEffect, useState, type KeyboardEvent } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '@/hooks/useAuth';
import { useBranding } from '@/hooks/useBranding';
import { Input } from '@/components/Input';
import { Button } from '@/components/Button';

const MIN_PASSWORD_LENGTH = 8;

export function ChangePassword() {
  const { changePassword, logout, status, error } = useAuth();
  const { branding } = useBranding();
  const navigate = useNavigate();

  const [currentPw,      setCurrentPw]   = useState('');
  const [newPw,          setNewPw]       = useState('');
  const [confirmPw,      setConfirmPw]   = useState('');
  const [submitting,     setSubmitting]  = useState(false);
  const [localError,     setLocalError]  = useState<string | null>(null);

  // Reactive redirect on transition to 'authenticated' (success path).
  // ProtectedRoute already handles the inverse (unauthenticated /
  // expired users land on /login). 'must_rotate' is the only state
  // that keeps us rendered.
  useEffect(() => {
    if (status === 'authenticated') {
      navigate('/', { replace: true });
    }
  }, [status, navigate]);

  async function handleSubmit() {
    if (submitting) return;

    // Client-side validation — match server policy so failures are
    // caught before a round-trip when possible.
    if (!currentPw) {
      setLocalError('Enter your current password.');
      return;
    }
    if (!newPw) {
      setLocalError('Enter a new password.');
      return;
    }
    if (newPw.length < MIN_PASSWORD_LENGTH) {
      setLocalError(`New password must be at least ${MIN_PASSWORD_LENGTH} characters.`);
      return;
    }
    if (newPw === currentPw) {
      setLocalError('New password must differ from your current password.');
      return;
    }
    if (newPw !== confirmPw) {
      setLocalError('Confirmation does not match the new password.');
      return;
    }

    setLocalError(null);
    setSubmitting(true);
    try {
      await changePassword(currentPw, newPw);
      // useEffect above fires navigation to '/' on status='authenticated'.
    } catch {
      // AuthProvider populated context.error with the user-friendly
      // message. We just need to stop spinning.
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

  // Escape hatch: if a user genuinely cannot remember any password,
  // they should be able to bail out to the login screen (which itself
  // offers a forgot-password path via Streamlit until React grows one).
  function handleCancel() {
    logout();
    navigate('/login', { replace: true });
  }

  const displayedError = error || localError;
  const isForced = status === 'must_rotate';

  return (
    <div className="min-h-screen bg-gray-50 flex flex-col">
      <header
        className="px-6 py-5 text-white shadow-sm"
        style={{ background: branding?.brand.secondary || '#0b2747' }}
      >
        <div className="max-w-5xl mx-auto">
          <div className="text-[11px] uppercase tracking-[2.5px]
                          font-bold opacity-70">
            {branding?.bank_name || 'A2Z MIS 360'}
          </div>
          <h1 className="text-xl font-bold mt-1">
            {branding?.app_name || 'A2Z'} MIS 360 — Set a new password
          </h1>
        </div>
      </header>

      <main className="flex-1 flex items-center justify-center px-4 py-12">
        <div className="w-full max-w-sm bg-white rounded-lg shadow-md
                        border border-gray-200 p-8">
          <h2 className="text-lg font-semibold text-gray-900 mb-1">
            {isForced ? 'Password change required' : 'Change your password'}
          </h2>
          <p className="text-sm text-gray-500 mb-6">
            {isForced
              ? 'Set a new password to continue.'
              : 'Update your sign-in credentials.'}
          </p>

          {isForced && (
            <div className="mb-4 px-3 py-2 rounded-md
                            bg-amber-50 border border-amber-200
                            text-sm text-amber-800">
              🔑 You must set a new password before you can access the
              system.
            </div>
          )}

          <div className="flex flex-col gap-4">
            <Input
              label="Current password"
              type="password"
              autoComplete="current-password"
              autoFocus
              value={currentPw}
              onChange={(e) => setCurrentPw(e.target.value)}
              onKeyDown={handleKeyDown}
              disabled={submitting}
            />
            <Input
              label="New password"
              type="password"
              autoComplete="new-password"
              helper={`At least ${MIN_PASSWORD_LENGTH} characters.`}
              value={newPw}
              onChange={(e) => setNewPw(e.target.value)}
              onKeyDown={handleKeyDown}
              disabled={submitting}
            />
            <Input
              label="Confirm new password"
              type="password"
              autoComplete="new-password"
              value={confirmPw}
              onChange={(e) => setConfirmPw(e.target.value)}
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
              {submitting ? 'Updating…' : 'Set new password'}
            </Button>
            <Button
              variant="ghost"
              size="md"
              fullWidth
              disabled={submitting}
              onClick={handleCancel}
            >
              Cancel and sign out
            </Button>
          </div>

          <p className="mt-6 text-xs text-gray-400 text-center">
            {branding?.regulator_full || ''}
          </p>
        </div>
      </main>

      <footer className="px-6 py-4 text-center text-xs text-gray-400">
        {branding?.ip_notice || ''}
      </footer>
    </div>
  );
}
