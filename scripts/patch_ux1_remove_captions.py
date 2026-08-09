#!/usr/bin/env python
# -*- coding: utf-8 -*-
r"""
UX1 - remove the explanatory captions. Every one of them.

RULING (2026-08-09): "why are we still having these explanations ... can't we
just stop writing them since no one really needs them, they are just explanatory
quotes".

Fair. I had been writing a caption under every panel heading explaining what the
panel obviously is. A user who has opened "Pipeline journey" does not need to be
told it shows each product's defined stages.

REMOVED - the header subtitle from all seven components:

    Pipeline journey      "Each product's defined stages, in the order the bank
                           configured them."
    Cumulative ranking    the per-level hint line
    Index analytics       "Index contribution by impact tier. Tiers are assigned
                           in Index Setup."
    Daily log consolidated "Branches are countersigned by the Head of Branches
                           and units by their Director..."
    Branch validation     "You countersign the branch day..."
    Daily log validation  "You are one of the branch management triad..."
    Pipeline day          "You countersign the branch pipeline day..."

ALSO REMOVED - the prose captions underneath:
    "Person-days that carried a target. Rest days and excused days are excluded."
    "Auto-submitted logs were swept at the 09:00 deadline..."
    "Three or more days is past the return window..." (both components)
    "of the index comes from high-impact activity"
    "— inferred from win probability, not a sales stage"
    the LEVELS hint field itself, so no dead data is left on the type

WHAT SURVIVES, deliberately: column headers, units on figures, the funnel's
four-word colour legend, and the empty-state lines that tell a user why a panel
has nothing in it. Those are labels and answers, not explanations - a blank
panel with no reason is a support call.

Verified: tsc --noEmit clean, vite build clean, and a grep for every removed
phrase returns nothing.

Usage (from project root, .venv active):
    python scripts\patch_ux1_remove_captions.py            # dry run
    python scripts\patch_ux1_remove_captions.py --apply    # write + .pre_ux1 backups
"""
import os
import shutil
import sys

BASE = os.path.join("frontend", "web", "src", "components")
BACKUP_SUFFIX = ".pre_ux1"

DEFINEDFUNNEL = r'''// DefinedFunnel — the pipeline centrepiece, drawn from ADMIN CONFIG.
//
// Ruling 2026-08-09: stages are never hardcoded. Every band here is a stage the
// bank configured in that product's flow, in the order it configured them, with
// the win probability it set for that stage WITHIN THAT FLOW.
//
// EMPTY STAGES ARE DRAWN. A funnel that hides the steps holding nothing is a bar
// chart of whatever happened to be busy — and the empty step is usually the
// finding: it is where deals stop arriving.
//
// THE CREDIT LAYER IS A SECOND AXIS, not a stage. Documentation / Branch Credit /
// Department / Credit Analysis / Credit Administration / TROPS say where a deal
// probably sits inside the bank, inferred from its probability. It sits beneath
// the journey and never filters it.

import { useEffect, useMemo, useState } from 'react';
import { Card } from '@/components/Card';
import { useToast } from '@/components/Toast';
import { fetchPipelineDefinedFunnel, type DefinedFunnel as FunnelData, type DefinedFlow } from '@/lib/api';

// Cool→warm sweep: early stages cool, closing stages warm. Depth comes from a
// vertical gradient plus a soft inner highlight, so a band reads as a solid
// object rather than a coloured rectangle.
const PALETTE = ['#0082BB', '#0C7BC0', '#3F6FC4', '#6A61C0', '#9455B0', '#BE4E93', '#D75A72', '#E0A02B', '#669438'];

function bandColour(i: number, n: number): string {
  if (n <= 1) return PALETTE[0];
  const seg = (i / (n - 1)) * (PALETTE.length - 1);
  const idx = Math.min(Math.floor(seg), PALETTE.length - 2);
  const t = seg - idx;
  const hex = (h: string) => [parseInt(h.slice(1, 3), 16), parseInt(h.slice(3, 5), 16), parseInt(h.slice(5, 7), 16)];
  const [r1, g1, b1] = hex(PALETTE[idx]);
  const [r2, g2, b2] = hex(PALETTE[idx + 1]);
  const m = (a: number, b: number) => Math.round(a + (b - a) * t);
  return `rgb(${m(r1, r2)}, ${m(g1, g2)}, ${m(b1, b2)})`;
}

function kes(n: number): string {
  if (!n) return '—';
  return Math.round(n).toLocaleString();
}

export interface DefinedFunnelProps {
  /** Clicking a non-empty band drills into that flow + stage. Preserved from the
   *  previous funnel: dropping it would have removed a working feature quietly. */
  onStageClick?: (flow: string, stage: string) => void;
}

export default function DefinedFunnel({ onStageClick }: DefinedFunnelProps = {}) {
  const { toast } = useToast();
  const [data, setData] = useState<FunnelData | null>(null);
  const [loading, setLoading] = useState(false);
  const [flowKey, setFlowKey] = useState('');
  const [hover, setHover] = useState('');

  useEffect(() => {
    let alive = true;
    setLoading(true);
    void (async () => {
      try {
        const r = await fetchPipelineDefinedFunnel();
        if (!alive) return;
        setData(r);
        setFlowKey((k) => k || (r.flows[0]?.flow ?? ''));
      } catch (e) {
        if (alive) toast({ tone: 'danger', message: e instanceof Error ? e.message : 'Could not load the funnel.' });
      } finally {
        if (alive) setLoading(false);
      }
    })();
    return () => { alive = false; };
  }, [toast]);

  const flow: DefinedFlow | undefined = useMemo(
    () => data?.flows.find((f) => f.flow === flowKey) ?? data?.flows[0],
    [data, flowKey]);

  const buckets = flow?.buckets ?? [];
  // Micro-steps open on demand: management reads the six buckets, an officer
  // opens the one they work in.
  const [openBucket, setOpenBucket] = useState('');

  return (
    <Card>
      <Card.Header>
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <h2 className="text-base font-semibold text-gray-900">Pipeline journey</h2>
          </div>
        </div>
      </Card.Header>

      <Card.Body>
        {loading && <p className="py-10 text-center text-sm text-gray-400">Loading the journey…</p>}

        {!loading && data && data.flows.length === 0 && (
          <p className="py-10 text-center text-sm text-gray-400">
            No product flows configured. Define them in Administration.
          </p>
        )}

        {!loading && data && data.flows.length > 0 && (
          <>
            <div className="mb-3 flex flex-wrap gap-1.5">
              {data.flows.map((f) => (
                <button key={f.flow} type="button" onClick={() => setFlowKey(f.flow)}
                  className={'rounded-full px-3 py-1 text-xs font-medium capitalize transition-colors '
                    + (flow?.flow === f.flow ? 'bg-[#005B82] text-white'
                                             : 'bg-gray-100 text-gray-600 hover:bg-[#0082BB]/10')}>
                  {f.flow}
                  <span className="ml-1.5 opacity-70">{f.deals}</span>
                </button>
              ))}
            </div>

            {/* A TRUE FUNNEL: each band is a trapezoid whose top edge matches
                the band above, so the silhouette is continuous from Initiation
                to disbursement rather than a stack of separate bars. Width
                follows the ideal taper — what a healthy pipeline SHOULD look
                like — while the RAG rail on the left reports what it is
                actually doing. Shape shows the plan; colour shows the truth. */}
            <div className="mx-auto" style={{ maxWidth: 760 }}>
              {buckets.map((b, i) => {
                const wTop = 100 - (i / Math.max(buckets.length, 1)) * 62;
                const wBot = 100 - ((i + 1) / Math.max(buckets.length, 1)) * 62;
                const colour = bandColour(i, buckets.length);
                const empty = b.count === 0;
                const on = hover === b.key;
                const open = openBucket === b.key;
                const h = b.health;
                const rag = h.status === 'red' ? '#C4536F'
                  : h.status === 'amber' ? '#E0A02B'
                  : h.status === 'green' ? '#669438' : '#D8DBDF';
                return (
                  <div key={b.key}>
                    <div
                      onMouseEnter={() => setHover(b.key)}
                      onMouseLeave={() => setHover('')}
                      onClick={() => setOpenBucket(open ? '' : b.key)}
                      className="relative flex cursor-pointer items-stretch gap-2"
                    >
                      {/* the health rail — red/amber/green, per stage */}
                      <div className="w-1.5 shrink-0 rounded-full transition-all"
                           style={{ background: rag, opacity: on ? 1 : 0.85 }}
                           title={h.status === 'idle'
                             ? 'No deals at this stage'
                             : `${h.avg_days} working days on average against a ${h.target_days}-day target`} />

                      <div className="relative flex-1" style={{ height: 58 }}>
                        {/* the trapezoid */}
                        <div
                          className="absolute inset-0 transition-transform duration-200"
                          style={{
                            clipPath: `polygon(${(100 - wTop) / 2}% 0%, ${100 - (100 - wTop) / 2}% 0%, ${100 - (100 - wBot) / 2}% 100%, ${(100 - wBot) / 2}% 100%)`,
                            background: empty
                              ? 'repeating-linear-gradient(45deg,#F4F5F7,#F4F5F7 7px,#E9EBEE 7px,#E9EBEE 14px)'
                              : `linear-gradient(180deg, rgba(255,255,255,0.30) 0%, ${colour} 34%, ${colour} 62%, rgba(0,0,0,0.26) 100%), ${colour}`,
                            transform: on ? 'scaleY(1.04)' : 'none',
                            filter: on ? 'brightness(1.06)' : 'none',
                          }}
                        />
                        {/* fill: how much of this band the deals occupy */}
                        {!empty && (
                          <div className="absolute inset-y-0 left-0 flex items-center justify-center"
                               style={{ width: '100%' }}>
                            <div className="flex items-baseline gap-2 text-white drop-shadow">
                              <span className="text-lg font-semibold tabular-nums">{b.count}</span>
                              <span className="text-[11px] opacity-90">KES {kes(b.value)}</span>
                            </div>
                          </div>
                        )}
                        {empty && (
                          <div className="absolute inset-0 flex items-center justify-center">
                            <span className="text-[11px] text-gray-400">nothing here</span>
                          </div>
                        )}
                      </div>

                      <div className="w-52 shrink-0 self-center">
                        <div className={'truncate text-xs font-semibold ' + (empty ? 'text-gray-400' : 'text-gray-800')}
                             title={b.label}>
                          <span className="mr-1 text-gray-400">{open ? '▾' : '▸'}</span>
                          {b.label}
                        </div>
                        <div className="text-[10px] text-gray-400">
                          {b.weight}% · {Math.round(b.probability * 100)}% at exit
                        </div>
                        <div className="text-[10px]" style={{ color: rag }}>
                          {h.status === 'idle'
                            ? 'no deals'
                            : `${h.avg_days}d avg / ${h.target_days}d target`
                              + (h.at_risk ? ` · ${h.at_risk} over` : '')}
                        </div>
                      </div>
                    </div>

                    {open && (
                      <div className="mb-1 ml-4 space-y-1 border-l-2 border-gray-200 pl-3">
                        {b.steps.map((st) => (
                          <div key={st.stage}
                               onClick={(e) => {
                                 e.stopPropagation();
                                 if (st.count && onStageClick && flow) onStageClick(flow.flow, st.stage);
                               }}
                               className={'flex items-center gap-3 text-xs '
                                 + (st.count && onStageClick ? 'cursor-pointer hover:bg-gray-50' : '')}>
                            <span className="w-56 truncate text-gray-600" title={st.stage}>{st.stage}</span>
                            <span className="w-14 text-right tabular-nums text-gray-400">
                              {Math.round(st.probability * 100)}%
                            </span>
                            <div className="h-2 flex-1 overflow-hidden rounded-full bg-gray-100">
                              <div className="h-full rounded-full"
                                   style={{ width: `${b.count ? (st.count / Math.max(b.count, 1)) * 100 : 0}%`,
                                            background: colour }} />
                            </div>
                            <span className="w-10 text-right tabular-nums text-gray-700">{st.count}</span>
                            <span className="w-28 text-right tabular-nums text-gray-500">KES {kes(st.value)}</span>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                );
              })}
            </div>

            {/* What the colours mean — three words, not a paragraph. */}
            <div className="mt-3 flex items-center justify-center gap-4 text-[10px] text-gray-500">
              {[['#669438', 'within target'], ['#E0A02B', 'slipping'],
                ['#C4536F', 'stalled'], ['#D8DBDF', 'no deals']].map(([c, l]) => (
                <span key={l} className="flex items-center gap-1">
                  <span className="inline-block h-2 w-2 rounded-full" style={{ background: c }} />
                  {l}
                </span>
              ))}
            </div>

            <div className="mt-3 flex flex-wrap items-center justify-between gap-2 border-t border-gray-100 pt-3 text-xs">
              <span className="text-gray-500">
                {flow?.deals ?? 0} deals · KES {kes(flow?.value ?? 0)} ·{' '}
                <span className="font-semibold text-gray-800">
                  KES {kes(flow?.weighted ?? 0)} weighted
                </span>
              </span>
            </div>

          </>
        )}
      </Card.Body>
    </Card>
  );
}
'''

LEADERBOARD = r'''// A2 — cumulative ranking, drillable: unit → branch → role → individual.
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

const LEVELS: { key: Level; label: string }[] = [
  { key: 'unit',    label: 'Units' },
  { key: 'segment', label: 'Segments' },
  { key: 'branch',  label: 'Branches' },
  { key: 'role',    label: 'Roles' },
  { key: 'staff',   label: 'Individuals' },
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
  // Three met/not-met gauges: the selected period, the year so far, and
  // today. A single window answers 'how did we do'; the three together
  // answer 'and is it getting better', which is the question a manager
  // actually acts on.
  const [ytd, setYtd] = useState<Leaderboard | null>(null);
  const [today, setToday] = useState<Leaderboard | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      setData(await fetchBranchLogLeaderboard({
        ...periodArgs(findPeriod(periodKey)), level, unit, branch, role,
      }));
      const now = new Date();
      const iso = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}-${String(now.getDate()).padStart(2, '0')}`;
      try {
        setYtd(await fetchBranchLogLeaderboard({
          start: `${now.getFullYear()}-01-01`, end: iso, level, unit, branch, role,
        }));
      } catch { setYtd(null); }
      try {
        setToday(await fetchBranchLogLeaderboard({
          start: iso, end: iso, level, unit, branch, role,
        }));
      } catch { setToday(null); }
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

        {/* Met vs not met on the same scope as the table, across three windows.
            A person-day counts only if it carried a target, so rest days and
            excused days neither flatter nor punish. */}
        {!loading && (
          <div className="mb-3 grid grid-cols-1 gap-3 sm:grid-cols-3">
            {([
              { key: 'sel', label: findPeriod(periodKey).label, d: data },
              { key: 'ytd', label: `Year to date`, d: ytd },
              { key: 'day', label: 'Today', d: today },
            ] as const).map(({ key, label, d }) => {
              const scored = d?.scored_days ?? 0;
              const met = d?.met_days ?? 0;
              return (
                <div key={key}
                     className="flex items-center gap-3 rounded-lg border border-gray-200 bg-gray-50/50 p-3">
                  <ResponsiveContainer width={78} height={78}>
                    <PieChart>
                      <Pie dataKey="value" innerRadius={22} outerRadius={36} paddingAngle={2}
                           data={scored
                             ? [{ name: 'Met', value: met },
                                { name: 'Not met', value: scored - met }]
                             : [{ name: 'No data', value: 1 }]}>
                        {scored
                          ? [<Cell key="m" fill="#669438" />, <Cell key="n" fill="#C4536F" />]
                          : [<Cell key="e" fill="#EDEDED" />]}
                      </Pie>
                      {scored ? <Tooltip formatter={(v: number) => [`${v} person-days`, '']} /> : null}
                    </PieChart>
                  </ResponsiveContainer>
                  <div className="min-w-0 text-xs">
                    <div className="truncate text-[11px] font-medium text-gray-500" title={label}>
                      {label}
                    </div>
                    <div className="text-xl font-semibold text-[#3B6D11]">
                      {scored ? `${d?.met_rate ?? 0}%` : '—'}
                    </div>
                    <div className="text-[10px] text-gray-400">
                      {scored
                        ? `${met.toLocaleString()} met · ${(scored - met).toLocaleString()} missed`
                        : 'nothing carried a target'}
                    </div>
                  </div>
                </div>
              );
            })}
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
                          {' / '}{(r.avg_target ?? 0).toFixed(0)}
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
                              <thead>
                                <tr className="border-b border-gray-200">
                                  <th className="w-8 py-1 pr-2 text-left text-[10px] font-semibold uppercase tracking-wide text-gray-500">#</th>
                                  <th className="py-1 pr-3 text-left text-[10px] font-semibold uppercase tracking-wide text-gray-500" style={{ width: 80 }}>Staff</th>
                                  <th className="py-1 pr-3 text-left text-[10px] font-semibold uppercase tracking-wide text-gray-500">Name</th>
                                  <th className="py-1 pr-3 text-left text-[10px] font-semibold uppercase tracking-wide text-gray-500">Role</th>
                                  <th className="py-1 pr-3 text-left text-[10px] font-semibold uppercase tracking-wide text-gray-500" style={{ width: 110 }}>Segment</th>
                                  <th className="py-1 pr-3 text-right text-[10px] font-semibold uppercase tracking-wide text-gray-500" style={{ width: 90 }}>Avg/day</th>
                                  <th className="py-1 pr-3 text-right text-[10px] font-semibold uppercase tracking-wide text-gray-500" style={{ width: 90 }}>Total index</th>
                                  <th className="py-1 pr-3 text-right text-[10px] font-semibold uppercase tracking-wide text-gray-500" style={{ width: 70 }}>On duty</th>
                                  <th className="py-1 text-right text-[10px] font-semibold uppercase tracking-wide text-gray-500" style={{ width: 60 }}>Met %</th>
                                </tr>
                              </thead>
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
                                    <td className="truncate py-1 pr-3 text-xs text-gray-500" title={m.role}>
                                      {m.role}
                                    </td>
                                    <td className="py-1 pr-3 text-xs text-gray-500">
                                      {/* A branch manager bears the branch rather than sitting
                                          in a segment (ruling 2026-08-09), so they read as
                                          "Branch" instead of showing an empty cell. */}
                                      {m.segment
                                        ? m.segment
                                        : <span className="rounded bg-[#E6F1FB] px-1.5 py-0.5 text-[10px] text-[#0C447C]">Branch</span>}
                                    </td>
                                    <td className="py-1 pr-3 text-right text-xs font-semibold tabular-nums"
                                        style={{ width: 90 }}>
                                      <span className={(m.avg_index ?? 0) >= (m.avg_target ?? 0) && (m.avg_target ?? 0) > 0
                                        ? 'text-[#3B6D11]' : 'text-gray-900'}>
                                        {(m.avg_index ?? 0).toFixed(1)}
                                      </span>
                                      <span className="ml-1 text-[10px] font-normal text-gray-400">
                                        / {(m.avg_target ?? 0).toFixed(0)}
                                      </span>
                                    </td>
                                    <td className="py-1 pr-3 text-right text-xs tabular-nums text-gray-600"
                                        style={{ width: 90 }}>
                                      {Math.round(Number(m.index) || 0).toLocaleString()}
                                    </td>
                                    <td className="py-1 pr-3 text-right text-xs tabular-nums text-gray-500"
                                        style={{ width: 70 }}>
                                      {m.scored_days ?? 0}
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
      </Card.Body>
    </Card>
  );
}
'''

DAILYLOGANALYTICS = r'''// A3 — daily-log analytics. The 80/20 view first, because that is the question
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
  // At a branch the MD-reporting unit is the wrong label — a teller does not
  // think of themselves as under 'Director Consumer & Commercial Banking'.
  // Default to segments when the caller's population sits in one branch.
  const [dim, setDim] = useState<'unit' | 'segment'>('segment');
  const [loading, setLoading] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const p = findPeriod(periodKey);
      const a = periodArgs(p);
      setData(await fetchBranchLogAnalytics(a.days ?? 0, '', a.start ?? '', a.end ?? ''));
      try {
        const lb = await fetchBranchLogLeaderboard({ ...a, level: dim });
        setByUnit(lb);
      } catch { setByUnit(null); }
    } catch (e) {
      toast({ tone: 'danger', message: e instanceof Error ? e.message : 'Could not load analytics.' });
      setData(null);
    } finally {
      setLoading(false);
    }
  }, [periodKey, dim, toast]);

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
                <div className="mb-1 flex items-center justify-between gap-2">
                  <span className="text-xs font-semibold text-gray-600">
                    By {dim === 'segment' ? 'segment' : 'unit'} — cumulative over{' '}
                    {findPeriod(periodKey).label.toLowerCase()}
                  </span>
                  <span className="flex gap-1 text-[11px]">
                    {(['segment', 'unit'] as const).map((d) => (
                      <button key={d} type="button" onClick={() => setDim(d)}
                        className={'rounded-full px-2 py-0.5 '
                          + (dim === d ? 'bg-[#0082BB] text-white'
                                       : 'text-[#005B82] hover:bg-[#0082BB]/10')}>
                        {d === 'segment' ? 'Consumer / Commercial / Operations' : 'Units'}
                      </button>
                    ))}
                  </span>
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
          </Card.Body>
        </Card>
      </div>
    </div>
  );
}
'''

UNITROLLUP = r'''// R2 — the consolidated roll-up for the MD and the Business Manager.
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
  fetchUnitDays, decideBranchDay, fetchBranchLogValidationQueue, fetchNonSubmitters,
  type UnitDays, type UnitRow, type ValidationQueue, type NonSubmitters,
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
  // R3: bank-wide follow-up — every outstanding log across branches AND units.
  const [outstanding, setOutstanding] = useState<NonSubmitters | null>(null);

  const load = useCallback(async (d: string) => {
    setLoading(true);
    try {
      const r = await fetchUnitDays(d);
      setData(r);
      const pending = (r.branches?.children ?? []).filter((x) => x.status === 'submitted').length
        + r.units.filter((x) => x.status === 'submitted').length;
      onCount?.(pending);
      try { setOutstanding(await fetchNonSubmitters(d)); }
      catch { setOutstanding(null); }
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
        : await fetchBranchLogValidationQueue(date, '', row.name));
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
                  <>
                    <tr key={u.key} className={i % 2 === 1 ? 'bg-gray-50/40' : 'bg-white'}>
                      <td className={`${td} text-gray-900`}>
                        <button type="button" onClick={() => void expand(u)}
                                className="flex items-center gap-1.5 text-left hover:text-brand-primary">
                          <span className="text-gray-400">{openKey === u.key ? '▾' : '▸'}</span>
                          {u.name}
                        </button>
                      </td>
                      {numbers(u)}
                      {actions(u)}
                    </tr>
                    {openKey === u.key && (
                      <tr key={`${u.key}-d`}>
                        <td colSpan={8} className="bg-[#F7FBFD] px-6 py-3">
                          {detailLoading && <p className="text-xs text-gray-400">Opening…</p>}
                          {!detailLoading && detail && (detail.rows ?? []).length === 0 && (
                            <p className="text-xs text-gray-400">
                              No direct reports recorded for this unit.
                            </p>
                          )}
                          {!detailLoading && (detail?.rows ?? []).length > 0 && (
                            <table className="w-full">
                              <tbody>
                                {(detail?.rows ?? []).map((m) => (
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
                                          ? <span className="text-amber-600">not filed</span>
                                          : <span className="text-gray-400">awaiting validation</span>}
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
              </tbody>
            </table>
          </div>
        )}
        {/* R3 — bank-wide follow-up. Excused staff are excluded and ageing is in
            BUSINESS days, the same rules the branch view uses, so the numbers
            here cannot disagree with the numbers a branch manager sees. */}
        {!loading && outstanding && outstanding.rows.length > 0 && (
          <div className="mt-6">
            <div className="mb-2 flex flex-wrap items-baseline justify-between gap-2">
              <h3 className="text-sm font-semibold text-gray-800">
                Outstanding daily logs — {outstanding.bank_wide ? 'bank-wide' : 'your scope'}
              </h3>
              <span className="text-xs text-gray-500">
                {outstanding.total} staff have not filed for this day
              </span>
            </div>
            <div className="max-h-96 overflow-auto rounded-lg border border-amber-200">
              <table className="w-full border-separate" style={{ borderSpacing: 0 }}>
                <thead>
                  <tr>
                    <th className={`${th} sticky top-0 bg-[#FAEEDA] text-[#854F0B]`}>Days</th>
                    <th className={`${th} sticky top-0 bg-[#FAEEDA] text-[#854F0B]`}>Staff</th>
                    <th className={`${th} sticky top-0 bg-[#FAEEDA] text-[#854F0B]`}>Name</th>
                    <th className={`${th} sticky top-0 bg-[#FAEEDA] text-[#854F0B]`}>Role</th>
                    <th className={`${th} sticky top-0 bg-[#FAEEDA] text-[#854F0B]`}>Branch / unit</th>
                    <th className={`${th} sticky top-0 bg-[#FAEEDA] text-[#854F0B]`}>Recorded reason</th>
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
          </div>
        )}
      </Card.Body>
    </Card>
  );
}
'''

BRANCHCOUNTERSIGN = r'''// TIER 2 — branch countersign.
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
          </div>
        )}
      </Card.Body>
    </Card>
  );
}
'''

DAILYLOGVALIDATION = r'''// Daily log validation — the Manager Queues tab.
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
  // Thousands separators on every figure (ruling 2026-08-09).
  return Number.isInteger(n)
    ? n.toLocaleString()
    : n.toLocaleString(undefined, { minimumFractionDigits: 1, maximumFractionDigits: 1 });
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

PIPELINEDAYCOUNTERSIGN = r'''// P2 — pipeline day countersign, tiers 2 and 3.
//
// Deliberately the same shape as BranchCountersign for the daily log: a manager
// who has learned one screen has learned both. One row per branch, expandable
// to that branch's deals read-only, with Countersign and Return (note required).
//
// Ruling 2026-08-08 applies unchanged: validation TERMINATES. The Head of
// Branches countersigns a branch pipeline day; the MD and Business Manager
// observe and may return, but never countersign.

import { useCallback, useEffect, useState } from 'react';
import { Button } from '@/components/Button';
import { Card } from '@/components/Card';
import { useToast } from '@/components/Toast';
import {
  fetchPipelineValidationDays, decidePipelineDay, fetchPipelineValidationQueue,
  type PipelineDays, type PipelineDayRow, type PipelineQueue,
} from '@/lib/api';

const STATUS: Record<string, { label: string; cls: string }> = {
  draft:     { label: 'Not closed',    cls: 'bg-gray-100 text-gray-500' },
  submitted: { label: 'Awaiting you',  cls: 'bg-[#FAEEDA] text-[#854F0B]' },
  validated: { label: 'Countersigned', cls: 'bg-[#EAF3DE] text-[#3B6D11]' },
  returned:  { label: 'Returned',      cls: 'bg-[#FBEAF0] text-[#993556]' },
};

function todayIso(): string {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
}

function kes(n: number): string {
  if (!n) return '—';
  return Math.round(n).toLocaleString();
}

export default function PipelineDayCountersign({ onCount }: { onCount?: (n: number) => void }) {
  const { toast } = useToast();
  const [date, setDate] = useState(todayIso());
  const [data, setData] = useState<PipelineDays | null>(null);
  const [loading, setLoading] = useState(false);
  const [openKey, setOpenKey] = useState('');
  const [detail, setDetail] = useState<PipelineQueue | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [returning, setReturning] = useState('');
  const [note, setNote] = useState('');
  const [busy, setBusy] = useState('');

  const load = useCallback(async (d: string) => {
    setLoading(true);
    try {
      const r = await fetchPipelineValidationDays(d);
      setData(r);
      onCount?.(r.rows.filter((x) => x.status === 'submitted').length);
    } catch (e) {
      toast({ tone: 'danger', message: e instanceof Error ? e.message : 'Could not load pipeline days.' });
      setData(null);
    } finally {
      setLoading(false);
    }
  }, [toast, onCount]);

  useEffect(() => { void load(date); }, [date, load]);

  async function expand(row: PipelineDayRow) {
    if (openKey === row.branch) { setOpenKey(''); setDetail(null); return; }
    setOpenKey(row.branch);
    setDetail(null);
    setDetailLoading(true);
    try {
      setDetail(await fetchPipelineValidationQueue(date, row.branch));
    } catch (e) {
      toast({ tone: 'danger', message: e instanceof Error ? e.message : 'Could not open that branch.' });
      setOpenKey('');
    } finally {
      setDetailLoading(false);
    }
  }

  async function decide(row: PipelineDayRow, approve: boolean) {
    if (!approve && !note.trim()) {
      toast({ tone: 'danger', message: 'A note is required when returning a day.' });
      return;
    }
    setBusy(row.branch);
    try {
      await decidePipelineDay(row.branch, date, approve, note.trim());
      toast({ tone: 'success',
              message: approve ? `${row.branch} pipeline day countersigned.`
                               : `${row.branch} returned to the branch.` });
      setReturning(''); setNote('');
      await load(date);
    } catch (e) {
      toast({ tone: 'danger', message: e instanceof Error ? e.message : 'Action failed.' });
    } finally {
      setBusy('');
    }
  }

  const rows = data?.rows ?? [];
  const th = 'whitespace-nowrap px-3 py-2 text-left text-[11px] font-semibold uppercase tracking-wide';
  const td = 'whitespace-nowrap px-3 py-2 text-sm';

  return (
    <Card className="mt-4">
      <Card.Header>
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <h2 className="text-base font-semibold text-gray-900">Pipeline day — branches</h2>
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
        {loading && <p className="py-8 text-center text-sm text-gray-400">Loading…</p>}

        {!loading && data && data.working_day === false && (
          <p className="py-8 text-center text-sm text-gray-500">
            {data.label || 'Rest day'} — no pipeline day is expected.
          </p>
        )}

        {!loading && data?.working_day !== false && rows.length === 0 && (
          <p className="py-8 text-center text-sm text-gray-400">
            No branches consolidate to you for this day.
          </p>
        )}

        {!loading && rows.length > 0 && (
          <div className="overflow-auto rounded-lg border border-gray-200">
            <table className="w-full border-separate" style={{ borderSpacing: 0 }}>
              <thead>
                <tr>
                  <th className={`${th} bg-gray-100 text-gray-600`}>Branch</th>
                  <th className={`${th} bg-gray-100 text-gray-600`}>Deals</th>
                  <th className={`${th} bg-gray-100 text-gray-600`}>Validated</th>
                  <th className={`${th} bg-gray-100 text-gray-600`}>Pending</th>
                  <th className={`${th} bg-[#003D57] text-white`}>Value (KES)</th>
                  <th className={`${th} bg-gray-100 text-gray-600`}>Status</th>
                  <th className={`${th} bg-gray-100 text-gray-600`}>Decision</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((r, i) => {
                  const st = STATUS[r.status] ?? STATUS.draft;
                  const bg = i % 2 === 1 ? 'bg-gray-50/40' : 'bg-white';
                  const canAct = r.status === 'submitted'
                    && (!data?.top_of_house || (data?.can_return ?? false));
                  return (
                    <>
                      <tr key={r.branch}>
                        <td className={`${td} ${bg} font-medium text-gray-900`}>
                          <button type="button" onClick={() => void expand(r)}
                                  className="flex items-center gap-1.5 hover:text-brand-primary">
                            <span className="text-gray-400">{openKey === r.branch ? '▾' : '▸'}</span>
                            {r.branch}
                          </button>
                        </td>
                        <td className={`${td} ${bg} tabular-nums text-gray-700`}>{r.deals}</td>
                        <td className={`${td} ${bg} tabular-nums text-[#3B6D11]`}>{r.validated}</td>
                        <td className={`${td} ${bg} tabular-nums ${r.pending ? 'text-amber-600' : 'text-gray-300'}`}>
                          {r.pending || '—'}
                        </td>
                        <td className={`${td} ${bg} tabular-nums font-semibold text-[#003D57]`}>
                          {kes(r.value)}
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
                          {!canAct ? (
                            <span className="text-[11px] text-gray-400">—</span>
                          ) : returning === r.branch ? (
                            <div className="flex flex-col gap-1" style={{ minWidth: 210 }}>
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
                              {!data?.top_of_house && (
                                <Button size="sm" disabled={busy === r.branch}
                                        onClick={() => void decide(r, true)}>Countersign</Button>
                              )}
                              <Button size="sm" variant="ghost"
                                      onClick={() => { setReturning(r.branch); setNote(''); }}>
                                Return
                              </Button>
                            </div>
                          )}
                        </td>
                      </tr>

                      {openKey === r.branch && (
                        <tr key={`${r.branch}-d`}>
                          <td colSpan={7} className="bg-[#F7FBFD] px-6 py-3">
                            {detailLoading && <p className="text-xs text-gray-400">Opening {r.branch}…</p>}
                            {!detailLoading && (detail?.rows ?? []).length === 0 && (
                              <p className="text-xs text-gray-400">No deals recorded for this day.</p>
                            )}
                            {!detailLoading && (detail?.rows ?? []).length > 0 && (
                              <table className="w-full">
                                <tbody>
                                  {(detail?.rows ?? []).map((d) => (
                                    <tr key={d.deal_id} className="border-b border-gray-100 last:border-0">
                                      <td className="py-1 pr-3 text-xs tabular-nums text-gray-500" style={{ width: 80 }}>
                                        {d.deal_id}
                                      </td>
                                      <td className="py-1 pr-3 text-xs text-gray-800">{d.staff_name}</td>
                                      <td className="py-1 pr-3 text-xs text-gray-500">{d.client}</td>
                                      <td className="py-1 pr-3 text-xs text-gray-500">{d.product}</td>
                                      <td className="py-1 pr-3 text-xs tabular-nums text-gray-700" style={{ width: 80 }}>
                                        {kes(d.deal_value)}
                                      </td>
                                      <td className="py-1 text-xs" style={{ width: 130 }}>
                                        {d.validated
                                          ? <span className="text-[#3B6D11]">✓ validated</span>
                                          : <span className="text-amber-600">awaiting validation</span>}
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



FILES = {
    "DefinedFunnel.tsx": DEFINEDFUNNEL,
    "Leaderboard.tsx": LEADERBOARD,
    "DailyLogAnalytics.tsx": DAILYLOGANALYTICS,
    "UnitRollup.tsx": UNITROLLUP,
    "BranchCountersign.tsx": BRANCHCOUNTERSIGN,
    "DailyLogValidation.tsx": DAILYLOGVALIDATION,
    "PipelineDayCountersign.tsx": PIPELINEDAYCOUNTERSIGN,
}

GONE = [
    "Each product's defined stages",
    "Index contribution by impact tier",
    "You countersign the branch day",
    "You are one of the branch management triad",
    "Person-days that carried a target",
    "Auto-submitted logs were swept",
    "Three or more days is past",
    "inferred from win probability",
    "hint:",
]


def main():
    apply = "--apply" in sys.argv
    missing = [f for f in FILES if not os.path.isfile(os.path.join(BASE, f))]
    if missing:
        print("ABORT: not found: %s" % ", ".join(missing))
        print("       Apply the earlier patchers first.")
        return 1

    cur = open(os.path.join(BASE, "DefinedFunnel.tsx"), encoding="utf-8").read()
    if "Each product's defined stages" not in cur:
        print("ABORT: the captions are already gone - UX1 looks applied.")
        return 1

    # Every removed phrase must be absent from EVERY embedded file.
    for name, blob in FILES.items():
        for phrase in GONE:
            if phrase in blob:
                print("ABORT: %r survives in %s." % (phrase, name))
                return 1
        for op, cl in (("{", "}"), ("(", ")")):
            if blob.count(op) != blob.count(cl):
                print("ABORT: %s unbalanced %s%s." % (name, op, cl))
                return 1
    print("  ok  %d components validated, %d phrases confirmed gone"
          % (len(FILES), len(GONE)))

    # Things that must SURVIVE - empty states are answers, not explanations.
    keep = [("DefinedFunnel.tsx", "within target"),
            ("DefinedFunnel.tsx", "nothing here"),
            ("UnitRollup.tsx", "Nothing consolidates to you"),
            ("DailyLogValidation.tsx", "No staff report to you")]
    for name, phrase in keep:
        if phrase not in FILES[name]:
            print("ABORT: %r was lost from %s - empty states must stay." % (phrase, name))
            return 1
    print("  ok  empty states and the colour legend preserved")

    if not apply:
        print("\nDRY RUN - nothing written. Re-run with --apply.")
        return 0

    for name, blob in FILES.items():
        path = os.path.join(BASE, name)
        shutil.copy2(path, path + BACKUP_SUFFIX)
        open(path, "w", encoding="utf-8", newline="").write(blob)
        print("APPLIED %s" % path)

    print("\nNext: pushd frontend\\web && pnpm tsc --noEmit && popd && echo TSC_PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
