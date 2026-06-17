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

import { useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useBranding } from '@/hooks/useBranding';
import { usePipelineDeals } from '@/hooks/usePipelineDeals';
import { useRole } from '@/hooks/useRole';
import { fetchPipelineConfig, fetchPipelineAnalytics } from '@/lib/api';
import { Card } from '@/components/Card';
import { Stat } from '@/components/Stat';
import { Badge } from '@/components/Badge';
import { Button } from '@/components/Button';
import { Table, type Column } from '@/components/Table';
import { PermissionBadges } from '@/components/PermissionBadges';
import { PipelineFunnel } from '@/components/PipelineFunnel';
import {
  stageTone,
  type PipelineDeal,
  type PipelineConfig,
  type PipelineAnalyticsResponse,
} from '@/types/pipeline';


// ── Display helpers ─────────────────────────────────────────────────────

/** Format a deal_value in the tenant's currency. Compact format for table cells. */
function formatValue(v: number, symbol: string): string {
  if (!Number.isFinite(v) || v === 0) return '—';
  if (v >= 1e9) return `${symbol} ${(v / 1e9).toFixed(2)}B`;
  if (v >= 1e6) return `${symbol} ${(v / 1e6).toFixed(2)}M`;
  if (v >= 1e3) return `${symbol} ${(v / 1e3).toFixed(0)}K`;
  return `${symbol} ${v.toLocaleString()}`;
}

/** Days a deal has been open, from its earliest available timestamp. */
function daysOpen(deal: PipelineDeal): number | null {
  const raw = deal.created_at || deal.open_date || deal.updated_at;
  if (!raw) return null;
  const start = new Date(raw).getTime();
  if (!Number.isFinite(start)) return null;
  const diff = Date.now() - start;
  if (diff < 0) return 0;
  return Math.floor(diff / 86_400_000);
}


// ── Page component ──────────────────────────────────────────────────────

export function Pipeline() {
  const { branding } = useBranding();
  const { user } = useRole();
  const { deals, count, loading, error, refetch } = usePipelineDeals();

  // Batch A: admin-configured category/stage filters (from /api/pipeline/stages)
  const [config, setConfig] = useState<PipelineConfig | null>(null);
  const [catFilter, setCatFilter] = useState('');
  const [stageFilter, setStageFilter] = useState('');

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
      sortAccessor: (row) => Number(row.deal_value) || 0,
      exportValue: (row) => String(row.deal_value ?? ''),
      render: (row) => (
        <span className="font-medium text-gray-900">
          {formatValue(Number(row.deal_value), branding?.currency_symbol ?? '')}
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
      key: 'staff_name',
      header: 'Owner',
      sortable: true,
      exportValue: (row) => row.staff_name || '',
      render: (row) => (
        <div>
          <div className="text-sm text-gray-800">{row.staff_name || '—'}</div>
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
      {/* Header — matches Dashboard pattern */}
      <header
        className="px-6 py-5 text-white shadow-sm"
        style={{ background: 'var(--brand-secondary)' }}
      >
        <div className="max-w-7xl 2xl:max-w-[1680px] mx-auto flex items-center justify-between flex-wrap gap-4">
          <div>
            <div className="text-[11px] uppercase tracking-[2.5px] font-bold opacity-70">
              {branding?.bank_name ?? 'A2Z MIS 360'}
            </div>
            <h1 className="text-xl font-bold mt-1">
              {branding?.app_name ?? 'A2Z'} MIS 360 — Pipeline
            </h1>
          </div>
          <div className="text-right text-xs opacity-70 leading-relaxed">
            {user?.full_name && (
              <div className="font-medium opacity-90">{user.full_name}</div>
            )}
            {user?.role && <div>{user.role}</div>}
          </div>
        </div>
      </header>

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
            stripe="primary"
          />
          <Stat
            label="Liability Pipeline"
            value={analytics ? formatValue(analytics.pipelines.liability.value, sym) : '—'}
            sub={analytics && analytics.pipelines.liability.pending_value > 0
              ? `${formatValue(analytics.pipelines.liability.pending_value, sym)} pending assurance`
              : 'Assured'}
            loading={loading}
            stripe="secondary"
          />
          <Stat
            label="Insurance"
            value={analytics ? formatValue(analytics.pipelines.insurance.value, sym) : '—'}
            sub={analytics && analytics.pipelines.insurance.pending_value > 0
              ? `${formatValue(analytics.pipelines.insurance.pending_value, sym)} pending assurance`
              : 'Assured'}
            loading={loading}
            stripe="accent"
          />
          <Stat
            label="Other"
            value={analytics ? formatValue(analytics.pipelines.other.value, sym) : '—'}
            sub={analytics && analytics.pipelines.other.pending_value > 0
              ? `${formatValue(analytics.pipelines.other.pending_value, sym)} pending assurance`
              : 'Assured'}
            loading={loading}
          />
        </div>

        {/* Scope summary row */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mt-4">
          <Stat
            label="Deals Visible"
            value={loading ? '—' : count}
            sub="In your cascade scope"
            loading={loading}
          />
          <Stat
            label="Pending Validation"
            value={analytics ? analytics.totals.pending_validation : (loading ? '—' : 0)}
            sub={analytics && analytics.totals.pending_validation > 0
              ? 'Awaiting your sign-off'
              : 'Nothing to validate'}
            loading={loading}
            stripe={analytics && analytics.totals.pending_validation > 0 ? 'accent' : 'secondary'}
          />
          <Stat
            label="Total Assured"
            value={analytics ? formatValue(analytics.totals.total_value, sym) : '—'}
            sub={analytics && analytics.totals.pending_value > 0
              ? `${formatValue(analytics.totals.pending_value, sym)} pending assurance`
              : 'All validated'}
            loading={loading}
          />
        </div>

        {/* Validated pipeline funnel */}
        <Card className="mt-6">
          <Card.Header>
            <h2 className="text-base font-semibold text-gray-900">
              Validated pipeline funnel
            </h2>
            <span className="text-xs text-gray-400">Assured deals by stage</span>
          </Card.Header>
          <Card.Body>
            <PipelineFunnel
              stages={analytics?.funnel ?? []}
              currencySymbol={sym}
              emptyHint="No validated deals yet — validate deals to populate the funnel."
            />
          </Card.Body>
        </Card>

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
              <Badge tone="brand" size="sm">v10.582 capstone</Badge>
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
              <Button
                variant="ghost"
                size="sm"
                onClick={() => void refetch()}
                loading={loading}
              >
                Refresh
              </Button>
              <Button
                variant="primary"
                size="sm"
                onClick={() => navigate('/pipeline/new')}
              >
                + New Deal
              </Button>
            </div>
          </Card.Header>
          <Card.Body className="p-4">
            <Table<PipelineDeal>
              columns={columns}
              rows={deals}
              rowKey="id"
              loading={loading}
              searchable
              searchPlaceholder="Search deals by client, stage, owner…"
              paginated
              pageSize={25}
              exportable
              exportFilename="pipeline-deals.csv"
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
