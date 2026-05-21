"""utils/pipeline_to_bsc.py — Pipeline → BSC actuals bridge (v10.323).

Joshua's design insight: the pipeline module is the canonical place
for sales-related activity. Multiple roles tap into it — Tellers
(deposits at counter), Direct Sales Reps, Relationship Officers
(Personal/Business Banking), Branch Senior Relationship Officers,
Relationship Managers (Corporate/SME/Public Sector). Their BSC
KPIs around DEP_GROWTH, LOAN_DISB, FEES_COMM, NEW_CUST should pull
data FROM the pipeline rather than each having a separate
generator.

This module is that bridge. It reads pipeline.json + a configurable
product→KPI mapping, aggregates won deals per staff/period/KPI,
and submits the aggregates to bsc_engine.

Key design choices:
  1. **Configurable mapping** via data/pipeline_kpi_mapping.json —
     admin can re-classify products without touching code
  2. **Period from last_updated** for won deals (when the deal
     actually closed); aggregation period is "YYYY-QN" derived
     from the date
  3. **Sum aggregation** for volume KPIs (Disbursements *, Deposit
     Growth) — sum deal amounts
  4. **Fee estimation** for NFI KPIs (Total NFI) — multiply deal
     amount by configured fee rate per product type
  5. **Idempotent** — running twice doesn't double-count. Uses
     `source=pipeline_bridge` + `detail` field to identify
     existing submissions

Per Rule 7, this is a PRODUCER (it submits actuals). Like v10.317's
Teller activity generator. The downstream consumer is the BSC
scoring engine (v10.319-320) which now reads pipeline-derived
actuals for sales roles' scorecards.

Shipped: v10.323.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

REPO_ROOT = Path(__file__).parent.parent
DATA_DIR = REPO_ROOT / "data"


# ════════════════════════════════════════════════════════════════════
# Config + pipeline loaders
# ════════════════════════════════════════════════════════════════════

def load_pipeline() -> List[Dict[str, Any]]:
    """Read pipeline.json (list of deal records)."""
    from utils.db import db
    data = db.load_json(DATA_DIR / "pipeline.json", default=[])
    if isinstance(data, list):
        return data
    return []


def load_mapping() -> Dict[str, Any]:
    """Read pipeline_kpi_mapping.json (product → KPI + stage rules)."""
    from utils.db import db
    return db.load_json(
        DATA_DIR / "pipeline_kpi_mapping.json",
        default={},
    ) or {}


# ════════════════════════════════════════════════════════════════════
# Period derivation
# ════════════════════════════════════════════════════════════════════

def period_from_date(date_str: str) -> Optional[str]:
    """Convert 'YYYY-MM-DD' → 'YYYY-QN'."""
    if not date_str or len(date_str) < 7:
        return None
    try:
        year = int(date_str[:4])
        month = int(date_str[5:7])
    except (ValueError, TypeError):
        return None
    quarter = (month - 1) // 3 + 1
    return f"{year}-Q{quarter}"


# ════════════════════════════════════════════════════════════════════
# Deal → KPI mapping
# ════════════════════════════════════════════════════════════════════

@dataclass(frozen=True)
class DealContribution:
    """A single deal's contribution to a staff's KPI."""
    staff_code: str
    period: str
    kpi_id: str
    value: float                # in KPI units (per org_config currency)
    deal_id: str
    product: str
    source: str                 # 'amount' or 'fee_estimate'


def is_won_stage(stage: str, mapping: Dict[str, Any]) -> bool:
    """Check if a deal stage counts as won/realized."""
    won_list = (
        mapping.get("_meta", {})
        .get("stages_treated_as_won",
              ["Disbursed", "Closed Won", "Signed",
               "Documentation"])
    )
    return stage in won_list


def deal_to_contribution(
    deal: Dict[str, Any],
    mapping: Dict[str, Any],
) -> Optional[DealContribution]:
    """Convert one pipeline deal record to a BSC contribution.

    Returns None if the deal doesn't map (unknown product, no
    valid date, not won, no amount).
    """
    if not is_won_stage(deal.get("stage", ""), mapping):
        return None

    product = deal.get("product", "")
    kpi_id = mapping.get("product_to_kpi", {}).get(product)
    if not kpi_id:
        return None

    amount = deal.get("amount", 0)
    if not isinstance(amount, (int, float)) or amount <= 0:
        return None

    staff_code = deal.get("staff_code", "")
    if not staff_code:
        return None

    # Period from last_updated (when the deal closed)
    period = period_from_date(deal.get("last_updated", ""))
    if not period:
        # Fallback to expected_close
        period = period_from_date(
            deal.get("expected_close", ""))
    if not period:
        return None

    # For fee-bearing KPIs, estimate fee rather than using deal amount
    fee_kpis = {
        "Total NFI", "Fee Income", "Non-Funded Income",
    }
    if kpi_id in fee_kpis:
        rates = mapping.get("fee_estimation_rates", {})
        rate = rates.get(product, rates.get("_default", 0.01))
        value = float(amount) * float(rate)
        source = "fee_estimate"
    else:
        value = float(amount)
        source = "amount"

    return DealContribution(
        staff_code=staff_code,
        period=period,
        kpi_id=kpi_id,
        value=value,
        deal_id=deal.get("id", ""),
        product=product,
        source=source,
    )


# ════════════════════════════════════════════════════════════════════
# Aggregation
# ════════════════════════════════════════════════════════════════════

@dataclass
class AggregatedActual:
    """A summed contribution across multiple deals for one staff/
    KPI/period."""
    staff_code: str
    period: str
    kpi_id: str
    total_value: float
    deal_count: int
    deal_ids: List[str]


def aggregate_contributions(
    contributions: List[DealContribution],
) -> Dict[Tuple[str, str, str], AggregatedActual]:
    """Sum contributions by (staff_code, period, kpi_id)."""
    out: Dict[Tuple[str, str, str], AggregatedActual] = {}
    for c in contributions:
        key = (c.staff_code, c.period, c.kpi_id)
        if key in out:
            agg = out[key]
            agg.total_value += c.value
            agg.deal_count += 1
            agg.deal_ids.append(c.deal_id)
        else:
            out[key] = AggregatedActual(
                staff_code=c.staff_code,
                period=c.period,
                kpi_id=c.kpi_id,
                total_value=round(c.value, 2),
                deal_count=1,
                deal_ids=[c.deal_id],
            )
    return out


def all_contributions() -> List[DealContribution]:
    """Compute all contributions from the current pipeline.json
    + mapping config."""
    pipeline = load_pipeline()
    mapping = load_mapping()
    out: List[DealContribution] = []
    for deal in pipeline:
        c = deal_to_contribution(deal, mapping)
        if c:
            out.append(c)
    return out


# ════════════════════════════════════════════════════════════════════
# Submission to bsc_engine
# ════════════════════════════════════════════════════════════════════

@dataclass
class SyncReport:
    contributions: int
    aggregates: int
    submitted: int
    skipped: int
    by_period: Dict[str, int]
    by_kpi: Dict[str, int]
    sample: List[Dict[str, Any]]


def sync_pipeline_to_bsc(
    dry_run: bool = False,
    source_tag: str = "pipeline_bridge",
) -> SyncReport:
    """Aggregate won deals from pipeline + submit as BSC actuals.

    Args:
        dry_run: don't actually submit, just compute the report
        source_tag: source attribution on submitted actuals (lets
            future re-syncs identify what came from pipeline vs
            other producers)

    Idempotency: bsc_engine.submit_actual upserts by
    (staff_code, kpi_id, period) — re-submitting the same key
    overwrites. Safe to re-run.
    """
    contributions = all_contributions()
    aggregates = aggregate_contributions(contributions)

    by_period: Dict[str, int] = {}
    by_kpi: Dict[str, int] = {}
    submitted = 0
    skipped = 0
    sample: List[Dict[str, Any]] = []

    for key, agg in aggregates.items():
        by_period[agg.period] = by_period.get(agg.period, 0) + 1
        by_kpi[agg.kpi_id] = by_kpi.get(agg.kpi_id, 0) + 1

        if dry_run:
            submitted += 1
            if len(sample) < 5:
                sample.append({
                    "staff_code": agg.staff_code,
                    "period": agg.period,
                    "kpi_id": agg.kpi_id,
                    "value": agg.total_value,
                    "deal_count": agg.deal_count,
                })
            continue

        # Real submission
        try:
            from utils.bsc_engine import submit as _bsc_submit
            ok, op = _bsc_submit(
                staff_code=agg.staff_code,
                kpi_id=agg.kpi_id,
                value=agg.total_value,
                period=agg.period,
                source_module=source_tag,
                metadata={
                    "deal_count": agg.deal_count,
                    "deal_ids": agg.deal_ids[:5],
                    "bridge_version": "v10.323",
                },
            )
            if ok:
                submitted += 1
                if len(sample) < 5:
                    sample.append({
                        "staff_code": agg.staff_code,
                        "period": agg.period,
                        "kpi_id": agg.kpi_id,
                        "value": agg.total_value,
                        "deal_count": agg.deal_count,
                        "op": op,
                    })
            else:
                skipped += 1
        except Exception:  # noqa: BLE001
            skipped += 1

    return SyncReport(
        contributions=len(contributions),
        aggregates=len(aggregates),
        submitted=submitted,
        skipped=skipped,
        by_period=by_period,
        by_kpi=by_kpi,
        sample=sample,
    )


SPEC_DEVIATION_NOTE = (
    "This module is a PRODUCER (Rule 7 — submits actuals via "
    "bsc_engine.submit_actual). It reads pipeline.json (existing "
    "deal records) + data/pipeline_kpi_mapping.json (admin-editable "
    "product→KPI map + fee rates) and aggregates won deals "
    "(Disbursed/Closed Won/Signed/Documentation stages) per "
    "(staff_code, period, kpi_id), then submits the aggregates "
    "as BSC actuals tagged source='pipeline_bridge'. Re-running "
    "is idempotent (upsert by key). This is the canonical path "
    "for sales-role BSC data — multiple roles (RMs, ROs, DSRs, "
    "Tellers for deposit/account products) feed into pipeline, "
    "and pipeline feeds their BSC scorecards through this bridge."
)


# ════════════════════════════════════════════════════════════════════
# v10.337 — Pipeline Activity Bridge
# ════════════════════════════════════════════════════════════════════
#
# The original bridge (above) only emits actuals from won-stage deals.
# That means staff with active pipeline work but no closed deals don't
# get credit in their scorecard even though they're producing.
#
# This second bridge fixes that. It emits three pipeline-ACTIVITY
# KPIs per staff per quarter regardless of whether deals closed:
#
#   PIPELINE_DEALS_WON         — count of deals at won stages
#   PIPELINE_CONVERSION_RATE   — won / (won + lost + active-late-stage)
#   NEW_CUSTOMERS_ACQUIRED     — distinct customer count from won deals
#
# Combined with v10.337's branch_staff_generator (which handles the
# operational/quality KPIs for sales roles), branch sales staff now
# get a complete scorecard:
#
#   branch_staff_generator   → CX / Audit / Compliance / Staff Prod
#   pipeline_bridge (orig)   → DISB_RETAIL / DISB_MSME / Total NFI
#   pipeline_activity (new)  → PIPELINE_DEALS_WON / CONVERSION / NEW_CUSTOMERS
#
# Neither path writes a KPI the other writes — clean separation.

def _classify_deal_state(stage: str, mapping: Dict[str, Any]) -> str:
    """Return 'won' | 'lost' | 'active' | 'unknown' for a stage."""
    meta = mapping.get("_meta", {})
    won_list = set(
        meta.get(
            "stages_treated_as_won",
            ["Disbursed", "Closed Won", "Signed", "Documentation"],
        )
    )
    lost_list = set(meta.get("stages_treated_as_lost", ["Closed Lost"]))
    if stage in won_list:
        return "won"
    if stage in lost_list:
        return "lost"
    if stage:
        return "active"
    return "unknown"


def _activity_period_for(deal: Dict[str, Any]) -> Optional[str]:
    """Pick the period a deal belongs to for activity-rollup.

    Won/lost deals → period of last_updated (or expected_close).
    Active deals → period of last_updated (current activity).
    """
    p = period_from_date(deal.get("last_updated", ""))
    if not p:
        p = period_from_date(deal.get("expected_close", ""))
    return p


def compute_pipeline_activity(
    pipeline: Optional[List[Dict[str, Any]]] = None,
    mapping: Optional[Dict[str, Any]] = None,
) -> Dict[Tuple[str, str], Dict[str, Any]]:
    """Aggregate pipeline activity per (staff_code, period).

    Returns dict keyed on (staff_code, period) with values:
      {
        'won_count': int,
        'lost_count': int,
        'active_count': int,
        'won_customer_ids': set[str],
      }
    """
    if pipeline is None:
        pipeline = load_pipeline()
    if mapping is None:
        mapping = load_mapping()

    by_key: Dict[Tuple[str, str], Dict[str, Any]] = {}
    for deal in pipeline:
        staff_code = deal.get("staff_code")
        if not staff_code:
            continue
        period = _activity_period_for(deal)
        if not period:
            continue
        state = _classify_deal_state(deal.get("stage", ""), mapping)

        key = (str(staff_code), period)
        agg = by_key.setdefault(key, {
            "won_count": 0,
            "lost_count": 0,
            "active_count": 0,
            "won_customer_ids": set(),
        })
        if state == "won":
            agg["won_count"] += 1
            cust = deal.get("customer_id") or deal.get("customer_name")
            if cust:
                agg["won_customer_ids"].add(str(cust))
        elif state == "lost":
            agg["lost_count"] += 1
        elif state == "active":
            agg["active_count"] += 1

    return by_key


def sync_pipeline_activity_to_bsc(
    dry_run: bool = False,
    source_tag: str = "pipeline_activity_bridge",
) -> SyncReport:
    """Submit pipeline activity KPIs as BSC actuals.

    Emits three KPIs per (staff_code, period):
      PIPELINE_DEALS_WON       — count
      PIPELINE_CONVERSION_RATE — % = won / (won + lost + active)
      NEW_CUSTOMERS_ACQUIRED   — distinct customer count from won deals

    Idempotent via bsc_engine.submit_actual upsert.
    """
    activity = compute_pipeline_activity()

    by_period: Dict[str, int] = {}
    by_kpi: Dict[str, int] = {}
    submitted = 0
    skipped = 0
    sample: List[Dict[str, Any]] = []
    contributions = 0
    aggregates = len(activity)

    for (staff_code, period), agg in activity.items():
        contributions += (
            agg["won_count"] + agg["lost_count"] + agg["active_count"]
        )

        total_deals = (
            agg["won_count"] + agg["lost_count"] + agg["active_count"]
        )
        conversion_pct = (
            (100.0 * agg["won_count"] / total_deals)
            if total_deals > 0 else 0.0
        )
        new_customers = len(agg["won_customer_ids"])

        emissions = [
            ("PIPELINE_DEALS_WON", float(agg["won_count"])),
            ("PIPELINE_CONVERSION_RATE", round(conversion_pct, 2)),
            ("NEW_CUSTOMERS_ACQUIRED", float(new_customers)),
        ]

        for kpi_id, value in emissions:
            by_period[period] = by_period.get(period, 0) + 1
            by_kpi[kpi_id] = by_kpi.get(kpi_id, 0) + 1

            if dry_run:
                submitted += 1
                if len(sample) < 6:
                    sample.append({
                        "staff_code": staff_code,
                        "period": period,
                        "kpi_id": kpi_id,
                        "value": value,
                    })
                continue

            try:
                from utils.bsc_engine import submit as _bsc_submit
                ok, op = _bsc_submit(
                    staff_code=staff_code,
                    kpi_id=kpi_id,
                    value=value,
                    period=period,
                    source_module=source_tag,
                    metadata={
                        "won": agg["won_count"],
                        "lost": agg["lost_count"],
                        "active": agg["active_count"],
                        "bridge_version": "v10.337",
                    },
                )
                if ok:
                    submitted += 1
                    if len(sample) < 6:
                        sample.append({
                            "staff_code": staff_code,
                            "period": period,
                            "kpi_id": kpi_id,
                            "value": value,
                            "op": op,
                        })
                else:
                    skipped += 1
            except Exception:  # noqa: BLE001
                skipped += 1

    return SyncReport(
        contributions=contributions,
        aggregates=aggregates,
        submitted=submitted,
        skipped=skipped,
        by_period=by_period,
        by_kpi=by_kpi,
        sample=sample,
    )
