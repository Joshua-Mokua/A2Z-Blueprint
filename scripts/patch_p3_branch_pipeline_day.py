#!/usr/bin/env python
# -*- coding: utf-8 -*-
r"""
P3 - the branch triad gets the enhanced pipeline validation, not the old cards.

PILOT REPORT (2026-08-10): "the pipeline validation for the branch manager is
the old one and not the one we enhanced".

Correct, and it was a gap I left deliberately. P2 routed BRANCH and ROLL-UP
callers to the new countersign view but left tier 1 - the branch triad - on the
original per-deal ValidationCard list, on the grounds that it worked and
replacing working functionality is not free. I flagged it at the time. The
pilot's answer is that the inconsistency costs more than the extra detail was
worth.

WHAT THE TRIAD NOW SEES, in the same shape as DailyLogValidation:
    deal rows with Validate / Return
    a BRANCH LINE showing what the day adds up to, and how much is validated
    a gate: "Close the day" stays disabled while anything is unvalidated

RETURN IS A QUERY, NOT A CANCELLATION. validatePipelineDeal already carries
approved:false for exactly this. The first draft routed Return through the
cancel endpoint, which would have asked to KILL a live deal when the manager
only wanted it corrected.

NO BACKEND CHANGE. /pipeline-validation/queue and /days/submit came with P1;
only the tier-1 view was missing.

The old ValidationCard list is left in the file but is no longer reachable -
every tier now has its own component. Deleting it in the same step as replacing
it would make a revert harder.

Verified: tsc --noEmit clean, vite build clean.

REQUIRES P2.

Usage (from project root, .venv active):
    python scripts\patch_p3_branch_pipeline_day.py            # dry run
    python scripts\patch_p3_branch_pipeline_day.py --apply    # write + .pre_p3b backup
"""
import os
import shutil
import sys

COMP = os.path.join("frontend", "web", "src", "components", "PipelineBranchDay.tsx")
PAGE = os.path.join("frontend", "web", "src", "pages", "PipelineManagerQueues.tsx")
BACKUP_SUFFIX = ".pre_p3b"

COMPONENT = r'''// PipelineBranchDay — tier 1: the branch triad validating the day's deals.
//
// The counterpart to DailyLogValidation, and deliberately the same shape: deal
// rows with Validate / Return, a branch line, and a gate that will not let the
// day close while anything is still open. A branch manager who has learned the
// daily-log screen should recognise this one immediately.
//
// Replaces the per-deal card list for the triad. Those cards were kept through
// P2 rather than removed, on the grounds that they worked — the pilot's answer
// was that the inconsistency costs more than the extra detail was worth.

import { useCallback, useEffect, useState } from 'react';
import { Button } from '@/components/Button';
import { Card } from '@/components/Card';
import { useToast } from '@/components/Toast';
import {
  fetchPipelineValidationQueue, submitPipelineDay, validatePipelineDeal,
  type PipelineQueue, type PipelineQueueRow,
} from '@/lib/api';

function todayIso(): string {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
}

function kes(n: number): string {
  if (!n) return '—';
  return Math.round(n).toLocaleString();
}

export default function PipelineBranchDay() {
  const { toast } = useToast();
  const [date, setDate] = useState(todayIso());
  const [data, setData] = useState<PipelineQueue | null>(null);
  const [loading, setLoading] = useState(false);
  const [busy, setBusy] = useState('');
  const [returning, setReturning] = useState('');
  const [note, setNote] = useState('');
  const [closing, setClosing] = useState(false);

  const load = useCallback(async (d: string) => {
    setLoading(true);
    try {
      setData(await fetchPipelineValidationQueue(d));
    } catch (e) {
      toast({ tone: 'danger', message: e instanceof Error ? e.message : 'Could not load the day.' });
      setData(null);
    } finally {
      setLoading(false);
    }
  }, [toast]);

  useEffect(() => { void load(date); }, [date, load]);

  const rows = data?.rows ?? [];
  const pending = rows.filter((r) => !r.validated).length;
  const value = rows.reduce((a, r) => a + (Number(r.deal_value) || 0), 0);
  const validatedValue = rows.filter((r) => r.validated)
    .reduce((a, r) => a + (Number(r.deal_value) || 0), 0);

  async function decide(row: PipelineQueueRow, approve: boolean) {
    if (!approve && !note.trim()) {
      toast({ tone: 'danger', message: 'A note is required when returning a deal.' });
      return;
    }
    setBusy(row.deal_id);
    try {
      // Returning is a QUERY, not a cancellation — validatePipelineDeal already
      // carries approved:false for exactly this. Routing "return" through the
      // cancel endpoint would ask to kill a live deal when the manager only
      // wanted it corrected.
      await validatePipelineDeal(row.deal_id, { approved: approve, note: note.trim() });
      toast({ tone: 'success', message: approve ? 'Deal validated.' : 'Returned to the owner.' });
      setReturning(''); setNote('');
      await load(date);
    } catch (e) {
      toast({ tone: 'danger', message: e instanceof Error ? e.message : 'Action failed.' });
    } finally {
      setBusy('');
    }
  }

  async function closeDay() {
    const branch = rows[0]?.branch || '';
    if (!branch) return;
    setClosing(true);
    try {
      await submitPipelineDay(branch, date);
      toast({ tone: 'success', message: `${branch} pipeline day closed and sent for countersigning.` });
      await load(date);
    } catch (e) {
      toast({ tone: 'danger', message: e instanceof Error ? e.message : 'Could not close the day.' });
    } finally {
      setClosing(false);
    }
  }

  const th = 'whitespace-nowrap px-3 py-2 text-left text-[11px] font-semibold uppercase tracking-wide';
  const td = 'whitespace-nowrap px-3 py-2 text-sm';

  return (
    <Card className="mt-4">
      <Card.Header>
        <div className="flex flex-wrap items-center justify-between gap-3">
          <h2 className="text-base font-semibold text-gray-900">Pipeline day</h2>
          <div className="flex items-center gap-2 text-xs">
            <label className="text-gray-500">Day</label>
            <input type="date" value={date} onChange={(e) => setDate(e.target.value)}
                   className="rounded border border-gray-200 px-2 py-1 text-xs" />
            <span className={'rounded-full px-2.5 py-1 text-[11px] '
              + (pending ? 'bg-[#FAEEDA] text-[#854F0B]' : 'bg-[#EAF3DE] text-[#3B6D11]')}>
              {pending ? `${pending} to validate` : 'all validated'}
            </span>
          </div>
        </div>
      </Card.Header>

      <Card.Body>
        {loading && <p className="py-8 text-center text-sm text-gray-400">Loading…</p>}

        {!loading && data && data.working_day === false && (
          <p className="py-8 text-center text-sm text-gray-500">
            {data.label || 'Rest day'} — no pipeline day is expected.
          </p>
        )}

        {!loading && data?.working_day !== false && rows.length === 0 && (
          <p className="py-8 text-center text-sm text-gray-400">No deals recorded for this day.</p>
        )}

        {!loading && rows.length > 0 && (
          <>
            <div className="overflow-auto rounded-lg border border-gray-200">
              <table className="w-full border-separate" style={{ borderSpacing: 0 }}>
                <thead>
                  <tr>
                    <th className={`${th} bg-gray-100 text-gray-600`}>Deal</th>
                    <th className={`${th} bg-gray-100 text-gray-600`}>Owner</th>
                    <th className={`${th} bg-gray-100 text-gray-600`}>Client</th>
                    <th className={`${th} bg-gray-100 text-gray-600`}>Product</th>
                    <th className={`${th} bg-gray-100 text-gray-600`}>Stage</th>
                    <th className={`${th} bg-[#003D57] text-right text-white`}>Value (KES)</th>
                    <th className={`${th} bg-gray-100 text-gray-600`}>Decision</th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map((r, i) => {
                    const bg = i % 2 === 1 ? 'bg-gray-50/40' : 'bg-white';
                    return (
                      <tr key={r.deal_id}>
                        <td className={`${td} ${bg} tabular-nums text-gray-500`}>{r.deal_id}</td>
                        <td className={`${td} ${bg} text-gray-800`}>{r.staff_name}</td>
                        <td className={`${td} ${bg} text-gray-600`}>{r.client}</td>
                        <td className={`${td} ${bg} text-gray-600`}>{r.product}</td>
                        <td className={`${td} ${bg} text-gray-600`}>{r.stage}</td>
                        <td className={`${td} ${bg} text-right font-semibold tabular-nums text-[#003D57]`}>
                          {kes(r.deal_value)}
                        </td>
                        <td className={`${td} ${bg}`}>
                          {r.validated ? (
                            <span className="text-[11px] text-[#3B6D11]">
                              ✓ validated{r.validated_by ? ` · ${r.validated_by}` : ''}
                            </span>
                          ) : !r.can_act ? (
                            <span className="text-[11px] text-gray-400">not yours to validate</span>
                          ) : returning === r.deal_id ? (
                            <div className="flex flex-col gap-1" style={{ minWidth: 220 }}>
                              <input autoFocus value={note} onChange={(e) => setNote(e.target.value)}
                                     placeholder="Why is it going back?"
                                     className="w-full rounded border border-gray-300 px-2 py-1 text-xs" />
                              <div className="flex gap-1">
                                <Button size="sm" variant="secondary" disabled={busy === r.deal_id}
                                        onClick={() => void decide(r, false)}>Send back</Button>
                                <Button size="sm" variant="ghost"
                                        onClick={() => { setReturning(''); setNote(''); }}>Cancel</Button>
                              </div>
                            </div>
                          ) : (
                            <div className="flex gap-1">
                              <Button size="sm" disabled={busy === r.deal_id}
                                      onClick={() => void decide(r, true)}>Validate</Button>
                              <Button size="sm" variant="ghost"
                                      onClick={() => { setReturning(r.deal_id); setNote(''); }}>Return</Button>
                            </div>
                          )}
                        </td>
                      </tr>
                    );
                  })}

                  <tr>
                    <td className="bg-[#EDF4F8] px-3 py-2 text-sm font-semibold text-gray-800" colSpan={5}>
                      Branch total · {rows.length} deal{rows.length === 1 ? '' : 's'}
                    </td>
                    <td className="bg-[#EDF4F8] px-3 py-2 text-right text-sm font-semibold tabular-nums text-[#003D57]">
                      {kes(value)}
                    </td>
                    <td className="bg-[#EDF4F8] px-3 py-2 text-[11px] text-gray-600">
                      {kes(validatedValue)} validated
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>

            <div className="mt-3 flex flex-wrap items-center justify-between gap-2">
              <span className="text-xs text-gray-500">
                {pending
                  ? `${pending} deal${pending === 1 ? '' : 's'} still to validate before the day can close.`
                  : 'Every deal is validated. The day can be closed.'}
              </span>
              <Button disabled={pending > 0 || closing} onClick={() => void closeDay()}>
                {closing ? 'Closing…' : 'Close the day'}
              </Button>
            </div>
          </>
        )}
      </Card.Body>
    </Card>
  );
}
'''

PAGE_NEW = r'''// v10.513 Phase 4 Batch β4 — PipelineManagerQueues page.
//
// Manager-only page at /pipeline/queues with two tabs:
//
//   1. Validation queue — deals past Lead awaiting manager validation.
//      Each deal has Validate (approved:true) / Query (approved:false)
//      action panel.
//
//   2. Cancellation queue — deals with pending cancellation requests
//      awaiting manager decision. Each deal has Approve / Reject
//      action panel.
//
// Authorization layers (defense in depth):
//   1. Sidebar hides the "Manager Queues" link from non-managers (UX)
//   2. This page renders "Not authorized" guard when isManager(user)
//      is false, before even attempting the fetch (UX)
//   3. Server returns 403 to non-managers on the queue endpoints
//      (the real security boundary)
//
// Pattern reuse:
//   - Tab strip + count badges: bespoke (no Tab primitive)
//   - Per-deal action panels: same shape as β2 detail page panels
//   - Same Toast pattern for success / error
//   - Same mutation hook pattern

import { displayName } from "../lib/names";
import { useCallback, useEffect, useState } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import { useBranding } from '@/hooks/useBranding';
import { useRole } from '@/hooks/useRole';
import { useToast } from '@/components/Toast';
import { usePipelineDealMutations } from '@/hooks/usePipelineDealMutations';
import { isManager } from '@/lib/role';
import {
  fetchValidationQueue, AuthExpiredError,
} from '@/lib/api';
import { Card } from '@/components/Card';
import { Badge } from '@/components/Badge';
import { Button } from '@/components/Button';
import { Skeleton } from '@/components/Skeleton';
import { PageHeader } from '@/components/PageHeader';
import DailyLogValidation from '@/components/DailyLogValidation';
import BranchCountersign from '@/components/BranchCountersign';
import UnitRollup from '@/components/UnitRollup';
import Leaderboard from '@/components/Leaderboard';
import DailyLogAnalytics from '@/components/DailyLogAnalytics';
import PipelineLeaderboard from '@/components/PipelineLeaderboard';
import PipelineDayCountersign from '@/components/PipelineDayCountersign';
import PipelineBranchDay from '@/components/PipelineBranchDay';
import { fetchUnitDays } from '@/lib/api';
import {
  stageTone, type PipelineDeal,
} from '@/types/pipeline';


type TabKey = 'validation' | 'dailylog' | 'ranking' | 'analytics';


// ── Page component ──────────────────────────────────────────────────────

export function PipelineManagerQueues() {
  const { branding } = useBranding();
  const { user } = useRole();
  const { toast } = useToast();
  const navigate = useNavigate();

  const userIsManager = isManager(user);

  // ── Page-local state ──────────────────────────────────────────────────

  const [activeTab, setActiveTab] = useState<TabKey>('validation');
  const [validationDeals, setValidationDeals] = useState<PipelineDeal[]>([]);
  const [loadingV, setLoadingV] = useState(false);
  const [errorV,   setErrorV]   = useState<string | null>(null);
  // Daily-log queue owns its own fetching; the page only tracks the count
  // for the tab badge.
  const [dailyLogPending, setDailyLogPending] = useState(0);
  // Tier 2 (Head of Branches, MD) countersigns BRANCHES; everyone else
  // validates individuals. Decided by asking the server what this caller
  // oversees rather than by inspecting their role string here.
  // 'staff' = validates individuals, 'branch' = countersigns branches,
  // 'rollup' = MD / Business Manager, observes and may return.
  const [tier, setTier] = useState<'staff' | 'branch' | 'rollup' | null>(null);
  const [rankView, setRankView] = useState<'index' | 'pipeline'>('index');

  // ── Fetchers ─────────────────────────────────────────────────────────

  const loadValidation = useCallback(async () => {
    if (!userIsManager) return;
    setLoadingV(true);
    setErrorV(null);
    try {
      const res = await fetchValidationQueue();
      setValidationDeals(res.deals);
    } catch (e) {
      if (e instanceof AuthExpiredError) return;
      const msg = e instanceof Error ? e.message : 'Failed to load validation queue';
      setErrorV(msg);
      setValidationDeals([]);
    } finally {
      setLoadingV(false);
    }
  }, [userIsManager]);

  useEffect(() => {
    let alive = true;
    void (async () => {
      try {
        // One probe. /unit-days answers both questions: top_of_house marks the
        // observation tier, and a Branches node means this caller countersigns
        // branches. Asking the server beats inspecting a role string here.
        const r = await fetchUnitDays();
        if (!alive) return;
        if (r.top_of_house) setTier('rollup');
        else if ((r.branches?.children?.length ?? 0) > 0) setTier('branch');
        else setTier('staff');
      } catch {
        if (alive) setTier('staff');
      }
    })();
    return () => { alive = false; };
  }, []);

  // Initial load + reload on tab focus to keep queues fresh
  useEffect(() => {
    void loadValidation();
  }, [loadValidation]);

  // ── Render guards ────────────────────────────────────────────────────

  if (!userIsManager) {
    return (
      <div className="min-h-screen bg-gray-50">
        <PageHeader
          title="Manager Queues"
          breadcrumbs={[{ label: 'EKE Pipeline Intelligence System (PIS)' }, { label: 'Manager Queues' }]}
        />
        <div className="max-w-7xl 2xl:max-w-[1680px] mx-auto px-6 py-6">
        <Card>
          <Card.Header>
            <div className="flex items-center gap-3">
              <Badge tone="warning">Not authorized</Badge>
              <h2 className="text-base font-semibold text-gray-900">
                Manager queues
              </h2>
            </div>
          </Card.Header>
          <Card.Body>
            <p className="text-sm text-gray-700">
              These queues are only visible to staff with manager authority
              (Branch Manager, Regional Head, Director, MD, etc.).
            </p>
            <p className="text-sm text-gray-500 mt-3">
              If you believe this is wrong, contact your administrator.
              Your current role is{' '}
              <span className="font-mono text-gray-700">
                {user?.role ?? '(unknown)'}
              </span>.
            </p>
            <div className="mt-4">
              <Link
                to="/pipeline"
                className="text-sm text-brand-primary underline"
              >
                ← Back to pipeline
              </Link>
            </div>
          </Card.Body>
        </Card>
        </div>
      </div>
    );
  }

  // ── Active tab data ──────────────────────────────────────────────────

  // Cancellation was removed from this page (ruling 2026-08-09); the deal list
  // here is now only ever the pipeline validation queue.
  const activeDeals    = validationDeals;
  const activeLoading  = loadingV;
  const activeError    = errorV;
  const activeReload   = loadValidation;

  // ── Main render ──────────────────────────────────────────────────────

  return (
    <div className="min-h-screen bg-gray-50">
      <PageHeader
        title="Manager Queues"
        breadcrumbs={[{ label: 'EKE Pipeline Intelligence System (PIS)' }, { label: 'Manager Queues' }]}
      />
      <div className="max-w-7xl 2xl:max-w-[1680px] mx-auto px-6 py-6">

      {/* Tab strip */}
      <div className="flex items-center gap-2 border-b border-gray-200">
        <TabBtn
          active={activeTab === 'validation'}
          onClick={() => setActiveTab('validation')}
          label="Pipeline validation"
          count={validationDeals.length}
          loading={loadingV}
        />
        <TabBtn
          active={activeTab === 'dailylog'}
          onClick={() => setActiveTab('dailylog')}
          label="Daily log validation"
          count={dailyLogPending}
          loading={false}
        />
        <TabBtn
          active={activeTab === 'ranking'}
          onClick={() => setActiveTab('ranking')}
          label="Ranking"
          count={0}
          loading={false}
        />
        <TabBtn
          active={activeTab === 'analytics'}
          onClick={() => setActiveTab('analytics')}
          label="Index analytics"
          count={0}
          loading={false}
        />
        <div className="flex-1" />
        <Button
          variant="ghost"
          size="sm"
          onClick={() => void activeReload()}
          loading={activeLoading}
        >
          Refresh
        </Button>
      </div>

      {/* Daily-log validation owns its own loading, empty and error states. */}
      {activeTab === 'dailylog' && tier === null && (
        <Card className="mt-4"><Card.Body>
          <div className="text-sm text-gray-400">Loading…</div>
        </Card.Body></Card>
      )}
      {activeTab === 'dailylog' && tier === 'rollup' && (
        <UnitRollup onCount={setDailyLogPending} />
      )}
      {activeTab === 'dailylog' && tier === 'branch' && (
        <BranchCountersign onCount={setDailyLogPending} />
      )}
      {activeTab === 'dailylog' && tier === 'staff' && (
        <DailyLogValidation onCount={setDailyLogPending} />
      )}

      {/* Ranking and analytics live here too: a manager works out of this page,
          and making them navigate elsewhere to see how their team is doing
          splits one job across two screens. Both components are scope-aware
          server-side, so each manager sees their own population. */}
      {/* Pipeline validation follows the daily log's tier routing: a branch or
          roll-up caller countersigns days; everyone else works the deal queue
          below. Same shape, so a manager learns one screen and knows both. */}
      {activeTab === 'validation' && (tier === 'branch' || tier === 'rollup') && (
        <PipelineDayCountersign onCount={() => { /* count shown on the tab */ }} />
      )}

      {/* Tier 1 — the branch triad. This was the old per-deal card list; the
          pilot reported that it did not match the daily log, so it now uses the
          same shape: rows, a branch line, and a gate on closing the day. */}
      {activeTab === 'validation' && tier === 'staff' && <PipelineBranchDay />}

      {/* Two rankings, one tab: the productivity INDEX and the PIPELINE. They
          measure different things over the same people, so they sit side by
          side rather than being blended into a single misleading number. */}
      {activeTab === 'ranking' && (
        <div className="mt-4 space-y-4">
          <div className="flex gap-1.5 text-xs">
            {(['index', 'pipeline'] as const).map((k) => (
              <button key={k} type="button" onClick={() => setRankView(k)}
                className={'rounded-full px-3 py-1 font-medium '
                  + (rankView === k ? 'bg-[#005B82] text-white'
                                    : 'bg-gray-100 text-gray-600 hover:bg-[#0082BB]/10')}>
                {k === 'index' ? 'Index ranking' : 'Pipeline ranking'}
              </button>
            ))}
          </div>
          {rankView === 'index' ? <Leaderboard /> : <PipelineLeaderboard />}
        </div>
      )}
      {activeTab === 'analytics' && <DailyLogAnalytics />}

      {/* Error panel */}
      {!['dailylog', 'ranking', 'analytics'].includes(activeTab)
        && !(activeTab === 'validation' && (tier === 'branch' || tier === 'rollup' || tier === 'staff'))
        && activeError && (
        <Card className="mt-4">
          <Card.Body>
            <div className="flex items-center gap-3">
              <Badge tone="danger">Error</Badge>
              <div className="flex-1 text-sm text-gray-700">{activeError}</div>
              <Button variant="ghost" size="sm" onClick={() => void activeReload()}>
                Retry
              </Button>
            </div>
          </Card.Body>
        </Card>
      )}

      {/* Empty / loading / content */}
      {['dailylog', 'ranking', 'analytics'].includes(activeTab)
        || (activeTab === 'validation' && (tier === 'branch' || tier === 'rollup' || tier === 'staff'))
        ? null : activeLoading && activeDeals.length === 0 ? (
        <Card className="mt-4">
          <Card.Body>
            <Skeleton shape="line" className="w-1/3" />
            <div className="mt-3"><Skeleton shape="block" className="h-12" /></div>
            <div className="mt-2"><Skeleton shape="block" className="h-12" /></div>
          </Card.Body>
        </Card>
      ) : activeDeals.length === 0 && !activeError ? (
        <Card className="mt-4">
          <Card.Body>
            <div className="text-sm text-gray-700 font-medium">
              No deals in this queue.
            </div>
            <div className="text-xs text-gray-500 mt-1">
              {activeTab === 'validation'
                ? 'New deals past Lead stage will appear here for your validation.'
                : 'Cancellation requests from your team will appear here for your decision.'}
            </div>
          </Card.Body>
        </Card>
      ) : (
        <div className="mt-4 space-y-3">
          {activeDeals.map((deal) => (
            activeTab === 'validation' ? (
              <ValidationCard
                key={deal.id}
                deal={deal}
                onNavigate={() => navigate(`/pipeline/${encodeURIComponent(deal.id)}`)}
                onResolved={() => {
                  toast({ tone: 'success', message: 'Validation decision recorded.' });
                  void loadValidation();
                }}
                onErrorToast={(msg) => toast({ tone: 'danger', message: msg })}
              />
            ) : (
              <CancellationCard
                key={deal.id}
                deal={deal}
                onNavigate={() => navigate(`/pipeline/${encodeURIComponent(deal.id)}`)}
                onResolved={() => {
                  toast({ tone: 'success', message: 'Decision recorded.' });
                  void loadValidation();
                }}
                onErrorToast={(msg) => toast({ tone: 'danger', message: msg })}
              />
            )
          ))}
        </div>
      )}

      {/* Footer */}
      <footer className="mt-12 pb-6 text-center text-[11px] text-gray-400 leading-relaxed">
        {branding?.ip_notice}
      </footer>
      </div>
    </div>
  );
}


// ── Tab button ──────────────────────────────────────────────────────────

interface TabBtnProps {
  active:   boolean;
  onClick:  () => void;
  label:    string;
  count:    number;
  loading:  boolean;
}

function TabBtn({ active, onClick, label, count, loading }: TabBtnProps) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`px-4 py-2 text-sm font-medium border-b-2 transition-colors -mb-px ${
        active
          ? 'border-brand-primary text-brand-primary'
          : 'border-transparent text-gray-600 hover:text-gray-900'
      }`}
    >
      {label}
      {' '}
      <span className={`ml-1 px-2 py-0.5 text-[11px] rounded-full ${
        active ? 'bg-brand-primary text-white' : 'bg-gray-200 text-gray-700'
      }`}>
        {loading ? '…' : count}
      </span>
    </button>
  );
}


// ── Common queue card scaffolding ───────────────────────────────────────

interface QueueCardCommonProps {
  deal:         PipelineDeal;
  onNavigate:   () => void;
  children:     React.ReactNode;
}

function QueueCard({ deal, onNavigate, children }: QueueCardCommonProps) {
  const { branding } = useBranding();
  const sym = branding?.currency_symbol ?? '';
  return (
    <Card>
      <Card.Header>
        <div className="flex items-center gap-3 flex-wrap">
          <button
            type="button"
            onClick={onNavigate}
            className="font-mono text-xs text-brand-primary hover:underline"
          >
            {deal.id}
          </button>
          <h3 className="text-sm font-semibold text-gray-900">
            {deal.client_name || '—'}
          </h3>
          <Badge tone={stageTone(deal.stage)} size="sm">{deal.stage}</Badge>
        </div>
        <div className="text-xs text-gray-500 text-right">
          <div>{deal.product_type ?? deal.product ?? '—'}</div>
          <div className="font-medium text-gray-900 mt-0.5">
            {sym} {Number(deal.amount_kes ?? deal.deal_value ?? 0).toLocaleString()}
          </div>
        </div>
      </Card.Header>
      <Card.Body>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3 text-xs mb-3">
          <Field label="Owner" value={deal.staff_name ? displayName(deal.staff_name) : undefined} sub={deal.staff_code} />
          <Field label="Probability" value={
            typeof deal.probability === 'number'
              ? `${Math.round(deal.probability * 100)}%`
              : '—'
          } />
          <Field label="Next action" value={deal.next_action} />
          <Field label="Expected close" value={(deal.expected_close ?? '').slice(0, 10) || '—'} />
        </div>
        {children}
      </Card.Body>
    </Card>
  );
}

function Field({ label, value, sub }: {
  label: string;
  value: React.ReactNode;
  sub?: React.ReactNode;
}) {
  return (
    <div>
      <div className="text-[10px] font-semibold uppercase tracking-wider text-gray-500">
        {label}
      </div>
      <div className="text-sm text-gray-900 mt-0.5">{value ?? '—'}</div>
      {sub && (
        <div className="text-[10px] text-gray-400 font-mono">{sub}</div>
      )}
    </div>
  );
}


// ── Validation card (Validate / Query buttons + note) ───────────────────

interface ResolvedCallbacks {
  onResolved:    () => void;
  onErrorToast:  (msg: string) => void;
}

function ValidationCard({ deal, onNavigate, onResolved, onErrorToast }: {
  deal: PipelineDeal;
  onNavigate: () => void;
} & ResolvedCallbacks) {
  const mutations = usePipelineDealMutations();
  const [note, setNote] = useState('');

  const submit = async (approved: boolean) => {
    const result = await mutations.validate(deal.id, {
      approved,
      note: note.trim() || undefined,
    });
    if (result.ok) {
      setNote('');
      onResolved();
    } else {
      onErrorToast(result.error);
    }
  };

  return (
    <QueueCard deal={deal} onNavigate={onNavigate}>
      <div className="border-t border-gray-100 pt-3">
        <label className="text-xs font-medium text-gray-700">
          Manager note (optional)
        </label>
        <input
          type="text"
          value={note}
          onChange={(e) => setNote(e.target.value)}
          disabled={mutations.loading}
          placeholder="Context for the owner if querying"
          className="mt-1 w-full h-9 px-3 rounded-md border border-gray-300 bg-white text-sm focus:outline-none focus:border-brand-primary focus:ring-2 focus:ring-brand-primary/20"
        />
        <div className="mt-3 flex items-center justify-end gap-2">
          <Button
            variant="ghost"
            size="sm"
            onClick={() => void submit(false)}
            loading={mutations.loading}
          >
            Query (return to owner)
          </Button>
          <Button
            variant="primary"
            size="sm"
            onClick={() => void submit(true)}
            loading={mutations.loading}
          >
            Validate — include in forecast
          </Button>
        </div>
      </div>
    </QueueCard>
  );
}


// ── Cancellation card (Approve / Reject buttons + reason context) ───────

function CancellationCard({ deal, onNavigate, onResolved, onErrorToast }: {
  deal: PipelineDeal;
  onNavigate: () => void;
} & ResolvedCallbacks) {
  const mutations = usePipelineDealMutations();
  const [note, setNote] = useState('');

  const submit = async (approve: boolean) => {
    const result = await mutations.approveCancel(deal.id, {
      approve,
      note: note.trim() || undefined,
    });
    if (result.ok) {
      setNote('');
      onResolved();
    } else {
      onErrorToast(result.error);
    }
  };

  return (
    <QueueCard deal={deal} onNavigate={onNavigate}>
      {/* Requested-by + reason context */}
      <div className="px-3 py-2 rounded-md bg-amber-50 border border-amber-200 text-xs">
        <div className="font-semibold text-amber-900">
          Cancellation requested
          {deal.cancel_requested_by && ` by ${deal.cancel_requested_by}`}
        </div>
        {deal.cancel_reason && (
          <div className="text-amber-800 mt-1">
            <span className="font-medium">Reason:</span> {deal.cancel_reason}
          </div>
        )}
      </div>
      <div className="border-t border-gray-100 pt-3 mt-3">
        <label className="text-xs font-medium text-gray-700">
          Your decision note (optional)
        </label>
        <input
          type="text"
          value={note}
          onChange={(e) => setNote(e.target.value)}
          disabled={mutations.loading}
          placeholder="Recorded on the deal for audit"
          className="mt-1 w-full h-9 px-3 rounded-md border border-gray-300 bg-white text-sm focus:outline-none focus:border-brand-primary focus:ring-2 focus:ring-brand-primary/20"
        />
        <div className="mt-3 flex items-center justify-end gap-2">
          <Button
            variant="ghost"
            size="sm"
            onClick={() => void submit(false)}
            loading={mutations.loading}
          >
            Reject (deal continues)
          </Button>
          <Button
            variant="danger"
            size="sm"
            onClick={() => void submit(true)}
            loading={mutations.loading}
          >
            Approve — close as Lost
          </Button>
        </div>
      </div>
    </QueueCard>
  );
}
'''


def main():
    apply = "--apply" in sys.argv
    if not os.path.isfile(PAGE):
        print("ABORT: %s not found. Run from the project root." % PAGE)
        return 1
    if os.path.exists(COMP):
        print("ABORT: %s already exists - P3 looks applied." % COMP)
        return 1

    cur = open(PAGE, encoding="utf-8").read()
    if "PipelineDayCountersign" not in cur:
        print("ABORT: apply patch_p2_pipeline_ui.py first.")
        return 1
    if "PipelineBranchDay" in cur:
        print("ABORT: the page already routes to PipelineBranchDay.")
        return 1

    # Return must NOT go through the cancel endpoint.
    if "requestPipelineDealCancel" in COMPONENT or "requestDealCancellation" in COMPONENT:
        print("ABORT: the component routes Return through a cancel endpoint.")
        print("       Returning is a query; cancelling kills a live deal.")
        return 1
    if "validatePipelineDeal" not in COMPONENT:
        print("ABORT: the component is not using validatePipelineDeal.")
        return 1
    for token in ("Close the day", "Branch total", "pending > 0"):
        if token not in COMPONENT:
            print("ABORT: embedded component missing %r." % token)
            return 1
    if "tier === 'staff' && <PipelineBranchDay />" not in PAGE_NEW:
        print("ABORT: the page does not route tier 1 to the new view.")
        return 1
    # Every tier must be covered, or the old card list resurfaces for someone.
    if "tier === 'branch' || tier === 'rollup' || tier === 'staff'" not in PAGE_NEW:
        print("ABORT: the old deal list is still reachable for some tier.")
        return 1
    for name, blob in (("component", COMPONENT), ("page", PAGE_NEW)):
        for op, cl in (("{", "}"), ("(", ")")):
            if blob.count(op) != blob.count(cl):
                print("ABORT: %s unbalanced %s%s." % (name, op, cl))
                return 1
    print("  ok  embedded component and page validated")

    if not apply:
        print("\nDRY RUN - nothing written. Re-run with --apply.")
        return 0

    open(COMP, "w", encoding="utf-8", newline="").write(COMPONENT)
    print("CREATED %s" % COMP)
    shutil.copy2(PAGE, PAGE + BACKUP_SUFFIX)
    open(PAGE, "w", encoding="utf-8", newline="").write(PAGE_NEW)
    print("APPLIED %s" % PAGE)

    print("\nNext: pushd frontend\\web && pnpm tsc --noEmit && popd && echo TSC_PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
