import { useCallback, useEffect, useState } from 'react';
import { PageHeader } from '@/components/PageHeader';
import { Card } from '@/components/Card';
import { Button } from '@/components/Button';
import { Badge } from '@/components/Badge';
import { useToast } from '@/components/Toast';
import { useRole } from '@/hooks/useRole';
import {
  fetchBranchLogFields, fetchBranchLogAutoActivities, fetchMyBranchLogs, fetchPendingBranchLogs,
  submitBranchLog, validateBranchLog,
  type BranchLogField, type BranchLogEntry, type BranchLogActivity,
} from '@/lib/api';

type Tab = 'entry' | 'history' | 'review';

export default function BranchLog() {
  const { toast } = useToast();
  const { user, isAdmin } = useRole();
  const [tab, setTab] = useState<Tab>('entry');
  const [fields, setFields] = useState<BranchLogField[]>([]);
  const [values, setValues] = useState<Record<string, string>>({});
  const [mine, setMine] = useState<BranchLogEntry[]>([]);
  const [pending, setPending] = useState<BranchLogEntry[]>([]);
  const [notes, setNotes] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);
  const [autoActs, setAutoActs] = useState<BranchLogActivity[]>([]);

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

  useEffect(() => { void loadFields(); void loadMine(); void loadAuto(); }, [loadFields, loadMine, loadAuto]);
  useEffect(() => { if (tab === 'review' && canReview) void loadPending(); }, [tab, canReview, loadPending]);

  const todaysLog = mine.find((l) => l.log_date === today);

  const submit = async () => {
    setBusy(true);
    try {
      await submitBranchLog(values);
      toast({ tone: 'success', message: 'Daily log submitted for validation.' });
      setValues({}); void loadMine();
    } catch (e) {
      toast({ tone: 'danger', message: e instanceof Error ? e.message : 'Submit failed.' });
    } finally { setBusy(false); }
  };

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
  ];

  return (
    <div className="mx-auto max-w-5xl px-4 py-6">
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
            {autoActs.length > 0 && (
              <div className="mb-4 rounded-md border border-gray-200 bg-gray-50 p-3">
                <div className="text-sm font-semibold text-gray-800">Tracked automatically today</div>
                <p className="mb-2 text-xs text-gray-400">Pulled from your pipeline actions — no need to key these.</p>
                <ol className="space-y-1">
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
            <div className="grid grid-cols-1 gap-6 md:grid-cols-2">
              {/* Quantitative — counts & amounts */}
              <div>
                <h3 className="mb-2 text-sm font-semibold text-gray-800">Quantitative</h3>
                <p className="mb-3 text-xs text-gray-400">Counts and amounts for the day.</p>
                <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                  {metricFields.map((f) => (
                    <label key={f.key} className="text-sm">
                      <span className="mb-1 block text-gray-700">{f.label}{f.unit ? ` (${f.unit})` : ''}</span>
                      <input type="number" min={0} className="w-full rounded border px-2 py-1.5 text-sm"
                        value={values[f.key] ?? ''} onChange={(e) => setValues((p) => ({ ...p, [f.key]: e.target.value }))} />
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
                    value={values.remarks ?? ''} onChange={(e) => setValues((p) => ({ ...p, remarks: e.target.value }))} />
                </label>
              </div>
            </div>
            <div className="mt-3 flex justify-end">
              <Button onClick={() => void submit()} disabled={busy}>Submit daily log</Button>
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
