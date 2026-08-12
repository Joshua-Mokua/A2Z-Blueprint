#!/usr/bin/env python
# -*- coding: utf-8 -*-
r"""
BL1 - see Consumer as a whole before Premier, Advantage and Direct.

RULING (2026-08-12): "on the Sales Pro Analytics they are not able to see e.g.
Consumer as a whole before they go into Premier, Advantage, Direct. It will be
important when the MD or anybody is narrowing down to first see Consumer in
general and then progress."

The units were the only level available, so the MD saw three Consumer
sub-lines as separate rows and had to add them up before comparing Consumer
against Commercial. A roll-up is the level people reason in, which is why it
goes FIRST in the dimension list. Departments stays for the step after.

FROM client_type, THE COMPULSORY FIELD. The first version walked the org chart
up from the owner's ROLE - which answers "who owns this deal" rather than "what
kind of deal is it", and left anyone missing from the chart as Unassigned. The
pilot saw far too many of those, and they were material.

client_type is captured at deal creation and already carries exactly the three
values. It is the deal's own answer, given at the point somebody knew it, and
no derivation beats that. Spellings fold together - Individual and Retail to
Consumer, SME to Commercial, Corporate and Institution to CIB - so one line
cannot appear twice in a report.

THE ORG WALK REMAINS AS A FALLBACK for deals captured before the field was
compulsory, so nothing existing vanishes:

    Relationship Manager, Premier Banking -> Head Premier Banking
                                          -> Head of Consumer

A new sub-unit inherits its line the day somebody adds it to the chart.

TWO THINGS THE FIRST ATTEMPT GOT WRONG, both caught by running it:

  IT STOPPED AT THE FIRST "HEAD", returning "Premier Banking" - the sub-line
  the MD already sees, and precisely not the roll-up asked for. It now walks to
  the LAST head below the executive tier, because above Director/Chief/MD
  everything converges and the distinction disappears.

  IT READ ONLY functional_hierarchy. That carries the RM-to-unit-head links;
  the head-to-head ones live in `hierarchy`. Reading one chart stopped the walk
  halfway. Both are merged now.

Measured:

    Relationship Manager, Premier Banking   -> Consumer
    Relationship Officer, Premier Banking   -> Consumer
    Relationship Manager, Employee Schemes  -> Consumer
    Relationship Manager, SME               -> Commercial Banking
    Relationship Manager, Local Corporate   -> Commercial Banking

A deal whose owner is not in the chart falls back to client_type, so it lands
somewhere rather than vanishing. The aggregation is best-effort: if it fails,
analytics still render without that dimension.

Verified: py_compile clean, tsc --noEmit clean, vite build clean.

Usage (from project root, .venv active):
    python scripts\\patch_bl1_business_line.py            # dry run
    python scripts\\patch_bl1_business_line.py --apply
"""
import os
import shutil
import sys

API = os.path.join("utils", "api.py")
ANALYTICS = os.path.join("frontend", "web", "src", "pages", "Analytics.tsx")
TYPES = os.path.join("frontend", "web", "src", "types", "pipeline.ts")
BACKUP_SUFFIX = ".pre_bl1"

RES_ANCHOR = "def _segment_of("
AGG_ANCHOR = "    # by_probability_band: ACTIVE deals grouped"
PAYLOAD_OLD = '        "by_segment": _by_segment,'
PAYLOAD_NEW = '''        "by_segment": _by_segment,
        "by_business_line": _by_business_line,'''

RESOLVER = r'''def _business_line_of(deal: dict) -> str:
    """The business line a deal belongs to - Consumer, Commercial, CIB.

    CLIENT TYPE FIRST, and this is a correction. The first version walked the
    org chart up from the OWNER'S ROLE, which answers "who owns this deal"
    rather than "what kind of deal is it" - and anyone missing from the chart
    fell through to Unassigned, which is why the pilot saw so many.

    client_type is COMPULSORY AT DEAL CREATION and already carries exactly the
    three values wanted. It is the deal's own answer, given at the point
    somebody knew it, and no derivation can beat that.

    The org walk stays as a FALLBACK for older deals captured before the field
    was compulsory, so nothing existing vanishes from the roll-up.
    """
    ct = str(deal.get("client_type") or deal.get("segment") or "").strip()
    if ct:
        # Normalise the spellings that reach the field, so one line does not
        # appear twice in a report.
        low = ct.lower()
        if low.startswith("consumer") or low in ("individual", "personal", "retail"):
            return "Consumer"
        if low.startswith("commercial") or low in ("sme", "business"):
            return "Commercial"
        if low.startswith("cib") or low.startswith("corporate") or low == "institution":
            return "CIB"
        return ct

    # ── FALLBACK: walk the org chart ────────────────────────────────────────
    # Only for a deal with no client_type - captured before the field was
    # compulsory. Both charts are consulted: functional_hierarchy carries the
    # RM-to-unit-head links, hierarchy the head-to-head ones.
    try:
        from utils.core import get_org_config
        _org = get_org_config() or {}
        fh = dict(_org.get("hierarchy", {}) or {})
        fh.update(_org.get("functional_hierarchy", {}) or {})
    except Exception:
        fh = {}
    role = str(deal.get("staff_role") or deal.get("role") or "").strip()
    if not role:
        try:
            from utils.api_pipeline_scope import get_staff_roster
            df = get_staff_roster()
            code = str(deal.get("staff_code") or "")
            for _i, r in df.iterrows():
                if str(r.get("Staff Code") or "") == code:
                    role = str(r.get("Role") or "")
                    break
        except Exception:
            pass

    _EXEC = ("director", "chief", "managing", "ceo")
    seen, cur, last_head = set(), role, ""
    for _ in range(8):
        if not cur or cur in seen:
            break
        seen.add(cur)
        low = cur.lower()
        if any(x in low for x in _EXEC):
            break
        if low.startswith("head"):
            last_head = cur
        nxt = fh.get(cur)
        cur = (nxt[0] if isinstance(nxt, list) and nxt else
               nxt if isinstance(nxt, str) else "")
    if last_head:
        out = last_head.split(",", 1)[-1] if "," in last_head else last_head
        for tok in ("Head of", "Head"):
            out = out.replace(tok, "")
        return out.strip() or last_head
    return ""

'''

AGGREGATION = r'''    # ── BY BUSINESS LINE (pilot, 2026-08-12) ────────────────────────────────
    # "On Sales Pro Analytics they are not able to see e.g. Consumer as a whole
    # before they go into Premier, Advantage, Direct. It will be important when
    # the MD or anybody is narrowing down to first see Consumer in general and
    # then progress."
    #
    # The units were the only level available, so the MD saw three Consumer
    # sub-lines and had to add them up mentally before comparing Consumer with
    # Commercial. A roll-up is the level people actually think in.
    #
    # DERIVED BY WALKING THE ORG CHART, not by a second list to maintain.
    # functional_hierarchy already says "Relationship Manager, Premier Banking"
    # -> "Head Premier Banking" -> "Head of Consumer", so the business line is
    # the top of that walk. A new sub-unit inherits its line the day it is added
    # to the chart, with nothing else to update.
    _by_business_line: list = []
    try:
        _bl: dict = {}
        for d in live:
            key = _business_line_of(d) or "Unassigned"
            e = _bl.setdefault(key, {"business_line": key, "value": 0.0, "count": 0})
            e["value"] += _deal_value(d)
            e["count"] += 1
        _by_business_line = sorted(_bl.values(), key=lambda x: x["value"], reverse=True)
    except Exception as _exc:
        logger.warning("business-line rollup unavailable: %s", _exc)

'''

ANALYTICS_SRC = r'''// #3b — Analytics page. Consumes /api/pipeline/analytics (KES-equivalent,
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
  // 'Business Line' sits FIRST because it is the level people reason in.
  // Without it the MD saw Premier, Advantage and Direct as three rows and had
  // to add them up before comparing Consumer with Commercial. Departments is
  // still there for the step after.
  const DIMENSIONS = ['Business Line', 'Origin', 'Product', 'Segment', 'Sector', 'Stage', 'Product Funnel', 'Probability', 'Currency', 'Branch', 'RM', 'Departments'] as const;
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
      case 'Business Line':
        return (data.by_business_line ?? []).map((x) => ({
          label: x.business_line, value: x.value, count: x.count }));
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
  // ORIGIN is a share question - what proportion of the book came from each
  // channel - so it belongs with the donuts rather than the ranked bars.
  const isDonut = dim === 'Origin' || dim === 'Sector' || dim === 'Segment' || dim === 'Currency';
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

TYPES_SRC = r'''// v10.510 Phase 4 Batch β1 — TypeScript types for pipeline domain.
//
// These interfaces mirror the FastAPI backend's response shapes from:
//   - GET /api/pipeline/deals       (α1 — list, α2 — scope-filtered, α7 — permissions-enriched)
//   - GET /api/pipeline/deals/{id}  (α7 — single deal + permissions)
//
// Backend shape is defined by:
//   - utils/api_pipeline_models.py::PipelineDeal       (data shape, extra="allow")
//   - utils/api_pipeline_permissions.py::PERMISSION_KEYS  (the 6 permission booleans)
//
// If backend changes, this file changes. A future Stage C gate
// (gate_pipeline_types_contract_match) will enforce alignment by
// comparing TypeScript schema against backend Pydantic output.

// ── Permissions (α7 contract — audit Section 15.6 + GAP-012) ────────────
// Six booleans resolved server-side per (caller, deal) relationship.
// React reads these to decide which buttons to render — never duplicates
// the authorization logic in TypeScript.

export interface DealPermissions {
  /** Caller can see the deal at all. False → deal shouldn't appear. */
  can_view:             boolean;
  /** Edit deal fields. False for backup-only callers (Section 15.6:656). */
  can_edit:             boolean;
  /** Move stage forward. False on terminal stages (Closed Won/Lost). */
  can_advance_stage:    boolean;
  /** Request cancellation. False if already requested or terminal. */
  can_request_cancel:   boolean;
  /** Approve/reject pending cancel. Manager-only + needs pending request. */
  can_approve_cancel:   boolean;
  /** Validate or query the deal. Manager-only + must be validation stage. */
  can_validate:         boolean;
}

// ── Pipeline deal shape ─────────────────────────────────────────────────
// Matches PipelineDeal Pydantic model. Extra fields are tolerated
// (model has extra="allow") — TypeScript "[key: string]: unknown"
// index signature would catch them but reduces type safety for the
// known fields. Trade-off: explicit known fields, additional fields
// accessed by string keys when needed.

export interface DealSlaStatus {
  state?:                  'on_track' | 'due_soon' | 'breached';
  clock?:                  'step' | 'age';
  step?:                   string | null;
  elapsed_business_days?:  number;
  target_days?:            number;
  remaining_business_days?: number;
  overdue_business_days?:  number;
  breached?:               boolean;
  escalate_to?:            string | null;
  commitment_status?:      'active' | 'unfulfilled' | null;
}

export interface PipelineDeal {
  segment?: string | null;
  // Identity
  id:                   string;
  client_name:          string;
  client_cif?:          string;     // δ2: CBS CIF when matched to a CBS customer
  client_type?:         string;
  is_ntb?:              boolean;
  is_referral?:         boolean;

  // Per-deal SLA status (attached by GET /api/pipeline/deals — Phase 4 #81)
  sla?:                 DealSlaStatus | null;

  /** Admin-authored win probability (0–100) DERIVED from the deal's current
   *  stage in its product flow (P-WP). Derived on read, never stored, so it
   *  auto-updates as the deal advances. Null when the stage has none set.
   *  Distinct from `probability` (the generic stage-weight forecast). */
  win_probability?:     number | null;

  // Staff attribution
  staff_code:           string;
  staff_name?:          string;
  backup_staff_codes?:  string[];

  // Pipeline classification
  stage:                string;
  pipeline_category?:   string;
  deal_category?:       string;       // legacy field, transitional compat
  product_type?:        string;
  product?:             string;
  unit?:                string;
  source?:              string;

  // Financials
  deal_value:           number;
  /** KES-equivalent of deal_value (FCY deals); equals deal_value for LCY.
   * The pipeline reports in KES, so DISPLAY this, not the native deal_value. */
  amount_kes?:          number;
  currency_book?:       string;       // 'LCY' | 'FCY'
  probability?:         number;
  currency?:            string;

  // Workflow timestamps
  created_at?:          string;
  open_date?:           string;      // DB-sourced deals carry this (aging)
  updated_at?:          string;
  next_action?:         string;
  next_action_date?:    string;
  expected_close?:      string;

  // Manager validation
  manager_validated?:   boolean;
  validated_by?:        string;
  validated_by_name?:   string;
  validated_by_role?:   string;
  validated_by_code?:   string;
  validated_at?:        string;
  validation_note?:     string;
  draft?:               boolean;

  // Cancellation lifecycle
  cancel_requested?:           boolean;
  cancel_requested_by?:        string;
  cancel_requested_at?:        string;
  cancel_reason?:              string;
  cancel_approved?:            boolean | null;
  cancel_approved_by?:         string;
  cancel_approved_at?:         string;
  cancel_note?:                string;

  // Portfolio conflict resolution (α5)
  portfolio_owner_code?:       string;
  portfolio_owner_name?:       string;
  bsc_credit_to?:              string;
  manager_override_note?:      string;

  // Referral lifecycle (A1 — refer an existing deal to another person)
  referral_status?:            string;   // 'pending' | 'accepted' | 'declined'
  referred_to?:                string;
  referred_to_code?:           string;
  referred_by_name?:           string;
  referred_by_code?:           string;
  referral_note?:              string;
  decline_reason?:             string;

  // LMS handoff (α4)
  lms_application_id?:         string;
  loss_reason?:                string;
  // Phase L — origination lock (submitted to credit; unless returned/info-requested)
  locked?:                     boolean;
  lock_reason?:                string;
  // Phase V — line-manager validation
  validation_requests?:        import('@/lib/api').ValidationRequest[];
  validator?:                  { code?: string | null; name?: string | null; role?: string | null; admin_fallback?: boolean } | null;
  reopen_available?:           boolean;
  // Phase H — on-hold (freezes SLA clocks)
  on_hold?:                    boolean;
  hold_available?:             boolean;
  hold_reason?:                string;
  hold_started_at?:            string | null;
  held_intervals?:             { start?: string | null; end?: string | null; reason?: string }[];

  // α7 per-deal permissions — added by the API enrichment layer
  permissions?:         DealPermissions;
}


// ── Response envelopes ──────────────────────────────────────────────────

export interface PipelineDealsListResponse {
  deals:    PipelineDeal[];
  count:    number;
  source:   string;   // 'pipeline_manager' per α1
}

export interface PipelineDealDetailResponse {
  deal:         PipelineDeal;
  permissions:  DealPermissions;
  /** B17: this deal's product-class stage flow (admin config). The advance
   *  dropdown reads this instead of a flat hardcoded list. */
  stage_flow?:  string[];
}


// ── Query parameter helpers ─────────────────────────────────────────────
// The list endpoint supports stage/category/unit filters + pagination.

export interface PipelineDealsQuery {
  stage?:     string;
  category?:  string;
  unit?:      string;
  offset?:    number;
  limit?:     number;
}


// ── Admin-configured pipeline config (from /api/pipeline/stages) ─────────
// Single source of truth for category/stage/sector/decision-level dropdowns.
// Driven by data/pipeline_settings.json (Batch A2).

export interface PipelineStageConfig {
  stage:         string;
  description?:  string;
  color?:        string;
  prob_default?: number;
}

export interface DealCategoryConfig {
  category:     string;
  description?: string;
  stages:       string[];
  /** A2a: which product classes this category filters to (asset/liability/insurance/other). */
  product_class?: string[];
  /** A2a: "pipeline" = shown in create-deal dropdown; "dormant" = kept but hidden. */
  surface?:     string;
}

/** P4a: one stage in a product's flow, carrying its own SLA target (days). */
export interface ProductFlowStage {
  stage: string;
  target_days: number;
  /** P-WP: admin-authored win probability (0–100) for deals at this stage.
   *  Optional — a stage without it yields no derived probability. */
  win_probability?: number | null;
}
/** P4a: a single product's process flow — ordered stages (each with a target)
 * plus the client types that offer it (empty list = offered to all). */
export interface ProductFlow {
  client_types: string[];
  stages: ProductFlowStage[];
  required_documents?: string[];
  documents_required_at_stage?: string;
  committee_journey?: string[];
}

export interface PipelineConfig {
  stages:            PipelineStageConfig[];
  deal_categories:   DealCategoryConfig[];
  sectors:           string[];
  decision_levels:   string[];
  probability_map:   Record<string, number>;
  deal_types:        string[];
  product_catalogue: Record<string, string[]>;
  /** B17: per-product-class stage flows (asset/liability/insurance/other). */
  stage_flows?:      Record<string, string[]>;
  /** P4a: per-PRODUCT flows — each product's own stage sequence (with a
   * per-stage target_days) and the client types that offer it (empty = all). */
  product_flows?:    Record<string, ProductFlow>;
  /** Admin display-name map for segments (e.g. Ecobank: Mass/Retail→Direct). */
  segment_labels?:   Record<string, string>;
  /** Segment options per client type (Individual / Business). */
  customer_segments?: Record<string, string[]>;
  /** Client business lines (Consumer / Commercial / CIB), admin-configurable. */
  client_types?: { key: string; label: string; field: 'mou' | 'sector' }[];
  /** CBK economic-sector classification for BUSINESS clients (admin config). */
  business_sectors?: string[];
  /** Active partnership/MOU register for INDIVIDUAL clients. */
  individual_mous?: { id: string; title: string; partner_name?: string }[];
  /** Allow an "Other…" free-text fallback on the sector / MOU field. */
  allow_other_sector?: boolean;
  allow_other_mou?:    boolean;
  /** Deal-create fields the bank requires (admin-configured). */
  required_fields?:    string[];
  currency:          string;
}


// ── Mutation request bodies (v10.511 Phase 4 Batch β2) ──────────────────
// Match the FastAPI Pydantic models in utils/api_pipeline_models.py.

/** POST /api/pipeline/deals/{id}/advance — body shape. */
export interface AdvanceDealRequest {
  /** Target stage to advance to. Server validates against allowed stages. */
  target_stage: string;
  /** Optional probability override (server uses default if omitted). */
  probability?: number;
  /** Optional note recorded on the deal. */
  note?: string;
}

/** POST /api/pipeline/deals/{id}/cancel/request — body shape (α6). */
export interface RequestCancelRequest {
  /** Why the deal should be cancelled. Min 5 chars per server validation. */
  reason: string;
}


// ── Mutation response envelopes ────────────────────────────────────────
// Mutation endpoints return the updated deal + status metadata. Per α7
// design note, mutation responses do NOT carry a permissions object —
// the React UI refetches the list (or single deal) after mutation.

export interface AdvanceDealResponse {
  deal:                  PipelineDeal;
  status:                string;       // 'advanced' on success
  bsc_triggered?:        boolean;
  lms_triggered?:        boolean;
  lms_application_id?:   string;
  lms_error?:            string;
}

export interface RequestCancelResponse {
  deal:               PipelineDeal;
  status:             string;          // 'cancel_requested'
  cancel_requested:   boolean;
  awaiting_manager:   boolean;
}


// ── Display helpers — pure data, no React ───────────────────────────────

/** Stage → Badge tone mapping. Drives PermissionBadges and DealCard. */
export const STAGE_TONE: Record<string, 'neutral' | 'info' | 'warning' | 'success' | 'danger'> = {
  // Early stages
  'Lead':         'neutral',
  'Contacted':    'info',
  'Qualified':    'info',
  'Proposal':     'info',
  'Negotiation':  'warning',
  'Compliance':   'warning',
  // LMS / credit stages
  'Credit Review':     'warning',
  'Approval':          'warning',
  'Bank Approval':     'warning',
  'Credit Committee':  'warning',
  'Documentation':     'info',
  'Vetting':           'info',
  'Disbursed':         'success',
  // Account / Deposit stages
  'Documentation Complete':  'info',
  'Negotiating':             'warning',
  'Account Opened':          'success',
  'Funded':                  'success',
  // Terminal
  'Closed Won':   'success',
  'Closed Lost':  'danger',
};

/** Get tone for an unknown stage — falls back to neutral. */
export function stageTone(stage: string): 'neutral' | 'info' | 'warning' | 'success' | 'danger' {
  return STAGE_TONE[stage] ?? 'neutral';
}


/** Common target stages a user can advance a deal to.
 *
 * Conservative subset — the server validates the actual transition,
 * so this list doesn't need to encode the full stage graph (which is
 * a server-side concern per α3 doctrine). LMS-handoff stages (Credit
 * Review, Approval, etc.) are reachable via α4's allowlist but are
 * intentionally omitted from this dropdown — those transitions are
 * triggered server-side as side effects of advancing TO Compliance,
 * not by manually selecting them.
 *
 * If the server rejects an advance with 400, the React UI surfaces
 * the error message rather than pre-filtering options here.
 */
export const ADVANCE_TARGET_STAGES: readonly string[] = [
  'Contacted',
  'Qualified',
  'Proposal',
  'Negotiation',
  'Compliance',
  'Closed Won',
  'Closed Lost',
] as const;


// ── Pipeline category + stage scaffolding (v10.512 Phase 4 Batch β3) ────
//
// Mirrors the backend's ALLOWED_ADVANCE_STAGES set from
// utils/api_pipeline_mutations.py. Grouping by pipeline category so
// the create form can offer a sensible default stage dropdown.
//
// Drift warning: these constants are duplicated from the backend.
// A future batch SHOULD replace this with a GET /api/pipeline/stages
// endpoint that returns the canonical stage list. For β3 the duplication
// is accepted — the backend rejects invalid stages anyway, so drift
// would surface as a 400 error rather than a silent bug.

export const PIPELINE_CATEGORIES = ['Loan', 'Deposit', 'Account'] as const;
export type PipelineCategory = typeof PIPELINE_CATEGORIES[number];

/** Initial stages a deal can be created at, grouped by category.
 *  Subset of ALLOWED_ADVANCE_STAGES that excludes terminal stages
 *  (Closed Won / Closed Lost). */
export const INITIAL_STAGES_BY_CATEGORY: Record<PipelineCategory, readonly string[]> = {
  Loan:    ['Lead', 'Contacted', 'Qualified', 'Proposal', 'Negotiation', 'Compliance'],
  Deposit: ['Lead', 'Pitched', 'Negotiating', 'Funded'],
  Account: ['Lead', 'Information Gathered', 'Documentation Complete', 'Account Opened'],
} as const;

/** Common products as quick-pick suggestions for the create form.
 *  NOT exhaustive — the create form accepts arbitrary product_type
 *  strings and the server doesn't currently validate against a
 *  canonical list. β4 candidate: add GET /api/pipeline/products. */
export const COMMON_PRODUCTS_BY_CATEGORY: Record<PipelineCategory, readonly string[]> = {
  Loan: [
    'Business Loan',
    'Personal Loan',
    'Mortgage / Home Loan',
    'Overdraft',
    'Trade Finance',
    'Asset Finance',
    'LPO Finance',
    'Bancassurance',
  ],
  Deposit: [
    'Current Account (CASA)',
    'Savings Account (CASA)',
    'Fixed Deposit',
    'Call Deposit',
    'Business Current Account',
    'Business Savings',
  ],
  Account: [
    'Account Opening',
  ],
} as const;

/** Lead source options — mirrors Streamlit's source dropdown. */
export const SOURCE_OPTIONS: readonly string[] = [
  'Referral',
  'Existing relationship',
  'Walk-in',
  'Cold call',
  'Branch campaign',
  'Digital / online',
  'Partner / broker',
  'Other',
] as const;

/** Minimum length of manager override note when override semantics
 *  detected. Matches MIN_OVERRIDE_NOTE_LEN in
 *  utils/api_pipeline_mutations.py — kept in sync so client-side
 *  validation provides the same hint the server enforces. */
export const MIN_OVERRIDE_NOTE_LEN = 10;


// ── Create mutation request/response (β3) ───────────────────────────────
// Matches PipelineDealCreate from utils/api_pipeline_models.py.

export interface CreateDealRequest {
  // Required
  client_name:           string;
  staff_code:            string;
  staff_name:            string;
  deal_value:            number;
  product_type:          string;
  stage:                 string;

  // Optional but commonly supplied
  client_type?:          string;     // 'Individual' or 'Business'
  currency?:             string;     // ISO code; defaults KES (admin FX table)
  segment?:              string;     // segment within client type (cascade)
  sector?:               string;     // CBK economic sector (Business clients)
  mou_id?:               string;     // partnership/MOU id (Individual clients)
  /** How the deal entered - one of the DECLARABLE origins. The server
   *  validates it and replaces any system-routed value (referral, warehouse),
   *  which are stamped by the workflow that actually routed the deal. */
  origin?:               string;
  /** The chosen source for that origin - a sponsored event. Cleared server-side
   *  if it does not belong to the origin. */
  event_id?:             string;
  mou_title?:            string;     // MOU title or free-text partner ("Other")
  client_cif?:           string;     // δ2: CBS CIF when client matched in CBS lookup
  is_ntb?:               boolean;
  pipeline_category?:    string;
  is_top_up?:            boolean;   // true if topping up an existing facility
  top_up_amount?:        number;    // the increment (becomes pipeline value)
  bundle_lines?:         { product_type: string; amount: number }[]; // Bundled Loan Product lines
  original_facility_amount?: number; // existing facility size (context only)
  probability?:          number;     // 0..1 (NOT 0..100)
  next_action?:          string;
  next_action_date?:     string;     // YYYY-MM-DD
  expected_close?:       string;     // YYYY-MM-DD
  notes?:                string;
  source?:               string;
  unit?:                 string;
  account_number?:       string;
  phone?:                string;
  email?:                string;

  // Conflict resolution fields (β3)
  portfolio_owner_code?:    string;
  portfolio_owner_name?:    string;
  bsc_credit_to?:           string;
  manager_override_note?:   string;
}

export interface CreateDealResponse {
  deal:           PipelineDeal;
  status:         string;  // 'created'
  bsc_triggered:  boolean;
  // LMS fields are not populated for create (only advance), but
  // the server's response schema may include them as null.
  lms_triggered?:        boolean | null;
  lms_application_id?:   string | null;
  lms_error?:            string | null;
}


// ── Refer endpoint request/response (β3) ────────────────────────────────
// Matches PipelineDealRefer from utils/api_pipeline_models.py.

export interface ReferDealRequest {
  // Required
  client_name:            string;
  staff_code:             string;  // the referring RM
  staff_name:             string;
  portfolio_owner_code:   string;  // who's being referred TO
  portfolio_owner_name:   string;
  referred_to:            string;  // named recipient (often == portfolio_owner_name)

  // Optional
  referral_note?:         string;
  account_number?:        string;
  unit?:                  string;
}

export interface ReferDealResponse {
  deal:           PipelineDeal;
  status:         string;  // 'referred'
  bsc_triggered:  boolean;
}


// ── Manager queue types (v10.513 Phase 4 Batch β4) ──────────────────────
// Manager-only endpoints. Server enforces 403 on these for non-managers
// (per utils/api_pipeline_manager_actions.py::is_manager). React uses
// lib/role.ts::isManager to hide nav links + page guards as UX.

/** Validation queue: deals past Lead stage awaiting manager validation
 *  (manager_validated:false, stage in active set, not cancel_requested). */
export interface ValidationQueueResponse {
  deals:  PipelineDeal[];
  count:  number;
  queue:  'validation';
}

/** Cancellation queue: deals with cancel_requested:true AND
 *  cancel_approved:null/false (awaiting manager decision). */
export interface CancellationQueueResponse {
  deals:  PipelineDeal[];
  count:  number;
  queue:  'cancellation';
}


// ── Validate deal mutation (v10.513 Phase 4 Batch β4) ──────────────────
// POST /api/pipeline/deals/{id}/validate. Manager either VALIDATES
// (approved:true → deal joins forecast) or QUERIES (approved:false →
// deal returns to owner with note). Mirrors Streamlit pages/3_pipeline.py.

export interface ValidateDealRequest {
  /** True = validate (include in forecast); False = query (return to owner). */
  approved:  boolean;
  /** Manager's note. Server doesn't enforce length, matching Streamlit. */
  note?:     string;
}

export interface ValidateDealResponse {
  deal:           PipelineDeal;
  status:         string;  // 'validated' | 'queried' depending on approved
  bsc_triggered:  boolean;
}


// ── Approve/reject cancellation (v10.513 Phase 4 Batch β4) ──────────────
// POST /api/pipeline/deals/{id}/cancel/approve. Manager either APPROVES
// (approve:true → deal moves to Closed Lost) or REJECTS (approve:false →
// deal continues, cancel_requested flag cleared).

export interface ApproveCancelRequest {
  /** True = approve cancellation; False = reject (deal continues). */
  approve:   boolean;
  /** Manager's decision note. Visible on the deal for audit. */
  note?:     string;
}

export interface ApproveCancelResponse {
  deal:           PipelineDeal;
  status:         string;  // 'cancel_approved' | 'cancel_rejected'
  bsc_triggered:  boolean;
}


// ── Credit submission gate (v10.574 Batch B10) ─────────────────────────
// GET /api/pipeline/deals/{id}/credit-checklist response, and the
// POST /api/pipeline/deals/{id}/submit-to-credit response.

export interface CreditChecklistResponse {
  required:            string[];
  provided:            string[];
  missing:             string[];
  already_submitted:   boolean;
  lms_application_id:   string | null;
  can_submit:          boolean;
  current_stage?:      string;
  stage_required?:     string;
  stage_ok?:           boolean;
  cr_required?:        boolean;
  cr_ok?:              boolean;
  committee_ok?:       boolean;
  manager_validated?:  boolean;
  committee_pending?:  string[];
  committee_rejected?: string[];
}

export interface SubmitToCreditResponse {
  application_id:  string;
  status:          string;   // 'submitted_to_credit'
  missing:         string[];
}


// ── Pipeline analytics (B14/B15 backend) ────────────────────────────────
// GET /api/pipeline/analytics. Headline value is VALIDATED (manager-assured);
// pending_value is unvalidated active ("pending assurance"). Funnel is
// validated-only. Buckets sourced from admin product_catalogue.

export interface FunnelStage {
  stage:  string;
  count:  number;
  value:  number;
}

export interface OtherProduct {
  product:  string;
  value:    number;
  count:    number;
}

export interface OtherSubclass {
  subclass:  string;
  value:     number;
  count:     number;
  products:  OtherProduct[];
}

export interface PipelineBucket {
  label:          string;
  value:          number;        // assured (validated active)
  pending_value:  number;        // pending assurance (unvalidated active)
  weighted:       number;
  active_count:   number;
  pending_count:  number;
  won_value:      number;
  funnel:         FunnelStage[];
  breakdown?:     OtherSubclass[];   // only on the "other" bucket
}

export interface PipelineAnalyticsTotals {
  total_value:        number;    // validated active (assured)
  pending_value:      number;    // pending assurance
  weighted_value:     number;
  won_value:          number;
  active_count:       number;
  pending_count:      number;
  won_count:          number;
  lost_count:         number;
  live_count:         number;
  win_rate:           number;
  pending_validation: number;    // scope-aware: deals awaiting this manager
  pending_cancel:     number;
}

export interface ProductBreakdown { product: string; value: number; count: number; won_value: number }
export interface SectorBreakdown  { sector: string; value: number; count: number }
export interface SegmentBreakdown { segment: string; value: number; count: number }
export interface SegmentFunnel { segment: string; active_count: number; value: number; funnel: FunnelStage[] }
export interface UnitBreakdown    { unit: string; value: number; count: number }
export interface RmBreakdown      { rm: string; value: number; count: number }
export interface DrillDeal {
  id: string;
  client_name: string;
  product_type: string;
  stage: string;
  amount_kes: number;
  currency: string;
  staff_name: string;
  unit: string;
  expected_close: string | null;
  probability: number | null;
}
export interface PipelineDrillResponse {
  unit: string | null;
  rm: string | null;
  by_rm: RmBreakdown[];
  deals: DrillDeal[];
  totals: { value: number; count: number };
}
export interface CurrencyBookSplit { value: number; count: number }

export interface FunnelDrillDeal {
  id: string;
  client_name: string;
  product_type: string;
  segment: string;
  stage: string;
  amount_kes: number;
  staff_name: string;
  unit: string | null;
}
export interface FunnelDrillResponse {
  cls: string;
  stage: string;
  totals: { value: number; count: number };
  by_product: ProductBreakdown[];
  by_segment: SegmentBreakdown[];
  by_sector: SectorBreakdown[];
  deals: FunnelDrillDeal[];
}

export interface PipelineAnalyticsResponse {
  totals:       PipelineAnalyticsTotals;
  pipelines: {
    asset:      PipelineBucket;
    liability:  PipelineBucket;
    insurance:  PipelineBucket;
    other:      PipelineBucket;
  };
  funnel:       FunnelStage[];
  by_category:  unknown[];
  by_product?:        ProductBreakdown[];
  by_sector?:         SectorBreakdown[];
  by_segment?:        SegmentBreakdown[];
  /** Roll-up above the units: Premier, Advantage and Direct all report as
   *  Consumer, so the MD can compare business lines before drilling in.
   *  Derived by walking the org chart, not a second list to maintain. */
  by_business_line?:  { business_line: string; value: number; count: number }[];
  by_segment_funnel?: SegmentFunnel[];
  by_currency_book?:  { LCY: CurrencyBookSplit; FCY: CurrencyBookSplit };
  by_unit?:           UnitBreakdown[];
  by_rm?:             RmBreakdown[];
  by_probability_band?: ProbabilityBandBreakdown[];
  by_product_funnel?: ProductFunnel[];
  by_referral_department?: ReferralDepartmentBreakdown[];
  /** Every configured deal origin, with its readable label. Replaces the
   *  referred-vs-originated pair as the way to ask where work came from. */
  by_origin?: { origin: string; label?: string; credits_party?: boolean;
                count: number; value: number; won: number }[];
  referral_branch_split?: { in_branch: number; cross_branch: number };
  referral_vs_originated?: {
    open:   { referred: { count: number; value: number }; originated: { count: number; value: number } };
    closed: { referred: { count: number; value: number }; originated: { count: number; value: number } };
  };
}

export interface ReferralReferrer {
  referrer: string;
  count: number;
  value: number;
}
export interface ReferralDepartmentBreakdown {
  department: string;
  value: number;
  count: number;
  head_count: number;
  in_branch: number;
  cross_branch: number;
  referred_out: number;
  referred_out_value: number;
  referrers: ReferralReferrer[];
}

export interface ProductFunnelStage {
  stage: string;
  count: number;
  value: number;
  win_probability: number | null;
}
export interface ProductFunnel {
  product: string;
  active_count: number;
  value: number;
  funnel: ProductFunnelStage[];
}

export interface ProbabilityBandStage {
  stage: string;
  product: string;
  win_probability: number | null;
  count: number;
  value: number;
}
export interface ProbabilityBandBreakdown {
  band:  string;
  value: number;
  count: number;
  stages?: ProbabilityBandStage[];
}
'''


def main():
    apply = "--apply" in sys.argv
    for p in (API, ANALYTICS, TYPES):
        if not os.path.isfile(p):
            print("ABORT: %s not found." % p)
            return 1

    api = open(API, encoding="utf-8").read()
    if "_business_line_of" in api:
        print("ABORT: BL1 looks applied.")
        return 1
    for name, needle in (("resolver", RES_ANCHOR), ("aggregation", AGG_ANCHOR),
                         ("payload", PAYLOAD_OLD)):
        if api.count(needle) != 1:
            print("ABORT: the %s anchor matched %d times." % (name, api.count(needle)))
            return 1

    api = api.replace(RES_ANCHOR, RESOLVER + RES_ANCHOR, 1)
    api = api.replace(AGG_ANCHOR, AGGREGATION + AGG_ANCHOR, 1)
    api = api.replace(PAYLOAD_OLD, PAYLOAD_NEW, 1)
    print("  ok  resolver, aggregation, payload, dimension")

    # CLIENT TYPE MUST WIN. The org walk answers "who owns this deal", not
    # "what kind of deal is it" - and anyone missing from the chart falls to
    # Unassigned, which is what the pilot saw.
    if 'deal.get("client_type")' not in RESOLVER:
        print("ABORT: the roll-up does not use client_type, which is the")
        print("       compulsory field that already carries the answer.")
        return 1
    if RESOLVER.index('client_type') > RESOLVER.index("get_org_config"):
        print("ABORT: the org walk is consulted before client_type.")
        return 1
    if "last_head" not in RESOLVER:
        print("ABORT: the fallback walk stops at the first head, so an older")
        print("       Premier deal would report as Premier, not Consumer.")
        return 1
    if "_EXEC" not in RESOLVER:
        print("ABORT: the walk does not stop below the executive tier - every")
        print("       line would converge on the MD.")
        return 1
    if "functional_hierarchy" not in RESOLVER or '"hierarchy"' not in RESOLVER:
        print("ABORT: only one org chart is consulted - the head-to-head links")
        print("       live in the other one.")
        return 1
    if "Business Line" not in ANALYTICS_SRC:
        print("ABORT: the dimension is not offered in the UI.")
        return 1
    for op, cl in (("{", "}"), ("(", ")")):
        if ANALYTICS_SRC.count(op) != ANALYTICS_SRC.count(cl):
            print("ABORT: analytics unbalanced %s%s." % (op, cl))
            return 1
    print("  ok  post-checks: walks to the top, both charts, dimension offered")

    if not apply:
        print("\nDRY RUN - nothing written. Re-run with --apply.")
        return 0

    for path, content in ((API, api), (ANALYTICS, ANALYTICS_SRC), (TYPES, TYPES_SRC)):
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

    print("")
    print("Next: pushd frontend\\web && pnpm tsc --noEmit && popd, restart uvicorn.")
    print("Sales Pro Analytics opens on Business Line - Consumer, Commercial,")
    print("CIB - with Departments still there for the drill-down.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
