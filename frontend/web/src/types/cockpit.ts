// v10.551 Phase P Batch P5 — credit cockpit types.
//
// Mirrors /api/cockpit/credit/open-work (utils/cockpit_read.py::credit_open_work).
// Bank-wide credit landscape: applications by lane + IFRS9 stage distribution.

export interface CreditOpenWork {
  applications_total: number;
  applications_open: number;
  /** swim_lane -> application count */
  applications_by_stage: Record<string, number>;
  ifrs9_total: number;
  ifrs9_stage1: number;   // performing
  ifrs9_stage2: number;   // significant increase in credit risk (watch)
  ifrs9_stage3: number;   // non-performing (NPL)
  npl_pct: number | null; // null when no IFRS9 records / no outstanding
  watchlist_count: number;
  as_at: string;          // ISO timestamp of the read
}
