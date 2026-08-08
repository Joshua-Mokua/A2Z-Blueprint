#!/usr/bin/env python
# -*- coding: utf-8 -*-
r"""
E3 - cross-branch follow-up: who has not filed, and for how long.

Your requirement: "just below the head of branches list of branches after
everything there should be the list of all staff across the branches that did
not submit for follow up".

ADDS
  GET /api/branch-log/non-submitters?date=
      Everyone across the caller's branches with no log for that day.

      "Days outstanding" is the run of consecutive WORKING days ending on this
      date that the person has missed. A weekend or a gazetted holiday never
      inflates it, and neither does a day they were excused for - the streak
      stops at the first day they either filed OR were excused.

      EXCUSED STAFF ARE EXCLUDED OUTRIGHT. A person on approved leave is not a
      follow-up item, and listing them would train managers to ignore the list.
      That is the whole value of E1's excuse/refusal split showing up here.

      Sorted by days outstanding descending: the oldest neglect first.

  The list renders under the branch table in BranchCountersign, amber-framed,
  with 3+ days in red - past the return window, where logs lock and need an
  admin unlock. The "Recorded reason" column shows a non-excusing exception
  (refused / no explanation) where one exists, so a manager can tell "nobody has
  asked them" from "they were asked and declined".

Verified: py_compile clean, tsc --noEmit clean, vite build clean.

Usage (from project root, .venv active):
    python scripts\\patch_e3_followup.py            # dry run
    python scripts\\patch_e3_followup.py --apply    # write + .pre_e3 backups
"""
import os
import shutil
import sys

API = os.path.join("utils", "api_branch_log.py")
APITS = os.path.join("frontend", "web", "src", "lib", "api.ts")
COMP = os.path.join("frontend", "web", "src", "components", "BranchCountersign.tsx")
BACKUP_SUFFIX = ".pre_e3"

API_ANCHOR = '@router.get("/validation-queue")'
TS_ANCHOR = "export async function fetchBranchDays(date = \'\'): Promise<BranchDays> {"

ENDPOINT_NEW = r'''@router.get("/non-submitters")
def branch_log_non_submitters(date: str = "", user: dict = Depends(get_current_user)):
    """TIER 2 accountability: everyone across the caller's branches who has not
    filed for this day, aged in BUSINESS days.

    "Days outstanding" is the run of consecutive WORKING days ending on this
    date that the person has missed — so a Sunday or a gazetted holiday never
    inflates it, and neither does a day they were excused for. The oldest
    neglect sorts to the top, because that is what needs chasing first.

    Excused days are excluded outright: a person on approved leave is not a
    follow-up item, and listing them would train managers to ignore the list.
    """
    from datetime import date as _date, timedelta as _td
    from utils.staff_code import canon as _canon_n

    me = _identity(user)
    my_code = str(me.get("staff_code", "") or "")
    try:
        day = _date.fromisoformat(str(date)[:10]) if date else _date.today()
    except ValueError:
        raise HTTPException(status_code=400, detail="date must be YYYY-MM-DD")

    try:
        from utils.org_validator import branches_validated_by
        scope = branches_validated_by(my_code)
    except Exception:
        scope = {"branches": []}
    branches = set(scope.get("branches") or [])
    if not branches:
        return {"rows": [], "date": day.isoformat(), "total": 0}

    try:
        from utils import workcal as _wc
        if not _wc.is_working_day(day):
            return {"rows": [], "date": day.isoformat(), "total": 0,
                    "working_day": False}
    except Exception:
        pass

    # The last 15 working days, newest first — enough to age a streak without
    # walking the whole store.
    window, d = [], day
    while len(window) < 15:
        try:
            from utils import workcal as _wc2
            if _wc2.is_working_day(d):
                window.append(d)
        except Exception:
            if d.weekday() != 6:
                window.append(d)
        d -= _td(days=1)

    blm = BranchLogManager()
    logs = blm.get_history(days=40)
    filed = set()
    for l in logs:
        filed.add((_canon_n(l.get("staff_code")), str(l.get("log_date"))[:10]))

    try:
        from utils.branch_log_exceptions import exception_for
    except Exception:
        exception_for = lambda *_a, **_k: None   # noqa: E731

    dims = _roster_dims()
    rows = []
    iso = day.isoformat()
    for ck, dd in dims.items():
        branch = str((dd or {}).get("branch") or "").strip()
        if branch not in branches:
            continue
        code = dd.get("code") or ck
        if (_canon_n(code), iso) in filed:
            continue
        exc = exception_for(code, iso) or {}
        if exc.get("excuses_target"):
            continue          # excused is not a follow-up item

        streak = 0
        for wd in window:
            wiso = wd.isoformat()
            if (_canon_n(code), wiso) in filed:
                break
            e = exception_for(code, wiso) or {}
            if e.get("excuses_target"):
                break
            streak += 1

        rows.append({
            "staff_code": code,
            "staff_name": dd.get("full_name", ""),
            "role": dd.get("role", ""),
            "branch": branch,
            "department": dd.get("department", ""),
            "days_outstanding": streak,
            "exception": exc.get("reason", ""),
            "exception_note": exc.get("note", ""),
        })

    rows.sort(key=lambda r: (-r["days_outstanding"], r["branch"], r["staff_name"]))
    return {"rows": rows, "date": iso, "total": len(rows), "working_day": True}


'''

TS_NEW = r'''export interface NonSubmitterRow {
  staff_code: string; staff_name: string; role: string;
  branch: string; department: string;
  days_outstanding: number;
  exception: string; exception_note: string;
}
export interface NonSubmitters {
  rows: NonSubmitterRow[]; date: string; total: number; working_day?: boolean;
}
export async function fetchNonSubmitters(date = ''): Promise<NonSubmitters> {
  return getJson<NonSubmitters>(
    `/branch-log/non-submitters${date ? `?date=${encodeURIComponent(date)}` : ''}`);
}
'''

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
            <p className="mt-2 text-[11px] text-gray-500">
              Three or more days is past the return window — those logs lock and
              need an admin unlock. Branch managers record the reason; excused
              staff do not appear here.
            </p>
          </div>
        )}
      </Card.Body>
    </Card>
  );
}
'''


def main():
    apply = "--apply" in sys.argv
    for p in (API, APITS, COMP):
        if not os.path.isfile(p):
            print("ABORT: %s not found." % p)
            if p == COMP:
                print("       Apply patch_b3_tier2_view.py first.")
            return 1

    api = open(API, encoding="utf-8").read()
    ts = open(APITS, encoding="utf-8").read()

    if "/non-submitters" in api:
        print("ABORT: non-submitters endpoint already present - E3 looks applied.")
        return 1
    if "inspect_only" not in api:
        print("ABORT: apply patch_b3_tier2_view.py first.")
        return 1
    if api.count(API_ANCHOR) != 1:
        print("ABORT: api anchor matched %d times." % api.count(API_ANCHOR))
        return 1
    if ts.count(TS_ANCHOR) != 1:
        print("ABORT: api.ts anchor matched %d times." % ts.count(TS_ANCHOR))
        return 1

    api = api.replace(API_ANCHOR, ENDPOINT_NEW + API_ANCHOR, 1)
    print("  ok  GET /non-submitters")

    ts = ts.replace(TS_ANCHOR, TS_NEW + TS_ANCHOR, 1)
    print("  ok  api.ts - fetchNonSubmitters")

    for token in ("Outstanding daily logs", "days_outstanding", "fetchNonSubmitters"):
        if token not in COMPONENT:
            print("ABORT: embedded component missing %r." % token)
            return 1
    for o, c in (("{", "}"), ("(", ")")):
        if COMPONENT.count(o) != COMPONENT.count(c):
            print("ABORT: embedded component unbalanced %s%s." % (o, c))
            return 1

    if api.count('@router.get("/non-submitters")') != 1:
        print("ABORT: post-check - endpoint count is not 1.")
        return 1
    if "fetchBranchLogHistoryGrid" not in ts:
        print("ABORT: post-check - api.ts lost fetchBranchLogHistoryGrid.")
        return 1
    print("  ok  post-checks: one endpoint, api.ts intact")

    if not apply:
        print("\nDRY RUN - nothing written. Re-run with --apply.")
        return 0

    for path, content in ((API, api), (APITS, ts), (COMP, COMPONENT)):
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

    print("\nNext: pushd frontend\\web && pnpm tsc --noEmit && popd, then restart uvicorn.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
