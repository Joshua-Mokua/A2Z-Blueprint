// Types for /api/credit/analytics and /api/credit/drill.

export interface CreditTotals {
  outstanding:     number;
  accounts:        number;
  npl_outstanding: number;
  npl_count:       number;
  npl_ratio_pct:   number;
}

export interface CreditClassBreakdown  { classification: string; outstanding: number; accounts: number; npl_outstanding: number; npl_ratio_pct: number }
export interface CreditRegionBreakdown { region: string;         outstanding: number; accounts: number; npl_outstanding: number; npl_ratio_pct: number }
export interface CreditBranchBreakdown { branch: string;         outstanding: number; accounts: number; npl_outstanding: number; npl_ratio_pct: number }
export interface CreditRmBreakdown     { rm: string;             outstanding: number; accounts: number; npl_outstanding: number; npl_ratio_pct: number }

export interface CreditAnalyticsResponse {
  totals:     CreditTotals;
  by_class:   CreditClassBreakdown[];
  by_region:  CreditRegionBreakdown[];
  by_branch:  CreditBranchBreakdown[];
  by_rm:      CreditRmBreakdown[];
}

export interface CreditAccount {
  account_number:  string;
  cif:             string;
  classification:  string;
  outstanding:     number;
  npl_days:        number;
  branch_name:     string;
  rm_name:         string;
  collateral_type: string;
  stage:           string;
}

export interface CreditDrillResponse {
  region:    string | null;
  branch:    string | null;
  rm:        string | null;
  by_branch: CreditBranchBreakdown[];
  by_rm:     CreditRmBreakdown[];
  accounts:  CreditAccount[];
  totals:    CreditTotals;
}
