#!/usr/bin/env python
# -*- coding: utf-8 -*-
r"""
OR6 - Sales Pro Analytics gets ALL the origins, not referred-versus-own.

RULING (2026-08-11): "wire to the overall Sales Pro analytics page, to add to
the pie showing lead origin where we only had referral and own - this should now
have all the origin sources."

referral_vs_originated answers a two-way question the bank has outgrown.
"Originated" quietly lumps events, partnerships, lead generators and the
warehouse together as though they were one thing - which is precisely what the
seven-origin model exists to separate.

    ORIGIN becomes a slicer dimension, listed FIRST: where work came from is
    the question the model was built to answer.

SERVED FROM deal_origin.summarise - the SAME function the Origin Channels page
uses. Two implementations of "how much came from where" would drift, and the
first anyone would know is two pages disagreeing in a meeting.

COMPUTED FROM `active`, this function's own live non-draft list, so the origin
split cannot disagree with the product, stage or sector splits beside it. The
first draft passed a variable that does not exist in that scope - it would have
failed into the except and returned an empty split silently, which is the
failure mode this codebase keeps having to unlearn.

EVERY CONFIGURED ORIGIN APPEARS, including empty ones - an origin producing no
deals is a finding, not a row to hide.

referral_vs_originated IS LEFT IN PLACE. Existing callers depend on it, and
removing it in the same change would turn an addition into a migration.

NOTE FOR RELEASES: Analytics.tsx is on the alex-dev delta list, so this stays on
our side unless that ruling changes.

Verified: py_compile clean, tsc --noEmit clean, vite build clean.

Usage (from project root, .venv active):
    python scripts\patch_or6_analytics_origins.py            # dry run
    python scripts\patch_or6_analytics_origins.py --apply
"""
import os
import shutil
import sys

API = os.path.join("utils", "api.py")
PAGE = os.path.join("frontend", "web", "src", "pages", "Analytics.tsx")
TYPES = os.path.join("frontend", "web", "src", "types", "pipeline.ts")
BACKUP_SUFFIX = ".pre_or6"

RETURN_ANCHOR = '        "referral_vs_originated": {"open": _rvo_open, "closed": _rvo_closed},\n    }'
RETURN_NEW = '''        "referral_vs_originated": {"open": _rvo_open, "closed": _rvo_closed},
        # ORIGIN, ALL OF THEM (2026-08-11). Served from deal_origin.summarise -
        # the same function the channels page uses - so the two cannot disagree
        # about how much came from where.
        "by_origin": _origin_split,
    }'''

TYPE_OLD = "  by_referral_department?: ReferralDepartmentBreakdown[];"
TYPE_NEW = '''  by_referral_department?: ReferralDepartmentBreakdown[];
  /** Every configured deal origin, with its readable label. Replaces the
   *  referred-vs-originated pair as the way to ask where work came from. */
  by_origin?: { origin: string; label?: string; credits_party?: boolean;
                count: number; value: number; won: number }[];'''

SEGMENT = r'''    try:
        from utils.deal_origin import summarise as _summarise_origin
        # `active` is this function's live, non-draft list - the same deals
        # every other breakdown here is computed from, so the origin split
        # cannot disagree with the product or stage splits beside it.
        _origin_split = _summarise_origin(active)
    except Exception as _exc:
        logger.warning("origin split unavailable: %s", _exc)
        _origin_split = []

'''

PAGE_SRC = r'''// #3b — Analytics page. Consumes /api/pipeline/analytics (KES-equivalent,
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
import { Skeleton } from '@/components/Skeleton';
import { CategoryBarChart } from '@/components/charts/CategoryBarChart';
import { DonutChart } from '@/components/charts/DonutChart';

function abbrev(n: number): string {
  const a = Math.abs(n);
  if (a >= 1e12) return (n / 1e12).toFixed(2) + 'T';
  if (a >= 1e9)  return (n / 1e9).toFixed(2) + 'B';
  if (a >= 1e6)  return (n / 1e6).toFixed(1) + 'M';
  if (a >= 1e3)  return (n / 1e3).toFixed(1) + 'K';
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
  // ORIGIN sits first: where work came from is the question the seven-origin
  // model exists to answer, and it was previously reduced to referred-vs-own.
  const DIMENSIONS = ['Origin', 'Product', 'Segment', 'Sector', 'Stage', 'Product Funnel', 'Probability', 'Currency', 'Branch', 'RM', 'Departments'] as const;
  type Dimension = typeof DIMENSIONS[number];

  const sliceFor = (dim: Dimension): { label: string; value: number; count: number }[] => {
    switch (dim) {
      case 'Origin':
        // Every configured origin, including those with nothing in them - an
        // origin producing no deals is a finding, not a row to hide.
        return (data.by_origin ?? []).map((x) => ({
          label: x.label || x.origin, value: x.value, count: x.count }));
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
    for p in (API, PAGE, TYPES):
        if not os.path.isfile(p):
            print("ABORT: %s not found." % p)
            return 1
    if not os.path.isfile(os.path.join("utils", "deal_origin.py")):
        print("ABORT: apply patch_or1_deal_origin.py first.")
        return 1

    api = open(API, encoding="utf-8").read()
    tp = open(TYPES, encoding="utf-8").read()

    if '"by_origin"' in api:
        print("ABORT: by_origin already served - OR6 looks applied.")
        return 1
    if api.count(RETURN_ANCHOR) != 1:
        print("ABORT: the analytics return matched %d times." % api.count(RETURN_ANCHOR))
        return 1
    if tp.count(TYPE_OLD) != 1:
        print("ABORT: the analytics type matched %d times." % tp.count(TYPE_OLD))
        return 1

    # The split must be computed before the return, from THIS function's list.
    j = api.index(RETURN_ANCHOR)
    k = api.rindex("    return {", 0, j)
    api = api[:k] + SEGMENT + api[k:]
    api = api.replace(RETURN_ANCHOR, RETURN_NEW, 1)
    tp = tp.replace(TYPE_OLD, TYPE_NEW, 1)
    print("  ok  api serves by_origin; types carry it")

    if "_summarise_origin(active)" not in SEGMENT:
        print("ABORT: the split is not computed from this function's live list -")
        print("       a name that does not exist here would fail into the")
        print("       except and return an empty split silently.")
        return 1
    if "'Origin'" not in PAGE_SRC:
        print("ABORT: Origin is not a slicer dimension.")
        return 1
    if "data.by_origin" not in PAGE_SRC:
        print("ABORT: the page does not read by_origin.")
        return 1
    if "referral_vs_originated" not in api:
        print("ABORT: referral_vs_originated was removed - existing callers")
        print("       depend on it; this is an addition, not a migration.")
        return 1
    for op, cl in (("{", "}"), ("(", ")")):
        if PAGE_SRC.count(op) != PAGE_SRC.count(cl):
            print("ABORT: page unbalanced %s%s." % (op, cl))
            return 1
    print("  ok  post-checks: right list, dimension present, old field kept")

    if not apply:
        print("\nDRY RUN - nothing written. Re-run with --apply.")
        return 0

    for path, content in ((API, api), (TYPES, tp), (PAGE, PAGE_SRC)):
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
    print("Sales Pro Analytics > Origin. Note Analytics.tsx is on the alex-dev")
    print("delta list, so this stays on our side.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
