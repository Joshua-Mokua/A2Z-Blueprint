import { useEffect, useState } from 'react';
import { PageHeader } from '@/components/PageHeader';
import { Card } from '@/components/Card';
import { fetchMyPortfolio, type PortfolioResponse } from '@/lib/api';

const kes = (n: number) => new Intl.NumberFormat('en-KE', { maximumFractionDigits: 0 }).format(n || 0);

function Stat({ label, value, tone }: { label: string; value: string; tone?: 'good' | 'warn' }) {
  return (
    <Card><Card.Body>
      <div className="text-xs text-gray-400">{label}</div>
      <div className={'mt-1 text-lg font-semibold ' + (tone === 'good' ? 'text-emerald-600' : tone === 'warn' ? 'text-amber-600' : 'text-gray-900')}>{value}</div>
    </Card.Body></Card>
  );
}

export default function Portfolio() {
  const [data, setData] = useState<PortfolioResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState('');

  useEffect(() => {
    (async () => {
      try { setData(await fetchMyPortfolio()); }
      catch (e) { setErr(e instanceof Error ? e.message : 'Failed to load portfolio'); }
      finally { setLoading(false); }
    })();
  }, []);

  const s = data?.summary;
  const mv = s?.deposit_movement;

  return (
    <>
      <PageHeader ribbon title="Portfolio" subtitle="Accounts tagged to you in CBS, with analytics." />
      {loading ? (
        <Card><Card.Body><p className="text-sm text-gray-400">Loading your portfolio…</p></Card.Body></Card>
      ) : err ? (
        <Card><Card.Body><p className="text-sm text-red-600">{err}</p></Card.Body></Card>
      ) : !s || s.accounts === 0 ? (
        <Card><Card.Body><p className="text-sm text-gray-400">No CBS accounts are currently tagged to you.</p></Card.Body></Card>
      ) : (
        <div className="space-y-4">
          <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
            <Stat label="Deposits (KES)" value={kes(s.deposits)} />
            <Stat label="Loans (KES)" value={kes(s.loans)} />
            <Stat label="Customers" value={String(s.customers)} />
            <Stat label="Accounts" value={String(s.accounts)} />
            <Stat label="Dormant accounts" value={`${s.dormant_accounts} (${s.dormant_pct}%)`} tone={s.dormant_pct > 20 ? 'warn' : undefined} />
            <Stat label="NPL accounts" value={String(s.npl_accounts)} tone={s.npl_accounts > 0 ? 'warn' : undefined} />
            <Stat label="Total book (KES)" value={kes(s.total_balance)} />
            <Stat
              label="Deposit movement"
              value={mv ? `${mv.delta >= 0 ? '+' : ''}${kes(mv.delta)}` : 'baseline pending'}
              tone={mv ? (mv.delta >= 0 ? 'good' : 'warn') : undefined}
            />
          </div>

          {mv && (
            <Card><Card.Body>
              <div className="mb-1 text-sm font-semibold text-gray-900">Deposit movement vs {s.baseline_date ?? 'baseline'}</div>
              <p className="text-sm text-gray-600">
                Baseline {kes(mv.baseline)} → current {kes(mv.current)} ({mv.pct != null ? `${mv.pct}%` : '—'})
              </p>
            </Card.Body></Card>
          )}

          <Card>
            <Card.Header><h2 className="text-base font-semibold text-gray-900">Book by account type</h2></Card.Header>
            <Card.Body>
              <table className="w-full text-sm">
                <thead><tr className="text-left text-xs text-gray-400">
                  <th className="py-1">Type</th><th className="text-right">Accounts</th><th className="text-right">Balance (KES)</th>
                </tr></thead>
                <tbody>
                  {s.by_type.map((t) => (
                    <tr key={t.type} className="border-t border-gray-100">
                      <td className="py-1.5 text-gray-800">{t.type}</td>
                      <td className="text-right tabular-nums">{t.count}</td>
                      <td className="text-right tabular-nums">{kes(t.balance)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </Card.Body>
          </Card>

          <Card>
            <Card.Header><h2 className="text-base font-semibold text-gray-900">Accounts ({s.accounts})</h2></Card.Header>
            <Card.Body>
              <div className="overflow-auto">
                <table className="w-full text-sm">
                  <thead><tr className="text-left text-xs text-gray-400">
                    <th className="py-1">Account</th><th>CIF</th><th>Type</th><th className="text-right">Balance</th><th>Status</th><th>Dormancy</th>
                  </tr></thead>
                  <tbody>
                    {data!.accounts.slice(0, 200).map((a) => (
                      <tr key={a.account_number} className="border-t border-gray-100">
                        <td className="py-1.5 tabular-nums">{a.account_number}</td>
                        <td className="text-gray-500">{a.cif}</td>
                        <td className="text-gray-700">{a.account_type_name}</td>
                        <td className="text-right tabular-nums">{kes(a.current_balance)}</td>
                        <td className="text-gray-600">{a.account_status}</td>
                        <td className={/active|regular/i.test(a.dormancy_status) ? 'text-gray-500' : 'text-amber-600'}>{a.dormancy_status || '—'}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </Card.Body>
          </Card>
        </div>
      )}
    </>
  );
}
