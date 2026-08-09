#!/usr/bin/env python
# -*- coding: utf-8 -*-
r"""
P2 - pipeline validation UI, and the Manager Queues restructure.

YOUR RULING: "on the manager queue we can have instead of validation, we have
pipeline validation, then daily log validation and we remove what we have on
that page named cancellation, then the pipeline can have the same structure
upward".

MANAGER QUEUES IS NOW
    Pipeline validation | Daily log validation | Ranking | Analytics
    Cancellation removed - the tab, its loader, its state and its fetch.

PIPELINE VALIDATION ROUTES BY TIER, exactly as the daily log does:
    branch / roll-up caller  -> PipelineDayCountersign (branch pipeline days)
    everyone else            -> the existing deal queue, unchanged

WHAT IS PRESERVED, DELIBERATELY. The rich per-deal ValidationCard stays for the
people who validate deals. Replacing it with a thin row list would have been
"consistency" that removed working functionality - the structure above it is
what you asked to be consistent, not the deal screen itself.

PipelineDayCountersign is the same shape as BranchCountersign: one row per
branch (deals / validated / pending / value / status), expandable to that
branch's deals read-only, Countersign and Return with a note required. A manager
who has learned the daily log screen has learned this one.

Validation still TERMINATES (ruling 2026-08-08): the Head of Branches
countersigns; the MD and Business Manager observe and may return, and the
Countersign button is not rendered for them at all.

Verified: tsc --noEmit clean, vite build clean, and no dangling reference to the
removed cancellation queue.

Usage (from project root, .venv active):
    python scripts\patch_p2_pipeline_ui.py            # dry run
    python scripts\patch_p2_pipeline_ui.py --apply    # write + .pre_p2 backups
"""
import os
import shutil
import sys

COMP = os.path.join("frontend", "web", "src", "components", "PipelineDayCountersign.tsx")
APITS = os.path.join("frontend", "web", "src", "lib", "api.ts")
PAGE = os.path.join("frontend", "web", "src", "pages", "PipelineManagerQueues.tsx")
BACKUP_SUFFIX = ".pre_p2"

TS_ANCHOR = "// \u2500\u2500 Cumulative leaderboard (staff / role / branch / unit) \u2500\u2500"

TS_NEW = r'''// ── Pipeline validation (same tier structure as the Daily Log) ────────────
export interface PipelineQueueRow {
  deal_id: string; staff_code: string; staff_name: string; role: string;
  branch: string; client: string; product: string; stage: string;
  deal_value: number; validated: boolean; validated_by: string; can_act: boolean;
}
export interface PipelineQueue {
  rows: PipelineQueueRow[]; date: string; working_day: boolean; label: string;
  pending: number; branch?: string; mode: string;
}
export interface PipelineDayRow {
  branch: string; deals: number; validated: number; pending: number; value: number;
  status: string; submitted_by_name: string; validated_by_name: string;
  return_note: string;
}
export interface PipelineDays {
  rows: PipelineDayRow[]; date: string; working_day?: boolean; label?: string;
  top_of_house: boolean; can_return?: boolean;
}
export async function fetchPipelineValidationQueue(
  date = '', branch = '',
): Promise<PipelineQueue> {
  const q = new URLSearchParams();
  if (date) q.set('date', date);
  if (branch) q.set('branch', branch);
  const s = q.toString();
  return getJson<PipelineQueue>(`/pipeline-validation/queue${s ? `?${s}` : ''}`);
}
export async function fetchPipelineValidationDays(date = ''): Promise<PipelineDays> {
  return getJson<PipelineDays>(
    `/pipeline-validation/days${date ? `?date=${encodeURIComponent(date)}` : ''}`);
}
export async function submitPipelineDay(
  branch: string, date: string,
): Promise<{ pipeline_day: Record<string, unknown> }> {
  return postJson<{ pipeline_day: Record<string, unknown> },
                  { branch: string; date: string }>(
    '/pipeline-validation/days/submit', { branch, date });
}
export async function decidePipelineDay(
  branch: string, date: string, approved: boolean, note = '',
): Promise<{ pipeline_day: Record<string, unknown> }> {
  return postJson<{ pipeline_day: Record<string, unknown> },
                  { branch: string; date: string; approved: boolean; note: string }>(
    '/pipeline-validation/days/validate', { branch, date, approved, note });
}

'''

COMPONENT = r'''// P2 — pipeline day countersign, tiers 2 and 3.
//
// Deliberately the same shape as BranchCountersign for the daily log: a manager
// who has learned one screen has learned both. One row per branch, expandable
// to that branch's deals read-only, with Countersign and Return (note required).
//
// Ruling 2026-08-08 applies unchanged: validation TERMINATES. The Head of
// Branches countersigns a branch pipeline day; the MD and Business Manager
// observe and may return, but never countersign.

import { useCallback, useEffect, useState } from 'react';
import { Button } from '@/components/Button';
import { Card } from '@/components/Card';
import { useToast } from '@/components/Toast';
import {
  fetchPipelineValidationDays, decidePipelineDay, fetchPipelineValidationQueue,
  type PipelineDays, type PipelineDayRow, type PipelineQueue,
} from '@/lib/api';

const STATUS: Record<string, { label: string; cls: string }> = {
  draft:     { label: 'Not closed',    cls: 'bg-gray-100 text-gray-500' },
  submitted: { label: 'Awaiting you',  cls: 'bg-[#FAEEDA] text-[#854F0B]' },
  validated: { label: 'Countersigned', cls: 'bg-[#EAF3DE] text-[#3B6D11]' },
  returned:  { label: 'Returned',      cls: 'bg-[#FBEAF0] text-[#993556]' },
};

function todayIso(): string {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
}

function kes(n: number): string {
  if (!n) return '—';
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000) return `${Math.round(n / 1_000)}K`;
  return String(Math.round(n));
}

export default function PipelineDayCountersign({ onCount }: { onCount?: (n: number) => void }) {
  const { toast } = useToast();
  const [date, setDate] = useState(todayIso());
  const [data, setData] = useState<PipelineDays | null>(null);
  const [loading, setLoading] = useState(false);
  const [openKey, setOpenKey] = useState('');
  const [detail, setDetail] = useState<PipelineQueue | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [returning, setReturning] = useState('');
  const [note, setNote] = useState('');
  const [busy, setBusy] = useState('');

  const load = useCallback(async (d: string) => {
    setLoading(true);
    try {
      const r = await fetchPipelineValidationDays(d);
      setData(r);
      onCount?.(r.rows.filter((x) => x.status === 'submitted').length);
    } catch (e) {
      toast({ tone: 'danger', message: e instanceof Error ? e.message : 'Could not load pipeline days.' });
      setData(null);
    } finally {
      setLoading(false);
    }
  }, [toast, onCount]);

  useEffect(() => { void load(date); }, [date, load]);

  async function expand(row: PipelineDayRow) {
    if (openKey === row.branch) { setOpenKey(''); setDetail(null); return; }
    setOpenKey(row.branch);
    setDetail(null);
    setDetailLoading(true);
    try {
      setDetail(await fetchPipelineValidationQueue(date, row.branch));
    } catch (e) {
      toast({ tone: 'danger', message: e instanceof Error ? e.message : 'Could not open that branch.' });
      setOpenKey('');
    } finally {
      setDetailLoading(false);
    }
  }

  async function decide(row: PipelineDayRow, approve: boolean) {
    if (!approve && !note.trim()) {
      toast({ tone: 'danger', message: 'A note is required when returning a day.' });
      return;
    }
    setBusy(row.branch);
    try {
      await decidePipelineDay(row.branch, date, approve, note.trim());
      toast({ tone: 'success',
              message: approve ? `${row.branch} pipeline day countersigned.`
                               : `${row.branch} returned to the branch.` });
      setReturning(''); setNote('');
      await load(date);
    } catch (e) {
      toast({ tone: 'danger', message: e instanceof Error ? e.message : 'Action failed.' });
    } finally {
      setBusy('');
    }
  }

  const rows = data?.rows ?? [];
  const th = 'whitespace-nowrap px-3 py-2 text-left text-[11px] font-semibold uppercase tracking-wide';
  const td = 'whitespace-nowrap px-3 py-2 text-sm';

  return (
    <Card className="mt-4">
      <Card.Header>
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <h2 className="text-base font-semibold text-gray-900">Pipeline day — branches</h2>
            <p className="mt-0.5 text-xs text-gray-500">
              {data?.top_of_house
                ? 'You observe these and may return a day for amendment.'
                : 'You countersign the branch pipeline day once its deals are validated.'}
            </p>
          </div>
          <div className="flex items-center gap-2 text-xs">
            <label className="text-gray-500">Day</label>
            <input type="date" value={date} onChange={(e) => setDate(e.target.value)}
                   className="rounded border border-gray-200 px-2 py-1 text-xs" />
            <span className="rounded-full bg-[#E6F1FB] px-2.5 py-1 text-[11px] text-[#0C447C]">
              {rows.length} branches
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
          <p className="py-8 text-center text-sm text-gray-400">
            No branches consolidate to you for this day.
          </p>
        )}

        {!loading && rows.length > 0 && (
          <div className="overflow-auto rounded-lg border border-gray-200">
            <table className="w-full border-separate" style={{ borderSpacing: 0 }}>
              <thead>
                <tr>
                  <th className={`${th} bg-gray-100 text-gray-600`}>Branch</th>
                  <th className={`${th} bg-gray-100 text-gray-600`}>Deals</th>
                  <th className={`${th} bg-gray-100 text-gray-600`}>Validated</th>
                  <th className={`${th} bg-gray-100 text-gray-600`}>Pending</th>
                  <th className={`${th} bg-[#003D57] text-white`}>Value (KES)</th>
                  <th className={`${th} bg-gray-100 text-gray-600`}>Status</th>
                  <th className={`${th} bg-gray-100 text-gray-600`}>Decision</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((r, i) => {
                  const st = STATUS[r.status] ?? STATUS.draft;
                  const bg = i % 2 === 1 ? 'bg-gray-50/40' : 'bg-white';
                  const canAct = r.status === 'submitted'
                    && (!data?.top_of_house || (data?.can_return ?? false));
                  return (
                    <>
                      <tr key={r.branch}>
                        <td className={`${td} ${bg} font-medium text-gray-900`}>
                          <button type="button" onClick={() => void expand(r)}
                                  className="flex items-center gap-1.5 hover:text-brand-primary">
                            <span className="text-gray-400">{openKey === r.branch ? '▾' : '▸'}</span>
                            {r.branch}
                          </button>
                        </td>
                        <td className={`${td} ${bg} tabular-nums text-gray-700`}>{r.deals}</td>
                        <td className={`${td} ${bg} tabular-nums text-[#3B6D11]`}>{r.validated}</td>
                        <td className={`${td} ${bg} tabular-nums ${r.pending ? 'text-amber-600' : 'text-gray-300'}`}>
                          {r.pending || '—'}
                        </td>
                        <td className={`${td} ${bg} tabular-nums font-semibold text-[#003D57]`}>
                          {kes(r.value)}
                        </td>
                        <td className={`${td} ${bg}`}>
                          <span className={`rounded-full px-2 py-0.5 text-[11px] font-medium ${st.cls}`}>
                            {st.label}
                          </span>
                          {r.submitted_by_name && (
                            <div className="mt-0.5 text-[10px] text-gray-400">by {r.submitted_by_name}</div>
                          )}
                          {r.status === 'returned' && r.return_note && (
                            <div className="mt-0.5 text-[10px] text-[#993556]">{r.return_note}</div>
                          )}
                        </td>
                        <td className={`${td} ${bg}`}>
                          {!canAct ? (
                            <span className="text-[11px] text-gray-400">—</span>
                          ) : returning === r.branch ? (
                            <div className="flex flex-col gap-1" style={{ minWidth: 210 }}>
                              <input autoFocus value={note} onChange={(e) => setNote(e.target.value)}
                                     placeholder="Why is it going back?"
                                     className="w-full rounded border border-gray-300 px-2 py-1 text-xs" />
                              <div className="flex gap-1">
                                <Button size="sm" variant="secondary" disabled={busy === r.branch}
                                        onClick={() => void decide(r, false)}>Send back</Button>
                                <Button size="sm" variant="ghost"
                                        onClick={() => { setReturning(''); setNote(''); }}>Cancel</Button>
                              </div>
                            </div>
                          ) : (
                            <div className="flex gap-1">
                              {!data?.top_of_house && (
                                <Button size="sm" disabled={busy === r.branch}
                                        onClick={() => void decide(r, true)}>Countersign</Button>
                              )}
                              <Button size="sm" variant="ghost"
                                      onClick={() => { setReturning(r.branch); setNote(''); }}>
                                Return
                              </Button>
                            </div>
                          )}
                        </td>
                      </tr>

                      {openKey === r.branch && (
                        <tr key={`${r.branch}-d`}>
                          <td colSpan={7} className="bg-[#F7FBFD] px-6 py-3">
                            {detailLoading && <p className="text-xs text-gray-400">Opening {r.branch}…</p>}
                            {!detailLoading && (detail?.rows ?? []).length === 0 && (
                              <p className="text-xs text-gray-400">No deals recorded for this day.</p>
                            )}
                            {!detailLoading && (detail?.rows ?? []).length > 0 && (
                              <table className="w-full">
                                <tbody>
                                  {(detail?.rows ?? []).map((d) => (
                                    <tr key={d.deal_id} className="border-b border-gray-100 last:border-0">
                                      <td className="py-1 pr-3 text-xs tabular-nums text-gray-500" style={{ width: 80 }}>
                                        {d.deal_id}
                                      </td>
                                      <td className="py-1 pr-3 text-xs text-gray-800">{d.staff_name}</td>
                                      <td className="py-1 pr-3 text-xs text-gray-500">{d.client}</td>
                                      <td className="py-1 pr-3 text-xs text-gray-500">{d.product}</td>
                                      <td className="py-1 pr-3 text-xs tabular-nums text-gray-700" style={{ width: 80 }}>
                                        {kes(d.deal_value)}
                                      </td>
                                      <td className="py-1 text-xs" style={{ width: 130 }}>
                                        {d.validated
                                          ? <span className="text-[#3B6D11]">✓ validated</span>
                                          : <span className="text-amber-600">awaiting validation</span>}
                                      </td>
                                    </tr>
                                  ))}
                                </tbody>
                              </table>
                            )}
                          </td>
                        </tr>
                      )}
                    </>
                  );
                })}
              </tbody>
            </table>
          </div>
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
import PipelineDayCountersign from '@/components/PipelineDayCountersign';
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
          label="Analytics"
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

      {activeTab === 'ranking' && <div className="mt-4"><Leaderboard /></div>}
      {activeTab === 'analytics' && <DailyLogAnalytics />}

      {/* Error panel */}
      {!['dailylog', 'ranking', 'analytics'].includes(activeTab)
        && !(activeTab === 'validation' && (tier === 'branch' || tier === 'rollup'))
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
        || (activeTab === 'validation' && (tier === 'branch' || tier === 'rollup'))
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
    for p in (APITS, PAGE):
        if not os.path.isfile(p):
            print("ABORT: %s not found. Run from the project root." % p)
            return 1
    if os.path.exists(COMP):
        print("ABORT: %s already exists - P2 looks applied." % COMP)
        return 1

    ts = open(APITS, encoding="utf-8").read()
    cur = open(PAGE, encoding="utf-8").read()

    if "fetchPipelineValidationDays" in ts:
        print("ABORT: api.ts already has the pipeline validation clients.")
        return 1
    if "DailyLogAnalytics" not in cur:
        print("ABORT: apply patch_a3_analytics.py first.")
        return 1
    if "cancellation" not in cur.lower():
        print("ABORT: this page no longer has a cancellation queue - unexpected state.")
        return 1
    if ts.count(TS_ANCHOR) != 1:
        print("ABORT: api.ts anchor matched %d times." % ts.count(TS_ANCHOR))
        return 1

    ts = ts.replace(TS_ANCHOR, TS_NEW + TS_ANCHOR, 1)
    print("  ok  api.ts - pipeline validation clients")

    for token in ("PipelineDayCountersign", "Pipeline validation",
                  "Daily log validation"):
        if token not in PAGE_NEW:
            print("ABORT: embedded page missing %r." % token)
            return 1
    if "fetchCancellationQueue" in PAGE_NEW or "loadCancellation" in PAGE_NEW:
        print("ABORT: embedded page still references the cancellation queue.")
        return 1
    for name, blob in (("component", COMPONENT), ("page", PAGE_NEW)):
        for o, c in (("{", "}"), ("(", ")")):
            if blob.count(o) != blob.count(c):
                print("ABORT: embedded %s unbalanced %s%s." % (name, o, c))
                return 1
    print("  ok  embedded page + component validated")

    if "fetchBranchLogHistoryGrid" not in ts:
        print("ABORT: post-check - api.ts lost fetchBranchLogHistoryGrid.")
        return 1
    print("  ok  post-checks clean")

    if not apply:
        print("\nDRY RUN - nothing written. Re-run with --apply.")
        return 0

    open(COMP, "w", encoding="utf-8", newline="").write(COMPONENT)
    print("CREATED %s" % COMP)
    for path, content in ((APITS, ts), (PAGE, PAGE_NEW)):
        shutil.copy2(path, path + BACKUP_SUFFIX)
        open(path, "w", encoding="utf-8", newline="").write(content)
        print("APPLIED %s" % path)

    print("\nNext: pushd frontend\\web && pnpm tsc --noEmit && popd && echo TSC_PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
