// #3b — Analytics page. Consumes /api/pipeline/analytics (KES-equivalent,
// dashboard-consistent) and showcases the pipeline across products, sectors,
// currency book, the conversion funnel, and the four product-class pipelines.

import { useMemo } from 'react';
import { useAnalytics } from '@/hooks/useAnalytics';
import { useBranding } from '@/hooks/useBranding';
import { Card } from '@/components/Card';
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

export function Analytics() {
  const { branding } = useBranding();
  const { data, loading, error } = useAnalytics();
  const sym = branding?.currency_symbol ?? 'KES';
  const kes = (n: number) => `${sym} ${abbrev(n)}`;

  const productData = useMemo(
    () => (data?.by_product ?? []).slice(0, 10),
    [data],
  );
  const sectorData = useMemo(
    () => (data?.by_sector ?? []).map((s) => ({ name: s.sector, value: s.value })),
    [data],
  );
  const currencyData = useMemo(() => {
    const cb = data?.by_currency_book;
    if (!cb) return [];
    return [
      { name: 'Local (LCY)',   value: cb.LCY?.value ?? 0 },
      { name: 'Foreign (FCY)', value: cb.FCY?.value ?? 0 },
    ];
  }, [data]);

  if (loading) {
    return (
      <div className="p-6 max-w-6xl mx-auto space-y-4">
        <Skeleton /><Skeleton /><Skeleton />
      </div>
    );
  }
  if (error || !data) {
    return (
      <div className="p-6 max-w-6xl mx-auto">
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

  return (
    <div className="p-6 max-w-6xl mx-auto">
      <h1 className="text-xl font-semibold text-gray-900">Pipeline Analytics</h1>
      <p className="text-sm text-gray-500 mb-6">
        Assured pipeline in KES-equivalent — consistent with the MD dashboard.
      </p>

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

      {/* Product mix */}
      <h2 className="text-xs font-semibold uppercase tracking-wider text-gray-500 mt-8 mb-3">
        Pipeline by Product
      </h2>
      <Card><Card.Body>
        {productData.length > 0 ? (
          <CategoryBarChart
            data={productData as unknown as Array<Record<string, unknown>>}
            xKey="product"
            series={[{ key: 'value', label: 'Pipeline value' }]}
            height={300}
          />
        ) : <p className="text-sm text-gray-500">No product data.</p>}
      </Card.Body></Card>

      {/* Sector + Currency book */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 mt-4">
        <Card>
          <Card.Header>By Sector</Card.Header>
          <Card.Body>
            {sectorData.length > 0 ? (
              <DonutChart data={sectorData} height={280} />
            ) : <p className="text-sm text-gray-500">No sector data.</p>}
          </Card.Body>
        </Card>
        <Card>
          <Card.Header>Currency Book (KES-equiv.)</Card.Header>
          <Card.Body>
            {currencyData.length > 0 ? (
              <DonutChart data={currencyData} height={280}
                          centerLabel="Total"
                          centerValue={abbrev(currencyData.reduce((s, d) => s + d.value, 0))} />
            ) : <p className="text-sm text-gray-500">No currency data.</p>}
          </Card.Body>
        </Card>
      </div>

      {/* Conversion funnel */}
      <h2 className="text-xs font-semibold uppercase tracking-wider text-gray-500 mt-8 mb-3">
        Conversion Funnel (assured)
      </h2>
      <Card><Card.Body>
        {data.funnel.length > 0 ? (
          <CategoryBarChart
            data={data.funnel as unknown as Array<Record<string, unknown>>}
            xKey="stage"
            series={[{ key: 'value', label: 'Value' }]}
            height={280}
          />
        ) : <p className="text-sm text-gray-500">No funnel data.</p>}
      </Card.Body></Card>

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
  );
}
