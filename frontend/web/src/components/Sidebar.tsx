import { displayName } from "../lib/names";
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

// A hardcoded hide list already existed and was empty. Rather than add a second
// mechanism beside it, the same filter now also reads `hidden_modules` from
// BRANDING - which comes from org_config.json, a file each deployment owns.
//
// So the pilot hides a module by listing its route in ITS config, and this side
// keeps it, with no divergent code and nothing to remember at release time.
// Keyed on ROUTE, not label: "EKE Sales Pro" and "A2Z Sales Pro" are the same
// module, and a list keyed on the words would stop matching after a rebrand.
const DEMO_HIDE = new Set<string>([]);

const NAV_GROUPS: NavGroup[] = [
  {
    label: 'Executive Intelligence',
    items: [
      { path: '/',              label: 'Dashboard',        matchActive: (p) => p === '/' },
      { path: '/perform',       label: 'Balanced Scorecard', matchActive: (p) => p === '/perform' },
      { path: '/cascade',       label: 'Target Cascade',   matchActive: (p) => p === '/cascade' || p.startsWith('/cascade/'), visibleFor: (_m, _a, _c, md) => md },
      { path: '/initiatives',   label: 'Initiatives',      matchActive: (p) => p === '/initiatives' || p.startsWith('/initiatives/') },
      { path: '/profitability', label: 'Profitability',    matchActive: (p) => p === '/profitability' },
      { path: '/sla',           label: 'SLA Monitor',      matchActive: (p) => p.startsWith('/sla'), visibleFor: (m, a) => m || a },
    ],
  },
  {
    label: 'Pipeline Intelligence (PIS)',
    items: [
      { path: '/pipeline',        label: 'EKE Sales Pro',        matchActive: (p) => p === '/pipeline' || (p.startsWith('/pipeline/') && !p.startsWith('/pipeline/queues') && !p.startsWith('/pipeline/events') && !p.startsWith('/pipeline/channels') && !p.startsWith('/pipeline/warehouse')) },
      { path: '/analytics',       label: 'Sales Pro Analytics',  matchActive: (p) => p.startsWith('/analytics') },
      { path: '/pipeline/queues', label: 'Manager Queues',       matchActive: (p) => p.startsWith('/pipeline/queues'), visibleFor: (m) => m },
      { path: '/pipeline/channels', label: 'Origin Channels',    matchActive: (p) => p.startsWith('/pipeline/channels') || p.startsWith('/pipeline/events') },
      // Standalone, NOT a channel: a shelf with claim mechanics and no budget,
      // so grouping it with the invested channels would imply a return question
      // it cannot answer.
      { path: '/referrals',       label: 'A2Z Sales Referral Analytics', matchActive: (p) => p.startsWith('/referrals') },
      { path: '/branch-log',      label: 'Daily Log',     matchActive: (p) => p.startsWith('/branch-log') },
      { path: '/portfolio',       label: 'Portfolio',            matchActive: (p) => p.startsWith('/portfolio') },
    ],
  },
  {
    // ── DEPARTMENT REVIEW, ITS OWN SECTION (ruling 2026-08-14) ────────────
    // "For the department gate we have a sidebar dedicated to the department
    // which we could name Department Review ... this can also be the place
    // where the head-office team, especially those voting, can get in and see
    // the committee as can also vote, but it be restricted to selected voters
    // only."
    //
    // Credit Analysis is the BANK credit analyst's module - Julius Korir's
    // work. The department analyst and the committee members were borrowing it
    // and seeing a screen built for somebody else's job. They now have their
    // own way in.
    //
    // RESTRICTED TO CREDIT STAFF, which is the same gate Credit Analysis uses.
    // A tighter one - only named committee members - belongs on the SERVER,
    // where it already is: the vote endpoint refuses a non-member with a 403.
    // Hiding a menu entry is not a permission, and treating it as one is how
    // people end up believing a screen is safe because it is hard to find.
    label: 'Department Review',
    items: [
      // NOT FOR CREDIT RISK (ruling 2026-08-18): "I want his sidebar not to
      // have the Department Review, since that one does not really concern
      // them - the CIS is their main workbench."
      //
      // Department Review is the segment analyst's desk. Credit risk arrives
      // after that work is finished, and an entry leading to somebody else's
      // queue is an invitation to duplicate it.
      { path: '/lms',                 label: 'Department Review',   matchActive: (p) => p === '/lms' || p.startsWith('/lms/'), visibleFor: (_m, _a, _c, _md, credit) => credit },
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
      { path: '/admin/config',     label: 'Administration',      matchActive: (p) => (p.startsWith('/admin/') && !p.startsWith('/admin/cbs-debug')) || p.startsWith('/fx-rates'), visibleFor: (_m, _a, _c, md) => md },
      { path: '/admin/cbs-debug', label: 'CBS / FlexCube Debug', matchActive: (p) => p.startsWith('/admin/cbs-debug'), visibleFor: (_m, isA) => isA },
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
  // Absent config hides nothing, so this cannot take a module away from
  // somebody who never asked for it.
  const hidden = new Set<string>(branding?.hidden_modules ?? []);
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
  // Credit risk works at the credit stage, not the department stage.
  const isCreditStaff = isAdminOrMd || /credit|analys|underwrit|recover|collection|treasur|disburs/i.test(user?.role ?? '');

  return (
    <aside className="sidebar">
      <div className="sb-brand">
        <img src="/img/ecobank-light.svg" alt="Ecobank" className="sb-logo" />
        <div className="sb-brand-text">
          <div className="sb-brand-name">{branding?.app_name ?? 'EKE Blueprint'}</div>
          <div className="sb-brand-tag">MIS 360</div>
        </div>
      </div>

      <nav className="sb-nav">
        {NAV_GROUPS.map((group) => {
          const items = group.items.filter(
            (item) => !DEMO_HIDE.has(item.path)
              && !hidden.has(item.path)
              && (!item.visibleFor || item.visibleFor(isMgr, isAdmin, isCfgAdmin, isAdminOrMd, isCreditStaff))
              && !(/credit risk|credit admin|remedial|recover/i.test(user?.role ?? '')
                   && item.label === 'Department Review'),
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
            <div className="sb-user-name">{user?.full_name ? displayName(user.full_name, (user as any).display_name) : (user?.username ?? '—')}</div>
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
        <Link to="/about" onClick={() => onNavigate?.()}
          className="mt-2 block text-center text-[11px] text-white/40 hover:text-white/70">
          © 2026 A2Z · About
        </Link>
      </div>
    </aside>
  );
}
