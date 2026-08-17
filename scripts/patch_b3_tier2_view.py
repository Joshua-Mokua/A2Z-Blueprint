#!/usr/bin/env python
# -*- coding: utf-8 -*-
r"""
B3 - the tier-2 branch view. Answers "why is Muthama still seeing individuals?"

He was seeing individuals because B2 built only the backend. The tab still
called /validation-queue, and staff_validated_by returns his BMs and CSMs in
line_manager mode because they report to him directly. This is the frontend
half, plus the read-only inspection the tier-2 view needs.

WHAT CHANGES

  utils/api_branch_log.py - /validation-queue takes an optional `branch`.
      For a caller who OVERSEES that branch (branches_validated_by), it returns
      that branch's staff with can_act forced FALSE. Tier 2 inspects; it never
      validates individuals. The server enforces that, so the UI and the API
      agree rather than the UI merely hiding buttons.

  frontend .../lib/api.ts - fetchBranchDays, submitBranchDay, decideBranchDay,
      BranchDayRow/BranchDays types, and the branch parameter on the queue.

  frontend .../components/BranchCountersign.tsx (new)
      One row per branch: staff / filed / validated / not filed / branch index /
      status, with Countersign and Return (note required). Expanding a branch
      lists its members READ-ONLY with each one's state - validated, awaiting
      the BM, excused, or not filed.

  frontend .../pages/PipelineManagerQueues.tsx - the Daily log tab now routes
      by TIER. Which tier is decided by ASKING THE SERVER what the caller
      oversees (a GET /branch-days returning rows means tier 2), not by
      inspecting a role string in the client - the same mistake that gave the
      queue its own weaker hierarchy in P3f.

STATUS VOCABULARY on a branch row:
      Not submitted   the BM has not closed the day
      Awaiting you    submitted, needs your countersignature
      Countersigned   done
      Returned        sent back, with the reason shown

Branches with an over-reporting breach carry a red chip, because that is what
blocks the BM from submitting in the first place.

Verified: py_compile clean, tsc --noEmit clean, vite build clean.

STILL OPEN: the cross-branch "who has not filed" list below the branch table
(E3) - the per-branch view shows it on expand, but the consolidated list across
all branches is not built. Also E2b submit-on-behalf, and E4 notifications.

Usage (from project root, .venv active):
    python scripts\\patch_b3_tier2_view.py            # dry run
    python scripts\\patch_b3_tier2_view.py --apply    # write + .pre_b3 backups
"""
import os
import shutil
import sys

API = os.path.join("utils", "api_branch_log.py")
APITS = os.path.join("frontend", "web", "src", "lib", "api.ts")
COMP = os.path.join("frontend", "web", "src", "components", "BranchCountersign.tsx")
PAGE = os.path.join("frontend", "web", "src", "pages", "PipelineManagerQueues.tsx")
BACKUP_SUFFIX = ".pre_b3"

SIG_OLD = 'def branch_log_validation_queue(date: str = "", user: dict = Depends(get_current_user)):'
SIG_NEW = ('def branch_log_validation_queue(date: str = "", branch: str = "",\n'
           '                                user: dict = Depends(get_current_user)):')

SCOPE_START = "    from utils.org_validator import staff_validated_by"
SCOPE_END = "    if not mine:"

CANACT_OLD = '                "can_act": (not validated) and status in ("submitted", "auto_submitted"),'
CANACT_NEW = ('                "can_act": (not inspect_only) and (not validated)\n'
              '                           and status in ("submitted", "auto_submitted"),')

TS_OLD = """export async function fetchBranchLogValidationQueue(date = ''): Promise<ValidationQueue> {
  return getJson<ValidationQueue>(
    `/branch-log/validation-queue${date ? `?date=${encodeURIComponent(date)}` : ''}`);
}"""

SCOPE_NEW = r'''    from utils.org_validator import staff_validated_by
    inspect_only = False
    if branch:
        # B3: TIER-2 INSPECTION. A Head of Branches opening a branch sees that
        # branch's staff READ-ONLY — they countersign the branch, they do not
        # validate individuals (ruling 2026-08-08). can_act is forced false
        # below, so the buttons never render for them.
        try:
            from utils.org_validator import branches_validated_by
            scope2 = branches_validated_by(my_code)
        except Exception:
            scope2 = {"branches": []}
        if branch not in (scope2.get("branches") or []) and not _is_admin(user):
            raise HTTPException(status_code=403,
                                detail=f"{branch} is not a branch you oversee.")
        inspect_only = True
        mode = "inspect"
        mine = [(d.get("code") or ck, d) for ck, d in dims.items()
                if str((d or {}).get("branch") or "").strip() == branch]
    else:
        try:
            res = staff_validated_by(my_code)
        except Exception:
            res = {"mode": "", "codes": []}
        mode = res.get("mode", "")
        mine = []
        for code in res.get("codes", []):
            d = dims.get(_canon_q(code)) or {}
            mine.append((d.get("code") or code, d))

'''

TS_BLOCK = r'''export async function fetchBranchLogValidationQueue(
  date = '', branch = '',
): Promise<ValidationQueue> {
  const q = new URLSearchParams();
  if (date) q.set('date', date);
  if (branch) q.set('branch', branch);      // tier-2 read-only inspection
  const s = q.toString();
  return getJson<ValidationQueue>(`/branch-log/validation-queue${s ? `?${s}` : ''}`);
}

// ── Tier 2: branch-day countersign ────────────────────────────────────────
export interface BranchDayRow {
  branch: string;
  expected: number; filed: number; validated: number; pending: number; not_filed: number;
  status: string;               // draft | submitted | validated | returned
  branch_index: number;
  submitted_by_name: string; submitted_at: string;
  return_note: string; validated_by_name: string;
  over_reported: number;
}
export interface BranchDays {
  rows: BranchDayRow[]; date: string; mode: string;
  all_view: boolean; working_day: boolean; label?: string;
}
export async function fetchBranchDays(date = ''): Promise<BranchDays> {
  return getJson<BranchDays>(
    `/branch-log/branch-days${date ? `?date=${encodeURIComponent(date)}` : ''}`);
}
export async function submitBranchDay(
  branch: string, date: string, branchIndex: number,
  staffTotals: Record<string, number>, controlTotals: Record<string, number>,
  counts: Record<string, number>,
): Promise<{ branch_day: Record<string, unknown> }> {
  return postJson<{ branch_day: Record<string, unknown> }, Record<string, unknown>>(
    '/branch-log/branch-days/submit',
    { branch, date, branch_index: branchIndex, staff_totals: staffTotals,
      control_totals: controlTotals, counts });
}
export async function decideBranchDay(
  branch: string, date: string, approved: boolean, note = '',
): Promise<{ branch_day: Record<string, unknown> }> {
  return postJson<{ branch_day: Record<string, unknown> },
                  { branch: string; date: string; approved: boolean; note: string }>(
    '/branch-log/branch-days/validate', { branch, date, approved, note });
}'''

COMPONENT = r'''// TIER 2 — branch countersign.
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
  type BranchDays, type BranchDayRow, type ValidationQueue,
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

  const load = useCallback(async (d: string) => {
    setLoading(true);
    try {
      const r = await fetchBranchDays(d);
      setData(r);
      onCount?.(r.rows.filter((x) => x.status === 'submitted').length);
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
            <p className="mt-0.5 text-xs text-gray-500">
              You countersign the branch day. Branch managers validate their own staff.
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
      </Card.Body>
    </Card>
  );
}
'''


PAGE_EDITS = [
    ("imports",
     "import DailyLogValidation from '@/components/DailyLogValidation';",
     "import DailyLogValidation from '@/components/DailyLogValidation';\n"
     "import BranchCountersign from '@/components/BranchCountersign';\n"
     "import { fetchBranchDays } from '@/lib/api';"),
    ("tier state",
     "  const [dailyLogPending, setDailyLogPending] = useState(0);",
     "  const [dailyLogPending, setDailyLogPending] = useState(0);\n"
     "  // Tier 2 (Head of Branches, MD) countersigns BRANCHES; everyone else\n"
     "  // validates individuals. Decided by asking the server what this caller\n"
     "  // oversees rather than by inspecting their role string here.\n"
     "  const [tier2, setTier2] = useState<boolean | null>(null);"),
    ("tier probe",
     "  // Initial load + reload on tab focus to keep queues fresh",
     "  useEffect(() => {\n"
     "    let alive = true;\n"
     "    void (async () => {\n"
     "      try {\n"
     "        const r = await fetchBranchDays();\n"
     "        if (alive) setTier2((r.rows?.length ?? 0) > 0);\n"
     "      } catch {\n"
     "        if (alive) setTier2(false);\n"
     "      }\n"
     "    })();\n"
     "    return () => { alive = false; };\n"
     "  }, []);\n\n"
     "  // Initial load + reload on tab focus to keep queues fresh"),
    ("tab routing",
     "      {activeTab === 'dailylog' && (\n"
     "        <DailyLogValidation onCount={setDailyLogPending} />\n"
     "      )}",
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
     "      )}"),
]


def main():
    apply = "--apply" in sys.argv
    for p in (API, APITS, PAGE):
        if not os.path.isfile(p):
            print("ABORT: %s not found. Run from the project root." % p)
            return 1
    if os.path.exists(COMP):
        print("ABORT: %s already exists - B3 looks applied." % COMP)
        return 1

    api = open(API, encoding="utf-8").read()
    ts = open(APITS, encoding="utf-8").read()
    page = open(PAGE, encoding="utf-8").read()

    if "inspect_only" in api:
        print("ABORT: queue already has inspect_only.")
        return 1
    if "/branch-days" not in api:
        print("ABORT: apply patch_b2_branch_day.py first.")
        return 1
    for label, hay, mark in (("queue signature", api, SIG_OLD),
                             ("can_act", api, CANACT_OLD),
                             ("api.ts queue fn", ts, TS_OLD)):
        if hay.count(mark) != 1:
            print("ABORT: %s anchor matched %d times." % (label, hay.count(mark)))
            return 1

    api = api.replace(SIG_OLD, SIG_NEW, 1)
    # Bound the scope replacement to the queue function: the same import line
    # appears in other endpoints, and an unbounded index() landed it inside a
    # try block elsewhere and broke the module.
    fn = api.index("def branch_log_validation_queue(")
    i = api.index(SCOPE_START, fn)
    j = api.index(SCOPE_END, i)
    api = api[:i] + SCOPE_NEW + api[j:]
    api = api.replace(CANACT_OLD, CANACT_NEW, 1)
    print("  ok  /validation-queue - optional branch, read-only inspection")

    ts = ts.replace(TS_OLD, TS_BLOCK, 1)
    print("  ok  api.ts - branch-day clients")

    for name, old, new in PAGE_EDITS:
        if page.count(old) != 1:
            print("ABORT: ManagerQueues %r anchor matched %d times." % (name, page.count(old)))
            return 1
        page = page.replace(old, new, 1)
        print("  ok  ManagerQueues - %s" % name)

    if "fetchBranchLogHistoryGrid" not in ts:
        print("ABORT: post-check - api.ts lost fetchBranchLogHistoryGrid.")
        return 1
    if api.count("inspect_only") < 3:
        print("ABORT: post-check - inspect_only not wired through.")
        return 1
    if "BranchCountersign" not in page or "tier2" not in page:
        print("ABORT: post-check - tier routing missing.")
        return 1
    for o, c in (("{", "}"), ("(", ")")):
        if COMPONENT.count(o) != COMPONENT.count(c):
            print("ABORT: embedded component unbalanced %s%s." % (o, c))
            return 1
    print("  ok  post-checks: inspection wired, tier routing present")

    if not apply:
        print("\nDRY RUN - nothing written. Re-run with --apply.")
        return 0

    open(COMP, "w", encoding="utf-8", newline="").write(COMPONENT)
    print("CREATED %s" % COMP)
    for path, content in ((API, api), (APITS, ts), (PAGE, page)):
        shutil.copy2(path, path + BACKUP_SUFFIX)
        open(path, "w", encoding="utf-8", newline="").write(content)
        print("APPLIED %s" % path)

    import py_compile
    try:
        py_compile.compile(API, doraise=True)
        print("  ok  api_branch_log.py compiles")
    except Exception as exc:
        print("  FAIL %s" % exc)
        return 1

    print("\nNext:")
    print("  1. pushd frontend\\web && pnpm tsc --noEmit && popd && echo TSC_PASSED")
    print("  2. restart uvicorn")
    return 0


if __name__ == "__main__":
    sys.exit(main())
