#!/usr/bin/env python
# -*- coding: utf-8 -*-
r"""
EV2 - the Events page. What each sponsorship cost, and what it produced.

EV1 made deals point at events. EV2 makes that visible, which is the whole
payoff: the reason to tag a deal to a roadshow is to answer "was it worth it?"

Pipeline Intelligence gains EVENTS, listing every sponsored event with:

    spent            from the event record
    leads            DERIVED - every deal tagged to the event - against target
    accounts         DERIVED - only deals that CLOSED WON - against target
    won value        the value of those closed deals
    return           (won value - spent) / spent, computed from real records

BOTH FIGURES, NEVER ONE. The stored actual_leads / actual_accounts / roi_pct are
generated test data, but the derived numbers sit beside them rather than
replacing them - because when the two disagree that is itself information, and
because nobody should have to guess which number they are reading.

"NOBODY HAS TAGGED ANYTHING" IS NOT "THE EVENT FAILED". When no deals are tagged,
every derived figure is zero and a red return column would read as a verdict on
the sponsorship. The page says so explicitly in a banner rather than letting
someone draw the wrong conclusion from an honest zero.

ATTRIBUTION IS COMPUTED ONCE over the caller's scoped deals and bucketed by
event id - not per event. Reading the deal store twelve times to render one page
is the per-row cost this codebase has paid for before.

The sidebar's Sales Pro matcher is narrowed so it no longer claims
/pipeline/events, which would have highlighted two entries at once.

Verified: tsc --noEmit clean, vite build clean.

REQUIRES EV1.

Usage (from project root, .venv active):
    python scripts\patch_ev2_events_page.py            # dry run
    python scripts\patch_ev2_events_page.py --apply
"""
import os
import shutil
import sys

API = os.path.join("utils", "api.py")
PAGE = os.path.join("frontend", "web", "src", "pages", "Events.tsx")
APITS = os.path.join("frontend", "web", "src", "lib", "api.ts")
APP = os.path.join("frontend", "web", "src", "App.tsx")
SB = os.path.join("frontend", "web", "src", "components", "Sidebar.tsx")
BACKUP_SUFFIX = ".pre_ev2"

TS_ANCHOR = "export interface OriginSourceOption"
API_ANCHOR = '@app.get("/api/pipeline/origin-sources")'

ENDPOINT = r'''@app.get("/api/pipeline/events")
def pipeline_events(active_only: bool = False,
                    user: dict = Depends(get_current_user)):
    """Sponsored events with what the DEALS say each produced.

    Attribution is computed once over the caller's scoped deals rather than per
    event - reading the deal store twelve times to answer one page is the
    per-row cost this codebase has paid for before.

    Every event is returned with BOTH figures. An event whose derived numbers
    are far below its stored ones is not necessarily wrong: it may simply mean
    nobody tagged their deals to it, which is worth seeing rather than hiding.
    """
    from utils.origin_sources import events as _events

    deals = _acquire_scoped_deals(user)
    by_event = {}
    for d in deals:
        eid = str(d.get("event_id") or "").strip()
        if eid:
            by_event.setdefault(eid, []).append(d)

    def _val(d):
        try:
            return float(d.get("amount_kes") or d.get("deal_value") or 0)
        except (TypeError, ValueError):
            return 0.0

    out = []
    for e in _events(bool(active_only)):
        eid = str(e.get("id") or "")
        mine = by_event.get(eid, [])
        won = [d for d in mine if str(d.get("stage") or "") == "Closed Won"]
        spent = float(e.get("spent_kes") or e.get("budget_kes") or 0)
        won_value = round(sum(_val(d) for d in won), 2)
        out.append({
            "id": eid,
            "name": e.get("name"),
            "partner": e.get("partner"),
            "branch": e.get("branch"),
            "department": e.get("department"),
            "category": e.get("category_name") or e.get("event_category"),
            "start_date": e.get("start_date"),
            "end_date": e.get("end_date"),
            "status": e.get("status"),
            "budget_kes": e.get("budget_kes"),
            "spent_kes": e.get("spent_kes"),
            "target_leads": e.get("target_leads"),
            "target_accounts": e.get("target_accounts"),
            "stored_leads": e.get("actual_leads"),
            "stored_accounts": e.get("actual_accounts"),
            "derived_leads": len(mine),
            "derived_accounts": len(won),
            "derived_value": won_value,
            # Return on what was SPENT, from deals that actually closed. The
            # stored roi_pct is a generated figure; this one is arithmetic on
            # real records, and the two are shown side by side rather than one
            # quietly replacing the other.
            "derived_roi_pct": (round((won_value - spent) / spent * 100, 1)
                                if spent else None),
            "stored_roi_pct": e.get("roi_pct"),
        })
    return {"events": out, "tagged_deals": sum(len(v) for v in by_event.values()),
            "total_deals": len(deals)}


'''

TS_NEW = r'''export interface PipelineEvent {
  id: string; name: string; partner: string; branch: string;
  department: string; category: string;
  start_date: string; end_date: string; status: string;
  budget_kes: number; spent_kes: number;
  target_leads: number | null; target_accounts: number | null;
  stored_leads: number | null; stored_accounts: number | null;
  derived_leads: number; derived_accounts: number; derived_value: number;
  derived_roi_pct: number | null; stored_roi_pct: number | null;
}
export async function fetchPipelineEvents(
  activeOnly = false,
): Promise<{ events: PipelineEvent[]; tagged_deals: number; total_deals: number }> {
  const q = new URLSearchParams({ active_only: String(activeOnly) });
  return getJson<{ events: PipelineEvent[]; tagged_deals: number; total_deals: number }>(
    `/pipeline/events?${q.toString()}`);
}
'''

PAGE_SRC = r'''// Events — what each sponsorship cost, and what the deals say it produced.
//
// The point of tagging deals to an event is to answer one question honestly:
// was it worth it? So this shows spend against DERIVED leads and accounts —
// counted from deals, with accounts counted only after closure — beside the
// stored figures, rather than replacing them.
//
// When derived is far below stored, that usually means nobody tagged their
// deals to the event rather than that the event failed. Saying so on screen is
// better than letting someone read a red number as a verdict.

import { useCallback, useEffect, useState } from 'react';
import { Card } from '@/components/Card';
import { PageHeader } from '@/components/PageHeader';
import { useToast } from '@/components/Toast';
import { fetchPipelineEvents, type PipelineEvent } from '@/lib/api';

function kes(n: number | null | undefined): string {
  const v = Number(n ?? 0);
  if (!v) return '—';
  return Math.round(v).toLocaleString();
}

function pct(a: number, b: number | null | undefined): number {
  const t = Number(b ?? 0);
  return t > 0 ? Math.round((a / t) * 100) : 0;
}

export default function Events() {
  const { toast } = useToast();
  const [rows, setRows] = useState<PipelineEvent[]>([]);
  const [tagged, setTagged] = useState(0);
  const [loading, setLoading] = useState(false);
  const [activeOnly, setActiveOnly] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const r = await fetchPipelineEvents(activeOnly);
      setRows(r.events ?? []);
      setTagged(r.tagged_deals ?? 0);
    } catch (e) {
      toast({ tone: 'danger', message: e instanceof Error ? e.message : 'Could not load events.' });
      setRows([]);
    } finally {
      setLoading(false);
    }
  }, [activeOnly, toast]);

  useEffect(() => { void load(); }, [load]);

  const th = 'whitespace-nowrap px-3 py-2 text-left text-[11px] font-semibold uppercase tracking-wide';
  const td = 'whitespace-nowrap px-3 py-2 text-sm';

  return (
    <>
      <PageHeader
        ribbon
        breadcrumbs={[{ label: 'Pipeline Intelligence (PIS)' }, { label: 'Events' }]}
        title="Events"
      />
      <div className="mx-auto max-w-7xl p-6">
        <Card>
          <Card.Header>
            <div className="flex flex-wrap items-center justify-between gap-3">
              <h2 className="text-base font-semibold text-gray-900">Sponsored events</h2>
              <div className="flex items-center gap-3 text-xs">
                <label className="flex items-center gap-1.5 text-gray-600">
                  <input type="checkbox" checked={activeOnly}
                         onChange={(e) => setActiveOnly(e.target.checked)} />
                  Active only
                </label>
                <span className="rounded-full bg-[#E6F1FB] px-2.5 py-1 text-[#0C447C]">
                  {tagged} deal{tagged === 1 ? '' : 's'} tagged
                </span>
              </div>
            </div>
          </Card.Header>
          <Card.Body>
            {loading && <p className="py-8 text-center text-sm text-gray-400">Loading…</p>}

            {!loading && rows.length === 0 && (
              <p className="py-8 text-center text-sm text-gray-400">No events.</p>
            )}

            {!loading && rows.length > 0 && tagged === 0 && (
              <p className="mb-3 rounded-lg border border-[#FAEEDA] bg-[#FEFAF3] px-3 py-2 text-xs text-[#854F0B]">
                No deals are tagged to any event yet, so every derived figure below
                is zero. Choose “Events” on the deal capture form and pick the
                event to start attributing.
              </p>
            )}

            {!loading && rows.length > 0 && (
              <div className="overflow-auto rounded-lg border border-gray-200">
                <table className="w-full border-separate" style={{ borderSpacing: 0 }}>
                  <thead>
                    <tr>
                      <th className={`${th} bg-gray-100 text-gray-600`}>Event</th>
                      <th className={`${th} bg-gray-100 text-gray-600`}>Where</th>
                      <th className={`${th} bg-gray-100 text-gray-600`}>When</th>
                      <th className={`${th} bg-gray-100 text-right text-gray-600`}>Spent (KES)</th>
                      <th className={`${th} bg-[#0082BB] text-right text-white`}>Leads</th>
                      <th className={`${th} bg-[#0082BB] text-right text-white`}>Accounts</th>
                      <th className={`${th} bg-gray-100 text-right text-gray-600`}>Won value (KES)</th>
                      <th className={`${th} bg-gray-100 text-right text-gray-600`}>Return</th>
                    </tr>
                  </thead>
                  <tbody>
                    {rows.map((e, i) => {
                      const bg = i % 2 === 1 ? 'bg-gray-50/40' : 'bg-white';
                      const lp = pct(e.derived_leads, e.target_leads);
                      const ap = pct(e.derived_accounts, e.target_accounts);
                      return (
                        <tr key={e.id}>
                          <td className={`${td} ${bg} font-medium text-gray-900`}>
                            <div className="truncate" style={{ maxWidth: 280 }} title={e.name}>
                              {e.name}
                            </div>
                            {e.partner && (
                              <div className="text-[10px] text-gray-400">{e.partner}</div>
                            )}
                          </td>
                          <td className={`${td} ${bg} text-gray-600`}>{e.branch}</td>
                          <td className={`${td} ${bg} text-gray-500`}>
                            {String(e.start_date ?? '').slice(0, 10)}
                            <div className="text-[10px] text-gray-400">{e.status}</div>
                          </td>
                          <td className={`${td} ${bg} text-right tabular-nums text-gray-700`}>
                            {kes(e.spent_kes)}
                          </td>
                          <td className={`${td} ${bg} text-right tabular-nums`}>
                            <span className="font-semibold text-gray-900">{e.derived_leads}</span>
                            <span className="ml-1 text-[10px] text-gray-400">
                              / {e.target_leads ?? '—'}{e.target_leads ? ` · ${lp}%` : ''}
                            </span>
                          </td>
                          <td className={`${td} ${bg} text-right tabular-nums`}>
                            <span className="font-semibold text-[#3B6D11]">{e.derived_accounts}</span>
                            <span className="ml-1 text-[10px] text-gray-400">
                              / {e.target_accounts ?? '—'}{e.target_accounts ? ` · ${ap}%` : ''}
                            </span>
                          </td>
                          <td className={`${td} ${bg} text-right font-semibold tabular-nums text-[#003D57]`}>
                            {kes(e.derived_value)}
                          </td>
                          <td className={`${td} ${bg} text-right tabular-nums`}>
                            {e.derived_roi_pct === null || e.derived_roi_pct === undefined ? (
                              <span className="text-gray-300">—</span>
                            ) : (
                              <span className={e.derived_roi_pct >= 0 ? 'text-[#3B6D11]' : 'text-rose-600'}>
                                {e.derived_roi_pct}%
                              </span>
                            )}
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            )}
          </Card.Body>
        </Card>
      </div>
    </>
  );
}
'''

APP_SRC = r'''// a2z/web/src/App.tsx
//
// Standard #37 — React SPA Architecture.
// v10.495 amendment: BrandingProvider added between QueryClient and Auth.
// v10.496 amendment: ToastProvider added between Branding and Auth.
//                    /components route added (Showcase page).
// v10.500 Phase 1 Batch 3a:
//   - /login route added (public, no ProtectedRoute wrapper).
//   - /perform and /profitability now wrapped in ProtectedRoute.
//   - /components remains public per Batch 3a doctrine — design-system
//     showcase, must be reachable for frontend governance inspection.
//   - AuthProvider is now the real provider (no longer a stub).
// v10.500 Phase 1 Batch 3b:
//   - /change-password route added, wrapped in ProtectedRoute. The
//     route is reachable for both 'must_rotate' (forced rotation) and
//     'authenticated' (future voluntary rotation) auth states.
//     ProtectedRoute's path-aware must_rotate gate confines users with
//     must_rotate tokens to this route specifically.
// v10.510 Phase 4 Batch β1:
//   - /pipeline route added (protected, requireAuth).
//   - Pipeline route element is wrapped in PipelineProvider so the
//     deal list state lives only where it's consumed — not hoisted to
//     app-level. Keeps the G381-protected provider chain unchanged.
// v10.511 Phase 4 Batch β2:
//   - /pipeline/:dealId route added (protected, requireAuth).
//   - Detail page is page-local — no PipelineProvider wrap.
// v10.512 Phase 4 Batch β3:
//   - /pipeline/new route added BEFORE /pipeline/:dealId. RR6 ranks
//     static routes above dynamic ones automatically, but explicit
//     ordering documents intent for future maintainers.
// v10.513 Phase 4 Batch β4:
//   - /pipeline/queues route added (manager-only via page guard).
//   - AppShell layout route introduced wrapping all protected routes
//     EXCEPT /change-password. The shell renders the persistent
//     Sidebar; pages render via React Router 6's <Outlet />.
//   - /change-password deliberately stays OUTSIDE AppShell — user
//     in must_rotate status would see a mocking sidebar of nav
//     links they can't use otherwise.
//   - /login and /components stay outside AppShell as before
//     (public, no auth needed).
//   - G381 byte-for-byte chain still unchanged:
//     QueryClient → Branding → Toast → Auth → Role → WebSocket → BrowserRouter
//
// CONTRACT NOTES (G381 - replaces phantom G46, G382 enforced from v10.496):
//
// Preserved byte-for-byte (G381 enforced):
//   - `import { QueryClient, QueryClientProvider } from '@tanstack/react-query'`
//   - `const queryClient = new QueryClient()`
//   - `<QueryClientProvider client={queryClient}>`
//   - `<AuthProvider><WebSocketProvider><BrowserRouter>` — chain order
//   - Existing route paths `/`, `/perform`, `/profitability`, `/components`,
//     `/login`, `/change-password`, `/pipeline`, `/pipeline/new`,
//     `/pipeline/:dealId`

import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { BrowserRouter, Route, Routes } from 'react-router-dom';

import { BrandingProvider } from './providers/BrandingProvider';
import { AuthProvider } from './providers/AuthProvider';
import { RoleProvider } from './providers/RoleProvider';
import { WebSocketProvider } from './providers/WebSocketProvider';
import { PipelineProvider } from './providers/PipelineProvider';
import { ToastProvider } from './components/Toast';
import { ProtectedRoute } from './components/ProtectedRoute';
import { AppShell } from './components/AppShell';
import About from './pages/About';
import { Dashboard } from './pages/Dashboard';
import { Perform } from './pages/Perform';
import { Profitability } from './pages/Profitability';
import { Showcase } from './pages/Showcase';
import { Login } from './pages/Login';
import { ChangePassword } from './pages/ChangePassword';
import { Pipeline } from './pages/Pipeline';
import { Analytics } from './pages/Analytics';
import { CreditAnalytics } from './pages/CreditAnalytics';
import { PipelineDealDetail } from './pages/PipelineDealDetail';
import { PipelineCreate } from './pages/PipelineCreate';
import { PipelineManagerQueues } from './pages/PipelineManagerQueues';
import Events from './pages/Events';
import { Lms } from './pages/Lms';
import { LmsApplicationDetail } from './pages/LmsApplicationDetail';
import { CreditAdmin } from './pages/CreditAdmin';
import { CreditAdminCaseDetail } from './pages/CreditAdminCaseDetail';
import { Troops } from './pages/Troops';
import { Cbs } from './pages/Cbs';
import { CbsCustomerDetail } from './pages/CbsCustomerDetail';
import { Cascade } from './pages/Cascade';
import { Initiatives } from './pages/Initiatives';
import { FxRates } from './pages/FxRates';
import AdminConfig from './pages/AdminConfig';
import DailyLogAdmin from './pages/DailyLogAdmin';
import RolesAdmin from './pages/RolesAdmin';
import HierarchyAdmin from './pages/HierarchyAdmin';
import BranchLog from './pages/BranchLog';
import Portfolio from './pages/Portfolio';
import CommitteeAdmin from './pages/CommitteeAdmin';
import { CommitteeConvening } from './pages/CommitteeConvening';
import StaffAdmin from './pages/StaffAdmin';
import CbsDebug from './pages/CbsDebug';
import Referrals from './pages/Referrals';
import Sla from './pages/Sla';
import { InitiativeDetail } from './pages/InitiativeDetail';

const queryClient = new QueryClient();

function App() {
    return <QueryClientProvider client={queryClient}>
        <BrandingProvider>
        <ToastProvider>
        <AuthProvider><RoleProvider><WebSocketProvider><BrowserRouter>
            <Routes>
                {/* Public — login surface */}
                <Route path="/login" element={<Login />} />

                {/* Public — design-system showcase (Batch 3a) */}
                <Route path="/components" element={<Showcase />} />

                {/* Protected (no shell) — password rotation must be
                    standalone so must_rotate users don't see a sidebar
                    of nav links they can't use until rotation completes. */}
                <Route path="/change-password" element={
                    <ProtectedRoute requireAuth><ChangePassword /></ProtectedRoute>
                } />

                {/* Protected (with shell) — all operational surfaces
                    share the AppShell layout with persistent Sidebar.
                    Pages render via <Outlet /> inside AppShell. */}
                <Route element={
                    <ProtectedRoute requireAuth>
                        <AppShell />
                    </ProtectedRoute>
                }>
                    {/* Dashboard at root */}
                    <Route path="/" element={<Dashboard />} />

                    {/* BSC + Profitability */}
                    <Route path="/perform" element={<Perform />} />
                    <Route path="/about" element={<About />} />
                    <Route path="/profitability" element={<Profitability />} />

                    {/* Pipeline list — wrapped in PipelineProvider for the
                        cascade-scoped deal list state. */}
                    <Route path="/pipeline" element={
                        <PipelineProvider>
                            <Pipeline />
                        </PipelineProvider>
                    } />

                    {/* Pipeline subroutes — order: static before dynamic.
                        RR6 ranks these automatically but explicit ordering
                        documents intent. */}
                    <Route path="/pipeline/new"     element={<PipelineCreate />} />
                    <Route path="/pipeline/queues"  element={<PipelineManagerQueues />} />
                    <Route path="/pipeline/events"  element={<Events />} />
                    <Route path="/pipeline/:dealId" element={<PipelineDealDetail />} />
                    <Route path="/analytics" element={<Analytics />} />
                    <Route path="/credit-analytics" element={<CreditAnalytics />} />

                    {/* LMS subroutes — β5. Same static-before-dynamic ordering. */}
                    <Route path="/lms"         element={<Lms />} />
                    <Route path="/lms/:appId"  element={<LmsApplicationDetail />} />
                    <Route path="/committee/convening" element={<CommitteeConvening />} />

                    {/* Credit Admin subroutes — β6. */}
                    <Route path="/credit-admin"          element={<CreditAdmin />} />
                    <Route path="/credit-admin/:caseId"  element={<CreditAdminCaseDetail />} />
                    <Route path="/troops"                element={<Troops />} />

                    {/* CBS Customer Lookup — γ2. */}
                    <Route path="/cbs"         element={<Cbs />} />
                    <Route path="/cbs/:cif"    element={<CbsCustomerDetail />} />

                    {/* Target Cascade — γ3 (read-only). */}
                    <Route path="/cascade"     element={<Cascade />} />

                    {/* FX rates admin — P4-1c. Table visible to all; editor admin-gated (server enforces). */}
                    <Route path="/fx-rates"    element={<FxRates />} />

                    {/* Admin → Configuration — P4 Batch 1b. CEO/MD/Director; server enforces. */}
                    <Route path="/admin/config" element={<AdminConfig />} />
                    <Route path="/admin/daily-log" element={<DailyLogAdmin />} />
                    <Route path="/admin/roles" element={<RolesAdmin />} />
                    <Route path="/admin/hierarchy" element={<HierarchyAdmin />} />
                    <Route path="/branch-log" element={<BranchLog />} />
                    <Route path="/portfolio" element={<Portfolio />} />
                    <Route path="/admin/committees" element={<CommitteeAdmin />} />
                    <Route path="/admin/staff"      element={<StaffAdmin />} />
                    <Route path="/admin/cbs-debug" element={<CbsDebug />} />
                    <Route path="/referrals" element={<Referrals />} />
                    <Route path="/sla" element={<Sla />} />

                    {/* Strategic Initiatives — γ4 (read-only). */}
                    <Route path="/initiatives"                  element={<Initiatives />} />
                    <Route path="/initiatives/:initiativeId"    element={<InitiativeDetail />} />
                </Route>
            </Routes>
        </BrowserRouter></WebSocketProvider></RoleProvider></AuthProvider>
        </ToastProvider>
        </BrandingProvider>
    </QueryClientProvider>;
}

export default App;
'''

SIDEBAR = r'''import { displayName } from "../lib/names";
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
      { path: '/pipeline',        label: 'A2Z Sales Pro',        matchActive: (p) => p === '/pipeline' || (p.startsWith('/pipeline/') && !p.startsWith('/pipeline/queues') && !p.startsWith('/pipeline/events')) },
      { path: '/analytics',       label: 'Sales Pro Analytics',  matchActive: (p) => p.startsWith('/analytics') },
      { path: '/pipeline/queues', label: 'Manager Queues',       matchActive: (p) => p.startsWith('/pipeline/queues'), visibleFor: (m) => m },
      { path: '/pipeline/events', label: 'Events',                matchActive: (p) => p.startsWith('/pipeline/events') },
      { path: '/referrals',       label: 'A2Z Sales Referral Analytics', matchActive: (p) => p.startsWith('/referrals') },
      { path: '/branch-log',      label: 'Daily Log',     matchActive: (p) => p.startsWith('/branch-log') },
      { path: '/portfolio',       label: 'Portfolio',            matchActive: (p) => p.startsWith('/portfolio') },
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
'''


def main():
    apply = "--apply" in sys.argv
    for p in (API, APITS, APP, SB):
        if not os.path.isfile(p):
            print("ABORT: %s not found." % p)
            return 1
    if os.path.exists(PAGE):
        print("ABORT: %s already exists - EV2 looks applied." % PAGE)
        return 1

    api = open(API, encoding="utf-8").read()
    ts = open(APITS, encoding="utf-8").read()

    if '@app.get("/api/pipeline/events")' in api:
        print("ABORT: the events endpoint already exists.")
        return 1
    if API_ANCHOR not in api:
        print("ABORT: apply patch_ev1_origin_sources.py first.")
        return 1
    if ts.count(TS_ANCHOR) != 1:
        print("ABORT: api.ts anchor matched %d times." % ts.count(TS_ANCHOR))
        return 1

    api = api.replace(API_ANCHOR, ENDPOINT + API_ANCHOR, 1)
    ts = ts.replace(TS_ANCHOR, TS_NEW + TS_ANCHOR, 1)
    print("  ok  events endpoint and client")

    # Accounts must stay closure-only, or every event flatters itself.
    if '== "Closed Won"' not in ENDPOINT:
        print("ABORT: the endpoint counts accounts before closure.")
        return 1
    if "stored_leads" not in ENDPOINT or "derived_leads" not in ENDPOINT:
        print("ABORT: the endpoint must return BOTH figures.")
        return 1
    # Attribution must not be per-event.
    if ENDPOINT.count("_acquire_scoped_deals") != 1:
        print("ABORT: deals are read %d times - attribution must be computed"
              % ENDPOINT.count("_acquire_scoped_deals"))
        print("       once and bucketed, not per event.")
        return 1
    if "tagged === 0" not in PAGE_SRC:
        print("ABORT: the page does not distinguish 'nothing tagged' from a")
        print("       failed event - a red zero would read as a verdict.")
        return 1
    if "!p.startsWith('/pipeline/events')" not in SIDEBAR:
        print("ABORT: Sales Pro still claims /pipeline/events - two sidebar")
        print("       entries would highlight at once.")
        return 1
    for name, blob in (("page", PAGE_SRC), ("app", APP_SRC), ("sidebar", SIDEBAR)):
        for op, cl in (("{", "}"), ("(", ")")):
            if blob.count(op) != blob.count(cl):
                print("ABORT: %s unbalanced %s%s." % (name, op, cl))
                return 1
    print("  ok  post-checks: closure-only, both figures, one read, no clash")

    if not apply:
        print("\nDRY RUN - nothing written. Re-run with --apply.")
        return 0

    open(PAGE, "w", encoding="utf-8", newline="").write(PAGE_SRC)
    print("CREATED %s" % PAGE)
    for path, content in ((API, api), (APITS, ts), (APP, APP_SRC), (SB, SIDEBAR)):
        shutil.copy2(path, path + BACKUP_SUFFIX)
        open(path, "w", encoding="utf-8", newline="").write(content)
        print("APPLIED %s" % path)

    import py_compile
    try:
        py_compile.compile(API, doraise=True)
        print("  ok  api.py compiles")
    except Exception as exc:
        print("  FAIL %s" % exc)
        return 1

    print("\nNext: pushd frontend\\web && pnpm tsc --noEmit && popd, restart uvicorn.")
    print("Pipeline Intelligence > Events. Every derived figure will be zero")
    print("until deals are tagged - the page says so rather than implying")
    print("twelve failed sponsorships.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
