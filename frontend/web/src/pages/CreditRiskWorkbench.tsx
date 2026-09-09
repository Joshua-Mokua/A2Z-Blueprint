// ── CREDIT RISK WORKBENCH ─────────────────────────────────────────────────────
// RULING (2026-08-18): "I want his sidebar not to have the Department Review,
// since that one does not really concern them - the CIS is their main
// workbench."
//
// Credit Analysis and Department Review both pointed at /lms, so credit risk
// and the segment analysts shared one screen. That screen is the segment
// analyst's desk: claim from the pool, request documents, return for rework,
// mark ready for committee. None of it is credit risk's job, and the noise of
// it hid the cases that were.
//
// This is the other half of that ruling. It lists ONLY cases a committee has
// recommended, and offers only the decision credit risk exists to make.
import { useCallback, useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { fetchLmsApplications, recordLmsDecision } from '@/lib/api';
import type { LoanApplication } from '@/types/lms';

// What a committee recommendation looks like once CS2 has written it. The old
// spelling is accepted so a case marked before the rename still appears.
const READY = ['committee_recommended', 'committee_approved'];

function money(v?: number, ccy?: string) {
  if (v === undefined || v === null) return '—';
  return `${ccy ?? 'KES'} ${Number(v).toLocaleString()}`;
}

export function CreditRiskWorkbench() {
  const navigate = useNavigate();
  const [apps, setApps] = useState<LoanApplication[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [open, setOpen] = useState<string | null>(null);
  const [verdict, setVerdict] = useState<'approved' | 'declined' | 'returned'>('approved');
  const [reason, setReason] = useState('');

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetchLmsApplications();
      setApps(res?.applications ?? []);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not load the cases.');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { void load(); }, [load]);

  // Only what a committee has recommended. Everything earlier belongs to the
  // segment analyst and appears on Department Review.
  const mine = useMemo(
    () => apps.filter((a) => READY.includes(String(a.status ?? '').toLowerCase())),
    [apps],
  );

  async function decide(appId: string) {
    if (reason.trim().length < 5) return;
    setBusy(appId);
    try {
      await recordLmsDecision(appId, {
        verdict,
        authority: 'Credit Risk',
        reason: reason.trim(),
      });
      setOpen(null);
      setReason('');
      await load();
    } catch (e) {
      // The server's refusal says something useful - show it rather than a
      // generic failure.
      setError(e instanceof Error ? e.message : 'Could not record the decision.');
    } finally {
      setBusy(null);
    }
  }

  return (
    <div className="p-6">
      <h1 className="text-xl font-semibold text-[#003D57]">Credit Risk</h1>
      <p className="mt-1 text-sm text-gray-600">
        Cases a committee has recommended, waiting on your decision. Work still
        with the department analysts is on Department Review.
      </p>

      <div className="mt-4 flex gap-4">
        <div className="rounded-lg border bg-white px-5 py-3">
          <div className="text-xs uppercase tracking-wide text-gray-500">Awaiting you</div>
          <div className="text-2xl font-semibold">{mine.length}</div>
        </div>
        <div className="rounded-lg border bg-white px-5 py-3">
          <div className="text-xs uppercase tracking-wide text-gray-500">Their value</div>
          <div className="text-2xl font-semibold">
            {money(mine.reduce((t, a) => t + (Number(a.amount) || 0), 0))}
          </div>
        </div>
        <button type="button" onClick={() => void load()}
                className="ml-auto self-center rounded-lg border px-4 py-2 text-sm">
          Refresh
        </button>
      </div>

      {error && (
        <div className="mt-4 rounded-lg border border-red-300 bg-red-50 p-3 text-sm text-red-800">
          {error}
        </div>
      )}

      {loading ? (
        <p className="mt-8 text-center text-gray-500">Loading…</p>
      ) : mine.length === 0 ? (
        <div className="mt-8 rounded-lg border bg-white p-10 text-center">
          <p className="text-gray-700">Nothing is waiting on you.</p>
          <p className="mt-1 text-sm text-gray-500">
            A case arrives here once its committee has recommended it. Until
            then it sits with the department analyst.
          </p>
        </div>
      ) : (
        <div className="mt-4 overflow-hidden rounded-lg border bg-white">
          <table className="w-full text-sm">
            <thead className="bg-gray-50 text-left text-xs uppercase tracking-wide text-gray-500">
              <tr>
                <th className="px-4 py-3">Case</th>
                <th className="px-4 py-3">Client</th>
                <th className="px-4 py-3">Product</th>
                <th className="px-4 py-3 text-right">Amount</th>
                <th className="px-4 py-3">Recommended by</th>
                <th className="px-4 py-3"></th>
              </tr>
            </thead>
            <tbody>
              {mine.map((a) => {
                const id = String(a.id);
                return (
                  <>
                    <tr key={id} className="border-t">
                      <td className="px-4 py-3 font-mono text-xs">{id}</td>
                      <td className="px-4 py-3">{a.client_name}</td>
                      <td className="px-4 py-3">{a.product ?? '—'}</td>
                      <td className="px-4 py-3 text-right">{money(a.amount, a.currency)}</td>
                      <td className="px-4 py-3 text-gray-600">
                        {String((a as { committee_recommended_by?: string })
                          .committee_recommended_by ?? '—')}
                      </td>
                      <td className="px-4 py-3 text-right">
                        <button type="button"
                                onClick={() => navigate(`/lms/${encodeURIComponent(id)}`)}
                                className="mr-2 rounded border px-3 py-1 text-xs">
                          Open
                        </button>
                        <button type="button"
                                onClick={() => { setOpen(open === id ? null : id); setReason(''); }}
                                className="rounded bg-[#0097A7] px-3 py-1 text-xs font-medium text-white">
                          Decide
                        </button>
                      </td>
                    </tr>
                    {open === id && (
                      <tr key={`${id}-decide`} className="border-t bg-gray-50">
                        <td colSpan={6} className="px-4 py-4">
                          <div className="flex flex-wrap items-end gap-3">
                            <div>
                              <label className="block text-xs font-medium text-gray-700">Decision</label>
                              <select className="mt-1 rounded-lg border px-3 py-2"
                                      value={verdict}
                                      onChange={(e) => setVerdict(e.target.value as typeof verdict)}>
                                <option value="approved">Approve</option>
                                <option value="declined">Decline</option>
                                <option value="returned">Return for rework</option>
                              </select>
                            </div>
                            <div className="min-w-[22rem] flex-1">
                              <label className="block text-xs font-medium text-gray-700">
                                Reason — this goes on the case
                              </label>
                              <input className="mt-1 w-full rounded-lg border px-3 py-2"
                                     value={reason}
                                     onChange={(e) => setReason(e.target.value)}
                                     placeholder="What decided it" />
                            </div>
                            <button type="button"
                                    disabled={reason.trim().length < 5 || busy === id}
                                    onClick={() => void decide(id)}
                                    className={`rounded-lg px-4 py-2 text-sm font-medium text-white
                                      ${reason.trim().length >= 5 && busy !== id
                                        ? 'bg-[#0097A7]' : 'bg-gray-300'}`}>
                              {busy === id ? 'Recording…' : 'Record'}
                            </button>
                          </div>
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
    </div>
  );
}
