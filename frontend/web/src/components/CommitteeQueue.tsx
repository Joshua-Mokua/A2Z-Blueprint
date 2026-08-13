// Cases waiting on a committee this person sits on.
//
// RULING (2026-08-12): the branch managers were gathered and nothing moved.
// Once the committees existed, the reason it still would not have moved is
// that MEMBERS HAD NOWHERE TO LOOK - a decision could only be recorded by
// knowing a deal id and opening it. A committee that cannot find its own cases
// is not a committee.
//
// NO NEW SIDEBAR ENTRY (ruling: "I am avoiding too many side bars"). This
// mounts inside Manager Queues for managers and inside the Daily Log for
// everybody else, so a committee member meets it where they already work.
//
// Review takes them to the deal, where the committee panel already lives -
// rather than building a second decision surface that could drift from it.
import { useCallback, useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { fetchCommitteeQueue, type CommitteeQueueResponse } from '@/lib/api';

export function CommitteeQueue({ compact = false }: { compact?: boolean }) {
  const nav = useNavigate();
  const [data, setData] = useState<CommitteeQueueResponse | null>(null);
  const [loading, setLoading] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      setData(await fetchCommitteeQueue());
    } catch {
      setData(null);
    } finally {
      setLoading(false);
    }
  }, []);
  useEffect(() => { void load(); }, [load]);

  // Somebody on no committee sees nothing at all - an empty panel headed
  // "Committee" would only make them wonder what they were missing.
  if (!loading && (!data || data.committees.length === 0)) return null;

  const kes = (n?: number) => (n == null ? "\u2014" : n.toLocaleString());

  return (
    <div className={compact ? 'mt-4' : ''}>
      <div className="mb-2 flex flex-wrap items-baseline justify-between gap-2">
        <div>
          <h2 className="text-base font-semibold text-gray-900">
            Awaiting your committee
          </h2>
          <p className="text-xs text-gray-500">
            {(data?.committees ?? []).map((c) => c.name).join(' \u00b7 ')}
          </p>
        </div>
        <button type="button" onClick={() => void load()}
                className="text-xs text-gray-500 hover:text-gray-800">
          Refresh
        </button>
      </div>

      {loading && (
        <p className="py-6 text-center text-sm text-gray-400">Loading\u2026</p>
      )}

      {!loading && (data?.cases.length ?? 0) === 0 && (
        <p className="rounded-lg border border-gray-200 bg-gray-50/60 py-6 text-center text-sm text-gray-500">
          Nothing waiting on your committee.
        </p>
      )}

      {!loading && (data?.cases.length ?? 0) > 0 && (
        <div className="overflow-hidden rounded-lg border border-gray-200">
          <table className="w-full text-sm">
            <thead className="bg-gray-50 text-left text-[11px] uppercase tracking-wide text-gray-500">
              <tr>
                <th className="px-3 py-2">Client</th>
                <th className="px-3 py-2">Product</th>
                <th className="px-3 py-2 text-right">Value</th>
                <th className="px-3 py-2">Owner</th>
                <th className="px-3 py-2">Committee</th>
                <th className="px-3 py-2" />
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {(data?.cases ?? []).map((c) => (
                <tr key={c.deal_id} className="hover:bg-gray-50/60">
                  <td className="px-3 py-2 font-medium text-gray-900">
                    {c.client_name}
                    <span className="ml-2 text-[11px] text-gray-400">{c.deal_id}</span>
                  </td>
                  <td className="px-3 py-2 text-gray-700">{c.product}</td>
                  <td className="px-3 py-2 text-right tabular-nums text-gray-700">
                    {c.currency} {kes(c.deal_value)}
                  </td>
                  <td className="px-3 py-2 text-gray-600">{c.owner}</td>
                  <td className="px-3 py-2 text-[11px] text-gray-500">
                    {(c.awaiting_names ?? []).join(', ')}
                  </td>
                  <td className="px-3 py-2 text-right">
                    <button
                      type="button"
                      onClick={() => nav(`/pipeline/deals/${encodeURIComponent(c.deal_id)}`)}
                      className="rounded-md bg-brand-primary px-3 py-1.5 text-xs font-semibold text-white hover:opacity-90"
                    >
                      Review
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
