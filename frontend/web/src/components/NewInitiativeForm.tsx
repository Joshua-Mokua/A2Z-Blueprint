// v10.544 Phase 1 — New Initiative form. Creates an initiative (starts at gate G0)
// via POST /initiatives. Owner picked from the register (StaffPicker) so `io` is a real
// Staff Name and compute_initiative_kpis feeds the BSC.
import { useState } from 'react';
import { StaffPicker } from '@/components/StaffPicker';
import { Badge } from '@/components/Badge';
import type { StaffMember } from '@/lib/api';
import { createInitiative } from '@/lib/api';
import { displayName } from '@/lib/names';

const inputCls =
  'w-full px-3 py-1.5 rounded-md border border-gray-300 text-sm focus:outline-none ' +
  'focus:border-brand-primary focus:ring-2 focus:ring-brand-primary/20';

const CATEGORIES = ['Strategic Initiative', 'Action Commitment', 'Must Win Battle'];

export function NewInitiativeForm({ onCreated }: { onCreated: () => void }) {
  const [openForm, setOpenForm] = useState(false);
  const [name, setName] = useState('');
  const [objective, setObjective] = useState('');
  const [category, setCategory] = useState(CATEGORIES[0]);
  const [workstream, setWorkstream] = useState('Consumer Banking');
  const [owner, setOwner] = useState<StaffMember | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const reset = () => {
    setName(''); setObjective(''); setCategory(CATEGORIES[0]);
    setWorkstream('Consumer Banking'); setOwner(null); setErr(null);
  };

  const canSubmit = name.trim() && objective.trim() && workstream.trim() && owner;

  const submit = async () => {
    if (!canSubmit || !owner) return;
    setBusy(true); setErr(null);
    try {
      const res = await createInitiative({
        name: name.trim(),
        objective: objective.trim(),
        category,
        workstream: workstream.trim(),
        io: owner.name,
      });
      if (res.status !== 'ok') throw new Error('Create failed');
      reset();
      setOpenForm(false);
      onCreated();
    } catch (e) {
      setErr(e instanceof Error ? e.message : 'Create failed');
    } finally {
      setBusy(false);
    }
  };

  if (!openForm) {
    return (
      <button
        type="button"
        onClick={() => setOpenForm(true)}
        className="px-3 py-1.5 rounded-md text-sm font-medium text-white bg-[var(--brand-primary,#0082BB)] hover:opacity-90"
      >
        + New Initiative
      </button>
    );
  }

  return (
    <div className="rounded-lg border border-gray-200 p-4 bg-gray-50 space-y-3">
      <div className="flex items-center justify-between">
        <span className="font-medium text-gray-900">New Initiative</span>
        <button type="button" onClick={() => { reset(); setOpenForm(false); }}
          className="text-xs text-gray-500 underline">Cancel</button>
      </div>

      <div className="space-y-2">
        <input className={inputCls} placeholder="Initiative name"
          value={name} onChange={(e) => setName(e.target.value)} autoComplete="off" />
        <input className={inputCls} placeholder="Objective (what it delivers)"
          value={objective} onChange={(e) => setObjective(e.target.value)} autoComplete="off" />
        <div className="flex gap-2">
          <select className={inputCls} value={category} onChange={(e) => setCategory(e.target.value)}>
            {CATEGORIES.map((c) => <option key={c} value={c}>{c}</option>)}
          </select>
          <input className={inputCls} placeholder="Workstream"
            value={workstream} onChange={(e) => setWorkstream(e.target.value)} autoComplete="off" />
        </div>
        <div>
          <div className="text-xs text-gray-500 mb-1">Owner</div>
          {owner ? (
            <div className="flex items-center gap-2">
              <Badge tone="success">{displayName(owner.name)}</Badge>
              <button type="button" onClick={() => setOwner(null)}
                className="text-xs text-gray-500 underline">change</button>
            </div>
          ) : (
            <StaffPicker value={owner} onChange={setOwner} />
          )}
        </div>
      </div>

      {err && <div className="text-sm text-red-700">{err}</div>}

      <div className="flex justify-end gap-2">
        <button type="button" disabled={!canSubmit || busy} onClick={() => void submit()}
          className="px-3 py-1.5 rounded-md text-sm font-medium text-white bg-[var(--brand-primary,#0082BB)] disabled:opacity-40 hover:opacity-90">
          {busy ? 'Creating…' : 'Create'}
        </button>
      </div>
    </div>
  );
}
