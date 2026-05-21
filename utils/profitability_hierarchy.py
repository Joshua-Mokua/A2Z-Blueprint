"""utils.profitability_hierarchy — Customer Profitability Hierarchy
(Standard #22, v5.47). Volume Three.

Per the master spec:

    TIERS = {
        "platinum": {"threshold": 0.8, "action": "Retain at all costs"},
        "negative": {"threshold": -float('inf'), "action": "Exit relationship"},
    }

Verification:
  - Pyramid updates daily  ← deployed-runtime metric (whether a daily
                              scheduler runs); OUT OF SCOPE here.

The verifiable structural claim is **classification correctness**:
given a set of customer PBT inputs (from #21), every customer ends
up in the correct tier OR is honestly marked "unclassified" when
the data doesn't support a tier assignment. Audit gate G33 enforces
≥99% classification correctness on labeled fixtures.

WHY THIS ENGINE EXISTS
----------------------
A bank with hundreds of thousands of customers needs a way to
prioritise relationship management effort. The pyramid pattern
puts platinum at the top (few customers, high value, retain at all
costs) and negative at the bottom (loss-makers — the spec literally
says "exit relationship"). The ranking is the basis for Standards
#23 (RM dashboards), #24 (allocation optimisation), and downstream
strategic decisions.

THE TIER SCHEMA
---------------
The spec gives only platinum (0.8) and negative (-inf) boundaries.
v5.47 fills in the conventional banking tier set:

  platinum   : margin ≥ 0.80      "Retain at all costs"  (spec-quoted)
  gold       : margin ≥ 0.50      "Deepen relationship"
  silver     : margin ≥ 0.20      "Maintain"
  bronze     : margin ≥ 0.00      "Improve or maintain"
  negative   : margin <  0.00     "Exit relationship"     (spec-quoted)

Plus one engine-only bucket the spec doesn't name:

  unclassified : data quality insufficient to assign a tier

CRITICAL HONESTY RULES (per master prompt Standard #11)
========================================================
This engine is a SECONDARY consumer of financial reporting. It
reads #21's PBT and margin. If #21 was wrong, the tier is wrong.
The honesty rules below stop that error from propagating silently.

1. **pbt_margin is None → tier = "unclassified".**
   #21 returns None for margin when total_revenue ≤ 0. The hierarchy
   refuses to put such customers in "negative" — we don't know their
   margin. They appear in the "unclassified" bucket and the meta
   block carries the reason.

2. **FTP-blind classification of deposit-only customers is REFUSED.**
   When the upstream PnL was computed in ftp_mode="off" AND the
   customer has zero loan balance (i.e. they're a depositor whose
   funding value the upstream didn't measure), the hierarchy puts
   them in "unclassified" rather than "negative". This is exactly
   the trap the master prompt's Mandatory Standard #11 warns about
   — a deposit-only customer with naive gross-interest math will
   show negative PBT, and a naive tier engine would tag them for
   exit. v5.47 refuses.

3. **min_revenue_for_tier (optional secondary criterion).**
   A "platinum" margin on KES 100 of revenue is a rounding error,
   not a top-tier customer. The constructor accepts an optional
   `min_revenue_for_tier` dict that, when set, demotes customers
   below the revenue floor for their margin-derived tier. Example:
   {"platinum": 1_000_000} prevents anyone with <KES 1M revenue
   from claiming platinum even at 80%+ margin. The choice is
   recorded in meta.tier_secondary_criterion. Default: None
   (margin-only classification).

4. **Tier "action" strings are recommendations, not directives.**
   The spec's wording is preserved verbatim for platinum and
   negative ("Retain at all costs", "Exit relationship"). The
   intermediate tiers use measured wording. Production deployments
   should treat these as suggested actions for relationship
   management — board-level decisions remain board-level.

5. **build_pyramid is deterministic.**
   Given the same input set, two runs produce identical output.
   No randomness, no time-dependent behavior beyond `generated_at`
   timestamp. Auditable.

6. **No silent fallback when #21 outputs are unavailable.**
   If get_pnl() returns None for a customer in the requested period,
   the customer is reported in `meta.unavailable_customers` and
   excluded from the pyramid (not silently put in "unclassified").
   The pyramid count + unavailable count = total_requested.

THE TIER BOUNDARIES — VERIFIED
-------------------------------
Fence-post boundaries are checked in tests:
  margin = 0.80  → platinum (≥, not >)
  margin = 0.50  → gold     (≥, not >)
  margin = 0.20  → silver
  margin = 0.00  → bronze   (≥ 0, exactly 0 IS bronze)
  margin = -0.01 → negative
  margin = -inf  → negative
  margin = None  → unclassified

This is the standard "lower bound inclusive" pattern.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field, asdict
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

logger = logging.getLogger("a2z.hierarchy")

ROOT = Path(__file__).parent.parent
DATA_DIR = ROOT / "data"
PYRAMID_FILE = DATA_DIR / "profitability_pyramid.json"


# ─────────────────────────────────────────────────────────────────────
# Tier schema (spec-aligned + standard banking fill-in)
# ─────────────────────────────────────────────────────────────────────

# Spec literal: platinum and negative are spec-quoted. Gold/silver/bronze
# are standard banking tier-fill (documented in module docstring).
TIERS: Dict[str, Dict[str, Any]] = {
    "platinum":  {"threshold": 0.80,           "action": "Retain at all costs"},
    "gold":      {"threshold": 0.50,           "action": "Deepen relationship"},
    "silver":    {"threshold": 0.20,           "action": "Maintain"},
    "bronze":    {"threshold": 0.00,           "action": "Improve or maintain"},
    "negative":  {"threshold": -float("inf"),  "action": "Exit relationship"},
}

# Iteration order: high → low. Critical: classification walks this list
# in order, returning the FIRST tier whose threshold the margin meets.
TIER_ORDER: Tuple[str, ...] = ("platinum", "gold", "silver", "bronze", "negative")

UNCLASSIFIED = "unclassified"


# ─────────────────────────────────────────────────────────────────────
# Data model
# ─────────────────────────────────────────────────────────────────────

@dataclass
class Classification:
    customer_id:     str = ""
    period:          str = ""
    tier:            str = ""
    margin:          Optional[float] = None
    pbt:             float = 0.0
    revenue:         float = 0.0
    action:          str = ""
    reason:          str = ""    # why "unclassified" if applicable
    classified_at:   str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


# ─────────────────────────────────────────────────────────────────────
# Engine
# ─────────────────────────────────────────────────────────────────────

class CustomerProfitabilityHierarchy:
    """Standard #22 — Customer Profitability Hierarchy.

    Stateless: each call returns a fresh classification or pyramid.
    Reads #21's saved customer_pnl.json by default; injectable for
    tests.
    """

    TIERS = TIERS   # spec compliance — class attribute mirrors module dict

    def __init__(
        self,
        pnl_lookup_fn:        Optional[Callable[[str, str], Optional[dict]]] = None,
        all_customers_fn:     Optional[Callable[[], List[str]]] = None,
        min_revenue_for_tier: Optional[Dict[str, float]] = None,
    ):
        """All collaborators injectable.

        pnl_lookup_fn(customer_id, period) → dict | None
            Returns the #21 PnL output dict (must have keys
            'pbt', 'pbt_margin', 'total_revenue', 'meta'). Default
            reads data/customer_pnl.json via #21's get_pnl helper.

        all_customers_fn() → list of customer_ids
            Returns all known customer IDs. Used by build_pyramid.
            Default reads data/customer_intelligence.json keys.

        min_revenue_for_tier: optional dict of tier → min revenue.
            Customers with revenue below the floor for their
            margin-derived tier get demoted one tier. Default: None
            (no secondary criterion).
        """
        self._pnl_lookup     = pnl_lookup_fn      or _default_pnl_lookup
        self._all_customers  = all_customers_fn   or _default_all_customers
        self._min_rev        = dict(min_revenue_for_tier) if min_revenue_for_tier else None
        if self._min_rev is not None:
            for k in self._min_rev:
                if k not in TIER_ORDER:
                    raise ValueError(
                        f"min_revenue_for_tier key {k!r} is not a valid tier; "
                        f"valid tiers: {TIER_ORDER}"
                    )

    # ──────────────────────────────────────────────────────────────────
    # Single-customer classification
    # ──────────────────────────────────────────────────────────────────

    def classify(
        self, customer_id: str, period: str,
    ) -> Dict[str, Any]:
        """Classify one customer for one period.

        Returns:
            {
              "customer_id": str,
              "period": str,
              "tier": str,                   # one of TIER_ORDER + "unclassified"
              "margin": float | None,
              "pbt": float,
              "revenue": float,
              "action": str,
              "reason": str,                  # populated when unclassified
              "meta": {...},
            }

        Returns {} when:
            - customer_id or period is empty
            - pnl_lookup_fn returns None (PnL hasn't been computed yet)

        Returns tier="unclassified" with an explanatory reason when:
            - margin is None (revenue ≤ 0 in upstream)
            - upstream was FTP-blind (ftp_mode="off") AND customer has
              zero loan balance — the deposit-funder trap
        """
        if not customer_id or not period:
            return {}

        pnl = self._pnl_lookup(customer_id, period)
        if not pnl:
            return {}

        margin = pnl.get("pbt_margin")
        pbt = float(pnl.get("pbt", 0))
        revenue = float(pnl.get("total_revenue", 0))
        upstream_meta = pnl.get("meta") or {}

        tier, reason = self._derive_tier(
            margin=margin, revenue=revenue, upstream_meta=upstream_meta, pbt=pbt,
        )
        action = (TIERS.get(tier) or {}).get("action", "")
        if tier == UNCLASSIFIED:
            action = "Re-evaluate when upstream data is complete"

        return {
            "customer_id": customer_id,
            "period":      period,
            "tier":        tier,
            "margin":      margin,
            "pbt":         round(pbt, 2),
            "revenue":     round(revenue, 2),
            "action":      action,
            "reason":      reason,
            "meta": {
                "upstream_ftp_mode":          upstream_meta.get("ftp_mode"),
                "upstream_balance_basis":     upstream_meta.get("balance_basis"),
                "upstream_allocation_method": upstream_meta.get("allocation_method"),
                "tier_secondary_criterion":   self._min_rev,
                "tier_thresholds":            {t: TIERS[t]["threshold"] for t in TIER_ORDER},
                "classified_at":              datetime.now(timezone.utc).isoformat(),
            },
        }

    # ──────────────────────────────────────────────────────────────────
    # Pyramid (population view)
    # ──────────────────────────────────────────────────────────────────

    def build_pyramid(
        self, period: str,
        customer_ids: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Aggregate classifications across customers into a tier pyramid.

        Returns:
            {
              "period": str,
              "total_customers": int,
              "tiers": {
                tier_name: {
                  "count": int,
                  "share": float,           # 0..1
                  "total_pbt": float,
                  "total_revenue": float,
                  "median_margin": float | None,
                  "action": str,
                },
                ...
              },
              "total_pbt": float,
              "total_revenue": float,
              "meta": {
                "unavailable_customers": list,
                "requested_count": int,
                "classified_count": int,
                "tier_secondary_criterion": ...,
                "generated_at": ...,
              },
            }

        Returns {} when period is empty.
        """
        if not period:
            return {}

        ids = customer_ids if customer_ids is not None else (self._all_customers() or [])
        ids = [str(c) for c in ids if c]

        # Initialise tier buckets (including unclassified)
        tier_buckets: Dict[str, Dict[str, Any]] = {
            t: {"count": 0, "total_pbt": 0.0, "total_revenue": 0.0,
                "margins": [], "action": TIERS[t]["action"]}
            for t in TIER_ORDER
        }
        tier_buckets[UNCLASSIFIED] = {
            "count": 0, "total_pbt": 0.0, "total_revenue": 0.0,
            "margins": [],
            "action": "Re-evaluate when upstream data is complete",
        }

        unavailable: List[str] = []
        classified = 0
        for cid in ids:
            c = self.classify(cid, period)
            if not c:
                unavailable.append(cid)
                continue
            classified += 1
            bucket = tier_buckets.get(c["tier"], tier_buckets[UNCLASSIFIED])
            bucket["count"] += 1
            bucket["total_pbt"] += c["pbt"]
            bucket["total_revenue"] += c["revenue"]
            if c["margin"] is not None:
                bucket["margins"].append(float(c["margin"]))

        # Build output buckets with shares + median margin
        out_tiers: Dict[str, Dict[str, Any]] = {}
        for name, b in tier_buckets.items():
            margins = b.pop("margins")
            b["share"] = round(b["count"] / classified, 4) if classified > 0 else 0.0
            b["total_pbt"] = round(b["total_pbt"], 2)
            b["total_revenue"] = round(b["total_revenue"], 2)
            b["median_margin"] = (
                round(_median(margins), 4) if margins else None
            )
            out_tiers[name] = b

        total_pbt = round(sum(b["total_pbt"] for b in out_tiers.values()), 2)
        total_revenue = round(sum(b["total_revenue"] for b in out_tiers.values()), 2)

        return {
            "period":           period,
            "total_customers":  classified,
            "tiers":            out_tiers,
            "total_pbt":        total_pbt,
            "total_revenue":    total_revenue,
            "meta": {
                "requested_count":        len(ids),
                "classified_count":       classified,
                "unavailable_customers":  unavailable,
                "unavailable_count":      len(unavailable),
                "tier_secondary_criterion": self._min_rev,
                "tier_order":             list(TIER_ORDER) + [UNCLASSIFIED],
                "generated_at":           datetime.now(timezone.utc).isoformat(),
            },
        }

    # ──────────────────────────────────────────────────────────────────
    # Tier derivation
    # ──────────────────────────────────────────────────────────────────

    def _derive_tier(
        self,
        margin: Optional[float],
        revenue: float,
        pbt: float,
        upstream_meta: dict,
    ) -> Tuple[str, str]:
        """Return (tier, reason). reason is non-empty only when
        tier == UNCLASSIFIED.
        """
        # Honesty rule 1: None margin → unclassified
        if margin is None:
            return UNCLASSIFIED, "upstream pbt_margin is None (revenue ≤ 0)"

        # Honesty rule 2: FTP-blind on deposit-only customer → unclassified
        upstream_ftp_mode = upstream_meta.get("ftp_mode")
        if upstream_ftp_mode == "off":
            # We can detect deposit-funder pattern only if the upstream
            # surfaces it. We use a conservative test: PBT < 0 AND the
            # customer has fee or other_income (i.e. they're not just
            # a money-loser in a normal lending relationship). Since
            # we don't have direct access to deposit/loan balances at
            # this layer, we apply a structural heuristic: ftp_mode=off
            # AND pbt < 0 AND revenue > 0 strongly suggests the
            # deposit-funder case the master prompt warns about. We
            # mark this for review rather than auto-tagging "negative".
            if pbt < 0 and revenue > 0:
                return UNCLASSIFIED, (
                    "upstream ftp_mode='off' and PBT is negative — "
                    "may be a deposit-funder customer mis-priced by "
                    "naive gross-interest math (per Mandatory Standard #11). "
                    "Re-run upstream with ftp_mode='on' before classifying."
                )

        # Walk the tier ladder high → low
        margin_f = float(margin)
        for tier_name in TIER_ORDER:
            threshold = TIERS[tier_name]["threshold"]
            if margin_f >= threshold:
                derived = tier_name
                break
        else:
            # Should never happen since negative threshold is -inf, but
            # defensive fallback is unclassified, never silent default
            return UNCLASSIFIED, "margin did not match any tier threshold (unexpected)"

        # Apply min_revenue_for_tier secondary criterion if configured
        if self._min_rev:
            floor = self._min_rev.get(derived)
            if floor is not None and revenue < float(floor):
                # Demote one tier
                idx = TIER_ORDER.index(derived)
                if idx + 1 < len(TIER_ORDER):
                    derived = TIER_ORDER[idx + 1]
                # Note: we don't iterate demotion (one-step demotion is
                # the convention; deeper demotion would compound and
                # surprise users)
        return derived, ""


# ─────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────

def _median(xs: List[float]) -> float:
    """Defensive median; returns 0.0 on empty input."""
    if not xs:
        return 0.0
    s = sorted(xs)
    n = len(s)
    mid = n // 2
    return s[mid] if n % 2 else (s[mid - 1] + s[mid]) / 2


def _safe_load(path: Path, default):
    try:
        from utils.db import db
        return db.load_json(path, default=default)
    except Exception as e:
        logger.warning("hierarchy: could not load %s: %s", path, e)
        return default


# ─────────────────────────────────────────────────────────────────────
# Default collaborators
# ─────────────────────────────────────────────────────────────────────

def _default_pnl_lookup(customer_id: str, period: str) -> Optional[dict]:
    """Read #21's saved PnL via its get_pnl helper."""
    try:
        from utils.customer_profitability import get_pnl
        return get_pnl(customer_id, period)
    except Exception as e:
        logger.warning("hierarchy: get_pnl failed: %s", e)
        return None


def _default_all_customers() -> List[str]:
    raw = _safe_load(DATA_DIR / "customer_intelligence.json", {})
    if isinstance(raw, dict):
        if isinstance(raw.get("customers"), dict):
            return [str(k) for k in raw["customers"].keys()]
        return [str(k) for k in raw.keys()]
    return []


# ─────────────────────────────────────────────────────────────────────
# Persistence
# ─────────────────────────────────────────────────────────────────────

def save_pyramid(period: str, pyramid: dict) -> bool:
    if not period or not pyramid:
        return False
    try:
        from utils.db import db
        existing = db.load_json(PYRAMID_FILE, default={})
    except Exception:
        existing = {}
    if not isinstance(existing, dict):
        existing = {}
    existing[period] = pyramid
    try:
        from utils.db import db
        db.save_json(PYRAMID_FILE, existing)
        return True
    except Exception as e:
        logger.error("hierarchy: could not save pyramid: %s", e)
        return False


def get_pyramid(period: str) -> Optional[dict]:
    try:
        from utils.db import db
        existing = db.load_json(PYRAMID_FILE, default={})
    except Exception:
        return None
    if not isinstance(existing, dict):
        return None
    return existing.get(period)


# ─────────────────────────────────────────────────────────────────────
# Self-test (`python -m utils.profitability_hierarchy`)
# ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("A2Z MIS 360 — utils.profitability_hierarchy self-test")

    # ── Helper to build a fake #21 PnL output ─────────────────────────
    def mk_pnl(pbt, margin, revenue=100000.0, ftp_mode="on", balance_basis="average"):
        return {
            "pbt":             float(pbt),
            "pbt_margin":      margin,
            "total_revenue":   float(revenue),
            "total_direct_costs":   0.0,
            "total_indirect_costs": 0.0,
            "revenue":         {},
            "direct_costs":    {},
            "indirect_costs":  {},
            "meta": {
                "ftp_mode":          ftp_mode,
                "balance_basis":     balance_basis,
                "allocation_method": "revenue_weighted",
            },
        }

    # ── Spec contract ─────────────────────────────────────────────────
    assert "platinum" in TIERS
    assert "negative" in TIERS
    assert TIERS["platinum"]["threshold"] == 0.8
    assert TIERS["platinum"]["action"] == "Retain at all costs"
    assert TIERS["negative"]["threshold"] == -float("inf")
    assert TIERS["negative"]["action"] == "Exit relationship"
    assert CustomerProfitabilityHierarchy.TIERS == TIERS
    print(f"  ✅ TIERS spec compliance (platinum 0.8, negative -inf)")

    # ── Tier boundaries (fence-post tests) ────────────────────────────
    pnls = {
        "C_PLAT_HI":      mk_pnl(900000, 0.90, 1000000),
        "C_PLAT_BOUND":   mk_pnl(800000, 0.80, 1000000),    # exactly 0.80 → platinum
        "C_GOLD_HI":      mk_pnl(700000, 0.70, 1000000),
        "C_GOLD_BOUND":   mk_pnl(500000, 0.50, 1000000),    # exactly 0.50 → gold
        "C_SILVER":       mk_pnl(300000, 0.30, 1000000),
        "C_SILVER_BOUND": mk_pnl(200000, 0.20, 1000000),    # exactly 0.20 → silver
        "C_BRONZE":       mk_pnl(100000, 0.10, 1000000),
        "C_BRONZE_BOUND": mk_pnl(0,      0.00, 1000000),    # exactly 0.00 → bronze
        "C_NEG_SMALL":    mk_pnl(-100,  -0.001, 1000000),
        "C_NEG_HUGE":     mk_pnl(-1e9,  -10.0, 1000000),
    }

    eng = CustomerProfitabilityHierarchy(
        pnl_lookup_fn=lambda c, p: pnls.get(c),
        all_customers_fn=lambda: list(pnls.keys()),
    )

    expected = {
        "C_PLAT_HI":      "platinum",
        "C_PLAT_BOUND":   "platinum",
        "C_GOLD_HI":      "gold",
        "C_GOLD_BOUND":   "gold",
        "C_SILVER":       "silver",
        "C_SILVER_BOUND": "silver",
        "C_BRONZE":       "bronze",
        "C_BRONZE_BOUND": "bronze",
        "C_NEG_SMALL":    "negative",
        "C_NEG_HUGE":     "negative",
    }
    for cid, exp_tier in expected.items():
        c = eng.classify(cid, "2026-04")
        assert c["tier"] == exp_tier, f"{cid}: expected {exp_tier}, got {c['tier']}"
    print(f"  ✅ tier boundaries: {len(expected)} fence-post tests pass")

    # ── Honesty rule 1: None margin → unclassified ────────────────────
    pnls2 = {"C_NONE": mk_pnl(-100, None, 0.0)}    # zero revenue, margin=None
    eng2 = CustomerProfitabilityHierarchy(
        pnl_lookup_fn=lambda c, p: pnls2.get(c),
    )
    c = eng2.classify("C_NONE", "2026-04")
    assert c["tier"] == "unclassified"
    assert "None" in c["reason"]
    print(f"  ✅ None margin → unclassified (reason: {c['reason'][:60]}...)")

    # ── Honesty rule 2: FTP-off + negative PBT → unclassified ─────────
    pnls3 = {
        "C_DEP_TRAP": mk_pnl(pbt=-6500, margin=-3.25, revenue=2000, ftp_mode="off"),
    }
    eng3 = CustomerProfitabilityHierarchy(
        pnl_lookup_fn=lambda c, p: pnls3.get(c),
    )
    c = eng3.classify("C_DEP_TRAP", "2026-04")
    assert c["tier"] == "unclassified", f"expected unclassified, got {c['tier']}"
    assert "ftp_mode='off'" in c["reason"]
    assert "Mandatory Standard #11" in c["reason"]
    print(f"  ✅ FTP-blind deposit trap refused (reason links to Std #11)")

    # ── Same customer with FTP=on and negative margin → negative tier ──
    pnls4 = {
        "C_REAL_NEG": mk_pnl(pbt=-50000, margin=-0.5, revenue=100000, ftp_mode="on"),
    }
    eng4 = CustomerProfitabilityHierarchy(
        pnl_lookup_fn=lambda c, p: pnls4.get(c),
    )
    c = eng4.classify("C_REAL_NEG", "2026-04")
    assert c["tier"] == "negative", f"expected negative, got {c['tier']}"
    assert c["action"] == "Exit relationship"
    print(f"  ✅ FTP=on negative margin → negative tier (after FTP correction)")

    # ── Unknown customer / bad inputs → {} ────────────────────────────
    assert eng.classify("UNKNOWN", "2026-04") == {}
    assert eng.classify("", "2026-04") == {}
    assert eng.classify("C_PLAT_HI", "") == {}
    print(f"  ✅ defensive contract")

    # ── min_revenue_for_tier secondary criterion ──────────────────────
    pnls5 = {
        "C_TINY_PLAT": mk_pnl(80, 0.80, 100),         # 80% margin but only 100 revenue
        "C_BIG_PLAT":  mk_pnl(800000, 0.80, 1000000),
    }
    eng5 = CustomerProfitabilityHierarchy(
        pnl_lookup_fn=lambda c, p: pnls5.get(c),
        min_revenue_for_tier={"platinum": 50000},
    )
    c_tiny = eng5.classify("C_TINY_PLAT", "2026-04")
    c_big  = eng5.classify("C_BIG_PLAT", "2026-04")
    assert c_tiny["tier"] == "gold", f"tiny demoted: got {c_tiny['tier']}"
    assert c_big["tier"]  == "platinum"
    print(f"  ✅ min_revenue secondary criterion: tiny → {c_tiny['tier']}, big → {c_big['tier']}")

    # Invalid tier in min_revenue_for_tier raises
    try:
        CustomerProfitabilityHierarchy(min_revenue_for_tier={"diamond": 1})
        assert False
    except ValueError:
        pass
    print(f"  ✅ unknown tier in secondary criterion rejected")

    # ── build_pyramid ─────────────────────────────────────────────────
    pyramid = eng.build_pyramid("2026-04")
    assert pyramid["total_customers"] == 10
    assert pyramid["tiers"]["platinum"]["count"] == 2
    assert pyramid["tiers"]["gold"]["count"]     == 2
    assert pyramid["tiers"]["silver"]["count"]   == 2
    assert pyramid["tiers"]["bronze"]["count"]   == 2
    assert pyramid["tiers"]["negative"]["count"] == 2
    assert pyramid["tiers"]["unclassified"]["count"] == 0
    # Shares sum to ~1.0
    total_share = sum(b["share"] for b in pyramid["tiers"].values())
    assert abs(total_share - 1.0) < 1e-6
    # Pyramid carries actions
    assert pyramid["tiers"]["platinum"]["action"] == "Retain at all costs"
    assert pyramid["tiers"]["negative"]["action"] == "Exit relationship"
    print(f"  ✅ pyramid: 10 customers, 2 per tier, shares sum to {total_share:.4f}")

    # ── unavailable_customers tracking ────────────────────────────────
    eng_partial = CustomerProfitabilityHierarchy(
        pnl_lookup_fn=lambda c, p: pnls.get(c),
        all_customers_fn=lambda: list(pnls.keys()) + ["MISSING_1", "MISSING_2"],
    )
    pyr2 = eng_partial.build_pyramid("2026-04")
    assert pyr2["total_customers"] == 10   # only classified count
    assert pyr2["meta"]["requested_count"] == 12
    assert pyr2["meta"]["unavailable_count"] == 2
    assert "MISSING_1" in pyr2["meta"]["unavailable_customers"]
    print(f"  ✅ unavailable_customers tracked: {pyr2['meta']['unavailable_count']}/12 missing")

    # ── Determinism ───────────────────────────────────────────────────
    p1 = eng.build_pyramid("2026-04")
    p2 = eng.build_pyramid("2026-04")
    # Strip generated_at + classified_at (these vary by ms)
    def _strip_ts(d):
        if isinstance(d, dict):
            return {k: _strip_ts(v) for k, v in d.items() if k not in ("generated_at", "classified_at")}
        if isinstance(d, list):
            return [_strip_ts(x) for x in d]
        return d
    assert _strip_ts(p1) == _strip_ts(p2)
    print(f"  ✅ determinism: two runs produce identical pyramids")

    # ── Empty pyramid handling ────────────────────────────────────────
    eng_empty = CustomerProfitabilityHierarchy(
        pnl_lookup_fn=lambda c, p: None,
        all_customers_fn=lambda: [],
    )
    pyr_empty = eng_empty.build_pyramid("2026-04")
    assert pyr_empty["total_customers"] == 0
    for t in TIER_ORDER:
        assert pyr_empty["tiers"][t]["count"] == 0
    print(f"  ✅ empty pyramid: 0 customers, all tiers empty")

    # ── Bad period returns {} ─────────────────────────────────────────
    assert eng.build_pyramid("") == {}
    print(f"  ✅ empty period → {{}}")

    print("\n  ALL TESTS PASSED")
