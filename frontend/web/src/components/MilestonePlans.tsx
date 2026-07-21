// v10.542 — MilestonePlans: the canonical initiatives with their milestone plans.
//
// This is the surface that was missing: execute_initiatives.json carries milestones
// (owner, due date, status) and a gate that feeds the BSC initiative score. Rendered
// as an expandable list. Additive — dropped onto the existing Initiatives page below
// the RAG rollup, using the same Card/Badge primitives.

import { useState } from 'react';
import { Card } from '@/components/Card';
import { Badge } from '@/components/Badge';
import { Skeleton } from '@/components/Skeleton';
import { useExecuteInitiatives } from '@/hooks/useExecuteInitiatives';
import {
  GATE_LABEL,
  milestoneTone,
  type ExecuteInitiative,
} from '@/types/executeInitiatives';

function GateBar({ score }: { score: number }) {
  const pct = Math.max(0, Math.min(100, score));
  return (
    <div className="w-full h-2 rounded-full bg-gray-100 overflow-hidden">
      <div
        className="h-full rounded-full bg-[var(--brand-primary,#0082BB)]"
        style={{ width: `${pct}%` }}
      />
    </div>
  );
}

function InitiativeRow({ init }: { init: ExecuteInitiative }) {
  const [open, setOpen] = useState(false);
  const ms = Array.isArray(init.milestones) ? init.milestones : [];
  const total = init.milestone_total ?? ms.length;
  const done = init.milestone_complete ?? 0;
  const gate = init.gate ?? 'G0';
  const score = init.gate_score ?? 0;

  return (
    <div className="border-b border-gray-100 last:border-0">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="w-full text-left px-6 py-4 hover:bg-gray-50 focus:outline-none"
      >
        <div className="flex items-center justify-between gap-4">
          <div className="min-w-0">
            <div className="font-medium text-gray-900 truncate">{init.name}</div>
            <div className="text-xs text-gray-500 truncate">
              {init.io ? `Owner: ${init.io}` : 'Unassigned'}
              {init.workstream ? ` · ${init.workstream}` : ''}
            </div>
          </div>
          <div className="flex items-center gap-3 shrink-0">
            <Badge tone="neutral">{GATE_LABEL[gate] ?? gate}</Badge>
            <span className="text-xs text-gray-500">{done}/{total} done</span>
            <span className="text-gray-400 text-xs">{open ? '▾' : '▸'}</span>
          </div>
        </div>
        <div className="mt-2 flex items-center gap-3">
          <GateBar score={score} />
          <span className="text-xs text-gray-500 shrink-0">{score}%</span>
        </div>
      </button>

      {open && (
        <div className="px-6 pb-4">
          {init.objective && (
            <p className="text-xs text-gray-600 mb-3">{init.objective}</p>
          )}
          {ms.length === 0 ? (
            <div className="text-xs text-gray-400 italic">No milestones yet.</div>
          ) : (
            <ol className="space-y-1.5">
              {ms.map((m, i) => (
                <li
                  key={m.id ?? i}
                  className="flex items-center justify-between gap-3 text-sm"
                >
                  <span className="text-gray-800 truncate">
                    <span className="text-gray-400 mr-2">{i + 1}.</span>
                    {m.name ?? 'Untitled milestone'}
                  </span>
                  <span className="flex items-center gap-3 shrink-0">
                    {m.due_date && (
                      <span className="text-xs text-gray-500">{m.due_date}</span>
                    )}
                    <Badge tone={milestoneTone(m.status)}>
                      {m.status ?? 'Pending'}
                    </Badge>
                  </span>
                </li>
              ))}
            </ol>
          )}
        </div>
      )}
    </div>
  );
}

export function MilestonePlans() {
  const { initiatives, loading, error, refetch } = useExecuteInitiatives('All');

  // Sort: most-progressed first, so live battles surface above G0 placeholders.
  const sorted = [...initiatives].sort(
    (a, b) => (b.gate_score ?? 0) - (a.gate_score ?? 0),
  );

  return (
    <Card>
      <Card.Header>
        <h2 className="text-base font-semibold text-gray-900">
          Milestone Plans ({initiatives.length})
        </h2>
        <span className="text-xs text-gray-500">
          Execution initiatives with milestone plans and gate progress · feeds the BSC
        </span>
      </Card.Header>
      <Card.Body className="p-0">
        {loading && (
          <div className="px-6 py-4 space-y-2">
            <Skeleton className="h-6 w-full" />
            <Skeleton className="h-6 w-2/3" />
          </div>
        )}
        {error && !loading && (
          <div className="px-6 py-4 text-sm text-red-700">
            {error}
            <button
              type="button"
              onClick={() => void refetch()}
              className="ml-3 underline text-gray-600"
            >
              Retry
            </button>
          </div>
        )}
        {!loading && !error && sorted.length === 0 && (
          <div className="px-6 py-4 text-sm text-gray-500">
            No execution initiatives registered yet.
          </div>
        )}
        {!loading && !error && sorted.map((init) => (
          <InitiativeRow key={init.id} init={init} />
        ))}
      </Card.Body>
    </Card>
  );
}
