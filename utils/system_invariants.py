"""system_invariants.py — single source of truth for hard constraints.

v7.0 introduces this module to replace duplicated thresholds across
engines. Until v7.0, the CBK CAR floor (14.5%) was hard-coded in 4
places (capital_adequacy, stress_testing, audit, master prompt). When
the regulator changes a threshold, all 4 must update — error-prone.

After v7.0, engines read from this registry. A regulatory change
updates **one constant** and propagates everywhere.

Non-linear constraints are Donella Meadows' "leverage point #5: rules
of the system" — small changes in rules produce large behavioural
changes. Centralising rules makes leverage explicit.

Philosophy:
  - Pure: no I/O, no mutation, no global state
  - Honest: each constraint cites its regulatory or policy source
  - Backward-compatible: engines that hard-code today continue to work;
    migration to read from this registry is incremental in v7.x batches

References:
  Donella Meadows, *Thinking in Systems* (2008), Ch. 6: "Leverage
  Points to Intervene in a System"
  CBK Prudential Guidelines (PG/03 capital adequacy, PG/05 liquidity,
  PG/06 consumer protection)
  Basel III LCR/NSFR specifications
  IFRS 9 staging requirements
  A2Z Systems Charter, Section 6
"""
from __future__ import annotations
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple


# ──────────────────────────────────────────────────────────────────────
# Constraint dataclass
# ──────────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class SystemInvariant:
    """A hard non-linear constraint that binds the system."""
    invariant_id: str
    name: str
    threshold: Decimal  # The bound (use Decimal for precision)
    threshold_unit: str  # 'percent', 'KES', 'days', 'ratio'
    direction: str  # 'min' (must be >=) or 'max' (must be <=)
    source: str  # Regulatory source or policy source
    citation: str  # Specific document / section
    affected_contexts: Tuple[str, ...]  # Bounded contexts (Charter §3)
    affected_engines: Tuple[str, ...]  # Engine module names
    breach_severity: str  # 'CRITICAL' | 'HIGH' | 'MEDIUM' | 'LOW'
    breach_action: str  # What happens on breach
    notes: str = ""

    def is_breach(self, actual_value: Decimal) -> bool:
        """Return True if actual_value breaches this invariant."""
        if self.direction == "min":
            return actual_value < self.threshold
        elif self.direction == "max":
            return actual_value > self.threshold
        return False  # Unknown direction → no breach (conservative)

    def margin(self, actual_value: Decimal) -> Decimal:
        """Return how much room before breach. Negative if already breached.

        For 'min' invariants: margin = actual - threshold (positive = safe)
        For 'max' invariants: margin = threshold - actual (positive = safe)
        """
        if self.direction == "min":
            return actual_value - self.threshold
        elif self.direction == "max":
            return self.threshold - actual_value
        return Decimal("0")


# ──────────────────────────────────────────────────────────────────────
# The seven hard invariants (Charter Section 6)
# ──────────────────────────────────────────────────────────────────────

SYSTEM_INVARIANTS: Dict[str, SystemInvariant] = {
    "CBK_TOTAL_CAR_MIN": SystemInvariant(
        invariant_id="CBK_TOTAL_CAR_MIN",
        name="CBK Total Capital Adequacy Ratio minimum",
        threshold=Decimal("14.5"),
        threshold_unit="percent",
        direction="min",
        source="CBK PG/03",
        citation="CBK Prudential Guidelines, PG/03 Capital Adequacy",
        affected_contexts=("Daily-Risk Trifecta", "Treasury & ALM"),
        affected_engines=(
            "utils.capital_adequacy",
            "utils.stress_testing",
        ),
        breach_severity="CRITICAL",
        breach_action=(
            "Bank must submit capital remediation plan to CBK within 30 days. "
            "Dividend distribution suspended until restored."
        ),
        notes=(
            "Local prudential floor higher than Basel III 8% global "
            "minimum. Includes capital conservation buffer 2.5% on top of "
            "8% minimum + 4% domestic systemically-important add-on for "
            "Tier-1 banks. Tier-2 banks (e.g. Ecobank Kenya) face the "
            "14.5% effective floor."
        ),
    ),

    "CBK_TIER_1_CAR_MIN": SystemInvariant(
        invariant_id="CBK_TIER_1_CAR_MIN",
        name="CBK Tier 1 Capital Adequacy Ratio minimum",
        threshold=Decimal("10.5"),
        threshold_unit="percent",
        direction="min",
        source="CBK PG/03",
        citation="CBK Prudential Guidelines, PG/03 Capital Adequacy",
        affected_contexts=("Daily-Risk Trifecta", "Treasury & ALM"),
        affected_engines=("utils.capital_adequacy",),
        breach_severity="CRITICAL",
        breach_action=(
            "Same as Total CAR breach. Tier 1 specifically constrains "
            "loss-absorbing capacity (no subordinated debt counts here)."
        ),
        notes="Tier 1 = paid-up capital + reserves + retained earnings - intangibles - DTA.",
    ),

    "LCR_MIN": SystemInvariant(
        invariant_id="LCR_MIN",
        name="Liquidity Coverage Ratio minimum",
        threshold=Decimal("100"),
        threshold_unit="percent",
        direction="min",
        source="Basel III + CBK PG/05",
        citation="Basel III liquidity framework; CBK PG/05 Liquidity",
        affected_contexts=("Daily-Risk Trifecta", "Treasury & ALM"),
        affected_engines=("utils.liquidity_lcr_nsfr", "utils.alm"),
        breach_severity="HIGH",
        breach_action=(
            "Bank must report breach to CBK within 24 hours. Breach > "
            "30 days triggers supervisory action. HQLA must be replenished."
        ),
        notes=(
            "LCR = HQLA / net cash outflows over 30-day stress horizon. "
            "Net cash outflows are runoff-rate-weighted (deposit type, "
            "counterparty type). 100% means HQLA fully covers stressed "
            "outflows."
        ),
    ),

    "NSFR_MIN": SystemInvariant(
        invariant_id="NSFR_MIN",
        name="Net Stable Funding Ratio minimum",
        threshold=Decimal("100"),
        threshold_unit="percent",
        direction="min",
        source="Basel III + CBK PG/05",
        citation="Basel III liquidity framework; CBK PG/05 Liquidity",
        affected_contexts=("Daily-Risk Trifecta", "Treasury & ALM"),
        affected_engines=("utils.liquidity_lcr_nsfr", "utils.alm"),
        breach_severity="HIGH",
        breach_action=(
            "Quarterly reporting to CBK; persistent breach requires "
            "structural funding plan + CRO sign-off."
        ),
        notes=(
            "NSFR = available stable funding / required stable funding "
            "over 1-year horizon. Forces banks to fund long assets with "
            "long liabilities. Less reactive than LCR but binds capital "
            "structure long-term."
        ),
    ),

    "SINGLE_OBLIGOR_LIMIT_PCT": SystemInvariant(
        invariant_id="SINGLE_OBLIGOR_LIMIT_PCT",
        name="Single obligor exposure limit (% of core capital)",
        threshold=Decimal("25"),
        threshold_unit="percent",
        direction="max",
        source="CBK PG/03",
        citation="CBK Prudential Guidelines, PG/03 Concentration",
        affected_contexts=("Credit Risk",),
        affected_engines=(
            "utils.credit_monitoring",
            "utils.expected_credit_loss",
        ),
        breach_severity="CRITICAL",
        breach_action=(
            "Lending to that obligor must be reduced or core capital "
            "must be increased. Breach itself is regulatory failure."
        ),
        notes=(
            "Connected counterparties aggregated. 25% of core capital = "
            "tier 1 capital × 0.25. For a bank with KES 25B Tier 1, "
            "single obligor cap = KES 6.25B. Connected-party rules can "
            "shift this materially."
        ),
    ),

    "STAFF_LOAN_THIRD_RULE": SystemInvariant(
        invariant_id="STAFF_LOAN_THIRD_RULE",
        name="Staff loan one-third rule (monthly repayment ratio)",
        threshold=Decimal("0.33"),
        threshold_unit="ratio",
        direction="max",
        source="Bank policy (HR & Credit)",
        citation="Bank-specific policy; common across Kenyan banks",
        affected_contexts=("Credit Risk", "HR Intelligence"),
        affected_engines=(),  # Staff-loan-specific module varies by bank
        breach_severity="HIGH",
        breach_action=(
            "Loan application rejected. May approve with explicit "
            "exception + senior approval + offsetting collateral."
        ),
        notes=(
            "Standard prudential limit: monthly loan repayment shall not "
            "exceed 1/3 of net salary. Protects staff from over-"
            "leveraging and bank from elevated default risk on staff "
            "exposures. Some banks use 40% for senior staff."
        ),
    ),

    "IFRS9_STAGE2_MIN_ECL_HORIZON_MONTHS": SystemInvariant(
        invariant_id="IFRS9_STAGE2_MIN_ECL_HORIZON_MONTHS",
        name="IFRS 9 Stage 2 minimum ECL horizon (months)",
        threshold=Decimal("12"),
        threshold_unit="months",
        direction="min",
        source="IFRS 9",
        citation="IFRS 9 Financial Instruments, paragraph 5.5.5",
        affected_contexts=("Credit Risk",),
        affected_engines=(
            "utils.ifrs9_staging",
            "utils.expected_credit_loss",
        ),
        breach_severity="HIGH",
        breach_action=(
            "Audit qualification on financial statements. Restatement "
            "if material. Direct impact on retained earnings."
        ),
        notes=(
            "Stage 2 (significant increase in credit risk since "
            "origination) requires 12-month ECL minimum. Stage 3 "
            "(credit-impaired) requires lifetime ECL. Stage 1 (no SICR) "
            "requires 12-month ECL. The 12-month horizon is non-"
            "negotiable for all stages."
        ),
    ),

    "CBK_COMPLAINT_RESOLUTION_DAYS": SystemInvariant(
        invariant_id="CBK_COMPLAINT_RESOLUTION_DAYS",
        name="CBK consumer protection — complaint resolution SLA",
        threshold=Decimal("14"),
        threshold_unit="days",
        direction="max",
        source="CBK PG/06",
        citation="CBK Prudential Guidelines, PG/06 Consumer Protection",
        affected_contexts=("Compliance / AML", "Smart Alerts & Nudges"),
        affected_engines=(),  # Case management module varies
        breach_severity="MEDIUM",
        breach_action=(
            "Customer may escalate to CBK directly. Bank receives "
            "supervisory citation. Repeat offenders face fines."
        ),
        notes=(
            "14 days from complaint logged to documented resolution. "
            "Complex cases (>14 days) require interim communication "
            "to customer + extension justification."
        ),
    ),
}


# ──────────────────────────────────────────────────────────────────────
# Accessor functions
# ──────────────────────────────────────────────────────────────────────

def get_threshold(invariant_id: str) -> Optional[Decimal]:
    """Read the current threshold for an invariant.

    Engines should call this rather than hard-coding values. Returns
    None if the invariant_id is unknown — caller should handle None
    explicitly (do not silently default).
    """
    inv = SYSTEM_INVARIANTS.get(invariant_id)
    return inv.threshold if inv else None


def get_invariant(invariant_id: str) -> Optional[SystemInvariant]:
    """Return the full invariant record, or None if unknown."""
    return SYSTEM_INVARIANTS.get(invariant_id)


def list_invariants() -> List[SystemInvariant]:
    """Return all registered invariants."""
    return list(SYSTEM_INVARIANTS.values())


def invariants_for_context(context_name: str) -> List[SystemInvariant]:
    """Return all invariants affecting a given bounded context."""
    return [
        inv for inv in SYSTEM_INVARIANTS.values()
        if context_name in inv.affected_contexts
    ]


def invariants_for_engine(engine_name: str) -> List[SystemInvariant]:
    """Return all invariants enforced by a specific engine."""
    return [
        inv for inv in SYSTEM_INVARIANTS.values()
        if engine_name in inv.affected_engines
    ]


def check_breach(invariant_id: str,
                  actual_value: Any) -> Dict[str, Any]:
    """Check if a specific actual value breaches an invariant.

    Returns dict with: invariant_id, name, breach (bool),
    actual_value, threshold, margin, severity, action_if_breach,
    or status='UNKNOWN_INVARIANT' if invariant_id not found.

    Pure function. Caller decides what to do with breach result.
    """
    inv = SYSTEM_INVARIANTS.get(invariant_id)
    if inv is None:
        return {
            "invariant_id": invariant_id,
            "status": "UNKNOWN_INVARIANT",
            "breach": False,
        }

    try:
        actual_d = Decimal(str(actual_value))
    except Exception:
        return {
            "invariant_id": invariant_id,
            "status": "INVALID_ACTUAL_VALUE",
            "breach": False,
            "reason": f"Could not coerce {actual_value!r} to Decimal",
        }

    breach = inv.is_breach(actual_d)
    margin = inv.margin(actual_d)

    return {
        "invariant_id": inv.invariant_id,
        "name": inv.name,
        "breach": breach,
        "actual_value": str(actual_d),
        "threshold": str(inv.threshold),
        "threshold_unit": inv.threshold_unit,
        "direction": inv.direction,
        "margin": str(margin),
        "severity": inv.breach_severity if breach else "NONE",
        "action_if_breach": inv.breach_action if breach else None,
        "source": inv.source,
        "citation": inv.citation,
    }


# Convenience: counts for systems-view dashboard
def invariant_count_by_severity() -> Dict[str, int]:
    counts: Dict[str, int] = {}
    for inv in SYSTEM_INVARIANTS.values():
        counts[inv.breach_severity] = counts.get(inv.breach_severity, 0) + 1
    return counts


def all_thresholds() -> Dict[str, Dict[str, str]]:
    """Convenience: thresholds + units for documentation generators."""
    return {
        inv.invariant_id: {
            "threshold": str(inv.threshold),
            "unit": inv.threshold_unit,
            "direction": inv.direction,
            "source": inv.source,
        }
        for inv in SYSTEM_INVARIANTS.values()
    }
