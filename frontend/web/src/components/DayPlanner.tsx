import { useMemo, useState } from 'react';
import type { BranchLogField, HourlyMap, HourBlock } from '@/lib/api';

// Metric-family color coding (matches the approved mockup):
//   acquisition = teal · money = amber · service = blue · complaints/quality = pink
// Resolved-type positives read as teal (a "good" outcome). Anything unmapped -> neutral gray.
const FAMILY: Record<string, 'teal' | 'amber' | 'blue' | 'pink' | 'gray'> = {
  accounts_opened: 'teal', accounts_activated: 'teal', dfs_registrations: 'teal',
  cards_issued: 'teal', complaints_resolved: 'teal',
  deposits_mobilised: 'amber', loans_disbursed: 'amber', loans_referred: 'amber',
  bancassurance_sold: 'amber',
  customer_visits: 'blue', digital_txns: 'blue', transactions_count: 'blue',
  nps_collected: 'blue', new_leads: 'blue', cross_sell_success: 'blue',
  complaints_received: 'pink', teller_errors: 'pink',
};

const CHIP: Record<string, string> = {
  teal: 'bg-[#E1F5EE] text-[#0F6E56]',
  amber: 'bg-[#FAEEDA] text-[#854F0B]',
  blue: 'bg-[#E6F1FB] text-[#0C447C]',
  pink: 'bg-[#FBEAF0] text-[#993556]',
  gray: 'bg-gray-100 text-gray-600',
};

function chipClass(key: string): string {
  return CHIP[FAMILY[key] ?? 'gray'];
}

const HOURS = Array.from({ length: 24 }, (_, h) => h);
const hh = (h: number) => `${String(h).padStart(2, '0')}:00`;
const key2 = (h: number) => String(h).padStart(2, '0');

function fmtCount(f: BranchLogField, n: number): string {
  if (f.type === 'amount') {
    if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
    if (n >= 1_000) return `${Math.round(n / 1000)}k`;
    return String(Math.round(n));
  }
  return String(Math.round(n));
}

export interface DayPlannerProps {
  fields: BranchLogField[];            // metric fields (type !== 'text')
  hourly: HourlyMap;                   // current hourly state
  onChange: (next: HourlyMap) => void; // called on any edit (parent autosaves)
  target?: number;                     // daily index target (0 = none)
  dateLabel?: string;                  // e.g. "Thursday 8 August"
  currentHour?: number;                // highlight (defaults to local hour)
  readOnly?: boolean;
}

export default function DayPlanner({
  fields, hourly, onChange, target = 0, dateLabel, currentHour, readOnly = false,
}: DayPlannerProps) {
  const nowHour = currentHour ?? new Date().getHours();
  const [openHour, setOpenHour] = useState<number | null>(nowHour);

  const weightOf = useMemo(() => {
    const m: Record<string, number> = {};
    fields.forEach((f) => { m[f.key] = Number(f.weight) || 0; });
    return m;
  }, [fields]);

  // live day index = sum over all hours of count x weight
  const liveIndex = useMemo(() => {
    let total = 0;
    for (const block of Object.values(hourly)) {
      for (const [k, n] of Object.entries(block.counts || {})) {
        total += (Number(n) || 0) * (weightOf[k] || 0);
      }
    }
    return Math.round(total * 100) / 100;
  }, [hourly, weightOf]);

  const variance = target > 0 ? Math.round((liveIndex - target) * 100) / 100 : 0;
  const pct = target > 0 ? Math.min(100, Math.round((liveIndex / target) * 100)) : 0;

  function blockFor(h: number): HourBlock {
    return hourly[key2(h)] ?? { counts: {}, meetings: [] };
  }

  function setCount(h: number, metric: string, raw: string) {
    if (readOnly) return;
    const n = Number(raw);
    const k = key2(h);
    const cur = hourly[k] ?? { counts: {}, meetings: [] };
    const counts = { ...cur.counts };
    if (!raw || Number.isNaN(n) || n <= 0) delete counts[metric];
    else counts[metric] = n;
    const next: HourlyMap = { ...hourly };
    const block: HourBlock = { ...cur, counts };
    if (Object.keys(counts).length === 0 && (cur.meetings?.length ?? 0) === 0 && !cur.note) {
      delete next[k];
    } else {
      next[k] = block;
    }
    onChange(next);
  }

  function setNote(h: number, note: string) {
    if (readOnly) return;
    const k = key2(h);
    const cur = hourly[k] ?? { counts: {}, meetings: [] };
    const next: HourlyMap = { ...hourly };
    const trimmed = note.slice(0, 500);
    const block: HourBlock = { ...cur, note: trimmed };
    if (!trimmed && Object.keys(cur.counts || {}).length === 0 && (cur.meetings?.length ?? 0) === 0) {
      delete next[k];
    } else {
      if (!trimmed) delete block.note;
      next[k] = block;
    }
    onChange(next);
  }

  return (
    <div>
      {/* header: date + live index + target + variance + progress */}
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <div className="flex items-baseline gap-3">
          <span className="text-lg font-medium text-brand-secondary">{dateLabel ?? 'Today'}</span>
        </div>
        <div className="flex items-center gap-2">
          <span className="text-xs text-gray-400">Day index</span>
          <span className="text-2xl font-semibold tabular-nums text-brand-primary">{liveIndex}</span>
          {target > 0 && (
            <>
              <span className="text-xs text-gray-400">/ {target} target</span>
              <span className={
                'rounded-full px-2 py-0.5 text-[11px] ' +
                (variance >= 0 ? 'bg-[#EAF3DE] text-[#3B6D11]' : 'bg-[#FAECE7] text-[#993C1D]')
              }>
                {variance >= 0 ? '+' : ''}{variance} var
              </span>
            </>
          )}
        </div>
      </div>
      {target > 0 && (
        <div className="my-3 h-1.5 overflow-hidden rounded-full bg-[#EDEDED]">
          <div className="h-full bg-brand-primary" style={{ width: `${pct}%` }} />
        </div>
      )}

      {/* 24-hour vertical timeline */}
      <div className="overflow-hidden rounded-xl border border-gray-200">
        {HOURS.map((h) => {
          const block = blockFor(h);
          const entries = Object.entries(block.counts || {});
          const isNow = h === nowHour;
          const isOpen = openHour === h;
          return (
            <div key={h} className={'border-b border-gray-100 last:border-b-0 ' + (isNow ? 'bg-[#F7FBFD]' : '')}>
              {/* hour row */}
              <button
                type="button"
                onClick={() => setOpenHour(isOpen ? null : h)}
                className="grid w-full grid-cols-[64px_1fr_auto] items-center gap-2 px-0 text-left"
              >
                <span className={'py-2.5 pr-2 text-right text-xs tabular-nums ' + (isNow ? 'font-medium text-brand-primary' : 'text-gray-400')}>
                  {hh(h)}
                </span>
                <span className="flex flex-wrap items-center gap-1.5 py-2">
                  {entries.length === 0 && (block.meetings?.length ?? 0) === 0 && !block.note ? (
                    <span className="text-xs text-gray-300">—</span>
                  ) : (
                    <>
                      {entries.map(([k, n]) => {
                        const f = fields.find((x) => x.key === k);
                        return (
                          <span key={k} className={'rounded-full px-2.5 py-1 text-xs ' + chipClass(k)}>
                            {f?.label ?? k} {f ? fmtCount(f, Number(n)) : Math.round(Number(n))}
                          </span>
                        );
                      })}
                      {(block.meetings ?? []).map((m, i) => (
                        <span key={`m${i}`} className="rounded-full bg-[#EEEDFE] px-2.5 py-1 text-xs text-[#3C3489]">
                          {m.label}{m.span > 1 ? ` · ${m.span}h` : ''}
                        </span>
                      ))}
                      {block.note && (
                        <span className="text-xs italic text-gray-400" title={block.note}>note</span>
                      )}
                    </>
                  )}
                </span>
                <span className="py-2 pr-3 text-xs text-gray-300">
                  {isNow && !isOpen && <span className="mr-2 text-brand-primary">now</span>}
                  {isOpen ? '▾' : '▸'}
                </span>
              </button>

              {/* expanded editor for this hour */}
              {isOpen && !readOnly && (
                <div className="border-t border-gray-100 bg-white px-4 py-3">
                  <div className="grid grid-cols-1 gap-2 sm:grid-cols-2 lg:grid-cols-3">
                    {fields.map((f) => (
                      <label key={f.key} className="text-xs">
                        <span className="mb-0.5 block text-gray-600">
                          {f.label}{f.unit ? ` (${f.unit})` : ''}
                        </span>
                        <input
                          type="number" min={0}
                          className="w-full rounded border border-gray-200 px-2 py-1 text-sm"
                          value={block.counts?.[f.key] ?? ''}
                          onChange={(e) => setCount(h, f.key, e.target.value)}
                        />
                      </label>
                    ))}
                  </div>
                  <label className="mt-3 block text-xs">
                    <span className="mb-0.5 block text-gray-600">Note for this hour (optional)</span>
                    <input
                      type="text" maxLength={500}
                      placeholder="Anything critical worth recording this hour"
                      className="w-full rounded border border-gray-200 px-2 py-1 text-sm"
                      value={block.note ?? ''}
                      onChange={(e) => setNote(h, e.target.value)}
                    />
                  </label>
                </div>
              )}
              {isOpen && readOnly && block.note && (
                <div className="border-t border-gray-100 bg-white px-4 py-2 text-xs text-gray-600">
                  {block.note}
                </div>
              )}
            </div>
          );
        })}
      </div>
      {!hasAnyContent(hourly) && (
        <p className="mt-2 text-center text-[11px] text-gray-400">
          Tap an hour to log what you accomplished. Your day index updates as you go.
        </p>
      )}
    </div>
  );
}

function hasAnyContent(hourly: HourlyMap): boolean {
  return Object.values(hourly).some(
    (b) => Object.keys(b.counts || {}).length > 0 || (b.meetings?.length ?? 0) > 0 || !!b.note,
  );
}
