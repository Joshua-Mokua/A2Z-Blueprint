// v10.545 Phase P Batch P4 — CEO / MD Command Centre (live).
//
// Replaces the v10.496 shell. Consumes /api/dashboard/md via
// useMdDashboard and renders the executive aggregate with the P3a
// intelligence primitives (KpiTile + RagChip) plus Stat for raw values.
//
// RAG thresholds below are PRESENTATION HEURISTICS for the executive
// glance — not authoritative targets. Authoritative RAG should come from
// the Target Cascade once bank-level targets are wired into this payload;
// until then these give a sensible red/amber/green without inventing
// precise numbers into the data layer.

import { useBranding } from '@/hooks/useBranding';
import { useRole } from '@/hooks/useRole';
import { useMdDashboard } from '@/hooks/useMdDashboard';
import { useCreditOpenWork } from '@/hooks/useCreditOpenWork';
import { Card } from '@/components/Card';
import { Stat } from '@/components/Stat';
import { KpiTile } from '@/components/KpiTile';
import { Button } from '@/components/Button';
import { ChartCard } from '@/components/charts/ChartCard';
import { DonutChart } from '@/components/charts/DonutChart';
import { CategoryBarChart } from '@/components/charts/CategoryBarChart';
import { ragColor } from '@/lib/chartTheme';
import type { RagStatus } from '@/components/RagChip';
import type { MdDashboardResponse } from '@/types/dashboard';

// ── RAG heuristics (presentation only) ──────────────────────────────────
function bscStatus(avg: number): RagStatus {
  if (avg >= 80) return 'on_track';
  if (avg >= 65) return 'at_risk';
  return 'off_track';
}
function nplStatus(pct: number): RagStatus {
  // Lower is better. Industry-style bands; tune when real targets land.
  if (pct <= 5) return 'on_track';
  if (pct <= 10) return 'at_risk';
  return 'off_track';
}

// ── Number formatting ───────────────────────────────────────────────────
function abbrev(n: number): string {
  const a = Math.abs(n);
  if (a >= 1e12) return (n / 1e12).toFixed(2) + 'T';
  if (a >= 1e9)  return (n / 1e9).toFixed(2) + 'B';
  if (a >= 1e6)  return (n / 1e6).toFixed(1) + 'M';
  if (a >= 1e3)  return (n / 1e3).toFixed(1) + 'K';
  return n.toLocaleString();
}

export function Dashboard() {
  const { branding, loading: brandingLoading } = useBranding();
  const { user } = useRole();
  const { data, loading, error, refetch } = useMdDashboard();
  const { data: credit, loading: creditLoading } = useCreditOpenWork();

  if (brandingLoading) {
    return (
      <div className="flex items-center justify-center min-h-screen text-gray-500">
        Loading…
      </div>
    );
  }
  if (!branding) {
    return (
      <div className="flex items-center justify-center min-h-screen text-red-700">
        Branding unavailable.
      </div>
    );
  }

  const sym = branding.currency_symbol || '';
  const kes = (v: number) => `${sym} ${abbrev(v)}`.trim();

  // Null-safe accessor: returns the formatted value, or '—' when data
  // isn't present (error state with loading already false).
  const d: MdDashboardResponse | null = data;
  const show = (fn: (x: MdDashboardResponse) => string): string =>
    d ? fn(d) : '—';

  return (
    <div className="min-h-screen bg-gray-50">
      {/* Header */}
      <header
        className="px-6 py-5 text-white shadow-sm"
        style={{ background: branding.brand.secondary }}
      >
        <div className="max-w-7xl mx-auto flex items-center justify-between flex-wrap gap-4">
          <div>
            <div className="text-[11px] uppercase tracking-[2.5px] font-bold opacity-70">
              {branding.bank_name}
            </div>
            <h1 className="text-xl font-bold mt-1">
              {branding.app_name} MIS 360 — Executive Command Centre
            </h1>
            {user && (
              <div className="text-xs opacity-70 mt-1">
                {user.full_name} · {user.role}
              </div>
            )}
          </div>
          <div className="text-right text-xs opacity-70 leading-relaxed">
            <div>{branding.regulator_full}</div>
            <div>{branding.core_banking_system}</div>
          </div>
        </div>
      </header>

      <main className="max-w-7xl mx-auto px-6 py-8">
        {error && (
          <Card className="mb-6 border-red-200">
            <div className="flex items-center justify-between gap-4">
              <p className="text-sm text-red-700">
                Couldn't load the dashboard: {error}
              </p>
              <Button variant="ghost" size="sm" onClick={() => refetch()}>
                Retry
              </Button>
            </div>
          </Card>
        )}

        {/* Performance & Risk — RAG tiles */}
        <h2 className="text-xs font-semibold uppercase tracking-wider text-gray-500 mb-3">
          Performance &amp; Risk
        </h2>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
          <KpiTile
            label="BSC Score (bank avg)"
            actual={show((x) => x.bsc.overall_avg.toFixed(1))}
            target="100"
            status={d ? bscStatus(d.bsc.overall_avg) : undefined}
            loading={loading}
          />
          <KpiTile
            label="NPL Ratio"
            actual={show((x) => `${x.credit.npl_ratio_pct.toFixed(1)}%`)}
            invert
            status={d ? nplStatus(d.credit.npl_ratio_pct) : undefined}
            loading={loading}
          />
          <Stat
            label="Loan Book"
            value={show((x) => `${sym} ${x.credit.outstanding_bn.toFixed(1)}B`)}
            loading={loading}
            stripe="secondary"
          />
          <Stat
            label="Total Accounts"
            value={show((x) => x.credit.total_accounts.toLocaleString())}
            loading={loading}
            stripe="secondary"
          />
        </div>

        {/* Pipeline */}
        <h2 className="text-xs font-semibold uppercase tracking-wider text-gray-500 mt-8 mb-3">
          Pipeline
        </h2>
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
          <Stat label="Assured Pipeline Value"
                value={show((x) => kes(x.pipeline.validated_value ?? 0))}
                sub={show((x) => `${kes(x.pipeline.pending_value ?? 0)} pending assurance`)}
                loading={loading} />
          <Stat label="Closed-Won Value"
                value={show((x) => kes(x.pipeline.won_value))}
                loading={loading} />
          <Stat label="Total Deals"
                value={show((x) => x.pipeline.total_deals.toLocaleString())}
                loading={loading} />
        </div>

        {/* Currency book split (FCY/LCY) — KES-equivalent. */}
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 mt-4">
          <Stat label="Local Currency (LCY) — KES equiv."
                value={show((x) => kes(x.pipeline.lcy_value ?? 0))}
                sub={show((x) => {
                  const l = x.pipeline.lcy_value ?? 0, f = x.pipeline.fcy_value ?? 0;
                  const t = l + f;
                  return t > 0 ? `${((l / t) * 100).toFixed(1)}% of pipeline` : '—';
                })}
                loading={loading} />
          <Stat label="Foreign Currency (FCY) — KES equiv."
                value={show((x) => kes(x.pipeline.fcy_value ?? 0))}
                sub={show((x) => {
                  const l = x.pipeline.lcy_value ?? 0, f = x.pipeline.fcy_value ?? 0;
                  const t = l + f;
                  return t > 0 ? `${((f / t) * 100).toFixed(1)}% of pipeline` : '—';
                })}
                loading={loading} />
        </div>

        {/* Compliance & Org */}
        <h2 className="text-xs font-semibold uppercase tracking-wider text-gray-500 mt-8 mb-3">
          Compliance &amp; Organisation
        </h2>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
          <Stat label="AML Open Alerts"
                value={show((x) => x.aml.open_alerts.toLocaleString())}
                loading={loading} />
          <Stat label="High-Risk Flags"
                value={show((x) => x.aml.high_risk.toLocaleString())}
                loading={loading} />
          <Stat label="Active Staff"
                value={show((x) => x.org.total_staff.toLocaleString())}
                loading={loading} />
          <Stat label="Departments"
                value={show((x) => x.org.departments.toLocaleString())}
                loading={loading} />
        </div>

        {/* Credit Risk — charts from /api/cockpit/credit/open-work */}
        <h2 className="text-xs font-semibold uppercase tracking-wider text-gray-500 mt-8 mb-3">
          Credit Risk
        </h2>
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          <ChartCard
            title="IFRS9 Stage Distribution"
            subtitle="Loan book by impairment stage"
            loading={creditLoading}
            empty={!credit || credit.ifrs9_total === 0}
            emptyMessage="No IFRS9 loan records available."
          >
            <DonutChart
              centerValue={credit ? credit.ifrs9_total.toLocaleString() : ''}
              centerLabel="IFRS9 Loans"
              data={[
                { name: 'Stage 1 — Performing', value: credit?.ifrs9_stage1 ?? 0, color: ragColor.on_track },
                { name: 'Stage 2 — Watch (SICR)', value: credit?.ifrs9_stage2 ?? 0, color: ragColor.at_risk },
                { name: 'Stage 3 — NPL', value: credit?.ifrs9_stage3 ?? 0, color: ragColor.off_track },
              ]}
            />
          </ChartCard>

          <ChartCard
            title="Loan Applications by Lane"
            subtitle="Open credit work landscape"
            loading={creditLoading}
            empty={!credit || Object.keys(credit.applications_by_stage || {}).length === 0}
            emptyMessage="No loan applications in flight."
          >
            <CategoryBarChart
              xKey="lane"
              series={[{ key: 'count', label: 'Applications' }]}
              data={Object.entries(credit?.applications_by_stage ?? {}).map(
                ([lane, count]) => ({ lane, count }),
              )}
            />
          </ChartCard>
        </div>

        <div className="mt-4 grid grid-cols-1 sm:grid-cols-3 gap-4">
          <Stat label="NPL (IFRS9 Stage 3)"
                value={creditLoading ? '—'
                  : (credit?.npl_pct == null ? 'n/a' : `${credit.npl_pct.toFixed(1)}%`)}
                loading={creditLoading} />
          <Stat label="Watchlist Entries"
                value={creditLoading ? '—' : (credit?.watchlist_count ?? 0).toLocaleString()}
                loading={creditLoading} />
          <Stat label="Open Applications"
                value={creditLoading ? '—' : (credit?.applications_open ?? 0).toLocaleString()}
                loading={creditLoading} />
        </div>

        {/* Footer: freshness + refresh + ip notice */}
        <div className="mt-8 flex items-center justify-between gap-4 flex-wrap">
          <div className="text-xs text-gray-400">
            {d?.generated_at
              ? `Snapshot: ${new Date(d.generated_at).toLocaleString()}`
              : ''}
          </div>
          <Button variant="ghost" size="sm" onClick={() => refetch()} disabled={loading}>
            {loading ? 'Refreshing…' : 'Refresh'}
          </Button>
        </div>

        <footer className="mt-10 pb-6 text-center text-[11px] text-gray-400 leading-relaxed">
          {branding.ip_notice}
        </footer>
      </main>
    </div>
  );
}
