import { useCallback, useEffect, useState } from 'react';
import { PageHeader } from '@/components/PageHeader';
import { Card } from '@/components/Card';
import {
  fetchMyPortfolio, fetchCbsCustomer, fetchCbsCustomerAccounts,
  type PortfolioResponse,
} from '@/lib/api';
import type { CbsCustomer, CbsAccount } from '@/types/cbs';

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
  const [staff, setStaff] = useState('');
  const [c360, setC360] = useState<{ cif: string; customer: CbsCustomer | null; accounts: CbsAccount[] } | null>(null);
  const [c360Loading, setC360Loading] = useState(false);

  const load = useCallback(async (sc: string) => {
    setLoading(true); setErr('');
    try { setData(await fetchMyPortfolio(sc)); }
    catch (e) { setErr(e instanceof Error ? e.message : 'Failed to load portfolio'); }
    finally { setLoading(false); }
  }, []);

  useEffect(() => { void load(staff); }, [staff, load]);

  async function openCustomer360(cif: string) {
    if (!cif) return;
    setC360({ cif, customer: null, accounts: [] });
    setC360Loading(true);
    try {
      const [cust, accs] = await Promise.all([fetchCbsCustomer(cif), fetchCbsCustomerAccounts(cif)]);
      setC360({ cif, customer: cust.customer, accounts: accs.accounts });
    } catch {
      setC360({ cif, customer: null, accounts: [] });
    } finally { setC360Loading(false); }
  }

  const s = data?.summary;
  const mv = s?.deposit_movement;

  return (
    <>
      <PageHeader ribbon title="Portfolio" subtitle="Accounts tagged to you in CBS, with analytics." />

      {data?.is_manager && (
        <Card><Card.Body>
          <label className="flex items-center gap-2 text-sm">
            <span className="text-gray-600">Viewing:</span>
            <select className="rounded border px-2 py-1.5 text-sm" value={staff} onChange={(e) => setStaff(e.target.value)}>
              <option value="">All — consolidated ({data.team.length} staff)</option>
              {data.team.map((m) => <option key={m.staff_code} value={m.staff_code}>{m.name}</option>)}
            </select>
            {data.view === 'consolidated' && <span className="text-xs text-gray-400">Whole team / branch book</span>}
          </label>
        </Card.Body></Card>
      )}

      {loading ? (
        <Card><Card.Body><p className="text-sm text-gray-400">Loading portfolio…</p></Card.Body></Card>
      ) : err ? (
        <Card><Card.Body><p className="text-sm text-red-600">{err}</p></Card.Body></Card>
      ) : !s || s.accounts === 0 ? (
        <Card><Card.Body><p className="text-sm text-gray-400">No CBS accounts are currently tagged here.</p></Card.Body></Card>
      ) : (
        <div className="mt-4 space-y-4">
          <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
            <Stat label="Deposits (KES)" value={kes(s.deposits)} />
            <Stat label="Loans (KES)" value={kes(s.loans)} />
            <Stat label="Customers" value={String(s.customers)} />
            <Stat label="Accounts" value={String(s.accounts)} />
            <Stat label="Dormant accounts" value={`${s.dormant_accounts} (${s.dormant_pct}%)`} tone={s.dormant_pct > 20 ? 'warn' : undefined} />
            <Stat label="NPL accounts" value={String(s.npl_accounts)} tone={s.npl_accounts > 0 ? 'warn' : undefined} />
            <Stat label="Total book (KES)" value={kes(s.total_balance)} />
            <Stat label="Deposit movement" value={mv ? `${mv.delta >= 0 ? '+' : ''}${kes(mv.delta)}` : 'baseline pending'} tone={mv ? (mv.delta >= 0 ? 'good' : 'warn') : undefined} />
          </div>

          {mv && (
            <Card><Card.Body>
              <div className="mb-1 text-sm font-semibold text-gray-900">Deposit movement vs {s.baseline_date ?? 'baseline'}</div>
              <p className="text-sm text-gray-600">Baseline {kes(mv.baseline)} → current {kes(mv.current)} ({mv.pct != null ? `${mv.pct}%` : '—'})</p>
            </Card.Body></Card>
          )}

          <Card>
            <Card.Header><h2 className="text-base font-semibold text-gray-900">Book by account type</h2></Card.Header>
            <Card.Body>
              <table className="w-full text-sm">
                <thead><tr className="text-left text-xs text-gray-400"><th className="py-1">Type</th><th className="text-right">Accounts</th><th className="text-right">Balance (KES)</th></tr></thead>
                <tbody>{s.by_type.map((t) => (
                  <tr key={t.type} className="border-t border-gray-100">
                    <td className="py-1.5 text-gray-800">{t.type}</td>
                    <td className="text-right tabular-nums">{t.count}</td>
                    <td className="text-right tabular-nums">{kes(t.balance)}</td>
                  </tr>))}</tbody>
              </table>
            </Card.Body>
          </Card>

          <Card>
            <Card.Header><h2 className="text-base font-semibold text-gray-900">Accounts ({s.accounts}) — click a row for the customer 360</h2></Card.Header>
            <Card.Body>
              <div className="overflow-auto">
                <table className="w-full text-sm">
                  <thead><tr className="text-left text-xs text-gray-400"><th className="py-1">Account</th><th>CIF</th><th>Type</th><th className="text-right">Balance</th><th>Status</th><th>Dormancy</th></tr></thead>
                  <tbody>{data!.accounts.slice(0, 300).map((a) => (
                    <tr key={a.account_number} className="cursor-pointer border-t border-gray-100 hover:bg-gray-50" onClick={() => void openCustomer360(a.cif)}>
                      <td className="py-1.5 tabular-nums">{a.account_number}</td>
                      <td className="text-gray-500">{a.cif}</td>
                      <td className="text-gray-700">{a.account_type_name}</td>
                      <td className="text-right tabular-nums">{kes(a.current_balance)}</td>
                      <td className="text-gray-600">{a.account_status}</td>
                      <td className={/active|regular/i.test(a.dormancy_status) ? 'text-gray-500' : 'text-amber-600'}>{a.dormancy_status || '—'}</td>
                    </tr>))}</tbody>
                </table>
              </div>
            </Card.Body>
          </Card>
        </div>
      )}

      {c360 && (
        <div className="fixed inset-0 z-50 flex items-start justify-center overflow-auto bg-black/30 p-4" onClick={() => setC360(null)}>
          <div className="mt-10 w-full max-w-2xl rounded-lg bg-white p-5 shadow-xl" onClick={(e) => e.stopPropagation()}>
            <div className="mb-3 flex items-center justify-between">
              <h3 className="text-lg font-semibold text-gray-900">Customer 360 — {c360.customer?.full_name ?? c360.cif}</h3>
              <button className="text-gray-400 hover:text-gray-700" onClick={() => setC360(null)}>✕</button>
            </div>
            {c360Loading ? <p className="text-sm text-gray-400">Loading…</p> : (
              <>
                <div className="mb-4 grid grid-cols-2 gap-2 text-sm">
                  <div><span className="text-gray-400">CIF: </span>{c360.cif}</div>
                  <div><span className="text-gray-400">Segment: </span>{c360.customer?.segment ?? '—'}</div>
                  <div><span className="text-gray-400">Risk: </span>{c360.customer?.risk_rating ?? '—'}</div>
                  <div><span className="text-gray-400">KYC: </span>{c360.customer?.kyc_status ?? '—'}</div>
                </div>
                <div className="text-sm font-semibold text-gray-800">Accounts ({c360.accounts.length})</div>
                <table className="mt-1 w-full text-sm">
                  <thead><tr className="text-left text-xs text-gray-400"><th className="py-1">Account</th><th>Type</th><th className="text-right">Balance</th><th>Status</th></tr></thead>
                  <tbody>{c360.accounts.map((a) => (
                    <tr key={a.account_number} className="border-t border-gray-100">
                      <td className="py-1.5 tabular-nums">{a.account_number}</td>
                      <td className="text-gray-700">{a.account_type_name}</td>
                      <td className="text-right tabular-nums">{kes(a.current_balance)}</td>
                      <td className="text-gray-600">{a.account_status}</td>
                    </tr>))}</tbody>
                </table>
              </>
            )}
          </div>
        </div>
      )}
    </>
  );
}
