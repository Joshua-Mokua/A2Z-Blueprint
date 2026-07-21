// v10.542 — canonical execute-initiatives (milestone-bearing) types.
// Distinct from types/initiatives.ts (RAG portfolio). Mirrors GET /api/initiatives,
// which reads execute_initiatives.json via core.ExecuteManager — the store that
// carries milestone plans and feeds the BSC initiative score.

export interface ExecuteMilestone {
  id?: string; name?: string; owner?: string; due_date?: string;
  status?: string; confirmed?: boolean; [key: string]: unknown;
}

export interface ExecuteInitiative {
  id: string; name: string; objective?: string; workstream?: string;
  io?: string; gate?: string; gate_score?: number; status?: string;
  milestone_total?: number; milestone_complete?: number;
  milestones?: ExecuteMilestone[]; [key: string]: unknown;
}

export interface ExecuteInitiativesResponse {
  status: string; count: number; initiatives: ExecuteInitiative[]; note?: string;
}

export const GATE_LABEL: Record<string, string> = {
  G0: 'G0 · Concept', G1: 'G1 · Define', G2: 'G2 · Plan',
  G3: 'G3 · Build', G4: 'G4 · Pilot', G5: 'G5 · Delivered',
};

export function milestoneTone(status?: string): 'success' | 'warning' | 'danger' | 'neutral' {
  const s = (status || '').toLowerCase();
  if (s === 'complete' || s === 'completed') return 'success';
  if (s === 'in progress' || s === 'in_progress' || s === 'started') return 'warning';
  if (s === 'missed' || s === 'blocked' || s === 'overdue') return 'danger';
  return 'neutral';
}
