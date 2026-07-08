import { useNavigate } from 'react-router-dom';
import { useBranding } from '@/hooks/useBranding';
import { useMdDashboard } from '@/hooks/useMdDashboard';
import { useCreditOpenWork } from '@/hooks/useCreditOpenWork';
import { Card } from '@/components/Card';
import { KpiTile } from '@/components/KpiTile';
import { Button } from '@/components/Button';
import { ExceptionsStrip } from '@/components/ExceptionsStrip';
import { ChartCard } from '@/components/charts/ChartCard';
import { DonutChart } from '@/components/charts/DonutChart';
import { CategoryBarChart } from '@/components/charts/CategoryBarChart';
import { ragColor } from '@/lib/chartTheme';
import type { RagStatus } from '@/components/RagChip';
import type { MdDashboardResponse } from '@/types/dashboard';

function bscStatus(avg: number): RagStatus {
  if (avg >= 80) return 'on_track';
  if (avg >= 65) return 'at_risk';
  return 'off_track';
}
function nplStatus(pct: number): RagStatus {
  if (pct <= 5)  return 'on_track';
  if (pct <= 10) return 'at_risk';
  return 'off_track';
}
// Guards against a null/undefined numeric field reaching .toLocaleString()
// (e.g. a SQL SUM/AVG over zero matching rows returns NULL, not 0).
function num(n: number | null | undefined): string {
  return (n ?? 0).toLocaleString();
}
function abbrev(n: number): string {
  const a = Math.abs(n);
  if (a >= 1e12) return (n / 1e12).toFixed(2) + 'T';
  if (a >= 1e9)  return (n / 1e9).toFixed(2) + 'B';
  if (a >= 1e6)  return (n / 1e6).toFixed(1) + 'M';
  if (a >= 1e3)  return (n / 1e3).toFixed(1) + 'K';
  return n.toLocaleString();
}

export function Dashboard() {
  const navigate = useNavigate();
  const { branding, loading: brandingLoading } = useBranding();
  const { data, loading, error, refetch } = useMdDashboard();
  const { data: credit, loading: creditLoading } = useCreditOpenWork();

  if (brandingLoading) return <div className="dash-loading">Loading…</div>;
  if (!branding)       return <div className="dash-loading" style={{ color: 'var(--danger)' }}>Branding unavailable.</div>;

  const sym  = branding.currency_symbol || '';
  const kes  = (v: number) => `${sym} ${abbrev(v)}`.trim();
  const d: MdDashboardResponse | null = data;
  const show = (fn: (x: MdDashboardResponse) => string) => d ? fn(d) : '—';

  return (
    <div className="pg">

      {/* Hero — pipeline figure + three quick-nav chips */}
      <div className="card dashboard-hero">
        <div className="dashboard-hero-body">
          <div className="dashboard-hero-label">Total Pipeline · KES-equivalent</div>
          <div className="dashboard-hero-value">{show((x) => kes(x.pipeline.pipeline_value))}</div>
          <div className="dashboard-hero-meta">
            <span>LCY {show((x) => kes(x.pipeline.lcy_value ?? 0))}</span>
            <span>FCY {show((x) => kes(x.pipeline.fcy_value ?? 0))}</span>
            <span>{show((x) => num(x.pipeline.total_deals))} live deals</span>
            <button type="button" className="sec-lnk" onClick={() => navigate('/analytics')}>Drill into pipeline →</button>
          </div>
        </div>
        <div className="dashboard-hero-chips">
          {([
            ['BSC avg',   show((x) => x.bsc.overall_avg.toFixed(1)),         '/perform'],
            ['NPL ratio', show((x) => `${x.credit.npl_ratio_pct}%`),         '/credit-analytics'],
            ['Assured',   show((x) => kes(x.pipeline.validated_value ?? 0)), '/analytics'],
          ] as [string, string, string][]).map(([lbl, val, to]) => (
            <button key={lbl} type="button" className="dashboard-hero-chip" onClick={() => navigate(to)}>
              <span className="dashboard-hero-chip-label">{lbl}</span>
              <span className="dashboard-hero-chip-val">{val}</span>
            </button>
          ))}
        </div>
      </div>

      {error && (
        <Card className="mb-5">
          <div className="flex items-center justify-between gap-4 p-3">
            <p className="dash-error-text">Couldn't load dashboard: {error}</p>
            <Button variant="ghost" size="sm" onClick={() => refetch()}>Retry</Button>
          </div>
        </Card>
      )}

      <ExceptionsStrip />

      {/* Performance & Risk */}
      <div className="dash-section-head">
        <span className="sec-lbl">Performance &amp; Risk</span>
        <button type="button" className="sec-lnk" onClick={() => navigate('/credit-analytics')}>Credit drill →</button>
      </div>
      <div className="dash-kpi-row">
        <KpiTile label="BSC Score (bank avg)" actual={show((x) => x.bsc.overall_avg.toFixed(1))} target="100" status={d ? bscStatus(d.bsc.overall_avg) : undefined} loading={loading} />
        <KpiTile label="NPL Ratio" actual={show((x) => `${x.credit.npl_ratio_pct.toFixed(1)}%`)} invert status={d ? nplStatus(d.credit.npl_ratio_pct) : undefined} loading={loading} />
        <div className="kpi">
          <div className="kpi-label">Loan Book</div>
          <div className="kpi-value">{show((x) => `${sym} ${x.credit.outstanding_bn.toFixed(1)}B`)}</div>
        </div>
        <div className="kpi">
          <div className="kpi-label">Total Accounts</div>
          <div className="kpi-value">{show((x) => num(x.credit.total_accounts))}</div>
        </div>
      </div>

      {/* Pipeline */}
      <div className="dash-section-head">
        <span className="sec-lbl">Pipeline</span>
        <button type="button" className="sec-lnk" onClick={() => navigate('/analytics')}>Pipeline drill →</button>
      </div>
      <div className="dash-kpi-row">
        <div className="kpi">
          <div className="kpi-label">Assured Pipeline</div>
          <div className="kpi-value">{show((x) => kes(x.pipeline.validated_value ?? 0))}</div>
          <div className="kpi-sub">{show((x) => `${kes(x.pipeline.pending_value ?? 0)} pending`)} assurance</div>
        </div>
        <div className="kpi">
          <div className="kpi-label">Closed-Won</div>
          <div className="kpi-value">{show((x) => kes(x.pipeline.won_value))}</div>
        </div>
        <div className="kpi">
          <div className="kpi-label">Total Deals</div>
          <div className="kpi-value">{show((x) => num(x.pipeline.total_deals))}</div>
        </div>
        <div className="kpi">
          <div className="kpi-label">LCY — KES equiv.</div>
          <div className="kpi-value">{show((x) => kes(x.pipeline.lcy_value ?? 0))}</div>
        </div>
        <div className="kpi">
          <div className="kpi-label">FCY — KES equiv.</div>
          <div className="kpi-value">{show((x) => kes(x.pipeline.fcy_value ?? 0))}</div>
        </div>
      </div>

      {/* Compliance & Org */}
      <div className="dash-section-head">
        <span className="sec-lbl">Compliance &amp; Organisation</span>
      </div>
      <div className="dash-kpi-row">
        <div className="kpi"><div className="kpi-label">AML Open Alerts</div><div className="kpi-value">{show((x) => num(x.aml.open_alerts))}</div></div>
        <div className="kpi"><div className="kpi-label">High-Risk Flags</div><div className="kpi-value">{show((x) => num(x.aml.high_risk))}</div></div>
        <div className="kpi"><div className="kpi-label">Active Staff</div><div className="kpi-value">{show((x) => num(x.org.total_staff))}</div></div>
        <div className="kpi"><div className="kpi-label">Departments</div><div className="kpi-value">{show((x) => num(x.org.departments))}</div></div>
      </div>

      {/* Credit Risk charts */}
      <div className="dash-section-head">
        <span className="sec-lbl">Credit Risk</span>
      </div>
      <div className="dash-chart-row">
        <ChartCard title="IFRS9 Stage Distribution" subtitle="Loan book by impairment stage" loading={creditLoading} empty={!credit || credit.ifrs9_total === 0} emptyMessage="No IFRS9 loan records available.">
          <DonutChart
            centerValue={credit ? num(credit.ifrs9_total) : ''}
            centerLabel="IFRS9 Loans"
            data={[
              { name: 'Stage 1 — Performing',   value: credit?.ifrs9_stage1 ?? 0, color: ragColor.on_track },
              { name: 'Stage 2 — Watch (SICR)', value: credit?.ifrs9_stage2 ?? 0, color: ragColor.at_risk },
              { name: 'Stage 3 — NPL',           value: credit?.ifrs9_stage3 ?? 0, color: ragColor.off_track },
            ]}
          />
        </ChartCard>
        <ChartCard title="Credit Analysis by Lane" subtitle="Open credit work landscape" loading={creditLoading} empty={!credit || Object.keys(credit.applications_by_stage || {}).length === 0} emptyMessage="No loan applications in flight.">
          <CategoryBarChart
            xKey="lane"
            series={[{ key: 'count', label: 'Applications' }]}
            data={Object.entries(credit?.applications_by_stage ?? {}).map(([lane, count]) => ({ lane, count }))}
          />
        </ChartCard>
      </div>

      <div className="dash-kpi-row dash-kpi-row-mt">
        <div className="kpi"><div className="kpi-label">NPL (IFRS9 Stage 3)</div><div className="kpi-value">{creditLoading ? '—' : (credit?.npl_pct == null ? 'n/a' : `${credit.npl_pct.toFixed(1)}%`)}</div></div>
        <div className="kpi"><div className="kpi-label">Watchlist Entries</div><div className="kpi-value">{creditLoading ? '—' : (credit?.watchlist_count ?? 0).toLocaleString()}</div></div>
        <div className="kpi"><div className="kpi-label">Open Applications</div><div className="kpi-value">{creditLoading ? '—' : (credit?.applications_open ?? 0).toLocaleString()}</div></div>
      </div>

      <div className="dash-footer">
        <span>{d?.generated_at ? `Snapshot: ${new Date(d.generated_at).toLocaleString()}` : ''}</span>
        <Button variant="ghost" size="sm" onClick={() => refetch()} disabled={loading}>{loading ? 'Refreshing…' : 'Refresh'}</Button>
      </div>
      {branding.ip_notice && <p className="dash-ip">{branding.ip_notice}</p>}
    </div>
  );
}
