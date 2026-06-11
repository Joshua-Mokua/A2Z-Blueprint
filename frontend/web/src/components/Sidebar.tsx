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

const NAV_ITEMS: NavItem[] = [
  {
    path:        '/',
    label:       'Dashboard',
    matchActive: (p) => p === '/',
  },
  {
    path:        '/pipeline',
    label:       'Pipeline',
    matchActive: (p) =>
      p === '/pipeline' ||
      (p.startsWith('/pipeline/') && !p.startsWith('/pipeline/queues')),
  },
  {
    path:        '/pipeline/queues',
    label:       'Manager Queues',
    matchActive: (p) => p.startsWith('/pipeline/queues'),
    visibleFor:  (isMgr) => isMgr,
  },
  {
    path:        '/lms',
    label:       'Loan Applications',
    matchActive: (p) => p === '/lms' || p.startsWith('/lms/'),
  },
  {
    path:        '/credit-admin',
    label:       'Credit Admin',
    matchActive: (p) => p === '/credit-admin' || p.startsWith('/credit-admin/'),
  },
  {
    path:        '/perform',
    label:       'BSC Performance',
    matchActive: (p) => p === '/perform',
  },
  {
    path:        '/profitability',
    label:       'Profitability',
    matchActive: (p) => p === '/profitability',
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

  const visibleItems = NAV_ITEMS.filter(
    (item) => !item.visibleFor || item.visibleFor(isMgr, isAdmin),
  );

  return (
    <aside
      className="flex flex-col w-60 min-h-screen text-white shadow-xl"
      style={{ background: 'var(--brand-secondary)' }}
    >
      {/* Top: bank + app branding */}
      <div className="px-5 py-5 border-b border-white/10">
        <div className="text-[10px] uppercase tracking-[2.5px] font-bold opacity-70">
          {branding?.bank_name ?? 'A2Z'}
        </div>
        <div className="text-base font-bold mt-1 leading-tight">
          {branding?.app_name ?? 'A2Z'} MIS 360
        </div>
      </div>

      {/* Nav items */}
      <nav className="flex-1 px-3 py-4 space-y-1 overflow-y-auto">
        {visibleItems.map((item) => {
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
      </nav>

      {/* Bottom: user info + logout */}
      <div className="px-4 py-4 border-t border-white/10 text-sm">
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
