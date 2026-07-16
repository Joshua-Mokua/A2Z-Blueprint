// Balanced Scorecard — the real 2026 scorecards.
//
// Tabs are DEPARTMENTS, not people: the MD opens "Commercial" and picks from the team
// in it, rather than reading fifteen first names. The grouping is the register's own
// Department column, and scope comes from the reporting tree, so the same page serves
// every level — a Branch Manager sees their branch, a leaf sees only themselves.
//
// Actuals, targets, achievement and the 1-5 score come from compute_staff_scorecard
// via the API. A scorecard whose source weights were unusable shows its real structure
// with blank weights rather than invented ones.

import { useState, useMemo, useEffect } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Card } from '@/components/Card';
import { Badge } from '@/components/Badge';
import { EmptyState } from '@/components/EmptyState';
import { Skeleton } from '@/components/Skeleton';
import { fetchWhoamiDetailed } from '@/lib/api';
import {
  fetchBscDepartments, fetchBscPillars, fetchBscScorecard,
  pct, scoreTone, achBar, fmtNum, money,
  type BscKpi, type BscObjective, type BscScorecard, type BscPillars,
} from '@/lib/bsc';

const AREA_ORDER = [
  'Financial', 'Customer Focus', 'People & Learning',
  'Operational Excellence', 'Must Win Battles',
];

const MY_TAB = '__me__';

const areaMeta = (area: string, pillars?: BscPillars) => {
  const p = pillars?.pillars.find((x) => x.id === area);
  return { color: p?.color ?? '#464646', label: p?.name ?? area };
};

type Row = { kind: 'kpi'; kpi: BscKpi } | { kind: 'objective'; obj: BscObjective };

// ── the coloured ribbon, matching the credit workbenches ────────────────────
function Ribbon({
  title, subtitle, score, period, complete,
}: {
  title: string; subtitle: string; score: number | null;
  period: string; complete: boolean;
}) {
  const tone = scoreTone(score);
  const toneBg = tone === 'success' ? 'var(--brand-accent)'
    : tone === 'warning' ? '#E8A33D'
    : tone === 'danger' ? '#C0392B' : 'rgba(255,255,255,.18)';
  return (
    <div className="rounded-lg px-6 py-5 text-white"
         style={{ background: 'linear-gradient(100deg, var(--brand-secondary) 0%, var(--brand-primary) 100%)' }}>
      <div className="flex items-start justify-between gap-6 flex-wrap">
        <div>
          <div className="text-[10px] uppercase tracking-[0.14em] opacity-70">
            {period} Scorecard
          </div>
          <h1 className="text-2xl font-semibold mt-1">{title}</h1>
          <p className="text-sm opacity-80 mt-0.5">{subtitle}</p>
        </div>
        <div className="flex items-center gap-3">
          {!complete && (
            <span className="text-[11px] px-2 py-1 rounded"
                  style={{ background: 'rgba(255,255,255,.15)' }}>
              weights pending
            </span>
          )}
          <div className="text-right rounded-lg px-4 py-2" style={{ background: toneBg }}>
            <div className="text-2xl font-bold leading-none">
              {score === null ? '—' : score.toFixed(2)}
            </div>
            <div className="text-[10px] uppercase tracking-wide opacity-90 mt-1">
              overall / 5
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

/** The target in one currency, with the other basis beneath it where the viewer is
 *  allowed to see it. stretch is absent from the payload entirely for everyone else,
 *  so there is nothing to leak here. */
function TargetCell({ kpi, cur }: { kpi: BscKpi; cur: 'kes' | 'usd' }) {
  const shown = kpi.stretch_money ?? kpi.target_money;   // basis already applied server-side
  const other = kpi.stretch_money ? kpi.target_money : null;
  return (
    <div className="leading-tight">
      <div>{money(shown, cur)}</div>
      {other && (
        <div className="text-[10px] text-gray-400" title="plain target">
          {money(other, cur)}
        </div>
      )}
    </div>
  );
}

function AchievementCell({ kpi }: { kpi: BscKpi }) {
  if (kpi.achievement_pct === null) {
    return <span className="text-xs text-gray-300">—</span>;
  }
  const tone = scoreTone(kpi.score);
  const bar = tone === 'success' ? 'var(--brand-accent)'
    : tone === 'warning' ? '#E8A33D' : '#C0392B';
  return (
    <div className="flex items-center gap-2 justify-end">
      <div className="h-1.5 w-16 rounded-full bg-gray-100 overflow-hidden">
        <div className="h-full rounded-full transition-all"
             style={{ width: `${achBar(kpi.achievement_pct)}%`, background: bar }} />
      </div>
      <span className="text-xs tabular-nums text-gray-700 w-11 text-right">
        {kpi.achievement_pct.toFixed(0)}%
      </span>
    </div>
  );
}

function AreaSection({
  area, rows, areaWeight, pillars, complete,
}: {
  area: string; rows: Row[]; areaWeight: number | null;
  pillars?: BscPillars; complete: boolean;
}) {
  const { color, label } = areaMeta(area, pillars);
  const scored = rows.filter((r) => r.kind === 'kpi' && r.kpi.score !== null);
  const avg = scored.length
    ? scored.reduce((s, r) => s + ((r as { kpi: BscKpi }).kpi.score ?? 0), 0) / scored.length
    : null;

  return (
    <Card padding="none" className="overflow-hidden">
      <div className="flex items-center justify-between px-5 py-3"
           style={{ background: `${color}0F`, borderLeft: `4px solid ${color}` }}>
        <div className="flex items-baseline gap-3">
          <h3 className="text-sm font-semibold" style={{ color }}>{label}</h3>
          <span className="text-xs text-gray-500">
            {rows.length} measure{rows.length === 1 ? '' : 's'}
            {scored.length > 0 && ` · ${scored.length} scored`}
          </span>
        </div>
        <div className="flex items-center gap-5">
          {avg !== null && (
            <Badge tone={scoreTone(avg)} size="sm">avg {avg.toFixed(2)}</Badge>
          )}
          <div className="text-right">
            <div className="text-base font-semibold" style={{ color }}>
              {areaWeight === null ? '—' : pct(areaWeight, 0)}
            </div>
            <div className="text-[9px] uppercase tracking-wide text-gray-400">weight</div>
          </div>
        </div>
      </div>

      <table className="w-full text-sm table-fixed">
        <thead>
          <tr className="text-[10px] uppercase tracking-wide text-gray-400 bg-gray-50/70">
            <th className="text-left   font-medium pl-5 pr-2 py-2 w-[30%]">Measure</th>
            <th className="text-right  font-medium px-2 py-2 w-[7%]">Weight</th>
            <th className="text-right  font-medium px-2 py-2 w-[13%]">Target (KES)</th>
            <th className="text-right  font-medium px-2 py-2 w-[12%]">Target (USD)</th>
            <th className="text-right  font-medium px-2 py-2 w-[11%]">Actual</th>
            <th className="text-right  font-medium px-2 py-2 w-[19%]">Achievement</th>
            <th className="text-center font-medium pr-5 pl-2 py-2 w-[8%]">Score</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r, i) => {
            const isKpi = r.kind === 'kpi';
            const weight = isKpi ? r.kpi.weight : r.obj.weight;
            return (
              <tr key={i} className="border-t border-gray-100 hover:bg-gray-50/60">
                <td className="pl-5 pr-2 py-2">
                  <div className="flex items-start gap-2">
                    <span className="text-gray-800 leading-snug">
                      {isKpi ? r.kpi.name : r.obj.text}
                    </span>
                    {!isKpi && (
                      <Badge tone="info" size="sm">
                        {r.obj.due ? `due ${r.obj.due}` : 'objective'}
                      </Badge>
                    )}
                  </div>
                  {isKpi && (() => {
                    // Both hints are inline spans; without a separator they rendered
                    // as "lower is betterno target set".
                    const hints = [
                      r.kpi.direction === 'lower' ? 'lower is better' : null,
                      r.kpi.target_source === 'missing' && r.kpi.actual === null
                        ? 'no target set' : null,
                    ].filter(Boolean);
                    return hints.length ? (
                      <span className="text-[10px] text-gray-400">{hints.join(' · ')}</span>
                    ) : null;
                  })()}
                </td>
                <td className="px-2 py-2 text-right text-xs tabular-nums font-medium text-gray-700">
                  {weight === null || weight === undefined || !complete ? '—' : pct(weight)}
                </td>
                {/* Money rows carry both currencies; a percentage or a count converts
                    to nothing, so it shows its plain value under Target (KES) and
                    leaves the USD column empty rather than inventing a conversion. */}
                <td className="px-2 py-2 text-right text-xs tabular-nums text-gray-700">
                  {!isKpi ? '—'
                    : r.kpi.currency
                      ? <TargetCell kpi={r.kpi} cur="kes" />
                      : <span>{fmtNum(r.kpi.target)}
                          {r.kpi.unit ? <span className="text-gray-400"> {r.kpi.unit}</span> : null}
                        </span>}
                </td>
                <td className="px-2 py-2 text-right text-xs tabular-nums text-gray-600">
                  {isKpi && r.kpi.currency ? <TargetCell kpi={r.kpi} cur="usd" />
                                            : <span className="text-gray-300">—</span>}
                </td>
                <td className="px-2 py-2 text-right text-xs tabular-nums text-gray-800 font-medium">
                  {!isKpi ? '—'
                    : r.kpi.currency && r.kpi.actual_money
                      ? money(r.kpi.actual_money, 'kes')
                      : fmtNum(r.kpi.actual)}
                </td>
                <td className="px-2 py-2">
                  {isKpi ? <AchievementCell kpi={r.kpi} />
                         : <span className="text-xs text-gray-300 block text-right">—</span>}
                </td>
                <td className="pr-5 pl-2 py-2 text-center">
                  {isKpi && r.kpi.score !== null ? (
                    <Badge tone={scoreTone(r.kpi.score)} size="sm">
                      {r.kpi.score.toFixed(1)}
                    </Badge>
                  ) : <span className="text-xs text-gray-300">—</span>}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </Card>
  );
}

function Scorecard({ staffCode, pillars, basis, onBasis }: {
  staffCode: string; pillars?: BscPillars;
  basis: string; onBasis: (b: string) => void;
}) {
  const { data, isLoading, error } = useQuery<BscScorecard>({
    queryKey: ['bsc-scorecard', staffCode, basis],
    queryFn: () => fetchBscScorecard(staffCode, basis),
    enabled: !!staffCode,
    placeholderData: (prev) => prev,   // keep the last card while switching tabs
  });

  const grouped = useMemo(() => {
    const m = new Map<string, Row[]>();
    (data?.kpis ?? []).forEach((k) => {
      if (!m.has(k.area)) m.set(k.area, []);
      m.get(k.area)!.push({ kind: 'kpi', kpi: k });
    });
    (data?.objectives ?? []).forEach((o) => {
      if (!m.has(o.area)) m.set(o.area, []);
      m.get(o.area)!.push({ kind: 'objective', obj: o });
    });
    return m;
  }, [data]);

  const areas = useMemo(() => {
    const rank = (a: string) => {
      const i = AREA_ORDER.indexOf(a);
      return i === -1 ? AREA_ORDER.length : i;
    };
    return [...grouped.keys()].sort((a, b) => rank(a) - rank(b) || a.localeCompare(b));
  }, [grouped]);

  if (isLoading && !data) {
    return <div className="space-y-3">{[0, 1, 2].map((i) => <Skeleton key={i} />)}</div>;
  }
  if (error) {
    return <EmptyState title="Could not load this scorecard"
                       message={(error as Error).message} />;
  }
  if (!data?.has_scorecard) {
    return (
      <EmptyState
        title="No scorecard for this role yet"
        message={`No KPIs are assigned to "${data?.staff?.role || data?.role || 'this role'}". An administrator can build one in the KPI Library.`}
      />
    );
  }

  return (
    <div className="space-y-4">
      <Ribbon
        title={data.staff?.display_name || data.staff?.full_name || 'Scorecard'}
        subtitle={`${data.staff?.role || data.role}${data.staff?.department ? ` · ${data.staff.department}` : ''}`}
        score={data.final_score}
        period={data.period}
        complete={data.weights_complete}
      />

      <div className="flex flex-wrap items-center gap-2 text-xs text-gray-500">
        {data.can_switch_basis && (
          <div className="flex items-center gap-1 mr-2">
            {(['stretch', 'target'] as const).map((b) => (
              <button
                key={b}
                onClick={() => onBasis(b)}
                className={[
                  'px-2.5 py-1 rounded text-[11px] border transition-colors',
                  data.basis === b
                    ? 'bg-brand-primary text-white border-brand-primary'
                    : 'bg-white text-gray-500 border-gray-200 hover:text-gray-800',
                ].join(' ')}
              >
                {b === 'stretch' ? 'Stretch' : 'Target'}
              </button>
            ))}
            <span className="text-[10px] text-gray-400 ml-1">
              scoring basis · FX {data.fx_kes_per_usd}
            </span>
          </div>
        )}
        <span>{data.kpis.length} measures</span>
        {data.objectives.length > 0 && <><span>·</span><span>{data.objectives.length} objectives</span></>}
        <span>·</span>
        <span>{data.scored_count} scored</span>
        {data.weights_complete && (
          <Badge tone={Math.abs(data.total_weight - 1) < 0.02 ? 'success' : 'warning'} size="sm">
            weights {pct(data.total_weight, 0)}
          </Badge>
        )}
        {data.source_ambiguous && <Badge tone="warning" size="sm">source ambiguous</Badge>}
      </div>

      {!data.weights_complete && (
        <Card padding="sm" className="border-amber-200 bg-amber-50">
          <p className="text-xs text-amber-800">
            <span className="font-semibold">Weights not yet set.</span>{' '}
            {data.weights_pending_reason ||
              'The source scorecard did not provide usable weights.'}{' '}
            The measures are correct; the weights are left blank rather than estimated,
            and can be entered in admin once confirmed.
          </p>
        </Card>
      )}

      {areas.map((a) => (
        <AreaSection
          key={a} area={a} rows={grouped.get(a)!}
          areaWeight={data.areas?.[a] ?? null}
          pillars={pillars} complete={data.weights_complete}
        />
      ))}
    </div>
  );
}

export function Perform() {
  const { data: me } = useQuery({
    queryKey: ['whoami-detailed'], queryFn: fetchWhoamiDetailed,
  });
  const { data: depts, error: deptError } = useQuery({
    queryKey: ['bsc-departments'], queryFn: fetchBscDepartments,
  });
  const { data: pillars } = useQuery({
    queryKey: ['bsc-pillars'], queryFn: fetchBscPillars,
  });

  const [tab, setTab] = useState<string>(MY_TAB);
  const [picked, setPicked] = useState<Record<string, string>>({});
  // '' lets the server apply the admin default; only the permitted roles can move it.
  const [basis, setBasis] = useState<string>('');

  const activeDept = useMemo(
    () => depts?.departments.find((d) => d.department === tab),
    [depts, tab],
  );

  // Default each department to its head (or first person) the first time it opens.
  useEffect(() => {
    if (activeDept && !picked[activeDept.department]) {
      const first = activeDept.head?.staff_code || activeDept.people[0]?.staff_code;
      if (first) setPicked((p) => ({ ...p, [activeDept.department]: first }));
    }
  }, [activeDept, picked]);

  const meCode = depts?.me.staff_code || me?.staff_code || '';
  const active = tab === MY_TAB ? meCode : (picked[activeDept?.department ?? ''] ?? '');

  return (
    <div className="p-6 space-y-4">
      {deptError && (
        <Card padding="sm" className="border-red-200 bg-red-50">
          <p className="text-xs text-red-800">
            <span className="font-semibold">Could not load departments.</span>{' '}
            {(deptError as Error).message}
            {meCode ? ' — your own scorecard is shown below.' : ''}
          </p>
        </Card>
      )}

      {depts && depts.departments.length > 0 && (
        <div className="flex gap-1 border-b border-gray-200 overflow-x-auto">
          <button
            onClick={() => setTab(MY_TAB)}
            className={[
              'px-4 py-2 text-sm whitespace-nowrap border-b-2 -mb-px transition-colors',
              tab === MY_TAB
                ? 'border-brand-primary text-brand-primary font-medium'
                : 'border-transparent text-gray-500 hover:text-gray-800',
            ].join(' ')}
          >
            My scorecard
          </button>
          {depts.departments.map((d) => {
            const on = tab === d.department;
            return (
              <button
                key={d.department}
                onClick={() => setTab(d.department)}
                title={`${d.total} people · ${d.scorecard_count} with a scorecard`}
                className={[
                  'px-4 py-2 text-sm whitespace-nowrap border-b-2 -mb-px transition-colors',
                  on
                    ? 'border-brand-primary text-brand-primary font-medium'
                    : 'border-transparent text-gray-500 hover:text-gray-800',
                ].join(' ')}
              >
                {d.department}
                <span className="ml-1.5 text-[10px] text-gray-400">{d.total}</span>
              </button>
            );
          })}
        </div>
      )}

      {activeDept && (
        <div className="flex items-center gap-3">
          <label className="text-xs text-gray-500">{activeDept.department}</label>
          <select
            value={picked[activeDept.department] ?? ''}
            onChange={(e) => setPicked((p) => ({ ...p, [activeDept.department]: e.target.value }))}
            className="text-sm border border-gray-200 rounded-md px-3 py-1.5 bg-white
                       focus:outline-none focus:ring-2 focus:ring-brand-primary/30"
          >
            {activeDept.people.map((p) => (
              <option key={p.staff_code} value={p.staff_code}>
                {p.display_name} — {p.role}
                {p.has_scorecard ? '' : ' (no scorecard)'}
              </option>
            ))}
          </select>
          <span className="text-xs text-gray-400">
            {activeDept.scorecard_count} of {activeDept.total} have a 2026 scorecard
          </span>
        </div>
      )}

      {active
        ? <Scorecard staffCode={active} pillars={pillars}
                     basis={basis} onBasis={setBasis} />
        : <Skeleton />}
    </div>
  );
}
