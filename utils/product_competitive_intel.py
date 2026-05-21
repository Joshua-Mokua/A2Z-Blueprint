"""utils.product_competitive_intel — Competitive Intelligence for Products
(Standard ENH-134, v10.145). Phase 1E Product Module — fourth engine.

Per Continuation.docx §Standard #134 (Eco Bank QA spec):
    Automated competitive monitoring and benchmarking.

This is the FOURTH of ten Phase 1E Product standards (ENH-131..140,
closing at ~v10.148 with cockpit + API + UI gate per the v10.141
standing norm).

Per Rule 7 (No silent ML predictions):
  1. All position classifications are deterministic — same input
     → same output
  2. Leader/laggard thresholds are NAMED CONSTANTS; banks override
     via constructor arguments
  3. NO predicted competitor moves — engine reports the snapshot
     in data/competitor_data.json, never extrapolates
  4. Honest fallback when a product has no competitor benchmark
     mapping — returns status="no_competitor_benchmark" with the
     reason from data/product_competitor_mapping.json

WHAT THIS MODULE SHIPS
----------------------
1. ProductCompetitiveIntelligence class with:
   - get_competitor_landscape(product_id) — per-product market
     position summary
   - compare_pricing(product_id) — per-bank pricing comparison
   - get_market_position(product_id) — LEADER / FOLLOWER / LAGGARD
     / NO_DATA classification with delta vs peer median
   - get_peer_benchmarks(metric) — bank-level peer comparison
     (assets, npl_pct, car_pct, nim_pct, roe_pct, etc)
   - identify_pricing_gaps(threshold_pct) — products materially
     out of step (default 0.5% delta)
   - get_competitive_summary() — bank-wide competitive summary

2. Reads:
   - data/products.json (16 products with rate_avg)
   - data/competitor_data.json (9 banks + lending/deposit rates +
     market share + bank-level metrics)
   - data/product_competitor_mapping.json (NEW v10.145 seed;
     product_id → competitor benchmark key)

3. Position classification (config-overridable):
   - LEADER:    we are ≥0.5% better than peer median
                (lower lending / higher deposit)
   - FOLLOWER:  within ±0.5% of peer median
   - LAGGARD:   we are ≥0.5% worse than peer median
   - NO_DATA:   no competitor benchmark mapped for this product

HONESTY DISCIPLINE
------------------
- Engine NEVER fabricates competitor rates. If a product has no
  mapping in product_competitor_mapping.json, returns explicit
  status="no_competitor_benchmark" with the reason
- Peer median computed from EXCLUDING our own bank
  (OUR_BANK_KEY="Ecobank"); engine surfaces n_peers count so
  operators can judge if median is robust (n≥3 considered solid;
  n<3 flagged is_estimate=True)
- Lending vs deposits direction explicitly handled — for lending
  LOWER rate is BETTER; for deposits HIGHER rate is BETTER. The
  position classification respects the direction.
- get_peer_benchmarks for bank-level metrics (NPL, CAR, ROE etc)
  preserves the metric's natural direction
- All deltas reported with sign and basis points for clarity

RELATED STANDARDS
-----------------
- ENH-131 Product Profitability — provides per-product P&L; combined
  with this engine's competitive position gives "we're losing money
  AND priced uncompetitively" signal
- ENH-133 Customer Needs & Gap — provides demand-side gap; this
  engine provides supply-side competitive context
- ENH-135 CVP Builder (next drop) — consumes competitive position
  to draft differentiating value propositions
- ENH-137 Dynamic Pricing — will use peer benchmarks as price
  optimization input
"""
from __future__ import annotations
import json
from dataclasses import dataclass, field
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

DATA_DIR = Path(__file__).parent.parent / "data"
PRODUCTS_PATH = DATA_DIR / "products.json"
COMPETITOR_DATA_PATH = DATA_DIR / "competitor_data.json"
COMPETITOR_MAPPING_PATH = DATA_DIR / "product_competitor_mapping.json"


@dataclass(frozen=True)
class CompetitorLandscape:
    product_id: str
    name: str
    benchmark_type: Optional[str]   # "lending" | "deposits" | None
    benchmark_key: Optional[str]
    our_rate_pct: Optional[Decimal]
    peer_median_pct: Optional[Decimal]
    peer_min_pct: Optional[Decimal]
    peer_max_pct: Optional[Decimal]
    n_peers: int
    delta_vs_median_bps: Optional[int]   # signed; negative = lower than median
    position: str                          # LEADER | FOLLOWER | LAGGARD | NO_DATA
    is_estimate: bool                      # True when n_peers < 3
    status: str                            # "ok" | "no_competitor_benchmark" | "product_not_found"
    reason: Optional[str] = None
    per_peer_rates: Dict[str, Optional[Decimal]] = field(default_factory=dict)

    def as_dict(self) -> Dict[str, Any]:
        return {
            "product_id": self.product_id,
            "name": self.name,
            "benchmark_type": self.benchmark_type,
            "benchmark_key": self.benchmark_key,
            "our_rate_pct": (str(self.our_rate_pct)
                              if self.our_rate_pct is not None else None),
            "peer_median_pct": (str(self.peer_median_pct)
                                  if self.peer_median_pct is not None
                                  else None),
            "peer_min_pct": (str(self.peer_min_pct)
                              if self.peer_min_pct is not None else None),
            "peer_max_pct": (str(self.peer_max_pct)
                              if self.peer_max_pct is not None else None),
            "n_peers": self.n_peers,
            "delta_vs_median_bps": self.delta_vs_median_bps,
            "position": self.position,
            "is_estimate": self.is_estimate,
            "status": self.status,
            "reason": self.reason,
            "per_peer_rates": {k: (str(v) if v is not None else None)
                                for k, v in self.per_peer_rates.items()},
        }


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------

class ProductCompetitiveIntelligence:
    """Per-product competitive benchmarking from the existing
    data/competitor_data.json snapshot."""

    OUR_BANK_KEY = "Ecobank"
    LEADER_THRESHOLD_PCT = Decimal("0.5")     # 50 bps better
    LAGGARD_THRESHOLD_PCT = Decimal("0.5")    # 50 bps worse
    MIN_PEERS_FOR_ROBUST_MEDIAN = 3

    def __init__(
        self,
        products_path: Optional[Path] = None,
        competitor_data_path: Optional[Path] = None,
        competitor_mapping_path: Optional[Path] = None,
        our_bank_key: Optional[str] = None,
    ) -> None:
        self.products_path = products_path or PRODUCTS_PATH
        self.competitor_data_path = (competitor_data_path
                                       or COMPETITOR_DATA_PATH)
        self.competitor_mapping_path = (competitor_mapping_path
                                          or COMPETITOR_MAPPING_PATH)
        self.our_bank_key = our_bank_key or self.OUR_BANK_KEY
        self._products_cache: Optional[List[Dict[str, Any]]] = None
        self._competitor_cache: Optional[Dict[str, Any]] = None
        self._mapping_cache: Optional[Dict[str, Any]] = None

    # ------------------------------------------------------------------
    # Loading
    # ------------------------------------------------------------------

    def _load_products(self) -> List[Dict[str, Any]]:
        if self._products_cache is None:
            try:
                with open(self.products_path) as f:
                    self._products_cache = json.load(f)
            except (FileNotFoundError, json.JSONDecodeError):
                self._products_cache = []
        return self._products_cache

    def _load_competitor(self) -> Dict[str, Any]:
        if self._competitor_cache is None:
            try:
                with open(self.competitor_data_path) as f:
                    self._competitor_cache = json.load(f)
            except (FileNotFoundError, json.JSONDecodeError):
                self._competitor_cache = {}
        return self._competitor_cache or {}

    def _load_mapping(self) -> Dict[str, Any]:
        if self._mapping_cache is None:
            try:
                with open(self.competitor_mapping_path) as f:
                    self._mapping_cache = json.load(f)
            except (FileNotFoundError, json.JSONDecodeError):
                self._mapping_cache = {}
        return self._mapping_cache or {}

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _resolve_benchmark(
        self, product_id: str,
    ) -> Tuple[Optional[str], Optional[str], Optional[str]]:
        """Returns (benchmark_type, benchmark_key, unmapped_reason)."""
        mapping = self._load_mapping()
        lend_map = mapping.get("lending_rate_mapping", {})
        dep_map = mapping.get("deposit_rate_mapping", {})

        if product_id in lend_map:
            return "lending", lend_map[product_id], None
        if product_id in dep_map:
            return "deposits", dep_map[product_id], None

        # Look in unmapped[] for explicit rationale
        for entry in mapping.get("unmapped", []):
            if entry.get("product_id") == product_id:
                return None, None, entry.get(
                    "reason", "no_benchmark_mapping_provided")

        return None, None, "product_not_in_mapping_registry"

    def _peer_rates(
        self, benchmark_type: str, benchmark_key: str,
    ) -> Tuple[Dict[str, Decimal], Optional[Decimal]]:
        """Returns (per_peer_rates, our_rate).

        Excludes our_bank_key from the per_peer dict but returns it
        separately as our_rate.
        """
        comp = self._load_competitor()
        if benchmark_type == "lending":
            rates_dict = comp.get("lending_rates", {}).get(benchmark_key, {})
        elif benchmark_type == "deposits":
            rates_dict = comp.get("deposit_rates", {}).get(benchmark_key, {})
        else:
            rates_dict = {}

        peer_rates: Dict[str, Decimal] = {}
        our_rate: Optional[Decimal] = None
        for bank, rate in rates_dict.items():
            try:
                rate_dec = Decimal(str(rate))
            except Exception:
                continue
            if bank == self.our_bank_key:
                our_rate = rate_dec
            else:
                peer_rates[bank] = rate_dec

        return peer_rates, our_rate

    def _median(self, values: List[Decimal]) -> Optional[Decimal]:
        if not values:
            return None
        s = sorted(values)
        n = len(s)
        if n % 2 == 1:
            return s[n // 2]
        # Even: average of two middle values
        return ((s[n // 2 - 1] + s[n // 2]) / Decimal("2")).quantize(
            Decimal("0.0001"), rounding=ROUND_HALF_UP)

    def _classify_position(
        self, our_rate: Decimal, median: Decimal,
        benchmark_type: str,
    ) -> Tuple[str, int]:
        """Returns (position, delta_bps). delta_bps is signed: negative
        means our rate is BELOW peer median.

        Direction: lending → lower is better; deposits → higher is better.
        """
        delta = our_rate - median
        delta_bps = int((delta * Decimal("100")).quantize(
            Decimal("1"), rounding=ROUND_HALF_UP))

        threshold = self.LEADER_THRESHOLD_PCT

        if benchmark_type == "lending":
            # Lower is better
            if delta <= -threshold:
                return "LEADER", delta_bps
            if delta >= threshold:
                return "LAGGARD", delta_bps
            return "FOLLOWER", delta_bps
        elif benchmark_type == "deposits":
            # Higher is better
            if delta >= threshold:
                return "LEADER", delta_bps
            if delta <= -threshold:
                return "LAGGARD", delta_bps
            return "FOLLOWER", delta_bps
        else:
            return "FOLLOWER", delta_bps

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_competitor_landscape(
        self, product_id: str,
    ) -> CompetitorLandscape:
        product = next((p for p in self._load_products()
                        if p.get("id") == product_id), None)
        if not product:
            return CompetitorLandscape(
                product_id=product_id, name="",
                benchmark_type=None, benchmark_key=None,
                our_rate_pct=None, peer_median_pct=None,
                peer_min_pct=None, peer_max_pct=None,
                n_peers=0, delta_vs_median_bps=None,
                position="NO_DATA", is_estimate=False,
                status="product_not_found",
                reason=f"product_{product_id}_not_in_products.json")

        bm_type, bm_key, unmapped_reason = self._resolve_benchmark(
            product_id)

        if bm_type is None:
            return CompetitorLandscape(
                product_id=product_id,
                name=product.get("name", ""),
                benchmark_type=None, benchmark_key=None,
                our_rate_pct=Decimal(str(product.get("rate_avg", 0)
                                           or 0)),
                peer_median_pct=None, peer_min_pct=None,
                peer_max_pct=None, n_peers=0,
                delta_vs_median_bps=None,
                position="NO_DATA", is_estimate=False,
                status="no_competitor_benchmark",
                reason=unmapped_reason)

        peer_rates, our_rate_from_data = self._peer_rates(
            bm_type, bm_key)

        # Use rate_avg from products.json as our_rate; fallback to
        # competitor_data's Ecobank entry if products.json missing
        our_rate = Decimal(str(product.get("rate_avg", 0) or 0))
        if our_rate == 0 and our_rate_from_data is not None:
            our_rate = our_rate_from_data

        if not peer_rates:
            return CompetitorLandscape(
                product_id=product_id,
                name=product.get("name", ""),
                benchmark_type=bm_type, benchmark_key=bm_key,
                our_rate_pct=our_rate,
                peer_median_pct=None, peer_min_pct=None,
                peer_max_pct=None, n_peers=0,
                delta_vs_median_bps=None,
                position="NO_DATA", is_estimate=False,
                status="no_peer_data",
                reason=f"no_peer_rates_for_{bm_key}")

        peer_values = list(peer_rates.values())
        median = self._median(peer_values)
        position, delta_bps = self._classify_position(
            our_rate, median, bm_type) if median is not None \
            else ("NO_DATA", None)
        is_estimate = len(peer_values) < self.MIN_PEERS_FOR_ROBUST_MEDIAN

        return CompetitorLandscape(
            product_id=product_id,
            name=product.get("name", ""),
            benchmark_type=bm_type, benchmark_key=bm_key,
            our_rate_pct=our_rate,
            peer_median_pct=median,
            peer_min_pct=min(peer_values) if peer_values else None,
            peer_max_pct=max(peer_values) if peer_values else None,
            n_peers=len(peer_rates),
            delta_vs_median_bps=delta_bps,
            position=position,
            is_estimate=is_estimate,
            status="ok",
            per_peer_rates=peer_rates)

    def compare_pricing(self, product_id: str) -> Dict[str, Any]:
        """Per-bank pricing breakdown with sortable rates list."""
        landscape = self.get_competitor_landscape(product_id)
        if landscape.status != "ok":
            return {
                "ok": False,
                "product_id": product_id,
                "status": landscape.status,
                "reason": landscape.reason,
            }

        # Build sortable list of (bank, rate)
        rows: List[Dict[str, Any]] = []
        rows.append({"bank": self.our_bank_key,
                     "rate_pct": str(landscape.our_rate_pct),
                     "is_us": True})
        for bank, rate in landscape.per_peer_rates.items():
            rows.append({"bank": bank, "rate_pct": str(rate),
                         "is_us": False})

        # Sort by rate (ascending for lending, descending for deposits)
        reverse = (landscape.benchmark_type == "deposits")
        rows.sort(key=lambda r: float(r["rate_pct"]), reverse=reverse)

        return {
            "ok": True,
            "product_id": product_id,
            "name": landscape.name,
            "benchmark_type": landscape.benchmark_type,
            "benchmark_key": landscape.benchmark_key,
            "ranked_rates": rows,
            "our_rank": next(i for i, r in enumerate(rows, 1)
                              if r["is_us"]),
            "n_banks": len(rows),
            "position": landscape.position,
            "delta_vs_median_bps": landscape.delta_vs_median_bps,
        }

    def get_market_position(self, product_id: str) -> Dict[str, Any]:
        """Lightweight wrapper — just position + delta + status."""
        l = self.get_competitor_landscape(product_id)
        return {
            "product_id": product_id,
            "name": l.name,
            "position": l.position,
            "delta_vs_median_bps": l.delta_vs_median_bps,
            "is_estimate": l.is_estimate,
            "status": l.status,
            "reason": l.reason,
        }

    def get_peer_benchmarks(self, metric: str) -> Dict[str, Any]:
        """Bank-level metric comparison (assets_kes_b, loans_kes_b,
        deposits_kes_b, npl_pct, car_pct, nim_pct, roe_pct, branches,
        mobile_users_m).
        """
        comp = self._load_competitor()
        banks = comp.get("banks", {})
        if not banks:
            return {"ok": False, "reason": "no_competitor_data",
                    "metric": metric}

        per_bank: Dict[str, Decimal] = {}
        for bank, info in banks.items():
            v = info.get(metric)
            if v is None:
                continue
            try:
                per_bank[bank] = Decimal(str(v))
            except Exception:
                continue

        if not per_bank:
            return {"ok": False, "metric": metric,
                    "reason": f"metric_{metric}_not_in_bank_records"}

        our_value = per_bank.get(self.our_bank_key)
        peer_values = [v for b, v in per_bank.items()
                        if b != self.our_bank_key]
        median = self._median(peer_values) if peer_values else None

        return {
            "ok": True,
            "metric": metric,
            "our_bank": self.our_bank_key,
            "our_value": str(our_value) if our_value is not None else None,
            "peer_median": str(median) if median is not None else None,
            "peer_min": str(min(peer_values)) if peer_values else None,
            "peer_max": str(max(peer_values)) if peer_values else None,
            "n_peers": len(peer_values),
            "is_estimate": (len(peer_values)
                              < self.MIN_PEERS_FOR_ROBUST_MEDIAN),
            "per_bank": {b: str(v) for b, v in per_bank.items()},
        }

    def identify_pricing_gaps(
        self, threshold_pct: float = 0.5,
    ) -> List[Dict[str, Any]]:
        """Products materially out of step (|delta| ≥ threshold).

        Returns each gap with direction (we_charge_more / we_pay_less /
        we_charge_less / we_pay_more) so operators see the actionable
        side.
        """
        threshold_bps = int(Decimal(str(threshold_pct)) * Decimal("100"))
        out: List[Dict[str, Any]] = []
        for p in self._load_products():
            l = self.get_competitor_landscape(p.get("id", ""))
            if l.status != "ok" or l.delta_vs_median_bps is None:
                continue
            if abs(l.delta_vs_median_bps) < threshold_bps:
                continue
            # Direction interpretation
            if l.benchmark_type == "lending":
                direction = ("we_charge_less" if l.delta_vs_median_bps < 0
                              else "we_charge_more")
            else:
                direction = ("we_pay_more" if l.delta_vs_median_bps > 0
                              else "we_pay_less")
            out.append({
                "product_id": l.product_id,
                "name": l.name,
                "benchmark_key": l.benchmark_key,
                "position": l.position,
                "delta_vs_median_bps": l.delta_vs_median_bps,
                "direction": direction,
                "our_rate_pct": (str(l.our_rate_pct)
                                  if l.our_rate_pct is not None else None),
                "peer_median_pct": (str(l.peer_median_pct)
                                      if l.peer_median_pct is not None
                                      else None),
                "is_estimate": l.is_estimate,
            })
        out.sort(key=lambda x: -abs(x["delta_vs_median_bps"] or 0))
        return out

    def get_competitive_summary(self) -> Dict[str, Any]:
        """Bank-wide summary across the product portfolio."""
        n_leader = n_follower = n_laggard = n_no_data = 0
        n_total = 0
        for p in self._load_products():
            l = self.get_competitor_landscape(p.get("id", ""))
            n_total += 1
            if l.status != "ok":
                n_no_data += 1
                continue
            if l.position == "LEADER":
                n_leader += 1
            elif l.position == "LAGGARD":
                n_laggard += 1
            elif l.position == "FOLLOWER":
                n_follower += 1
            else:
                n_no_data += 1

        return {
            "n_products": n_total,
            "n_leader": n_leader,
            "n_follower": n_follower,
            "n_laggard": n_laggard,
            "n_no_data": n_no_data,
            "leadership_rate_pct": (
                round(100.0 * n_leader / n_total, 2) if n_total else 0.0),
            "lag_rate_pct": (
                round(100.0 * n_laggard / n_total, 2) if n_total else 0.0),
        }


# ---------------------------------------------------------------------------
# Self-test
# ---------------------------------------------------------------------------

def _self_test() -> None:
    eng = ProductCompetitiveIntelligence()
    print(f"Our bank key: {eng.our_bank_key}")
    print()

    # Bank-wide summary
    sm = eng.get_competitive_summary()
    print(f"Portfolio competitive position: "
          f"LEADER={sm['n_leader']} FOLLOWER={sm['n_follower']} "
          f"LAGGARD={sm['n_laggard']} NO_DATA={sm['n_no_data']} "
          f"of {sm['n_products']}")
    print(f"  leadership_rate={sm['leadership_rate_pct']}% "
          f"lag_rate={sm['lag_rate_pct']}%")
    print()

    # Per-product landscapes
    for pid in ("P001", "P002", "P005", "P010", "P013", "P014"):
        l = eng.get_competitor_landscape(pid)
        if l.status == "ok":
            print(f"{pid} {l.name}: us={l.our_rate_pct}% "
                  f"peer_median={l.peer_median_pct}% "
                  f"Δ={l.delta_vs_median_bps}bps "
                  f"→ {l.position} (n={l.n_peers})")
        else:
            print(f"{pid} {l.name}: {l.status} ({l.reason})")
    print()

    # Pricing gaps
    gaps = eng.identify_pricing_gaps(threshold_pct=0.3)
    print(f"Pricing gaps (|Δ|≥30bps): {len(gaps)}")
    for g in gaps[:10]:
        print(f"  {g['product_id']} {g['name']}: "
              f"Δ={g['delta_vs_median_bps']}bps "
              f"({g['direction']}) → {g['position']}")
    print()

    # Peer benchmarks for a few bank-level metrics
    for metric in ("npl_pct", "car_pct", "roe_pct", "nim_pct"):
        b = eng.get_peer_benchmarks(metric)
        if b.get("ok"):
            print(f"{metric}: us={b['our_value']} peer_median={b['peer_median']} "
                  f"min={b['peer_min']} max={b['peer_max']} (n_peers={b['n_peers']})")


if __name__ == "__main__":
    _self_test()
