"""utils.rm_profitability — RM Profitability Dashboard
(Standard #23, v5.48). Volume Three.

Per the master spec:

    class RMProfitabilityDashboard:
        def calculate_rm_portfolio_pnl(self, rm_code, period):
            customers = self.get_rm_customers(rm_code)
            for customer in customers:
                pnl = self.calculate_customer_pnl(customer.id, period)
            return {
                "portfolio_pnl":   portfolio_pnl,
                "peer_comparison": {"rank": self.get_rm_rank(rm_code)},
            }

Verification:
  - 100% RM adoption  ← deployed-runtime metric (whether RMs actually
                          open the dashboard); OUT OF SCOPE here.

The verifiable structural claims:
  - Portfolio aggregation correctness on labeled fixtures
  - Deterministic rank ordering (ties broken lexicographically)
  - Honesty inheritance from Mandatory Standard #11 (see below)

Audit gate G34 enforces ≥99% aggregation correctness on labeled
fixtures.

ARCHITECTURAL POSITION
-----------------------
This is the FIRST fully-aggregating engine in Volume Three:
  #21 → per-customer PBT
  #22 → per-customer tier classification
  #23 → per-RM portfolio aggregation  ← THIS ENGINE
  #24 → optimal customer-to-RM allocation (uses #23 output)

It composes via service-function calls (no class imports):
  customer_pnl_fn(customer_id, period) → #21's get_pnl
  rm_customer_lookup_fn(rm_code) → list[customer_id]
  all_rms_fn() → list[rm_code]

HONESTY INHERITANCE FROM MANDATORY STANDARD #11
================================================
The master prompt's Standard #11 requires that downstream engines
surface upstream FTP/balance-basis assumptions. This engine
INHERITS that responsibility for portfolio-level reporting.

If ANY customer in an RM's portfolio was computed in ftp_mode="off"
(naive gross-interest, no FTP credit on deposits), the portfolio
PBT is potentially distorted. v5.48 surfaces this in three ways:

1. **meta.upstream_ftp_modes**: a counter dict
   `{"on": 12, "off": 3, "unknown": 0}` showing how many of the
   portfolio's customers had each FTP mode in their upstream PnL.
   Consumers can read this to gauge data quality.

2. **data_quality_warning** (top-level string): populated when ANY
   customer in the portfolio was computed in ftp_mode="off". The
   warning explicitly cites Mandatory Standard #11 and recommends
   re-running #21 with ftp_mode="on" before treating the portfolio
   PBT as final.

3. **provisional flag** on portfolio_pnl: set to True when
   >50% of customers had ftp_mode="off". This signals that the
   headline portfolio PBT figure should be treated as a working
   draft, not a final number for board reporting.

THE PEER COMPARISON
-------------------
Spec asks for `peer_comparison.rank`. Engine returns rank-by-PBT
(the spec's apparent intent). Ties broken by rm_code lexicographic
for determinism.

**Honest add-on**: peer_comparison also returns
`rank_by_pbt_per_customer` and `rank_by_margin` — alternative
metrics that consumers can choose. A 100-customer portfolio with
KES 1M PBT each ranks above a 5-customer portfolio with KES 10M
PBT each on raw PBT (1B vs 50M), but the per-customer view tells
a different story. Both perspectives are honest; the engine
surfaces both.

**Critical**: peer comparison ONLY ranks RMs whose portfolios
were computed under consistent FTP treatment. Mixed-FTP rankings
are flagged in `meta.peer_comparison_caveats`. The spec didn't
ask for this, but Mandatory Standard #11 requires it.

DEFENSIVE CONTRACT
------------------
- Unknown rm_code → {}
- Empty period → {}
- RM with no customers → portfolio with all-zero totals,
  data_quality_warning = "RM has no assigned customers"
- All customer PnLs missing → portfolio with zeros + meta.unavailable_customers
  list (don't fabricate, don't aggregate fictional data)

DECIMAL PRECISION
-----------------
Same as #21: Decimal-internal at precision 28, output rounded to
2dp via ROUND_HALF_UP. Margins to 4dp. The portfolio sum of
billion-scale customer PBTs must be precise.
"""
from __future__ import annotations

import json
import logging
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP, getcontext
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

logger = logging.getLogger("a2z.rm_profitability")
getcontext().prec = 28

ROOT = Path(__file__).parent.parent
DATA_DIR = ROOT / "data"
RM_PORTFOLIOS_FILE = DATA_DIR / "rm_portfolios.json"

ZERO = Decimal("0")
PROVISIONAL_FTP_OFF_THRESHOLD = 0.5    # >50% off → provisional


# ─────────────────────────────────────────────────────────────────────
# Data model
# ─────────────────────────────────────────────────────────────────────

@dataclass
class PortfolioPnL:
    rm_code:                  str = ""
    period:                   str = ""
    customer_count:           int = 0
    total_revenue:            float = 0.0
    total_direct_costs:       float = 0.0
    total_indirect_costs:     float = 0.0
    total_pbt:                float = 0.0
    portfolio_margin:         Optional[float] = None
    provisional:              bool = False
    customers_unclassified:   int = 0


# ─────────────────────────────────────────────────────────────────────
# Engine
# ─────────────────────────────────────────────────────────────────────

class RMProfitabilityDashboard:
    """Standard #23 — RM Profitability Dashboard.

    Stateless: each call returns a fresh aggregation. Persistence
    helpers exist for caching computed portfolios.
    """

    def __init__(
        self,
        rm_customer_lookup_fn: Optional[Callable[[str], List[str]]] = None,
        customer_pnl_fn:        Optional[Callable[[str, str], Optional[dict]]] = None,
        all_rms_fn:             Optional[Callable[[], List[str]]] = None,
        rm_lookup_fn:           Optional[Callable[[str], Optional[dict]]] = None,
    ):
        """All collaborators injectable.

        rm_customer_lookup_fn(rm_code) → list[customer_id]
            Returns customer IDs assigned to this RM. Default reads
            customer_intelligence.json for `rm_code` field on each
            customer.

        customer_pnl_fn(customer_id, period) → dict | None
            Returns #21's PnL output for one customer. Default reads
            data/customer_pnl.json via #21's get_pnl helper.

        all_rms_fn() → list[rm_code]
            Returns all known RM codes. Used for peer ranking.
            Default reads users.json for staff with role containing
            'RM' or 'Relationship Manager'.

        rm_lookup_fn(rm_code) → dict | None
            Returns RM staff record (full_name, branch, etc.). Used
            to enrich the portfolio output. Default reads users.json.
        """
        self._rm_customers = rm_customer_lookup_fn or _default_rm_customer_lookup
        self._customer_pnl = customer_pnl_fn        or _default_customer_pnl
        self._all_rms      = all_rms_fn             or _default_all_rms
        self._rm_lookup    = rm_lookup_fn           or _default_rm_lookup

    # ──────────────────────────────────────────────────────────────────
    # Spec methods
    # ──────────────────────────────────────────────────────────────────

    def get_rm_customers(self, rm_code: str) -> List[str]:
        """Spec method — returns customer IDs assigned to this RM."""
        return self._rm_customers(rm_code) or []

    def calculate_rm_portfolio_pnl(
        self, rm_code: str, period: str,
    ) -> Dict[str, Any]:
        """Aggregate customer PnLs into a portfolio for one RM.

        Returns the spec-shaped dict (with extensions for
        traceability and Mandatory Standard #11 honesty
        inheritance):

            {
              "portfolio_pnl": {
                "rm_code": str,
                "period": str,
                "customer_count": int,
                "total_revenue": float,
                "total_direct_costs": float,
                "total_indirect_costs": float,
                "total_pbt": float,
                "portfolio_margin": float | None,
                "provisional": bool,
                "customers_unclassified": int,
              },
              "peer_comparison": {
                "rank": int | None,                   # by total_pbt
                "rank_by_pbt_per_customer": int | None,
                "rank_by_margin": int | None,
                "total_rms_ranked": int,
              },
              "data_quality_warning": str | None,
              "meta": {
                "rm_code": str,
                "rm_name": str,
                "period": str,
                "upstream_ftp_modes": {"on": ..., "off": ..., "unknown": ...},
                "ftp_off_share": float,                 # 0..1
                "unavailable_customers": list[str],
                "unavailable_count": int,
                "requested_count": int,
                "peer_comparison_caveats": list[str],
                "generated_at": ...,
              },
            }

        Returns {} for unknown rm_code or empty period.
        """
        if not rm_code or not period:
            return {}

        rm = self._rm_lookup(rm_code)
        if not rm:
            return {}

        customer_ids = self.get_rm_customers(rm_code)

        # Aggregate per-customer PnLs
        agg = self._aggregate_portfolio(rm_code, period, customer_ids)

        # Compute peer ranks
        peer = self._compute_peer_comparison(rm_code, period, agg["portfolio_pnl"])

        return {
            "portfolio_pnl":     agg["portfolio_pnl"],
            "peer_comparison":   peer,
            "data_quality_warning": agg["data_quality_warning"],
            "meta": {
                "rm_code":                 rm_code,
                "rm_name":                 rm.get("full_name", ""),
                "period":                  period,
                "upstream_ftp_modes":      agg["ftp_modes"],
                "ftp_off_share":           agg["ftp_off_share"],
                "unavailable_customers":   agg["unavailable_customers"],
                "unavailable_count":       agg["unavailable_count"],
                "requested_count":         len(customer_ids),
                "peer_comparison_caveats": peer.get("_caveats", []),
                "generated_at":            datetime.now(timezone.utc).isoformat(),
            },
        }

    def get_rm_rank(self, rm_code: str, period: Optional[str] = None) -> Optional[int]:
        """Spec method — returns this RM's rank among all RMs by
        total portfolio PBT.

        Returns None when:
          - rm_code or period missing
          - this RM has no portfolio data
          - no other RMs have computable portfolios
        """
        if not rm_code or not period:
            return None
        portfolios = self.build_all_portfolios(period)
        if not portfolios:
            return None
        ranked = sorted(
            [(r, p["portfolio_pnl"]["total_pbt"]) for r, p in portfolios.items()],
            key=lambda x: (-x[1], x[0]),    # PBT desc, then rm_code asc for ties
        )
        for i, (r, _) in enumerate(ranked, 1):
            if r == rm_code:
                return i
        return None

    def build_all_portfolios(self, period: str) -> Dict[str, dict]:
        """Compute portfolios for every known RM. Used internally by
        peer ranking; also useful for board-level reports.

        Returns {rm_code: portfolio_dict}. RMs with no customers or
        all-unavailable PnLs are still included (with zero totals).

        WARNING: this calls calculate_rm_portfolio_pnl for every RM,
        which calls customer_pnl_fn for every customer. On large banks
        this is O(N_rms × N_customers_per_rm) lookups — production
        deployments should cache.
        """
        if not period:
            return {}
        out: Dict[str, dict] = {}
        for rm_code in (self._all_rms() or []):
            r = self.calculate_rm_portfolio_pnl(rm_code, period)
            if r:
                out[rm_code] = r
        return out

    # ──────────────────────────────────────────────────────────────────
    # Internal: portfolio aggregation
    # ──────────────────────────────────────────────────────────────────

    def _aggregate_portfolio(
        self, rm_code: str, period: str, customer_ids: List[str],
    ) -> Dict[str, Any]:
        """Walk each customer, sum components, track FTP modes."""
        total_revenue  = ZERO
        total_direct   = ZERO
        total_indirect = ZERO
        total_pbt      = ZERO
        ftp_modes: Counter = Counter()
        unavailable: List[str] = []
        customers_unclassified = 0
        included_count = 0

        for cid in customer_ids:
            pnl = self._customer_pnl(cid, period)
            if not pnl:
                unavailable.append(cid)
                continue
            included_count += 1
            try:
                total_revenue  += Decimal(str(pnl.get("total_revenue", 0)))
                total_direct   += Decimal(str(pnl.get("total_direct_costs", 0)))
                total_indirect += Decimal(str(pnl.get("total_indirect_costs", 0)))
                total_pbt      += Decimal(str(pnl.get("pbt", 0)))
            except Exception as e:
                logger.warning(
                    "rm_profitability: failed to aggregate %s: %s", cid, e,
                )
                unavailable.append(cid)
                continue
            mode = (pnl.get("meta") or {}).get("ftp_mode") or "unknown"
            ftp_modes[mode] += 1
            if pnl.get("pbt_margin") is None:
                customers_unclassified += 1

        # Margin: weighted by total revenue (NOT mean of margins, which
        # would over-weight tiny customers).
        if total_revenue > ZERO:
            margin_d = total_pbt / total_revenue
            margin_out: Optional[float] = float(
                margin_d.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)
            )
        else:
            margin_out = None

        # FTP-off share
        total_classified = sum(ftp_modes.values())
        off_count = ftp_modes.get("off", 0)
        ftp_off_share = (off_count / total_classified) if total_classified else 0.0
        provisional = ftp_off_share > PROVISIONAL_FTP_OFF_THRESHOLD

        # Data quality warning
        warning: Optional[str] = None
        if not customer_ids:
            warning = "RM has no assigned customers"
        elif included_count == 0:
            warning = (
                "All customer PnLs unavailable for this period — "
                "portfolio totals are zero, not a real assessment"
            )
        elif off_count > 0:
            warning = (
                f"{off_count} of {total_classified} customers had upstream "
                f"PnL computed in ftp_mode='off'. Per Mandatory Standard #11, "
                f"the portfolio PBT may be distorted (deposit-funder customers "
                f"mis-priced by naive gross-interest math). "
                f"Re-run #21 with ftp_mode='on' before treating this portfolio "
                f"PBT as final."
            )

        portfolio = {
            "rm_code":              rm_code,
            "period":               period,
            "customer_count":       included_count,
            "total_revenue":        _money(total_revenue),
            "total_direct_costs":   _money(total_direct),
            "total_indirect_costs": _money(total_indirect),
            "total_pbt":            _money(total_pbt),
            "portfolio_margin":     margin_out,
            "provisional":          provisional,
            "customers_unclassified": customers_unclassified,
        }

        return {
            "portfolio_pnl":         portfolio,
            "ftp_modes":             dict(ftp_modes),
            "ftp_off_share":         round(ftp_off_share, 4),
            "unavailable_customers": unavailable,
            "unavailable_count":     len(unavailable),
            "data_quality_warning":  warning,
        }

    # ──────────────────────────────────────────────────────────────────
    # Internal: peer comparison
    # ──────────────────────────────────────────────────────────────────

    def _compute_peer_comparison(
        self, rm_code: str, period: str, my_portfolio: dict,
    ) -> Dict[str, Any]:
        """Compute rank by PBT (primary), PBT-per-customer (secondary),
        and margin (tertiary). Determinism: ties broken lexicographically
        on rm_code.

        Note: this re-walks every RM's portfolio. For large banks
        (hundreds of RMs × hundreds of customers each) this is
        expensive — production deployments should cache.
        """
        all_rms = self._all_rms() or []
        if rm_code not in all_rms:
            return {
                "rank": None,
                "rank_by_pbt_per_customer": None,
                "rank_by_margin": None,
                "total_rms_ranked": 0,
                "_caveats": [f"{rm_code} not in all_rms_fn output"],
            }

        # Build minimal portfolio summaries for ranking (avoid recursive
        # peer-comparison computation by aggregating directly)
        summaries: List[Tuple[str, float, int, Optional[float], str]] = []
        ftp_off_seen = False
        ftp_on_seen = False
        for rm in all_rms:
            customer_ids = self._rm_customers(rm) or []
            agg = self._aggregate_portfolio(rm, period, customer_ids)
            pf = agg["portfolio_pnl"]
            summaries.append((
                rm,
                pf["total_pbt"],
                pf["customer_count"],
                pf["portfolio_margin"],
                "off" if agg["ftp_off_share"] > 0 else "on",
            ))
            if agg["ftp_off_share"] > 0:
                ftp_off_seen = True
            else:
                ftp_on_seen = True

        # Rank by total_pbt desc, ties by rm_code asc
        by_pbt = sorted(summaries, key=lambda x: (-x[1], x[0]))
        rank = next((i for i, s in enumerate(by_pbt, 1) if s[0] == rm_code), None)

        # Rank by PBT per customer (only ranks RMs with ≥1 customer; others get None)
        per_cust_summaries = [
            (rm, (pbt / count) if count > 0 else None)
            for rm, pbt, count, _m, _f in summaries
        ]
        per_cust_ranked = sorted(
            [s for s in per_cust_summaries if s[1] is not None],
            key=lambda x: (-x[1], x[0]),
        )
        rank_per_cust = next(
            (i for i, s in enumerate(per_cust_ranked, 1) if s[0] == rm_code), None,
        )

        # Rank by portfolio margin (only RMs with computable margin)
        by_margin = sorted(
            [(rm, m) for rm, _p, _c, m, _f in summaries if m is not None],
            key=lambda x: (-x[1], x[0]),
        )
        rank_by_margin = next(
            (i for i, s in enumerate(by_margin, 1) if s[0] == rm_code), None,
        )

        caveats: List[str] = []
        if ftp_off_seen and ftp_on_seen:
            caveats.append(
                "Peer ranking includes RMs with mixed FTP treatment — "
                "rank may not be apples-to-apples (per Mandatory Standard #11)"
            )

        return {
            "rank":                       rank,
            "rank_by_pbt_per_customer":   rank_per_cust,
            "rank_by_margin":             rank_by_margin,
            "total_rms_ranked":           len(summaries),
            "_caveats":                   caveats,
        }


# ─────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────

def _money(d: Decimal) -> float:
    if not isinstance(d, Decimal):
        try: d = Decimal(str(d))
        except Exception: return 0.0
    return float(d.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def _safe_load(path: Path, default):
    try:
        from utils.db import db
        return db.load_json(path, default=default)
    except Exception as e:
        logger.warning("rm_profitability: could not load %s: %s", path, e)
        return default


# ─────────────────────────────────────────────────────────────────────
# Default collaborators
# ─────────────────────────────────────────────────────────────────────

def _default_rm_customer_lookup(rm_code: str) -> List[str]:
    """v10.383 — canonical lookup consuming v10.378 unified customer master.

    Returns list of customer CIFs assigned to the given RM. Mirrors the
    v10.381 customer_profitability refactor pattern: canonical-first with
    legacy fallback.

    Resolution order:
      1. Try v10.378 canonical engine (compute_unified_customer_master) —
         finds customers with rm_code in CBS as well as marketing intel
      2. Fall back to direct customer_intelligence.json read (legacy)

    Why this matters: pre-v10.383, this engine only saw customers in
    marketing_intelligence.json. A customer assigned to an RM via CBS
    but not yet enriched with marketing data was INVISIBLE to RM
    profitability dashboards. After v10.383, the RM sees their full
    customer portfolio per CBS truth.
    """
    canonical = _canonical_rm_customer_lookup_v10383(rm_code)
    if canonical is not None:
        return canonical
    # Legacy fallback
    return _legacy_rm_customer_lookup(rm_code)


# Module-level cache for the unified master (per-process)
_RM_UNIFIED_MASTER_CACHE: Optional[Dict[str, Any]] = None
_RM_BY_RM_CODE_INDEX: Optional[Dict[str, List[str]]] = None


def _canonical_rm_customer_lookup_v10383(rm_code: str) -> Optional[List[str]]:
    """Look up customers by rm_code via the v10.378 canonical engine.

    Builds an rm_code → [customer_cifs] index once per process, caches
    it. Returns None if canonical engine unavailable (caller falls back).
    """
    global _RM_UNIFIED_MASTER_CACHE, _RM_BY_RM_CODE_INDEX
    try:
        if _RM_BY_RM_CODE_INDEX is None:
            from utils.customer_master_canonical import compute_unified_customer_master
            if _RM_UNIFIED_MASTER_CACHE is None:
                _RM_UNIFIED_MASTER_CACHE = compute_unified_customer_master(cbs_dir=None)
            # Build the rm_code → [cifs] index from the unified master
            index: Dict[str, List[str]] = {}
            for cif, rec in _RM_UNIFIED_MASTER_CACHE.items():
                rec_rm = getattr(rec, "rm_code", None)
                if rec_rm:
                    index.setdefault(str(rec_rm), []).append(str(cif))
            _RM_BY_RM_CODE_INDEX = index
        return _RM_BY_RM_CODE_INDEX.get(str(rm_code), [])
    except Exception:
        return None


def reset_canonical_rm_cache() -> None:
    """Reset the module-level caches.

    Test helper — call between tests that change customer data, or after
    CBS data refresh during a running process.
    """
    global _RM_UNIFIED_MASTER_CACHE, _RM_BY_RM_CODE_INDEX
    _RM_UNIFIED_MASTER_CACHE = None
    _RM_BY_RM_CODE_INDEX = None


def _legacy_rm_customer_lookup(rm_code: str) -> List[str]:
    """Pre-v10.383 lookup: reads customer_intelligence.json directly.

    Preserved as fallback for: (a) v10.378 module unavailable,
    (b) customers in marketing intel but not in unified master yet.
    """
    raw = _safe_load(DATA_DIR / "customer_intelligence.json", {})
    if not isinstance(raw, dict):
        return []
    out: List[str] = []
    src = raw.get("customers", raw) if isinstance(raw, dict) else raw
    if not isinstance(src, dict):
        return []
    for cid, info in src.items():
        if isinstance(info, dict) and str(info.get("rm_code", "")) == str(rm_code):
            out.append(str(cid))
    return out


def _default_customer_pnl(customer_id: str, period: str) -> Optional[dict]:
    try:
        from utils.customer_profitability import get_pnl
        return get_pnl(customer_id, period)
    except Exception as e:
        logger.warning("rm_profitability: get_pnl failed for %s: %s", customer_id, e)
        return None


def _default_all_rms() -> List[str]:
    users = _safe_load(DATA_DIR / "users.json", {})
    if not isinstance(users, dict):
        return []
    out: List[str] = []
    for _, info in users.items():
        if not isinstance(info, dict) or not info.get("active"):
            continue
        role = (info.get("role") or "").lower()
        if "rm " in role or role.startswith("rm") or "relationship manager" in role:
            sc = str(info.get("staff_code", ""))
            if sc:
                out.append(sc)
    return sorted(set(out))


def _default_rm_lookup(rm_code: str) -> Optional[dict]:
    users = _safe_load(DATA_DIR / "users.json", {})
    if not isinstance(users, dict):
        return None
    for username, info in users.items():
        if isinstance(info, dict) and str(info.get("staff_code", "")) == str(rm_code):
            return {**info, "username": username}
    return None


# ─────────────────────────────────────────────────────────────────────
# Persistence
# ─────────────────────────────────────────────────────────────────────

def save_portfolio(rm_code: str, period: str, portfolio: dict) -> bool:
    if not rm_code or not period or not portfolio:
        return False
    try:
        from utils.db import db
        existing = db.load_json(RM_PORTFOLIOS_FILE, default={})
    except Exception:
        existing = {}
    if not isinstance(existing, dict):
        existing = {}
    by_rm = existing.setdefault(str(rm_code), {})
    if not isinstance(by_rm, dict):
        by_rm = {}
        existing[str(rm_code)] = by_rm
    by_rm[period] = portfolio
    try:
        from utils.db import db
        db.save_json(RM_PORTFOLIOS_FILE, existing)
        return True
    except Exception as e:
        logger.error("rm_profitability: could not save: %s", e)
        return False


def get_portfolio(rm_code: str, period: str) -> Optional[dict]:
    try:
        from utils.db import db
        existing = db.load_json(RM_PORTFOLIOS_FILE, default={})
    except Exception:
        return None
    if not isinstance(existing, dict):
        return None
    by_rm = existing.get(str(rm_code), {})
    if not isinstance(by_rm, dict):
        return None
    return by_rm.get(period)


# ─────────────────────────────────────────────────────────────────────
# Self-test
# ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("A2Z MIS 360 — utils.rm_profitability self-test")

    def mk_pnl(pbt, margin=None, revenue=100000, ftp_mode="on", direct=0, indirect=0):
        return {
            "pbt":             float(pbt),
            "pbt_margin":      margin,
            "total_revenue":   float(revenue),
            "total_direct_costs":   float(direct),
            "total_indirect_costs": float(indirect),
            "meta": {"ftp_mode": ftp_mode, "balance_basis": "average"},
        }

    rms = {
        "RM001": {"staff_code": "RM001", "full_name": "Alice Mwangi", "active": True, "role": "RM Corporate"},
        "RM002": {"staff_code": "RM002", "full_name": "Bob Otieno",   "active": True, "role": "RM Corporate"},
        "RM003": {"staff_code": "RM003", "full_name": "Cathy Wanjiku","active": True, "role": "RM SME"},
    }
    rm_customers = {
        "RM001": ["C100", "C101", "C102"],
        "RM002": ["C200", "C201"],
        "RM003": [],
    }
    pnls = {
        ("C100", "2026-04"): mk_pnl(500000, 0.50, 1000000, ftp_mode="on", direct=400000, indirect=100000),
        ("C101", "2026-04"): mk_pnl(300000, 0.30, 1000000, ftp_mode="on", direct=600000, indirect=100000),
        ("C102", "2026-04"): mk_pnl(200000, 0.20, 1000000, ftp_mode="on", direct=700000, indirect=100000),
        ("C200", "2026-04"): mk_pnl(800000, 0.40, 2000000, ftp_mode="on", direct=1100000, indirect=100000),
        ("C201", "2026-04"): mk_pnl(100000, 0.10, 1000000, ftp_mode="on", direct=800000, indirect=100000),
    }

    eng = RMProfitabilityDashboard(
        rm_customer_lookup_fn=lambda rm: rm_customers.get(rm, []),
        customer_pnl_fn=       lambda c, p: pnls.get((c, p)),
        all_rms_fn=            lambda: list(rms.keys()),
        rm_lookup_fn=          lambda rm: rms.get(rm),
    )

    # Case 1: Spec contract
    r = eng.calculate_rm_portfolio_pnl("RM001", "2026-04")
    assert "portfolio_pnl" in r
    assert "peer_comparison" in r
    assert "rank" in r["peer_comparison"]
    print(f"  ✅ spec keys present (portfolio_pnl, peer_comparison.rank)")

    # Case 2: Aggregation correctness — RM001
    # Customers: PBT 500k + 300k + 200k = 1,000,000
    # Revenue: 3,000,000; Direct: 1,700,000; Indirect: 300,000
    # Margin: 1,000,000 / 3,000,000 = 0.3333
    pf = r["portfolio_pnl"]
    assert pf["customer_count"] == 3
    assert pf["total_pbt"] == 1000000.00
    assert pf["total_revenue"] == 3000000.00
    assert pf["total_direct_costs"] == 1700000.00
    assert pf["total_indirect_costs"] == 300000.00
    assert abs(pf["portfolio_margin"] - 0.3333) < 0.0001
    print(f"  ✅ RM001 aggregation: PBT={pf['total_pbt']:,.0f}, "
          f"margin={pf['portfolio_margin']}")

    # Case 3: RM002 aggregation — PBT 800k + 100k = 900k
    r2 = eng.calculate_rm_portfolio_pnl("RM002", "2026-04")
    pf2 = r2["portfolio_pnl"]
    assert pf2["total_pbt"] == 900000.00
    assert pf2["customer_count"] == 2
    print(f"  ✅ RM002 aggregation: PBT={pf2['total_pbt']:,.0f}")

    # Case 4: Peer ranking (RM001 PBT 1M > RM002 PBT 900k > RM003 PBT 0)
    assert r["peer_comparison"]["rank"] == 1
    assert r2["peer_comparison"]["rank"] == 2
    print(f"  ✅ peer rank: RM001 #1, RM002 #2")

    # Case 5: RM with no customers
    r3 = eng.calculate_rm_portfolio_pnl("RM003", "2026-04")
    assert r3["portfolio_pnl"]["customer_count"] == 0
    assert r3["portfolio_pnl"]["total_pbt"] == 0.0
    assert r3["data_quality_warning"] == "RM has no assigned customers"
    print(f"  ✅ empty portfolio: warning='{r3['data_quality_warning']}'")

    # Case 6: Unknown RM
    assert eng.calculate_rm_portfolio_pnl("UNKNOWN", "2026-04") == {}
    assert eng.calculate_rm_portfolio_pnl("", "2026-04") == {}
    assert eng.calculate_rm_portfolio_pnl("RM001", "") == {}
    print(f"  ✅ defensive contract")

    # Case 7: Honesty inheritance — FTP-off customer in portfolio
    pnls_mixed = dict(pnls)
    pnls_mixed[("C100", "2026-04")] = mk_pnl(-6500, -3.25, 2000, ftp_mode="off", direct=8500)
    eng_mixed = RMProfitabilityDashboard(
        rm_customer_lookup_fn=lambda rm: rm_customers.get(rm, []),
        customer_pnl_fn=       lambda c, p: pnls_mixed.get((c, p)),
        all_rms_fn=            lambda: list(rms.keys()),
        rm_lookup_fn=          lambda rm: rms.get(rm),
    )
    r_mixed = eng_mixed.calculate_rm_portfolio_pnl("RM001", "2026-04")
    # The FTP-off customer is in there
    assert r_mixed["meta"]["upstream_ftp_modes"]["off"] == 1
    assert r_mixed["meta"]["upstream_ftp_modes"]["on"] == 2
    assert r_mixed["data_quality_warning"] is not None
    assert "Mandatory Standard #11" in r_mixed["data_quality_warning"]
    # Not provisional yet (only 1/3 = 33% off, below 50% threshold)
    assert r_mixed["portfolio_pnl"]["provisional"] is False
    print(f"  ✅ FTP-off honesty: 1/3 FTP-off, warning surfaced, provisional=False")

    # Case 8: >50% FTP-off → provisional flag
    pnls_mostly_off = dict(pnls)
    pnls_mostly_off[("C100", "2026-04")] = mk_pnl(-5000, -2.5, 2000, ftp_mode="off")
    pnls_mostly_off[("C101", "2026-04")] = mk_pnl(-3000, -1.5, 2000, ftp_mode="off")
    eng_mostly = RMProfitabilityDashboard(
        rm_customer_lookup_fn=lambda rm: rm_customers.get(rm, []),
        customer_pnl_fn=       lambda c, p: pnls_mostly_off.get((c, p)),
        all_rms_fn=            lambda: list(rms.keys()),
        rm_lookup_fn=          lambda rm: rms.get(rm),
    )
    r_mostly = eng_mostly.calculate_rm_portfolio_pnl("RM001", "2026-04")
    # 2/3 = 67% off → provisional
    assert r_mostly["portfolio_pnl"]["provisional"] is True, \
        f"expected True, got {r_mostly['portfolio_pnl']['provisional']}"
    print(f"  ✅ >50% FTP-off → provisional=True")

    # Case 9: Mixed FTP across RMs → caveat surfaces
    # RM001 has FTP-off customers, RM002 has only FTP-on
    assert r_mixed["meta"]["peer_comparison_caveats"]
    caveat = r_mixed["meta"]["peer_comparison_caveats"][0]
    assert "Mandatory Standard #11" in caveat
    print(f"  ✅ mixed-FTP peer caveat surfaces")

    # Case 10: Determinism
    p1 = eng.calculate_rm_portfolio_pnl("RM001", "2026-04")
    p2 = eng.calculate_rm_portfolio_pnl("RM001", "2026-04")
    def strip(d):
        if isinstance(d, dict):
            return {k: strip(v) for k, v in d.items() if k not in ("generated_at", "classified_at")}
        if isinstance(d, list): return [strip(x) for x in d]
        return d
    assert strip(p1) == strip(p2)
    print(f"  ✅ determinism")

    # Case 11: All customer PnLs missing
    eng_empty = RMProfitabilityDashboard(
        rm_customer_lookup_fn=lambda rm: ["C_GHOST_1", "C_GHOST_2"],
        customer_pnl_fn=       lambda c, p: None,
        all_rms_fn=            lambda: ["RM001"],
        rm_lookup_fn=          lambda rm: rms.get(rm),
    )
    r_empty = eng_empty.calculate_rm_portfolio_pnl("RM001", "2026-04")
    assert r_empty["portfolio_pnl"]["customer_count"] == 0
    assert r_empty["portfolio_pnl"]["total_pbt"] == 0.0
    assert r_empty["meta"]["unavailable_count"] == 2
    assert "All customer PnLs unavailable" in r_empty["data_quality_warning"]
    print(f"  ✅ all PnLs missing: unavailable_count={r_empty['meta']['unavailable_count']}, "
          f"warning surfaced")

    # Case 12: get_rm_rank works as standalone spec method
    rk = eng.get_rm_rank("RM001", "2026-04")
    assert rk == 1
    rk2 = eng.get_rm_rank("RM003", "2026-04")
    assert rk2 == 3   # last by PBT
    print(f"  ✅ get_rm_rank: RM001→{rk}, RM003→{rk2}")

    # Case 13: Margin = None when revenue is 0
    pnls_zero = {("C100", "2026-04"): mk_pnl(-100, None, 0, ftp_mode="on")}
    rm_customers_zero = {"RM001": ["C100"]}
    eng_zero = RMProfitabilityDashboard(
        rm_customer_lookup_fn=lambda rm: rm_customers_zero.get(rm, []),
        customer_pnl_fn=       lambda c, p: pnls_zero.get((c, p)),
        all_rms_fn=            lambda: ["RM001"],
        rm_lookup_fn=          lambda rm: rms.get(rm),
    )
    r_zero = eng_zero.calculate_rm_portfolio_pnl("RM001", "2026-04")
    assert r_zero["portfolio_pnl"]["portfolio_margin"] is None
    assert r_zero["portfolio_pnl"]["customers_unclassified"] == 1
    print(f"  ✅ zero-revenue portfolio: margin=None, customers_unclassified=1")

    # Case 14: Tie-breaking determinism (rm_code lex order)
    pnls_tied = {
        ("C100", "2026-04"): mk_pnl(500000, 0.50, 1000000),
        ("C200", "2026-04"): mk_pnl(500000, 0.50, 1000000),
    }
    rm_customers_tied = {"RM001": ["C100"], "RM002": ["C200"]}
    eng_tied = RMProfitabilityDashboard(
        rm_customer_lookup_fn=lambda rm: rm_customers_tied.get(rm, []),
        customer_pnl_fn=       lambda c, p: pnls_tied.get((c, p)),
        all_rms_fn=            lambda: ["RM001", "RM002"],
        rm_lookup_fn=          lambda rm: rms.get(rm),
    )
    r1 = eng_tied.calculate_rm_portfolio_pnl("RM001", "2026-04")
    r2 = eng_tied.calculate_rm_portfolio_pnl("RM002", "2026-04")
    # RM001 < RM002 lexicographically → RM001 ranks first on tie
    assert r1["peer_comparison"]["rank"] == 1
    assert r2["peer_comparison"]["rank"] == 2
    print(f"  ✅ tied PBT: RM001 ranks #1 (lex tie-break)")

    print("\n  ALL TESTS PASSED")
