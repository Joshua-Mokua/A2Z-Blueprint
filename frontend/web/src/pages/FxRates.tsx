// P4-1c — FX rates admin page.
//
// Lists the operational FX rate table and (for admins) lets them add/update a
// rate. KES is base and shown read-only at 1.0. Non-admins see the table but
// the editor is hidden (server also enforces admin-only on POST /api/fx/rates).
//
// Pattern mirrors CreditAdmin.tsx (β6): useState list hook + Card/Badge/Button.

import { useState, useMemo } from 'react';
import { useRole } from '@/hooks/useRole';
import { useFxRates } from '@/hooks/useFxRates';
import { useFxMutations } from '@/hooks/useFxMutations';
import { useToast } from '@/components/Toast';
import { Card } from '@/components/Card';
import { Badge } from '@/components/Badge';
import { Button } from '@/components/Button';
import { Input } from '@/components/Input';
import { Skeleton } from '@/components/Skeleton';
import type { FxRate, FxRateType } from '@/types/fx';

const RATE_TYPES: FxRateType[] = ['mid', 'buy', 'sell'];

function todayIso(): string {
  return new Date().toISOString().slice(0, 10);
}

export function FxRates() {
  const { isAdmin } = useRole();
  const { rates, baseCurrency, loading, error, refetch } = useFxRates(false);
  const { upsertRate, loading: saving } = useFxMutations();
  const { toast } = useToast();

  const [currency, setCurrency]   = useState('USD');
  const [rateType, setRateType]   = useState<FxRateType>('mid');
  const [rateToKes, setRateToKes] = useState('');
  const [effDate, setEffDate]     = useState(todayIso());

  // Group rows by currency for a tidy table.
  const grouped = useMemo(() => {
    const m = new Map<string, FxRate[]>();
    for (const r of rates) {
      const k = (r.currency || '').toUpperCase();
      if (!m.has(k)) m.set(k, []);
      m.get(k)!.push(r);
    }
    for (const list of m.values()) {
      list.sort((a, b) => (b.effective_date || '').localeCompare(a.effective_date || ''));
    }
    return Array.from(m.entries()).sort((a, b) => a[0].localeCompare(b[0]));
  }, [rates]);

  async function handleSave() {
    const cur = currency.trim().toUpperCase();
    const rate = Number(rateToKes);
    if (!cur) { toast({ tone: 'warning', message: 'Currency is required.' }); return; }
    if (cur === baseCurrency.toUpperCase()) {
      toast({ tone: 'warning', message: `${baseCurrency} is the base currency (rate is always 1).` });
      return;
    }
    if (!Number.isFinite(rate) || rate <= 0) {
      toast({ tone: 'warning', message: 'Rate to KES must be a positive number.' });
      return;
    }
    const res = await upsertRate({
      currency: cur, rate_to_kes: rate, effective_date: effDate, rate_type: rateType,
    });
    if (res.ok) {
      toast({ tone: 'success', message: `Saved ${cur} ${rateType} = ${rate} (from ${effDate}).` });
      setRateToKes('');
      await refetch();
    } else {
      toast({ tone: 'danger', message: res.error });
    }
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold" style={{ color: 'var(--brand-secondary)' }}>
          FX Rates
        </h1>
        <p className="text-sm text-gray-500 mt-1">
          Operational rates for currency conversion. {baseCurrency} is the base currency
          (rate = 1). Loans, deposits, and reporting normalize to {baseCurrency} using the
          latest active rate on or before the booking date.
        </p>
      </div>

      {isAdmin && (
        <Card stripe>
          <h2 className="text-lg font-medium mb-3">Add / update a rate</h2>
          <div className="grid grid-cols-1 md:grid-cols-5 gap-3 items-end">
            <label className="text-sm">
              <span className="block mb-1 text-gray-600">Currency</span>
              <Input value={currency} onChange={(e) => setCurrency(e.target.value.toUpperCase())}
                     placeholder="USD" maxLength={3} />
            </label>
            <label className="text-sm">
              <span className="block mb-1 text-gray-600">Rate type</span>
              <select className="w-full border rounded px-2 py-2 text-sm"
                      value={rateType} onChange={(e) => setRateType(e.target.value as FxRateType)}>
                {RATE_TYPES.map((t) => <option key={t} value={t}>{t}</option>)}
              </select>
            </label>
            <label className="text-sm">
              <span className="block mb-1 text-gray-600">Rate to {baseCurrency}</span>
              <Input value={rateToKes} onChange={(e) => setRateToKes(e.target.value)}
                     placeholder="129.50" inputMode="decimal" />
            </label>
            <label className="text-sm">
              <span className="block mb-1 text-gray-600">Effective date</span>
              <Input type="date" value={effDate} onChange={(e) => setEffDate(e.target.value)} />
            </label>
            <Button onClick={handleSave} disabled={saving}>
              {saving ? 'Saving…' : 'Save rate'}
            </Button>
          </div>
          <p className="text-xs text-gray-400 mt-2">
            History is preserved — a new effective date adds a row; the resolver always
            picks the latest rate on or before the booking date.
          </p>
        </Card>
      )}

      <Card>
        {loading ? (
          <div className="space-y-2">
            <Skeleton shape="line" className="w-1/3" />
            <Skeleton shape="line" className="w-2/3" />
            <Skeleton shape="line" className="w-1/2" />
          </div>
        ) : error ? (
          <div className="text-sm text-red-600">{error}</div>
        ) : grouped.length === 0 ? (
          <div className="text-sm text-gray-500">No FX rates configured yet.</div>
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-gray-500 border-b">
                <th className="py-2 pr-4">Currency</th>
                <th className="py-2 pr-4">Book</th>
                <th className="py-2 pr-4">Type</th>
                <th className="py-2 pr-4">Rate → {baseCurrency}</th>
                <th className="py-2 pr-4">Effective</th>
                <th className="py-2 pr-4">Source</th>
                <th className="py-2 pr-4">Active</th>
              </tr>
            </thead>
            <tbody>
              {grouped.map(([cur, list]) =>
                list.map((r, i) => {
                  const isBase = cur === baseCurrency.toUpperCase();
                  return (
                    <tr key={`${cur}-${r.rate_type}-${r.effective_date}-${i}`} className="border-b last:border-0">
                      <td className="py-2 pr-4 font-medium">{i === 0 ? cur : ''}</td>
                      <td className="py-2 pr-4">
                        {i === 0 && (
                          <Badge tone={isBase ? 'info' : 'brand'}>{isBase ? 'LCY' : 'FCY'}</Badge>
                        )}
                      </td>
                      <td className="py-2 pr-4">{r.rate_type}</td>
                      <td className="py-2 pr-4 tabular-nums">{Number(r.rate_to_kes).toLocaleString()}</td>
                      <td className="py-2 pr-4">{r.effective_date}</td>
                      <td className="py-2 pr-4 text-gray-500">{r.source || '—'}</td>
                      <td className="py-2 pr-4">
                        <Badge tone={r.active === false ? 'neutral' : 'success'}>
                          {r.active === false ? 'inactive' : 'active'}
                        </Badge>
                      </td>
                    </tr>
                  );
                }),
              )}
            </tbody>
          </table>
        )}
      </Card>
    </div>
  );
}
