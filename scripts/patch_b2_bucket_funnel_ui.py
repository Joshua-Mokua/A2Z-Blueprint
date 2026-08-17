#!/usr/bin/env python
# -*- coding: utf-8 -*-
r"""
B2 - the funnel shows BUCKETS. The side layer is gone.

Follows B1. The six names - Initiation, Documentation, Unit Review, Credit
Analysis, Credit Administration, TROPS - ARE the journey, so the funnel now
draws them as its bands and the probability-inferred "side layer" is REMOVED
from both the endpoint and the UI.

That removal is the point. Leaving the same six names in two places, once as the
journey and once as an inferred second axis, is exactly the confusion to avoid
on a system heading to production - two competing answers to "where is this
deal".

WHAT MANAGEMENT SEES
    six bands for a loan, four for an account, each carrying its weight
    ("15% of journey"), its exit probability, count and value.

WHAT AN OFFICER SEES
    clicking a bucket opens its micro-steps, each with its own cumulative
    probability, count and value - so Unit Review unfolds into Branch Credit
    Committee / Department Analyst / Department Business Committee.

THE DRILL MOVED DOWN A LEVEL, deliberately: it now fires on the MICRO-STEP,
which is the real stage a deal sits at. Clicking a step stops propagation so it
does not also collapse the bucket the user just opened.

Empty buckets are still drawn, hatched and labelled - the empty bucket is where
deals stop arriving, which is usually the finding.

Verified: py_compile clean, tsc --noEmit clean, vite build clean.

REQUIRES B1 (and the migration having been run, or the buckets will be empty).

Usage (from project root, .venv active):
    python scripts\patch_b2_bucket_funnel_ui.py            # dry run
    python scripts\patch_b2_bucket_funnel_ui.py --apply    # write + .pre_b2b backups
"""
import os
import shutil
import sys

COMP = os.path.join("frontend", "web", "src", "components", "DefinedFunnel.tsx")
APITS = os.path.join("frontend", "web", "src", "lib", "api.ts")
API = os.path.join("utils", "api.py")
BACKUP_SUFFIX = ".pre_b2b"

ENDPOINT = r'''@app.get("/api/pipeline/funnel")
def pipeline_funnel_defined(user: dict = Depends(get_current_user)):
    """The DEFINED journey per product flow — from admin config, not from code.

    Returns every configured stage of every flow in order, including the ones
    holding nothing: a funnel that hides its empty steps is a bar chart of
    whatever happened to be busy, and the gap is usually the finding.

    Each stage carries its win probability PER FLOW (ruling 2026-08-09) and the
    credit band that probability implies. The band is a SIDE LAYER describing
    where the deal probably sits inside the bank — it is not a sales stage and
    it never filters the journey.

    Scope is the caller's own: the same visible-deal rule the rest of the
    pipeline uses, so this can never show a deal the list would hide.
    """
    from utils.pipeline_funnel import (
        stage_flows, flow_for_deal, buckets_for, bucket_view, micro_steps,
    )

    # _acquire_scoped_deals is the canonical scope read used by the pipeline
    # list and analytics. NO try/except fallback here on purpose: a fallback to
    # "all deals" would silently show a caller deals outside their cascade, and
    # a scope bypass that looks like a working page is worse than an error.
    deals = _acquire_scoped_deals(user)

    grouped: dict = {}
    for d in deals:
        grouped.setdefault(flow_for_deal(d), []).append(d)

    flows_out = []
    for flow in (stage_flows() or {}):
        mine = grouped.get(flow, [])
        # BUCKETS are the journey (ruling 2026-08-09). Management reads six rows
        # for a loan, not eleven; the micro-steps travel inside their bucket so
        # an officer can still see exactly where a deal sits.
        buckets = bucket_view(mine, flow)
        weighted = 0.0
        for b in buckets:
            for st in b["steps"]:
                weighted += float(st["value"]) * float(st["probability"])
        flows_out.append({
            "flow": flow,
            "buckets": buckets,
            "deals": len(mine),
            "value": round(sum(float(b["value"]) for b in buckets), 2),
            "weighted": round(weighted, 2),
        })
    flows_out.sort(key=lambda f: -f["deals"])

    # Deals sitting at a stage no configured bucket contains. Reported, never
    # dropped: silently vanishing deals is the defect this endpoint replaces.
    unplaced = 0
    for d in deals:
        st = str(d.get("stage") or "").strip()
        if st in ("Closed Won", "Closed Lost"):
            continue
        if st not in micro_steps(flow_for_deal(d)):
            unplaced += 1

    return {
        "flows": flows_out,
        "total_deals": len(deals),
        # Deals sitting at a stage NO configured flow contains. Reported rather
        # than dropped: silently vanishing deals is the defect this replaces.
        "unplaced_deals": unplaced,
    }


'''

TS_NEW = r'''// ── Defined funnel (journey from admin config + credit side layer) ────────
export interface DefinedStep {
  stage: string; count: number; value: number; probability: number;
}
export interface DefinedBucket {
  key: string; label: string; weight: number;
  count: number; value: number; probability: number;
  steps: DefinedStep[];
}
export interface DefinedFlow {
  flow: string; buckets: DefinedBucket[];
  deals: number; value: number; weighted: number;
}
export interface DefinedFunnel {
  flows: DefinedFlow[];
  total_deals: number;
  unplaced_deals: number;
}
export async function fetchPipelineDefinedFunnel(): Promise<DefinedFunnel> {
  return getJson<DefinedFunnel>('/pipeline/funnel');
}

'''

COMPONENT = r'''// DefinedFunnel — the pipeline centrepiece, drawn from ADMIN CONFIG.
//
// Ruling 2026-08-09: stages are never hardcoded. Every band here is a stage the
// bank configured in that product's flow, in the order it configured them, with
// the win probability it set for that stage WITHIN THAT FLOW.
//
// EMPTY STAGES ARE DRAWN. A funnel that hides the steps holding nothing is a bar
// chart of whatever happened to be busy — and the empty step is usually the
// finding: it is where deals stop arriving.
//
// THE CREDIT LAYER IS A SECOND AXIS, not a stage. Documentation / Branch Credit /
// Department / Credit Analysis / Credit Administration / TROPS say where a deal
// probably sits inside the bank, inferred from its probability. It sits beneath
// the journey and never filters it.

import { useEffect, useMemo, useState } from 'react';
import { Card } from '@/components/Card';
import { useToast } from '@/components/Toast';
import { fetchPipelineDefinedFunnel, type DefinedFunnel as FunnelData, type DefinedFlow } from '@/lib/api';

// Cool→warm sweep: early stages cool, closing stages warm. Depth comes from a
// vertical gradient plus a soft inner highlight, so a band reads as a solid
// object rather than a coloured rectangle.
const PALETTE = ['#0082BB', '#0C7BC0', '#3F6FC4', '#6A61C0', '#9455B0', '#BE4E93', '#D75A72', '#E0A02B', '#669438'];

function bandColour(i: number, n: number): string {
  if (n <= 1) return PALETTE[0];
  const seg = (i / (n - 1)) * (PALETTE.length - 1);
  const idx = Math.min(Math.floor(seg), PALETTE.length - 2);
  const t = seg - idx;
  const hex = (h: string) => [parseInt(h.slice(1, 3), 16), parseInt(h.slice(3, 5), 16), parseInt(h.slice(5, 7), 16)];
  const [r1, g1, b1] = hex(PALETTE[idx]);
  const [r2, g2, b2] = hex(PALETTE[idx + 1]);
  const m = (a: number, b: number) => Math.round(a + (b - a) * t);
  return `rgb(${m(r1, r2)}, ${m(g1, g2)}, ${m(b1, b2)})`;
}

function kes(n: number): string {
  if (!n) return '—';
  return Math.round(n).toLocaleString();
}

export interface DefinedFunnelProps {
  /** Clicking a non-empty band drills into that flow + stage. Preserved from the
   *  previous funnel: dropping it would have removed a working feature quietly. */
  onStageClick?: (flow: string, stage: string) => void;
}

export default function DefinedFunnel({ onStageClick }: DefinedFunnelProps = {}) {
  const { toast } = useToast();
  const [data, setData] = useState<FunnelData | null>(null);
  const [loading, setLoading] = useState(false);
  const [flowKey, setFlowKey] = useState('');
  const [sizeBy, setSizeBy] = useState<'count' | 'value'>('count');
  const [hover, setHover] = useState('');

  useEffect(() => {
    let alive = true;
    setLoading(true);
    void (async () => {
      try {
        const r = await fetchPipelineDefinedFunnel();
        if (!alive) return;
        setData(r);
        setFlowKey((k) => k || (r.flows[0]?.flow ?? ''));
      } catch (e) {
        if (alive) toast({ tone: 'danger', message: e instanceof Error ? e.message : 'Could not load the funnel.' });
      } finally {
        if (alive) setLoading(false);
      }
    })();
    return () => { alive = false; };
  }, [toast]);

  const flow: DefinedFlow | undefined = useMemo(
    () => data?.flows.find((f) => f.flow === flowKey) ?? data?.flows[0],
    [data, flowKey]);

  const buckets = flow?.buckets ?? [];
  const max = Math.max(1, ...buckets.map((b) => (sizeBy === 'count' ? b.count : b.value)));
  // Micro-steps open on demand: management reads the six buckets, an officer
  // opens the one they work in.
  const [openBucket, setOpenBucket] = useState('');

  return (
    <Card>
      <Card.Header>
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <h2 className="text-base font-semibold text-gray-900">Pipeline journey</h2>
            <p className="mt-0.5 text-xs text-gray-500">
              Each product's defined stages, in the order the bank configured them.
            </p>
          </div>
          <div className="flex items-center gap-1 text-[11px]">
            {(['count', 'value'] as const).map((s) => (
              <button key={s} type="button" onClick={() => setSizeBy(s)}
                className={'rounded-full px-2.5 py-1 font-medium '
                  + (sizeBy === s ? 'bg-[#0082BB] text-white' : 'text-[#005B82] hover:bg-[#0082BB]/10')}>
                by {s}
              </button>
            ))}
          </div>
        </div>
      </Card.Header>

      <Card.Body>
        {loading && <p className="py-10 text-center text-sm text-gray-400">Loading the journey…</p>}

        {!loading && data && data.flows.length === 0 && (
          <p className="py-10 text-center text-sm text-gray-400">
            No product flows configured. Define them in Administration.
          </p>
        )}

        {!loading && data && data.flows.length > 0 && (
          <>
            <div className="mb-3 flex flex-wrap gap-1.5">
              {data.flows.map((f) => (
                <button key={f.flow} type="button" onClick={() => setFlowKey(f.flow)}
                  className={'rounded-full px-3 py-1 text-xs font-medium capitalize transition-colors '
                    + (flow?.flow === f.flow ? 'bg-[#005B82] text-white'
                                             : 'bg-gray-100 text-gray-600 hover:bg-[#0082BB]/10')}>
                  {f.flow}
                  <span className="ml-1.5 opacity-70">{f.deals}</span>
                </button>
              ))}
            </div>

            {/* The journey, as BUCKETS. Bands taper by position so the shape
                reads as a funnel even where the numbers do not decline
                monotonically — real pipelines rarely do, and a mis-shaped
                funnel makes people distrust correct data. */}
            <div className="space-y-1.5">
              {buckets.map((b, i) => {
                const metric = sizeBy === 'count' ? b.count : b.value;
                const fill = Math.max(metric / max, metric > 0 ? 0.06 : 0);
                const taper = 1 - (i / Math.max(buckets.length, 2)) * 0.34;
                const colour = bandColour(i, buckets.length);
                const empty = b.count === 0;
                const on = hover === b.key;
                const open = openBucket === b.key;
                return (
                  <div key={b.key}>
                    <div
                      onMouseEnter={() => setHover(b.key)}
                      onMouseLeave={() => setHover('')}
                      onClick={() => setOpenBucket(open ? '' : b.key)}
                      className="group relative flex cursor-pointer items-center gap-3"
                    >
                      <div className="w-44 shrink-0 text-right">
                        <div className={'truncate text-xs font-semibold ' + (empty ? 'text-gray-400' : 'text-gray-800')}
                             title={b.label}>
                          <span className="mr-1 text-gray-400">{open ? '▾' : '▸'}</span>
                          {b.label}
                        </div>
                        <div className="text-[10px] text-gray-400">
                          {b.weight}% of journey · {Math.round(b.probability * 100)}% at exit
                        </div>
                      </div>

                      <div className="relative h-12 flex-1" style={{ paddingInline: `${(1 - taper) * 50}%` }}>
                        <div className="absolute inset-y-0 left-0 right-0 rounded-md bg-gray-100/70"
                             style={{ marginInline: `${(1 - taper) * 50}%` }} />
                        <div
                          className={'relative h-full rounded-md transition-all duration-200 '
                            + (on ? 'shadow-lg' : 'shadow-sm')}
                          style={{
                            width: `${Math.max(fill * 100, 0)}%`,
                            background: empty
                              ? 'repeating-linear-gradient(45deg,#F3F4F6,#F3F4F6 6px,#E9EBEE 6px,#E9EBEE 12px)'
                              : `linear-gradient(180deg, ${colour} 0%, ${colour} 42%, rgba(0,0,0,0.18) 100%), ${colour}`,
                            boxShadow: empty ? 'none'
                              : 'inset 0 1px 0 rgba(255,255,255,0.45), inset 0 -2px 6px rgba(0,0,0,0.18)',
                            transform: on ? 'translateY(-1px)' : 'none',
                          }}
                        >
                          {!empty && (
                            <div className="flex h-full items-center gap-2 px-3 text-white">
                              <span className="text-base font-semibold tabular-nums drop-shadow">{b.count}</span>
                              <span className="truncate text-[11px] opacity-90">KES {kes(b.value)}</span>
                            </div>
                          )}
                        </div>
                        {empty && (
                          <div className="pointer-events-none absolute inset-0 flex items-center px-3">
                            <span className="text-[11px] text-gray-400">no deals in this bucket</span>
                          </div>
                        )}
                      </div>

                      <div className="w-24 shrink-0 text-right">
                        <div className="text-[11px] tabular-nums text-gray-600">{b.steps.length} step{b.steps.length === 1 ? '' : 's'}</div>
                      </div>
                    </div>

                    {open && (
                      <div className="ml-44 mt-1 space-y-1 border-l-2 border-gray-200 pl-3">
                        {b.steps.map((st) => (
                          <div key={st.stage}
                               onClick={(e) => {
                                 // Drill on the MICRO-STEP, which is the real
                                 // stage a deal sits at. Stopping propagation
                                 // keeps the click from also collapsing the
                                 // bucket the user just opened.
                                 e.stopPropagation();
                                 if (st.count && onStageClick && flow) onStageClick(flow.flow, st.stage);
                               }}
                               className={'flex items-center gap-3 text-xs '
                                 + (st.count && onStageClick ? 'cursor-pointer hover:bg-gray-50' : '')}>
                            <span className="w-56 truncate text-gray-600" title={st.stage}>{st.stage}</span>
                            <span className="w-14 text-right tabular-nums text-gray-400">
                              {Math.round(st.probability * 100)}%
                            </span>
                            <div className="h-2 flex-1 overflow-hidden rounded-full bg-gray-100">
                              <div className="h-full rounded-full"
                                   style={{ width: `${b.count ? (st.count / Math.max(b.count, 1)) * 100 : 0}%`,
                                            background: colour }} />
                            </div>
                            <span className="w-10 text-right tabular-nums text-gray-700">{st.count}</span>
                            <span className="w-28 text-right tabular-nums text-gray-500">KES {kes(st.value)}</span>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                );
              })}
            </div>

            <div className="mt-3 flex flex-wrap items-center justify-between gap-2 border-t border-gray-100 pt-3 text-xs">
              <span className="text-gray-500">
                {flow?.deals ?? 0} deals · KES {kes(flow?.value ?? 0)} ·{' '}
                <span className="font-semibold text-gray-800">
                  KES {kes(flow?.weighted ?? 0)} weighted
                </span>
              </span>
              {(data.unplaced_deals ?? 0) > 0 && (
                <span className="rounded-full bg-[#FBEAF0] px-2.5 py-1 text-[11px] text-[#993556]">
                  {data.unplaced_deals} deal(s) sit at a stage no configured flow contains —
                  they are counted nowhere above
                </span>
              )}
            </div>

          </>
        )}
      </Card.Body>
    </Card>
  );
}
'''


def main():
    apply = "--apply" in sys.argv
    for p in (COMP, APITS, API):
        if not os.path.isfile(p):
            print("ABORT: %s not found - apply patch_f2_funnel_ui.py first." % p)
            return 1
    if not os.path.isfile(os.path.join("utils", "pipeline_funnel.py")):
        print("ABORT: apply patch_b1_stage_buckets.py first.")
        return 1

    api = open(API, encoding="utf-8").read()
    ts = open(APITS, encoding="utf-8").read()

    if '"buckets": buckets' in api:
        print("ABORT: the endpoint already returns buckets - B2 looks applied.")
        return 1
    if "bucket_view" not in open(os.path.join("utils", "pipeline_funnel.py"),
                                 encoding="utf-8").read():
        print("ABORT: bucket_view missing - apply patch_b1_stage_buckets.py first.")
        return 1

    i = api.index('@app.get("/api/pipeline/funnel")')
    j = api.index("from utils.api_branch_log import router as branch_log_router", i)
    api = api[:i] + ENDPOINT + api[j:]
    print("  ok  /api/pipeline/funnel returns buckets")

    a = ts.index("// \u2500\u2500 Defined funnel (journey from admin config + credit side layer) \u2500\u2500")
    b = ts.index("// \u2500\u2500 Cumulative leaderboard (staff / role / branch / unit) \u2500\u2500", a)
    ts = ts[:a] + TS_NEW + ts[b:]
    print("  ok  api.ts - bucket types")

    # post-checks
    if api.count('@app.get("/api/pipeline/funnel")') != 1:
        print("ABORT: post-check - funnel route count is not 1.")
        return 1
    if "credit_layer" in api[api.index('@app.get("/api/pipeline/funnel")'):
                             api.index("from utils.api_branch_log import")]:
        print("ABORT: post-check - the side layer survives in the endpoint.")
        return 1
    if "credit_layer" in COMPONENT:
        print("ABORT: post-check - the side layer survives in the component.")
        return 1
    if "onStageClick" not in COMPONENT or "st.stage)" not in COMPONENT:
        print("ABORT: post-check - the stage drill was not reconnected.")
        return 1
    if "unplaced_deals" not in api:
        print("ABORT: post-check - unplaced deals are no longer reported.")
        return 1
    for op, cl in (("{", "}"), ("(", ")")):
        if COMPONENT.count(op) != COMPONENT.count(cl):
            print("ABORT: component unbalanced %s%s." % (op, cl))
            return 1
    if "fetchBranchLogHistoryGrid" not in ts:
        print("ABORT: post-check - api.ts lost an existing client.")
        return 1
    print("  ok  post-checks: one journey, drill preserved, unplaced still reported")

    if not apply:
        print("\nDRY RUN - nothing written. Re-run with --apply.")
        return 0

    for path, content in ((API, api), (APITS, ts), (COMP, COMPONENT)):
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
