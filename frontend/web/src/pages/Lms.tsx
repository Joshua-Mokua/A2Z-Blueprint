// v10.520 Phase 4 Batch β5 — LMS application list page.
//
// First consumer of GET /api/lms/applications (α8). Cascade-scoped
// table with status filters. Clicking a row navigates to detail.
//
// Layout mirrors Pipeline.tsx: header strip + filter chips + Card-based
// table + empty/loading/error states.

import { displayName } from "../lib/names";
import { useState, useMemo, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { useBranding } from '@/hooks/useBranding';
import { useRole } from '@/hooks/useRole';
import { useLmsApplications } from '@/hooks/useLmsApplications';
import { useToast } from '@/components/Toast';
import { fetchAssignmentRequests, assignLmsAnalyst, fetchMyAnalysts, type AssignmentRequestCase, type AssignableAnalyst, pickLmsApplication } from '@/lib/api';
import { Card } from '@/components/Card';
import { PageHeader } from '@/components/PageHeader';
import { Badge } from '@/components/Badge';
import { Button } from '@/components/Button';
import { Skeleton } from '@/components/Skeleton';
import {
  statusTone,
  type LoanApplication,
} from '@/types/lms';


// ── Helpers ─────────────────────────────────────────────────────────────

function formatAmount(v: number | undefined, symbol: string): string {
  const n = Number(v);
  if (!Number.isFinite(n) || n === 0) return '—';
  return `${symbol} ${n.toLocaleString()}`;
}

function formatDate(s: string | undefined): string {
  if (!s) return '—';
  return s.slice(0, 10);
}


// ── Page component ──────────────────────────────────────────────────────

export function Lms() {
  const navigate = useNavigate();
  const { branding } = useBranding();
  const { user, isAdmin } = useRole();
  const { applications, loading, error, refetch } = useLmsApplications();

  // ── Filter state (client-side; server always returns all in-scope) ──
  const [statusFilter, setStatusFilter] = useState<string | 'all'>('all');
  const [searchTerm,   setSearchTerm]   = useState<string>('');
  // B1: workload tabs. Analysts default to their own cases; managers to All.
  const myCode = String(user?.staff_code ?? '');
  const roleLc = String(user?.role ?? '').toLowerCase();
  const isPureAnalyst = roleLc.includes('analyst') && !isAdmin
    && !/chief|head|manager|officer|director|managing/.test(roleLc);
  const [tab, setTab] = useState<'mine' | 'pool' | 'all'>('all');
  const [page, setPage] = useState(0);
  const PAGE_SIZE = 25;
  const { toast } = useToast();
  const [requestBusy, setRequestBusy] = useState<string | null>(null);
  const isManagerRole = isAdmin || /chief|head|manager|officer|director|managing/.test(roleLc);
  // PICKING IS IMMEDIATE. doRequest below asks a manager to allocate the case
  // and is kept for the roles that still work that way; a department analyst
  // takes their own segment's work without asking.
  const doPick = async (appId: string) => {
    setRequestBusy(appId);
    try {
      await pickLmsApplication(appId);
      toast({ tone: 'success', message: 'Picked — it is in My cases now.' });
      await refetch();
    } catch (e) {
      toast({ tone: 'danger',
        message: e instanceof Error ? e.message : 'Could not pick this case' });
    } finally {
      setRequestBusy(null);
    }
  };

  // doRequest removed with the button it served: a department analyst picks
  // rather than requests. If a role that still needs manager allocation
  // appears, request-assignment is untouched on the server.
  const [requestsCases, setRequestsCases] = useState<AssignmentRequestCase[]>([]);
  const [analystPool, setAnalystPool] = useState<AssignableAnalyst[]>([]);
  const [assignBusy, setAssignBusy] = useState<string | null>(null);
  const [assignMenuFor, setAssignMenuFor] = useState<string | null>(null);
  const [assignPurpose, setAssignPurpose] = useState<'decisioning' | 'correctness'>('decisioning');
  const loadRequests = async () => {
    if (!isManagerRole) return;
    try { const r = await fetchAssignmentRequests(); setRequestsCases(r.cases); } catch { /* non-fatal */ }
    try { const a = await fetchMyAnalysts(); setAnalystPool(a.analysts); } catch { /* non-fatal */ }
  };
  useEffect(() => { void loadRequests(); /* eslint-disable-next-line */ }, [isManagerRole, applications]);
  const doAssign = async (appId: string, code: string, name: string, purpose: 'decisioning' | 'correctness' = 'decisioning') => {
    setAssignBusy(appId + code);
    try {
      await assignLmsAnalyst(appId, { analyst_code: code, analyst_name: name, purpose });
      toast({ tone: 'success', message: purpose === 'correctness' ? `Assigned to ${name} for correctness check.` : `Assigned to ${name} for decisioning.` });
      await refetch();
      await loadRequests();
    } catch (e) {
      toast({ tone: 'danger', message: e instanceof Error ? e.message : 'Assign failed' });
    } finally { setAssignBusy(null); }
  };
  useEffect(() => { setTab(isPureAnalyst ? 'mine' : 'all'); }, [isPureAnalyst]);

  // ── Filtered apps ──
  const filteredApps = useMemo<LoanApplication[]>(() => {
    let result = applications;
    if (statusFilter !== 'all') {
      result = result.filter((a) => (a.status || '').toLowerCase() === statusFilter);
    }
    if (searchTerm.trim()) {
      const t = searchTerm.trim().toLowerCase();
      result = result.filter((a) =>
        (a.client_name || '').toLowerCase().includes(t) ||
        (a.id || '').toLowerCase().includes(t) ||
        (a.product || '').toLowerCase().includes(t) ||
        (a.rm_name || '').toLowerCase().includes(t)
      );
    }
    // B1: workload tab filter.
    if (tab === 'mine') {
      result = result.filter((a) => String(a.analyst?.code ?? '') === myCode);
    } else if (tab === 'pool') {
      result = result.filter((a) => !a.analyst?.code
        && ['submitted'].includes((a.status || '').toLowerCase()));
    }
    return result;
  }, [applications, statusFilter, searchTerm, tab, myCode]);
  // Keep the current page in range when the filtered set shrinks.
  const pageCount = Math.max(1, Math.ceil(filteredApps.length / PAGE_SIZE));
  const safePage = Math.min(page, pageCount - 1);
  const pagedApps = filteredApps.slice(safePage * PAGE_SIZE, safePage * PAGE_SIZE + PAGE_SIZE);

  // ── Status counts for the filter chips ──
  // statusCounts is gone with the filter row it fed. statusFilter itself
  // stays and remains 'all' - it is the mechanism the search box and the tabs
  // narrow through, and removing it would mean rewriting a working filter to
  // delete a row of buttons.

  const tabCounts = useMemo(() => ({
    mine: applications.filter((a) => String(a.analyst?.code ?? '') === myCode).length,
    pool: applications.filter((a) => !a.analyst?.code && (a.status || '').toLowerCase() === 'submitted').length,
    all: applications.length,
  }), [applications, myCode]);

  const currencySymbol = branding?.currency_symbol ?? 'KES';


  return (
    <div className="min-h-screen bg-gray-50">
      {/* Header strip — same brand-navy as Pipeline pages */}
      <PageHeader
        ribbon
        breadcrumbs={[{ label: 'A2Z Credit Intelligence System (CIS)' }, { label: 'Credit Analysis' }]}
        title="Credit Analysis"
        subtitle="Submitted, assigned, and decided applications in your cascade."
      />

      <main className="max-w-7xl 2xl:max-w-[1680px] mx-auto px-6 py-6">

        {/* ── Summary strip ──────────────────────────────────────── */}
        {!loading && !error && applications.length > 0 && (
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-4">
            {(() => {
              const total = applications.length;
              const inAnalysis = applications.filter((a) =>
                ['submitted', 'assigned', 'info_requested'].includes((a.status || '').toLowerCase())).length;
              const decided = applications.filter((a) =>
                ['approved', 'declined', 'disbursed'].includes((a.status || '').toLowerCase())).length;
              const totalValue = applications.reduce((s, a) => s + (Number(a.amount) || 0), 0);
              const stat = (label: string, value: string, accent: string) => (
                <Card>
                  <Card.Body className="py-3">
                    <div className="text-xs text-gray-500">{label}</div>
                    <div className={`text-xl font-semibold mt-0.5 ${accent}`}>{value}</div>
                  </Card.Body>
                </Card>
              );
              return (
                <>
                  {stat('In queue', String(total), 'text-gray-900')}
                  {stat('In analysis', String(inAnalysis), 'text-brand-primary')}
                  {stat('Decided', String(decided), 'text-gray-900')}
                  {stat('Total value', formatAmount(totalValue, currencySymbol), 'text-gray-900')}
                </>
              );
            })()}
          </div>
        )}

        {/* B2: assignment requests (manager) */}
        {isManagerRole && requestsCases.length > 0 && (
          <Card className="mb-4" stripe="accent">
            <Card.Header>
              <h2 className="text-base font-semibold text-gray-900">Assignment requests</h2>
              <Badge tone="warning" size="sm">{requestsCases.length}</Badge>
            </Card.Header>
            <Card.Body>
              <div className="space-y-3">
                {requestsCases.map((c) => (
                  <div key={c.id} className="rounded border p-3">
                    <div className="mb-2 flex items-center justify-between">
                      <div>
                        <span className="font-mono text-xs text-gray-500">{c.id}</span>
                        <span className="ml-2 text-sm font-medium">{c.client_name}</span>
                        <span className="ml-2 text-xs text-gray-400">{c.product}</span>
                      </div>
                    </div>
                    <div className="space-y-1">
                      {c.requests.map((r) => (
                        <div key={r.by_code} className="flex items-center justify-between rounded bg-gray-50 px-2 py-1 text-sm">
                          <span>Requested by <span className="font-medium">{r.by_name}</span> ({r.by_code})</span>
                          <Button size="sm" onClick={() => void doAssign(c.id, r.by_code, r.by_name)}
                            disabled={assignBusy === c.id + r.by_code}>
                            {assignBusy === c.id + r.by_code ? 'Assigning…' : `Assign to ${r.by_name.split(' ')[0]}`}
                          </Button>
                        </div>
                      ))}
                    </div>
                    <div className="mt-2 flex items-center gap-2">
                      <span className="text-xs text-gray-500">or assign someone else:</span>
                      <select
                        className="rounded border px-2 py-1 text-xs"
                        defaultValue=""
                        onChange={(e) => {
                          const a = analystPool.find((x) => x.staff_code === e.target.value);
                          if (a) void doAssign(c.id, a.staff_code, a.name);
                          e.target.value = '';
                        }}
                      >
                        <option value="">— pick analyst —</option>
                        {analystPool.map((a) => (
                          <option key={a.staff_code} value={a.staff_code}>{displayName(a.name)} ({a.staff_code})</option>
                        ))}
                      </select>
                    </div>
                  </div>
                ))}
              </div>
            </Card.Body>
          </Card>
        )}

        {/* ── Filter bar ─────────────────────────────────────────── */}
        <Card className="mb-4">
          <Card.Body>
            {/* B1: workload tabs */}
            <div className="flex items-center gap-2 mb-3 border-b border-gray-100 pb-3">
              {/* TWO TABS (ruling 2026-08-14): "this should be My cases and
                  the Pool. It is the pool that will contain all the cases
                  submitted from the branch, and from here is where they select
                  and it comes to My cases - once selected it moves out of the
                  pool. This is for a department especially with 2 analysts to
                  all pick from the pool."

                  "All" was a third view of the same cases that answered no
                  question an analyst asks. What is waiting for anyone, and
                  what is mine - those are the two. */}
              {([['mine', 'My cases'], ['pool', 'Pool']] as const).map(([key, label]) => (
                <button
                  key={key}
                  onClick={() => setTab(key)}
                  className={`px-3 py-1.5 rounded-md text-sm font-medium transition ${
                    tab === key ? 'bg-brand-primary text-white' : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
                  }`}
                >
                  {label} ({tabCounts[key]})
                </button>
              ))}
              {tab === 'pool' && (
                <span className="ml-2 text-xs text-gray-500">Everything waiting for this department. Open a case and pick it — it moves to My cases and out of the pool.</span>
              )}
            </div>
            {/* THE STATUS FILTER ROW IS GONE (ruling 2026-08-14): "we can
                remove the rest of the items since they can still view that
                from the Sales Pro."

                Thirteen status buttons - approved, declined, offer_signed,
                analyst_confirmed - are the shape of the workflow, not a
                question anybody opens this page to ask. My cases and the Pool
                are. The full picture is a click away in Sales Pro. */}
            <div className="flex items-center gap-2">
              <input
                type="text"
                placeholder="Search by client name, app id, product, or RM..."
                value={searchTerm}
                onChange={(e) => setSearchTerm(e.target.value)}
                className="flex-1 h-9 px-3 rounded-md border border-gray-300 bg-white text-sm focus:outline-none focus:border-brand-primary focus:ring-2 focus:ring-brand-primary/20"
              />
              {searchTerm && (
                <Button variant="ghost" size="sm" onClick={() => setSearchTerm('')}>
                  Clear
                </Button>
              )}
              <Button variant="ghost" size="sm" onClick={() => refetch()}>
                Refresh
              </Button>
            </div>
          </Card.Body>
        </Card>


        {/* ── Error state ─────────────────────────────────────────── */}
        {error && (
          <Card className="mb-4">
            <Card.Body>
              <div className="text-sm text-red-800">
                <div className="font-semibold mb-1">Failed to load applications</div>
                <div>{error}</div>
              </div>
            </Card.Body>
          </Card>
        )}


        {/* ── Loading state ───────────────────────────────────────── */}
        {loading && !error && (
          <Card>
            <Card.Body>
              <div className="space-y-2">
                <Skeleton className="h-6 w-full" />
                <Skeleton className="h-6 w-full" />
                <Skeleton className="h-6 w-full" />
                <Skeleton className="h-6 w-3/4" />
              </div>
            </Card.Body>
          </Card>
        )}


        {/* ── Empty state ─────────────────────────────────────────── */}
        {!loading && !error && filteredApps.length === 0 && (
          <Card>
            <Card.Body>
              <div className="text-center py-10">
                {applications.length === 0 ? (
                  <>
                    <div className="text-sm font-medium text-gray-800 mb-1">
                      No applications in your queue yet
                    </div>
                    <div className="text-xs text-gray-500 max-w-md mx-auto">
                      Applications submitted to credit{user?.full_name ? ` for ${user.full_name}` : ''} will
                      appear here once a relationship manager submits a deal and it is assigned for analysis.
                    </div>
                  </>
                ) : (
                  <>
                    <div className="text-sm font-medium text-gray-800 mb-1">
                      Nothing matches this filter
                    </div>
                    <div className="text-xs text-gray-500 mb-3">
                      {applications.length} application{applications.length === 1 ? '' : 's'} in your queue,
                      none in {statusFilter !== 'all' ? `“${statusFilter}”` : 'this view'}
                      {searchTerm ? ` matching “${searchTerm}”` : ''}.
                    </div>
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => { setStatusFilter('all'); setSearchTerm(''); }}
                    >
                      Clear filters
                    </Button>
                  </>
                )}
              </div>
            </Card.Body>
          </Card>
        )}


        {/* ── List table ──────────────────────────────────────────── */}
        {!loading && !error && filteredApps.length > 0 && (
          <Card>
            <Card.Body className="p-0">
              <div className="overflow-x-auto">
                <table className="min-w-full text-sm">
                  <thead className="bg-gray-50 border-b border-gray-200">
                    <tr className="text-left text-xs font-medium text-gray-500 uppercase tracking-wide">
                      <th className="px-4 py-3">ID</th>
                      <th className="px-4 py-3">Client</th>
                      <th className="px-4 py-3">Product</th>
                      <th className="px-4 py-3 text-right">Amount</th>
                      <th className="px-4 py-3">Status</th>
                      <th className="px-4 py-3">RM</th>
                      <th className="px-4 py-3">Analyst</th>
                      <th className="px-4 py-3">SLA</th>
                      <th className="px-4 py-3">Review</th>
                      {isManagerRole && <th className="px-4 py-3">Assign</th>}
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-gray-100">
                    {pagedApps.map((app) => (
                      <tr
                        key={app.id}
                        onClick={() => navigate(`/lms/${encodeURIComponent(app.id)}`)}
                        className="hover:bg-gray-50 cursor-pointer transition"
                      >
                        <td className="px-4 py-3 font-mono text-xs text-gray-500 whitespace-nowrap">
                          {app.id}
                        </td>
                        <td className="px-4 py-3">
                          <div className="font-medium text-gray-900">{app.client_name}</div>
                        </td>
                        <td className="px-4 py-3 text-gray-700">
                          {app.product || '—'}
                        </td>
                        <td className="px-4 py-3 text-right font-mono text-gray-700">
                          {formatAmount(app.amount, currencySymbol)}
                        </td>
                        <td className="px-4 py-3">
                          <Badge tone={statusTone(app.status)} size="sm">
                            {app.status}
                          </Badge>
                        </td>
                        <td className="px-4 py-3 text-gray-700 text-xs">
                          {app.rm_name || '—'}
                        </td>
                        <td className="px-4 py-3 text-gray-700 text-xs">
                          {app.analyst?.name
                            ? app.analyst.name
                            : (tab === 'pool' && isPureAnalyst ? (
                              /* PICK, NOT REQUEST (ruling 2026-08-14): "this
                                 page should now have pick and not request
                                 assignment."

                                 Requesting belongs where a manager allocates
                                 work. A department analyst owns their
                                 segment's cases already, so asking permission
                                 to take one adds a person to the chain for no
                                 decision - and leaves the case sitting in the
                                 pool while everybody waits. */
                              <button
                                onClick={(e) => { e.stopPropagation(); void doPick(app.id); }}
                                disabled={requestBusy === app.id}
                                className="rounded border border-brand-primary px-2 py-0.5 text-xs font-medium text-brand-primary hover:bg-brand-primary/5 disabled:opacity-50"
                              >
                                {requestBusy === app.id ? 'Picking…' : 'Pick'}
                              </button>
                            ) : <span className="text-gray-400">unassigned</span>)}
                        </td>
                        <td className="px-4 py-3 text-xs">
                          {app.sla ? (
                            <div className="flex flex-col gap-0.5">
                              {app.sla.stage && (
                                <span className={`inline-flex w-fit items-center gap-1 rounded px-1.5 py-0.5 font-medium ${
                                  app.sla.stage.state === 'breached' ? 'bg-red-100 text-red-700'
                                  : app.sla.stage.state === 'due_soon' ? 'bg-amber-100 text-amber-700'
                                  : 'bg-green-100 text-green-700'}`}>
                                  My: {app.sla.stage.state === 'breached'
                                    ? `${app.sla.stage.overdue_business_days}d over`
                                    : `${app.sla.stage.remaining_business_days}d left`}
                                </span>
                              )}
                              <span className={`inline-flex w-fit items-center gap-1 rounded px-1.5 py-0.5 ${
                                app.sla.state === 'breached' ? 'text-red-600'
                                : app.sla.state === 'due_soon' ? 'text-amber-600'
                                : 'text-green-600'}`}>
                                Case: {app.sla.state === 'breached'
                                  ? `${app.sla.overdue_business_days}d over`
                                  : app.sla.state === 'due_soon'
                                  ? `${app.sla.remaining_business_days}d left`
                                  : 'on track'}
                              </span>
                            </div>
                          ) : <span className="text-gray-300">—</span>}
                        </td>
                        {/* WHAT THE REVIEW SAYS, not when it was applied for
                            (ruling 2026-08-14): "once the analyst recommends or
                            returns it records here as reviewed and returned."

                            The application date was the same for every DRYRUN
                            case and told nobody whether their queue had moved.
                            What an analyst scanning this list wants is which
                            cases they have dealt with. The date is still on
                            the case itself. */}
                        <td className="px-4 py-3 text-xs">
                          {(() => {
                            const r = (app as unknown as {
                              committee_readiness?: { state?: string; by_name?: string };
                            }).committee_readiness;
                            const st = String(app.status || '').toLowerCase();
                            if (r?.state === 'ready_for_committee') {
                              return <span className="font-medium text-[#005B82]">Reviewed · recommended</span>;
                            }
                            if (r?.state === 'returned_for_rework' || st === 'returned') {
                              return <span className="font-medium text-amber-700">Reviewed · returned</span>;
                            }
                            if (st === 'assigned') {
                              return <span className="text-gray-500">In review</span>;
                            }
                            return <span className="text-gray-400">{formatDate(app.application_date)}</span>;
                          })()}
                        </td>
                        {isManagerRole && (
                          <td className="px-4 py-3 text-xs relative" onClick={(e) => e.stopPropagation()}>
                            {!app.analyst?.code && (app.status || '').toLowerCase() === 'submitted' ? (
                              <>
                                <button
                                  onClick={() => setAssignMenuFor(assignMenuFor === app.id ? null : app.id)}
                                  className="rounded border border-brand-primary px-2 py-0.5 text-xs text-brand-primary hover:bg-brand-primary/5"
                                >
                                  Assign ▾
                                </button>
                                {assignMenuFor === app.id && (
                                  <div className="absolute right-0 z-10 mt-1 w-64 rounded-md border border-gray-200 bg-white p-2 shadow-lg">
                                    <div className="mb-1 text-xs font-medium text-gray-500">Purpose</div>
                                    <div className="mb-2 flex gap-1">
                                      {(['decisioning', 'correctness'] as const).map((pp) => (
                                        <button key={pp}
                                          onClick={() => setAssignPurpose(pp)}
                                          className={`flex-1 rounded px-2 py-1 text-xs ${
                                            assignPurpose === pp ? 'bg-brand-primary text-white' : 'bg-gray-100 text-gray-700'}`}>
                                          {pp === 'decisioning' ? 'Decisioning' : 'Correctness check'}
                                        </button>
                                      ))}
                                    </div>
                                    <div className="mb-1 text-xs font-medium text-gray-500">To</div>
                                    <select
                                      className="mb-2 w-full rounded border px-2 py-1 text-xs"
                                      defaultValue=""
                                      onChange={(e) => {
                                        const a = analystPool.find((x) => x.staff_code === e.target.value);
                                        if (a) { void doAssign(app.id, a.staff_code, a.name, assignPurpose); setAssignMenuFor(null); }
                                      }}
                                    >
                                      <option value="">— pick person —</option>
                                      {analystPool.map((a) => (
                                        <option key={a.staff_code} value={a.staff_code}>{a.name}</option>
                                      ))}
                                    </select>
                                    <div className="border-t border-gray-100 pt-2">
                                      <button
                                        onClick={() => { setAssignMenuFor(null); navigate(`/lms/${encodeURIComponent(app.id)}`); }}
                                        className="w-full rounded bg-gray-50 px-2 py-1 text-left text-xs text-gray-700 hover:bg-gray-100"
                                      >
                                        Route to committee →
                                      </button>
                                    </div>
                                  </div>
                                )}
                              </>
                            ) : (
                              <span className="text-gray-300">—</span>
                            )}
                          </td>
                        )}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <div className="flex items-center justify-between px-4 py-3 border-t border-gray-100 text-xs text-gray-500">
                <span>
                  {filteredApps.length === 0 ? 'No applications' :
                    `${safePage * PAGE_SIZE + 1}–${Math.min((safePage + 1) * PAGE_SIZE, filteredApps.length)} of ${filteredApps.length}`}
                  {statusFilter !== 'all' && ` (status: ${statusFilter})`}
                  {searchTerm && ` (search: "${searchTerm}")`}
                </span>
                {pageCount > 1 && (
                  <span className="inline-flex items-center gap-2">
                    <button type="button" onClick={() => setPage(Math.max(0, safePage - 1))}
                      disabled={safePage === 0}
                      className="rounded border px-2 py-1 text-brand-primary disabled:opacity-40 hover:bg-gray-50">Prev</button>
                    <span>Page {safePage + 1} / {pageCount}</span>
                    <button type="button" onClick={() => setPage(Math.min(pageCount - 1, safePage + 1))}
                      disabled={safePage >= pageCount - 1}
                      className="rounded border px-2 py-1 text-brand-primary disabled:opacity-40 hover:bg-gray-50">Next</button>
                  </span>
                )}
              </div>
            </Card.Body>
          </Card>
        )}

      </main>
    </div>
  );
}
