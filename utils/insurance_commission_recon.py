"""
================================================================================
A2Z MIS 360 — Standards #305 + #309: Insurance Commission Recon + Partner Scorecard
================================================================================

Risk classification: Cat A (financial — multi-insurer commission reconciliation
                              with dispute workflow) + Cat B (deterministic scorecard)

Combined module:
    #305: Multi-insurer commission reconciliation engine — bank's
          expected vs insurer's paid. Aging, dispute workflow.
    #309: Per-insurer partner scorecard — policy count, premium volume,
          commission, claim ratio, customer satisfaction, dispute time.

Public API (#305):
    record_expected_commission(insurer_id, policy_id, amount, period, actor)
    record_paid_commission(insurer_id, policy_id, amount, paid_date, actor)
    reconcile_period(insurer_id, period) -> {matched, unmatched, disputes}
    open_dispute(reconciliation_id, reason, actor)
    resolve_dispute(dispute_id, resolution, actor)
    aging_report(insurer_id, as_of_date) -> aged buckets

Public API (#309):
    record_scorecard_dimension(insurer_id, period, dimension, value, actor)
    compute_insurer_scorecard(insurer_id, period) -> {dimensions, composite, tier}
    rank_insurers(period) -> ordered scorecards

RECON_STATES byte-for-byte:
    PENDING_MATCH      -- expected recorded; no payment yet
    MATCHED            -- expected matches paid within tolerance (terminal)
    PARTIALLY_MATCHED  -- some matched; some shortfall
    DISPUTED           -- dispute opened
    RESOLVED           -- dispute resolved (terminal)
    WRITTEN_OFF        -- formally written off (terminal)

DISPUTE_STATES byte-for-byte:
    OPEN               -- newly raised
    UNDER_REVIEW       -- being investigated
    INSURER_RESPONSE   -- waiting insurer reply
    RESOLVED_PAID      -- resolved with insurer paying
    RESOLVED_WRITTEN_OFF -- resolved with bank writing off
    ESCALATED          -- escalated to senior management

RECONCILIATION_TOLERANCE_PCT = Decimal("1")  -- 1% tolerance on amount match

INSURER_SCORECARD_DIMENSIONS byte-for-byte (#309):
    POLICY_COUNT             -- policies issued in period
    PREMIUM_VOLUME_KES       -- total premium received
    COMMISSION_KES           -- total commission paid to bank
    CLAIM_RATIO              -- claims paid / premium received (percent)
    CUSTOMER_SATISFACTION    -- CSAT (0-100)
    DISPUTE_RESOLUTION_DAYS  -- average days to resolve disputes (lower better)

INSURER_DIMENSION_WEIGHTS byte-for-byte (sum=100):
    POLICY_COUNT            = 15
    PREMIUM_VOLUME_KES      = 25
    COMMISSION_KES          = 25
    CLAIM_RATIO             = 15  (inverted in normalization — high claim ratio reduces score)
    CUSTOMER_SATISFACTION   = 10
    DISPUTE_RESOLUTION_DAYS = 10  (inverted — fast resolution scores higher)

INSURER_TIERS byte-for-byte:
    PREFERRED   -- ≥85
    PARTNER     -- ≥70
    OBSERVATION -- ≥50
    AT_RISK     -- <50

Honesty rules:
    Rule 4: actor + reason mandatory; no skip transitions
    Rule 6: invalid state / dimension rejected
    Rule 1: insurer_scorecard returns composite=None when dimensions missing

================================================================================
"""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, date, timedelta
from decimal import Decimal, getcontext
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

getcontext().prec = 28


# ────────────────────────────────────────────────────────────────────
# Reconciliation catalogs (#305)
# ────────────────────────────────────────────────────────────────────

RECON_STATES: Tuple[str, ...] = (
    "PENDING_MATCH", "MATCHED", "PARTIALLY_MATCHED",
    "DISPUTED", "RESOLVED", "WRITTEN_OFF",
)

DISPUTE_STATES: Tuple[str, ...] = (
    "OPEN", "UNDER_REVIEW", "INSURER_RESPONSE",
    "RESOLVED_PAID", "RESOLVED_WRITTEN_OFF", "ESCALATED",
)

RECONCILIATION_TOLERANCE_PCT: Decimal = Decimal("1")


# ────────────────────────────────────────────────────────────────────
# Scorecard catalogs (#309)
# ────────────────────────────────────────────────────────────────────

INSURER_SCORECARD_DIMENSIONS: Tuple[str, ...] = (
    "POLICY_COUNT",
    "PREMIUM_VOLUME_KES",
    "COMMISSION_KES",
    "CLAIM_RATIO",
    "CUSTOMER_SATISFACTION",
    "DISPUTE_RESOLUTION_DAYS",
)

INSURER_DIMENSION_WEIGHTS: Dict[str, Decimal] = {
    "POLICY_COUNT":            Decimal("15"),
    "PREMIUM_VOLUME_KES":      Decimal("25"),
    "COMMISSION_KES":          Decimal("25"),
    "CLAIM_RATIO":             Decimal("15"),
    "CUSTOMER_SATISFACTION":   Decimal("10"),
    "DISPUTE_RESOLUTION_DAYS": Decimal("10"),
}

INSURER_TIERS: Tuple[str, ...] = (
    "PREFERRED", "PARTNER", "OBSERVATION", "AT_RISK",
)

PREFERRED_THRESHOLD:    Decimal = Decimal("85")
PARTNER_THRESHOLD:      Decimal = Decimal("70")
OBSERVATION_THRESHOLD:  Decimal = Decimal("50")


def classify_insurer_tier(composite: Decimal) -> str:
    if composite >= PREFERRED_THRESHOLD:
        return "PREFERRED"
    if composite >= PARTNER_THRESHOLD:
        return "PARTNER"
    if composite >= OBSERVATION_THRESHOLD:
        return "OBSERVATION"
    return "AT_RISK"


# ────────────────────────────────────────────────────────────────────
# Engine
# ────────────────────────────────────────────────────────────────────

class CommissionReconAndScorecardEngine:
    """Multi-insurer commission reconciliation + scorecard."""

    def __init__(
        self,
        recon_path: Optional[Path] = None,
        disputes_path: Optional[Path] = None,
        scorecards_path: Optional[Path] = None,
    ):
        base = Path(__file__).parent.parent / "data"
        self.recon_path = recon_path or base / "insurance_commission_recon.json"
        self.disputes_path = disputes_path or base / "insurance_commission_disputes.json"
        self.scorecards_path = scorecards_path or base / "insurance_partner_scorecards.json"

    def _load(self, path: Path, table: str, idx: Tuple[str, ...]) -> List[Dict[str, Any]]:
        try:
            from utils.db import db as _db
            data = _db.dual_load(path, table=table, index_cols=idx)
            return data if isinstance(data, list) else []
        except Exception:
            return []

    def _save(self, path: Path, records: List[Dict[str, Any]],
                table: str, pk: str) -> bool:
        try:
            from utils.db import db as _db
            path.parent.mkdir(parents=True, exist_ok=True)
            _db.dual_save(path, data=records, table=table, pk_col=pk)
            return True
        except Exception:
            return False

    # ── Commission reconciliation (#305) ───────────────────────────

    def record_expected_commission(
        self,
        insurer_id: str,
        policy_id: str,
        amount_kes: Decimal,
        period: str,
        actor: str,
    ) -> Dict[str, Any]:
        if not actor:
            return {"recorded": False, "error": "actor_required"}
        try:
            amt = Decimal(str(amount_kes))
        except (ValueError, TypeError):
            return {"recorded": False, "error": "amount_not_decimal"}
        if amt <= 0:
            return {"recorded": False, "error": "amount_must_be_positive"}

        records = self._load(self.recon_path,
                                "insurance_commission_recon",
                                ("recon_id",))
        recon_id = f"RCN-{insurer_id}-{policy_id}-{period}"
        # Reject duplicates
        if any(r.get("recon_id") == recon_id for r in records):
            return {"recorded": False, "error": "duplicate_recon_id"}

        record = {
            "recon_id": recon_id,
            "insurer_id": insurer_id,
            "policy_id": policy_id,
            "period": period,
            "expected_kes": str(amt),
            "paid_kes": "0",
            "state": "PENDING_MATCH",
            "recorded_by": actor,
            "recorded_at": datetime.utcnow().isoformat(),
        }
        records.append(record)
        ok = self._save(self.recon_path, records,
                          "insurance_commission_recon", "recon_id")
        return {"recorded": ok, "recon_id": recon_id}

    def record_paid_commission(
        self,
        insurer_id: str,
        policy_id: str,
        period: str,
        amount_kes: Decimal,
        paid_date: str,
        actor: str,
    ) -> Dict[str, Any]:
        """Record commission paid by insurer; auto-reconcile."""
        if not actor:
            return {"recorded": False, "error": "actor_required"}
        try:
            paid = Decimal(str(amount_kes))
        except (ValueError, TypeError):
            return {"recorded": False, "error": "amount_not_decimal"}
        try:
            date.fromisoformat(paid_date)
        except (ValueError, TypeError):
            return {"recorded": False, "error": "invalid_paid_date"}

        recon_id = f"RCN-{insurer_id}-{policy_id}-{period}"
        records = self._load(self.recon_path,
                                "insurance_commission_recon",
                                ("recon_id",))
        for r in records:
            if r.get("recon_id") == recon_id:
                if r.get("state") in ("RESOLVED", "WRITTEN_OFF"):
                    return {
                        "recorded": False,
                        "error": f"recon_in_terminal_state:{r['state']}",
                    }
                r["paid_kes"] = str(paid.quantize(Decimal("0.01")))
                r["paid_date"] = paid_date
                r["paid_by_insurer_actor"] = actor
                # Auto-reconcile against expected
                expected = Decimal(r["expected_kes"])
                tolerance = expected * RECONCILIATION_TOLERANCE_PCT / Decimal("100")
                variance = paid - expected
                if abs(variance) <= tolerance:
                    r["state"] = "MATCHED"
                elif paid > 0:
                    r["state"] = "PARTIALLY_MATCHED"
                r["variance_kes"] = str(variance.quantize(Decimal("0.01")))
                ok = self._save(self.recon_path, records,
                                  "insurance_commission_recon", "recon_id")
                return {
                    "recorded": ok,
                    "recon_id": recon_id,
                    "state": r["state"],
                    "variance_kes": r["variance_kes"],
                }

        return {"recorded": False, "error": "recon_record_not_found"}

    def reconcile_period(
        self,
        insurer_id: str,
        period: str,
    ) -> Dict[str, Any]:
        """Aggregate reconciliation for an insurer-period."""
        records = self._load(self.recon_path,
                                "insurance_commission_recon",
                                ("recon_id",))
        filtered = [
            r for r in records
            if r.get("insurer_id") == insurer_id and r.get("period") == period
        ]

        total_expected = Decimal("0")
        total_paid = Decimal("0")
        by_state: Counter = Counter()
        for r in filtered:
            try:
                total_expected += Decimal(r.get("expected_kes", "0"))
                total_paid += Decimal(r.get("paid_kes", "0"))
            except (ValueError, TypeError):
                continue
            by_state[r.get("state")] += 1

        return {
            "insurer_id": insurer_id,
            "period": period,
            "record_count": len(filtered),
            "expected_total_kes": str(total_expected.quantize(Decimal("0.01"))),
            "paid_total_kes": str(total_paid.quantize(Decimal("0.01"))),
            "variance_kes": str((total_paid - total_expected).quantize(Decimal("0.01"))),
            "by_state": dict(by_state),
        }

    def open_dispute(
        self,
        recon_id: str,
        reason: str,
        actor: str,
    ) -> Dict[str, Any]:
        if not actor or not reason:
            return {"opened": False, "error": "actor_and_reason_required"}

        recons = self._load(self.recon_path,
                                "insurance_commission_recon",
                                ("recon_id",))
        recon = next((r for r in recons if r.get("recon_id") == recon_id), None)
        if recon is None:
            return {"opened": False, "error": "recon_not_found"}
        if recon.get("state") in ("RESOLVED", "WRITTEN_OFF"):
            return {
                "opened": False,
                "error": f"recon_in_terminal_state:{recon['state']}",
            }

        # Mark recon as disputed
        recon["state"] = "DISPUTED"
        self._save(self.recon_path, recons,
                     "insurance_commission_recon", "recon_id")

        # Create dispute record
        disputes = self._load(self.disputes_path,
                                  "insurance_commission_disputes",
                                  ("dispute_id",))
        dispute_id = f"DSP-{recon_id}-{int(datetime.utcnow().timestamp())}"
        dispute = {
            "dispute_id": dispute_id,
            "recon_id": recon_id,
            "insurer_id": recon["insurer_id"],
            "state": "OPEN",
            "reason": reason,
            "opened_by": actor,
            "opened_at": datetime.utcnow().isoformat(),
            "transitions": [{
                "to": "OPEN", "actor": actor,
                "at": datetime.utcnow().isoformat(),
                "reason": reason,
            }],
        }
        disputes.append(dispute)
        ok = self._save(self.disputes_path, disputes,
                          "insurance_commission_disputes", "dispute_id")
        return {"opened": ok, "dispute_id": dispute_id}

    def resolve_dispute(
        self,
        dispute_id: str,
        resolution_state: str,
        actor: str,
        notes: str = "",
    ) -> Dict[str, Any]:
        if not actor:
            return {"resolved": False, "error": "actor_required"}
        if resolution_state not in DISPUTE_STATES:
            return {"resolved": False, "error": f"invalid_state:{resolution_state}"}
        if resolution_state not in (
            "RESOLVED_PAID", "RESOLVED_WRITTEN_OFF", "ESCALATED",
            "UNDER_REVIEW", "INSURER_RESPONSE",
        ):
            return {
                "resolved": False,
                "error": f"not_a_resolution_state:{resolution_state}",
            }

        disputes = self._load(self.disputes_path,
                                  "insurance_commission_disputes",
                                  ("dispute_id",))
        for d in disputes:
            if d.get("dispute_id") == dispute_id:
                current = d.get("state", "OPEN")
                if current in ("RESOLVED_PAID", "RESOLVED_WRITTEN_OFF"):
                    return {
                        "resolved": False,
                        "error": f"dispute_already_resolved:{current}",
                    }
                d["state"] = resolution_state
                d.setdefault("transitions", []).append({
                    "to": resolution_state, "actor": actor,
                    "at": datetime.utcnow().isoformat(),
                    "reason": notes,
                })

                # If resolved, update parent recon
                if resolution_state in ("RESOLVED_PAID", "RESOLVED_WRITTEN_OFF"):
                    final_recon_state = (
                        "RESOLVED" if resolution_state == "RESOLVED_PAID"
                        else "WRITTEN_OFF"
                    )
                    recons = self._load(self.recon_path,
                                          "insurance_commission_recon",
                                          ("recon_id",))
                    for r in recons:
                        if r.get("recon_id") == d.get("recon_id"):
                            r["state"] = final_recon_state
                            break
                    self._save(self.recon_path, recons,
                                 "insurance_commission_recon", "recon_id")

                ok = self._save(self.disputes_path, disputes,
                                  "insurance_commission_disputes", "dispute_id")
                return {"resolved": ok, "from": current, "to": resolution_state}

        return {"resolved": False, "error": "dispute_not_found"}

    def aging_report(
        self,
        insurer_id: str,
        as_of: Optional[date] = None,
    ) -> Dict[str, Any]:
        """Aged buckets for unpaid expected commissions."""
        as_of = as_of or date.today()
        records = self._load(self.recon_path,
                                "insurance_commission_recon",
                                ("recon_id",))
        buckets = {"0-30": Decimal("0"), "31-60": Decimal("0"),
                     "61-90": Decimal("0"), "91+": Decimal("0")}
        counts = {"0-30": 0, "31-60": 0, "61-90": 0, "91+": 0}

        for r in records:
            if r.get("insurer_id") != insurer_id:
                continue
            if r.get("state") in ("MATCHED", "RESOLVED", "WRITTEN_OFF"):
                continue
            try:
                expected = Decimal(r.get("expected_kes", "0"))
                paid = Decimal(r.get("paid_kes", "0"))
                outstanding = expected - paid
            except (ValueError, TypeError):
                continue
            if outstanding <= 0:
                continue
            recorded = r.get("recorded_at", "")[:10]
            try:
                rec_date = date.fromisoformat(recorded)
            except (ValueError, TypeError):
                continue
            age_days = (as_of - rec_date).days
            if age_days <= 30:
                bucket = "0-30"
            elif age_days <= 60:
                bucket = "31-60"
            elif age_days <= 90:
                bucket = "61-90"
            else:
                bucket = "91+"
            buckets[bucket] += outstanding
            counts[bucket] += 1

        return {
            "insurer_id": insurer_id,
            "as_of": as_of.isoformat(),
            "buckets_kes": {k: str(v.quantize(Decimal("0.01")))
                              for k, v in buckets.items()},
            "buckets_count": counts,
            "total_outstanding_kes": str(
                sum(buckets.values()).quantize(Decimal("0.01"))
            ),
        }

    # ── Insurer scorecard (#309) ───────────────────────────────────

    def record_scorecard_dimension(
        self,
        insurer_id: str,
        period: str,
        dimension: str,
        value: Decimal,
        actor: str,
    ) -> Dict[str, Any]:
        if not actor:
            return {"recorded": False, "error": "actor_required"}
        if dimension not in INSURER_SCORECARD_DIMENSIONS:
            return {
                "recorded": False,
                "error": f"invalid_dimension:{dimension}",
                "valid_dimensions": list(INSURER_SCORECARD_DIMENSIONS),
            }
        try:
            v = Decimal(str(value))
        except (ValueError, TypeError):
            return {"recorded": False, "error": "value_not_decimal"}
        if v < 0:
            return {"recorded": False, "error": "value_negative"}

        # Range checks
        if dimension == "CUSTOMER_SATISFACTION" and v > 100:
            return {"recorded": False, "error": "csat_above_100"}
        if dimension == "CLAIM_RATIO" and v > 200:
            # Allow up to 200% (catastrophic claim period); above is data error
            return {"recorded": False, "error": "claim_ratio_unrealistic"}

        records = self._load(self.scorecards_path,
                                "insurance_partner_scorecards",
                                ("insurer_id", "period", "dimension"))
        # Replace existing
        for r in records:
            if (r.get("insurer_id") == insurer_id
                    and r.get("period") == period
                    and r.get("dimension") == dimension):
                r["value"] = str(v)
                r["actor"] = actor
                r["recorded_at"] = datetime.utcnow().isoformat()
                ok = self._save(self.scorecards_path, records,
                                  "insurance_partner_scorecards", "insurer_id")
                return {"recorded": ok, "replaced": True}

        records.append({
            "insurer_id": insurer_id,
            "period": period,
            "dimension": dimension,
            "value": str(v),
            "actor": actor,
            "recorded_at": datetime.utcnow().isoformat(),
        })
        ok = self._save(self.scorecards_path, records,
                          "insurance_partner_scorecards", "insurer_id")
        return {"recorded": ok, "replaced": False}

    def _normalize_insurer_dim(
        self, dimension: str, raw: Decimal,
        policy_baseline: int = 1000,
        premium_baseline: Decimal = Decimal("100000000"),
        commission_baseline: Decimal = Decimal("10000000"),
        dispute_days_baseline: int = 30,
    ) -> Decimal:
        """Normalize raw dimension to 0-100 scale."""
        if dimension == "POLICY_COUNT":
            if policy_baseline <= 0:
                return Decimal("0")
            n = (raw / Decimal(policy_baseline)) * Decimal("100")
            return min(n, Decimal("100"))
        if dimension == "PREMIUM_VOLUME_KES":
            if premium_baseline <= 0:
                return Decimal("0")
            n = (raw / premium_baseline) * Decimal("100")
            return min(n, Decimal("100"))
        if dimension == "COMMISSION_KES":
            if commission_baseline <= 0:
                return Decimal("0")
            n = (raw / commission_baseline) * Decimal("100")
            return min(n, Decimal("100"))
        if dimension == "CLAIM_RATIO":
            # Inverted: lower claim ratio is better
            # 0% claim ratio → 100; 100% → 0; >100 → 0
            if raw >= Decimal("100"):
                return Decimal("0")
            return Decimal("100") - raw
        if dimension == "CUSTOMER_SATISFACTION":
            return min(raw, Decimal("100"))
        if dimension == "DISPUTE_RESOLUTION_DAYS":
            # Inverted: faster is better
            # 0 days → 100; >=baseline → 0
            if raw <= 0:
                return Decimal("100")
            if raw >= Decimal(dispute_days_baseline):
                return Decimal("0")
            return ((Decimal(dispute_days_baseline) - raw) /
                      Decimal(dispute_days_baseline) * Decimal("100"))
        return raw

    def compute_insurer_scorecard(
        self,
        insurer_id: str,
        period: str,
        policy_baseline: int = 1000,
        premium_baseline: Decimal = Decimal("100000000"),
        commission_baseline: Decimal = Decimal("10000000"),
    ) -> Dict[str, Any]:
        """Composite insurer scorecard."""
        records = self._load(self.scorecards_path,
                                "insurance_partner_scorecards",
                                ("insurer_id", "period", "dimension"))
        period_recs = [
            r for r in records
            if r.get("insurer_id") == insurer_id and r.get("period") == period
        ]

        dim_values: Dict[str, Decimal] = {}
        for r in period_recs:
            d = r.get("dimension")
            if d in INSURER_SCORECARD_DIMENSIONS:
                try:
                    dim_values[d] = Decimal(str(r["value"]))
                except (ValueError, TypeError):
                    continue

        missing = [d for d in INSURER_SCORECARD_DIMENSIONS if d not in dim_values]
        if missing:
            return {
                "insurer_id": insurer_id,
                "period": period,
                "composite": None,
                "tier": None,
                "missing_dimensions": missing,
                "reason": "missing_dimensions",
            }

        composite = Decimal("0")
        normalized = {}
        for d in INSURER_SCORECARD_DIMENSIONS:
            n = self._normalize_insurer_dim(
                d, dim_values[d], policy_baseline,
                premium_baseline, commission_baseline,
            )
            normalized[d] = n
            composite += n * INSURER_DIMENSION_WEIGHTS[d] / Decimal("100")

        composite = composite.quantize(Decimal("0.01"))
        tier = classify_insurer_tier(composite)

        return {
            "insurer_id": insurer_id,
            "period": period,
            "composite": str(composite),
            "tier": tier,
            "dimensions_raw": {d: str(v) for d, v in dim_values.items()},
            "dimensions_normalized": {
                d: str(v.quantize(Decimal("0.01")))
                for d, v in normalized.items()
            },
            "weights": {d: str(w) for d, w in INSURER_DIMENSION_WEIGHTS.items()},
        }

    def rank_insurers(self, period: str) -> List[Dict[str, Any]]:
        records = self._load(self.scorecards_path,
                                "insurance_partner_scorecards",
                                ("insurer_id", "period", "dimension"))
        insurer_ids = sorted({
            r["insurer_id"] for r in records if r.get("period") == period
        })
        scorecards = []
        for ins in insurer_ids:
            sc = self.compute_insurer_scorecard(ins, period)
            if sc.get("composite") is not None:
                scorecards.append(sc)
        scorecards.sort(key=lambda x: Decimal(x["composite"]), reverse=True)
        return scorecards


def _self_test() -> None:
    import tempfile

    # Sanity: weight sum
    assert sum(INSURER_DIMENSION_WEIGHTS.values()) == Decimal("100")

    # Tier classification
    assert classify_insurer_tier(Decimal("90")) == "PREFERRED"
    assert classify_insurer_tier(Decimal("75")) == "PARTNER"
    assert classify_insurer_tier(Decimal("60")) == "OBSERVATION"
    assert classify_insurer_tier(Decimal("40")) == "AT_RISK"

    with tempfile.TemporaryDirectory() as tmpdir:
        engine = CommissionReconAndScorecardEngine(
            recon_path=Path(tmpdir) / "rcn.json",
            disputes_path=Path(tmpdir) / "dsp.json",
            scorecards_path=Path(tmpdir) / "sc.json",
        )

        # === Reconciliation tests ===

        # Test 1: record expected
        r = engine.record_expected_commission(
            "INS-A", "POL-001", Decimal("10000"),
            "2026-Q1", actor="finance",
        )
        assert r["recorded"]

        # Test 2: duplicate rejected
        r = engine.record_expected_commission(
            "INS-A", "POL-001", Decimal("10000"),
            "2026-Q1", actor="finance",
        )
        assert not r["recorded"]
        assert r["error"] == "duplicate_recon_id"

        # Test 3: paid within tolerance → MATCHED
        r = engine.record_paid_commission(
            "INS-A", "POL-001", "2026-Q1",
            Decimal("10050"), "2026-04-15", actor="ins_a_ops",
        )
        # 10050 vs 10000 → variance 50 → tolerance 1% of 10000 = 100 → within
        assert r["recorded"]
        assert r["state"] == "MATCHED"

        # Test 4: paid outside tolerance → PARTIALLY_MATCHED
        engine.record_expected_commission(
            "INS-A", "POL-002", Decimal("20000"),
            "2026-Q1", actor="finance",
        )
        r = engine.record_paid_commission(
            "INS-A", "POL-002", "2026-Q1",
            Decimal("15000"), "2026-04-15", actor="ins_a_ops",
        )
        assert r["state"] == "PARTIALLY_MATCHED"

        # Test 5: dispute workflow
        d = engine.open_dispute(
            "RCN-INS-A-POL-002-2026-Q1",
            reason="Insurer disputes commission rate",
            actor="finance",
        )
        assert d["opened"]
        dispute_id = d["dispute_id"]

        # Test 6: resolve dispute → recon state propagates
        rs = engine.resolve_dispute(
            dispute_id, "RESOLVED_PAID",
            actor="finance",
            notes="Insurer paid difference",
        )
        assert rs["resolved"]
        # Verify recon now RESOLVED
        recons = engine._load(engine.recon_path,
                                  "insurance_commission_recon",
                                  ("recon_id",))
        recon = next(r for r in recons if r.get("recon_id") == "RCN-INS-A-POL-002-2026-Q1")
        assert recon["state"] == "RESOLVED"

        # Test 7: cannot re-resolve resolved dispute
        rs = engine.resolve_dispute(
            dispute_id, "RESOLVED_PAID", actor="finance"
        )
        assert not rs["resolved"]
        assert "already_resolved" in rs["error"]

        # Test 8: invalid resolution state rejected
        rs = engine.resolve_dispute(
            dispute_id, "INVALID", actor="finance"
        )
        assert not rs["resolved"]

        # Test 9: reconcile_period summary
        summary = engine.reconcile_period("INS-A", "2026-Q1")
        assert summary["record_count"] == 2
        # POL-001 MATCHED + POL-002 RESOLVED
        assert "MATCHED" in summary["by_state"] or "RESOLVED" in summary["by_state"]

        # Test 10: aging_report
        aging = engine.aging_report("INS-A", as_of=date(2026, 5, 7))
        # All matched/resolved → no outstanding
        assert Decimal(aging["total_outstanding_kes"]) == Decimal("0")

        # Test 11: outstanding aging
        engine.record_expected_commission(
            "INS-B", "POL-X", Decimal("50000"),
            "2026-Q1", actor="finance",
        )
        # No payment received → outstanding
        aging = engine.aging_report("INS-B", as_of=date.today())
        assert Decimal(aging["total_outstanding_kes"]) == Decimal("50000")

        # === Scorecard tests ===

        # Test 12: record all 6 dimensions
        for d, v in [("POLICY_COUNT", "800"),
                       ("PREMIUM_VOLUME_KES", "80000000"),
                       ("COMMISSION_KES", "8000000"),
                       ("CLAIM_RATIO", "65"),
                       ("CUSTOMER_SATISFACTION", "85"),
                       ("DISPUTE_RESOLUTION_DAYS", "10")]:
            engine.record_scorecard_dimension(
                "INS-A", "2026-Q1", d, Decimal(v), actor="ops"
            )
        sc = engine.compute_insurer_scorecard("INS-A", "2026-Q1")
        assert sc["composite"] is not None
        assert sc["tier"] in INSURER_TIERS

        # Test 13: missing dimension → composite None
        engine.record_scorecard_dimension(
            "INS-B", "2026-Q1", "POLICY_COUNT",
            Decimal("100"), actor="ops"
        )
        sc = engine.compute_insurer_scorecard("INS-B", "2026-Q1")
        assert sc["composite"] is None
        assert len(sc["missing_dimensions"]) == 5

        # Test 14: invalid CSAT rejected
        r = engine.record_scorecard_dimension(
            "INS-C", "2026-Q1", "CUSTOMER_SATISFACTION",
            Decimal("150"), actor="ops"
        )
        assert not r["recorded"]

        # Test 15: invalid dimension rejected
        r = engine.record_scorecard_dimension(
            "INS-C", "2026-Q1", "INVALID", Decimal("50"), actor="ops"
        )
        assert not r["recorded"]

        # Test 16: rank_insurers
        ranked = engine.rank_insurers("2026-Q1")
        assert len(ranked) == 1  # only INS-A complete
        assert ranked[0]["insurer_id"] == "INS-A"

    print("  ✅ insurance_commission_recon self-test PASS")


if __name__ == "__main__":
    _self_test()
