#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Phase 3c - filter by the bank's real structure, not free text.

THE PROBLEM
The Daily Log record stores a free-text `unit` typed at submit time. In live
data that field is inconsistent - "Fortis" and "Fortis Branch", "Consumer" /
"Consumer Bank" / "Consumer Banking", plus shouty imports like
"EKE-CONSUMER BANKING DEPARTMENT". Filtering an MD's bank-wide view on that is
useless.

THE FIX
data/staff_roster.json is the source of truth and already holds BOTH dimensions
cleanly for 362 staff:
    department  - the function: Commercial Banking, Consumer Banking, Corporate
                  Banking, Treasury, Finance, Internal Audit, Internal Control,
                  Credit Risk Management, Legal, Operations, CAD, Compliance,
                  Risk, Technology, HR, MD's Office  (23 in total)
    unit        - the branch: Fortis, Westlands, Eldoret, Karen, Kisumu,
                  Mombasa Moi, Head Office ...        (17 in total)

utils/api_branch_log.py now joins the roster onto every grid row and emits
`department` and `branch`. Keyed on utils.staff_code.canon so KE0439/KE439/439
all resolve, with a whitespace-stripped fallback for codes stored as "CN 272".
Cached on roster mtime, so an edit is picked up without restarting uvicorn.
The roster's full_name also replaces the log's copy, which fixes the
"RIBUTHI Loise [EKE-Operations]" suffix at source rather than by regex.
Unmatched codes fall back to the log's own unit - the grid never blanks.

The grid then filters on DEPARTMENT, then BRANCH, then PERSON. Branch narrows
to the chosen department but the two are independent dimensions, because staff
in one branch report across several departments.

Verified before delivery: py_compile clean, tsc --noEmit clean, vite build
clean, and the roster join checked against real codes
(KE814 -> Loise Wanjiru Ributhi | Commercial Banking | Karen).

Usage (from project root, .venv active):
    python scripts\\patch_p3c_org_filters.py            # dry run
    python scripts\\patch_p3c_org_filters.py --apply    # write + .pre_p3c backups
"""
import os
import shutil
import sys

API = os.path.join("utils", "api_branch_log.py")
APITS = os.path.join("frontend", "web", "src", "lib", "api.ts")
COMP = os.path.join("frontend", "web", "src", "components", "HistoryGrid.tsx")
BACKUP_SUFFIX = ".pre_p3c"

API_HELPER_ANCHOR = '''@router.get("/history-grid")'''
API_HELPER = '''_ROSTER_DIMS_CACHE = None
_ROSTER_DIMS_MTIME = None


def _roster_dims() -> dict:
    """Canonical {staff_code -> (department, branch, full_name)} from the roster.

    The Daily Log record carries a free-text `unit` typed at submit time, which
    in live data is inconsistent ("Fortis" / "Fortis Branch" / "Consumer" /
    "EKE-CONSUMER BANKING DEPARTMENT"). The roster is the source of truth and
    holds BOTH dimensions properly: `department` is the function (Commercial
    Banking, Treasury, Internal Audit...) and `unit` is the branch (Fortis,
    Westlands, Head Office...). Grid filters must use these, not the free text.

    Keyed on utils.staff_code.canon so KE0439/KE439/439 all resolve, plus a
    whitespace-stripped fallback for codes stored as "CN 272".
    Cached on file mtime; a roster edit is picked up without a restart.
    """
    global _ROSTER_DIMS_CACHE, _ROSTER_DIMS_MTIME
    import json as _json
    import os as _os
    from pathlib import Path as _Path
    from utils.core import DATA_DIR as _DATA_DIR
    from utils.staff_code import canon as _canon

    p = str(_Path(_DATA_DIR) / "staff_roster.json")
    try:
        mtime = _os.path.getmtime(p)
    except OSError:
        # Roster missing is a real condition, not a silent one: the grid still
        # renders, it just falls back to the log's own free-text unit.
        return _ROSTER_DIMS_CACHE or {}

    if _ROSTER_DIMS_CACHE is not None and _ROSTER_DIMS_MTIME == mtime:
        return _ROSTER_DIMS_CACHE

    out = {}
    try:
        raw = _json.loads(open(p, encoding="utf-8").read())
        rows = raw if isinstance(raw, list) else next(
            (v for v in raw.values() if isinstance(v, list)), [])
        for r in rows:
            if not isinstance(r, dict):
                continue
            rec = {
                "department": str(r.get("department") or "").strip(),
                "branch":     str(r.get("unit") or "").strip(),
                "full_name":  str(r.get("full_name") or "").strip(),
            }
            code = str(r.get("staff_code") or "")
            for key in {_canon(code), "".join(code.split()).upper()}:
                if key:
                    out.setdefault(key, rec)
    except Exception:
        return _ROSTER_DIMS_CACHE or {}

    _ROSTER_DIMS_CACHE, _ROSTER_DIMS_MTIME = out, mtime
    return out


def _dims_for(staff_code) -> dict:
    """Roster dimensions for a staff code, empty dict when unmatched."""
    from utils.staff_code import canon as _canon
    dims = _roster_dims()
    code = str(staff_code or "")
    return dims.get(_canon(code)) or dims.get("".join(code.split()).upper()) or {}


@router.get("/history-grid")'''

API_ROW_OLD = '''                "manager_note": str(r.get("manager_note") or ""),
            }'''
API_ROW_NEW = '''                "manager_note": str(r.get("manager_note") or ""),
            }
            # P3c: canonical dimensions from the roster. The log's own free-text
            # `unit` stays on the row for backward compatibility, but the grid
            # filters on department/branch because those are the structure the
            # bank actually reports against.
            _d = _dims_for(r.get("staff_code"))
            row["department"] = _d.get("department", "")
            row["branch"] = _d.get("branch", "") or str(r.get("unit") or "")
            if _d.get("full_name"):
                row["staff_name"] = _d["full_name"]'''

TS_OLD = "  remarks?: string; manager_note?: string;"
TS_NEW = ("  remarks?: string; manager_note?: string;\n"
          "  department?: string; branch?: string;   // canonical, joined from the roster")

COMPONENT = r"""// Phase 3 — wide spreadsheet history grid for the Daily Log.
//
// One row per staff per day. Identity columns (Date / Staff / Name / Role) are
// frozen to the left so they survive horizontal scrolling across an arbitrary
// number of activity columns; the header row is frozen to the top. The four
// corner cells carry the highest stacking order or the scrolling body overruns
// them.
//
// Column groups, per the approved mockup:
//   identity   — frozen, white
//   activities — one per metric field, from the server's `columns` metadata
//   scoring    — Index / Target / Var on brand primary        #0082BB
//   balance    — running carried-forward variance, deep blue   #003D57
//
// REST DAYS: WC-2b excludes Sundays and public holidays from the carried-forward
// walk, and those rows arrive with working_day=false. They must NOT render as a
// zero target with a zero variance — that reads as "logged nothing, achieved
// nothing" when the truth is "no work was expected". They render muted, with an
// em-dash target and a Rest chip.

import { useMemo, useState } from 'react';
import type { HistoryGrid as Grid, HistoryGridRow } from '@/lib/api';

// Frozen column widths in px. The cumulative offsets must stay in step with
// these — a mismatch shows as overlapping or gapped sticky columns.
const W_DATE = 92;
const W_CODE = 74;
const W_NAME = 158;
const W_ROLE = 132;
const W_UNIT = 118;
const L_DATE = 0;
const L_CODE = W_DATE;
const L_NAME = W_DATE + W_CODE;
const L_ROLE = W_DATE + W_CODE + W_NAME;
const L_UNIT = W_DATE + W_CODE + W_NAME + W_ROLE;

// The roster bakes a department suffix into the name — "RIBUTHI Loise
// [EKE-Operations]". The unit already has its own column, so strip it rather
// than print the same fact twice in a cell that has no room for it.
function cleanName(n: unknown): string {
  return String(n ?? '').replace(/\s*\[[^\]]*\]\s*$/, '').trim();
}

// Activity families, mirroring DayPlanner's chip colours so the Entry tab and
// this grid read as one system. Header tint names the family; the column body
// carries a 3% wash of the same hue so a wide scroll stays orientated.
const FAMILY: Record<string, 'teal' | 'amber' | 'blue' | 'pink' | 'gray'> = {
  accounts_opened: 'teal', accounts_activated: 'teal', dfs_registrations: 'teal',
  cards_issued: 'teal', complaints_resolved: 'teal',
  deposits_mobilised: 'amber', loans_disbursed: 'amber', loans_referred: 'amber',
  bancassurance_sold: 'amber',
  customer_visits: 'blue', digital_txns: 'blue', transactions_count: 'blue',
  nps_collected: 'blue', new_leads: 'blue', cross_sell_success: 'blue',
  complaints_received: 'pink', teller_errors: 'pink',
};
const FAM_HEAD: Record<string, string> = {
  teal:  'bg-[#E1F5EE] text-[#0F6E56]',
  amber: 'bg-[#FAEEDA] text-[#854F0B]',
  blue:  'bg-[#E6F1FB] text-[#0C447C]',
  pink:  'bg-[#FBEAF0] text-[#993556]',
  gray:  'bg-gray-100 text-gray-600',
};
const FAM_CELL: Record<string, string> = {
  teal:  'bg-[#E1F5EE]/30', amber: 'bg-[#FAEEDA]/30',
  blue:  'bg-[#E6F1FB]/30', pink:  'bg-[#FBEAF0]/30', gray: '',
};
function famOf(key: string): string { return FAMILY[key] ?? 'gray'; }

const SCOPE_LABEL: Record<string, string> = {
  bank: 'Bank-wide', subtree: 'My team', self: 'My logs',
};

function num(v: unknown): number {
  const n = Number(v);
  return Number.isFinite(n) ? n : 0;
}

function fmt(v: unknown): string {
  const n = num(v);
  if (n === 0) return '';                        // blank reads better than a field of zeros
  return Number.isInteger(n) ? String(n) : n.toFixed(1);
}

function signed(n: number): string {
  return (n > 0 ? '+' : '') + (Number.isInteger(n) ? String(n) : n.toFixed(1));
}

function dayLabel(iso: string): { day: string; date: string } {
  const [y, m, d] = String(iso).slice(0, 10).split('-').map(Number);
  if (!y || !m || !d) return { day: '', date: String(iso) };
  const dt = new Date(y, m - 1, d);              // local midnight — see lib/datetime
  return {
    day:  dt.toLocaleDateString(undefined, { weekday: 'short' }),
    date: dt.toLocaleDateString(undefined, { day: '2-digit', month: 'short' }),
  };
}

export interface HistoryGridProps {
  grid: Grid | null;
  loading?: boolean;
  days: number;
  onDaysChange: (d: number) => void;
}

export default function HistoryGrid({ grid, loading, days, onDaysChange }: HistoryGridProps) {
  const allRows = grid?.rows ?? [];
  const cols = grid?.columns ?? [];

  // Unit / person filters. Derived from the loaded rows rather than fetched:
  // a head of branches or the MD gets the whole bank back and needs to narrow
  // to one branch, then one person, without a round trip.
  const [deptFilter, setDeptFilter] = useState('');
  const [branchFilter, setBranchFilter] = useState('');
  const [staffFilter, setStaffFilter] = useState('');

  const dept = (r: HistoryGridRow) => String(r.department ?? '').trim();
  const branch = (r: HistoryGridRow) => String(r.branch ?? r.unit ?? '').trim();

  const depts = useMemo(
    () => Array.from(new Set(allRows.map(dept).filter(Boolean))).sort(), [allRows]);

  // Branches narrow to the chosen department: staff in a branch report across
  // several departments, so the two dimensions are independent, not nested.
  const branches = useMemo(() => Array.from(new Set(
    allRows.filter((r) => !deptFilter || dept(r) === deptFilter).map(branch).filter(Boolean),
  )).sort(), [allRows, deptFilter]);

  const people = useMemo(() => {
    const seen = new Map<string, string>();
    for (const r of allRows) {
      if (deptFilter && dept(r) !== deptFilter) continue;
      if (branchFilter && branch(r) !== branchFilter) continue;
      const code = String(r.staff_code ?? '');
      if (code && !seen.has(code)) seen.set(code, cleanName(r.staff_name));
    }
    return Array.from(seen, ([code, name]) => ({ code, name }))
      .sort((a, b) => a.name.localeCompare(b.name));
  }, [allRows, deptFilter, branchFilter]);

  const rows = useMemo(() => allRows.filter((r) =>
    (!deptFilter || dept(r) === deptFilter)
    && (!branchFilter || branch(r) === branchFilter)
    && (!staffFilter || String(r.staff_code ?? '') === staffFilter)),
    [allRows, deptFilter, branchFilter, staffFilter]);

  // Closing balance per staff = cf_variance of their most recent row. Rows
  // arrive newest-first, so the first sighting of a staff code wins.
  const closing = useMemo(() => {
    const out: Record<string, number> = {};
    for (const r of rows) {
      const k = String(r.staff_code ?? '');
      if (!(k in out)) out[k] = num(r.cf_variance);
    }
    return out;
  }, [rows]);

  const staffCount = Object.keys(closing).length;
  const behind = Object.values(closing).filter((v) => v < 0).length;

  function exportCsv() {
    const head = ['Date', 'Staff', 'Name', 'Role', 'Department', 'Branch', ...cols.map((c) => c.label),
                  'Index', 'Target', 'Variance', 'C/F balance', 'Notes', 'Manager note'];
    const body = rows.map((r) => [
      r.log_date, r.staff_code, cleanName(r.staff_name), r.role, dept(r), branch(r),
      ...cols.map((c) => num(r[c.key])),
      num(r.index),
      r.working_day === false ? '' : num(r.target),
      r.working_day === false ? '' : num(r.variance),
      num(r.cf_variance), r.remarks ?? '', r.manager_note ?? '',
    ]);
    const csv = [head, ...body]
      .map((line) => line.map((c) => '"' + String(c ?? '').replace(/"/g, '""') + '"').join(','))
      .join('\n');
    const url = URL.createObjectURL(new Blob([csv], { type: 'text/csv;charset=utf-8;' }));
    const a = document.createElement('a');
    a.href = url;
    a.download = 'daily-log-history-' + new Date().toISOString().slice(0, 10) + '.csv';
    a.click();
    URL.revokeObjectURL(url);
  }

  const th = 'whitespace-nowrap px-2 py-2 text-left text-[11px] font-semibold uppercase tracking-wide';
  // Activity headers wrap to three lines — some labels are full sentences and a
  // single nowrap line pushed the grid absurdly wide.
  const thWrap = 'px-2 py-2 text-left align-bottom text-[10px] font-semibold uppercase tracking-tight';
  const td = 'whitespace-nowrap px-2 py-1.5 text-xs';

  return (
    <div>
      <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
        <div className="flex flex-wrap items-center gap-2 text-xs">
          <span className="text-gray-500">Showing</span>
          <select
            className="rounded border border-gray-200 px-2 py-1 text-xs"
            value={days}
            onChange={(e) => onDaysChange(Number(e.target.value))}
          >
            {[7, 14, 30, 60, 90].map((d) => <option key={d} value={d}>last {d} days</option>)}
          </select>
          {grid && (
            <span className="rounded-full bg-[#E6F1FB] px-2.5 py-1 text-[11px] text-[#0C447C]">
              {SCOPE_LABEL[grid.scope_tier] ?? grid.scope_tier}
            </span>
          )}
          {depts.length > 1 && (
            <select
              className="max-w-[190px] rounded border border-gray-200 px-2 py-1 text-xs"
              value={deptFilter}
              onChange={(e) => { setDeptFilter(e.target.value); setBranchFilter(''); setStaffFilter(''); }}
            >
              <option value="">All departments ({depts.length})</option>
              {depts.map((d) => <option key={d} value={d}>{d}</option>)}
            </select>
          )}
          {branches.length > 1 && (
            <select
              className="max-w-[170px] rounded border border-gray-200 px-2 py-1 text-xs"
              value={branchFilter}
              onChange={(e) => { setBranchFilter(e.target.value); setStaffFilter(''); }}
            >
              <option value="">All branches ({branches.length})</option>
              {branches.map((b) => <option key={b} value={b}>{b}</option>)}
            </select>
          )}
          {people.length > 1 && (
            <select
              className="max-w-[190px] rounded border border-gray-200 px-2 py-1 text-xs"
              value={staffFilter}
              onChange={(e) => setStaffFilter(e.target.value)}
            >
              <option value="">Everyone ({people.length})</option>
              {people.map((p) => <option key={p.code} value={p.code}>{p.name}</option>)}
            </select>
          )}
          {(deptFilter || branchFilter || staffFilter) && (
            <button type="button"
              onClick={() => { setDeptFilter(''); setBranchFilter(''); setStaffFilter(''); }}
              className="rounded px-1.5 py-0.5 text-[11px] text-brand-primary hover:bg-[#0082BB]/10">
              Clear
            </button>
          )}
          {staffCount > 0 && (
            <span className="text-gray-400">
              {rows.length} rows · {staffCount} staff
              {behind > 0 && <span className="text-rose-600"> · {behind} behind target</span>}
            </span>
          )}
        </div>
        <button
          type="button"
          onClick={exportCsv}
          disabled={rows.length === 0}
          className="rounded border border-gray-200 px-2.5 py-1 text-xs text-gray-600 transition-colors hover:bg-gray-50 disabled:opacity-40"
        >
          Export CSV
        </button>
      </div>

      {loading && <p className="py-8 text-center text-sm text-gray-400">Loading history…</p>}

      {!loading && rows.length === 0 && (
        <p className="py-8 text-center text-sm text-gray-400">
          No logs in this period. Entries appear here once a day is submitted.
        </p>
      )}

      {!loading && rows.length > 0 && (
        <div
          className="relative overflow-auto rounded-lg border border-gray-200"
          style={{ maxHeight: 'calc(100vh - 20rem)' }}
        >
          <table className="border-separate" style={{ borderSpacing: 0 }}>
            <thead>
              <tr>
                <th className={th + ' sticky z-30 bg-gray-100 text-gray-600'}
                    style={{ left: L_DATE, top: 0, minWidth: W_DATE }}>Date</th>
                <th className={th + ' sticky z-30 bg-gray-100 text-gray-600'}
                    style={{ left: L_CODE, top: 0, minWidth: W_CODE }}>Staff</th>
                <th className={th + ' sticky z-30 bg-gray-100 text-gray-600'}
                    style={{ left: L_NAME, top: 0, minWidth: W_NAME }}>Name</th>
                <th className={th + ' sticky z-30 bg-gray-100 text-gray-600'}
                    style={{ left: L_ROLE, top: 0, minWidth: W_ROLE }}>Role</th>
                <th className={th + ' sticky z-30 border-r border-gray-300 bg-gray-100 text-gray-600'}
                    style={{ left: L_UNIT, top: 0, minWidth: W_UNIT }}>Dept / Branch</th>
                {cols.map((c) => (
                  <th key={c.key}
                      className={thWrap + ' sticky z-20 ' + FAM_HEAD[famOf(c.key)]}
                      style={{ top: 0, width: 88, minWidth: 88, maxWidth: 88 }}
                      title={c.label + (c.unit ? ' (' + c.unit + ')' : '')}>
                    <span className="block overflow-hidden leading-[1.15]"
                          style={{ display: '-webkit-box', WebkitLineClamp: 3, WebkitBoxOrient: 'vertical' }}>
                      {c.label}
                    </span>
                    {c.unit ? <span className="mt-0.5 block font-normal normal-case opacity-60">{c.unit}</span> : null}
                  </th>
                ))}
                <th className={th + ' sticky z-20 bg-[#0082BB] text-white'} style={{ top: 0 }}>Index</th>
                <th className={th + ' sticky z-20 bg-[#0082BB] text-white'} style={{ top: 0 }}>Target</th>
                <th className={th + ' sticky z-20 bg-[#0082BB] text-white'} style={{ top: 0 }}>Var</th>
                <th className={th + ' sticky z-20 bg-[#003D57] text-white'} style={{ top: 0 }}>C/F balance</th>
                <th className={th + ' sticky z-20 bg-gray-100 text-gray-600'}
                    style={{ top: 0, minWidth: 260 }}>Notes for the day</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r: HistoryGridRow, i) => {
                const rest = r.working_day === false;
                const { day, date } = dayLabel(String(r.log_date));
                const variance = num(r.variance);
                const cf = num(r.cf_variance);
                const bg = rest ? 'bg-gray-50' : i % 2 === 1 ? 'bg-gray-50/40' : 'bg-white';
                const frozen = td + ' sticky z-10 ' + bg;
                return (
                  <tr key={String(r.staff_code) + '-' + String(r.log_date)}
                      className={rest ? 'text-gray-400' : ''}>
                    <td className={frozen + ' tabular-nums'} style={{ left: L_DATE }}>
                      <span className="text-gray-400">{day}</span>{' '}
                      <span className={rest ? '' : 'text-gray-900'}>{date}</span>
                    </td>
                    <td className={frozen + ' tabular-nums text-gray-500'} style={{ left: L_CODE }}>
                      {r.staff_code}
                    </td>
                    <td className={frozen + (rest ? '' : ' text-gray-900')} style={{ left: L_NAME }}
                        title={String(r.staff_name ?? '')}>
                      {cleanName(r.staff_name)}
                      {r.auto_submitted && (
                        <span className="ml-1 rounded bg-[#FAEEDA] px-1 py-0.5 text-[10px] text-[#854F0B]">auto</span>
                      )}
                      {r.validated && <span className="ml-1 text-[10px] text-[#3B6D11]">✓</span>}
                    </td>
                    <td className={frozen + ' text-gray-500'} style={{ left: L_ROLE }}
                        title={String(r.role ?? '')}>
                      <span className="block overflow-hidden text-ellipsis" style={{ maxWidth: W_ROLE - 12 }}>
                        {r.role}
                      </span>
                    </td>
                    <td className={frozen + ' border-r border-gray-300'} style={{ left: L_UNIT }}
                        title={[dept(r), branch(r)].filter(Boolean).join(' · ')}>
                      <span className="block overflow-hidden text-ellipsis leading-tight text-gray-600"
                            style={{ maxWidth: W_UNIT - 12 }}>
                        {dept(r) || <span className="text-gray-300">—</span>}
                      </span>
                      <span className="block overflow-hidden text-ellipsis text-[10px] leading-tight text-gray-400"
                            style={{ maxWidth: W_UNIT - 12 }}>
                        {branch(r)}
                      </span>
                    </td>

                    {cols.map((c) => {
                      const v = num(r[c.key]);
                      return (
                        <td key={c.key}
                            className={td + ' tabular-nums text-gray-700 '
                              + (rest ? bg : v > 0 ? FAM_CELL[famOf(c.key)] : bg)}>
                          {fmt(r[c.key])}
                        </td>
                      );
                    })}

                    <td className={td + ' ' + bg + ' border-l border-gray-200 tabular-nums font-medium text-gray-900'}>
                      {num(r.index) === 0 ? <span className="text-gray-300">0</span> : num(r.index).toFixed(1)}
                    </td>
                    <td className={td + ' ' + bg + ' tabular-nums text-gray-500'}>
                      {rest ? <span className="text-gray-300">—</span> : num(r.target).toFixed(1)}
                    </td>
                    <td className={td + ' ' + bg + ' tabular-nums'}>
                      {rest
                        ? <span className="rounded bg-gray-100 px-1.5 py-0.5 text-[10px] text-gray-400">Rest</span>
                        : <span className={variance < 0 ? 'text-rose-600' : variance > 0 ? 'text-[#3B6D11]' : 'text-gray-400'}>
                            {signed(variance)}
                          </span>}
                    </td>
                    <td className={td + ' ' + bg + ' tabular-nums font-medium'}>
                      <span className={cf < 0 ? 'text-rose-700' : cf > 0 ? 'text-[#3B6D11]' : 'text-gray-400'}>
                        {signed(cf)}
                      </span>
                    </td>
                    <td className={td + ' ' + bg + ' max-w-[380px] text-gray-600'}
                        title={[r.remarks, r.manager_note && ('Manager: ' + r.manager_note)]
                          .filter(Boolean).join('  |  ')}>
                      <span className="block overflow-hidden text-ellipsis" style={{ maxWidth: 370 }}>
                        {r.remarks ? <span>· {r.remarks}</span> : <span className="text-gray-300">—</span>}
                        {r.manager_note
                          ? <span className="ml-2 text-brand-primary">· Manager: {r.manager_note}</span>
                          : null}
                      </span>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
"""


def main():
    apply = "--apply" in sys.argv
    for p in (API, APITS, COMP):
        if not os.path.isfile(p):
            print("ABORT: %s not found." % p)
            return 1

    api = open(API, encoding="utf-8").read()
    ts = open(APITS, encoding="utf-8").read()
    cur = open(COMP, encoding="utf-8").read()

    if "_roster_dims" in api:
        print("ABORT: api_branch_log already has _roster_dims - Phase 3c looks applied.")
        return 1
    if "cleanName" not in cur:
        print("ABORT: HistoryGrid is not at Phase 3b - apply patch_p3b_grid_filters.py first.")
        return 1

    for label, hay, old in (("helper", api, API_HELPER_ANCHOR),
                            ("row fields", api, API_ROW_OLD),
                            ("api.ts", ts, TS_OLD)):
        if hay.count(old) != 1:
            print("ABORT: %s anchor matched %d times (expected 1)." % (label, hay.count(old)))
            return 1

    api = api.replace(API_HELPER_ANCHOR, API_HELPER, 1)
    api = api.replace(API_ROW_OLD, API_ROW_NEW, 1)
    ts = ts.replace(TS_OLD, TS_NEW, 1)
    print("  ok  api_branch_log - roster join (_roster_dims / _dims_for)")
    print("  ok  api_branch_log - department + branch on grid rows")
    print("  ok  api.ts - HistoryGridRow department/branch")

    for token in ("deptFilter", "branchFilter", "Dept / Branch", "All departments"):
        if token not in COMPONENT:
            print("ABORT: embedded component missing '%s'." % token)
            return 1
    # Braces and parens only - the cleanName regex carries an unbalanced ]
    # by design (character class). tsc is the real structural gate.
    for o, c in (("{", "}"), ("(", ")")):
        if COMPONENT.count(o) != COMPONENT.count(c):
            print("ABORT: embedded component unbalanced %s%s." % (o, c))
            return 1
    print("  ok  embedded component validated (%d lines)" % (COMPONENT.count("\n") + 1))

    if not apply:
        print("\nDRY RUN - nothing written. Re-run with --apply.")
        return 0

    for path, content in ((API, api), (APITS, ts), (COMP, COMPONENT)):
        shutil.copy2(path, path + BACKUP_SUFFIX)
        open(path, "w", encoding="utf-8", newline="").write(content)
        print("APPLIED %s" % path)

    print("\nNext:")
    print("  1. pushd frontend\\web && pnpm tsc --noEmit && popd && echo TSC_PASSED")
    print("  2. restart uvicorn - the endpoint now joins the roster")
    return 0


if __name__ == "__main__":
    sys.exit(main())
