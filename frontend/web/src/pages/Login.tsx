// v10.500 Phase 1 Batch 3a — Login page.
// v10.500 Phase 1 Batch 3b — extended with must_rotate redirect.
//
// First operational entry-point for the React SPA. Composes the existing
// design-system primitives (Input, Button) and consumes useBranding for
// bank-themed presentation. On submit, calls auth.login() which posts
// to /api/auth/login (utils/api.py) and transitions auth.status to
// 'authenticated' OR 'must_rotate' on success.
//
// Post-login redirect logic (Batch 3b):
//   'authenticated' → original target (from ProtectedRoute) or '/'
//   'must_rotate'   → '/change-password'   (rotation required)
//   anything else   → stay on /login (form remains interactive)
//
// No HTML <form> tag per system constraint; submit is wired via Button's
// onClick + Enter-key handler on the password field for keyboard UX.

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

  const [username, setUsername]     = useState('');
  const [password, setPassword]     = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [localError, setLocalError] = useState<string | null>(null);

  const redirectTarget =
    (location.state as RedirectState | null)?.from?.pathname || '/';

  const isSessionExpired = status === 'expired';

  // Reactive redirect (Batch 3a + 3b):
  //   - 'authenticated' → redirectTarget (the originally requested route)
  //   - 'must_rotate'   → /change-password (forced rotation flow)
  // One effect, one source of truth, no race with the submit handler.
  useEffect(() => {
    if (status === 'authenticated') {
      navigate(redirectTarget, { replace: true });
    } else if (status === 'must_rotate') {
      navigate('/change-password', { replace: true });
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
      // useEffect above fires navigation based on resulting status.
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

  const displayedError = error || localError;

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
            {branding?.app_name || 'A2Z'} MIS 360 — Sign in
          </h1>
        </div>
      </header>

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
        </div>
      </main>

      <footer className="px-6 py-4 text-center text-xs text-gray-400">
        {branding?.ip_notice || ''}
      </footer>
    </div>
  );
}
