import { useEffect, useState, type KeyboardEvent } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { useAuth } from '@/hooks/useAuth';
import { useBranding } from '@/hooks/useBranding';

interface RedirectState { from?: { pathname: string }; }

export function Login() {
  const { login, error, status } = useAuth();
  const { branding } = useBranding();
  const navigate  = useNavigate();
  const location  = useLocation();

  const [username,   setUsername]   = useState('');
  const [password,   setPassword]   = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [localError, setLocalError] = useState<string | null>(null);
  // AD auth can legitimately take up to ~20s (the server's ad_timeout_seconds)
  // before it even falls back to local auth. Without this, a slow AD server
  // makes the button just sit on "Signing in…" with nothing to suggest it's
  // still working rather than stuck.
  const [showSlowHint, setShowSlowHint] = useState(false);

  // Hiding a route from the Sidebar's nav list (org_config.json's
  // hidden_modules) does not change what the router mounts at that path -
  // so without this, a fresh login (no prior "from" location) always fell
  // through to the '/' default and rendered Dashboard even when it's hidden.
  // '/pipeline' has no visibleFor gate in Sidebar.tsx, so it's a safe
  // fallback landing page for every authenticated role.
  const requestedTarget = (location.state as RedirectState | null)?.from?.pathname;
  const hiddenModules = new Set(branding?.hidden_modules ?? []);
  const fallbackHome = hiddenModules.has('/') ? '/pipeline' : '/';
  const redirectTarget = (requestedTarget && !hiddenModules.has(requestedTarget)) ? requestedTarget : fallbackHome;
  const isExpired = status === 'expired';

  useEffect(() => {
    if (status === 'authenticated') navigate(redirectTarget, { replace: true });
    else if (status === 'must_rotate') navigate('/change-password', { replace: true });
  }, [status, redirectTarget, navigate]);

  async function handleSubmit() {
    if (submitting) return;
    if (!username.trim() || !password) { setLocalError('Please enter both username and password.'); return; }
    setLocalError(null);
    setSubmitting(true);
    setShowSlowHint(false);
    const slowTimer = setTimeout(() => setShowSlowHint(true), 4_000);
    try { await login(username.trim(), password); }
    catch { /* error surfaced via context */ }
    finally {
      clearTimeout(slowTimer);
      setSubmitting(false);
      setShowSlowHint(false);
    }
  }

  function onKey(e: KeyboardEvent<HTMLInputElement>) {
    if (e.key === 'Enter') { e.preventDefault(); handleSubmit(); }
  }

  const displayedError = error || localError;

  return (
    <div className="login-shell">
      {/* Left panel — brand */}
      <div className="login-left">
        <div className="login-brand">
          <div className="login-brand-row">
            <img src="/img/ecobank-light.svg" alt="Ecobank" className="login-logo" />
            <div className="login-brand-text">
              <div className="login-brand-name">{branding?.app_name ?? 'EKE Blueprint'}</div>
              <div className="login-brand-tag">MIS 360</div>
            </div>
          </div>
        </div>
        <div className="login-tagline">
          One platform.<br />Total intelligence.
        </div>
        <div className="login-sub">
          Executive, pipeline and credit intelligence for the modern banking team.
        </div>
        <div className="login-dots">
          <span className="login-dot active" />
          <span className="login-dot" />
          <span className="login-dot" />
        </div>
      </div>

      {/* Right panel — form */}
      <div className="login-right">
        <div className="login-card">
          <h2 className="login-heading">Sign in</h2>
          <p className="login-sub-text">Use your staff credentials to continue.</p>

          {isExpired && !displayedError && (
            <div className="login-alert warn">Your session expired. Please sign in again.</div>
          )}
          {displayedError && (
            <div className="login-alert error">{displayedError}</div>
          )}

          <div className="login-field">
            <label className="login-label" htmlFor="login-username">Username</label>
            <input
              id="login-username"
              className="login-input"
              type="text"
              autoComplete="username"
              autoFocus
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              onKeyDown={onKey}
              disabled={submitting}
              placeholder="staff.username"
            />
          </div>

          <div className="login-field">
            <label className="login-label" htmlFor="login-password">Password</label>
            <input
              id="login-password"
              className="login-input"
              type="password"
              autoComplete="current-password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              onKeyDown={onKey}
              disabled={submitting}
              placeholder="••••••••"
            />
          </div>

          <button
            type="button"
            className="login-btn"
            disabled={submitting}
            onClick={handleSubmit}
          >
            {submitting && (
              <span className="login-spinner" aria-hidden="true" />
            )}
            {submitting ? 'Signing in…' : 'Sign in'}
          </button>

          {submitting && showSlowHint && (
            <p className="login-slow-hint">
              Still contacting the authentication server — this can take up to 45 seconds.
            </p>
          )}

          {branding?.ip_notice && (
            <p className="login-notice">{branding.ip_notice}</p>
          )}
        </div>
      </div>
    </div>
  );
}
