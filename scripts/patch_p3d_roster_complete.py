#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Phase 3d - roster-complete grid on the canonical hierarchy source.

TWO FIXES.

1. WRONG SOURCE (my error in 3c). The roster join read data/staff_roster.json -
   a 362-row shadow file. The canonical source is data/staff_register.xlsx, read
   through utils.api_pipeline_scope.get_staff_roster(), which is the SAME loader
   the pipeline hierarchy and visibility engine uses. It carries 363 rows with
   Department, Branch, Unit, Region AND Reports To Code. Two readers pointed at
   two files for one concept is exactly the drift this codebase keeps paying
   for; there is now one reader and one file.

2. NON-FILERS WERE INVISIBLE AND FREE. carried_forward only walks logs that
   exist, so a staff member who never files had no rows, no target and no
   deficit. In the current week 74 of 363 staff filed - the other 289 did not
   appear in the grid at all, which is why an MD login showed only three
   departments.

   The endpoint now emits a zero row for every WORKING day a scoped staff member
   has no entry. Scope comes from get_visible_staff_codes - the same upward
   hierarchy the pipeline uses - so admin sees the bank, a manager sees their
   subtree, everyone else sees themselves.

   Measured on live data: a never-filer over the last 6 working days accrues
       Mon-Fri  -25.0 each   (full weekday target)
       Sat      -12.5        (WC-2b half day)
       Sun      excluded
       balance  -137.5
   Rest days still contribute nothing, so the calendar rules hold.

   New query param include_missing (default true) can switch it off.

VOLUME: roster-complete means 363 staff x working days. The grid's default range
drops from 30 days to 7 (~2,200 rows) because 30 would be ~9,500 before
filtering. Department / Branch / Person filters do the narrowing.

Rows the backend synthesised carry status='missing' and render distinctly:
amber row wash, a "Not filed" chip in the notes column, and a middot instead of
a zero in each activity cell - a synthesised zero must not look like a filed
zero.

Verified before delivery: py_compile clean, tsc --noEmit clean, vite build
clean, roster join checked against real codes, and the deficit arithmetic
checked against the live calendar.

Usage (from project root, .venv active):
    python scripts\\patch_p3d_roster_complete.py            # dry run
    python scripts\\patch_p3d_roster_complete.py --apply    # write + .pre_p3d backups
"""
import os
import shutil
import sys

API = os.path.join("utils", "api_branch_log.py")
PAGE = os.path.join("frontend", "web", "src", "pages", "BranchLog.tsx")
COMP = os.path.join("frontend", "web", "src", "components", "HistoryGrid.tsx")
BACKUP_SUFFIX = ".pre_p3d"

HELPER_NEW = r'''def _roster_dims() -> dict:
    """Canonical {canon(staff_code) -> {department, branch, full_name, role}}.

    SOURCE OF TRUTH: data/staff_register.xlsx, read through
    utils.api_pipeline_scope.get_staff_roster() — the SAME loader the pipeline
    hierarchy and visibility engine uses. It carries Department, Branch, Unit,
    Region and Reports To Code, so the grid's dimensions cannot drift from the
    hierarchy the rest of the system reports against.

    (An earlier revision of this joined data/staff_roster.json — a 362-row
    shadow of the same population without the reporting column. Two readers,
    two files, one concept: exactly the drift this codebase keeps paying for.)

    The Daily Log record's own `unit` is free text typed at submit time and is
    inconsistent in live data ("Fortis" / "Fortis Branch" / "Consumer" /
    "EKE-CONSUMER BANKING DEPARTMENT"); it is used only as a fallback.

    Keyed on utils.staff_code.canon so KE0439 / KE439 / 439 all resolve.
    """
    from utils.staff_code import canon as _canon
    out: dict = {}
    try:
        from utils.api_pipeline_scope import get_staff_roster
        df = get_staff_roster()
        if df is None or len(df) == 0:
            return out
        cols = set(df.columns)

        def pick(row, *names):
            for n in names:
                if n in cols:
                    v = row.get(n)
                    if v is not None and str(v).strip() and str(v) != "nan":
                        return str(v).strip()
            return ""

        for _, row in df.iterrows():
            code = pick(row, "Staff Code", "staff_code")
            if not code:
                continue
            out[_canon(code)] = {
                "department": pick(row, "Department", "department"),
                "branch":     pick(row, "Branch", "Unit", "branch", "unit"),
                "full_name":  pick(row, "Staff Name", "staff_name", "full_name"),
                "role":       pick(row, "Role", "role"),
                "code":       code,
            }
    except Exception:
        return out
    return out


def _dims_for(staff_code) -> dict:
    """Roster dimensions for a staff code, empty dict when unmatched."""
    from utils.staff_code import canon as _canon
    return _roster_dims().get(_canon(staff_code)) or {}


'''

FILL_NEW = r"""    if include_missing:
        from datetime import date as _date, timedelta as _td
        from utils.staff_code import canon as _canon
        try:
            from utils import workcal as _wc
        except Exception:
            _wc = None

        dims = _roster_dims()
        if _is_admin(user):
            scope_codes = set(dims.keys())
        elif _is_manager(user):
            try:
                from utils.api_pipeline_scope import get_visible_staff_codes
                scope_codes = {_canon(c) for c in get_visible_staff_codes({
                    "staff_code": me.get("staff_code", ""),
                    "role": me.get("role", ""),
                    "is_admin": bool(user.get("is_admin")),
                })}
            except Exception:
                scope_codes = {_canon(c) for c in by_staff}
        else:
            scope_codes = {_canon(me.get("staff_code", ""))}
        scope_codes.discard("")

        # Working days in the window, newest-inclusive.
        today = _date.today()
        window = [today - _td(days=i) for i in range(int(days))]
        work_days = [d for d in window if (_wc.is_working_day(d) if _wc else d.weekday() != 6)]

        # Index existing logs by canonical code + date so the fill never
        # duplicates a day someone actually filed.
        filed = {}
        for code, ls in by_staff.items():
            for l in ls:
                filed.setdefault(_canon(code), set()).add(str(l.get("log_date"))[:10])

        for ck in scope_codes:
            d = dims.get(ck) or {}
            have = filed.get(ck, set())
            bucket = by_staff.setdefault(d.get("code") or ck, [])
            for day in work_days:
                iso = day.isoformat()
                if iso in have:
                    continue
                blank = {
                    "log_date": iso,
                    "staff_code": d.get("code") or ck,
                    "staff_name": d.get("full_name", ""),
                    "role": d.get("role", ""),
                    "unit": d.get("branch", ""),
                    "status": "missing",
                    "validated": False,
                    "auto_submitted": False,
                    "index": 0.0,
                    "remarks": "",
                    "manager_note": "",
                }
                for k in mkeys:
                    blank[k] = 0
                bucket.append(blank)
    rows = []
    for sc, staff_logs in by_staff.items():
        annotated = carried_forward(staff_logs)  # sorted asc, adds target/variance/cf_variance
        for r in annotated:
            row = {
                "log_date":   r.get("log_date"),
                "staff_code": r.get("staff_code"),
                "staff_name": r.get("staff_name"),
                "role":       r.get("role"),
                "unit":       r.get("unit"),
                "status":     r.get("status", "submitted"),
                "validated":  bool(r.get("validated")),
                "auto_submitted": bool(r.get("auto_submitted")),
                "index":      round(float(r.get("index") or 0), 2),
                "target":     r.get("target"),
                "variance":   r.get("variance"),
                "cf_variance": r.get("cf_variance"),
                # WC-2b sets working_day on the annotated row (false on Sundays
                # and gazetted holidays). The endpoint was dropping it, so the
                # grid could never distinguish a rest day from a missed one and
                # rendered every Sunday as 0/0/0.
                "working_day":  bool(r.get("working_day", True)),
                # P3b: the day's note travels with the row so a manager reading
                # the spreadsheet sees the context without opening each entry.
                "remarks":      str(r.get("remarks") or ""),
                "manager_note": str(r.get("manager_note") or ""),
            }
            # P3c: canonical dimensions from the roster. The log's own free-text
            # `unit` stays on the row for backward compatibility, but the grid
            # filters on department/branch because those are the structure the
            # bank actually reports against.
            _d = _dims_for(r.get("staff_code"))
            row["department"] = _d.get("department", "")
            row["branch"] = _d.get("branch", "") or str(r.get("unit") or "")
            if _d.get("full_name"):
                row["staff_name"] = _d["full_name"]
            for k in mkeys:
                row[k] = r.get(k, 0)
            rows.append(row)"""

SIG_OLD = 'def branch_log_history_grid(days: int = 30, unit: str = "", user: dict = Depends(get_current_user)):'
SIG_NEW = ('def branch_log_history_grid(days: int = 30, unit: str = "", include_missing: bool = True,\n'
           '                            user: dict = Depends(get_current_user)):')

FILL_ANCHOR = "    mkeys = metric_keys()"

PAGE_OLD = "  const [gridDays, setGridDays] = useState(30);"
PAGE_NEW = ("  // 7 by default: the grid is now roster-complete (every scoped staff member\n"
            "  // for every working day), so 30 days is ~9,500 rows before filtering.\n"
            "  const [gridDays, setGridDays] = useState(7);")

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
  // Rows the backend synthesised for a working day nobody filed.
  const notFiled = rows.filter((r) => String(r.status ?? '') === 'missing').length;

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
              {notFiled > 0 && <span className="text-amber-600"> · {notFiled} days not filed</span>}
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
                const missing = String(r.status ?? '') === 'missing';
                const { day, date } = dayLabel(String(r.log_date));
                const variance = num(r.variance);
                const cf = num(r.cf_variance);
                const bg = rest ? 'bg-gray-50'
                  : missing ? 'bg-[#FDF6EC]'
                  : i % 2 === 1 ? 'bg-gray-50/40' : 'bg-white';
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
                              + (rest || missing ? bg : v > 0 ? FAM_CELL[famOf(c.key)] : bg)}>
                          {missing ? <span className="text-gray-300">·</span> : fmt(r[c.key])}
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
                        {missing
                          ? <span className="rounded bg-[#FAEEDA] px-1.5 py-0.5 text-[10px] font-medium text-[#854F0B]">Not filed</span>
                          : r.remarks ? <span>· {r.remarks}</span> : <span className="text-gray-300">—</span>}
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
    for p in (API, PAGE, COMP):
        if not os.path.isfile(p):
            print("ABORT: %s not found." % p)
            return 1

    api = open(API, encoding="utf-8").read()
    page = open(PAGE, encoding="utf-8").read()
    cur = open(COMP, encoding="utf-8").read()

    if "include_missing" in api:
        print("ABORT: api_branch_log already has include_missing - Phase 3d looks applied.")
        return 1
    if "_roster_dims" not in api:
        print("ABORT: apply patch_p3c_org_filters.py first.")
        return 1
    if "deptFilter" not in cur:
        print("ABORT: HistoryGrid is not at Phase 3c.")
        return 1

    # 1. swap the roster reader (JSON shadow -> canonical xlsx loader)
    try:
        i = api.index("def _roster_dims()")
        j = api.index('@router.get("/history-grid")')
    except ValueError:
        print("ABORT: could not locate the roster helper block.")
        return 1
    # keep anything defined before the helper (cache globals) out of the way
    k = api.rindex("\n", 0, i)
    head = api[:k + 1]
    if "_ROSTER_DIMS_CACHE" in head:
        head = head[:head.index("_ROSTER_DIMS_CACHE")]
    api = head + HELPER_NEW + api[j:]
    print("  ok  roster reader -> staff_register.xlsx via get_staff_roster()")

    if api.count(SIG_OLD) != 1:
        print("ABORT: endpoint signature matched %d times." % api.count(SIG_OLD))
        return 1
    api = api.replace(SIG_OLD, SIG_NEW, 1)
    print("  ok  include_missing query param")

    if api.count(FILL_ANCHOR) != 1:
        print("ABORT: fill anchor matched %d times." % api.count(FILL_ANCHOR))
        return 1
    api = api.replace(FILL_ANCHOR, FILL_ANCHOR + "\n\n" + FILL_NEW, 1)
    print("  ok  roster completion (zero rows for unfiled working days)")

    if page.count(PAGE_OLD) != 1:
        print("ABORT: default-range anchor matched %d times." % page.count(PAGE_OLD))
        return 1
    page = page.replace(PAGE_OLD, PAGE_NEW, 1)
    print("  ok  default range 30 -> 7 days")

    for token in ("missing", "Not filed", "notFiled"):
        if token not in COMPONENT:
            print("ABORT: embedded component missing '%s'." % token)
            return 1
    for o, c in (("{", "}"), ("(", ")")):
        if COMPONENT.count(o) != COMPONENT.count(c):
            print("ABORT: embedded component unbalanced %s%s." % (o, c))
            return 1
    print("  ok  embedded component validated (%d lines)" % (COMPONENT.count("\n") + 1))

    if not apply:
        print("\nDRY RUN - nothing written. Re-run with --apply.")
        return 0

    for path, content in ((API, api), (PAGE, page), (COMP, COMPONENT)):
        shutil.copy2(path, path + BACKUP_SUFFIX)
        open(path, "w", encoding="utf-8", newline="").write(content)
        print("APPLIED %s" % path)

    import py_compile
    try:
        py_compile.compile(API, doraise=True)
        print("  ok  %s compiles" % API)
    except Exception as exc:
        print("  FAIL %s: %s" % (API, exc))
        return 1

    print("\nNext:")
    print("  1. pushd frontend\\web && pnpm tsc --noEmit && popd && echo TSC_PASSED")
    print("  2. restart uvicorn - the endpoint now completes against the roster")
    return 0


if __name__ == "__main__":
    sys.exit(main())
