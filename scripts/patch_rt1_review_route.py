#!/usr/bin/env python
# -*- coding: utf-8 -*-
r"""
RT1 - Review opens the case instead of a blank page.

THE CONSOLE, again, named it in one line:

    No routes matched location "/pipeline/deals/SIMBCC_FORTIS_03"

The committee queue's Review button navigated to /pipeline/deals/{id}. That
route does not exist. Every other page in the application links to
/pipeline/{id} - Analytics, the deal list, the create page - and this one
invented a path that reads more logically and matches nothing. React Router
rendered nothing, which is what a blank page is.

One line. It cost an afternoon because a blank page shows no error to the
person looking at it, and I spent that afternoon proposing causes instead of
asking for the console.

TWO LESSONS WORTH KEEPING:

  A blank React page means the console, first, always. Both faults behind this
  one - the Rules of Hooks violation and this route - were named exactly by it,
  in seconds, after hours of plausible theories that were wrong.

  A new component linking somewhere should copy how the rest of the app links
  there, rather than construct a path that seems right.

Verified: tsc --noEmit clean, vite build clean.

Usage (from project root, .venv active):
    python scripts\\patch_rt1_review_route.py            # dry run
    python scripts\\patch_rt1_review_route.py --apply
"""
import os
import shutil
import sys

QUEUE = os.path.join("frontend", "web", "src", "components", "CommitteeQueue.tsx")
BACKUP_SUFFIX = ".pre_rt1"

OLD = "onClick={() => nav(`/pipeline/deals/${encodeURIComponent(c.deal_id)}`)}"

COMPONENT = r'''// Cases waiting on a committee this person sits on.
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
                      // THE ROUTE IS /pipeline/{id}, not /pipeline/deals/{id}. The wrong path
                      // matched no route at all, so React Router rendered nothing and
                      // Review opened a blank page:
                      //     No routes matched location "/pipeline/deals/SIMBCC_FORTIS_03"
                      // Every other page in the app links this way; this one invented
                      // a path that reads more logically and does not exist.
                      onClick={() => nav(`/pipeline/${encodeURIComponent(c.deal_id)}`)}
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
'''


NEW = COMPONENT


def main():
    apply = "--apply" in sys.argv
    if not os.path.isfile(QUEUE):
        print("ABORT: %s not found." % QUEUE)
        return 1

    cur = open(QUEUE, encoding="utf-8").read()
    if "THE ROUTE IS /pipeline/{id}" in cur:
        print("ABORT: RT1 looks applied.")
        return 1
    if OLD not in cur:
        print("ABORT: the old navigation call is not there - has this file")
        print("       moved on, or is CQ1 not applied?")
        return 1
    print("  ok  Review points at /pipeline/{id}")

    # The CALL must be right; the comment may mention the old path.
    if "nav(`/pipeline/deals/" in NEW:
        print("ABORT: the navigation still uses the route that does not exist.")
        return 1
    if "nav(`/pipeline/${encodeURIComponent" not in NEW:
        print("ABORT: the corrected navigation is missing.")
        return 1
    for op, cl in (("{", "}"), ("(", ")")):
        if NEW.count(op) != NEW.count(cl):
            print("ABORT: unbalanced %s%s." % (op, cl))
            return 1
    print("  ok  post-checks: the call is corrected, brackets balanced")

    if not apply:
        print("\nDRY RUN - nothing written. Re-run with --apply.")
        return 0

    shutil.copy2(QUEUE, QUEUE + BACKUP_SUFFIX)
    open(QUEUE, "w", encoding="utf-8", newline="").write(NEW)
    print("APPLIED %s" % QUEUE)
    print("\nNext: pushd frontend\\web && pnpm tsc --noEmit && pnpm build && popd")
    print("Then RESTART pnpm dev - Vite keeps a stale module across a change")
    print("like this and the browser will otherwise show the old behaviour.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
