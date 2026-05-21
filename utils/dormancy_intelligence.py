"""utils.dormancy_intelligence — Dormant Account Management
(Standard #41, v5.53). Volume Six — Dormancy Intelligence.

Per v6 spec §7:
    DormancyIntelligenceEngine: status engine (Cat B, full Python) +
    prediction engine (Cat D, scaffolding with deterministic rule-based
    fallback per Rule 7).

WHAT THIS MODULE SHIPS
----------------------
1. Schema DDL (Cat A): customer.account_dormancy, customer.dormancy_actions,
   performance.dormancy_kpi_targets — exposed via build_schema_ddl()

2. DormancyIntelligenceEngine class with:
   - analyze_dormancy_risk(as_of_date) — classify all accounts by inactivity
     bucket (ACTIVE / WARNING / DORMANT / RESTRICTED)
   - predict_dormancy(account_number, days_ahead=60) — Cat D scaffolding:
     ML hook returns None+reason when no model loaded; rule-based fallback
     score is deterministic and documented inline

3. DEFAULT_DORMANCY_TARGETS / KPI_TARGETS catalog (BSC integration hook)

4. Spec literal thresholds (CBK regulation byte-for-byte):
   - WARNING_THRESHOLD_DAYS = 300
   - DORMANCY_THRESHOLD_DAYS = 365
   - RESTRICTED_THRESHOLD_DAYS = 730

HONESTY DISCIPLINE
------------------
Rule 1 — Standard #11:
  - Decimal-internal for last_balance / average_balance_3m where they
    feed monetary computations
  - last_balance None → status still classifiable from days_inactive

Rule 6 — No privilege escalation:
  - Status defaults to "ACTIVE"; classification only escalates given
    measurable inactivity

Rule 7 (NEW for v6) — No silent ML predictions:
  - predict_dormancy() refuses to predict (returns ml_score=None) when
    no model loaded
  - Rule-based fallback is DETERMINISTIC — same input → same output
  - meta.spec_deviation surfaces the deferred-work note
  - Rule-based scoring components surfaced in meta.fallback_basis (not opaque)
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP, getcontext
from typing import Any, Callable, Dict, List, Optional


logger = logging.getLogger("a2z.dormancy_intelligence")
getcontext().prec = 28

ZERO = Decimal("0")


# ─────────────────────────────────────────────────────────────────────
# Spec literals (v6 §7 #41 — CBK regulation byte-for-byte)
# ─────────────────────────────────────────────────────────────────────

# CBK regulation: 12 months = dormant
DORMANCY_THRESHOLD_DAYS = 365
WARNING_THRESHOLD_DAYS  = 300    # ~2 months warning
RESTRICTED_THRESHOLD_DAYS = 730  # CBK restriction (24 months)

# Status enum
STATUS_ACTIVE     = "ACTIVE"
STATUS_WARNING    = "WARNING"
STATUS_DORMANT    = "DORMANT"
STATUS_RESTRICTED = "RESTRICTED"

ALL_STATUSES = [STATUS_ACTIVE, STATUS_WARNING, STATUS_DORMANT, STATUS_RESTRICTED]

# Action types (for dormancy_actions table)
ACTION_TYPES = ["CALL", "SMS", "EMAIL", "INCENTIVE", "ESCALATION"]

# Risk levels for prediction
RISK_HIGH    = "HIGH"     # score > 70
RISK_MEDIUM  = "MEDIUM"   # 40 < score ≤ 70
RISK_LOW     = "LOW"      # score ≤ 40

# Rule 7 scaffolding marker
SPEC_DEVIATION_NOTE = "ML dormancy-prediction model training is downstream work; v6 ships rule-based score"


# ─────────────────────────────────────────────────────────────────────
# Schema DDL (Cat A)
# ─────────────────────────────────────────────────────────────────────

def build_schema_ddl() -> str:
    """Build CREATE TABLE statements for dormancy schema.

    Spec literal columns preserved byte-for-byte per v6 spec §7 #41.
    """
    return """
-- Customer account dormancy tracking
CREATE TABLE IF NOT EXISTS customer.account_dormancy (
    id                      SERIAL PRIMARY KEY,
    account_number          VARCHAR(20),
    customer_code           VARCHAR(20),
    branch_code             VARCHAR(10),
    rm_code                 VARCHAR(20),
    segment                 VARCHAR(50),
    account_type            VARCHAR(30),
    last_transaction_date   DATE,
    last_balance            NUMERIC(20,2),
    average_balance_3m      NUMERIC(20,2),
    days_inactive           INTEGER,
    dormancy_status         VARCHAR(20),
    days_to_dormancy        INTEGER,
    risk_score              INTEGER,
    created_at              TIMESTAMP DEFAULT NOW(),
    updated_at              TIMESTAMP
);

-- Dormancy action tracking
CREATE TABLE IF NOT EXISTS customer.dormancy_actions (
    id                      SERIAL PRIMARY KEY,
    account_number          VARCHAR(20),
    action_type             VARCHAR(30),
    action_date             DATE,
    performed_by            VARCHAR(50),
    customer_response       VARCHAR(100),
    transaction_occurred    BOOLEAN DEFAULT FALSE,
    transaction_date        DATE,
    follow_up_required      BOOLEAN DEFAULT FALSE,
    follow_up_date          DATE,
    notes                   TEXT,
    created_at              TIMESTAMP
);

-- Dormancy KPI targets (for BSC)
CREATE TABLE IF NOT EXISTS performance.dormancy_kpi_targets (
    id                          SERIAL PRIMARY KEY,
    staff_code                  VARCHAR(20),
    role                        VARCHAR(50),
    period                      VARCHAR(7),
    target_reactivation_rate    DECIMAL(5,2),
    target_dormancy_reduction   DECIMAL(5,2),
    actual_reactivation_rate    DECIMAL(5,2),
    achieved                    BOOLEAN DEFAULT FALSE,
    bonus_earned                DECIMAL(10,2)
);
""".strip()


def ddl_contains_required_columns(ddl: str) -> Dict[str, List[str]]:
    """Audit helper: verify spec-literal columns are present.

    Returns {table_name: [missing columns]} — empty list means complete.
    """
    required = {
        "customer.account_dormancy": [
            "account_number", "customer_code", "branch_code", "rm_code",
            "segment", "account_type", "last_transaction_date",
            "last_balance", "average_balance_3m", "days_inactive",
            "dormancy_status", "days_to_dormancy", "risk_score",
        ],
        "customer.dormancy_actions": [
            "account_number", "action_type", "action_date", "performed_by",
            "customer_response", "transaction_occurred", "transaction_date",
            "follow_up_required", "follow_up_date", "notes",
        ],
        "performance.dormancy_kpi_targets": [
            "staff_code", "role", "period",
            "target_reactivation_rate", "target_dormancy_reduction",
            "actual_reactivation_rate", "achieved", "bonus_earned",
        ],
    }
    out: Dict[str, List[str]] = {}
    for table, cols in required.items():
        # Find table block
        idx = ddl.find(f"CREATE TABLE IF NOT EXISTS {table} (")
        if idx == -1:
            idx = ddl.find(f"CREATE TABLE {table} (")
        if idx == -1:
            out[table] = ["TABLE_NOT_FOUND"]
            continue
        # Extract block to closing );
        end = ddl.find(");", idx)
        block = ddl[idx:end] if end > idx else ddl[idx:]
        missing = [c for c in cols if c not in block]
        out[table] = missing
    return out


# ─────────────────────────────────────────────────────────────────────
# Engine
# ─────────────────────────────────────────────────────────────────────

class DormancyIntelligenceEngine:
    """Dormant account intelligence — status (Cat B) + prediction (Cat D).

    Status engine is fully deterministic Python — classifies accounts by
    days-inactive into the four CBK-regulation buckets.

    Prediction engine follows Rule 7: ML hook is wired but disabled by
    default. When no model loaded, returns ml_score=None plus a rule-based
    score (separately labelled, NEVER substituted silently).
    """

    DORMANCY_THRESHOLD_DAYS   = DORMANCY_THRESHOLD_DAYS
    WARNING_THRESHOLD_DAYS    = WARNING_THRESHOLD_DAYS
    RESTRICTED_THRESHOLD_DAYS = RESTRICTED_THRESHOLD_DAYS

    def __init__(
        self,
        account_lookup_fn:    Optional[Callable[[], List[dict]]] = None,
        feature_lookup_fn:    Optional[Callable[[str], Dict[str, Any]]] = None,
        model_loader_fn:      Optional[Callable[[], Any]] = None,
        action_history_fn:    Optional[Callable[[str], List[dict]]] = None,
    ):
        """All collaborators injectable for testability.

        account_lookup_fn() → list of account dicts with at least:
            account_number, last_transaction_date (YYYY-MM-DD)
        feature_lookup_fn(account_number) → feature dict for prediction
        model_loader_fn() → trained ML model (None in sandbox per Rule 7)
        action_history_fn(account_number) → list of action records
        """
        self._accounts = account_lookup_fn  or (lambda: [])
        self._features = feature_lookup_fn  or (lambda an: {})
        self._model    = model_loader_fn    or (lambda: None)
        self._actions  = action_history_fn  or (lambda an: [])

    # ──────────────────────────────────────────────────────────────────
    # Cat B: deterministic status classification
    # ──────────────────────────────────────────────────────────────────

    def analyze_dormancy_risk(self, as_of_date: Optional[str] = None) -> Dict[str, Any]:
        """Daily job: classify all accounts by inactivity bucket.

        Returns:
            {
              "as_of_date": str,
              "warning":     [account dicts with status fields],
              "dormant":     [...],
              "restricted":  [...],
              "active":      [...] (or count, depending on volume),
              "reactivated": [...],
              "summary": {warning: N, dormant: N, restricted: N, active: N},
              "meta": {...}
            }
        """
        if as_of_date is None:
            as_of_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        try:
            as_of = datetime.strptime(as_of_date, "%Y-%m-%d")
        except ValueError:
            return {"error": f"as_of_date must be YYYY-MM-DD, got {as_of_date!r}"}

        accounts = self._accounts() or []
        results = {
            "warning":     [],
            "dormant":     [],
            "restricted":  [],
            "active":      [],
            "reactivated": [],
        }

        for account in accounts:
            if not isinstance(account, dict):
                continue
            days = self._days_inactive(account, as_of)
            if days is None:
                # Honesty: when last_transaction_date missing, default to
                # ACTIVE bucket but flag in account record (Rule 6 — never
                # silently escalate without observable signal)
                account_out = {**account, "days_inactive": None,
                               "dormancy_status": STATUS_ACTIVE,
                               "_data_quality_note": "no_last_transaction_date"}
                results["active"].append(account_out)
                continue

            status = self._classify(days)
            account_out = {
                **account,
                "days_inactive":     days,
                "dormancy_status":   status,
                "days_to_dormancy":  max(0, self.DORMANCY_THRESHOLD_DAYS - days),
            }

            if status == STATUS_RESTRICTED:
                results["restricted"].append(account_out)
            elif status == STATUS_DORMANT:
                results["dormant"].append(account_out)
            elif status == STATUS_WARNING:
                results["warning"].append(account_out)
            else:
                results["active"].append(account_out)

            # Reactivation detection — was dormant, now had recent activity
            if self._was_dormant_and_reactivated(account):
                results["reactivated"].append(account_out)

        summary = {k: len(v) for k, v in results.items()}

        return {
            "as_of_date":   as_of_date,
            "warning":      results["warning"],
            "dormant":      results["dormant"],
            "restricted":   results["restricted"],
            "active":       results["active"],
            "reactivated":  results["reactivated"],
            "summary":      summary,
            "meta": {
                "warning_threshold_days":     self.WARNING_THRESHOLD_DAYS,
                "dormancy_threshold_days":    self.DORMANCY_THRESHOLD_DAYS,
                "restricted_threshold_days":  self.RESTRICTED_THRESHOLD_DAYS,
                "regulation_basis":           "CBK 12-month dormancy + 24-month restriction",
                "accounts_processed":         len(accounts),
                "generated_at":               datetime.now(timezone.utc).isoformat(),
            },
        }

    def classify_account(self, account: dict, as_of_date: Optional[str] = None) -> Dict[str, Any]:
        """Classify a single account. Returns {status, days_inactive, days_to_dormancy}."""
        if as_of_date is None:
            as_of = datetime.now(timezone.utc)
        else:
            try:
                as_of = datetime.strptime(as_of_date, "%Y-%m-%d")
            except ValueError:
                return {"error": f"invalid as_of_date {as_of_date!r}"}

        days = self._days_inactive(account, as_of)
        if days is None:
            return {
                "status":           STATUS_ACTIVE,
                "days_inactive":    None,
                "days_to_dormancy": None,
                "data_quality_note": "no_last_transaction_date",
            }
        return {
            "status":           self._classify(days),
            "days_inactive":    days,
            "days_to_dormancy": max(0, self.DORMANCY_THRESHOLD_DAYS - days),
        }

    # ──────────────────────────────────────────────────────────────────
    # Cat D: prediction with rule-based fallback (Rule 7)
    # ──────────────────────────────────────────────────────────────────

    def predict_dormancy(
        self, account_number: str, days_ahead: int = 60,
    ) -> Dict[str, Any]:
        """Predict dormancy risk N days ahead.

        Rule 7 application: NEVER silently substitutes rule-based for ML.
        - When no ML model loaded: ml_score=None, reason set, rule_based_score
          surfaced separately
        - When ML model loaded: returns model output + rule_based for comparison

        Returns:
            {
              "account_number": str,
              "ml_score": float | None,         # None when no model
              "ml_level": str | None,
              "rule_based_score": float,         # ALWAYS computed (deterministic)
              "rule_based_level": str,
              "reason": str | None,             # set when ml_score=None
              "meta": {
                "fallback_basis": str,          # what the rule-based uses
                "spec_deviation": str | None,   # set when no model
                "feature_summary": dict,
              }
            }
        """
        if not account_number:
            return {}

        features = self._features(account_number) or {}
        model = self._model()

        # Always compute rule-based for transparency
        rule_score = self._rule_based_dormancy_score(features)
        rule_level = self._level(rule_score)

        if model is None:
            # Rule 7 — refuse to silently substitute
            return {
                "account_number":   account_number,
                "ml_score":         None,
                "ml_level":         None,
                "rule_based_score": rule_score,
                "rule_based_level": rule_level,
                "reason":           "no_ml_model_loaded",
                "meta": {
                    "fallback_basis":   "balance_decline + tx_gap + age_segment + product_type + digital_adoption",
                    "spec_deviation":   SPEC_DEVIATION_NOTE,
                    "feature_summary":  {k: features.get(k) for k in (
                        "balance_decline_pct", "days_since_last_tx",
                        "digital_adoption_score", "product_type", "age_segment",
                    )},
                    "days_ahead":       days_ahead,
                },
            }

        # Production path — ML model present
        try:
            score = float(model.predict(features))
        except Exception as e:
            logger.warning("ML model prediction failed: %s — falling back", e)
            return {
                "account_number":   account_number,
                "ml_score":         None,
                "ml_level":         None,
                "rule_based_score": rule_score,
                "rule_based_level": rule_level,
                "reason":           f"ml_model_error: {type(e).__name__}",
                "meta": {
                    "fallback_basis":   "balance_decline + tx_gap + age_segment + product_type + digital_adoption",
                    "spec_deviation":   SPEC_DEVIATION_NOTE,
                    "days_ahead":       days_ahead,
                },
            }

        return {
            "account_number":   account_number,
            "ml_score":         score,
            "ml_level":         self._level(score),
            "rule_based_score": rule_score,
            "rule_based_level": rule_level,
            "reason":           None,
            "meta": {
                "fallback_basis":   "balance_decline + tx_gap + age_segment + product_type + digital_adoption",
                "spec_deviation":   None,
                "days_ahead":       days_ahead,
            },
        }

    def _rule_based_dormancy_score(self, features: Dict[str, Any]) -> int:
        """Deterministic fallback. Documented logic, no ML.

        Score components (sum capped at 100):
          balance_decline > 30%      → +30
          days_since_last_tx > 45    → +25
          digital_adoption < 0.3     → +20
          product_type == SAVINGS    → +15
          age_segment in YOUTH/STUDENT → +10
        """
        score = 0
        try:
            if float(features.get("balance_decline_pct", 0)) > 0.30:
                score += 30
        except (TypeError, ValueError):
            pass
        try:
            if int(features.get("days_since_last_tx", 0)) > 45:
                score += 25
        except (TypeError, ValueError):
            pass
        try:
            if float(features.get("digital_adoption_score", 1.0)) < 0.3:
                score += 20
        except (TypeError, ValueError):
            pass
        if features.get("product_type") == "SAVINGS":
            score += 15
        if features.get("age_segment") in ("YOUTH", "STUDENT"):
            score += 10
        return min(score, 100)

    def _level(self, score: Optional[float]) -> Optional[str]:
        if score is None:
            return None
        if score > 70:
            return RISK_HIGH
        if score > 40:
            return RISK_MEDIUM
        return RISK_LOW

    # ──────────────────────────────────────────────────────────────────
    # Internal helpers
    # ──────────────────────────────────────────────────────────────────

    def _days_inactive(self, account: dict, as_of: datetime) -> Optional[int]:
        """Days since last transaction. Returns None if date missing."""
        ltd = account.get("last_transaction_date")
        if not ltd:
            return None
        try:
            if isinstance(ltd, str):
                ltd_dt = datetime.strptime(ltd, "%Y-%m-%d")
            elif isinstance(ltd, datetime):
                ltd_dt = ltd
            else:
                return None
            # Strip tz for comparison if needed
            if ltd_dt.tzinfo and not as_of.tzinfo:
                ltd_dt = ltd_dt.replace(tzinfo=None)
            elif as_of.tzinfo and not ltd_dt.tzinfo:
                as_of = as_of.replace(tzinfo=None)
            return max(0, (as_of - ltd_dt).days)
        except (ValueError, TypeError):
            return None

    def _classify(self, days: int) -> str:
        """Map days_inactive to status bucket. CBK-regulation thresholds."""
        if days >= self.RESTRICTED_THRESHOLD_DAYS:
            return STATUS_RESTRICTED
        if days >= self.DORMANCY_THRESHOLD_DAYS:
            return STATUS_DORMANT
        if days >= self.WARNING_THRESHOLD_DAYS:
            return STATUS_WARNING
        return STATUS_ACTIVE

    def _was_dormant_and_reactivated(self, account: dict) -> bool:
        """Was account dormant in last status snapshot, now showing activity?"""
        prev_status = account.get("previous_dormancy_status")
        ltd = account.get("last_transaction_date")
        if not prev_status or not ltd:
            return False
        if prev_status not in (STATUS_DORMANT, STATUS_WARNING):
            return False
        # If last transaction is recent (within 30 days), considered reactivated
        try:
            ltd_dt = datetime.strptime(ltd, "%Y-%m-%d") if isinstance(ltd, str) else ltd
            return (datetime.now() - ltd_dt).days < 30
        except (ValueError, TypeError):
            return False


# ─────────────────────────────────────────────────────────────────────
# Self-test
# ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("A2Z MIS 360 — utils.dormancy_intelligence self-test")

    # ── Spec literals ─────────────────────────────────────────────────
    assert WARNING_THRESHOLD_DAYS == 300
    assert DORMANCY_THRESHOLD_DAYS == 365
    assert RESTRICTED_THRESHOLD_DAYS == 730
    print(f"  ✅ CBK thresholds: warning=300, dormancy=365, restricted=730 days")

    assert STATUS_ACTIVE == "ACTIVE"
    assert STATUS_DORMANT == "DORMANT"
    assert STATUS_RESTRICTED == "RESTRICTED"
    print(f"  ✅ status enum: {ALL_STATUSES}")

    # ── Schema DDL has all required columns ───────────────────────────
    ddl = build_schema_ddl()
    missing = ddl_contains_required_columns(ddl)
    for table, cols in missing.items():
        assert cols == [], f"table {table} missing: {cols}"
    print(f"  ✅ schema DDL: all columns present in 3 tables")

    # ── Empty inputs ──────────────────────────────────────────────────
    eng = DormancyIntelligenceEngine()
    r = eng.analyze_dormancy_risk()
    assert r["summary"]["warning"] == 0
    assert r["summary"]["dormant"] == 0
    assert r["summary"]["restricted"] == 0
    print(f"  ✅ empty accounts → zero counts (no fabrication)")

    # ── Status classification at thresholds ───────────────────────────
    accounts = [
        {"account_number": "A001", "last_transaction_date": "2025-12-29"},  # ~120 days → ACTIVE
        {"account_number": "A002", "last_transaction_date": "2025-06-29"},  # ~304 days → WARNING
        {"account_number": "A003", "last_transaction_date": "2025-04-29"},  # ~365 days → DORMANT
        {"account_number": "A004", "last_transaction_date": "2024-04-29"},  # ~730 days → RESTRICTED
    ]
    eng2 = DormancyIntelligenceEngine(account_lookup_fn=lambda: accounts)
    r = eng2.analyze_dormancy_risk("2026-04-29")
    assert r["summary"]["active"]     == 1
    assert r["summary"]["warning"]    == 1
    assert r["summary"]["dormant"]    == 1
    assert r["summary"]["restricted"] == 1
    print(f"  ✅ classification: active=1, warning=1, dormant=1, restricted=1")

    # ── Boundary behavior at exactly threshold ────────────────────────
    boundary = [{"account_number": "B1", "last_transaction_date": "2025-05-04"}]   # exactly 360 days from 2026-04-29
    eng_b = DormancyIntelligenceEngine(account_lookup_fn=lambda: boundary)
    r = eng_b.classify_account(boundary[0], "2026-04-29")
    # 360 days < 365 → still WARNING (not yet DORMANT)
    assert r["status"] == STATUS_WARNING
    # At exactly 365 days
    boundary2 = [{"account_number": "B2", "last_transaction_date": "2025-04-29"}]   # 365 days exactly
    r2 = eng_b.classify_account(boundary2[0], "2026-04-29")
    assert r2["status"] == STATUS_DORMANT
    print(f"  ✅ boundary: 360d=WARNING, 365d=DORMANT (strict ≥)")

    # ── Missing date → ACTIVE with note (Rule 6 — no escalation without signal) ──
    no_date = [{"account_number": "X1"}]    # no last_transaction_date
    eng_nd = DormancyIntelligenceEngine(account_lookup_fn=lambda: no_date)
    r = eng_nd.analyze_dormancy_risk("2026-04-29")
    assert r["summary"]["active"] == 1
    assert r["active"][0]["_data_quality_note"] == "no_last_transaction_date"
    print(f"  ✅ missing date → ACTIVE with data_quality_note (Rule 6)")

    # ── days_to_dormancy field ────────────────────────────────────────
    r = eng2.analyze_dormancy_risk("2026-04-29")
    warning_account = r["warning"][0]
    assert "days_to_dormancy" in warning_account
    assert warning_account["days_to_dormancy"] >= 0
    assert warning_account["days_to_dormancy"] < 365
    print(f"  ✅ days_to_dormancy computed: warning account has {warning_account['days_to_dormancy']} days")

    # ── Cat D: predict_dormancy with NO model (Rule 7) ────────────────
    features_high_risk = {
        "balance_decline_pct":     0.50,    # > 30% → +30
        "days_since_last_tx":      60,      # > 45 → +25
        "digital_adoption_score":  0.10,    # < 0.3 → +20
        "product_type":            "SAVINGS",  # +15
        "age_segment":             "YOUTH",  # +10
    }
    eng_pred = DormancyIntelligenceEngine(
        feature_lookup_fn=lambda an: features_high_risk,
    )
    r = eng_pred.predict_dormancy("A001")
    assert r["ml_score"] is None
    assert r["ml_level"] is None
    assert r["reason"] == "no_ml_model_loaded"
    assert r["rule_based_score"] == 100    # all components fire = capped at 100
    assert r["rule_based_level"] == RISK_HIGH
    assert r["meta"]["spec_deviation"] is not None
    assert "downstream work" in r["meta"]["spec_deviation"]
    print(f"  ✅ predict_dormancy (no model): ml=None, rule_based={r['rule_based_score']}, "
          f"level={r['rule_based_level']}, spec_deviation surfaced")

    # ── Cat D: rule-based score is DETERMINISTIC (Rule 7) ────────────
    r1 = eng_pred.predict_dormancy("A001")
    r2 = eng_pred.predict_dormancy("A001")
    assert r1["rule_based_score"] == r2["rule_based_score"]
    assert r1["rule_based_level"] == r2["rule_based_level"]
    print(f"  ✅ rule-based score is deterministic (same input → same output)")

    # ── Cat D: low-risk feature set ───────────────────────────────────
    features_low = {
        "balance_decline_pct":     0.05,    # not > 0.30 → 0
        "days_since_last_tx":      10,      # not > 45 → 0
        "digital_adoption_score":  0.95,    # not < 0.3 → 0
        "product_type":            "CURRENT",  # not SAVINGS → 0
        "age_segment":             "ADULT",  # not YOUTH/STUDENT → 0
    }
    eng_low = DormancyIntelligenceEngine(feature_lookup_fn=lambda an: features_low)
    r = eng_low.predict_dormancy("A001")
    assert r["rule_based_score"] == 0
    assert r["rule_based_level"] == RISK_LOW
    print(f"  ✅ low-risk features → rule_based=0, level=LOW")

    # ── Cat D: ML model loaded → basis is ML ─────────────────────────
    class _FakeModel:
        def predict(self, features):
            return 85.0    # simulated ML score
    eng_ml = DormancyIntelligenceEngine(
        feature_lookup_fn=lambda an: features_high_risk,
        model_loader_fn=lambda: _FakeModel(),
    )
    r = eng_ml.predict_dormancy("A001")
    assert r["ml_score"] == 85.0
    assert r["ml_level"] == RISK_HIGH
    assert r["reason"] is None
    assert r["meta"]["spec_deviation"] is None
    # rule_based still computed for comparison
    assert r["rule_based_score"] == 100
    print(f"  ✅ ML model loaded: ml_score={r['ml_score']}, rule-based still surfaced for comparison")

    # ── Cat D: ML model failure → fallback with explicit reason ──────
    class _FailingModel:
        def predict(self, features):
            raise RuntimeError("model corrupted")
    eng_fail = DormancyIntelligenceEngine(
        feature_lookup_fn=lambda an: features_high_risk,
        model_loader_fn=lambda: _FailingModel(),
    )
    r = eng_fail.predict_dormancy("A001")
    assert r["ml_score"] is None
    assert "ml_model_error" in r["reason"]
    assert "RuntimeError" in r["reason"]
    print(f"  ✅ ML failure → fallback with explicit reason: {r['reason']}")

    # ── Empty account_number ─────────────────────────────────────────
    r = eng_pred.predict_dormancy("")
    assert r == {}
    print(f"  ✅ empty account_number → {{}}")

    # ── Tampering check: SPEC_DEVIATION_NOTE byte-for-byte ───────────
    canonical = "ML dormancy-prediction model training is downstream work; v6 ships rule-based score"
    assert SPEC_DEVIATION_NOTE == canonical
    print(f"  ✅ SPEC_DEVIATION_NOTE preserved: '{SPEC_DEVIATION_NOTE[:60]}...'")

    print("\n  ALL TESTS PASSED")
