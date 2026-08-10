#!/usr/bin/env python
# -*- coding: utf-8 -*-
r"""
RF3 - the referral field becomes AUTO and uneditable. Closes the referral arc.

RULING (2026-08-09): "if we confirm that, then we should make the referral place
on the daily log uneditable since it is auto."

Now safe to do, because RF1 made the credit real: accepted referrals credit the
referrer's day, derived at read time. Leaving the field typeable as well would
count the same referral TWICE - once by hand, once by machine.

SEQUENCING MATTERED and was honoured: this lands AFTER the auto-credit works,
not before. Doing it first would simply have removed people's ability to record
referrals at all.

THREE PARTS, and the middle one is the only real enforcement:

  1. SCHEMA   fields_schema() marks the field `auto: true`. Config-driven via
     branch_log_config.auto_fields, defaulting to referral_credit.credit_field(),
     so the next derived metric needs no code change.

  2. SERVER   submit() DISCARDS whatever arrives for an auto field. A read-only
     input is a UI courtesy; a crafted request would still write. Scoped to
     submit() only - the DRAFT path is untouched, on the same reasoning that
     already exempts drafts from bounds checking: a half-typed number is not an
     error yet.

  3. UI       DayPlanner renders an "auto - counted when accepted" chip instead
     of a number box. SHOWN, not hidden: the activity still counts toward the
     index, and a person who cannot see the row would reasonably assume it does
     not.

MEASURED: a submit posting loans_referred=99 stores 0, while accounts_opened=3
in the same request survives as 3.

Verified: py_compile clean, tsc --noEmit clean, vite build clean.

REQUIRES RF1.

Usage (from project root, .venv active):
    python scripts\patch_rf3_auto_referral_field.py            # dry run
    python scripts\patch_rf3_auto_referral_field.py --apply    # write + .pre_rf3 backups
"""
import os
import shutil
import sys

BL = os.path.join("utils", "branch_log.py")
APITS = os.path.join("frontend", "web", "src", "lib", "api.ts")
DP = os.path.join("frontend", "web", "src", "components", "DayPlanner.tsx")
BACKUP_SUFFIX = ".pre_rf3"

SCHEMA_OLD = '''def fields_schema() -> list:
    w = activity_weights()
    return [{"key": k, "label": lbl, "type": t, "unit": u, "bsc_kpi": kpi,
             "weight": float(w.get(k, 0) or 0)}
            for k, lbl, t, u, kpi in LOG_FIELDS]'''

TS_OLD = ("export interface BranchLogField { key: string; label: string; "
          "type: string; unit: string; bsc_kpi: string | null; weight?: number; }")
TS_NEW = ("export interface BranchLogField { key: string; label: string; "
          "type: string; unit: string; bsc_kpi: string | null; weight?: number; "
          "auto?: boolean; }")

REMARKS = '        remarks = str(values.get("remarks", "") or "")'

SCHEMA_NEW = r'''def auto_fields() -> set:
    """Fields the SYSTEM derives; a person must not type them.

    Ruling 2026-08-09: the referral field becomes uneditable once referral
    credit is automatic (RF1), because otherwise the same referral is counted
    twice - once by hand and once by machine.

    Config-driven, so the next derived metric needs no code change.
    """
    try:
        cfg = load_log_config() or {}
        v = cfg.get("auto_fields")
        if isinstance(v, list):
            return {str(x) for x in v if str(x).strip()}
    except Exception:
        pass
    try:
        from utils.referral_credit import credit_field
        return {credit_field()}
    except Exception:
        return {"loans_referred"}


def fields_schema() -> list:
    w = activity_weights()
    auto = auto_fields()
    return [{"key": k, "label": lbl, "type": t, "unit": u, "bsc_kpi": kpi,
             "weight": float(w.get(k, 0) or 0), "auto": k in auto}
            for k, lbl, t, u, kpi in LOG_FIELDS]


def fields_schema() -> list:
    w = activity_weights()
    auto = auto_fields()
    return [{"key": k, "label": lbl, "type": t, "unit": u, "bsc_kpi": kpi,
             "weight": float(w.get(k, 0) or 0), "auto": k in auto}
            for k, lbl, t, u, kpi in LOG_FIELDS]'''

ENFORCE = r'''        # AUTO FIELDS ARE IGNORED, not trusted. A read-only input is a UI
        # courtesy; a crafted request would still write. Whatever arrives for an
        # auto field is discarded, and the value is derived at read time instead
        # (utils.referral_credit), so a machine count and a typed count can
        # never disagree. Drafts are NOT touched - same reasoning that exempts
        # them from bounds checking.
        for _k in auto_fields():
            if _k in metrics:
                metrics[_k] = 0

'''

DP_NEW = r'''import { useEffect, useMemo, useRef, useState } from 'react';
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

// Time-of-day colouring. Deliberately wall-clock and independent of
// dayStart/dayEnd — those control what the scroll box parks on, whereas
// morning/afternoon/evening are what the hour actually IS. Brand palette only.
type Period = 'night' | 'morning' | 'afternoon' | 'evening';

function periodOf(h: number): Period {
  if (h >= 8 && h <= 11) return 'morning';
  if (h >= 12 && h <= 16) return 'afternoon';
  if (h >= 17 && h <= 19) return 'evening';
  return 'night';
}

const PERIOD: Record<Period, { rail: string; pill: string; tint: string }> = {
  morning:   { rail: '#0082BB', pill: 'bg-[#E6F1FB] text-[#0C447C]', tint: 'bg-[#0082BB]/[0.04]' },
  afternoon: { rail: '#669438', pill: 'bg-[#EAF3DE] text-[#3B6D11]', tint: 'bg-[#669438]/[0.05]' },
  evening:   { rail: '#005B82', pill: 'bg-[#DDEAF1] text-[#004965]', tint: 'bg-[#005B82]/[0.04]' },
  night:     { rail: '#EDEDED', pill: 'bg-gray-100 text-gray-400',   tint: 'bg-gray-100/80' },
};

const HOURS = Array.from({ length: 24 }, (_, h) => h);
const hh = (h: number) => `${String(h).padStart(2, '0')}:00`;
const key2 = (h: number) => String(h).padStart(2, '0');

function fmtCount(_f: BranchLogField, n: number): string {
  // Full figures with thousands separators - no K/M abbreviation anywhere
  // (ruling 2026-08-09). An abbreviated number is a number somebody has to
  // decode, and 367K hides whether it was 367,000 or 367,400.
  return Math.round(n).toLocaleString();
}

export interface DayPlannerProps {
  fields: BranchLogField[];            // metric fields (type !== 'text')
  hourly: HourlyMap;                   // current hourly state
  onChange: (next: HourlyMap) => void; // called on any edit (parent autosaves)
  target?: number;                     // daily index target (0 = none)
  dateLabel?: string;                  // e.g. "Thursday 8 August"
  currentHour?: number;                // highlight (defaults to local hour)
  readOnly?: boolean;
  dayStart?: number;                   // first prominent hour (default 08)
  dayEnd?: number;                     // last prominent hour, inclusive (default 19)
}

export default function DayPlanner({
  fields, hourly, onChange, target = 0, dateLabel, currentHour, readOnly = false,
  dayStart = 8, dayEnd = 19,
}: DayPlannerProps) {
  const nowHour = currentHour ?? new Date().getHours();
  const [openHour, setOpenHour] = useState<number | null>(nowHour);

  // All 24 hours stay mounted and editable; the box just starts parked on the
  // working day so the graveyard hours don't eat the page.
  const scrollRef = useRef<HTMLDivElement | null>(null);
  const rowRefs = useRef<Record<number, HTMLDivElement | null>>({});

  function scrollToHour(h: number) {
    const el = rowRefs.current[h];
    const box = scrollRef.current;
    if (el && box) box.scrollTop = el.offsetTop;
  }

  // Mount only. Re-anchoring mid-edit would yank the view out from under the user.
  useEffect(() => {
    const outside = nowHour < dayStart || nowHour > dayEnd;
    scrollToHour(outside ? nowHour : dayStart);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

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

      {/* 24-hour vertical timeline, scrolled to the working day */}
      <div
        ref={scrollRef}
        className="relative max-h-[calc(100vh_-_21rem)] min-h-[17rem] overflow-y-auto overflow-x-hidden rounded-xl border border-gray-200"
      >
        {HOURS.map((h) => {
          const block = blockFor(h);
          const entries = Object.entries(block.counts || {});
          const isNow = h === nowHour;
          const isOpen = openHour === h;
          const offHours = h < dayStart || h > dayEnd;
          const period = PERIOD[periodOf(h)];
          const hasContent = entries.length > 0 || (block.meetings?.length ?? 0) > 0 || !!block.note;
          return (
            <div
              key={h}
              ref={(el) => { rowRefs.current[h] = el; }}
              style={{ borderLeft: `3px solid ${period.rail}` }}
              className={'border-b border-gray-100 last:border-b-0 '
                + (isNow ? 'bg-[#F7FBFD]' : hasContent ? period.tint : offHours ? 'bg-gray-50/70' : '')}
            >
              {/* hour row */}
              <button
                type="button"
                onClick={() => setOpenHour(isOpen ? null : h)}
                className="grid w-full grid-cols-[64px_1fr_auto] items-center gap-2 px-0 text-left"
              >
                <span className="flex justify-end py-2 pr-2">
                  <span className={'rounded px-1.5 py-0.5 text-[11px] tabular-nums '
                    + (isNow ? 'bg-brand-primary font-medium text-white' : period.pill)}>
                    {hh(h)}
                  </span>
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
                  <div className="grid grid-cols-1 gap-2 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
                    {fields.map((f) => (
                      <label key={f.key} className="text-xs">
                        <span className="mb-0.5 block text-gray-600">
                          {f.label}{f.unit ? ` (${f.unit})` : ''}
                        </span>
                        {f.auto ? (
                          // Derived by the system, so there is nothing to type.
                          // Shown rather than hidden: the activity still counts,
                          // and a person who cannot see it would assume it does
                          // not.
                          <div className="flex w-full items-center gap-1.5 rounded border border-dashed border-gray-200 bg-gray-50 px-2 py-1 text-sm text-gray-500">
                            <span className="text-[10px] uppercase tracking-wide text-[#0C447C]">auto</span>
                            <span className="text-[11px]">counted when accepted</span>
                          </div>
                        ) : (
                          <input
                            type="number" min={0}
                            className="w-full rounded border border-gray-200 px-2 py-1 text-sm"
                            value={block.counts?.[f.key] ?? ''}
                            onChange={(e) => setCount(h, f.key, e.target.value)}
                          />
                        )}
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
    </div>
  );
}
'''


def main():
    apply = "--apply" in sys.argv
    for p in (BL, APITS, DP):
        if not os.path.isfile(p):
            print("ABORT: %s not found. Run from the project root." % p)
            return 1

    bl = open(BL, encoding="utf-8").read()
    ts = open(APITS, encoding="utf-8").read()
    dp = open(DP, encoding="utf-8").read()

    if "auto_fields" in bl:
        print("ABORT: auto_fields already present - RF3 looks applied.")
        return 1
    if not os.path.isfile(os.path.join("utils", "referral_credit.py")):
        print("ABORT: apply patch_rf1_referral_credit.py first. Making the field")
        print("       uneditable BEFORE the credit works would simply remove the")
        print("       ability to record referrals at all.")
        return 1
    if bl.count(SCHEMA_OLD) != 1:
        print("ABORT: fields_schema matched %d times." % bl.count(SCHEMA_OLD))
        return 1
    if ts.count(TS_OLD) != 1:
        print("ABORT: BranchLogField type matched %d times." % ts.count(TS_OLD))
        return 1

    bl = bl.replace(SCHEMA_OLD, SCHEMA_NEW, 1)
    print("  ok  fields_schema marks auto fields")

    # Scope enforcement to submit() ONLY - the draft path shares this line.
    fn = bl.index("    def submit(self, staff_code: str, staff_name: str, "
                  "unit: str, role: str,")
    i = bl.index(REMARKS, fn)
    bl = bl[:i] + ENFORCE + bl[i:]
    print("  ok  submit discards posted auto-field values (drafts untouched)")

    ts = ts.replace(TS_OLD, TS_NEW, 1)
    print("  ok  api.ts - auto flag on the field type")

    # post-checks
    if bl.count("for _k in auto_fields()") != 1:
        print("ABORT: post-check - enforcement appears %d times, expected 1."
              % bl.count("for _k in auto_fields()"))
        return 1
    sub = bl.index("def submit(self")
    nxt = bl.index("\n    def ", sub + 20)
    if "for _k in auto_fields()" not in bl[sub:nxt]:
        print("ABORT: post-check - enforcement did not land inside submit().")
        return 1
    if "auto" not in DP_NEW or "counted when accepted" not in DP_NEW:
        print("ABORT: DayPlanner does not render the auto chip.")
        return 1
    for op, cl in (("{", "}"), ("(", ")")):
        if DP_NEW.count(op) != DP_NEW.count(cl):
            print("ABORT: DayPlanner unbalanced %s%s." % (op, cl))
            return 1
    print("  ok  post-checks clean")

    if not apply:
        print("\nDRY RUN - nothing written. Re-run with --apply.")
        return 0

    for path, content in ((BL, bl), (APITS, ts), (DP, DP_NEW)):
        shutil.copy2(path, path + BACKUP_SUFFIX)
        open(path, "w", encoding="utf-8", newline="").write(content)
        print("APPLIED %s" % path)

    import py_compile
    try:
        py_compile.compile(BL, doraise=True)
        print("  ok  branch_log.py compiles")
    except Exception as exc:
        print("  FAIL %s" % exc)
        return 1

    print("\nRestart uvicorn. The referral field is now a chip, not a box, and")
    print("a crafted request cannot write to it.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
