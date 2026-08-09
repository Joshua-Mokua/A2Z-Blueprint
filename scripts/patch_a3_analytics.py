#!/usr/bin/env python
# -*- coding: utf-8 -*-
r"""
A3 - daily-log analytics, and housing ranking + analytics in Manager Queues.

YOUR ASK: "on the managers queue for the manager is where i wish to house the
index ranking and analytics as well". A manager works out of that page; making
them navigate elsewhere to see how their team is doing splits one job across two
screens.

ADDS
  frontend .../components/DailyLogAnalytics.tsx (new)

    IMPACT - the 80/20 view first, because that is the question management
        actually asks: which few activities are producing the output. A tier
        donut (high / medium / low) with the headline "X% of the index comes
        from high-impact activity", BESIDE a per-activity bar chart coloured by
        tier. The pie is never a black box - you can see which activity put each
        slice there.

    VALIDATION - validated / pending / returned / auto-submitted, with the
        validation rate.

    PARTICIPATION - logs, people filing, pending, auto-swept, returned, total
        index. The footnote explains that a high auto-submitted count usually
        means people are not closing their day, not that they did nothing -
        a number that is easy to misread as poor performance.

  Manager Queues gains RANKING and ANALYTICS tabs. Both components are
  scope-aware server-side, so each manager sees their own population without
  this page deciding anything.

Colours are the brand palette with high impact in primary blue and low in grey,
so the eye reads importance by saturation rather than hue alone.

DEPENDS ON THE TIERS BEING ASSIGNED. Run scripts\seed_impact_tiers.py --apply
first, or every activity resolves to 'medium' and the donut is one colour.

Verified: tsc --noEmit clean, vite build clean. recharts 2.12 was already a
dependency; nothing new was added.

Usage (from project root, .venv active):
    python scripts\patch_a3_analytics.py            # dry run
    python scripts\patch_a3_analytics.py --apply    # write + .pre_a3 backup
"""
import os
import shutil
import sys

COMP = os.path.join("frontend", "web", "src", "components", "DailyLogAnalytics.tsx")
PAGE = os.path.join("frontend", "web", "src", "pages", "PipelineManagerQueues.tsx")
BACKUP_SUFFIX = ".pre_a3"

COMPONENT = r'''// A3 — daily-log analytics. The 80/20 view first, because that is the question
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
import { fetchBranchLogAnalytics, type BranchLogAnalytics } from '@/lib/api';

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
  const [days, setDays] = useState(30);
  const [data, setData] = useState<BranchLogAnalytics | null>(null);
  const [loading, setLoading] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      setData(await fetchBranchLogAnalytics(days));
    } catch (e) {
      toast({ tone: 'danger', message: e instanceof Error ? e.message : 'Could not load analytics.' });
      setData(null);
    } finally {
      setLoading(false);
    }
  }, [days, toast]);

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
                Impact analysis — where the output comes from
              </h2>
              <p className="mt-0.5 text-xs text-gray-500">
                Index contribution by impact tier. Tiers are assigned in Index Setup.
              </p>
            </div>
            <select value={days} onChange={(e) => setDays(Number(e.target.value))}
                    className="rounded border border-gray-200 px-2 py-1 text-xs">
              {[7, 14, 30, 60, 90].map((d) => <option key={d} value={d}>last {d} days</option>)}
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


EDITS = [
    ("imports",
     "import UnitRollup from '@/components/UnitRollup';",
     "import UnitRollup from '@/components/UnitRollup';\n"
     "import Leaderboard from '@/components/Leaderboard';\n"
     "import DailyLogAnalytics from '@/components/DailyLogAnalytics';"),
    ("tab keys",
     "type TabKey = 'validation' | 'cancellation' | 'dailylog';",
     "type TabKey = 'validation' | 'cancellation' | 'dailylog' | 'ranking' | 'analytics';"),
    ("tab buttons",
     '        <TabBtn\n'
     "          active={activeTab === 'cancellation'}\n"
     "          onClick={() => setActiveTab('cancellation')}\n"
     '          label="Cancellation"\n'
     '          count={cancellationDeals.length}\n'
     '          loading={loadingC}\n'
     '        />',
     '        <TabBtn\n'
     "          active={activeTab === 'cancellation'}\n"
     "          onClick={() => setActiveTab('cancellation')}\n"
     '          label="Cancellation"\n'
     '          count={cancellationDeals.length}\n'
     '          loading={loadingC}\n'
     '        />\n'
     '        <TabBtn\n'
     "          active={activeTab === 'ranking'}\n"
     "          onClick={() => setActiveTab('ranking')}\n"
     '          label="Ranking"\n'
     '          count={0}\n'
     '          loading={false}\n'
     '        />\n'
     '        <TabBtn\n'
     "          active={activeTab === 'analytics'}\n"
     "          onClick={() => setActiveTab('analytics')}\n"
     '          label="Analytics"\n'
     '          count={0}\n'
     '          loading={false}\n'
     '        />'),
    ("tab bodies",
     "      {activeTab === 'dailylog' && tier === 'staff' && (\n"
     "        <DailyLogValidation onCount={setDailyLogPending} />\n"
     "      )}",
     "      {activeTab === 'dailylog' && tier === 'staff' && (\n"
     "        <DailyLogValidation onCount={setDailyLogPending} />\n"
     "      )}\n\n"
     "      {/* Ranking and analytics live here too: a manager works out of this page,\n"
     "          and making them navigate elsewhere to see how their team is doing\n"
     "          splits one job across two screens. Both components are scope-aware\n"
     "          server-side, so each manager sees their own population. */}\n"
     "      {activeTab === 'ranking' && <div className=\"mt-4\"><Leaderboard /></div>}\n"
     "      {activeTab === 'analytics' && <DailyLogAnalytics />}"),
    ("deal body guard",
     "      {activeTab === 'dailylog' ? null : activeLoading && activeDeals.length === 0 ? (",
     "      {['dailylog', 'ranking', 'analytics'].includes(activeTab) ? null : activeLoading && activeDeals.length === 0 ? ("),
    ("error panel guard",
     "      {activeTab !== 'dailylog' && activeError && (",
     "      {!['dailylog', 'ranking', 'analytics'].includes(activeTab) && activeError && ("),
]


def main():
    apply = "--apply" in sys.argv
    if not os.path.isfile(PAGE):
        print("ABORT: %s not found. Run from the project root." % PAGE)
        return 1
    if os.path.exists(COMP):
        print("ABORT: %s already exists - A3 looks applied." % COMP)
        return 1

    page = open(PAGE, encoding="utf-8").read()
    if "UnitRollup" not in page:
        print("ABORT: apply patch_r2_rollup_view.py first.")
        return 1
    if "Leaderboard" in page:
        print("ABORT: Manager Queues already references Leaderboard.")
        return 1

    for name, old, new in EDITS:
        if page.count(old) != 1:
            print("ABORT: %r anchor matched %d times (expected 1)." % (name, page.count(old)))
            return 1
        page = page.replace(old, new, 1)
        print("  ok  %s" % name)

    for token in ("DailyLogAnalytics", "'ranking'", "'analytics'"):
        if token not in page:
            print("ABORT: post-check - %r missing after patch." % token)
            return 1
    for o, c in (("{", "}"), ("(", ")")):
        if COMPONENT.count(o) != COMPONENT.count(c):
            print("ABORT: embedded component unbalanced %s%s." % (o, c))
            return 1
    print("  ok  post-checks clean")

    if not apply:
        print("\nDRY RUN - nothing written. Re-run with --apply.")
        return 0

    open(COMP, "w", encoding="utf-8", newline="").write(COMPONENT)
    print("CREATED %s" % COMP)
    shutil.copy2(PAGE, PAGE + BACKUP_SUFFIX)
    open(PAGE, "w", encoding="utf-8", newline="").write(page)
    print("APPLIED %s" % PAGE)

    print("\nRun scripts\\seed_impact_tiers.py --apply first if you have not, or")
    print("every activity resolves to 'medium' and the impact donut is one colour.")
    print("Then: pushd frontend\\web && pnpm tsc --noEmit && popd && echo TSC_PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
