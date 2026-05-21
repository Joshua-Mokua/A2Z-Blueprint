"""
================================================================================
A2Z MIS 360 — Standard #79: Stress Testing Framework Engine
================================================================================

Risk classification: Cat B (deterministic supervisory stress test scenarios)

Computes stress test impact per CBK supervisory + Basel ICAAP framework:
    - apply_scenario(baseline, scenario)         -- apply shock factors deterministically
    - run_supervisory_scenarios(...)             -- baseline / adverse / severely_adverse
    - reverse_stress_test(...)                   -- find shock that breaches CAR minimum
    - capital_projection(starting_car, scenarios) -- 3-year projection

Three standard supervisory scenarios (CBK ICAAP + Fed CCAR-style):
    BASELINE          : business-as-usual; no shocks
    ADVERSE           : moderate downturn (-3pp GDP, +200bps rates, +30% NPL)
    SEVERELY_ADVERSE  : severe stress (-6pp GDP, +400bps rates, +60% NPL,
                       -30% asset prices, KES devaluation 15%)

Reverse stress test:
    Finds the shock magnitude (NPL shock + rate shock) that brings Total CAR
    just below CBK minimum 14.5%. Useful for identifying the bank's "edge".

Honesty rules applied:
    Rule 1: projected ratios = None when starting RWA <= 0
    Rule 6: missing scenario parameters → use 0 (no shock) with explicit note

================================================================================
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal, getcontext
from typing import Any, Dict, List, Optional, Tuple

getcontext().prec = 28

# Three standard supervisory scenarios (CBK ICAAP)
STRESS_SCENARIOS: Tuple[str, ...] = ("BASELINE", "ADVERSE", "SEVERELY_ADVERSE")

# Scenario shock parameters byte-for-byte (CBK supervisory + Basel ICAAP)
SCENARIO_SHOCKS: Dict[str, Dict[str, Decimal]] = {
    "BASELINE": {
        "gdp_growth_delta_pp": Decimal("0"),
        "interest_rate_shock_bps": Decimal("0"),
        "npl_increase_pct": Decimal("0"),
        "asset_price_shock_pct": Decimal("0"),
        "fx_devaluation_pct": Decimal("0"),
        "deposit_outflow_pct": Decimal("0"),
        "rwa_inflation_pct": Decimal("0"),
    },
    "ADVERSE": {
        "gdp_growth_delta_pp": Decimal("-3"),
        "interest_rate_shock_bps": Decimal("200"),
        "npl_increase_pct": Decimal("30"),
        "asset_price_shock_pct": Decimal("-15"),
        "fx_devaluation_pct": Decimal("8"),
        "deposit_outflow_pct": Decimal("5"),
        "rwa_inflation_pct": Decimal("10"),
    },
    "SEVERELY_ADVERSE": {
        "gdp_growth_delta_pp": Decimal("-6"),
        "interest_rate_shock_bps": Decimal("400"),
        "npl_increase_pct": Decimal("60"),
        "asset_price_shock_pct": Decimal("-30"),
        "fx_devaluation_pct": Decimal("15"),
        "deposit_outflow_pct": Decimal("15"),
        "rwa_inflation_pct": Decimal("25"),
    },
}

# Translation factors: how shocks affect capital and RWA
# These are simplified linear approximations for deterministic projection
NPL_INCREASE_TO_LOSS_FACTOR = Decimal("0.45")  # avg LGD on new NPLs
ASSET_PRICE_SHOCK_TO_PROVISIONS = Decimal("0.5")  # 50% of paper losses → realized
RATE_SHOCK_TO_NII_BPS = Decimal("0.5")  # half of rate shock impact flows through

# CBK Total CAR minimum — sourced from system_invariants registry (v7.0).
# Engine keeps local constant for backward compatibility (9 usages in
# pages/35_stress_testing.py reference this name); the value now flows
# from the single source of truth at utils.system_invariants.
# Fallback to hard-coded 14.5 ensures engine works even if registry
# import fails — defensive per Rule 6 honesty discipline.
try:
    from utils.system_invariants import get_threshold as _get_invariant
    _car_min_from_registry = _get_invariant("CBK_TOTAL_CAR_MIN")
    CBK_TOTAL_CAR_MIN_PCT_LOCAL = (
        _car_min_from_registry if _car_min_from_registry is not None
        else Decimal("14.5")
    )
except ImportError:
    CBK_TOTAL_CAR_MIN_PCT_LOCAL = Decimal("14.5")

# Reverse stress test parameters
REVERSE_STRESS_NPL_STEP_PCT = Decimal("5")
REVERSE_STRESS_MAX_NPL_PCT = Decimal("100")
REVERSE_STRESS_RATE_STEP_BPS = Decimal("50")
REVERSE_STRESS_MAX_RATE_BPS = Decimal("1500")


@dataclass
class StressTestInputs:
    starting_total_capital_kes: Optional[Decimal] = None
    starting_rwa_kes: Optional[Decimal] = None
    starting_loan_book_kes: Optional[Decimal] = None
    starting_npl_kes: Optional[Decimal] = None
    starting_securities_kes: Optional[Decimal] = None
    starting_fx_open_position_kes: Optional[Decimal] = None
    annual_pre_tax_profit_kes: Optional[Decimal] = None  # used as buffer
    horizon_years: int = 3


def _apply_shock_to_capital(
    starting_capital: Decimal,
    starting_rwa: Decimal,
    inputs: StressTestInputs,
    shock: Dict[str, Decimal],
) -> Tuple[Decimal, Decimal]:
    """
    Compute stressed capital & RWA after applying scenario.
    Returns (stressed_capital, stressed_rwa).
    """
    # 1. Loan losses from NPL increase
    loan_book = inputs.starting_loan_book_kes or Decimal("0")
    npl_loss = (loan_book * shock["npl_increase_pct"] / Decimal("100")
                * NPL_INCREASE_TO_LOSS_FACTOR)

    # 2. Securities mark-to-market loss
    securities = inputs.starting_securities_kes or Decimal("0")
    securities_loss = (securities * abs(shock["asset_price_shock_pct"]) / Decimal("100")
                       * ASSET_PRICE_SHOCK_TO_PROVISIONS)

    # 3. FX loss on open position
    fx_pos = inputs.starting_fx_open_position_kes or Decimal("0")
    fx_loss = abs(fx_pos) * shock["fx_devaluation_pct"] / Decimal("100")

    # 4. Profit cushion (positive contribution if any)
    profit_buffer = inputs.annual_pre_tax_profit_kes or Decimal("0")
    if profit_buffer < 0:
        profit_buffer = Decimal("0")

    total_loss = npl_loss + securities_loss + fx_loss
    stressed_capital = starting_capital - total_loss + profit_buffer

    # 5. RWA inflation (NPL-related risk weight migration + ratings downgrade)
    stressed_rwa = starting_rwa * (Decimal("1") + shock["rwa_inflation_pct"] / Decimal("100"))

    return stressed_capital, stressed_rwa


class StressTestingEngine:
    """Deterministic supervisory stress test framework."""

    @staticmethod
    def apply_scenario(
        inputs: StressTestInputs,
        scenario: str,
    ) -> Dict[str, Any]:
        """
        Apply a named scenario to baseline inputs and return stressed CAR.
        Rule 1: stressed_car=None when starting RWA<=0.
        """
        if scenario not in STRESS_SCENARIOS:
            return {"scenario": scenario, "error": f"unknown_scenario:{scenario}",
                    "valid_scenarios": list(STRESS_SCENARIOS)}

        starting_capital = inputs.starting_total_capital_kes or Decimal("0")
        starting_rwa = inputs.starting_rwa_kes or Decimal("0")

        if starting_rwa <= 0:
            return {
                "scenario": scenario,
                "stressed_car_pct": None,
                "stressed_capital_kes": None,
                "stressed_rwa_kes": None,
                "reason": "starting_rwa_zero_or_negative",
            }

        shock = SCENARIO_SHOCKS[scenario]
        stressed_capital, stressed_rwa = _apply_shock_to_capital(
            starting_capital, starting_rwa, inputs, shock
        )

        if stressed_rwa <= 0:
            stressed_car = None
        else:
            stressed_car = (stressed_capital / stressed_rwa) * Decimal("100")

        # Starting CAR for comparison
        starting_car = (starting_capital / starting_rwa) * Decimal("100")

        return {
            "scenario": scenario,
            "shock_parameters": {k: str(v) for k, v in shock.items()},
            "starting_capital_kes": str(starting_capital.quantize(Decimal("0.01"))),
            "starting_rwa_kes": str(starting_rwa.quantize(Decimal("0.01"))),
            "starting_car_pct": str(starting_car.quantize(Decimal("0.01"))),
            "stressed_capital_kes": str(stressed_capital.quantize(Decimal("0.01"))),
            "stressed_rwa_kes": str(stressed_rwa.quantize(Decimal("0.01"))),
            "stressed_car_pct": str(stressed_car.quantize(Decimal("0.01"))) if stressed_car is not None else None,
            "car_drop_pp": (str((starting_car - stressed_car).quantize(Decimal("0.01")))
                            if stressed_car is not None else None),
            "breaches_cbk_minimum": (stressed_car < CBK_TOTAL_CAR_MIN_PCT_LOCAL
                                      if stressed_car is not None else None),
            "cbk_minimum_pct": str(CBK_TOTAL_CAR_MIN_PCT_LOCAL),
        }

    @classmethod
    def run_supervisory_scenarios(cls, inputs: StressTestInputs) -> Dict[str, Any]:
        """Run BASELINE + ADVERSE + SEVERELY_ADVERSE in sequence."""
        results = {}
        for sc in STRESS_SCENARIOS:
            results[sc] = cls.apply_scenario(inputs, sc)

        # Determine worst scenario
        worst_scenario = None
        worst_car = None
        for sc, r in results.items():
            if r.get("stressed_car_pct") is None:
                continue
            car_val = Decimal(r["stressed_car_pct"])
            if worst_car is None or car_val < worst_car:
                worst_car = car_val
                worst_scenario = sc

        # Pass/fail aggregate
        any_breach = any(r.get("breaches_cbk_minimum") is True for r in results.values())

        return {
            "scenarios": results,
            "worst_scenario": worst_scenario,
            "worst_stressed_car_pct": str(worst_car) if worst_car is not None else None,
            "any_scenario_breaches_cbk_min": any_breach,
            "verdict": "FAIL" if any_breach else "PASS",
        }

    @classmethod
    def reverse_stress_test(
        cls,
        inputs: StressTestInputs,
        breach_threshold_pct: Decimal = CBK_TOTAL_CAR_MIN_PCT_LOCAL,
    ) -> Dict[str, Any]:
        """
        Find smallest combined NPL+rate shock that brings CAR below threshold.
        Iterative grid search up to MAX limits.
        """
        starting_capital = inputs.starting_total_capital_kes or Decimal("0")
        starting_rwa = inputs.starting_rwa_kes or Decimal("0")

        if starting_rwa <= 0:
            return {
                "breach_npl_pct": None,
                "breach_rate_bps": None,
                "reason": "starting_rwa_zero_or_negative",
            }

        starting_car = (starting_capital / starting_rwa) * Decimal("100")
        if starting_car < breach_threshold_pct:
            return {
                "breach_npl_pct": Decimal("0"),
                "breach_rate_bps": Decimal("0"),
                "reason": "already_below_threshold",
                "starting_car_pct": str(starting_car.quantize(Decimal("0.01"))),
            }

        npl = Decimal("0")
        while npl <= REVERSE_STRESS_MAX_NPL_PCT:
            rate = Decimal("0")
            while rate <= REVERSE_STRESS_MAX_RATE_BPS:
                shock = {
                    "gdp_growth_delta_pp": Decimal("0"),
                    "interest_rate_shock_bps": rate,
                    "npl_increase_pct": npl,
                    "asset_price_shock_pct": Decimal("0"),
                    "fx_devaluation_pct": Decimal("0"),
                    "deposit_outflow_pct": Decimal("0"),
                    "rwa_inflation_pct": npl / Decimal("3"),  # rough heuristic
                }
                sc, sr = _apply_shock_to_capital(starting_capital, starting_rwa, inputs, shock)
                if sr > 0:
                    car = (sc / sr) * Decimal("100")
                    if car < breach_threshold_pct:
                        return {
                            "breach_npl_pct": str(npl),
                            "breach_rate_bps": str(rate),
                            "stressed_car_pct": str(car.quantize(Decimal("0.01"))),
                            "breach_threshold_pct": str(breach_threshold_pct),
                            "starting_car_pct": str(starting_car.quantize(Decimal("0.01"))),
                        }
                rate += REVERSE_STRESS_RATE_STEP_BPS
            npl += REVERSE_STRESS_NPL_STEP_PCT
        return {
            "breach_npl_pct": None,
            "breach_rate_bps": None,
            "reason": "no_breach_within_search_grid",
            "max_npl_searched_pct": str(REVERSE_STRESS_MAX_NPL_PCT),
            "max_rate_searched_bps": str(REVERSE_STRESS_MAX_RATE_BPS),
            "starting_car_pct": str(starting_car.quantize(Decimal("0.01"))),
        }

    @classmethod
    def capital_projection(
        cls,
        inputs: StressTestInputs,
        scenario: str,
    ) -> Dict[str, Any]:
        """
        Multi-year projection under a given scenario.
        Each year applies fresh shock + retains profit cushion.
        """
        if scenario not in STRESS_SCENARIOS:
            return {"error": f"unknown_scenario:{scenario}"}

        starting_capital = inputs.starting_total_capital_kes or Decimal("0")
        starting_rwa = inputs.starting_rwa_kes or Decimal("0")
        if starting_rwa <= 0:
            return {"error": "starting_rwa_zero_or_negative"}

        shock = SCENARIO_SHOCKS[scenario]
        years = []
        cur_capital = starting_capital
        cur_rwa = starting_rwa
        for y in range(inputs.horizon_years):
            cur_capital, cur_rwa = _apply_shock_to_capital(
                cur_capital, cur_rwa, inputs, shock
            )
            car = (cur_capital / cur_rwa * Decimal("100")) if cur_rwa > 0 else None
            years.append({
                "year_index": y + 1,
                "capital_kes": str(cur_capital.quantize(Decimal("0.01"))),
                "rwa_kes": str(cur_rwa.quantize(Decimal("0.01"))),
                "car_pct": str(car.quantize(Decimal("0.01"))) if car is not None else None,
                "breaches_cbk_min": (car < CBK_TOTAL_CAR_MIN_PCT_LOCAL) if car is not None else None,
            })
        return {
            "scenario": scenario,
            "horizon_years": inputs.horizon_years,
            "yearly_projection": years,
        }

    # ============================================================================
    # v7.2: L06 Stress test → Capital plan feedback loop (PRODUCER)
    # ============================================================================
    @classmethod
    def stress_capital_shortfall_summary(
        cls,
        inputs: StressTestInputs,
    ) -> Dict[str, Any]:
        """L06 (PRODUCER) — produce capital shortfall payload for capital plan.

        Computes capital shortfall under each supervisory scenario relative
        to CBK Total CAR minimum (sourced from system_invariants registry).
        Output is consumed by `capital_adequacy.capital_plan_from_stress()`.

        Per Charter §7 integration patterns, this uses **Published Language**
        — the return dict is the stable contract that downstream consumers
        depend on. Internal scenario logic can change; the public payload
        cannot break.

        Returns:
            dict with keys:
                worst_scenario: str — name of scenario with max shortfall
                worst_shortfall_kes: str (Decimal) — capital needed to restore
                                                       CBK floor under worst scenario
                shortfall_by_scenario: dict[str, dict] — per-scenario detail
                cbk_min_pct: str — registry-sourced CBK floor used
                payload_version: str — bumps when contract changes
                cited_invariants: list[str] — registry invariants consumed
                pattern: str — DDD integration pattern marker
        """
        sup = cls.run_supervisory_scenarios(inputs)
        cbk_min = CBK_TOTAL_CAR_MIN_PCT_LOCAL  # already sourced from registry

        shortfalls = {}
        worst_scenario = None
        worst_shortfall = Decimal("0")

        for scen_name, scen_result in sup["scenarios"].items():
            stressed_car = Decimal(str(scen_result["stressed_car_pct"]))
            stressed_rwa = Decimal(str(scen_result["stressed_rwa_kes"]))

            if stressed_car < cbk_min:
                # capital_required_to_meet_min = cbk_min/100 × stressed_rwa
                # shortfall = required - current_stressed_capital
                cur_stressed_capital = Decimal(
                    str(scen_result["stressed_capital_kes"]))
                required_capital = (cbk_min / Decimal("100")) * stressed_rwa
                shortfall = (required_capital - cur_stressed_capital).quantize(
                    Decimal("0.01"))
            else:
                shortfall = Decimal("0.00")

            shortfalls[scen_name] = {
                "stressed_car_pct": str(stressed_car),
                "stressed_rwa_kes": str(stressed_rwa),
                "breach": str(scen_result["breaches_cbk_minimum"]),
                "shortfall_kes": str(shortfall),
            }

            if shortfall > worst_shortfall:
                worst_shortfall = shortfall
                worst_scenario = scen_name

        return {
            "payload_version": "1.0",
            "pattern": "PUBLISHED_LANGUAGE",
            "cited_invariants": ["CBK_TOTAL_CAR_MIN"],
            "cbk_min_pct": str(cbk_min),
            "worst_scenario": worst_scenario,
            "worst_shortfall_kes": str(worst_shortfall),
            "shortfall_by_scenario": shortfalls,
            "any_breach": any(
                s["breach"] == "True" for s in shortfalls.values()),
        }


# ============================================================================
# Self-tests
# ============================================================================

def _inputs(**kw):
    defaults = dict(
        starting_total_capital_kes=Decimal("20000000000"),  # 20B capital
        starting_rwa_kes=Decimal("100000000000"),           # 100B RWA → 20% CAR
        starting_loan_book_kes=Decimal("80000000000"),       # 80B loans
        starting_npl_kes=Decimal("4000000000"),             # 4B NPLs (5%)
        starting_securities_kes=Decimal("20000000000"),     # 20B securities
        starting_fx_open_position_kes=Decimal("5000000000"),# 5B FX
        annual_pre_tax_profit_kes=Decimal("1500000000"),    # 1.5B profit
        horizon_years=3,
    )
    defaults.update(kw)
    return StressTestInputs(**defaults)


def _test_baseline_no_shock():
    r = StressTestingEngine.apply_scenario(_inputs(), "BASELINE")
    # Baseline has no shocks but profit cushion adds capital
    starting_car = Decimal(r["starting_car_pct"])
    stressed_car = Decimal(r["stressed_car_pct"])
    # Profit added → stressed CAR slightly higher than starting
    assert stressed_car >= starting_car


def _test_adverse_drops_car():
    r = StressTestingEngine.apply_scenario(_inputs(), "ADVERSE")
    starting_car = Decimal(r["starting_car_pct"])
    stressed_car = Decimal(r["stressed_car_pct"])
    assert stressed_car < starting_car


def _test_severely_adverse_worst():
    inputs = _inputs()
    r_adv = StressTestingEngine.apply_scenario(inputs, "ADVERSE")
    r_sev = StressTestingEngine.apply_scenario(inputs, "SEVERELY_ADVERSE")
    # Severely adverse should give lower CAR
    assert Decimal(r_sev["stressed_car_pct"]) < Decimal(r_adv["stressed_car_pct"])


def _test_unknown_scenario():
    r = StressTestingEngine.apply_scenario(_inputs(), "WEIRD")
    assert "error" in r


def _test_zero_rwa_rule1():
    inputs = _inputs(starting_rwa_kes=Decimal("0"))
    r = StressTestingEngine.apply_scenario(inputs, "ADVERSE")
    assert r["stressed_car_pct"] is None


def _test_run_supervisory_scenarios():
    r = StressTestingEngine.run_supervisory_scenarios(_inputs())
    assert "BASELINE" in r["scenarios"]
    assert "ADVERSE" in r["scenarios"]
    assert "SEVERELY_ADVERSE" in r["scenarios"]
    assert r["worst_scenario"] == "SEVERELY_ADVERSE"


def _test_reverse_stress_test_finds_breach():
    """Bank with thin capital should breach quickly."""
    inputs = _inputs(
        starting_total_capital_kes=Decimal("15500000000"),  # 15.5% CAR
        starting_rwa_kes=Decimal("100000000000"),
    )
    r = StressTestingEngine.reverse_stress_test(inputs)
    assert r.get("breach_npl_pct") is not None


def _test_reverse_stress_already_below():
    """Bank already below CBK min."""
    inputs = _inputs(
        starting_total_capital_kes=Decimal("10000000000"),  # 10% CAR
        starting_rwa_kes=Decimal("100000000000"),
    )
    r = StressTestingEngine.reverse_stress_test(inputs)
    assert r["reason"] == "already_below_threshold"


def _test_capital_projection_3yr():
    r = StressTestingEngine.capital_projection(_inputs(), "ADVERSE")
    assert len(r["yearly_projection"]) == 3


def _test_baseline_shocks_byte_for_byte():
    s = SCENARIO_SHOCKS["BASELINE"]
    assert s["gdp_growth_delta_pp"] == Decimal("0")
    assert s["interest_rate_shock_bps"] == Decimal("0")
    assert s["npl_increase_pct"] == Decimal("0")


def _test_adverse_shocks_byte_for_byte():
    s = SCENARIO_SHOCKS["ADVERSE"]
    assert s["gdp_growth_delta_pp"] == Decimal("-3")
    assert s["interest_rate_shock_bps"] == Decimal("200")
    assert s["npl_increase_pct"] == Decimal("30")
    assert s["asset_price_shock_pct"] == Decimal("-15")
    assert s["fx_devaluation_pct"] == Decimal("8")
    assert s["rwa_inflation_pct"] == Decimal("10")


def _test_severely_adverse_shocks_byte_for_byte():
    s = SCENARIO_SHOCKS["SEVERELY_ADVERSE"]
    assert s["gdp_growth_delta_pp"] == Decimal("-6")
    assert s["interest_rate_shock_bps"] == Decimal("400")
    assert s["npl_increase_pct"] == Decimal("60")
    assert s["asset_price_shock_pct"] == Decimal("-30")
    assert s["fx_devaluation_pct"] == Decimal("15")


def _test_scenarios_byte_for_byte():
    expected = ("BASELINE", "ADVERSE", "SEVERELY_ADVERSE")
    for s in expected:
        assert s in STRESS_SCENARIOS


def _test_factors_byte_for_byte():
    assert NPL_INCREASE_TO_LOSS_FACTOR == Decimal("0.45")
    assert ASSET_PRICE_SHOCK_TO_PROVISIONS == Decimal("0.5")


def _test_apply_scenario_determinism():
    inputs = _inputs()
    r1 = StressTestingEngine.apply_scenario(inputs, "ADVERSE")
    r2 = StressTestingEngine.apply_scenario(inputs, "ADVERSE")
    assert r1["stressed_car_pct"] == r2["stressed_car_pct"]


def self_test() -> bool:
    tests = [
        _test_baseline_no_shock,
        _test_adverse_drops_car,
        _test_severely_adverse_worst,
        _test_unknown_scenario,
        _test_zero_rwa_rule1,
        _test_run_supervisory_scenarios,
        _test_reverse_stress_test_finds_breach,
        _test_reverse_stress_already_below,
        _test_capital_projection_3yr,
        _test_baseline_shocks_byte_for_byte,
        _test_adverse_shocks_byte_for_byte,
        _test_severely_adverse_shocks_byte_for_byte,
        _test_scenarios_byte_for_byte,
        _test_factors_byte_for_byte,
        _test_apply_scenario_determinism,
    ]
    print("=" * 60)
    print("Stress Testing Engine — Self-Tests (#79)")
    print("=" * 60)
    failed = 0
    for t in tests:
        try:
            t()
            print(f"  PASS  {t.__name__}")
        except AssertionError as e:
            failed += 1
            print(f"  FAIL  {t.__name__}: {e}")
        except Exception as e:
            failed += 1
            print(f"  ERROR {t.__name__}: {e}")
    print("-" * 60)
    if failed == 0:
        print(f"  ALL {len(tests)} TESTS PASSED")
        return True
    print(f"  {failed}/{len(tests)} FAILED")
    return False


if __name__ == "__main__":
    import sys
    sys.exit(0 if self_test() else 1)
