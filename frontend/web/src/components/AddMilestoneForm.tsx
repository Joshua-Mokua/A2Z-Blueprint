// v10.544 Phase 1 — inline Add-Milestone form, shown inside an expanded initiative.
// POST /initiatives/{id}/milestones. Owner from StaffPicker (register name).
import { useState } from 'react';
import { StaffPicker } from '@/components/StaffPicker';
import { Badge } from '@/components/Badge';
import type { StaffMember } from '@/lib/api';
import { addMilestone } from '@/lib/api';
import { displayName } from '@/lib/names';

const inputCls =
  'w-full px-3 py-1.5 rounded-md border border-gray-300 text-sm focus:outline-none ' +
  'focus:border-brand-primary focus:ring-2 focus:ring-brand-primary/20';

export function AddMilestoneForm(
  { initiativeId, onAdded }: { initiativeId: string; onAdded: () => void },
) {
  const [open, setOpen] = useState(false);
  const [name, setName] = useState('');
  const [owner, setOwner] = useState<StaffMember | null>(null);
  const [start, setStart] = useState('');
  const [due, setDue] = useState('');
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const reset = () => { setName(''); setOwner(null); setStart(''); setDue(''); setErr(null); };
  const canSubmit = name.trim() && owner && due;

  const submit = async () => {
    if (!canSubmit || !owner) return;
    setBusy(true); setErr(null);
    try {
      const res = await addMilestone(initiativeId, {
        name: name.trim(),
        owner: owner.name,
        due_date: due,
        start_date: start || undefined,
      });
      if (res.status !== 'ok') throw new Error('Add failed');
      reset(); setOpen(false); onAdded();
    } catch (e) {
      setErr(e instanceof Error ? e.message : 'Add failed');
    } finally { setBusy(false); }
  };

  if (!open) {
    return (
      <button type="button" onClick={() => setOpen(true)}
        className="text-xs font-medium text-[var(--brand-primary,#0082BB)] hover:underline">
        + Add milestone
      </button>
    );
  }

  return (
    <div className="rounded-md border border-gray-200 p-3 bg-white space-y-2 mt-2">
      <input className={inputCls} placeholder="Milestone name"
        value={name} onChange={(e) => setName(e.target.value)} autoComplete="off" />
      <div>
        <div className="text-xs text-gray-500 mb-1">Owner</div>
        {owner ? (
          <div className="flex items-center gap-2">
            <Badge tone="success">{displayName(owner.name)}</Badge>
            <button type="button" onClick={() => setOwner(null)}
              className="text-xs text-gray-500 underline">change</button>
          </div>
        ) : <StaffPicker value={owner} onChange={setOwner} />}
      </div>
      <div className="flex gap-2">
        <label className="flex-1 text-xs text-gray-500">
          Start
          <input type="date" className={inputCls} value={start}
            onChange={(e) => setStart(e.target.value)} />
        </label>
        <label className="flex-1 text-xs text-gray-500">
          Due
          <input type="date" className={inputCls} value={due}
            onChange={(e) => setDue(e.target.value)} />
        </label>
      </div>
      {err && <div className="text-sm text-red-700">{err}</div>}
      <div className="flex justify-end gap-2">
        <button type="button" onClick={() => { reset(); setOpen(false); }}
          className="text-xs text-gray-500 underline">Cancel</button>
        <button type="button" disabled={!canSubmit || busy} onClick={() => void submit()}
          className="px-3 py-1 rounded-md text-xs font-medium text-white bg-[var(--brand-primary,#0082BB)] disabled:opacity-40 hover:opacity-90">
          {busy ? 'Adding…' : 'Add milestone'}
        </button>
      </div>
    </div>
  );
}
