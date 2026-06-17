// Executive exceptions strip — types.
// Mirrors GET /api/dashboard/exceptions (read-only, scoped, drill-linked).

export type ExceptionSeverity = 'danger' | 'warning' | 'info';

export interface ExceptionItem {
  id:       string;
  severity: ExceptionSeverity;
  title:    string;
  detail:   string;
  value:    string;
  /** Drill route, e.g. '/credit-analytics'. */
  link:     string;
}

export interface ExceptionsResponse {
  exceptions:   ExceptionItem[];
  count:        number;
  generated_at: string;
}
