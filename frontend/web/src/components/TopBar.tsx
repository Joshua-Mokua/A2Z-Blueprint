// Fixed application top bar — Ecobank navy, matching the sidebar so the two form
// one brand frame around the light content. Title-forward (domain eyebrow + page
// title, Streamlit-style); search is a compact utility on the right. A soft
// shadow lets content visibly scroll underneath. Presentation only.

import { useState } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { useRole } from '@/hooks/useRole';

interface RouteEntry { label: string; domain: string; path: string; match: (p: string) => boolean }

// DEMO_HIDE (2026-06-23): keep these out of the command-search jump so the demo
// can't navigate to pages we're temporarily hiding from the sidebar. Mirrors
// Sidebar's DEMO_HIDE. Flip to an empty Set to restore.
const DEMO_HIDE = new Set<string>(['/', '/initiatives', '/profitability']);

const ROUTES: RouteEntry[] = [
  { label: 'Dashboard',           domain: 'Executive Intelligence', path: '/',                 match: (p) => p === '/' },
  { label: 'BSC Performance',     domain: 'Executive Intelligence', path: '/perform',          match: (p) => p === '/perform' },
  { label: 'Target Cascade',      domain: 'Executive Intelligence', path: '/cascade',          match: (p) => p.startsWith('/cascade') },
  { label: 'Strategic Initiatives', domain: 'Executive Intelligence', path: '/initiatives',    match: (p) => p.startsWith('/initiatives') },
  { label: 'Profitability',       domain: 'Executive Intelligence', path: '/profitability',    match: (p) => p === '/profitability' },
  { label: 'A2Z Sales Pro',       domain: 'A2Z Pipeline Intelligence System (PIS)',    path: '/pipeline',         match: (p) => p.startsWith('/pipeline') && !p.startsWith('/pipeline/queues') },
  { label: 'A2Z Sales Pro Analytics', domain: 'A2Z Pipeline Intelligence System (PIS)', path: '/analytics',        match: (p) => p.startsWith('/analytics') },
  { label: 'Manager Queues',      domain: 'A2Z Pipeline Intelligence System (PIS)',    path: '/pipeline/queues',  match: (p) => p.startsWith('/pipeline/queues') },
  { label: 'A2Z Sales Referral',  domain: 'A2Z Pipeline Intelligence System (PIS)',    path: '/referrals',        match: (p) => p.startsWith('/referrals') },
  { label: 'Credit Analysis',       domain: 'A2Z Credit Intelligence System (CIS)',         path: '/lms',              match: (p) => p.startsWith('/lms') },
  { label: 'Credit Admin',        domain: 'A2Z Credit Intelligence System (CIS)',         path: '/credit-admin',     match: (p) => p.startsWith('/credit-admin') },
  { label: 'Credit Analytics',    domain: 'A2Z Credit Intelligence System (CIS)',         path: '/credit-analytics', match: (p) => p.startsWith('/credit-analytics') },
  { label: 'Customer Lookup',     domain: 'Reference & Admin',      path: '/cbs',              match: (p) => p.startsWith('/cbs') },
  { label: 'FX Rates',            domain: 'Reference & Admin',      path: '/fx-rates',         match: (p) => p.startsWith('/fx-rates') },
  { label: 'Role Registry',       domain: 'Reference & Admin',      path: '/admin/roles',      match: (p) => p.startsWith('/admin/roles') },
];

function routeFor(pathname: string): RouteEntry | undefined {
  return ROUTES.find((r) => r.match(pathname));
}

function initials(name?: string): string {
  if (!name) return '—';
  return name.trim().split(/\s+/).slice(0, 2).map((s) => s[0]?.toUpperCase() ?? '').join('');
}

export function TopBar({ onMenuClick }: { onMenuClick: () => void }) {
  const { pathname } = useLocation();
  const navigate = useNavigate();
  const { user } = useRole();
  const [q, setQ] = useState('');
  const [notifyOpen, setNotifyOpen] = useState(false);

  const current = routeFor(pathname);
  const title = current?.label ?? 'A2Z MIS 360';
  const domain = current?.domain ?? '';

  const query = q.trim().toLowerCase();
  const matches = query ? ROUTES.filter((r) => !DEMO_HIDE.has(r.path) && r.label.toLowerCase().includes(query)) : [];
  const go = (path: string) => { setQ(''); navigate(path); };

  return (
    <header
      className="flex-shrink-0 h-16 flex items-center gap-3 px-5 text-white shadow-md border-b border-white/10 relative z-20"
      style={{ background: 'var(--brand-secondary, #0e2440)' }}
    >
      <button
        type="button"
        onClick={onMenuClick}
        aria-label="Open navigation"
        className="md:hidden w-9 h-9 rounded-md hover:bg-white/10 flex items-center justify-center text-white/80"
      >
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
          <line x1="3" y1="6" x2="21" y2="6" /><line x1="3" y1="12" x2="21" y2="12" /><line x1="3" y1="18" x2="21" y2="18" />
        </svg>
      </button>

      {/* Title is the hero of the bar */}
      <div className="min-w-0">
        {domain && (
          <div className="text-[10px] uppercase tracking-[1.6px] font-bold text-sky-300 leading-none">
            {domain}
          </div>
        )}
        <h1 className="text-lg font-bold text-white leading-tight mt-1 truncate">{title}</h1>
      </div>

      <div className="flex-1" />

      {/* Compact utility search */}
      <div className="relative w-56 hidden md:block">
        <span className="absolute left-3 top-1/2 -translate-y-1/2 text-white/50">
          <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <circle cx="11" cy="11" r="8" /><line x1="21" y1="21" x2="16.65" y2="16.65" />
          </svg>
        </span>
        <input
          value={q}
          onChange={(e) => setQ(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter' && matches[0]) go(matches[0].path);
            if (e.key === 'Escape') setQ('');
          }}
          placeholder="Search…"
          aria-label="Search modules"
          className="w-full h-9 rounded-md bg-white/10 border border-white/20 pl-9 pr-3 text-sm text-white placeholder:text-white/50 focus:bg-white/15 focus:border-white/40 outline-none transition-colors"
        />
        {matches.length > 0 && (
          <div className="absolute z-50 mt-1 w-full bg-white border border-gray-200 rounded-md shadow-lg overflow-hidden">
            {matches.slice(0, 6).map((m) => (
              <button
                key={m.path}
                onClick={() => go(m.path)}
                className="block w-full text-left px-3 py-2 text-sm text-gray-700 hover:bg-gray-50"
              >
                <span className="text-[10px] uppercase tracking-wider text-gray-400 block leading-none">{m.domain}</span>
                {m.label}
              </button>
            ))}
          </div>
        )}
      </div>

      {/* Notifications */}
      <div className="relative">
        <button
          type="button"
          onClick={() => setNotifyOpen((o) => !o)}
          aria-label="Notifications"
          className="w-9 h-9 rounded-md hover:bg-white/10 flex items-center justify-center text-white/70"
        >
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9" /><path d="M13.73 21a2 2 0 0 1-3.46 0" />
          </svg>
        </button>
        {notifyOpen && (
          <div className="absolute right-0 z-50 mt-1 w-64 bg-white border border-gray-200 rounded-md shadow-lg p-4 text-left">
            <div className="text-sm font-semibold text-gray-900">Notifications</div>
            <div className="text-xs text-gray-500 mt-1">You're all caught up.</div>
          </div>
        )}
      </div>

      {/* Canonical user chip */}
      {user && (
        <div className="flex items-center gap-2 pl-3 ml-1 border-l border-white/15">
          <div
            className="w-9 h-9 rounded-full flex items-center justify-center text-xs font-bold text-white ring-2 ring-white/20"
            style={{ background: 'var(--brand-primary, #1797ce)' }}
          >
            {initials(user.full_name)}
          </div>
          <div className="hidden lg:block leading-tight">
            <div className="text-xs font-semibold text-white truncate max-w-[160px]">{user.full_name}</div>
            <div className="text-[10px] text-white/60 truncate max-w-[160px]">{user.role}</div>
          </div>
        </div>
      )}
    </header>
  );
}
