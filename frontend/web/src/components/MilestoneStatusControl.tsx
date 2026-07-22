// v10.545 Phase 2 — per-milestone status control. Cycles Not Started -> Active ->
// Complete via PATCH. Marking Complete moves the initiative's done-count / % and feeds
// the gate score to the BSC.
import { useState } from 'react';
import { setMilestoneStatus } from '@/lib/api';

const CYCLE: Record<string, string> = {
  'Not Started': 'Active',
  'Active': 'Complete',
  'Complete': 'Not Started',
};
const LABEL: Record<string, string> = {
  'Not Started': 'Not Started',
  'Active': 'In Progress',
  'Complete': 'Complete',
};
const TONE: Record<string, string> = {
  'Not Started': 'text-gray-500 bg-gray-100',
  'Active': 'text-amber-800 bg-amber-100',
  'Complete': 'text-green-800 bg-green-100',
};

export function MilestoneStatusControl(
  { initiativeId, msId, status, onChanged }:
  { initiativeId: string; msId: string; status?: string; onChanged: () => void },
) {
  const [busy, setBusy] = useState(false);
  const cur = status && status in CYCLE ? status : 'Not Started';

  const advance = async () => {
    const next = CYCLE[cur];
    setBusy(true);
    try {
      await setMilestoneStatus(initiativeId, msId, {
        status: next,
        started: next === 'Active' ? true : undefined,
      });
      onChanged();
    } catch {
      // swallow — onChanged refetch will reflect true state
    } finally {
      setBusy(false);
    }
  };

  return (
    <button
      type="button"
      onClick={() => void advance()}
      disabled={busy}
      title="Click to advance status"
      className={`px-2 py-0.5 rounded-full text-xs font-medium ${TONE[cur]} disabled:opacity-50 hover:ring-2 hover:ring-offset-1 hover:ring-gray-300`}
    >
      {busy ? '…' : LABEL[cur]}
    </button>
  );
}
