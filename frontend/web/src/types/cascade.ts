// v10.533 Phase 5 Batch γ3b — TypeScript types for Target Cascade.
//
// Mirrors utils/api_cascade_routes.py (γ3a) return shapes. Defensive
// type strategy: explicit fields for the keys verified from
// target_cascade.json recon; index signatures for fields the backend
// may add. The React UI degrades gracefully — unknown fields are
// undefined, formatters return "—".
//
// Reasoning for the defensive types: the underlying CascadeManager
// methods (get_my_allocations, get_what_i_was_given) don't have
// return-type annotations in utils/core.py. I authored γ3a against
// what target_cascade.json itself looks like (sample seen during
// recon), so 80% of fields are known but the wrapping shape of the
// "given_to_me" projection could vary. If it does, the React UI
// shows "—" where the unknown field lives and we hotfix with the
// exact shape next batch.


// ── Bank target ──────────────────────────────────────────────────────────

export interface BankTarget {
  kpi:         string;
  period:      string;
  target:      number;
  buffer_pct:  number;
  /** Display hint derived by backend heuristic. */
  unit:        'currency' | 'percent' | 'count' | string;
}

export interface BankTargetsResponse {
  targets:  BankTarget[];
  count:    number;
  period:   string;
  source:   string;
}


// ── Allocation (one row in a cascade entry's allocations list) ───────────

export interface Allocation {
  to_code:  string;
  to_name:  string;
  amount:   number;
  [key: string]: unknown;
}


// ── Cascade entry (my outgoing) ──────────────────────────────────────────
// Shape verified from target_cascade.json recon — keyed as
// "{from_code}|{kpi}|{period}".

export interface CascadeEntry {
  from_code:       string;
  from_name:       string;
  kpi:             string;
  period:          string;
  total_target:    number;
  allocated_sum:   number;
  allocations:     Allocation[];
  [key: string]:   unknown;
}

export interface MyAllocationsResponse {
  /** Likely list of CascadeEntry; defensively typed since backend method has no return annotation. */
  allocations:  CascadeEntry[] | Record<string, CascadeEntry>;
  count:        number;
  staff_code:   string;
  period:       string;
  source:       string;
}


// ── Incoming allocation (what was given to me) ──────────────────────────
// Best-effort inferred shape: each item is one KPI that I was allocated
// from a single 'from' parent. We expect at least kpi + from + amount.

export interface IncomingAllocation {
  from_code?:     string;
  from_name?:     string;
  kpi?:           string;
  period?:        string;
  amount?:        number;
  /** Some implementations also project the source's total_target for context. */
  total_target?:  number;
  [key: string]:  unknown;
}

export interface GivenToMeResponse {
  allocations:  IncomingAllocation[];
  count:        number;
  staff_code:   string;
  staff_name:   string;
  period:       string;
  source:       string;
}


// ── Coverage analysis ────────────────────────────────────────────────────

export interface Coverage {
  total_target?:   number;
  allocated_sum?:  number;
  /** If backend returns gap or coverage_pct directly, we display them; else we compute. */
  gap?:            number;
  coverage_pct?:   number;
  allocations?:    Allocation[];
  [key: string]:   unknown;
}

export interface CoverageResponse {
  coverage:    Coverage;
  from_code:   string;
  kpi:         string;
  period:      string;
  source:      string;
}


// ── Helpers ──────────────────────────────────────────────────────────────

/**
 * Format a numeric target/allocation for display, branching on unit.
 * Currency abbreviates large values (B/M/K); percent appends %; count is plain.
 */
export function formatTargetValue(value: number | undefined | null, unit: string, symbol: string = 'KES'): string {
  if (value === null || value === undefined || !Number.isFinite(Number(value))) return '—';
  const n = Number(value);

  if (unit === 'percent') {
    return `${n.toLocaleString(undefined, { maximumFractionDigits: 2 })}%`;
  }
  if (unit === 'count') {
    return n.toLocaleString();
  }
  // currency (default)
  if (n === 0) return `${symbol} 0`;
  const abs = Math.abs(n);
  if (abs >= 1e9) return `${symbol} ${(n / 1e9).toFixed(2)}B`;
  if (abs >= 1e6) return `${symbol} ${(n / 1e6).toFixed(2)}M`;
  if (abs >= 1e3) return `${symbol} ${(n / 1e3).toFixed(0)}K`;
  return `${symbol} ${n.toLocaleString()}`;
}


/**
 * Coverage status from total_target + allocated_sum.
 * 'over' if allocated > 1.05 * target (5% buffer for rounding)
 * 'under' if allocated < 0.95 * target
 * 'balanced' otherwise
 * 'unknown' if either is missing
 */
export type CoverageStatus = 'over' | 'under' | 'balanced' | 'unknown';

export function coverageStatus(totalTarget: number | undefined, allocatedSum: number | undefined): CoverageStatus {
  if (totalTarget === undefined || allocatedSum === undefined || !Number.isFinite(totalTarget) || !Number.isFinite(allocatedSum)) {
    return 'unknown';
  }
  if (totalTarget === 0) return allocatedSum === 0 ? 'balanced' : 'over';
  const ratio = allocatedSum / totalTarget;
  if (ratio > 1.05) return 'over';
  if (ratio < 0.95) return 'under';
  return 'balanced';
}


/** Coverage-status to BadgeTone. */
export function coverageTone(status: CoverageStatus): 'success' | 'warning' | 'danger' | 'neutral' {
  if (status === 'balanced') return 'success';
  if (status === 'over')     return 'danger';
  if (status === 'under')    return 'warning';
  return 'neutral';
}


/** Human label for the coverage chip. */
export function coverageLabel(status: CoverageStatus, totalTarget: number | undefined, allocatedSum: number | undefined): string {
  if (status === 'unknown' || totalTarget === undefined || allocatedSum === undefined || totalTarget === 0) {
    return status;
  }
  const ratio = allocatedSum / totalTarget;
  const pct = (ratio * 100).toFixed(0);
  if (status === 'balanced') return `balanced (${pct}%)`;
  if (status === 'over')     return `over-allocated (${pct}%)`;
  if (status === 'under')    return `under-allocated (${pct}%)`;
  return status;
}


/**
 * Defensive coercion: my-allocations response may return a dict or a list.
 * Normalize to an array for the UI.
 */
export function normalizeCascadeEntries(
  data: CascadeEntry[] | Record<string, CascadeEntry> | undefined,
): CascadeEntry[] {
  if (!data) return [];
  if (Array.isArray(data)) return data;
  if (typeof data === 'object') return Object.values(data);
  return [];
}


// ── γ5a write surfaces ───────────────────────────────────────────────────

/** PUT /api/cascade/bank-targets — MD only. */
export interface SetBankTargetRequest {
  kpi:        string;
  period:     string;
  target:     number;
  buffer_pct: number;
}

export interface SetBankTargetResponse {
  ok:         boolean;
  kpi:        string;
  period:     string;
  target:     number;
  buffer_pct: number;
  source:     string;
}

/** PUT /api/cascade/allocations — caller must equal from_code. */
export interface AllocationRowIn {
  to_code: string;
  to_name?: string;
  amount: number;
}

export interface SetAllocationRequest {
  from_code:    string;
  kpi:          string;
  period:       string;
  total_target: number;
  allocations:  AllocationRowIn[];
}

export interface SetAllocationResponse {
  ok:     boolean;
  entry:  CascadeEntry;
  source: string;
}
