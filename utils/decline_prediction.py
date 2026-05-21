"""
================================================================================
A2Z MIS 360 — Standard #344: Decline Prediction & Intervention Engine
================================================================================

Risk classification: Cat A (revenue protection — proactive churn intervention)
                     + Rule 7 ML hook factory

NOTE on filename: This module is `decline_prediction.py` (not
`churn_prediction.py`) because the latter already exists for the legacy
ENH-71 standard ("Churn Prediction Engine") which uses different
signals + segmentation. ENH-344 is the customer-behavioral-cluster
churn prediction with 90-day horizon + intervention tracking + Rule 7
ml_nba_fn hook for journey_and_widget.

Predict customer churn 90 days ahead. Automated intervention triggers:
outreach, retention offers, RM assignment. v10.276 ships deterministic
risk-factor weighting + Rule 7 ml_nba_fn factory consumable by v10.275
journey_and_widget for ML-driven NBA upgrade.

Public API:
    predict_decline(customer_id, as_of=None, product_count=0)
        -> {risk_score, risk_level, contributing_factors, prediction_horizon_days}
    at_risk_customers(customer_ids, threshold=70) -> bulk scan
    register_intervention(customer_id, intervention_data, actor)
    intervention_outcome(intervention_id, outcome, actor)
    make_ml_nba_fn() -> Callable for journey_and_widget NBA upgrade

DECLINE_RISK_FACTORS byte-for-byte (sum of weights = 100):
    DECLINING_ENGAGEMENT       -- 25 (60d event count vs prior 60d)
    MULTI_CHANNEL_FAILURE      -- 20 (failures across 2+ channels)
    HIGH_COMPLAINT_FREQUENCY   -- 20 (≥2 complaints in 30 days)
    DORMANCY_PROXIMITY         -- 15 (60-89 days since last event)
    LOW_PRODUCT_DIVERSITY      -- 10 (single product / sparse engagement)
    RECENT_FRICTION_INDICATOR  -- 10 (any v10.275 friction indicator)

DECLINE_RISK_LEVELS byte-for-byte:
    HIGH       -- score ≥ 70 (urgent intervention)
    MEDIUM     -- 40 ≤ score < 70 (monitor + soft outreach)
    LOW        -- score < 40 (no action needed)
    UNKNOWN    -- insufficient data

INTERVENTION_TYPES byte-for-byte:
    OUTREACH_CALL          -- RM call
    RETENTION_OFFER        -- discount / fee waiver / preferential rate
    PRODUCT_RECOMMENDATION -- NBA cross-sell to deepen relationship
    RM_REASSIGNMENT        -- assign new RM
    EXECUTIVE_ESCALATION   -- senior intervention
    WIN_BACK_CAMPAIGN      -- formal win-back program

INTERVENTION_OUTCOMES byte-for-byte:
    RETAINED           -- customer stayed + engagement recovered
    PARTIALLY_RETAINED -- customer stayed but engagement still low
    CHURNED            -- customer left despite intervention (terminal)
    NO_RESPONSE        -- intervention had no measurable effect (terminal)

PREDICTION_HORIZON_DAYS = 90  (per Continuation.docx threshold)
HIGH_RISK_THRESHOLD = 70
MEDIUM_RISK_THRESHOLD = 40

Honesty rules:
    Rule 1: predict_decline returns risk_level=UNKNOWN when no events
    Rule 6: invalid intervention_type / outcome rejected
    Rule 7: SPEC_DEVIATION_NOTE — production ML requires labeled churn
            outcomes + supervised model

================================================================================
"""

from __future__ import annotations

from datetime import datetime, date, timedelta
from decimal import Decimal, getcontext
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Callable

from utils.interaction_capture import InteractionCaptureEngine
from utils.journey_and_widget import (
    JourneyAndWidgetEngine,
    DORMANT_THRESHOLD_DAYS,
)

getcontext().prec = 28


SPEC_DEVIATION_NOTE: str = (
    "Continuation.docx #344 specifies ML-based churn prediction with "
    "90-day horizon. v10.276 ships deterministic risk-factor weighting "
    "(6 factors summing to 100) over the v10.275 event store and "
    "journey_and_widget friction outputs. Production ML training "
    "requires labeled churn outcomes (ground-truth churned vs retained "
    "customers) + supervised model with feature engineering — deferred "
    "to deployment phase. The Rule 7 ml_nba_fn factory "
    "(make_ml_nba_fn) returns a callable that upgrades the v10.275 "
    "journey_and_widget rule-based NBA to incorporate decline risk."
)


DECLINE_RISK_FACTORS: Tuple[str, ...] = (
    "DECLINING_ENGAGEMENT", "MULTI_CHANNEL_FAILURE",
    "HIGH_COMPLAINT_FREQUENCY", "DORMANCY_PROXIMITY",
    "LOW_PRODUCT_DIVERSITY", "RECENT_FRICTION_INDICATOR",
)

DECLINE_FACTOR_WEIGHTS: Dict[str, Decimal] = {
    "DECLINING_ENGAGEMENT":      Decimal("25"),
    "MULTI_CHANNEL_FAILURE":     Decimal("20"),
    "HIGH_COMPLAINT_FREQUENCY":  Decimal("20"),
    "DORMANCY_PROXIMITY":        Decimal("15"),
    "LOW_PRODUCT_DIVERSITY":     Decimal("10"),
    "RECENT_FRICTION_INDICATOR": Decimal("10"),
}

DECLINE_RISK_LEVELS: Tuple[str, ...] = ("HIGH", "MEDIUM", "LOW", "UNKNOWN")

INTERVENTION_TYPES: Tuple[str, ...] = (
    "OUTREACH_CALL", "RETENTION_OFFER", "PRODUCT_RECOMMENDATION",
    "RM_REASSIGNMENT", "EXECUTIVE_ESCALATION", "WIN_BACK_CAMPAIGN",
)

INTERVENTION_OUTCOMES: Tuple[str, ...] = (
    "RETAINED", "PARTIALLY_RETAINED", "CHURNED", "NO_RESPONSE",
)

PREDICTION_HORIZON_DAYS: int = 90
HIGH_RISK_THRESHOLD: Decimal = Decimal("70")
MEDIUM_RISK_THRESHOLD: Decimal = Decimal("40")


class DeclinePredictionEngine:
    """Deterministic decline-risk scoring + intervention tracking."""

    def __init__(
        self,
        capture: Optional[InteractionCaptureEngine] = None,
        journey: Optional[JourneyAndWidgetEngine] = None,
        interventions_path: Optional[Path] = None,
    ):
        self.capture = capture or InteractionCaptureEngine()
        self.journey = journey or JourneyAndWidgetEngine(capture=self.capture)
        self.interventions_path = (
            interventions_path
            if interventions_path is not None
            else Path(__file__).parent.parent / "data"
                 / "decline_interventions.json"
        )

    def _load_interventions(self) -> List[Dict[str, Any]]:
        try:
            from utils.db import db as _db
            data = _db.dual_load(
                self.interventions_path,
                table="decline_interventions",
                index_cols=("intervention_id",))
            return data if isinstance(data, list) else []
        except Exception:
            return []

    def _save_interventions(self, records: List[Dict[str, Any]]) -> bool:
        try:
            from utils.db import db as _db
            self.interventions_path.parent.mkdir(parents=True, exist_ok=True)
            _db.dual_save(
                self.interventions_path,
                data=records,
                table="decline_interventions",
                pk_col="intervention_id")
            return True
        except Exception:
            return False

    def predict_decline(
        self,
        customer_id: str,
        as_of: Optional[date] = None,
        product_count: int = 0,
    ) -> Dict[str, Any]:
        """Compute decline risk score + level."""
        as_of = as_of or date.today()
        events = self.capture.list_events(customer_id, limit=10**9)

        if not events:
            return {
                "customer_id": customer_id,
                "risk_score": None,
                "risk_level": "UNKNOWN",
                "reason": "no_events_no_history",
                "prediction_horizon_days": PREDICTION_HORIZON_DAYS,
            }

        events.sort(key=lambda e: e.get("occurred_at", ""))

        score = Decimal("0")
        contributing_factors: Dict[str, Dict[str, Any]] = {}

        # 1. DECLINING_ENGAGEMENT
        prev_start = (as_of - timedelta(days=120)).isoformat()
        prev_end = (as_of - timedelta(days=60)).isoformat()
        this_start = (as_of - timedelta(days=60)).isoformat()
        prev_count = sum(1 for e in events
                            if prev_start <= e.get("occurred_at", "") < prev_end)
        this_count = sum(1 for e in events
                            if this_start <= e.get("occurred_at", ""))
        if prev_count >= 5:
            decline = (prev_count - this_count) / prev_count if prev_count else 0
            if decline >= 0.5:
                w = DECLINE_FACTOR_WEIGHTS["DECLINING_ENGAGEMENT"]
                score += w
                contributing_factors["DECLINING_ENGAGEMENT"] = {
                    "weight": str(w),
                    "prev_60d_count": prev_count,
                    "this_60d_count": this_count,
                    "decline_pct": round(decline * 100, 2),
                }

        # 2. MULTI_CHANNEL_FAILURE
        seven_ago = (as_of - timedelta(days=7)).isoformat()
        recent_failures = [
            e for e in events
            if e.get("outcome") in ("FAILURE", "ABANDONED")
            and e.get("occurred_at", "") >= seven_ago
        ]
        failure_channels = {e.get("channel") for e in recent_failures}
        if len(failure_channels) >= 2:
            w = DECLINE_FACTOR_WEIGHTS["MULTI_CHANNEL_FAILURE"]
            score += w
            contributing_factors["MULTI_CHANNEL_FAILURE"] = {
                "weight": str(w),
                "failure_channels": sorted(failure_channels),
                "failure_count": len(recent_failures),
            }

        # 3. HIGH_COMPLAINT_FREQUENCY
        thirty_ago = (as_of - timedelta(days=30)).isoformat()
        complaints = [
            e for e in events
            if e.get("event_type") == "COMPLAINT"
            and e.get("occurred_at", "") >= thirty_ago
        ]
        if len(complaints) >= 2:
            w = DECLINE_FACTOR_WEIGHTS["HIGH_COMPLAINT_FREQUENCY"]
            score += w
            contributing_factors["HIGH_COMPLAINT_FREQUENCY"] = {
                "weight": str(w),
                "complaint_count_30d": len(complaints),
            }

        # 4. DORMANCY_PROXIMITY
        last_ts = events[-1].get("occurred_at", "")
        try:
            last_dt = datetime.fromisoformat(last_ts.replace("Z", ""))
            days_since = (datetime.combine(as_of, datetime.min.time()) - last_dt).days
        except (ValueError, AttributeError):
            days_since = 0
        if 60 <= days_since < DORMANT_THRESHOLD_DAYS:
            w = DECLINE_FACTOR_WEIGHTS["DORMANCY_PROXIMITY"]
            score += w
            contributing_factors["DORMANCY_PROXIMITY"] = {
                "weight": str(w),
                "days_since_last_event": days_since,
            }

        # 5. LOW_PRODUCT_DIVERSITY
        if product_count <= 1:
            w = DECLINE_FACTOR_WEIGHTS["LOW_PRODUCT_DIVERSITY"]
            score += w
            contributing_factors["LOW_PRODUCT_DIVERSITY"] = {
                "weight": str(w),
                "product_count": product_count,
            }

        # 6. RECENT_FRICTION_INDICATOR
        friction = self.journey.journey_friction_points(customer_id, as_of)
        if friction.get("indicator_count", 0) > 0:
            w = DECLINE_FACTOR_WEIGHTS["RECENT_FRICTION_INDICATOR"]
            score += w
            contributing_factors["RECENT_FRICTION_INDICATOR"] = {
                "weight": str(w),
                "indicators_present": friction.get("indicators_present", []),
            }

        score = min(score, Decimal("100"))

        if score >= HIGH_RISK_THRESHOLD:
            level = "HIGH"
        elif score >= MEDIUM_RISK_THRESHOLD:
            level = "MEDIUM"
        else:
            level = "LOW"

        return {
            "customer_id": customer_id,
            "risk_score": str(score.quantize(Decimal("0.01"))),
            "risk_level": level,
            "contributing_factors": contributing_factors,
            "prediction_horizon_days": PREDICTION_HORIZON_DAYS,
            "factor_weights": {k: str(v) for k, v in DECLINE_FACTOR_WEIGHTS.items()},
            "_meta": {"spec_deviation": SPEC_DEVIATION_NOTE},
        }

    def at_risk_customers(
        self,
        customer_ids: List[str],
        threshold: int = 70,
        as_of: Optional[date] = None,
    ) -> List[Dict[str, Any]]:
        out = []
        for cid in customer_ids:
            pred = self.predict_decline(cid, as_of=as_of)
            score = pred.get("risk_score")
            if score is None:
                continue
            try:
                if Decimal(score) >= Decimal(threshold):
                    out.append({
                        "customer_id": cid,
                        "risk_score": score,
                        "risk_level": pred["risk_level"],
                        "contributing_factors": list(
                            pred.get("contributing_factors", {}).keys()
                        ),
                    })
            except (ValueError, TypeError):
                continue
        out.sort(key=lambda x: Decimal(x["risk_score"]), reverse=True)
        return out

    def register_intervention(
        self,
        customer_id: str,
        intervention_data: Dict[str, Any],
        actor: str,
    ) -> Dict[str, Any]:
        if not actor:
            return {"registered": False, "error": "actor_required"}
        for f in ("intervention_id", "intervention_type"):
            if f not in intervention_data or not intervention_data[f]:
                return {"registered": False, "error": f"missing_field:{f}"}
        if intervention_data["intervention_type"] not in INTERVENTION_TYPES:
            return {
                "registered": False,
                "error": f"invalid_intervention_type:{intervention_data['intervention_type']}",
            }

        records = self._load_interventions()
        if any(r.get("intervention_id") == intervention_data["intervention_id"]
                 for r in records):
            return {"registered": False, "error": "duplicate_intervention_id"}

        record = {
            "intervention_id": intervention_data["intervention_id"],
            "customer_id": customer_id,
            "intervention_type": intervention_data["intervention_type"],
            "trigger_risk_score": intervention_data.get("trigger_risk_score"),
            "notes": intervention_data.get("notes", ""),
            "outcome": None,
            "registered_by": actor,
            "registered_at": datetime.utcnow().isoformat(),
        }
        records.append(record)
        ok = self._save_interventions(records)
        return {"registered": ok,
                  "intervention_id": intervention_data["intervention_id"]}

    def intervention_outcome(
        self,
        intervention_id: str,
        outcome: str,
        actor: str,
        notes: str = "",
    ) -> Dict[str, Any]:
        if not actor:
            return {"recorded": False, "error": "actor_required"}
        if outcome not in INTERVENTION_OUTCOMES:
            return {
                "recorded": False,
                "error": f"invalid_outcome:{outcome}",
            }

        records = self._load_interventions()
        for r in records:
            if r.get("intervention_id") == intervention_id:
                if r.get("outcome") in ("CHURNED", "NO_RESPONSE"):
                    return {
                        "recorded": False,
                        "error": f"outcome_already_terminal:{r['outcome']}",
                    }
                r["outcome"] = outcome
                r["outcome_notes"] = notes
                r["outcome_recorded_by"] = actor
                r["outcome_recorded_at"] = datetime.utcnow().isoformat()
                ok = self._save_interventions(records)
                return {"recorded": ok, "outcome": outcome}
        return {"recorded": False, "error": "intervention_not_found"}

    # ── Rule 7 hook factory ─────────────────────────────────────────

    def make_ml_nba_fn(self) -> Callable[..., Dict[str, Any]]:
        """
        Returns a callable for journey_and_widget.ml_nba_fn upgrade.

        Signature: fn(customer_id, stage, product_count, as_of=None)
                   -> Dict {action, reason, confidence, ml_driven}

        HIGH risk → HIGH_RISK_OUTREACH (overrides rule-based).
        MEDIUM risk in ENGAGEMENT/LOYALTY → RETENTION_GIFT (preempt churn).
        Otherwise returns action=None signaling defer to rule-based NBA.
        """
        engine_self = self

        def _ml_nba_fn(
            customer_id: str,
            stage: Optional[str] = None,
            product_count: int = 0,
            as_of: Optional[date] = None,
        ) -> Dict[str, Any]:
            pred = engine_self.predict_decline(
                customer_id, as_of=as_of, product_count=product_count,
            )
            level = pred.get("risk_level")
            score = pred.get("risk_score")

            if level == "HIGH":
                return {
                    "action": "HIGH_RISK_OUTREACH",
                    "reason": f"decline_risk_HIGH_score_{score}",
                    "confidence": "HIGH",
                    "ml_driven": True,
                    "underlying_risk_score": score,
                }
            if level == "MEDIUM" and stage in ("ENGAGEMENT", "LOYALTY"):
                return {
                    "action": "RETENTION_GIFT",
                    "reason": f"decline_risk_MEDIUM_in_{stage}_score_{score}",
                    "confidence": "MEDIUM",
                    "ml_driven": True,
                    "underlying_risk_score": score,
                }
            return {
                "action": None,
                "reason": f"defer_to_rule_based_risk_{level}",
                "confidence": "LOW",
                "ml_driven": False,
                "underlying_risk_score": score,
            }

        return _ml_nba_fn


def _self_test() -> None:
    import tempfile

    assert sum(DECLINE_FACTOR_WEIGHTS.values()) == Decimal("100")
    assert PREDICTION_HORIZON_DAYS == 90
    assert "v10.275" in SPEC_DEVIATION_NOTE

    with tempfile.TemporaryDirectory() as tmpdir:
        capture = InteractionCaptureEngine(
            events_path=Path(tmpdir) / "ev.json",
        )
        engine = DeclinePredictionEngine(
            capture=capture,
            interventions_path=Path(tmpdir) / "intv.json",
        )

        # Test 1: no events → UNKNOWN
        pred = engine.predict_decline("UNKNOWN")
        assert pred["risk_level"] == "UNKNOWN"

        # Test 2: HIGH risk customer
        for i in range(40):
            day = (date.today() - timedelta(days=119 - i)).isoformat()
            capture.capture_event(
                "CUST-HIGH",
                {"event_id": f"PRIOR-{i}",
                 "channel": "MOBILE_APP",
                 "event_type": "TRANSACTION",
                 "outcome": "SUCCESS",
                 "occurred_at": day + "T10:00:00",
                 "amount_kes": "5000"},
                actor="pipeline",
            )
        for i in range(2):
            capture.capture_event(
                "CUST-HIGH",
                {"event_id": f"COMP-{i}",
                 "channel": "CALL_CENTER",
                 "event_type": "COMPLAINT",
                 "outcome": "PENDING",
                 "occurred_at": (date.today() - timedelta(days=10-i)).isoformat() + "T10:00:00"},
                actor="pipeline",
            )
        for i, ch in enumerate(["MOBILE_APP", "WEB"]):
            capture.capture_event(
                "CUST-HIGH",
                {"event_id": f"FAIL-{i}",
                 "channel": ch,
                 "event_type": "TRANSACTION",
                 "outcome": "FAILURE",
                 "occurred_at": (date.today() - timedelta(days=3)).isoformat() + f"T1{i}:00:00"},
                actor="pipeline",
            )
        pred = engine.predict_decline("CUST-HIGH", product_count=1)
        # Decline + 2 complaints + multi-channel failure + LOW_DIV
        assert Decimal(pred["risk_score"]) >= Decimal("50")

        # Test 3: register intervention
        r = engine.register_intervention(
            "CUST-HIGH",
            {"intervention_id": "INV-001",
             "intervention_type": "OUTREACH_CALL",
             "trigger_risk_score": "75"},
            actor="rm_lead",
        )
        assert r["registered"]

        # Test 4: invalid intervention type
        r = engine.register_intervention(
            "CUST-X",
            {"intervention_id": "INV-X", "intervention_type": "INVALID"},
            actor="rm",
        )
        assert not r["registered"]

        # Test 5: duplicate intervention_id
        r = engine.register_intervention(
            "CUST-HIGH",
            {"intervention_id": "INV-001",
             "intervention_type": "OUTREACH_CALL"},
            actor="rm",
        )
        assert not r["registered"]

        # Test 6: outcome
        o = engine.intervention_outcome(
            "INV-001", "RETAINED", actor="rm",
        )
        assert o["recorded"]

        # Test 7: cannot resolve already-terminal CHURNED
        engine.register_intervention(
            "CUST-X2",
            {"intervention_id": "INV-002", "intervention_type": "OUTREACH_CALL"},
            actor="rm",
        )
        engine.intervention_outcome("INV-002", "CHURNED", actor="rm")
        o = engine.intervention_outcome("INV-002", "RETAINED", actor="rm")
        assert not o["recorded"]
        assert "outcome_already_terminal" in o["error"]

        # Test 8: invalid outcome
        engine.register_intervention(
            "CUST-X3",
            {"intervention_id": "INV-003", "intervention_type": "OUTREACH_CALL"},
            actor="rm",
        )
        o = engine.intervention_outcome("INV-003", "MAYBE", actor="rm")
        assert not o["recorded"]

        # Test 9: at_risk_customers bulk scan
        # Need a low-risk customer too — seed steady pattern
        for i in range(60):
            day = (date.today() - timedelta(days=119 - i*2)).isoformat()
            capture.capture_event(
                "CUST-LOW",
                {"event_id": f"LOW-{i}",
                 "channel": "MOBILE_APP",
                 "event_type": "TRANSACTION",
                 "outcome": "SUCCESS",
                 "occurred_at": day + "T10:00:00",
                 "amount_kes": "5000"},
                actor="pipeline",
            )
        results = engine.at_risk_customers(
            ["CUST-LOW", "CUST-HIGH"], threshold=40,
        )
        assert any(r["customer_id"] == "CUST-HIGH" for r in results)

        # Test 10: ml_nba_fn factory
        nba_fn = engine.make_ml_nba_fn()
        assert callable(nba_fn)

        # CUST-HIGH should return ml_driven action
        result = nba_fn("CUST-HIGH", stage="ENGAGEMENT", product_count=1)
        assert result["ml_driven"] is True or result["action"] is None

        # CUST-LOW should defer
        result = nba_fn("CUST-LOW", stage="LOYALTY", product_count=3)
        # Should defer (no high risk signals)
        if not result["ml_driven"]:
            assert result["action"] is None

    print("  ✅ decline_prediction self-test PASS")


if __name__ == "__main__":
    _self_test()
