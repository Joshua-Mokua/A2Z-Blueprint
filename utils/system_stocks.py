"""system_stocks.py — explicit stock-and-flow definitions for A2Z.

v7.0 introduces this module to make Donella Meadows' "stocks" first-class
citizens of the platform. Until v7.0, stocks (customer base, loan
portfolio, deposit base, NPL inventory, dormant accounts, capital base)
existed implicitly in the CBS database but were not modelled as stocks
with explicit accumulation rules.

This module is **descriptive, not prescriptive**. It does not modify
any engine behaviour. It provides:
  1. A canonical list of the 6 system stocks (Charter Section 5)
  2. Per-stock metadata: contributors (engines that add), drainers
     (engines that remove), unit, owner context, accumulation rule
  3. A read-only snapshot accessor that returns current values from CBS
     where wired, or returns `STOCK_NOT_WIRED` honestly otherwise

The module follows v6.0 composite-scoring philosophy:
  - Pure: no I/O, no global state, no engine modifications
  - Honest: surfaces "not yet wired" as first-class status, not as zero
  - Caller-side: pages query this module for stock views; engines
    don't have to know about it

Future v7.x batches will wire the snapshot accessor to live CBS data;
v7.0 ships the registry + scaffolding only.

References:
  Donella Meadows, *Thinking in Systems* (2008), Ch. 1: "Stocks as the
  memory of the system"
  A2Z Systems Charter, Section 5
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple


# ──────────────────────────────────────────────────────────────────────
# Status constants — honest reporting of wiring status
# ──────────────────────────────────────────────────────────────────────

STOCK_WIRED = "WIRED"            # Snapshot accessor returns live data
STOCK_NOT_WIRED = "NOT_WIRED"    # Stock defined but accessor returns None
STOCK_PARTIAL = "PARTIAL"        # Some data sources wired, others not


# ──────────────────────────────────────────────────────────────────────
# Stock dataclass
# ──────────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class SystemStock:
    """A single stock in the A2Z system."""
    stock_id: str
    name: str
    unit: str  # 'count', 'KES', etc.
    owner_context: str  # Bounded-context name from Charter Section 3
    contributors: Tuple[str, ...]  # Engines that add to this stock
    drainers: Tuple[str, ...]  # Engines that remove from this stock
    accumulation_rule: str  # Plain-English rule
    why_first_class: str  # Why this stock matters at system level
    status: str = STOCK_NOT_WIRED  # Wiring status
    notes: str = ""

    def is_wired(self) -> bool:
        return self.status == STOCK_WIRED


# ──────────────────────────────────────────────────────────────────────
# The six system stocks (Charter Section 5)
# ──────────────────────────────────────────────────────────────────────

SYSTEM_STOCKS: Dict[str, SystemStock] = {
    "customer_base": SystemStock(
        stock_id="customer_base",
        name="Customer base",
        unit="count",
        owner_context="Customer Intelligence",
        contributors=(
            "onboarding",
            "kyc_aml_risk",  # KYC approval is the gating contributor
        ),
        drainers=(
            "churn_prediction",  # Predicts attrition; doesn't remove directly
            "account_closure",   # Wired in CBS, not in A2Z
        ),
        accumulation_rule=(
            "current = previous + new_customers - attrited_customers - "
            "closed_accounts. Period: monthly. Accumulation timescale: "
            "slow (months). Flow timescale: fast (daily new accounts)."
        ),
        why_first_class=(
            "The customer base is the bank's revenue substrate. Every "
            "cross-sell, every deposit, every loan flows from a customer. "
            "Lose customers faster than you gain them and the bank "
            "contracts regardless of how good individual products are."
        ),
        status=STOCK_WIRED,  # v7.4: wired with demo defaults until CBS integration
        notes=(
            "v7.4: snapshot accessor wired with demo defaults representing "
            "Tier-2 Kenya bank customer base (700K total customers — matches "
            "A2Z Blueprint CBS simulation). Future v7.x batch wires to CBS "
            "customer table for live counts + segment breakdown."
        ),
    ),

    "loan_portfolio": SystemStock(
        stock_id="loan_portfolio",
        name="Loan portfolio (gross outstanding)",
        unit="KES",
        owner_context="Credit Risk",
        contributors=(
            "credit_monitoring",  # Disbursement records
            "loan_origination",   # Wired in CBS, not in A2Z
        ),
        drainers=(
            "credit_monitoring",  # Repayment records
            "ifrs9_staging",      # Write-offs (Stage 3 derecognition)
            "loan_sales",         # Securitisation / sale (rare)
        ),
        accumulation_rule=(
            "current = previous + disbursements - repayments - "
            "write_offs - sales. Period: daily. Interest accrual is NOT "
            "a stock change for A2Z (it's an income-statement flow)."
        ),
        why_first_class=(
            "The loan portfolio is the largest asset on a bank's balance "
            "sheet and the primary driver of both income (interest) and "
            "risk (credit losses). Stress testing, ECL, capital adequacy, "
            "concentration limits all read from this stock."
        ),
        status=STOCK_WIRED,  # v7.1: wired with demo defaults until FLEXCUBE ACL
        notes=(
            "v7.1: snapshot accessor wired with demo defaults representing "
            "Tier-2 Kenya bank loan book. Future v7.x batch wires to "
            "FLEXCUBE loan portfolio table via Anti-Corruption Layer."
        ),
    ),

    "deposit_base": SystemStock(
        stock_id="deposit_base",
        name="Deposit base (customer deposits)",
        unit="KES",
        owner_context="Treasury & ALM",
        contributors=(
            "customer_inflows",
            "new_account_opening",  # CBS-side
        ),
        drainers=(
            "customer_outflows",
            "account_closure",
            "withdrawals",
        ),
        accumulation_rule=(
            "current = previous + inflows - outflows - closures. "
            "Period: daily. Net change is the most-watched metric in "
            "treasury — a sudden drop signals confidence loss."
        ),
        why_first_class=(
            "Deposits fund the loan book. Loan-to-deposit ratio (LDR) "
            "is a primary liquidity indicator. LCR + NSFR depend on "
            "deposit composition by stability tier (Basel III)."
        ),
        status=STOCK_WIRED,  # v7.3: wired with demo defaults until FLEXCUBE ACL
        notes=(
            "v7.3: snapshot accessor wired with demo defaults representing "
            "Tier-2 Kenya bank deposit book composition. Future v7.x batch "
            "wires to FLEXCUBE deposits table via Anti-Corruption Layer "
            "(same pattern that will be reused for live loan_portfolio + "
            "npl_inventory refresh)."
        ),
    ),

    "npl_inventory": SystemStock(
        stock_id="npl_inventory",
        name="NPL inventory (non-performing loans)",
        unit="KES",
        owner_context="Credit Risk",
        contributors=(
            "credit_monitoring",  # New defaults
            "ifrs9_staging",      # Stage 2 → Stage 3 transitions
        ),
        drainers=(
            "collections",        # Recoveries
            "ifrs9_staging",      # Write-offs (terminal)
            "credit_monitoring",  # Cure (Stage 3 → Stage 1, rare)
        ),
        accumulation_rule=(
            "current = previous + new_npls + downgrades - recoveries - "
            "write_offs - cures. NPL ratio = current / loan_portfolio. "
            "CBK reportable monthly (NPL > 90 days past due)."
        ),
        why_first_class=(
            "NPL inventory is the canary for credit-cycle health. "
            "Provisioning, capital, regulatory reporting (CBK BSD/RB1) "
            "all depend on this stock. Material movements signal "
            "macro stress."
        ),
        status=STOCK_WIRED,  # v7.1: wired alongside loan_portfolio
        notes=(
            "v7.1: snapshot accessor wired with demo defaults. NPL ratio "
            "computed from npl_inventory / loan_portfolio. Linked to L01 "
            "feedback loop (Collections → PD recalibration), now WIRED."
        ),
    ),

    "dormant_accounts": SystemStock(
        stock_id="dormant_accounts",
        name="Dormant accounts",
        unit="count",
        owner_context="Customer Intelligence",
        contributors=(
            "dormancy_engine",  # Time-based — accounts age into dormancy
        ),
        drainers=(
            "reactivation_campaign",  # Active outreach reactivates
            "account_closure",         # Closed dormant accounts removed
        ),
        accumulation_rule=(
            "Dormancy bands: 90 / 180 / 365 days inactivity. An account "
            "moves between bands as time passes (positive flow into "
            "longer-dormancy bands). Reactivation removes from all bands. "
            "Closure removes terminally."
        ),
        why_first_class=(
            "Dormant accounts represent latent value (or latent loss). "
            "A reactivation campaign that recovers 10% of 90-day-dormant "
            "accounts beats a new-customer acquisition campaign with "
            "the same conversion rate, because the customer is already "
            "verified, KYC'd, and known."
        ),
        status=STOCK_WIRED,  # v7.4: wired with demo defaults until CBS integration
        notes=(
            "v7.4: snapshot accessor wired with demo defaults. Three "
            "dormancy bands per CBK guidance + bank policy. Future v7.x "
            "batch wires to CBS account-activity table for live counts."
        ),
    ),

    "capital_base": SystemStock(
        stock_id="capital_base",
        name="Capital base (Tier 1 + Tier 2)",
        unit="KES",
        owner_context="Treasury & ALM",
        contributors=(
            "profit_retention",  # Annual retained earnings
            "rights_issue",       # Equity raises (rare, episodic)
            "tier_2_issuance",   # Subordinated debt (less rare)
        ),
        drainers=(
            "losses",             # Net losses reduce retained earnings
            "dividends",          # Distributions to shareholders
            "tier_2_redemption",  # Subordinated debt maturing
            "buybacks",           # Share repurchases (rare in Kenya)
        ),
        accumulation_rule=(
            "Tier 1 = paid_up_capital + reserves + retained_earnings - "
            "intangibles - deferred_tax. Tier 2 = qualifying_subordinated "
            "+ general_provisions (capped). Total = T1 + T2. CBK requires "
            "T1 >= 10.5% RWA and Total >= 14.5% RWA."
        ),
        why_first_class=(
            "Capital is the bank's loss-absorbing buffer. Stress test "
            "scenarios (#51), CAR floors (Section 6 Constraint #1, #2), "
            "single-obligor limits (Constraint #5) all read from capital "
            "base. A capital adequacy breach is regulatory failure."
        ),
        status=STOCK_WIRED,  # v7.0.1: wired to capital_adequacy engine
        notes=(
            "v7.0.1: snapshot accessor wired via "
            "CapitalAdequacyEngine.total_capital(). "
            "Caller must supply CapitalComponents + RWA to get a value; "
            "snapshot returns demo defaults if no input provided."
        ),
    ),
}


# ──────────────────────────────────────────────────────────────────────
# Snapshot accessor — returns current value or STOCK_NOT_WIRED
# ──────────────────────────────────────────────────────────────────────

def get_stock_snapshot(
    stock_id: str,
    capital_components: Optional[Any] = None,
    total_rwa_kes: Optional[Any] = None,
) -> Dict[str, Any]:
    """Return current snapshot for a stock.

    Returns dict with:
      stock_id, name, status, value, unit, period_change,
      contributors_active (list), drainers_active (list),
      reason (if NOT_WIRED).

    Honest reporting per A2Z Rule 6: if a stock is not yet wired, return
    status=STOCK_NOT_WIRED and value=None rather than fabricating zero.

    For wired stocks, the caller may pass live inputs:
      capital_base: pass capital_components (CapitalComponents dataclass)
                    and total_rwa_kes (Decimal). Without inputs, returns
                    a demo snapshot using realistic Tier-2 Kenya defaults.
    """
    if stock_id not in SYSTEM_STOCKS:
        return {
            "stock_id": stock_id,
            "status": "UNKNOWN_STOCK",
            "value": None,
            "reason": f"stock_id '{stock_id}' not in registry",
        }

    stock = SYSTEM_STOCKS[stock_id]

    if stock.status == STOCK_NOT_WIRED:
        return {
            "stock_id": stock.stock_id,
            "name": stock.name,
            "status": STOCK_NOT_WIRED,
            "value": None,
            "unit": stock.unit,
            "period_change": None,
            "contributors_defined": list(stock.contributors),
            "drainers_defined": list(stock.drainers),
            "reason": (
                "Stock is defined in registry but live snapshot accessor "
                "is not yet wired. Future v7.x batch will integrate with "
                "underlying data source."
            ),
        }

    # WIRED stocks — dispatch to per-stock accessors
    if stock_id == "capital_base":
        return _capital_base_snapshot(stock, capital_components, total_rwa_kes)
    if stock_id == "loan_portfolio":
        return _loan_portfolio_snapshot(stock)
    if stock_id == "npl_inventory":
        return _npl_inventory_snapshot(stock)
    if stock_id == "deposit_base":
        return _deposit_base_snapshot(stock)
    if stock_id == "customer_base":
        return _customer_base_snapshot(stock)
    if stock_id == "dormant_accounts":
        return _dormant_accounts_snapshot(stock)

    return {
        "stock_id": stock.stock_id,
        "name": stock.name,
        "status": stock.status,
        "value": None,
        "unit": stock.unit,
        "reason": f"Status {stock.status} but no per-stock accessor implemented",
    }


def _capital_base_snapshot(
    stock: SystemStock,
    capital_components: Optional[Any],
    total_rwa_kes: Optional[Any],
) -> Dict[str, Any]:
    """Live snapshot for capital_base via CapitalAdequacyEngine.total_capital().

    v7.0.1: first wired stock. Demonstrates the pattern for future stocks
    (loan_portfolio, deposit_base, npl_inventory, customer_base,
    dormant_accounts).
    """
    try:
        from utils.capital_adequacy import (CapitalAdequacyEngine,
            CapitalComponents)
    except ImportError as e:
        return {
            "stock_id": stock.stock_id,
            "name": stock.name,
            "status": STOCK_NOT_WIRED,
            "value": None,
            "unit": stock.unit,
            "reason": f"capital_adequacy import failed: {e}",
        }

    # If caller didn't supply inputs, use realistic Tier-2 Kenya bank
    # defaults so the systems-view page can render something useful.
    # Per Rule 6, this is documented as 'DEMO_DEFAULTS' status, not
    # silently fabricated.
    used_defaults = False
    if capital_components is None or total_rwa_kes is None:
        used_defaults = True
        from decimal import Decimal as _D
        capital_components = CapitalComponents(
            paid_up_capital_kes=_D("12000000000"),    # 12B
            share_premium_kes=_D("0"),
            retained_earnings_kes=_D("12000000000"),  # 8B retained + 4B reserves
            accumulated_oci_kes=_D("0"),
            goodwill_kes=_D("0"),
            other_intangibles_kes=_D("500000000"),     # 0.5B
            deferred_tax_assets_kes=_D("300000000"),   # 0.3B
            subordinated_debt_kes=_D("3000000000"),    # 3B
            general_provisions_kes=_D("1000000000"),   # 1B
        )
        total_rwa_kes = _D("100000000000")  # 100B RWA

    try:
        result = CapitalAdequacyEngine.total_capital(
            capital_components, total_rwa_kes)
    except Exception as e:
        return {
            "stock_id": stock.stock_id,
            "name": stock.name,
            "status": "ERROR",
            "value": None,
            "unit": stock.unit,
            "reason": f"total_capital() raised {type(e).__name__}: {e}",
        }

    return {
        "stock_id": stock.stock_id,
        "name": stock.name,
        "status": STOCK_WIRED,
        "value": result.get("total_capital_kes"),
        "unit": stock.unit,
        "tier1_kes": result.get("tier1_kes"),
        "tier2_kes": result.get("tier2_kes_capped"),
        "period_change": None,  # Period-over-period requires history; future
        "contributors_defined": list(stock.contributors),
        "drainers_defined": list(stock.drainers),
        "data_source": (
            "demo_defaults (Tier-2 Kenya bank baseline)" if used_defaults
            else "caller-supplied capital_components + total_rwa_kes"
        ),
        "rwa_basis_kes": str(total_rwa_kes),
    }


def list_stocks() -> List[Dict[str, Any]]:
    """Return summary of all 6 stocks for display."""
    return [
        {
            "stock_id": s.stock_id,
            "name": s.name,
            "unit": s.unit,
            "owner_context": s.owner_context,
            "contributors": len(s.contributors),
            "drainers": len(s.drainers),
            "status": s.status,
        }
        for s in SYSTEM_STOCKS.values()
    ]


def stocks_by_status() -> Dict[str, List[str]]:
    """Group stocks by wiring status for at-a-glance view."""
    by_status: Dict[str, List[str]] = {
        STOCK_WIRED: [],
        STOCK_PARTIAL: [],
        STOCK_NOT_WIRED: [],
    }
    for stock in SYSTEM_STOCKS.values():
        by_status.setdefault(stock.status, []).append(stock.stock_id)
    return by_status


# Convenience: counts for systems-view dashboard
def stock_count_by_status() -> Dict[str, int]:
    return {k: len(v) for k, v in stocks_by_status().items()}


# ──────────────────────────────────────────────────────────────────────
# v7.1: loan_portfolio + npl_inventory snapshot accessors
# ──────────────────────────────────────────────────────────────────────

def _loan_portfolio_snapshot(stock: SystemStock) -> Dict[str, Any]:
    """Live snapshot for loan_portfolio.

    v7.10: wired to FLEXCUBE Aggregator (utils.flexcube_aggregator).
    Mode-aware ACL pattern (Charter §7):
        - mode=live → calls FLEXCUBE Apigee (stub today, v8.x ready)
        - mode=synthetic/mock → reads cbs_data/ aggregates if available
        - else → demo defaults (Tier-2 Kenya bank book)

    The `data_source` field is the v7.10 honesty contract — every snapshot
    explicitly states whether figures came from live, CBS synthetic, or
    demo defaults.
    """
    from utils.flexcube_aggregator import fetch_loan_portfolio_aggregate
    from decimal import Decimal as _D

    agg = fetch_loan_portfolio_aggregate()

    return {
        "stock_id": stock.stock_id,
        "name": stock.name,
        "status": STOCK_WIRED,
        "value": agg["gross_outstanding_kes"],
        "unit": stock.unit,
        "by_segment_kes": agg["by_segment_kes"],
        "by_ifrs9_stage_kes": agg["by_stage_kes"],
        "weighted_avg_pd_pct": agg.get("weighted_avg_pd_pct"),
        "average_lgd_pct": agg.get("average_lgd_pct"),
        "period_change": None,  # period-over-period requires history
        "contributors_defined": list(stock.contributors),
        "drainers_defined": list(stock.drainers),
        "data_source": (
            f"flexcube_aggregator: {agg['data_source']} (mode={agg['mode']}). "
            f"v7.10 wired to ACL — when FLEXCUBE goes live, no caller change needed."
        ),
    }


def _npl_inventory_snapshot(stock: SystemStock) -> Dict[str, Any]:
    """Live snapshot for npl_inventory.

    v7.10: wired to FLEXCUBE Aggregator. Stage 3 = 8B KES = 10% NPL ratio
    (matches loan_portfolio basis from same aggregator). NPL ratio is
    computed against loan_portfolio so caller can reason about it cleanly.

    Linked to feedback loop L01 (Collections → PD recalibration), wired in v7.1.
    """
    from utils.flexcube_aggregator import fetch_npl_aggregate

    agg = fetch_npl_aggregate()

    return {
        "stock_id": stock.stock_id,
        "name": stock.name,
        "status": STOCK_WIRED,
        "value": agg["stage_3_kes"],
        "unit": stock.unit,
        "npl_ratio_pct": agg["npl_ratio_pct"],
        "by_aging_kes": agg.get("by_aging_kes", {}),
        "loan_book_basis_kes": agg["loan_book_basis_kes"],
        "period_change": None,
        "contributors_defined": list(stock.contributors),
        "drainers_defined": list(stock.drainers),
        "data_source": (
            f"flexcube_aggregator: {agg['data_source']} (mode={agg['mode']}). "
            f"v7.10 wired to ACL — when FLEXCUBE goes live, no caller change needed."
        ),
    }


def _deposit_base_snapshot(stock: SystemStock) -> Dict[str, Any]:
    """Live snapshot for deposit_base.

    v7.10: wired to FLEXCUBE Aggregator. Same ACL that drives
    loan_portfolio + npl_inventory snapshots — when FLEXCUBE goes live,
    no caller change needed.
    """
    from utils.flexcube_aggregator import fetch_deposit_book_aggregate

    agg = fetch_deposit_book_aggregate()

    return {
        "stock_id": stock.stock_id,
        "name": stock.name,
        "status": STOCK_WIRED,
        "value": agg["total_deposits_kes"],
        "unit": stock.unit,
        "by_stability_tier_kes": agg["by_stability_tier_kes"],
        "by_product_kes": agg["by_product_kes"],
        "by_segment_kes": agg["by_segment_kes"],
        "loan_to_deposit_ratio_pct": agg["loan_to_deposit_ratio_pct"],
        "loan_book_basis_kes": "80000000000",  # v8.x: cross-aggregate LDR computation
        "period_change": None,
        "contributors_defined": list(stock.contributors),
        "drainers_defined": list(stock.drainers),
        "data_source": (
            f"flexcube_aggregator: {agg['data_source']} (mode={agg['mode']}). "
            f"v7.10 wired to ACL — when FLEXCUBE goes live, no caller change needed."
        ),
    }


def _customer_base_snapshot(stock: SystemStock) -> Dict[str, Any]:
    """Live snapshot for customer_base.

    v7.11: wired to FLEXCUBE Aggregator. Same ACL pattern as the v7.10
    loan_portfolio + deposit_base + npl_inventory wiring.
    """
    from utils.flexcube_aggregator import fetch_customer_base_aggregate

    agg = fetch_customer_base_aggregate()

    return {
        "stock_id": stock.stock_id,
        "name": stock.name,
        "status": STOCK_WIRED,
        "value": str(agg["total_customers"]),
        "unit": stock.unit,
        "by_segment_count": agg["by_segment_count"],
        "by_tenure_band_count": agg["by_tenure_band_count"],
        "by_onboarding_channel_count": agg["by_onboarding_channel_count"],
        "by_kyc_risk_band_count": agg["by_kyc_risk_band_count"],
        "monthly_growth_rate_pct": agg["monthly_growth_rate_pct"],
        "period_change": None,
        "contributors_defined": list(stock.contributors),
        "drainers_defined": list(stock.drainers),
        "data_source": (
            f"flexcube_aggregator: {agg['data_source']} (mode={agg['mode']}). "
            f"v7.11 wired to ACL — when CBS goes live, no caller change needed."
        ),
    }


def _dormant_accounts_snapshot(stock: SystemStock) -> Dict[str, Any]:
    """Live snapshot for dormant_accounts.

    v7.11: wired to FLEXCUBE Aggregator. Same ACL pattern as the v7.10
    loan_portfolio + deposit_base + npl_inventory wiring. Three dormancy
    bands per CBK guidance + bank policy: 90 / 180 / 365 days.
    """
    from utils.flexcube_aggregator import fetch_dormant_accounts_aggregate

    agg = fetch_dormant_accounts_aggregate()

    return {
        "stock_id": stock.stock_id,
        "name": stock.name,
        "status": STOCK_WIRED,
        "value": str(agg["total_dormant"]),
        "unit": stock.unit,
        "by_dormancy_band_count": agg["by_dormancy_band_count"],
        "by_segment_count": agg["by_segment_count"],
        "dormancy_rate_pct": agg["dormancy_rate_pct"],
        "customer_basis_count": agg["customer_basis_count"],
        "reactivation_potential_count": agg["reactivation_potential_count"],
        "avg_balance_per_dormant_kes": agg["avg_balance_per_dormant_kes"],
        "estimated_latent_value_kes": agg["estimated_latent_value_kes"],
        "period_change": None,
        "contributors_defined": list(stock.contributors),
        "drainers_defined": list(stock.drainers),
        "data_source": (
            f"flexcube_aggregator: {agg['data_source']} (mode={agg['mode']}). "
            f"v7.11 wired to ACL — when CBS goes live, no caller change needed."
        ),
    }
