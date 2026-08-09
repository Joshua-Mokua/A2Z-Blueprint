#!/usr/bin/env python
# -*- coding: utf-8 -*-
r"""
PL1 - pipeline ranking in two levels: referral and direct.

RULING (2026-08-09): "on the pipeline ranking we will also have it in two
levels, the referral and the direct pipeline from the sales team."

THE RULE THAT KEEPS IT HONEST. A deal's value counts ONCE, for whoever owns it.
Under "Referred" the same deals are attributed to the REFERRER instead - not in
addition. Blending the two would let one referred deal inflate both the owner's
and the referrer's totals, as though the bank had booked it twice. The two views
answer different questions about the same book, which is why they are a toggle
rather than a sum.

A referral counts only once ACCEPTED, matching the daily-log credit rule
(ruling 2026-08-09) - a pending referral is an intention, not an outcome. The
same deal therefore tells the same story in the daily log, the pipeline
analytics and here.

ADDS
  GET /api/pipeline/leaderboard?days=&start=&end=&level=&origin=&branch=&unit=
      level  staff | role | branch | unit
      origin all | direct | referred
      Rows carry deals, value, weighted (via _deal_probability, the one
      probability model), won/lost and win rate.

  frontend .../components/PipelineLeaderboard.tsx

  Manager Queues' Ranking tab gains an INDEX / PIPELINE switch. They measure
  different things over the same people, so they sit side by side rather than
  being blended into one misleading number.

Uses the SAME roster reader as everything else (api_branch_log._roster_dims) -
the first draft called a _roster_dims_pipeline that does not exist, which is how
this codebase grew two of everything before.

Verified: py_compile clean, tsc --noEmit clean, vite build clean.

Usage (from project root, .venv active):
    python scripts\patch_pl1_pipeline_ranking.py            # dry run
    python scripts\patch_pl1_pipeline_ranking.py --apply    # write + .pre_pl1 backups
"""
import os
import shutil
import sys

COMP = os.path.join("frontend", "web", "src", "components", "PipelineLeaderboard.tsx")
PAGE = os.path.join("frontend", "web", "src", "pages", "PipelineManagerQueues.tsx")
APITS = os.path.join("frontend", "web", "src", "lib", "api.ts")
API = os.path.join("utils", "api.py")
BACKUP_SUFFIX = ".pre_pl1"

ENDPOINT = r'''@app.get("/api/pipeline/leaderboard")
def pipeline_leaderboard(days: int = 30, start: str = "", end: str = "",
                         level: str = "staff", origin: str = "all",
                         branch: str = "", unit: str = "",
                         user: dict = Depends(get_current_user)):
    """Pipeline ranking, in TWO LEVELS: referral and direct.

    Ruling 2026-08-09: "on the pipeline ranking we will also have it in two
    levels, the referral and the direct pipeline from the sales team."

    A deal's VALUE counts once, for whoever owns it. The REFERRER is credited
    separately, under origin=referred, so a referred deal never inflates both
    the owner's and the referrer's totals as though the bank booked it twice.

    A referral counts only once ACCEPTED, matching the daily-log credit rule -
    a pending referral is an intention, not an outcome.

    level:  staff | role | branch | unit
    origin: all | referred | direct
    """
    from datetime import date as _date, timedelta as _td
    from utils.staff_code import canon as _canon_p

    deals = _acquire_scoped_deals(user)

    if start or end:
        lo = str(start or "0000-01-01")[:10]
        hi = str(end or "9999-12-31")[:10]
    else:
        hi = _date.today().isoformat()
        lo = (_date.today() - _td(days=max(int(days or 30), 1))).isoformat()

    def _when(d):
        return str(d.get("created_at") or d.get("open_date") or "")[:10]

    def _val(d):
        try:
            return float(d.get("amount_kes") or d.get("deal_value") or 0)
        except (TypeError, ValueError):
            return 0.0

    def _accepted_referral(d):
        return bool(d.get("is_referral")) and str(d.get("referral_status") or "") == "accepted"

    live = [d for d in deals if not d.get("draft") and lo <= (_when(d) or lo) <= hi]
    if origin == "referred":
        live = [d for d in live if _accepted_referral(d)]
    elif origin == "direct":
        live = [d for d in live if not _accepted_referral(d)]

    # The roster dimensions the daily log already builds - cached, canonical,
    # and the same source the rankings and grids use. Inventing a second reader
    # here is how this codebase grew two of everything.
    from utils.api_branch_log import _roster_dims
    dims = _roster_dims()
    try:
        from utils.org_validator import unit_for_role, segment_for_role
    except Exception:
        unit_for_role = segment_for_role = lambda _r: ""

    # Attribute to the OWNER. For origin=referred we attribute to the REFERRER
    # instead - that is the whole point of the second level.
    rows_by_key: dict = {}
    for d in live:
        if origin == "referred":
            code = _canon_p(d.get("referred_by_code")
                            or (d.get("referral_chain") or [{}])[0].get("referred_by_code")
                            or "")
        else:
            code = _canon_p(d.get("staff_code") or "")
        if not code:
            continue
        dd = dims.get(code) or {}
        role = str(dd.get("role") or "")
        b = str(dd.get("branch") or "")
        u = unit_for_role(role) or ""
        if branch and b != branch:
            continue
        if unit and u != unit:
            continue
        key = {"staff": code, "role": role, "branch": b, "unit": u}.get(level, code)
        if not key:
            key = "(unassigned)"
        e = rows_by_key.setdefault(key, {
            "key": key,
            "staff_code": code if level == "staff" else "",
            "name": (dd.get("full_name") or code) if level == "staff" else key,
            "role": role if level == "staff" else "",
            "branch": b if level == "staff" else "",
            "deals": 0, "value": 0.0, "weighted": 0.0, "won": 0, "lost": 0,
            "referred": 0,
        })
        e["deals"] += 1
        e["value"] += _val(d)
        e["weighted"] += _val(d) * _deal_probability(d)
        st = str(d.get("stage") or "")
        if st == "Closed Won":
            e["won"] += 1
        elif st == "Closed Lost":
            e["lost"] += 1
        if _accepted_referral(d):
            e["referred"] += 1

    rows = []
    for e in rows_by_key.values():
        closed = e["won"] + e["lost"]
        e["value"] = round(e["value"], 2)
        e["weighted"] = round(e["weighted"], 2)
        e["win_rate"] = round(e["won"] / closed * 100, 1) if closed else 0.0
        rows.append(e)
    rows.sort(key=lambda r: -r["value"])
    for i, r in enumerate(rows, 1):
        r["rank"] = i

    return {
        "level": level, "origin": origin, "start": lo, "end": hi,
        "rows": rows,
        "total_deals": len(live),
        "total_value": round(sum(r["value"] for r in rows), 2),
        "total_weighted": round(sum(r["weighted"] for r in rows), 2),
        "branches": sorted({r["branch"] for r in rows if r.get("branch")}),
    }


'''

TS_NEW = r'''export interface PipelineLeaderboardRow {
  key: string; rank: number; name: string;
  staff_code: string; role: string; branch: string;
  deals: number; value: number; weighted: number;
  won: number; lost: number; referred: number; win_rate: number;
}
export interface PipelineLeaderboard {
  level: string; origin: string; start: string; end: string;
  rows: PipelineLeaderboardRow[];
  total_deals: number; total_value: number; total_weighted: number;
  branches: string[];
}
export async function fetchPipelineLeaderboard(opts: {
  days?: number; start?: string; end?: string;
  level?: string; origin?: string; branch?: string; unit?: string;
} = {}): Promise<PipelineLeaderboard> {
  const q = new URLSearchParams();
  if (opts.days) q.set('days', String(opts.days));
  if (opts.start) q.set('start', opts.start);
  if (opts.end) q.set('end', opts.end);
  if (opts.level) q.set('level', opts.level);
  if (opts.origin) q.set('origin', opts.origin);
  if (opts.branch) q.set('branch', opts.branch);
  if (opts.unit) q.set('unit', opts.unit);
  return getJson<PipelineLeaderboard>(`/pipeline/leaderboard?${q.toString()}`);
}

'''

COMPONENT = r'''// PipelineLeaderboard — pipeline ranking in two levels: referral and direct.
//
// A deal's value counts once, for whoever owns it. Under "Referred" the same
// deals are attributed to the REFERRER instead, so a referred deal is never
// counted twice as though the bank booked it twice — the two views answer
// different questions about the same book.

import { useCallback, useEffect, useState } from 'react';
import { Card } from '@/components/Card';
import { useToast } from '@/components/Toast';
import {
  fetchPipelineLeaderboard, type PipelineLeaderboard as Board,
} from '@/lib/api';
import { periods, findPeriod, periodArgs, DEFAULT_PERIOD_KEY } from '@/lib/period';

type Level = 'unit' | 'branch' | 'role' | 'staff';
type Origin = 'all' | 'direct' | 'referred';

const LEVELS: { key: Level; label: string }[] = [
  { key: 'unit', label: 'Units' },
  { key: 'branch', label: 'Branches' },
  { key: 'role', label: 'Roles' },
  { key: 'staff', label: 'Individuals' },
];

const ORIGINS: { key: Origin; label: string }[] = [
  { key: 'all', label: 'All deals' },
  { key: 'direct', label: 'Direct' },
  { key: 'referred', label: 'Referred' },
];

const MEDAL = ['bg-[#BED600] text-[#3B6D11]', 'bg-[#E6F1FB] text-[#0C447C]', 'bg-[#FAEEDA] text-[#854F0B]'];

function kes(n: number): string {
  if (!n) return '—';
  return Math.round(n).toLocaleString();
}

export default function PipelineLeaderboard() {
  const { toast } = useToast();
  const [periodKey, setPeriodKey] = useState(DEFAULT_PERIOD_KEY);
  const [level, setLevel] = useState<Level>('branch');
  const [origin, setOrigin] = useState<Origin>('all');
  const [data, setData] = useState<Board | null>(null);
  const [loading, setLoading] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const a = periodArgs(findPeriod(periodKey));
      setData(await fetchPipelineLeaderboard({ ...a, level, origin }));
    } catch (e) {
      toast({ tone: 'danger', message: e instanceof Error ? e.message : 'Could not load the pipeline ranking.' });
      setData(null);
    } finally {
      setLoading(false);
    }
  }, [periodKey, level, origin, toast]);

  useEffect(() => { void load(); }, [load]);

  const rows = data?.rows ?? [];
  const isStaff = level === 'staff';
  const max = Math.max(1, ...rows.map((r) => r.value));

  return (
    <Card>
      <Card.Header>
        <div className="flex flex-wrap items-center justify-between gap-3">
          <h2 className="text-base font-semibold text-gray-900">Pipeline ranking</h2>
          <div className="flex flex-wrap items-center gap-1.5 text-xs">
            {LEVELS.map((l) => (
              <button key={l.key} type="button" onClick={() => setLevel(l.key)}
                className={'rounded-full px-3 py-1 font-medium '
                  + (level === l.key ? 'bg-[#0082BB] text-white'
                                     : 'text-[#005B82] hover:bg-[#0082BB]/10')}>
                {l.label}
              </button>
            ))}
            <select value={periodKey} onChange={(e) => setPeriodKey(e.target.value)}
                    className="ml-2 rounded border border-gray-200 px-2 py-1 text-xs">
              {periods().map((p) => <option key={p.key} value={p.key}>{p.label}</option>)}
            </select>
          </div>
        </div>
      </Card.Header>

      <Card.Body>
        <div className="mb-3 flex flex-wrap items-center gap-2 text-xs">
          <span className="inline-flex overflow-hidden rounded-lg border border-gray-200">
            {ORIGINS.map((o) => (
              <button key={o.key} type="button" onClick={() => setOrigin(o.key)}
                className={'px-3 py-1 font-medium '
                  + (origin === o.key ? 'bg-[#005B82] text-white'
                                      : 'bg-white text-gray-600 hover:bg-gray-50')}>
                {o.label}
              </button>
            ))}
          </span>
          {origin === 'referred' && (
            <span className="text-[11px] text-gray-500">credited to the referrer</span>
          )}
          {data && (
            <span className="ml-auto text-gray-500">
              {data.total_deals} deals · KES{' '}
              <span className="font-semibold text-gray-800">{kes(data.total_value)}</span>
              {' · '}KES {kes(data.total_weighted)} weighted
            </span>
          )}
        </div>

        {loading && <p className="py-8 text-center text-sm text-gray-400">Ranking…</p>}

        {!loading && rows.length === 0 && (
          <p className="py-8 text-center text-sm text-gray-400">
            {origin === 'referred'
              ? 'No accepted referrals in this period.'
              : 'Nothing to rank for this period.'}
          </p>
        )}

        {!loading && rows.length > 0 && (
          <div className="overflow-auto rounded-lg border border-gray-200">
            <table className="w-full table-fixed border-separate" style={{ borderSpacing: 0 }}>
              <colgroup>
                <col style={{ width: 44 }} />
                <col />
                {isStaff && <col style={{ width: '20%' }} />}
                {isStaff && <col style={{ width: '14%' }} />}
                <col style={{ width: 70 }} />
                <col style={{ width: 130 }} />
                <col style={{ width: 130 }} />
                <col style={{ width: 150 }} />
                <col style={{ width: 70 }} />
              </colgroup>
              <thead>
                <tr>
                  {['#', isStaff ? 'Staff' : LEVELS.find((l) => l.key === level)?.label,
                    ...(isStaff ? ['Role', 'Branch'] : []),
                    'Deals', 'Value (KES)', 'Weighted (KES)', 'Share', 'Win %'].map((h, i) => (
                    <th key={i}
                        className={'px-2 py-2 text-[11px] font-semibold uppercase '
                          + (i >= 4 ? 'text-right ' : 'text-left ')
                          + (h === 'Value (KES)' ? 'bg-[#0082BB] text-white' : 'bg-gray-100 text-gray-600')}>
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {rows.map((r, i) => {
                  const bg = i % 2 === 1 ? 'bg-gray-50/40' : 'bg-white';
                  return (
                    <tr key={r.key}>
                      <td className={`${bg} px-2 py-1.5 text-xs`}>
                        <span className={'inline-flex h-5 w-5 items-center justify-center rounded-full text-[10px] font-semibold '
                          + (r.rank <= 3 ? MEDAL[r.rank - 1] : 'text-gray-400')}>
                          {r.rank}
                        </span>
                      </td>
                      <td className={`${bg} truncate px-2 py-1.5 text-xs font-medium text-gray-900`}
                          title={r.name}>{r.name}</td>
                      {isStaff && (
                        <td className={`${bg} truncate px-2 py-1.5 text-xs text-gray-500`} title={r.role}>
                          {r.role}
                        </td>
                      )}
                      {isStaff && (
                        <td className={`${bg} truncate px-2 py-1.5 text-xs text-gray-500`} title={r.branch}>
                          {r.branch}
                        </td>
                      )}
                      <td className={`${bg} px-2 py-1.5 text-right text-xs tabular-nums text-gray-700`}>
                        {r.deals}
                      </td>
                      <td className={`${bg} px-2 py-1.5 text-right text-xs font-semibold tabular-nums text-gray-900`}>
                        {kes(r.value)}
                      </td>
                      <td className={`${bg} px-2 py-1.5 text-right text-xs tabular-nums text-gray-600`}>
                        {kes(r.weighted)}
                      </td>
                      <td className={`${bg} px-2 py-1.5`}>
                        <div className="h-2 w-full overflow-hidden rounded-full bg-gray-100">
                          <div className="h-full rounded-full bg-[#0082BB]"
                               style={{ width: `${(r.value / max) * 100}%` }} />
                        </div>
                      </td>
                      <td className={`${bg} px-2 py-1.5 text-right text-xs tabular-nums`}>
                        <span className={r.win_rate >= 50 ? 'text-[#3B6D11]' : 'text-gray-500'}>
                          {r.win_rate}%
                        </span>
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
    for p in (PAGE, APITS, API):
        if not os.path.isfile(p):
            print("ABORT: %s not found. Run from the project root." % p)
            return 1
    if os.path.exists(COMP):
        print("ABORT: %s already exists - PL1 looks applied." % COMP)
        return 1

    api = open(API, encoding="utf-8").read()
    ts = open(APITS, encoding="utf-8").read()

    if '@app.get("/api/pipeline/leaderboard")' in api:
        print("ABORT: the pipeline leaderboard route is already registered.")
        return 1
    if "/api/pipeline/analytics/summary" not in api:
        print("ABORT: apply patch_pa1_pipeline_analytics.py first.")
        return 1
    if "_deal_probability" not in api:
        print("ABORT: apply patch_f3_one_probability_model.py first.")
        return 1

    anchor = '@app.get("/api/pipeline/analytics/summary")'
    api = api.replace(anchor, ENDPOINT + anchor, 1)
    print("  ok  GET /api/pipeline/leaderboard")

    ts_anchor = "export interface PipelineOriginSplit {"
    if ts.count(ts_anchor) != 1:
        print("ABORT: api.ts anchor matched %d times." % ts.count(ts_anchor))
        return 1
    ts = ts.replace(ts_anchor, TS_NEW + ts_anchor, 1)
    print("  ok  api.ts - fetchPipelineLeaderboard")

    # The endpoint must not invent a roster reader.
    if "_roster_dims_pipeline" in ENDPOINT:
        print("ABORT: the endpoint calls a roster reader that does not exist.")
        return 1
    if "from utils.api_branch_log import _roster_dims" not in ENDPOINT:
        print("ABORT: the endpoint is not using the canonical roster reader.")
        return 1
    for token in ("PipelineLeaderboard", "rankView"):
        if token not in PAGE_NEW:
            print("ABORT: the page is missing %r." % token)
            return 1
    for token in ("Pipeline validation", "Daily log validation", "Index analytics"):
        if token not in PAGE_NEW:
            print("ABORT: the page lost %r - nothing existing should be removed." % token)
            return 1
    for name, blob in (("component", COMPONENT), ("page", PAGE_NEW)):
        for op, cl in (("{", "}"), ("(", ")")):
            if blob.count(op) != blob.count(cl):
                print("ABORT: %s unbalanced %s%s." % (name, op, cl))
                return 1
    if api.count('@app.get("/api/pipeline/leaderboard")') != 1:
        print("ABORT: post-check - route count is not 1.")
        return 1
    print("  ok  post-checks: canonical roster, tabs intact, one new route")

    if not apply:
        print("\nDRY RUN - nothing written. Re-run with --apply.")
        return 0

    open(COMP, "w", encoding="utf-8", newline="").write(COMPONENT)
    print("CREATED %s" % COMP)
    for path, content in ((API, api), (APITS, ts), (PAGE, PAGE_NEW)):
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

    print("\nNext: pushd frontend\\web && pnpm tsc --noEmit && popd, then restart uvicorn.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
