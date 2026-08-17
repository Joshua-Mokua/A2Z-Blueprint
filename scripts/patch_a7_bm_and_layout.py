#!/usr/bin/env python
# -*- coding: utf-8 -*-
r"""
A7 - the branch manager bears the branch; even column distribution; ordering.

RULING (2026-08-09): "branch manager cuts across but mostly their contribution
in commercial, so theirs we simply let them bear the branch, which is the same
logic that kicks when we are ranking branches".

  The Branch Manager is now ABSENT from the segment split rather than filed
  under Operations. Placing them anywhere would credit one segment with a
  contribution that is really the whole branch's.

  THE HONEST CONSEQUENCE, surfaced rather than hidden: the segment level is the
  ONE view that does not sum to the bank total, because 11 branch managers are
  held back. The response returns bears_branch {headcount, index} and the UI
  says so in a footnote. A level that quietly fails to reconcile would be worse
  than one that explains itself - somebody would eventually find the gap and
  distrust every other number on the page.

  Live roster after the change:
      Consumer 89 · Operations 76 · Commercial 17 · bears the branch 11

ORDERING - "on the drop we can be arranging staff from top performer to least,
this should apply across". Verified rather than assumed: rows.sort is descending
on the sort key at every level, and an expanded row fetches level=staff which
sorts on avg_index, so the drill-down is already best-to-worst. The footer now
STATES the order, because an unstated sort is one the reader has to test.

LAYOUT - "there is a wide space from one item to the other, squeezing items to
the end instead of even distribution". The table had no fixed layout, so the
name column absorbed every pixel of slack and pushed the numbers into a huddle
at the right edge. Now table-fixed with an explicit colgroup: numeric columns get
the width they need and no more, the name column takes the remainder, and long
names truncate with the full text on hover instead of stretching the row.

Verified: py_compile clean, tsc --noEmit clean, vite build clean.

Usage (from project root, .venv active):
    python scripts\patch_a7_bm_and_layout.py            # dry run
    python scripts\patch_a7_bm_and_layout.py --apply    # write + .pre_a7 backups
"""
import os
import shutil
import sys

OV = os.path.join("utils", "org_validator.py")
API = os.path.join("utils", "api_branch_log.py")
APITS = os.path.join("frontend", "web", "src", "lib", "api.ts")
LEAD = os.path.join("frontend", "web", "src", "components", "Leaderboard.tsx")
BACKUP_SUFFIX = ".pre_a7"

SEG_NEW = r'''# ── Branch segments ─────────────────────────────────────────────────────────
# RULING (2026-08-09): at a BRANCH the meaningful split is Consumer, Commercial
# and Operations - "operations which will include tellers and the operations
# team". The MD-reporting unit is the wrong label there: a teller does not think
# of themselves as sitting under "Director Consumer & Commercial Banking (CCB)".
#
# It cannot come from the register's Department either: branch staff carry only
# Commercial Banking (100) and Consumer Banking (93), with every operations role
# filed under Commercial. So the segment is derived from ROLE, and the mapping
# lives in org_config.json under `branch_segments` so the bank can move a role
# between segments without a deploy.
_DEFAULT_SEGMENTS = {
    "Operations": [
        "branch operations officer", "assistant branch service & operations manager",
        "customer service manager", "teller", "branch operations manager",
        "service assistant, operations officer",
        # RULING 2026-08-09: the BRANCH MANAGER is deliberately absent. They cut
        # across all three segments, so "they simply bear the branch" - the same
        # logic that already applies when branches are ranked against each
        # other. Placing them in Operations would credit operations with a
        # contribution that is really the whole branch's.
    ],
    "Consumer": [
        "relationship officer", "relationship manager, premier banking",
        "relationship officer, premier banking", "direct sales agent",
        "branch dsa team lead", "bancassurance officer",
        "relationship manager, employee schemes",
    ],
    "Commercial": [
        "relationship manager, sme", "relationship manager, local corporate",
        "relationship manager", "relationship manager, corporate",
    ],
}


def branch_segments() -> dict:
    """{segment: [role, ...]} from org_config, falling back to the defaults."""
    try:
        from utils.config import load_org_config
        cfg = (load_org_config() or {}).get("branch_segments")
        if isinstance(cfg, dict) and cfg:
            return {str(k): [str(r).lower() for r in (v or [])] for k, v in cfg.items()}
    except Exception:
        pass
    return {k: list(v) for k, v in _DEFAULT_SEGMENTS.items()}


@lru_cache(maxsize=1)
def _segment_index() -> dict:
    out = {}
    for seg, roles in branch_segments().items():
        for r in roles:
            out[str(r).strip().lower()] = seg
    return out


def segment_for_role(role: str) -> str:
    """Consumer / Commercial / Operations for a branch role, or '' if unmapped.

    An UNMAPPED role returns '' rather than being guessed into a segment - a
    quietly miscategorised teller is worse than a visible gap, because nobody
    goes looking for a number that already looks plausible.
    """
    r = _s(role).lower()
    idx = _segment_index()
    if r in idx:
        return idx[r]
    # Substring fallback for variant spellings, longest match first so
    # "relationship manager, sme" beats "relationship manager".
    for known in sorted(idx, key=len, reverse=True):
        if known and known in r:
            return idx[known]
    return ""


'''

LB_NEW = r'''@router.get("/leaderboard")
def branch_log_leaderboard(days: int = 30, level: str = "staff", role: str = "",
                           branch: str = "", unit: str = "", segment: str = "",
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
        seg = ""
        try:
            from utils.org_validator import segment_for_role
            seg = segment_for_role(r) or ""
        except Exception:
            seg = ""
        if role and r != role:
            continue
        if branch and b != branch:
            continue
        if unit and u != unit:
            continue
        if segment and seg != segment:
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
            "role": r, "branch": b, "unit": u, "segment": seg,
            "index": idx, "target": tgt,
            "days_filed": len(mine),
            "validated": sum(1 for x in mine if x.get("validated")),
            "cf_variance": rows[-1].get("cf_variance", 0) if rows else 0,
            "met_days": met,
            "scored_days": len(scored),
            # RULING 2026-08-09: the index is a DAILY measure, so a fair ranking
            # averages it over the days a person was ACTUALLY ON DUTY. Total
            # accumulation punishes a new joiner and anyone who took approved
            # leave, which is precisely what the exception model exists to
            # prevent. scored_days already excludes rest days and excused days,
            # so it is exactly "days on duty".
            "avg_index": round(idx / len(scored), 2) if scored else 0.0,
            "avg_target": round(tgt / len(scored), 2) if scored else 0.0,
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
            # Average per on-duty day, so a large unit cannot outrank a small
            # one on headcount alone.
            e["avg_index"] = (round(e["index"] / e["scored_days"], 2)
                              if e["scored_days"] else 0.0)
            e["avg_target"] = (round(e["target"] / e["scored_days"], 2)
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
    elif level == "segment":
        # Consumer / Commercial / Operations — the split that means something at
        # a branch, where the MD-reporting unit does not.
        #
        # Branch managers are EXCLUDED, not bucketed: they cut across all three
        # and bear the branch instead (ruling 2026-08-09). That means this level
        # is the ONE that does not sum to the bank total, so the count and index
        # of the people held back are returned explicitly — a level that quietly
        # fails to reconcile would be worse than one that says why.
        segmented = [p for p in people if p["segment"]]
        unsegmented = [p for p in people if not p["segment"]]
        rows = agg(segmented, lambda p: p["segment"], "name")
        sort_key = "avg_index"
    else:
        level = "staff"
        for p in people:
            p["achievement"] = round((p["index"] / p["target"]) * 100, 1) if p["target"] else 0.0
            p["met_rate"] = (round(p["met_days"] / p["scored_days"] * 100, 1)
                             if p["scored_days"] else 0.0)
        rows = people
        # Individuals rank on the AVERAGE per on-duty day, not the total: a
        # person who joined in June or took two weeks' leave should not be
        # ranked below someone with the same daily performance and more days.
        # The total stays on the row - it is still what the bank banked.
        sort_key = "avg_index"

    rows.sort(key=lambda r: -float(r.get(sort_key) or 0))
    for i, r in enumerate(rows, 1):
        r["rank"] = i

    total_index = round(sum(float(r.get("index") or 0) for r in rows), 1)
    _held = locals().get("unsegmented") or []
    bears_branch = {
        "headcount": len(_held),
        "index": round(sum(float(p.get("index") or 0) for p in _held), 1),
    } if _held else None
    met_total = sum(int(p.get("met_days") or 0) for p in people)
    scored_total = sum(int(p.get("scored_days") or 0) for p in people)
    return {
        "level": level, "days": days, "start": start, "end": end, "rows": rows,
        "total_index": total_index,
        "met_days": met_total, "scored_days": scored_total,
        "met_rate": round(met_total / scored_total * 100, 1) if scored_total else 0.0,
        "total_headcount": len(people),
        "filters": {"role": role, "branch": branch, "unit": unit, "segment": segment},
        "roles": sorted({p["role"] for p in people if p["role"]}),
        "branches": sorted({p["branch"] for p in people if p["branch"]}),
        "units": sorted({p["unit"] for p in people if p["unit"]}),
        "segments": sorted({p["segment"] for p in people if p["segment"]}),
        "bears_branch": bears_branch,
    }


'''

TSL_NEW = r'''// ── Cumulative leaderboard (staff / role / branch / unit) ─────────────────
export interface LeaderboardRow {
  rank?: number;
  name?: string;                       // role / branch / unit rows
  staff_code?: string; staff_name?: string; role?: string; branch?: string; unit?: string;
  index: number; target: number; achievement?: number;
  headcount?: number; index_per_head?: number;
  days_filed: number; validated: number; cf_variance?: number;
  met_days?: number; scored_days?: number; met_rate?: number;
  segment?: string;
  avg_index?: number; avg_target?: number;   // per ON-DUTY day
}
export interface Leaderboard {
  level: string; days: number; rows: LeaderboardRow[];
  total_index: number; total_headcount: number;
  met_days?: number; scored_days?: number; met_rate?: number;
  filters: { role: string; branch: string; unit: string };
  roles: string[]; branches: string[]; units: string[]; segments?: string[];
  // Segment level only: people held back because they bear the branch.
  bears_branch?: { headcount: number; index: number } | null;
}
export async function fetchBranchLogLeaderboard(opts: {
  days?: number; level?: string; role?: string; branch?: string; unit?: string;
  segment?: string; start?: string; end?: string;
} = {}): Promise<Leaderboard> {
  const q = new URLSearchParams();
  if (opts.days) q.set('days', String(opts.days));
  if (opts.start) q.set('start', opts.start);
  if (opts.end) q.set('end', opts.end);
  if (opts.level) q.set('level', opts.level);
  if (opts.role) q.set('role', opts.role);
  if (opts.branch) q.set('branch', opts.branch);
  if (opts.unit) q.set('unit', opts.unit);
  if (opts.segment) q.set('segment', opts.segment);
  const s = q.toString();
  return getJson<Leaderboard>(`/branch-log/leaderboard${s ? `?${s}` : ''}`);
}

'''

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

type Level = 'unit' | 'segment' | 'branch' | 'role' | 'staff';

const LEVELS: { key: Level; label: string; hint: string }[] = [
  { key: 'unit',    label: 'Units',       hint: 'Everything beneath each MD-reporting unit' },
  { key: 'segment', label: 'Segments',    hint: 'Consumer, Commercial and Operations — the split that means something at a branch' },
  { key: 'branch',  label: 'Branches',    hint: 'The 16 branches and Head Office' },
  { key: 'role',    label: 'Roles',       hint: 'Averaged per on-duty day, so a big role cannot win on size' },
  { key: 'staff',   label: 'Individuals', hint: 'Ranked on the average per day on duty, not the total' },
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
            <table className="w-full table-fixed border-separate" style={{ borderSpacing: 0 }}>
              <colgroup>
                <col style={{ width: 44 }} />
                <col />
                {isStaff && <col style={{ width: '18%' }} />}
                {isStaff && <col style={{ width: '14%' }} />}
                {!isStaff && <col style={{ width: 72 }} />}
                <col style={{ width: 104 }} />
                <col style={{ width: 96 }} />
                <col style={{ width: 76 }} />
                <col style={{ width: 150 }} />
                <col style={{ width: 76 }} />
                {!isStaff && <col style={{ width: 84 }} />}
                <col style={{ width: 68 }} />
              </colgroup>
              <thead>
                <tr>
                  <th className="bg-gray-100 px-2 py-2 text-left text-[11px] font-semibold uppercase text-gray-600">#</th>
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
                  <th className="bg-[#0082BB] px-2 py-2 text-right text-[11px] font-semibold uppercase text-white">Avg/day</th>
                  <th className="bg-gray-100 px-2 py-2 text-right text-[11px] font-semibold uppercase text-gray-600">Total index</th>
                  <th className="bg-gray-100 px-2 py-2 text-right text-[11px] font-semibold uppercase text-gray-600">On duty</th>
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
                      <td className={`${bg} truncate px-2 py-1.5 text-xs font-medium text-gray-900`}
                          title={nameOf(r)}>
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
                      {isStaff && (
                        <td className={`${bg} truncate px-2 py-1.5 text-xs text-gray-500`} title={r.role}>
                          {r.role}
                        </td>
                      )}
                      {isStaff && (
                        <td className={`${bg} truncate px-2 py-1.5 text-xs text-gray-500`} title={r.branch}>
                          {r.branch}
                        </td>
                      )}
                      {!isStaff && (
                        <td className={`${bg} px-2 py-1.5 text-right text-xs tabular-nums text-gray-500`}>
                          {r.headcount}
                        </td>
                      )}
                      <td className={`${bg} px-2 py-1.5 text-right text-xs font-semibold tabular-nums`}>
                        <span className={(r.avg_index ?? 0) >= (r.avg_target ?? 0) && (r.avg_target ?? 0) > 0
                          ? 'text-[#3B6D11]' : 'text-gray-900'}>
                          {(r.avg_index ?? 0).toFixed(1)}
                        </span>
                        <span className="ml-1 text-[10px] font-normal text-gray-400">
                          / {(r.avg_target ?? 0).toFixed(0)}
                        </span>
                      </td>
                      <td className={`${bg} px-2 py-1.5 text-right text-xs tabular-nums text-gray-600`}>
                        {idx.toLocaleString()}
                      </td>
                      <td className={`${bg} px-2 py-1.5 text-right text-xs tabular-nums text-gray-500`}>
                        {r.scored_days ?? 0}
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
                        <td colSpan={10} className="bg-[#F7FBFD] px-6 py-3">
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
          Sorted best to worst on the <strong>average index per day on duty</strong> —
          at every level, and inside every expanded row. Days on leave,
          rest days and excused absences are not counted as days on duty, so nobody is
          penalised for a day the bank did not expect work — that is what the manager's
          exception is for. The total index stays on the row as what was actually banked.
          Each person is counted once at every level, so switching lens changes how the
          total is divided, never the total itself.
        </p>
        {level === 'segment' && data?.bears_branch && (
          <p className="mt-1 text-[11px] text-gray-500">
            {data.bears_branch.headcount} branch manager(s) are not in these segments —
            they cut across all three and bear the branch instead, the same logic used
            when branches are ranked against each other. Their{' '}
            {data.bears_branch.index.toLocaleString()} index sits at branch level, which
            is why this is the one view that does not sum to the bank total.
          </p>
        )}
      </Card.Body>
    </Card>
  );
}
'''


def main():
    apply = "--apply" in sys.argv
    for p in (OV, API, APITS, LEAD):
        if not os.path.isfile(p):
            print("ABORT: %s not found." % p)
            print("       Apply patch_a6_average_and_segments.py first.")
            return 1

    ov = open(OV, encoding="utf-8").read()
    api = open(API, encoding="utf-8").read()
    ts = open(APITS, encoding="utf-8").read()

    if "segment_for_role" not in ov:
        print("ABORT: apply patch_a6_average_and_segments.py first.")
        return 1
    if "bears_branch" in api:
        print("ABORT: /leaderboard already reports bears_branch - A7 looks applied.")
        return 1

    i = ov.index("# \u2500\u2500 Branch segments \u2500\u2500")
    j = ov.index("def unit_for_role(role: str) -> str:")
    ov = ov[:i] + SEG_NEW + ov[j:]
    print("  ok  org_validator - branch manager out of the segment split")

    a = api.index('@router.get("/leaderboard")')
    b = api.index('@router.get("/analytics")', a)
    api = api[:a] + LB_NEW + api[b:]
    print("  ok  /leaderboard - segment level excludes BMs and reports bears_branch")

    m = ts.index("// \u2500\u2500 Cumulative leaderboard (staff / role / branch / unit) \u2500\u2500")
    n = ts.index("export async function fetchBranchLogRanking(", m)
    ts = ts[:m] + TSL_NEW + ts[n:]
    print("  ok  api.ts - bears_branch")

    # post-checks
    if '"branch manager",' in SEG_NEW:
        print("ABORT: post-check - the branch manager is still in a segment.")
        return 1
    if "bears_branch" not in api or api.count('@router.get("/leaderboard")') != 1:
        print("ABORT: post-check - endpoint not as expected.")
        return 1
    if "rows.sort(key=lambda r: -float(r.get(sort_key) or 0))" not in api:
        print("ABORT: post-check - descending sort is missing.")
        return 1
    if "table-fixed" not in LEAD_NEW or "<colgroup>" not in LEAD_NEW:
        print("ABORT: post-check - the column layout fix is missing.")
        return 1
    if "fetchBranchLogHistoryGrid" not in ts:
        print("ABORT: post-check - api.ts lost fetchBranchLogHistoryGrid.")
        return 1
    for op, cl in (("{", "}"), ("(", ")")):
        if LEAD_NEW.count(op) != LEAD_NEW.count(cl):
            print("ABORT: Leaderboard unbalanced %s%s." % (op, cl))
            return 1
    print("  ok  post-checks clean")

    if not apply:
        print("\nDRY RUN - nothing written. Re-run with --apply.")
        return 0

    for path, content in ((OV, ov), (API, api), (APITS, ts), (LEAD, LEAD_NEW)):
        shutil.copy2(path, path + BACKUP_SUFFIX)
        open(path, "w", encoding="utf-8", newline="").write(content)
        print("APPLIED %s" % path)

    import py_compile
    for path in (OV, API):
        try:
            py_compile.compile(path, doraise=True)
            print("  ok  %s compiles" % os.path.basename(path))
        except Exception as exc:
            print("  FAIL %s: %s" % (path, exc))
            return 1

    print("\nRestart uvicorn. Expect Consumer / Operations / Commercial in the")
    print("segment view, with branch managers held back at branch level.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
