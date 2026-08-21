// Treasury Rate Desk — term deposit rate requests raised by branches.
//
// RULING (2026-08-19): "in treasury we can expose it to all treasury staff in a
// pool. Treasury approves or gives a counter rate."
//
// A POOL, NOT A QUEUE PER PERSON. Nothing is routed to an individual and there
// is no claiming: any dealer prices any request. A rate is one person's call
// and the customer is usually on the phone, so the shared list is what gets it
// answered rather than assigned.
//
// IT SHOWS THE ANSWERED ONES TOO. A desk that only sees what it has not done
// yet cannot tell whether its pricing is winning business - so the outcomes,
// won at the asked rate, won at the counter, lost at the counter, stay on the
// page underneath.

import { useCallback, useEffect, useState } from 'react';
import {
  fetchRatePool, approveRateRequest, counterRateRequest,
  type RatePoolResponse, type RatePoolRow,
} from '@/lib/api';
import { Card } from '@/components/Card';
import { Button } from '@/components/Button';
import { useToast } from '@/components/Toast';
import { PageHeader } from '@/components/PageHeader';
import { Skeleton } from '@/components/Skeleton';
import { Badge } from '@/components/Badge';

function money(n: number | undefined): string {
  const v = Number(n ?? 0);
  return `KES ${v.toLocaleString()}`;
}

function rate(n: number | null | undefined): string {
  return n === null || n === undefined ? '—' : `${Number(n).toFixed(2)}%`;
}

/** What happened, in words rather than a status key. */
function outcomeLabel(row: RatePoolRow): { text: string; tone: 'success' | 'danger' | 'warning' | 'neutral' } {
  switch (row.status) {
    case 'approved':
      return { text: `Won at ${rate(row.offered_rate)}`, tone: 'success' };
    case 'accepted_at_counter':
      return { text: `Won at the counter, ${rate(row.offered_rate)}`, tone: 'success' };
    case 'declined_at_counter':
      return { text: `Lost at ${rate(row.offered_rate)}`, tone: 'danger' };
    case 'countered':
      return { text: `Countered at ${rate(row.offered_rate)} — with the branch`, tone: 'warning' };
    default:
      return { text: row.status ?? '—', tone: 'neutral' };
  }
}

export default function TreasuryRateDesk() {
  const { toast } = useToast();
  const [data, setData] = useState<RatePoolResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [denied, setDenied] = useState(false);
  const [busy, setBusy] = useState<string | null>(null);
  const [counterFor, setCounterFor] = useState<string | null>(null);
  const [offer, setOffer] = useState('');
  const [note, setNote] = useState('');

  const load = useCallback(async () => {
    setLoading(true);
    try {
      setData(await fetchRatePool());
      setDenied(false);
    } catch (e) {
      const msg = e instanceof Error ? e.message : '';
      // A 403 here is not an error to apologise for - it means the person is
      // not on the treasury desk, which is a fact rather than a failure.
      if (msg.includes('403')) setDenied(true);
      else toast({ tone: 'danger', message: msg || 'Could not read the rate pool' });
    } finally { setLoading(false); }
  }, [toast]);

  useEffect(() => { void load(); }, [load]);

  const approve = async (row: RatePoolRow) => {
    setBusy(row.deal_id);
    try {
      await approveRateRequest(row.deal_id, {});
      toast({ tone: 'success',
        message: `Approved at ${rate(row.requested_rate)} — booked and closed at the branch.` });
      await load();
    } catch (e) {
      toast({ tone: 'danger', message: e instanceof Error ? e.message : 'Could not approve' });
    } finally { setBusy(null); }
  };

  const counter = async (row: RatePoolRow) => {
    const v = Number(offer);
    if (!Number.isFinite(v) || v <= 0) {
      toast({ tone: 'danger', message: 'State the rate you are offering.' });
      return;
    }
    setBusy(row.deal_id);
    try {
      await counterRateRequest(row.deal_id, { offered_rate: v, note: note.trim() });
      toast({ tone: 'success',
        message: `Countered at ${v.toFixed(2)}% — it goes to the branch to put to the customer.` });
      setCounterFor(null); setOffer(''); setNote('');
      await load();
    } catch (e) {
      toast({ tone: 'danger', message: e instanceof Error ? e.message : 'Could not counter' });
    } finally { setBusy(null); }
  };

  if (denied) {
    return (
      <>
        <PageHeader title="Treasury Rate Desk" />
        <Card><Card.Body>
          <p className="text-sm text-gray-700">
            This queue belongs to the treasury desk. If you price term deposits
            and cannot see it, ask an administrator to check your role.
          </p>
        </Card.Body></Card>
      </>
    );
  }

  const waiting = data?.waiting ?? [];
  const answered = data?.answered ?? [];

  return (
    <>
      <PageHeader
        title="Treasury Rate Desk"
        subtitle="Term deposit rates asked for by branches. Any dealer may price any request."
      />

      {loading && !data ? <Skeleton className="h-40" /> : (
        <>
          <Card className="mb-4">
            <Card.Header>
              <div className="flex items-center justify-between">
                <h2 className="text-base font-semibold text-gray-900">
                  Waiting on a price ({waiting.length})
                </h2>
                <Button size="sm" variant="secondary" onClick={() => void load()}>
                  Refresh
                </Button>
              </div>
            </Card.Header>
            <Card.Body>
              {waiting.length === 0 ? (
                <p className="py-6 text-center text-sm text-gray-400">
                  Nothing waiting. Requests raised by branches appear here.
                </p>
              ) : (
                <div className="space-y-3">
                  {waiting.map((row) => (
                    <div key={row.deal_id}
                         className="rounded-lg border border-gray-200 p-3">
                      <div className="flex flex-wrap items-start justify-between gap-2">
                        <div>
                          <p className="text-sm font-semibold text-gray-900">
                            {row.client_name}
                          </p>
                          <p className="text-xs text-gray-500">
                            {row.branch} · {row.rm_name} · {row.product}
                          </p>
                        </div>
                        <div className="text-right">
                          <p className="text-sm font-semibold text-gray-900">
                            {money(row.amount)}
                          </p>
                          <p className="text-xs text-gray-500">
                            {row.tenor} days · asking {rate(row.requested_rate)}
                          </p>
                        </div>
                      </div>

                      {counterFor === row.deal_id ? (
                        <div className="mt-3 rounded-md border border-amber-300 bg-amber-50 p-3">
                          <div className="flex flex-wrap items-end gap-2">
                            <div>
                              <label className="text-xs font-medium text-gray-700">
                                Your rate (%)
                              </label>
                              <input
                                type="number" step="0.01" value={offer} autoFocus
                                onChange={(e) => setOffer(e.target.value)}
                                className="mt-1 w-28 rounded-md border border-gray-300 px-2 py-1 text-sm"
                              />
                            </div>
                            <div className="min-w-[16rem] flex-1">
                              <label className="text-xs font-medium text-gray-700">
                                Why (the branch reads this to the customer)
                              </label>
                              <input
                                type="text" value={note}
                                onChange={(e) => setNote(e.target.value)}
                                placeholder="Above the curve for 91 days…"
                                className="mt-1 w-full rounded-md border border-gray-300 px-2 py-1 text-sm"
                              />
                            </div>
                            <Button size="sm" disabled={busy === row.deal_id}
                                    onClick={() => void counter(row)}>
                              Send the counter
                            </Button>
                            <Button size="sm" variant="secondary"
                                    onClick={() => { setCounterFor(null); setOffer(''); setNote(''); }}>
                              Cancel
                            </Button>
                          </div>
                        </div>
                      ) : (
                        <div className="mt-3 flex items-center gap-2">
                          <Button size="sm" disabled={busy === row.deal_id}
                                  onClick={() => void approve(row)}>
                            Approve at {rate(row.requested_rate)}
                          </Button>
                          <Button size="sm" variant="secondary"
                                  disabled={busy === row.deal_id}
                                  onClick={() => { setCounterFor(row.deal_id); setOffer(''); setNote(''); }}>
                            Counter
                          </Button>
                          {/* Said plainly, because it is the part that surprises
                              people: approving closes the deal there and then. */}
                          <span className="text-xs text-gray-500">
                            Approving books it and closes the deal at the branch.
                          </span>
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              )}
            </Card.Body>
          </Card>

          <Card>
            <Card.Header>
              <h2 className="text-base font-semibold text-gray-900">
                Recently answered
              </h2>
            </Card.Header>
            <Card.Body>
              {answered.length === 0 ? (
                <p className="py-4 text-center text-sm text-gray-400">
                  Nothing answered yet.
                </p>
              ) : (
                <div className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="border-b text-left text-xs uppercase tracking-wider text-gray-500">
                        <th className="px-3 py-2">Client</th>
                        <th className="px-3 py-2">Branch</th>
                        <th className="px-3 py-2 text-right">Amount</th>
                        <th className="px-3 py-2">Tenor</th>
                        <th className="px-3 py-2 text-right">Asked</th>
                        <th className="px-3 py-2">Outcome</th>
                        <th className="px-3 py-2">Priced by</th>
                      </tr>
                    </thead>
                    <tbody>
                      {answered.map((row) => {
                        const o = outcomeLabel(row);
                        return (
                          <tr key={row.deal_id} className="border-b last:border-0">
                            <td className="px-3 py-2 text-gray-900">{row.client_name}</td>
                            <td className="px-3 py-2 text-gray-600">{row.branch}</td>
                            <td className="px-3 py-2 text-right text-gray-900">{money(row.amount)}</td>
                            <td className="px-3 py-2 text-gray-600">{row.tenor}</td>
                            <td className="px-3 py-2 text-right text-gray-600">{rate(row.requested_rate)}</td>
                            <td className="px-3 py-2"><Badge tone={o.tone}>{o.text}</Badge></td>
                            <td className="px-3 py-2 text-gray-600">{row.priced_by_name ?? '—'}</td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              )}
            </Card.Body>
          </Card>
        </>
      )}
    </>
  );
}
