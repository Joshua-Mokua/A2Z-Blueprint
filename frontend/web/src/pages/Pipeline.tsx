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

import { useMemo } from 'react';
import { useBranding } from '@/hooks/useBranding';
import { usePipelineDeals } from '@/hooks/usePipelineDeals';
import { useRole } from '@/hooks/useRole';
import { Card } from '@/components/Card';
import { Stat } from '@/components/Stat';
import { Badge } from '@/components/Badge';
import { Button } from '@/components/Button';
import { Table, type Column } from '@/components/Table';
import { PermissionBadges } from '@/components/PermissionBadges';
import { stageTone, type PipelineDeal } from '@/types/pipeline';


// ── Display helpers ─────────────────────────────────────────────────────

/** Format a deal_value in the tenant's currency. Compact format for table cells. */
function formatValue(v: number, symbol: string): string {
  if (!Number.isFinite(v) || v === 0) return '—';
  if (v >= 1e9) return `${symbol} ${(v / 1e9).toFixed(2)}B`;
  if (v >= 1e6) return `${symbol} ${(v / 1e6).toFixed(2)}M`;
  if (v >= 1e3) return `${symbol} ${(v / 1e3).toFixed(0)}K`;
  return `${symbol} ${v.toLocaleString()}`;
}

/** Sum active (non-terminal, non-draft) deal value. */
function totalActiveValue(deals: PipelineDeal[]): number {
  const terminal = new Set(['Closed Won', 'Closed Lost', 'Account Opened', 'Funded']);
  return deals
    .filter((d) => !d.draft && !terminal.has(d.stage))
    .reduce((sum, d) => sum + (Number(d.deal_value) || 0), 0);
}


// ── Page component ──────────────────────────────────────────────────────

export function Pipeline() {
  const { branding } = useBranding();
  const { user } = useRole();
  const { deals, count, loading, error, refetch } = usePipelineDeals();

  // Derived KPIs — memoized so re-renders from props don't recompute
  const totalValue = useMemo(() => totalActiveValue(deals), [deals]);
  const dealsAtRisk = useMemo(
    () => deals.filter((d) => d.cancel_requested && !d.cancel_approved).length,
    [deals],
  );
  const dealsPending = useMemo(
    () => deals.filter((d) => !d.manager_validated
                              && d.stage !== 'Lead'
                              && !d.draft).length,
    [deals],
  );

  // Table column config — typed against PipelineDeal so render functions
  // get full intellisense on row data.
  const columns: Column<PipelineDeal>[] = useMemo(() => [
    {
      key: 'id',
      header: 'Deal ID',
      width: 110,
      render: (row) => (
        <span className="font-mono text-xs text-gray-600">{row.id}</span>
      ),
    },
    {
      key: 'client_name',
      header: 'Client',
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
      render: (row) => (
        <Badge tone={stageTone(row.stage)} size="sm">{row.stage}</Badge>
      ),
    },
    {
      key: 'deal_value',
      header: 'Value',
      align: 'right',
      render: (row) => (
        <span className="font-medium text-gray-900">
          {formatValue(Number(row.deal_value), branding?.currency_symbol ?? '')}
        </span>
      ),
    },
    {
      key: 'staff_name',
      header: 'Owner',
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
        <div className="max-w-7xl mx-auto flex items-center justify-between flex-wrap gap-4">
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
      <main className="max-w-7xl mx-auto px-6 py-8">
        {/* KPI strip — three Stats summarizing what we just loaded */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
          <Stat
            label="Deals Visible"
            value={loading ? '—' : count}
            sub="In your cascade scope"
            loading={loading}
          />
          <Stat
            label="Active Pipeline Value"
            value={loading
              ? '—'
              : formatValue(totalValue, branding?.currency_symbol ?? '')}
            sub="Excluding closed and drafts"
            loading={loading}
            stripe="primary"
          />
          <Stat
            label="Pending Validation"
            value={loading ? '—' : dealsPending}
            sub={dealsAtRisk > 0
              ? `${dealsAtRisk} cancel request${dealsAtRisk === 1 ? '' : 's'} pending`
              : 'No cancel requests'}
            loading={loading}
            stripe={dealsAtRisk > 0 ? 'accent' : 'secondary'}
          />
        </div>

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
              <Badge tone="brand" size="sm">v10.510 β1</Badge>
            </div>
            <Button
              variant="ghost"
              size="sm"
              onClick={() => void refetch()}
              loading={loading}
            >
              Refresh
            </Button>
          </Card.Header>
          <Card.Body className="p-0">
            <Table<PipelineDeal>
              columns={columns}
              rows={deals}
              rowKey="id"
              loading={loading}
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
              This is the read-only first cut of the Pipeline page.
              Create, edit, advance, refer, validate, and cancellation
              flows ship in subsequent β-batches. The{' '}
              <span className="font-semibold">You can</span> column
              shows what the server says you're allowed to do per deal —
              that's α7's per-deal permission resolution wired through.
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
