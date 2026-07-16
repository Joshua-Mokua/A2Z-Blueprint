// Balanced Scorecard — types + fetchers for /api/v1/bsc.
//
// These serve the scorecard DEFINITION (which KPIs a role is measured on, in which
// performance area, at what weight, plus the dated objectives). The older
// /api/bsc/summary returns computed scores and is unrelated.

import { getJson } from '@/lib/api';

export interface BscKpi {
  id:                 string;
  name:               string;
  area:               string;
  unit:               string;
  direction:          string;
  /** Effective share of the whole scorecard: area_weight x within_area_weight. */
  weight:             number;
  area_weight:        number | null;
  within_area_weight: number | null;
  defined:            boolean;
  description:        string;
  /** From compute_staff_scorecard. null where no actual or target is configured. */
  actual:             number | null;
  target:             number | null;
  target_source:      string;   // bank_fixed | cascaded | role_default | missing
  achievement_pct:    number | null;
  score:              number | null;   // 1-5
}

export interface BscObjective {
  text:               string;
  area:               string;
  due:                string | null;
  /** null when the source scorecard gave no usable weight. */
  weight:             number | null;
  within_area_weight: number | null;
}

export interface BscStaff {
  staff_code:   string;
  full_name:    string;
  display_name: string;
  role:         string;
  unit:         string;
  department:   string;
}

export interface BscScorecard {
  role:                    string;
  areas:                   Record<string, number> | null;
  kpis:                    BscKpi[];
  objectives:              BscObjective[];
  weights_complete:        boolean;
  weights_pending_reason:  string | null;
  source_ambiguous:        boolean;
  source:                  string | null;
  total_weight:            number;
  has_scorecard:           boolean;
  staff?:                  BscStaff;
  period:                  string;
  final_score:             number | null;
  scored_count:            number;
}

export interface BscTeamMember extends BscStaff {
  is_direct_report: boolean;
  has_scorecard:    boolean;
}

export interface BscTeam {
  me:                  BscTeamMember;
  reports:             BscTeamMember[];
  direct_report_count: number;
  total_visible:       number;
}

export interface BscDepartment {
  department:          string;
  people:              BscTeamMember[];
  head:                BscTeamMember | null;
  direct_report_count: number;
  scorecard_count:     number;
  total:               number;
}

export interface BscDepartments {
  me:               BscTeamMember;
  departments:      BscDepartment[];
  department_count: number;
  total_visible:    number;
}

export interface BscPillar { id: string; name: string; color: string }

export interface BscPillars {
  pillars:        BscPillar[];
  pillar_weights: Record<string, number>;
}

// getJson prepends API_BASE ('/api'), so paths here start AFTER it: '/v1/bsc/...'
// produces /api/v1/bsc/... . Passing the full '/api/v1/bsc/...' yields
// /api/api/v1/bsc/... and a 404 that names the path argument, not the URL fetched.
export const fetchBscTeam    = () => getJson<BscTeam>('/v1/bsc/team');
export const fetchBscDepartments = () => getJson<BscDepartments>('/v1/bsc/departments');
export const fetchBscPillars = () => getJson<BscPillars>('/v1/bsc/pillars');
export const fetchBscScorecard = (staffCode: string) =>
  getJson<BscScorecard>(`/v1/bsc/scorecard/${encodeURIComponent(staffCode)}`);

/** Percent for display. Weights are stored as fractions of the whole scorecard. */
export const pct = (w: number | null | undefined, dp = 1): string =>
  w === null || w === undefined ? '—' : `${(w * 100).toFixed(dp)}%`;

/** 1-5 score to a RAG tone — the bank's own bands: 4+ exceeds, under 2.5 at risk. */
export function scoreTone(score: number | null | undefined):
    'success' | 'warning' | 'danger' | 'neutral' {
  if (score === null || score === undefined) return 'neutral';
  if (score >= 4) return 'success';
  if (score >= 2.5) return 'warning';
  return 'danger';
}

/** Width of the achievement bar: 120% achievement fills it, since 120 scores a 5. */
export const achBar = (a: number | null | undefined): number =>
  a === null || a === undefined ? 0 : Math.max(0, Math.min(100, a / 1.2));

export const fmtNum = (v: number | null | undefined): string => {
  if (v === null || v === undefined) return '—';
  const abs = Math.abs(v);
  if (abs >= 1_000_000) return `${(v / 1_000_000).toFixed(1)}M`;
  if (abs >= 1_000) return `${(v / 1_000).toFixed(1)}K`;
  return Number.isInteger(v) ? String(v) : v.toFixed(1);
};
