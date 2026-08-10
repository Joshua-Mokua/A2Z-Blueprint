#!/usr/bin/env python
# -*- coding: utf-8 -*-
r"""
AS4 - the admin panel for per-unit activities. Closes the AS arc.

RULING (2026-08-10): "the branch default but with admin still being able to
amend."

AS3 made the endpoint accept unit sets and weights. AS4 gives the admin a
surface for it, so amending no longer means editing JSON on a server.

Daily Log Admin gains "ACTIVITIES BY UNIT":

    a unit picker listing all 16 MD-reporting units, each showing how many
    activities it has configured

    a checkbox per activity, with the BANK WEIGHT beside a per-unit override
    box. Blank inherits - the placeholder literally reads "inherit" - so an
    admin only types the weights that actually differ for that unit.

    the referral carries an "always included" chip, because it travels to every
    unit whatever is ticked and an admin unticking it would otherwise expect it
    to disappear.

CLEARING ALL ACTIVITIES RETURNS THE UNIT TO THE BRANCH SET, and the panel says
so on screen and again in the save confirmation. That is the safe direction: an
empty set would leave a unit with no activities and its people reading zero,
which looks identical to having done no work.

The unit payload is sent ON ITS OWN, so saving a unit never rewrites the
bank-wide weights as a side effect of a shared form.

Uses the page's existing setMsg for feedback rather than introducing a toast -
two conventions on one screen is how a codebase starts disagreeing with itself.

Verified: tsc --noEmit clean, vite build clean.

REQUIRES AS3.

Usage (from project root, .venv active):
    python scripts\patch_as4_unit_admin_ui.py            # dry run
    python scripts\patch_as4_unit_admin_ui.py --apply
"""
import os
import shutil
import sys

PAGE = os.path.join("frontend", "web", "src", "pages", "DailyLogAdmin.tsx")
APITS = os.path.join("frontend", "web", "src", "lib", "api.ts")
BACKUP_SUFFIX = ".pre_as4"

TS_OLD = ("export interface BranchLogConfig { activity_weights: "
          "Record<string, number>; daily_index_target: number; "
          "fields: BranchLogField[]; }")

SAVE_OLD = '''export async function saveBranchLogConfig(activity_weights: Record<string, number>, daily_index_target: number): Promise<{ status: string }> {
  return postJson<{ status: string }, { activity_weights: Record<string, number>; daily_index_target: number }>(
    '/branch-log/config', { activity_weights, daily_index_target });
}'''

SAVE_NEW = '''export async function saveBranchLogConfig(activity_weights: Record<string, number>, daily_index_target: number): Promise<{ status: string }> {
  return postJson<{ status: string }, { activity_weights: Record<string, number>; daily_index_target: number }>(
    '/branch-log/config', { activity_weights, daily_index_target });
}
// Per-unit sets and weights (AS1-AS3). Sent on their own, so saving one unit
// never rewrites the bank-wide weights as a side effect.
export interface UnitConfigPayload {
  activity_sets?: Record<string, string[]>;
  unit_activity_weights?: Record<string, Record<string, number>>;
}
export async function saveBranchLogUnitConfig(
  body: UnitConfigPayload,
): Promise<{ status: string }> {
  return postJson<{ status: string }, UnitConfigPayload>('/branch-log/config', body);
}'''

TS_NEW = r'''export interface BranchLogConfig {
  activity_weights: Record<string, number>;
  daily_index_target: number;
  fields: BranchLogField[];
  activity_sets?: Record<string, string[]>;
  unit_activity_weights?: Record<string, Record<string, number>>;
  units?: string[];
}'''

PAGE_NEW = r'''// ──────────────────────────────────────────────────────────────────────────
// Admin > Daily Log — productivity index configuration, consolidated into the
// Administration area (previously only reachable as an "Index Setup" tab on the
// Daily Log page itself).
//
// Three sections, all against existing endpoints:
//   1. Daily index target        POST /branch-log/config
//   2. Points per activity       POST /branch-log/config  (activity_weights)
//   3. Extra activities          POST /branch-log/activities  (role-tagged)
//
// AMOUNT-FIELD SCALING: compute_index is sum(count x weight), so an amount field
// (deposits in KES) with weight 1 would score 500,000 for a KES 500k deposit and
// drown out every count-based activity. For amount fields this panel takes
// "points per KES 100,000" and stores weight = entered / 100000.
// ──────────────────────────────────────────────────────────────────────────
import { useCallback, useEffect, useState } from 'react';
import { Card } from '@/components/Card';
import { AdminTabs } from '@/components/AdminTabs';
import {
  fetchBranchLogFields,
  fetchBranchLogConfig,
  saveBranchLogConfig,
  saveBranchLogUnitConfig,
  fetchBranchLogActivities,
  saveBranchLogActivities,
  type BranchLogField,
  type ExtraActivity,
} from '@/lib/api';

const AMOUNT_SCALE = 100000; // amount weights are entered per KES 100,000

const inputCls =
  'w-full rounded-md border border-gray-300 px-2 py-1.5 text-sm focus:outline-none ' +
  'focus:border-brand-primary focus:ring-2 focus:ring-brand-primary/20';

const btn =
  'rounded-md px-3 py-1.5 text-sm font-medium text-white bg-[#0082BB] ' +
  'hover:opacity-90 disabled:opacity-40';
const btnGhost =
  'rounded-md px-3 py-1.5 text-sm font-medium text-gray-600 border border-gray-300 hover:bg-gray-50';

function isAmount(f: BranchLogField): boolean {
  return String(f.type || '').toLowerCase() === 'amount';
}

export function DailyLogAdmin() {
  const [fields, setFields] = useState<BranchLogField[]>([]);
  const [weights, setWeights] = useState<Record<string, string>>({});
  const [target, setTarget] = useState('');
  // Per-unit sets and weights (AS1-AS3). A unit with NO set keeps the branch
  // base, so "not configured" is the normal state, not an error.
  const [units, setUnits] = useState<string[]>([]);
  const [sets, setSets] = useState<Record<string, string[]>>({});
  const [unitW, setUnitW] = useState<Record<string, Record<string, number>>>({});
  const [unit, setUnit] = useState('');
  const [savingUnit, setSavingUnit] = useState(false);

  const unitKeys = unit ? (sets[unit] ?? []) : [];
  const unitConfigured = unit ? Boolean(sets[unit]?.length) : false;

  function toggleKey(k: string) {
    if (!unit) return;
    const cur = sets[unit] ?? [];
    const next = cur.includes(k) ? cur.filter((x) => x !== k) : [...cur, k];
    setSets({ ...sets, [unit]: next });
  }

  function setUnitWeight(k: string, v: string) {
    if (!unit) return;
    const cur = { ...(unitW[unit] ?? {}) };
    if (v.trim() === '') delete cur[k];
    else cur[k] = Number(v) || 0;
    setUnitW({ ...unitW, [unit]: cur });
  }

  async function saveUnit() {
    if (!unit) return;
    setSavingUnit(true);
    try {
      // Sent as its own payload. An empty set REMOVES the unit server-side,
      // returning its people to the branch base rather than leaving them with
      // no activities at all.
      await saveBranchLogUnitConfig({
        activity_sets: { [unit]: sets[unit] ?? [] },
        unit_activity_weights: { [unit]: unitW[unit] ?? {} },
      });
      // This page reports through setMsg, not a toast - matching the two save
      // handlers already here rather than introducing a second convention.
      setMsg({
        tone: 'ok',
        text: (sets[unit] ?? []).length
          ? `${unit} saved.`
          : `${unit} returned to the branch activity set.`,
      });
    } catch (e) {
      setMsg({ tone: 'err', text: e instanceof Error ? e.message : 'Could not save.' });
    } finally {
      setSavingUnit(false);
    }
  }
  const [extras, setExtras] = useState<ExtraActivity[]>([]);
  const [newAct, setNewAct] = useState({ key: '', label: '', unit: '', weight: '', roles: '' });
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<{ tone: 'ok' | 'err'; text: string } | null>(null);

  const load = useCallback(async () => {
    try {
      const [f, cfg, acts] = await Promise.all([
        fetchBranchLogFields(),
        fetchBranchLogConfig(),
        fetchBranchLogActivities(),
      ]);
      setFields(f.fields ?? []);
      const w: Record<string, string> = {};
      for (const fl of f.fields ?? []) {
        const raw = Number(cfg.activity_weights?.[fl.key] ?? 0);
        w[fl.key] = String(isAmount(fl) ? raw * AMOUNT_SCALE : raw);
      }
      setWeights(w);
      setTarget(String(cfg.daily_index_target ?? 0));
      setUnits(cfg.units ?? []);
      setSets(cfg.activity_sets ?? {});
      setUnitW(cfg.unit_activity_weights ?? {});
      setExtras(acts.extra ?? []);
    } catch (e) {
      setMsg({ tone: 'err', text: e instanceof Error ? e.message : 'Could not load config' });
    }
  }, []);

  useEffect(() => { void load(); }, [load]);

  const saveWeights = async () => {
    setBusy(true); setMsg(null);
    try {
      const out: Record<string, number> = {};
      for (const f of fields) {
        const entered = Number(weights[f.key] ?? 0) || 0;
        out[f.key] = isAmount(f) ? entered / AMOUNT_SCALE : entered;
      }
      await saveBranchLogConfig(out, Number(target) || 0);
      setMsg({ tone: 'ok', text: 'Points and target saved.' });
      await load();
    } catch (e) {
      setMsg({ tone: 'err', text: e instanceof Error ? e.message : 'Save failed' });
    } finally { setBusy(false); }
  };

  const addExtra = () => {
    const k = newAct.key.trim();
    if (!k || !newAct.label.trim()) {
      setMsg({ tone: 'err', text: 'Key and label are required.' }); return;
    }
    setExtras((p) => [
      ...p.filter((x) => x.key !== k),
      {
        key: k,
        label: newAct.label.trim(),
        type: 'int',
        unit: newAct.unit.trim(),
        weight: Number(newAct.weight) || 0,
        roles: newAct.roles.split(',').map((r) => r.trim()).filter(Boolean),
      },
    ]);
    setNewAct({ key: '', label: '', unit: '', weight: '', roles: '' });
  };

  const saveExtras = async () => {
    setBusy(true); setMsg(null);
    try {
      await saveBranchLogActivities(extras);
      setMsg({ tone: 'ok', text: 'Extra activities saved.' });
      await load();
    } catch (e) {
      setMsg({ tone: 'err', text: e instanceof Error ? e.message : 'Save failed' });
    } finally { setBusy(false); }
  };

  return (
    <>
      <AdminTabs subtitle="Daily Log productivity index — activity points, target, and role-specific activities." />
      <div className="mx-auto max-w-7xl space-y-4 px-6 py-5 2xl:max-w-[1680px]">
        {msg && (
          <div className={`rounded-md px-3 py-2 text-sm ${
            msg.tone === 'ok' ? 'bg-green-50 text-green-800' : 'bg-red-50 text-red-700'}`}>
            {msg.text}
          </div>
        )}

        <Card>
          <Card.Header>
            <h2 className="text-base font-semibold text-gray-900">Activity points &amp; daily target</h2>
          </Card.Header>
          <Card.Body>
            <label className="mb-4 block text-sm">
              <span className="mb-1 block text-gray-700">Daily index target</span>
              <input type="number" min={0} className={`${inputCls} w-40`}
                value={target} onChange={(e) => setTarget(e.target.value)} />
              <span className="mt-1 block text-xs text-gray-400">
                The index a productive day should reach. Ranking shows each person against this.
              </span>
            </label>

            <p className="mb-1 text-sm font-medium text-gray-700">Points per activity</p>
            <p className="mb-3 text-xs text-gray-400">
              Count activities score points x quantity. Amount activities (KES) are entered as
              points per KES {AMOUNT_SCALE.toLocaleString()} so they stay comparable with counts.
            </p>
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
              {fields.map((f) => (
                <label key={f.key} className="flex items-center justify-between gap-3 text-sm">
                  <span className="text-gray-700">
                    {f.label}
                    <span className="ml-1 text-xs text-gray-400">
                      {isAmount(f) ? `(per KES ${AMOUNT_SCALE.toLocaleString()})` : `(${f.unit || 'count'})`}
                    </span>
                  </span>
                  <input type="number" step="any" className={`${inputCls} w-24`}
                    value={weights[f.key] ?? ''}
                    onChange={(e) => setWeights((p) => ({ ...p, [f.key]: e.target.value }))} />
                </label>
              ))}
            </div>
            <div className="mt-4 flex justify-end">
              <button type="button" className={btn} disabled={busy} onClick={() => void saveWeights()}>
                {busy ? 'Saving…' : 'Save points & target'}
              </button>
            </div>
          </Card.Body>
        </Card>

        <Card>
          <Card.Header>
            <h2 className="text-base font-semibold text-gray-900">Role-specific activities</h2>
          </Card.Header>
          <Card.Body>
            <p className="mb-3 text-xs text-gray-400">
              Activities beyond the common base. Leave roles blank to show for everyone; list roles
              (comma-separated) to show only for those roles — anything logged outside a person's
              own role counts as over-and-above.
            </p>

            {extras.length > 0 && (
              <div className="mb-3 space-y-1">
                {extras.map((a, i) => (
                  <div key={a.key}
                    className="flex items-center justify-between rounded border border-gray-100 px-3 py-2">
                    <div className="min-w-0">
                      <span className="font-medium text-gray-800">{a.label}</span>
                      <span className="ml-2 text-xs text-gray-500">
                        {a.unit || 'count'} · {a.weight} pts
                        {a.roles?.length ? ` · ${a.roles.join(', ')}` : ' · all roles'}
                      </span>
                    </div>
                    <button type="button" className="text-xs text-gray-400 hover:text-red-600"
                      onClick={() => setExtras((p) => p.filter((_, j) => j !== i))}>
                      Remove
                    </button>
                  </div>
                ))}
              </div>
            )}

            <div className="grid grid-cols-1 gap-2 sm:grid-cols-5">
              <input className={inputCls} placeholder="key (e.g. credit_files)"
                value={newAct.key} onChange={(e) => setNewAct((p) => ({ ...p, key: e.target.value }))} />
              <input className={inputCls} placeholder="Label"
                value={newAct.label} onChange={(e) => setNewAct((p) => ({ ...p, label: e.target.value }))} />
              <input className={inputCls} placeholder="unit"
                value={newAct.unit} onChange={(e) => setNewAct((p) => ({ ...p, unit: e.target.value }))} />
              <input className={inputCls} type="number" step="any" placeholder="points"
                value={newAct.weight} onChange={(e) => setNewAct((p) => ({ ...p, weight: e.target.value }))} />
              <input className={inputCls} placeholder="roles (comma-sep)"
                value={newAct.roles} onChange={(e) => setNewAct((p) => ({ ...p, roles: e.target.value }))} />
            </div>

            <div className="mt-3 flex justify-end gap-2">
              <button type="button" className={btnGhost} onClick={addExtra}>Add activity</button>
              <button type="button" className={btn} disabled={busy} onClick={() => void saveExtras()}>
                {busy ? 'Saving…' : 'Save activities'}
              </button>
            </div>
          </Card.Body>
        </Card>

        <Card className="mt-4">
          <Card.Header>
            <div className="flex flex-wrap items-center justify-between gap-3">
              <h2 className="text-base font-semibold text-gray-900">Activities by unit</h2>
              <select value={unit} onChange={(e) => setUnit(e.target.value)}
                      className="rounded border border-gray-200 px-2 py-1 text-xs">
                <option value="">Select a unit…</option>
                {units.map((u) => (
                  <option key={u} value={u}>
                    {u}{sets[u]?.length ? ` (${sets[u].length})` : ''}
                  </option>
                ))}
              </select>
            </div>
          </Card.Header>
          <Card.Body>
            {!unit && (
              <p className="py-6 text-center text-sm text-gray-400">
                Pick a unit to give it its own activities.
              </p>
            )}

            {unit && (
              <>
                <p className="mb-3 text-xs text-gray-500">
                  {unitConfigured
                    ? `${unitKeys.length} selected. Clear them all to return this unit to the branch set.`
                    : 'Not configured — this unit currently uses the branch activity set.'}
                </p>

                <div className="overflow-auto rounded-lg border border-gray-200">
                  <table className="w-full border-separate" style={{ borderSpacing: 0 }}>
                    <thead>
                      <tr>
                        <th className="w-10 bg-gray-100 px-2 py-2"></th>
                        <th className="bg-gray-100 px-2 py-2 text-left text-[11px] font-semibold uppercase text-gray-600">Activity</th>
                        <th className="bg-gray-100 px-2 py-2 text-right text-[11px] font-semibold uppercase text-gray-600">Bank weight</th>
                        <th className="bg-gray-100 px-2 py-2 text-right text-[11px] font-semibold uppercase text-gray-600">This unit</th>
                      </tr>
                    </thead>
                    <tbody>
                      {fields.filter((f) => f.key !== 'remarks').map((f, i) => {
                        const on = unitKeys.includes(f.key);
                        const bg = i % 2 === 1 ? 'bg-gray-50/40' : 'bg-white';
                        const ov = unitW[unit]?.[f.key];
                        return (
                          <tr key={f.key}>
                            <td className={`${bg} px-2 py-1.5`}>
                              <input type="checkbox" checked={on}
                                     onChange={() => toggleKey(f.key)} />
                            </td>
                            <td className={`${bg} px-2 py-1.5 text-xs ${on ? 'text-gray-900' : 'text-gray-400'}`}>
                              {f.label}
                              {f.key === 'loans_referred' && (
                                <span className="ml-2 rounded bg-[#E6F1FB] px-1.5 py-0.5 text-[10px] text-[#0C447C]">
                                  always included
                                </span>
                              )}
                            </td>
                            <td className={`${bg} px-2 py-1.5 text-right text-xs tabular-nums text-gray-500`}>
                              {weights[f.key] ?? 0}
                            </td>
                            <td className={`${bg} px-2 py-1.5 text-right`}>
                              <input
                                type="number" step="0.1"
                                value={ov === undefined ? '' : String(ov)}
                                placeholder="inherit"
                                onChange={(e) => setUnitWeight(f.key, e.target.value)}
                                className="w-20 rounded border border-gray-200 px-2 py-1 text-right text-xs"
                              />
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>

                <div className="mt-3 flex items-center justify-between gap-2">
                  <span className="text-[11px] text-gray-500">
                    Blank weight inherits the bank figure. Target stays {target} for everyone.
                  </span>
                  <button type="button" className={btn} disabled={savingUnit}
                          onClick={() => void saveUnit()}>
                    {savingUnit ? 'Saving…' : `Save ${unit.slice(0, 28)}`}
                  </button>
                </div>
              </>
            )}
          </Card.Body>
        </Card>
      </div>
    </>
  );
}

export default DailyLogAdmin;
'''


def main():
    apply = "--apply" in sys.argv
    for p in (PAGE, APITS):
        if not os.path.isfile(p):
            print("ABORT: %s not found. Run from the project root." % p)
            return 1

    ts = open(APITS, encoding="utf-8").read()
    cur = open(PAGE, encoding="utf-8").read()

    if "saveBranchLogUnitConfig" in ts:
        print("ABORT: api.ts already has the unit config client - AS4 looks applied.")
        return 1
    if '"activity_sets"' not in open(os.path.join("utils", "api_branch_log.py"),
                                     encoding="utf-8").read():
        print("ABORT: apply patch_as3_admin_unit_config.py first - the endpoint")
        print("       would reject everything this panel sends.")
        return 1
    if ts.count(TS_OLD) != 1:
        print("ABORT: BranchLogConfig matched %d times." % ts.count(TS_OLD))
        return 1
    if ts.count(SAVE_OLD) != 1:
        print("ABORT: saveBranchLogConfig matched %d times." % ts.count(SAVE_OLD))
        return 1

    ts = ts.replace(TS_OLD, TS_NEW, 1).replace(SAVE_OLD, SAVE_NEW, 1)
    print("  ok  api.ts - config type extended, unit client added")

    for token in ("Activities by unit", "always included", "inherit",
                  "returned to the branch activity set"):
        if token not in PAGE_NEW:
            print("ABORT: embedded page missing %r." % token)
            return 1
    # The page has its own message mechanism; a toast here would be a second
    # convention on one screen.
    if "toast(" in PAGE_NEW:
        print("ABORT: the page uses a toast - it should use setMsg like its")
        print("       existing save handlers.")
        return 1
    for op, cl in (("{", "}"), ("(", ")")):
        if PAGE_NEW.count(op) != PAGE_NEW.count(cl):
            print("ABORT: page unbalanced %s%s." % (op, cl))
            return 1
    if "fetchBranchLogHistoryGrid" not in ts:
        print("ABORT: post-check - api.ts lost an existing client.")
        return 1
    print("  ok  post-checks clean")

    if not apply:
        print("\nDRY RUN - nothing written. Re-run with --apply.")
        return 0

    for path, content in ((APITS, ts), (PAGE, PAGE_NEW)):
        shutil.copy2(path, path + BACKUP_SUFFIX)
        open(path, "w", encoding="utf-8", newline="").write(content)
        print("APPLIED %s" % path)

    print("\nNext: pushd frontend\\web && pnpm tsc --noEmit && popd && echo TSC_PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
