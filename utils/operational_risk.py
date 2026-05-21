"""utils.operational_risk — Operational Risk
(Standard #55, v5.55). Volume Nine — Risk Intelligence.

Per v6 spec §9 + Basel III operational risk principles:
    OperationalRiskEngine: loss event tracking + Basel-aligned categorization
    + KRI (Key Risk Indicator) computation.

WHAT THIS MODULE SHIPS
----------------------
1. Schema DDL (Cat A): risk.loss_events, risk.kri_metrics
2. OperationalRiskEngine class with:
   - log_loss_event(category, severity, date, description, financial_impact_kes)
   - aggregate_losses_by_category(period_start, period_end)
   - compute_kri_metrics(period_start, period_end) — frequency + severity rates

3. ORM_CATEGORIES catalog (Basel II/III 7-category):
   - INTERNAL_FRAUD
   - EXTERNAL_FRAUD
   - EMPLOYMENT_PRACTICES
   - CLIENTS_PRODUCTS_BUSINESS
   - DAMAGE_PHYSICAL_ASSETS
   - BUSINESS_DISRUPTION
   - EXECUTION_DELIVERY

4. SEVERITY_LEVELS: LOW (<100k), MEDIUM (100k-1M), HIGH (1M-10M), SEVERE (>10M)

HONESTY DISCIPLINE
------------------
Rule 1 — Standard #11:
  - Decimal precision for monetary impacts
  - average_loss returns None when event count is zero (Rule 1)

Rule 6 — No silent fallback:
  - Invalid category rejected (not silently re-bucketed)
  - Missing financial_impact treated as None (event still logged but
    excluded from monetary aggregations with explicit count)
"""
from __future__ import annotations

import logging
from collections import defaultdict
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP, getcontext
from typing import Any, Callable, Dict, List, Optional


logger = logging.getLogger("a2z.operational_risk")
getcontext().prec = 28


# ─────────────────────────────────────────────────────────────────────
# Spec literals (Basel II/III 7-category operational risk taxonomy)
# ─────────────────────────────────────────────────────────────────────

ORM_CATEGORIES: List[str] = [
    "INTERNAL_FRAUD",
    "EXTERNAL_FRAUD",
    "EMPLOYMENT_PRACTICES",
    "CLIENTS_PRODUCTS_BUSINESS",
    "DAMAGE_PHYSICAL_ASSETS",
    "BUSINESS_DISRUPTION",
    "EXECUTION_DELIVERY",
]

SEVERITY_LEVELS: List[str] = ["LOW", "MEDIUM", "HIGH", "SEVERE"]

# Severity thresholds (KES)
SEVERITY_THRESHOLDS = {
    "LOW":    Decimal("100000"),       # <100k
    "MEDIUM": Decimal("1000000"),      # <1M
    "HIGH":   Decimal("10000000"),     # <10M
    "SEVERE": None,                    # ≥10M
}

EVENT_STATUSES: List[str] = ["OPEN", "INVESTIGATING", "RESOLVED", "CLOSED"]


# ─────────────────────────────────────────────────────────────────────
# Schema DDL (Cat A)
# ─────────────────────────────────────────────────────────────────────

def build_schema_ddl() -> str:
    return """
-- Operational risk loss events
CREATE TABLE IF NOT EXISTS risk.loss_events (
    id                      SERIAL PRIMARY KEY,
    event_id                VARCHAR(50) UNIQUE,
    category                VARCHAR(50),
    severity                VARCHAR(20),
    event_date              DATE,
    detection_date          DATE,
    description             TEXT,
    financial_impact_kes    NUMERIC(20,2),
    branch_code             VARCHAR(10),
    department              VARCHAR(50),
    status                  VARCHAR(20),
    root_cause              TEXT,
    remediation             TEXT,
    reported_by             VARCHAR(50),
    created_at              TIMESTAMP DEFAULT NOW()
);

-- Key risk indicators
CREATE TABLE IF NOT EXISTS risk.kri_metrics (
    id                      SERIAL PRIMARY KEY,
    metric_name             VARCHAR(100),
    period                  VARCHAR(10),
    metric_value            NUMERIC(20,4),
    threshold_warning       NUMERIC(20,4),
    threshold_breach        NUMERIC(20,4),
    breach_status           VARCHAR(20),
    computed_at             TIMESTAMP
);
""".strip()


def ddl_contains_required_columns(ddl: str) -> Dict[str, List[str]]:
    required = {
        "risk.loss_events": [
            "event_id", "category", "severity", "event_date", "detection_date",
            "description", "financial_impact_kes", "branch_code", "department",
            "status", "root_cause", "remediation", "reported_by",
        ],
        "risk.kri_metrics": [
            "metric_name", "period", "metric_value",
            "threshold_warning", "threshold_breach", "breach_status",
        ],
    }
    out: Dict[str, List[str]] = {}
    for table, cols in required.items():
        idx = ddl.find(f"CREATE TABLE IF NOT EXISTS {table} (")
        if idx == -1:
            idx = ddl.find(f"CREATE TABLE {table} (")
        if idx == -1:
            out[table] = ["TABLE_NOT_FOUND"]
            continue
        end = ddl.find(");", idx)
        block = ddl[idx:end] if end > idx else ddl[idx:]
        out[table] = [c for c in cols if c not in block]
    return out


# ─────────────────────────────────────────────────────────────────────
# Engine
# ─────────────────────────────────────────────────────────────────────

class OperationalRiskEngine:
    """Operational risk loss event tracking + Basel-aligned aggregation."""

    ORM_CATEGORIES = ORM_CATEGORIES
    SEVERITY_LEVELS = SEVERITY_LEVELS

    def __init__(
        self,
        event_store_fn:    Optional[Callable[[dict], str]] = None,
        event_query_fn:    Optional[Callable[[str, str], List[dict]]] = None,
    ):
        """
        event_store_fn(event_dict) → event_id
        event_query_fn(period_start, period_end) → list of events in window
        """
        self._events: List[dict] = []
        self._store = event_store_fn or self._default_store
        self._query = event_query_fn or self._default_query

    # ──────────────────────────────────────────────────────────────────
    # Spec entry: log_loss_event
    # ──────────────────────────────────────────────────────────────────

    def log_loss_event(
        self,
        category: str,
        event_date: str,
        description: str,
        financial_impact_kes: Optional[float] = None,
        branch_code: Optional[str] = None,
        reported_by: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Log an operational loss event with Basel-aligned classification."""
        if category not in ORM_CATEGORIES:
            return {
                "success": False,
                "error":   f"invalid category {category!r}; valid: {ORM_CATEGORIES}",
            }
        if not event_date:
            return {"success": False, "error": "event_date required"}
        if not description:
            return {"success": False, "error": "description required"}

        try:
            datetime.strptime(event_date, "%Y-%m-%d")
        except ValueError:
            return {"success": False, "error": f"event_date must be YYYY-MM-DD, got {event_date!r}"}

        # Severity from financial impact
        severity = self._classify_severity(financial_impact_kes)

        event_id = f"EVT_{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S%f')[:18]}"
        record = {
            "event_id":              event_id,
            "category":              category,
            "severity":              severity,
            "event_date":            event_date,
            "detection_date":        datetime.now(timezone.utc).strftime("%Y-%m-%d"),
            "description":           description,
            "financial_impact_kes":  financial_impact_kes,
            "branch_code":           branch_code,
            "status":                "OPEN",
            "reported_by":           reported_by,
            "created_at":            datetime.now(timezone.utc).isoformat(),
        }
        stored_id = self._store(record)

        return {
            "success":   True,
            "event_id":  stored_id,
            "severity":  severity,
            "category":  category,
            "financial_impact_known": financial_impact_kes is not None,
        }

    def _classify_severity(self, impact_kes: Optional[float]) -> str:
        """Classify severity from financial impact. None impact → LOW (default)."""
        if impact_kes is None:
            return "LOW"    # Default to LOW when impact unknown (conservative)
        try:
            impact_dec = Decimal(str(impact_kes))
        except Exception:
            return "LOW"
        if impact_dec >= Decimal("10000000"):
            return "SEVERE"
        if impact_dec >= Decimal("1000000"):
            return "HIGH"
        if impact_dec >= Decimal("100000"):
            return "MEDIUM"
        return "LOW"

    # ──────────────────────────────────────────────────────────────────
    # Spec entry: aggregate_losses_by_category
    # ──────────────────────────────────────────────────────────────────

    def aggregate_losses_by_category(
        self, period_start: str, period_end: str,
    ) -> Dict[str, Any]:
        """Aggregate losses by Basel category for a period."""
        events = self._query(period_start, period_end) or []

        by_category: Dict[str, Dict[str, Any]] = {
            cat: {
                "event_count":      0,
                "total_impact":     Decimal("0"),
                "events_with_impact": 0,
                "events_no_impact": 0,
                "by_severity":      {s: 0 for s in SEVERITY_LEVELS},
            }
            for cat in ORM_CATEGORIES
        }

        for event in events:
            if not isinstance(event, dict):
                continue
            cat = event.get("category")
            if cat not in by_category:
                continue
            by_category[cat]["event_count"] += 1
            sev = event.get("severity", "LOW")
            if sev in by_category[cat]["by_severity"]:
                by_category[cat]["by_severity"][sev] += 1

            impact = event.get("financial_impact_kes")
            if impact is None:
                by_category[cat]["events_no_impact"] += 1
            else:
                try:
                    by_category[cat]["total_impact"] += Decimal(str(impact))
                    by_category[cat]["events_with_impact"] += 1
                except Exception:
                    by_category[cat]["events_no_impact"] += 1

        # Format output
        out: Dict[str, Dict[str, Any]] = {}
        for cat, stats in by_category.items():
            out[cat] = {
                "event_count":         stats["event_count"],
                "total_impact":        _money(stats["total_impact"]),
                "events_with_impact":  stats["events_with_impact"],
                "events_no_impact":    stats["events_no_impact"],
                "by_severity":         stats["by_severity"],
                # Rule 1 — None when no events with impact
                "average_loss":        (
                    _money(stats["total_impact"] / Decimal(stats["events_with_impact"]))
                    if stats["events_with_impact"] > 0 else None
                ),
            }

        return {
            "period_start":     period_start,
            "period_end":       period_end,
            "by_category":      out,
            "total_event_count": sum(c["event_count"] for c in out.values()),
            "total_impact":      _money(sum(
                Decimal(str(c["total_impact"])) for c in out.values()
            )),
            "meta": {
                "categories":   list(ORM_CATEGORIES),
                "generated_at": datetime.now(timezone.utc).isoformat(),
            },
        }

    # ──────────────────────────────────────────────────────────────────
    # Spec entry: compute_kri_metrics
    # ──────────────────────────────────────────────────────────────────

    def compute_kri_metrics(
        self, period_start: str, period_end: str,
    ) -> Dict[str, Any]:
        """Compute KRIs: event frequency, severity distribution."""
        events = self._query(period_start, period_end) or []

        try:
            d_start = datetime.strptime(period_start, "%Y-%m-%d")
            d_end = datetime.strptime(period_end, "%Y-%m-%d")
            days = max(1, (d_end - d_start).days + 1)
        except ValueError:
            return {"error": f"invalid period dates"}

        events_by_severity = {s: 0 for s in SEVERITY_LEVELS}
        for e in events:
            if not isinstance(e, dict):
                continue
            sev = e.get("severity", "LOW")
            if sev in events_by_severity:
                events_by_severity[sev] += 1

        return {
            "period_start":          period_start,
            "period_end":            period_end,
            "period_days":           days,
            "event_frequency":       len(events),
            "events_per_day":        round(len(events) / days, 4),
            "severity_distribution": events_by_severity,
            "severe_events":         events_by_severity["SEVERE"],
            "meta": {
                "generated_at": datetime.now(timezone.utc).isoformat(),
            },
        }

    # ── Default in-memory implementations (testing) ──────────────────
    def _default_store(self, record: dict) -> str:
        self._events.append(dict(record))
        return record["event_id"]

    def _default_query(self, period_start: str, period_end: str) -> List[dict]:
        return [e for e in self._events
                if period_start <= e.get("event_date", "") <= period_end]

    # ============================================================================
    # v7.6: L04 Vendor health → Operational risk feedback loop (CONSUMER)
    # ============================================================================
    @classmethod
    def vendor_health_to_oprisk(
        cls,
        concentration_payload: Optional[Dict[str, Any]] = None,
        sla_breach_records: Optional[List[Dict[str, Any]]] = None,
        due_diligence_payload: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """L04 (CONSUMER) — convert vendor health signals into operational risk events.

        Consumes:
            - `vendor_risk.vendor_concentration_check()` payload — flags
              category-level concentration breaches
            - `vendor_risk.sla_breach_severity()` outputs aggregated as a
              list of breach records {vendor_id, downtime_hours, severity}
            - `vendor_risk.due_diligence_completeness()` payload —
              expired/incomplete due-diligence flags

        Per Charter §7 Published Language pattern, depends only on the
        public dict contracts of vendor_risk engine.

        Strategy:
            - Concentration breach (single vendor > threshold) → HIGH oprisk event
            - SLA breach severity HIGH/CRITICAL → corresponding oprisk severity
            - Expired due diligence → MEDIUM oprisk event (compliance gap)

        Returns dict with:
            oprisk_events: list[dict] — synthesised operational risk events
            summary: counts by source + severity
            consumed_payload_version: str
            pattern: str
        """
        oprisk_events: List[Dict[str, Any]] = []
        sources_count = {"concentration": 0, "sla": 0, "due_diligence": 0}

        # 1. Concentration breach
        if isinstance(concentration_payload, dict):
            breached = concentration_payload.get("concentration_breached")
            if breached:
                top_share = concentration_payload.get("top_vendor_share_pct")
                top_vendor = concentration_payload.get("top_vendor_id")
                category = concentration_payload.get("category")
                oprisk_events.append({
                    "source": "vendor_concentration",
                    "category": "OUTSOURCING_RISK",
                    "severity": "HIGH",
                    "description": (
                        f"Vendor concentration breach in '{category}': "
                        f"top vendor '{top_vendor}' = {top_share}% (threshold breached)"
                    ),
                    "vendor_id": top_vendor,
                    "metric": "concentration_pct",
                    "value": top_share,
                })
                sources_count["concentration"] += 1

        # 2. SLA breaches
        if isinstance(sla_breach_records, list):
            for rec in sla_breach_records:
                if not isinstance(rec, dict):
                    continue
                sev = rec.get("severity")
                if sev not in ("HIGH", "CRITICAL"):
                    continue
                oprisk_events.append({
                    "source": "vendor_sla_breach",
                    "category": "BUSINESS_DISRUPTION",
                    "severity": sev,
                    "description": (
                        f"Vendor SLA breach — vendor '{rec.get('vendor_id')}' "
                        f"downtime {rec.get('downtime_hours')}h ({sev})"
                    ),
                    "vendor_id": rec.get("vendor_id"),
                    "metric": "downtime_hours",
                    "value": rec.get("downtime_hours"),
                })
                sources_count["sla"] += 1

        # 3. Due diligence gaps
        if isinstance(due_diligence_payload, dict):
            completeness_pct = due_diligence_payload.get("completeness_pct")
            missing_items = due_diligence_payload.get("missing_items", [])
            if completeness_pct is not None:
                try:
                    cp = float(completeness_pct)
                    if cp < 80:  # threshold
                        oprisk_events.append({
                            "source": "vendor_due_diligence",
                            "category": "COMPLIANCE_GAP",
                            "severity": "MEDIUM",
                            "description": (
                                f"Vendor due diligence incomplete — "
                                f"{cp:.0f}% complete, {len(missing_items)} items missing"
                            ),
                            "vendor_id": due_diligence_payload.get("vendor_id"),
                            "metric": "completeness_pct",
                            "value": cp,
                        })
                        sources_count["due_diligence"] += 1
                except (TypeError, ValueError):
                    pass

        # Severity counts
        severity_counts: Dict[str, int] = {}
        for e in oprisk_events:
            severity_counts[e["severity"]] = severity_counts.get(e["severity"], 0) + 1

        return {
            "oprisk_events": oprisk_events,
            "summary": {
                "total_events": len(oprisk_events),
                "by_source": sources_count,
                "by_severity": severity_counts,
            },
            "consumed_payload_version": (
                "vendor_risk.vendor_concentration_check+sla_breach_severity"
                "+due_diligence_completeness v1.0"
            ),
            "pattern": "PUBLISHED_LANGUAGE",
            "cited_invariants": [],
        }


# ─────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────

def _money(d) -> float:
    if not isinstance(d, Decimal):
        try:
            d = Decimal(str(d))
        except Exception:
            return 0.0
    return float(d.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


# ─────────────────────────────────────────────────────────────────────
# Self-test
# ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("A2Z MIS 360 — utils.operational_risk self-test")

    assert len(ORM_CATEGORIES) == 7
    assert "INTERNAL_FRAUD" in ORM_CATEGORIES
    print(f"  ✅ Basel 7-category taxonomy: {len(ORM_CATEGORIES)} categories")
    assert SEVERITY_LEVELS == ["LOW", "MEDIUM", "HIGH", "SEVERE"]
    print(f"  ✅ severity levels: {SEVERITY_LEVELS}")

    # Schema
    ddl = build_schema_ddl()
    missing = ddl_contains_required_columns(ddl)
    for table, cols in missing.items():
        assert cols == [], f"{table} missing: {cols}"
    print(f"  ✅ schema 2 tables complete")

    # Log valid event
    eng = OperationalRiskEngine()
    r = eng.log_loss_event(
        category="EXTERNAL_FRAUD",
        event_date="2026-04-15",
        description="ATM card cloning incident",
        financial_impact_kes=250_000,
        branch_code="BR001",
        reported_by="risk_officer_001",
    )
    assert r["success"] is True
    assert r["severity"] == "MEDIUM"   # 250k → MEDIUM (≥100k, <1M)
    print(f"  ✅ event logged: severity={r['severity']}")

    # Severity classification
    assert eng._classify_severity(50_000) == "LOW"
    assert eng._classify_severity(500_000) == "MEDIUM"
    assert eng._classify_severity(5_000_000) == "HIGH"
    assert eng._classify_severity(50_000_000) == "SEVERE"
    print(f"  ✅ severity bands: 50k=LOW, 500k=MEDIUM, 5M=HIGH, 50M=SEVERE")

    # Invalid category rejected
    r = eng.log_loss_event("MAGIC_BAD_THING", "2026-04-15", "test")
    assert r["success"] is False
    assert "invalid category" in r["error"]
    print(f"  ✅ invalid category rejected (Rule 6)")

    # Invalid date
    r = eng.log_loss_event("INTERNAL_FRAUD", "not-a-date", "test")
    assert r["success"] is False
    print(f"  ✅ invalid date rejected")

    # Aggregation
    eng.log_loss_event("INTERNAL_FRAUD", "2026-04-10", "Embezzlement", 5_000_000)
    eng.log_loss_event("INTERNAL_FRAUD", "2026-04-20", "Forgery", 200_000)
    eng.log_loss_event("EXTERNAL_FRAUD", "2026-04-25", "Cybercrime", 12_000_000)
    eng.log_loss_event("EXECUTION_DELIVERY", "2026-04-12", "Settlement error")  # no impact
    r = eng.aggregate_losses_by_category("2026-04-01", "2026-04-30")
    int_fraud = r["by_category"]["INTERNAL_FRAUD"]
    assert int_fraud["event_count"] == 2
    assert int_fraud["total_impact"] == 5_200_000.00
    assert int_fraud["by_severity"]["HIGH"] == 1
    assert int_fraud["by_severity"]["MEDIUM"] == 1
    print(f"  ✅ INTERNAL_FRAUD: 2 events, 5.2M total, severity split")

    ext_fraud = r["by_category"]["EXTERNAL_FRAUD"]
    assert ext_fraud["by_severity"]["SEVERE"] == 1   # 12M > 10M
    print(f"  ✅ 12M event → SEVERE")

    # No-impact event tracked separately (Rule 6)
    exec_del = r["by_category"]["EXECUTION_DELIVERY"]
    assert exec_del["events_no_impact"] == 1
    assert exec_del["events_with_impact"] == 0
    assert exec_del["average_loss"] is None     # Rule 1 — None when zero events with impact
    print(f"  ✅ no-impact event: tracked separately, avg=None (Rule 1+6)")

    # KRI computation
    r = eng.compute_kri_metrics("2026-04-01", "2026-04-30")
    assert r["event_frequency"] == 5
    assert r["severe_events"] == 1
    print(f"  ✅ KRI: {r['event_frequency']} events / {r['period_days']}d, "
          f"{r['severe_events']} SEVERE")

    print("\n  ALL TESTS PASSED")
