import { useState } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { useRole } from '@/hooks/useRole';

interface RouteEntry { label: string; domain: string; path: string; match: (p: string) => boolean; }

const DEMO_HIDE = new Set<string>(['/', '/initiatives', '/profitability']);

const ROUTES: RouteEntry[] = [
  { label: 'Dashboard',             domain: 'Executive Intelligence',       path: '/',                 match: (p) => p === '/' },
  { label: 'BSC Performance',       domain: 'Executive Intelligence',       path: '/perform',          match: (p) => p === '/perform' },
  { label: 'Target Cascade',        domain: 'Executive Intelligence',       path: '/cascade',          match: (p) => p.startsWith('/cascade') },
  { label: 'Strategic Initiatives', domain: 'Executive Intelligence',       path: '/initiatives',      match: (p) => p.startsWith('/initiatives') },
  { label: 'Profitability',         domain: 'Executive Intelligence',       path: '/profitability',    match: (p) => p === '/profitability' },
  { label: 'EKE Sales Pro',         domain: 'Pipeline Intelligence (PIS)', path: '/pipeline',         match: (p) => p.startsWith('/pipeline') && !p.startsWith('/pipeline/queues') },
  { label: 'Sales Pro Analytics',   domain: 'Pipeline Intelligence (PIS)', path: '/analytics',        match: (p) => p.startsWith('/analytics') },
  { label: 'Manager Queues',        domain: 'Pipeline Intelligence (PIS)', path: '/pipeline/queues',  match: (p) => p.startsWith('/pipeline/queues') },
  { label: 'Sales Referral',        domain: 'Pipeline Intelligence (PIS)', path: '/referrals',        match: (p) => p.startsWith('/referrals') },
  { label: 'Credit Analysis',       domain: 'Credit Intelligence (CIS)',   path: '/lms',              match: (p) => p.startsWith('/lms') },
  { label: 'Credit Admin',          domain: 'Credit Intelligence (CIS)',   path: '/credit-admin',     match: (p) => p.startsWith('/credit-admin') },
  { label: 'Credit Analytics',      domain: 'Credit Intelligence (CIS)',   path: '/credit-analytics', match: (p) => p.startsWith('/credit-analytics') },
  { label: 'Customer Lookup',       domain: 'Reference & Admin',           path: '/cbs',              match: (p) => p.startsWith('/cbs') },
  { label: 'FX Rates',              domain: 'Reference & Admin',           path: '/fx-rates',         match: (p) => p.startsWith('/fx-rates') },
  { label: 'Role Registry',         domain: 'Reference & Admin',           path: '/admin/roles',      match: (p) => p.startsWith('/admin/roles') },
];

function initials(name?: string) {
  if (!name) return '—';
  return name.trim().split(/\s+/).slice(0, 2).map((s) => s[0]?.toUpperCase() ?? '').join('');
}

const IconSearch = () => (
  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
    <circle cx="11" cy="11" r="8" /><line x1="21" y1="21" x2="16.65" y2="16.65" />
  </svg>
);
const IconBell = () => (
  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
    <path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9" />
    <path d="M13.73 21a2 2 0 0 1-3.46 0" />
  </svg>
);
const IconMenu = () => (
  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
    <line x1="3" y1="6" x2="21" y2="6" /><line x1="3" y1="12" x2="21" y2="12" /><line x1="3" y1="18" x2="21" y2="18" />
  </svg>
);

export function TopBar({ onMenuClick }: { onMenuClick: () => void }) {
  const { pathname } = useLocation();
  const navigate     = useNavigate();
  const { user }     = useRole();
  const [q, setQ]               = useState('');
  const [notifyOpen, setNotify] = useState(false);

  const current = ROUTES.find((r) => r.match(pathname));
  const title  = current?.label  ?? 'EKE MIS 360';
  const domain = current?.domain ?? '';

  const query   = q.trim().toLowerCase();
  const matches = query ? ROUTES.filter((r) => !DEMO_HIDE.has(r.path) && r.label.toLowerCase().includes(query)) : [];
  const go = (path: string) => { setQ(''); navigate(path); };

  return (
    <header className="topbar">
      <button type="button" className="tb-hamburger md:hidden" onClick={onMenuClick} aria-label="Open navigation">
        <IconMenu />
      </button>

      <div className="tb-title-wrap">
        {domain && <div className="tb-eyebrow">{domain}</div>}
        <h1 className="tb-title">{title}</h1>
      </div>

      {/* Search */}
      <div className="tb-search-wrap hidden md:block">
        <div className="tb-search">
          <span className="tb-search-icon"><IconSearch /></span>
          <input
            value={q}
            onChange={(e) => setQ(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && matches[0]) go(matches[0].path);
              if (e.key === 'Escape') setQ('');
            }}
            placeholder="Search modules…"
            aria-label="Search modules"
          />
        </div>
        {matches.length > 0 && (
          <div className="tb-dropdown">
            {matches.slice(0, 6).map((m) => (
              <button key={m.path} type="button" className="tb-dropdown-item" onClick={() => go(m.path)}>
                <span className="tb-dropdown-domain">{m.domain}</span>
                {m.label}
              </button>
            ))}
          </div>
        )}
      </div>

      <div className="tb-actions">
        <div className="tb-notify-wrap">
          <button type="button" className="icon-btn" onClick={() => setNotify((o) => !o)} aria-label="Notifications">
            <IconBell />
          </button>
          {notifyOpen && (
            <div className="tb-notify-panel">
              <div className="tb-notify-title">Notifications</div>
              <div className="tb-notify-empty">You're all caught up.</div>
            </div>
          )}
        </div>

        {user && (
          <div className="tb-avatar" title={user.full_name ?? user.username}>
            {initials(user.full_name)}
          </div>
        )}
      </div>
    </header>
  );
}
