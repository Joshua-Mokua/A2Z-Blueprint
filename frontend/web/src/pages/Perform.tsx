// Balanced Scorecard — the real 2026 scorecards, per role.
//
// Tabs across the people whose scorecards the viewer may open: the API scopes that
// through the reporting tree, so this replicates down the hierarchy without any
// role-specific code here — a Branch Manager sees their branch, the MD sees EXCO.
//
// A scorecard whose source weights were unusable is shown as incomplete rather than
// filled with invented numbers: the structure is real, the weights are pending admin.

import { useState, useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';
import { PageHeader } from '@/components/PageHeader';
import { Card } from '@/components/Card';
import { Badge } from '@/components/Badge';
import { EmptyState } from '@/components/EmptyState';
import { Skeleton } from '@/components/Skeleton';
import { fetchWhoamiDetailed } from '@/lib/api';
import {
  fetchBscTeam, fetchBscPillars, fetchBscScorecard, pct,
  type BscKpi, type BscObjective, type BscScorecard, type BscPillars,
} from '@/lib/bsc';

const AREA_ORDER = [
  'Financial', 'Customer Focus', 'People & Learning',
  'Operational Excellence', 'Must Win Battles',
];

function areaColor(area: string, pillars?: BscPillars): string {
  return pillars?.pillars.find((p) => p.id === area)?.color ?? '#464646';
}

function areaLabel(area: string, pillars?: BscPillars): string {
  return pillars?.pillars.find((p) => p.id === area)?.name ?? area;
}

/** KPIs and objectives share the area weighting, so they render as one list. */
type Row =
  | { kind: 'kpi'; kpi: BscKpi }
  | { kind: 'objective'; obj: BscObjective };

function AreaSection({
  area, rows, areaWeight, pillars, complete,
}: {
  area: string; rows: Row[]; areaWeight: number | null;
  pillars?: BscPillars; complete: boolean;
}) {
  const color = areaColor(area, pillars);
  const measured = rows.reduce(
    (s, r) => s + (r.kind === 'kpi' ? r.kpi.weight : r.obj.weight ?? 0), 0,
  );
  return (
    <Card padding="none" className="overflow-hidden">
      <div className="flex items-center justify-between px-5 py-3 border-b border-gray-200"
           style={{ borderLeft: `4px solid ${color}` }}>
        <div>
          <h3 className="text-sm font-semibold" style={{ color }}>
            {areaLabel(area, pillars)}
          </h3>
          <p className="text-xs text-gray-500 mt-0.5">
            {rows.length} measure{rows.length === 1 ? '' : 's'}
            {complete && ` · ${pct(measured)} of the scorecard`}
          </p>
        </div>
        <div className="text-right">
          <div className="text-lg font-semibold text-gray-800">
            {areaWeight === null ? '—' : pct(areaWeight, 0)}
          </div>
          <div className="text-[10px] uppercase tracking-wide text-gray-400">area weight</div>
        </div>
      </div>

      <table className="w-full text-sm">
        <thead>
          <tr className="text-[11px] uppercase tracking-wide text-gray-400 bg-gray-50">
            <th className="text-left font-medium px-5 py-2">Measure</th>
            <th className="text-left font-medium px-3 py-2 w-24">Unit</th>
            <th className="text-right font-medium px-3 py-2 w-28">Within area</th>
            <th className="text-right font-medium px-5 py-2 w-28">Weight</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r, i) => {
            const isKpi = r.kind === 'kpi';
            const name = isKpi ? r.kpi.name : r.obj.text;
            const within = isKpi ? r.kpi.within_area_weight : r.obj.within_area_weight;
            const weight = isKpi ? r.kpi.weight : r.obj.weight;
            return (
              <tr key={i} className="border-t border-gray-100 hover:bg-gray-50">
                <td className="px-5 py-2.5">
                  <div className="flex items-start gap-2">
                    <span className="text-gray-800">{name}</span>
                    {!isKpi && (
                      <Badge tone="info" size="sm">
                        {r.obj.due ? `due ${r.obj.due}` : 'objective'}
                      </Badge>
                    )}
                    {isKpi && !r.kpi.defined && (
                      <Badge tone="danger" size="sm">undefined</Badge>
                    )}
                  </div>
                  {isKpi && r.kpi.direction === 'lower' && (
                    <span className="text-[10px] text-gray-400">lower is better</span>
                  )}
                </td>
                <td className="px-3 py-2.5 text-gray-500 text-xs">
                  {isKpi ? r.kpi.unit || '—' : '—'}
                </td>
                <td className="px-3 py-2.5 text-right text-gray-500 text-xs">
                  {within === null || within === undefined ? '—' : pct(within, 0)}
                </td>
                <td className="px-5 py-2.5 text-right font-medium text-gray-800">
                  {weight === null || weight === undefined || !complete ? '—' : pct(weight)}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </Card>
  );
}

function Scorecard({ staffCode, pillars }: { staffCode: string; pillars?: BscPillars }) {
  const { data, isLoading, error } = useQuery<BscScorecard>({
    queryKey: ['bsc-scorecard', staffCode],
    queryFn: () => fetchBscScorecard(staffCode),
    enabled: !!staffCode,
  });

  // Every hook runs before any early return — hooks must not sit behind a branch.
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

  // Canonical area order first, anything unrecognised after it, alphabetically.
  const areas = useMemo(() => {
    const rank = (a: string) => {
      const i = AREA_ORDER.indexOf(a);
      return i === -1 ? AREA_ORDER.length : i;
    };
    return [...grouped.keys()].sort((a, b) => rank(a) - rank(b) || a.localeCompare(b));
  }, [grouped]);

  if (isLoading) {
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
        message={`No KPIs are assigned to "${data?.role || 'this role'}". An administrator can build one in the KPI Library.`}
      />
    );
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-sm text-gray-500">{data.staff?.role || data.role}</span>
        <span className="text-gray-300">·</span>
        <span className="text-sm text-gray-500">
          {data.kpis.length} measures
          {data.objectives.length > 0 && ` · ${data.objectives.length} objectives`}
        </span>
        {data.weights_complete ? (
          <Badge tone={Math.abs(data.total_weight - 1) < 0.02 ? 'success' : 'warning'} size="sm">
            weights total {pct(data.total_weight, 0)}
          </Badge>
        ) : (
          <Badge tone="warning" size="sm">weights pending</Badge>
        )}
        {data.source_ambiguous && <Badge tone="warning" size="sm">source ambiguous</Badge>}
      </div>

      {!data.weights_complete && (
        <Card padding="sm" className="border-amber-200 bg-amber-50">
          <p className="text-xs text-amber-800">
            <span className="font-semibold">Weights not yet set.</span>{' '}
            {data.weights_pending_reason ||
              'The source scorecard did not provide usable weights.'}{' '}
            The measures below are correct; the weights are left blank rather than
            estimated, and can be entered in admin once confirmed.
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
  const { data: team, isLoading: teamLoading, error: teamError } = useQuery({
    queryKey: ['bsc-team'], queryFn: fetchBscTeam,
  });
  const { data: pillars } = useQuery({
    queryKey: ['bsc-pillars'], queryFn: fetchBscPillars,
  });
  // Own identity, so a failing /team still leaves the viewer their own scorecard.
  // Deriving the active tab solely from /team meant one failed request blanked the
  // whole page — including the scorecard the error message promised was below.
  const { data: me } = useQuery({
    queryKey: ['whoami-detailed'], queryFn: fetchWhoamiDetailed,
  });
  const [selected, setSelected] = useState<string>('');

  const tabs = useMemo(() => {
    if (!team) return [];
    return [{ ...team.me, label: 'My scorecard' },
            ...team.reports.map((r) => ({ ...r, label: r.display_name }))];
  }, [team]);

  const active = selected || team?.me.staff_code || me?.staff_code || '';

  return (
    <div className="p-6 space-y-5">
      <PageHeader
        title="Balanced Scorecard"
        subtitle={
          team && team.reports.length > 0
            ? `Your scorecard, and your ${team.direct_report_count} direct report${team.direct_report_count === 1 ? '' : 's'}`
            : 'Your scorecard'
        }
      />

      {teamError && (
        <Card padding="sm" className="border-red-200 bg-red-50">
          <p className="text-xs text-red-800">
            <span className="font-semibold">Could not load your team.</span>{' '}
            {(teamError as Error).message}
            {me?.staff_code
              ? ' — your own scorecard is shown below; reportee tabs are unavailable.'
              : ' — no scorecard can be shown until this is resolved.'}
          </p>
        </Card>
      )}

      {teamLoading ? (
        <Skeleton />
      ) : tabs.length > 1 ? (
        <div className="flex gap-1 border-b border-gray-200 overflow-x-auto">
          {tabs.map((t) => {
            const on = t.staff_code === active;
            return (
              <button
                key={t.staff_code}
                onClick={() => setSelected(t.staff_code)}
                className={[
                  'px-4 py-2 text-sm whitespace-nowrap border-b-2 -mb-px transition-colors',
                  on
                    ? 'border-brand-primary text-brand-primary font-medium'
                    : 'border-transparent text-gray-500 hover:text-gray-800',
                ].join(' ')}
              >
                {t.label}
                {!t.has_scorecard && (
                  <span className="ml-1.5 text-[10px] text-gray-400"
                        title="No scorecard for this role yet">○</span>
                )}
              </button>
            );
          })}
        </div>
      ) : null}

      {active && <Scorecard staffCode={active} pillars={pillars} />}
    </div>
  );
}
