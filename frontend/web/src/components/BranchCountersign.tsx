// TIER 2 — branch countersign.
//
// Ruling 2026-08-08: the Branch Manager validates individuals and closes the
// branch day; the Head of Branches validates the BRANCH, may return it to the
// BM with a reason, and may expand a branch to inspect its members READ-ONLY.
// This component never offers per-staff Validate/Return — the server also
// forces can_act=false for an inspecting caller, so the two agree.
//
// Below the branch list sits the accountability surface you asked for: every
// staff member across all branches who has not filed, aged in business days,
// so the oldest neglect is at the top.

import { useCallback, useEffect, useState } from 'react';
import { Button } from '@/components/Button';
import { Card } from '@/components/Card';
import { useToast } from '@/components/Toast';
import {
  fetchBranchDays, decideBranchDay, fetchBranchLogValidationQueue,
  fetchNonSubmitters,
  type BranchDays, type BranchDayRow, type ValidationQueue,
  type NonSubmitters,
} from '@/lib/api';

const STATUS: Record<string, { label: string; cls: string }> = {
  draft:     { label: 'Not submitted', cls: 'bg-gray-100 text-gray-500' },
  submitted: { label: 'Awaiting you',  cls: 'bg-[#FAEEDA] text-[#854F0B]' },
  validated: { label: 'Countersigned', cls: 'bg-[#EAF3DE] text-[#3B6D11]' },
  returned:  { label: 'Returned',      cls: 'bg-[#FBEAF0] text-[#993556]' },
};

function todayIso(): string {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
}

export default function BranchCountersign({ onCount }: { onCount?: (n: number) => void }) {
  const { toast } = useToast();
  const [date, setDate] = useState(todayIso());
  const [data, setData] = useState<BranchDays | null>(null);
  const [loading, setLoading] = useState(false);
  const [busy, setBusy] = useState('');
  const [returning, setReturning] = useState('');
  const [note, setNote] = useState('');
  const [open, setOpen] = useState('');                       // expanded branch
  const [detail, setDetail] = useState<ValidationQueue | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  // E3: the cross-branch follow-up list, below the branch table.
  const [outstanding, setOutstanding] = useState<NonSubmitters | null>(null);

  const load = useCallback(async (d: string) => {
    setLoading(true);
    try {
      const r = await fetchBranchDays(d);
      setData(r);
      onCount?.(r.rows.filter((x) => x.status === 'submitted').length);
      try { setOutstanding(await fetchNonSubmitters(d)); }
      catch { setOutstanding(null); }
    } catch (e) {
      toast({ tone: 'danger', message: e instanceof Error ? e.message : 'Could not load branches.' });
      setData(null);
    } finally {
      setLoading(false);
    }
  }, [toast, onCount]);

  useEffect(() => { void load(date); }, [date, load]);

  async function expand(branch: string) {
    if (open === branch) { setOpen(''); setDetail(null); return; }
    setOpen(branch);
    setDetail(null);
    setDetailLoading(true);
    try {
      setDetail(await fetchBranchLogValidationQueue(date, branch));
    } catch (e) {
      toast({ tone: 'danger', message: e instanceof Error ? e.message : 'Could not open the branch.' });
      setOpen('');
    } finally {
      setDetailLoading(false);
    }
  }

  async function decide(row: BranchDayRow, approve: boolean) {
    if (!approve && !note.trim()) {
      toast({ tone: 'danger', message: 'A note is required when returning a branch day.' });
      return;
    }
    setBusy(row.branch);
    try {
      await decideBranchDay(row.branch, date, approve, note.trim());
      toast({ tone: 'success',
              message: approve ? `${row.branch} countersigned.`
                               : `${row.branch} returned to the branch manager.` });
      setReturning(''); setNote('');
      await load(date);
    } catch (e) {
      toast({ tone: 'danger', message: e instanceof Error ? e.message : 'Action failed.' });
    } finally {
      setBusy('');
    }
  }

  const rows = data?.rows ?? [];
  const notFiled = (detail?.rows ?? []).filter((r) => r.status === 'missing');
  const th = 'whitespace-nowrap px-3 py-2 text-left text-[11px] font-semibold uppercase tracking-wide';
  const td = 'whitespace-nowrap px-3 py-2 text-sm';

  return (
    <Card className="mt-4">
      <Card.Header>
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <h2 className="text-base font-semibold text-gray-900">Branch validation</h2>
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
        {loading && <p className="py-8 text-center text-sm text-gray-400">Loading branches…</p>}

        {!loading && data && !data.working_day && (
          <p className="py-8 text-center text-sm text-gray-500">
            {data.label || 'Rest day'} — no branch days are expected.
          </p>
        )}

        {!loading && data?.working_day && rows.length === 0 && (
          <p className="py-8 text-center text-sm text-gray-400">
            No branches report to you for countersigning.
          </p>
        )}

        {!loading && rows.length > 0 && (
          <div className="overflow-auto rounded-lg border border-gray-200">
            <table className="w-full border-separate" style={{ borderSpacing: 0 }}>
              <thead>
                <tr>
                  <th className={`${th} bg-gray-100 text-gray-600`}>Branch</th>
                  <th className={`${th} bg-gray-100 text-gray-600`}>Staff</th>
                  <th className={`${th} bg-gray-100 text-gray-600`}>Filed</th>
                  <th className={`${th} bg-gray-100 text-gray-600`}>Validated</th>
                  <th className={`${th} bg-gray-100 text-gray-600`}>Not filed</th>
                  <th className={`${th} bg-[#003D57] text-white`}>Branch index</th>
                  <th className={`${th} bg-gray-100 text-gray-600`}>Status</th>
                  <th className={`${th} bg-gray-100 text-gray-600`}>Decision</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((r, i) => {
                  const st = STATUS[r.status] ?? STATUS.draft;
                  const expanded = open === r.branch;
                  const bg = i % 2 === 1 ? 'bg-gray-50/40' : 'bg-white';
                  return (
                    <>
                      <tr key={r.branch}>
                        <td className={`${td} ${bg} font-medium text-gray-900`}>
                          <button type="button" onClick={() => void expand(r.branch)}
                                  className="flex items-center gap-1.5 hover:text-brand-primary">
                            <span className="text-gray-400">{expanded ? '▾' : '▸'}</span>
                            {r.branch}
                          </button>
                          {r.over_reported > 0 && (
                            <span className="ml-2 rounded bg-[#FBEAF0] px-1.5 py-0.5 text-[10px] font-medium text-[#993556]">
                              {r.over_reported} over-reported
                            </span>
                          )}
                        </td>
                        <td className={`${td} ${bg} tabular-nums text-gray-500`}>{r.expected}</td>
                        <td className={`${td} ${bg} tabular-nums text-gray-700`}>{r.filed}</td>
                        <td className={`${td} ${bg} tabular-nums text-[#3B6D11]`}>{r.validated}</td>
                        <td className={`${td} ${bg} tabular-nums ${r.not_filed ? 'text-amber-600' : 'text-gray-300'}`}>
                          {r.not_filed || '—'}
                        </td>
                        <td className={`${td} ${bg} tabular-nums font-semibold text-[#003D57]`}>
                          {(r.branch_index || 0).toFixed(1)}
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
                          {r.status !== 'submitted' ? (
                            <span className="text-[11px] text-gray-400">—</span>
                          ) : returning === r.branch ? (
                            <div className="flex flex-col gap-1" style={{ minWidth: 220 }}>
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
                              <Button size="sm" disabled={busy === r.branch}
                                      onClick={() => void decide(r, true)}>Countersign</Button>
                              <Button size="sm" variant="ghost"
                                      onClick={() => { setReturning(r.branch); setNote(''); }}>Return</Button>
                            </div>
                          )}
                        </td>
                      </tr>

                      {expanded && (
                        <tr key={`${r.branch}-detail`}>
                          <td colSpan={8} className="bg-[#F7FBFD] px-4 py-3">
                            {detailLoading && <p className="text-xs text-gray-400">Opening {r.branch}…</p>}
                            {!detailLoading && detail && (
                              <div>
                                <div className="mb-2 text-xs font-semibold text-gray-600">
                                  {r.branch} — members (read-only; the branch manager validates these)
                                </div>
                                <table className="w-full">
                                  <tbody>
                                    {(detail.rows ?? []).map((m) => (
                                      <tr key={m.staff_code} className="border-b border-gray-100 last:border-0">
                                        <td className="py-1 pr-3 text-xs tabular-nums text-gray-500"
                                            style={{ width: 80 }}>{m.staff_code}</td>
                                        <td className="py-1 pr-3 text-xs text-gray-800">{m.staff_name}</td>
                                        <td className="py-1 pr-3 text-xs text-gray-500">{m.role}</td>
                                        <td className="py-1 pr-3 text-xs tabular-nums text-gray-700"
                                            style={{ width: 60 }}>
                                          {m.status === 'missing' ? '—' : Number(m.index ?? 0).toFixed(1)}
                                        </td>
                                        <td className="py-1 text-xs" style={{ width: 150 }}>
                                          {m.validated
                                            ? <span className="text-[#3B6D11]">✓ Validated</span>
                                            : m.status === 'missing'
                                              ? (m as unknown as { excused?: boolean }).excused
                                                ? <span className="text-gray-500">Excused</span>
                                                : <span className="text-amber-600">Not filed</span>
                                              : <span className="text-gray-400">Awaiting the BM</span>}
                                        </td>
                                      </tr>
                                    ))}
                                  </tbody>
                                </table>
                                {notFiled.length > 0 && (
                                  <p className="mt-2 text-[11px] text-amber-700">
                                    {notFiled.length} of {detail.rows.length} have not filed —
                                    the branch manager can record a reason within the window.
                                  </p>
                                )}
                              </div>
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
        {/* E3 — cross-branch follow-up. Excused staff are deliberately absent:
            a person on approved leave is not a follow-up item, and listing them
            would train managers to ignore the list. Ageing is in BUSINESS days,
            so a weekend never inflates it. */}
        {!loading && outstanding && outstanding.rows.length > 0 && (
          <div className="mt-6">
            <div className="mb-2 flex flex-wrap items-baseline justify-between gap-2">
              <h3 className="text-sm font-semibold text-gray-800">
                Outstanding daily logs — follow-up
              </h3>
              <span className="text-xs text-gray-500">
                {outstanding.total} staff across your branches have not filed for this day
              </span>
            </div>
            <div className="overflow-auto rounded-lg border border-amber-200">
              <table className="w-full border-separate" style={{ borderSpacing: 0 }}>
                <thead>
                  <tr>
                    <th className={`${th} bg-[#FAEEDA] text-[#854F0B]`}>Days</th>
                    <th className={`${th} bg-[#FAEEDA] text-[#854F0B]`}>Staff</th>
                    <th className={`${th} bg-[#FAEEDA] text-[#854F0B]`}>Name</th>
                    <th className={`${th} bg-[#FAEEDA] text-[#854F0B]`}>Role</th>
                    <th className={`${th} bg-[#FAEEDA] text-[#854F0B]`}>Branch</th>
                    <th className={`${th} bg-[#FAEEDA] text-[#854F0B]`}>Recorded reason</th>
                  </tr>
                </thead>
                <tbody>
                  {outstanding.rows.map((r, i) => (
                    <tr key={r.staff_code} className={i % 2 === 1 ? 'bg-[#FFFBF4]' : 'bg-white'}>
                      <td className={`${td} tabular-nums font-semibold ${
                        r.days_outstanding >= 3 ? 'text-rose-600' : 'text-amber-700'}`}>
                        {r.days_outstanding}
                      </td>
                      <td className={`${td} tabular-nums text-gray-500`}>{r.staff_code}</td>
                      <td className={`${td} text-gray-900`}>{r.staff_name}</td>
                      <td className={`${td} text-gray-500`}>{r.role}</td>
                      <td className={`${td} text-gray-600`}>{r.branch}</td>
                      <td className={`${td} text-gray-500`}>
                        {r.exception
                          ? <span>{r.exception}{r.exception_note ? ` — ${r.exception_note}` : ''}</span>
                          : <span className="text-gray-300">none recorded</span>}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}
      </Card.Body>
    </Card>
  );
}
