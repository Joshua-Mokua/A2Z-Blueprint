#!/usr/bin/env python
# -*- coding: utf-8 -*-
r"""
CQ1 - a committee can find its own cases.

FROM THE PILOT (2026-08-12): the branch managers were gathered and nothing
moved. The committees were not configured, which was the first cause - but even
once they were, the case would still not have moved, because MEMBERS HAD
NOWHERE TO LOOK. A decision could only be recorded by knowing a deal id and
opening it. The only committee page in the product was the MD convening queue,
which reads LMS applications, not the branch gate on a pipeline deal.

A committee that cannot find its own cases is not a committee.

GET /api/pipeline/queues/committee returns the cases waiting on a committee
this person SITS ON.

  MEMBERSHIP DECIDES WHAT YOU SEE, not role. A branch manager sees their own
  branch's committee because they sit on it; somebody on two sees both. That is
  the rule the bank would apply in a room.

  SCOPE STILL APPLIES. Sitting on a committee does not open every deal in the
  bank - a member sees the cases their existing scope allows.

  A CASE LEAVES THE LIST the moment a decision is recorded for that committee,
  which is what makes it trustworthy enough to work from. Measured: a case
  appears for a member, disappears once decided, and never appears for a
  non-member.

NO NEW SIDEBAR ENTRY (ruling: "I am avoiding too many side bars"). It mounts as
a tab in Manager Queues beside validation - the same kind of work - and inside
the Daily Log for committee members who are not managers and would never open
Manager Queues. It renders NOTHING for somebody on no committee, rather than an
empty panel that makes them wonder what they are missing.

REVIEW TAKES THEM TO THE DEAL, where the committee panel already is - rather
than a second decision surface that could drift from the first.

History of past decisions is deliberately not here yet; the list of what is
WAITING is what unblocks a meeting tomorrow.

Verified: py_compile clean, tsc --noEmit clean, vite build clean.

Usage (from project root, .venv active):
    python scripts\\patch_cq1_committee_queue.py            # dry run
    python scripts\\patch_cq1_committee_queue.py --apply
"""
import os
import shutil
import sys

API = os.path.join("utils", "api.py")
COMP = os.path.join("frontend", "web", "src", "components", "CommitteeQueue.tsx")
APITS = os.path.join("frontend", "web", "src", "lib", "api.ts")
MQ = os.path.join("frontend", "web", "src", "pages", "PipelineManagerQueues.tsx")
BL = os.path.join("frontend", "web", "src", "pages", "BranchLog.tsx")
BACKUP_SUFFIX = ".pre_cq1"

API_ANCHOR = '@app.get("/api/pipeline/queues/cancellation")'
TS_ANCHOR = "export async function fetchCreditChecklist("

ENDPOINT = r'''@app.get("/api/pipeline/queues/committee")
def pipeline_queue_committee(user: dict = Depends(get_current_user)):
    """Cases waiting on a committee this person sits on.

    RULING (2026-08-12): the branch managers were gathered and nothing moved -
    and once the committees existed, the reason it still would not have moved
    is that MEMBERS HAD NOWHERE TO LOOK. A decision could only be recorded by
    knowing a deal id and opening it. A committee that cannot find its own
    cases is not a committee.

    MEMBERSHIP DECIDES WHAT YOU SEE, not role. A branch manager sees their own
    branch's committee because they sit on it; somebody added to two committees
    sees both. That is the same rule the bank would apply in a room.

    A CASE APPEARS WHEN it is at a stage whose journey includes that committee
    AND no decision has been recorded for it yet. It leaves the moment one is,
    which is what makes the list trustworthy enough to work from.
    """
    me = str(user.get("staff_code", "") or "").strip()
    me_name = str(user.get("full_name", "") or "").strip().lower()
    if not me and not me_name:
        return {"committees": [], "cases": [], "total": 0}

    # Which committees is this person on? Chair counts - they convene it.
    mine = []
    for c in _read_committee_palette():
        members = c.get("members") or []
        codes = {str(m.get("staff_code", "") or "").strip()
                 for m in members if isinstance(m, dict)}
        names = {str(m.get("name", "") or "").strip().lower()
                 for m in members if isinstance(m, dict)}
        chair = str(c.get("chaired_by", "") or "").strip().lower()
        if (me and me in codes) or (me_name and (me_name in names or me_name == chair)):
            mine.append(c)
    if not mine:
        return {"committees": [], "cases": [], "total": 0}

    my_codes = {str(c.get("code")) for c in mine}
    # Imported locally, as every other queue in this module does - api.py has
    # no module-level PipelineManager and adding one here would be a different
    # convention for no reason.
    from utils.core import PipelineManager as _PM_for_api
    from utils.api_pipeline_scope import get_visible_staff_codes as _vis
    from utils.api_pipeline_permissions import resolve_deal_permissions as _perms
    pm = _PM_for_api()
    try:
        visible = _vis(user)
    except Exception:
        visible = set()

    cases = []
    for d in (getattr(pm, "deals", []) or []):
        if str(d.get("stage", "")).lower().startswith("closed"):
            continue
        try:
            journey = _effective_committee_journey(d)
        except Exception:
            continue
        pending = [c for c in journey if c in my_codes
                   and not (d.get("committee_records") or {}).get(c)]
        if not pending:
            continue
        # SCOPE STILL APPLIES. Sitting on a committee does not open every deal
        # in the bank - a member sees the cases their scope already allows,
        # which for a branch committee is their own branch.
        if not _perms(d, user, visible).get("can_view"):
            continue
        cases.append({
            "deal_id": d.get("id"),
            "client_name": d.get("client_name"),
            "product": d.get("product_type") or d.get("product"),
            "deal_value": d.get("deal_value"),
            "currency": d.get("currency") or "KES",
            "branch": d.get("branch") or d.get("unit"),
            "stage": d.get("stage"),
            "owner": d.get("staff_name"),
            "awaiting": pending,
            "awaiting_names": [next((str(c.get("name")) for c in mine
                                     if str(c.get("code")) == p), p) for p in pending],
            "submitted_at": d.get("updated_at") or d.get("created_at"),
        })

    cases.sort(key=lambda x: str(x.get("submitted_at") or ""), reverse=True)
    return {
        "committees": [{"code": c.get("code"), "name": c.get("name"),
                        "members": len(c.get("members") or [])} for c in mine],
        "cases": cases,
        "total": len(cases),
    }


'''

TS_NEW = r'''export interface CommitteeQueueCase {
  deal_id: string; client_name: string; product: string;
  deal_value?: number; currency?: string; branch?: string; stage?: string;
  owner?: string; awaiting: string[]; awaiting_names: string[];
  submitted_at?: string;
}
export interface CommitteeQueueResponse {
  committees: { code: string; name: string; members: number }[];
  cases: CommitteeQueueCase[];
  total: number;
}
export async function fetchCommitteeQueue(): Promise<CommitteeQueueResponse> {
  return getJson<CommitteeQueueResponse>('/pipeline/queues/committee');
}
'''

COMPONENT = r'''// Cases waiting on a committee this person sits on.
//
// RULING (2026-08-12): the branch managers were gathered and nothing moved.
// Once the committees existed, the reason it still would not have moved is
// that MEMBERS HAD NOWHERE TO LOOK - a decision could only be recorded by
// knowing a deal id and opening it. A committee that cannot find its own cases
// is not a committee.
//
// NO NEW SIDEBAR ENTRY (ruling: "I am avoiding too many side bars"). This
// mounts inside Manager Queues for managers and inside the Daily Log for
// everybody else, so a committee member meets it where they already work.
//
// Review takes them to the deal, where the committee panel already lives -
// rather than building a second decision surface that could drift from it.
import { useCallback, useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { fetchCommitteeQueue, type CommitteeQueueResponse } from '@/lib/api';

export function CommitteeQueue({ compact = false }: { compact?: boolean }) {
  const nav = useNavigate();
  const [data, setData] = useState<CommitteeQueueResponse | null>(null);
  const [loading, setLoading] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      setData(await fetchCommitteeQueue());
    } catch {
      setData(null);
    } finally {
      setLoading(false);
    }
  }, []);
  useEffect(() => { void load(); }, [load]);

  // Somebody on no committee sees nothing at all - an empty panel headed
  // "Committee" would only make them wonder what they were missing.
  if (!loading && (!data || data.committees.length === 0)) return null;

  const kes = (n?: number) => (n == null ? "\u2014" : n.toLocaleString());

  return (
    <div className={compact ? 'mt-4' : ''}>
      <div className="mb-2 flex flex-wrap items-baseline justify-between gap-2">
        <div>
          <h2 className="text-base font-semibold text-gray-900">
            Awaiting your committee
          </h2>
          <p className="text-xs text-gray-500">
            {(data?.committees ?? []).map((c) => c.name).join(' \u00b7 ')}
          </p>
        </div>
        <button type="button" onClick={() => void load()}
                className="text-xs text-gray-500 hover:text-gray-800">
          Refresh
        </button>
      </div>

      {loading && (
        <p className="py-6 text-center text-sm text-gray-400">Loading\u2026</p>
      )}

      {!loading && (data?.cases.length ?? 0) === 0 && (
        <p className="rounded-lg border border-gray-200 bg-gray-50/60 py-6 text-center text-sm text-gray-500">
          Nothing waiting on your committee.
        </p>
      )}

      {!loading && (data?.cases.length ?? 0) > 0 && (
        <div className="overflow-hidden rounded-lg border border-gray-200">
          <table className="w-full text-sm">
            <thead className="bg-gray-50 text-left text-[11px] uppercase tracking-wide text-gray-500">
              <tr>
                <th className="px-3 py-2">Client</th>
                <th className="px-3 py-2">Product</th>
                <th className="px-3 py-2 text-right">Value</th>
                <th className="px-3 py-2">Owner</th>
                <th className="px-3 py-2">Committee</th>
                <th className="px-3 py-2" />
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {(data?.cases ?? []).map((c) => (
                <tr key={c.deal_id} className="hover:bg-gray-50/60">
                  <td className="px-3 py-2 font-medium text-gray-900">
                    {c.client_name}
                    <span className="ml-2 text-[11px] text-gray-400">{c.deal_id}</span>
                  </td>
                  <td className="px-3 py-2 text-gray-700">{c.product}</td>
                  <td className="px-3 py-2 text-right tabular-nums text-gray-700">
                    {c.currency} {kes(c.deal_value)}
                  </td>
                  <td className="px-3 py-2 text-gray-600">{c.owner}</td>
                  <td className="px-3 py-2 text-[11px] text-gray-500">
                    {(c.awaiting_names ?? []).join(', ')}
                  </td>
                  <td className="px-3 py-2 text-right">
                    <button
                      type="button"
                      onClick={() => nav(`/pipeline/deals/${encodeURIComponent(c.deal_id)}`)}
                      className="rounded-md bg-brand-primary px-3 py-1.5 text-xs font-semibold text-white hover:opacity-90"
                    >
                      Review
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
'''

MQ_SRC = r'''// v10.513 Phase 4 Batch β4 — PipelineManagerQueues page.
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
import { CommitteeQueue } from '@/components/CommitteeQueue';
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


type TabKey = 'validation' | 'committee' | 'dailylog' | 'ranking' | 'analytics';


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
        {/* Committee sits beside validation because it is the same kind of
            work - a queue of things waiting on this person's decision. No new
            sidebar entry (ruling 2026-08-12). */}
        <TabBtn
          active={activeTab === 'committee'}
          onClick={() => setActiveTab('committee')}
          label="Committee"
          count={0}
          loading={false}
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
      {activeTab === 'committee' && <CommitteeQueue />}

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

BL_SRC = r'''import { useCallback, useEffect, useRef, useState } from 'react';
import { PageHeader } from '@/components/PageHeader';
import { CommitteeQueue } from '@/components/CommitteeQueue';
import { Card } from '@/components/Card';
import { Button } from '@/components/Button';
import { useToast } from '@/components/Toast';
import { useRole } from '@/hooks/useRole';
import DayPlanner from '@/components/DayPlanner';
import HistoryGrid from '@/components/HistoryGrid';
import Leaderboard from '@/components/Leaderboard';
import {
  fetchBranchLogFields, fetchBranchLogAutoActivities, fetchMyBranchLogs, fetchPendingBranchLogs,
  submitBranchLogHourly, saveBranchLogHourlyDraft, fetchBranchLogDraft, validateBranchLog, fetchBranchLogConfig, saveBranchLogConfig, fetchBranchLogRanking,
  fetchBranchLogActivities, saveBranchLogActivities,
  fetchDayContext, fetchBranchLogHistoryGrid,
  type BranchLogField, type BranchLogEntry, type BranchLogActivity, type ExtraActivity,
  type HourlyMap, type DayContext, type HistoryGrid as HistoryGridData,
} from '@/lib/api';
import { displayName } from '@/lib/names';

type Tab = 'entry' | 'history' | 'review' | 'ranking' | 'setup';

// Per-tab accent. `text` colours the label when the tab is active (white pill on
// the blue ribbon); `dot` keeps the colour legible while the tab is inactive.
const TAB_TONE: Record<Tab, { text: string; dot: string }> = {
  entry:   { text: 'text-[#0082BB]', dot: 'bg-[#0082BB]' },
  history: { text: 'text-[#005B82]', dot: 'bg-[#005B82]' },
  review:  { text: 'text-[#854F0B]', dot: 'bg-[#E0A02B]' },
  ranking: { text: 'text-[#3B6D11]', dot: 'bg-[#BED600]' },
  setup:   { text: 'text-[#464646]', dot: 'bg-[#979797]' },
};

// True when the planner holds anything worth persisting. Module scope on purpose:
// the submit/draft callbacks must stay dependency-free to keep a stable identity.
function hasEntryContent(h: HourlyMap, r: string): boolean {
  if (r.trim().length > 0) return true;
  return Object.values(h).some(
    (b) => Object.keys(b.counts || {}).length > 0 || (b.meetings?.length ?? 0) > 0 || !!b.note,
  );
}

export default function BranchLog() {
  const { toast } = useToast();
  const { user, isAdmin } = useRole();
  const [tab, setTab] = useState<Tab>('entry');
  const [fields, setFields] = useState<BranchLogField[]>([]);
  // Phase 2c: the day planner is the entry surface. `hourly` is the source of
  // truth; day totals are derived server-side (utils/branch_log.derive_from_hourly).
  const [hourly, setHourly] = useState<HourlyMap>({});
  const [remarks, setRemarks] = useState('');
  const [lastSaved, setLastSaved] = useState<Date | null>(null);
  const [dayCtx, setDayCtx] = useState<DayContext | null>(null);
  const [grid, setGrid] = useState<HistoryGridData | null>(null);
  // 7 by default: the grid is now roster-complete (every scoped staff member
  // for every working day), so 30 days is ~9,500 rows before filtering.
  const [gridDays, setGridDays] = useState(7);
  const [gridLoading, setGridLoading] = useState(false);
  const [mine, setMine] = useState<BranchLogEntry[]>([]);
  const [pending, setPending] = useState<BranchLogEntry[]>([]);
  const [notes, setNotes] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);
  // Item 3/4: track unsaved edits so we can auto-save a draft on leave.
  const [dirty, setDirty] = useState(false);
  const [savingDraft, setSavingDraft] = useState(false);
  const [autoActs, setAutoActs] = useState<BranchLogActivity[]>([]);
  const [indexTarget, setIndexTarget] = useState(0);
  const [weightDraft, setWeightDraft] = useState<Record<string, string>>({});
  const [targetDraft, setTargetDraft] = useState('');
  const [extraActs, setExtraActs] = useState<ExtraActivity[]>([]);
  const [newAct, setNewAct] = useState<{ key: string; label: string; unit: string; weight: string; roles: string }>({ key: '', label: '', unit: '', weight: '', roles: '' });

  const canReview = isAdmin || /manager|head|supervisor/i.test(String(user?.role ?? ''));
  const metricFields = fields.filter((f) => f.type !== 'text');
  const today = new Date().toISOString().slice(0, 10);

  const loadFields = useCallback(async () => {
    try { const r = await fetchBranchLogFields(); setFields(r.fields); } catch { /* ignore */ }
  }, []);
  const loadMine = useCallback(async () => {
    try { const r = await fetchMyBranchLogs(14); setMine(r.logs); } catch { /* ignore */ }
  }, []);
  const loadPending = useCallback(async () => {
    try { const r = await fetchPendingBranchLogs(); setPending(r.logs); } catch { /* ignore */ }
  }, []);
  const loadAuto = useCallback(async () => {
    try { const r = await fetchBranchLogAutoActivities(); setAutoActs(r.activities); } catch { /* ignore */ }
  }, []);
  const loadCfg = useCallback(async () => {
    try {
      const r = await fetchBranchLogConfig();
      setIndexTarget(r.daily_index_target || 0);
      setTargetDraft(String(r.daily_index_target || 0));
      const wd: Record<string, string> = {};
      for (const [k, v] of Object.entries(r.activity_weights || {})) wd[k] = String(v);
      setWeightDraft(wd);
    } catch { /* ignore */ }
  }, []);
  const loadRanking = useCallback(async () => {
    // The Leaderboard component owns the ranking now; this call survives only to
    // pick up the daily index target, which the Day Planner header needs.
    try { const r = await fetchBranchLogRanking(30); setIndexTarget(r.daily_index_target || 0); } catch { /* ignore */ }
  }, []);
  const loadActs = useCallback(async () => {
    try { const r = await fetchBranchLogActivities(); setExtraActs(r.extra); } catch { /* ignore */ }
  }, []);
  // Calendar context for the header. Failure is silent: a missing work calendar
  // must not stop anyone logging their day.
  const loadDayCtx = useCallback(async () => {
    try { setDayCtx(await fetchDayContext()); } catch { /* header falls back */ }
  }, []);
  // Phase 3: the wide history grid. Loads on demand (History tab) and on
  // range change, not on mount - it is the heaviest call on the page.
  const loadGrid = useCallback(async (days: number) => {
    setGridLoading(true);
    try { setGrid(await fetchBranchLogHistoryGrid(days)); }
    catch (e) { toast({ tone: 'danger', message: e instanceof Error ? e.message : 'Could not load history.' }); }
    finally { setGridLoading(false); }
  }, [toast]);

  useEffect(() => { void loadFields(); void loadMine(); void loadAuto(); void loadCfg(); void loadDayCtx(); }, [loadFields, loadMine, loadAuto, loadCfg, loadDayCtx]);
  useEffect(() => { if (tab === 'ranking') void loadRanking(); }, [tab, loadRanking]);
  useEffect(() => { if (tab === 'setup') void loadActs(); }, [tab, loadActs]);
  useEffect(() => { if (tab === 'review' && canReview) void loadPending(); }, [tab, canReview, loadPending]);

  const todaysLog = mine.find((l) => l.log_date === today);

  // Phase 2c: submit/draft read the entry from a ref so the callbacks keep a
  // stable identity. The 30s timer and the unmount handler must not be re-armed
  // on every keystroke (that previously fired a draft POST per edit).
  const entryRef = useRef<{ hourly: HourlyMap; remarks: string }>({ hourly: {}, remarks: '' });
  useEffect(() => { entryRef.current = { hourly, remarks }; }, [hourly, remarks]);

  const submit = async () => {
    const { hourly: h, remarks: r } = entryRef.current;
    // Guard: an empty planner would derive all-zero day totals and wipe a
    // pre-existing entry for today. Make the user log something first.
    if (!hasEntryContent(h, r)) {
      toast({ tone: 'danger', message: 'Log at least one activity or a remark before submitting.' });
      return;
    }
    setBusy(true);
    try {
      await submitBranchLogHourly(h, r);
      toast({ tone: 'success', message: 'Daily log submitted for validation.' });
      setDirty(false); setLastSaved(new Date()); void loadMine();
    } catch (e) {
      toast({ tone: 'danger', message: e instanceof Error ? e.message : 'Submit failed.' });
    } finally { setBusy(false); }
  };

  // Item 3 (Phase 2c): save the planner as a private draft (not submitted).
  const saveDraft = useCallback(async (silent = false) => {
    const { hourly: h, remarks: r } = entryRef.current;
    if (!hasEntryContent(h, r)) return;
    setSavingDraft(true);
    try {
      await saveBranchLogHourlyDraft(h, r);
      setDirty(false);
      setLastSaved(new Date());
      if (!silent) toast({ tone: 'success', message: 'Draft saved. You can submit later today.' });
    } catch (e) {
      if (!silent) toast({ tone: 'danger', message: e instanceof Error ? e.message : 'Could not save draft.' });
    } finally { setSavingDraft(false); }
  }, [toast]);

  // Item 3 (Phase 2c): re-hydrate today's hourly map (draft or submitted) on load.
  // Legacy flat entries carry no `hourly` — those open as an empty planner.
  const loadDraft = useCallback(async () => {
    try {
      const r = await fetchBranchLogDraft();
      const log = r.log;
      if (!log) return;
      const raw = (log as { hourly?: unknown }).hourly;
      if (raw && typeof raw === 'object' && Object.keys(raw as object).length > 0) {
        setHourly((prev) => (Object.keys(prev).length ? prev : (raw as HourlyMap)));
      }
      if (typeof log.remarks === 'string' && log.remarks) {
        setRemarks((prev) => (prev ? prev : (log.remarks as string)));
      }
    } catch { /* no entry today — start blank */ }
  }, []);

  // Item 3: load today's saved entry once, on mount (after loadDraft exists).
  useEffect(() => { void loadDraft(); }, [loadDraft]);
  useEffect(() => { if (tab === 'history') void loadGrid(gridDays); }, [tab, gridDays, loadGrid]);

  // Item 4: auto-save a draft when leaving with unsaved edits. The unmount
  // handler runs on logout and in-app navigation (React unmounts the page) and
  // uses the normal authenticated saveDraft. A beforeunload warning covers the
  // browser-close/refresh case (sendBeacon can't carry the JWT, so we warn).
  const dirtyRef = useRef(false); useEffect(() => { dirtyRef.current = dirty; }, [dirty]);
  useEffect(() => {
    const warn = (e: BeforeUnloadEvent) => {
      if (dirtyRef.current) { e.preventDefault(); e.returnValue = ''; }
    };
    window.addEventListener('beforeunload', warn);
    return () => {
      window.removeEventListener('beforeunload', warn);
      if (dirtyRef.current) void saveDraft(true);
    };
  }, [saveDraft]);

  // Phase 2c: autosave the planner every 30 seconds while edits are pending.
  // saveDraft is ref-backed and stable, so the timer is armed once per mount.
  useEffect(() => {
    const id = window.setInterval(() => {
      if (dirtyRef.current) void saveDraft(true);
    }, 30_000);
    return () => window.clearInterval(id);
  }, [saveDraft]);

  const review = async (id: string, approved: boolean) => {
    setBusy(true);
    try {
      await validateBranchLog(id, approved, (notes[id] ?? '').trim());
      toast({ tone: 'success', message: approved ? 'Log validated.' : 'Log returned.' });
      void loadPending();
    } catch (e) {
      toast({ tone: 'danger', message: e instanceof Error ? e.message : 'Action failed.' });
    } finally { setBusy(false); }
  };

  const fmt = (v: unknown) => (typeof v === 'number' ? v.toLocaleString() : String(v ?? ''));
  const metricSummary = (l: BranchLogEntry) =>
    metricFields.filter((f) => Number(l[f.key]) > 0).map((f) => (
      <span key={f.key}>{f.label}: <b>{fmt(l[f.key])}</b></span>
    ));

  const tabs: [Tab, string][] = [
    ['entry', 'Daily Log Entry'],
    ['history', 'Log History'],
    ...(canReview ? ([['review', 'Supervisor Review']] as [Tab, string][]) : []),
    ['ranking', 'Ranking'],
    ...(isAdmin ? ([['setup', 'Index Setup']] as [Tab, string][]) : []),
  ];
  // DayPlanner renders the live day index itself (sum of count x weight over hours).
  const dateLabel = new Date().toLocaleDateString(undefined, { weekday: 'long', day: 'numeric', month: 'long' });
  // Greeting name: prefer the server-resolved staff name, fall back to the JWT
  // identity, and render an impersonal greeting rather than "Dear ," if neither.
  const firstName = displayName(dayCtx?.staff_name || user?.full_name || '');

  return (
    <div>
      <PageHeader
        ribbon
        sticky
        title="Daily Log"
        subtitle={dateLabel}
        actions={
          <div className="flex flex-wrap items-center justify-end gap-1.5">
            {tabs.map(([id, lbl]) => (
              <button key={id} onClick={() => setTab(id)}
                className={'flex items-center gap-1.5 rounded-full px-3 py-1.5 text-sm font-medium transition-colors '
                  + (tab === id ? `bg-white shadow-sm ${TAB_TONE[id].text}` : 'text-white/80 hover:bg-white/15')}>
                <span className={'h-1.5 w-1.5 rounded-full ' + (tab === id ? TAB_TONE[id].dot : 'bg-white/50')} />
                {lbl}{id === 'review' && pending.length ? ` (${pending.length})` : ''}
              </button>
            ))}
          </div>
        }
      />

      <div className="mx-auto max-w-7xl px-4 py-6 2xl:max-w-[1680px]">

      {tab === 'entry' && (
        <Card>
          <Card.Header>
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div className="min-w-0">
                <h2 className="text-base font-semibold text-gray-900">
                  {firstName ? `Dear ${firstName}, the day is all yours — make every activity count.`
                             : 'The day is all yours — make every activity count.'}
                </h2>
                <p className="mt-0.5 text-xs text-gray-500">
                  {dayCtx
                    ? `${dayCtx.weekday} · day ${dayCtx.day_of_year} of ${dayCtx.days_in_year}`
                    : 'Today\u2019s activity'}
                </p>
              </div>
              {dayCtx && (
                <div className="flex flex-wrap items-center gap-1.5 text-[11px]">
                  {dayCtx.holiday && (
                    <span className="rounded-full bg-[#FAEEDA] px-2.5 py-1 font-medium text-[#854F0B]">
                      {dayCtx.holiday_label || 'Public holiday'}
                    </span>
                  )}
                  {!dayCtx.holiday && dayCtx.half_day && (
                    <span className="rounded-full bg-[#EAF3DE] px-2.5 py-1 font-medium text-[#3B6D11]">
                      Half day · {dayCtx.hours_today}h
                    </span>
                  )}
                  {!dayCtx.working && !dayCtx.holiday && (
                    <span className="rounded-full bg-gray-100 px-2.5 py-1 font-medium text-gray-500">
                      Rest day
                    </span>
                  )}
                  <span className="rounded-full bg-[#E6F1FB] px-2.5 py-1 text-[#0C447C]">
                    {dayCtx.days_remaining.toLocaleString()} days left in {dayCtx.date.slice(0, 4)}
                  </span>
                  <span className="rounded-full bg-[#E6F1FB] px-2.5 py-1 text-[#0C447C]">
                    {dayCtx.working_days_remaining.toLocaleString()} working days
                  </span>
                  <span className="rounded-full bg-[#E6F1FB] px-2.5 py-1 text-[#0C447C]">
                    {dayCtx.working_hours_remaining.toLocaleString()} working hours
                  </span>
                </div>
              )}
            </div>
          </Card.Header>
          <Card.Body>
            {todaysLog && (
              <div className="mb-3 rounded border border-blue-100 bg-blue-50 p-2 text-sm text-blue-800">
                You already submitted today
                {todaysLog.validated ? ' (validated)' : todaysLog.rejected ? ' (returned — please correct)' : ' (awaiting validation)'}.
                {' '}Re-submitting updates it.
              </div>
            )}
            <div className="grid grid-cols-1 gap-5 lg:grid-cols-[minmax(0,1fr)_20rem]">
              <DayPlanner
                fields={metricFields}
                hourly={hourly}
                onChange={(next) => { setDirty(true); setHourly(next); }}
                target={indexTarget}
              />

              {/* Context in, actions out. Keeps Save/Submit beside the timeline
                  rather than below it, so they stay above the fold. */}
              <aside className="flex flex-col gap-4">
                {autoActs.length > 0 && (
                  <div className="rounded-md border border-gray-200 bg-gray-50 p-3">
                    <div className="text-sm font-semibold text-gray-800">Tracked automatically today</div>
                    <p className="mb-2 text-xs text-gray-400">Pulled from your pipeline actions — no need to key these.</p>
                    <ol className="max-h-40 space-y-1 overflow-y-auto">
                      {autoActs.map((a, i) => (
                        <li key={i} className="flex items-start gap-2 text-sm">
                          <span className="tabular-nums text-gray-400">{a.time}</span>
                          <span className="rounded border border-gray-200 bg-white px-1.5 py-0.5 text-xs text-gray-600">{a.kind}</span>
                          <span className="text-gray-700">{a.detail}</span>
                        </li>
                      ))}
                    </ol>
                  </div>
                )}

                <label className="block text-sm">
                  <span className="mb-1 block text-gray-700">Remarks / challenges</span>
                  <textarea rows={4} className="w-full rounded border px-2 py-1.5 text-sm"
                    placeholder="Blockers, escalations, anything the hours don't say."
                    value={remarks} onChange={(e) => { setDirty(true); setRemarks(e.target.value); }} />
                </label>

                <div className="mt-auto border-t border-gray-100 pt-3">
                  <div className="mb-2 text-xs text-gray-400">
                    {savingDraft
                      ? 'Saving…'
                      : dirty
                        ? 'Unsaved changes — autosaves every 30 seconds.'
                        : lastSaved
                          ? `All changes saved ${lastSaved.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}`
                          : 'Autosaves every 30 seconds.'}
                  </div>
                  <div className="flex flex-col gap-2">
                    <Button fullWidth onClick={() => void submit()} disabled={busy}>Submit daily log</Button>
                    <Button fullWidth variant="ghost" onClick={() => void saveDraft()} disabled={busy || savingDraft}>
                      {savingDraft ? 'Saving…' : 'Save draft'}
                    </Button>
                  </div>
                </div>
              </aside>
            </div>
          </Card.Body>
        </Card>
      )}

      {tab === 'ranking' && <Leaderboard />}

      {tab === 'setup' && isAdmin && (
        <Card>
          <Card.Header><h2 className="text-base font-semibold text-gray-900">Activity weights &amp; daily index target</h2></Card.Header>
          <Card.Body>
            <label className="mb-4 block text-sm">
              <span className="mb-1 block text-gray-700">Daily index target</span>
              <input type="number" min={0} className="w-40 rounded border px-2 py-1.5 text-sm"
                value={targetDraft} onChange={(e) => setTargetDraft(e.target.value)} />
            </label>
            <p className="mb-2 text-sm font-medium text-gray-700">Points per activity</p>
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
              {metricFields.map((f) => (
                <label key={f.key} className="flex items-center justify-between gap-2 text-sm">
                  <span className="text-gray-700">{f.label}</span>
                  <input type="number" step="any" className="w-24 rounded border px-2 py-1 text-sm"
                    value={weightDraft[f.key] ?? ''} onChange={(e) => setWeightDraft((p) => ({ ...p, [f.key]: e.target.value }))} />
                </label>
              ))}
            </div>
            <div className="mt-4 flex justify-end">
              <Button disabled={busy} onClick={async () => {
                setBusy(true);
                try {
                  const w: Record<string, number> = {};
                  for (const [k, v] of Object.entries(weightDraft)) w[k] = Number(v) || 0;
                  await saveBranchLogConfig(w, Number(targetDraft) || 0);
                  toast({ tone: 'success', message: 'Weights & target saved.' });
                  await loadFields(); await loadCfg();
                } catch (e) { toast({ tone: 'danger', message: e instanceof Error ? e.message : 'Save failed' }); }
                finally { setBusy(false); }
              }}>Save weights &amp; target</Button>
            </div>

            <div className="mt-6 border-t border-gray-100 pt-4">
              <h3 className="mb-1 text-sm font-semibold text-gray-800">Extra activities (head office / role-specific)</h3>
              <p className="mb-3 text-xs text-gray-400">These appear only for the roles you list (comma-separated). Leave roles blank to show for everyone.</p>
              {extraActs.length > 0 && (
                <div className="mb-3 space-y-1">
                  {extraActs.map((a, i) => (
                    <div key={a.key} className="flex items-center justify-between rounded border border-gray-200 bg-gray-50 px-2 py-1 text-sm">
                      <div>
                        <span className="font-medium text-gray-800">{a.label}</span>
                        <span className="ml-2 text-xs text-gray-500">{a.unit || 'count'} · wt {a.weight}{a.roles.length ? ` · ${a.roles.join(', ')}` : ' · all roles'}</span>
                      </div>
                      <button className="text-xs text-gray-400 hover:text-red-600"
                        onClick={() => setExtraActs((p) => p.filter((_, j) => j !== i))}>Remove</button>
                    </div>
                  ))}
                </div>
              )}
              <div className="grid grid-cols-1 gap-2 sm:grid-cols-5">
                <input className={'rounded border px-2 py-1 text-sm'} placeholder="key (e.g. credit_apps)" value={newAct.key} onChange={(e) => setNewAct((p) => ({ ...p, key: e.target.value }))} />
                <input className={'rounded border px-2 py-1 text-sm'} placeholder="Label" value={newAct.label} onChange={(e) => setNewAct((p) => ({ ...p, label: e.target.value }))} />
                <input className={'rounded border px-2 py-1 text-sm'} placeholder="unit" value={newAct.unit} onChange={(e) => setNewAct((p) => ({ ...p, unit: e.target.value }))} />
                <input className={'rounded border px-2 py-1 text-sm'} type="number" step="any" placeholder="weight" value={newAct.weight} onChange={(e) => setNewAct((p) => ({ ...p, weight: e.target.value }))} />
                <input className={'rounded border px-2 py-1 text-sm'} placeholder="roles (comma-sep)" value={newAct.roles} onChange={(e) => setNewAct((p) => ({ ...p, roles: e.target.value }))} />
              </div>
              <div className="mt-2 flex gap-2">
                <Button variant="ghost" onClick={() => {
                  const k = newAct.key.trim(); if (!k || !newAct.label.trim()) { toast({ tone: 'danger', message: 'Key and label required.' }); return; }
                  setExtraActs((p) => [...p.filter((x) => x.key !== k), { key: k, label: newAct.label.trim(), type: 'int', unit: newAct.unit.trim(), weight: Number(newAct.weight) || 0, roles: newAct.roles.split(',').map((s) => s.trim()).filter(Boolean) }]);
                  setNewAct({ key: '', label: '', unit: '', weight: '', roles: '' });
                }}>Add activity</Button>
                <Button disabled={busy} onClick={async () => {
                  setBusy(true);
                  try { await saveBranchLogActivities(extraActs); toast({ tone: 'success', message: 'Activities saved.' }); await loadFields(); await loadActs(); }
                  catch (e) { toast({ tone: 'danger', message: e instanceof Error ? e.message : 'Save failed' }); }
                  finally { setBusy(false); }
                }}>Save activities</Button>
              </div>
            </div>
          </Card.Body>
        </Card>
      )}

      {/* A committee member who is not a manager never opens Manager

          Queues, so the same list appears here. It renders nothing at

          all for somebody on no committee. */}

      <CommitteeQueue compact />


      {tab === 'history' && (
        <Card>
          <Card.Header>
            <div className="flex flex-wrap items-center justify-between gap-2">
              <h2 className="text-base font-semibold text-gray-900">Log history</h2>
              <span className="text-xs text-gray-400">
                Index vs target per day, with the running carried-forward balance.
              </span>
            </div>
          </Card.Header>
          <Card.Body>
            <HistoryGrid grid={grid} loading={gridLoading} days={gridDays} onDaysChange={setGridDays} />
          </Card.Body>
        </Card>
      )}

      {tab === 'review' && canReview && (
        <Card>
          <Card.Header><h2 className="text-base font-semibold text-gray-900">Awaiting validation</h2></Card.Header>
          <Card.Body>
            {pending.length === 0 ? <p className="text-sm text-gray-400">Nothing pending in your unit.</p> : (
              <div className="space-y-3">
                {pending.map((l) => (
                  <div key={l.id} className="rounded border border-amber-200 bg-amber-50 p-3">
                    <div className="flex items-center justify-between">
                      <span className="font-medium text-gray-900">{l.staff_name} <span className="text-gray-400">({l.role}, {l.unit})</span></span>
                      <span className="text-xs text-gray-500">{l.log_date}</span>
                    </div>
                    <div className="mt-1 flex flex-wrap gap-x-4 gap-y-1 text-xs text-gray-600">{metricSummary(l)}</div>
                    {l.remarks ? <p className="mt-1 text-xs text-gray-500">{l.remarks}</p> : null}
                    <input className="mt-2 w-full rounded border px-2 py-1 text-xs" placeholder="Note (optional)"
                      value={notes[l.id] ?? ''} onChange={(e) => setNotes((p) => ({ ...p, [l.id]: e.target.value }))} />
                    <div className="mt-2 flex gap-2">
                      <Button size="sm" onClick={() => void review(l.id, true)} disabled={busy}>Validate</Button>
                      <Button size="sm" variant="ghost" onClick={() => void review(l.id, false)} disabled={busy}>Return</Button>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </Card.Body>
        </Card>
      )}
      </div>
    </div>
  );
}
'''


def main():
    apply = "--apply" in sys.argv
    for p in (API, APITS, MQ, BL):
        if not os.path.isfile(p):
            print("ABORT: %s not found." % p)
            return 1

    api = open(API, encoding="utf-8").read()
    ts = open(APITS, encoding="utf-8").read()

    if "queues/committee" in api:
        print("ABORT: CQ1 looks applied.")
        return 1
    if api.count(API_ANCHOR) != 1 or ts.count(TS_ANCHOR) != 1:
        print("ABORT: anchors matched %d / %d times."
              % (api.count(API_ANCHOR), ts.count(TS_ANCHOR)))
        return 1

    api = api.replace(API_ANCHOR, ENDPOINT + API_ANCHOR, 1)
    ts = ts.replace(TS_ANCHOR, TS_NEW + TS_ANCHOR, 1)
    print("  ok  endpoint, client, component, both surfaces")

    # Membership, not role - or every manager sees every committee.
    if "members" not in ENDPOINT or "chaired_by" not in ENDPOINT:
        print("ABORT: the queue is not driven by committee membership.")
        return 1
    # Scope must still apply.
    if "can_view" not in ENDPOINT:
        print("ABORT: a committee member would see deals outside their scope.")
        return 1
    # A decided case must leave the list.
    if "committee_records" not in ENDPOINT:
        print("ABORT: a decided case would stay in the queue, which makes the")
        print("       list useless the second time somebody opens it.")
        return 1
    # Nothing for a non-member.
    # Checked against the text that is actually there. The first version of
    # this guard looked for a string I had reworded, and aborted a correct
    # patch - a post-check that fails on right code is worse than none.
    if "data.committees.length === 0)) return null" not in COMPONENT:
        print("ABORT: somebody on no committee would see an empty panel.")
        return 1
    for name, blob in (("component", COMPONENT), ("queues", MQ_SRC), ("log", BL_SRC)):
        for op, cl in (("{", "}"), ("(", ")")):
            if blob.count(op) != blob.count(cl):
                print("ABORT: %s unbalanced %s%s." % (name, op, cl))
                return 1
    print("  ok  post-checks: membership-driven, scoped, clears when decided")

    if not apply:
        print("\nDRY RUN - nothing written. Re-run with --apply.")
        return 0

    for path, content in ((API, api), (APITS, ts), (MQ, MQ_SRC), (BL, BL_SRC)):
        shutil.copy2(path, path + BACKUP_SUFFIX)
        open(path, "w", encoding="utf-8", newline="").write(content)
        print("APPLIED %s" % path)
    open(COMP, "w", encoding="utf-8", newline="").write(COMPONENT)
    print("CREATED %s" % COMP)

    import py_compile
    try:
        py_compile.compile(API, doraise=True)
        print("  ok  api.py compiles")
    except Exception as exc:
        print("  FAIL %s" % exc)
        return 1

    print("")
    print("Next: pushd frontend\\web && pnpm tsc --noEmit && popd, restart uvicorn.")
    print("Manager Queues > Committee, and the same list inside the Daily Log")
    print("for members who are not managers. Review opens the deal, where the")
    print("committee panel already is.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
