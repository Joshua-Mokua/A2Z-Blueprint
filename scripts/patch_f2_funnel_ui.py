#!/usr/bin/env python
# -*- coding: utf-8 -*-
r"""
F2 - the funnel as the centrepiece: the defined journey, drawn from admin.

Replaces the old PipelineFunnel on Sales Pro. That one intersected the deals
against a CODE constant, which is why 22 active deals across four stages showed
as one band with one deal - only "Offer / Proposal" existed in both vocabularies.

WHAT IT DRAWS
  THE JOURNEY - every stage of the selected product's configured flow, in the
      configured order, with the win probability set for that stage WITHIN THAT
      FLOW. Bands carry count and value; the right rail carries the weighted
      value; the left rail carries the stage and its win %.

  EMPTY STAGES ARE DRAWN, hatched and labelled "no deals at this stage". A
      funnel that hides them is a bar chart of whatever happened to be busy, and
      the empty step is usually the finding - it is where deals stop arriving.

  THE CREDIT LAYER beneath: Documentation / Branch Credit / Department / Credit
      Analysis / Credit Administration / TROPS, each with its probability band,
      count and value. A SECOND AXIS over the same deals - it never filters the
      journey, and the caption says so on screen.

  UNPLACED DEALS are called out in red rather than dropped. Deals sitting at a
      stage no configured flow contains used to vanish; now the funnel says how
      many and that they are counted nowhere above.

DEPTH WITHOUT A 3D LIBRARY: a vertical gradient plus an inset highlight and
shadow, so a band reads as a solid object; bands taper by position so the shape
reads as a funnel even where the numbers do not decline monotonically - real
pipelines rarely do, and a mis-shaped funnel invites the reader to think the
data is wrong when it is not. Hover lifts the band.

THE STAGE DRILL IS PRESERVED. The old funnel had onStageClick wired to
fetchFunnelDrill; dropping it while swapping components would have removed a
working feature quietly, so DefinedFunnel takes the same callback and
Pipeline.tsx passes the same handler.

Verified: tsc --noEmit clean, vite build clean.

REQUIRES F1 (the endpoint and the admin config).

Usage (from project root, .venv active):
    python scripts\patch_f2_funnel_ui.py            # dry run
    python scripts\patch_f2_funnel_ui.py --apply    # write + .pre_f2 backups
"""
import os
import shutil
import sys

COMP = os.path.join("frontend", "web", "src", "components", "DefinedFunnel.tsx")
APITS = os.path.join("frontend", "web", "src", "lib", "api.ts")
PAGE = os.path.join("frontend", "web", "src", "pages", "Pipeline.tsx")
BACKUP_SUFFIX = ".pre_f2"

TS_NEW = r'''// ── Defined funnel (journey from admin config + credit side layer) ────────
export interface DefinedStage {
  stage: string; count: number; value: number;
  probability: number; weighted: number; credit_band: string;
}
export interface DefinedFlow {
  flow: string; stages: DefinedStage[];
  deals: number; value: number; weighted: number;
}
export interface CreditBandTally {
  label: string; count: number; value: number; min: number; max: number;
}
export interface DefinedFunnel {
  flows: DefinedFlow[];
  credit_layer: CreditBandTally[];
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

  const stages = flow?.stages ?? [];
  const max = Math.max(1, ...stages.map((s) => (sizeBy === 'count' ? s.count : s.value)));
  const creditMax = Math.max(1, ...(data?.credit_layer ?? []).map((c) => c.count));

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

            {/* The journey. Bands taper by position so the shape reads as a
                funnel even where the numbers do not decline monotonically —
                real pipelines rarely do, and a mis-shaped funnel invites the
                reader to think the data is wrong when it is not. */}
            <div className="space-y-1.5">
              {stages.map((s, i) => {
                const metric = sizeBy === 'count' ? s.count : s.value;
                const fill = Math.max(metric / max, metric > 0 ? 0.06 : 0);
                const taper = 1 - (i / Math.max(stages.length, 2)) * 0.34;
                const colour = bandColour(i, stages.length);
                const empty = s.count === 0;
                const on = hover === s.stage;
                return (
                  <div key={s.stage}
                       onMouseEnter={() => setHover(s.stage)}
                       onMouseLeave={() => setHover('')}
                       onClick={() => {
                         if (!empty && onStageClick && flow) onStageClick(flow.flow, s.stage);
                       }}
                       className={'group relative flex items-center gap-3 '
                         + (!empty && onStageClick ? 'cursor-pointer' : '')}>
                    <div className="w-40 shrink-0 text-right">
                      <div className={'truncate text-xs font-medium ' + (empty ? 'text-gray-400' : 'text-gray-800')}
                           title={s.stage}>
                        {s.stage}
                      </div>
                      <div className="text-[10px] text-gray-400">
                        {Math.round(s.probability * 100)}% win
                      </div>
                    </div>

                    <div className="relative h-11 flex-1" style={{ paddingInline: `${(1 - taper) * 50}%` }}>
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
                            : `inset 0 1px 0 rgba(255,255,255,0.45), inset 0 -2px 6px rgba(0,0,0,0.18)`,
                          transform: on ? 'translateY(-1px)' : 'none',
                        }}
                      >
                        {!empty && (
                          <div className="flex h-full items-center gap-2 px-3 text-white">
                            <span className="text-sm font-semibold tabular-nums drop-shadow">{s.count}</span>
                            <span className="truncate text-[11px] opacity-90">
                              KES {kes(s.value)}
                            </span>
                          </div>
                        )}
                      </div>
                      {empty && (
                        <div className="pointer-events-none absolute inset-0 flex items-center px-3">
                          <span className="text-[11px] text-gray-400">no deals at this stage</span>
                        </div>
                      )}
                    </div>

                    <div className="w-32 shrink-0 text-right">
                      <div className="text-[11px] tabular-nums text-gray-600">
                        KES {kes(s.weighted)}
                      </div>
                      <div className="text-[10px] text-gray-400">weighted</div>
                    </div>
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

            {/* The side layer. A second axis over the same deals, never a filter. */}
            {(data.credit_layer ?? []).length > 0 && (
              <div className="mt-5">
                <div className="mb-1.5 text-xs font-semibold text-gray-600">
                  Where these deals sit inside the bank
                  <span className="ml-1 font-normal text-gray-400">
                    — inferred from win probability, not a sales stage
                  </span>
                </div>
                <div className="flex gap-1.5 overflow-x-auto pb-1">
                  {data.credit_layer.map((c, i) => (
                    <div key={c.label}
                         className="min-w-[132px] flex-1 rounded-lg border border-gray-200 p-2">
                      <div className="h-1.5 w-full overflow-hidden rounded-full bg-gray-100">
                        <div className="h-full rounded-full"
                             style={{ width: `${(c.count / creditMax) * 100}%`,
                                      background: bandColour(i, data.credit_layer.length) }} />
                      </div>
                      <div className="mt-1.5 truncate text-[11px] font-medium text-gray-700"
                           title={c.label}>{c.label}</div>
                      <div className="text-[10px] text-gray-400">
                        {Math.round(c.min * 100)}–{Math.round(Math.min(c.max, 1) * 100)}%
                      </div>
                      <div className="mt-0.5 text-sm font-semibold tabular-nums text-gray-900">
                        {c.count}
                      </div>
                      <div className="text-[10px] tabular-nums text-gray-500">
                        KES {kes(c.value)}
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </>
        )}
      </Card.Body>
    </Card>
  );
}
'''

PAGE_NEW = r'''// v10.510 Phase 4 Batch β1 — Pipeline page.
//
// First read-only consumer of the α1-α7 pipeline API surface. Shows
// the caller's cascade-scoped deal list with per-deal permission
// indicators (α7) visible inline. The mutation surface (create, edit,
// advance, refer, validate, cancel/request, cancel/approve) lands in
// subsequent β-batches.
//
// What this proves end-to-end:
//   1. α1's pipeline list endpoint returns data → React renders it
//   2. α2's cascade scope filters → caller sees only own/scope deals
//   3. α3's CRUD endpoint Pydantic typing → matches our TypeScript shape
//   4. α7's permissions object → React reads it without recomputing auth
//   5. The Bearer-header JWT lifecycle from Phase 1 → carries through
//      to a brand-new authenticated endpoint
//   6. The Provider pattern from Batch 2d → extends cleanly to a new domain
//
// Layout pattern matches Dashboard.tsx:
//   - Header strip with brand.secondary background (deep navy)
//   - max-w-7xl content column
//   - Stat strip at top for at-a-glance metrics
//   - Card-wrapped Table for the deal list
//   - Footer with branding ip_notice
//
// Composition: 100% bespoke v10.496 primitives. No new visual atoms.

import { displayName } from "../lib/names";
import { useEffect, useMemo, useRef, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { useBranding } from '@/hooks/useBranding';
import { usePipelineDeals } from '@/hooks/usePipelineDeals';
import { useRole } from '@/hooks/useRole';
import { fetchPipelineConfig, fetchPipelineAnalytics, fetchFunnelDrill, downloadFile } from '@/lib/api';
import { Card } from '@/components/Card';
import DefinedFunnel from '@/components/DefinedFunnel';
import { PageHeader } from '@/components/PageHeader';
import { Stat } from '@/components/Stat';
import { Badge, type BadgeTone } from '@/components/Badge';
import { Button } from '@/components/Button';
import { Table, type Column } from '@/components/Table';
import { PermissionBadges } from '@/components/PermissionBadges';
import { parseTs } from '@/lib/datetime';
import {
  stageTone,
  type PipelineDeal,
  type PipelineConfig,
  type PipelineAnalyticsResponse,
  type FunnelDrillResponse,
} from '@/types/pipeline';


// ── Display helpers ─────────────────────────────────────────────────────

/** Format a deal_value in the tenant's currency. Compact format for table cells. */
function formatValue(v: number, symbol: string): string {
  if (!Number.isFinite(v) || v === 0) return '—';
  return `${symbol} ${v.toLocaleString()}`;
}

/** Days a deal has been open, from its earliest available timestamp. */
function daysOpen(deal: PipelineDeal): number | null {
  const raw = deal.created_at || deal.open_date || deal.updated_at;
  if (!raw) return null;
  // parseTs, not new Date: a date-only open_date must anchor to LOCAL midnight,
  // otherwise the age is measured from 03:00 and can round down a whole day.
  const parsed = parseTs(raw);
  if (!parsed) return null;
  const start = parsed.getTime();
  if (!Number.isFinite(start)) return null;
  const diff = Date.now() - start;
  if (diff < 0) return 0;
  return Math.floor(diff / 86_400_000);
}

/** Traffic-light cell for a deal's attached SLA status. Null when no SLA applies
 *  (closed / no timestamp). */
function slaCell(deal: PipelineDeal): { tone: BadgeTone; label: string; title: string } | null {
  const s = deal.sla;
  if (!s || !s.state) return null;
  const clock = s.clock === 'step' ? (s.step || 'step').replace(/_/g, ' ') : 'age';
  if (s.state === 'breached') {
    return {
      tone: 'danger',
      label: `breached +${s.overdue_business_days ?? 0}`,
      title: `${clock}: ${s.elapsed_business_days ?? '?'}/${s.target_days ?? '?'} bd — escalate to ${(s.escalate_to || '').replace(/_/g, ' ') || 'step owner'}`,
    };
  }
  if (s.state === 'due_soon') {
    return { tone: 'warning', label: 'due soon', title: `${clock}: ${s.remaining_business_days ?? '?'} bd to target` };
  }
  return { tone: 'success', label: 'on track', title: `${clock}: ${s.remaining_business_days ?? '?'} bd to target` };
}


// ── Page component ──────────────────────────────────────────────────────

export function Pipeline() {
  const { branding } = useBranding();
  const { user } = useRole();
  const { deals, count, loading, error, refetch } = usePipelineDeals();

  // SLA traffic-light filter, driven by ?sla=on_track|due_soon|breached (e.g. from the
  // Analytics SLA summary card). Filters the already-loaded deals client-side on sla.state.
  const [searchParams, setSearchParams] = useSearchParams();
  const slaFilter = searchParams.get('sla');
  // Win-probability band filter (?winprob=high|medium|low). high ≥75, medium 40–74,
  // low <40 — derived per-deal from the current stage's product flow. Combines with sla.
  const winprobFilter = searchParams.get('winprob');
  const winprobBand = (wp: number | null | undefined): 'high' | 'medium' | 'low' | null => {
    if (typeof wp !== 'number') return null;
    return wp >= 75 ? 'high' : wp >= 40 ? 'medium' : 'low';
  };
  const [config, setConfig] = useState<PipelineConfig | null>(null);
  const [segmentFilter, setSegmentFilter] = useState('');
  // Two-level segment model, sourced from the configurable business units (customer_segments):
  //   Business unit (Consumer/Commercial/CIB/Treasury) -> its sub-segments (Premier/SME/...).
  // Each visible deal's sub-segment is resolved to its business unit via a reverse map, then
  // grouped by unit. A single-unit viewer (e.g. Consumer) therefore sees ONLY that unit's
  // sub-segments; a leaked cross-unit value groups under its OWN unit, never polluting another.
  const segmentGroups = useMemo(() => {
    const cfgSegs = config?.customer_segments ?? {};
    // reverse map: sub-segment -> business unit
    const subToUnit = new Map<string, string>();
    for (const [unit, subs] of Object.entries(cfgSegs)) {
      for (const sub of subs) subToUnit.set(sub, unit);
    }
    // tally sub-segment counts present in visible deals
    const counts = new Map<string, number>();
    for (const d of deals) {
      const k = (d.segment && String(d.segment).trim()) || 'Unclassified';
      counts.set(k, (counts.get(k) ?? 0) + 1);
    }
    // build ordered groups: business unit -> [{key, count}] in config order
    const groups: { unit: string; subs: { key: string; count: number }[] }[] = [];
    for (const [unit, subs] of Object.entries(cfgSegs)) {
      const present = subs
        .filter((sub) => counts.has(sub))
        .map((sub) => ({ key: sub, count: counts.get(sub) ?? 0 }));
      if (present.length) groups.push({ unit, subs: present });
    }
    // any present sub-segment that IS a bare business-unit name (mis-tagged) or unknown:
    // collect under an 'Other' group so it's visible but not mixed into a real unit.
    const known = new Set<string>();
    for (const g of groups) for (const s of g.subs) known.add(s.key);
    const other: { key: string; count: number }[] = [];
    for (const [k, c] of counts.entries()) {
      if (k === 'Unclassified') continue;
      if (!known.has(k) && !subToUnit.has(k)) other.push({ key: k, count: c });
    }
    if (other.length) groups.push({ unit: 'Other', subs: other });
    if (counts.has('Unclassified')) {
      groups.push({ unit: 'Unclassified', subs: [{ key: 'Unclassified', count: counts.get('Unclassified') ?? 0 }] });
    }
    return groups;
  }, [deals, config]);
  const singleUnit = segmentGroups.length === 1;
  const visibleDeals = useMemo(
    () => deals.filter((d) =>
      (!slaFilter || d.sla?.state === slaFilter)
      && (!winprobFilter || winprobBand(d.win_probability) === winprobFilter)
      && (!segmentFilter || (d.segment || 'Unclassified') === segmentFilter)),
    [deals, slaFilter, winprobFilter, segmentFilter],
  );
  const clearSlaFilter = () => {
    const next = new URLSearchParams(searchParams);
    next.delete('sla');
    setSearchParams(next, { replace: true });
  };
  const setWinprobFilter = (band: string) => {
    const next = new URLSearchParams(searchParams);
    if (band) next.set('winprob', band); else next.delete('winprob');
    setSearchParams(next, { replace: true });
  };

  // Batch A: admin-configured category/stage filters (from /api/pipeline/stages)
  const [catFilter, setCatFilter] = useState('');
  const [stageFilter, setStageFilter] = useState('');

  // Funnel stage-drill: click a band → fetch deals at that class+stage,
  // broken down by product and segment.
  const [drill, setDrill] = useState<FunnelDrillResponse | null>(null);
  const [drillLoading, setDrillLoading] = useState(false);
  const [drillVisible, setDrillVisible] = useState(50);
  const [exporting, setExporting] = useState(false);
  const drillRef = useRef<HTMLDivElement | null>(null);
  const onStageDrill = (cls: string, stage: string): void => {
    setDrillLoading(true);
    setDrill(null);
    setDrillVisible(50);
    fetchFunnelDrill(cls, stage)
      .then((d) => setDrill(d))
      .catch(() => setDrill(null))
      .finally(() => setDrillLoading(false));
  };
  // When the drill opens, bring the panel into view (the funnel can be tall,
  // so the panel would otherwise open below the fold).
  useEffect(() => {
    if (drill && drillRef.current) {
      drillRef.current.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }
  }, [drill]);

  useEffect(() => {
    let active = true;
    fetchPipelineConfig()
      .then((c) => { if (active) setConfig(c); })
      .catch(() => { /* dropdowns stay empty if config can't load */ });
    return () => { active = false; };
  }, []);

  // Analytics: validated/pending split, per-class buckets, the validated
  // funnel, and the scope-aware pending-validation count. Refetched whenever
  // the deal list settles (after create/validate/advance/refresh).
  const [analytics, setAnalytics] = useState<PipelineAnalyticsResponse | null>(null);
  useEffect(() => {
    if (loading) return;
    let active = true;
    fetchPipelineAnalytics()
      .then((a) => { if (active) setAnalytics(a); })
      .catch(() => { /* tiles fall back to local sums if analytics fails */ });
    return () => { active = false; };
  }, [loading, count]);

  // Stage options narrow to the selected category's flow; else all stages.
  const stageOptions = useMemo(() => {
    if (!config) return [] as string[];
    if (catFilter) {
      const cat = config.deal_categories.find((c) => c.category === catFilter);
      if (cat) return cat.stages;
    }
    return config.stages.map((s) => s.stage);
  }, [config, catFilter]);

  const onCategoryChange = (value: string) => {
    setCatFilter(value);
    setStageFilter('');
    void refetch({ category: value || undefined });
  };
  const onStageChange = (value: string) => {
    setStageFilter(value);
    void refetch({ category: catFilter || undefined, stage: value || undefined });
  };
  const navigate = useNavigate();

  const sym = branding?.currency_symbol ?? '';

  // Table column config — typed against PipelineDeal so render functions
  // get full intellisense on row data.
  const columns: Column<PipelineDeal>[] = useMemo(() => [
    {
      key: 'id',
      header: 'Deal ID',
      width: 110,
      sortable: true,
      exportValue: (row) => row.id,
      render: (row) => (
        <span className="font-mono text-xs text-gray-600">{row.id}</span>
      ),
    },
    {
      key: 'client_name',
      header: 'Client',
      sortable: true,
      exportValue: (row) => row.client_name || '',
      render: (row) => (
        <div>
          <div className="font-medium text-gray-900">{row.client_name || '—'}</div>
          {row.product_type && (
            <div className="text-xs text-gray-500 mt-0.5">{row.product_type}</div>
          )}
        </div>
      ),
    },
    {
      key: 'stage',
      header: 'Stage',
      sortable: true,
      exportValue: (row) => row.stage,
      render: (row) => (
        <Badge tone={stageTone(row.stage)} size="sm">{row.stage}</Badge>
      ),
    },
    {
      key: 'deal_value',
      header: 'Value',
      align: 'right',
      sortable: true,
      sortAccessor: (row) => Number(row.amount_kes ?? row.deal_value) || 0,
      exportValue: (row) => String(row.amount_kes ?? row.deal_value ?? ''),
      render: (row) => (
        <span className="font-medium text-gray-900">
          {formatValue(Number(row.amount_kes ?? row.deal_value), branding?.currency_symbol ?? '')}
        </span>
      ),
    },
    {
      key: 'aging',
      header: 'Age',
      align: 'right',
      sortable: true,
      sortAccessor: (row) => daysOpen(row) ?? -1,
      exportValue: (row) => { const d = daysOpen(row); return d == null ? '' : String(d); },
      render: (row) => {
        const d = daysOpen(row);
        if (d == null) return <span className="text-xs text-gray-400">—</span>;
        const stale = d > 14;
        return (
          <span className={`text-xs font-medium ${stale ? 'text-red-600' : 'text-gray-600'}`}>
            {d}d{stale ? ' · stale' : ''}
          </span>
        );
      },
    },
    {
      key: 'sla',
      header: 'SLA',
      exportValue: (row) => row.sla?.state || '',
      render: (row) => {
        const c = slaCell(row);
        if (!c) return <span className="text-xs text-gray-300">—</span>;
        return <span title={c.title}><Badge tone={c.tone} size="sm">{c.label}</Badge></span>;
      },
    },
    {
      key: 'win_probability',
      header: 'Win %',
      align: 'right',
      sortable: true,
      sortAccessor: (row) => (typeof row.win_probability === 'number' ? row.win_probability : -1),
      exportValue: (row) => (typeof row.win_probability === 'number' ? String(row.win_probability) : ''),
      render: (row) => {
        const wp = row.win_probability;
        if (typeof wp !== 'number') return <span className="text-xs text-gray-300">—</span>;
        const tone: BadgeTone = wp >= 75 ? 'success' : wp >= 40 ? 'info' : 'neutral';
        return (
          <span title="Likelihood of closing, from the current stage's product flow">
            <Badge tone={tone} size="sm">{Math.round(wp)}%</Badge>
          </span>
        );
      },
    },
    {
      key: 'staff_name',
      header: 'Owner',
      sortable: true,
      exportValue: (row) => row.staff_name || '',
      render: (row) => (
        <div>
          <div className="text-sm text-gray-800">{row.staff_name ? displayName(row.staff_name) : '—'}</div>
          {row.staff_code && (
            <div className="text-xs text-gray-400 mt-0.5 font-mono">
              {row.staff_code}
            </div>
          )}
        </div>
      ),
    },
    {
      key: 'permissions',
      header: 'You can',
      render: (row) => <PermissionBadges permissions={row.permissions} />,
    },
  // intentionally not depending on the dynamic data; column config is stable
  // eslint-disable-next-line react-hooks/exhaustive-deps
  ], [branding?.currency_symbol]);

  // ── Render ────────────────────────────────────────────────────────────

  return (
    <div className="min-h-screen bg-gray-50">
      <PageHeader
        ribbon
        breadcrumbs={[{ label: 'EKE Pipeline Intelligence System (PIS)' }, { label: 'EKE Sales Pro' }]}
        title="EKE Sales Pro"
        subtitle="Deals across your scope — assured value, stage, and ownership."
        actions={
          <>
            <Button
              variant="secondary"
              onClick={() => {
                setExporting(true);
                downloadFile('/pipeline/export/xlsx', 'EKE_Pipeline.xlsx')
                  .catch(() => { /* surfaced via button state only */ })
                  .finally(() => setExporting(false));
              }}
              disabled={exporting}
            >
              {exporting ? 'Exporting…' : 'Export Excel'}
            </Button>
            <Button variant="primary" onClick={() => navigate('/pipeline/new')}>
              + New Deal
            </Button>
          </>
        }
      />

      {/* Main content */}
      <main className="max-w-7xl 2xl:max-w-[1680px] mx-auto px-6 py-8">
        {/* Assured pipeline by product class — validated value headline,
            pending-assurance beneath. Sourced from /api/pipeline/analytics. */}
        <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
          <Stat
            label="Asset Pipeline"
            value={analytics ? formatValue(analytics.pipelines.asset.value, sym) : '—'}
            sub={analytics && analytics.pipelines.asset.pending_value > 0
              ? `${formatValue(analytics.pipelines.asset.pending_value, sym)} pending assurance`
              : 'Assured'}
            loading={loading}
            stripe={false}
            tone="primary"
            onClick={() => navigate('/analytics')}
          />
          <Stat
            label="Liability Pipeline"
            value={analytics ? formatValue(analytics.pipelines.liability.value, sym) : '—'}
            sub={analytics && analytics.pipelines.liability.pending_value > 0
              ? `${formatValue(analytics.pipelines.liability.pending_value, sym)} pending assurance`
              : 'Assured'}
            loading={loading}
            stripe={false}
            tone="success"
            onClick={() => navigate('/analytics')}
          />
          <Stat
            label="Insurance"
            value={analytics ? formatValue(analytics.pipelines.insurance.value, sym) : '—'}
            sub={analytics && analytics.pipelines.insurance.pending_value > 0
              ? `${formatValue(analytics.pipelines.insurance.pending_value, sym)} pending assurance`
              : 'Assured'}
            loading={loading}
            stripe={false}
            tone="lime"
            onClick={() => navigate('/analytics')}
          />
          <Stat
            label="Other"
            value={analytics ? formatValue(analytics.pipelines.other.value, sym) : '—'}
            sub={analytics && analytics.pipelines.other.pending_value > 0
              ? `${formatValue(analytics.pipelines.other.pending_value, sym)} pending assurance`
              : 'Assured'}
            loading={loading}
            stripe={false}
            tone="violet"
            onClick={() => navigate('/analytics')}
          />
        </div>

        {/* Scope summary row */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mt-4">
          <Stat
            label="Deals Visible"
            value={loading ? '—' : count}
            sub="In your cascade scope"
            loading={loading}
            stripe={false}
            tone="teal"
            onClick={() => navigate('/analytics')}
          />
          <Stat
            label="Pending Validation"
            value={analytics ? analytics.totals.pending_validation : (loading ? '—' : 0)}
            sub={analytics && analytics.totals.pending_validation > 0
              ? 'Awaiting your sign-off'
              : 'Nothing to validate'}
            loading={loading}
            stripe={false}
            tone={analytics && analytics.totals.pending_validation > 0 ? 'accent' : 'neutral'}
            onClick={() => navigate('/pipeline/queues')}
          />
          <Stat
            label="Total Assured"
            value={analytics ? formatValue(analytics.totals.total_value, sym) : '—'}
            sub={analytics && analytics.totals.pending_value > 0
              ? `${formatValue(analytics.totals.pending_value, sym)} pending assurance`
              : 'All validated'}
            loading={loading}
            stripe={false}
            tone="secondary"
            onClick={() => navigate('/analytics')}
          />
        </div>

        {/* Validated pipeline funnel */}
        <DefinedFunnel onStageClick={onStageDrill} />

        {/* Funnel stage-drill panel */}
        {(drillLoading || drill) && (
          <div ref={drillRef} className="scroll-mt-24">
          <Card className="mt-4 ring-2 ring-[var(--brand-primary)]/30">
            <Card.Header>
              <h2 className="text-base font-semibold text-gray-900">
                {drill ? `${drill.cls === 'all' ? 'All' : drill.cls[0].toUpperCase() + drill.cls.slice(1)} · ${drill.stage}` : 'Loading…'}
              </h2>
              <button
                type="button"
                onClick={() => setDrill(null)}
                className="text-xs text-gray-400 hover:text-gray-700"
              >
                Close ✕
              </button>
            </Card.Header>
            <Card.Body>
              {drillLoading && <div className="h-24 animate-pulse rounded bg-gray-100" />}
              {drill && (
                <div>
                  <div className="mb-4 text-sm text-gray-500">
                    <span className="font-semibold text-gray-800">{drill.totals.count}</span> assured deals ·{' '}
                    <span className="font-semibold text-gray-800">{formatValue(drill.totals.value, sym)}</span>
                  </div>
                  <div className="grid gap-6 md:grid-cols-3">
                    <DrillBreakdown title="By segment" rows={drill.by_segment.map((s) => ({ label: s.segment, value: s.value, count: s.count }))} sym={sym} />
                    <DrillBreakdown title="By sector" rows={drill.by_sector.map((s) => ({ label: s.sector, value: s.value, count: s.count }))} sym={sym} />
                    <DrillBreakdown title="By product" rows={drill.by_product.map((p) => ({ label: p.product, value: p.value, count: p.count }))} sym={sym} />
                  </div>
                  {drill.deals.length > 0 && (
                    <div className="mt-6 overflow-x-auto">
                      <table className="w-full text-sm">
                        <thead>
                          <tr className="border-b border-gray-200 text-left text-xs text-gray-500">
                            <th className="py-2 pr-3">Deal</th>
                            <th className="py-2 pr-3">Client</th>
                            <th className="py-2 pr-3">Product</th>
                            <th className="py-2 pr-3">Segment</th>
                            <th className="py-2 pr-3 text-right">Value</th>
                            <th className="py-2 pr-3">Owner</th>
                          </tr>
                        </thead>
                        <tbody>
                          {drill.deals.slice(0, drillVisible).map((d) => (
                            <tr key={d.id} className="border-b border-gray-100">
                              <td className="py-1.5 pr-3 font-mono text-xs text-gray-500">{d.id}</td>
                              <td className="py-1.5 pr-3 text-gray-800">{d.client_name}</td>
                              <td className="py-1.5 pr-3 text-gray-600">{d.product_type}</td>
                              <td className="py-1.5 pr-3 text-gray-600">{d.segment}</td>
                              <td className="py-1.5 pr-3 text-right tabular-nums text-gray-800">{formatValue(d.amount_kes, sym)}</td>
                              <td className="py-1.5 pr-3 text-gray-600">{displayName(d.staff_name)}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                      {drill.deals.length > drillVisible ? (
                        <div className="mt-2 flex items-center gap-3">
                          <Button variant="ghost" size="sm" onClick={() => setDrillVisible((n) => n + 50)}>
                            Show more ({drill.deals.length - drillVisible} more)
                          </Button>
                          <span className="text-xs text-gray-400">Showing {drillVisible} of {drill.deals.length}</span>
                        </div>
                      ) : drill.deals.length > 50 ? (
                        <div className="mt-2 text-xs text-gray-400">Showing all {drill.deals.length} deals.</div>
                      ) : null}
                    </div>
                  )}
                </div>
              )}
            </Card.Body>
          </Card>
          </div>
        )}

        {/* Error panel — only renders on error */}
        {error && (
          <Card className="mt-6">
            <Card.Body>
              <div className="flex items-center gap-3">
                <Badge tone="danger">Error</Badge>
                <div className="flex-1 text-sm text-gray-700">{error}</div>
                <Button variant="ghost" size="sm" onClick={() => void refetch()}>
                  Retry
                </Button>
              </div>
            </Card.Body>
          </Card>
        )}

        {/* Deal table */}
        <Card className="mt-8" padding="none">
          <Card.Header>
            <div className="flex items-center gap-3">
              <h2 className="text-base font-semibold text-gray-900">
                Pipeline Deals
              </h2>
                </div>
            <div className="flex items-center gap-2">
              <select
                value={catFilter}
                onChange={(e) => onCategoryChange(e.target.value)}
                aria-label="Filter by deal category"
                className="h-9 px-2 rounded-md border border-gray-300 bg-white text-sm text-gray-900 focus:outline-none focus:border-brand-primary focus:ring-2 focus:ring-brand-primary/20"
              >
                <option value="">All categories</option>
                {config?.deal_categories.map((c) => (
                  <option key={c.category} value={c.category}>{c.category}</option>
                ))}
              </select>
              <select
                value={stageFilter}
                onChange={(e) => onStageChange(e.target.value)}
                aria-label="Filter by stage"
                className="h-9 px-2 rounded-md border border-gray-300 bg-white text-sm text-gray-900 focus:outline-none focus:border-brand-primary focus:ring-2 focus:ring-brand-primary/20"
              >
                <option value="">All stages</option>
                {stageOptions.map((s) => (
                  <option key={s} value={s}>{s}</option>
                ))}
              </select>
              {segmentGroups.length > 0 && (
                <div className="flex flex-wrap items-center gap-2" role="tablist" aria-label="Filter by segment">
                  <div className="flex items-center gap-1 rounded-lg bg-gray-100 p-1">
                    <button
                      type="button"
                      onClick={() => setSegmentFilter('')}
                      className={[
                        'rounded-md px-3 py-1.5 text-xs font-semibold transition-colors',
                        segmentFilter === '' ? 'bg-white text-[var(--brand-secondary)] shadow-sm'
                                             : 'text-gray-500 hover:text-gray-800',
                      ].join(' ')}
                    >
                      All
                    </button>
                  </div>
                  {segmentGroups.map((g) => (
                    <div key={g.unit} className="flex items-center gap-1 rounded-lg bg-gray-100 p-1">
                      {!singleUnit && (
                        <span className="px-2 text-[10px] font-semibold uppercase tracking-wide text-gray-400">{g.unit}</span>
                      )}
                      {g.subs.map((sg) => {
                        const on = segmentFilter === sg.key;
                        return (
                          <button
                            key={sg.key}
                            type="button"
                            onClick={() => setSegmentFilter(sg.key)}
                            className={[
                              'rounded-md px-3 py-1.5 text-xs font-semibold transition-colors',
                              on ? 'bg-white text-[var(--brand-secondary)] shadow-sm'
                                 : 'text-gray-500 hover:text-gray-800',
                            ].join(' ')}
                          >
                            {sg.key}
                            <span className="ml-1.5 text-gray-400">{sg.count}</span>
                          </button>
                        );
                      })}
                    </div>
                  ))}
                </div>
              )}
              <select
                value={winprobFilter ?? ''}
                onChange={(e) => setWinprobFilter(e.target.value)}
                aria-label="Filter by win probability"
                className="h-9 px-2 rounded-md border border-gray-300 bg-white text-sm text-gray-900 focus:outline-none focus:border-brand-primary focus:ring-2 focus:ring-brand-primary/20"
              >
                <option value="">All win %</option>
                <option value="high">High (≥75%)</option>
                <option value="medium">Medium (40–74%)</option>
                <option value="low">Low (&lt;40%)</option>
              </select>
              <Button
                variant="ghost"
                size="sm"
                onClick={() => void refetch()}
                loading={loading}
              >
                Refresh
              </Button>
            </div>
          </Card.Header>
          <Card.Body className="p-4">
            {slaFilter && (
              <div className="mb-3 flex items-center gap-2 text-sm">
                <span className="text-gray-500">SLA filter:</span>
                <Badge
                  tone={slaFilter === 'breached' ? 'danger' : slaFilter === 'due_soon' ? 'warning' : 'success'}
                  size="sm"
                >
                  {slaFilter.replace(/_/g, ' ')}
                </Badge>
                <span className="text-xs text-gray-400">{visibleDeals.length} of {deals.length}</span>
                <button onClick={clearSlaFilter} className="text-xs text-brand-primary hover:underline">clear</button>
              </div>
            )}
            {winprobFilter && (
              <div className="mb-3 flex items-center gap-2 text-sm">
                <span className="text-gray-500">Win probability:</span>
                <Badge
                  tone={winprobFilter === 'high' ? 'success' : winprobFilter === 'medium' ? 'info' : 'neutral'}
                  size="sm"
                >
                  {winprobFilter === 'high' ? 'High (≥75%)' : winprobFilter === 'medium' ? 'Medium (40–74%)' : 'Low (<40%)'}
                </Badge>
                <span className="text-xs text-gray-400">{visibleDeals.length} of {deals.length}</span>
                <button onClick={() => setWinprobFilter('')} className="text-xs text-brand-primary hover:underline">clear</button>
              </div>
            )}
            <Table<PipelineDeal>
              columns={columns}
              rows={visibleDeals}
              rowKey="id"
              loading={loading}
              searchable
              searchPlaceholder="Search deals by client, stage, owner…"
              paginated
              pageSize={25}
              onRowClick={(row) => navigate(`/pipeline/${encodeURIComponent(row.id)}`)}
              empty={
                <div className="py-8">
                  <div className="text-base text-gray-700 font-medium">
                    No deals in your scope.
                  </div>
                  <div className="text-sm text-gray-500 mt-1">
                    {user?.role && `As ${user.role}, you see deals from your cascade.`}
                  </div>
                </div>
              }
            />
          </Card.Body>
        </Card>

        {/* Status footer — what this page is and isn't */}
        <Card className="mt-6">
          <Card.Body>
            <div className="text-xs text-gray-500 leading-relaxed">
              Click any deal row to view its detail page. Advance and
              cancel-request actions live there, gated by the per-deal
              permissions from α7. Create-deal and manager queues land
              in subsequent β-batches.
            </div>
          </Card.Body>
        </Card>

        {/* IP notice footer — verbatim from /api/branding */}
        <footer className="mt-12 pb-6 text-center text-[11px] text-gray-400 leading-relaxed">
          {branding?.ip_notice}
        </footer>
      </main>
    </div>
  );
}

// ── Drill breakdown: a compact value-ranked bar list (segment / product) ──
function DrillBreakdown({
  title, rows, sym,
}: {
  title: string;
  rows: { label: string; value: number; count: number }[];
  sym: string;
}) {
  const max = Math.max(...rows.map((r) => r.value), 1);
  const PALETTE = ['#06b6d4', '#3b82f6', '#6366f1', '#a855f7', '#ec4899', '#f59e0b', '#10b981', '#14b8a6'];
  return (
    <div>
      <div className="mb-2 text-xs font-semibold uppercase tracking-wide text-gray-400">{title}</div>
      {rows.length === 0 ? (
        <div className="text-sm text-gray-400">No data.</div>
      ) : (
        <div className="space-y-2">
          {rows.slice(0, 8).map((r, i) => (
            <div key={r.label} className="flex items-center gap-3">
              <div className="w-28 shrink-0 truncate text-xs text-gray-600" title={r.label}>{r.label}</div>
              <div className="h-4 flex-1 rounded bg-gray-100">
                <div
                  className="h-4 rounded"
                  style={{ width: `${Math.max(4, Math.round((r.value / max) * 100))}%`, background: PALETTE[i % PALETTE.length] }}
                />
              </div>
              <div className="w-32 shrink-0 text-right text-xs text-gray-500">
                {formatValue(r.value, sym)} <span className="text-gray-400">· {r.count}</span>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
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
        print("ABORT: %s already exists - F2 looks applied." % COMP)
        return 1
    if not os.path.isfile(os.path.join("utils", "pipeline_funnel.py")):
        print("ABORT: apply patch_f1_funnel_model.py first - this reads its endpoint.")
        return 1

    ts = open(APITS, encoding="utf-8").read()
    if "fetchPipelineDefinedFunnel" in ts:
        print("ABORT: api.ts already has the defined-funnel client.")
        return 1
    anchor = "// \u2500\u2500 Cumulative leaderboard (staff / role / branch / unit) \u2500\u2500"
    if ts.count(anchor) != 1:
        print("ABORT: api.ts anchor matched %d times." % ts.count(anchor))
        return 1
    ts = ts.replace(anchor, TS_NEW + anchor, 1)
    print("  ok  api.ts - defined funnel client")

    for token in ("no deals at this stage", "credit_layer", "unplaced_deals",
                  "onStageClick"):
        if token not in COMPONENT:
            print("ABORT: embedded component missing %r." % token)
            return 1
    if "PipelineFunnel" in PAGE_NEW:
        print("ABORT: the page still references the old funnel component.")
        return 1
    if "onStageClick={onStageDrill}" not in PAGE_NEW:
        print("ABORT: the stage drill was not reconnected - that would silently")
        print("       remove a working feature.")
        return 1
    for name, blob in (("component", COMPONENT), ("page", PAGE_NEW)):
        for op, cl in (("{", "}"), ("(", ")")):
            if blob.count(op) != blob.count(cl):
                print("ABORT: embedded %s unbalanced %s%s." % (name, op, cl))
                return 1
    if "fetchBranchLogHistoryGrid" not in ts:
        print("ABORT: post-check - api.ts lost an existing client.")
        return 1
    print("  ok  post-checks: drill preserved, api.ts intact")

    if not apply:
        print("\nDRY RUN - nothing written. Re-run with --apply.")
        return 0

    open(COMP, "w", encoding="utf-8", newline="").write(COMPONENT)
    print("CREATED %s" % COMP)
    for path, content in ((APITS, ts), (PAGE, PAGE_NEW)):
        shutil.copy2(path, path + BACKUP_SUFFIX)
        open(path, "w", encoding="utf-8", newline="").write(content)
        print("APPLIED %s" % path)

    print("")
    print("The old PipelineFunnel.tsx is now unused but left in place - deleting a")
    print("component in the same step as replacing it makes a revert harder.")
    print("Next: pushd frontend\\web && pnpm tsc --noEmit && popd && echo TSC_PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
