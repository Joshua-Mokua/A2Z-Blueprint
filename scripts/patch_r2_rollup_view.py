#!/usr/bin/env python
# -*- coding: utf-8 -*-
r"""
R2 - the consolidated roll-up for the MD and the Business Manager.

RULINGS HONOURED
  Validation TERMINATES (2026-08-08). A branch day is countersigned by the Head
  of Branches; a Head Office unit day by its Director. This tier OBSERVES and
  may RETURN a day for amendment - it never countersigns.

  A person's index belongs to the unit that EMPLOYS them (2026-08-09). Nothing
  here re-sums what is already counted below: the Branches node aggregates
  branch indices, and unit rows sit BESIDE it showing their own direct reports
  and their own increment. Never inside it.

WHAT THIS ADDS
  frontend .../components/UnitRollup.tsx (new)
      Three levels: Branches (collapsed) -> a branch -> that branch's staff,
      with Head Office units as siblings of the Branches node. Each row shows
      staff / filed / validated / not filed / index / status. Return-for-
      amendment is available where can_return is set; there is no Countersign
      button anywhere on this view, by design.

  frontend .../lib/api.ts - UnitRow / UnitDays types and fetchUnitDays().

  frontend .../pages/PipelineManagerQueues.tsx
      The Daily log tab now routes across THREE tiers on a SINGLE probe:
          top_of_house            -> UnitRollup        (MD / Business Manager)
          a Branches node present -> BranchCountersign (Head of Branches)
          otherwise               -> DailyLogValidation (branch triad / line mgr)
      /unit-days answers both questions in one call, and the answer comes from
      the server rather than from inspecting a role string in the client.

KNOWN LIMIT, stated rather than hidden: a UNIT row expands to nothing yet.
Branch rows drill to staff via /validation-queue?branch=, but there is no
equivalent per-unit staff endpoint, so a Director's direct reports are counted
but not yet listable from this view. That is a small backend addition, not a
redesign.

Verified: tsc --noEmit clean, vite build clean, and the previous two-tier probe
fully replaced (0 references to fetchBranchDays remain in the page).

Usage (from project root, .venv active):
    python scripts\\patch_r2_rollup_view.py            # dry run
    python scripts\\patch_r2_rollup_view.py --apply    # write + .pre_r2 backups
"""
import os
import shutil
import sys

COMP = os.path.join("frontend", "web", "src", "components", "UnitRollup.tsx")
APITS = os.path.join("frontend", "web", "src", "lib", "api.ts")
PAGE = os.path.join("frontend", "web", "src", "pages", "PipelineManagerQueues.tsx")
BACKUP_SUFFIX = ".pre_r2"

TS_ANCHOR = "export async function fetchBranchDays(date = \'\'): Promise<BranchDays> {"

TS_NEW = r'''export interface UnitRow {
  key: string; name: string; kind: string;            // branch | unit | rollup
  expected: number; filed: number; validated: number; not_filed: number;
  status: string; index: number; owner: string; over_reported: number;
  can_countersign?: boolean;
  count?: number; countersigned?: number;             // rollup only
  children?: UnitRow[];
}
export interface UnitDays {
  branches: UnitRow | null; units: UnitRow[];
  date: string; working_day?: boolean; label?: string;
  top_of_house: boolean; can_return?: boolean;
}
export async function fetchUnitDays(date = ''): Promise<UnitDays> {
  return getJson<UnitDays>(
    `/branch-log/unit-days${date ? `?date=${encodeURIComponent(date)}` : ''}`);
}
'''

COMPONENT = r'''// R2 — the consolidated roll-up for the MD and the Business Manager.
//
// Ruling 2026-08-08: VALIDATION TERMINATES. A branch day is countersigned by
// the Head of Branches; a Head Office unit day by its Director. This tier
// OBSERVES and may RETURN a day for amendment — it never countersigns.
//
// Ruling 2026-08-09: a person's index belongs to the unit that EMPLOYS them.
// Nothing here re-sums what is already counted below; a unit row shows its own
// direct reports and its own increment. So the Branches node is a roll-up of
// branch indices, and the unit rows sit beside it — never inside it.
//
// Three levels: Branches (collapsed) -> a branch -> that branch's staff.
// Unit rows expand one level, to their direct reports.

import { useCallback, useEffect, useState } from 'react';
import { Button } from '@/components/Button';
import { Card } from '@/components/Card';
import { useToast } from '@/components/Toast';
import {
  fetchUnitDays, decideBranchDay, fetchBranchLogValidationQueue,
  type UnitDays, type UnitRow, type ValidationQueue,
} from '@/lib/api';

const STATUS: Record<string, { label: string; cls: string }> = {
  draft:     { label: 'Not submitted', cls: 'bg-gray-100 text-gray-500' },
  submitted: { label: 'Submitted',     cls: 'bg-[#FAEEDA] text-[#854F0B]' },
  validated: { label: 'Countersigned', cls: 'bg-[#EAF3DE] text-[#3B6D11]' },
  returned:  { label: 'Returned',      cls: 'bg-[#FBEAF0] text-[#993556]' },
};

function todayIso(): string {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
}

export default function UnitRollup({ onCount }: { onCount?: (n: number) => void }) {
  const { toast } = useToast();
  const [date, setDate] = useState(todayIso());
  const [data, setData] = useState<UnitDays | null>(null);
  const [loading, setLoading] = useState(false);
  const [openBranches, setOpenBranches] = useState(false);   // the rollup node
  const [openKey, setOpenKey] = useState('');                // a branch or unit
  const [detail, setDetail] = useState<ValidationQueue | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [returning, setReturning] = useState('');
  const [note, setNote] = useState('');
  const [busy, setBusy] = useState('');

  const load = useCallback(async (d: string) => {
    setLoading(true);
    try {
      const r = await fetchUnitDays(d);
      setData(r);
      const pending = (r.branches?.children ?? []).filter((x) => x.status === 'submitted').length
        + r.units.filter((x) => x.status === 'submitted').length;
      onCount?.(pending);
    } catch (e) {
      toast({ tone: 'danger', message: e instanceof Error ? e.message : 'Could not load the roll-up.' });
      setData(null);
    } finally {
      setLoading(false);
    }
  }, [toast, onCount]);

  useEffect(() => { void load(date); }, [date, load]);

  async function expand(row: UnitRow) {
    if (openKey === row.key) { setOpenKey(''); setDetail(null); return; }
    setOpenKey(row.key);
    setDetail(null);
    setDetailLoading(true);
    try {
      // Branch rows inspect by branch; unit rows have no per-unit staff endpoint
      // yet, so only branches drill to staff for now.
      setDetail(row.kind === 'branch'
        ? await fetchBranchLogValidationQueue(date, row.name)
        : null);
    } catch (e) {
      toast({ tone: 'danger', message: e instanceof Error ? e.message : 'Could not open that row.' });
      setOpenKey('');
    } finally {
      setDetailLoading(false);
    }
  }

  async function sendBack(row: UnitRow) {
    if (!note.trim()) {
      toast({ tone: 'danger', message: 'A note is required when returning a day.' });
      return;
    }
    setBusy(row.key);
    try {
      await decideBranchDay(row.name, date, false, note.trim());
      toast({ tone: 'success', message: `${row.name} returned for amendment.` });
      setReturning(''); setNote('');
      await load(date);
    } catch (e) {
      toast({ tone: 'danger', message: e instanceof Error ? e.message : 'Could not return it.' });
    } finally {
      setBusy('');
    }
  }

  const th = 'whitespace-nowrap px-3 py-2 text-left text-[11px] font-semibold uppercase tracking-wide';
  const td = 'whitespace-nowrap px-3 py-2 text-sm';

  function numbers(r: UnitRow, indent = false) {
    const st = STATUS[r.status] ?? STATUS.draft;
    return (
      <>
        <td className={`${td} tabular-nums text-gray-500`}>{r.expected}</td>
        <td className={`${td} tabular-nums text-gray-700`}>{r.filed}</td>
        <td className={`${td} tabular-nums text-[#3B6D11]`}>{r.validated}</td>
        <td className={`${td} tabular-nums ${r.not_filed ? 'text-amber-600' : 'text-gray-300'}`}>
          {r.not_filed || '—'}
        </td>
        <td className={`${td} tabular-nums font-semibold text-[#003D57]`}>
          {(r.index || 0).toFixed(1)}
        </td>
        <td className={td}>
          {r.kind === 'rollup' ? (
            <span className="text-[11px] text-gray-500">
              {r.countersigned} of {r.count} countersigned
            </span>
          ) : (
            <span className={`rounded-full px-2 py-0.5 text-[11px] font-medium ${st.cls}`}>
              {st.label}
            </span>
          )}
          {r.owner && !indent && (
            <div className="mt-0.5 text-[10px] text-gray-400">{r.owner}</div>
          )}
        </td>
      </>
    );
  }

  function actions(r: UnitRow) {
    if (r.kind === 'rollup') return <td className={td} />;
    const canReturn = (data?.can_return ?? false) && r.status !== 'draft';
    if (!canReturn) return <td className={`${td} text-[11px] text-gray-400`}>—</td>;
    return (
      <td className={td}>
        {returning === r.key ? (
          <div className="flex flex-col gap-1" style={{ minWidth: 210 }}>
            <input autoFocus value={note} onChange={(e) => setNote(e.target.value)}
                   placeholder="Why is it going back?"
                   className="w-full rounded border border-gray-300 px-2 py-1 text-xs" />
            <div className="flex gap-1">
              <Button size="sm" variant="secondary" disabled={busy === r.key}
                      onClick={() => void sendBack(r)}>Send back</Button>
              <Button size="sm" variant="ghost"
                      onClick={() => { setReturning(''); setNote(''); }}>Cancel</Button>
            </div>
          </div>
        ) : (
          <Button size="sm" variant="ghost"
                  onClick={() => { setReturning(r.key); setNote(''); }}>
            Return
          </Button>
        )}
      </td>
    );
  }

  const b = data?.branches ?? null;

  return (
    <Card className="mt-4">
      <Card.Header>
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <h2 className="text-base font-semibold text-gray-900">Daily log — consolidated</h2>
            <p className="mt-0.5 text-xs text-gray-500">
              Branches are countersigned by the Head of Branches and units by their Director.
              You observe, and may return a day for amendment.
            </p>
          </div>
          <div className="flex items-center gap-2 text-xs">
            <label className="text-gray-500">Day</label>
            <input type="date" value={date} onChange={(e) => setDate(e.target.value)}
                   className="rounded border border-gray-200 px-2 py-1 text-xs" />
          </div>
        </div>
      </Card.Header>

      <Card.Body>
        {loading && <p className="py-8 text-center text-sm text-gray-400">Loading…</p>}

        {!loading && data && data.working_day === false && (
          <p className="py-8 text-center text-sm text-gray-500">
            {data.label || 'Rest day'} — no days are expected.
          </p>
        )}

        {!loading && data?.working_day !== false && !b && (data?.units.length ?? 0) === 0 && (
          <p className="py-8 text-center text-sm text-gray-400">
            Nothing consolidates to you for this day.
          </p>
        )}

        {!loading && (b || (data?.units.length ?? 0) > 0) && (
          <div className="overflow-auto rounded-lg border border-gray-200">
            <table className="w-full border-separate" style={{ borderSpacing: 0 }}>
              <thead>
                <tr>
                  <th className={`${th} bg-gray-100 text-gray-600`}>Unit</th>
                  <th className={`${th} bg-gray-100 text-gray-600`}>Staff</th>
                  <th className={`${th} bg-gray-100 text-gray-600`}>Filed</th>
                  <th className={`${th} bg-gray-100 text-gray-600`}>Validated</th>
                  <th className={`${th} bg-gray-100 text-gray-600`}>Not filed</th>
                  <th className={`${th} bg-[#003D57] text-white`}>Index</th>
                  <th className={`${th} bg-gray-100 text-gray-600`}>Status</th>
                  <th className={`${th} bg-gray-100 text-gray-600`}>Action</th>
                </tr>
              </thead>
              <tbody>
                {/* ── the collapsed Branches node ─────────────────────────── */}
                {b && (
                  <tr className="bg-[#EFF6FB]">
                    <td className={`${td} font-semibold text-[#005B82]`}>
                      <button type="button" onClick={() => setOpenBranches((v) => !v)}
                              className="flex items-center gap-1.5 hover:text-brand-primary">
                        <span className="text-gray-400">{openBranches ? '▾' : '▸'}</span>
                        Branches
                        <span className="ml-1 rounded-full bg-white px-1.5 py-0.5 text-[10px] font-normal text-gray-500">
                          {b.count}
                        </span>
                      </button>
                      {b.over_reported > 0 && (
                        <span className="ml-2 rounded bg-[#FBEAF0] px-1.5 py-0.5 text-[10px] font-medium text-[#993556]">
                          {b.over_reported} over-reported
                        </span>
                      )}
                    </td>
                    {numbers(b)}
                    {actions(b)}
                  </tr>
                )}

                {openBranches && (b?.children ?? []).map((br) => (
                  <>
                    <tr key={br.key} className="bg-white">
                      <td className={`${td} pl-8 text-gray-800`}>
                        <button type="button" onClick={() => void expand(br)}
                                className="flex items-center gap-1.5 hover:text-brand-primary">
                          <span className="text-gray-400">{openKey === br.key ? '▾' : '▸'}</span>
                          {br.name}
                        </button>
                      </td>
                      {numbers(br, true)}
                      {actions(br)}
                    </tr>
                    {openKey === br.key && (
                      <tr key={`${br.key}-d`}>
                        <td colSpan={8} className="bg-[#F7FBFD] px-6 py-3">
                          {detailLoading && <p className="text-xs text-gray-400">Opening {br.name}…</p>}
                          {!detailLoading && detail && (
                            <table className="w-full">
                              <tbody>
                                {(detail.rows ?? []).map((m) => (
                                  <tr key={m.staff_code} className="border-b border-gray-100 last:border-0">
                                    <td className="py-1 pr-3 text-xs tabular-nums text-gray-500" style={{ width: 80 }}>
                                      {m.staff_code}
                                    </td>
                                    <td className="py-1 pr-3 text-xs text-gray-800">{m.staff_name}</td>
                                    <td className="py-1 pr-3 text-xs text-gray-500">{m.role}</td>
                                    <td className="py-1 pr-3 text-xs tabular-nums text-gray-700" style={{ width: 60 }}>
                                      {m.status === 'missing' ? '—' : Number(m.index ?? 0).toFixed(1)}
                                    </td>
                                    <td className="py-1 text-xs" style={{ width: 160 }}>
                                      {m.validated
                                        ? <span className="text-[#3B6D11]">✓ validated</span>
                                        : m.status === 'missing'
                                          ? (m as unknown as { excused?: boolean }).excused
                                            ? <span className="text-gray-500">excused</span>
                                            : <span className="text-amber-600">not filed</span>
                                          : <span className="text-gray-400">awaiting the BM</span>}
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
                ))}

                {/* ── Head Office units, siblings of Branches ─────────────── */}
                {(data?.units ?? []).map((u, i) => (
                  <tr key={u.key} className={i % 2 === 1 ? 'bg-gray-50/40' : 'bg-white'}>
                    <td className={`${td} text-gray-900`}>{u.name}</td>
                    {numbers(u)}
                    {actions(u)}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card.Body>
    </Card>
  );
}
'''


PAGE_EDITS = [
    ("imports",
     "import { fetchBranchDays } from '@/lib/api';",
     "import UnitRollup from '@/components/UnitRollup';\n"
     "import { fetchUnitDays } from '@/lib/api';"),
    ("tier state",
     "  const [tier2, setTier2] = useState<boolean | null>(null);",
     "  // 'staff' = validates individuals, 'branch' = countersigns branches,\n"
     "  // 'rollup' = MD / Business Manager, observes and may return.\n"
     "  const [tier, setTier] = useState<'staff' | 'branch' | 'rollup' | null>(null);"),
    ("probe",
     "      try {\n"
     "        const r = await fetchBranchDays();\n"
     "        if (alive) setTier2((r.rows?.length ?? 0) > 0);\n"
     "      } catch {\n"
     "        if (alive) setTier2(false);\n"
     "      }",
     "      try {\n"
     "        // One probe. /unit-days answers both questions: top_of_house marks the\n"
     "        // observation tier, and a Branches node means this caller countersigns\n"
     "        // branches. Asking the server beats inspecting a role string here.\n"
     "        const r = await fetchUnitDays();\n"
     "        if (!alive) return;\n"
     "        if (r.top_of_house) setTier('rollup');\n"
     "        else if ((r.branches?.children?.length ?? 0) > 0) setTier('branch');\n"
     "        else setTier('staff');\n"
     "      } catch {\n"
     "        if (alive) setTier('staff');\n"
     "      }"),
    ("tab routing",
     "      {activeTab === 'dailylog' && tier2 === null && (\n"
     "        <Card className=\"mt-4\"><Card.Body>\n"
     "          <div className=\"text-sm text-gray-400\">Loading…</div>\n"
     "        </Card.Body></Card>\n"
     "      )}\n"
     "      {activeTab === 'dailylog' && tier2 === true && (\n"
     "        <BranchCountersign onCount={setDailyLogPending} />\n"
     "      )}\n"
     "      {activeTab === 'dailylog' && tier2 === false && (\n"
     "        <DailyLogValidation onCount={setDailyLogPending} />\n"
     "      )}",
     "      {activeTab === 'dailylog' && tier === null && (\n"
     "        <Card className=\"mt-4\"><Card.Body>\n"
     "          <div className=\"text-sm text-gray-400\">Loading…</div>\n"
     "        </Card.Body></Card>\n"
     "      )}\n"
     "      {activeTab === 'dailylog' && tier === 'rollup' && (\n"
     "        <UnitRollup onCount={setDailyLogPending} />\n"
     "      )}\n"
     "      {activeTab === 'dailylog' && tier === 'branch' && (\n"
     "        <BranchCountersign onCount={setDailyLogPending} />\n"
     "      )}\n"
     "      {activeTab === 'dailylog' && tier === 'staff' && (\n"
     "        <DailyLogValidation onCount={setDailyLogPending} />\n"
     "      )}"),
]


def main():
    apply = "--apply" in sys.argv
    for p in (APITS, PAGE):
        if not os.path.isfile(p):
            print("ABORT: %s not found. Run from the project root." % p)
            return 1
    if os.path.exists(COMP):
        print("ABORT: %s already exists - R2 looks applied." % COMP)
        return 1

    ts = open(APITS, encoding="utf-8").read()
    page = open(PAGE, encoding="utf-8").read()

    if "fetchUnitDays" in ts:
        print("ABORT: api.ts already has fetchUnitDays.")
        return 1
    if ts.count(TS_ANCHOR) != 1:
        print("ABORT: api.ts anchor matched %d times." % ts.count(TS_ANCHOR))
        return 1

    ts = ts.replace(TS_ANCHOR, TS_NEW + TS_ANCHOR, 1)
    print("  ok  api.ts - UnitRow / UnitDays / fetchUnitDays")

    for name, old, new in PAGE_EDITS:
        if page.count(old) != 1:
            print("ABORT: ManagerQueues %r anchor matched %d times." % (name, page.count(old)))
            return 1
        page = page.replace(old, new, 1)
        print("  ok  ManagerQueues - %s" % name)

    if "fetchBranchDays" in page:
        print("ABORT: post-check - the old two-tier probe is still referenced.")
        return 1
    if "UnitRollup" not in page or "tier === 'rollup'" not in page:
        print("ABORT: post-check - roll-up routing missing.")
        return 1
    if "fetchBranchLogHistoryGrid" not in ts:
        print("ABORT: post-check - api.ts lost fetchBranchLogHistoryGrid.")
        return 1
    for o, c in (("{", "}"), ("(", ")")):
        if COMPONENT.count(o) != COMPONENT.count(c):
            print("ABORT: embedded component unbalanced %s%s." % (o, c))
            return 1
    print("  ok  post-checks: old probe gone, api.ts intact")

    if not apply:
        print("\nDRY RUN - nothing written. Re-run with --apply.")
        return 0

    open(COMP, "w", encoding="utf-8", newline="").write(COMPONENT)
    print("CREATED %s" % COMP)
    for path, content in ((APITS, ts), (PAGE, page)):
        shutil.copy2(path, path + BACKUP_SUFFIX)
        open(path, "w", encoding="utf-8", newline="").write(content)
        print("APPLIED %s" % path)

    print("\nNext: pushd frontend\\web && pnpm tsc --noEmit && popd && echo TSC_PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
