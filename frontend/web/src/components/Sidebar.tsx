// v10.513 Phase 4 Batch β4 — Sidebar nav rail.
//
// The persistent navigation surface mounted by AppShell. Lists all
// modules with the current route highlighted. Manager-only routes
// (Queues) are conditionally rendered based on lib/role.ts::isManager.
//
// Responsive behavior:
//   - Desktop (md+): always visible as a 240px-wide fixed rail on the left
//   - Mobile (< md): hidden by default; toggled via hamburger button in
//     the floating header overlay (rendered by AppShell)
//
// Theming:
//   Background uses var(--brand-secondary) — the navy chrome you see on
//   every page header. White text. Active link gets a subtle highlight
//   from var(--brand-primary).
//
// Active link logic:
//   Each nav item declares its match logic explicitly (exact / prefix).
//   Pipeline matches /pipeline, /pipeline/new, /pipeline/:dealId — but
//   NOT /pipeline/queues (Queues has its own item).

import { Link, useLocation } from 'react-router-dom';
import { useAuth } from '@/hooks/useAuth';
import { useBranding } from '@/hooks/useBranding';
import { useRole } from '@/hooks/useRole';
import { isManager } from '@/lib/role';


// ── Nav item definitions ────────────────────────────────────────────────

interface NavItem {
  path:          string;
  label:         string;
  /** Returns true if this item should be highlighted given the current pathname. */
  matchActive:   (pathname: string) => boolean;
  /** Returns true if this item should be rendered for the current user. */
  visibleFor?:   (isManagerUser: boolean, isAdmin: boolean, isConfigAdmin: boolean) => boolean;
}

interface NavGroup {
  label: string;
  items: NavItem[];
}

// Grouped into business domains so the platform reads as coherent areas
// rather than a flat list. Item order and match logic unchanged.
//
// DEMO_HIDE (2026-06-23): temporarily hide nav items not yet ready to show.
// Flip to an empty Set to restore them. Matched by `path`.
const DEMO_HIDE = new Set<string>(['/', '/initiatives', '/profitability']);
const NAV_GROUPS: NavGroup[] = [
  {
    label: 'Executive Intelligence',
    items: [
      { path: '/', label: 'Dashboard', matchActive: (p) => p === '/' },
      { path: '/perform', label: 'BSC Performance', matchActive: (p) => p === '/perform' },
      { path: '/cascade', label: 'Target Cascade', matchActive: (p) => p === '/cascade' || p.startsWith('/cascade/') },
      { path: '/initiatives', label: 'Initiatives', matchActive: (p) => p === '/initiatives' || p.startsWith('/initiatives/') },
      { path: '/profitability', label: 'Profitability', matchActive: (p) => p === '/profitability' },
      {
        path: '/sla', label: 'SLA Monitor',
        matchActive: (p) => p.startsWith('/sla'),
        visibleFor: (isMgr, isAdmin) => isMgr || isAdmin,
      },
    ],
  },
  {
    label: 'A2Z Pipeline Intelligence System (PIS)',
    items: [
      {
        path: '/pipeline', label: 'A2Z Sales Pro',
        matchActive: (p) => p === '/pipeline' || (p.startsWith('/pipeline/') && !p.startsWith('/pipeline/queues')),
      },
      { path: '/analytics', label: 'A2Z Sales Pro Analytics', matchActive: (p) => p.startsWith('/analytics') },
      {
        path: '/pipeline/queues', label: 'Manager Queues',
        matchActive: (p) => p.startsWith('/pipeline/queues'), visibleFor: (isMgr) => isMgr,
      },
      { path: '/referrals', label: 'A2Z Sales Referral', matchActive: (p) => p.startsWith('/referrals') },
    ],
  },
  {
    label: 'A2Z Credit Intelligence System (CIS)',
    items: [
      { path: '/lms', label: 'Credit Analysis', matchActive: (p) => p === '/lms' || p.startsWith('/lms/') },
      { path: '/committee/convening', label: 'Committee Convening', matchActive: (p) => p.startsWith('/committee/convening') },
      { path: '/credit-admin', label: 'Credit Admin', matchActive: (p) => p === '/credit-admin' || p.startsWith('/credit-admin/') },
      { path: '/troops', label: 'Trops Disbursement', matchActive: (p) => p.startsWith('/troops') },
      { path: '/credit-analytics', label: 'Credit Analytics', matchActive: (p) => p.startsWith('/credit-analytics') },
    ],
  },
  {
    label: 'Reference & Admin',
    items: [
      { path: '/cbs', label: 'Customer Lookup', matchActive: (p) => p === '/cbs' || p.startsWith('/cbs/') },
      {
        path: '/fx-rates', label: 'FX Rates',
        matchActive: (p) => p.startsWith('/fx-rates'), visibleFor: (_isMgr, isAdmin) => isAdmin,
      },
      {
        path: '/admin/config', label: 'Configuration',
        matchActive: (p) => p.startsWith('/admin/config'),
        visibleFor: (_isMgr, _isAdmin, isConfigAdmin) => isConfigAdmin,
      },
      {
        path: '/admin/roles', label: 'Role Registry',
        matchActive: (p) => p.startsWith('/admin/roles'),
      },
      {
        path: '/admin/hierarchy', label: 'Reporting Hierarchy',
        matchActive: (p) => p.startsWith('/admin/hierarchy'),
        visibleFor: (_isMgr, _isAdmin, isConfigAdmin) => isConfigAdmin,
      },
      {
        path: '/admin/committees', label: 'Credit Committees',
        matchActive: (p) => p.startsWith('/admin/committees'),
        visibleFor: (_isMgr, _isAdmin, isConfigAdmin) => isConfigAdmin,
      },
      {
        path: '/admin/staff', label: 'Staff Admin',
        matchActive: (p) => p.startsWith('/admin/staff'),
        visibleFor: (_isMgr, _isAdmin, isConfigAdmin) => isConfigAdmin,
      },
    ],
  },
];


// ── Sidebar component ───────────────────────────────────────────────────

interface SidebarProps {
  /** Tracked by AppShell so the mobile overlay can close after a nav click. */
  onNavigate?: () => void;
}

export function Sidebar({ onNavigate }: SidebarProps) {
  const { pathname } = useLocation();
  const { user } = useRole();
  const { branding } = useBranding();
  const { logout } = useAuth();

  const isMgr   = isManager(user);
  const isAdmin = user?.is_admin ?? false;
  // Config-admin = executive tier (CEO / MD / Director) or system admin. Mirrors
  // the backend require_config_admin substring gate so the CEO/MD see the
  // Configuration link even if they don't carry the is_admin flag.
  const isConfigAdmin = isAdmin
    || ['admin', 'director', 'chief', 'managing']
        .some((t) => (user?.role ?? '').toLowerCase().includes(t));

  return (
    <aside
      className="flex flex-col w-60 h-full text-white shadow-xl"
      style={{ background: 'var(--brand-secondary)' }}
    >
      {/* Top: bank + app branding */}
      <div className="px-5 py-5 border-b border-white/10 flex-shrink-0">
        <div className="text-[10px] uppercase tracking-[2.5px] font-bold opacity-70">
          {branding?.bank_name ?? 'A2Z'}
        </div>
        <div className="text-base font-bold mt-1 leading-tight">
          {branding?.app_name ?? 'A2Z'} MIS 360
        </div>
      </div>

      {/* Grouped nav */}
      <nav className="flex-1 px-3 py-4 overflow-y-auto space-y-5 [&::-webkit-scrollbar]:w-1.5 [&::-webkit-scrollbar-track]:bg-transparent [&::-webkit-scrollbar-thumb]:bg-white/15 [&::-webkit-scrollbar-thumb]:rounded-full">
        {NAV_GROUPS.map((group) => {
          const items = group.items.filter(
            (item) => !DEMO_HIDE.has(item.path)
              && (!item.visibleFor || item.visibleFor(isMgr, isAdmin, isConfigAdmin)),
          );
          if (items.length === 0) return null;
          return (
            <div key={group.label}>
              <div className="px-3 mb-1.5 text-[10px] uppercase tracking-[1.5px] font-bold text-white/40">
                {group.label}
              </div>
              <div className="space-y-0.5">
                {items.map((item) => {
                  const active = item.matchActive(pathname);
                  return (
                    <Link
                      key={item.path}
                      to={item.path}
                      onClick={onNavigate}
                      className={`block px-3 py-2 rounded-md text-sm font-medium transition-colors ${
                        active
                          ? 'bg-white/15 text-white'
                          : 'text-white/75 hover:bg-white/8 hover:text-white'
                      }`}
                      style={active
                        ? { borderLeft: '3px solid var(--brand-primary)', paddingLeft: '13px' }
                        : undefined}
                    >
                      {item.label}
                    </Link>
                  );
                })}
              </div>
            </div>
          );
        })}
      </nav>

      {/* Bottom: user info + logout */}
      <div className="px-4 py-4 border-t border-white/10 text-sm flex-shrink-0">
        {user && (
          <div className="mb-3 flex items-center gap-3">
            <div
              className="flex-shrink-0 h-9 w-9 rounded-full flex items-center justify-center text-sm font-bold text-white"
              style={{ background: 'var(--brand-primary)' }}
              aria-hidden
            >
              {(user.full_name || user.username || '?').trim().charAt(0).toUpperCase()}
            </div>
            <div className="min-w-0">
              <div className="font-semibold text-white truncate">
                {user.full_name}
              </div>
              <div className="text-xs text-white/60 truncate">
                {user.role}
              </div>
              {user.staff_code && (
                <div className="text-[10px] text-white/40 font-mono mt-0.5">
                  {user.staff_code}
                </div>
              )}
            </div>
          </div>
        )}
        <button
          type="button"
          onClick={() => {
            logout();
            if (onNavigate) onNavigate();
          }}
          className="w-full px-3 py-2 rounded-md text-xs font-medium bg-white/8 hover:bg-white/15 text-white/85 hover:text-white transition-colors"
        >
          Sign out
        </button>
      </div>
    </aside>
  );
}
