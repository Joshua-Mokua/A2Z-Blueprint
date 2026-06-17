// Credit Analytics — loan book over the caller's scoped accounts. KPIs, a
// dimension slicer (Class / Region / Branch / RM) with NPL per slice, and a
// click-to-drill Region -> Branch -> RM -> individual account. Mirrors the
// pipeline Analytics page.

import { useMemo, useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { useCreditAnalytics } from '@/hooks/useCreditAnalytics';
import { useBranding } from '@/hooks/useBranding';
import { fetchCreditDrill } from '@/lib/api';
import type {
  CreditRegionBreakdown, CreditDrillResponse,
} from '@/types/creditAnalytics';
import { Card } from '@/components/Card';
import { Skeleton } from '@/components/Skeleton';
import { Badge } from '@/components/Badge';
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
    <Card><Card.Body>
      <div className="text-xs uppercase tracking-wider text-gray-500">{label}</div>
      <div className="text-2xl font-semibold text-gray-900 mt-1">{value}</div>
      {sub && <div className="text-xs text-gray-500 mt-1">{sub}</div>}
    </Card.Body></Card>
  );
}

function nplTone(pct: number): 'success' | 'warning' | 'danger' {
  if (pct >= 10) return 'danger';
  if (pct >= 5) return 'warning';
  return 'success';
}

export function CreditAnalytics() {
  const { branding } = useBranding();
  const { data, loading, error } = useCreditAnalytics();
  const sym = branding?.currency_symbol ?? 'KES';
  const kes = (n: number) => `${sym} ${abbrev(n)}`;

  if (loading) {
    return <div className="p-6 max-w-6xl mx-auto space-y-4"><Skeleton /><Skeleton /><Skeleton /></div>;
  }
  if (error || !data) {
    return (
      <div className="p-6 max-w-6xl mx-auto">
        <Card><Card.Body>
          <p className="text-sm text-red-600">{error ?? 'No credit analytics available.'}</p>
        </Card.Body></Card>
      </div>
    );
  }

  const t = data.totals;

  return (
    <div className="p-6 max-w-6xl mx-auto">
      <h1 className="text-xl font-semibold text-gray-900">Credit Analytics</h1>
      <p className="text-sm text-gray-500 mb-6">
        Loan book within your scope — outstanding and NPL by classification, region, branch, and RM.
      </p>

      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-4">
        <Stat label="Outstanding" value={kes(t.outstanding)} sub={`${t.accounts.toLocaleString()} accounts`} />
        <Stat label="NPL Outstanding" value={kes(t.npl_outstanding)} sub={`${t.npl_count.toLocaleString()} accounts`} />
        <Stat label="NPL Ratio" value={`${t.npl_ratio_pct}%`} />
        <Stat label="Accounts" value={t.accounts.toLocaleString()} />
        <Stat label="Performing" value={kes(t.outstanding - t.npl_outstanding)} />
      </div>

      <CreditSlicer data={data} kes={kes} />

      <CreditDrill regions={data.by_region} kes={kes} />
    </div>
  );
}

// ── slicer: pick a dimension, see outstanding + NPL by it ────────────────
function CreditSlicer({
  data, kes,
}: {
  data: import('@/types/creditAnalytics').CreditAnalyticsResponse;
  kes: (n: number) => string;
}) {
  const DIMENSIONS = ['Classification', 'Region', 'Branch', 'RM'] as const;
  const [dim, setDim] = useState<string>('Classification');

  type Row = { label: string; outstanding: number; accounts: number; npl_ratio_pct: number };
  const rows: Row[] = useMemo(() => {
    const map = (arr: { outstanding: number; accounts: number; npl_ratio_pct: number }[], key: string) =>
      arr.map((x) => ({ label: String((x as Record<string, unknown>)[key]), outstanding: x.outstanding, accounts: x.accounts, npl_ratio_pct: x.npl_ratio_pct }));
    switch (dim) {
      case 'Classification': return map(data.by_class, 'classification');
      case 'Region':         return map(data.by_region, 'region');
      case 'Branch':         return map(data.by_branch, 'branch');
      case 'RM':             return map(data.by_rm, 'rm');
      default:               return [];
    }
  }, [dim, data]);

  const sorted = useMemo(() => rows.slice().sort((a, b) => b.outstanding - a.outstanding), [rows]);
  const total = useMemo(() => sorted.reduce((s, r) => s + r.outstanding, 0), [sorted]);
  const isDonut = dim === 'Classification';
  const donutData = sorted.slice(0, 8).map((r) => ({ name: r.label, value: r.outstanding }));
  const barData = sorted.slice(0, 12).map((r) => ({ label: r.label, value: r.outstanding }));

  return (
    <>
      <div className="flex items-center justify-between mt-8 mb-3 flex-wrap gap-3">
        <h2 className="text-xs font-semibold uppercase tracking-wider text-gray-500">Slice loan book by</h2>
        <div className="inline-flex rounded-lg border border-gray-200 overflow-hidden">
          {DIMENSIONS.map((d) => (
            <button key={d} onClick={() => setDim(d)}
              className={`px-3 py-1.5 text-sm transition-colors ${dim === d ? 'bg-brand-primary text-white' : 'bg-white text-gray-600 hover:bg-gray-50'}`}>
              {d}
            </button>
          ))}
        </div>
      </div>
      <Card><Card.Body>
        {sorted.length === 0 ? (
          <p className="text-sm text-gray-500">No data for this dimension yet.</p>
        ) : (
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            <div>
              {isDonut ? (
                <DonutChart data={donutData} height={300} centerLabel="Outstanding" centerValue={abbrev(total)} />
              ) : (
                <CategoryBarChart
                  data={barData as unknown as Array<Record<string, unknown>>}
                  xKey="label" series={[{ key: 'value', label: 'Outstanding' }]}
                  height={Math.max(220, barData.length * 26)} />
              )}
            </div>
            <div className="overflow-auto max-h-96">
              <table className="w-full text-sm">
                <thead><tr className="text-left text-gray-500 border-b">
                  <th className="py-1 pr-3" />
                  <th className="py-1 pr-3 text-right">Outstanding</th>
                  <th className="py-1 pr-3 text-right">Accounts</th>
                  <th className="py-1 text-right">NPL</th>
                </tr></thead>
                <tbody>
                  {sorted.map((r) => (
                    <tr key={r.label} className="border-b last:border-0">
                      <td className="py-1 pr-3">{r.label}</td>
                      <td className="py-1 pr-3 text-right tabular-nums">{kes(r.outstanding)}</td>
                      <td className="py-1 pr-3 text-right tabular-nums">{r.accounts}</td>
                      <td className="py-1 text-right">
                        <Badge tone={nplTone(r.npl_ratio_pct)}>{r.npl_ratio_pct}%</Badge>
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

// ── drill: Region -> Branch -> RM -> individual accounts ──────────────────
function CreditDrill({ regions, kes }: { regions: CreditRegionBreakdown[]; kes: (n: number) => string }) {
  const navigate = useNavigate();
  const [region, setRegion] = useState<string | null>(null);
  const [branch, setBranch] = useState<string | null>(null);
  const [rm, setRm] = useState<string | null>(null);
  const [data, setData] = useState<CreditDrillResponse | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!region) { setData(null); return; }
    let live = true;
    setLoading(true);
    fetchCreditDrill(region, branch ?? undefined, rm ?? undefined)
      .then((d) => { if (live) setData(d); })
      .catch(() => { if (live) setData(null); })
      .finally(() => { if (live) setLoading(false); });
    return () => { live = false; };
  }, [region, branch, rm]);

  const crumb = 'text-brand-primary hover:underline';
  const here = 'font-semibold text-gray-900';

  return (
    <>
      <h2 className="text-xs font-semibold uppercase tracking-wider text-gray-500 mt-8 mb-3">
        Drill down · region → branch → RM → accounts
      </h2>
      <Card><Card.Body>
        <div className="flex items-center gap-2 text-sm mb-4 flex-wrap">
          <button onClick={() => { setRegion(null); setBranch(null); setRm(null); }} className={region ? crumb : here}>All regions</button>
          {region && <><span className="text-gray-400">›</span>
            <button onClick={() => { setBranch(null); setRm(null); }} className={branch ? crumb : here}>{region}</button></>}
          {branch && <><span className="text-gray-400">›</span>
            <button onClick={() => setRm(null)} className={rm ? crumb : here}>{branch}</button></>}
          {rm && <><span className="text-gray-400">›</span><span className={here}>{rm}</span></>}
        </div>

        {!region && (
          regions.length === 0
            ? <p className="text-sm text-gray-500">No region data yet.</p>
            : <DrillTable head={['Region', 'Outstanding', 'NPL']}
                rows={regions.slice().sort((a, b) => b.outstanding - a.outstanding).map((r) => ({
                  key: r.region, label: r.region, outstanding: kes(r.outstanding), npl: r.npl_ratio_pct,
                  onClick: () => setRegion(r.region),
                }))} />
        )}

        {region && !branch && (
          loading ? <Skeleton />
            : <DrillTable head={['Branch', 'Outstanding', 'NPL']}
                rows={(data?.by_branch ?? []).map((b) => ({
                  key: b.branch, label: b.branch, outstanding: kes(b.outstanding), npl: b.npl_ratio_pct,
                  onClick: () => setBranch(b.branch),
                }))} />
        )}

        {region && branch && !rm && (
          loading ? <Skeleton />
            : <DrillTable head={['Relationship Manager', 'Outstanding', 'NPL']}
                rows={(data?.by_rm ?? []).map((m) => ({
                  key: m.rm, label: m.rm, outstanding: kes(m.outstanding), npl: m.npl_ratio_pct,
                  onClick: () => setRm(m.rm),
                }))} />
        )}

        {region && branch && rm && (
          loading ? <Skeleton />
            : (data?.accounts.length ?? 0) === 0
              ? <p className="text-sm text-gray-500">No accounts for this RM.</p>
              : <div className="overflow-auto max-h-96">
                  <table className="w-full text-sm">
                    <thead><tr className="text-left text-gray-500 border-b">
                      <th className="py-1 pr-3">Account</th>
                      <th className="py-1 pr-3">Class</th>
                      <th className="py-1 pr-3 text-right">Outstanding</th>
                      <th className="py-1 pr-3 text-right">DPD</th>
                      <th className="py-1">Collateral</th>
                    </tr></thead>
                    <tbody>
                      {(data?.accounts ?? []).map((a) => {
                        const canDrill = Boolean(a.cif);
                        return (
                        <tr key={a.account_number}
                            onClick={canDrill ? () => navigate(`/cbs/${encodeURIComponent(a.cif)}`) : undefined}
                            className={`border-b last:border-0 ${canDrill ? 'cursor-pointer hover:bg-gray-50' : ''}`}>
                          <td className={`py-1 pr-3 tabular-nums ${canDrill ? 'text-brand-primary font-medium' : ''}`}>{a.account_number}</td>
                          <td className="py-1 pr-3">{a.classification}</td>
                          <td className="py-1 pr-3 text-right tabular-nums">{kes(a.outstanding)}</td>
                          <td className="py-1 pr-3 text-right tabular-nums">{a.npl_days}</td>
                          <td className="py-1">{a.collateral_type}</td>
                        </tr>
                        );
                      })}
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
  rows: { key: string; label: string; outstanding: string; npl: number; onClick: () => void }[];
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
            <tr key={r.key} onClick={r.onClick}
                className="border-b last:border-0 cursor-pointer hover:bg-gray-50">
              <td className="py-1.5 pr-3 text-brand-primary font-medium">{r.label}</td>
              <td className="py-1.5 pr-3 text-right tabular-nums">{r.outstanding}</td>
              <td className="py-1.5 text-right">
                <Badge tone={nplTone(r.npl)}>{r.npl}%</Badge>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
