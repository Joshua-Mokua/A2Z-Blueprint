// v10.500 Phase 1 Batch 3a — Login page.
//
// First operational entry-point for the React SPA. Composes the existing
// design-system primitives (Input, Button) and consumes useBranding for
// bank-themed presentation. On submit, calls auth.login() which posts
// to /api/auth/login (utils/api.py:276) and transitions auth.status to
// 'authenticated' on success.
//
// Post-login redirect honors the `from` location passed by
// ProtectedRoute when an unauthenticated user was bounced here, so the
// user lands back on the page they tried to reach. Falls back to '/' if
// they navigated to /login directly.
//
// No HTML <form> tag per system constraint; submit is wired via Button's
// onClick + Enter-key handler on the password field for keyboard UX.
//
// Architecture notes (REVIVAL_LEDGER):
//   - This page does NOT check `must_change_password`. That contract
//     belongs to Batch 3b — the FastAPI login route will be taught to
//     return a distinguishable response when the flag is set, and the
//     frontend will react then. For Batch 3a, every successful auth
//     transitions straight to 'authenticated'.
//   - Branding is pre-loaded (BrandingProvider sits above AuthProvider
//     in the chain, fetches /api/branding which is public). The login
//     page will not flash unstyled — branding is ready by the time
//     Login mounts.

import { useEffect, useState, type KeyboardEvent } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { useAuth } from '@/hooks/useAuth';
import { useBranding } from '@/hooks/useBranding';
import { Input } from '@/components/Input';
import { Button } from '@/components/Button';


// React-Router's location.state shape when ProtectedRoute redirects here.
interface RedirectState {
  from?: { pathname: string };
}


export function Login() {
  const { login, error, status } = useAuth();
  const { branding } = useBranding();
  const navigate = useNavigate();
  const location = useLocation();

  const [username, setUsername]         = useState('');
  const [password, setPassword]         = useState('');
  const [submitting, setSubmitting]     = useState(false);
  const [localError, setLocalError]     = useState<string | null>(null);

  // Capture the original target if ProtectedRoute redirected here, so
  // post-login we can return the user to where they were going. Falls
  // back to '/'.
  const redirectTarget =
    (location.state as RedirectState | null)?.from?.pathname || '/';

  const isSessionExpired = status === 'expired';

  // Reactive redirect: handles both post-login (state flips to
  // 'authenticated' after submit resolves) AND the URL-bar case (user
  // navigates to /login while already authenticated). One effect, one
  // source of truth, no race with the submit handler.
  useEffect(() => {
    if (status === 'authenticated') {
      navigate(redirectTarget, { replace: true });
    }
  }, [status, redirectTarget, navigate]);

  async function handleSubmit() {
    if (submitting) return;
    if (!username.trim() || !password) {
      setLocalError('Please enter both username and password.');
      return;
    }
    setLocalError(null);
    setSubmitting(true);
    try {
      await login(username.trim(), password);
      // Successful login transitions auth.status to 'authenticated';
      // the useEffect above fires the navigation. We intentionally do
      // NOT navigate here to keep one source of truth.
    } catch {
      // AuthProvider has already populated context.error with the
      // user-friendly message. We just need to stop spinning.
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

  // Prefer AuthProvider's structured error over the local "fill both
  // fields" hint. Local hint only shows when there is no submission
  // attempt to report on.
  const displayedError = error || localError;

  return (
    <div className="min-h-screen bg-gray-50 flex flex-col">
      {/* Header — uses brand secondary (navy in Ecobank palette) */}
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
            {branding?.app_name || 'A2Z'} MIS 360 — Sign in
          </h1>
        </div>
      </header>

      {/* Body — centered card */}
      <main className="flex-1 flex items-center justify-center px-4 py-12">
        <div className="w-full max-w-sm bg-white rounded-lg shadow-md
                        border border-gray-200 p-8">
          <h2 className="text-lg font-semibold text-gray-900 mb-1">
            Sign in to continue
          </h2>
          <p className="text-sm text-gray-500 mb-6">
            Use your staff credentials.
          </p>

          {isSessionExpired && !displayedError && (
            <div className="mb-4 px-3 py-2 rounded-md
                            bg-amber-50 border border-amber-200
                            text-sm text-amber-800">
              Your session expired. Please sign in again.
            </div>
          )}

          <div className="flex flex-col gap-4">
            <Input
              label="Username"
              type="text"
              autoComplete="username"
              autoFocus
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              onKeyDown={handleKeyDown}
              disabled={submitting}
            />
            <Input
              label="Password"
              type="password"
              autoComplete="current-password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
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
              {submitting ? 'Signing in…' : 'Sign in'}
            </Button>
          </div>

          <p className="mt-6 text-xs text-gray-400 text-center">
            {branding?.regulator_full || ''}
          </p>
        </div>
      </main>

      {/* Footer — IP / branding notice */}
      <footer className="px-6 py-4 text-center text-xs text-gray-400">
        {branding?.ip_notice || ''}
      </footer>
    </div>
  );
}
