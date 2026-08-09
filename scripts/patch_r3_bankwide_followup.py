#!/usr/bin/env python
# -*- coding: utf-8 -*-
r"""
R3 - bank-wide follow-up, and the unit drill-down R2 left open.

TWO GAPS CLOSED

1. /non-submitters was confined to BRANCHES. For the MD and Business Manager it
   now covers the whole bank: a Head Office unit that never files is exactly as
   much a follow-up item as a branch that never files. The response carries
   bank_wide so the heading can say which scope is shown.

2. A UNIT row in the roll-up expanded to nothing - R2 shipped with that stated
   rather than hidden. /validation-queue now takes a `unit` parameter and
   returns that unit's DIRECT REPORTS read-only (ruling 2026-08-09: a subtree
   would re-absorb the branches and count them twice). can_act is forced false,
   so the server and the UI agree rather than the UI merely hiding buttons.

THE FOLLOW-UP TABLE uses the SAME rules as the branch-level one: ageing in
BUSINESS days, the streak stopping at the first day filed or excused, and
excused staff excluded entirely. That is deliberate - two lists computed two
ways would eventually disagree, and a manager would have no way to tell which
was right.

Three or more days shows red: past the return window, where logs lock and need
an admin unlock.

Verified: py_compile clean, tsc --noEmit clean, vite build clean.

Usage (from project root, .venv active):
    python scripts\\patch_r3_bankwide_followup.py            # dry run
    python scripts\\patch_r3_bankwide_followup.py --apply    # write + .pre_r3 backups
"""
import os
import shutil
import sys

API = os.path.join("utils", "api_branch_log.py")
APITS = os.path.join("frontend", "web", "src", "lib", "api.ts")
COMP = os.path.join("frontend", "web", "src", "components", "UnitRollup.tsx")
BACKUP_SUFFIX = ".pre_r3"

SIG_OLD = ('def branch_log_validation_queue(date: str = "", branch: str = "",\n'
           '                                user: dict = Depends(get_current_user)):')
SIG_NEW = ('def branch_log_validation_queue(date: str = "", branch: str = "", unit: str = "",\n'
           '                                user: dict = Depends(get_current_user)):')

UNIT_ANCHOR = "    inspect_only = False\n    if branch:"

SCOPE_OLD = '''    try:
        from utils.org_validator import branches_validated_by
        scope = branches_validated_by(my_code)
    except Exception:
        scope = {"branches": []}
    branches = set(scope.get("branches") or [])
    if not branches:
        return {"rows": [], "date": day.isoformat(), "total": 0}'''

FILTER_OLD = '''        branch = str((dd or {}).get("branch") or "").strip()
        if branch not in branches:
            continue'''
FILTER_NEW = '''        branch = str((dd or {}).get("branch") or "").strip()
        if not top and branch not in branches:
            continue'''

RET_OLD = '    return {"rows": rows, "date": iso, "total": len(rows), "working_day": True}'
RET_NEW = ('    return {"rows": rows, "date": iso, "total": len(rows), "working_day": True,\n'
           '            "bank_wide": top}')

TSQ_OLD = """export async function fetchBranchLogValidationQueue(
  date = '', branch = '',
): Promise<ValidationQueue> {
  const q = new URLSearchParams();
  if (date) q.set('date', date);
  if (branch) q.set('branch', branch);      // tier-2 read-only inspection"""
TSQ_NEW = """export async function fetchBranchLogValidationQueue(
  date = '', branch = '', unit = '',
): Promise<ValidationQueue> {
  const q = new URLSearchParams();
  if (date) q.set('date', date);
  if (branch) q.set('branch', branch);      // tier-2 read-only inspection
  if (unit) q.set('unit', unit);            // Head Office unit, read-only"""

TSN_OLD = """export interface NonSubmitters {
  rows: NonSubmitterRow[]; date: string; total: number; working_day?: boolean;
}"""
TSN_NEW = """export interface NonSubmitters {
  rows: NonSubmitterRow[]; date: string; total: number; working_day?: boolean;
  bank_wide?: boolean;
}"""

UNIT_NEW = r'''    if unit:
        # R3: inspect a HEAD OFFICE unit read-only. Members are the unit's DIRECT
        # REPORTS (ruling 2026-08-09) — a subtree would re-absorb the branches.
        try:
            from utils.org_validator import units_validated_by, direct_reports_of_role
            uscope = units_validated_by(my_code)
        except Exception:
            uscope, direct_reports_of_role = {"units": []}, None
        if unit not in (uscope.get("units") or []) and not _is_admin(user):
            raise HTTPException(status_code=403,
                                detail=f"{unit} is not a unit you oversee.")
        inspect_only = True
        mode = "inspect-unit"
        codes = set()
        if direct_reports_of_role:
            try:
                codes = {_canon_q(c) for c in direct_reports_of_role(unit)}
            except Exception:
                codes = set()
        mine = [(d.get("code") or ck, d) for ck, d in dims.items()
                if _canon_q(d.get("code") or ck) in codes]
'''

SCOPE_NEW = r'''    # R3: the MD and Business Manager observe the WHOLE bank, so their follow-up
    # list is not confined to branches — a Head Office unit that never files is
    # exactly as much a follow-up item as a branch that never files.
    top = False
    try:
        from utils.org_validator import branches_validated_by, units_validated_by
        scope = branches_validated_by(my_code)
        top = bool((units_validated_by(my_code) or {}).get("top_of_house"))
    except Exception:
        scope = {"branches": []}
'''

COMPONENT = r'''// R2 — the consolidated roll-up for the MD and the Business Manager.
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
            <p className="mt-0.5 text-xs text-gray-500">
              Branches are countersigned by the Head of Branches and units by their Director.
              You observe, and may return a day for amendment.
            </p>
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
            <p className="mt-2 text-[11px] text-gray-500">
              Three or more days is past the return window — those logs lock and need an
              admin unlock. Staff excused for leave, sickness or training do not appear.
            </p>
          </div>
        )}
      </Card.Body>
    </Card>
  );
}
'''


def main():
    apply = "--apply" in sys.argv
    for p in (API, APITS, COMP):
        if not os.path.isfile(p):
            print("ABORT: %s not found." % p)
            if p == COMP:
                print("       Apply patch_r2_rollup_view.py first.")
            return 1

    api = open(API, encoding="utf-8").read()
    ts = open(APITS, encoding="utf-8").read()

    if "inspect-unit" in api:
        print("ABORT: /validation-queue already supports unit - R3 looks applied.")
        return 1
    if "/non-submitters" not in api:
        print("ABORT: apply patch_e3_followup.py first.")
        return 1
    for label, hay, mark in (("queue signature", api, SIG_OLD),
                             ("unit anchor", api, UNIT_ANCHOR),
                             ("follow-up scope", api, SCOPE_OLD),
                             ("follow-up filter", api, FILTER_OLD),
                             ("follow-up return", api, RET_OLD),
                             ("api.ts queue fn", ts, TSQ_OLD),
                             ("api.ts NonSubmitters", ts, TSN_OLD)):
        if hay.count(mark) != 1:
            print("ABORT: %s anchor matched %d times." % (label, hay.count(mark)))
            return 1

    api = api.replace(SIG_OLD, SIG_NEW, 1)
    api = api.replace(UNIT_ANCHOR, "    inspect_only = False\n" + UNIT_NEW + "    elif branch:", 1)
    print("  ok  /validation-queue - unit inspection (direct reports, read-only)")

    api = api.replace(SCOPE_OLD, SCOPE_NEW + '    branches = set(scope.get("branches") or [])\n'
                      '    if not branches and not top:\n'
                      '        return {"rows": [], "date": day.isoformat(), "total": 0}', 1)
    api = api.replace(FILTER_OLD, FILTER_NEW, 1)
    api = api.replace(RET_OLD, RET_NEW, 1)
    print("  ok  /non-submitters - bank-wide for the observation tier")

    ts = ts.replace(TSQ_OLD, TSQ_NEW, 1).replace(TSN_OLD, TSN_NEW, 1)
    print("  ok  api.ts - unit param + bank_wide flag")

    if api.count("inspect-unit") != 1 or api.count('"bank_wide": top') != 1:
        print("ABORT: post-check - backend edits not applied exactly once.")
        return 1
    if api.count('@router.get("/validation-queue")') != 1:
        print("ABORT: post-check - queue route count changed.")
        return 1
    for token in ("Outstanding daily logs", "bank_wide", "inspect"):
        if token not in COMPONENT:
            print("ABORT: embedded component missing %r." % token)
            return 1
    for o, c in (("{", "}"), ("(", ")")):
        if COMPONENT.count(o) != COMPONENT.count(c):
            print("ABORT: embedded component unbalanced %s%s." % (o, c))
            return 1
    print("  ok  post-checks clean")

    if not apply:
        print("\nDRY RUN - nothing written. Re-run with --apply.")
        return 0

    for path, content in ((API, api), (APITS, ts), (COMP, COMPONENT)):
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
