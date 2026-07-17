// Credit Analytics — pipeline-origin credit FLOW by workflow stage, scoped to
// the caller's cascade. This is the live credit workload (so Operations can prep
// against what's sitting at each step), NOT the loan book / NPL view — that is
// deferred to the Phase-2 Credit Monitoring module.

import { useEffect, useMemo, useState } from 'react';
import { useBranding } from '@/hooks/useBranding';
import { fetchCreditFlowByStage, type CreditFlowByStageResponse } from '@/lib/api';
import { Card } from '@/components/Card';
import { PageHeader } from '@/components/PageHeader';
import { Skeleton } from '@/components/Skeleton';
import { Badge } from '@/components/Badge';
import { CategoryBarChart } from '@/components/charts/CategoryBarChart';

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
    <Card><Card.Body>
      <div className="text-xs uppercase tracking-wider text-gray-500">{label}</div>
      <div className="text-2xl font-semibold text-gray-900 mt-1">{value}</div>
      {sub && <div className="text-xs text-gray-500 mt-1">{sub}</div>}
    </Card.Body></Card>
  );
}

// Terminal stages are shown but visually distinct from in-flight work.
const TERMINAL_KEYS = new Set(['disbursed', 'declined']);

export function CreditAnalytics() {
  const { branding } = useBranding();
  const sym = branding?.currency_symbol ?? 'KES';
  const kes = (n: number) => `${sym} ${abbrev(n)}`;

  const [data, setData] = useState<CreditFlowByStageResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    setLoading(true);
    fetchCreditFlowByStage()
      .then((d) => { if (active) { setData(d); setError(null); } })
      .catch((e) => { if (active) setError(e instanceof Error ? e.message : 'Could not load credit flow.'); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, []);

  const barData = useMemo(
    () => (data?.stages ?? [])
      .filter((s) => !TERMINAL_KEYS.has(s.key))
      .map((s) => ({ stage: s.label, cases: s.count })),
    [data],
  );

  if (loading) {
    return <div className="p-6 max-w-7xl 2xl:max-w-[1680px] mx-auto space-y-4"><Skeleton /><Skeleton /><Skeleton /></div>;
  }
  if (error || !data) {
    return (
      <div className="p-6 max-w-7xl 2xl:max-w-[1680px] mx-auto">
        <Card><Card.Body>
          <p className="text-sm text-red-600">{error ?? 'No credit flow available.'}</p>
        </Card.Body></Card>
      </div>
    );
  }

  const t = data.totals;

  return (
    <>
      <PageHeader
        ribbon
        breadcrumbs={[{ label: 'EKE Credit Intelligence System (CIS)' }, { label: 'Credit Analytics' }]}
        title="Credit Analytics"
        subtitle="Pipeline-origin credit flow within your scope — live cases by workflow stage, so the team can prep workload. (Loan-book / NPL analytics arrive with the Credit Monitoring module.)"
      />
      <div className="p-6 max-w-7xl 2xl:max-w-[1680px] mx-auto space-y-6">

        <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
          <Stat label="Cases in flight" value={t.in_flight_count.toLocaleString()} sub="not yet disbursed/declined" />
          <Stat label="In-flight value" value={kes(t.in_flight_value)} />
          <Stat label="All cases" value={t.count.toLocaleString()} sub="incl. disbursed & declined" />
          <Stat label="Total value" value={kes(t.value)} />
        </div>

        {barData.length > 0 && (
          <Card>
            <Card.Header>
              <h2 className="text-base font-semibold text-gray-900">Workload by stage</h2>
              <span className="text-xs text-gray-400">In-flight credit cases</span>
            </Card.Header>
            <Card.Body>
              <CategoryBarChart
                data={barData}
                xKey="stage"
                series={[{ key: 'cases', label: 'Cases' }]}
              />
            </Card.Body>
          </Card>
        )}

        <Card>
          <Card.Header>
            <h2 className="text-base font-semibold text-gray-900">Cases by stage</h2>
            <span className="text-xs text-gray-400">Count &amp; value at each step</span>
          </Card.Header>
          <Card.Body>
            <table className="w-full text-sm">
              <thead>
                <tr className="text-xs uppercase tracking-wider text-gray-500 border-b border-gray-200">
                  <th className="py-2 text-left">Stage</th>
                  <th className="py-2 text-right">Cases</th>
                  <th className="py-2 text-right">Value</th>
                  <th className="py-2 text-right">Status</th>
                </tr>
              </thead>
              <tbody>
                {data.stages.map((s) => {
                  const terminal = TERMINAL_KEYS.has(s.key);
                  return (
                    <tr key={s.key} className="border-b border-gray-100 last:border-0">
                      <td className="py-2 text-gray-800">{s.label}</td>
                      <td className="py-2 text-right tabular-nums font-medium text-gray-900">
                        {s.count.toLocaleString()}
                      </td>
                      <td className="py-2 text-right tabular-nums text-gray-700">{kes(s.value)}</td>
                      <td className="py-2 text-right">
                        <Badge tone={terminal ? 'neutral' : s.count > 0 ? 'info' : 'neutral'} size="sm">
                          {terminal ? 'closed' : s.count > 0 ? 'active' : 'clear'}
                        </Badge>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </Card.Body>
        </Card>

      </div>
    </>
  );
}
