// PipelineBranchDay — tier 1: the branch triad validating the day's deals.
//
// The counterpart to DailyLogValidation, and deliberately the same shape: deal
// rows with Validate / Return, a branch line, and a gate that will not let the
// day close while anything is still open. A branch manager who has learned the
// daily-log screen should recognise this one immediately.
//
// Replaces the per-deal card list for the triad. Those cards were kept through
// P2 rather than removed, on the grounds that they worked — the pilot's answer
// was that the inconsistency costs more than the extra detail was worth.

import { useCallback, useEffect, useState } from 'react';
import { Button } from '@/components/Button';
import { Card } from '@/components/Card';
import { useToast } from '@/components/Toast';
import {
  fetchPipelineValidationQueue, submitPipelineDay, validatePipelineDeal,
  type PipelineQueue, type PipelineQueueRow,
} from '@/lib/api';

function todayIso(): string {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
}

function kes(n: number): string {
  if (!n) return '—';
  return Math.round(n).toLocaleString();
}

export default function PipelineBranchDay() {
  const { toast } = useToast();
  const [date, setDate] = useState(todayIso());
  const [data, setData] = useState<PipelineQueue | null>(null);
  const [loading, setLoading] = useState(false);
  const [busy, setBusy] = useState('');
  const [returning, setReturning] = useState('');
  const [note, setNote] = useState('');
  const [closing, setClosing] = useState(false);

  const load = useCallback(async (d: string) => {
    setLoading(true);
    try {
      setData(await fetchPipelineValidationQueue(d));
    } catch (e) {
      toast({ tone: 'danger', message: e instanceof Error ? e.message : 'Could not load the day.' });
      setData(null);
    } finally {
      setLoading(false);
    }
  }, [toast]);

  useEffect(() => { void load(date); }, [date, load]);

  const rows = data?.rows ?? [];
  const pending = rows.filter((r) => !r.validated).length;
  const value = rows.reduce((a, r) => a + (Number(r.deal_value) || 0), 0);
  const validatedValue = rows.filter((r) => r.validated)
    .reduce((a, r) => a + (Number(r.deal_value) || 0), 0);

  async function decide(row: PipelineQueueRow, approve: boolean) {
    if (!approve && !note.trim()) {
      toast({ tone: 'danger', message: 'A note is required when returning a deal.' });
      return;
    }
    setBusy(row.deal_id);
    try {
      // Returning is a QUERY, not a cancellation — validatePipelineDeal already
      // carries approved:false for exactly this. Routing "return" through the
      // cancel endpoint would ask to kill a live deal when the manager only
      // wanted it corrected.
      await validatePipelineDeal(row.deal_id, { approved: approve, note: note.trim() });
      toast({ tone: 'success', message: approve ? 'Deal validated.' : 'Returned to the owner.' });
      setReturning(''); setNote('');
      await load(date);
    } catch (e) {
      toast({ tone: 'danger', message: e instanceof Error ? e.message : 'Action failed.' });
    } finally {
      setBusy('');
    }
  }

  async function closeDay() {
    const branch = rows[0]?.branch || '';
    if (!branch) return;
    setClosing(true);
    try {
      await submitPipelineDay(branch, date);
      toast({ tone: 'success', message: `${branch} pipeline day closed and sent for countersigning.` });
      await load(date);
    } catch (e) {
      toast({ tone: 'danger', message: e instanceof Error ? e.message : 'Could not close the day.' });
    } finally {
      setClosing(false);
    }
  }

  const th = 'whitespace-nowrap px-3 py-2 text-left text-[11px] font-semibold uppercase tracking-wide';
  const td = 'whitespace-nowrap px-3 py-2 text-sm';

  return (
    <Card className="mt-4">
      <Card.Header>
        <div className="flex flex-wrap items-center justify-between gap-3">
          <h2 className="text-base font-semibold text-gray-900">Pipeline day</h2>
          <div className="flex items-center gap-2 text-xs">
            <label className="text-gray-500">Day</label>
            <input type="date" value={date} onChange={(e) => setDate(e.target.value)}
                   className="rounded border border-gray-200 px-2 py-1 text-xs" />
            <span className={'rounded-full px-2.5 py-1 text-[11px] '
              + (pending ? 'bg-[#FAEEDA] text-[#854F0B]' : 'bg-[#EAF3DE] text-[#3B6D11]')}>
              {pending ? `${pending} to validate` : 'all validated'}
            </span>
          </div>
        </div>
      </Card.Header>

      <Card.Body>
        {loading && <p className="py-8 text-center text-sm text-gray-400">Loading…</p>}

        {!loading && data && data.working_day === false && (
          <p className="py-8 text-center text-sm text-gray-500">
            {data.label || 'Rest day'} — no pipeline day is expected.
          </p>
        )}

        {!loading && data?.working_day !== false && rows.length === 0 && (
          <p className="py-8 text-center text-sm text-gray-400">No deals recorded for this day.</p>
        )}

        {!loading && rows.length > 0 && (
          <>
            <div className="overflow-auto rounded-lg border border-gray-200">
              <table className="w-full border-separate" style={{ borderSpacing: 0 }}>
                <thead>
                  <tr>
                    <th className={`${th} bg-gray-100 text-gray-600`}>Deal</th>
                    <th className={`${th} bg-gray-100 text-gray-600`}>Owner</th>
                    <th className={`${th} bg-gray-100 text-gray-600`}>Client</th>
                    <th className={`${th} bg-gray-100 text-gray-600`}>Product</th>
                    <th className={`${th} bg-gray-100 text-gray-600`}>Stage</th>
                    <th className={`${th} bg-[#003D57] text-right text-white`}>Value (KES)</th>
                    <th className={`${th} bg-gray-100 text-gray-600`}>Decision</th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map((r, i) => {
                    const bg = i % 2 === 1 ? 'bg-gray-50/40' : 'bg-white';
                    return (
                      <tr key={r.deal_id}>
                        <td className={`${td} ${bg} tabular-nums text-gray-500`}>{r.deal_id}</td>
                        <td className={`${td} ${bg} text-gray-800`}>{r.staff_name}</td>
                        <td className={`${td} ${bg} text-gray-600`}>{r.client}</td>
                        <td className={`${td} ${bg} text-gray-600`}>{r.product}</td>
                        <td className={`${td} ${bg} text-gray-600`}>{r.stage}</td>
                        <td className={`${td} ${bg} text-right font-semibold tabular-nums text-[#003D57]`}>
                          {kes(r.deal_value)}
                        </td>
                        <td className={`${td} ${bg}`}>
                          {r.validated ? (
                            <span className="text-[11px] text-[#3B6D11]">
                              ✓ validated{r.validated_by ? ` · ${r.validated_by}` : ''}
                            </span>
                          ) : !r.can_act ? (
                            <span className="text-[11px] text-gray-400">not yours to validate</span>
                          ) : returning === r.deal_id ? (
                            <div className="flex flex-col gap-1" style={{ minWidth: 220 }}>
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
                                      onClick={() => void decide(r, true)}>Validate</Button>
                              <Button size="sm" variant="ghost"
                                      onClick={() => { setReturning(r.deal_id); setNote(''); }}>Return</Button>
                            </div>
                          )}
                        </td>
                      </tr>
                    );
                  })}

                  <tr>
                    <td className="bg-[#EDF4F8] px-3 py-2 text-sm font-semibold text-gray-800" colSpan={5}>
                      Branch total · {rows.length} deal{rows.length === 1 ? '' : 's'}
                    </td>
                    <td className="bg-[#EDF4F8] px-3 py-2 text-right text-sm font-semibold tabular-nums text-[#003D57]">
                      {kes(value)}
                    </td>
                    <td className="bg-[#EDF4F8] px-3 py-2 text-[11px] text-gray-600">
                      {kes(validatedValue)} validated
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>

            <div className="mt-3 flex flex-wrap items-center justify-between gap-2">
              <span className="text-xs text-gray-500">
                {pending
                  ? `${pending} deal${pending === 1 ? '' : 's'} still to validate before the day can close.`
                  : 'Every deal is validated. The day can be closed.'}
              </span>
              <Button disabled={pending > 0 || closing} onClick={() => void closeDay()}>
                {closing ? 'Closing…' : 'Close the day'}
              </Button>
            </div>
          </>
        )}
      </Card.Body>
    </Card>
  );
}
