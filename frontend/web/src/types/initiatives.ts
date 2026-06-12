// v10.541 Phase 8 Batch γ4b — Strategic Initiatives types.
//
// Mirrors utils/api_initiatives_routes.py (γ4a) response shapes.
// Defensive types throughout: the underlying engine
// (CommandCentreStrategicInitiativesEngine) has no return-type annotations
// available from the recon, AND the data file doesn't exist yet so we have
// no live response samples. Both factors argue for tolerance.
//
// [key: string]: unknown index signatures let unknown fields pass through
// without TypeScript errors; the React UI displays known fields explicitly
// and ignores the rest until we know more.


// ── RAG / Phase / Risk catalogs from docstrings ─────────────────────────

export type InitiativeRag = 'GREEN' | 'AMBER' | 'RED';

export type InitiativePhase =
  | 'PLANNING'
  | 'IN_PROGRESS'
  | 'AT_RISK'
  | 'DELIVERED'
  | 'CANCELLED';

export type RiskLevel = 'LOW' | 'MEDIUM' | 'HIGH' | 'CRITICAL';

export type MilestoneState = 'PENDING' | 'IN_PROGRESS' | 'COMPLETED' | 'MISSED';


// ── Atom types ───────────────────────────────────────────────────────────

export interface InitiativeMilestone {
  id?:         string;
  name?:       string;
  due_date?:   string;
  state?:      MilestoneState | string;
  completed_at?: string;
  [key: string]: unknown;
}

export interface InitiativeBsc {
  perspective?:  string;
  kpi_id?:       string;
  [key: string]: unknown;
}

export interface InitiativeDependency {
  depends_on_id?: string;
  depends_on_name?: string;
  status?:        string;
  [key: string]: unknown;
}


// ── Detail (per-initiative status) ───────────────────────────────────────

export interface Initiative {
  id?:           string;
  name?:         string;
  description?:  string;
  owner?:        string;
  owner_code?:   string;
  rag?:          InitiativeRag | string;
  phase?:        InitiativePhase | string;
  risk_level?:   RiskLevel | string;
  start_date?:   string;
  end_date?:     string;
  budget?:       number;
  spend?:        number;
  milestones?:   InitiativeMilestone[];
  dependencies?: InitiativeDependency[];
  bsc_linkage?:  InitiativeBsc[];
  [key: string]: unknown;
}


// ── Portfolio summary (top dashboard card) ──────────────────────────────

export interface RagDistribution {
  GREEN?: number;
  AMBER?: number;
  RED?:   number;
  [key: string]: number | undefined;
}

export interface AtRiskItem {
  id?:   string;
  name?: string;
  rag?:  InitiativeRag | string;
  phase?: InitiativePhase | string;
  reason?: string;
  [key: string]: unknown;
}

export interface PortfolioSummary {
  total?:            number;
  rag_distribution?: RagDistribution;
  at_risk?:          AtRiskItem[];
  [key: string]:     unknown;
}


// ── API response envelopes (γ4a shape) ──────────────────────────────────

export interface PortfolioSummaryResponse {
  status:  'ok' | 'no_data' | string;
  summary: PortfolioSummary;
  source:  string;
  note?:   string;
}

export interface InitiativeDetailResponse {
  status:     'ok' | string;
  initiative: Initiative;
  source:     string;
}


// ── Helpers ──────────────────────────────────────────────────────────────

/** Map RAG/Phase strings to BadgeTone. */
export function ragTone(rag: string | undefined): 'success' | 'warning' | 'danger' | 'neutral' {
  if (!rag) return 'neutral';
  const r = String(rag).toUpperCase();
  if (r === 'GREEN')  return 'success';
  if (r === 'AMBER')  return 'warning';
  if (r === 'RED')    return 'danger';
  return 'neutral';
}

export function phaseTone(phase: string | undefined): 'success' | 'warning' | 'danger' | 'info' | 'neutral' {
  if (!phase) return 'neutral';
  const p = String(phase).toUpperCase();
  if (p === 'DELIVERED')   return 'success';
  if (p === 'IN_PROGRESS') return 'info';
  if (p === 'AT_RISK')     return 'warning';
  if (p === 'CANCELLED')   return 'danger';
  if (p === 'PLANNING')    return 'neutral';
  return 'neutral';
}

export function riskTone(risk: string | undefined): 'success' | 'warning' | 'danger' | 'neutral' {
  if (!risk) return 'neutral';
  const r = String(risk).toUpperCase();
  if (r === 'LOW')      return 'success';
  if (r === 'MEDIUM')   return 'warning';
  if (r === 'HIGH')     return 'danger';
  if (r === 'CRITICAL') return 'danger';
  return 'neutral';
}

export function milestoneStateTone(state: string | undefined): 'success' | 'warning' | 'danger' | 'info' | 'neutral' {
  if (!state) return 'neutral';
  const s = String(state).toUpperCase();
  if (s === 'COMPLETED')   return 'success';
  if (s === 'IN_PROGRESS') return 'info';
  if (s === 'PENDING')     return 'neutral';
  if (s === 'MISSED')      return 'danger';
  return 'neutral';
}

/**
 * Format a numeric currency value with K/M/B abbreviation.
 * Returns "—" for null/undefined/non-finite values.
 */
export function formatBudget(value: number | undefined | null, symbol: string = 'KES'): string {
  if (value === null || value === undefined || !Number.isFinite(Number(value))) return '—';
  const n = Number(value);
  if (n === 0) return `${symbol} 0`;
  const abs = Math.abs(n);
  if (abs >= 1e9) return `${symbol} ${(n / 1e9).toFixed(2)}B`;
  if (abs >= 1e6) return `${symbol} ${(n / 1e6).toFixed(2)}M`;
  if (abs >= 1e3) return `${symbol} ${(n / 1e3).toFixed(0)}K`;
  return `${symbol} ${n.toLocaleString()}`;
}
