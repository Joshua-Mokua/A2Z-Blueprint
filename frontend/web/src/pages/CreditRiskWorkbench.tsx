// ── CREDIT RISK WORKBENCH ─────────────────────────────────────────────────────
// RULING (2026-08-18): "I want his sidebar not to have the Department Review,
// since that one does not really concern them - the CIS is their main
// workbench."
//
// Credit Analysis and Department Review both pointed at /lms, so credit risk
// got the segment analyst's desk: claim from the pool, request documents,
// return for rework, mark ready for committee. None of it their job, and the
// noise of it hid the cases that were.
//
// This lists only what a DEPARTMENT committee has recommended, and offers the
// decision the bank designed: approve with the conditions it carries, approve
// but send it up to the Chief Credit Risk, decline with a reason, or return it
// to a named person on the case rather than always to the deal's owner.
//
// Every endpoint behind this already existed. Nothing called them.
import { useCallback, useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  fetchLmsApplications, getConditionLibrary, recordCreditRiskDecision,
  returnCaseForRework, escalateToChief, claimCase, seekInput,
} from '@/lib/api';
import type { ConditionLibrary } from '@/lib/api';
import type { LoanApplication } from '@/types/lms';
import { useRole } from '@/hooks/useRole';

// What a department committee recommendation looks like. The older spelling is
// accepted so a case marked before the rename still appears.
const READY = ['committee_recommended', 'committee_approved'];

const DECLINE_REASONS = [
  'Debt service ratio outside policy',
  '1/3 rule violation',
  'Adverse CRB listing',
  'Insufficient or unverifiable income',
  'Facility exceeds the salary multiplier',
  'Tenor outside product terms',
  'Security inadequate or unacceptable',
  'Employer or sector not acceptable',
  'Existing arrears with the bank',
  'Documentation not satisfactory',
];

function money(v?: number, ccy?: string) {
  if (v === undefined || v === null) return '—';
  return `${ccy ?? 'KES'} ${Number(v).toLocaleString()}`;
}

type Mode = 'approve' | 'escalate' | 'decline' | 'return' | 'input';

export function CreditRiskWorkbench() {
  const { user } = useRole();
  const navigate = useNavigate();
  const myCode = String(user?.staff_code ?? '');

  const [apps, setApps] = useState<LoanApplication[]>([]);
  const [lib, setLib] = useState<ConditionLibrary | null>(null);
  const [tab, setTab] = useState<'mine' | 'pool'>('mine');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);

  const [open, setOpen] = useState<string | null>(null);
  const [mode, setMode] = useState<Mode>('approve');
  const [reason, setReason] = useState('');
  const [preApproval, setPreApproval] = useState<string[]>([]);
  const [preDisb, setPreDisb] = useState<string[]>([]);
  const [returnTo, setReturnTo] = useState('');

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [res, conds] = await Promise.all([
        fetchLmsApplications(),
        getConditionLibrary().catch(() => null),
      ]);
      setApps(res?.applications ?? []);
      setLib(conds);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not load the cases.');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { void load(); }, [load]);

  const ready = useMemo(
    () => apps.filter((a) => READY.includes(String(a.status ?? '').toLowerCase())),
    [apps],
  );
  const assigneeOf = (a: LoanApplication) => {
    const an = (a as { analyst?: { code?: string; name?: string } }).analyst;
    return { code: String(an?.code ?? ''), name: String(an?.name ?? '') };
  };
  const mine = useMemo(
    () => ready.filter((a) => assigneeOf(a).code === myCode && myCode !== ''),
    [ready, myCode],
  );
  const pool = useMemo(() => ready.filter((a) => !assigneeOf(a).code), [ready]);
  const shown = tab === 'mine' ? mine : pool;

  // Who a case can be returned to: everyone already on it. Returning to
  // somebody who has never touched the case is how work goes missing.
  function peopleOn(a: LoanApplication): { code: string; label: string }[] {
    const out: { code: string; label: string }[] = [];
    const push = (code?: string, label?: string, role?: string) => {
      const c = String(code ?? '').trim();
      if (!c || out.some((x) => x.code === c)) return;
      out.push({ code: c, label: `${label || c}${role ? ` — ${role}` : ''}` });
    };
    const rec = a as Record<string, unknown>;
    push(String(rec.rm_code ?? ''), String(rec.rm_name ?? ''), 'the deal owner');
    const an = assigneeOf(a);
    push(an.code, an.name, 'analyst');
    push(String(rec.returned_by_code ?? ''), String(rec.returned_by_name ?? ''),
         'returned it before');
    push(String(rec.committee_recommended_by ?? ''), '', 'recommending committee');
    return out;
  }

  function reset() {
    setOpen(null);
    setMode('approve');
    setReason('');
    setPreApproval([]);
    setPreDisb([]);
    setReturnTo('');
  }

  const toggle = (list: string[], set: (v: string[]) => void, c: string) =>
    set(list.includes(c) ? list.filter((x) => x !== c) : [...list, c]);

  async function act(a: LoanApplication) {
    const id = String(a.id);
    if (reason.trim().length < 5) return;
    setBusy(id);
    setError(null);
    try {
      if (mode === 'escalate') {
        await escalateToChief(id, { reason: reason.trim(), to: 'chief' });
      } else if (mode === 'input') {
        const to = peopleOn(a).find((p) => p.code === returnTo);
        await seekInput(id, {
          to: returnTo,
          to_name: to?.label.split(' — ')[0],
          question: reason.trim(),
        });
      } else if (mode === 'return') {
        const to = peopleOn(a).find((p) => p.code === returnTo);
        await returnCaseForRework(id, {
          reason: reason.trim(),
          return_to: returnTo || undefined,
          return_to_name: to?.label.split(' — ')[0],
        });
      } else {
        await recordCreditRiskDecision(id, {
          verdict: mode === 'approve' ? 'approved' : 'declined',
          authority: 'Credit Risk',
          reason: reason.trim(),
          pre_approval_conditions: mode === 'approve' ? preApproval : undefined,
          pre_disbursement_conditions: mode === 'approve' ? preDisb : undefined,
        });
      }
      reset();
      await load();
    } catch (e) {
      // The server's refusal says something useful. Show it.
      setError(e instanceof Error ? e.message : 'Could not record that.');
    } finally {
      setBusy(null);
    }
  }

  async function claim(a: LoanApplication) {
    const id = String(a.id);
    setBusy(id);
    setError(null);
    try {
      await claimCase(id, myCode, String(user?.full_name ?? ''));
      setTab('mine');
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not claim that case.');
    } finally {
      setBusy(null);
    }
  }

  const canRecord = reason.trim().length >= 5
    && (mode !== 'return' || returnTo !== '')
    // A request for input needs somebody to ask and something to ask them.
    && (mode !== 'input' || (returnTo !== '' && reason.trim().length >= 10));

  return (
    <div className="p-6">
      <h1 className="text-xl font-semibold text-[#003D57]">Credit Risk</h1>
      <p className="mt-1 text-sm text-gray-600">
        Cases a department committee has recommended. Work still with the
        department analysts is on Department Review.
      </p>

      <div className="mt-4 flex flex-wrap items-center gap-3">
        <button type="button" onClick={() => setTab('mine')}
                className={`rounded-lg px-4 py-2 text-sm font-medium ${
                  tab === 'mine' ? 'bg-[#0097A7] text-white' : 'border bg-white'}`}>
          My cases ({mine.length})
        </button>
        <button type="button" onClick={() => setTab('pool')}
                className={`rounded-lg px-4 py-2 text-sm font-medium ${
                  tab === 'pool' ? 'bg-[#0097A7] text-white' : 'border bg-white'}`}>
          Pool ({pool.length})
        </button>
        <div className="rounded-lg border bg-white px-4 py-2 text-sm">
          Their value{' '}
          <span className="font-semibold">
            {money(shown.reduce((t, a) => t + (Number(a.amount) || 0), 0))}
          </span>
        </div>
        <button type="button" onClick={() => void load()}
                className="ml-auto rounded-lg border px-4 py-2 text-sm">
          Refresh
        </button>
      </div>

      {lib && !lib.configured && (
        <div className="mt-4 rounded-lg border border-amber-300 bg-amber-50 p-3 text-sm text-amber-900">
          The condition library is empty, so there is nothing to pick from when
          approving. An administrator can seed it.
        </div>
      )}
      {error && (
        <div className="mt-4 rounded-lg border border-red-300 bg-red-50 p-3 text-sm text-red-800">
          {error}
        </div>
      )}

      {loading ? (
        <p className="mt-8 text-center text-gray-500">Loading…</p>
      ) : shown.length === 0 ? (
        <div className="mt-6 rounded-lg border bg-white p-10 text-center">
          <p className="text-gray-700">
            {tab === 'mine' ? 'Nothing is assigned to you.' : 'The pool is empty.'}
          </p>
          <p className="mt-1 text-sm text-gray-500">
            A case arrives here once a department committee has recommended it.
            Until then it sits with the department analyst.
          </p>
        </div>
      ) : (
        <div className="mt-4 space-y-3">
          {shown.map((a) => {
            const id = String(a.id);
            const an = assigneeOf(a);
            const isOpen = open === id;
            return (
              <div key={id} className="rounded-lg border bg-white">
                <div className="flex flex-wrap items-center gap-4 p-4">
                  <div className="min-w-[16rem] flex-1">
                    <div className="font-medium text-gray-900">{a.client_name}</div>
                    <div className="text-xs text-gray-500">
                      {id} · {a.product ?? '—'} · recommended by{' '}
                      {String((a as Record<string, unknown>).committee_recommended_by ?? '—')}
                    </div>
                  </div>
                  <div className="text-right">
                    <div className="font-semibold">{money(a.amount, a.currency)}</div>
                    <div className="text-xs text-gray-500">
                      {an.code ? `with ${an.name || an.code}` : 'unassigned'}
                    </div>
                  </div>
                  <div className="flex gap-2">
                    <button type="button"
                            onClick={() => navigate(`/lms/${encodeURIComponent(id)}`)}
                            className="rounded border px-3 py-1.5 text-xs">
                      Open the case
                    </button>
                    {!an.code && (
                      <button type="button" disabled={busy === id}
                              onClick={() => void claim(a)}
                              className="rounded border px-3 py-1.5 text-xs">
                        {busy === id ? 'Claiming…' : 'Claim'}
                      </button>
                    )}
                    <button type="button"
                            onClick={() => { if (isOpen) reset(); else { reset(); setOpen(id); } }}
                            className="rounded bg-[#0097A7] px-3 py-1.5 text-xs font-medium text-white">
                      {isOpen ? 'Close' : 'Decide'}
                    </button>
                  </div>
                </div>

                {isOpen && (
                  <div className="border-t bg-gray-50 p-4">
                    <div className="flex flex-wrap gap-2">
                      {([['approve', 'Approve'],
                         ['escalate', 'Approve — send up to the Chief'],
                         ['decline', 'Decline'],
                         ['return', 'Return for rework'],
                         // A question is not a rejection. The case stays here.
                         ['input', 'Seek input']] as [Mode, string][])
                        .map(([m, label]) => (
                          <button key={m} type="button" onClick={() => setMode(m)}
                                  className={`rounded-lg px-3 py-1.5 text-sm ${
                                    mode === m ? 'bg-[#003D57] text-white' : 'border bg-white'}`}>
                            {label}
                          </button>
                        ))}
                    </div>

                    {mode === 'approve' && lib && (
                      <div className="mt-4 grid gap-4 md:grid-cols-2">
                        <div>
                          <div className="text-xs font-semibold uppercase tracking-wide text-gray-600">
                            Conditions before approval takes effect
                          </div>
                          <div className="mt-2 space-y-1">
                            {lib.pre_approval.map((c) => (
                              <label key={c} className="flex items-start gap-2 text-sm">
                                <input type="checkbox" className="mt-1"
                                       checked={preApproval.includes(c)}
                                       onChange={() => toggle(preApproval, setPreApproval, c)} />
                                <span>{c}</span>
                              </label>
                            ))}
                          </div>
                        </div>
                        <div>
                          <div className="text-xs font-semibold uppercase tracking-wide text-gray-600">
                            Conditions before disbursement
                          </div>
                          <p className="mt-1 text-xs text-gray-500">
                            Credit admin ticks these off. Nothing disburses until
                            every one is met.
                          </p>
                          <div className="mt-2 space-y-1">
                            {lib.pre_disbursement.map((c) => (
                              <label key={c} className="flex items-start gap-2 text-sm">
                                <input type="checkbox" className="mt-1"
                                       checked={preDisb.includes(c)}
                                       onChange={() => toggle(preDisb, setPreDisb, c)} />
                                <span>{c}</span>
                              </label>
                            ))}
                          </div>
                        </div>
                      </div>
                    )}

                    {mode === 'decline' && (
                      <div className="mt-4">
                        <div className="text-xs font-semibold uppercase tracking-wide text-gray-600">
                          Why it is declined
                        </div>
                        <div className="mt-2 flex flex-wrap gap-2">
                          {DECLINE_REASONS.map((r) => (
                            <button key={r} type="button"
                                    onClick={() => setReason(r)}
                                    className={`rounded-full border px-3 py-1 text-xs ${
                                      reason === r ? 'border-[#003D57] bg-white font-medium' : 'bg-white'}`}>
                              {r}
                            </button>
                          ))}
                        </div>
                      </div>
                    )}

                    {(mode === 'return' || mode === 'input') && (
                      <div className="mt-4">
                        <label className="block text-xs font-semibold uppercase tracking-wide text-gray-600">
                          Send it back to
                        </label>
                        <select className="mt-2 w-full max-w-md rounded-lg border px-3 py-2"
                                value={returnTo}
                                onChange={(e) => setReturnTo(e.target.value)}>
                          <option value="">Choose someone on this case…</option>
                          {peopleOn(a).map((p) => (
                            <option key={p.code} value={p.code}>{p.label}</option>
                          ))}
                        </select>
                        <p className="mt-1 text-xs text-gray-500">
                          It goes to them, not to the deal's owner, and lands on
                          their screen rather than waiting in a pool.
                        </p>
                      </div>
                    )}

                    {mode === 'escalate' && (
                      <p className="mt-4 text-sm text-gray-700">
                        This goes to the Chief Credit Risk for their approval.
                        Say why it is above your authority.
                      </p>
                    )}

                    <div className="mt-4">
                      <label className="block text-xs font-semibold uppercase tracking-wide text-gray-600">
                        {mode === 'decline' ? 'Reason — this goes on the case'
                          : mode === 'return' ? 'What needs doing'
                          : 'Reason — this goes on the case'}
                      </label>
                      <input className="mt-2 w-full rounded-lg border px-3 py-2"
                             value={reason}
                             onChange={(e) => setReason(e.target.value)}
                             placeholder="What decided it" />
                    </div>

                    <div className="mt-4 flex items-center justify-end gap-3">
                      {mode === 'approve' && (preApproval.length + preDisb.length) > 0 && (
                        <span className="text-xs text-gray-500">
                          {preApproval.length} before approval,{' '}
                          {preDisb.length} before disbursement
                        </span>
                      )}
                      <button type="button" disabled={!canRecord || busy === id}
                              onClick={() => void act(a)}
                              className={`rounded-lg px-4 py-2 text-sm font-medium text-white ${
                                canRecord && busy !== id ? 'bg-[#0097A7]' : 'bg-gray-300'}`}>
                        {busy === id ? 'Recording…' : 'Record'}
                      </button>
                    </div>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
