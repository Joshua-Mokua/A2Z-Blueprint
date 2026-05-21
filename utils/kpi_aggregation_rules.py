"""utils/kpi_aggregation_rules.py — v10.108 Integration Layer.

Registry of aggregation rules that read operational tables and produce
per-staff KPI actuals. Each rule declares:

    - kpi_id       : library KPI id/code/alias the rule produces an
                     actual for (the autofit pipeline normalises this
                     through kpi_ownership._normalise_kpi_key).
    - source_table : operational table the rule reads from. Must match
                     an entry in TABLE_USE_DB / data/<table>.json.
    - pattern      : one of the 6 archetypes below. Determines the
                     aggregation maths.
    - **pattern-specific fields** (see ARCHETYPES).

The 6 archetypes cover essentially every operational KPI:

    COUNT          Number of records satisfying a predicate.
                   e.g. "Number of new SME loans this month"
                   fields: predicate (callable), [period_field]

    SUM            Sum of a numeric column where predicate holds.
                   e.g. "Total disbursement value, retail"
                   fields: predicate, value_field, [period_field]

    PERCENTAGE     numerator_pred / denominator_pred * 100.
                   e.g. "% loan applications closed within SLA"
                   fields: numerator_pred, denominator_pred, [period_field]

    TAT_DAYS       Mean of (end_field - start_field) in days.
                   e.g. "Mean Loan Processing TAT"
                   fields: start_field, end_field, predicate, [period_field]

    RATIO          Sum(numerator_field) / Sum(denominator_field).
                   e.g. "Recovery Rate = Recovered / NPL"
                   fields: numerator_field, denominator_field, predicate

    BOOL_FRACTION  Fraction of records where bool_field is truthy.
                   e.g. "% staff with consent capture done"
                   fields: bool_field, predicate, [period_field]

Each rule also declares ``staff_field`` — the per-table staff identifier.
Resolved through utils/staff_field_resolver.STAFF_FIELD_BY_TABLE when
unset; declaring it in the rule is for cases where one table has
multiple staff identifiers (e.g. an opportunity's owner and supervisor
may both fire actuals for different KPIs).

This module ships the registry mechanism + 4 concrete reference rules
covering 4 of the 6 patterns, demonstrating the contract end-to-end.
v10.109+ batches add the remaining ~83 operational rules until G143
flips from informational-pass to strict and reports 100% coverage.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Callable, Optional


# ─── Pattern names ──────────────────────────────────────────────────────

PATTERN_COUNT = "COUNT"
PATTERN_SUM = "SUM"
PATTERN_PERCENTAGE = "PERCENTAGE"
PATTERN_TAT_DAYS = "TAT_DAYS"
PATTERN_RATIO = "RATIO"
PATTERN_BOOL_FRACTION = "BOOL_FRACTION"
# v10.115: pre-computed TAT field. Use when the source table has a
# `tat_days` (or similar) column already calculated by the upstream
# system, rather than separate start/end date columns. Mean of the
# numeric `value_field` values where predicate is true. Operationally
# different from SUM (which gives the total) — semantic is mean.
# Banks where FLEXCUBE / loan workflow systems pre-compute TAT in
# the source record use this pattern; banks that store start/end
# dates use TAT_DAYS.
PATTERN_TAT_FIELD = "TAT_FIELD"
# v10.118: alias for TAT_FIELD with broader naming. The pattern's
# actual semantic ("mean of numeric value_field where predicate is
# true, drops non-numeric silently") generalises to any per-staff
# numeric average — see K102 Strategy Execution Score (mean
# completion_pct per owner) for the canonical non-TAT use case.
# Both names resolve to the same dispatch logic; MEAN_FIELD is the
# canonical name from v10.118 onward, TAT_FIELD is preserved as an
# alias for backward compatibility with v10.115-v10.117 rules.
PATTERN_MEAN_FIELD = "MEAN_FIELD"

ALL_PATTERNS = (
    PATTERN_COUNT,
    PATTERN_SUM,
    PATTERN_PERCENTAGE,
    PATTERN_TAT_DAYS,
    PATTERN_RATIO,
    PATTERN_BOOL_FRACTION,
    PATTERN_TAT_FIELD,
    PATTERN_MEAN_FIELD,
)


def _is_mean_pattern(p: str) -> bool:
    """v10.118: TAT_FIELD and MEAN_FIELD are aliases for the same
    mean-of-numeric-value-field semantic. This helper centralises
    the dispatch check so adding a third alias (or renaming) is a
    one-line change."""
    return p in (PATTERN_TAT_FIELD, PATTERN_MEAN_FIELD)


# ─── Rule dataclass ─────────────────────────────────────────────────────

@dataclass
class AggregationRule:
    """A single (kpi, table, pattern) registration. Everything needed
    to compute an actual for the KPI from the table.

    ``staff_field`` is None to defer to STAFF_FIELD_BY_TABLE; set it to
    override (rare). All ``*_pred`` fields are predicates: callable
    taking a row dict and returning bool.

    ``period_field`` is the row attribute holding a date or YYYY-MM
    string used to filter to the requested period; None means the rule
    aggregates over all rows in the table (rare — only for snapshot KPIs
    like 'current_npl_count').
    """
    kpi_id: str
    source_table: str
    pattern: str
    description: str = ""

    # Pattern-specific fields (each pattern uses a subset)
    predicate: Optional[Callable[[dict], bool]] = None
    numerator_pred: Optional[Callable[[dict], bool]] = None
    denominator_pred: Optional[Callable[[dict], bool]] = None
    value_field: Optional[str] = None
    start_field: Optional[str] = None
    end_field: Optional[str] = None
    numerator_field: Optional[str] = None
    denominator_field: Optional[str] = None
    bool_field: Optional[str] = None

    period_field: Optional[str] = None
    staff_field: Optional[str] = None
    # v10.109: callable that extracts the staff identifier from a row.
    # When set, takes precedence over both staff_field (rule-level) and
    # STAFF_FIELD_BY_TABLE (table-level). Use for nested fields like
    # `legal_officer.code` or computed identifiers (e.g., a username
    # that needs lower-casing before BSC submission).
    staff_field_extractor: Optional[Callable[[dict], Optional[str]]] = None

    # v10.110: when True, BOOL_FRACTION and PERCENTAGE rules return
    # (100 - x). Use when the bool_field/numerator_pred captures the
    # OPPOSITE of what the KPI semantically rewards. Example: a KPI
    # "% Compliance Score" (direction:higher) wired to the bool field
    # `compliance_flag` (where True = problem) needs invert:true so
    # the rule emits "% clean" matching the library direction.
    # Has no effect on COUNT/SUM/TAT_DAYS/RATIO patterns.
    invert: bool = False

    # Output coercion
    decimals: int = 2

    def validate(self) -> list[str]:
        """Return a list of validation errors (empty list = valid)."""
        errs = []
        if not self.kpi_id:
            errs.append("kpi_id is required")
        if not self.source_table:
            errs.append("source_table is required")
        if self.pattern not in ALL_PATTERNS:
            errs.append(
                f"pattern '{self.pattern}' not in {ALL_PATTERNS}")

        # Per-pattern requirements
        p = self.pattern
        if p == PATTERN_COUNT and self.predicate is None:
            errs.append("COUNT requires predicate")
        elif p == PATTERN_SUM:
            if self.predicate is None:
                errs.append("SUM requires predicate")
            if not self.value_field:
                errs.append("SUM requires value_field")
        elif p == PATTERN_PERCENTAGE:
            if self.numerator_pred is None or self.denominator_pred is None:
                errs.append(
                    "PERCENTAGE requires numerator_pred + denominator_pred")
        elif p == PATTERN_TAT_DAYS:
            if not self.start_field or not self.end_field:
                errs.append("TAT_DAYS requires start_field + end_field")
            if self.predicate is None:
                errs.append("TAT_DAYS requires predicate")
        elif p == PATTERN_RATIO:
            if not self.numerator_field or not self.denominator_field:
                errs.append(
                    "RATIO requires numerator_field + denominator_field")
        elif p == PATTERN_BOOL_FRACTION:
            if not self.bool_field:
                errs.append("BOOL_FRACTION requires bool_field")
        elif _is_mean_pattern(p):
            # v10.115 introduced TAT_FIELD; v10.118 added MEAN_FIELD
            # alias. Same validation rules apply to both.
            if not self.value_field:
                errs.append(
                    f"{p} requires value_field (the pre-computed "
                    f"days/hours/numeric column)")
            if self.predicate is None:
                errs.append(f"{p} requires predicate")
        return errs


# ─── Pattern computation engine ─────────────────────────────────────────

def _to_dt(v) -> Optional[datetime]:
    """Coerce a date-like value to datetime, or None on failure."""
    if v is None or v == "":
        return None
    if isinstance(v, datetime):
        return v
    if isinstance(v, str):
        for fmt in (
                "%Y-%m-%d", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M:%S.%f",
                "%Y/%m/%d", "%d/%m/%Y", "%d-%m-%Y"):
            try:
                return datetime.strptime(v[:len(fmt) + 6], fmt)
            except ValueError:
                continue
    return None


def _row_in_period(row: dict, period_field: Optional[str],
                   period: str) -> bool:
    """True if the row's period_field falls within `period` (YYYY-MM
    format expected). If period_field is None, always True.

    Period format is the bsc_engine canonical YYYY-MM. The row's
    period_field can be a full date or YYYY-MM string."""
    if not period_field:
        return True
    if not period:
        return True
    raw = row.get(period_field)
    if raw is None:
        return False
    raw_s = str(raw)
    # Direct YYYY-MM prefix match handles "2026-04", "2026-04-15", and
    # "2026-04-15T10:30:00" alike.
    return raw_s.startswith(period)


def compute_rule(rule: AggregationRule, rows: list[dict],
                 period: str, staff_field: str) -> dict:
    """Apply `rule` to `rows`, grouping by `staff_field`, returning
    {staff_code: actual_value}.

    Rows that fail period filtering or lack a staff_field value are
    skipped silently (Rule 6 honesty: never fabricate, never silently
    treat as zero — but operational tables routinely contain rows that
    aren't relevant to a given period, so skipping is correct).
    """
    # Group to per-staff lists first
    by_staff: dict[str, list[dict]] = {}
    extractor = rule.staff_field_extractor
    for row in rows:
        if not isinstance(row, dict):
            continue
        if not _row_in_period(row, rule.period_field, period):
            continue
        # v10.109: per-rule extractor wins over the table-level
        # staff_field. Used for nested fields (legal_officer.code) and
        # computed identifiers.
        if extractor is not None:
            try:
                sc = extractor(row)
            except Exception:
                continue
        else:
            sc = row.get(staff_field)
        if not sc:
            continue
        sc = str(sc).strip()
        by_staff.setdefault(sc, []).append(row)

    # Apply pattern per staff
    out: dict[str, float] = {}
    for sc, staff_rows in by_staff.items():
        try:
            val = _apply_pattern(rule, staff_rows)
        except Exception:
            # Defensive: a single staff's bad data should not poison
            # the whole batch. Skip, the autofit caller will log.
            continue
        if val is None:
            continue
        out[sc] = round(float(val), rule.decimals)
    return out


def _apply_pattern(rule: AggregationRule, rows: list[dict]):
    """Compute the rule's aggregation against a per-staff row list.
    Returns None when the pattern can't produce a meaningful number
    (e.g. divide-by-zero in PERCENTAGE/RATIO/BOOL_FRACTION/TAT_DAYS).
    """
    p = rule.pattern

    if p == PATTERN_COUNT:
        n = sum(1 for r in rows if rule.predicate(r))
        # Drop staff with zero qualifying rows. They didn't meaningfully
        # participate; submitting a 0 actual would pollute the BSC with
        # noise from staff who appeared in the table by coincidence.
        return n if n > 0 else None

    if p == PATTERN_SUM:
        any_qualifying = False
        total = 0.0
        for r in rows:
            if not rule.predicate(r):
                continue
            any_qualifying = True
            v = r.get(rule.value_field)
            try:
                total += float(v) if v is not None else 0.0
            except (TypeError, ValueError):
                continue
        # If no rows qualified (predicate filtered everything), drop
        # silently — same reasoning as COUNT above.
        return total if any_qualifying else None

    if p == PATTERN_PERCENTAGE:
        num = sum(1 for r in rows if rule.numerator_pred(r))
        den = sum(1 for r in rows if rule.denominator_pred(r))
        if den == 0:
            return None
        result = num / den * 100.0
        # v10.110 invert flag — semantic mirror for KPIs whose
        # numerator captures the opposite of what's rewarded.
        return (100.0 - result) if rule.invert else result

    if p == PATTERN_TAT_DAYS:
        deltas: list[float] = []
        for r in rows:
            if not rule.predicate(r):
                continue
            start = _to_dt(r.get(rule.start_field))
            end = _to_dt(r.get(rule.end_field))
            if start is None or end is None:
                continue
            deltas.append((end - start).total_seconds() / 86400.0)
        if not deltas:
            return None
        return sum(deltas) / len(deltas)

    if p == PATTERN_RATIO:
        num = 0.0
        den = 0.0
        for r in rows:
            if rule.predicate is not None and not rule.predicate(r):
                continue
            try:
                num += float(r.get(rule.numerator_field) or 0)
            except (TypeError, ValueError):
                pass
            try:
                den += float(r.get(rule.denominator_field) or 0)
            except (TypeError, ValueError):
                pass
        if den == 0:
            return None
        return num / den

    if p == PATTERN_BOOL_FRACTION:
        applicable = [r for r in rows
                      if rule.predicate is None or rule.predicate(r)]
        if not applicable:
            return None
        truthy = sum(1 for r in applicable if r.get(rule.bool_field))
        result = truthy / len(applicable) * 100.0
        # v10.110 invert flag — semantic mirror.
        return (100.0 - result) if rule.invert else result

    if _is_mean_pattern(p):
        # v10.115 TAT_FIELD + v10.118 MEAN_FIELD: mean of pre-computed
        # numeric values where predicate true. Coerces to float, drops
        # non-numeric entries silently. Empty set → None (caller drops,
        # no actual submitted).
        values: list[float] = []
        for r in rows:
            if rule.predicate is None or rule.predicate(r):
                v = r.get(rule.value_field)
                if isinstance(v, (int, float)):
                    values.append(float(v))
        if not values:
            return None
        return sum(values) / len(values)

    return None


# ─── The Registry ──────────────────────────────────────────────────────

REGISTRY: list[AggregationRule] = []


def register(rule: AggregationRule) -> None:
    """Add a rule to the registry. Rejects rules that fail validation."""
    errs = rule.validate()
    if errs:
        raise ValueError(
            f"Invalid rule for {rule.kpi_id}: {'; '.join(errs)}")
    REGISTRY.append(rule)


def rules_for_table(table: str) -> list[AggregationRule]:
    """All registered rules whose source_table matches `table`."""
    return [r for r in REGISTRY if r.source_table == table]


def kpis_with_aggregator() -> set[str]:
    """KPI ids registered in any rule (used by audit gate G143)."""
    return {r.kpi_id for r in REGISTRY}


# ─── v10.110 Rule loading from data/aggregation_rules.json ────────────
#
# v10.108-v10.109 hard-coded rule definitions in this file as register()
# calls. v10.110 externalizes them to JSON so admins can adjust per-bank
# without editing Python. The 6 patterns + compute_rule logic stay here
# (universal). The data moves out (configurable).
#
# If the JSON load fails, REGISTRY remains empty and the operational
# autofit pathway becomes a no-op — the CBS pathway and the rest of the
# platform are unaffected. Failure mode is logged via the loader.

def _bootstrap_rules_from_json():
    """Module-import-time bootstrap. Idempotent: if rules are already
    loaded (REGISTRY non-empty) does nothing. Set A2Z_SKIP_RULE_BOOTSTRAP
    env var to skip — useful for tests that want a clean registry."""
    import os
    if os.environ.get("A2Z_SKIP_RULE_BOOTSTRAP"):
        return
    if REGISTRY:
        return
    try:
        from utils.aggregation_rules_loader import load_rules_from_json
        result = load_rules_from_json(clear_registry=False)
        if result.get("errors"):
            import logging
            logging.getLogger(__name__).warning(
                f"v10.110 rule loader: {len(result['errors'])} errors; "
                f"loaded {result['loaded']} rules. First error: "
                f"{result['errors'][0]}")
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning(
            f"v10.110 rule loader bootstrap failed: "
            f"{type(e).__name__}: {e}")


_bootstrap_rules_from_json()
