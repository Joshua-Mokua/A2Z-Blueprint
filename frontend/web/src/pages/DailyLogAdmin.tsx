// ──────────────────────────────────────────────────────────────────────────
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
      </div>
    </>
  );
}

export default DailyLogAdmin;
