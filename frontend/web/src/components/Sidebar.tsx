import { Link, useLocation } from 'react-router-dom';
import { useBranding } from '@/hooks/useBranding';
import { useAuth } from '@/hooks/useAuth';
import { useRole } from '@/hooks/useRole';
import { isManager } from '@/lib/role';

interface NavItem {
  path: string;
  label: string;
  matchActive: (pathname: string) => boolean;
  visibleFor?: (isMgr: boolean, isAdmin: boolean, isCfgAdmin: boolean) => boolean;
}
interface NavGroup { label: string; items: NavItem[]; }

const DEMO_HIDE = new Set<string>(['/', '/initiatives', '/profitability']);

const NAV_GROUPS: NavGroup[] = [
  {
    label: 'Executive Intelligence',
    items: [
      { path: '/',              label: 'Dashboard',        matchActive: (p) => p === '/' },
      { path: '/perform',       label: 'BSC Performance',  matchActive: (p) => p === '/perform' },
      { path: '/cascade',       label: 'Target Cascade',   matchActive: (p) => p === '/cascade' || p.startsWith('/cascade/') },
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
      { path: '/lms',                 label: 'Credit Analysis',     matchActive: (p) => p === '/lms' || p.startsWith('/lms/') },
      { path: '/committee/convening', label: 'Committee Convening', matchActive: (p) => p.startsWith('/committee/convening') },
      { path: '/credit-admin',        label: 'Credit Admin',        matchActive: (p) => p === '/credit-admin' || p.startsWith('/credit-admin/') },
      { path: '/troops',              label: 'Trops Disbursement',  matchActive: (p) => p.startsWith('/troops') },
      { path: '/credit-analytics',    label: 'Credit Analytics',    matchActive: (p) => p.startsWith('/credit-analytics') },
    ],
  },
  {
    label: 'Reference & Admin',
    items: [
      { path: '/cbs',              label: 'Customer Lookup',     matchActive: (p) => p === '/cbs' || p.startsWith('/cbs/') },
      { path: '/fx-rates',         label: 'FX Rates',            matchActive: (p) => p.startsWith('/fx-rates'), visibleFor: (_m, a) => a },
      { path: '/admin/config',     label: 'Configuration',       matchActive: (p) => p.startsWith('/admin/config'), visibleFor: (_m, _a, c) => c },
      { path: '/admin/roles',      label: 'Role Registry',       matchActive: (p) => p.startsWith('/admin/roles') },
      { path: '/admin/hierarchy',  label: 'Reporting Hierarchy', matchActive: (p) => p.startsWith('/admin/hierarchy'), visibleFor: (_m, _a, c) => c },
      { path: '/admin/committees', label: 'Credit Committees',   matchActive: (p) => p.startsWith('/admin/committees'), visibleFor: (_m, _a, c) => c },
      { path: '/admin/staff',      label: 'Staff Admin',         matchActive: (p) => p.startsWith('/admin/staff'), visibleFor: (_m, _a, c) => c },
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
            (item) => !DEMO_HIDE.has(item.path) && (!item.visibleFor || item.visibleFor(isMgr, isAdmin, isCfgAdmin)),
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
