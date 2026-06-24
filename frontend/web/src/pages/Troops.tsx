// Troops — Treasury Back Office disbursement flow by stage. Shows the live
// disbursement workload (cleared → booked → value-dated → disbursed) so the
// disbursement desk and Operations can prep against what sits at each step.
// Role-gated server-side to Treasury Back Office; a non-Troops caller gets a
// clear access message rather than an error.

import { useEffect, useMemo, useState } from 'react';
import { useBranding } from '@/hooks/useBranding';
import { fetchTroopsFlowByStage, type TroopsFlowByStageResponse } from '@/lib/api';
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

const DONE_KEY = 'disbursed';

export function Troops() {
  const { branding } = useBranding();
  const sym = branding?.currency_symbol ?? 'KES';
  const kes = (n: number) => `${sym} ${abbrev(n)}`;

  const [data, setData] = useState<TroopsFlowByStageResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [forbidden, setForbidden] = useState(false);

  useEffect(() => {
    let active = true;
    setLoading(true);
    fetchTroopsFlowByStage()
      .then((d) => { if (active) { setData(d); setError(null); setForbidden(false); } })
      .catch((e) => {
        if (!active) return;
        const msg = e instanceof Error ? e.message : '';
        if (msg.includes('403') || /authority|forbidden/i.test(msg)) {
          setForbidden(true);
        } else {
          setError(msg || 'Could not load disbursement flow.');
        }
      })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, []);

  const barData = useMemo(
    () => (data?.stages ?? [])
      .filter((s) => s.key !== DONE_KEY)
      .map((s) => ({ stage: s.label, cases: s.count })),
    [data],
  );

  if (loading) {
    return <div className="p-6 max-w-7xl 2xl:max-w-[1680px] mx-auto space-y-4"><Skeleton /><Skeleton /><Skeleton /></div>;
  }

  if (forbidden) {
    return (
      <>
        <PageHeader
          breadcrumbs={[{ label: 'A2Z Credit Intelligence System (CIS)' }, { label: 'Troops Disbursement' }]}
          title="Troops Disbursement"
          subtitle="Treasury Back Office disbursement desk."
        />
        <div className="p-6 max-w-7xl 2xl:max-w-[1680px] mx-auto">
          <Card><Card.Body>
            <p className="text-sm text-gray-700">
              This view is for the Treasury Back Office disbursement desk. Your role doesn’t
              have disbursement authority, so there’s nothing to action here.
            </p>
          </Card.Body></Card>
        </div>
      </>
    );
  }

  if (error || !data) {
    return (
      <div className="p-6 max-w-7xl 2xl:max-w-[1680px] mx-auto">
        <Card><Card.Body>
          <p className="text-sm text-red-600">{error ?? 'No disbursement flow available.'}</p>
        </Card.Body></Card>
      </div>
    );
  }

  const t = data.totals;

  return (
    <>
      <PageHeader
        breadcrumbs={[{ label: 'A2Z Credit Intelligence System (CIS)' }, { label: 'Troops Disbursement' }]}
        title="Troops Disbursement"
        subtitle="Treasury Back Office disbursement flow by stage — cleared facilities moving through booking, value-dating, and disbursement."
      />
      <div className="p-6 max-w-7xl 2xl:max-w-[1680px] mx-auto space-y-6">

        <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
          <Stat label="Pending disbursement" value={t.pending_count.toLocaleString()} sub="cleared, not yet disbursed" />
          <Stat label="Pending value" value={kes(t.pending_value)} />
          <Stat label="All cases" value={t.count.toLocaleString()} sub="incl. disbursed" />
          <Stat label="Total value" value={kes(t.value)} />
        </div>

        {barData.length > 0 && (
          <Card>
            <Card.Header>
              <h2 className="text-base font-semibold text-gray-900">Disbursement workload by stage</h2>
              <span className="text-xs text-gray-400">Cases awaiting disbursement</span>
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
                  const done = s.key === DONE_KEY;
                  return (
                    <tr key={s.key} className="border-b border-gray-100 last:border-0">
                      <td className="py-2 text-gray-800">{s.label}</td>
                      <td className="py-2 text-right tabular-nums font-medium text-gray-900">
                        {s.count.toLocaleString()}
                      </td>
                      <td className="py-2 text-right tabular-nums text-gray-700">{kes(s.value)}</td>
                      <td className="py-2 text-right">
                        <Badge tone={done ? 'neutral' : s.count > 0 ? 'info' : 'neutral'} size="sm">
                          {done ? 'done' : s.count > 0 ? 'pending' : 'clear'}
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
