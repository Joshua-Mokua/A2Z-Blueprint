// ReferralBench — what is waiting on me, and what I sent that nobody has actioned.
//
// The second list is the reason this exists. Today a referrer sends one and
// hears nothing; there is no screen anywhere that says "three people have been
// sitting on yours for a week".
//
// Referrals do NOT expire (ruling 2026-08-09) — they escalate until a decision
// is given, stopping at the unit owner. So an overdue row carries the ladder of
// people to lean on rather than a dead badge saying the referral lapsed.

import { useCallback, useEffect, useState } from 'react';
import { Button } from '@/components/Button';
import { Card } from '@/components/Card';
import { useToast } from '@/components/Toast';
import {
  fetchReferralBench, acceptReferral, declineReferral,
  type ReferralBench as Bench, type ReferralBenchRow,
} from '@/lib/api';

function kes(n: number): string {
  if (!n) return '—';
  return Math.round(n).toLocaleString();
}

function due(row: ReferralBenchRow): { text: string; tone: string } {
  const c = row.clock;
  if (c.status === 'overdue') {
    const d = Math.floor(c.overdue_hours / 24);
    return {
      text: d >= 1 ? `${d} day${d === 1 ? '' : 's'} overdue` : `${Math.round(c.overdue_hours)}h overdue`,
      tone: 'text-[#993556]',
    };
  }
  if (c.hours_left >= 24) return { text: `${Math.floor(c.hours_left / 24)}d left`, tone: 'text-gray-500' };
  return { text: `${Math.round(c.hours_left)}h left`, tone: 'text-amber-600' };
}

export default function ReferralBench() {
  const { toast } = useToast();
  const [data, setData] = useState<Bench | null>(null);
  const [loading, setLoading] = useState(false);
  const [busy, setBusy] = useState('');
  const [returning, setReturning] = useState('');
  const [note, setNote] = useState('');

  const load = useCallback(async () => {
    setLoading(true);
    try {
      setData(await fetchReferralBench());
    } catch (e) {
      toast({ tone: 'danger', message: e instanceof Error ? e.message : 'Could not load the referral bench.' });
      setData(null);
    } finally {
      setLoading(false);
    }
  }, [toast]);

  useEffect(() => { void load(); }, [load]);

  async function decide(row: ReferralBenchRow, accept: boolean) {
    if (!accept && !note.trim()) {
      toast({ tone: 'danger', message: 'A note is required when returning a referral.' });
      return;
    }
    setBusy(row.deal_id);
    try {
      if (accept) await acceptReferral(row.deal_id);
      else await declineReferral(row.deal_id, note.trim());
      toast({
        tone: 'success',
        message: accept
          ? `Accepted — ${row.from_name || 'the referrer'} is credited for the day they sent it.`
          : 'Returned to the referrer.',
      });
      setReturning(''); setNote('');
      await load();
    } catch (e) {
      toast({ tone: 'danger', message: e instanceof Error ? e.message : 'Action failed.' });
    } finally {
      setBusy('');
    }
  }

  const incoming = data?.incoming ?? [];
  const outgoing = data?.outgoing ?? [];

  return (
    <div className="space-y-4">
      <Card>
        <Card.Header>
          <div className="flex flex-wrap items-center justify-between gap-2">
            <h2 className="text-base font-semibold text-gray-900">Referrals to me</h2>
            <span className="flex items-center gap-2 text-xs">
              {(data?.incoming_overdue ?? 0) > 0 && (
                <span className="rounded-full bg-[#FBEAF0] px-2.5 py-1 text-[#993556]">
                  {data?.incoming_overdue} overdue
                </span>
              )}
              <span className="rounded-full bg-[#E6F1FB] px-2.5 py-1 text-[#0C447C]">
                {incoming.length} waiting
              </span>
            </span>
          </div>
        </Card.Header>
        <Card.Body>
          {loading && <p className="py-8 text-center text-sm text-gray-400">Loading…</p>}

          {!loading && incoming.length === 0 && (
            <p className="py-8 text-center text-sm text-gray-400">Nothing is waiting on you.</p>
          )}

          {!loading && incoming.length > 0 && (
            <div className="space-y-2">
              {incoming.map((r) => {
                const d = due(r);
                return (
                  <div key={r.deal_id}
                       className="flex flex-wrap items-center gap-3 rounded-lg border border-gray-200 p-3">
                    <div className="min-w-0 flex-1">
                      <div className="truncate text-sm font-medium text-gray-900">
                        {r.client || r.deal_id}
                      </div>
                      <div className="mt-0.5 text-xs text-gray-500">
                        {r.product && <span>{r.product} · </span>}
                        KES {kes(r.value)}
                        {r.from_name && <span> · from {r.from_name}</span>}
                      </div>
                    </div>
                    <div className={`text-xs tabular-nums ${d.tone}`} style={{ minWidth: 96 }}>
                      {d.text}
                    </div>
                    {returning === r.deal_id ? (
                      <div className="flex flex-col gap-1" style={{ minWidth: 240 }}>
                        <input autoFocus value={note} onChange={(e) => setNote(e.target.value)}
                               placeholder="Why is it going back?"
                               className="w-full rounded border border-gray-300 px-2 py-1 text-xs" />
                        <div className="flex gap-1">
                          <Button size="sm" variant="secondary" disabled={busy === r.deal_id}
                                  onClick={() => void decide(r, false)}>Send back</Button>
                          <Button size="sm" variant="ghost"
                                  onClick={() => { setReturning(''); setNote(''); }}>Cancel</Button>
                        </div>
                      </div>
                    ) : (
                      <div className="flex gap-1">
                        <Button size="sm" disabled={busy === r.deal_id}
                                onClick={() => void decide(r, true)}>Accept</Button>
                        <Button size="sm" variant="ghost"
                                onClick={() => { setReturning(r.deal_id); setNote(''); }}>Return</Button>
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          )}
        </Card.Body>
      </Card>

      <Card>
        <Card.Header>
          <div className="flex flex-wrap items-center justify-between gap-2">
            <h2 className="text-base font-semibold text-gray-900">Sent, not yet actioned</h2>
            {(data?.outgoing_overdue ?? 0) > 0 && (
              <span className="rounded-full bg-[#FBEAF0] px-2.5 py-1 text-xs text-[#993556]">
                {data?.outgoing_overdue} overdue
              </span>
            )}
          </div>
        </Card.Header>
        <Card.Body>
          {!loading && outgoing.length === 0 && (
            <p className="py-8 text-center text-sm text-gray-400">
              Everything you referred has been actioned.
            </p>
          )}

          {!loading && outgoing.length > 0 && (
            <div className="space-y-2">
              {outgoing.map((r) => {
                const d = due(r);
                const ladder = r.clock.escalate_to ?? [];
                return (
                  <div key={r.deal_id} className="rounded-lg border border-gray-200 p-3">
                    <div className="flex flex-wrap items-center gap-3">
                      <div className="min-w-0 flex-1">
                        <div className="truncate text-sm font-medium text-gray-900">
                          {r.client || r.deal_id}
                        </div>
                        <div className="mt-0.5 text-xs text-gray-500">
                          {r.product && <span>{r.product} · </span>}
                          KES {kes(r.value)}
                          {r.to_name && <span> · with {r.to_name}</span>}
                        </div>
                      </div>
                      <div className={`text-xs tabular-nums ${d.tone}`}>{d.text}</div>
                    </div>
                    {ladder.length > 0 && (
                      <div className="mt-2 border-t border-gray-100 pt-2 text-xs text-gray-600">
                        <span className="text-gray-400">Escalating to </span>
                        {ladder.map((x, i) => (
                          <span key={`${x.code}-${i}`}>
                            {i > 0 && <span className="text-gray-300"> → </span>}
                            <span className={x.level === 'unit_owner' ? 'font-medium text-gray-800' : ''}>
                              {x.name}
                            </span>
                          </span>
                        ))}
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          )}
        </Card.Body>
      </Card>
    </div>
  );
}
