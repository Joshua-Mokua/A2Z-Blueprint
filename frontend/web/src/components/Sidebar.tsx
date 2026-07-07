import { Link, useLocation } from 'react-router-dom';
import { useBranding } from '@/hooks/useBranding';
import { useAuth } from '@/hooks/useAuth';
import { useRole } from '@/hooks/useRole';
import { isManager } from '@/lib/role';

interface NavItem {
  path: string;
  label: string;
  matchActive: (pathname: string) => boolean;
  visibleFor?: (isMgr: boolean, isAdmin: boolean, isCfgAdmin: boolean, isAdminOrMd: boolean, isCreditStaff: boolean) => boolean;
}
interface NavGroup { label: string; items: NavItem[]; }

const DEMO_HIDE = new Set<string>(['/', '/initiatives', '/profitability']);

const NAV_GROUPS: NavGroup[] = [
  {
    label: 'Executive Intelligence',
    items: [
      { path: '/',              label: 'Dashboard',        matchActive: (p) => p === '/' },
      { path: '/perform',       label: 'BSC Performance',  matchActive: (p) => p === '/perform' },
      { path: '/cascade',       label: 'Target Cascade',   matchActive: (p) => p === '/cascade' || p.startsWith('/cascade/'), visibleFor: (_m, _a, _c, md) => md },
      { path: '/initiatives',   label: 'Initiatives',      matchActive: (p) => p === '/initiatives' || p.startsWith('/initiatives/') },
      { path: '/profitability', label: 'Profitability',    matchActive: (p) => p === '/profitability' },
      { path: '/sla',           label: 'SLA Monitor',      matchActive: (p) => p.startsWith('/sla'), visibleFor: (m, a) => m || a },
    ],
  },
  {
    label: 'Pipeline Intelligence (PIS)',
    items: [
      { path: '/pipeline',        label: 'A2Z Sales Pro',        matchActive: (p) => p === '/pipeline' || (p.startsWith('/pipeline/') && !p.startsWith('/pipeline/queues')) },
      { path: '/analytics',       label: 'Sales Pro Analytics',  matchActive: (p) => p.startsWith('/analytics') },
      { path: '/pipeline/queues', label: 'Manager Queues',       matchActive: (p) => p.startsWith('/pipeline/queues'), visibleFor: (m) => m },
      { path: '/referrals',       label: 'Sales Referral',       matchActive: (p) => p.startsWith('/referrals') },
      { path: '/branch-log',      label: 'Daily Branch Log',     matchActive: (p) => p.startsWith('/branch-log') },
    ],
  },
  {
    label: 'Credit Intelligence (CIS)',
    items: [
      { path: '/lms',                 label: 'Credit Analysis',     matchActive: (p) => p === '/lms' || p.startsWith('/lms/'), visibleFor: (_m, _a, _c, _md, credit) => credit },
      { path: '/committee/convening', label: 'Committee Convening', matchActive: (p) => p.startsWith('/committee/convening'), visibleFor: (_m, _a, _c, md) => md },
      { path: '/credit-admin',        label: 'Credit Admin',        matchActive: (p) => p === '/credit-admin' || p.startsWith('/credit-admin/'), visibleFor: (_m, _a, _c, _md, credit) => credit },
      { path: '/troops',              label: 'Trops Disbursement',  matchActive: (p) => p.startsWith('/troops'), visibleFor: (_m, _a, _c, _md, credit) => credit },
      { path: '/credit-analytics',    label: 'Credit Analytics',    matchActive: (p) => p.startsWith('/credit-analytics'), visibleFor: (_m, _a, _c, _md, credit) => credit },
    ],
  },
  {
    label: 'Reference & Admin',
    items: [
      { path: '/cbs',              label: 'Customer Lookup',     matchActive: (p) => p === '/cbs' || p.startsWith('/cbs/'), visibleFor: (_m, _a, _c, md) => md },
      { path: '/fx-rates',         label: 'FX Rates',            matchActive: (p) => p.startsWith('/fx-rates'), visibleFor: (_m, _a, _c, md) => md },
      { path: '/admin/config',     label: 'Configuration',       matchActive: (p) => p.startsWith('/admin/config'), visibleFor: (_m, _a, _c, md) => md },
      { path: '/admin/roles',      label: 'Role Registry',       matchActive: (p) => p.startsWith('/admin/roles'), visibleFor: (_m, _a, _c, md) => md },
      { path: '/admin/hierarchy',  label: 'Reporting Hierarchy', matchActive: (p) => p.startsWith('/admin/hierarchy'), visibleFor: (_m, _a, _c, md) => md },
      { path: '/admin/committees', label: 'Credit Committees',   matchActive: (p) => p.startsWith('/admin/committees'), visibleFor: (_m, _a, _c, md) => md },
      { path: '/admin/staff',      label: 'Staff Admin',         matchActive: (p) => p.startsWith('/admin/staff'), visibleFor: (_m, _a, _c, md) => md },
    ],
  },
];

function initials(name?: string) {
  return (name ?? '?').trim().split(/\s+/).slice(0, 2).map((s) => s[0]?.toUpperCase() ?? '').join('');
}

interface SidebarProps { onNavigate?: () => void; }

export function Sidebar({ onNavigate }: SidebarProps) {
  const { pathname } = useLocation();
  const { branding } = useBranding();
  const { user } = useRole();
  const { logout } = useAuth();

  const isMgr      = isManager(user);
  const isAdmin    = user?.is_admin ?? false;
  const isCfgAdmin = isAdmin || ['admin', 'director', 'chief', 'managing'].some((t) => (user?.role ?? '').toLowerCase().includes(t));
  // First-rollout gate: admin or the MD/CEO only.
  const isAdminOrMd = isAdmin || ['managing director', 'chief executive'].some((t) => (user?.role ?? '').toLowerCase().includes(t));
  // Credit Intelligence modules belong to credit staff (analysts, credit admin,
  // treasury/disbursement, recovery) + admin/MD. Front-line RMs/branch see the
  // pipeline instead, and track their own cases there.
  const isCreditStaff = isAdminOrMd || /credit|analys|underwrit|recover|collection|treasur|disburs/i.test(user?.role ?? '');

  return (
    <aside className="sidebar">
      <div className="sb-brand">
        <img src="/img/ecobank-light.svg" alt="Ecobank" className="sb-logo" />
        <div className="sb-brand-text">
          <div className="sb-brand-name">{branding?.app_name ?? 'A2Z Blueprint'}</div>
          <div className="sb-brand-tag">MIS 360</div>
        </div>
      </div>

      <nav className="sb-nav">
        {NAV_GROUPS.map((group) => {
          const items = group.items.filter(
            (item) => !DEMO_HIDE.has(item.path) && (!item.visibleFor || item.visibleFor(isMgr, isAdmin, isCfgAdmin, isAdminOrMd, isCreditStaff)),
          );
          if (!items.length) return null;
          return (
            <div key={group.label}>
              <div className="sb-section-lbl">{group.label}</div>
              {items.map((item) => {
                const active = item.matchActive(pathname);
                return (
                  <Link
                    key={item.path}
                    to={item.path}
                    onClick={onNavigate}
                    className={`sb-item${active ? ' active' : ''}`}
                  >
                    {item.label}
                  </Link>
                );
              })}
            </div>
          );
        })}
      </nav>

      <div className="sb-foot">
        <div className="sb-user">
          <div className="sb-av">{initials(user?.full_name ?? user?.username)}</div>
          <div className="sb-user-info">
            <div className="sb-user-name">{user?.full_name ?? user?.username ?? '—'}</div>
            <div className="sb-user-role">{user?.role ?? ''}</div>
          </div>
        </div>
        <button
          type="button"
          className="sb-logout"
          onClick={() => { logout(); onNavigate?.(); }}
        >
          Sign out
        </button>
      </div>
    </aside>
  );
}
