#!/usr/bin/env python
# -*- coding: utf-8 -*-
r"""
A5 - reporting periods (quarters and year-to-date), and "Index analytics".

YOUR ASKS
  "on the drop of looking at 7,30,90 days we need to have an year to date, then
   probably each quarter across"
  "on the analytics we state index analytics"

TWO KINDS OF WINDOW, and the distinction is why this needed a backend change:

    ROLLING   "last 30 days"  - moves every day
    CALENDAR  Q2, year to date - FIXED boundaries

A quarter cannot be expressed as a day count without drifting as the year
advances, so /leaderboard and /analytics now accept an explicit start/end
alongside days. Rolling windows still send days; nothing existing changes.

frontend/web/src/lib/period.ts is the SINGLE definition, used by both the
ranking and the analytics - so the two can never be looking at different windows
while appearing to agree. Quarters that have not started yet are not offered: an
empty chart reads as a failure rather than as "not yet", and a future quarter in
a dropdown is noise. The current quarter is labelled as such and clipped to
today.

RENAMED to "Index analytics" - on the tab and on the panel heading. These
measure the productivity INDEX; pipeline analytics measures something else
entirely, and two things both called "Analytics" would be a standing source of
confusion once both exist.

Verified: py_compile clean, tsc --noEmit clean, vite build clean.

Usage (from project root, .venv active):
    python scripts\patch_a5_periods.py            # dry run
    python scripts\patch_a5_periods.py --apply    # write + .pre_a5 backups
"""
import os
import shutil
import sys

PER = os.path.join("frontend", "web", "src", "lib", "period.ts")
APITS = os.path.join("frontend", "web", "src", "lib", "api.ts")
LEAD = os.path.join("frontend", "web", "src", "components", "Leaderboard.tsx")
ANAL = os.path.join("frontend", "web", "src", "components", "DailyLogAnalytics.tsx")
PAGE = os.path.join("frontend", "web", "src", "pages", "PipelineManagerQueues.tsx")
API = os.path.join("utils", "api_branch_log.py")
BACKUP_SUFFIX = ".pre_a5"

PER_NEW = r'''// Shared reporting period. One definition, used by the ranking and the
// analytics, so the two can never be looking at different windows while
// appearing to agree.
//
// Two kinds of window, and the distinction is not cosmetic:
//
//   ROLLING   "last 30 days" — moves every day, good for "how are we doing now"
//   CALENDAR  Q2, year to date — fixed boundaries, good for "how did we do in
//             the period the bank reports on"
//
// A quarter cannot be expressed as a day count without drifting as the year
// advances, which is why the API takes an explicit start/end for these rather
// than a number of days.

export type PeriodKind = 'rolling' | 'calendar';

export interface Period {
  key: string;
  label: string;
  kind: PeriodKind;
  days?: number;             // rolling
  start?: string;            // calendar, YYYY-MM-DD
  end?: string;
}

function iso(d: Date): string {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
}

/** Quarter boundaries for a year, clipped so a future quarter never runs past today. */
function quarter(year: number, q: number): { start: string; end: string } {
  const startMonth = (q - 1) * 3;
  const start = new Date(year, startMonth, 1);
  const end = new Date(year, startMonth + 3, 0);      // day 0 = last of prev month
  const today = new Date();
  return { start: iso(start), end: iso(end > today ? today : end) };
}

export function periods(now = new Date()): Period[] {
  const year = now.getFullYear();
  const thisQ = Math.floor(now.getMonth() / 3) + 1;

  const out: Period[] = [
    { key: '7', label: 'Last 7 days', kind: 'rolling', days: 7 },
    { key: '30', label: 'Last 30 days', kind: 'rolling', days: 30 },
    { key: '90', label: 'Last 90 days', kind: 'rolling', days: 90 },
    { key: 'ytd', label: `Year to date (${year})`, kind: 'calendar',
      start: `${year}-01-01`, end: iso(now) },
  ];

  // Quarters that have started. A quarter nobody has reached yet is noise in a
  // dropdown, and an empty chart reads as a failure rather than as "not yet".
  for (let q = 1; q <= thisQ; q += 1) {
    const { start, end } = quarter(year, q);
    out.push({
      key: `q${q}`,
      label: q === thisQ ? `Q${q} ${year} (current)` : `Q${q} ${year}`,
      kind: 'calendar', start, end,
    });
  }
  return out;
}

export const DEFAULT_PERIOD_KEY = '30';

export function findPeriod(key: string, now = new Date()): Period {
  const all = periods(now);
  return all.find((p) => p.key === key) ?? all[1];
}

/** The query arguments this period implies — days, or an explicit window. */
export function periodArgs(p: Period): { days?: number; start?: string; end?: string } {
  return p.kind === 'rolling'
    ? { days: p.days }
    : { start: p.start, end: p.end };
}

/** How many days the period spans, for anything that still needs a count. */
export function periodDays(p: Period): number {
  if (p.kind === 'rolling') return p.days ?? 30;
  const a = new Date(`${p.start}T00:00:00`);
  const b = new Date(`${p.end}T00:00:00`);
  return Math.max(1, Math.round((b.getTime() - a.getTime()) / 86400000) + 1);
}
'''

LB_NEW = r'''@router.get("/leaderboard")
def branch_log_leaderboard(days: int = 30, level: str = "staff", role: str = "",
                           branch: str = "", unit: str = "",
                           start: str = "", end: str = "",
                           user: dict = Depends(get_current_user)):
    """Cumulative ranking, drillable: staff -> role -> branch -> unit.

    Every person is counted EXACTLY ONCE at each level, so a level always sums
    to the same bank total. Ranking is a different lens from index ownership:
    the ruling that a person's index belongs to their employing unit governs
    what a unit's OWN number is; this asks how much activity sits beneath a
    unit in total. The SOLID line is used for the unit roll-up — the dotted
    line would place a branch RM in both Fortis and Consumer and the level
    would stop summing.

    level:  staff | role | branch | unit
    role/branch/unit: optional filters, so a Branch Manager can rank tellers
    inside their own branch.

    Scope is the canonical engine (get_visible_staff_codes), the same call the
    history grid and the pipeline use.
    """
    from utils.branch_log import metric_keys
    from utils.branch_log_analytics import carried_forward, _target_for
    from utils.staff_code import canon as _canon_l

    me = _identity(user)
    my_code = str(me.get("staff_code", "") or "")

    _stored = {}
    try:
        from utils.core import UserManager
        _stored = UserManager().users.get(str(user.get("username", "")) or "") or {}
    except Exception:
        _stored = {}
    user_ctx = {
        "staff_code":   my_code or str(_stored.get("staff_code", "") or ""),
        "role":         me.get("role", "") or str(_stored.get("role", "") or ""),
        "full_name":    str(_stored.get("full_name", "") or me.get("staff_name", "") or ""),
        "unit":         me.get("unit", "") or str(_stored.get("unit", "") or ""),
        "department":   str(_stored.get("department", "") or ""),
        "is_admin":     bool(user.get("is_admin") or _stored.get("is_admin")),
        "can_view_all": bool(user.get("can_view_all") or _stored.get("can_view_all")),
    }
    try:
        from utils.api_pipeline_scope import get_visible_staff_codes
        visible = {_canon_l(c) for c in get_visible_staff_codes(user_ctx)}
    except Exception:
        visible = set()
    visible.discard("")
    if not visible and user_ctx["staff_code"]:
        visible = {_canon_l(user_ctx["staff_code"])}

    dims = _roster_dims()
    try:
        from utils.org_validator import unit_for_role
    except Exception:
        unit_for_role = lambda _r: ""      # noqa: E731

    # A rolling window (days) or an EXPLICIT one (start/end). Quarters and
    # year-to-date are fixed calendar windows, not "the last N days", so they
    # cannot be expressed as a day count without drifting as the year advances.
    blm = BranchLogManager()
    if start or end:
        lo = str(start or "0000-01-01")[:10]
        hi = str(end or "9999-12-31")[:10]
        pool = [l for l in blm.get_history(days=400)
                if lo <= str(l.get("log_date"))[:10] <= hi]
    else:
        pool = blm.get_history(days=days)
    logs = [l for l in pool if _canon_l(l.get("staff_code")) in visible]

    # Per-staff cumulative: index actually achieved, target that applied, and
    # the closing carried-forward balance from the same read-time engine the
    # grid uses — so a leaderboard can never disagree with the history.
    by_staff = {}
    for l in logs:
        by_staff.setdefault(_canon_l(l.get("staff_code")), []).append(l)

    people = []
    for ck, dd in dims.items():
        code = dd.get("code") or ck
        if _canon_l(code) not in visible:
            continue
        r = str(dd.get("role") or "")
        b = str(dd.get("branch") or "")
        u = unit_for_role(r) or ""
        if role and r != role:
            continue
        if branch and b != branch:
            continue
        if unit and u != unit:
            continue
        mine = by_staff.get(_canon_l(code), [])
        rows = carried_forward(mine) if mine else []
        idx = round(sum(float(x.get("index") or 0) for x in rows), 2)
        tgt = round(sum(float(x.get("target") or 0) for x in rows), 2)
        # MET vs NOT MET, per person-day. Only days that CARRIED a target count:
        # rest days and excused days have no target, so counting them either way
        # would flatter or punish people for days nobody expected work on.
        scored = [x for x in rows if float(x.get("target") or 0) > 0]
        met = sum(1 for x in scored
                  if float(x.get("index") or 0) >= float(x.get("target") or 0))
        people.append({
            "staff_code": code, "staff_name": dd.get("full_name", ""),
            "role": r, "branch": b, "unit": u,
            "index": idx, "target": tgt,
            "days_filed": len(mine),
            "validated": sum(1 for x in mine if x.get("validated")),
            "cf_variance": rows[-1].get("cf_variance", 0) if rows else 0,
            "met_days": met,
            "scored_days": len(scored),
        })

    def agg(rows, keyfn, label):
        out = {}
        for p in rows:
            k = keyfn(p) or "(unassigned)"
            e = out.setdefault(k, {label: k, "index": 0.0, "target": 0.0,
                                   "headcount": 0, "days_filed": 0, "validated": 0,
                                   "met_days": 0, "scored_days": 0})
            e["index"] += p["index"]; e["target"] += p["target"]
            e["headcount"] += 1; e["days_filed"] += p["days_filed"]
            e["validated"] += p["validated"]
            e["met_days"] += p["met_days"]; e["scored_days"] += p["scored_days"]
        for e in out.values():
            e["index"] = round(e["index"], 1)
            e["target"] = round(e["target"], 1)
            e["achievement"] = round((e["index"] / e["target"]) * 100, 1) if e["target"] else 0.0
            e["index_per_head"] = round(e["index"] / e["headcount"], 1) if e["headcount"] else 0.0
            e["met_rate"] = (round(e["met_days"] / e["scored_days"] * 100, 1)
                             if e["scored_days"] else 0.0)
        return list(out.values())

    if level == "role":
        rows = agg(people, lambda p: p["role"], "name")
        sort_key = "index_per_head"
    elif level == "branch":
        rows = agg(people, lambda p: p["branch"], "name")
        sort_key = "index"
    elif level == "unit":
        rows = agg(people, lambda p: p["unit"], "name")
        sort_key = "index"
    else:
        level = "staff"
        for p in people:
            p["achievement"] = round((p["index"] / p["target"]) * 100, 1) if p["target"] else 0.0
            p["met_rate"] = (round(p["met_days"] / p["scored_days"] * 100, 1)
                             if p["scored_days"] else 0.0)
        rows = people
        sort_key = "index"

    rows.sort(key=lambda r: -float(r.get(sort_key) or 0))
    for i, r in enumerate(rows, 1):
        r["rank"] = i

    total_index = round(sum(float(r.get("index") or 0) for r in rows), 1)
    met_total = sum(int(p.get("met_days") or 0) for p in people)
    scored_total = sum(int(p.get("scored_days") or 0) for p in people)
    return {
        "level": level, "days": days, "start": start, "end": end, "rows": rows,
        "total_index": total_index,
        "met_days": met_total, "scored_days": scored_total,
        "met_rate": round(met_total / scored_total * 100, 1) if scored_total else 0.0,
        "total_headcount": len(people),
        "filters": {"role": role, "branch": branch, "unit": unit},
        "roles": sorted({p["role"] for p in people if p["role"]}),
        "branches": sorted({p["branch"] for p in people if p["branch"]}),
        "units": sorted({p["unit"] for p in people if p["unit"]}),
    }


'''

ANAP_NEW = r'''def branch_log_analytics(days: int = 30, unit: str = "",
                         start: str = "", end: str = "",
                         user: dict = Depends(get_current_user)):
    """Daily-log analytics, scope-aware. Includes the 80/20 impact-tier breakdown (for the pie),
    validation split, and totals. Admin sees all; manager sees subtree; else self."""
    from utils.branch_log_analytics import impact_breakdown, high_impact_keys
    me = _identity(user)
    blm = BranchLogManager()
    try:
        from utils.branch_log_state import run_maintenance
        run_maintenance(blm)
    except Exception:
        pass
    if start or end:
        _lo = str(start or "0000-01-01")[:10]
        _hi = str(end or "9999-12-31")[:10]
        logs = [l for l in blm.get_history(days=400)
                if _lo <= str(l.get("log_date"))[:10] <= _hi]
    else:
        logs = blm.get_history(days=days)
    if unit and unit != "All":
        logs = [l for l in logs if str(l.get("unit", "")) == unit]

    # Scope from the CANONICAL engine, as the history grid and leaderboard do.
    # This endpoint previously carried its own _is_admin/_is_manager rules, so
    # analytics and the grid could disagree about the same population — the
    # second-hierarchy fault fixed in P3f, still present here.
    from utils.staff_code import canon as _canon_a
    _stored = {}
    try:
        from utils.core import UserManager
        _stored = UserManager().users.get(str(user.get("username", "")) or "") or {}
    except Exception:
        _stored = {}
    _ctx = {
        "staff_code":   me.get("staff_code", "") or str(_stored.get("staff_code", "") or ""),
        "role":         me.get("role", "") or str(_stored.get("role", "") or ""),
        "full_name":    str(_stored.get("full_name", "") or me.get("staff_name", "") or ""),
        "unit":         me.get("unit", "") or str(_stored.get("unit", "") or ""),
        "department":   str(_stored.get("department", "") or ""),
        "is_admin":     bool(user.get("is_admin") or _stored.get("is_admin")),
        "can_view_all": bool(user.get("can_view_all") or _stored.get("can_view_all")),
    }
    try:
        from utils.api_pipeline_scope import get_visible_staff_codes
        _visible = {_canon_a(c) for c in get_visible_staff_codes(_ctx)}
    except Exception:
        _visible = set()
    _visible.discard("")
    if not _visible and _ctx["staff_code"]:
        _visible = {_canon_a(_ctx["staff_code"])}
    scoped = [l for l in logs if _canon_a(l.get("staff_code")) in _visible]

'''

TSL_NEW = r'''export async function fetchBranchLogLeaderboard(opts: {
  days?: number; level?: string; role?: string; branch?: string; unit?: string;
  start?: string; end?: string;
} = {}): Promise<Leaderboard> {
  const q = new URLSearchParams();
  if (opts.days) q.set('days', String(opts.days));
  if (opts.start) q.set('start', opts.start);
  if (opts.end) q.set('end', opts.end);
  if (opts.level) q.set('level', opts.level);
  if (opts.role) q.set('role', opts.role);
  if (opts.branch) q.set('branch', opts.branch);
  if (opts.unit) q.set('unit', opts.unit);
  const s = q.toString();
  return getJson<Leaderboard>(`/branch-log/leaderboard${s ? `?${s}` : ''}`);
}

'''

TSA_NEW = r'''export async function fetchBranchLogAnalytics(
  days = 30, unit = '', start = '', end = '',
): Promise<BranchLogAnalytics> {
  const p = new URLSearchParams();
  if (days) p.set('days', String(days));
  if (unit) p.set('unit', unit);
  if (start) p.set('start', start);   // calendar window (quarter / YTD)
  if (end) p.set('end', end);
  const q = `?${p.toString()}`;
  return getJson<BranchLogAnalytics>(`/branch-log/analytics${q}'''

LEAD_NEW = r'''// A2 — cumulative ranking, drillable: unit → branch → role → individual.
//
// Every person is counted exactly once at each level, so switching level never
// changes the bank total — only how it is partitioned. That is the property
// that makes a leaderboard trustworthy: if the totals moved when you changed
// the lens, nobody could tell which number was real.
//
// Filters compose downward. Pick a unit and the branch list narrows to that
// unit; pick a branch and the role list narrows to that branch. So "rank the
// tellers in Fortis" is two clicks, and "rank branches inside CCB" is one.
//
// Per-staff totals come from carried_forward() server-side — the same engine
// the history grid uses — so this can never disagree with the history.

import { useCallback, useEffect, useMemo, useState } from 'react';
import { PieChart, Pie, Cell, ResponsiveContainer, Tooltip } from 'recharts';
import { Card } from '@/components/Card';
import { useToast } from '@/components/Toast';
import { fetchBranchLogLeaderboard, type Leaderboard, type LeaderboardRow } from '@/lib/api';
import { periods, findPeriod, periodArgs, DEFAULT_PERIOD_KEY } from '@/lib/period';

type Level = 'unit' | 'branch' | 'role' | 'staff';

const LEVELS: { key: Level; label: string; hint: string }[] = [
  { key: 'unit',   label: 'Units',       hint: 'Everything beneath each MD-reporting unit' },
  { key: 'branch', label: 'Branches',    hint: 'The 16 branches and Head Office' },
  { key: 'role',   label: 'Roles',       hint: 'Ranked by index per head, so a big role cannot win on size' },
  { key: 'staff',  label: 'Individuals', hint: 'Every person you can see' },
];

// Medal tint for the top three, brand palette only.
const MEDAL = ['bg-[#BED600] text-[#3B6D11]', 'bg-[#E6F1FB] text-[#0C447C]', 'bg-[#FAEEDA] text-[#854F0B]'];

function bar(pct: number): string {
  if (pct >= 100) return 'bg-[#669438]';
  if (pct >= 75) return 'bg-[#BED600]';
  if (pct >= 50) return 'bg-[#E0A02B]';
  return 'bg-[#C4536F]';
}

export default function Leaderboard() {
  const { toast } = useToast();
  const [level, setLevel] = useState<Level>('branch');
  const [periodKey, setPeriodKey] = useState(DEFAULT_PERIOD_KEY);
  const [unit, setUnit] = useState('');
  const [branch, setBranch] = useState('');
  const [role, setRole] = useState('');
  const [data, setData] = useState<Leaderboard | null>(null);
  const [loading, setLoading] = useState(false);
  // Row expansion: clicking a unit/branch/role shows the individuals inside it,
  // fetched with that row as a filter — the same drill the daily log uses.
  const [openRow, setOpenRow] = useState('');
  const [drill, setDrill] = useState<LeaderboardRow[] | null>(null);
  const [drillLoading, setDrillLoading] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      setData(await fetchBranchLogLeaderboard({
        ...periodArgs(findPeriod(periodKey)), level, unit, branch, role,
      }));
    } catch (e) {
      toast({ tone: 'danger', message: e instanceof Error ? e.message : 'Could not load the ranking.' });
      setData(null);
    } finally {
      setLoading(false);
    }
  }, [periodKey, level, unit, branch, role, toast]);

  useEffect(() => { void load(); }, [load]);
  useEffect(() => { setOpenRow(''); setDrill(null); }, [level, periodKey, unit, branch, role]);

  async function expand(r: LeaderboardRow) {
    const key = String(r.name || r.staff_code || '');
    if (openRow === key) { setOpenRow(''); setDrill(null); return; }
    setOpenRow(key);
    setDrill(null);
    setDrillLoading(true);
    try {
      // Narrow by whichever dimension this row represents, then ask for people.
      const extra = level === 'unit' ? { unit: key }
        : level === 'branch' ? { branch: key }
        : { role: key };
      const r2 = await fetchBranchLogLeaderboard({
        ...periodArgs(findPeriod(periodKey)), level: 'staff', unit, branch, role, ...extra,
      });
      setDrill(r2.rows);
    } catch (e) {
      toast({ tone: 'danger', message: e instanceof Error ? e.message : 'Could not open that row.' });
      setOpenRow('');
    } finally {
      setDrillLoading(false);
    }
  }

  const rows = data?.rows ?? [];
  const max = useMemo(
    () => Math.max(1, ...rows.map((r) => Number(r.index) || 0)), [rows]);

  const isStaff = level === 'staff';
  const nameOf = (r: LeaderboardRow) =>
    isStaff ? String(r.staff_name || r.staff_code || '') : String(r.name || '');

  return (
    <Card>
      <Card.Header>
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <h2 className="text-base font-semibold text-gray-900">Cumulative ranking</h2>
            <p className="mt-0.5 text-xs text-gray-500">
              {LEVELS.find((l) => l.key === level)?.hint}
            </p>
          </div>
          <div className="flex flex-wrap items-center gap-1.5 text-xs">
            {LEVELS.map((l) => (
              <button key={l.key} type="button" onClick={() => setLevel(l.key)}
                className={'rounded-full px-3 py-1 font-medium transition-colors '
                  + (level === l.key ? 'bg-[#0082BB] text-white'
                                     : 'text-[#005B82] hover:bg-[#0082BB]/10')}>
                {l.label}
              </button>
            ))}
            <select value={periodKey} onChange={(e) => setPeriodKey(e.target.value)}
                    className="ml-2 rounded border border-gray-200 px-2 py-1 text-xs">
              {periods().map((p) => <option key={p.key} value={p.key}>{p.label}</option>)}
            </select>
          </div>
        </div>
      </Card.Header>

      <Card.Body>
        {/* Filters compose downward: unit narrows branches, branch narrows roles. */}
        <div className="mb-3 flex flex-wrap items-center gap-2 text-xs">
          <select value={unit} onChange={(e) => { setUnit(e.target.value); setBranch(''); setRole(''); }}
                  className="max-w-[240px] rounded border border-gray-200 px-2 py-1 text-xs">
            <option value="">All units</option>
            {(data?.units ?? []).map((u) => <option key={u} value={u}>{u}</option>)}
          </select>
          <select value={branch} onChange={(e) => { setBranch(e.target.value); setRole(''); }}
                  className="max-w-[180px] rounded border border-gray-200 px-2 py-1 text-xs">
            <option value="">All branches</option>
            {(data?.branches ?? []).map((b) => <option key={b} value={b}>{b}</option>)}
          </select>
          <select value={role} onChange={(e) => setRole(e.target.value)}
                  className="max-w-[240px] rounded border border-gray-200 px-2 py-1 text-xs">
            <option value="">All roles</option>
            {(data?.roles ?? []).map((r) => <option key={r} value={r}>{r}</option>)}
          </select>
          {(unit || branch || role) && (
            <button type="button"
                    onClick={() => { setUnit(''); setBranch(''); setRole(''); }}
                    className="rounded px-1.5 py-0.5 text-[11px] text-brand-primary hover:bg-[#0082BB]/10">
              Clear
            </button>
          )}
          {data && (
            <span className="ml-auto text-gray-500">
              {data.total_headcount} staff · total index{' '}
              <span className="font-semibold text-gray-800">{data.total_index.toLocaleString()}</span>
            </span>
          )}
        </div>

        {/* Met vs not met, on the same scope as the table. A person-day counts
            only if it carried a target, so rest days and excused days neither
            flatter nor punish. */}
        {!loading && data && (data.scored_days ?? 0) > 0 && (
          <div className="mb-3 flex items-center gap-4 rounded-lg border border-gray-200 bg-gray-50/50 p-3">
            <ResponsiveContainer width={110} height={110}>
              <PieChart>
                <Pie dataKey="value" innerRadius={30} outerRadius={50} paddingAngle={2}
                     data={[{ name: 'Met', value: data.met_days ?? 0 },
                            { name: 'Not met', value: (data.scored_days ?? 0) - (data.met_days ?? 0) }]}>
                  <Cell fill="#669438" />
                  <Cell fill="#C4536F" />
                </Pie>
                <Tooltip formatter={(v: number) => [`${v} person-days`, '']} />
              </PieChart>
            </ResponsiveContainer>
            <div className="text-xs">
              <div className="text-2xl font-semibold text-[#3B6D11]">{data.met_rate ?? 0}%</div>
              <div className="text-gray-600">of person-days met the daily target</div>
              <div className="mt-1 text-gray-400">
                {(data.met_days ?? 0).toLocaleString()} met ·{' '}
                {((data.scored_days ?? 0) - (data.met_days ?? 0)).toLocaleString()} missed ·{' '}
                {(data.scored_days ?? 0).toLocaleString()} days carrying a target
              </div>
            </div>
          </div>
        )}

        {loading && <p className="py-8 text-center text-sm text-gray-400">Ranking…</p>}

        {!loading && rows.length === 0 && (
          <p className="py-8 text-center text-sm text-gray-400">
            Nothing to rank for this period and filter.
          </p>
        )}

        {!loading && rows.length > 0 && (
          <div className="overflow-auto rounded-lg border border-gray-200">
            <table className="w-full border-separate" style={{ borderSpacing: 0 }}>
              <thead>
                <tr>
                  <th className="w-10 bg-gray-100 px-2 py-2 text-left text-[11px] font-semibold uppercase text-gray-600">#</th>
                  <th className="bg-gray-100 px-2 py-2 text-left text-[11px] font-semibold uppercase text-gray-600">
                    {isStaff ? 'Staff' : LEVELS.find((l) => l.key === level)?.label}
                  </th>
                  {isStaff && (
                    <th className="bg-gray-100 px-2 py-2 text-left text-[11px] font-semibold uppercase text-gray-600">Role</th>
                  )}
                  {isStaff && (
                    <th className="bg-gray-100 px-2 py-2 text-left text-[11px] font-semibold uppercase text-gray-600">Branch</th>
                  )}
                  {!isStaff && (
                    <th className="bg-gray-100 px-2 py-2 text-right text-[11px] font-semibold uppercase text-gray-600">Staff</th>
                  )}
                  <th className="bg-[#0082BB] px-2 py-2 text-right text-[11px] font-semibold uppercase text-white">Index</th>
                  <th className="bg-gray-100 px-2 py-2 text-right text-[11px] font-semibold uppercase text-gray-600">Target</th>
                  <th className="bg-gray-100 px-2 py-2 text-left text-[11px] font-semibold uppercase text-gray-600">Achievement</th>
                  <th className="bg-gray-100 px-2 py-2 text-right text-[11px] font-semibold uppercase text-gray-600">Met %</th>
                  {!isStaff && (
                    <th className="bg-gray-100 px-2 py-2 text-right text-[11px] font-semibold uppercase text-gray-600">Per head</th>
                  )}
                  <th className="bg-gray-100 px-2 py-2 text-right text-[11px] font-semibold uppercase text-gray-600">Filed</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((r, i) => {
                  const pct = Number(r.achievement) || 0;
                  const idx = Number(r.index) || 0;
                  const bg = i % 2 === 1 ? 'bg-gray-50/40' : 'bg-white';
                  const rowKey = String(r.name || r.staff_code || i);
                  const expanded = !isStaff && openRow === rowKey;
                  return (
                    <>
                    <tr key={rowKey}>
                      <td className={`${bg} px-2 py-1.5 text-xs`}>
                        <span className={'inline-flex h-5 w-5 items-center justify-center rounded-full text-[10px] font-semibold '
                          + (r.rank && r.rank <= 3 ? MEDAL[r.rank - 1] : 'text-gray-400')}>
                          {r.rank}
                        </span>
                      </td>
                      <td className={`${bg} px-2 py-1.5 text-xs font-medium text-gray-900`}>
                        {isStaff ? nameOf(r) : (
                          <button type="button" onClick={() => void expand(r)}
                                  className="flex items-center gap-1.5 text-left hover:text-brand-primary">
                            <span className="text-gray-400">
                              {openRow === String(r.name || '') ? '▾' : '▸'}
                            </span>
                            {nameOf(r)}
                          </button>
                        )}
                      </td>
                      {isStaff && <td className={`${bg} px-2 py-1.5 text-xs text-gray-500`}>{r.role}</td>}
                      {isStaff && <td className={`${bg} px-2 py-1.5 text-xs text-gray-500`}>{r.branch}</td>}
                      {!isStaff && (
                        <td className={`${bg} px-2 py-1.5 text-right text-xs tabular-nums text-gray-500`}>
                          {r.headcount}
                        </td>
                      )}
                      <td className={`${bg} px-2 py-1.5 text-right text-xs font-semibold tabular-nums text-gray-900`}>
                        {idx.toLocaleString()}
                      </td>
                      <td className={`${bg} px-2 py-1.5 text-right text-xs tabular-nums text-gray-500`}>
                        {(Number(r.target) || 0).toLocaleString()}
                      </td>
                      <td className={`${bg} px-2 py-1.5`}>
                        <div className="flex items-center gap-2">
                          <div className="h-2 w-24 overflow-hidden rounded-full bg-gray-100">
                            <div className={`h-full ${bar(pct)}`}
                                 style={{ width: `${Math.min(Math.max(idx / max, 0), 1) * 100}%` }} />
                          </div>
                          <span className={'text-[11px] tabular-nums '
                            + (pct >= 100 ? 'text-[#3B6D11]' : pct >= 50 ? 'text-gray-600' : 'text-rose-600')}>
                            {pct}%
                          </span>
                        </div>
                      </td>
                      <td className={`${bg} px-2 py-1.5 text-right text-xs tabular-nums`}>
                        <span className={(r.met_rate ?? 0) >= 60 ? 'text-[#3B6D11]'
                          : (r.met_rate ?? 0) >= 30 ? 'text-amber-600' : 'text-rose-600'}>
                          {r.met_rate ?? 0}%
                        </span>
                      </td>
                      {!isStaff && (
                        <td className={`${bg} px-2 py-1.5 text-right text-xs tabular-nums text-gray-700`}>
                          {r.index_per_head}
                        </td>
                      )}
                      <td className={`${bg} px-2 py-1.5 text-right text-xs tabular-nums text-gray-500`}>
                        {r.days_filed}
                      </td>
                    </tr>
                    {expanded && (
                      <tr key={`${rowKey}-drill`}>
                        <td colSpan={9} className="bg-[#F7FBFD] px-6 py-3">
                          {drillLoading && (
                            <p className="text-xs text-gray-400">Opening {rowKey}…</p>
                          )}
                          {!drillLoading && drill && drill.length === 0 && (
                            <p className="text-xs text-gray-400">Nobody to show here.</p>
                          )}
                          {!drillLoading && drill && drill.length > 0 && (
                            <table className="w-full">
                              <tbody>
                                {drill.slice(0, 40).map((m) => (
                                  <tr key={m.staff_code} className="border-b border-gray-100 last:border-0">
                                    <td className="w-8 py-1 pr-2 text-[11px] tabular-nums text-gray-400">
                                      {m.rank}
                                    </td>
                                    <td className="py-1 pr-3 text-xs tabular-nums text-gray-500" style={{ width: 80 }}>
                                      {m.staff_code}
                                    </td>
                                    <td className="py-1 pr-3 text-xs text-gray-800">{m.staff_name}</td>
                                    <td className="py-1 pr-3 text-xs text-gray-500">{m.role}</td>
                                    <td className="py-1 pr-3 text-xs text-gray-500">{m.branch}</td>
                                    <td className="py-1 pr-3 text-right text-xs font-semibold tabular-nums text-gray-900"
                                        style={{ width: 80 }}>
                                      {Math.round(Number(m.index) || 0).toLocaleString()}
                                    </td>
                                    <td className="py-1 pr-3 text-right text-xs tabular-nums text-gray-500"
                                        style={{ width: 70 }}>
                                      {m.achievement ?? 0}%
                                    </td>
                                    <td className="py-1 text-right text-xs tabular-nums" style={{ width: 60 }}>
                                      <span className={(m.met_rate ?? 0) >= 60 ? 'text-[#3B6D11]'
                                        : (m.met_rate ?? 0) >= 30 ? 'text-amber-600' : 'text-rose-600'}>
                                        {m.met_rate ?? 0}%
                                      </span>
                                    </td>
                                  </tr>
                                ))}
                              </tbody>
                            </table>
                          )}
                          {!drillLoading && (drill?.length ?? 0) > 40 && (
                            <p className="mt-1 text-[11px] text-gray-400">
                              showing the top 40 of {drill?.length}
                            </p>
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

        <p className="mt-2 text-[11px] text-gray-400">
          Each person is counted once at every level, so the total index does not change
          when you switch lens — only how it is divided. Roles rank on index per head so a
          large role cannot win on size alone.
        </p>
      </Card.Body>
    </Card>
  );
}
'''

ANAL_NEW = r'''// A3 — daily-log analytics. The 80/20 view first, because that is the question
// management actually asks: which few activities are producing the output.
//
// Three panels:
//   IMPACT     tier split (high/medium/low) plus the per-activity contribution
//              that produced it, so the pie is never a black box — you can see
//              which activity put each slice there.
//   VALIDATION where the logs stand: validated, pending, returned, auto-swept.
//   TREND      index per day across the window, so a dip has a date.
//
// Scope comes from the server (get_visible_staff_codes), so a branch manager
// sees their branch and the MD sees the bank without this component deciding
// anything.

import { useCallback, useEffect, useMemo, useState } from 'react';
import {
  PieChart, Pie, Cell, ResponsiveContainer, Tooltip, Legend,
  BarChart, Bar, XAxis, YAxis, CartesianGrid,
} from 'recharts';
import { Card } from '@/components/Card';
import { useToast } from '@/components/Toast';
import {
  fetchBranchLogAnalytics, fetchBranchLogLeaderboard,
  type BranchLogAnalytics, type Leaderboard,
} from '@/lib/api';
import { periods, findPeriod, periodArgs, DEFAULT_PERIOD_KEY } from '@/lib/period';

// Brand palette. High is primary blue, medium the deep blue, low grey — so the
// eye reads importance by saturation rather than by hue alone.
const TIER_COLOUR: Record<string, string> = {
  high: '#0082BB', medium: '#005B82', low: '#979797',
};
const TIER_LABEL: Record<string, string> = {
  high: 'High impact', medium: 'Medium', low: 'Low',
};
const VALID_COLOUR = ['#669438', '#E0A02B', '#C4536F', '#979797'];

function pct(n: number, total: number): string {
  if (!total) return '0%';
  return `${Math.round((n / total) * 1000) / 10}%`;
}

export default function DailyLogAnalytics() {
  const { toast } = useToast();
  const [periodKey, setPeriodKey] = useState(DEFAULT_PERIOD_KEY);
  const [data, setData] = useState<BranchLogAnalytics | null>(null);
  // Met vs not met per unit, cumulative over the window. Sourced from the
  // leaderboard so the analytics and the ranking cannot report different
  // achievement for the same population.
  const [byUnit, setByUnit] = useState<Leaderboard | null>(null);
  const [loading, setLoading] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const p = findPeriod(periodKey);
      const a = periodArgs(p);
      setData(await fetchBranchLogAnalytics(a.days ?? 0, '', a.start ?? '', a.end ?? ''));
      try { setByUnit(await fetchBranchLogLeaderboard({ ...a, level: 'unit' })); }
      catch { setByUnit(null); }
    } catch (e) {
      toast({ tone: 'danger', message: e instanceof Error ? e.message : 'Could not load analytics.' });
      setData(null);
    } finally {
      setLoading(false);
    }
  }, [periodKey, toast]);

  useEffect(() => { void load(); }, [load]);

  const impact = data?.impact;
  const totals = data?.totals;

  const tierData = useMemo(() => {
    if (!impact) return [];
    return (['high', 'medium', 'low'] as const)
      .map((t) => ({ name: TIER_LABEL[t], key: t, value: Math.max(Number(impact[t]) || 0, 0) }))
      .filter((d) => d.value > 0);
  }, [impact]);

  const activityData = useMemo(() => {
    const by = impact?.by_activity ?? {};
    return Object.entries(by)
      .map(([k, v]) => ({
        key: k,
        name: k.replace(/_/g, ' '),
        index: Math.round(Number((v as { index: number }).index) || 0),
        tier: String((v as { tier: string }).tier || 'medium'),
      }))
      .filter((d) => d.index > 0)
      .sort((a, b) => b.index - a.index)
      .slice(0, 12);
  }, [impact]);

  const validationData = useMemo(() => {
    if (!totals) return [];
    return [
      { name: 'Validated', value: totals.validated || 0 },
      { name: 'Pending', value: totals.pending || 0 },
      { name: 'Returned', value: totals.returned || 0 },
      { name: 'Auto-submitted', value: totals.auto_submitted || 0 },
    ].filter((d) => d.value > 0);
  }, [totals]);

  const totalIndex = Number(impact?.total) || 0;
  const highPct = Number(impact?.high_pct) || 0;

  return (
    <div className="mt-4 space-y-4">
      <Card>
        <Card.Header>
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <h2 className="text-base font-semibold text-gray-900">
                Index analytics — where the output comes from
              </h2>
              <p className="mt-0.5 text-xs text-gray-500">
                Index contribution by impact tier. Tiers are assigned in Index Setup.
              </p>
            </div>
            <select value={periodKey} onChange={(e) => setPeriodKey(e.target.value)}
                    className="rounded border border-gray-200 px-2 py-1 text-xs">
              {periods().map((p) => <option key={p.key} value={p.key}>{p.label}</option>)}
            </select>
          </div>
        </Card.Header>
        <Card.Body>
          {loading && <p className="py-10 text-center text-sm text-gray-400">Loading analytics…</p>}

          {!loading && !data && (
            <p className="py-10 text-center text-sm text-gray-400">No analytics available.</p>
          )}

          {!loading && data && totalIndex === 0 && (
            <p className="py-10 text-center text-sm text-gray-400">
              No index produced in this period.
            </p>
          )}

          {!loading && data && totalIndex > 0 && (
            <div className="grid grid-cols-1 gap-6 lg:grid-cols-[300px_minmax(0,1fr)]">
              <div>
                <ResponsiveContainer width="100%" height={230}>
                  <PieChart>
                    <Pie data={tierData} dataKey="value" nameKey="name"
                         innerRadius={55} outerRadius={90} paddingAngle={2}>
                      {tierData.map((d) => (
                        <Cell key={d.key} fill={TIER_COLOUR[d.key]} />
                      ))}
                    </Pie>
                    <Tooltip formatter={(v: number) => [`${Math.round(v)} index`, '']} />
                    <Legend verticalAlign="bottom" height={24}
                            wrapperStyle={{ fontSize: 11 }} />
                  </PieChart>
                </ResponsiveContainer>
                <div className="mt-1 text-center">
                  <div className="text-2xl font-semibold text-[#0082BB]">
                    {Math.round(highPct)}%
                  </div>
                  <div className="text-xs text-gray-500">
                    of the index comes from high-impact activity
                  </div>
                </div>
              </div>

              {/* The pie is never a black box: this is what put each slice there. */}
              <div>
                <div className="mb-1 text-xs font-semibold text-gray-600">
                  Contribution by activity
                </div>
                <ResponsiveContainer width="100%" height={280}>
                  <BarChart data={activityData} layout="vertical"
                            margin={{ left: 8, right: 16, top: 4, bottom: 4 }}>
                    <CartesianGrid strokeDasharray="3 3" horizontal={false} stroke="#EDEDED" />
                    <XAxis type="number" tick={{ fontSize: 10, fill: '#979797' }} />
                    <YAxis type="category" dataKey="name" width={150}
                           tick={{ fontSize: 10, fill: '#464646' }} />
                    <Tooltip formatter={(v: number) => [`${v} index`, '']} />
                    <Bar dataKey="index" radius={[0, 3, 3, 0]}>
                      {activityData.map((d) => (
                        <Cell key={d.key} fill={TIER_COLOUR[d.tier] || '#979797'} />
                      ))}
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
              </div>
            </div>
          )}
        </Card.Body>
      </Card>

      <Card>
        <Card.Header>
          <div className="flex flex-wrap items-baseline justify-between gap-2">
            <h2 className="text-base font-semibold text-gray-900">
              Daily target — met vs not met
            </h2>
            <span className="text-xs text-gray-500">
              Person-days that carried a target. Rest days and excused days are excluded.
            </span>
          </div>
        </Card.Header>
        <Card.Body>
          {!byUnit || (byUnit.scored_days ?? 0) === 0 ? (
            <p className="py-8 text-center text-sm text-gray-400">
              No scored days in this period.
            </p>
          ) : (
            <div className="grid grid-cols-1 gap-6 lg:grid-cols-[220px_minmax(0,1fr)]">
              <div className="text-center">
                <ResponsiveContainer width="100%" height={180}>
                  <PieChart>
                    <Pie dataKey="value" innerRadius={48} outerRadius={78} paddingAngle={2}
                         data={[{ name: 'Met', value: byUnit.met_days ?? 0 },
                                { name: 'Not met',
                                  value: (byUnit.scored_days ?? 0) - (byUnit.met_days ?? 0) }]}>
                      <Cell fill="#669438" />
                      <Cell fill="#C4536F" />
                    </Pie>
                    <Tooltip formatter={(v: number) => [`${v} person-days`, '']} />
                  </PieChart>
                </ResponsiveContainer>
                <div className="text-2xl font-semibold text-[#3B6D11]">
                  {byUnit.met_rate ?? 0}%
                </div>
                <div className="text-xs text-gray-500">
                  of person-days met the target, bank-wide
                </div>
              </div>

              <div>
                <div className="mb-1 text-xs font-semibold text-gray-600">
                  By unit — cumulative over {findPeriod(periodKey).label.toLowerCase()}
                </div>
                <ResponsiveContainer width="100%" height={Math.max(180, (byUnit.rows.length || 1) * 26)}>
                  <BarChart
                    data={byUnit.rows.map((r) => ({
                      name: String(r.name || '').replace(/^Director,? /, '').slice(0, 26),
                      met: r.met_days ?? 0,
                      missed: (r.scored_days ?? 0) - (r.met_days ?? 0),
                      rate: r.met_rate ?? 0,
                    }))}
                    layout="vertical" stackOffset="expand"
                    margin={{ left: 8, right: 16, top: 4, bottom: 4 }}
                  >
                    <CartesianGrid strokeDasharray="3 3" horizontal={false} stroke="#EDEDED" />
                    <XAxis type="number" tickFormatter={(v: number) => `${Math.round(v * 100)}%`}
                           tick={{ fontSize: 10, fill: '#979797' }} />
                    <YAxis type="category" dataKey="name" width={170}
                           tick={{ fontSize: 10, fill: '#464646' }} />
                    <Tooltip formatter={(v: number, n: string) => [`${v} days`, n]} />
                    <Bar dataKey="met" stackId="a" fill="#669438" radius={[0, 0, 0, 0]} />
                    <Bar dataKey="missed" stackId="a" fill="#C4536F" radius={[0, 3, 3, 0]} />
                  </BarChart>
                </ResponsiveContainer>
                <p className="mt-1 text-[11px] text-gray-400">
                  Bars are proportional, so a small unit and a large one are compared on
                  rate rather than volume. Hover for the day counts behind each.
                </p>
              </div>
            </div>
          )}
        </Card.Body>
      </Card>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <Card>
          <Card.Header>
            <h2 className="text-base font-semibold text-gray-900">Validation state</h2>
          </Card.Header>
          <Card.Body>
            {validationData.length === 0 ? (
              <p className="py-8 text-center text-sm text-gray-400">No logs in this period.</p>
            ) : (
              <div className="grid grid-cols-[180px_minmax(0,1fr)] items-center gap-4">
                <ResponsiveContainer width="100%" height={170}>
                  <PieChart>
                    <Pie data={validationData} dataKey="value" nameKey="name"
                         innerRadius={42} outerRadius={70} paddingAngle={2}>
                      {validationData.map((d, i) => (
                        <Cell key={d.name} fill={VALID_COLOUR[i % VALID_COLOUR.length]} />
                      ))}
                    </Pie>
                    <Tooltip />
                  </PieChart>
                </ResponsiveContainer>
                <div className="space-y-1 text-xs">
                  {validationData.map((d, i) => (
                    <div key={d.name} className="flex items-center justify-between gap-2">
                      <span className="flex items-center gap-1.5 text-gray-600">
                        <span className="inline-block h-2 w-2 rounded-full"
                              style={{ background: VALID_COLOUR[i % VALID_COLOUR.length] }} />
                        {d.name}
                      </span>
                      <span className="tabular-nums text-gray-800">
                        {d.value}
                        <span className="ml-1 text-gray-400">
                          {pct(d.value, totals?.logs || 0)}
                        </span>
                      </span>
                    </div>
                  ))}
                  <div className="mt-2 border-t border-gray-100 pt-2 text-gray-500">
                    Validation rate{' '}
                    <span className="font-semibold text-gray-800">
                      {totals?.validation_rate ?? 0}%
                    </span>
                  </div>
                </div>
              </div>
            )}
          </Card.Body>
        </Card>

        <Card>
          <Card.Header>
            <h2 className="text-base font-semibold text-gray-900">Participation</h2>
          </Card.Header>
          <Card.Body>
            {!totals ? (
              <p className="py-8 text-center text-sm text-gray-400">No data.</p>
            ) : (
              <div className="grid grid-cols-2 gap-3">
                {[
                  { label: 'Logs submitted', value: totals.logs, tone: 'text-gray-900' },
                  { label: 'People filing', value: totals.submitters, tone: 'text-gray-900' },
                  { label: 'Awaiting validation', value: totals.pending, tone: 'text-amber-600' },
                  { label: 'Auto-submitted at deadline', value: totals.auto_submitted, tone: 'text-amber-700' },
                  { label: 'Returned for amendment', value: totals.returned, tone: 'text-rose-600' },
                  { label: 'Total index', value: Math.round(totalIndex), tone: 'text-[#0082BB]' },
                ].map((s) => (
                  <div key={s.label} className="rounded-lg border border-gray-200 p-3">
                    <div className={`text-xl font-semibold tabular-nums ${s.tone}`}>
                      {Number(s.value || 0).toLocaleString()}
                    </div>
                    <div className="mt-0.5 text-[11px] text-gray-500">{s.label}</div>
                  </div>
                ))}
              </div>
            )}
            <p className="mt-3 text-[11px] text-gray-400">
              Auto-submitted logs were swept at the 09:00 deadline with whatever had been
              autosaved — a high count here usually means people are not closing their day,
              not that they did nothing.
            </p>
          </Card.Body>
        </Card>
      </div>
    </div>
  );
}
'''

PAGE_NEW = r'''// v10.513 Phase 4 Batch β4 — PipelineManagerQueues page.
//
// Manager-only page at /pipeline/queues with two tabs:
//
//   1. Validation queue — deals past Lead awaiting manager validation.
//      Each deal has Validate (approved:true) / Query (approved:false)
//      action panel.
//
//   2. Cancellation queue — deals with pending cancellation requests
//      awaiting manager decision. Each deal has Approve / Reject
//      action panel.
//
// Authorization layers (defense in depth):
//   1. Sidebar hides the "Manager Queues" link from non-managers (UX)
//   2. This page renders "Not authorized" guard when isManager(user)
//      is false, before even attempting the fetch (UX)
//   3. Server returns 403 to non-managers on the queue endpoints
//      (the real security boundary)
//
// Pattern reuse:
//   - Tab strip + count badges: bespoke (no Tab primitive)
//   - Per-deal action panels: same shape as β2 detail page panels
//   - Same Toast pattern for success / error
//   - Same mutation hook pattern

import { displayName } from "../lib/names";
import { useCallback, useEffect, useState } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import { useBranding } from '@/hooks/useBranding';
import { useRole } from '@/hooks/useRole';
import { useToast } from '@/components/Toast';
import { usePipelineDealMutations } from '@/hooks/usePipelineDealMutations';
import { isManager } from '@/lib/role';
import {
  fetchValidationQueue, AuthExpiredError,
} from '@/lib/api';
import { Card } from '@/components/Card';
import { Badge } from '@/components/Badge';
import { Button } from '@/components/Button';
import { Skeleton } from '@/components/Skeleton';
import { PageHeader } from '@/components/PageHeader';
import DailyLogValidation from '@/components/DailyLogValidation';
import BranchCountersign from '@/components/BranchCountersign';
import UnitRollup from '@/components/UnitRollup';
import Leaderboard from '@/components/Leaderboard';
import DailyLogAnalytics from '@/components/DailyLogAnalytics';
import PipelineDayCountersign from '@/components/PipelineDayCountersign';
import { fetchUnitDays } from '@/lib/api';
import {
  stageTone, type PipelineDeal,
} from '@/types/pipeline';


type TabKey = 'validation' | 'dailylog' | 'ranking' | 'analytics';


// ── Page component ──────────────────────────────────────────────────────

export function PipelineManagerQueues() {
  const { branding } = useBranding();
  const { user } = useRole();
  const { toast } = useToast();
  const navigate = useNavigate();

  const userIsManager = isManager(user);

  // ── Page-local state ──────────────────────────────────────────────────

  const [activeTab, setActiveTab] = useState<TabKey>('validation');
  const [validationDeals, setValidationDeals] = useState<PipelineDeal[]>([]);
  const [loadingV, setLoadingV] = useState(false);
  const [errorV,   setErrorV]   = useState<string | null>(null);
  // Daily-log queue owns its own fetching; the page only tracks the count
  // for the tab badge.
  const [dailyLogPending, setDailyLogPending] = useState(0);
  // Tier 2 (Head of Branches, MD) countersigns BRANCHES; everyone else
  // validates individuals. Decided by asking the server what this caller
  // oversees rather than by inspecting their role string here.
  // 'staff' = validates individuals, 'branch' = countersigns branches,
  // 'rollup' = MD / Business Manager, observes and may return.
  const [tier, setTier] = useState<'staff' | 'branch' | 'rollup' | null>(null);

  // ── Fetchers ─────────────────────────────────────────────────────────

  const loadValidation = useCallback(async () => {
    if (!userIsManager) return;
    setLoadingV(true);
    setErrorV(null);
    try {
      const res = await fetchValidationQueue();
      setValidationDeals(res.deals);
    } catch (e) {
      if (e instanceof AuthExpiredError) return;
      const msg = e instanceof Error ? e.message : 'Failed to load validation queue';
      setErrorV(msg);
      setValidationDeals([]);
    } finally {
      setLoadingV(false);
    }
  }, [userIsManager]);

  useEffect(() => {
    let alive = true;
    void (async () => {
      try {
        // One probe. /unit-days answers both questions: top_of_house marks the
        // observation tier, and a Branches node means this caller countersigns
        // branches. Asking the server beats inspecting a role string here.
        const r = await fetchUnitDays();
        if (!alive) return;
        if (r.top_of_house) setTier('rollup');
        else if ((r.branches?.children?.length ?? 0) > 0) setTier('branch');
        else setTier('staff');
      } catch {
        if (alive) setTier('staff');
      }
    })();
    return () => { alive = false; };
  }, []);

  // Initial load + reload on tab focus to keep queues fresh
  useEffect(() => {
    void loadValidation();
  }, [loadValidation]);

  // ── Render guards ────────────────────────────────────────────────────

  if (!userIsManager) {
    return (
      <div className="min-h-screen bg-gray-50">
        <PageHeader
          title="Manager Queues"
          breadcrumbs={[{ label: 'EKE Pipeline Intelligence System (PIS)' }, { label: 'Manager Queues' }]}
        />
        <div className="max-w-7xl 2xl:max-w-[1680px] mx-auto px-6 py-6">
        <Card>
          <Card.Header>
            <div className="flex items-center gap-3">
              <Badge tone="warning">Not authorized</Badge>
              <h2 className="text-base font-semibold text-gray-900">
                Manager queues
              </h2>
            </div>
          </Card.Header>
          <Card.Body>
            <p className="text-sm text-gray-700">
              These queues are only visible to staff with manager authority
              (Branch Manager, Regional Head, Director, MD, etc.).
            </p>
            <p className="text-sm text-gray-500 mt-3">
              If you believe this is wrong, contact your administrator.
              Your current role is{' '}
              <span className="font-mono text-gray-700">
                {user?.role ?? '(unknown)'}
              </span>.
            </p>
            <div className="mt-4">
              <Link
                to="/pipeline"
                className="text-sm text-brand-primary underline"
              >
                ← Back to pipeline
              </Link>
            </div>
          </Card.Body>
        </Card>
        </div>
      </div>
    );
  }

  // ── Active tab data ──────────────────────────────────────────────────

  // Cancellation was removed from this page (ruling 2026-08-09); the deal list
  // here is now only ever the pipeline validation queue.
  const activeDeals    = validationDeals;
  const activeLoading  = loadingV;
  const activeError    = errorV;
  const activeReload   = loadValidation;

  // ── Main render ──────────────────────────────────────────────────────

  return (
    <div className="min-h-screen bg-gray-50">
      <PageHeader
        title="Manager Queues"
        breadcrumbs={[{ label: 'EKE Pipeline Intelligence System (PIS)' }, { label: 'Manager Queues' }]}
      />
      <div className="max-w-7xl 2xl:max-w-[1680px] mx-auto px-6 py-6">

      {/* Tab strip */}
      <div className="flex items-center gap-2 border-b border-gray-200">
        <TabBtn
          active={activeTab === 'validation'}
          onClick={() => setActiveTab('validation')}
          label="Pipeline validation"
          count={validationDeals.length}
          loading={loadingV}
        />
        <TabBtn
          active={activeTab === 'dailylog'}
          onClick={() => setActiveTab('dailylog')}
          label="Daily log validation"
          count={dailyLogPending}
          loading={false}
        />
        <TabBtn
          active={activeTab === 'ranking'}
          onClick={() => setActiveTab('ranking')}
          label="Ranking"
          count={0}
          loading={false}
        />
        <TabBtn
          active={activeTab === 'analytics'}
          onClick={() => setActiveTab('analytics')}
          label="Index analytics"
          count={0}
          loading={false}
        />
        <div className="flex-1" />
        <Button
          variant="ghost"
          size="sm"
          onClick={() => void activeReload()}
          loading={activeLoading}
        >
          Refresh
        </Button>
      </div>

      {/* Daily-log validation owns its own loading, empty and error states. */}
      {activeTab === 'dailylog' && tier === null && (
        <Card className="mt-4"><Card.Body>
          <div className="text-sm text-gray-400">Loading…</div>
        </Card.Body></Card>
      )}
      {activeTab === 'dailylog' && tier === 'rollup' && (
        <UnitRollup onCount={setDailyLogPending} />
      )}
      {activeTab === 'dailylog' && tier === 'branch' && (
        <BranchCountersign onCount={setDailyLogPending} />
      )}
      {activeTab === 'dailylog' && tier === 'staff' && (
        <DailyLogValidation onCount={setDailyLogPending} />
      )}

      {/* Ranking and analytics live here too: a manager works out of this page,
          and making them navigate elsewhere to see how their team is doing
          splits one job across two screens. Both components are scope-aware
          server-side, so each manager sees their own population. */}
      {/* Pipeline validation follows the daily log's tier routing: a branch or
          roll-up caller countersigns days; everyone else works the deal queue
          below. Same shape, so a manager learns one screen and knows both. */}
      {activeTab === 'validation' && (tier === 'branch' || tier === 'rollup') && (
        <PipelineDayCountersign onCount={() => { /* count shown on the tab */ }} />
      )}

      {activeTab === 'ranking' && <div className="mt-4"><Leaderboard /></div>}
      {activeTab === 'analytics' && <DailyLogAnalytics />}

      {/* Error panel */}
      {!['dailylog', 'ranking', 'analytics'].includes(activeTab)
        && !(activeTab === 'validation' && (tier === 'branch' || tier === 'rollup'))
        && activeError && (
        <Card className="mt-4">
          <Card.Body>
            <div className="flex items-center gap-3">
              <Badge tone="danger">Error</Badge>
              <div className="flex-1 text-sm text-gray-700">{activeError}</div>
              <Button variant="ghost" size="sm" onClick={() => void activeReload()}>
                Retry
              </Button>
            </div>
          </Card.Body>
        </Card>
      )}

      {/* Empty / loading / content */}
      {['dailylog', 'ranking', 'analytics'].includes(activeTab)
        || (activeTab === 'validation' && (tier === 'branch' || tier === 'rollup'))
        ? null : activeLoading && activeDeals.length === 0 ? (
        <Card className="mt-4">
          <Card.Body>
            <Skeleton shape="line" className="w-1/3" />
            <div className="mt-3"><Skeleton shape="block" className="h-12" /></div>
            <div className="mt-2"><Skeleton shape="block" className="h-12" /></div>
          </Card.Body>
        </Card>
      ) : activeDeals.length === 0 && !activeError ? (
        <Card className="mt-4">
          <Card.Body>
            <div className="text-sm text-gray-700 font-medium">
              No deals in this queue.
            </div>
            <div className="text-xs text-gray-500 mt-1">
              {activeTab === 'validation'
                ? 'New deals past Lead stage will appear here for your validation.'
                : 'Cancellation requests from your team will appear here for your decision.'}
            </div>
          </Card.Body>
        </Card>
      ) : (
        <div className="mt-4 space-y-3">
          {activeDeals.map((deal) => (
            activeTab === 'validation' ? (
              <ValidationCard
                key={deal.id}
                deal={deal}
                onNavigate={() => navigate(`/pipeline/${encodeURIComponent(deal.id)}`)}
                onResolved={() => {
                  toast({ tone: 'success', message: 'Validation decision recorded.' });
                  void loadValidation();
                }}
                onErrorToast={(msg) => toast({ tone: 'danger', message: msg })}
              />
            ) : (
              <CancellationCard
                key={deal.id}
                deal={deal}
                onNavigate={() => navigate(`/pipeline/${encodeURIComponent(deal.id)}`)}
                onResolved={() => {
                  toast({ tone: 'success', message: 'Decision recorded.' });
                  void loadValidation();
                }}
                onErrorToast={(msg) => toast({ tone: 'danger', message: msg })}
              />
            )
          ))}
        </div>
      )}

      {/* Footer */}
      <footer className="mt-12 pb-6 text-center text-[11px] text-gray-400 leading-relaxed">
        {branding?.ip_notice}
      </footer>
      </div>
    </div>
  );
}


// ── Tab button ──────────────────────────────────────────────────────────

interface TabBtnProps {
  active:   boolean;
  onClick:  () => void;
  label:    string;
  count:    number;
  loading:  boolean;
}

function TabBtn({ active, onClick, label, count, loading }: TabBtnProps) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`px-4 py-2 text-sm font-medium border-b-2 transition-colors -mb-px ${
        active
          ? 'border-brand-primary text-brand-primary'
          : 'border-transparent text-gray-600 hover:text-gray-900'
      }`}
    >
      {label}
      {' '}
      <span className={`ml-1 px-2 py-0.5 text-[11px] rounded-full ${
        active ? 'bg-brand-primary text-white' : 'bg-gray-200 text-gray-700'
      }`}>
        {loading ? '…' : count}
      </span>
    </button>
  );
}


// ── Common queue card scaffolding ───────────────────────────────────────

interface QueueCardCommonProps {
  deal:         PipelineDeal;
  onNavigate:   () => void;
  children:     React.ReactNode;
}

function QueueCard({ deal, onNavigate, children }: QueueCardCommonProps) {
  const { branding } = useBranding();
  const sym = branding?.currency_symbol ?? '';
  return (
    <Card>
      <Card.Header>
        <div className="flex items-center gap-3 flex-wrap">
          <button
            type="button"
            onClick={onNavigate}
            className="font-mono text-xs text-brand-primary hover:underline"
          >
            {deal.id}
          </button>
          <h3 className="text-sm font-semibold text-gray-900">
            {deal.client_name || '—'}
          </h3>
          <Badge tone={stageTone(deal.stage)} size="sm">{deal.stage}</Badge>
        </div>
        <div className="text-xs text-gray-500 text-right">
          <div>{deal.product_type ?? deal.product ?? '—'}</div>
          <div className="font-medium text-gray-900 mt-0.5">
            {sym} {Number(deal.amount_kes ?? deal.deal_value ?? 0).toLocaleString()}
          </div>
        </div>
      </Card.Header>
      <Card.Body>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3 text-xs mb-3">
          <Field label="Owner" value={deal.staff_name ? displayName(deal.staff_name) : undefined} sub={deal.staff_code} />
          <Field label="Probability" value={
            typeof deal.probability === 'number'
              ? `${Math.round(deal.probability * 100)}%`
              : '—'
          } />
          <Field label="Next action" value={deal.next_action} />
          <Field label="Expected close" value={(deal.expected_close ?? '').slice(0, 10) || '—'} />
        </div>
        {children}
      </Card.Body>
    </Card>
  );
}

function Field({ label, value, sub }: {
  label: string;
  value: React.ReactNode;
  sub?: React.ReactNode;
}) {
  return (
    <div>
      <div className="text-[10px] font-semibold uppercase tracking-wider text-gray-500">
        {label}
      </div>
      <div className="text-sm text-gray-900 mt-0.5">{value ?? '—'}</div>
      {sub && (
        <div className="text-[10px] text-gray-400 font-mono">{sub}</div>
      )}
    </div>
  );
}


// ── Validation card (Validate / Query buttons + note) ───────────────────

interface ResolvedCallbacks {
  onResolved:    () => void;
  onErrorToast:  (msg: string) => void;
}

function ValidationCard({ deal, onNavigate, onResolved, onErrorToast }: {
  deal: PipelineDeal;
  onNavigate: () => void;
} & ResolvedCallbacks) {
  const mutations = usePipelineDealMutations();
  const [note, setNote] = useState('');

  const submit = async (approved: boolean) => {
    const result = await mutations.validate(deal.id, {
      approved,
      note: note.trim() || undefined,
    });
    if (result.ok) {
      setNote('');
      onResolved();
    } else {
      onErrorToast(result.error);
    }
  };

  return (
    <QueueCard deal={deal} onNavigate={onNavigate}>
      <div className="border-t border-gray-100 pt-3">
        <label className="text-xs font-medium text-gray-700">
          Manager note (optional)
        </label>
        <input
          type="text"
          value={note}
          onChange={(e) => setNote(e.target.value)}
          disabled={mutations.loading}
          placeholder="Context for the owner if querying"
          className="mt-1 w-full h-9 px-3 rounded-md border border-gray-300 bg-white text-sm focus:outline-none focus:border-brand-primary focus:ring-2 focus:ring-brand-primary/20"
        />
        <div className="mt-3 flex items-center justify-end gap-2">
          <Button
            variant="ghost"
            size="sm"
            onClick={() => void submit(false)}
            loading={mutations.loading}
          >
            Query (return to owner)
          </Button>
          <Button
            variant="primary"
            size="sm"
            onClick={() => void submit(true)}
            loading={mutations.loading}
          >
            Validate — include in forecast
          </Button>
        </div>
      </div>
    </QueueCard>
  );
}


// ── Cancellation card (Approve / Reject buttons + reason context) ───────

function CancellationCard({ deal, onNavigate, onResolved, onErrorToast }: {
  deal: PipelineDeal;
  onNavigate: () => void;
} & ResolvedCallbacks) {
  const mutations = usePipelineDealMutations();
  const [note, setNote] = useState('');

  const submit = async (approve: boolean) => {
    const result = await mutations.approveCancel(deal.id, {
      approve,
      note: note.trim() || undefined,
    });
    if (result.ok) {
      setNote('');
      onResolved();
    } else {
      onErrorToast(result.error);
    }
  };

  return (
    <QueueCard deal={deal} onNavigate={onNavigate}>
      {/* Requested-by + reason context */}
      <div className="px-3 py-2 rounded-md bg-amber-50 border border-amber-200 text-xs">
        <div className="font-semibold text-amber-900">
          Cancellation requested
          {deal.cancel_requested_by && ` by ${deal.cancel_requested_by}`}
        </div>
        {deal.cancel_reason && (
          <div className="text-amber-800 mt-1">
            <span className="font-medium">Reason:</span> {deal.cancel_reason}
          </div>
        )}
      </div>
      <div className="border-t border-gray-100 pt-3 mt-3">
        <label className="text-xs font-medium text-gray-700">
          Your decision note (optional)
        </label>
        <input
          type="text"
          value={note}
          onChange={(e) => setNote(e.target.value)}
          disabled={mutations.loading}
          placeholder="Recorded on the deal for audit"
          className="mt-1 w-full h-9 px-3 rounded-md border border-gray-300 bg-white text-sm focus:outline-none focus:border-brand-primary focus:ring-2 focus:ring-brand-primary/20"
        />
        <div className="mt-3 flex items-center justify-end gap-2">
          <Button
            variant="ghost"
            size="sm"
            onClick={() => void submit(false)}
            loading={mutations.loading}
          >
            Reject (deal continues)
          </Button>
          <Button
            variant="danger"
            size="sm"
            onClick={() => void submit(true)}
            loading={mutations.loading}
          >
            Approve — close as Lost
          </Button>
        </div>
      </div>
    </QueueCard>
  );
}
'''


TSL_OLD_HEAD = "export async function fetchBranchLogLeaderboard(opts: {"
TSA_OLD_HEAD = "export async function fetchBranchLogAnalytics("


def main():
    apply = "--apply" in sys.argv
    for p in (APITS, LEAD, ANAL, PAGE, API):
        if not os.path.isfile(p):
            print("ABORT: %s not found." % p)
            print("       Apply patch_a4_drilldown.py and its predecessors first.")
            return 1
    if os.path.exists(PER):
        print("ABORT: %s already exists - A5 looks applied." % PER)
        return 1

    api = open(API, encoding="utf-8").read()
    ts = open(APITS, encoding="utf-8").read()

    if 'start: str = ""' in api:
        print("ABORT: the endpoints already accept start/end.")
        return 1
    if "met_rate" not in api:
        print("ABORT: apply patch_a4_drilldown.py first.")
        return 1

    # Backend: replace the two endpoint bodies wholesale.
    a = api.index('@router.get("/leaderboard")')
    b = api.index('@router.get("/analytics")', a)
    api = api[:a] + LB_NEW + api[b:]
    k = api.index("def branch_log_analytics(")
    l = api.index("    breakdown = impact_breakdown(scoped)", k)
    api = api[:k] + ANAP_NEW + api[l:]
    print("  ok  /leaderboard and /analytics accept start/end")

    # api.ts: two client functions.
    m = ts.index(TSL_OLD_HEAD)
    n = ts.index("export async function fetchBranchLogRanking(", m)
    ts = ts[:m] + TSL_NEW + ts[n:]
    o = ts.index(TSA_OLD_HEAD)
    q = ts.index("}", ts.index("return getJson<BranchLogAnalytics>", o)) + 1
    ts = ts[:o] + TSA_NEW + ts[q:]
    print("  ok  api.ts - start/end plumbed on both clients")

    # post-checks before anything is written
    if api.count('start: str = ""') != 2:
        print("ABORT: post-check - expected start/end on exactly two endpoints.")
        return 1
    if api.count('@router.get("/leaderboard")') != 1 or api.count('@router.get("/analytics")') != 1:
        print("ABORT: post-check - endpoint count changed.")
        return 1
    if "fetchBranchLogHistoryGrid" not in ts or "fetchBranchLogRanking" not in ts:
        print("ABORT: post-check - api.ts lost an existing client.")
        return 1
    for name, blob in (("period.ts", PER_NEW), ("Leaderboard", LEAD_NEW),
                       ("DailyLogAnalytics", ANAL_NEW), ("ManagerQueues", PAGE_NEW)):
        for op, cl in (("{", "}"), ("(", ")")):
            if blob.count(op) != blob.count(cl):
                print("ABORT: %s unbalanced %s%s." % (name, op, cl))
                return 1
    if "Index analytics" not in ANAL_NEW or "Index analytics" not in PAGE_NEW:
        print("ABORT: post-check - the Index analytics rename is missing.")
        return 1
    if "periodArgs" not in LEAD_NEW or "periodArgs" not in ANAL_NEW:
        print("ABORT: post-check - the period selector is not wired into both.")
        return 1
    print("  ok  post-checks clean")

    if not apply:
        print("\nDRY RUN - nothing written. Re-run with --apply.")
        return 0

    open(PER, "w", encoding="utf-8", newline="").write(PER_NEW)
    print("CREATED %s" % PER)
    for path, content in ((API, api), (APITS, ts), (LEAD, LEAD_NEW),
                          (ANAL, ANAL_NEW), (PAGE, PAGE_NEW)):
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
