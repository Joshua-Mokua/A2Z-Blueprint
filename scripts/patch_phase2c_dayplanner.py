#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Phase 2c — wire DayPlanner into the Daily Log Entry tab.

Target : frontend/web/src/pages/BranchLog.tsx
Changes:
  1. imports        — swap flat submit/draft clients for the hourly ones, add
                      DayPlanner + HourlyMap.
  2. state          — replace `values` with `hourly` / `remarks` / `lastSaved`.
  3. submit/draft   — repoint at submitBranchLogHourly / saveBranchLogHourlyDraft,
                      re-hydrate `hourly` from today's draft, guard empty submits,
                      make saveDraft ref-backed (stable identity).
  4. leave-handler  — drop `dirty` from the unmount-autosave deps (it was firing a
                      draft POST on every edit) and arm a 30-second autosave timer.
  5. liveIndex      — removed; DayPlanner renders the live day index itself.
  6. Entry JSX      — flat quantitative/qualitative grid -> <DayPlanner> + a
                      whole-day remarks box + save-status footer.

Usage (from project root, .venv active):
    python scripts\\patch_phase2c_dayplanner.py            # dry run
    python scripts\\patch_phase2c_dayplanner.py --apply    # write + .pre_phase2c backup
"""
import os
import shutil
import sys

TARGET = os.path.join("frontend", "web", "src", "pages", "BranchLog.tsx")
BACKUP_SUFFIX = ".pre_phase2c"

# ── 1. imports ────────────────────────────────────────────────────────────────
OLD_IMPORTS = """import {
  fetchBranchLogFields, fetchBranchLogAutoActivities, fetchMyBranchLogs, fetchPendingBranchLogs,
  submitBranchLog, saveBranchLogDraft, fetchBranchLogDraft, validateBranchLog, fetchBranchLogConfig, saveBranchLogConfig, fetchBranchLogRanking,
  fetchBranchLogActivities, saveBranchLogActivities,
  type BranchLogField, type BranchLogEntry, type BranchLogActivity, type BranchLogRankRow, type ExtraActivity,
} from '@/lib/api';"""

NEW_IMPORTS = """import DayPlanner from '@/components/DayPlanner';
import {
  fetchBranchLogFields, fetchBranchLogAutoActivities, fetchMyBranchLogs, fetchPendingBranchLogs,
  submitBranchLogHourly, saveBranchLogHourlyDraft, fetchBranchLogDraft, validateBranchLog, fetchBranchLogConfig, saveBranchLogConfig, fetchBranchLogRanking,
  fetchBranchLogActivities, saveBranchLogActivities,
  type BranchLogField, type BranchLogEntry, type BranchLogActivity, type BranchLogRankRow, type ExtraActivity,
  type HourlyMap,
} from '@/lib/api';"""

# ── 1b. module-scope helper ───────────────────────────────────────────────────
OLD_TABTYPE = """type Tab = 'entry' | 'history' | 'review' | 'ranking' | 'setup';"""

NEW_TABTYPE = """type Tab = 'entry' | 'history' | 'review' | 'ranking' | 'setup';

// True when the planner holds anything worth persisting. Module scope on purpose:
// the submit/draft callbacks must stay dependency-free to keep a stable identity.
function hasEntryContent(h: HourlyMap, r: string): boolean {
  if (r.trim().length > 0) return true;
  return Object.values(h).some(
    (b) => Object.keys(b.counts || {}).length > 0 || (b.meetings?.length ?? 0) > 0 || !!b.note,
  );
}"""

# ── 2. state ──────────────────────────────────────────────────────────────────
OLD_STATE = """  const [values, setValues] = useState<Record<string, string>>({});"""

NEW_STATE = """  // Phase 2c: the day planner is the entry surface. `hourly` is the source of
  // truth; day totals are derived server-side (utils/branch_log.derive_from_hourly).
  const [hourly, setHourly] = useState<HourlyMap>({});
  const [remarks, setRemarks] = useState('');
  const [lastSaved, setLastSaved] = useState<Date | null>(null);"""

# ── 3. submit / saveDraft / loadDraft ─────────────────────────────────────────
OLD_SUBMIT_BLOCK = """  const submit = async () => {
    setBusy(true);
    try {
      await submitBranchLog(values);
      toast({ tone: 'success', message: 'Daily log submitted for validation.' });
      setValues({}); setDirty(false); void loadMine();
    } catch (e) {
      toast({ tone: 'danger', message: e instanceof Error ? e.message : 'Submit failed.' });
    } finally { setBusy(false); }
  };

  // Item 3: save the current entry as a private draft (not submitted).
  const saveDraft = useCallback(async (silent = false) => {
    if (Object.keys(values).length === 0) return;
    setSavingDraft(true);
    try {
      await saveBranchLogDraft(values);
      setDirty(false);
      if (!silent) toast({ tone: 'success', message: 'Draft saved. You can submit later today.' });
    } catch (e) {
      if (!silent) toast({ tone: 'danger', message: e instanceof Error ? e.message : 'Could not save draft.' });
    } finally { setSavingDraft(false); }
  }, [values, toast]);

  // Item 3: re-hydrate today's saved entry (draft or submitted) on first load.
  const loadDraft = useCallback(async () => {
    try {
      const r = await fetchBranchLogDraft();
      if (r.log) {
        const v: Record<string, string> = {};
        for (const [k, val] of Object.entries(r.log)) {
          if (typeof val === 'number') v[k] = String(val);
        }
        if (typeof r.log.remarks === 'string') v.remarks = r.log.remarks;
        setValues((prev) => (Object.keys(prev).length ? prev : v));
      }
    } catch { /* no draft — start blank */ }
  }, []);

  // Item 3: load today's saved entry once, on mount (after loadDraft exists).
  useEffect(() => { void loadDraft(); }, [loadDraft]);"""

NEW_SUBMIT_BLOCK = """  // Phase 2c: submit/draft read the entry from a ref so the callbacks keep a
  // stable identity. The 30s timer and the unmount handler must not be re-armed
  // on every keystroke (that previously fired a draft POST per edit).
  const entryRef = useRef<{ hourly: HourlyMap; remarks: string }>({ hourly: {}, remarks: '' });
  useEffect(() => { entryRef.current = { hourly, remarks }; }, [hourly, remarks]);

  const submit = async () => {
    const { hourly: h, remarks: r } = entryRef.current;
    // Guard: an empty planner would derive all-zero day totals and wipe a
    // pre-existing entry for today. Make the user log something first.
    if (!hasEntryContent(h, r)) {
      toast({ tone: 'danger', message: 'Log at least one activity or a remark before submitting.' });
      return;
    }
    setBusy(true);
    try {
      await submitBranchLogHourly(h, r);
      toast({ tone: 'success', message: 'Daily log submitted for validation.' });
      setDirty(false); setLastSaved(new Date()); void loadMine();
    } catch (e) {
      toast({ tone: 'danger', message: e instanceof Error ? e.message : 'Submit failed.' });
    } finally { setBusy(false); }
  };

  // Item 3 (Phase 2c): save the planner as a private draft (not submitted).
  const saveDraft = useCallback(async (silent = false) => {
    const { hourly: h, remarks: r } = entryRef.current;
    if (!hasEntryContent(h, r)) return;
    setSavingDraft(true);
    try {
      await saveBranchLogHourlyDraft(h, r);
      setDirty(false);
      setLastSaved(new Date());
      if (!silent) toast({ tone: 'success', message: 'Draft saved. You can submit later today.' });
    } catch (e) {
      if (!silent) toast({ tone: 'danger', message: e instanceof Error ? e.message : 'Could not save draft.' });
    } finally { setSavingDraft(false); }
  }, [toast]);

  // Item 3 (Phase 2c): re-hydrate today's hourly map (draft or submitted) on load.
  // Legacy flat entries carry no `hourly` — those open as an empty planner.
  const loadDraft = useCallback(async () => {
    try {
      const r = await fetchBranchLogDraft();
      const log = r.log;
      if (!log) return;
      const raw = (log as { hourly?: unknown }).hourly;
      if (raw && typeof raw === 'object' && Object.keys(raw as object).length > 0) {
        setHourly((prev) => (Object.keys(prev).length ? prev : (raw as HourlyMap)));
      }
      if (typeof log.remarks === 'string' && log.remarks) {
        setRemarks((prev) => (prev ? prev : (log.remarks as string)));
      }
    } catch { /* no entry today — start blank */ }
  }, []);

  // Item 3: load today's saved entry once, on mount (after loadDraft exists).
  useEffect(() => { void loadDraft(); }, [loadDraft]);"""

# ── 4. leave-handler deps + 30s autosave ──────────────────────────────────────
OLD_LEAVE = """      if (dirtyRef.current) void saveDraft(true);
    };
  }, [saveDraft, dirty]);"""

NEW_LEAVE = """      if (dirtyRef.current) void saveDraft(true);
    };
  }, [saveDraft]);

  // Phase 2c: autosave the planner every 30 seconds while edits are pending.
  // saveDraft is ref-backed and stable, so the timer is armed once per mount.
  useEffect(() => {
    const id = window.setInterval(() => {
      if (dirtyRef.current) void saveDraft(true);
    }, 30_000);
    return () => window.clearInterval(id);
  }, [saveDraft]);"""

# ── 5. liveIndex -> dateLabel ─────────────────────────────────────────────────
OLD_LIVEINDEX = """  const liveIndex = metricFields.reduce((s, f) => s + (Number(values[f.key]) || 0) * (Number(f.weight) || 0), 0);"""

NEW_LIVEINDEX = """  // DayPlanner renders the live day index itself (sum of count x weight over hours).
  const dateLabel = new Date().toLocaleDateString(undefined, { weekday: 'long', day: 'numeric', month: 'long' });"""

# ── 6. Entry tab JSX ──────────────────────────────────────────────────────────
OLD_ENTRY_JSX = """            <div className="grid grid-cols-1 gap-6 md:grid-cols-2">
              {/* Quantitative — counts & amounts */}
              <div>
                <h3 className="mb-2 text-sm font-semibold text-gray-800">Quantitative</h3>
                <p className="mb-3 text-xs text-gray-400">Counts and amounts for the day.</p>
                <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                  {metricFields.map((f) => (
                    <label key={f.key} className="text-sm">
                      <span className="mb-1 block text-gray-700">{f.label}{f.unit ? ` (${f.unit})` : ''}</span>
                      <input type="number" min={0} className="w-full rounded border px-2 py-1.5 text-sm"
                        value={values[f.key] ?? ''} onChange={(e) => { setDirty(true); setValues((p) => ({ ...p, [f.key]: e.target.value })); }} />
                    </label>
                  ))}
                </div>
              </div>
              {/* Qualitative — notes & remarks */}
              <div>
                <h3 className="mb-2 text-sm font-semibold text-gray-800">Qualitative</h3>
                <p className="mb-3 text-xs text-gray-400">Notes, challenges, and context.</p>
                <label className="block text-sm">
                  <span className="mb-1 block text-gray-700">Remarks / challenges</span>
                  <textarea rows={12} className="w-full rounded border px-2 py-1.5 text-sm"
                    value={values.remarks ?? ''} onChange={(e) => { setDirty(true); setValues((p) => ({ ...p, remarks: e.target.value })); }} />
                </label>
              </div>
            </div>
            <div className="mt-3 flex items-center justify-between border-t border-gray-100 pt-3">
              <div className="text-sm">
                <span className="text-gray-500">Today&apos;s productivity index: </span>
                <span className="font-semibold text-gray-900">{Math.round(liveIndex)}</span>
                {indexTarget > 0 && (
                  <span className={liveIndex >= indexTarget ? 'ml-1 text-emerald-600' : 'ml-1 text-gray-400'}>
                    {' '}/ target {indexTarget} ({Math.round((liveIndex / indexTarget) * 100)}%)
                  </span>
                )}
              </div>
              <div className="flex items-center gap-2">
                <Button variant="secondary" onClick={() => void saveDraft()} disabled={busy || savingDraft}>
                  {savingDraft ? 'Saving…' : 'Save draft'}
                </Button>
                <Button onClick={() => void submit()} disabled={busy}>Submit daily log</Button>
              </div>
            </div>"""

NEW_ENTRY_JSX = """            <DayPlanner
              fields={metricFields}
              hourly={hourly}
              onChange={(next) => { setDirty(true); setHourly(next); }}
              target={indexTarget}
              dateLabel={dateLabel}
            />

            <label className="mt-4 block text-sm">
              <span className="mb-1 block text-gray-700">Remarks / challenges (whole day)</span>
              <textarea rows={3} className="w-full rounded border px-2 py-1.5 text-sm"
                placeholder="Context your manager should know — blockers, escalations, anything the hours don't say."
                value={remarks} onChange={(e) => { setDirty(true); setRemarks(e.target.value); }} />
            </label>

            <div className="mt-3 flex items-center justify-between border-t border-gray-100 pt-3">
              <div className="text-xs text-gray-400">
                {savingDraft
                  ? 'Saving…'
                  : dirty
                    ? 'Unsaved changes — autosaves every 30 seconds.'
                    : lastSaved
                      ? `All changes saved ${lastSaved.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}`
                      : 'Autosaves every 30 seconds.'}
              </div>
              <div className="flex items-center gap-2">
                <Button variant="secondary" onClick={() => void saveDraft()} disabled={busy || savingDraft}>
                  {savingDraft ? 'Saving…' : 'Save draft'}
                </Button>
                <Button onClick={() => void submit()} disabled={busy}>Submit daily log</Button>
              </div>
            </div>"""

EDITS = [
    ("imports (DayPlanner + hourly clients + HourlyMap)", OLD_IMPORTS, NEW_IMPORTS),
    ("module-scope hasEntryContent helper", OLD_TABTYPE, NEW_TABTYPE),
    ("state (values -> hourly/remarks/lastSaved)", OLD_STATE, NEW_STATE),
    ("submit / saveDraft / loadDraft -> hourly path", OLD_SUBMIT_BLOCK, NEW_SUBMIT_BLOCK),
    ("leave-handler deps + 30s autosave timer", OLD_LEAVE, NEW_LEAVE),
    ("liveIndex -> dateLabel", OLD_LIVEINDEX, NEW_LIVEINDEX),
    ("Entry tab JSX -> <DayPlanner>", OLD_ENTRY_JSX, NEW_ENTRY_JSX),
]

# Guards that must hold AFTER patching (cheap self-check; tsc is the real gate).
FORBIDDEN_AFTER = [
    ("setValues(", "flat-form state setter still referenced"),
    ("submitBranchLog(", "flat submit client still referenced"),
    ("saveBranchLogDraft(", "flat draft client still referenced"),
    ("liveIndex", "removed liveIndex still referenced"),
]
REQUIRED_AFTER = [
    "import DayPlanner from '@/components/DayPlanner';",
    "<DayPlanner",
    "submitBranchLogHourly(",
    "saveBranchLogHourlyDraft(",
    "window.setInterval(",
]


def main() -> int:
    apply = "--apply" in sys.argv
    if not os.path.isfile(TARGET):
        print("ABORT: %s not found. Run from the project root." % TARGET)
        return 1

    with open(TARGET, "r", encoding="utf-8") as fh:
        src = fh.read()
    original = src

    # Idempotency check.
    if "import DayPlanner from '@/components/DayPlanner';" in src:
        print("ABORT: BranchLog.tsx already imports DayPlanner — Phase 2c looks applied.")
        return 1

    for name, old, new in EDITS:
        n = src.count(old)
        if n != 1:
            print("ABORT: anchor '%s' matched %d times (expected exactly 1)." % (name, n))
            print("       The file has drifted from the expected 1e757d2 state; no changes written.")
            return 1
        src = src.replace(old, new, 1)
        print("  ok  %s" % name)

    for token, why in FORBIDDEN_AFTER:
        if token in src:
            print("ABORT: post-check failed — %s ('%s' still present)." % (why, token))
            return 1
    for token in REQUIRED_AFTER:
        if token not in src:
            print("ABORT: post-check failed — expected '%s' missing after patch." % token)
            return 1

    # Cheap structural sanity on the whole file.
    for opener, closer in (("{", "}"), ("(", ")"), ("[", "]")):
        if src.count(opener) != src.count(closer):
            print("ABORT: unbalanced %s%s after patch (%d vs %d)."
                  % (opener, closer, src.count(opener), src.count(closer)))
            return 1

    print("\n7/7 anchors matched, post-checks clean.")
    print("Lines: %d -> %d" % (original.count("\n") + 1, src.count("\n") + 1))

    if not apply:
        print("\nDRY RUN — nothing written. Re-run with --apply to commit changes to disk.")
        return 0

    backup = TARGET + BACKUP_SUFFIX
    shutil.copy2(TARGET, backup)
    with open(TARGET, "w", encoding="utf-8", newline="") as fh:
        fh.write(src)
    print("\nAPPLIED. Backup: %s" % backup)
    print("Next: pushd frontend\\web && pnpm tsc --noEmit && popd && echo TSC_PASSED_PROCEED_WITH_COMMIT")
    return 0


if __name__ == "__main__":
    sys.exit(main())
