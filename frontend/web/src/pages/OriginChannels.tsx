// Origin Channels — one page for every channel the bank invests in.
//
// Events, Partnerships and Lead Generators ask the same question: what did we
// spend, what did it produce, was it worth it. Three sidebar entries would be
// three doors into one question, so they share a page and a switcher.
//
// CREATE IS A BUTTON, NOT A TAB. Four tabs across three channels would be
// twelve views, and "create" is not a view you return to — it is an action.
//
// The warehouse is deliberately NOT here: it is a shared shelf with claim
// mechanics and no budget, so putting it beside these would imply a return
// question it cannot answer.

import { useCallback, useEffect, useMemo, useState } from 'react';
import { Button } from '@/components/Button';
import { Card } from '@/components/Card';
import { PageHeader } from '@/components/PageHeader';
import { useToast } from '@/components/Toast';
import {
  fetchChannels, fetchChannelRecords, createChannelRecord,
  type OriginChannel, type ChannelRecord,
} from '@/lib/api';

function kes(n: number | null | undefined): string {
  const v = Number(n ?? 0);
  if (!v) return '—';
  return Math.round(v).toLocaleString();
}

function pct(a: number, b: number | null | undefined): string {
  const t = Number(b ?? 0);
  return t > 0 ? `${Math.round((a / t) * 100)}%` : '';
}

export default function OriginChannels() {
  const { toast } = useToast();
  const [channels, setChannels] = useState<OriginChannel[]>([]);
  const [key, setKey] = useState('events');
  const [rows, setRows] = useState<ChannelRecord[]>([]);
  const [tagged, setTagged] = useState(0);
  const [loading, setLoading] = useState(false);
  const [mine, setMine] = useState(false);
  const [activeOnly, setActiveOnly] = useState(false);
  const [creating, setCreating] = useState(false);
  const [busy, setBusy] = useState(false);

  const [form, setForm] = useState({
    name: '', owner_type: 'unit', owner: '', party: '', category: '',
    start_date: '', end_date: '', budget_kes: '', target_leads: '',
    target_accounts: '', target_value_kes: '',
  });

  useEffect(() => {
    void (async () => {
      try {
        const r = await fetchChannels();
        setChannels(r.channels ?? []);
      } catch {
        setChannels([]);
      }
    })();
  }, []);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const r = await fetchChannelRecords(key, activeOnly, mine);
      setRows(r.records ?? []);
      setTagged(r.tagged_deals ?? 0);
    } catch (e) {
      toast({ tone: 'danger', message: e instanceof Error ? e.message : 'Could not load.' });
      setRows([]);
    } finally {
      setLoading(false);
    }
  }, [key, activeOnly, mine, toast]);

  useEffect(() => { void load(); }, [load]);

  const current = useMemo(
    () => channels.find((c) => c.key === key), [channels, key]);

  async function submit() {
    if (!form.name.trim() || !form.owner.trim()) {
      toast({ tone: 'danger', message: 'A name and an owner are required.' });
      return;
    }
    setBusy(true);
    try {
      await createChannelRecord(key, {
        ...form,
        budget_kes: Number(form.budget_kes) || 0,
        target_leads: Number(form.target_leads) || 0,
        target_accounts: Number(form.target_accounts) || 0,
        target_value_kes: Number(form.target_value_kes) || 0,
      });
      toast({ tone: 'success', message: `${form.name} created.` });
      setCreating(false);
      setForm({ ...form, name: '', party: '', budget_kes: '' });
      await load();
    } catch (e) {
      toast({ tone: 'danger', message: e instanceof Error ? e.message : 'Could not create.' });
    } finally {
      setBusy(false);
    }
  }

  const th = 'whitespace-nowrap px-3 py-2 text-left text-[11px] font-semibold uppercase tracking-wide';
  const td = 'whitespace-nowrap px-3 py-2 text-sm';
  const inp = 'mt-1 w-full h-9 px-2 rounded border border-gray-300 text-sm';

  return (
    <>
      <PageHeader
        ribbon
        breadcrumbs={[{ label: 'Pipeline Intelligence (PIS)' }, { label: 'Origin Channels' }]}
        title="Origin Channels"
      />
      <div className="mx-auto max-w-7xl p-6">
        <div className="mb-4 flex flex-wrap items-center gap-2">
          {channels.map((c) => (
            <button
              key={c.key}
              type="button"
              onClick={() => setKey(c.key)}
              className={'rounded-full px-3 py-1.5 text-xs font-medium ' + (
                c.key === key
                  ? 'bg-[#0082BB] text-white'
                  : 'bg-gray-100 text-gray-600 hover:bg-gray-200')}
            >
              {c.label}
            </button>
          ))}
        </div>

        {current?.note && (
          <p className="mb-3 text-xs text-gray-500">{current.note}</p>
        )}

        <Card>
          <Card.Header>
            <div className="flex flex-wrap items-center justify-between gap-3">
              <h2 className="text-base font-semibold text-gray-900">
                {current?.label ?? 'Channels'}
              </h2>
              <div className="flex flex-wrap items-center gap-3 text-xs">
                <label className="flex items-center gap-1.5 text-gray-600">
                  <input type="checkbox" checked={mine}
                         onChange={(e) => setMine(e.target.checked)} />
                  Mine
                </label>
                <label className="flex items-center gap-1.5 text-gray-600">
                  <input type="checkbox" checked={activeOnly}
                         onChange={(e) => setActiveOnly(e.target.checked)} />
                  Active only
                </label>
                <span className="rounded-full bg-[#E6F1FB] px-2.5 py-1 text-[#0C447C]">
                  {tagged} deal{tagged === 1 ? '' : 's'} tagged
                </span>
                <Button size="sm" onClick={() => setCreating((v) => !v)}>
                  {creating ? 'Cancel' : 'Create'}
                </Button>
              </div>
            </div>
          </Card.Header>

          <Card.Body>
            {creating && (
              <div className="mb-4 rounded-lg border border-gray-200 bg-gray-50/60 p-3">
                <div className="grid gap-3 sm:grid-cols-3">
                  <label className="text-xs text-gray-600">
                    Name
                    <input className={inp} value={form.name}
                           onChange={(e) => setForm({ ...form, name: e.target.value })} />
                  </label>
                  <label className="text-xs text-gray-600">
                    Belongs to
                    <select className={inp} value={form.owner_type}
                            onChange={(e) => setForm({ ...form, owner_type: e.target.value })}>
                      <option value="unit">A unit</option>
                      <option value="branch">A branch</option>
                    </select>
                  </label>
                  <label className="text-xs text-gray-600">
                    {form.owner_type === 'unit' ? 'Which unit' : 'Which branch'}
                    <input className={inp} value={form.owner}
                           onChange={(e) => setForm({ ...form, owner: e.target.value })} />
                  </label>
                  <label className="text-xs text-gray-600">
                    {current?.party_label || 'Partner'}
                    <input className={inp} value={form.party}
                           onChange={(e) => setForm({ ...form, party: e.target.value })} />
                  </label>
                  <label className="text-xs text-gray-600">
                    Starts
                    <input type="date" className={inp} value={form.start_date}
                           onChange={(e) => setForm({ ...form, start_date: e.target.value })} />
                  </label>
                  <label className="text-xs text-gray-600">
                    Ends
                    <input type="date" className={inp} value={form.end_date}
                           onChange={(e) => setForm({ ...form, end_date: e.target.value })} />
                  </label>
                  {current?.supports_roi && (
                    <label className="text-xs text-gray-600">
                      Budget (KES)
                      <input className={inp} value={form.budget_kes}
                             onChange={(e) => setForm({ ...form, budget_kes: e.target.value })} />
                    </label>
                  )}
                  <label className="text-xs text-gray-600">
                    Target leads
                    <input className={inp} value={form.target_leads}
                           onChange={(e) => setForm({ ...form, target_leads: e.target.value })} />
                  </label>
                  <label className="text-xs text-gray-600">
                    Target accounts
                    <input className={inp} value={form.target_accounts}
                           onChange={(e) => setForm({ ...form, target_accounts: e.target.value })} />
                  </label>
                </div>
                <div className="mt-3 flex justify-end">
                  <Button size="sm" disabled={busy} onClick={() => void submit()}>
                    {busy ? 'Creating…' : `Create ${current?.label?.replace(/s$/, '') ?? ''}`}
                  </Button>
                </div>
              </div>
            )}

            {loading && <p className="py-8 text-center text-sm text-gray-400">Loading…</p>}

            {!loading && rows.length === 0 && (
              <p className="py-8 text-center text-sm text-gray-400">
                {mine ? 'Nothing owned by you.' : 'Nothing here yet.'}
              </p>
            )}

            {!loading && rows.length > 0 && tagged === 0 && (
              <p className="mb-3 rounded-lg border border-[#FAEEDA] bg-[#FEFAF3] px-3 py-2 text-xs text-[#854F0B]">
                No deals are tagged to any of these yet, so leads and accounts
                below are zero. That is not a verdict on the channel — pick it
                on the deal capture form to start attributing.
              </p>
            )}

            {!loading && rows.length > 0 && (
              <div className="overflow-auto rounded-lg border border-gray-200">
                <table className="w-full border-separate" style={{ borderSpacing: 0 }}>
                  <thead>
                    <tr>
                      <th className={`${th} bg-gray-100 text-gray-600`}>Name</th>
                      <th className={`${th} bg-gray-100 text-gray-600`}>Owner</th>
                      <th className={`${th} bg-gray-100 text-gray-600`}>When</th>
                      {current?.supports_roi && (
                        <th className={`${th} bg-gray-100 text-right text-gray-600`}>Spent</th>
                      )}
                      <th className={`${th} bg-[#0082BB] text-right text-white`}>Leads</th>
                      <th className={`${th} bg-[#0082BB] text-right text-white`}>Accounts</th>
                      <th className={`${th} bg-gray-100 text-right text-gray-600`}>Won value</th>
                      <th className={`${th} bg-gray-100 text-right text-gray-600`}>
                        {current?.supports_roi ? 'Return' : 'Expected'}
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    {rows.map((r, i) => {
                      const bg = i % 2 === 1 ? 'bg-gray-50/40' : 'bg-white';
                      return (
                        <tr key={r.id}>
                          <td className={`${td} ${bg} font-medium text-gray-900`}>
                            <div className="truncate" style={{ maxWidth: 260 }} title={r.name}>
                              {r.name}
                            </div>
                            {r.party && <div className="text-[10px] text-gray-400">{r.party}</div>}
                          </td>
                          <td className={`${td} ${bg} text-gray-600`}>
                            {r.owner || <span className="text-gray-300">unassigned</span>}
                            {r.owner_type && (
                              <div className="text-[10px] text-gray-400">{r.owner_type}</div>
                            )}
                          </td>
                          <td className={`${td} ${bg} text-gray-500`}>
                            {String(r.start_date ?? '').slice(0, 10)}
                            <div className="text-[10px] text-gray-400">{r.status}</div>
                          </td>
                          {current?.supports_roi && (
                            <td className={`${td} ${bg} text-right tabular-nums text-gray-700`}>
                              {kes(r.spent_kes ?? r.budget_kes)}
                            </td>
                          )}
                          <td className={`${td} ${bg} text-right tabular-nums`}>
                            <span className="font-semibold text-gray-900">{r.leads}</span>
                            {r.target_leads ? (
                              <span className="ml-1 text-[10px] text-gray-400">
                                / {r.target_leads} · {pct(r.leads, r.target_leads)}
                              </span>
                            ) : null}
                          </td>
                          <td className={`${td} ${bg} text-right tabular-nums`}>
                            <span className="font-semibold text-[#3B6D11]">{r.accounts}</span>
                            {r.target_accounts ? (
                              <span className="ml-1 text-[10px] text-gray-400">
                                / {r.target_accounts} · {pct(r.accounts, r.target_accounts)}
                              </span>
                            ) : null}
                          </td>
                          <td className={`${td} ${bg} text-right font-semibold tabular-nums text-[#003D57]`}>
                            {kes(r.won_value)}
                          </td>
                          <td className={`${td} ${bg} text-right tabular-nums`}>
                            {current?.supports_roi ? (
                              r.roi_pct === null || r.roi_pct === undefined ? (
                                <span className="text-gray-300">—</span>
                              ) : (
                                <span className={r.roi_pct >= 0 ? 'text-[#3B6D11]' : 'text-rose-600'}>
                                  {r.roi_pct}%
                                </span>
                              )
                            ) : (
                              <span className="text-gray-600">{kes(r.target_value_kes)}</span>
                            )}
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            )}
          </Card.Body>
        </Card>
      </div>
    </>
  );
}
