// v10.510 Phase 4 Batch β1 — Pipeline page.
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
  // COMPACT ABOVE A MILLION. "KES 632,907,965.8" is eighteen characters and
  // overflowed the card at text-3xl; nobody reads the last six digits of a
  // pipeline total anyway. The exact figure stays in the tooltip.
  const abs = Math.abs(v);
  if (abs >= 1_000_000_000) return `${symbol} ${(v / 1_000_000_000).toFixed(2)}B`;
  if (abs >= 1_000_000) return `${symbol} ${(v / 1_000_000).toFixed(1)}M`;
  return `${symbol} ${Math.round(v).toLocaleString()}`;
}

/** The exact figure, for a title attribute - compact display should never be
 *  the only place a number exists. */
function exactValue(v: number, symbol: string): string {
  if (!Number.isFinite(v)) return '—';
  return `${symbol} ${v.toLocaleString(undefined, { maximumFractionDigits: 2 })}`;
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

  // ── THE BUSINESS-LINE SELECTOR, BESIDE THE FUNNEL ────────────────────────
  // It used to sit above the deal list as a row of chips that wrapped, with
  // sub-segments inline beside their line - so "Consumer Premier Direct
  // Advantage Commercial SME..." ran together and the shape of the hierarchy
  // was lost. Vertical, it reads as what it is: three lines, each with its own
  // sub-segments underneath.
  //
  // It lives in the funnel's empty right-hand side, which puts the thing you
  // filter BY next to the thing it filters - and the funnel now follows the
  // selection, so the two panels always describe the same book.
  const segmentAside = segmentGroups.length === 0 ? null : (
    <div role="tablist" aria-label="Filter by segment" className="text-sm">
      <div className="mb-2 text-[11px] font-semibold uppercase tracking-wide text-gray-600">
        Business line
      </div>
      <button
        type="button"
        onClick={() => setSegmentFilter('')}
        className={[
          'mb-1 w-full rounded-md px-2.5 py-1.5 text-left text-xs font-semibold transition-colors',
          segmentFilter === '' ? 'bg-[#005B82] text-white'
                               : 'text-gray-900 hover:bg-[#0082BB]/10 hover:text-[#005B82]',
        ].join(' ')}
      >
        All
      </button>
      {segmentGroups.map((g) => {
        const unitKey = `unit:${g.unit}`;
        const unitOn = segmentFilter === unitKey;
        const total = g.subs.reduce((a, x) => a + x.count, 0);
        return (
          <div key={g.unit} className="mb-1">
            <button
              type="button"
              onClick={() => setSegmentFilter(unitOn ? '' : unitKey)}
              title={`All ${g.unit} deals`}
              className={[
                'flex w-full items-center justify-between rounded-md px-2.5 py-1.5',
                'text-xs font-semibold transition-colors',
                unitOn ? 'bg-[#005B82] text-white'
                       : 'text-gray-900 hover:bg-[#0082BB]/10 hover:text-[#005B82]',
              ].join(' ')}
            >
              <span>{g.unit}</span>
              <span className={unitOn ? 'text-white/80'
                                      : 'font-semibold text-[#005B82]'}>{total}</span>
            </button>
            {/* Sub-segments sit UNDER their line, indented, so the hierarchy
                is visible rather than implied by ordering. */}
            <div className="ml-2 border-l-2 border-[#0082BB]/25 pl-2">
              {g.subs.map((sg) => {
                const on = segmentFilter === sg.key;
                return (
                  <button
                    key={sg.key}
                    type="button"
                    onClick={() => setSegmentFilter(on ? '' : sg.key)}
                    className={[
                      'flex w-full items-center justify-between rounded-md px-2 py-1',
                      'text-[11px] transition-colors',
                      on ? 'bg-[#0082BB]/15 font-semibold text-[#005B82]'
                         : 'text-gray-700 hover:bg-[#0082BB]/10 hover:text-[#005B82]',
                    ].join(' ')}
                  >
                    <span className="truncate">{sg.key}</span>
                    <span className="ml-2 shrink-0 font-medium text-gray-600">{sg.count}</span>
                  </button>
                );
              })}
            </div>
          </div>
        );
      })}
    </div>
  );

  const visibleDeals = useMemo(
    () => deals.filter((d) =>
      (!slaFilter || d.sla?.state === slaFilter)
      && (!winprobFilter || winprobBand(d.win_probability) === winprobFilter)
      // A filter of `unit:Consumer` matches every sub-segment configured under
      // Consumer, so the line can be read as one. Anything else is the exact
      // sub-segment, as before.
      && (!segmentFilter
          || (segmentFilter.startsWith('unit:')
              ? (segmentGroups.find((g) => `unit:${g.unit}` === segmentFilter)?.subs ?? [])
                  .some((sg) => sg.key === (d.segment || 'Unclassified'))
              : (d.segment || 'Unclassified') === segmentFilter))),
    [deals, slaFilter, winprobFilter, segmentFilter, segmentGroups],
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
    // THE HEADLINE FIGURES FOLLOW THE BUSINESS LINE, like the funnel below
    // them. Without this the top of the page described the whole book while
    // everything under it described one line.
    fetchPipelineAnalytics({
      unit: segmentFilter.startsWith('unit:') ? segmentFilter.slice(5) : undefined,
      segment: segmentFilter && !segmentFilter.startsWith('unit:') ? segmentFilter : undefined,
    })
      .then((a) => { if (active) setAnalytics(a); })
      .catch(() => { /* tiles fall back to local sums if analytics fails */ });
    return () => { active = false; };
  }, [loading, count, segmentFilter]);

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
        // STICKY: the ribbon carries Export and New Deal, and it scrolled away
        // the moment somebody moved down the deal list - so the two things they
        // most often want were only reachable by scrolling back up.
        sticky
        // The breadcrumb repeated what the bar above already says. One trail is
        // a trail; two is noise. The subtitle carries the only line that was
        // adding anything.
        title="A2Z Sales Pro"
        subtitle="Your pipeline"
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
        {/* FOUR ACROSS, and now exactly four cards. With five children the fifth
            wrapped onto a row of its own and the block looked broken. */}
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
          <Stat
            label="Asset Pipeline"
            value={analytics ? formatValue(analytics.pipelines.asset.value, sym) : '—'}
            titleText={analytics ? exactValue(analytics.pipelines.asset.value, sym) : undefined}
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
            titleText={analytics ? exactValue(analytics.pipelines.liability.value, sym) : undefined}
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
          {/* "Total Assured" REMOVED (ruling 2026-08-13): it added the asset
              and liability books together, which is not a number anybody uses -
              a loan and a deposit do not sum to anything meaningful. The two
              books are already shown separately above. */}
        </div>

        {/* Validated pipeline funnel */}
        <DefinedFunnel
          onStageClick={onStageDrill}
          unit={segmentFilter.startsWith('unit:') ? segmentFilter.slice(5) : undefined}
          segment={segmentFilter && !segmentFilter.startsWith('unit:')
            ? segmentFilter : undefined}
          aside={segmentAside}
        />

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
