// v10.545 Phase P Batch P4 — MD/CEO dashboard types.
//
// Mirrors the /api/dashboard/md response composed in utils/api.py
// (md_dashboard). The endpoint aggregates five domain summaries into a
// single executive payload. All numeric; defensive defaults are applied
// server-side (every field falls back to 0), so the client can render
// without optional-chaining gymnastics.

export interface MdDashboardResponse {
  bsc: {
    /** Bank-wide average BSC score (0–100). */
    overall_avg: number;
    total_staff: number;
  };
  pipeline: {
    total_deals: number;
    /** Open weighted/absolute pipeline value (currency units). */
    pipeline_value: number;
    /** Manager-assured (validated) pipeline value — the management anchor. */
    validated_value?: number;
    /** Value still pending validation/assurance. */
    pending_value?: number;
    /** Count of deals pending validation (manager scope). */
    pending_validation?: number;
    /** Closed-won value. */
    won_value: number;
  };
  credit: {
    total_accounts: number;
    /** Outstanding loan book, in billions. */
    outstanding_bn: number;
    npl_ratio_pct: number;
  };
  aml: {
    open_alerts: number;
    high_risk: number;
  };
  org: {
    total_staff: number;
    departments: number;
  };
  /** ISO timestamp the server composed this snapshot. */
  generated_at: string;
}
