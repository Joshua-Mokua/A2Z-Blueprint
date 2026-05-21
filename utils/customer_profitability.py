"""utils.customer_profitability — Customer 360 Profitability Engine
(Standard #21, v5.46). Volume Three.

Per the master spec:

    class CustomerProfitabilityEngine:
        def calculate_customer_pnl(self, customer_id, period):
            revenue        = {"interest_income": ...}
            direct_costs   = {"interest_expense": ...}
            indirect_costs = self.allocate_indirect_costs(customer, period)
            pbt = sum(revenue.values()) - sum(direct_costs.values()) - sum(indirect_costs.values())
            return {"pbt": pbt, "pbt_margin": pbt / sum(revenue.values())}

Verification:
  - Matches Excel within 0.5%  ← VERIFIABLE in code via labeled
                                   fixtures with Excel-computed
                                   expected PBT. Audit gate G32.

This is the most consequential engine in the platform so far.
Customer PBT flows into board reports, SBU performance, RM
scorecards, and strategic decisions about which relationships to
retain. Dishonest math here is dishonest financial reporting.

V5.45 → V5.46 — FTP CORRECTION
==============================
v5.45 shipped a naive "gross-interest" treatment: revenue was
loan interest collected, direct cost was deposit interest paid.
That made deposit-only customers look loss-making (fixture P018:
revenue 2,000 − interest_expense 8,000 = PBT -6,000) — which is
wrong on the economics. A deposit-only customer is NOT a loss to
the bank: their deposits fund lending elsewhere, and that lending
generates the spread which pays the depositor and earns margin.

Real bank profitability accounting splits the interest book into
two sides via an internal Funds Transfer Price (FTP). v5.46 adds
the FTP-aware mode:

  Deposit side (customer is a funder):
    ftp_credit_on_deposits = deposit_bal × (FTP_rate - deposit_rate_paid)
    → revenue, because the deposits create funding-value the bank
      uses to make loans elsewhere.

  Loan side (customer is a user of funds):
    ftp_charge_on_loans = loan_bal × FTP_rate
    → direct cost, because the loan consumes the bank's funding pool;
      customer is credited with rate_charged, charged FTP_rate, so
      net interest income to the customer = loan_bal × (rate_charged
      - FTP_rate). This is the lending margin only.

The two sides sum to the bank's actual NIM, with each customer
credited only for the half they create. No double-counting, no
false losses, no false windfalls.

FTP MODES
---------
The engine has two modes, selected at construction:

  ftp_mode = "off" (DEFAULT)
    Engine behaves as v5.45 did: gross-interest revenue,
    gross-interest direct cost. Backward-compatible with the
    existing 20 fixtures.

  ftp_mode = "on"
    Engine pulls FTP rate + balances from `ftp_inputs_fn` and
    adds two extra buckets:
      revenue.ftp_credit_on_deposits
      direct_costs.ftp_charge_on_loans
    The existing interest_income/interest_expense buckets stay
    populated (the customer is credited with what they actually
    paid/received). PBT is the sum of all buckets — both halves
    of the FTP split are visible on every report.

WHAT FTP MODE = "on" REQUIRES FROM THE CALLER
---------------------------------------------
ftp_inputs_fn(customer_id, period) → dict with:
  ftp_rate:          internal funding rate, e.g. 0.08 for 8%
  deposit_balance:   customer's average deposit balance for period
  deposit_rate_paid: weighted-average rate paid to customer (already
                      reflected in interest_expense, used for sanity)
  loan_balance:      customer's average loan balance for period
  period_fraction:   what fraction of a year the period covers
                      (1/12 for monthly, 1/4 for quarterly, 1.0 yearly)

Production deployments will need a curve-based FTP lookup
(different rates for different tenors / products). v5.46 ships a
flat FTP rate and documents the simplification in
meta.ftp_simplifications. Curve support is future work.

BALANCE BASIS
-------------
Banks compute interest on AVERAGE balance over the period, not
end-of-period snapshot. Our seed data has snapshots, not averages.
The engine accepts whatever the caller supplies and records the
choice in meta.balance_basis ("average" | "spot" | "unknown") so
auditors can trace the answer.

THE FORMULA — V5.46
-------------------
    PBT = revenue - direct_costs - indirect_costs

Where in ftp_mode = "on":

  Revenue:
    interest_income                — interest customer paid on lending
    fee_income                     — account/transaction fees, FX margin
    other_income                   — investment, insurance, etc.
    ftp_credit_on_deposits         — funding value of customer deposits

  Direct costs:
    interest_expense               — interest paid to customer on deposits
    loan_loss_provisions           — IFRS-9 ECL allocated
    transaction_costs              — direct processing costs
    ftp_charge_on_loans            — internal funding cost of customer loans

  Indirect costs:
    allocated_overhead             — share of central costs

In ftp_mode = "off" (default) the two ftp_* buckets are absent.

INDIRECT COST ALLOCATION
------------------------
Unchanged from v5.45. Production deployments choose:
  equal_per_customer / revenue_weighted (DEFAULT) /
  asset_weighted / activity_weighted

HONESTY RULES (UNCHANGED FROM V5.45 + ONE NEW)
-----------------------------------------------
1. Engine NEVER fabricates revenue or cost components.
2. pbt_margin returned as None when total_revenue ≤ 0.
3. Returns {} for unknown customer.
4. Decimal-internal at precision 28; output 2dp.
5. meta records every input bucket with source.
6. **NEW:** When ftp_mode="on" but ftp_inputs_fn returns
   incomplete data (missing rate or balances), the engine
   does NOT silently fall back to ftp_mode="off". Instead it
   logs the missing inputs in meta.ftp_missing and skips the
   FTP buckets for THAT customer (other components still
   compute normally). This makes data-quality issues visible
   on a per-customer basis rather than hidden in aggregate.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field, asdict
from datetime import date, datetime, timezone
from decimal import Decimal, ROUND_HALF_UP, getcontext
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger("a2z.profitability")

# Use enough precision for KES-scale balance-sheet math (10 figures comfortably)
getcontext().prec = 28

ROOT = Path(__file__).parent.parent
DATA_DIR = ROOT / "data"
CUSTOMER_PNL_FILE = DATA_DIR / "customer_pnl.json"

ZERO = Decimal("0")

# ── Spec-aligned tolerance ───────────────────────────────────────────
EXCEL_MATCH_TOLERANCE = Decimal("0.005")    # ±0.5%

# ── Allocation method enum ───────────────────────────────────────────
ALLOCATION_METHODS = (
    "equal_per_customer",
    "revenue_weighted",
    "asset_weighted",
    "activity_weighted",
)
DEFAULT_ALLOCATION_METHOD = "revenue_weighted"


# ─────────────────────────────────────────────────────────────────────
# Data model
# ─────────────────────────────────────────────────────────────────────

@dataclass
class CustomerPnL:
    customer_id:         str = ""
    period:              str = ""
    revenue:             Dict[str, float] = field(default_factory=dict)
    direct_costs:        Dict[str, float] = field(default_factory=dict)
    indirect_costs:      Dict[str, float] = field(default_factory=dict)
    pbt:                 float = 0.0
    pbt_margin:          Optional[float] = None
    total_revenue:       float = 0.0
    total_direct_costs:  float = 0.0
    total_indirect_costs: float = 0.0
    generated_at:        str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


# ─────────────────────────────────────────────────────────────────────
# Engine
# ─────────────────────────────────────────────────────────────────────

class CustomerProfitabilityEngine:
    """Standard #21 — Customer 360 Profitability Engine.

    Stateless: each call returns a fresh PnL dict. Persistence is the
    caller's responsibility (use save_pnl).
    """

    def __init__(
        self,
        customer_lookup_fn:   Optional[Callable[[str], Optional[dict]]] = None,
        revenue_fn:           Optional[Callable[[str, str], Dict[str, Decimal]]] = None,
        direct_costs_fn:      Optional[Callable[[str, str], Dict[str, Decimal]]] = None,
        overhead_pool_fn:     Optional[Callable[[str], Decimal]] = None,
        allocation_inputs_fn: Optional[Callable[[str, str], dict]] = None,
        allocation_method:    str = DEFAULT_ALLOCATION_METHOD,
        ftp_mode:             str = "off",
        ftp_inputs_fn:        Optional[Callable[[str, str], Optional[dict]]] = None,
        balance_basis:        str = "unknown",
    ):
        """All collaborators injectable.

        customer_lookup_fn(customer_id) → dict | None
            Returns customer record (CIF, segment, tags). Default
            reads data/customer_intelligence.json.

        revenue_fn(customer_id, period) → dict[str, Decimal]
            Returns the revenue components (interest_income,
            fee_income, other_income, etc.). Each value is
            Decimal for precision.

        direct_costs_fn(customer_id, period) → dict[str, Decimal]
            Returns direct cost components (interest_expense,
            loan_loss_provisions, transaction_costs).

        overhead_pool_fn(period) → Decimal
            Returns total bank-wide indirect cost pool for the period.

        allocation_inputs_fn(customer_id, period) → dict with keys:
            - customer_count:   total active customers in period
            - my_revenue:       this customer's revenue (revenue_weighted)
            - total_revenue:    bank-wide total revenue (revenue_weighted)
            - my_assets:        loan + deposit balances (asset_weighted)
            - total_assets:     bank-wide totals (asset_weighted)
            - my_activity:      transaction count (activity_weighted)
            - total_activity:   bank-wide transaction count (activity_weighted)

        allocation_method: one of ALLOCATION_METHODS (default
            revenue_weighted).

        ftp_mode: "off" (DEFAULT) | "on"
            "off" → engine ignores FTP. revenue/direct buckets are
                    exactly what the caller supplies (gross-interest
                    treatment from v5.45). All existing fixtures work
                    in this mode.
            "on"  → engine adds two extra buckets:
                      revenue.ftp_credit_on_deposits
                      direct_costs.ftp_charge_on_loans
                    derived from ftp_inputs_fn output.

        ftp_inputs_fn(customer_id, period) → dict | None
            Required when ftp_mode = "on". Returns:
              ftp_rate:          internal funding rate, e.g. 0.08
              deposit_balance:   customer's deposit balance for period
              deposit_rate_paid: weighted-average rate paid (sanity)
              loan_balance:      customer's loan balance for period
              period_fraction:   fraction of year (1/12, 1/4, 1.0)
            Returns None when FTP inputs unavailable for THIS customer
            — engine logs in meta.ftp_missing and skips FTP buckets
            for THAT customer (other components still compute).

        balance_basis: "average" | "spot" | "unknown" (DEFAULT)
            Records what the supplied balances represent. Banks compute
            interest on average balance over the period; production
            deployments should pass "average". Recorded in meta for
            audit traceability — does NOT affect the math.
        """
        if allocation_method not in ALLOCATION_METHODS:
            raise ValueError(
                f"allocation_method must be one of {ALLOCATION_METHODS}, "
                f"got {allocation_method!r}"
            )
        if ftp_mode not in ("off", "on"):
            raise ValueError(
                f"ftp_mode must be 'off' or 'on', got {ftp_mode!r}"
            )
        if balance_basis not in ("average", "spot", "unknown"):
            raise ValueError(
                f"balance_basis must be 'average'/'spot'/'unknown', got {balance_basis!r}"
            )
        self._customer_lookup    = customer_lookup_fn   or _default_customer_lookup
        self._revenue            = revenue_fn           or _default_revenue
        self._direct_costs       = direct_costs_fn      or _default_direct_costs
        self._overhead_pool      = overhead_pool_fn     or _default_overhead_pool
        self._allocation_inputs  = allocation_inputs_fn or _default_allocation_inputs
        self._allocation_method  = allocation_method
        self._ftp_mode           = ftp_mode
        self._ftp_inputs         = ftp_inputs_fn        or _default_ftp_inputs
        self._balance_basis      = balance_basis

    # ──────────────────────────────────────────────────────────────────
    # Spec entry
    # ──────────────────────────────────────────────────────────────────

    def calculate_customer_pnl(
        self, customer_id: str, period: str,
    ) -> Dict[str, Any]:
        """Compute one customer's one-period PBT.

        Returns the spec-shaped dict (with extensions for traceability):
            {
              "pbt": float,
              "pbt_margin": float | None,
              "revenue": {component: amount, ...},
              "direct_costs": {component: amount, ...},
              "indirect_costs": {component: amount, ...},
              "total_revenue": float,
              "total_direct_costs": float,
              "total_indirect_costs": float,
              "meta": {...},
            }

        Returns {} for unknown customer.
        """
        if not customer_id or not period:
            return {}

        customer = self._customer_lookup(customer_id)
        if not customer:
            return {}

        # ── Collect revenue (Decimal precision) ────────────────────────
        revenue_raw = self._revenue(customer_id, period) or {}
        revenue: Dict[str, Decimal] = {}
        missing_components: List[str] = []
        for k, v in revenue_raw.items():
            try:
                revenue[k] = Decimal(str(v)) if v is not None else ZERO
            except Exception:
                revenue[k] = ZERO
                missing_components.append(f"revenue.{k}")

        # ── Collect direct costs ──────────────────────────────────────
        direct_raw = self._direct_costs(customer_id, period) or {}
        direct_costs: Dict[str, Decimal] = {}
        for k, v in direct_raw.items():
            try:
                direct_costs[k] = Decimal(str(v)) if v is not None else ZERO
            except Exception:
                direct_costs[k] = ZERO
                missing_components.append(f"direct_costs.{k}")

        # ── FTP buckets (only when ftp_mode = "on") ──────────────────
        # Honesty rule: when FTP inputs are incomplete for this
        # customer, we DO NOT silently fall back to "off". We log
        # the missing inputs in meta.ftp_missing and skip the FTP
        # buckets for THIS customer; other components still compute.
        ftp_missing: List[str] = []
        ftp_rate_used: Optional[Decimal] = None
        ftp_simplifications: List[str] = []
        if self._ftp_mode == "on":
            ftp_inputs = self._ftp_inputs(customer_id, period)
            if not ftp_inputs:
                ftp_missing.append("ftp_inputs_fn returned None")
            else:
                # Pull and validate inputs
                rate = ftp_inputs.get("ftp_rate")
                dep_bal = ftp_inputs.get("deposit_balance")
                dep_rate = ftp_inputs.get("deposit_rate_paid")
                loan_bal = ftp_inputs.get("loan_balance")
                pf = ftp_inputs.get("period_fraction")

                missing_keys = []
                if rate is None:
                    missing_keys.append("ftp_rate")
                if pf is None:
                    missing_keys.append("period_fraction")
                # Deposit-side and loan-side are independently optional.
                # A pure-loan customer can have deposit_balance=0; a
                # pure-deposit customer can have loan_balance=0. Only
                # the rate + period_fraction are universally required.

                if missing_keys:
                    ftp_missing.extend(missing_keys)
                else:
                    try:
                        rate_d    = Decimal(str(rate))
                        pf_d      = Decimal(str(pf))
                        dep_bal_d = Decimal(str(dep_bal))    if dep_bal is not None  else ZERO
                        dep_rate_d= Decimal(str(dep_rate))   if dep_rate is not None else ZERO
                        loan_bal_d= Decimal(str(loan_bal))   if loan_bal is not None else ZERO
                        ftp_rate_used = rate_d
                        ftp_simplifications.append("flat_ftp_rate (no curve lookup)")

                        # Deposit side: ftp_credit = bal × (FTP - paid_rate) × period_fraction
                        # Only added when there's a real deposit balance.
                        if dep_bal_d > ZERO:
                            credit = dep_bal_d * (rate_d - dep_rate_d) * pf_d
                            revenue["ftp_credit_on_deposits"] = credit

                        # Loan side: funding charge = loan_bal × FTP × period_fraction
                        if loan_bal_d > ZERO:
                            charge = loan_bal_d * rate_d * pf_d
                            direct_costs["ftp_charge_on_loans"] = charge
                    except Exception as e:
                        ftp_missing.append(f"ftp_compute_error:{e}")

        # ── Allocate indirect costs ───────────────────────────────────
        indirect_costs = self._compute_indirect_costs(customer_id, period)

        # ── PBT ───────────────────────────────────────────────────────
        total_revenue = sum(revenue.values(), start=ZERO)
        total_direct  = sum(direct_costs.values(), start=ZERO)
        total_indirect = sum(indirect_costs.values(), start=ZERO)
        pbt = total_revenue - total_direct - total_indirect

        # ── Margin: HONEST about division-by-zero ─────────────────────
        # Spec formula: pbt / revenue. Meaningless if revenue ≤ 0.
        if total_revenue > ZERO:
            margin = pbt / total_revenue
            margin_out = float(margin.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP))
        else:
            margin_out = None
            missing_components.append("pbt_margin (revenue ≤ 0)")

        return {
            "pbt":                  _money(pbt),
            "pbt_margin":           margin_out,
            "revenue":              {k: _money(v) for k, v in revenue.items()},
            "direct_costs":         {k: _money(v) for k, v in direct_costs.items()},
            "indirect_costs":       {k: _money(v) for k, v in indirect_costs.items()},
            "total_revenue":        _money(total_revenue),
            "total_direct_costs":   _money(total_direct),
            "total_indirect_costs": _money(total_indirect),
            "meta": {
                "customer_id":          customer_id,
                "customer_segment":     customer.get("segment", ""),
                "period":               period,
                "allocation_method":    self._allocation_method,
                "missing_components":   missing_components,
                "input_currency":       "KES",
                "precision":            "Decimal-internal, 2dp output",
                "tolerance_excel_pct":  float(EXCEL_MATCH_TOLERANCE * 100),
                "ftp_mode":             self._ftp_mode,
                "ftp_rate":             float(ftp_rate_used) if ftp_rate_used is not None else None,
                "ftp_missing":          ftp_missing,
                "ftp_simplifications":  ftp_simplifications,
                "balance_basis":        self._balance_basis,
                "generated_at":         datetime.now(timezone.utc).isoformat(),
            },
        }

    # ──────────────────────────────────────────────────────────────────
    # Indirect cost allocation
    # ──────────────────────────────────────────────────────────────────

    def _compute_indirect_costs(
        self, customer_id: str, period: str,
    ) -> Dict[str, Decimal]:
        """Allocate the bank's indirect cost pool to this customer."""
        pool = self._overhead_pool(period)
        if pool is None:
            return {"allocated_overhead": ZERO}
        try:
            pool_d = Decimal(str(pool))
        except Exception:
            return {"allocated_overhead": ZERO}
        if pool_d <= ZERO:
            return {"allocated_overhead": ZERO}

        inputs = self._allocation_inputs(customer_id, period) or {}
        allocated = self._allocate(pool_d, inputs)
        return {"allocated_overhead": allocated}

    def _allocate(self, pool: Decimal, inputs: dict) -> Decimal:
        method = self._allocation_method
        try:
            if method == "equal_per_customer":
                count = int(inputs.get("customer_count", 0) or 0)
                if count <= 0:
                    return ZERO
                return pool / Decimal(count)

            if method == "revenue_weighted":
                my = Decimal(str(inputs.get("my_revenue", 0) or 0))
                total = Decimal(str(inputs.get("total_revenue", 0) or 0))
                if total <= ZERO:
                    return ZERO
                return pool * (my / total)

            if method == "asset_weighted":
                my = Decimal(str(inputs.get("my_assets", 0) or 0))
                total = Decimal(str(inputs.get("total_assets", 0) or 0))
                if total <= ZERO:
                    return ZERO
                return pool * (my / total)

            if method == "activity_weighted":
                my = Decimal(str(inputs.get("my_activity", 0) or 0))
                total = Decimal(str(inputs.get("total_activity", 0) or 0))
                if total <= ZERO:
                    return ZERO
                return pool * (my / total)

        except Exception as e:
            logger.warning("profitability: allocation error: %s", e)
            return ZERO
        return ZERO


# ─────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────

def _money(d: Decimal) -> float:
    """Round to 2dp for output (currency precision)."""
    if not isinstance(d, Decimal):
        try:
            d = Decimal(str(d))
        except Exception:
            return 0.0
    return float(d.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def _safe_load(path: Path, default):
    try:
        from utils.db import db
        return db.load_json(path, default=default)
    except Exception as e:
        logger.warning("profitability: could not load %s: %s", path, e)
        return default


# ─────────────────────────────────────────────────────────────────────
# Default collaborators (best-effort over current seed data)
# ─────────────────────────────────────────────────────────────────────

def _default_customer_lookup(customer_id: str) -> Optional[dict]:
    """v10.381 — canonical lookup consuming v10.378 unified customer master.

    Per Joshua's Phase B roadmap: parallel profitability engines (customer
    and RM) should consume the canonical customer master rather than read
    customer_intelligence.json directly. This makes them see CBS-merged
    data with full lineage (the v10.378 unification).

    Resolution order:
      1. Try the v10.378 canonical engine (compute_unified_customer_master)
      2. Fall back to direct customer_intelligence.json read (legacy)

    The fallback ensures: (a) no breakage if v10.378 module is unavailable
    (old deployments); (b) customers in the legacy file but not in CBS
    still resolve.

    Engine consumer contract: returns a plain dict with at minimum a
    `segment` field (the only one currently used by the engine).
    """
    # Try canonical path first
    rec_dict = _canonical_customer_lookup_v10381(customer_id)
    if rec_dict is not None:
        return rec_dict
    # Legacy fallback
    return _legacy_customer_intelligence_lookup(customer_id)


# Module-level cache for unified master (avoid recomputing on every lookup)
_UNIFIED_MASTER_CACHE: Optional[Dict[str, Any]] = None


def _canonical_customer_lookup_v10381(customer_id: str) -> Optional[dict]:
    """Look up customer via the v10.378 canonical engine.

    Caches the unified master at module level — compute_unified_customer_master
    iterates all sources, so we run it once per process. Returns None if
    canonical engine unavailable or customer not found there.
    """
    global _UNIFIED_MASTER_CACHE
    try:
        from dataclasses import asdict
        if _UNIFIED_MASTER_CACHE is None:
            from utils.customer_master_canonical import compute_unified_customer_master
            _UNIFIED_MASTER_CACHE = compute_unified_customer_master(cbs_dir=None)
        rec = _UNIFIED_MASTER_CACHE.get(str(customer_id))
        if rec is None:
            return None
        return asdict(rec)
    except Exception:
        # Canonical engine unavailable (old deployment) — fall through
        return None


def reset_canonical_customer_cache() -> None:
    """Reset the module-level unified-master cache.

    Test helper — call this between tests that change customer data. Also
    useful when CBS data refreshes during a running process.
    """
    global _UNIFIED_MASTER_CACHE
    _UNIFIED_MASTER_CACHE = None


def _legacy_customer_intelligence_lookup(customer_id: str) -> Optional[dict]:
    """Pre-v10.381 lookup: reads customer_intelligence.json directly.

    Preserved as fallback for: (a) v10.378 module unavailable, (b) customers
    in marketing intel but not yet merged through the canonical engine.
    """
    raw = _safe_load(DATA_DIR / "customer_intelligence.json", {})
    if not isinstance(raw, dict):
        return None
    rec = raw.get(str(customer_id))
    if isinstance(rec, dict):
        return rec
    # Some seed shapes nest under "customers"
    if isinstance(raw.get("customers"), dict):
        rec = raw["customers"].get(str(customer_id))
        if isinstance(rec, dict):
            return rec
    return None


def _default_revenue(customer_id: str, period: str) -> Dict[str, Decimal]:
    """Best-effort revenue assembly from available seed data.

    NOTE: real production deployments would source these from FLEXCUBE
    GL movements per customer per period. Default returns ZEROS for
    seed data — caller should inject a real source.
    """
    return {
        "interest_income": ZERO,
        "fee_income":      ZERO,
        "other_income":    ZERO,
    }


def _default_direct_costs(customer_id: str, period: str) -> Dict[str, Decimal]:
    return {
        "interest_expense":     ZERO,
        "loan_loss_provisions": ZERO,
        "transaction_costs":    ZERO,
    }


def _default_overhead_pool(period: str) -> Decimal:
    return ZERO


def _default_allocation_inputs(customer_id: str, period: str) -> dict:
    return {
        "customer_count":  0,
        "my_revenue":      0,
        "total_revenue":   0,
        "my_assets":       0,
        "total_assets":    0,
        "my_activity":     0,
        "total_activity":  0,
    }


def _default_ftp_inputs(customer_id: str, period: str) -> Optional[dict]:
    """Default returns None — FTP requires explicit caller wiring.

    Production deployments inject ftp_inputs_fn that reads the bank's
    published FTP curve + per-customer balances from FLEXCUBE GL.
    """
    return None


# ─────────────────────────────────────────────────────────────────────
# Persistence
# ─────────────────────────────────────────────────────────────────────

def save_pnl(customer_id: str, period: str, pnl: dict) -> bool:
    if not pnl or not customer_id or not period:
        return False
    try:
        from utils.db import db
        existing = db.load_json(CUSTOMER_PNL_FILE, default={})
    except Exception:
        existing = {}
    if not isinstance(existing, dict):
        existing = {}
    by_customer = existing.setdefault(str(customer_id), {})
    if not isinstance(by_customer, dict):
        by_customer = {}
        existing[str(customer_id)] = by_customer
    by_customer[period] = pnl
    try:
        from utils.db import db
        db.save_json(CUSTOMER_PNL_FILE, existing)
        return True
    except Exception as e:
        logger.error("profitability: could not save: %s", e)
        return False


def get_pnl(customer_id: str, period: str) -> Optional[dict]:
    try:
        from utils.db import db
        existing = db.load_json(CUSTOMER_PNL_FILE, default={})
    except Exception:
        return None
    if not isinstance(existing, dict):
        return None
    by_c = existing.get(str(customer_id), {})
    if not isinstance(by_c, dict):
        return None
    return by_c.get(period)


# ─────────────────────────────────────────────────────────────────────
# Self-test (`python -m utils.customer_profitability`)
# ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("A2Z MIS 360 — utils.customer_profitability self-test")

    customers = {
        "C100": {"cif": "C100", "segment": "Corporate"},
        "C200": {"cif": "C200", "segment": "Mass"},
        "C300": {"cif": "C300", "segment": "SME"},
    }
    revenue = {
        # Big corporate: high revenue
        ("C100", "2026-04"): {
            "interest_income": Decimal("500000"),
            "fee_income":      Decimal("80000"),
            "other_income":    Decimal("20000"),
        },
        # Mass retail: small revenue
        ("C200", "2026-04"): {
            "interest_income": Decimal("3000"),
            "fee_income":      Decimal("500"),
            "other_income":    Decimal("0"),
        },
        # SME: moderate
        ("C300", "2026-04"): {
            "interest_income": Decimal("80000"),
            "fee_income":      Decimal("12000"),
            "other_income":    Decimal("3000"),
        },
        # Low-revenue customer (margin → meaningful number near 0)
        ("C400", "2026-04"): {
            "interest_income": Decimal("1"),
            "fee_income":      Decimal("0"),
            "other_income":    Decimal("0"),
        },
    }
    direct = {
        ("C100", "2026-04"): {
            "interest_expense":     Decimal("180000"),
            "loan_loss_provisions": Decimal("25000"),
            "transaction_costs":    Decimal("8000"),
        },
        ("C200", "2026-04"): {
            "interest_expense":     Decimal("400"),
            "loan_loss_provisions": Decimal("100"),
            "transaction_costs":    Decimal("50"),
        },
        ("C300", "2026-04"): {
            "interest_expense":     Decimal("28000"),
            "loan_loss_provisions": Decimal("4000"),
            "transaction_costs":    Decimal("1500"),
        },
    }
    pool = Decimal("100000")
    alloc_inputs = {
        ("C100", "2026-04"): {
            "customer_count": 4, "my_revenue": 600000, "total_revenue": 698501,
        },
        ("C200", "2026-04"): {
            "customer_count": 4, "my_revenue": 3500, "total_revenue": 698501,
        },
        ("C300", "2026-04"): {
            "customer_count": 4, "my_revenue": 95000, "total_revenue": 698501,
        },
    }

    eng = CustomerProfitabilityEngine(
        customer_lookup_fn=lambda c: customers.get(c),
        revenue_fn=lambda c, p: revenue.get((c, p), {}),
        direct_costs_fn=lambda c, p: direct.get((c, p), {}),
        overhead_pool_fn=lambda p: pool,
        allocation_inputs_fn=lambda c, p: alloc_inputs.get((c, p), {}),
        allocation_method="revenue_weighted",
    )

    # Case 1: Spec contract — has pbt, pbt_margin
    r = eng.calculate_customer_pnl("C100", "2026-04")
    assert "pbt" in r and "pbt_margin" in r
    print(f"  ✅ spec keys present")

    # Case 2: PBT math correct
    # Revenue = 500000 + 80000 + 20000 = 600000
    # Direct = 180000 + 25000 + 8000 = 213000
    # Indirect = pool * (600000/698501) = 100000 * 0.8590 ≈ 85896.51
    # PBT = 600000 - 213000 - 85896.51 ≈ 301103.49
    expected_indirect = float(pool) * (600000 / 698501)
    expected_pbt = 600000 - 213000 - expected_indirect
    assert abs(r["pbt"] - expected_pbt) < 0.5, f"pbt={r['pbt']}, expected≈{expected_pbt}"
    print(f"  ✅ C100 PBT={r['pbt']:.2f} (expected≈{expected_pbt:.2f})")

    # Case 3: Margin math
    expected_margin = expected_pbt / 600000
    assert abs(r["pbt_margin"] - round(expected_margin, 4)) < 0.0001
    print(f"  ✅ C100 margin={r['pbt_margin']:.4f}")

    # Case 4: Mass-retail customer (small numbers, no float drift)
    r2 = eng.calculate_customer_pnl("C200", "2026-04")
    # rev=3500, direct=550, indirect=100000*(3500/698501)=501.07
    # pbt=3500 - 550 - 501.07 = 2448.93
    expected_pbt_C200 = 3500 - 550 - (100000 * 3500 / 698501)
    assert abs(r2["pbt"] - expected_pbt_C200) < 0.5
    print(f"  ✅ C200 PBT={r2['pbt']:.2f}")

    # Case 5: Unknown customer
    assert eng.calculate_customer_pnl("UNKNOWN", "2026-04") == {}
    print(f"  ✅ unknown customer → {{}}")

    # Case 6: Bad inputs
    assert eng.calculate_customer_pnl("", "2026-04") == {}
    assert eng.calculate_customer_pnl("C100", "") == {}
    print(f"  ✅ bad inputs → {{}}")

    # Case 7: Zero revenue → margin is None
    eng_zero = CustomerProfitabilityEngine(
        customer_lookup_fn=lambda c: customers.get(c),
        revenue_fn=lambda c, p: {"interest_income": Decimal("0")},
        direct_costs_fn=lambda c, p: {"interest_expense": Decimal("100")},
        overhead_pool_fn=lambda p: Decimal("0"),
        allocation_inputs_fn=lambda c, p: {},
    )
    r3 = eng_zero.calculate_customer_pnl("C100", "2026-04")
    assert r3["pbt_margin"] is None, f"expected None, got {r3['pbt_margin']}"
    assert r3["pbt"] == -100   # 0 - 100 - 0
    print(f"  ✅ zero-revenue customer: margin=None, PBT={r3['pbt']}")

    # Case 8: Allocation method validation
    try:
        CustomerProfitabilityEngine(allocation_method="bogus")
        assert False, "should have raised"
    except ValueError:
        pass
    print(f"  ✅ invalid allocation method rejected")

    # Case 9: equal_per_customer allocation
    eng_eq = CustomerProfitabilityEngine(
        customer_lookup_fn=lambda c: customers.get(c),
        revenue_fn=lambda c, p: revenue.get((c, p), {}),
        direct_costs_fn=lambda c, p: direct.get((c, p), {}),
        overhead_pool_fn=lambda p: Decimal("100000"),
        allocation_inputs_fn=lambda c, p: {"customer_count": 4},
        allocation_method="equal_per_customer",
    )
    r4 = eng_eq.calculate_customer_pnl("C100", "2026-04")
    # Indirect = 100000 / 4 = 25000
    assert r4["indirect_costs"]["allocated_overhead"] == 25000.0
    print(f"  ✅ equal_per_customer: indirect={r4['indirect_costs']['allocated_overhead']}")

    # Case 10: Decimal precision (no float drift on KES-scale numbers)
    eng_big = CustomerProfitabilityEngine(
        customer_lookup_fn=lambda c: customers.get(c),
        revenue_fn=lambda c, p: {"interest_income": Decimal("1234567890.12")},
        direct_costs_fn=lambda c, p: {"interest_expense": Decimal("987654321.05")},
        overhead_pool_fn=lambda p: Decimal("0"),
        allocation_inputs_fn=lambda c, p: {},
    )
    r5 = eng_big.calculate_customer_pnl("C100", "2026-04")
    expected = 1234567890.12 - 987654321.05
    assert abs(r5["pbt"] - expected) < 0.01
    print(f"  ✅ KES-scale precision: PBT={r5['pbt']:,.2f}")

    # Case 11: meta block
    r = eng.calculate_customer_pnl("C100", "2026-04")
    assert r["meta"]["allocation_method"] == "revenue_weighted"
    assert r["meta"]["customer_id"] == "C100"
    assert r["meta"]["tolerance_excel_pct"] == 0.5
    # v5.46 additions
    assert r["meta"]["ftp_mode"] == "off"
    assert r["meta"]["ftp_rate"] is None
    assert r["meta"]["ftp_missing"] == []
    assert r["meta"]["balance_basis"] == "unknown"
    print(f"  ✅ meta block: method={r['meta']['allocation_method']}, "
          f"tolerance={r['meta']['tolerance_excel_pct']}%")

    # ── v5.46 FTP CASES ──────────────────────────────────────────────

    # Case 12: ftp_mode='on' with deposit-only customer.
    # KES 10M deposit, 1% paid, 8% FTP, 1/12 period →
    # ftp_credit = 10M × (0.08 − 0.01) × 1/12 = 58,333.33
    # interest_expense (already on customer) = 10M × 0.01 × 1/12 = 8,333.33
    # No fees, no loans, no overhead.
    eng_ftp = CustomerProfitabilityEngine(
        customer_lookup_fn=lambda c: customers.get(c),
        revenue_fn=lambda c, p: {},   # no fees, no other income
        direct_costs_fn=lambda c, p: {"interest_expense": Decimal("8333.33")},
        overhead_pool_fn=lambda p: ZERO,
        allocation_inputs_fn=lambda c, p: {},
        ftp_mode="on",
        ftp_inputs_fn=lambda c, p: {
            "ftp_rate":          Decimal("0.08"),
            "deposit_balance":   Decimal("10000000"),
            "deposit_rate_paid": Decimal("0.01"),
            "loan_balance":      Decimal("0"),
            "period_fraction":   Decimal("1") / Decimal("12"),
        },
        balance_basis="average",
    )
    r12 = eng_ftp.calculate_customer_pnl("C100", "2026-04")
    # Revenue should now have ftp_credit_on_deposits ≈ 58,333.33
    assert "ftp_credit_on_deposits" in r12["revenue"]
    assert abs(r12["revenue"]["ftp_credit_on_deposits"] - 58333.33) < 0.5
    # Total_revenue ≈ 58,333.33; direct = 8,333.33; PBT ≈ 50,000
    assert abs(r12["pbt"] - 50000) < 1.0, f"deposit-only PBT: {r12['pbt']}"
    assert r12["meta"]["ftp_mode"] == "on"
    assert r12["meta"]["ftp_rate"] == 0.08
    assert r12["meta"]["balance_basis"] == "average"
    print(f"  ✅ FTP on (deposit-only): PBT={r12['pbt']:,.2f} (was negative in v5.45)")

    # Case 13: ftp_mode='on' with loan-only customer.
    # KES 5M loan at 14%, 8% FTP, 1/12 period →
    # interest_income (on customer) = 5M × 0.14 × 1/12 = 58,333.33
    # ftp_charge_on_loans = 5M × 0.08 × 1/12 = 33,333.33
    # Net lending NII = 58,333.33 − 33,333.33 = 25,000
    eng_loan = CustomerProfitabilityEngine(
        customer_lookup_fn=lambda c: customers.get(c),
        revenue_fn=lambda c, p: {"interest_income": Decimal("58333.33")},
        direct_costs_fn=lambda c, p: {},
        overhead_pool_fn=lambda p: ZERO,
        allocation_inputs_fn=lambda c, p: {},
        ftp_mode="on",
        ftp_inputs_fn=lambda c, p: {
            "ftp_rate":          Decimal("0.08"),
            "deposit_balance":   Decimal("0"),
            "deposit_rate_paid": Decimal("0"),
            "loan_balance":      Decimal("5000000"),
            "period_fraction":   Decimal("1") / Decimal("12"),
        },
    )
    r13 = eng_loan.calculate_customer_pnl("C100", "2026-04")
    assert "ftp_charge_on_loans" in r13["direct_costs"]
    assert abs(r13["direct_costs"]["ftp_charge_on_loans"] - 33333.33) < 0.5
    # PBT ≈ 58,333.33 − 33,333.33 = 25,000
    assert abs(r13["pbt"] - 25000) < 1.0
    print(f"  ✅ FTP on (loan-only): PBT={r13['pbt']:,.2f} (lending margin only)")

    # Case 14: ftp_mode='on' with INCOMPLETE inputs (missing rate)
    # → engine logs in meta.ftp_missing, doesn't fall back silently
    eng_partial = CustomerProfitabilityEngine(
        customer_lookup_fn=lambda c: customers.get(c),
        revenue_fn=lambda c, p: {"interest_income": Decimal("100")},
        direct_costs_fn=lambda c, p: {},
        overhead_pool_fn=lambda p: ZERO,
        allocation_inputs_fn=lambda c, p: {},
        ftp_mode="on",
        ftp_inputs_fn=lambda c, p: {
            "deposit_balance": Decimal("10000000"),
            # ftp_rate MISSING
            # period_fraction MISSING
        },
    )
    r14 = eng_partial.calculate_customer_pnl("C100", "2026-04")
    assert "ftp_credit_on_deposits" not in r14["revenue"]
    assert "ftp_charge_on_loans" not in r14["direct_costs"]
    assert "ftp_rate" in r14["meta"]["ftp_missing"]
    assert "period_fraction" in r14["meta"]["ftp_missing"]
    # PBT computed normally from supplied buckets (100 - 0 - 0 = 100)
    assert r14["pbt"] == 100.0
    print(f"  ✅ FTP on with missing inputs: ftp_missing={r14['meta']['ftp_missing']}, "
          f"PBT={r14['pbt']} (other components still compute)")

    # Case 15: ftp_inputs_fn returns None → ftp_missing logged
    eng_none = CustomerProfitabilityEngine(
        customer_lookup_fn=lambda c: customers.get(c),
        revenue_fn=lambda c, p: {"interest_income": Decimal("100")},
        direct_costs_fn=lambda c, p: {},
        overhead_pool_fn=lambda p: ZERO,
        allocation_inputs_fn=lambda c, p: {},
        ftp_mode="on",
        ftp_inputs_fn=lambda c, p: None,
    )
    r15 = eng_none.calculate_customer_pnl("C100", "2026-04")
    assert "ftp_inputs_fn returned None" in r15["meta"]["ftp_missing"]
    print(f"  ✅ FTP on with None inputs: clearly logged")

    # Case 16: Invalid ftp_mode rejected
    try:
        CustomerProfitabilityEngine(ftp_mode="bogus")
        assert False, "should raise"
    except ValueError:
        pass
    print(f"  ✅ invalid ftp_mode rejected")

    # Case 17: Invalid balance_basis rejected
    try:
        CustomerProfitabilityEngine(balance_basis="quarterly")
        assert False, "should raise"
    except ValueError:
        pass
    print(f"  ✅ invalid balance_basis rejected")

    # Case 18: ftp_mode='on' but customer has neither deposits nor loans
    # → no FTP buckets added, but no error
    eng_neither = CustomerProfitabilityEngine(
        customer_lookup_fn=lambda c: customers.get(c),
        revenue_fn=lambda c, p: {"fee_income": Decimal("500")},
        direct_costs_fn=lambda c, p: {},
        overhead_pool_fn=lambda p: ZERO,
        allocation_inputs_fn=lambda c, p: {},
        ftp_mode="on",
        ftp_inputs_fn=lambda c, p: {
            "ftp_rate":          Decimal("0.08"),
            "deposit_balance":   Decimal("0"),
            "loan_balance":      Decimal("0"),
            "period_fraction":   Decimal("1") / Decimal("12"),
        },
    )
    r18 = eng_neither.calculate_customer_pnl("C100", "2026-04")
    assert "ftp_credit_on_deposits" not in r18["revenue"]
    assert "ftp_charge_on_loans" not in r18["direct_costs"]
    assert r18["meta"]["ftp_mode"] == "on"
    assert r18["meta"]["ftp_rate"] == 0.08    # rate WAS supplied
    assert r18["meta"]["ftp_missing"] == []
    print(f"  ✅ FTP on with zero balances: no FTP buckets, no errors")

    print("\n  ALL TESTS PASSED")
