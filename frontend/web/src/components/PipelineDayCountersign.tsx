// P2 — pipeline day countersign, tiers 2 and 3.
//
// Deliberately the same shape as BranchCountersign for the daily log: a manager
// who has learned one screen has learned both. One row per branch, expandable
// to that branch's deals read-only, with Countersign and Return (note required).
//
// Ruling 2026-08-08 applies unchanged: validation TERMINATES. The Head of
// Branches countersigns a branch pipeline day; the MD and Business Manager
// observe and may return, but never countersign.

import { useCallback, useEffect, useState } from 'react';
import { Button } from '@/components/Button';
import { Card } from '@/components/Card';
import { useToast } from '@/components/Toast';
import {
  fetchPipelineValidationDays, decidePipelineDay, fetchPipelineValidationQueue,
  type PipelineDays, type PipelineDayRow, type PipelineQueue,
} from '@/lib/api';

const STATUS: Record<string, { label: string; cls: string }> = {
  draft:     { label: 'Not closed',    cls: 'bg-gray-100 text-gray-500' },
  submitted: { label: 'Awaiting you',  cls: 'bg-[#FAEEDA] text-[#854F0B]' },
  validated: { label: 'Countersigned', cls: 'bg-[#EAF3DE] text-[#3B6D11]' },
  returned:  { label: 'Returned',      cls: 'bg-[#FBEAF0] text-[#993556]' },
};

function todayIso(): string {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
}

function kes(n: number): string {
  if (!n) return '—';
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000) return `${Math.round(n / 1_000)}K`;
  return String(Math.round(n));
}

export default function PipelineDayCountersign({ onCount }: { onCount?: (n: number) => void }) {
  const { toast } = useToast();
  const [date, setDate] = useState(todayIso());
  const [data, setData] = useState<PipelineDays | null>(null);
  const [loading, setLoading] = useState(false);
  const [openKey, setOpenKey] = useState('');
  const [detail, setDetail] = useState<PipelineQueue | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [returning, setReturning] = useState('');
  const [note, setNote] = useState('');
  const [busy, setBusy] = useState('');

  const load = useCallback(async (d: string) => {
    setLoading(true);
    try {
      const r = await fetchPipelineValidationDays(d);
      setData(r);
      onCount?.(r.rows.filter((x) => x.status === 'submitted').length);
    } catch (e) {
      toast({ tone: 'danger', message: e instanceof Error ? e.message : 'Could not load pipeline days.' });
      setData(null);
    } finally {
      setLoading(false);
    }
  }, [toast, onCount]);

  useEffect(() => { void load(date); }, [date, load]);

  async function expand(row: PipelineDayRow) {
    if (openKey === row.branch) { setOpenKey(''); setDetail(null); return; }
    setOpenKey(row.branch);
    setDetail(null);
    setDetailLoading(true);
    try {
      setDetail(await fetchPipelineValidationQueue(date, row.branch));
    } catch (e) {
      toast({ tone: 'danger', message: e instanceof Error ? e.message : 'Could not open that branch.' });
      setOpenKey('');
    } finally {
      setDetailLoading(false);
    }
  }

  async function decide(row: PipelineDayRow, approve: boolean) {
    if (!approve && !note.trim()) {
      toast({ tone: 'danger', message: 'A note is required when returning a day.' });
      return;
    }
    setBusy(row.branch);
    try {
      await decidePipelineDay(row.branch, date, approve, note.trim());
      toast({ tone: 'success',
              message: approve ? `${row.branch} pipeline day countersigned.`
                               : `${row.branch} returned to the branch.` });
      setReturning(''); setNote('');
      await load(date);
    } catch (e) {
      toast({ tone: 'danger', message: e instanceof Error ? e.message : 'Action failed.' });
    } finally {
      setBusy('');
    }
  }

  const rows = data?.rows ?? [];
  const th = 'whitespace-nowrap px-3 py-2 text-left text-[11px] font-semibold uppercase tracking-wide';
  const td = 'whitespace-nowrap px-3 py-2 text-sm';

  return (
    <Card className="mt-4">
      <Card.Header>
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <h2 className="text-base font-semibold text-gray-900">Pipeline day — branches</h2>
            <p className="mt-0.5 text-xs text-gray-500">
              {data?.top_of_house
                ? 'You observe these and may return a day for amendment.'
                : 'You countersign the branch pipeline day once its deals are validated.'}
            </p>
          </div>
          <div className="flex items-center gap-2 text-xs">
            <label className="text-gray-500">Day</label>
            <input type="date" value={date} onChange={(e) => setDate(e.target.value)}
                   className="rounded border border-gray-200 px-2 py-1 text-xs" />
            <span className="rounded-full bg-[#E6F1FB] px-2.5 py-1 text-[11px] text-[#0C447C]">
              {rows.length} branches
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
          <p className="py-8 text-center text-sm text-gray-400">
            No branches consolidate to you for this day.
          </p>
        )}

        {!loading && rows.length > 0 && (
          <div className="overflow-auto rounded-lg border border-gray-200">
            <table className="w-full border-separate" style={{ borderSpacing: 0 }}>
              <thead>
                <tr>
                  <th className={`${th} bg-gray-100 text-gray-600`}>Branch</th>
                  <th className={`${th} bg-gray-100 text-gray-600`}>Deals</th>
                  <th className={`${th} bg-gray-100 text-gray-600`}>Validated</th>
                  <th className={`${th} bg-gray-100 text-gray-600`}>Pending</th>
                  <th className={`${th} bg-[#003D57] text-white`}>Value (KES)</th>
                  <th className={`${th} bg-gray-100 text-gray-600`}>Status</th>
                  <th className={`${th} bg-gray-100 text-gray-600`}>Decision</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((r, i) => {
                  const st = STATUS[r.status] ?? STATUS.draft;
                  const bg = i % 2 === 1 ? 'bg-gray-50/40' : 'bg-white';
                  const canAct = r.status === 'submitted'
                    && (!data?.top_of_house || (data?.can_return ?? false));
                  return (
                    <>
                      <tr key={r.branch}>
                        <td className={`${td} ${bg} font-medium text-gray-900`}>
                          <button type="button" onClick={() => void expand(r)}
                                  className="flex items-center gap-1.5 hover:text-brand-primary">
                            <span className="text-gray-400">{openKey === r.branch ? '▾' : '▸'}</span>
                            {r.branch}
                          </button>
                        </td>
                        <td className={`${td} ${bg} tabular-nums text-gray-700`}>{r.deals}</td>
                        <td className={`${td} ${bg} tabular-nums text-[#3B6D11]`}>{r.validated}</td>
                        <td className={`${td} ${bg} tabular-nums ${r.pending ? 'text-amber-600' : 'text-gray-300'}`}>
                          {r.pending || '—'}
                        </td>
                        <td className={`${td} ${bg} tabular-nums font-semibold text-[#003D57]`}>
                          {kes(r.value)}
                        </td>
                        <td className={`${td} ${bg}`}>
                          <span className={`rounded-full px-2 py-0.5 text-[11px] font-medium ${st.cls}`}>
                            {st.label}
                          </span>
                          {r.submitted_by_name && (
                            <div className="mt-0.5 text-[10px] text-gray-400">by {r.submitted_by_name}</div>
                          )}
                          {r.status === 'returned' && r.return_note && (
                            <div className="mt-0.5 text-[10px] text-[#993556]">{r.return_note}</div>
                          )}
                        </td>
                        <td className={`${td} ${bg}`}>
                          {!canAct ? (
                            <span className="text-[11px] text-gray-400">—</span>
                          ) : returning === r.branch ? (
                            <div className="flex flex-col gap-1" style={{ minWidth: 210 }}>
                              <input autoFocus value={note} onChange={(e) => setNote(e.target.value)}
                                     placeholder="Why is it going back?"
                                     className="w-full rounded border border-gray-300 px-2 py-1 text-xs" />
                              <div className="flex gap-1">
                                <Button size="sm" variant="secondary" disabled={busy === r.branch}
                                        onClick={() => void decide(r, false)}>Send back</Button>
                                <Button size="sm" variant="ghost"
                                        onClick={() => { setReturning(''); setNote(''); }}>Cancel</Button>
                              </div>
                            </div>
                          ) : (
                            <div className="flex gap-1">
                              {!data?.top_of_house && (
                                <Button size="sm" disabled={busy === r.branch}
                                        onClick={() => void decide(r, true)}>Countersign</Button>
                              )}
                              <Button size="sm" variant="ghost"
                                      onClick={() => { setReturning(r.branch); setNote(''); }}>
                                Return
                              </Button>
                            </div>
                          )}
                        </td>
                      </tr>

                      {openKey === r.branch && (
                        <tr key={`${r.branch}-d`}>
                          <td colSpan={7} className="bg-[#F7FBFD] px-6 py-3">
                            {detailLoading && <p className="text-xs text-gray-400">Opening {r.branch}…</p>}
                            {!detailLoading && (detail?.rows ?? []).length === 0 && (
                              <p className="text-xs text-gray-400">No deals recorded for this day.</p>
                            )}
                            {!detailLoading && (detail?.rows ?? []).length > 0 && (
                              <table className="w-full">
                                <tbody>
                                  {(detail?.rows ?? []).map((d) => (
                                    <tr key={d.deal_id} className="border-b border-gray-100 last:border-0">
                                      <td className="py-1 pr-3 text-xs tabular-nums text-gray-500" style={{ width: 80 }}>
                                        {d.deal_id}
                                      </td>
                                      <td className="py-1 pr-3 text-xs text-gray-800">{d.staff_name}</td>
                                      <td className="py-1 pr-3 text-xs text-gray-500">{d.client}</td>
                                      <td className="py-1 pr-3 text-xs text-gray-500">{d.product}</td>
                                      <td className="py-1 pr-3 text-xs tabular-nums text-gray-700" style={{ width: 80 }}>
                                        {kes(d.deal_value)}
                                      </td>
                                      <td className="py-1 text-xs" style={{ width: 130 }}>
                                        {d.validated
                                          ? <span className="text-[#3B6D11]">✓ validated</span>
                                          : <span className="text-amber-600">awaiting validation</span>}
                                      </td>
                                    </tr>
                                  ))}
                                </tbody>
                              </table>
                            )}
                          </td>
                        </tr>
                      )}
                    </>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </Card.Body>
    </Card>
  );
}
