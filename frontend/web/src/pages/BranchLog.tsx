import { useCallback, useEffect, useRef, useState } from 'react';
import { PageHeader } from '@/components/PageHeader';
import { Card } from '@/components/Card';
import { Button } from '@/components/Button';
import { Badge } from '@/components/Badge';
import { useToast } from '@/components/Toast';
import { useRole } from '@/hooks/useRole';
import DayPlanner from '@/components/DayPlanner';
import {
  fetchBranchLogFields, fetchBranchLogAutoActivities, fetchMyBranchLogs, fetchPendingBranchLogs,
  submitBranchLogHourly, saveBranchLogHourlyDraft, fetchBranchLogDraft, validateBranchLog, fetchBranchLogConfig, saveBranchLogConfig, fetchBranchLogRanking,
  fetchBranchLogActivities, saveBranchLogActivities,
  type BranchLogField, type BranchLogEntry, type BranchLogActivity, type BranchLogRankRow, type ExtraActivity,
  type HourlyMap,
} from '@/lib/api';

type Tab = 'entry' | 'history' | 'review' | 'ranking' | 'setup';

// True when the planner holds anything worth persisting. Module scope on purpose:
// the submit/draft callbacks must stay dependency-free to keep a stable identity.
function hasEntryContent(h: HourlyMap, r: string): boolean {
  if (r.trim().length > 0) return true;
  return Object.values(h).some(
    (b) => Object.keys(b.counts || {}).length > 0 || (b.meetings?.length ?? 0) > 0 || !!b.note,
  );
}

export default function BranchLog() {
  const { toast } = useToast();
  const { user, isAdmin } = useRole();
  const [tab, setTab] = useState<Tab>('entry');
  const [fields, setFields] = useState<BranchLogField[]>([]);
  // Phase 2c: the day planner is the entry surface. `hourly` is the source of
  // truth; day totals are derived server-side (utils/branch_log.derive_from_hourly).
  const [hourly, setHourly] = useState<HourlyMap>({});
  const [remarks, setRemarks] = useState('');
  const [lastSaved, setLastSaved] = useState<Date | null>(null);
  const [mine, setMine] = useState<BranchLogEntry[]>([]);
  const [pending, setPending] = useState<BranchLogEntry[]>([]);
  const [notes, setNotes] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);
  // Item 3/4: track unsaved edits so we can auto-save a draft on leave.
  const [dirty, setDirty] = useState(false);
  const [savingDraft, setSavingDraft] = useState(false);
  const [autoActs, setAutoActs] = useState<BranchLogActivity[]>([]);
  const [indexTarget, setIndexTarget] = useState(0);
  const [ranking, setRanking] = useState<BranchLogRankRow[]>([]);
  const [weightDraft, setWeightDraft] = useState<Record<string, string>>({});
  const [targetDraft, setTargetDraft] = useState('');
  const [extraActs, setExtraActs] = useState<ExtraActivity[]>([]);
  const [newAct, setNewAct] = useState<{ key: string; label: string; unit: string; weight: string; roles: string }>({ key: '', label: '', unit: '', weight: '', roles: '' });

  const canReview = isAdmin || /manager|head|supervisor/i.test(String(user?.role ?? ''));
  const metricFields = fields.filter((f) => f.type !== 'text');
  const today = new Date().toISOString().slice(0, 10);

  const loadFields = useCallback(async () => {
    try { const r = await fetchBranchLogFields(); setFields(r.fields); } catch { /* ignore */ }
  }, []);
  const loadMine = useCallback(async () => {
    try { const r = await fetchMyBranchLogs(14); setMine(r.logs); } catch { /* ignore */ }
  }, []);
  const loadPending = useCallback(async () => {
    try { const r = await fetchPendingBranchLogs(); setPending(r.logs); } catch { /* ignore */ }
  }, []);
  const loadAuto = useCallback(async () => {
    try { const r = await fetchBranchLogAutoActivities(); setAutoActs(r.activities); } catch { /* ignore */ }
  }, []);
  const loadCfg = useCallback(async () => {
    try {
      const r = await fetchBranchLogConfig();
      setIndexTarget(r.daily_index_target || 0);
      setTargetDraft(String(r.daily_index_target || 0));
      const wd: Record<string, string> = {};
      for (const [k, v] of Object.entries(r.activity_weights || {})) wd[k] = String(v);
      setWeightDraft(wd);
    } catch { /* ignore */ }
  }, []);
  const loadRanking = useCallback(async () => {
    try { const r = await fetchBranchLogRanking(30); setRanking(r.ranking); setIndexTarget(r.daily_index_target || 0); } catch { /* ignore */ }
  }, []);
  const loadActs = useCallback(async () => {
    try { const r = await fetchBranchLogActivities(); setExtraActs(r.extra); } catch { /* ignore */ }
  }, []);

  useEffect(() => { void loadFields(); void loadMine(); void loadAuto(); void loadCfg(); }, [loadFields, loadMine, loadAuto, loadCfg]);
  useEffect(() => { if (tab === 'ranking') void loadRanking(); }, [tab, loadRanking]);
  useEffect(() => { if (tab === 'setup') void loadActs(); }, [tab, loadActs]);
  useEffect(() => { if (tab === 'review' && canReview) void loadPending(); }, [tab, canReview, loadPending]);

  const todaysLog = mine.find((l) => l.log_date === today);

  // Phase 2c: submit/draft read the entry from a ref so the callbacks keep a
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
  useEffect(() => { void loadDraft(); }, [loadDraft]);

  // Item 4: auto-save a draft when leaving with unsaved edits. The unmount
  // handler runs on logout and in-app navigation (React unmounts the page) and
  // uses the normal authenticated saveDraft. A beforeunload warning covers the
  // browser-close/refresh case (sendBeacon can't carry the JWT, so we warn).
  const dirtyRef = useRef(false); useEffect(() => { dirtyRef.current = dirty; }, [dirty]);
  useEffect(() => {
    const warn = (e: BeforeUnloadEvent) => {
      if (dirtyRef.current) { e.preventDefault(); e.returnValue = ''; }
    };
    window.addEventListener('beforeunload', warn);
    return () => {
      window.removeEventListener('beforeunload', warn);
      if (dirtyRef.current) void saveDraft(true);
    };
  }, [saveDraft]);

  // Phase 2c: autosave the planner every 30 seconds while edits are pending.
  // saveDraft is ref-backed and stable, so the timer is armed once per mount.
  useEffect(() => {
    const id = window.setInterval(() => {
      if (dirtyRef.current) void saveDraft(true);
    }, 30_000);
    return () => window.clearInterval(id);
  }, [saveDraft]);

  const review = async (id: string, approved: boolean) => {
    setBusy(true);
    try {
      await validateBranchLog(id, approved, (notes[id] ?? '').trim());
      toast({ tone: 'success', message: approved ? 'Log validated.' : 'Log returned.' });
      void loadPending();
    } catch (e) {
      toast({ tone: 'danger', message: e instanceof Error ? e.message : 'Action failed.' });
    } finally { setBusy(false); }
  };

  const fmt = (v: unknown) => (typeof v === 'number' ? v.toLocaleString() : String(v ?? ''));
  const metricSummary = (l: BranchLogEntry) =>
    metricFields.filter((f) => Number(l[f.key]) > 0).map((f) => (
      <span key={f.key}>{f.label}: <b>{fmt(l[f.key])}</b></span>
    ));

  const tabs: [Tab, string][] = [
    ['entry', 'Daily Log Entry'],
    ['history', 'Log History'],
    ...(canReview ? ([['review', 'Supervisor Review']] as [Tab, string][]) : []),
    ['ranking', 'Ranking'],
    ...(isAdmin ? ([['setup', 'Index Setup']] as [Tab, string][]) : []),
  ];
  // DayPlanner renders the live day index itself (sum of count x weight over hours).
  const dateLabel = new Date().toLocaleDateString(undefined, { weekday: 'long', day: 'numeric', month: 'long' });

  return (
    <div className="mx-auto max-w-7xl px-4 py-6 2xl:max-w-[1680px]">
      <PageHeader ribbon title="Daily Log" subtitle="Log your daily activity; supervisors validate." />

      <div className="mb-4 flex gap-1 text-sm">
        {tabs.map(([id, lbl]) => (
          <button key={id} onClick={() => setTab(id)}
            className={`rounded px-3 py-1.5 font-medium transition-colors ${
              tab === id ? 'bg-[#0082BB] text-white' : 'text-[#005B82] hover:bg-[#0082BB]/10'}`}>
            {lbl}{id === 'review' && pending.length ? ` (${pending.length})` : ''}
          </button>
        ))}
      </div>

      {tab === 'entry' && (
        <Card>
          <Card.Header><h2 className="text-base font-semibold text-gray-900">Today&apos;s activity</h2></Card.Header>
          <Card.Body>
            {todaysLog && (
              <div className="mb-3 rounded border border-blue-100 bg-blue-50 p-2 text-sm text-blue-800">
                You already submitted today
                {todaysLog.validated ? ' (validated)' : todaysLog.rejected ? ' (returned — please correct)' : ' (awaiting validation)'}.
                {' '}Re-submitting updates it.
              </div>
            )}
            <div className="grid grid-cols-1 gap-5 lg:grid-cols-[minmax(0,1fr)_20rem]">
              <DayPlanner
                fields={metricFields}
                hourly={hourly}
                onChange={(next) => { setDirty(true); setHourly(next); }}
                target={indexTarget}
                dateLabel={dateLabel}
              />

              {/* Context in, actions out. Keeps Save/Submit beside the timeline
                  rather than below it, so they stay above the fold. */}
              <aside className="flex flex-col gap-4">
                {autoActs.length > 0 && (
                  <div className="rounded-md border border-gray-200 bg-gray-50 p-3">
                    <div className="text-sm font-semibold text-gray-800">Tracked automatically today</div>
                    <p className="mb-2 text-xs text-gray-400">Pulled from your pipeline actions — no need to key these.</p>
                    <ol className="max-h-40 space-y-1 overflow-y-auto">
                      {autoActs.map((a, i) => (
                        <li key={i} className="flex items-start gap-2 text-sm">
                          <span className="tabular-nums text-gray-400">{a.time}</span>
                          <span className="rounded border border-gray-200 bg-white px-1.5 py-0.5 text-xs text-gray-600">{a.kind}</span>
                          <span className="text-gray-700">{a.detail}</span>
                        </li>
                      ))}
                    </ol>
                  </div>
                )}

                <label className="block text-sm">
                  <span className="mb-1 block text-gray-700">Remarks / challenges</span>
                  <textarea rows={4} className="w-full rounded border px-2 py-1.5 text-sm"
                    placeholder="Blockers, escalations, anything the hours don't say."
                    value={remarks} onChange={(e) => { setDirty(true); setRemarks(e.target.value); }} />
                </label>

                <div className="mt-auto border-t border-gray-100 pt-3">
                  <div className="mb-2 text-xs text-gray-400">
                    {savingDraft
                      ? 'Saving…'
                      : dirty
                        ? 'Unsaved changes — autosaves every 30 seconds.'
                        : lastSaved
                          ? `All changes saved ${lastSaved.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}`
                          : 'Autosaves every 30 seconds.'}
                  </div>
                  <div className="flex flex-col gap-2">
                    <Button fullWidth onClick={() => void submit()} disabled={busy}>Submit daily log</Button>
                    <Button fullWidth variant="ghost" onClick={() => void saveDraft()} disabled={busy || savingDraft}>
                      {savingDraft ? 'Saving…' : 'Save draft'}
                    </Button>
                  </div>
                </div>
              </aside>
            </div>
          </Card.Body>
        </Card>
      )}

      {tab === 'ranking' && (
        <Card>
          <Card.Header><h2 className="text-base font-semibold text-gray-900">Productivity ranking — last 30 days</h2></Card.Header>
          <Card.Body>
            {ranking.length === 0 ? <p className="text-sm text-gray-400">No logs in this period.</p> : (
              <table className="w-full text-sm">
                <thead><tr className="text-left text-xs text-gray-400">
                  <th className="py-1">#</th><th>Staff</th><th>Unit</th><th className="text-right">Index</th><th className="text-right">Avg/day</th><th className="text-right">Days</th>
                </tr></thead>
                <tbody>
                  {ranking.map((r) => (
                    <tr key={r.staff_code} className="border-t border-gray-100">
                      <td className="py-1.5 font-medium text-gray-500">{r.rank}</td>
                      <td className="font-medium text-gray-900">{r.staff_name}</td>
                      <td className="text-gray-500">{r.unit}</td>
                      <td className="text-right font-semibold tabular-nums">{r.index}</td>
                      <td className={'text-right tabular-nums ' + (r.target > 0 && r.avg_per_day >= r.target ? 'text-emerald-600' : 'text-gray-600')}>{r.avg_per_day}</td>
                      <td className="text-right tabular-nums text-gray-500">{r.days}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </Card.Body>
        </Card>
      )}

      {tab === 'setup' && isAdmin && (
        <Card>
          <Card.Header><h2 className="text-base font-semibold text-gray-900">Activity weights &amp; daily index target</h2></Card.Header>
          <Card.Body>
            <label className="mb-4 block text-sm">
              <span className="mb-1 block text-gray-700">Daily index target</span>
              <input type="number" min={0} className="w-40 rounded border px-2 py-1.5 text-sm"
                value={targetDraft} onChange={(e) => setTargetDraft(e.target.value)} />
            </label>
            <p className="mb-2 text-sm font-medium text-gray-700">Points per activity</p>
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
              {metricFields.map((f) => (
                <label key={f.key} className="flex items-center justify-between gap-2 text-sm">
                  <span className="text-gray-700">{f.label}</span>
                  <input type="number" step="any" className="w-24 rounded border px-2 py-1 text-sm"
                    value={weightDraft[f.key] ?? ''} onChange={(e) => setWeightDraft((p) => ({ ...p, [f.key]: e.target.value }))} />
                </label>
              ))}
            </div>
            <div className="mt-4 flex justify-end">
              <Button disabled={busy} onClick={async () => {
                setBusy(true);
                try {
                  const w: Record<string, number> = {};
                  for (const [k, v] of Object.entries(weightDraft)) w[k] = Number(v) || 0;
                  await saveBranchLogConfig(w, Number(targetDraft) || 0);
                  toast({ tone: 'success', message: 'Weights & target saved.' });
                  await loadFields(); await loadCfg();
                } catch (e) { toast({ tone: 'danger', message: e instanceof Error ? e.message : 'Save failed' }); }
                finally { setBusy(false); }
              }}>Save weights &amp; target</Button>
            </div>

            <div className="mt-6 border-t border-gray-100 pt-4">
              <h3 className="mb-1 text-sm font-semibold text-gray-800">Extra activities (head office / role-specific)</h3>
              <p className="mb-3 text-xs text-gray-400">These appear only for the roles you list (comma-separated). Leave roles blank to show for everyone.</p>
              {extraActs.length > 0 && (
                <div className="mb-3 space-y-1">
                  {extraActs.map((a, i) => (
                    <div key={a.key} className="flex items-center justify-between rounded border border-gray-200 bg-gray-50 px-2 py-1 text-sm">
                      <div>
                        <span className="font-medium text-gray-800">{a.label}</span>
                        <span className="ml-2 text-xs text-gray-500">{a.unit || 'count'} · wt {a.weight}{a.roles.length ? ` · ${a.roles.join(', ')}` : ' · all roles'}</span>
                      </div>
                      <button className="text-xs text-gray-400 hover:text-red-600"
                        onClick={() => setExtraActs((p) => p.filter((_, j) => j !== i))}>Remove</button>
                    </div>
                  ))}
                </div>
              )}
              <div className="grid grid-cols-1 gap-2 sm:grid-cols-5">
                <input className={'rounded border px-2 py-1 text-sm'} placeholder="key (e.g. credit_apps)" value={newAct.key} onChange={(e) => setNewAct((p) => ({ ...p, key: e.target.value }))} />
                <input className={'rounded border px-2 py-1 text-sm'} placeholder="Label" value={newAct.label} onChange={(e) => setNewAct((p) => ({ ...p, label: e.target.value }))} />
                <input className={'rounded border px-2 py-1 text-sm'} placeholder="unit" value={newAct.unit} onChange={(e) => setNewAct((p) => ({ ...p, unit: e.target.value }))} />
                <input className={'rounded border px-2 py-1 text-sm'} type="number" step="any" placeholder="weight" value={newAct.weight} onChange={(e) => setNewAct((p) => ({ ...p, weight: e.target.value }))} />
                <input className={'rounded border px-2 py-1 text-sm'} placeholder="roles (comma-sep)" value={newAct.roles} onChange={(e) => setNewAct((p) => ({ ...p, roles: e.target.value }))} />
              </div>
              <div className="mt-2 flex gap-2">
                <Button variant="ghost" onClick={() => {
                  const k = newAct.key.trim(); if (!k || !newAct.label.trim()) { toast({ tone: 'danger', message: 'Key and label required.' }); return; }
                  setExtraActs((p) => [...p.filter((x) => x.key !== k), { key: k, label: newAct.label.trim(), type: 'int', unit: newAct.unit.trim(), weight: Number(newAct.weight) || 0, roles: newAct.roles.split(',').map((s) => s.trim()).filter(Boolean) }]);
                  setNewAct({ key: '', label: '', unit: '', weight: '', roles: '' });
                }}>Add activity</Button>
                <Button disabled={busy} onClick={async () => {
                  setBusy(true);
                  try { await saveBranchLogActivities(extraActs); toast({ tone: 'success', message: 'Activities saved.' }); await loadFields(); await loadActs(); }
                  catch (e) { toast({ tone: 'danger', message: e instanceof Error ? e.message : 'Save failed' }); }
                  finally { setBusy(false); }
                }}>Save activities</Button>
              </div>
            </div>
          </Card.Body>
        </Card>
      )}

      {tab === 'history' && (
        <Card>
          <Card.Header><h2 className="text-base font-semibold text-gray-900">My recent logs</h2></Card.Header>
          <Card.Body>
            {mine.length === 0 ? <p className="text-sm text-gray-400">No logs in the last 14 days.</p> : (
              <div className="space-y-2">
                {mine.map((l) => (
                  <div key={l.id} className="rounded border border-gray-100 p-3">
                    <div className="flex items-center justify-between">
                      <span className="font-medium text-gray-900">{l.log_date}</span>
                      <Badge tone={l.validated ? 'success' : l.rejected ? 'danger' : 'warning'} size="sm">
                        {l.validated ? 'Validated' : l.rejected ? 'Returned' : 'Pending'}
                      </Badge>
                    </div>
                    <div className="mt-1 flex flex-wrap gap-x-4 gap-y-1 text-xs text-gray-600">{metricSummary(l)}</div>
                    {l.remarks ? <p className="mt-1 text-xs text-gray-500">{l.remarks}</p> : null}
                    {l.manager_note ? <p className="mt-1 text-xs text-brand-primary">Manager: {l.manager_note}</p> : null}
                  </div>
                ))}
              </div>
            )}
          </Card.Body>
        </Card>
      )}

      {tab === 'review' && canReview && (
        <Card>
          <Card.Header><h2 className="text-base font-semibold text-gray-900">Awaiting validation</h2></Card.Header>
          <Card.Body>
            {pending.length === 0 ? <p className="text-sm text-gray-400">Nothing pending in your unit.</p> : (
              <div className="space-y-3">
                {pending.map((l) => (
                  <div key={l.id} className="rounded border border-amber-200 bg-amber-50 p-3">
                    <div className="flex items-center justify-between">
                      <span className="font-medium text-gray-900">{l.staff_name} <span className="text-gray-400">({l.role}, {l.unit})</span></span>
                      <span className="text-xs text-gray-500">{l.log_date}</span>
                    </div>
                    <div className="mt-1 flex flex-wrap gap-x-4 gap-y-1 text-xs text-gray-600">{metricSummary(l)}</div>
                    {l.remarks ? <p className="mt-1 text-xs text-gray-500">{l.remarks}</p> : null}
                    <input className="mt-2 w-full rounded border px-2 py-1 text-xs" placeholder="Note (optional)"
                      value={notes[l.id] ?? ''} onChange={(e) => setNotes((p) => ({ ...p, [l.id]: e.target.value }))} />
                    <div className="mt-2 flex gap-2">
                      <Button size="sm" onClick={() => void review(l.id, true)} disabled={busy}>Validate</Button>
                      <Button size="sm" variant="ghost" onClick={() => void review(l.id, false)} disabled={busy}>Return</Button>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </Card.Body>
        </Card>
      )}
    </div>
  );
}
