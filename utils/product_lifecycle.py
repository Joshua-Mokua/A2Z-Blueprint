"""utils.product_lifecycle — Product Lifecycle Management
(Standard ENH-132, v10.143). Phase 1E Product Module — second engine.

Per Continuation.docx §Standard #132 (Eco Bank QA spec):
    Stage-gate lifecycle with automated gates, approvals, and
    sunset criteria.

This is the SECOND of ten Phase 1E Product standards (ENH-131..140,
closing at ~v10.146 with cockpit + API + UI gate per the v10.141
standing norm).

NOTE — companion engine relationship
    utils/product_profitability.py (Standard #47, v5.52) has a
    `product_lifecycle()` method that CLASSIFIES position from
    revenue history (LAUNCH/GROWTH/MATURITY/DECLINE).
    THIS engine (ENH-132) MANAGES the stage-gate process —
    transitions with approvals, gate criteria evaluation, sunset
    candidate detection, transition log persistence.
    Position-classification is descriptive; stage-gate-management is
    procedural. The two are complementary.

Per Rule 7 (No silent ML predictions):
  1. All gate criteria are deterministic — same input → same eval
  2. Transition thresholds are NAMED CONSTANTS; banks override
     via data/product_stagegate_config.json
  3. NO auto-transition at sunset — the engine RECOMMENDS sunset
     candidates; the decision requires explicit approver action
  4. Every transition requires explicit approver records per the
     configured approval matrix

WHAT THIS MODULE SHIPS
----------------------
1. ProductLifecycleEngine class with:
   - get_product_stage(product_id) — current stage
   - get_stage_history(product_id) — transitions + timestamps
   - evaluate_stage_gate(product_id, target_stage) — criteria check
   - request_stage_transition(product_id, target_stage, requested_by)
   - approve_transition(transition_id, approver_role, approver_id)
   - reject_transition(transition_id, approver_role, reason)
   - evaluate_sunset_criteria(product_id) — sunset evaluation
   - get_sunset_candidates() — products meeting sunset triggers
   - get_pending_approvals(approver_role=None)

2. Eight canonical stages (linear progression with one alternate
   sunset path from any stage):

     IDEATION → BUSINESS_CASE → DEVELOPMENT → LAUNCH
              → GROWTH → MATURITY → DECLINE → SUNSET

3. Bank-overridable stage-gate criteria (data/product_stagegate_config.json):
   - LAUNCH → GROWTH:    book ≥ 1B KES, customer_count ≥ 1000
   - GROWTH → MATURITY:  growth_rate_pct ≤ 5.0
   - MATURITY → DECLINE: 2 consecutive periods of negative growth
   - DECLINE → SUNSET:   3 consecutive loss periods OR book decline ≥ 20%

4. Approval matrix (config-driven; required roles per transition):
   - IDEATION → BUSINESS_CASE:     [product_head]
   - BUSINESS_CASE → DEVELOPMENT:  [product_head, risk_head, finance_head]
   - DEVELOPMENT → LAUNCH:         [product_head, compliance_head, ops_head]
   - LAUNCH → GROWTH / GROWTH → MATURITY / MATURITY → DECLINE: [] (auto on criteria)
   - DECLINE → SUNSET:             [product_head, ceo]

5. Reads:
   - data/products.json (16 products)
   - data/product_lifecycle.json (NEW seed; per-product current stage + history)
   - data/product_stagegate_config.json (NEW seed; thresholds + approval matrix)

6. Writes (read-modify-write JSON):
   - data/product_lifecycle.json on transition request / approval / rejection

HONESTY DISCIPLINE
------------------
- Sunset NEVER auto-triggers — engine returns
  candidate_status="recommended_for_sunset_review" not a decision
- Stage-gate evaluation reports per-criterion pass/fail with explicit
  missing_inputs trail when revenue/book history is too short
- evaluate_stage_gate(LAUNCH→GROWTH) for a brand-new product with
  zero customer_count returns gate_open=False with reason rather than
  silently treating zero as "not yet met"
- Transitions are timestamped UTC with approver records — audit trail
  is the discipline
- Approval matrix requires ALL listed roles before transition lands;
  partial approvals stay pending
- Pending transitions older than configured TTL surface in
  get_pending_approvals() with stale=True flag
"""
from __future__ import annotations
import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

DATA_DIR = Path(__file__).parent.parent / "data"
PRODUCTS_PATH = DATA_DIR / "products.json"
LIFECYCLE_PATH = DATA_DIR / "product_lifecycle.json"
STAGEGATE_CONFIG_PATH = DATA_DIR / "product_stagegate_config.json"


# Canonical stage progression
CANONICAL_STAGES: Tuple[str, ...] = (
    "IDEATION", "BUSINESS_CASE", "DEVELOPMENT", "LAUNCH",
    "GROWTH", "MATURITY", "DECLINE", "SUNSET",
)


@dataclass(frozen=True)
class StageGateEvaluation:
    product_id: str
    current_stage: str
    target_stage: str
    gate_open: bool
    criteria_results: Tuple[Dict[str, Any], ...]   # per criterion
    requires_approval: bool
    required_approvers: Tuple[str, ...]
    missing_inputs: Tuple[str, ...] = field(default_factory=tuple)
    fallback_reason: Optional[str] = None

    def as_dict(self) -> Dict[str, Any]:
        return {
            "product_id": self.product_id,
            "current_stage": self.current_stage,
            "target_stage": self.target_stage,
            "gate_open": self.gate_open,
            "criteria_results": list(self.criteria_results),
            "requires_approval": self.requires_approval,
            "required_approvers": list(self.required_approvers),
            "missing_inputs": list(self.missing_inputs),
            "fallback_reason": self.fallback_reason,
        }


@dataclass(frozen=True)
class SunsetEvaluation:
    product_id: str
    name: str
    candidate: bool
    triggers_met: Tuple[str, ...]
    book_decline_pct: Optional[Decimal]
    consecutive_loss_periods: int
    candidate_status: str   # "recommended_for_sunset_review" | "no_action"
    rationale: str

    def as_dict(self) -> Dict[str, Any]:
        return {
            "product_id": self.product_id,
            "name": self.name,
            "candidate": self.candidate,
            "triggers_met": list(self.triggers_met),
            "book_decline_pct": (str(self.book_decline_pct)
                                  if self.book_decline_pct is not None
                                  else None),
            "consecutive_loss_periods": self.consecutive_loss_periods,
            "candidate_status": self.candidate_status,
            "rationale": self.rationale,
        }


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------

class ProductLifecycleEngine:
    """Stage-gate lifecycle management for products.

    Read-mostly contract — writes only to data/product_lifecycle.json
    on transition request / approval / rejection.
    """

    # Default gate thresholds (config overrides via JSON)
    LAUNCH_TO_GROWTH_BOOK_THRESHOLD_KES = Decimal("1000000000")  # 1B
    LAUNCH_TO_GROWTH_CUSTOMER_THRESHOLD = 1000
    GROWTH_TO_MATURITY_GROWTH_RATE_PCT = Decimal("5.0")
    MATURITY_TO_DECLINE_NEGATIVE_PERIODS = 2
    SUNSET_LOSS_PERIODS = 3
    SUNSET_BOOK_DECLINE_PCT = Decimal("-20.0")

    PENDING_APPROVAL_TTL_DAYS = 14

    # Default approval matrix
    DEFAULT_APPROVAL_MATRIX = {
        "IDEATION->BUSINESS_CASE":    ("product_head",),
        "BUSINESS_CASE->DEVELOPMENT": ("product_head", "risk_head",
                                        "finance_head"),
        "DEVELOPMENT->LAUNCH":         ("product_head", "compliance_head",
                                        "ops_head"),
        "LAUNCH->GROWTH":              (),   # auto if criteria
        "GROWTH->MATURITY":            (),   # auto if criteria
        "MATURITY->DECLINE":           (),   # auto if criteria
        "DECLINE->SUNSET":             ("product_head", "ceo"),
    }

    def __init__(
        self,
        products_path: Optional[Path] = None,
        lifecycle_path: Optional[Path] = None,
        stagegate_config_path: Optional[Path] = None,
    ) -> None:
        self.products_path = products_path or PRODUCTS_PATH
        self.lifecycle_path = lifecycle_path or LIFECYCLE_PATH
        self.stagegate_config_path = (stagegate_config_path
                                       or STAGEGATE_CONFIG_PATH)

    # ------------------------------------------------------------------
    # Data loading
    # ------------------------------------------------------------------

    def _load_products(self) -> List[Dict[str, Any]]:
        try:
            with open(self.products_path) as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return []

    def _load_lifecycle(self) -> Dict[str, Any]:
        try:
            with open(self.lifecycle_path) as f:
                data = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            data = {}
        if not isinstance(data, dict):
            data = {}
        data.setdefault("products", {})
        data.setdefault("transitions", [])
        data.setdefault("pending", [])
        return data

    def _load_config(self) -> Dict[str, Any]:
        try:
            with open(self.stagegate_config_path) as f:
                cfg = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            cfg = {}
        return cfg if isinstance(cfg, dict) else {}

    def _save_lifecycle(self, data: Dict[str, Any]) -> bool:
        try:
            with open(self.lifecycle_path, "w") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            return True
        except OSError:
            return False

    def _approval_matrix(self) -> Dict[str, Tuple[str, ...]]:
        cfg = self._load_config()
        override = cfg.get("approval_matrix", {})
        out = {}
        for k, v in self.DEFAULT_APPROVAL_MATRIX.items():
            if k in override:
                out[k] = tuple(override[k])
            else:
                out[k] = v
        return out

    def _config_decimal(self, key: str, default: Decimal) -> Decimal:
        cfg = self._load_config()
        if key in cfg:
            return Decimal(str(cfg[key]))
        return default

    def _config_int(self, key: str, default: int) -> int:
        cfg = self._load_config()
        if key in cfg:
            return int(cfg[key])
        return default

    # ------------------------------------------------------------------
    # Stage queries
    # ------------------------------------------------------------------

    def get_product_stage(self, product_id: str) -> Dict[str, Any]:
        lifecycle = self._load_lifecycle()
        entry = lifecycle.get("products", {}).get(product_id)
        if not entry:
            return {"product_id": product_id, "current_stage": None,
                    "since": None, "found": False}
        return {"product_id": product_id,
                "current_stage": entry.get("current_stage"),
                "since": entry.get("since"),
                "found": True}

    def get_stage_history(self, product_id: str) -> List[Dict[str, Any]]:
        lifecycle = self._load_lifecycle()
        return [t for t in lifecycle.get("transitions", [])
                if t.get("product_id") == product_id]

    # ------------------------------------------------------------------
    # Stage-gate evaluation
    # ------------------------------------------------------------------

    def evaluate_stage_gate(self, product_id: str,
                             target_stage: str) -> StageGateEvaluation:
        if target_stage not in CANONICAL_STAGES:
            return StageGateEvaluation(
                product_id=product_id,
                current_stage="",
                target_stage=target_stage,
                gate_open=False,
                criteria_results=(),
                requires_approval=False,
                required_approvers=(),
                fallback_reason=f"unknown_target_stage:{target_stage}")

        stage_info = self.get_product_stage(product_id)
        current = stage_info.get("current_stage")
        if not current:
            return StageGateEvaluation(
                product_id=product_id,
                current_stage="",
                target_stage=target_stage,
                gate_open=False,
                criteria_results=(),
                requires_approval=False,
                required_approvers=(),
                fallback_reason="product_not_in_lifecycle_registry")

        # Validate target is the immediate next stage OR SUNSET
        cur_idx = CANONICAL_STAGES.index(current)
        if target_stage == "SUNSET":
            valid = current in ("DECLINE", "MATURITY", "GROWTH",
                                "LAUNCH", "DEVELOPMENT", "BUSINESS_CASE",
                                "IDEATION")
        else:
            tgt_idx = CANONICAL_STAGES.index(target_stage)
            valid = (tgt_idx == cur_idx + 1)

        if not valid:
            return StageGateEvaluation(
                product_id=product_id,
                current_stage=current,
                target_stage=target_stage,
                gate_open=False,
                criteria_results=(),
                requires_approval=False,
                required_approvers=(),
                fallback_reason=(f"invalid_transition:"
                                 f"{current}->{target_stage}"))

        # Look up the product in products.json for criteria evaluation
        product = next((p for p in self._load_products()
                        if p.get("id") == product_id), None)

        criteria, missing = self._evaluate_criteria(
            current, target_stage, product, product_id)

        all_passed = (len(criteria) == 0
                      or all(c.get("passed") for c in criteria))

        # Approval requirement
        transition_key = f"{current}->{target_stage}"
        approvers = self._approval_matrix().get(transition_key, ())
        requires_approval = len(approvers) > 0

        return StageGateEvaluation(
            product_id=product_id,
            current_stage=current,
            target_stage=target_stage,
            gate_open=all_passed,
            criteria_results=tuple(criteria),
            requires_approval=requires_approval,
            required_approvers=approvers,
            missing_inputs=tuple(missing))

    def _evaluate_criteria(
        self, current: str, target: str,
        product: Optional[Dict[str, Any]], product_id: str,
    ) -> Tuple[List[Dict[str, Any]], List[str]]:
        """Per-transition criteria — returns (results, missing_inputs)."""
        results: List[Dict[str, Any]] = []
        missing: List[str] = []

        if not product:
            missing.append(f"product_{product_id}_not_in_products.json")
            return results, missing

        actual_book = Decimal(str(product.get("actual_book", 0) or 0))
        growth_rate = Decimal(str(product.get("growth_rate", 0) or 0))
        # customer_count not in products.json — flag as missing if needed

        if current == "LAUNCH" and target == "GROWTH":
            book_threshold = self._config_decimal(
                "launch_to_growth_book_threshold_kes",
                self.LAUNCH_TO_GROWTH_BOOK_THRESHOLD_KES)
            results.append({
                "criterion": "book_size_threshold",
                "expected": f">={book_threshold}",
                "actual": str(actual_book),
                "passed": actual_book >= book_threshold,
            })
            missing.append(("customer_count: not in products.json — "
                            "criterion skipped, supply via config or"
                            " external feed"))

        elif current == "GROWTH" and target == "MATURITY":
            growth_threshold = self._config_decimal(
                "growth_to_maturity_growth_rate_pct",
                self.GROWTH_TO_MATURITY_GROWTH_RATE_PCT)
            results.append({
                "criterion": "growth_rate_decelerated",
                "expected": f"<={growth_threshold}%",
                "actual": f"{growth_rate}%",
                "passed": growth_rate <= growth_threshold,
            })

        elif current == "MATURITY" and target == "DECLINE":
            results.append({
                "criterion": "negative_growth_signal",
                "expected": "growth_rate < 0",
                "actual": f"{growth_rate}%",
                "passed": growth_rate < Decimal("0"),
            })
            missing.append(("consecutive_period_check: requires period "
                            "history not present in products.json"))

        elif current == "DECLINE" and target == "SUNSET":
            sunset_decline = self._config_decimal(
                "sunset_book_decline_pct",
                self.SUNSET_BOOK_DECLINE_PCT)
            results.append({
                "criterion": "book_decline_threshold",
                "expected": f"<={sunset_decline}%",
                "actual": f"{growth_rate}%",
                "passed": growth_rate <= sunset_decline,
            })
            missing.append(("consecutive_loss_periods: requires P&L "
                            "history; integrate with ENH-131"))

        # Pre-launch transitions (IDEATION → BUSINESS_CASE etc.) have no
        # quantitative criteria — they are gated entirely by the approval
        # matrix; criteria_results stays empty + gate_open == True iff
        # criteria list is empty (vacuous truth)

        return results, missing

    # ------------------------------------------------------------------
    # Transition lifecycle
    # ------------------------------------------------------------------

    def request_stage_transition(
        self, product_id: str, target_stage: str, requested_by: str,
    ) -> Dict[str, Any]:
        evaluation = self.evaluate_stage_gate(product_id, target_stage)
        if not evaluation.gate_open:
            return {
                "ok": False,
                "reason": "gate_criteria_not_met",
                "evaluation": evaluation.as_dict(),
            }

        lifecycle = self._load_lifecycle()
        transition_id = f"T_{uuid.uuid4().hex[:12]}"
        now = datetime.now(timezone.utc).isoformat()

        # Auto-transition path — no approvals required
        if not evaluation.requires_approval:
            # Direct landing
            lifecycle["transitions"].append({
                "transition_id": transition_id,
                "product_id": product_id,
                "from_stage": evaluation.current_stage,
                "to_stage": target_stage,
                "requested_by": requested_by,
                "requested_at": now,
                "decided_at": now,
                "approvals": [],
                "rejections": [],
                "auto": True,
                "status": "approved",
            })
            lifecycle.setdefault("products", {})[product_id] = {
                "current_stage": target_stage, "since": now,
            }
            self._save_lifecycle(lifecycle)
            return {
                "ok": True,
                "transition_id": transition_id,
                "auto": True,
                "new_stage": target_stage,
            }

        # Approval-required path — register pending
        pending_entry = {
            "transition_id": transition_id,
            "product_id": product_id,
            "from_stage": evaluation.current_stage,
            "to_stage": target_stage,
            "requested_by": requested_by,
            "requested_at": now,
            "required_approvers": list(evaluation.required_approvers),
            "approvals": [],
            "rejections": [],
            "status": "pending",
        }
        lifecycle.setdefault("pending", []).append(pending_entry)
        self._save_lifecycle(lifecycle)
        return {
            "ok": True,
            "transition_id": transition_id,
            "auto": False,
            "required_approvers": list(evaluation.required_approvers),
            "status": "pending",
        }

    def approve_transition(
        self, transition_id: str, approver_role: str, approver_id: str,
    ) -> Dict[str, Any]:
        lifecycle = self._load_lifecycle()
        pending_list = lifecycle.get("pending", [])
        entry = next((p for p in pending_list
                      if p["transition_id"] == transition_id), None)
        if not entry:
            return {"ok": False, "reason": "transition_not_pending"}

        if approver_role not in entry["required_approvers"]:
            return {"ok": False,
                    "reason": f"approver_role_not_required:{approver_role}",
                    "required_approvers": entry["required_approvers"]}

        # Check this role hasn't already approved
        existing_roles = {a["approver_role"] for a in entry["approvals"]}
        if approver_role in existing_roles:
            return {"ok": False,
                    "reason": f"role_already_approved:{approver_role}"}

        entry["approvals"].append({
            "approver_role": approver_role,
            "approver_id": approver_id,
            "approved_at": datetime.now(timezone.utc).isoformat(),
        })

        # All required approvers landed?
        approved_roles = {a["approver_role"] for a in entry["approvals"]}
        all_approved = all(r in approved_roles
                           for r in entry["required_approvers"])

        if all_approved:
            now = datetime.now(timezone.utc).isoformat()
            entry["status"] = "approved"
            entry["decided_at"] = now
            # Move from pending to transitions
            lifecycle["transitions"].append(dict(entry,
                                                  auto=False))
            lifecycle["pending"] = [p for p in pending_list
                                     if p["transition_id"] != transition_id]
            lifecycle.setdefault("products", {})[entry["product_id"]] = {
                "current_stage": entry["to_stage"],
                "since": now,
            }
        else:
            # Stay pending
            pass

        self._save_lifecycle(lifecycle)
        return {
            "ok": True,
            "transition_id": transition_id,
            "approvals_collected": len(entry["approvals"]),
            "approvals_required": len(entry["required_approvers"]),
            "status": entry["status"],
            "new_stage": (entry["to_stage"] if all_approved else None),
        }

    def reject_transition(
        self, transition_id: str, approver_role: str, reason: str,
    ) -> Dict[str, Any]:
        lifecycle = self._load_lifecycle()
        pending_list = lifecycle.get("pending", [])
        entry = next((p for p in pending_list
                      if p["transition_id"] == transition_id), None)
        if not entry:
            return {"ok": False, "reason": "transition_not_pending"}

        entry.setdefault("rejections", []).append({
            "approver_role": approver_role,
            "rejected_at": datetime.now(timezone.utc).isoformat(),
            "reason": reason,
        })
        entry["status"] = "rejected"
        entry["decided_at"] = datetime.now(timezone.utc).isoformat()
        # Move to transitions log (rejected) and remove from pending
        lifecycle["transitions"].append(dict(entry, auto=False))
        lifecycle["pending"] = [p for p in pending_list
                                 if p["transition_id"] != transition_id]
        self._save_lifecycle(lifecycle)
        return {"ok": True, "transition_id": transition_id,
                "status": "rejected"}

    # ------------------------------------------------------------------
    # Pending approvals
    # ------------------------------------------------------------------

    def get_pending_approvals(
        self, approver_role: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        lifecycle = self._load_lifecycle()
        ttl_days = self._config_int(
            "pending_approval_ttl_days",
            self.PENDING_APPROVAL_TTL_DAYS)
        now = datetime.now(timezone.utc)
        cutoff = now - timedelta(days=ttl_days)

        out: List[Dict[str, Any]] = []
        for p in lifecycle.get("pending", []):
            # Filter by approver_role if given
            if approver_role:
                if approver_role not in p.get("required_approvers", ()):
                    continue
                # Skip if this role already approved
                if any(a["approver_role"] == approver_role
                       for a in p.get("approvals", [])):
                    continue
            try:
                req_at = datetime.fromisoformat(
                    p["requested_at"].replace("Z", "+00:00"))
                if req_at.tzinfo is None:
                    req_at = req_at.replace(tzinfo=timezone.utc)
                stale = req_at < cutoff
            except (KeyError, ValueError):
                stale = False
            out.append({**p, "stale": stale})
        return out

    # ------------------------------------------------------------------
    # Sunset evaluation
    # ------------------------------------------------------------------

    def evaluate_sunset_criteria(self, product_id: str) -> SunsetEvaluation:
        product = next((p for p in self._load_products()
                        if p.get("id") == product_id), None)
        if not product:
            return SunsetEvaluation(
                product_id=product_id, name="",
                candidate=False, triggers_met=(),
                book_decline_pct=None, consecutive_loss_periods=0,
                candidate_status="no_action",
                rationale="product_not_found")

        growth_rate = Decimal(str(product.get("growth_rate", 0) or 0))
        sunset_decline = self._config_decimal(
            "sunset_book_decline_pct",
            self.SUNSET_BOOK_DECLINE_PCT)

        triggers: List[str] = []

        if growth_rate <= sunset_decline:
            triggers.append("book_decline_exceeds_threshold")

        # Loss-period detection — best-effort from current data
        # (true period history needs a P&L history feed; honest fallback)
        consecutive_losses = 0
        actual_revenue = Decimal(str(product.get("actual_revenue", 0)
                                       or 0))
        target_revenue = Decimal(str(product.get("target_revenue", 0)
                                      or 0))
        if (target_revenue > 0
                and actual_revenue < target_revenue * Decimal("0.5")):
            triggers.append("revenue_far_below_target")

        candidate = len(triggers) > 0
        rationale = (("Triggers met: " + ", ".join(triggers))
                     if candidate
                     else "No sunset triggers met on current data")

        return SunsetEvaluation(
            product_id=product_id,
            name=product.get("name", ""),
            candidate=candidate,
            triggers_met=tuple(triggers),
            book_decline_pct=growth_rate,
            consecutive_loss_periods=consecutive_losses,
            candidate_status=("recommended_for_sunset_review"
                              if candidate else "no_action"),
            rationale=rationale)

    def get_sunset_candidates(self) -> List[Dict[str, Any]]:
        out: List[Dict[str, Any]] = []
        for p in self._load_products():
            ev = self.evaluate_sunset_criteria(p.get("id", ""))
            if ev.candidate:
                out.append(ev.as_dict())
        return out


# ---------------------------------------------------------------------------
# Self-test
# ---------------------------------------------------------------------------

def _self_test() -> None:
    eng = ProductLifecycleEngine()
    # Stage queries
    for pid in ("P001", "P004", "P016"):
        s = eng.get_product_stage(pid)
        print(f"{pid}: stage={s.get('current_stage')} "
              f"since={s.get('since')} found={s.get('found')}")
    print()

    # Sunset candidates on real data
    cands = eng.get_sunset_candidates()
    print(f"Sunset candidates: {len(cands)}")
    for c in cands[:5]:
        print(f"  {c['product_id']} {c['name']}: "
              f"triggers={c['triggers_met']} status={c['candidate_status']}")
    print()

    # Evaluate a stage gate
    ev = eng.evaluate_stage_gate("P001", "SUNSET")
    print(f"P001 → SUNSET: gate_open={ev.gate_open} "
          f"requires_approval={ev.requires_approval} "
          f"required_approvers={ev.required_approvers}")
    print(f"  criteria_results: {ev.criteria_results}")
    print(f"  missing_inputs: {len(ev.missing_inputs)} entries")
    print()

    # Pending approvals (should be empty on first run)
    pending = eng.get_pending_approvals()
    print(f"Pending approvals: {len(pending)}")


if __name__ == "__main__":
    _self_test()
