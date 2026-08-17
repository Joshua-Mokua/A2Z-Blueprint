#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
B1 - branch line: staff totals, branch actuals, variance, and the submit gate.

RULING (2026-08-08): the branch productivity index is the SUM of validated staff
indices PLUS whatever the manager adds on the branch line, scored on the SAME
index weights. The branch manager does not file personally; they own the branch
output.

ONE NUMBER, TWO JOBS - deliberately. The "Fortis branch (actual)" row is both
  (a) where the manager records activity no individual logged, and
  (b) the control total the over-reporting checker compares against.
Keeping them as two separate numbers would let them drift, and the check would
then be against a figure nobody maintains.

Because the gate guarantees reported <= actual, the branch line's contribution
is exactly the unattributed remainder. So a column WITH an actual scores that
actual; a column WITHOUT one scores what staff reported. Staff reporting always
sets the floor.

WHAT THIS ADDS

  utils/api_branch_log.py - /validation-queue now returns branch, staff_totals,
  control_totals, reconciliation, branch_index, validated_count, filed_count.
  Reuses control_totals_for + reconcile_branch_day from branch_log_reconcile,
  which already implements exactly the rule you asked for: flag ONLY when the
  reported sum exceeds the branch actual; under-reporting is not an anomaly.

  frontend .../lib/api.ts - the queue type gains those fields and a
  saveBranchControlTotals() client. It reuses the ReconMetric / ReconBranchDay
  types already declared further down that file rather than restating them.

  frontend .../components/DailyLogValidation.tsx - three footer rows:
      Staff total     read-only column sums, with "N of M filed"
      Branch (actual) editable per column + Save branch line
      Variance        actual minus reported; red names an over-report

  and a gated "Submit branch day": disabled while any column is over-reported
  OR any filed log is still unactioned. Individual validation is NEVER blocked -
  a manager must be able to validate a correct row even when another is wrong.

NOT YET WIRED: the submit button currently confirms readiness rather than
writing a branch-day submission record. That record, and the branch index
entering /ranking, are B2/B3 - deliberately separate, because they change what
the rankings mean.

Verified: py_compile clean, tsc --noEmit clean, vite build clean, and the
reconciliation gate demonstrated firing on seeded data (Fortis, 9 anomalies,
naming the contributing staff).

Usage (from project root, .venv active):
    python scripts\\patch_b1_branch_line.py            # dry run
    python scripts\\patch_b1_branch_line.py --apply    # write + .pre_b1 backups
"""
import os
import shutil
import sys

API = os.path.join("utils", "api_branch_log.py")
APITS = os.path.join("frontend", "web", "src", "lib", "api.ts")
COMP = os.path.join("frontend", "web", "src", "components", "DailyLogValidation.tsx")
BACKUP_SUFFIX = ".pre_b1"

API_BLOCK = r'''    # B1: the branch the caller closes, its control totals for the day, and the
    # over-reporting reconciliation. The branch line is BOTH the manager's entry
    # point for unattributed activity AND the control total the checker uses —
    # one number, not two competing ones.
    branch = ""
    for _c, _d in mine:
        b = str((_d or {}).get("branch") or "").strip()
        if b:
            branch = b
            break
    control, recon = {}, {}
    if branch:
        try:
            from utils.branch_log_reconcile import control_totals_for, reconcile_branch_day
            control = control_totals_for(branch, iso) or {}
            recon = reconcile_branch_day(logs, branch, iso) or {}
        except Exception:
            control, recon = {}, {}

    # Branch productivity index (ruling 2026-08-08): the sum of validated staff
    # indices PLUS whatever the manager adds on the branch line, scored on the
    # SAME activity weights — one scale, not a second scoring system. Because
    # the gate guarantees reported <= actual, the branch line's addition is the
    # unattributed remainder, so a column with a control total scores its actual
    # and a column without one scores what staff reported.
    try:
        from utils.branch_log import activity_weights
        w = activity_weights()
    except Exception:
        w = {}
    staff_totals = {}
    for r in rows:
        if r.get("status") == "missing":
            continue
        for k in mkeys:
            staff_totals[k] = staff_totals.get(k, 0) + float(r.get(k) or 0)
    branch_index = 0.0
    for k in mkeys:
        reported = float(staff_totals.get(k, 0) or 0)
        actual = control.get(k)
        use = float(actual) if actual not in (None, "") else reported
        branch_index += use * float(w.get(k, 0) or 0)

    return {"rows": rows, "columns": columns, "date": iso, "working_day": True,
            "label": "", "mode": mode, "pending": pending,
            "branch": branch,
            "staff_totals": {k: round(v, 2) for k, v in staff_totals.items()},
            "control_totals": control,
            "reconciliation": recon,
            "branch_index": round(branch_index, 2),
            "validated_count": sum(1 for r in rows if r.get("validated")),
            "filed_count": sum(1 for r in rows if r.get("status") != "missing")}'''

TS_BLOCK = r'''export interface ValidationQueue {
  rows: ValidationQueueRow[]; columns: HistoryGridColumn[];
  date: string; working_day: boolean; label: string;
  mode: string; pending: number;
  branch?: string;
  staff_totals?: Record<string, number>;
  control_totals?: Record<string, number>;
  // ReconBranchDay/ReconMetric are declared further down this file with the
  // other reconciliation types — reuse them rather than restating the shape.
  reconciliation?: Partial<ReconBranchDay>;
  branch_index?: number;
  validated_count?: number;
  filed_count?: number;
}
export async function saveBranchControlTotals(
  branch: string, date: string, totals: Record<string, number>,
): Promise<{ status: string; totals: Record<string, number> }> {
  return postJson<{ status: string; totals: Record<string, number> },
                  { branch: string; date: string; totals: Record<string, number> }>(
    '/branch-log/control-totals', { branch, date, totals });
}
'''

COMPONENT = r'''// Daily log validation — the Manager Queues tab.
//
// One day at a time, one row per staff member this manager is a permitted
// validator for. Permission is decided server-side by
// utils.org_validator.daily_log_validators_for (branch triad inside a branch,
// line manager at Head Office); this component never infers it.
//
// Rulings honoured here (2026-08-08):
//   * NO bulk validate. Each row is actioned individually and deliberately.
//   * Staff who filed nothing DO appear, so a manager sees who owes a log.
//     They carry can_act=false and offer no actions — there is nothing to
//     validate, only something to chase.
//   * Returning a log REQUIRES a note. A returned log with no reason leaves
//     the staff member nothing to act on.
//
// Colours come from HistoryGrid's exported family palette, so the Entry tab,
// the History grid and this queue speak one visual language.

import { useCallback, useEffect, useState } from 'react';
import { Button } from '@/components/Button';
import { Card } from '@/components/Card';
import { useToast } from '@/components/Toast';
import { FAM_CELL, FAM_HEAD, famOf } from '@/components/HistoryGrid';
import {
  fetchBranchLogValidationQueue, validateBranchLog, returnBranchLog,
  saveBranchControlTotals,
  type ValidationQueue, type ValidationQueueRow,
} from '@/lib/api';

function num(v: unknown): number {
  const n = Number(v);
  return Number.isFinite(n) ? n : 0;
}

function fmt(v: unknown): string {
  const n = num(v);
  if (n === 0) return '';
  return Number.isInteger(n) ? String(n) : n.toFixed(1);
}

function todayIso(): string {
  const d = new Date();                      // local, not UTC — see lib/datetime
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
}

export default function DailyLogValidation({ onCount }: { onCount?: (n: number) => void }) {
  const { toast } = useToast();
  const [date, setDate] = useState(todayIso());
  const [q, setQ] = useState<ValidationQueue | null>(null);
  const [loading, setLoading] = useState(false);
  const [busyId, setBusyId] = useState('');
  const [returning, setReturning] = useState('');   // log_id with an open note box
  const [note, setNote] = useState('');
  // B1: the branch line. Held as strings so a half-typed number does not fight
  // the input, and only parsed on save.
  const [actuals, setActuals] = useState<Record<string, string>>({});
  const [savingBranch, setSavingBranch] = useState(false);

  const load = useCallback(async (d: string) => {
    setLoading(true);
    try {
      const r = await fetchBranchLogValidationQueue(d);
      setQ(r);
      onCount?.(r.pending ?? 0);
      const ct = r.control_totals ?? {};
      setActuals(Object.fromEntries(
        Object.entries(ct).map(([k, v]) => [k, v == null ? '' : String(v)])));
    } catch (e) {
      toast({ tone: 'danger', message: e instanceof Error ? e.message : 'Could not load the queue.' });
      setQ(null);
    } finally {
      setLoading(false);
    }
  }, [toast, onCount]);

  useEffect(() => { void load(date); }, [date, load]);

  async function act(row: ValidationQueueRow, approve: boolean) {
    if (!row.log_id) return;
    if (!approve && !note.trim()) {
      toast({ tone: 'danger', message: 'A note is required when returning a log.' });
      return;
    }
    setBusyId(row.log_id);
    try {
      if (approve) {
        await validateBranchLog(row.log_id, true, '');
        toast({ tone: 'success', message: `Validated ${row.staff_name}.` });
      } else {
        await returnBranchLog(row.log_id, note.trim());
        toast({ tone: 'success', message: `Returned to ${row.staff_name} for amendment.` });
      }
      setReturning('');
      setNote('');
      await load(date);
    } catch (e) {
      toast({ tone: 'danger', message: e instanceof Error ? e.message : 'Action failed.' });
    } finally {
      setBusyId('');
    }
  }

  async function saveBranchLine() {
    if (!q?.branch) return;
    const totals: Record<string, number> = {};
    for (const [k, v] of Object.entries(actuals)) {
      const n = Number(v);
      if (v !== '' && Number.isFinite(n)) totals[k] = n;
    }
    setSavingBranch(true);
    try {
      await saveBranchControlTotals(q.branch, date, totals);
      toast({ tone: 'success', message: `${q.branch} branch line saved.` });
      await load(date);
    } catch (e) {
      toast({ tone: 'danger', message: e instanceof Error ? e.message : 'Could not save the branch line.' });
    } finally {
      setSavingBranch(false);
    }
  }

  const rows = q?.rows ?? [];
  const cols = q?.columns ?? [];
  const staffTotals = q?.staff_totals ?? {};
  const reconMetrics = q?.reconciliation?.metrics ?? {};
  const breaches = Object.entries(reconMetrics).filter(([, m]) => m?.anomaly);
  const blocked = breaches.length > 0;
  const th = 'whitespace-nowrap px-2 py-2 text-left text-[11px] font-semibold uppercase tracking-wide';
  const td = 'whitespace-nowrap px-2 py-2 text-xs align-top';

  return (
    <Card className="mt-4">
      <Card.Header>
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <h2 className="text-base font-semibold text-gray-900">Daily log validation</h2>
            <p className="mt-0.5 text-xs text-gray-500">
              {q?.mode === 'triad'
                ? 'You are one of the branch management triad for these staff.'
                : q?.mode === 'line_manager'
                  ? 'You are the line manager for these staff.'
                  : 'Staff whose daily logs you may validate.'}
            </p>
          </div>
          <div className="flex items-center gap-2 text-xs">
            <label className="text-gray-500">Day</label>
            <input
              type="date"
              value={date}
              onChange={(e) => setDate(e.target.value)}
              className="rounded border border-gray-200 px-2 py-1 text-xs"
            />
            {q && q.pending > 0 && (
              <span className="rounded-full bg-[#FAEEDA] px-2.5 py-1 font-medium text-[#854F0B]">
                {q.pending} awaiting you
              </span>
            )}
          </div>
        </div>
      </Card.Header>

      <Card.Body>
        {loading && <p className="py-8 text-center text-sm text-gray-400">Loading…</p>}

        {!loading && q && !q.working_day && (
          <p className="py-8 text-center text-sm text-gray-500">
            {q.label || 'Rest day'} — no logs are expected, so there is nothing to validate.
          </p>
        )}

        {!loading && q?.working_day && rows.length === 0 && (
          <p className="py-8 text-center text-sm text-gray-400">
            No staff report to you for daily-log validation on this day.
          </p>
        )}

        {!loading && rows.length > 0 && (
          <div className="overflow-auto rounded-lg border border-gray-200">
            <table className="w-full border-separate" style={{ borderSpacing: 0 }}>
              <thead>
                <tr>
                  <th className={`${th} sticky top-0 z-10 bg-gray-100 text-gray-600`}>Staff</th>
                  <th className={`${th} sticky top-0 z-10 bg-gray-100 text-gray-600`}>Name</th>
                  <th className={`${th} sticky top-0 z-10 bg-gray-100 text-gray-600`}>Role</th>
                  {cols.map((c) => (
                    <th key={c.key}
                        className={`px-2 py-2 text-left text-[10px] font-semibold uppercase tracking-tight sticky top-0 z-10 ${FAM_HEAD[famOf(c.key)]}`}
                        style={{ width: 74, minWidth: 74 }}
                        title={c.label}>
                      <span className="block overflow-hidden leading-[1.15]"
                            style={{ display: '-webkit-box', WebkitLineClamp: 3, WebkitBoxOrient: 'vertical' }}>
                        {c.label}
                      </span>
                    </th>
                  ))}
                  <th className={`${th} sticky top-0 z-10 bg-[#0082BB] text-white`}>Index</th>
                  <th className={`${th} sticky top-0 z-10 bg-[#0082BB] text-white`}>Target</th>
                  <th className={`${th} sticky top-0 z-10 bg-gray-100 text-gray-600`}>Note</th>
                  <th className={`${th} sticky top-0 z-10 bg-gray-100 text-gray-600`}>Decision</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((r, i) => {
                  const missing = r.status === 'missing';
                  const bg = missing ? 'bg-[#FDF6EC]'
                    : r.validated ? 'bg-[#F3F8EC]'
                    : i % 2 === 1 ? 'bg-gray-50/40' : 'bg-white';
                  const busy = busyId === r.log_id;
                  return (
                    <tr key={r.staff_code} className={missing ? 'text-gray-400' : ''}>
                      <td className={`${td} ${bg} tabular-nums text-gray-500`}>{r.staff_code}</td>
                      <td className={`${td} ${bg} ${missing ? '' : 'text-gray-900'}`}>
                        {r.staff_name}
                        {r.auto_submitted && (
                          <span className="ml-1 rounded bg-[#FAEEDA] px-1 py-0.5 text-[10px] text-[#854F0B]">auto</span>
                        )}
                      </td>
                      <td className={`${td} ${bg} text-gray-500`}>{r.role}</td>

                      {cols.map((c) => {
                        const v = num(r[c.key]);
                        return (
                          <td key={c.key}
                              className={`${td} tabular-nums text-gray-700 ${
                                missing ? bg : v > 0 ? FAM_CELL[famOf(c.key)] : bg}`}>
                            {missing ? <span className="text-gray-300">·</span> : fmt(r[c.key])}
                          </td>
                        );
                      })}

                      <td className={`${td} ${bg} tabular-nums font-medium text-gray-900`}>
                        {missing ? <span className="text-gray-300">—</span> : num(r.index).toFixed(1)}
                      </td>
                      <td className={`${td} ${bg} tabular-nums text-gray-500`}>{num(r.target).toFixed(1)}</td>

                      <td className={`${td} ${bg} max-w-[260px] whitespace-normal text-gray-600`}>
                        {missing
                          ? <span className="rounded bg-[#FAEEDA] px-1.5 py-0.5 text-[10px] font-medium text-[#854F0B]">Not filed</span>
                          : r.remarks || <span className="text-gray-300">—</span>}
                      </td>

                      <td className={`${td} ${bg}`}>
                        {r.validated ? (
                          <span className="text-[11px] font-medium text-[#3B6D11]">✓ Validated</span>
                        ) : !r.can_act ? (
                          <span className="text-[11px] text-gray-400">—</span>
                        ) : returning === r.log_id ? (
                          <div className="flex flex-col gap-1" style={{ minWidth: 210 }}>
                            <input
                              autoFocus
                              value={note}
                              onChange={(e) => setNote(e.target.value)}
                              placeholder="Why is it being returned?"
                              className="w-full rounded border border-gray-300 px-2 py-1 text-xs"
                            />
                            <div className="flex gap-1">
                              <Button size="sm" variant="secondary" disabled={busy}
                                      onClick={() => void act(r, false)}>
                                Send back
                              </Button>
                              <Button size="sm" variant="ghost" disabled={busy}
                                      onClick={() => { setReturning(''); setNote(''); }}>
                                Cancel
                              </Button>
                            </div>
                          </div>
                        ) : (
                          <div className="flex gap-1">
                            <Button size="sm" disabled={busy} onClick={() => void act(r, true)}>
                              {busy ? '…' : 'Validate'}
                            </Button>
                            <Button size="sm" variant="ghost" disabled={busy}
                                    onClick={() => { setReturning(r.log_id); setNote(''); }}>
                              Return
                            </Button>
                          </div>
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>

              {/* ── B1: the branch line ──────────────────────────────────────
                  STAFF TOTAL  — what individuals reported, read-only.
                  BRANCH       — the branch's ACTUAL numbers, entered by the
                                 triad. This is one number doing two jobs on
                                 purpose: it is where unattributed branch
                                 activity is recorded, AND it is the control
                                 total the over-reporting checker compares
                                 against. Two competing numbers would drift.
                  VARIANCE     — actual minus reported. Red when a column is
                                 over-reported; that blocks branch submission
                                 but never blocks validating a correct row. */}
              <tfoot>
                <tr className="border-t-2 border-gray-300 bg-gray-50">
                  <td className={`${td} font-semibold text-gray-700`} colSpan={3}>
                    Staff total ({q?.filed_count ?? 0} of {rows.length} filed)
                  </td>
                  {cols.map((c) => (
                    <td key={c.key} className={`${td} tabular-nums font-semibold text-gray-800`}>
                      {fmt(staffTotals[c.key])}
                    </td>
                  ))}
                  <td className={`${td} tabular-nums font-semibold text-gray-800`}>
                    {rows.reduce((a, r) => a + (r.status === 'missing' ? 0 : num(r.index)), 0).toFixed(1)}
                  </td>
                  <td className={td} />
                  <td className={td} colSpan={2} />
                </tr>

                <tr className="bg-[#EFF6FB]">
                  <td className={`${td} font-semibold text-[#005B82]`} colSpan={3}>
                    {q?.branch ? `${q.branch} branch (actual)` : 'Branch (actual)'}
                    <div className="mt-0.5 text-[10px] font-normal text-gray-500">
                      The branch's real numbers, including activity not logged by an individual.
                    </div>
                  </td>
                  {cols.map((c) => (
                    <td key={c.key} className={`${td} ${FAM_CELL[famOf(c.key)]}`}>
                      <input
                        value={actuals[c.key] ?? ''}
                        onChange={(e) => setActuals((p) => ({ ...p, [c.key]: e.target.value }))}
                        inputMode="numeric"
                        placeholder="—"
                        className="w-full rounded border border-gray-300 bg-white px-1 py-0.5 text-right text-xs tabular-nums"
                        style={{ maxWidth: 70 }}
                      />
                    </td>
                  ))}
                  <td className={`${td} tabular-nums font-semibold text-[#003D57]`}
                      title="Validated staff indices plus the branch line, on the same index weights">
                    {(q?.branch_index ?? 0).toFixed(1)}
                  </td>
                  <td className={td} />
                  <td className={td} colSpan={2}>
                    <Button size="sm" variant="secondary" disabled={savingBranch || !q?.branch}
                            onClick={() => void saveBranchLine()}>
                      {savingBranch ? 'Saving…' : 'Save branch line'}
                    </Button>
                  </td>
                </tr>

                <tr className="bg-gray-50">
                  <td className={`${td} font-semibold text-gray-600`} colSpan={3}>Variance</td>
                  {cols.map((c) => {
                    const m = reconMetrics[c.key];
                    if (!m || m.control_total == null) {
                      return <td key={c.key} className={`${td} text-gray-300`}>—</td>;
                    }
                    const diff = num(m.control_total) - num(m.reported_sum);
                    return (
                      <td key={c.key}
                          className={`${td} tabular-nums font-medium ${
                            m.anomaly ? 'text-rose-600' : 'text-[#3B6D11]'}`}
                          title={m.anomaly
                            ? `Over-reported by ${m.over_by}`
                            : 'Reported within the branch actual'}>
                        {diff > 0 ? `+${diff}` : diff}
                      </td>
                    );
                  })}
                  <td className={td} colSpan={4} />
                </tr>
              </tfoot>
            </table>
          </div>
        )}

        {!loading && rows.length > 0 && (
          <div className="mt-4 flex flex-wrap items-center justify-between gap-3 border-t border-gray-100 pt-3">
            <div className="text-xs">
              {blocked ? (
                <span className="text-rose-600">
                  <span className="font-semibold">Over-reported:</span>{' '}
                  {breaches.map(([k, m]) => {
                    const label = cols.find((c) => c.key === k)?.label ?? k;
                    return `${label} (+${m.over_by})`;
                  }).join(', ')}
                  <span className="ml-1 text-gray-500">
                    — staff reported more than the branch actual. Correct the branch line
                    or return the affected logs before submitting the day.
                  </span>
                </span>
              ) : (
                <span className="text-gray-500">
                  {q?.validated_count ?? 0} of {q?.filed_count ?? 0} filed logs validated
                  {q?.pending ? ` · ${q.pending} still awaiting you` : ''}
                </span>
              )}
            </div>
            <Button
              disabled={blocked || (q?.pending ?? 0) > 0}
              title={blocked
                ? 'Nothing can be submitted while a column is over-reported'
                : (q?.pending ?? 0) > 0
                  ? 'Validate or return every filed log first'
                  : 'Close the branch day'}
              onClick={() => toast({
                tone: 'success',
                message: `${q?.branch ?? 'Branch'} day ready to submit — branch index ${(q?.branch_index ?? 0).toFixed(1)}.`,
              })}
            >
              Submit branch day
            </Button>
          </div>
        )}
      </Card.Body>
    </Card>
  );
}
'''


API_OLD = '''    return {"rows": rows, "columns": columns, "date": iso, "working_day": True,
            "label": "", "mode": mode, "pending": pending}'''

TS_START = "export interface ValidationQueue {"
TS_END = "export async function fetchBranchLogValidationQueue("


def main():
    apply = "--apply" in sys.argv
    for p in (API, APITS, COMP):
        if not os.path.isfile(p):
            print("ABORT: %s not found. Run from the project root." % p)
            return 1

    api = open(API, encoding="utf-8").read()
    ts = open(APITS, encoding="utf-8").read()
    comp = open(COMP, encoding="utf-8").read()

    if "branch_index" in api:
        print("ABORT: /validation-queue already returns branch_index - B1 looks applied.")
        return 1
    if "staff_validated_by" not in api:
        print("ABORT: apply patch_v2a_queue_perf.py first.")
        return 1
    if api.count(API_OLD) != 1:
        print("ABORT: queue return anchor matched %d times." % api.count(API_OLD))
        return 1
    if ts.count(TS_START) != 1 or ts.count(TS_END) != 1:
        print("ABORT: api.ts anchors not found exactly once.")
        return 1
    if "ReconBranchDay" not in ts:
        print("ABORT: ReconBranchDay is missing from api.ts - reconciliation types expected.")
        return 1

    api = api.replace(API_OLD, API_BLOCK, 1)
    print("  ok  /validation-queue - branch totals, reconciliation, branch index")

    a = ts.index(TS_START)
    b = ts.index(TS_END, a)
    ts = ts[:a] + TS_BLOCK + ts[b:]
    print("  ok  api.ts - queue type + saveBranchControlTotals")

    for token in ("Save branch line", "Submit branch day", "Staff total", "blocked"):
        if token not in COMPONENT:
            print("ABORT: embedded component missing %r." % token)
            return 1
    for o, c in (("{", "}"), ("(", ")")):
        if COMPONENT.count(o) != COMPONENT.count(c):
            print("ABORT: embedded component unbalanced %s%s." % (o, c))
            return 1
    print("  ok  embedded component validated (%d lines)" % (COMPONENT.count("\n") + 1))

    if "return {\"rows\": rows" not in api or api.count("\"branch_index\"") != 1:
        print("ABORT: post-check - queue return block is not as expected.")
        return 1

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

    print("\nNext:")
    print("  1. pushd frontend\\web && pnpm tsc --noEmit && popd && echo TSC_PASSED")
    print("  2. restart uvicorn")
    return 0


if __name__ == "__main__":
    sys.exit(main())
