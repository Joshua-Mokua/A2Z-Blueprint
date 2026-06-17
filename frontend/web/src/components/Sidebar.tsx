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
  visibleFor?:   (isManagerUser: boolean, isAdmin: boolean) => boolean;
}

interface NavGroup {
  label: string;
  items: NavItem[];
}

// Grouped into business domains so the platform reads as coherent areas
// rather than a flat list. Item order and match logic unchanged.
const NAV_GROUPS: NavGroup[] = [
  {
    label: 'Executive Intelligence',
    items: [
      { path: '/', label: 'Dashboard', matchActive: (p) => p === '/' },
      { path: '/perform', label: 'BSC Performance', matchActive: (p) => p === '/perform' },
      { path: '/cascade', label: 'Target Cascade', matchActive: (p) => p === '/cascade' || p.startsWith('/cascade/') },
      { path: '/initiatives', label: 'Initiatives', matchActive: (p) => p === '/initiatives' || p.startsWith('/initiatives/') },
      { path: '/profitability', label: 'Profitability', matchActive: (p) => p === '/profitability' },
    ],
  },
  {
    label: 'Business Development',
    items: [
      {
        path: '/pipeline', label: 'Pipeline',
        matchActive: (p) => p === '/pipeline' || (p.startsWith('/pipeline/') && !p.startsWith('/pipeline/queues')),
      },
      { path: '/analytics', label: 'Pipeline Analytics', matchActive: (p) => p.startsWith('/analytics') },
      {
        path: '/pipeline/queues', label: 'Manager Queues',
        matchActive: (p) => p.startsWith('/pipeline/queues'), visibleFor: (isMgr) => isMgr,
      },
    ],
  },
  {
    label: 'Credit Factory',
    items: [
      { path: '/lms', label: 'Loan Applications', matchActive: (p) => p === '/lms' || p.startsWith('/lms/') },
      { path: '/credit-admin', label: 'Credit Admin', matchActive: (p) => p === '/credit-admin' || p.startsWith('/credit-admin/') },
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
            (item) => !item.visibleFor || item.visibleFor(isMgr, isAdmin),
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
          <div className="mb-3">
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
