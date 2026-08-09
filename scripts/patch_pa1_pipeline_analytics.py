#!/usr/bin/env python
# -*- coding: utf-8 -*-
r"""
PA1 - pipeline analytics, closing the item left open from the analytics arc.

"we are yet to close on the pipeline analytics in a similar context" - so this
mirrors the index analytics: same period model (rolling days, or an explicit
calendar window for a quarter / year-to-date), and the same scope read, so the
two analytics pages cannot disagree about the same population.

THREE QUESTIONS, in the order management asks them:

  WHERE IS THE MONEY   open deals, open value, weighted, won, win rate.
      Weighted uses _deal_probability - the per-flow config model - so it agrees
      with the funnel and the headline rather than being a third calculation.

  WHERE DOES IT STALL  conversion through the journey, per flow, bar per bucket
      coloured by the SAME RAG health the funnel uses (average working days in
      bucket against that bucket's target). One health model, two views.

  WHERE DOES IT COME FROM  referred versus direct, by count, value and wins.
      A REFERRAL COUNTS ONLY ONCE ACCEPTED, matching the daily-log credit rule
      (ruling 2026-08-09) - a pending referral is an intention, not an outcome.
      Counting sent-but-unaccepted referrals here would have contradicted the
      index the same deal feeds.

ADDS
  GET /api/pipeline/analytics/summary?days=&start=&end=
  frontend .../components/PipelineAnalytics.tsx, mounted at the top of the
  existing Sales Pro Analytics page - above the SLA tiles, so the money question
  is answered before the exception list.

Nothing existing on that page is removed: the SLA tiles, product-class
pipelines, slicer and branch drill-down all remain.

Verified: py_compile clean, tsc --noEmit clean, vite build clean.

Usage (from project root, .venv active):
    python scripts\patch_pa1_pipeline_analytics.py            # dry run
    python scripts\patch_pa1_pipeline_analytics.py --apply    # write + .pre_pa1 backups
"""
import os
import shutil
import sys

COMP = os.path.join("frontend", "web", "src", "components", "PipelineAnalytics.tsx")
PAGE = os.path.join("frontend", "web", "src", "pages", "Analytics.tsx")
APITS = os.path.join("frontend", "web", "src", "lib", "api.ts")
API = os.path.join("utils", "api.py")
BACKUP_SUFFIX = ".pre_pa1"

ENDPOINT = r'''@app.get("/api/pipeline/analytics/summary")
def pipeline_analytics_summary(days: int = 30, start: str = "", end: str = "",
                               user: dict = Depends(get_current_user)):
    """Pipeline analytics over a reporting period, mirroring the index analytics.

    Same period model (rolling days, or an explicit calendar window for a
    quarter / year-to-date) and the same scope read, so the two analytics pages
    cannot disagree about the same population.

    Returns the journey conversion by bucket, the referred-vs-direct split, and
    the win/loss picture.
    """
    from datetime import date as _date, timedelta as _td
    from utils.pipeline_funnel import (
        stage_flows, flow_for_deal, bucket_view, micro_steps,
    )

    deals = _acquire_scoped_deals(user)

    if start or end:
        lo = str(start or "0000-01-01")[:10]
        hi = str(end or "9999-12-31")[:10]
    else:
        hi = _date.today().isoformat()
        lo = (_date.today() - _td(days=max(int(days or 30), 1))).isoformat()

    def _when(d):
        return str(d.get("created_at") or d.get("open_date") or "")[:10]

    live = [d for d in deals
            if not d.get("draft") and lo <= (_when(d) or lo) <= hi]

    won = [d for d in live if str(d.get("stage")) == "Closed Won"]
    lost = [d for d in live if str(d.get("stage")) == "Closed Lost"]
    open_deals = [d for d in live if str(d.get("stage")) not in ("Closed Won", "Closed Lost")]

    def _val(d):
        try:
            return float(d.get("amount_kes") or d.get("deal_value") or 0)
        except (TypeError, ValueError):
            return 0.0

    # Journey conversion, per flow, using the SAME bucket view the funnel draws
    # so the two can never show different counts for the same stage.
    journey = []
    for flow in (stage_flows() or {}):
        mine = [d for d in open_deals if flow_for_deal(d) == flow]
        if not mine:
            continue
        journey.append({"flow": flow, "buckets": bucket_view(mine, flow),
                        "deals": len(mine)})
    journey.sort(key=lambda f: -f["deals"])

    # Referred vs direct. A referral is only counted once it has been ACCEPTED,
    # matching the daily-log credit rule - a pending referral is an intention.
    def _is_ref(d):
        return bool(d.get("is_referral")) and str(d.get("referral_status") or "") == "accepted"

    referred = [d for d in live if _is_ref(d)]
    direct = [d for d in live if not _is_ref(d)]
    origin = [
        {"origin": "Referred", "count": len(referred),
         "value": round(sum(_val(d) for d in referred), 2),
         "won": sum(1 for d in referred if str(d.get("stage")) == "Closed Won")},
        {"origin": "Direct", "count": len(direct),
         "value": round(sum(_val(d) for d in direct), 2),
         "won": sum(1 for d in direct if str(d.get("stage")) == "Closed Won")},
    ]

    closed = len(won) + len(lost)
    return {
        "start": lo, "end": hi, "days": days,
        "totals": {
            "deals": len(live),
            "open": len(open_deals),
            "won": len(won),
            "lost": len(lost),
            "open_value": round(sum(_val(d) for d in open_deals), 2),
            "won_value": round(sum(_val(d) for d in won), 2),
            "weighted": round(sum(_val(d) * _deal_probability(d) for d in open_deals), 2),
            "win_rate": round(len(won) / closed * 100, 1) if closed else 0.0,
        },
        "journey": journey,
        "origin": origin,
    }


'''

TS_NEW = r'''export interface PipelineOriginSplit {
  origin: string; count: number; value: number; won: number;
}
export interface PipelineJourneyFlow {
  flow: string; deals: number; buckets: DefinedBucket[];
}
export interface PipelineAnalyticsSummary {
  start: string; end: string; days: number;
  totals: {
    deals: number; open: number; won: number; lost: number;
    open_value: number; won_value: number; weighted: number; win_rate: number;
  };
  journey: PipelineJourneyFlow[];
  origin: PipelineOriginSplit[];
}
export async function fetchPipelineAnalyticsSummary(
  days = 30, start = '', end = '',
): Promise<PipelineAnalyticsSummary> {
  const q = new URLSearchParams();
  if (days) q.set('days', String(days));
  if (start) q.set('start', start);
  if (end) q.set('end', end);
  return getJson<PipelineAnalyticsSummary>(`/pipeline/analytics/summary?${q.toString()}`);
}

'''

COMPONENT = r'''// PipelineAnalytics — the pipeline counterpart to the index analytics.
//
// Same period model, same scope read, so the two pages cannot disagree about
// the same population. Three questions, in the order management asks them:
//
//   Where is the money        open / weighted / won, and the win rate
//   Where does it stall       conversion through the journey, RAG per bucket
//   Where does it come from   referred versus direct

import { useCallback, useEffect, useState } from 'react';
import { Card } from '@/components/Card';
import { useToast } from '@/components/Toast';
import {
  fetchPipelineAnalyticsSummary, type PipelineAnalyticsSummary,
} from '@/lib/api';
import { periods, findPeriod, periodArgs, DEFAULT_PERIOD_KEY } from '@/lib/period';

function kes(n: number): string {
  if (!n) return '—';
  return Math.round(n).toLocaleString();
}

const RAG: Record<string, string> = {
  green: '#669438', amber: '#E0A02B', red: '#C4536F', idle: '#D8DBDF',
};

export default function PipelineAnalytics() {
  const { toast } = useToast();
  const [periodKey, setPeriodKey] = useState(DEFAULT_PERIOD_KEY);
  const [data, setData] = useState<PipelineAnalyticsSummary | null>(null);
  const [loading, setLoading] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const a = periodArgs(findPeriod(periodKey));
      setData(await fetchPipelineAnalyticsSummary(a.days ?? 0, a.start ?? '', a.end ?? ''));
    } catch (e) {
      toast({ tone: 'danger', message: e instanceof Error ? e.message : 'Could not load pipeline analytics.' });
      setData(null);
    } finally {
      setLoading(false);
    }
  }, [periodKey, toast]);

  useEffect(() => { void load(); }, [load]);

  const t = data?.totals;
  const originTotal = (data?.origin ?? []).reduce((a, o) => a + o.count, 0);

  return (
    <div className="space-y-4">
      <Card>
        <Card.Header>
          <div className="flex flex-wrap items-center justify-between gap-3">
            <h2 className="text-base font-semibold text-gray-900">Pipeline analytics</h2>
            <select value={periodKey} onChange={(e) => setPeriodKey(e.target.value)}
                    className="rounded border border-gray-200 px-2 py-1 text-xs">
              {periods().map((p) => <option key={p.key} value={p.key}>{p.label}</option>)}
            </select>
          </div>
        </Card.Header>
        <Card.Body>
          {loading && <p className="py-8 text-center text-sm text-gray-400">Loading…</p>}

          {!loading && !t && (
            <p className="py-8 text-center text-sm text-gray-400">No pipeline data for this period.</p>
          )}

          {!loading && t && (
            <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
              {[
                { label: 'Open deals', value: t.open.toLocaleString(), tone: 'text-gray-900' },
                { label: 'Open value (KES)', value: kes(t.open_value), tone: 'text-[#0082BB]' },
                { label: 'Weighted (KES)', value: kes(t.weighted), tone: 'text-[#005B82]' },
                { label: 'Won (KES)', value: kes(t.won_value), tone: 'text-[#3B6D11]' },
                { label: 'Won', value: t.won.toLocaleString(), tone: 'text-[#3B6D11]' },
                { label: 'Lost', value: t.lost.toLocaleString(), tone: 'text-rose-600' },
                { label: 'Win rate', value: `${t.win_rate}%`, tone: 'text-gray-900' },
                { label: 'Deals in period', value: t.deals.toLocaleString(), tone: 'text-gray-900' },
              ].map((s) => (
                <div key={s.label} className="rounded-lg border border-gray-200 p-3">
                  <div className={`text-xl font-semibold tabular-nums ${s.tone}`}>{s.value}</div>
                  <div className="mt-0.5 text-[11px] text-gray-500">{s.label}</div>
                </div>
              ))}
            </div>
          )}
        </Card.Body>
      </Card>

      {!loading && (data?.journey ?? []).length > 0 && (
        <Card>
          <Card.Header>
            <h2 className="text-base font-semibold text-gray-900">Conversion through the journey</h2>
          </Card.Header>
          <Card.Body>
            <div className="space-y-5">
              {(data?.journey ?? []).map((f) => {
                const max = Math.max(1, ...f.buckets.map((b) => b.count));
                return (
                  <div key={f.flow}>
                    <div className="mb-1.5 flex items-baseline gap-2">
                      <span className="text-xs font-semibold capitalize text-gray-800">{f.flow}</span>
                      <span className="text-[11px] text-gray-400">{f.deals} open</span>
                    </div>
                    <div className="space-y-1">
                      {f.buckets.map((b) => (
                        <div key={b.key} className="flex items-center gap-2">
                          <span className="w-44 shrink-0 truncate text-[11px] text-gray-600"
                                title={b.label}>{b.label}</span>
                          <div className="h-4 flex-1 overflow-hidden rounded bg-gray-100">
                            <div className="h-full rounded"
                                 style={{ width: `${(b.count / max) * 100}%`,
                                          background: RAG[b.health.status] || RAG.idle }} />
                          </div>
                          <span className="w-10 shrink-0 text-right text-[11px] tabular-nums text-gray-700">
                            {b.count || '—'}
                          </span>
                          <span className="w-28 shrink-0 text-right text-[11px] tabular-nums text-gray-500">
                            {kes(b.value)}
                          </span>
                          <span className="w-24 shrink-0 text-right text-[10px] tabular-nums"
                                style={{ color: RAG[b.health.status] || RAG.idle }}>
                            {b.health.status === 'idle'
                              ? '—'
                              : `${b.health.avg_days}d / ${b.health.target_days}d`}
                          </span>
                        </div>
                      ))}
                    </div>
                  </div>
                );
              })}
            </div>
          </Card.Body>
        </Card>
      )}

      {!loading && originTotal > 0 && (
        <Card>
          <Card.Header>
            <h2 className="text-base font-semibold text-gray-900">Referred vs direct</h2>
          </Card.Header>
          <Card.Body>
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
              {(data?.origin ?? []).map((o) => (
                <div key={o.origin} className="rounded-lg border border-gray-200 p-3">
                  <div className="flex items-baseline justify-between">
                    <span className="text-sm font-semibold text-gray-800">{o.origin}</span>
                    <span className="text-xs tabular-nums text-gray-500">
                      {originTotal ? Math.round((o.count / originTotal) * 100) : 0}%
                    </span>
                  </div>
                  <div className="mt-1 h-2 overflow-hidden rounded-full bg-gray-100">
                    <div className="h-full rounded-full"
                         style={{ width: `${originTotal ? (o.count / originTotal) * 100 : 0}%`,
                                  background: o.origin === 'Referred' ? '#0082BB' : '#979797' }} />
                  </div>
                  <div className="mt-2 flex gap-4 text-[11px] tabular-nums text-gray-600">
                    <span>{o.count} deals</span>
                    <span>KES {kes(o.value)}</span>
                    <span className="text-[#3B6D11]">{o.won} won</span>
                  </div>
                </div>
              ))}
            </div>
          </Card.Body>
        </Card>
      )}
    </div>
  );
}
'''

PAGE_NEW = r'''// #3b — Analytics page. Consumes /api/pipeline/analytics (KES-equivalent,
// dashboard-consistent) and showcases the pipeline across products, sectors,
// currency book, the conversion funnel, and the four product-class pipelines.

import { useMemo, useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAnalytics } from '@/hooks/useAnalytics';
import { fetchPipelineDrill, fetchSlaViolations } from '@/lib/api';
import type { UnitBreakdown, PipelineDrillResponse, ProductFunnel, ProbabilityBandBreakdown, ReferralDepartmentBreakdown } from '@/types/pipeline';
import { useBranding } from '@/hooks/useBranding';
import { Card } from '@/components/Card';
import { Badge, type BadgeTone } from '@/components/Badge';
import { PageHeader } from '@/components/PageHeader';
import PipelineAnalytics from '@/components/PipelineAnalytics';
import { Skeleton } from '@/components/Skeleton';
import { CategoryBarChart } from '@/components/charts/CategoryBarChart';
import { DonutChart } from '@/components/charts/DonutChart';

function abbrev(n: number): string {
  return n.toLocaleString();
}

function Stat({ label, value, sub }: { label: string; value: string; sub?: string }) {
  return (
    <Card>
      <Card.Body>
        <div className="text-xs uppercase tracking-wider text-gray-500">{label}</div>
        <div className="text-2xl font-semibold text-gray-900 mt-1">{value}</div>
        {sub && <div className="text-xs text-gray-500 mt-1">{sub}</div>}
      </Card.Body>
    </Card>
  );
}

function SlaSummaryCard() {
  const navigate = useNavigate();
  const [bs, setBs] = useState<{ on_track: number; due_soon: number; breached: number } | null>(null);
  useEffect(() => {
    fetchSlaViolations().then((v) => setBs(v.by_state ?? null)).catch(() => setBs(null));
  }, []);
  if (!bs) return null;
  const tiles: { key: 'on_track' | 'due_soon' | 'breached'; label: string; n: number; tone: BadgeTone }[] = [
    { key: 'on_track', label: 'On track', n: bs.on_track ?? 0, tone: 'success' },
    { key: 'due_soon', label: 'Due soon', n: bs.due_soon ?? 0, tone: 'warning' },
    { key: 'breached', label: 'Breached', n: bs.breached ?? 0, tone: 'danger' },
  ];
  return (
    <Card className="mt-4"><Card.Body>
      <div className="flex items-center justify-between mb-3">
        <h2 className="text-xs font-semibold uppercase tracking-wider text-gray-500">SLA status across your pipeline</h2>
        <span className="text-xs text-gray-400">click a tile to view those deals</span>
      </div>
      <div className="grid grid-cols-3 gap-3">
        {tiles.map((t) => (
          <button
            key={t.key}
            type="button"
            onClick={() => navigate(`/pipeline?sla=${t.key}`)}
            className="rounded-lg border border-gray-200 p-4 text-left transition hover:border-gray-300 hover:shadow-sm"
          >
            <div className="text-2xl font-bold text-gray-900 tabular-nums">{t.n.toLocaleString()}</div>
            <div className="mt-1"><Badge tone={t.tone} size="sm">{t.label}</Badge></div>
          </button>
        ))}
      </div>
    </Card.Body></Card>
  );
}

export function Analytics() {
  const { branding } = useBranding();
  const { data, loading, error } = useAnalytics();
  const sym = branding?.currency_symbol ?? 'KES';
  const kes = (n: number) => `${sym} ${abbrev(n)}`;

  if (loading) {
    return (
      <div className="p-6 max-w-7xl 2xl:max-w-[1680px] mx-auto space-y-4">
        <Skeleton /><Skeleton /><Skeleton />
      </div>
    );
  }
  if (error || !data) {
    return (
      <div className="p-6 max-w-7xl 2xl:max-w-[1680px] mx-auto">
        <Card><Card.Body>
          <p className="text-sm text-red-600">{error ?? 'No analytics available.'}</p>
        </Card.Body></Card>
      </div>
    );
  }

  const t = data.totals;
  const buckets = [
    { key: 'asset',     b: data.pipelines.asset },
    { key: 'liability', b: data.pipelines.liability },
    { key: 'insurance', b: data.pipelines.insurance },
    { key: 'other',     b: data.pipelines.other },
  ];

  // Model A — slice the pipeline by a chosen dimension. Each dimension maps to
  // a normalized [{label, value, count}] list. Branch/RM may be thin until the
  // pipeline carries populated unit/RM data (see seed-data note).
  const DIMENSIONS = ['Product', 'Segment', 'Sector', 'Stage', 'Product Funnel', 'Probability', 'Currency', 'Branch', 'RM', 'Departments'] as const;
  type Dimension = typeof DIMENSIONS[number];

  const sliceFor = (dim: Dimension): { label: string; value: number; count: number }[] => {
    switch (dim) {
      case 'Product':
        return (data.by_product ?? []).map((x) => ({ label: x.product, value: x.value, count: x.count }));
      case 'Sector':
        return (data.by_sector ?? []).map((x) => ({ label: x.sector, value: x.value, count: x.count }));
      case 'Segment':
        return (data.by_segment ?? []).map((x) => ({ label: x.segment, value: x.value, count: x.count }));
      case 'Stage':
        return (data.funnel ?? []).map((x) => ({ label: x.stage, value: x.value, count: x.count }));
      case 'Probability':
        return (data.by_probability_band ?? []).map((x) => ({ label: x.band, value: x.value, count: x.count }));
      case 'Product Funnel':
        // Handled specially in the slicer (needs a product picker); return empty here.
        return [];
      case 'Currency': {
        const cb = data.by_currency_book;
        return cb ? [
          { label: 'Local (LCY)',   value: cb.LCY?.value ?? 0, count: cb.LCY?.count ?? 0 },
          { label: 'Foreign (FCY)', value: cb.FCY?.value ?? 0, count: cb.FCY?.count ?? 0 },
        ] : [];
      }
      case 'Branch':
        return (data.by_unit ?? []).map((x) => ({ label: x.unit, value: x.value, count: x.count }));
      case 'RM':
        return (data.by_rm ?? []).map((x) => ({ label: x.rm, value: x.value, count: x.count }));
      case 'Departments':
        // Handled specially in the slicer (two-level dept -> referrers); return empty here.
        return [];
    }
  };

  return (
    <>
      <PageHeader
        ribbon
        breadcrumbs={[{ label: 'A2Z Pipeline Intelligence System (PIS)' }, { label: 'A2Z Sales Pro Analytics' }]}
        title="A2Z Sales Pro Analytics"
        subtitle="Assured pipeline value, in KES."
      />
      <div className="p-6 max-w-7xl 2xl:max-w-[1680px] mx-auto">

      <PipelineAnalytics />

      {/* Headline KPIs */}
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-4">
        <Stat label="Assured Value" value={kes(t.total_value)}
              sub={`${kes(t.pending_value)} pending assurance`} />
        <Stat label="Weighted" value={kes(t.weighted_value)} />
        <Stat label="Closed-Won" value={kes(t.won_value)} sub={`${t.won_count} won`} />
        <Stat label="Win Rate" value={`${t.win_rate}%`} sub={`${t.lost_count} lost`} />
        <Stat label="Live Deals" value={t.live_count.toLocaleString()}
              sub={`${t.active_count} active`} />
      </div>

      {/* Model A slicer */}
      <PipelineSlicer dimensions={DIMENSIONS} sliceFor={sliceFor} kes={kes} productFunnels={data.by_product_funnel ?? []} probabilityBands={data.by_probability_band ?? []} referralDepartments={data.by_referral_department ?? []} referralBranchSplit={data.referral_branch_split} referralVsOriginated={data.referral_vs_originated} />

      {/* SLA status summary — click a tile to open the filtered Sales Pro list */}
      <SlaSummaryCard />

      {/* Click-to-drill: branch -> RM -> individual deals */}
      <BranchDrill branches={data.by_unit ?? []} kes={kes} />

      {/* Product-class pipelines */}
      <h2 className="text-xs font-semibold uppercase tracking-wider text-gray-500 mt-8 mb-3">
        Pipelines by Product Class
      </h2>
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        {buckets.map(({ key, b }) => (
          <Card key={key} stripe="primary">
            <Card.Body>
              <div className="text-sm font-medium text-gray-900">{b.label}</div>
              <div className="text-xl font-semibold mt-1">{kes(b.value)}</div>
              <div className="text-xs text-gray-500 mt-1">
                {b.active_count} active · {kes(b.won_value)} won
              </div>
            </Card.Body>
          </Card>
        ))}
      </div>
    </div>
    </>
  );
}

// ── Model A: pick a dimension, see the pipeline sliced by it ─────────────
function PipelineSlicer({
  dimensions, sliceFor, kes, productFunnels, probabilityBands, referralDepartments, referralBranchSplit, referralVsOriginated,
}: {
  dimensions: readonly string[];
  sliceFor: (d: never) => { label: string; value: number; count: number }[];
  kes: (n: number) => string;
  productFunnels: ProductFunnel[];
  probabilityBands: ProbabilityBandBreakdown[];
  referralDepartments: ReferralDepartmentBreakdown[];
  referralBranchSplit?: { in_branch: number; cross_branch: number };
  referralVsOriginated?: {
    open:   { referred: { count: number; value: number }; originated: { count: number; value: number } };
    closed: { referred: { count: number; value: number }; originated: { count: number; value: number } };
  };
}) {
  const [dim, setDim] = useState<string>('Product');
  const [expandedBand, setExpandedBand] = useState<string | null>(null);
  const [expandedDept, setExpandedDept] = useState<string | null>(null);
  const [pfProduct, setPfProduct] = useState<string>('');
  // Default the product-funnel picker to the highest-value product.
  const activePf = useMemo(() => {
    if (!productFunnels.length) return null;
    return productFunnels.find((p) => p.product === pfProduct) ?? productFunnels[0];
  }, [productFunnels, pfProduct]);
  // Stage renders as a funnel (server/flow order preserved); Sector & Currency
  // as donuts (share); everything else as ranked bars (value-sorted).
  const isProductFunnel = dim === 'Product Funnel';
  const isProbability = dim === 'Probability';
  const isReferralDept = dim === 'Departments';
  const isFunnel = dim === 'Stage' || isProductFunnel;
  const isDonut = dim === 'Sector' || dim === 'Segment' || dim === 'Currency';
  const rows = useMemo(() => {
    if (isProductFunnel) {
      return (activePf?.funnel ?? []).map((f) => ({
        label: f.win_probability != null ? `${f.stage} · ${f.win_probability}%` : f.stage,
        value: f.value,
        count: f.count,
      }));
    }
    const raw = sliceFor(dim as never);
    return isFunnel ? raw : raw.slice().sort((a, b) => b.value - a.value);
  }, [dim, sliceFor, isFunnel, isProductFunnel, activePf]);
  const total = useMemo(() => rows.reduce((s, r) => s + r.value, 0), [rows]);

  // Donut: top 8 slices + "Others" so 14 sectors don't clutter.
  const donutData = useMemo(() => {
    const top = rows.slice(0, 8).map((r) => ({ name: r.label, value: r.value }));
    const rest = rows.slice(8).reduce((s, r) => s + r.value, 0);
    return rest > 0 ? [...top, { name: 'Others', value: rest }] : top;
  }, [rows]);
  const barData = rows.slice(0, 12).map((r) => ({ label: r.label, value: r.value }));
  const funnelMax = rows.length ? Math.max(...rows.map((r) => r.value)) : 0;

  return (
    <>
      <div className="flex items-center justify-between mt-8 mb-3 flex-wrap gap-3">
        <h2 className="text-xs font-semibold uppercase tracking-wider text-gray-500">
          Slice pipeline by
        </h2>
        <div className="inline-flex rounded-lg border border-gray-200 overflow-hidden">
          {dimensions.map((d) => (
            <button
              key={d}
              onClick={() => setDim(d)}
              className={`px-3 py-1.5 text-sm transition-colors ${
                dim === d ? 'bg-brand-primary text-white' : 'bg-white text-gray-600 hover:bg-gray-50'
              }`}
            >
              {d}
            </button>
          ))}
        </div>
      </div>
      <Card><Card.Body>
        {isProductFunnel && productFunnels.length > 0 && (
          <div className="mb-4 flex items-center gap-2">
            <label className="text-sm text-gray-600">Product:</label>
            <select
              value={activePf?.product ?? ''}
              onChange={(e) => setPfProduct(e.target.value)}
              className="h-9 px-3 rounded-md border border-gray-300 bg-white text-sm text-gray-900 focus:outline-none focus:border-brand-primary focus:ring-2 focus:ring-brand-primary/20"
            >
              {productFunnels.map((p) => (
                <option key={p.product} value={p.product}>{p.product} ({p.active_count})</option>
              ))}
            </select>
          </div>
        )}
        {isReferralDept ? (
          referralDepartments.length === 0 ? (
            <p className="text-sm text-gray-500">No referral activity yet. Referrals appear here grouped by the receiving department.</p>
          ) : (
            <div className="space-y-2">
              {/* Referred-vs-Originated donut + In/Cross-branch split — the shadow-reporting overview */}
              {(referralVsOriginated || referralBranchSplit) && (
                <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 mb-4">
                  {referralVsOriginated && (
                    <div className="rounded border p-3">
                      <p className="text-xs font-medium text-gray-600 mb-2">Referred vs Originated (open pipeline)</p>
                      <DonutChart height={200}
                        data={[
                          { name: 'Referred',   value: referralVsOriginated.open.referred.value },
                          { name: 'Originated', value: referralVsOriginated.open.originated.value },
                        ]}
                        centerLabel="Deals"
                        centerValue={String(referralVsOriginated.open.referred.count + referralVsOriginated.open.originated.count)} />
                      <p className="mt-2 text-[11px] text-gray-500">
                        Closed-won: {referralVsOriginated.closed.referred.count} referred · {referralVsOriginated.closed.originated.count} originated
                        ({kes(referralVsOriginated.closed.referred.value)} vs {kes(referralVsOriginated.closed.originated.value)})
                      </p>
                    </div>
                  )}
                  {referralBranchSplit && (
                    <div className="rounded border p-3">
                      <p className="text-xs font-medium text-gray-600 mb-2">In-Branch vs Cross-Branch referrals</p>
                      <DonutChart height={200}
                        data={[
                          { name: 'In-Branch',    value: referralBranchSplit.in_branch },
                          { name: 'Cross-Branch', value: referralBranchSplit.cross_branch },
                        ]}
                        centerLabel="Referrals"
                        centerValue={String(referralBranchSplit.in_branch + referralBranchSplit.cross_branch)} />
                      <p className="mt-2 text-[11px] text-gray-500">
                        {referralBranchSplit.in_branch} stayed in-branch · {referralBranchSplit.cross_branch} crossed branches
                      </p>
                    </div>
                  )}
                </div>
              )}
              <p className="text-xs text-gray-500 mb-2">Per department: referrals <span className="font-medium">received</span> (bar) and <span className="text-emerald-700 font-medium">referred out</span> (support units' contribution), with head count. Click to see who referred in.</p>
              {(() => {
                const _sortedDepts = [...referralDepartments].sort((a, b) => (b.count + b.referred_out) - (a.count + a.referred_out));
                const maxV = Math.max(...referralDepartments.map((r) => Math.max(r.value, r.referred_out_value)), 0);
                return _sortedDepts.map((r) => {
                  const pct = maxV > 0 ? (r.value / maxV) * 100 : 0;
                  const open = expandedDept === r.department;
                  return (
                    <div key={r.department} className="rounded border">
                      <button type="button" onClick={() => setExpandedDept(open ? null : r.department)}
                        className="w-full flex items-center gap-3 p-2 text-left hover:bg-gray-50">
                        <span className="w-44 shrink-0 text-xs font-medium text-gray-700 truncate">{r.department}</span>
                        <span className="flex-1 bg-gray-100 rounded">
                          <span className="block h-6 rounded flex items-center justify-end px-2 text-[11px] text-white tabular-nums"
                            style={{ width: `${Math.max(pct, 8)}%`, background: 'var(--brand-primary, #0082BB)' }}>
                            {r.count} ref{r.count === 1 ? '' : 's'}
                          </span>
                        </span>
                        <span className="w-24 shrink-0 text-right text-[11px] text-emerald-700 tabular-nums" title="referrals sent out by this department">{r.referred_out} out</span>
                        <span className="w-28 shrink-0 text-right text-[11px] text-gray-500 tabular-nums">{r.in_branch}·in / {r.cross_branch}·cross</span>
                        <span className="w-20 shrink-0 text-right text-[11px] text-gray-500 tabular-nums">{r.head_count} staff</span>
                        <span className="w-24 shrink-0 text-right text-xs text-gray-600 tabular-nums">{kes(r.value)}</span>
                        <span className="w-4 shrink-0 text-xs text-gray-400">{open ? '▾' : '▸'}</span>
                      </button>
                      {open && (r.referrers ?? []).length > 0 && (
                        <div className="border-t bg-gray-50 px-3 py-2 space-y-1">
                          <p className="text-[11px] font-medium text-gray-500 mb-1">Referred in by:</p>
                          {(r.referrers ?? []).map((rf, i) => (
                            <div key={`${rf.referrer}-${i}`} className="flex items-center gap-2 text-xs text-gray-600">
                              <span className="flex-1">{rf.referrer}</span>
                              <span className="tabular-nums">{rf.count} ref{rf.count === 1 ? '' : 's'}</span>
                              <span className="w-24 text-right tabular-nums">{kes(rf.value)}</span>
                            </div>
                          ))}
                        </div>
                      )}
                    </div>
                  );
                });
              })()}
            </div>
          )
        ) : isProbability ? (
          probabilityBands.length === 0 ? (
            <p className="text-sm text-gray-500">No probability data yet — win % is set per product stage in Admin.</p>
          ) : (
            <div className="space-y-2">
              <p className="text-xs text-gray-500 mb-2">Win-probability bands (consistent across all products). Click a band to see the stages within it.</p>
              {(() => {
                const maxV = Math.max(...probabilityBands.map((b) => b.value), 0);
                return probabilityBands.map((b) => {
                  const bpct = maxV > 0 ? (b.value / maxV) * 100 : 0;
                  const open = expandedBand === b.band;
                  return (
                    <div key={b.band} className="rounded border">
                      <button type="button" onClick={() => setExpandedBand(open ? null : b.band)}
                        className="w-full flex items-center gap-3 p-2 text-left hover:bg-gray-50">
                        <span className="w-16 shrink-0 text-xs font-medium text-gray-700">{b.band}</span>
                        <span className="flex-1 bg-gray-100 rounded">
                          <span className="block h-6 rounded flex items-center justify-end px-2 text-[11px] text-white tabular-nums"
                            style={{ width: `${Math.max(bpct, 8)}%`, background: 'var(--brand-primary, #0082BB)' }}>
                            {b.count}
                          </span>
                        </span>
                        <span className="w-24 shrink-0 text-right text-xs text-gray-600 tabular-nums">{kes(b.value)}</span>
                        <span className="w-4 shrink-0 text-xs text-gray-400">{open ? '▾' : '▸'}</span>
                      </button>
                      {open && (b.stages ?? []).length > 0 && (
                        <div className="border-t bg-gray-50 px-3 py-2 space-y-1">
                          {(b.stages ?? []).map((st, i) => (
                            <div key={`${st.stage}-${st.product}-${i}`} className="flex items-center gap-2 text-xs text-gray-600">
                              <span className="flex-1">{st.stage} <span className="text-gray-400">· {st.product}</span>{st.win_probability != null ? ` · ${st.win_probability}%` : ''}</span>
                              <span className="tabular-nums">{st.count} deal{st.count === 1 ? '' : 's'}</span>
                              <span className="w-24 text-right tabular-nums">{kes(st.value)}</span>
                            </div>
                          ))}
                        </div>
                      )}
                    </div>
                  );
                });
              })()}
            </div>
          )
        ) : rows.length === 0 ? (
          <p className="text-sm text-gray-500">No data for this dimension yet.</p>
        ) : (
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            <div>
              {isDonut && (
                <DonutChart data={donutData} height={300}
                            centerLabel="Total" centerValue={abbrev(total)} />
              )}
              {isFunnel && (
                <div className="space-y-1.5 py-2">
                  {rows.map((r, i) => {
                    const pct = funnelMax > 0 ? (r.value / funnelMax) * 100 : 0;
                    const share = total > 0 ? (r.value / total) * 100 : 0;
                    return (
                      <div key={r.label} className="flex items-center gap-3">
                        <div className="w-36 shrink-0 text-xs text-gray-600 text-right">{r.label}</div>
                        <div className="flex-1 bg-gray-100 rounded">
                          <div
                            className="h-7 rounded flex items-center justify-end px-2 text-[11px] text-white tabular-nums"
                            style={{
                              width: `${Math.max(pct, 6)}%`,
                              background: 'var(--brand-primary, #1797ce)',
                              opacity: 1 - i * 0.07,
                            }}
                          >
                            {share.toFixed(0)}%
                          </div>
                        </div>
                      </div>
                    );
                  })}
                </div>
              )}
              {!isDonut && !isFunnel && (
                <CategoryBarChart
                  data={barData as unknown as Array<Record<string, unknown>>}
                  xKey="label"
                  series={[{ key: 'value', label: 'Pipeline value' }]}
                  height={Math.max(220, barData.length * 26)}
                />
              )}
            </div>
            <div className="overflow-auto">
              <table className="w-full text-sm">
                <thead><tr className="text-left text-gray-500 border-b">
                  <th className="py-1 pr-3">{/* label */}</th>
                  <th className="py-1 pr-3 text-right">Value</th>
                  <th className="py-1 pr-3 text-right">Deals</th>
                  <th className="py-1 text-right">Share</th>
                </tr></thead>
                <tbody>
                  {rows.map((r) => (
                    <tr key={r.label} className="border-b last:border-0">
                      <td className="py-1 pr-3">{r.label}</td>
                      <td className="py-1 pr-3 text-right tabular-nums">{kes(r.value)}</td>
                      <td className="py-1 pr-3 text-right tabular-nums">{r.count}</td>
                      <td className="py-1 text-right tabular-nums">
                        {total > 0 ? `${((r.value / total) * 100).toFixed(1)}%` : '—'}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}
      </Card.Body></Card>
    </>
  );
}

// ── #8: click-to-drill — branch → RM → individual deals ──────────────────
function BranchDrill({ branches, kes }: { branches: UnitBreakdown[]; kes: (n: number) => string }) {
  const navigate = useNavigate();
  const [unit, setUnit] = useState<string | null>(null);
  const [rm, setRm] = useState<string | null>(null);
  const [data, setData] = useState<PipelineDrillResponse | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!unit) { setData(null); return; }
    let live = true;
    setLoading(true);
    fetchPipelineDrill(unit, rm ?? undefined)
      .then((d) => { if (live) setData(d); })
      .catch(() => { if (live) setData(null); })
      .finally(() => { if (live) setLoading(false); });
    return () => { live = false; };
  }, [unit, rm]);

  const crumb = 'text-brand-primary hover:underline';
  const here = 'font-semibold text-gray-900';

  return (
    <>
      <h2 className="text-xs font-semibold uppercase tracking-wider text-gray-500 mt-8 mb-3">
        Drill down · branch → RM → deals
      </h2>
      <Card><Card.Body>
        <div className="flex items-center gap-2 text-sm mb-4 flex-wrap">
          <button onClick={() => { setUnit(null); setRm(null); }}
                  className={unit ? crumb : here}>All branches</button>
          {unit && <><span className="text-gray-400">›</span>
            <button onClick={() => setRm(null)} className={rm ? crumb : here}>{unit}</button></>}
          {rm && <><span className="text-gray-400">›</span><span className={here}>{rm}</span></>}
        </div>

        {!unit && (
          branches.length === 0
            ? <p className="text-sm text-gray-500">No branch data yet.</p>
            : <DrillTable
                head={['Branch', 'Value', 'Deals']}
                rows={branches.slice().sort((a, b) => b.value - a.value).map((b) => ({
                  key: b.unit, cells: [b.unit, kes(b.value), String(b.count)],
                  onClick: () => setUnit(b.unit),
                }))} />
        )}

        {unit && !rm && (
          loading ? <Skeleton />
            : (data?.by_rm.length ?? 0) === 0
              ? <p className="text-sm text-gray-500">No RMs in this branch.</p>
              : <DrillTable
                  head={['Relationship Manager', 'Value', 'Deals']}
                  rows={(data?.by_rm ?? []).map((r) => ({
                    key: r.rm, cells: [r.rm, kes(r.value), String(r.count)],
                    onClick: () => setRm(r.rm),
                  }))} />
        )}

        {unit && rm && (
          loading ? <Skeleton />
            : (data?.deals.length ?? 0) === 0
              ? <p className="text-sm text-gray-500">No deals for this RM.</p>
              : <div className="overflow-auto max-h-96">
                  <table className="w-full text-sm">
                    <thead><tr className="text-left text-gray-500 border-b">
                      <th className="py-1 pr-3">Client</th>
                      <th className="py-1 pr-3">Product</th>
                      <th className="py-1 pr-3">Stage</th>
                      <th className="py-1 pr-3 text-right">Value</th>
                      <th className="py-1 text-right">Close</th>
                    </tr></thead>
                    <tbody>
                      {(data?.deals ?? []).map((d) => (
                        <tr key={d.id}
                            onClick={() => navigate(`/pipeline/${encodeURIComponent(d.id)}`)}
                            className="border-b last:border-0 cursor-pointer hover:bg-gray-50">
                          <td className="py-1 pr-3 text-brand-primary font-medium">{d.client_name}</td>
                          <td className="py-1 pr-3">{d.product_type}</td>
                          <td className="py-1 pr-3">{d.stage}</td>
                          <td className="py-1 pr-3 text-right tabular-nums">{kes(d.amount_kes)}</td>
                          <td className="py-1 text-right tabular-nums">{d.expected_close ?? '—'}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
        )}
      </Card.Body></Card>
    </>
  );
}

function DrillTable({ head, rows }: {
  head: string[];
  rows: { key: string; cells: string[]; onClick: () => void }[];
}) {
  return (
    <div className="overflow-auto max-h-96">
      <table className="w-full text-sm">
        <thead><tr className="text-left text-gray-500 border-b">
          {head.map((h, i) => (
            <th key={h} className={`py-1 pr-3 ${i === 0 ? '' : 'text-right'}`}>{h}</th>
          ))}
        </tr></thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.key}
                onClick={r.onClick}
                className="border-b last:border-0 cursor-pointer hover:bg-gray-50">
              {r.cells.map((c, i) => (
                <td key={i} className={`py-1.5 pr-3 tabular-nums ${
                  i === 0 ? 'text-brand-primary font-medium' : 'text-right'}`}>{c}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
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
        print("ABORT: %s already exists - PA1 looks applied." % COMP)
        return 1

    api = open(API, encoding="utf-8").read()
    ts = open(APITS, encoding="utf-8").read()

    if "/api/pipeline/analytics/summary" in api:
        print("ABORT: the summary endpoint is already registered.")
        return 1
    if "_deal_probability" not in api:
        print("ABORT: apply patch_f3_one_probability_model.py first - the weighted")
        print("       figure must use the one probability model.")
        return 1
    if "bucket_view" not in open(os.path.join("utils", "pipeline_funnel.py"),
                                 encoding="utf-8").read():
        print("ABORT: apply patch_b1_stage_buckets.py first.")
        return 1
    anchor = '@app.get("/api/pipeline/funnel")'
    if api.count(anchor) != 1:
        print("ABORT: funnel route anchor matched %d times." % api.count(anchor))
        return 1
    api = api.replace(anchor, ENDPOINT + anchor, 1)
    print("  ok  GET /api/pipeline/analytics/summary")

    ts_anchor = "export async function fetchPipelineDefinedFunnel()"
    if ts.count(ts_anchor) != 1:
        print("ABORT: api.ts anchor matched %d times." % ts.count(ts_anchor))
        return 1
    ts = ts.replace(ts_anchor, TS_NEW + ts_anchor, 1)
    print("  ok  api.ts - fetchPipelineAnalyticsSummary")

    # The page must gain the component AND its import, and lose nothing.
    for token in ("PipelineAnalytics", "import PipelineAnalytics"):
        if token not in PAGE_NEW:
            print("ABORT: the page is missing %r." % token)
            return 1
    for token in ("SLA status across your pipeline", "Pipelines by Product Class",
                  "Drill down"):
        if token not in PAGE_NEW:
            print("ABORT: the page lost %r - nothing existing should be removed." % token)
            return 1
    for name, blob in (("component", COMPONENT), ("page", PAGE_NEW)):
        for op, cl in (("{", "}"), ("(", ")")):
            if blob.count(op) != blob.count(cl):
                print("ABORT: %s unbalanced %s%s." % (name, op, cl))
                return 1
    if api.count('@app.get("/api/pipeline/analytics/summary")') != 1:
        print("ABORT: post-check - summary route count is not 1.")
        return 1
    print("  ok  post-checks: page intact, one new route")

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
