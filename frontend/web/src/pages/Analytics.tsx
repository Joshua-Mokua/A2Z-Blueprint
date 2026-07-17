// #3b — Analytics page. Consumes /api/pipeline/analytics (KES-equivalent,
// dashboard-consistent) and showcases the pipeline across products, sectors,
// currency book, the conversion funnel, and the four product-class pipelines.

import { useMemo, useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAnalytics } from '@/hooks/useAnalytics';
import { fetchPipelineDrill, fetchSlaViolations } from '@/lib/api';
import type { UnitBreakdown, PipelineDrillResponse } from '@/types/pipeline';
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
  const DIMENSIONS = ['Product', 'Segment', 'Sector', 'Stage', 'Currency', 'Branch', 'RM'] as const;
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
    }
  };

  return (
    <>
      <PageHeader
        ribbon
        breadcrumbs={[{ label: 'EKE Pipeline Intelligence System (PIS)' }, { label: 'EKE Sales Pro Analytics' }]}
        title="EKE Sales Pro Analytics"
        subtitle="Assured pipeline in KES-equivalent — consistent with the MD dashboard."
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
      <PipelineSlicer dimensions={DIMENSIONS} sliceFor={sliceFor} kes={kes} />

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
  dimensions, sliceFor, kes,
}: {
  dimensions: readonly string[];
  sliceFor: (d: never) => { label: string; value: number; count: number }[];
  kes: (n: number) => string;
}) {
  const [dim, setDim] = useState<string>('Product');
  // Stage renders as a funnel (server/flow order preserved); Sector & Currency
  // as donuts (share); everything else as ranked bars (value-sorted).
  const isFunnel = dim === 'Stage';
  const isDonut = dim === 'Sector' || dim === 'Segment' || dim === 'Currency';
  const rows = useMemo(() => {
    const raw = sliceFor(dim as never);
    return isFunnel ? raw : raw.slice().sort((a, b) => b.value - a.value);
  }, [dim, sliceFor, isFunnel]);
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
        {rows.length === 0 ? (
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
