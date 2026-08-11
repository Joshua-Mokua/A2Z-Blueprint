// Events — what each sponsorship cost, and what the deals say it produced.
//
// The point of tagging deals to an event is to answer one question honestly:
// was it worth it? So this shows spend against DERIVED leads and accounts —
// counted from deals, with accounts counted only after closure — beside the
// stored figures, rather than replacing them.
//
// When derived is far below stored, that usually means nobody tagged their
// deals to the event rather than that the event failed. Saying so on screen is
// better than letting someone read a red number as a verdict.

import { useCallback, useEffect, useState } from 'react';
import { Card } from '@/components/Card';
import { PageHeader } from '@/components/PageHeader';
import { useToast } from '@/components/Toast';
import { fetchPipelineEvents, type PipelineEvent } from '@/lib/api';

function kes(n: number | null | undefined): string {
  const v = Number(n ?? 0);
  if (!v) return '—';
  return Math.round(v).toLocaleString();
}

function pct(a: number, b: number | null | undefined): number {
  const t = Number(b ?? 0);
  return t > 0 ? Math.round((a / t) * 100) : 0;
}

export default function Events() {
  const { toast } = useToast();
  const [rows, setRows] = useState<PipelineEvent[]>([]);
  const [tagged, setTagged] = useState(0);
  const [loading, setLoading] = useState(false);
  const [activeOnly, setActiveOnly] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const r = await fetchPipelineEvents(activeOnly);
      setRows(r.events ?? []);
      setTagged(r.tagged_deals ?? 0);
    } catch (e) {
      toast({ tone: 'danger', message: e instanceof Error ? e.message : 'Could not load events.' });
      setRows([]);
    } finally {
      setLoading(false);
    }
  }, [activeOnly, toast]);

  useEffect(() => { void load(); }, [load]);

  const th = 'whitespace-nowrap px-3 py-2 text-left text-[11px] font-semibold uppercase tracking-wide';
  const td = 'whitespace-nowrap px-3 py-2 text-sm';

  return (
    <>
      <PageHeader
        ribbon
        breadcrumbs={[{ label: 'Pipeline Intelligence (PIS)' }, { label: 'Events' }]}
        title="Events"
      />
      <div className="mx-auto max-w-7xl p-6">
        <Card>
          <Card.Header>
            <div className="flex flex-wrap items-center justify-between gap-3">
              <h2 className="text-base font-semibold text-gray-900">Sponsored events</h2>
              <div className="flex items-center gap-3 text-xs">
                <label className="flex items-center gap-1.5 text-gray-600">
                  <input type="checkbox" checked={activeOnly}
                         onChange={(e) => setActiveOnly(e.target.checked)} />
                  Active only
                </label>
                <span className="rounded-full bg-[#E6F1FB] px-2.5 py-1 text-[#0C447C]">
                  {tagged} deal{tagged === 1 ? '' : 's'} tagged
                </span>
              </div>
            </div>
          </Card.Header>
          <Card.Body>
            {loading && <p className="py-8 text-center text-sm text-gray-400">Loading…</p>}

            {!loading && rows.length === 0 && (
              <p className="py-8 text-center text-sm text-gray-400">No events.</p>
            )}

            {!loading && rows.length > 0 && tagged === 0 && (
              <p className="mb-3 rounded-lg border border-[#FAEEDA] bg-[#FEFAF3] px-3 py-2 text-xs text-[#854F0B]">
                No deals are tagged to any event yet, so every derived figure below
                is zero. Choose “Events” on the deal capture form and pick the
                event to start attributing.
              </p>
            )}

            {!loading && rows.length > 0 && (
              <div className="overflow-auto rounded-lg border border-gray-200">
                <table className="w-full border-separate" style={{ borderSpacing: 0 }}>
                  <thead>
                    <tr>
                      <th className={`${th} bg-gray-100 text-gray-600`}>Event</th>
                      <th className={`${th} bg-gray-100 text-gray-600`}>Where</th>
                      <th className={`${th} bg-gray-100 text-gray-600`}>When</th>
                      <th className={`${th} bg-gray-100 text-right text-gray-600`}>Spent (KES)</th>
                      <th className={`${th} bg-[#0082BB] text-right text-white`}>Leads</th>
                      <th className={`${th} bg-[#0082BB] text-right text-white`}>Accounts</th>
                      <th className={`${th} bg-gray-100 text-right text-gray-600`}>Won value (KES)</th>
                      <th className={`${th} bg-gray-100 text-right text-gray-600`}>Return</th>
                    </tr>
                  </thead>
                  <tbody>
                    {rows.map((e, i) => {
                      const bg = i % 2 === 1 ? 'bg-gray-50/40' : 'bg-white';
                      const lp = pct(e.derived_leads, e.target_leads);
                      const ap = pct(e.derived_accounts, e.target_accounts);
                      return (
                        <tr key={e.id}>
                          <td className={`${td} ${bg} font-medium text-gray-900`}>
                            <div className="truncate" style={{ maxWidth: 280 }} title={e.name}>
                              {e.name}
                            </div>
                            {e.partner && (
                              <div className="text-[10px] text-gray-400">{e.partner}</div>
                            )}
                          </td>
                          <td className={`${td} ${bg} text-gray-600`}>{e.branch}</td>
                          <td className={`${td} ${bg} text-gray-500`}>
                            {String(e.start_date ?? '').slice(0, 10)}
                            <div className="text-[10px] text-gray-400">{e.status}</div>
                          </td>
                          <td className={`${td} ${bg} text-right tabular-nums text-gray-700`}>
                            {kes(e.spent_kes)}
                          </td>
                          <td className={`${td} ${bg} text-right tabular-nums`}>
                            <span className="font-semibold text-gray-900">{e.derived_leads}</span>
                            <span className="ml-1 text-[10px] text-gray-400">
                              / {e.target_leads ?? '—'}{e.target_leads ? ` · ${lp}%` : ''}
                            </span>
                          </td>
                          <td className={`${td} ${bg} text-right tabular-nums`}>
                            <span className="font-semibold text-[#3B6D11]">{e.derived_accounts}</span>
                            <span className="ml-1 text-[10px] text-gray-400">
                              / {e.target_accounts ?? '—'}{e.target_accounts ? ` · ${ap}%` : ''}
                            </span>
                          </td>
                          <td className={`${td} ${bg} text-right font-semibold tabular-nums text-[#003D57]`}>
                            {kes(e.derived_value)}
                          </td>
                          <td className={`${td} ${bg} text-right tabular-nums`}>
                            {e.derived_roi_pct === null || e.derived_roi_pct === undefined ? (
                              <span className="text-gray-300">—</span>
                            ) : (
                              <span className={e.derived_roi_pct >= 0 ? 'text-[#3B6D11]' : 'text-rose-600'}>
                                {e.derived_roi_pct}%
                              </span>
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
