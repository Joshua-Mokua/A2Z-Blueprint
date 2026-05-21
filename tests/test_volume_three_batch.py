"""tests/test_volume_three_batch.py — Standards #24-#30 (v5.49).

Coverage:
  Standard #24 — CustomerAllocationOptimizer
  Standard #25 — Cost allocation rule schema (DDL)
  Standard #26 — DRIVERS catalog
  Standard #27 — Profitability heatmap data layer
  Standard #28 — ProfitabilityTrends
  Standard #29 — submit_rm_profitability_to_bsc
  Standard #30 — build_md_dashboard_data

Three harness tests at the end:
  - test_allocation_optimization_correctness_meets_99_percent → G35
  - test_trend_analysis_correctness_meets_99_percent           → G36
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest


ROOT = Path(__file__).parent.parent
ALLOCATION_FIXTURES = ROOT / "tests" / "fixtures" / "allocation_scenarios.json"
TREND_FIXTURES      = ROOT / "tests" / "fixtures" / "trend_scenarios.json"
ALLOCATION_RESULTS  = ROOT / "allocation_optimization_results.json"
TREND_RESULTS       = ROOT / "trend_analysis_results.json"


# ═══════════════════════════════════════════════════════════════════════
# Files exist
# ═══════════════════════════════════════════════════════════════════════

class TestFilesExist:
    def test_allocation_module(self):
        assert (ROOT / "utils" / "allocation_optimizer.py").exists()

    def test_cost_allocation_module(self):
        assert (ROOT / "utils" / "cost_allocation.py").exists()

    def test_trends_module(self):
        assert (ROOT / "utils" / "profitability_trends.py").exists()

    def test_integration_module(self):
        assert (ROOT / "utils" / "profitability_integration.py").exists()

    def test_heatmap_module(self):
        assert (ROOT / "utils" / "profitability_heatmap.py").exists()

    def test_allocation_fixtures(self):
        assert ALLOCATION_FIXTURES.exists()
        data = json.loads(ALLOCATION_FIXTURES.read_text())
        assert isinstance(data, list) and len(data) >= 10

    def test_trend_fixtures(self):
        assert TREND_FIXTURES.exists()
        data = json.loads(TREND_FIXTURES.read_text())
        assert isinstance(data, list) and len(data) >= 10


# ═══════════════════════════════════════════════════════════════════════
# Standard #24 — CustomerAllocationOptimizer
# ═══════════════════════════════════════════════════════════════════════

def _build_allocation_engine(fixture_input: dict):
    from utils.allocation_optimizer import CustomerAllocationOptimizer
    customers = fixture_input["customers"]
    rms = fixture_input["rms"]
    rm_cap = fixture_input["rm_capacity"]
    proj = fixture_input["projections"]
    current = fixture_input.get("current_allocation", {})

    def proj_fn(c, r, p):
        return proj.get(f"{c}__{r}")

    return CustomerAllocationOptimizer(
        customers_in_segment_fn=lambda s: customers,
        rms_for_segment_fn=lambda s: rms,
        rm_capacity_fn=lambda r: rm_cap.get(r, 5),
        current_allocation_fn=lambda c: current.get(c),
        projection_fn=proj_fn,
    )


class TestStandard24:
    def test_spec_method_exists(self):
        from utils.allocation_optimizer import CustomerAllocationOptimizer
        e = CustomerAllocationOptimizer()
        assert hasattr(e, "optimize_rm_allocation")
        assert callable(e.optimize_rm_allocation)

    def test_spec_named_helper_exists(self):
        from utils.allocation_optimizer import CustomerAllocationOptimizer
        e = CustomerAllocationOptimizer()
        assert hasattr(e, "project_profitability_if_served_by")

    def test_spec_return_keys(self):
        from utils.allocation_optimizer import CustomerAllocationOptimizer
        e = CustomerAllocationOptimizer(
            customers_in_segment_fn=lambda s: ["C1"],
            rms_for_segment_fn=lambda s: ["RM1"],
            projection_fn=lambda c, r, p: {"projected_pbt": 100, "ftp_mode": "on"},
        )
        r = e.optimize_rm_allocation("Mass")
        assert "assignments" in r
        assert "total_potential_gain" in r

    def test_empty_segment_returns_empty(self):
        from utils.allocation_optimizer import CustomerAllocationOptimizer
        e = CustomerAllocationOptimizer()
        assert e.optimize_rm_allocation("") == {}

    def test_provisional_threshold(self):
        """>50% FTP-off → provisional=True."""
        from utils.allocation_optimizer import CustomerAllocationOptimizer
        proj = {
            ("C1", "RM1"): {"projected_pbt": 100, "ftp_mode": "off"},
            ("C2", "RM1"): {"projected_pbt": 50, "ftp_mode": "off"},
            ("C3", "RM1"): {"projected_pbt": 30, "ftp_mode": "on"},
        }
        e = CustomerAllocationOptimizer(
            customers_in_segment_fn=lambda s: ["C1", "C2", "C3"],
            rms_for_segment_fn=lambda s: ["RM1"],
            rm_capacity_fn=lambda r: 5,
            projection_fn=lambda c, r, p: proj.get((c, r)),
        )
        r = e.optimize_rm_allocation("MostlyOff")
        assert r["provisional"] is True

    def test_warning_cites_mandatory_standard_11(self):
        from utils.allocation_optimizer import CustomerAllocationOptimizer
        proj = {("C1", "RM1"): {"projected_pbt": 100, "ftp_mode": "off"}}
        e = CustomerAllocationOptimizer(
            customers_in_segment_fn=lambda s: ["C1"],
            rms_for_segment_fn=lambda s: ["RM1"],
            rm_capacity_fn=lambda r: 5,
            projection_fn=lambda c, r, p: proj.get((c, r)),
        )
        r = e.optimize_rm_allocation("X")
        assert "Mandatory Standard #11" in r["data_quality_warning"]


# ═══════════════════════════════════════════════════════════════════════
# Standard #25 + #26 — Cost allocation
# ═══════════════════════════════════════════════════════════════════════

class TestStandard25_26:
    def test_drivers_has_spec_keys(self):
        from utils.cost_allocation import DRIVERS
        for k in ("staff_count_by_segment", "loan_portfolio_value", "deposit_balance"):
            assert k in DRIVERS

    def test_drivers_sql_verbatim_from_spec(self):
        from utils.cost_allocation import DRIVERS
        assert DRIVERS["staff_count_by_segment"]["sql"] == \
            "COUNT(staff_code) WHERE segment = target"
        assert DRIVERS["loan_portfolio_value"]["sql"] == \
            "SUM(outstanding_balance) WHERE customer_segment = target"
        assert DRIVERS["deposit_balance"]["sql"] == \
            "SUM(balance) WHERE customer_segment = target"

    def test_ddl_has_spec_columns(self):
        from utils.cost_allocation import build_rules_table_ddl, ddl_contains_required_columns
        ddl = build_rules_table_ddl()
        check = ddl_contains_required_columns(ddl)
        assert check["valid"], f"missing: {check['missing']}"

    def test_validate_rule_passes_good(self):
        from utils.cost_allocation import validate_rule
        r = validate_rule({"cost_item": "X", "allocation_method": "driver_based",
                           "driver_1": "deposit_balance", "driver_1_weight": 1.0})
        assert r["valid"]

    def test_validate_rule_rejects_unknown_driver(self):
        from utils.cost_allocation import validate_rule
        r = validate_rule({"cost_item": "X", "allocation_method": "driver_based",
                           "driver_1": "made_up", "driver_1_weight": 1.0})
        assert not r["valid"]

    def test_validate_rule_rejects_bad_weights(self):
        from utils.cost_allocation import validate_rule
        r = validate_rule({"cost_item": "X", "allocation_method": "driver_based",
                           "driver_1": "deposit_balance", "driver_1_weight": 0.7,
                           "driver_2": "loan_portfolio_value", "driver_2_weight": 0.5})
        assert not r["valid"]
        assert any("sum to" in e for e in r["errors"])

    def test_catalog_validation(self):
        from utils.cost_allocation import validate_driver_catalog
        v = validate_driver_catalog()
        assert v["valid"]


# ═══════════════════════════════════════════════════════════════════════
# Standard #27 — Heatmap data
# ═══════════════════════════════════════════════════════════════════════

class TestStandard27:
    def test_axis_labels_match_spec(self):
        from utils.profitability_heatmap import build_heatmap_data
        r = build_heatmap_data(
            segment="X",
            period="2026-04",
            customers_in_segment_fn=lambda s: [],
        )
        # Even with empty data, axis labels are spec-literal
        assert r["x_axis"]["label"] == "PBT (KES)"
        assert r["y_axis"]["label"] == "Relationship Value"
        assert r["x_axis"]["dataKey"] == "pbt"
        assert r["y_axis"]["dataKey"] == "relationship_value"

    def test_empty_inputs_return_empty(self):
        from utils.profitability_heatmap import build_heatmap_data
        assert build_heatmap_data("", "2026-04") == {}
        assert build_heatmap_data("X", "") == {}

    def test_ftp_off_warning(self):
        from utils.profitability_heatmap import build_heatmap_data
        pnls = {("C1", "p1"): {"pbt": 100, "total_revenue": 200, "meta": {"ftp_mode": "off"}}}
        r = build_heatmap_data(
            segment="X",
            period="p1",
            customers_in_segment_fn=lambda s: ["C1"],
            pnl_lookup_fn=lambda c, p: pnls.get((c, p)),
        )
        assert r["data_quality_warning"] is not None
        assert "Mandatory Standard #11" in r["data_quality_warning"]


# ═══════════════════════════════════════════════════════════════════════
# Standard #28 — Trends
# ═══════════════════════════════════════════════════════════════════════

class TestStandard28:
    def test_spec_method_exists(self):
        from utils.profitability_trends import ProfitabilityTrends
        e = ProfitabilityTrends()
        assert hasattr(e, "analyze_customer_trend")

    def test_alert_fires_at_minus_15(self):
        """Spec rule: alert when direction==down AND percentage<-0.15."""
        from utils.profitability_trends import ProfitabilityTrends

        def lookup(c, p):
            i = int(p.split("-")[1]) - 1
            values = [100, 95, 90, 85, 80]
            if 0 <= i < 5:
                return {"pbt": values[i], "pbt_margin": 0.5,
                        "meta": {"ftp_mode": "on"}}
            return None

        e = ProfitabilityTrends(
            pnl_lookup_fn=lookup,
            period_list_fn=lambda n: [f"2026-{i+1:02d}" for i in range(min(n, 5))],
        )
        r = e.analyze_customer_trend("C1", periods=5)
        assert r["alert"]["fired"] is True

    def test_alert_does_not_fire_at_minus_10(self):
        from utils.profitability_trends import ProfitabilityTrends

        def lookup(c, p):
            i = int(p.split("-")[1]) - 1
            values = [100, 98, 96, 94, 90]
            if 0 <= i < 5:
                return {"pbt": values[i], "pbt_margin": 0.5,
                        "meta": {"ftp_mode": "on"}}
            return None

        e = ProfitabilityTrends(
            pnl_lookup_fn=lookup,
            period_list_fn=lambda n: [f"2026-{i+1:02d}" for i in range(min(n, 5))],
        )
        r = e.analyze_customer_trend("C1", periods=5)
        assert r["alert"]["fired"] is False

    def test_alert_suppressed_on_mixed_modes(self):
        """Honesty rule: alert suppressed when periods have mixed ftp_modes."""
        from utils.profitability_trends import ProfitabilityTrends

        def lookup(c, p):
            i = int(p.split("-")[1]) - 1
            values = [100, 95, 80, 75, 70]
            modes = ["off", "off", "on", "on", "on"]
            if 0 <= i < 5:
                return {"pbt": values[i], "pbt_margin": 0.5,
                        "meta": {"ftp_mode": modes[i]}}
            return None

        e = ProfitabilityTrends(
            pnl_lookup_fn=lookup,
            period_list_fn=lambda n: [f"2026-{i+1:02d}" for i in range(min(n, 5))],
        )
        r = e.analyze_customer_trend("C1", periods=5)
        assert r["alert"]["fired"] is False
        assert r["alert"]["suppressed"] is True
        assert "Mandatory Standard #11" in r["alert"]["reason"]


# ═══════════════════════════════════════════════════════════════════════
# Standard #29 — BSC integration
# ═══════════════════════════════════════════════════════════════════════

class TestStandard29:
    def test_strict_mode_skips_provisional(self):
        from utils.profitability_integration import submit_rm_profitability_to_bsc
        portfolios = {
            ("RM01", "p1"): {"portfolio_pnl": {"total_pbt": 100, "provisional": False}},
            ("RM02", "p1"): {"portfolio_pnl": {"total_pbt": 50,  "provisional": True}},
        }
        submitted = []
        r = submit_rm_profitability_to_bsc(
            period="p1",
            all_rms_fn=lambda: ["RM01", "RM02"],
            rm_portfolio_fn=lambda rm, p: portfolios.get((rm, p)),
            bsc_submit_fn=lambda **kw: submitted.append(kw) or True,
            submission_mode="strict",
        )
        assert r["submitted_count"] == 1
        assert len(r["skipped_provisional"]) == 1
        assert {s["staff_code"] for s in submitted} == {"RM01"}

    def test_warn_mode_flags_provisional(self):
        from utils.profitability_integration import submit_rm_profitability_to_bsc
        portfolios = {
            ("RM02", "p1"): {"portfolio_pnl": {"total_pbt": 50, "provisional": True}},
        }
        submitted = []
        r = submit_rm_profitability_to_bsc(
            period="p1",
            all_rms_fn=lambda: ["RM02"],
            rm_portfolio_fn=lambda rm, p: portfolios.get((rm, p)),
            bsc_submit_fn=lambda **kw: submitted.append(kw) or True,
            submission_mode="warn",
        )
        assert r["submitted_count"] == 1
        assert submitted[0].get("is_provisional") is True

    def test_kpi_id_is_spec_literal(self):
        from utils.profitability_integration import submit_rm_profitability_to_bsc, RM_PORTFOLIO_PBT_KPI_ID
        assert RM_PORTFOLIO_PBT_KPI_ID == "RM_PORTFOLIO_PBT"

        portfolios = {("RM01", "p1"): {"portfolio_pnl": {"total_pbt": 100, "provisional": False}}}
        submitted = []
        submit_rm_profitability_to_bsc(
            period="p1",
            all_rms_fn=lambda: ["RM01"],
            rm_portfolio_fn=lambda rm, p: portfolios.get((rm, p)),
            bsc_submit_fn=lambda **kw: submitted.append(kw) or True,
        )
        assert submitted[0]["kpi_id"] == "RM_PORTFOLIO_PBT"

    def test_invalid_mode_raises(self):
        from utils.profitability_integration import submit_rm_profitability_to_bsc
        with pytest.raises(ValueError):
            submit_rm_profitability_to_bsc(period="p1", submission_mode="bogus")

    def test_empty_period_returns_empty(self):
        from utils.profitability_integration import submit_rm_profitability_to_bsc
        assert submit_rm_profitability_to_bsc(period="") == {}


# ═══════════════════════════════════════════════════════════════════════
# Standard #30 — MD dashboard data
# ═══════════════════════════════════════════════════════════════════════

class TestStandard30:
    def test_dashboard_data_shape(self):
        from utils.profitability_integration import build_md_dashboard_data
        r = build_md_dashboard_data(
            period="p1",
            all_customers_fn=lambda: ["C1"],
            pnl_lookup_fn=lambda c, p: {"pbt": 1000, "total_revenue": 2000, "pbt_margin": 0.5,
                                          "meta": {"ftp_mode": "on"}},
            pyramid_fn=lambda p: {"tiers": {"platinum": {"count": 1}}},
            all_rms_fn=lambda: [],
            rm_portfolio_fn=lambda rm, p: None,
        )
        for k in ("total_customer_pbt", "profitable_customer_pct",
                  "pyramid_distribution", "rm_portfolios", "data_quality_summary"):
            assert k in r

    def test_profitable_pct_correct(self):
        from utils.profitability_integration import build_md_dashboard_data
        pnls = {
            ("C1", "p1"): {"pbt": 100, "pbt_margin": 0.5, "total_revenue": 200, "meta": {"ftp_mode": "on"}},
            ("C2", "p1"): {"pbt": -50, "pbt_margin": -0.1, "total_revenue": 500, "meta": {"ftp_mode": "on"}},
        }
        r = build_md_dashboard_data(
            period="p1",
            all_customers_fn=lambda: ["C1", "C2"],
            pnl_lookup_fn=lambda c, p: pnls.get((c, p)),
            pyramid_fn=lambda p: None,
            all_rms_fn=lambda: [],
            rm_portfolio_fn=lambda rm, p: None,
        )
        assert r["profitable_customer_count"] == 1
        assert r["profitable_customer_pct"] == 50.0

    def test_data_quality_warnings_rolled_up(self):
        from utils.profitability_integration import build_md_dashboard_data
        pnls = {
            ("C1", "p1"): {"pbt": 100, "total_revenue": 200, "meta": {"ftp_mode": "off"}},
        }
        r = build_md_dashboard_data(
            period="p1",
            all_customers_fn=lambda: ["C1"],
            pnl_lookup_fn=lambda c, p: pnls.get((c, p)),
            pyramid_fn=lambda p: None,
            all_rms_fn=lambda: [],
            rm_portfolio_fn=lambda rm, p: None,
        )
        warnings = r["data_quality_summary"]["warnings"]
        assert any("ftp_mode='off'" in w for w in warnings)
        assert any("Mandatory Standard #11" in w for w in warnings)

    def test_empty_period_returns_empty(self):
        from utils.profitability_integration import build_md_dashboard_data
        assert build_md_dashboard_data("") == {}


# ═══════════════════════════════════════════════════════════════════════
# Harness #1 — Allocation optimization correctness (G35)
# ═══════════════════════════════════════════════════════════════════════

def test_allocation_optimization_correctness_meets_99_percent():
    """Each labelled fixture has known-expected outcomes (total_projected_pbt
    or assignments_made or warning text). The harness asserts ≥99% match
    rate. Writes G35 artifact.
    """
    from utils.allocation_optimizer import CustomerAllocationOptimizer

    scenarios = json.loads(ALLOCATION_FIXTURES.read_text())
    assert len(scenarios) >= 10

    correct = 0
    results = []
    for s in scenarios:
        eng = _build_allocation_engine(s["input"])
        r = eng.optimize_rm_allocation(s["input"]["segment"])
        expected = s["expected"]

        ok = True
        diffs = []
        if "total_projected_pbt" in expected:
            actual = r.get("total_projected_pbt", 0)
            if abs(actual - expected["total_projected_pbt"]) > 0.5:
                ok = False
                diffs.append(f"total_projected_pbt={actual} vs {expected['total_projected_pbt']}")
        if "assignments_made" in expected:
            actual = (r.get("meta") or {}).get("assignments_made", 0)
            if actual != expected["assignments_made"]:
                ok = False
                diffs.append(f"assignments_made={actual} vs {expected['assignments_made']}")
        if "unassignable_count" in expected:
            actual = (r.get("meta") or {}).get("unassignable_count", 0)
            if actual != expected["unassignable_count"]:
                ok = False
                diffs.append(f"unassignable_count={actual} vs {expected['unassignable_count']}")
        if "provisional" in expected:
            if r.get("provisional") != expected["provisional"]:
                ok = False
                diffs.append(f"provisional={r.get('provisional')} vs {expected['provisional']}")
        if "warning_present" in expected:
            warn = r.get("data_quality_warning")
            present = warn is not None
            if present != expected["warning_present"]:
                ok = False
                diffs.append(f"warning_present={present} vs {expected['warning_present']}")
        if "warning_substring" in expected:
            if expected["warning_substring"] not in (r.get("data_quality_warning") or ""):
                ok = False
                diffs.append(f"warning_substring missing")
        if "total_potential_gain" in expected:
            actual = r.get("total_potential_gain", 0)
            if abs(actual - expected["total_potential_gain"]) > 0.5:
                ok = False
                diffs.append(f"total_potential_gain={actual} vs {expected['total_potential_gain']}")
        if "first_assignment_rm" in expected:
            asg = r.get("assignments") or []
            actual = asg[0]["rm_code"] if asg else None
            if actual != expected["first_assignment_rm"]:
                ok = False
                diffs.append(f"first_assignment_rm={actual} vs {expected['first_assignment_rm']}")

        if ok:
            correct += 1
        results.append({"id": s["id"], "matched": ok, "diffs": diffs})

    total = len(scenarios)
    accuracy = correct / total * 100
    artifact = {
        "schema_version":  1,
        "run_at":          datetime.now(timezone.utc).isoformat(),
        "total_scenarios": total,
        "correct":         correct,
        "accuracy_pct":    round(accuracy, 2),
        "spec_target_pct": 99.0,
        "all_passed":      accuracy >= 99.0,
        "results":         results,
    }
    ALLOCATION_RESULTS.write_text(json.dumps(artifact, indent=2))
    assert accuracy >= 99.0, f"correctness {accuracy:.1f}% < 99%; failures: " + \
        ", ".join(f"{r['id']}({r['diffs']})" for r in results if not r["matched"])


# ═══════════════════════════════════════════════════════════════════════
# Harness #2 — Trend analysis correctness (G36)
# ═══════════════════════════════════════════════════════════════════════

def test_trend_analysis_correctness_meets_99_percent():
    from utils.profitability_trends import ProfitabilityTrends

    scenarios = json.loads(TREND_FIXTURES.read_text())
    assert len(scenarios) >= 10

    correct = 0
    results = []
    for s in scenarios:
        values = s["input"]["values"]
        modes = s["input"]["ftp_modes"]

        def lookup(c, p, _v=values, _m=modes):
            i = int(p.split("-")[1]) - 1
            if 0 <= i < len(_v) and _v[i] is not None:
                return {"pbt": _v[i], "pbt_margin": 0.5,
                        "meta": {"ftp_mode": _m[i] if _m[i] else "unknown"}}
            return None

        eng = ProfitabilityTrends(
            pnl_lookup_fn=lookup,
            period_list_fn=lambda n, _v=values: [f"2026-{i+1:02d}" for i in range(min(n, len(_v)))],
        )
        r = eng.analyze_customer_trend("C1", periods=len(values))
        expected = s["expected"]

        ok = True
        diffs = []
        if "direction" in expected:
            if r["trend"]["direction"] != expected["direction"]:
                ok = False
                diffs.append(f"direction={r['trend']['direction']} vs {expected['direction']}")
        if "percentage_approx" in expected:
            actual = r["trend"]["percentage"]
            exp = expected["percentage_approx"]
            if exp is None:
                if actual is not None:
                    ok = False
                    diffs.append(f"percentage={actual} expected None")
            elif actual is None:
                ok = False
                diffs.append("percentage=None, expected number")
            else:
                if abs(actual - exp) > 0.01:
                    ok = False
                    diffs.append(f"percentage={actual} vs {exp}")
        if "alert_fired" in expected:
            if r["alert"]["fired"] != expected["alert_fired"]:
                ok = False
                diffs.append(f"alert_fired={r['alert']['fired']} vs {expected['alert_fired']}")
        if "alert_suppressed" in expected:
            if r["alert"]["suppressed"] != expected["alert_suppressed"]:
                ok = False
                diffs.append(f"alert_suppressed={r['alert']['suppressed']} vs {expected['alert_suppressed']}")
        if "alert_message_substring" in expected:
            if expected["alert_message_substring"] not in (r["alert"]["message"] or ""):
                ok = False
                diffs.append("alert_message_substring missing")
        if "alert_reason_substring" in expected:
            if expected["alert_reason_substring"] not in (r["alert"]["reason"] or ""):
                ok = False
                diffs.append("alert_reason_substring missing")
        if "warning_present" in expected:
            warn = r.get("data_quality_warning")
            present = warn is not None
            if present != expected["warning_present"]:
                ok = False
                diffs.append(f"warning_present={present} vs {expected['warning_present']}")
        if "periods_with_data" in expected:
            actual = r["meta"]["periods_with_data"]
            if actual != expected["periods_with_data"]:
                ok = False
                diffs.append(f"periods_with_data={actual} vs {expected['periods_with_data']}")

        if ok:
            correct += 1
        results.append({"id": s["id"], "matched": ok, "diffs": diffs})

    total = len(scenarios)
    accuracy = correct / total * 100
    artifact = {
        "schema_version":  1,
        "run_at":          datetime.now(timezone.utc).isoformat(),
        "total_scenarios": total,
        "correct":         correct,
        "accuracy_pct":    round(accuracy, 2),
        "spec_target_pct": 99.0,
        "all_passed":      accuracy >= 99.0,
        "results":         results,
    }
    TREND_RESULTS.write_text(json.dumps(artifact, indent=2))
    assert accuracy >= 99.0, f"correctness {accuracy:.1f}% < 99%; failures: " + \
        ", ".join(f"{r['id']}({r['diffs']})" for r in results if not r["matched"])
