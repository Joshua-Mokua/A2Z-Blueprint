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

export interface BscPillar { id: string; name: string; color: string }

export interface BscPillars {
  pillars:        BscPillar[];
  pillar_weights: Record<string, number>;
}

export const fetchBscTeam    = () => getJson<BscTeam>('/api/v1/bsc/team');
export const fetchBscPillars = () => getJson<BscPillars>('/api/v1/bsc/pillars');
export const fetchBscScorecard = (staffCode: string) =>
  getJson<BscScorecard>(`/api/v1/bsc/scorecard/${encodeURIComponent(staffCode)}`);

/** Percent for display. Weights are stored as fractions of the whole scorecard. */
export const pct = (w: number | null | undefined, dp = 1): string =>
  w === null || w === undefined ? '—' : `${(w * 100).toFixed(dp)}%`;
